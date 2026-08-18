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
from .grader import warm_up as warm_up_grader
from .routes import auth, practice
from .routes.deps import NotLoggedIn, redirect_to_login

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 判定用的子行程先叫起來，讓第一位交卷的學生不必等 sympy 的 import
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
    return {"status": "ok"}
