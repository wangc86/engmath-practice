"""判定過程的硬性 timeout 與**請求之間的隔離**（PLAN.md §2.7、§5.6）。

學生輸入是**不可信輸入**。`parse.py` 已經用字元白名單、長度上限與複雜度上限
擋掉絕大多數病態輸入，但 `simplify` 這類符號運算沒有辦法保證停機——只要有一個
請求讓它跑不完，那條 worker thread 就永遠回不來，累積幾條就足以拖垮整台伺服器。

因此判定一律丟到**子行程**執行，逾時就把行程殺掉。這是唯一能保證「一定回得來」
的做法：

- `signal.setitimer` 只在主執行緒有效，而 FastAPI 的同步端點跑在 threadpool 裡，
  所以 signal 在這裡不可靠。
- 用 "spawn" 而非 "fork"：本行程是多執行緒的，從非主執行緒 fork 有可能在子行程
  裡卡在別的執行緒持有的鎖上（Python 3.12 起也已對此發出 DeprecationWarning）。
  代價是子行程要重新 import sympy（約 1 秒），因此 worker 是**常駐**的，
  並在啟動時就先暖機一個。

為什麼不用 `ProcessPoolExecutor`（v0.6 的改動）
------------------------------------------------

舊版用的是 `ProcessPoolExecutor`。它有一個在這個情境下會直接傷到學生的性質：
**沒有辦法取消單一個已經在執行的工作**。一次逾時只能整池殺掉重建，於是同一
瞬間另一個完全正常的請求會收到 `BrokenProcessPool`，被當成逾時，學生看到
「請再試一次」——他什麼都沒做錯。全班同時交卷時，一個人送出病態輸入就會波及
當下正在判定的其他人。

現在改成自己維護一小組常駐 worker，每個 worker 一條 `Pipe`，並且**一次只交給
它一件工作**。因為知道是哪個行程在跑哪一件事，逾時就只殺那一個：

    工作 A（病態輸入，逾時）→ 只有 worker #1 被殺掉，隨後補一個新的
    工作 B（正常，同時進行）→ 在 worker #2 上跑完，完全不受影響

取捨（本專案的情境是校內單一課程、單人維護、平時併發低但尖峰時全班同時交卷）：

- **不選「每次判定開一個新行程」**：隔離性最好，但每次都要重新 import sympy，
  每一次作答固定多等約一秒。平時的判定本身只要 0.1–0.5 秒，這個代價是常態，
  而它要換的東西（逾時的隔離）是罕見事件——把成本加在常態上不划算。
- **選「常駐 worker + 逐一指派 + 只殺出事的那個」**：常態零額外成本，逾時的
  代價收斂到單一個請求。多出來的是約 150 行需要自己維護的行程管理程式碼，
  這是本次改動真正付出的代價。
- **併發上限就是 worker 數**（`GRADER_WORKERS`）。滿載時後來的請求會排隊等一個
  空的 worker，等超過 `GRADER_QUEUE_TIMEOUT` 才放棄並回「系統忙碌」。這是刻意的：
  判定是 CPU 密集工作，讓它無限並行只會讓每個人都變慢。尖峰估算見 README「運維」。

沒有子行程時**不降級、直接失敗**（D8，v0.5）
--------------------------------------------

舊版在子行程建不起來時會靜默退回同行程執行。那把「唯一能保證回得來的機制」換成
「完全沒有機制」，而且不留任何痕跡。同行程的 timeout 在這個架構下**做不到**：

- `signal.setitimer` / `SIGALRM` 只有主執行緒收得到。判定跑在 FastAPI 的
  threadpool 裡，鬧鐘永遠不會響。
- 看門狗執行緒可以「發現」逾時，但 Python 沒有辦法中斷另一條執行緒——
  `PyThreadState_SetAsyncExc` 只在直譯器回到 bytecode 邊界時生效，而卡住的
  SymPy 多半正陷在 C 層或一個沒有函式呼叫的長迴圈裡。

所以降級模式等於「沒有 timeout 的模式」，只是換了個名字。因此：

- **啟動時**（`warm_up`）建不起來 → 記 ERROR 並拋錯，讓服務起不來。
- **執行期**建不起來 → 記 ERROR 並拋 :class:`GradingUnavailable`，該次判定回
  「系統忙碌」給學生。**不會**有任何一行不可信輸入在主行程裡跑。

失敗也**不黏著**：每次呼叫都重新嘗試，環境恢復了就自己好起來。
"""

