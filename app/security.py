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
from .logging_setup import get_logger

logger = get_logger(__name__)

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
    """驗證失敗一律回傳 False，不讓例外洩漏「帳號是否存在」的資訊。

    三種失敗要分開看（但對呼叫端一律是 False，時間行為也一致）：

    - `VerifyMismatchError`：密碼打錯。這是最正常不過的事，**不記 log**
      ——記了只會製造雜訊，還等於留下一份「誰在什麼時候登入失敗」的紀錄。
    - `InvalidHashError` / 其他 `VerificationError`：資料庫裡那串雜湊本身壞了。
      這種帳號**永遠登入不了**，學生只會看到「密碼錯誤」而百思不解，
      所以一定要記——但只記事實，不記雜湊、更不記密碼（專案硬規則 #2）。
    """
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError) as exc:
        logger.warning(
            "資料庫裡有一筆密碼雜湊無法解讀（%s）。該帳號會永遠登入失敗，"
            "需要重設密碼才救得回來。（此處不記錄雜湊與密碼本身。）",
            type(exc).__name__,
        )
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except InvalidHashError:
        # 回 True 讓呼叫端有機會在下次成功登入時換一份新的雜湊。
        logger.warning("有一筆密碼雜湊格式無法辨識，已標記為需要重新雜湊。")
        return True


def normalize_student_no(raw: str) -> str:
    return raw.strip().upper()


def validate_student_no(student_no: str) -> str | None:
    """回傳錯誤訊息；None 表示通過。"""
    if not student_no:
        return "Please enter your student ID."
    if not _STUDENT_NO_RE.match(student_no):
        return "Invalid student ID format (4-20 letters, digits or hyphens)."
    return None


def validate_password(password: str, student_no: str) -> str | None:
    """刻意寬鬆：只要求長度與排除明顯的不良選擇。

    強制大小寫／符號組合會逼出「Abc12345!」這類可預測密碼，反而更糟。
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
    if password.strip().upper() == student_no.upper():
        return "Your password must not be the same as your student ID."
    if password.isdigit():
        return "Your password must not consist only of digits."
    if password.lower() in _WEAK_PASSWORDS:
        return "That password is too common. Please choose another one."
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
