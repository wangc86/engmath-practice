"""資料表（PLAN.md §4.1）。

MVP 只有兩張表：`Student`（帳號）與 `UsageLog`（用量紀錄）。
作答判定的 `Attempt`、預生成題庫的 `Problem`、對話稽核的 `ChatLog`
都是階段 2／階段 3 才會建立。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(SQLModel, table=True):
    """學生自行註冊的帳號。不計分，因此不與校務系統勾稽。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    student_no: str = Field(index=True, unique=True)   # 學號（正規化為大寫、去空白）
    password_hash: str                                 # argon2id，**絕不存明碼**
    created_at: datetime = Field(default_factory=_utcnow)
    last_login_at: Optional[datetime] = None
    consent_at: Optional[datetime] = None              # 註冊時同意個資告知的時間


class UsageLog(SQLModel, table=True):
    """用量紀錄：誰、什麼時候、做了哪個題型、哪個難度。一列 = 一個動作。

    刻意不含作答內容與對錯 —— 依老師的決定，本系統不計分，
    這張表只用來看用量。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id", index=True)
    template_id: str = Field(index=True)
    difficulty: int = Field(index=True)
    seed: int                                          # 可完整重現該題
    action: str = Field(default="generate", index=True)  # generate | view_solution
    created_at: datetime = Field(default_factory=_utcnow, index=True)
