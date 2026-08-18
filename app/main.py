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
from .logging_setup import configure_logging
from .routes import auth, practice
from .routes.deps import NotLoggedIn, redirect_to_login

STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動與關閉。

    v0.7（D12）起這裡只剩建表。判定的子行程暖機與 fail-fast 自檢（D6／D8／D10）
    隨作答判定一起移除——那套機制存在的唯一理由是「要在獨立、殺得掉的行程裡
    執行學生給的表達式」，而系統已經不再執行任何不可信輸入。
    出題只吃 (template_id, difficulty, seed) 三個經過檢查的值。
    """
    configure_logging()
    init_db()
    yield


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
    """存活檢查。很便宜，可以讓監控每分鐘打一次。

    v0.7（D12）：原本會一併回報判定子行程池的狀態（`warmed_up`、`busy`、
    `spawned_total`…）。判定移除後沒有那個子系統可以報，這裡回到只證明
    「進程活著、路由掛得起來」。
    """
    return {"status": "ok"}
