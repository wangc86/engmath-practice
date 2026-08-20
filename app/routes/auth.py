"""登入、登出、個資告知同意、自行修改密碼。

**v0.15（D32）：`/register` 已移除。** 帳號由老師用
`scripts/create_accounts.py` 預先建立並把初始密碼配發給修課學生，
系統不再接受任何人自己開帳號。這個檔案原本有 `register_form()` 與
`register()` 兩個端點，以及它們共用的 `register_limiter`，全部拿掉了。

安全要點（PLAN.md §4.3）：
- 密碼以 argon2id 雜湊，絕不存明碼。
- 登入失敗訊息統一為「學號或密碼錯誤」，避免帳號列舉。
- 「請勿使用學校信箱／校務系統密碼」的警告，過去在註冊頁；註冊頁沒有了之後，
  它移到**個資告知頁**（第一次登入必經）與登入頁（較小字體重述）。

三個新端點（v0.15）：

- `GET/POST /consent`（D33）——第一次登入後強制顯示個資告知，確認後才寫入
  `Student.consent_at`。**未確認前不得使用任何功能**，這件事由
  `app/consent_gate.py` 的 middleware 強制，不是靠這裡的檢查。
- `GET/POST /account/password`（D34）——學生自行修改密碼。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from ..config import LOGIN_RATE_LIMIT, PASSWORD_CHANGE_RATE_LIMIT
from ..db.models import Student
from ..db.session import engine
from ..security import (
    RateLimiter,
    hash_password,
    needs_rehash,
    normalize_student_no,
    validate_password,
    verify_password,
)
from .deps import client_ip, current_student, session_student, templates

router = APIRouter()

login_limiter = RateLimiter(*LOGIN_RATE_LIMIT)
password_limiter = RateLimiter(*PASSWORD_CHANGE_RATE_LIMIT)

LOGIN_FAILED = "Incorrect student ID or password."


def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx)


# --- 登入／登出 -----------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("student_id"):
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    student_no: str = Form(""),
    password: str = Form(""),
):
    student_no = normalize_student_no(student_no)

    def fail(msg: str = LOGIN_FAILED):
        return _render(request, "login.html", error=msg, student_no=student_no)

    if not login_limiter.allow(client_ip(request)):
        return fail("Too many login attempts. Please try again later.")
    if not login_limiter.allow(f"user:{student_no}"):
        return fail("Too many login attempts. Please try again later.")

    with Session(engine) as session:
        student = session.exec(
            select(Student).where(Student.student_no == student_no)
        ).first()
        # 帳號不存在與密碼錯誤回傳同一則訊息，避免帳號列舉
        if student is None or not verify_password(student.password_hash, password):
            return fail()

        if needs_rehash(student.password_hash):
            student.password_hash = hash_password(password)
        student.last_login_at = datetime.now(timezone.utc)
        session.add(student)
        session.commit()
        request.session["student_id"] = student.id

    # 導向 "/" 而不是直接判斷要不要去 /consent：那個判斷只能有一個地方做，
    # 就是 consent_gate 的 middleware（D33）。在這裡再判斷一次，等於製造
    # 第二個必須同步維護的真相來源——而兩份會分岔的規則裡，會被繞過的
    # 一定是比較嚴格的那一份。
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- 個資告知與同意（D33）-------------------------------------------------

@router.get("/consent", response_class=HTMLResponse)
def consent_form(request: Request):
    """第一次登入後的個資告知頁。

    這一頁是 `/register` 消失之後告知義務（個資法第 8 條）的落點：告知文字
    原本在註冊表單裡，註冊頁一移除，學生就再也看不到它，`consent_at` 也
    沒有東西可以填。措辭與蒐集項目一字未改，只是換了出現的時機。
    """
    student = session_student(request)
    if student is None:
        return RedirectResponse("/login", status_code=303)
    if student.consent_at is not None:
        return RedirectResponse("/", status_code=303)
    return _render(request, "consent.html", student_no=student.student_no)


@router.post("/consent", response_class=HTMLResponse)
def consent(request: Request, consent: str = Form("")):
    student = session_student(request)
    if student is None:
        return RedirectResponse("/login", status_code=303)
    if student.consent_at is not None:
        return RedirectResponse("/", status_code=303)

    if consent != "on":
        return _render(
            request,
            "consent.html",
            student_no=student.student_no,
            error="Please read and accept the data collection notice to continue.",
        )

    with Session(engine) as session:
        row = session.exec(
            select(Student).where(Student.id == student.id)
        ).first()
        if row is None:                       # 帳號在讀告知的期間被刪掉了
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        row.consent_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()

    return RedirectResponse("/", status_code=303)


# --- 自行修改密碼（D34）---------------------------------------------------

@router.get("/account/password", response_class=HTMLResponse)
def password_form(request: Request, student: Student = Depends(current_student)):
    return _render(request, "password.html", student=student)


@router.post("/account/password", response_class=HTMLResponse)
def change_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    student: Student = Depends(current_student),
):
    def fail(msg: str):
        # 三個欄位一個都不回填——它們全都是密碼。
        return _render(request, "password.html", student=student, error=msg)

    if not password_limiter.allow(f"user:{student.student_no}"):
        return fail("Too many attempts. Please try again later.")

    if not verify_password(student.password_hash, current_password):
        # 這裡不必擔心帳號列舉（人已經登入了），但仍然不說「舊密碼錯在哪」。
        return fail("Your current password is not correct.")
    if new_password != new_password_confirm:
        return fail("The two new passwords do not match.")
    if new_password == current_password:
        return fail("Your new password must be different from the current one.")
    if (err := validate_password(new_password, student.student_no)) is not None:
        return fail(err)

    with Session(engine) as session:
        row = session.exec(select(Student).where(Student.id == student.id)).first()
        if row is None:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        row.password_hash = hash_password(new_password)
        session.add(row)
        session.commit()

    # session 刻意保留：改密碼不是重新登入。把人踢回登入頁只會讓他懷疑
    # 自己是不是改壞了，而這裡沒有「其他裝置可能被盜用」的情境需要處理
    # （14 天的 session cookie 本來就綁在這台瀏覽器上）。
    return _render(
        request,
        "password.html",
        student=student,
        success="Your password has been changed.",
    )
