"""出題頁、全班活動頁與 HTMX 片段。

題目**不存進資料庫**：`(template_id, difficulty, seed)` 三個值就能用
`generator.generate()` 重現同一題，因此用量紀錄只留這三個值。

**v0.7（D12）：作答判定已捨棄**（`/practice/submit` 與 `/practice/solution`
移除，保存在 tag `grading-v1`）。

**v0.16（D36、D39）：「我的紀錄」變成「全班活動」，而且換了讀者。**

這一節值得寫下來，因為它不是改個標題而已：

- 舊的 `/progress` 回答的是「**我**練了多少」。共用帳號之後那個問題
  **問不出來了**——系統不知道誰是誰，這正是 D35 想要的結果。
- 同一份查詢現在回答的是「**全班**練了多少」。那是一個老師的問題，
  不是學生的問題：學生看到「全班這週出了 380 題」既不知道自己佔幾題，
  也無從據以行動；它唯一穩定的效果是製造一個沒有人解釋得清楚的數字。
- 因此頁面搬到 `/activity`、只有 staff 帳號進得去（`Depends(staff_account)`），
  而首頁那個「我練了幾題」的側欄面板整個拿掉（`_usage.html` 隨之下架）。

`ROLE_STAFF` 的用量**不計入**任何一個數字：老師改一頁版面會重新整理十幾次，
那十幾列足以讓「這週學生練了幾題」失真。這是 `UsageLog.account_id` 留著的
唯一理由，也是它唯一的用途。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, func, select

from ..db.models import ROLE_CLASS, Account, UsageLog
from ..db.session import engine
from ..generator import (
    DIFFICULTY_LABELS,
    GenerationError,
    Problem,
    generate,
    list_templates,
)
from ..logging_setup import get_logger
from .demos import DEMO_ACTION, DEMOS
from .deps import current_account, staff_account, templates

logger = get_logger(__name__)

router = APIRouter()


def _log(account_id: int, template_id: str, difficulty: int, seed: int,
         action: str = "generate") -> None:
    with Session(engine) as session:
        session.add(
            UsageLog(
                account_id=account_id,
                template_id=template_id,
                difficulty=difficulty,
                seed=seed,
                action=action,
            )
        )
        session.commit()


def _class_account_id() -> int | None:
    """全班共用帳號的 id。查不到就回 None，並且**說出來**（規則 4）。

    查不到是一個真的會發生的狀況：老師只建了 staff 帳號就先自己試用。
    那時全班活動頁上的每一個數字都會是 0，而 0 與「還沒有人用」長得一模一樣
    ——所以差別必須寫在 log 裡，也寫在頁面上（`activity.html` 的空狀態）。
    """
    with Session(engine) as session:
        account_id = session.exec(
            select(Account.id).where(Account.role == ROLE_CLASS)
        ).first()
    if account_id is None:
        logger.warning(
            "資料庫裡沒有全班共用帳號（role=%s），全班活動頁的數字全部會是 0。"
            "請執行 `python scripts/create_accounts.py init` 建立它。",
            ROLE_CLASS,
        )
    return account_id


def _class_usage(class_id: int | None) -> dict:
    """全班的出題用量（不含 staff）。"""
    if class_id is None:
        return {"total": 0, "by_template": []}
    with Session(engine) as session:
        total = session.exec(
            select(func.count()).select_from(UsageLog).where(
                UsageLog.action == "generate",
                UsageLog.account_id == class_id,
            )
        ).one()
        rows = session.exec(
            select(UsageLog.template_id, func.count())
            .where(
                UsageLog.action == "generate",
                UsageLog.account_id == class_id,
            )
            .group_by(UsageLog.template_id)
        ).all()
    names = {t.template_id: t.name for t in list_templates()}
    by_template = [(names.get(tid, tid), n) for tid, n in rows]
    by_template.sort(key=lambda r: -r[1])
    return {"total": total, "by_template": by_template}


def _class_demo_usage(class_id: int | None) -> list[dict]:
    """全班開過哪些展示、各幾次（§8.7）。

    獨立的查詢而不是塞進 `_class_usage()`：那個摘要的分母是「出了幾題」，
    把展示的次數混進同一個總數會讓兩個數字都失去意義。
    """
    if class_id is None:
        return []
    with Session(engine) as session:
        rows = session.exec(
            select(UsageLog.template_id, func.count())
            .where(
                UsageLog.action == DEMO_ACTION,
                UsageLog.account_id == class_id,
            )
            .group_by(UsageLog.template_id)
        ).all()
    titles = {demo.template_id: demo.title for demo in DEMOS}
    summary = [
        {"name": titles.get(template_id, template_id), "count": count}
        for template_id, count in rows
    ]
    summary.sort(key=lambda row: -row["count"])
    return summary


def _excluded_row_count(class_id: int | None) -> int:
    """沒有被算進上面數字的列數（＝ staff 帳號寫的）。

    印在全班活動頁上是刻意的：老師需要看得出「我自己測試的那些也在資料庫裡，
    只是沒有算進上面的數字」。不印的話，`UsageLog` 的總列數與頁面上的總數
    對不起來，而對不起來又沒有解釋，就會讓人懷疑統計是不是漏了東西。
    """
    with Session(engine) as session:
        query = select(func.count()).select_from(UsageLog)
        if class_id is not None:
            query = query.where(UsageLog.account_id != class_id)
        return session.exec(query).one()


def _template_name(template_id: str) -> str:
    return next(
        (t.name for t in list_templates() if t.template_id == template_id),
        template_id,
    )


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
def index(request: Request, account: Account = Depends(current_account)):
    return templates.TemplateResponse(
        request,
        "practice.html",
        {
            "account": account,
            "templates_list": list_templates(),
            "difficulty_labels": DIFFICULTY_LABELS,
        },
    )


@router.post("/practice/generate", response_class=HTMLResponse)
def generate_problem(
    request: Request,
    template_id: str = Form(...),
    difficulty: int = Form(...),
    account: Account = Depends(current_account),
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

    _log(account.id, template_id, difficulty, problem.seed)
    return templates.TemplateResponse(
        request, "_problem.html", _problem_context(problem)
    )


@router.get("/activity", response_class=HTMLResponse)
def activity(request: Request, account: Account = Depends(staff_account)):
    """全班活動：彙總數字，沒有任何一列指得到人（D36、D39）。

    ⚠️ **這一頁刻意沒有「最近的紀錄」列表。** 舊的 `/progress` 有一張
    「最近 50 題」的表（時間、題型、難度）。逐列的時間戳在共用帳號之下是
    這個系統裡**最接近可識別資訊**的東西：知道某個人幾點在教室裡的人，
    可以從一列 14:32 的紀錄推回去。彙總數字沒有這個性質，而老師實際要問的
    問題（哪個題型被練得多、有沒有人在用）彙總就答得了。
    """
    class_id = _class_account_id()
    usage = _class_usage(class_id)
    return templates.TemplateResponse(
        request,
        "activity.html",
        {
            "account": account,
            "by_template": [
                {"name": name, "count": count}
                for name, count in usage["by_template"]
            ],
            "total": usage["total"],
            "demos": _class_demo_usage(class_id),
            "excluded_rows": _excluded_row_count(class_id),
            "class_account_missing": class_id is None,
        },
    )
