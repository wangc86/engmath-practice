"""出題頁、我的紀錄與 HTMX 片段。

題目**不存進資料庫**：`(template_id, difficulty, seed)` 三個值就能用
`generator.generate()` 重現同一題，因此用量紀錄只留這三個值。好處是沒有題庫表
要維護、任何一筆紀錄永遠可重現。

**v0.7（D12）：作答判定已捨棄。** 這個檔案原本還有 `/practice/submit`
（判定一次作答）與 `/practice/solution`（另外要逐步解答），兩個都移除了：

- `/practice/submit` 沒有東西可以做了。
- `/practice/solution` 是為了「解答不能隨題目一起送到瀏覽器，否則按 F12 就看得到」
  而存在的。有判定的時候那是硬性要求（貼上答案就能拿到 Correct）；沒有判定之後，
  提前看到答案的唯一後果是自己少練到一題，因此改用 `<details>` 收合，
  答案與逐步解答隨題目一起送出（D13，取捨寫在 PLAN.md §5.8 與 `_problem.html`）。

保留在 tag `grading-v1`。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, func, select

from ..db.models import Student, UsageLog
from ..db.session import engine
from ..generator import (
    DIFFICULTY_LABELS,
    GenerationError,
    Problem,
    generate,
    list_templates,
)
from ..logging_setup import get_logger
from .deps import current_student, templates

logger = get_logger(__name__)

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
        "usage": _usage_summary(student.id),
    }


def _error(request: Request, message: str, status_code: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": message}, status_code=status_code
    )


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
    """HTMX 端點：回傳一段題目卡片的 HTML 片段。

    片段裡包含答案與逐步解答，但兩者都在收合的 `<details>` 裡（D13）。
    """
    try:
        problem = generate(template_id, difficulty)
    except (KeyError, ValueError) as exc:
        return _error(request, f"Invalid selection: {exc}", 400)
    except GenerationError:
        # 學生只看到「再按一次」，但這其實是出題引擎在該難度下重抽多次都沒過
        # 驗證閘門——若某個題型反覆出現，那是模板的參數範圍出了問題。
        logger.warning(
            "出題失敗：template=%s difficulty=%s（重抽多次都沒通過殘差驗證）。"
            "偶爾一次是正常的；若集中在某個題型請檢查它的參數範圍。",
            template_id, difficulty,
        )
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


@router.get("/progress", response_class=HTMLResponse)
def progress(request: Request, student: Student = Depends(current_student)):
    """「我的紀錄」：只顯示登入者本人的資料。

    v0.7（D12）起這頁只有**用量**，沒有正確率——系統不判定答案，也就沒有
    「對幾題」這件事。老師仍然要看用量（D1 的主要交付），所以頁面保留。
    """
    names = {t.template_id: t.name for t in list_templates()}
    with Session(engine) as session:
        recent = session.exec(
            select(UsageLog)
            .where(
                UsageLog.student_id == student.id,
                UsageLog.action == "generate",
            )
            .order_by(UsageLog.created_at.desc(), UsageLog.id.desc())
            .limit(50)
        ).all()

    usage = _usage_summary(student.id)
    return templates.TemplateResponse(
        request,
        "progress.html",
        {
            "student": student,
            "recent": [
                {
                    "when": log.created_at,
                    "name": names.get(log.template_id, log.template_id),
                    "difficulty": log.difficulty,
                    "difficulty_label": DIFFICULTY_LABELS.get(log.difficulty, ""),
                }
                for log in recent
            ],
            "by_template": [
                {"name": name, "count": count}
                for name, count in usage["by_template"]
            ],
            "total": usage["total"],
        },
    )
