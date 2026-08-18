"""資料表（PLAN.md §4.1）。

目前有三張表：`Student`（帳號）、`UsageLog`（用量紀錄）、`Attempt`（作答紀錄）。
預生成題庫的 `Problem` 與對話稽核的 `ChatLog` 仍是後續階段的事。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlmodel import JSON, Field, SQLModel


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


class Attempt(SQLModel, table=True):
    """作答紀錄（階段 2）。

    依老師的決定（PLAN.md D1），本表**不得作為成績依據**，只用於
    「學生看自己的練習狀況」與「老師看班級的弱點分布」。因此這裡沒有分數欄位，
    也刻意不做加總；註冊頁的個資告知已相應更新為「包含你送出的答案」。

    題目不整份存下來：`(template_id, difficulty, seed)` 三個欄位就能用
    `generator.generate()` 完整重現同一題，`params_json` 只是為了在日後模板
    改版時，仍看得出當初那題長什麼樣。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id", index=True)
    template_id: str = Field(index=True)
    difficulty: int = Field(index=True)
    seed: int                                          # 與 template_id/difficulty 合起來可重現該題
    params_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    submitted_raw: str                                 # 學生的原始輸入（未經改寫）
    verdict: str = Field(index=True)                   # correct / wrong / parse_error / timeout …
    is_correct: bool = Field(default=False, index=True)
    is_partial: bool = Field(default=False)
    duration_ms: int = 0                               # 判定耗時
    created_at: datetime = Field(default_factory=_utcnow, index=True)