from __future__ import annotations

import multiprocessing
import queue
import threading
from dataclasses import dataclass, field

# 用模組參照而非 `from ..config import ...`：設定值要在**呼叫當下**才讀，
# 測試才有辦法用環境變數改掉它（測試會 importlib.reload(app.config)）。
from .. import config
from ..logging_setup import configure_logging, get_logger

logger = get_logger(__name__)


class GradingTimeout(Exception):
    """判定超過時限（或那個 worker 在判定途中死掉）。"""


class GradingUnavailable(Exception):
    """判定用的子行程建不起來——此時我們**拒絕判定**，不退回同行程執行。"""


class GradingBusy(Exception):
    """所有 worker 都在忙，排隊等不到——這是負載問題，不是輸入問題。"""


# --- worker 端 --------------------------------------------------------------

def _worker_loop(conn) -> None:
    """常駐 worker 的主迴圈：收一件工作、做完、把結果送回去，然後等下一件。

    spawn 出來的子行程是一個乾淨的直譯器：它會 import 到我們的模組，但不會經過
    `main.py` 的 lifespan，因此 logging 沒有被設定過。少了 `configure_logging()`，
    判定過程中在子行程裡記的東西就只剩 `logging.lastResort`（WARNING 以上、
    無時間戳），DEBUG 級的診斷訊息會直接消失。
    """
    configure_logging()
    try:
        import sympy  # noqa: F401 - 暖機：把最慢的 import 挪到收工作之前
    except Exception:                                  # noqa: BLE001 - 記下來再讓它死
        logger.exception("判定 worker 無法 import sympy，這個 worker 直接結束。")
        return

    while True:
        try:
            payload = conn.recv()
        except (EOFError, OSError):                    # 父行程收工了
            return
        if payload is None:                            # 明確的收工訊號
            return
        fn, args = payload
        try:
            reply = ("ok", fn(*args))
        except BaseException as exc:                   # noqa: BLE001 - 原樣回報給父行程
            reply = ("error", exc)
        try:
            conn.send(reply)
        except Exception:                              # noqa: BLE001 - 結果送不回去
            # 多半是結果或例外物件不能 pickle。降級成一則字串，總比讓父行程
            # 等到逾時（然後把這個 worker 當成病態輸入殺掉）好。
            try:
                conn.send(("error", RuntimeError(
                    f"grading result could not be sent back ({reply[0]})"
                )))
            except Exception:                          # noqa: BLE001 - 連線也壞了
                return


def start_worker_process(conn):
    """開一個 worker 子行程。**這是測試注入失敗的地方**——真的沒有行程額度時，
    就是在 `start()` 這裡拋 OSError。"""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_worker_loop, args=(conn,), daemon=True)
    proc.start()
    return proc


# --- 父行程端 ---------------------------------------------------------------

@dataclass(eq=False)          # eq=False → 保留 identity 比較與 hash，才放得進 set
class _Worker:
    """一個常駐 worker 與通往它的管線。同一時間只會有一條執行緒持有它。"""

    wid: int
    proc: object
    conn: object

    def alive(self) -> bool:
        return bool(self.proc.is_alive())

    def kill(self) -> None:
        try:
            self.proc.kill()
        except Exception as exc:                       # noqa: BLE001 - 殺不掉不致命，但要留紀錄
            logger.warning(
                "判定 worker #%d（pid %s）殺不掉：%s: %s。"
                "若這行反覆出現，請檢查有沒有孤兒 python 行程在燒 CPU。",
                self.wid, getattr(self.proc, "pid", "?"), type(exc).__name__, exc,
            )
        for closeable in (self.conn, self.proc):
            try:
                closeable.close()
            except Exception:                          # noqa: BLE001 - 關不掉就算了
                pass


