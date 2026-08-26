"""共用的 Jinja2 環境與登入相依項。"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..db.models import ROLE_STAFF, Account
from ..db.session import engine

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# autoescape 預設開啟，且範本中不使用 |safe 處理使用者輸入
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class NotLoggedIn(Exception):
    """未登入時丟出，由 main.py 的 exception handler 轉為導向登入頁。

    ⚠️ 正常情況下**不會**走到這裡：`app/login_gate.py` 的 middleware 已經
    在路由之前把未登入的請求擋掉了。留著它是因為那個 middleware 與這裡
    各自獨立——middleware 若哪天被誤改（例如豁免清單多了一項），
    路由這一側仍然不會把資料吐出去。兩層都在的成本是一次主鍵查詢。
    """


class NotStaff(Exception):
    """只有老師／助教帳號能看的頁面（D39）。"""


def session_account(request: Request) -> Account | None:
    """從 session 取出帳號，**取不到就回 None，不丟例外**。"""
    account_id = request.session.get("account_id")
    if account_id is None:
        return None
    with Session(engine) as session:
        account = session.exec(
            select(Account).where(Account.id == account_id)
        ).first()
    if account is None:                    # 帳號已被刪除，清掉殘留的 session
        request.session.clear()
    return account


def current_account(request: Request) -> Account:
    account = session_account(request)
    if account is None:
        raise NotLoggedIn()
    return account


def staff_account(request: Request) -> Account:
    """老師／助教帳號限定。

    **不假裝那一頁不存在。** 回 404 可以少洩漏一點資訊，但這裡沒有東西
    值得隱藏（頁面上是全班的彙總數字，不是誰的資料），而假裝不存在會讓一個
    點錯連結的人以為系統壞了。回 403 並說清楚是誰能看，比較誠實（D24 的
    誠實原則：不主動多說，但說出來的每一句都要是真的）。
    """
    account = current_account(request)
    if account.role != ROLE_STAFF:
        raise NotStaff()
    return account


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)
