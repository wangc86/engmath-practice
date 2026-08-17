"""出題頁與 HTMX 片段。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, func, select

from ..db.models import Student, UsageLog
from ..db.session import engine
from ..generator import (
    DIFFICULTY_LABELS,
    GenerationError,
    generate,
    list_templates,
)
from .deps import current_student, templates

router = APIRouter()


def _log(student_id: int, template_id: str, difficulty: int, seed: int,
         action: str = "generate") -> None:
    with Session(engine) as session:
        session.add(
            UsageLog(
                student_id=student_id,
                template_id=template_id,
                difficulty=difficulty,
                seed=seed,
                action=action,
            )
        )
        session.commit()


def _usage_summary(student_id: int) -> dict:
    """學生自己的用量摘要（老師的班級版本留待階段 4）。"""
    with Session(engine) as session:
        total = session.exec(
            select(func.count()).select_from(UsageLog).where(
                UsageLog.student_id == student_id,
                UsageLog.action == "generate",
            )
        ).one()
        rows = session.exec(
            select(UsageLog.template_id, func.count())
            .where(
                UsageLog.student_id == student_id,
                UsageLog.action == "generate",
            )
            .group_by(UsageLog.template_id)
        ).all()
    names = {t.template_id: t.name for t in list_templates()}
    by_template = [(names.get(tid, tid), n) for tid, n in rows]
    by_template.sort(key=lambda r: -r[1])
    return {"total": total, "by_template": by_template}


@router.get("/", response_class=HTMLResponse)
def index(request: Request, student: Student = Depends(current_student)):
    return templates.TemplateResponse(
        request,
        "practice.html",
        {
            "student": student,
            "templates_list": list_templates(),
            "difficulty_labels": DIFFICULTY_LABELS,
            "usage": _usage_summary(student.id),
        },
    )


@router.post("/practice/generate", response_class=HTMLResponse)
def generate_problem(
    request: Request,
    template_id: str = Form(...),
    difficulty: int = Form(...),
    student: Student = Depends(current_student),
):
    """HTMX 端點：回傳一段題目卡片的 HTML 片段。"""
    try:
        problem = generate(template_id, difficulty)
    except (KeyError, ValueError) as exc:
        return templates.TemplateResponse(
            request, "_error.html", {"message": f"Invalid selection: {exc}"}, status_code=400
        )
    except GenerationError:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "Could not generate a valid problem this time. Please press Generate again."},
            status_code=503,
        )

    _log(student.id, template_id, difficulty, problem.seed)

    return templates.TemplateResponse(
        request,
        "_problem.html",
        {
            "problem": problem,
            "template_name": next(
                t.name for t in list_templates() if t.template_id == template_id
            ),
            "difficulty_label": DIFFICULTY_LABELS[difficulty],
            "usage": _usage_summary(student.id),
        },
    )
