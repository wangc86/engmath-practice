"""SQLite 連線與 session。"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from ..config import DATABASE_URL, DB_PATH
from ..logging_setup import get_logger

logger = get_logger(__name__)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
    """WAL 模式讓讀寫併發不互相阻塞（PLAN.md §1.3）。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """建表，並把 DB 檔案權限收緊為 600（內含學號與密碼雜湊）。"""
    from . import models  # noqa: F401  匯入以註冊 SQLModel metadata

    SQLModel.metadata.create_all(engine)
    try:
        if DB_PATH.exists():
            os.chmod(DB_PATH, 0o600)
    except OSError as exc:
        # 不擋啟動（有些檔案系統就是不支援 chmod），但**一定要說**：
        # 這個檔案裡有學號明文與密碼雜湊，權限沒收緊是一件老師該知道的事。
        logger.warning(
            "無法把資料庫檔案 %s 的權限收緊為 600（%s）。"
            "該檔案含學號與密碼雜湊，請自行確認它不是全域可讀（ls -l）。",
            DB_PATH, exc,
        )


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
