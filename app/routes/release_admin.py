"""老師的內容開放管理頁 `/admin/content`（PLAN.md D53、§4.3a）。

**這是老師每週會用一次的東西，不是儀表板。** 因此它刻意只有一頁、一張表單、
沒有 HTMX、沒有 JavaScript、沒有圖表：

* 依課程週次分組，每一週一個區塊，區塊裡是那一週的內容（核取方塊）。
* 每一週有一組 **Open week / Close week** 按鈕——開學後每週要操作一次，
  逐項點二十下不可持續。
* 最下面一個 **Save** 按鈕，語意是「開放的就是現在勾起來的這些」。

### 三個按鈕的語意，以及為什麼是這樣

整張表單一起送出，所以三個按鈕拿到的都是**畫面上當下的勾選狀態**：

* `save` —— 開放 = 勾起來的那些。
* `open-week:N` —— 開放 = 勾起來的那些 **∪** 第 N 週的全部。
* `close-week:N` —— 開放 = 勾起來的那些 **−** 第 N 週的全部。

⚠️ 關鍵在於後兩者**以畫面上的勾選為基礎，而不是以資料庫為基礎**。
反過來寫（「忽略勾選，只對資料庫做加減」）會有一個安靜的失敗：老師先手動
改了三個核取方塊、再按「開放第 5 週」，那三個改動會**無聲消失**——
頁面重新載入之後看起來很正常，只是他剛剛做的事沒有發生。

### 為什麼不做「Close everything」

想過，沒做。它只在兩個時機有用（學期結束、換一屆重來），而兩個時機
都不趕時間；而它按錯一次的代價是全班的內容在上課中途消失。
逐週關比較慢，但慢得剛剛好。

---

## D21 的界線

這個檔案 import 了 `app.generator`（拿題型名稱）**與** `app.routes.demos`
（拿展示標題）。那不違反 D21——D21 禁止的是「兩個功能區共用抽象」，
而這裡沒有抽象：它把兩份清單各自的**顯示名稱**抓過來排版，就像
`/activity` 已經在做的事（`practice.py` 早就 import 了 `demos.DEMOS`）。
歸類本身住在 `app/curriculum.py`，那個檔案兩邊都不 import。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..curriculum import (
    WEEKS,
    ContentItem,
    borrowed_ids_for_week,
    ids_for_week,
    item_for,
    week_label,
)
from ..db.models import Account
from ..logging_setup import get_logger
from ..release import released_ids, set_released, updated_at_by_id
from .demos import DEMOS
from .deps import staff_account, templates

logger = get_logger(__name__)

router = APIRouter(prefix="/admin")

ADMIN_PATH = "/admin/content"


def _display_names() -> dict[str, str]:
    """`content_id` → 給人看的英文名稱。

    ⚠️ **每次呼叫都重新組，不做成模組層級的常數。** 測試會把
    `routes.demos` 重新載入，而模組層級的字典會抓著舊的那一份；
    更實際的理由是註冊表在 import 時才長齊，而這個模組可能先被載入。
    """
    from ..generator import list_templates

    names = {t.template_id: t.name for t in list_templates()}
    names.update({demo.template_id: demo.title for demo in DEMOS})
    return names


def _row(item: ContentItem, names: dict, open_now: frozenset[str],
         stamps: dict) -> dict:
    """管理頁上的一列。`content_id` 查不到名字時就印代號本身。

    查不到會發生在「`curriculum.CONTENT` 有一列，但那個題型被移除了」的
    情況下。印代號比印空白好——空白看起來像排版壞了，代號看得出是誰。
    `tests/test_release.py` 有一項測試確保正常情況下不會發生。
    """
    stamp = stamps.get(item.content_id)
    return {
        "content_id": item.content_id,
        "name": names.get(item.content_id, item.content_id),
        "kind": item.kind,
        "week_label": week_label(item),
        "is_multi_week": item.is_multi_week,
        "is_open": item.content_id in open_now,
        "updated_at": stamp.strftime("%Y-%m-%d %H:%M UTC") if stamp else "",
    }


def _page_context(request: Request, account: Account) -> dict:
    names = _display_names()
    open_now = released_ids()
    stamps = updated_at_by_id()

    weeks = []
    for week in WEEKS:
        owned = [item_for(cid) for cid in ids_for_week(week.number)]
        borrowed = [item_for(cid) for cid in borrowed_ids_for_week(week.number)]
        weeks.append({
            "number": week.number,
            "topic": week.topic,
            "rows": [_row(i, names, open_now, stamps) for i in owned if i],
            # 「別週擁有、本週也用得到」的項目，唯讀。沒有它的話 W12／W13
            # 看起來會像忘了做內容，而實際上它們與 W10 共用同一批題型。
            "borrowed": [
                {
                    "name": names.get(i.content_id, i.content_id),
                    "owner_week": i.release_week,
                    "is_open": i.content_id in open_now,
                }
                for i in borrowed if i
            ],
            "open_count": sum(
                1 for i in owned if i and i.content_id in open_now
            ),
        })

    from ..curriculum import ALL_CONTENT_IDS

    return {
        "account": account,
        "weeks": weeks,
        "open_total": len(open_now),
        "content_total": len(ALL_CONTENT_IDS),
        "opened": request.query_params.get("opened"),
        "closed": request.query_params.get("closed"),
    }


@router.get("/content", response_class=HTMLResponse)
def content_admin(request: Request, account: Account = Depends(staff_account)):
    return templates.TemplateResponse(
        request, "admin_content.html", _page_context(request, account)
    )


@router.post("/content", response_class=HTMLResponse)
def update_content(
    request: Request,
    account: Account = Depends(staff_account),
    action: str = Form("save"),
    open: list[str] = Form(default=[]),          # noqa: A002 - 表單欄位名
):
    """存檔後 **303 導回 GET**（Post/Redirect/Get）。

    不直接回傳頁面是為了讓重新整理不會把同一份表單再送一次——那在這裡
    不會造成損害（覆寫是幂等的），但它會讓瀏覽器跳出「要重新送出嗎」，
    而老師每週都要面對一次那個對話框。
    """
    wanted = set(open)

    if action.startswith("open-week:") or action.startswith("close-week:"):
        verb, _, raw = action.partition(":")
        try:
            week = int(raw)
        except ValueError:
            # 表單被改過。不靜默吞掉（規則 4），但也不必壞掉——當成 save。
            logger.warning("管理頁收到看不懂的週次：%r，當成單純存檔處理。", action)
            week = None
        if week is not None:
            batch = set(ids_for_week(week))
            if not batch:
                logger.info("第 %d 週目前沒有任何內容，%s 沒有東西可做。", week, verb)
            wanted = wanted | batch if verb == "open-week" else wanted - batch

    opened, closed = set_released(wanted)
    return RedirectResponse(
        f"{ADMIN_PATH}?opened={opened}&closed={closed}", status_code=303
    )
