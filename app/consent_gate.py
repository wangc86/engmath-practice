"""個資告知的強制閘門（D33）。

**問題**：`/register` 移除之後（D32），個資告知沒有地方顯示，`consent_at`
也沒有東西可以填。解法是把告知移到「第一次登入之後」——但那只有在
**沒有辦法繞過**的前提下才算數。

**為什麼是 middleware，不是一個 `Depends`。**
用相依注入寫（例如 `current_student()` 裡多一個檢查）在功能上是等價的，
但它的正確性依賴「每一個路由都記得掛上那個相依」。這個專案已經有兩個
功能區、日後還會有第三個（對話介面），而**漏掉一個 `Depends` 不會讓任何
測試變紅，也不會拋錯——它只會安靜地開一個洞**。middleware 的預設值反過來：
**沒有被明確豁免的路徑一律擋下**，新增路由時什麼都不必記得。

豁免清單刻意極短，而且每一項都有理由：

- `/login`、`/logout`：還沒登入的人要進得來，登入了的人要出得去。
  **`/logout` 特別重要**——不放行的話，一個不想同意的學生會被困在
  告知頁上，連登出都做不到。不同意就離開必須是一個做得到的選項。
- `/consent`：閘門本身。不豁免就是無窮迴圈。
- `/healthz`：監控用，不碰任何學生資料。
- `/static/*`：告知頁自己要載入 CSS。

`tests/test_web.py::test_no_route_is_reachable_before_consent` 會**列舉 app
上所有已註冊的路由**逐一嘗試，因此日後新增的端點如果忘了考慮這件事，
測試會直接紅燈——豁免清單以外的東西一律擋，是被驗證過的，不是靠紀律。
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from .db.models import Student
from .db.session import engine
from .logging_setup import get_logger

logger = get_logger(__name__)

CONSENT_PATH = "/consent"

#: 完整比對的豁免路徑。理由見模組說明——這份清單短是刻意的。
EXEMPT_PATHS = frozenset({"/login", "/logout", CONSENT_PATH, "/healthz"})

#: 前綴比對的豁免路徑。
EXEMPT_PREFIXES = ("/static/",)


def _has_consented(student_id: int) -> bool:
    """查資料庫，不查 session。

    把「已同意」快取進 session cookie 可以省下每個請求一次查詢，但那份快取
    是**學生的瀏覽器持有**的，而這道閘門存在的理由正是「不能被繞過」。
    一次以主鍵查 SQLite 的成本在這個規模（同時 30 人）是可以忽略的，
    拿它去換一個必須信任用戶端的最佳化不划算。
    """
    with Session(engine) as session:
        student = session.exec(
            select(Student).where(Student.id == student_id)
        ).first()
    return student is not None and student.consent_at is not None


class ConsentGateMiddleware(BaseHTTPMiddleware):
    """已登入但尚未確認個資告知的人，一律導向 `/consent`。

    ⚠️ **掛載順序有意義**：這個 middleware 需要 `request.session`，所以
    `SessionMiddleware` 必須在它**外面**。Starlette 是「後加入的在外層」，
    因此 `main.py` 必須先 `add_middleware(ConsentGateMiddleware)`、
    再 `add_middleware(SessionMiddleware)`。順序反了的症狀是
    `AssertionError: SessionMiddleware must be installed`。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        student_id = request.session.get("student_id")
        if student_id is None:
            # 未登入。這裡不處理——導向登入頁是路由自己的相依項在做的事
            # （`NotLoggedIn`），在這裡多做一次只會讓兩處的行為必須同步。
            return await call_next(request)

        if _has_consented(student_id):
            return await call_next(request)

        if request.headers.get("hx-request"):
            # HTMX 的請求收到 303 會把整頁告知塞進題目卡片的位置。
            # `HX-Redirect` 讓瀏覽器做一次真正的整頁跳轉。
            return Response(status_code=204, headers={"HX-Redirect": CONSENT_PATH})

        return RedirectResponse(CONSENT_PATH, status_code=303)
