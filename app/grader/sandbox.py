"""判定過程的硬性 timeout（PLAN.md §2.7、§5）。

學生輸入是**不可信輸入**。`parse.py` 已經用字元白名單、長度上限與複雜度上限
擋掉絕大多數病態輸入，但 `simplify` 這類符號運算沒有辦法保證停機——只要有一個
請求讓它跑不完，那條 worker thread 就永遠回不來，累積幾條就足以拖垮整台伺服器。

因此判定一律丟到**獨立子行程**執行，逾時就把行程殺掉。這是唯一能保證「一定回
得來」的做法：

- `signal.setitimer` 只在主執行緒有效，而 FastAPI 的同步端點跑在 threadpool 裡，
  所以 signal 在這裡不可靠。
- 用 "spawn" 而非 "fork"：本行程是多執行緒的，從非主執行緒 fork 有可能在子行程
  裡卡在別的執行緒持有的鎖上（Python 3.12 起也已對此發出 DeprecationWarning）。
  代價是子行程要重新 import sympy（約 1 秒），因此在啟動時就先暖機一次。

逾時的處置是**整池重建**：ProcessPoolExecutor 沒有辦法只取消單一個已在執行的
工作，只能殺行程。逾時代表輸入是惡意或病態的，本來就該是罕見事件，直接付這個
代價比留一個永遠在燒 CPU 的 worker 好。

沒有子行程時**不降級、直接失敗**（D8，v0.5）
--------------------------------------------

舊版在子行程建不起來時會靜默退回同行程執行。那是這個檔案裡最糟的一段程式：
它把「唯一能保證回得來的機制」換成「完全沒有機制」，而且不留任何痕跡。

同行程的 timeout 在這個架構下**做不到**，不是懶得做：

- `signal.setitimer` / `SIGALRM` 只有主執行緒收得到。判定跑在 FastAPI 的
  threadpool 裡，鬧鐘永遠不會響。
- 看門狗執行緒可以「發現」逾時，但 Python 沒有辦法中斷另一條執行緒——
  `PyThreadState_SetAsyncExc` 只在直譯器回到 bytecode 邊界時生效，而卡住的
  SymPy 多半正陷在 C 層或一個沒有函式呼叫的長迴圈裡。看門狗只會多印一行
  「它卡住了」，然後那條 worker thread 一樣永遠不回來。

所以降級模式等於「沒有 timeout 的模式」，只是換了個名字。既然如此就不留它：

- **啟動時**（`warm_up`）建不起來 → 記 ERROR 並拋錯，讓服務起不來。老師此刻
  正坐在鍵盤前，看得到訊息；代價是五分鐘，而不是整個學期都在裸奔。
- **執行期**建不起來 → 記 ERROR 並拋 :class:`GradingUnavailable`，該次判定回
  「系統忙碌」給學生。**不會**有任何一行不可信輸入在主行程裡跑。

另外拿掉了舊版那個 `_disabled` 全域旗標：它一旦被設起來就永不重試，代表一次
瞬時的資源不足會讓判定永久降級。現在每次呼叫都重新嘗試建池，環境恢復了就自己
好起來。
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
from ..logging_setup import configure_logging, get_logger

logger = get_logger(__name__)


def _init_worker() -> None:
    """每個 worker 起來時跑一次。

    spawn 出來的子行程是一個乾淨的直譯器：它會 import 到我們的模組，但不會經過
    `main.py` 的 lifespan，因此 logging 沒有被設定過。少了這一行，判定過程中在
    子行程裡記的東西就只剩 `logging.lastResort`（WARNING 以上、無時間戳），
    DEBUG 級的診斷訊息會直接消失。
    """
    configure_logging()


class GradingTimeout(Exception):
    """判定超過時限（或 worker 在判定途中被殺掉）。"""


class GradingUnavailable(Exception):
    """判定用的子行程池建不起來——此時我們**拒絕判定**，不退回同行程執行。"""


_lock = threading.Lock()
_pool: ProcessPoolExecutor | None = None
_warm: bool = False          # 暖機是否成功過（只給 /healthz 看，不影響行為）


def _noop() -> bool:
    """暖機用：讓子行程先把 sympy import 起來的最小工作。"""
    return True


def _get_pool() -> ProcessPoolExecutor:
    """取得（必要時建立）子行程池。建不起來就拋 :class:`GradingUnavailable`。"""
    global _pool
    if _pool is None:
        try:
            _pool = ProcessPoolExecutor(
                max_workers=config.GRADER_WORKERS,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_init_worker,
            )
        except Exception as exc:                       # noqa: BLE001 - 轉譯後重拋，不吞
            logger.error(
                "判定用的子行程池建不起來（%s: %s）。"
                "這台機器目前沒有辦法開子行程，判定會全部失敗——"
                "本系統不會退回同行程執行，因為那等於沒有 timeout，"
                "一個病態的作答就能把伺服器卡死。"
                "請檢查行程數／記憶體上限（ulimit -u、cgroup pids.max）與 /dev/shm。",
                type(exc).__name__, exc, exc_info=True,
            )
            raise GradingUnavailable("could not start the grading worker pool") from exc
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
        except Exception as exc:                       # noqa: BLE001 - 殺不掉不致命，但要留紀錄
            logger.warning(
                "判定 worker（pid %s）殺不掉：%s: %s。"
                "若這行反覆出現，請檢查有沒有孤兒 python 行程在燒 CPU。",
                getattr(proc, "pid", "?"), type(exc).__name__, exc,
            )
    try:
        pool.shutdown(wait=False)
    except Exception as exc:                           # noqa: BLE001 - 同上
        logger.warning(
            "關閉判定子行程池時出錯：%s: %s（下一次判定會重建一個新的池）。",
            type(exc).__name__, exc,
        )


def warm_up() -> None:
    """在應用啟動時把 worker 叫起來。失敗就拋錯，讓服務**起不來**（D8）。

    這裡刻意不吞例外：判定沒有子行程就沒有 timeout，而沒有 timeout 的判定是
    一個誰都能觸發的阻斷服務漏洞。與其安靜地跑一個學期，不如現在就讓部署的人
    看到。真的要略過（例如測試、或只想先開起來看看頁面）請設 `GRADER_WARMUP=0`。
    """
    global _warm
    if not config.GRADER_WARMUP:
        logger.info("GRADER_WARMUP=0，略過判定子行程的暖機（第一次判定會多花約 1 秒）。")
        return
    try:
        call(_noop, timeout=config.GRADER_WARMUP_TIMEOUT)
    except GradingTimeout as exc:
        logger.error(
            "判定子行程暖機逾時（%.0f 秒內連一個空工作都跑不完）。"
            "多半是機器負載過高或 sympy 的 import 異常地慢。"
            "服務不會啟動——判定若沒有子行程就沒有 timeout。"
            "確認機器沒問題後可調高 GRADER_WARMUP_TIMEOUT。",
            config.GRADER_WARMUP_TIMEOUT,
        )
        raise GradingUnavailable("grading worker warm-up timed out") from exc
    except GradingUnavailable:
        # _get_pool() 已經記過詳細原因了，這裡只補「影響是什麼」
        logger.error("判定子行程無法啟動，服務不會啟動。原因見上一行。")
        raise
    _warm = True
    logger.info(
        "判定子行程池已就緒（%d 個 worker，單次判定上限 %.1f 秒）。",
        config.GRADER_WORKERS, config.GRADER_TIMEOUT_SECONDS,
    )


def call(fn, *args, timeout: float | None = None):
    """在子行程中執行 ``fn(*args)``，逾時丟 :class:`GradingTimeout`。

    ``fn`` 與 ``args`` 都必須是可 pickle 的（因此 `Check` 是純資料，不含 lambda）。
    子行程池建不起來時丟 :class:`GradingUnavailable`——**不會**改在本行程執行。
    """
    if timeout is None:
        timeout = config.GRADER_TIMEOUT_SECONDS
    with _lock:
        pool = _get_pool()

    try:
        return pool.submit(fn, *args).result(timeout=timeout)
    except FuturesTimeout as exc:
        logger.warning(
            "一次判定超過 %.1f 秒的時限，整池 worker 重建。"
            "偶爾出現是正常的（學生送出了很難化簡的式子）；"
            "若頻繁出現請看 Attempt 表裡 verdict='timeout' 的作答內容。",
            timeout,
        )
        with _lock:
            _kill_pool()
        raise GradingTimeout("grading exceeded the time limit") from exc
    except BrokenProcessPool as exc:
        # 多半是同時有另一個請求逾時、整池被重建；對本次請求一樣視為逾時
        logger.warning(
            "判定 worker 在工作途中消失（%s）。"
            "通常代表同一時間有另一個請求逾時、整池被重建；"
            "若沒有伴隨的逾時訊息，請檢查是不是被 OOM killer 殺掉了。",
            type(exc).__name__,
        )
        with _lock:
            _kill_pool()
        raise GradingTimeout("grading worker was restarted") from exc


def status() -> dict:
    """給 `/healthz` 用的簡報。只看旗標，不送工作進去，因此非常便宜。"""
    return {
        "warmed_up": _warm,
        "pool_alive": _pool is not None,
        "workers": config.GRADER_WORKERS,
        "timeout_seconds": config.GRADER_TIMEOUT_SECONDS,
    }


def shutdown() -> None:
    global _warm
    with _lock:
        _kill_pool()
    _warm = False
