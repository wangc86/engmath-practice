"""SQLite 連線與 session。"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import event, inspect
from sqlmodel import Session, SQLModel, create_engine

from ..config import DATABASE_URL, DB_PATH
from ..logging_setup import get_logger

logger = get_logger(__name__)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


class LegacySchemaError(RuntimeError):
    """資料庫是 v0.15 以前的格式，程式不能接上去。"""


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
    """WAL 模式讓讀寫併發不互相阻塞（PLAN.md §1.3）。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _reject_legacy_schema() -> None:
    """v0.16（D35）：舊的資料庫接上新程式會壞，所以在啟動時就擋下來。

    `SQLModel.metadata.create_all()` 只建**缺少的**表，不會去改既有的表。
    因此一個 v0.15 的 `practice.db` 接上 v0.16 的程式會是這樣：

    - `account` 表被建起來（它不存在）；
    - `usagelog` **維持舊結構**（有 `student_id`，沒有 `account_id`）；
    - 一切看起來正常，直到第一次有人出題——那時才會噴
      `OperationalError: table usagelog has no column named account_id`。

    那是一個半夜出現在某一個學生螢幕上的 500，而不是老師在啟動時看到的
    一行字。規則 4 說「寧可讓啟動失敗」，所以就讓它啟動失敗。

    **不做自動遷移**是刻意的：舊資料庫裡的 `student_no` 是這個系統唯一一項
    個人資料，而 D35 的整個重點就是不要有它。一個「幫你把舊資料搬過來」的
    腳本，會把那批學號從一個要被刪掉的檔案搬進一個要長期使用的檔案裡。
    正確的處理方式是刪掉重建，README「升級到 v0.16」有寫。
    """
    if not DB_PATH.exists():
        return

    tables = set(inspect(engine).get_table_names())
    problems: list[str] = []

    if "student" in tables:
        problems.append("有一張舊的 `student` 表（內含學號，v0.16 已不再蒐集）")
    if "usagelog" in tables:
        columns = {c["name"] for c in inspect(engine).get_columns("usagelog")}
        if "student_id" in columns and "account_id" not in columns:
            problems.append("`usagelog` 還是舊的 `student_id` 欄位")

    if not problems:
        return

    raise LegacySchemaError(
        f"資料庫 {DB_PATH} 是 v0.15 以前的格式：" + "、".join(problems) + "。\n"
        "v0.16（PLAN.md D35）把 `Student` 換成了共用的 `Account`，"
        "而 SQLModel 不會改既有的表，所以接上去會在第一次寫用量紀錄時失敗。\n"
        "這個系統從未正式上線，資料庫裡只有測試資料——請把它刪掉讓程式重建：\n"
        f"    rm {DB_PATH} {DB_PATH}-wal {DB_PATH}-shm\n"
        "刻意不提供自動遷移：舊檔裡的學號正是 v0.16 要拿掉的東西，"
        "把它搬進新檔案與這個版本的目的相反。"
    )


def init_db() -> None:
    """建表，並把 DB 檔案權限收緊為 600。"""
    from . import models  # noqa: F401  匯入以註冊 SQLModel metadata

    _reject_legacy_schema()
    SQLModel.metadata.create_all(engine)
    try:
        if DB_PATH.exists():
            os.chmod(DB_PATH, 0o600)
    except OSError as exc:
        # 不擋啟動（有些檔案系統就是不支援 chmod），但**一定要說**。
        # v0.16 起這個檔案裡已經沒有個人資料了（D35），收緊權限的理由
        # 剩下密碼雜湊——那仍然是不該給別人讀的東西。
        logger.warning(
            "無法把資料庫檔案 %s 的權限收緊為 600（%s）。"
            "該檔案含兩組共用帳號的密碼雜湊，請自行確認它不是全域可讀（ls -l）。",
            DB_PATH, exc,
        )


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
