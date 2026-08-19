"""資料表（PLAN.md §4.1）。

目前有兩張表：`Student`（帳號）與 `UsageLog`（用量紀錄）。
預生成題庫的 `Problem` 與對話稽核的 `ChatLog` 仍是後續階段的事。

**v0.7（D12）移除了 `Attempt`**（作答紀錄）：系統不再判定學生的答案，
也不再蒐集作答內容。刻意**沒有做 migration**——這張表只在 v0.4–v0.6 存在，
系統從未正式上線，實際資料庫裡只有測試資料；而 `init_db()` 用的
`SQLModel.metadata.create_all()` 只建缺少的表、不碰既有的表，所以舊 DB 檔裡
殘留的 `attempt` 表會留在原地但永遠不被讀寫。要清掉就手動下一行
`DROP TABLE attempt`（README 有寫）。模型定義保存在 tag `grading-v1`。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(SQLModel, table=True):
    """學生自行註冊的帳號。系統不產生成績，因此不與校務系統勾稽。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    student_no: str = Field(index=True, unique=True)   # 學號（正規化為大寫、去空白）
    password_hash: str                                 # argon2id，**絕不存明碼**
    created_at: datetime = Field(default_factory=_utcnow)
    last_login_at: Optional[datetime] = None
    consent_at: Optional[datetime] = None              # 註冊時同意個資告知的時間


class UsageLog(SQLModel, table=True):
    """用量紀錄：誰、什麼時候、做了哪個題型、哪個難度。一列 = 一個動作。

    刻意不含作答內容與對錯 —— 系統不判定答案（D12），這張表只記用量（D1）。
    這一點在 v0.7 捨棄判定之後更是唯一的行為紀錄。

    ⚠️ 欄位不得擴充（D17）：這張表的內容就是註冊頁個資告知寫明的範圍，
    多存一個欄位就等於超出當初取得同意的範圍。
    `tests/test_web.py::test_notice_matches_the_fields_actually_stored` 盯著這件事。

    `action` 目前只會寫進 ``"generate"``。v0.4–v0.6 另有 ``"view_solution"``，
    但 D13 把解答改成 `<details>` 收合（展開不發請求），那個事件就沒有了；
    欄位保留是因為日後可能有別的動作要記，而且移除它需要 migration，
    換來的只是一個永遠等於同一個值的欄位——不划算。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id", index=True)
    template_id: str = Field(index=True)
    difficulty: int = Field(index=True)
    seed: int                                          # 可完整重現該題
    action: str = Field(default="generate", index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
