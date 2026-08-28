"""資料表（PLAN.md §4.1）。

目前有兩張表：`Account`（共用帳號）與 `UsageLog`（用量紀錄）。
預生成題庫的 `Problem` 仍是後續階段的事。

**v0.18（D41）：對話稽核的 `ChatLog` 不會建立。** 階段 3（對話介面 + LLM）
已從規劃中砍掉，而 `ChatLog` 正是砍掉它的主要理由之一——它的 `raw_text`
存的是學生打進去的原文，稽核的意義就是那一欄必須原樣留著（不能雜湊、不能省），
因此它是個人資料。**建了它，`_about.html` 對學生說的「不存你打的任何東西」
就變成假話**，而 v0.16 拆掉的那一整個個資法遵面必須整套復活。
規格留在 PLAN.md §3（整節標為已捨棄但保留）。

**v0.7（D12）移除了 `Attempt`**（作答紀錄）：系統不再判定學生的答案，
也不再蒐集作答內容。模型定義保存在 tag `grading-v1`。

**v0.16（D35–D36）：`Student` 改名為 `Account`，而且改的不只是名字。**
系統改為共用帳號——全班一組、老師與助教一組，總共就兩列——因此：

- `student_no` 這一欄整個消失。它是這個系統裡唯一一項個人資料
  （學號可間接識別特定個人，見已被取代的 §4.4），拿掉它之後
  **資料庫裡不再有任何欄位指得到特定的人**。
- `consent_at` 一併消失（D37）：沒有個資可蒐集，就沒有告知義務，
  也就沒有同意這件事。閘門改成純粹的登入閘門（`app/login_gate.py`）。
- `UsageLog.student_id` 改名為 `account_id`，**欄位數不變**。它現在的值
  只有兩種，用途也只剩一個：把老師的測試流量與全班的實際使用分開
  （理由見 `UsageLog` 的說明）。

⚠️ **沒有做 migration，而且這一次會（刻意地）大聲壞掉。** 欄位改了名字，
`SQLModel.metadata.create_all()` 只建缺少的表、不會去改既有的表，所以
**舊的 `practice.db` 接上新程式會在第一次寫紀錄時噴 `no such column`**。
與其讓它壞在半夜的某一個請求上，`app/db/session.py::init_db()` 會在啟動時
先檢查並拒絕啟動（規則 4：不做無聲降級）。實際資料庫裡只有測試資料，
處理方式就是把舊檔刪掉重建，README 有寫。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

#: 全班共用的帳號。發給所有修課學生。
ROLE_CLASS = "class"

#: 老師與助教測試用的帳號。它的用量**不計入全班統計**（D36）。
ROLE_STAFF = "staff"

#: 系統裡允許存在的角色就這兩個，沒有第三種，也沒有辦法從網頁上長出新的。
ROLES = (ROLE_CLASS, ROLE_STAFF)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(SQLModel, table=True):
    """一組**共用**帳號。這張表永遠只有兩列（D35）。

    「一列 = 一個人」在 v0.15 以前是成立的，v0.16 之後不是了：一列現在代表
    「一個進得了系統的身分」，而那個身分背後有幾十個人。這件事必須寫在
    模型上，因為所有「這個帳號做了什麼」的查詢在讀起來像「這個人做了什麼」，
    而它已經不是了。

    **欄位裡沒有任何一項是個人資料**，這是 D35 的重點，不是附帶效果：

    - `name`：登入名稱，預設是 ``"class"`` 與 ``"staff"``（可由設定改）。
      它識別的是角色，不是人。
    - `role`：`ROLE_CLASS` / `ROLE_STAFF`。**統計把 staff 排除在外靠的是它**，
      所以它不能從 `name` 推導——老師哪天把登入名稱改成 `engmath2026`，
      推導就會安靜地失效，而失效的症狀是「老師自己的測試流量混進全班統計」，
      沒有任何東西會報錯。
    - `last_login_at`：**最後一次有人登入的時間**，不是「他上次登入」。
      留著是因為它回答得了一個老師真的會問的問題：這個帳號到底有沒有人在用。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)         # 登入名稱（角色，不是人）
    role: str = Field(index=True)                      # ROLE_CLASS / ROLE_STAFF
    password_hash: str                                 # argon2id，**絕不存明碼**
    created_at: datetime = Field(default_factory=_utcnow)
    last_login_at: Optional[datetime] = None


class UsageLog(SQLModel, table=True):
    """用量紀錄：哪一組帳號、什麼時候、做了哪個題型、哪個難度。一列 = 一個動作。

    刻意不含作答內容與對錯 —— 系統不判定答案（D12），這張表只記用量（D1）。

    ⚠️ **欄位不得擴充，而且這條規則在 v0.16 換了理由**（D36）。
    v0.15 以前的理由是「這張表的內容就是個資告知寫明的範圍」；告知沒有了
    （D37），但規則留下來，理由改成更根本的一條：
    **這張表不得長出任何指得到特定個人的欄位。** 例如 session id、
    user agent、IP、時間精度細到可以當指紋的東西——加進來的那一刻，
    「系統不知道你是誰」這句話就變成假的，而**頁面上寫著那句話**。
    `tests/test_web.py::test_usage_log_cannot_identify_a_person` 盯著。

    ### `account_id` 為什麼留著

    全班共用一個帳號之後這一欄只會有兩個值，看起來形同無用。但那兩個值
    分別是「全班」與「老師測試」，而**老師的測試流量不該混進全班統計**：
    改一頁版面要重新整理十幾次，那十幾列會讓「這週學生練了幾題」直接失真。
    移除它的話只剩兩條路，兩條都比留著差：老師測試時不寫紀錄（於是
    「有沒有寫進去」變成一件無法驗證的事），或者讓它混進統計（於是統計不能用）。

    它也**沒有帶來任何個資風險**——`account_id` 指向的那一列裡沒有人。

    考慮過但沒有採用的替代方案：直接存一個 `role` 字串而不是外鍵。
    好處是老師砍掉重建帳號之後舊紀錄仍然分得出角色；壞處是同一件事有兩份
    真相（`Account.role` 與這裡），而 `Account` 那份會被當成權威。
    在「帳號只會被建立與重設、不會被刪除」的前提下外鍵比較誠實。

    `action` 目前只有 ``"generate"`` 與 ``"demo_open"``（§8.7）。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    template_id: str = Field(index=True)
    difficulty: int = Field(index=True)
    seed: int                                          # 可完整重現該題
    action: str = Field(default="generate", index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
