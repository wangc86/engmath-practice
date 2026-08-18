"""作答判定（PLAN.md §5）。

對外只有一個入口 :func:`grade_submission`。它負責把判定丟進子行程執行、
套用 timeout，並把任何意外都轉成一則學生看得懂的 :class:`Verdict`
——**這一層不會拋例外**，因為呼叫端是 Web 端點，不該因為某個學生打了
奇怪的東西就回 500。

模組分工：

    parse.py        學生輸入 → SymPy（字元白名單、長度與複雜度上限）
    equivalence.py  「是不是 0」與「常數是不是獨立」
    core.py         判定流程（跑在子行程裡）
    feedback.py     判定結果 → 英文回饋文字
    sandbox.py      子行程與 timeout
"""

from __future__ import annotations

import time

from ..config import MAX_ANSWER_LENGTH
from ..generator.base import Problem
from . import feedback
from .core import Verdict, grade
from .sandbox import GradingTimeout, call, shutdown, warm_up

__all__ = [
    "Verdict",
    "grade_submission",
    "shutdown",
    "warm_up",
]


def grade_submission(problem: Problem, raw: str) -> tuple[Verdict, int]:
    """判定一次作答，回傳 (判定結果, 耗時毫秒)。

    ``problem`` 由 (template_id, difficulty, seed) 重新生成而來，因此不需要
    題庫表；送進子行程的只有 `problem.check`、標準答案與學生的原始字串。
    """
    started = time.monotonic()
    text = (raw or "")[: MAX_ANSWER_LENGTH + 1]      # 先砍一刀，避免搬運超大字串
    try:
        verdict = call(grade, problem.check, problem.answer_expr, text)
    except GradingTimeout:
        verdict = Verdict.of("timeout", feedback.TIMEOUT_DETAIL)
    except Exception:                                # noqa: BLE001 - 端點不得因此 500
        verdict = Verdict.of("internal_error", feedback.INTERNAL_DETAIL)
    return verdict, int((time.monotonic() - started) * 1000)
