"""出題頁、作答判定與 HTMX 片段。

題目**不存進資料庫**：`(template_id, difficulty, seed)` 三個值就能用
`generator.generate()` 重現同一題，因此題目卡片把它們放在隱藏欄位裡，
作答與看解答時再重新生成一次。好處是沒有題庫表要維護、紀錄永遠可重現；
代價是每次提交多花約 0.1 秒重新出題，在本系統的量級下無所謂。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import case
from sqlmodel import Session, func, select

from ..config import SUBMIT_RATE_LIMIT
from ..db.models import Attempt, Student, UsageLog
from ..db.session import engine
from ..generator import (
    DIFFICULTY_LABELS,
    GenerationError,
    Problem,
    generate,
    list_templates,
)
from ..grader import grade_submission
from ..security import RateLimiter
from .deps import current_student, templates

router = APIRouter()

submit_limiter = RateLimiter(*SUBMIT_RATE_LIMIT)

MAX_SEED = 2**31 - 1


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


def _template_name(template_id: str) -> str:
    return next(
        (t.name for t in list_templates() if t.template_id == template_id),
        template_id,
    )


def _problem_context(problem: Problem, student: Student) -> dict:
    return {
        "problem": problem,
        "template_name": _template_name(problem.template_id),
        "difficulty_label": DIFFICULTY_LABELS[problem.difficulty],
        "answer_kind": problem.check.kind if problem.check else "scalar",
        "usage": _usage_summary(student.id),
    }


def _error(request: Request, message: str, status_code: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": message}, status_code=status_code
    )


def _reproduce(template_id: str, difficulty: int, seed: int) -> Problem:
    """由 (題型, 難度, seed) 重現一題。參數不合法時丟 ValueError/KeyError。"""
    if not 0 < seed <= MAX_SEED:
        raise ValueError("seed out of range")
    return generate(template_id, difficulty, seed=seed)


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
        return _error(request, f"Invalid selection: {exc}", 400)
    except GenerationError:
        return _error(
            request,
            "Could not generate a valid problem this time. Please press "
            "Generate again.",
            503,
        )

    _log(student.id, template_id, difficulty, problem.seed)
    return templates.TemplateResponse(
        request, "_problem.html", _problem_context(problem, student)
    )


@router.post("/practice/submit", response_class=HTMLResponse)
def submit_answer(
    request: Request,
    template_id: str = Form(...),
    difficulty: int = Form(...),
    seed: int = Form(...),
    answer: str = Form(""),
    student: Student = Depends(current_student),
):
    """HTMX 端點：判定一次作答，回傳回饋片段。

    判定本身跑在子行程裡並套用 timeout（見 app/grader/sandbox.py），
    因此這個端點不會被病態輸入卡住。
    """
    if not submit_limiter.allow(str(student.id)):
        return _error(
            request,
            "You are submitting very quickly. Please wait a moment and try again.",
            429,
        )
    try:
        problem = _reproduce(template_id, difficulty, seed)
    except (KeyError, ValueError):
        return _error(request, "This problem could not be reloaded. Please "
                               "generate a new one.", 400)
    except GenerationError:
        return _error(request, "This problem could not be reloaded. Please "
                               "generate a new one.", 503)

    verdict, duration_ms = grade_submission(problem, answer)

    with Session(engine) as session:
        session.add(
            Attempt(
                student_id=student.id,
                template_id=template_id,
                difficulty=difficulty,
                seed=seed,
                params_json=_jsonable(problem.params),
                submitted_raw=(answer or "")[:1000],
                verdict=verdict.code,
                is_correct=verdict.correct,
                is_partial=verdict.partial,
                duration_ms=duration_ms,
            )
        )
        session.commit()

    context = _problem_context(problem, student)
    context["verdict"] = verdict
    context["submitted"] = answer
    return templates.TemplateResponse(request, "_feedback.html", context)


@router.post("/practice/solution", response_class=HTMLResponse)
def show_solution(
    request: Request,
    template_id: str = Form(...),
    difficulty: int = Form(...),
    seed: int = Form(...),
    student: Student = Depends(current_student),
):
    """顯示逐步解答。

    解答刻意**不隨題目一起送到瀏覽器**：一來這樣「先自己算」才有意義
    （否則按 F12 就看得到），二來「看了解答」是重要的學習訊號，
    要能被記錄下來（UsageLog.action = view_solution，PLAN.md §4.2）。
    """
    try:
        problem = _reproduce(template_id, difficulty, seed)
    except (KeyError, ValueError, GenerationError):
        return _error(request, "This problem could not be reloaded. Please "
                               "generate a new one.", 400)

    _log(student.id, template_id, difficulty, seed, action="view_solution")
    return templates.TemplateResponse(
        request, "_solution.html", {"problem": problem}
    )


@router.get("/progress", response_class=HTMLResponse)
def progress(request: Request, student: Student = Depends(current_student)):
    """「我的紀錄」：只顯示登入者本人的資料。"""
    names = {t.template_id: t.name for t in list_templates()}
    with Session(engine) as session:
        recent = session.exec(
            select(Attempt)
            .where(Attempt.student_id == student.id)
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
            .limit(50)
        ).all()
        rows = session.exec(
            select(
                Attempt.template_id,
                func.count(),
                func.sum(case((Attempt.is_correct, 1), else_=0)),
                func.sum(case((Attempt.is_partial, 1), else_=0)),
            )
            .where(Attempt.student_id == student.id)
            .group_by(Attempt.template_id)
        ).all()

    by_template = [
        {
            "name": names.get(tid, tid),
            "attempts": total,
            "correct": correct or 0,
            "partial": partial or 0,
            "rate": round(100 * (correct or 0) / total) if total else 0,
        }
        for tid, total, correct, partial in rows
    ]
    by_template.sort(key=lambda r: -r["attempts"])

    return templates.TemplateResponse(
        request,
        "progress.html",
        {
            "student": student,
            "recent": [
                {
                    "when": a.created_at,
                    "name": names.get(a.template_id, a.template_id),
                    "difficulty": a.difficulty,
                    "answer": a.submitted_raw,
                    "verdict": a.verdict,
                    "is_correct": a.is_correct,
                    "is_partial": a.is_partial,
                }
                for a in recent
            ],
            "by_template": by_template,
            "total": sum(r["attempts"] for r in by_template),
        },
    )


def _jsonable(value):
    """params 裡可能夾帶 SymPy 物件，一律轉成 JSON 存得下的形式。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)
