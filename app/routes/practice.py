"""出題頁與 HTMX 片段。**這個檔案現在只有兩個端點。**

題目**不存進任何地方**：`(template_id, difficulty, seed)` 三個值就能用
`generator.generate()` 重現同一題，而 v0.29 之後連那三個值都不留——
系統跑在使用者自己的電腦上，沒有資料庫，關掉就什麼都不剩。

---

## v0.29（D57、D58、D59）：這個檔案少了三樣東西

- **`/activity`（全班活動）整個移除。** 它彙總的是 `UsageLog`，而那張表
  沒有了（D58）。老師改用別的方式了解學生怎麼使用（他自己的評估方式，
  例如請學生錄影操作），**系統這一側不再蒐集任何東西**。
- **`_log()` 與 `UsageLog` 的寫入移除。** 同上。
- **登入相依 `Depends(current_account)` 移除**（D57）。本機單人使用，
  一道問「你是誰」的門擋不住任何人。

## 週次分組（D52 的殘存用途，D59）

下拉選單依**課程週次**分組，不依章節。學生找東西的動機是「這週上課提到的
那個」（§7 #34 早就寫過），而 `Template.chapter`（"First-Order ODEs"）
回答的是另一個問題。

⚠️ **`chapter` 欄位沒有拿掉**，它仍然是 `list_templates()` 的排序鍵之一，
而且對讀程式碼的人有用。改的只是「畫面上用哪一個分組」。
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..curriculum import KIND_PRACTICE, ids_for_week, weeks_with_content
from ..generator import (
    DIFFICULTY_LABELS,
    GenerationError,
    Problem,
    generate,
    list_templates,
)
from ..logging_setup import get_logger
from .deps import templates

logger = get_logger(__name__)

router = APIRouter()


def _template_name(template_id: str) -> str:
    return next(
        (t.name for t in list_templates() if t.template_id == template_id),
        template_id,
    )


def _weekly_groups() -> list[dict]:
    """下拉選單的分組：每一週一個 `<optgroup>`，裡面是那一週的題型。

    ⚠️ **名稱從註冊表現查，不從 `curriculum.py` 拿**——後者只認得字串。
    抄一份名稱過去就是第二真相，而漂移的症狀是選單上的名字與題目卡片上的
    名字不一樣，兩邊都不會報錯。
    """
    by_id = {t.template_id: t for t in list_templates()}
    groups = []
    for week in weeks_with_content(KIND_PRACTICE):
        rows = [
            by_id[cid] for cid in ids_for_week(week.number, KIND_PRACTICE)
            if cid in by_id
        ]
        if rows:
            groups.append({
                "label": f"Week {week.number} — {week.topic}",
                "templates": rows,
            })
    return groups


def _problem_context(problem: Problem) -> dict:
    return {
        "problem": problem,
        "template_name": _template_name(problem.template_id),
        "difficulty_label": DIFFICULTY_LABELS[problem.difficulty],
    }


def _error(request: Request, message: str, status_code: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": message}, status_code=status_code
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "practice.html",
        {
            "weekly_groups": _weekly_groups(),
            "templates_list": list_templates(),
            "difficulty_labels": DIFFICULTY_LABELS,
        },
    )


@router.post("/practice/generate", response_class=HTMLResponse)
def generate_problem(
    request: Request,
    template_id: str = Form(...),
    difficulty: int = Form(...),
):
    """HTMX 端點：回傳一段題目卡片的 HTML 片段。

    片段裡包含答案與逐步解答，但兩者都在收合的 `<details>` 裡（D13）。
    """
    try:
        problem = generate(template_id, difficulty)
    except (KeyError, ValueError) as exc:
        return _error(request, f"Invalid selection: {exc}", 400)
    except GenerationError:
        # 使用者只看到「再按一次」，但這其實是出題引擎在該難度下重抽多次都沒過
        # 驗證閘門——若某個題型反覆出現，那是模板的參數範圍出了問題。
        logger.warning(
            "出題失敗：template=%s difficulty=%s（重抽多次都沒通過驗證閘門）。"
            "偶爾一次是正常的；若集中在某個題型請檢查它的參數範圍。",
            template_id, difficulty,
        )
        return _error(
            request,
            "Could not generate a valid problem this time. Please press "
            "Generate again.",
            503,
        )

    return templates.TemplateResponse(
        request, "_problem.html", _problem_context(problem)
    )
