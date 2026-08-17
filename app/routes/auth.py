"""註冊、登入、登出。

安全要點（PLAN.md §4.3）：
- 密碼以 argon2id 雜湊，絕不存明碼。
- 登入失敗訊息統一為「學號或密碼錯誤」，避免帳號列舉。
- 註冊頁強制顯示「請勿使用學校信箱／校務系統密碼」的警告。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from ..config import LOGIN_RATE_LIMIT, REGISTER_RATE_LIMIT
from ..db.models import Student
from ..db.session import engine
from ..security import (
    RateLimiter,
    hash_password,
    needs_rehash,
    normalize_student_no,
    validate_password,
    validate_student_no,
    verify_password,
)
from .deps import client_ip, templates

router = APIRouter()

login_limiter = RateLimiter(*LOGIN_RATE_LIMIT)
register_limiter = RateLimiter(*REGISTER_RATE_LIMIT)

LOGIN_FAILED = "Incorrect student ID or password."


def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx)


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    if request.session.get("student_id"):
        return RedirectResponse("/", status_code=303)
    return _render(request, "register.html")


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    student_no: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    consent: str = Form(""),
):
    student_no = normalize_student_no(student_no)

    def fail(msg: str):
        # 注意：回填學號但**不回填密碼**
        return _render(request, "register.html", error=msg, student_no=student_no)

    if not register_limiter.allow(client_ip(request)):
        return fail("Too many registration attempts. Please try again later.")

    if (err := validate_student_no(student_no)) is not None:
        return fail(err)
    if consent != "on":
        return fail("Please read and accept the data collection notice.")
    if password != password_confirm:
        return fail("The two passwords do not match.")
    if (err := validate_password(password, student_no)) is not None:
        return fail(err)

    with Session(engine) as session:
        exists = session.exec(
            select(Student).where(Student.student_no == student_no)
        ).first()
        if exists is not None:
            return fail("That student ID is already registered. Please log in instead.")

        now = datetime.now(timezone.utc)
        student = Student(
            student_no=student_no,
            password_hash=hash_password(password),
            consent_at=now,
            last_login_at=now,
        )
        session.add(student)
        session.commit()
        session.refresh(student)
        request.session["student_id"] = student.id

    return RedirectResponse("/", status_code=303)


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

    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
