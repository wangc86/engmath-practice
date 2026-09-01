"""開放閘門：沒有被明確分類過的路徑，學生一律進不去（PLAN.md D55）。

## 為什麼是 middleware，而不是每個路由掛一個 `Depends`

與 D33／D37 選 middleware 的論證逐字相同，換掉主詞之後仍然成立：

> 用相依注入寫在功能上是等價的，但它的正確性依賴「每一個路由都記得掛上
> 那個相依」，而**漏掉一個不會拋錯、不會讓任何測試變紅——它只會安靜地
> 開一個洞**。middleware 的預設值反過來：**沒有被明確分類的路徑一律擋下**。

在這個功能上，那個洞的形狀特別惡劣：漏掉一個路由的症狀是「某一週的內容
提早開放了」，而**頁面完全正常**——沒有錯誤、沒有例外，只是一批還沒教的
題目出現在學生的選單上，而改程式的人（知道那個題型存在）不會覺得哪裡不對。
這與規則 5（忘記收合答案）是同一類缺陷。

---

## ⚠️ 但 middleware 判不了全部，而那個例外必須寫出來

`POST /practice/generate` 的內容代號在 **表單 body 裡**，不在路徑上。
middleware 讀得到 body 嗎？技術上可以，但 `BaseHTTPMiddleware` 一旦把
`receive` 讀掉，下游的路由就再也拿不到 body（症狀是請求掛住，不是報錯）。
繞過的寫法（buffer 之後自己重放 `receive`）是可行的，但它把一個
「多一行檢查」的問題換成「自己實作 ASGI 協定的一小段」，而那一段出錯的
方式比它要防的東西還安靜。

**因此這裡的作法是**：那條路徑被列在 `SELF_GATED_PATHS` 裡，
middleware 放行，改由 `routes/practice.py` 自己呼叫 `release.visible_ids()`。
這是一個**明示的例外**，不是一個遺漏——而它由兩件事看守：

1. `tests/test_release.py::test_every_route_is_classified_for_release_gating`
   會列舉 app 上**所有**已註冊的路由，斷言每一條都落在下面三份清單之一，
   而且**把三份清單的內容逐字釘住**（改清單就要回頭改測試，改測試的人
   會先讀到這一段）。
2. `test_no_closed_topic_can_be_generated_by_url` 對 14 個題型逐一真的
   打一次 `POST`，確認關著的時候拿不到題目——也就是那個「自己守」
   真的有在守。

## 三份清單

* `UNGATED_PATHS`／`UNGATED_PREFIXES`——**不含任何週次相關內容**的路徑。
  它們可能有別的門（`/activity` 與 `/admin/content` 是 staff 限定），
  但週次開放與它們無關。
* `SELF_GATED_PATHS`——內容代號在 body 裡，由路由自己判定（見上）。
* 展示頁 `/demos/<group>/<name>`——**由這個 middleware 直接判定**，
  因為代號完全由路徑決定。

其餘一律**擋下**。

## 擋下來的樣子

* 展示頁關著 → 404 加一句英文說明。**刻意不回 403「這一頁存在但沒開放」**：
  那句話本身就洩漏了「有這麼一頁」，而 D24 的精神是系統不主動報告
  自己還有什麼沒拿出來。老師若要學生知道，他會在課堂上說。
* 沒有分類過的路徑 → 同樣 404，**但在 log 裡留一行 WARNING**（規則 4）。
  ⚠️ 學生打錯網址也會走到這裡，所以那一行不見得代表程式有問題；
  訊息裡因此寫明了兩種可能，免得看到的人以為系統壞了。

## staff 完全不受這道閘門影響

老師要在按下「開放」之前先自己點進去看一眼。理由與代價寫在
`release.visible_ids()`。
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from .db.models import ROLE_STAFF, Account
from .db.session import engine
from .logging_setup import get_logger
from .release import is_released

logger = get_logger(__name__)

#: 完整比對：不含任何週次相關內容的路徑。
#:
#: ⚠️ 每加一條都要問一次「這條路徑吐得出某一週的內容嗎」。加錯的成本是
#: 提早開放，而那是安靜的。`/` 與 `/demos` 在清單上，是因為那兩頁**自己**
#: 依開放狀態過濾要列出什麼（見 `routes/practice.py::index` 與
#: `routes/demos.py::index`）——它們沒有內容，只有一份清單。
UNGATED_PATHS = frozenset({
    "/",                 # 出題頁：選單自己過濾
    "/login",
    "/logout",
    "/healthz",
    "/demos",            # 展示索引：清單自己過濾
    "/activity",         # staff 限定，統計全部歷史用量（不受開放狀態影響）
    "/admin/content",    # staff 限定，這道閘門的管理頁本身
})

#: 前綴比對。
UNGATED_PREFIXES = ("/static/",)

#: 內容代號在 POST body 裡，由路由自己判定。理由見模組說明。
SELF_GATED_PATHS = frozenset({"/practice/generate"})

#: 展示頁的路徑前綴。這底下的東西由本 middleware 直接判定。
DEMO_PREFIX = "/demos/"


def _demo_id_for_path(path: str) -> str | None:
    """`/demos/<group>/<name>` → 該展示的 `template_id`；不是展示就回 `None`。

    ⚠️ **在函式裡 import，不在模組頂端。** `routes/demos.py` 會 import
    `routes/deps.py`，而測試每換一個資料庫就把那一串模組重新載入一次；
    頂端 import 會讓這個 middleware 抓著一份舊的 `DEMOS`。
    這裡查的是純資料（`slug` → `template_id`），重新查一次很便宜。
    """
    from .routes.demos import DEMOS

    slug = path[len(DEMO_PREFIX):].strip("/")
    for demo in DEMOS:
        if demo.slug == slug:
            return demo.template_id
    return None


def _account_for(request: Request) -> Account | None:
    """從 session 取帳號。查資料庫，理由同 `login_gate._account_exists()`。"""
    account_id = request.session.get("account_id")
    if account_id is None:
        return None
    with Session(engine) as session:
        return session.exec(
            select(Account).where(Account.id == account_id)
        ).first()


class ContentNotReleased(Exception):
    """學生要求了一項還沒開放的內容。由 `main.py` 轉成 404 頁面。

    ⚠️ 這個例外**只有 `routes/practice.py` 用得到**（它是自己守的那一條）。
    middleware 這一側不丟例外——它已經在路由外面，直接回一個 response
    比較短，而且丟例外會在 `BaseHTTPMiddleware` 裡變成 500。
    """


class ReleaseGateMiddleware(BaseHTTPMiddleware):
    """未開放的內容，學生直接打網址也拿不到。

    ⚠️ **掛載順序有意義**：它要在 `SessionMiddleware` 裡面（需要
    `request.session`），也要在 `LoginGateMiddleware` 裡面（未登入的人
    應該先被導去登入頁，而不是先被告知某一頁不存在）。
    `main.py` 那張圖是權威，`tests/test_web.py::test_middleware_order` 盯著。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in UNGATED_PATHS or path.startswith(UNGATED_PREFIXES):
            return await call_next(request)

        account = _account_for(request)
        if account is None:
            # 未登入。登入閘門在更外層，正常情況下走不到這裡；真的走到了
            # 就放行，讓那一層去處理（兩層各自獨立，不互相假設）。
            return await call_next(request)

        if account.role == ROLE_STAFF:
            return await call_next(request)

        if path in SELF_GATED_PATHS:
            return await call_next(request)

        if path.startswith(DEMO_PREFIX):
            content_id = _demo_id_for_path(path)
            if content_id is None:
                # 不是任何一個展示。可能是打錯網址，也可能是**新加的一頁
                # 忘了登記進 DEMOS**——後者若放行就是一個洞，所以擋下來。
                return self._not_here(request)
            if is_released(content_id):
                return await call_next(request)
            return self._not_here(request)

        logger.warning(
            "學生要求了一條沒有被分類過的路徑：%s。"
            "若這是一條新加的路由，請把它加進 app/release_gate.py 的三份清單之一"
            "（並回頭改 tests/test_release.py 那項列舉測試）；"
            "若只是打錯網址，這一行可以忽略。",
            path,
        )
        return self._not_here(request)

    def _not_here(self, request: Request) -> HTMLResponse:
        """一律 404，且不透露「這一頁存在但沒開放」（D24 的分寸）。

        ⚠️ 這裡自己建一個 `Jinja2Templates`，不 import `routes/deps.py`
        的那一個——理由與 `_demo_id_for_path()` 相同（測試會重新載入
        那個模組）。範本是同一個檔案，成本只是多一個 loader。
        """
        from .routes.deps import TEMPLATES_DIR

        return Jinja2Templates(directory=str(TEMPLATES_DIR)).TemplateResponse(
            request,
            "_error.html",
            {
                "message": (
                    "There is nothing at this address. If you are looking for "
                    "something from this week, it may not have been opened "
                    "yet — your instructor opens each week's material as the "
                    "course reaches it."
                )
            },
            status_code=404,
        )
