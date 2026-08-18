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
from ..logging_setup import get_logger
from . import feedback
from .core import Verdict, grade
from .sandbox import (
    GradingBusy,
    GradingTimeout,
    GradingUnavailable,
    call,
    shutdown,
    status,
    warm_up,
)

logger = get_logger(__name__)

__all__ = [
    "GradingBusy",
    "GradingUnavailable",
    "Verdict",
    "grade_submission",
    "shutdown",
    "status",
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
        # sandbox 那邊已經記過一行 WARNING（含時限）；這裡補上是哪一題，
        # 老師才有辦法把 log 和 Attempt 表對起來。學生的原始輸入不進 log。
        logger.warning(
            "判定逾時：template=%s difficulty=%s seed=%s（學生看到 timeout 訊息）。",
            problem.template_id, problem.difficulty, problem.seed,
        )
        verdict = Verdict.of("timeout", feedback.TIMEOUT_DETAIL)
    except GradingBusy:
        # 不是這位學生的問題，是判定容量不夠。sandbox 已經記過一行 WARNING
        # （含 worker 數與可調的旋鈕），這裡補上是哪一題。
        logger.warning(
            "判定排隊逾時：template=%s difficulty=%s seed=%s（學生看到 busy 訊息）。",
            problem.template_id, problem.difficulty, problem.seed,
        )
        verdict = Verdict.of("busy", feedback.BUSY_DETAIL)
    except GradingUnavailable:
        # 子行程池建不起來。原因 sandbox 已經記了，這裡強調它是**全站性**的。
        logger.error(
            "判定功能目前不可用（子行程池建不起來），"
            "所有作答都會得到 internal_error。原因見上面的 ERROR。",
        )
        verdict = Verdict.of("internal_error", feedback.INTERNAL_DETAIL)
    except Exception:                                # noqa: BLE001 - 端點不得因此 500
        # 端點不回 500，但這是**程式的 bug**，一定要留完整 traceback。
        logger.exception(
            "判定時發生預期外的錯誤：template=%s difficulty=%s seed=%s。",
            problem.template_id, problem.difficulty, problem.seed,
        )
        verdict = Verdict.of("internal_error", feedback.INTERNAL_DETAIL)
    return verdict, int((time.monotonic() - started) * 1000)
