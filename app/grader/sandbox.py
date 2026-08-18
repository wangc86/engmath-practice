"""判定過程的硬性 timeout（PLAN.md §2.7、§5）。

學生輸入是**不可信輸入**。`parse.py` 已經用字元白名單、長度上限與複雜度上限
擋掉絕大多數病態輸入，但 `simplify` 這類符號運算沒有辦法保證停機——只要有一個
請求讓它跑不完，那條 worker thread 就永遠回不來，累積幾條就足以拖垮整台伺服器。

因此判定一律丟到**獨立子行程**執行，逾時就把行程殺掉。這是唯一能保證「一定回
得來」的做法：

- `signal.setitimer` 只在主執行緒有效，而 FastAPI 的同步端點跑在 threadpool 裡，
  所以 signal 在這裡不可靠（僅作為子行程建不起來時的退路）。
- 用 "spawn" 而非 "fork"：本行程是多執行緒的，從非主執行緒 fork 有可能在子行程
  裡卡在別的執行緒持有的鎖上（Python 3.12 起也已對此發出 DeprecationWarning）。
  代價是子行程要重新 import sympy（約 1 秒），因此在啟動時就先暖機一次。

逾時的處置是**整池重建**：ProcessPoolExecutor 沒有辦法只取消單一個已在執行的
工作，只能殺行程。逾時代表輸入是惡意或病態的，本來就該是罕見事件，直接付這個
代價比留一個永遠在燒 CPU 的 worker 好。
"""

from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from concurrent.futures.process import BrokenProcessPool

# 用模組參照而非 `from ..config import ...`：設定值要在**呼叫當下**才讀，
# 測試才有辦法用環境變數改掉它（測試會 importlib.reload(app.config)）。
from .. import config


class GradingTimeout(Exception):
    """判定超過時限（或 worker 在判定途中被殺掉）。"""


_lock = threading.Lock()
_pool: ProcessPoolExecutor | None = None
_disabled = False          # 子行程建不起來的環境（極少見）→ 退回同行程執行


def _noop() -> bool:
    """暖機用：讓子行程先把 sympy import 起來的最小工作。"""
    return True


def _get_pool() -> ProcessPoolExecutor | None:
    global _pool, _disabled
    if _disabled:
        return None
    if _pool is None:
        try:
            _pool = ProcessPoolExecutor(
                max_workers=config.GRADER_WORKERS,
                mp_context=multiprocessing.get_context("spawn"),
            )
        except (OSError, ValueError, ImportError):   # 沙箱不給開行程
            _disabled = True
            return None
    return _pool


def _kill_pool() -> None:
    """把整池 worker 殺掉並丟棄，下次呼叫時重建。"""
    global _pool
    pool, _pool = _pool, None
    if pool is None:
        return
    for proc in list(getattr(pool, "_processes", {}).values()):
        try:
            proc.kill()
        except Exception:                            # noqa: BLE001 - 殺不掉就算了
            pass
    try:
        pool.shutdown(wait=False)
    except Exception:                                # noqa: BLE001
        pass


def warm_up() -> None:
    """在應用啟動時先把 worker 叫起來，讓第一位學生不必等 sympy 的 import。"""
    if not config.GRADER_WARMUP:
        return
    try:
        call(_noop, timeout=60)
    except Exception:                                # noqa: BLE001 - 暖機失敗不影響啟動
        pass


def call(fn, *args, timeout: float | None = None):
    """在子行程中執行 ``fn(*args)``，逾時丟 :class:`GradingTimeout`。

    ``fn`` 與 ``args`` 都必須是可 pickle 的（因此 `Check` 是純資料，不含 lambda）。
    """
    if timeout is None:
        timeout = config.GRADER_TIMEOUT_SECONDS
    with _lock:
        pool = _get_pool()

    if pool is None:                                 # 退路：同行程執行，只剩 parse 層的防護
        return fn(*args)

    try:
        return pool.submit(fn, *args).result(timeout=timeout)
    except FuturesTimeout as exc:
        with _lock:
            _kill_pool()
        raise GradingTimeout("grading exceeded the time limit") from exc
    except BrokenProcessPool as exc:
        # 多半是同時有另一個請求逾時、整池被重建；對本次請求一樣視為逾時
        with _lock:
            _kill_pool()
        raise GradingTimeout("grading worker was restarted") from exc


def shutdown() -> None:
    with _lock:
        _kill_pool()
