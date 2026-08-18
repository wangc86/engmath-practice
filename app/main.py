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

from .config import COOKIE_SECURE, SESSION_MAX_AGE, SESSION_SECRET
from .db.session import init_db
from .grader import shutdown as shutdown_grader
from .grader import status as grader_status
from .grader import warm_up as warm_up_grader
from .logging_setup import configure_logging
from .routes import auth, practice
from .routes.deps import NotLoggedIn, redirect_to_login

STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    # 判定用的子行程先叫起來，讓第一位交卷的學生不必等 sympy 的 import。
    # 這一步也是啟動自檢：叫不起來就**讓啟動失敗**（D8）。判定沒有子行程就沒有
    # 硬性 timeout，而那是一個誰都能觸發的阻斷服務漏洞，不該安靜地帶著上線。
    warm_up_grader()
    try:
        yield
    finally:
        shutdown_grader()


app = FastAPI(title="工程數學練習系統", lifespan=lifespan, docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=COOKIE_SECURE,     # 正式環境（HTTPS）請設 COOKIE_SECURE=1
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(practice.router)


@app.exception_handler(NotLoggedIn)
async def _not_logged_in(request: Request, exc: NotLoggedIn):
    return redirect_to_login()


@app.get("/healthz")
def healthz():
    """存活檢查，順便回報判定子行程池的狀態（README「運維」一節）。

    只讀旗標、不送工作進去，所以可以被監控每分鐘打一次。
    """
    return {"status": "ok", "grader": grader_status()}