@dataclass
class _Pool:
    """一小組常駐 worker。刻意做得很笨：一個 idle 佇列 + 一個併發名額號誌。"""

    size: int
    idle: queue.LifoQueue = field(default_factory=queue.LifoQueue)
    slots: threading.Semaphore = None                  # type: ignore[assignment]
    live: set = field(default_factory=set)
    spawned: int = 0                                   # 累計開過幾個 worker（診斷用）
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.slots = threading.BoundedSemaphore(self.size)


_lock = threading.Lock()
_pool: _Pool | None = None
_warm: bool = False          # 暖機是否成功過（只給 /healthz 看，不影響行為）
_next_wid = 0


def _get_pool() -> _Pool:
    """取得（必要時建立）worker 池。這一步不會開行程，因此不會失敗。"""
    global _pool
    with _lock:
        if _pool is None or _pool.size != config.GRADER_WORKERS:
            if _pool is not None:                      # 設定被改過（測試會這樣做）
                _shutdown_pool(_pool)
            _pool = _Pool(size=max(1, int(config.GRADER_WORKERS)))
        return _pool


def _new_worker(pool: _Pool) -> _Worker:
    """開一個新的 worker。開不起來就拋 :class:`GradingUnavailable`（D8）。"""
    global _next_wid
    try:
        ctx = multiprocessing.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=True)
        proc = start_worker_process(child_conn)
    except Exception as exc:                           # noqa: BLE001 - 轉譯後重拋，不吞
        logger.error(
            "判定用的子行程開不起來（%s: %s）。"
            "這台機器目前沒有辦法開子行程，判定會全部失敗——"
            "本系統不會退回同行程執行，因為那等於沒有 timeout，"
            "一個病態的作答就能把伺服器卡死。"
            "請檢查行程數／記憶體上限（ulimit -u、cgroup pids.max）與 /dev/shm。",
            type(exc).__name__, exc, exc_info=True,
        )
        raise GradingUnavailable("could not start a grading worker") from exc

    child_conn.close()                                 # 父行程這一端不需要它
    with pool.lock:
        _next_wid += 1
        worker = _Worker(wid=_next_wid, proc=proc, conn=parent_conn)
        pool.live.add(worker)
        pool.spawned += 1
    return worker


def _checkout(pool: _Pool) -> _Worker:
    """拿一個可用的 worker：先撿 idle 的，撿不到就開一個新的。"""
    while True:
        try:
            worker = pool.idle.get_nowait()
        except queue.Empty:
            return _new_worker(pool)
        if worker.alive():
            return worker
        # idle 佇列裡躺著一個已經死掉的 worker（例如被 OOM killer 收掉）。
        # 這不是本次請求的錯，但一定要留紀錄——否則只會表現成「偶爾慢一秒」。
        logger.warning(
            "判定 worker #%d 在閒置期間死掉了（多半是被 OOM killer 或系統管理者殺的）。"
            "改開一個新的；若這行反覆出現請檢查機器的記憶體。", worker.wid,
        )
        _discard(pool, worker)


def _discard(pool: _Pool, worker: _Worker) -> None:
    """殺掉並丟棄**單一個** worker。其他 worker 完全不受影響。"""
    with pool.lock:
        pool.live.discard(worker)
    worker.kill()


def _run(worker: _Worker, fn, args, timeout: float):
    """把工作交給指定的 worker，等它回覆。逾時或它死掉就拋 GradingTimeout。"""
    worker.conn.send((fn, args))
    if not worker.conn.poll(timeout):
        raise GradingTimeout("grading exceeded the time limit")
    try:
        kind, payload = worker.conn.recv()
    except (EOFError, OSError) as exc:
        raise GradingTimeout("grading worker died while working") from exc
    if kind == "error":
        raise payload
    return payload


