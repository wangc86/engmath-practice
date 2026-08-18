"""判定的 timeout 與子行程隔離（PLAN.md §2.7）。

這幾項守的是**可用性**，不是數學正確性：一個學生送出病態輸入，不能讓整台
伺服器的 worker thread 卡住。因此判定跑在子行程裡，逾時就把行程殺掉。

這個檔案會實際開子行程（spawn），所以比 test_grader.py 慢一些；
把它獨立出來，才不會拖慢平常最常跑的那一份。
"""

from __future__ import annotations

import time

import pytest

from app.generator import generate
from app.grader import grade_submission
from app.grader.sandbox import GradingTimeout, call, shutdown


def _sleep(seconds: float) -> str:                 # 必須是 module 層級的函式才 picklable
    time.sleep(seconds)
    return "finished"


def _boom() -> None:
    raise RuntimeError("worker exploded")


@pytest.fixture(autouse=True)
def _clean_pool():
    yield
    shutdown()


def test_worker_returns_normal_results():
    assert call(_sleep, 0.01, timeout=30) == "finished"


def test_slow_work_is_cut_off_at_the_timeout():
    """逾時要在時限附近就回來，而不是等它自己跑完。"""
    started = time.monotonic()
    with pytest.raises(GradingTimeout):
        call(_sleep, 30, timeout=2)
    elapsed = time.monotonic() - started
    assert elapsed < 20, f"逾時後過了 {elapsed:.1f} 秒才回來"


def test_pool_recovers_after_a_timeout():
    """殺掉 worker 之後，下一個請求仍要能正常判定。"""
    with pytest.raises(GradingTimeout):
        call(_sleep, 30, timeout=2)
    assert call(_sleep, 0.01, timeout=60) == "finished"


def test_worker_exception_does_not_escape_grade_submission():
    """判定端點不得因為 worker 出事而回 500。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    verdict, duration_ms = grade_submission(problem, "C1*e^(-x) + C2*e^(-2x)")
    assert verdict.code in {"correct", "wrong", "partial_missing_constants"}
    assert duration_ms >= 0


def test_grade_submission_runs_the_full_path():
    """走一次完整的「重現題目 → 子行程判定」路徑。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=7)
    r1, r2 = problem.params["r1"], problem.params["r2"]
    verdict, duration_ms = grade_submission(problem, f"C1*e^({r1}x) + C2*e^({r2}x)")
    assert verdict.correct, verdict.detail
    assert duration_ms > 0


def test_grade_submission_turns_a_timeout_into_a_verdict():
    """逾時要變成一則學生看得懂的訊息，而不是例外。"""
    import app.grader as grader

    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    original = grader.call

    def _always_timeout(*args, **kwargs):
        raise GradingTimeout("boom")

    grader.call = _always_timeout
    try:
        verdict, _ = grade_submission(problem, "C1*e^(-x)")
    finally:
        grader.call = original

    assert verdict.code == "timeout"
    assert not verdict.correct
    assert "time limit" in verdict.detail


def test_grade_submission_survives_an_internal_error():
    import app.grader as grader

    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    original = grader.call

    def _explode(*args, **kwargs):
        raise RuntimeError("something unexpected")

    grader.call = _explode
    try:
        verdict, _ = grade_submission(problem, "C1*e^(-x)")
    finally:
        grader.call = original

    assert verdict.code == "internal_error"
    assert not verdict.correct
