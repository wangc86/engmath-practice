"""共用的 Jinja2 環境與登入相依項。"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..db.models import Student
from ..db.session import engine

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# autoescape 預設開啟，且範本中不使用 |safe 處理使用者輸入
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class NotLoggedIn(Exception):
    """未登入時丟出，由 main.py 的 exception handler 轉為導向登入頁。"""


def current_student(request: Request) -> Student:
    student_id = request.session.get("student_id")
    if student_id is None:
        raise NotLoggedIn()
    with Session(engine) as session:
        student = session.exec(
            select(Student).where(Student.id == student_id)
        ).first()
    if student is None:                    # 帳號已被刪除，清掉殘留的 session
        request.session.clear()
        raise NotLoggedIn()
    return student


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
