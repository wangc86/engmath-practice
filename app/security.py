"""密碼雜湊、密碼規則與速率限制（PLAN.md §4.3）。

**密碼一律以 argon2id 雜湊儲存，任何情況下都不寫入明碼**
—— 不進資料庫、不進日誌、不出現在錯誤訊息或範本上下文中。
"""

from __future__ import annotations

import re
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

_ph = PasswordHasher()

_STUDENT_NO_RE = re.compile(r"^[A-Za-z0-9\-]{4,20}$")

# 常見弱密碼（示意；正式部署可換成前 1000 名清單檔）
_WEAK_PASSWORDS = {
    "password", "12345678", "123456789", "1234567890", "qwertyui",
    "iloveyou", "abcd1234", "a1234567", "password1", "11111111",
    "88888888", "asdfghjk", "qwerty123", "admin123", "letmein1",
}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """驗證失敗一律回傳 False，不讓例外洩漏「帳號是否存在」的資訊。"""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def normalize_student_no(raw: str) -> str:
    return raw.strip().upper()


def validate_student_no(student_no: str) -> str | None:
    """回傳錯誤訊息；None 表示通過。"""
    if not student_no:
        return "請輸入學號。"
    if not _STUDENT_NO_RE.match(student_no):
        return "學號格式不正確（限 4–20 個英數字或連字號）。"
    return None


def validate_password(password: str, student_no: str) -> str | None:
    """刻意寬鬆：只要求長度與排除明顯的不良選擇。

    強制大小寫／符號組合會逼出「Abc12345!」這類可預測密碼，反而更糟。
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密碼至少需要 {MIN_PASSWORD_LENGTH} 個字元。"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"密碼長度不可超過 {MAX_PASSWORD_LENGTH} 個字元。"
    if password.strip().upper() == student_no.upper():
        return "密碼不可與學號相同。"
    if password.isdigit():
        return "密碼不可全部都是數字。"
    if password.lower() in _WEAK_PASSWORDS:
        return "這組密碼太常見，請換一組。"
    return None


class RateLimiter:
    """單進程用的簡易滑動視窗計數器。

    MVP 是單一 uvicorn 進程，這樣就夠；多進程部署時要換成 Redis 或 DB 計數表。
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = [h for h in self._hits[key] if now - h < self.window]
        self._hits[key] = hits
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()