def call(fn, *args, timeout: float | None = None):
    """在子行程中執行 ``fn(*args)``，逾時丟 :class:`GradingTimeout`。

    ``fn`` 與 ``args`` 都必須是可 pickle 的（因此 `Check` 是純資料，不含 lambda）。
    子行程開不起來時丟 :class:`GradingUnavailable`——**不會**改在本行程執行。
    所有 worker 都忙、排隊逾時則丟 :class:`GradingBusy`。

    **隔離保證**：一次逾時只會殺掉執行那件工作的那一個 worker，同一時間在別的
    worker 上跑的請求不受任何影響。
    """
    if timeout is None:
        timeout = config.GRADER_TIMEOUT_SECONDS
    pool = _get_pool()

    if not pool.slots.acquire(timeout=config.GRADER_QUEUE_TIMEOUT):
        logger.warning(
            "判定排隊超過 %.1f 秒仍等不到空的 worker（共 %d 個），本次請求放棄。"
            "若這行成群出現，代表尖峰負載超過判定容量：調高 GRADER_WORKERS，"
            "或把提交速率限制（SUBMIT_RATE_LIMIT）收緊。",
            config.GRADER_QUEUE_TIMEOUT, pool.size,
        )
        raise GradingBusy("no grading worker became available in time")

    try:
        worker = _checkout(pool)
        try:
            result = _run(worker, fn, args, timeout)
        except GradingTimeout:
            logger.warning(
                "一次判定超過 %.1f 秒的時限，只殺掉 worker #%d（其他判定不受影響）。"
                "偶爾出現是正常的（學生送出了很難化簡的式子）；"
                "若頻繁出現請看 Attempt 表裡 verdict='timeout' 的作答內容。",
                timeout, worker.wid,
            )
            _discard(pool, worker)
            raise
        except BaseException:
            # fn 自己拋的例外（worker 還活著、狀態乾淨）→ 把 worker 收回去再重拋。
            _checkin(pool, worker)
            raise
        _checkin(pool, worker)
        return result
    finally:
        pool.slots.release()


def _checkin(pool: _Pool, worker: _Worker) -> None:
    if worker.alive():
        pool.idle.put(worker)
    else:
        _discard(pool, worker)


def _noop() -> bool:
    """暖機用：讓子行程先把 sympy import 起來的最小工作。"""
    return True


def warm_up() -> None:
    """在應用啟動時把一個 worker 叫起來。失敗就拋錯，讓服務**起不來**（D8）。

    判定沒有子行程就沒有 timeout，而沒有 timeout 的判定是一個誰都能觸發的阻斷
    服務漏洞。與其安靜地跑一個學期，不如現在就讓部署的人看到。真的要略過
    （例如測試、或只想先開起來看看頁面）請設 `GRADER_WARMUP=0`。
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
        # _new_worker() 已經記過詳細原因了，這裡只補「影響是什麼」
        logger.error("判定子行程無法啟動，服務不會啟動。原因見上一行。")
        raise
    _warm = True
    logger.info(
        "判定子行程已就緒（上限 %d 個 worker，單次判定上限 %.1f 秒，"
        "排隊上限 %.1f 秒）。",
        config.GRADER_WORKERS, config.GRADER_TIMEOUT_SECONDS,
        config.GRADER_QUEUE_TIMEOUT,
    )


def status() -> dict:
    """給 `/healthz` 用的簡報。只看旗標與計數，不送工作進去，因此非常便宜。

    `busy` 持續貼著 `workers` 就代表判定容量已經吃滿，該調 `GRADER_WORKERS` 了。
    """
    pool = _pool
    live = len(pool.live) if pool else 0
    idle = pool.idle.qsize() if pool else 0
    return {
        "warmed_up": _warm,
        "pool_alive": live > 0,
        "workers": config.GRADER_WORKERS,
        "live": live,
        "idle": idle,
        "busy": max(0, live - idle),
        "spawned_total": pool.spawned if pool else 0,
        "timeout_seconds": config.GRADER_TIMEOUT_SECONDS,
        "queue_timeout_seconds": config.GRADER_QUEUE_TIMEOUT,
    }


def _shutdown_pool(pool: _Pool) -> None:
    while True:
        try:
            pool.idle.get_nowait()
        except queue.Empty:
            break
    for worker in list(pool.live):
        pool.live.discard(worker)
        worker.kill()


def shutdown() -> None:
    global _pool, _warm
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        _shutdown_pool(pool)
    _warm = False
