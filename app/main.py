"""FastAPI 進入點。

啟動方式見 README.md：
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .access_log import AccessLogMiddleware
from .config import COOKIE_SECURE, SESSION_MAX_AGE, SESSION_SECRET
from .db.session import init_db
from .logging_setup import configure_access_logging, configure_logging
from .login_gate import LoginGateMiddleware
from .routes import auth, demos, practice
from .routes.deps import NotLoggedIn, NotStaff, redirect_to_login, templates

STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動與關閉。

    v0.7（D12）起這裡只剩建表。判定的子行程暖機與 fail-fast 自檢（D6／D8／D10）
    隨作答判定一起移除。

    **v0.16（D38）新增一件事：接管 uvicorn 的存取紀錄。**
    它必須在這裡做而不是在模組層級，因為 uvicorn 是在 `Server.run()` 裡設定
    logging 的——那個時點在這個模組被 import **之後**。在 import 時做等於白做，
    而白做的症狀是「終端機上每一行都印著學生的 IP，但程式碼裡看不出是誰印的」。
    """
    configure_logging()
    configure_access_logging()
    init_db()
    yield


app = FastAPI(title="工程數學練習系統", lifespan=lifespan, docs_url=None, redoc_url=None)

# ⚠️ 這三行的順序有意義，不要對調。
# Starlette 是「後加入的在外層」，因此實際的執行順序是由下往上：
#
#   AccessLogMiddleware（最外層，量得到完整耗時、也記得到被閘門擋掉的請求）
#     └─ SessionMiddleware（要在閘門外面，閘門需要 request.session）
#          └─ LoginGateMiddleware
#
# 順序反了的症狀：Session 在閘門裡面 → 每個請求都拋
# `AssertionError: SessionMiddleware must be installed`；
# 存取紀錄在最內層 → 被閘門擋掉的請求完全不會出現在紀錄裡。
# `tests/test_web.py::test_middleware_order` 盯著。
app.add_middleware(LoginGateMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=COOKIE_SECURE,     # 正式環境（HTTPS）請設 COOKIE_SECURE=1
)

app.add_middleware(AccessLogMiddleware)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(practice.router)
# 第二個功能區（PLAN.md §8）。與出題引擎只共用登入與 UsageLog（D21）。
app.include_router(demos.router)


@app.exception_handler(NotLoggedIn)
async def _not_logged_in(request: Request, exc: NotLoggedIn):
    return redirect_to_login()


@app.exception_handler(NotStaff)
async def _not_staff(request: Request, exc: NotStaff):
    """D39：全班活動頁只有 staff 帳號看得到。

    回 403 並說清楚，不假裝那一頁不存在——理由見 `routes/deps.py::staff_account`。
    """
    return templates.TemplateResponse(
        request,
        "_error.html",
        {
            "message": (
                "This page is only available to the course staff account. "
                "If you are taking this course, there is nothing for you here."
            )
        },
        status_code=403,
    )


@app.get("/healthz")
def healthz():
    """存活檢查。很便宜，可以讓監控每分鐘打一次。"""
    return {"status": "ok"}
