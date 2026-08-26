"""登入與登出。就這兩件事。

**v0.16（D35）：這個檔案少了三個端點，而且都是刻意的。**

- `/register`（v0.15，D32 移除）——沒有自行註冊。
- `/consent` 的 GET 與 POST（v0.16，D37 移除）——系統不再蒐集個人資料，
  沒有告知義務，也就沒有同意這件事。
- `/account/password` 的 GET 與 POST（v0.16，D35 移除）——**這一個要特別
  講清楚**：密碼是全班共用的，因此「學生自行修改密碼」在新的前提下不是一個
  便利功能，是一個**任何一個學生都能把全班鎖在門外的按鈕**。D34 當初的
  論證（讓老師手上那份明碼對照表會過期）也一起失效了，因為那份對照表
  不存在了——密碼只印在終端機上一次。改密碼改由老師執行：
  `python scripts/create_accounts.py reset class`。

安全要點（PLAN.md §4.3）：

- 密碼以 argon2id 雜湊，絕不存明碼。
- 登入失敗訊息統一為「帳號或密碼錯誤」，避免帳號列舉。
- 「這不是學校官方系統」的警告在登入頁（`_about.html`）。告知頁沒有了之後，
  那是它唯一的落點，而它**不能一起消失**——見 `app/templates/_about.html`。
- 速率限制是**全站共用的一個計數器**，不分帳號、不看來源 IP。
  理由與代價寫在 `config.LOGIN_RATE_LIMIT`（簡言之：每 IP 會誤傷 NAT 後面
  的整班，每帳號會讓一個人的手滑鎖住全班，而系統不碰 IP 是 D38）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from ..config import LOGIN_RATE_LIMIT
from ..db.models import Account
from ..db.session import engine
from ..security import (
    RateLimiter,
    hash_password,
    needs_rehash,
    normalize_account_name,
    verify_password,
)
from .deps import templates

router = APIRouter()

login_limiter = RateLimiter(*LOGIN_RATE_LIMIT)

#: 速率限制的 key。**固定字串**——這是全站一個計數器，而不是「以某個東西
#: 分組的計數器」。寫成常數是為了讓「這裡不會偷偷變成 IP」看得出來。
LOGIN_LIMIT_KEY = "login"

LOGIN_FAILED = "Incorrect account name or password."


def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("account_id"):
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    account: str = Form(""),
    password: str = Form(""),
):
    account_name = normalize_account_name(account)

    def fail(msg: str = LOGIN_FAILED):
        return _render(request, "login.html", error=msg, account=account_name)

    if not login_limiter.allow(LOGIN_LIMIT_KEY):
        return fail("Too many login attempts. Please try again in a minute.")

    with Session(engine) as session:
        row = session.exec(
            select(Account).where(Account.name == account_name)
        ).first()
        # 帳號不存在與密碼錯誤回傳同一則訊息，避免帳號列舉
        if row is None or not verify_password(row.password_hash, password):
            return fail()

        if needs_rehash(row.password_hash):
            row.password_hash = hash_password(password)
        # 「最後一次有人登入的時間」，不是「他上次登入」——帳號是共用的。
        row.last_login_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        request.session["account_id"] = row.id

    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
