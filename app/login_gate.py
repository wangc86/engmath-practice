"""登入閘門：沒有被明確豁免的路徑，一律要求先登入（D37）。

## 這個檔案的來歷

v0.15 它叫 `consent_gate.py`，擋的是「還沒讀過個資告知的人」（D33）。
v0.16 系統不再蒐集任何個人資料（D35），告知義務隨之消失，那道閘門
本來應該一起拆掉——**但拆掉的是它擋的東西，不是它的形狀**。

保留形狀是刻意的，因為 D33 當初選 middleware 而不是 `Depends` 的那段論證
與「擋什麼」無關，逐字換掉主詞之後仍然成立：

> 用相依注入寫（例如每個路由掛 `Depends(current_account)`）在功能上是等價的，
> 但它的正確性依賴「每一個路由都記得掛上那個相依」。這個專案已經有兩個
> 功能區、日後還會有第三個（對話介面），而**漏掉一個 `Depends` 不會讓任何
> 測試變紅，也不會拋錯——它只會安靜地開一個洞**。middleware 的預設值反過來：
> **沒有被明確豁免的路徑一律擋下**，新增路由時什麼都不必記得。

換掉主詞之後洞的嚴重性其實**降低**了（漏掉的後果從「個資告知被繞過」變成
「一個未登入的人看得到出題頁」），但成本是零——這個檔案已經寫好了，
留著只要改三個字。刪掉它再過半年重新發現需要它，才是貴的那個選項。

## 豁免清單

刻意極短，每一項都有理由：

- `/login`：還沒登入的人要進得來。
- `/logout`：登入了的人要出得去。
- `/healthz`：監控用，不碰任何資料。
- `/static/*`：登入頁自己要載入 CSS。

`/consent` 從清單上消失了——那一頁不存在了（D37）。

`tests/test_web.py::test_no_route_is_reachable_without_logging_in` 會**列舉
app 上所有已註冊的路由**逐一嘗試，因此日後新增的端點如果忘了考慮這件事，
測試會直接紅燈——豁免清單以外的東西一律擋，是被驗證過的，不是靠紀律。
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from .db.models import Account
from .db.session import engine
from .logging_setup import get_logger

logger = get_logger(__name__)

LOGIN_PATH = "/login"

#: 完整比對的豁免路徑。理由見模組說明——這份清單短是刻意的。
EXEMPT_PATHS = frozenset({LOGIN_PATH, "/logout", "/healthz"})

#: 前綴比對的豁免路徑。
EXEMPT_PREFIXES = ("/static/",)


def _account_exists(account_id: int) -> bool:
    """查資料庫，不查 session。

    把「這個 session 有效」快取進 cookie 可以省下每個請求一次查詢，但那份
    快取是**用戶端持有**的，而這道閘門存在的理由正是「不能被繞過」。
    一次以主鍵查 SQLite 的成本在這個規模（同時 30 人）可以忽略。

    另外它處理了一個真的會發生的狀況：老師砍掉資料庫重建之後，學生瀏覽器裡
    那個舊 session 的 `account_id` 會指向一列不存在的資料。不查的話，
    那個人會通過閘門、然後在某個路由裡拿到 None 而炸掉。
    """
    with Session(engine) as session:
        account = session.exec(
            select(Account).where(Account.id == account_id)
        ).first()
    return account is not None


class LoginGateMiddleware(BaseHTTPMiddleware):
    """未登入者一律導向 `/login`。

    ⚠️ **掛載順序有意義**：這個 middleware 需要 `request.session`，所以
    `SessionMiddleware` 必須在它**外面**。Starlette 是「後加入的在外層」，
    因此 `main.py` 必須先 `add_middleware(LoginGateMiddleware)`、
    再 `add_middleware(SessionMiddleware)`。順序反了的症狀是
    `AssertionError: SessionMiddleware must be installed`。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        account_id = request.session.get("account_id")
        if account_id is not None and _account_exists(account_id):
            return await call_next(request)

        if account_id is not None:
            # session 裡有 id 但資料庫查不到：清掉，否則他會一直被彈回登入頁
            # 而 cookie 裡那個死掉的 id 永遠不會消失。
            logger.info(
                "session 指向一個不存在的帳號（資料庫可能被重建過），已清除該 session。"
            )
            request.session.clear()

        if request.headers.get("hx-request"):
            # HTMX 的請求收到 303 會把整頁登入表單塞進題目卡片的位置。
            # `HX-Redirect` 讓瀏覽器做一次真正的整頁跳轉。
            return Response(status_code=204, headers={"HX-Redirect": LOGIN_PATH})

        return RedirectResponse(LOGIN_PATH, status_code=303)
