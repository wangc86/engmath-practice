"""內容開放狀態：讀、寫，以及「這個帳號看得到什麼」（PLAN.md D53–D55、§4.3a）。

這是 `ReleaseState` 那張表唯一的對外介面。閘門（`app/release_gate.py`）、
出題頁、展示索引頁與管理頁全部走這裡，**沒有任何地方自己 `select(ReleaseState)`**
——四個地方各寫一次查詢，就是四個地方各有一次寫錯的機會，而寫錯的方向
（多開一項）是安靜的。

---

## 預設全關（D54）

新部署、空資料庫 = 一項都沒有開放。理由與這個專案其他每一道閘門相同
（規則 1 的 `check is None`、登入閘門的豁免清單、`Problem.assets` 的白名單）：
**閘門的預設必須是擋下來**。

反過來想一次，才看得出為什麼：預設全開的話，老師忘了設定的後果是
「學生第一週就看得到全部 16 週的內容」——那正是這個功能要防止的事，
而且**沒有任何人會發現**，因為系統看起來完全正常。預設全關的後果是
「學生看到一頁空的」——不好，但**看得見**，而且十秒鐘就修得好。

⚠️ 「看得見」不會自己發生，所以它有三個落點，一個都不能省：

1. 學生端的空狀態訊息（`practice.html`／`demos/index.html`），
   說清楚是「還沒開放」而不是「系統壞了」。
2. `warn_if_nothing_is_open()`——啟動時在終端機上留一行（規則 4）。
3. 管理頁最上面的一行數字：現在開了幾項、總共幾項。

## 每次請求都查一次資料庫，不快取

`released_ids()` 會被閘門與每一次頁面渲染呼叫。掃一張最多 20 列的 SQLite 表，
**實測 0.34 ms／次**（沙箱，500 次平均，8/20 開放）——在同時 30 人的規模下
可以忽略，而一次出題本來就要 0.1 秒左右。與 `login_gate._account_exists()`
是同一個判斷，只是這次有量過。

**不加快取是刻意的**：快取要失效，而失效的時機正好是老師按下按鈕的那一刻。
一個「開了但學生還看不到」的系統，會讓老師在上課前重按好幾次，
然後不確定到底有沒有生效——那比多一次查詢貴得多。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from .curriculum import ALL_CONTENT_IDS
from .db.models import ROLE_STAFF, Account, ReleaseState
from .db.session import engine
from .logging_setup import get_logger

logger = get_logger(__name__)


def released_ids() -> frozenset[str]:
    """目前對學生開放的內容代號。

    ⚠️ **會過濾掉不在 `curriculum.ALL_CONTENT_IDS` 裡的列。** 那種列會出現在
    一個真的會發生的狀況裡：某個題型被改名或移除，而資料庫裡還留著舊代號。
    不過濾的話它只是一列孤兒（無害）；過濾之後這個函式的回傳值有一個
    很有用的性質——**它永遠是全部內容的子集合**，所以管理頁的「開了幾項 /
    共幾項」不會出現 21/20 這種讀不懂的數字。
    """
    with Session(engine) as session:
        rows = session.exec(
            select(ReleaseState.content_id).where(ReleaseState.is_open == True)  # noqa: E712
        ).all()
    return frozenset(rows) & ALL_CONTENT_IDS


def is_released(content_id: str) -> bool:
    """單一一項開了沒有。**未知的代號一律回 `False`**（閘門的預設是擋下來）。"""
    if content_id not in ALL_CONTENT_IDS:
        return False
    with Session(engine) as session:
        row = session.exec(
            select(ReleaseState).where(ReleaseState.content_id == content_id)
        ).first()
    return bool(row and row.is_open)


def visible_ids(account: Account | None) -> frozenset[str]:
    """這個帳號看得到哪些內容。

    **`staff` 看得到全部，而且不受開放狀態影響。** 這不是特權，是這個功能
    能用的前提：老師要在按下「開放」之前先自己點進去看一眼，而如果他也被
    擋著，唯一的檢查方式就變成「先開放給全班、自己看完再關掉」——
    那等於每週都對學生閃一次還沒準備好的內容。

    `None`（未登入）回空集合。正常情況下走不到這裡（登入閘門在更外層），
    但這個函式不應該假設呼叫端已經檢查過（與 `routes/deps.py` 兩層防護
    同一個理由）。
    """
    if account is None:
        return frozenset()
    if account.role == ROLE_STAFF:
        return ALL_CONTENT_IDS
    return released_ids()


def set_released(open_ids: set[str]) -> tuple[int, int]:
    """把開放狀態設成「**恰好** `open_ids` 這些是開的」，回傳 (開幾項, 關幾項)。

    ⚠️ **這是覆寫，不是增量。** 管理頁送上來的是整張表單的核取結果，
    所以「沒有勾的就是關的」——這是唯一一種不會讓老師疑惑的語意。
    增量式的介面（「加開這幾項」）在一個核取方塊表單上會讓取消勾選
    變成無效操作，而**取消勾選看起來明明有效**。

    不在 `ALL_CONTENT_IDS` 裡的代號會被丟掉並留一行 log（規則 4）——
    表單被改過、或內容被改名之後會發生。
    """
    unknown = set(open_ids) - ALL_CONTENT_IDS
    if unknown:
        logger.warning(
            "開放設定裡有不認得的內容代號，已忽略：%s。"
            "若某個題型剛改過代號，請確認 app/curriculum.py 的 CONTENT 也跟著改了。",
            sorted(unknown),
        )
    wanted = set(open_ids) & ALL_CONTENT_IDS
    now = datetime.now(timezone.utc)

    opened = closed = 0
    with Session(engine) as session:
        rows = {
            row.content_id: row
            for row in session.exec(select(ReleaseState)).all()
        }
        for content_id in sorted(ALL_CONTENT_IDS):
            should_be_open = content_id in wanted
            row = rows.get(content_id)
            if row is None:
                # 沒有列 = 關著（見 `ReleaseState` 的說明）。只有真的要開才建列，
                # 否則一個全新的資料庫會憑空長出 20 列「我沒有開它」。
                if should_be_open:
                    session.add(
                        ReleaseState(
                            content_id=content_id, is_open=True, updated_at=now
                        )
                    )
                    opened += 1
                continue
            if row.is_open != should_be_open:
                row.is_open = should_be_open
                row.updated_at = now
                session.add(row)
                opened += should_be_open
                closed += not should_be_open
        session.commit()

    logger.info(
        "內容開放設定已更新：新開 %d 項、關閉 %d 項，目前共 %d/%d 項開放。",
        opened, closed, len(wanted), len(ALL_CONTENT_IDS),
    )
    return opened, closed


def updated_at_by_id() -> dict[str, datetime]:
    """每一項最後一次被切換的時間，管理頁用。沒有列的就不在字典裡。"""
    with Session(engine) as session:
        rows = session.exec(select(ReleaseState)).all()
    return {row.content_id: row.updated_at for row in rows}


def warn_if_nothing_is_open() -> None:
    """啟動時檢查：一項都沒開就在終端機上說一聲（規則 4）。

    這是 D54「預設全關」的第二個落點。學生端的空狀態訊息是給學生看的，
    它沒有辦法讓老師知道——老師不會用學生帳號登入。而一個開學前部署完
    就忘了設定的系統，唯一還會被讀到的東西就是啟動時的那幾行 log。
    """
    count = len(released_ids())
    if count == 0:
        logger.warning(
            "目前沒有任何內容對學生開放（預設值就是全關，見 PLAN.md D54）。"
            "學生登入後會看到一頁空的、以及一句『尚未開放』的說明。"
            "要開放內容請用 staff 帳號登入後打開 /admin/content。"
        )
    else:
        logger.info(
            "內容開放狀態：%d/%d 項對學生開放。", count, len(ALL_CONTENT_IDS)
        )
