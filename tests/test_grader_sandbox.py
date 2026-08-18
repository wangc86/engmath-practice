"""判定的 timeout 與子行程隔離（PLAN.md §2.7）。

這幾項守的是**可用性**，不是數學正確性：一個學生送出病態輸入，不能讓整台
伺服器的 worker thread 卡住。因此判定跑在子行程裡，逾時就把行程殺掉。

這個檔案會實際開子行程（spawn），所以比 test_grader.py 慢一些；
把它獨立出來，才不會拖慢平常最常跑的那一份。
"""

from __future__ import annotations

import logging
import time

import pytest

from app import config
from app.generator import generate
from app.grader import grade_submission
from app.grader import sandbox as sandbox_module
from app.grader.sandbox import GradingTimeout, GradingUnavailable, call, shutdown


def _sleep(seconds: float) -> str:                 # 必須是 module 層級的函式才 picklable
    time.sleep(seconds)
    return "finished"


def _boom() -> None:
    raise RuntimeError("worker exploded")


@pytest.fixture(autouse=True)
def _clean_pool():
    yield
    shutdown()


@pytest.fixture()
def no_subprocesses(monkeypatch):
    """模擬「這台機器開不了子行程」。

    直接把 sandbox 用的 `ProcessPoolExecutor` 換掉，是最貼近真實失敗的注入點：
    真的沒有行程額度時，就是在建構子這裡拋 OSError。
    """
    def _refuse(*args, **kwargs):
        raise OSError("cannot start a process in this environment")

    monkeypatch.setattr(sandbox_module, "ProcessPoolExecutor", _refuse)
    shutdown()                                     # 確保沒有留著上一個測試的池
    return _refuse


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


# --- 子行程建不起來時：fail fast，不靜默降級（D8）--------------------------
#
# 這一組測試守的是 v0.5 的那個決定。舊版在這條路徑上會退回同行程執行，
# 於是硬性 timeout 消失、只剩 parse 層防護，而且沒有任何告警與測試。

def test_call_refuses_instead_of_running_in_this_process(no_subprocesses):
    """最重要的一條：子行程建不起來時，工作**不可以**在本行程被執行。"""
    executed = []

    def _should_not_run():
        executed.append(True)
        return "ran in the main process"

    with pytest.raises(GradingUnavailable):
        call(_should_not_run, timeout=5)

    assert executed == [], "不可信輸入絕不能在主行程裡跑——那等於沒有 timeout"


def test_pool_failure_is_logged_with_an_actionable_message(no_subprocesses, caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        with pytest.raises(GradingUnavailable):
            call(_sleep, 0.01, timeout=5)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "建池失敗必須留下 ERROR"
    text = "\n".join(r.getMessage() for r in errors)
    assert "子行程" in text
    assert "同行程" in text, "要講明我們不退回同行程執行，以及為什麼"
    assert "ulimit" in text, "要給老師一個可以動手查的方向"


def test_warm_up_raises_so_that_startup_fails(no_subprocesses, monkeypatch, caplog):
    monkeypatch.setattr(config, "GRADER_WARMUP", True)

    with caplog.at_level(logging.ERROR, logger="app"):
        with pytest.raises(GradingUnavailable):
            sandbox_module.warm_up()

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "服務不會啟動" in text, "告警要說清楚影響是什麼"
    assert sandbox_module.status()["warmed_up"] is False


def test_warm_up_timeout_also_fails_fast(monkeypatch, caplog):
    """池建得起來但連空工作都跑不完，一樣算這台機器有問題。"""
    monkeypatch.setattr(config, "GRADER_WARMUP", True)
    monkeypatch.setattr(config, "GRADER_WARMUP_TIMEOUT", 0.5)

    def _timeout(*args, **kwargs):
        raise GradingTimeout("too slow")

    monkeypatch.setattr(sandbox_module, "call", _timeout)

    with caplog.at_level(logging.ERROR, logger="app"):
        with pytest.raises(GradingUnavailable):
            sandbox_module.warm_up()

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "GRADER_WARMUP_TIMEOUT" in text, "要告訴老師可以調哪個旋鈕"


def test_warm_up_skipped_by_config_does_not_raise(monkeypatch):
    """GRADER_WARMUP=0 是明確的「我知道我在做什麼」，不該被 fail fast 擋住。"""
    monkeypatch.setattr(config, "GRADER_WARMUP", False)
    sandbox_module.warm_up()                       # 不得拋錯
    assert sandbox_module.status()["warmed_up"] is False


def test_successful_warm_up_reports_ready(monkeypatch, caplog):
    monkeypatch.setattr(config, "GRADER_WARMUP", True)

    with caplog.at_level(logging.INFO, logger="app"):
        sandbox_module.warm_up()

    assert sandbox_module.status()["warmed_up"] is True
    assert sandbox_module.status()["pool_alive"] is True
    assert any("已就緒" in r.getMessage() for r in caplog.records)


def test_pool_failure_is_not_sticky(monkeypatch):
    """一次瞬時失敗不該讓判定永久降級（舊版的 `_disabled` 旗標就是這個毛病）。"""
    real_pool_cls = sandbox_module.ProcessPoolExecutor
    attempts = {"n": 0}

    def _fail_once(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("transient: out of process slots")
        return real_pool_cls(*args, **kwargs)

    monkeypatch.setattr(sandbox_module, "ProcessPoolExecutor", _fail_once)
    shutdown()

    with pytest.raises(GradingUnavailable):
        call(_sleep, 0.01, timeout=5)
    assert call(_sleep, 0.01, timeout=60) == "finished"    # 環境好了就自己好起來


def test_grade_submission_turns_unavailability_into_a_verdict(no_subprocesses, caplog):
    """學生看到的是一則訊息，老師看到的是 ERROR——兩邊都不是靜默。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)

    with caplog.at_level(logging.ERROR, logger="app"):
        verdict, _ = grade_submission(problem, "C1*e^(-x) + C2*e^(-2x)")

    assert verdict.code == "internal_error"
    assert not verdict.correct
    assert any("判定功能目前不可用" in r.getMessage() for r in caplog.records)


def test_timeout_is_logged(caplog):
    """逾時是安全相關事件，不能只變成一則學生訊息就沒了。"""
    with caplog.at_level(logging.WARNING, logger="app"):
        with pytest.raises(GradingTimeout):
            call(_sleep, 30, timeout=2)

    assert any("超過" in r.getMessage() for r in caplog.records)
