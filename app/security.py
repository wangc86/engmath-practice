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

#: 帳號名稱的格式。v0.16（D35）起帳號只有兩組、由設定決定名稱，因此這條
#: 規則守的不再是「學號長得對不對」，而是「老師在環境變數裡打的東西是不是
#: 一個可以打進登入框的字串」。允許的字元刻意窄：全班要用嘴巴念它。
_ACCOUNT_NAME_RE = re.compile(r"^[a-z0-9\-]{3,32}$")

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


def normalize_account_name(raw: str) -> str:
    """正規化登入名稱：去空白、轉小寫。

    轉**小寫**是 v0.16 的改動（舊版的學號是轉大寫）。理由很實際：帳號名稱
    現在是老師在課堂上念出來、學生打進去的一個英文單字，而手機與平板的
    輸入法預設會把第一個字母自動大寫。
    """
    return raw.strip().lower()


def validate_account_name(name: str) -> str | None:
    """回傳錯誤訊息；None 表示通過。

    這個函式的讀者主要是老師（設定環境變數時）與 CLI，不是學生——學生打錯
    名稱看到的是統一的「帳號或密碼錯誤」，不會走到這裡。
    """
    if not name:
        return "Account name must not be empty."
    if not _ACCOUNT_NAME_RE.match(name):
        return (
            "Invalid account name (3-32 lowercase letters, digits or hyphens)."
        )
    return None


def validate_password(password: str, account_name: str = "") -> str | None:
    """刻意寬鬆：只要求長度與排除明顯的不良選擇。

    強制大小寫／符號組合會逼出「Abc12345!」這類可預測密碼，反而更糟。

    `account_name` 可以省略：v0.16 起這個函式的呼叫者只剩 `app/accounts.py`
    （老師自己指定密碼時驗一次），而那裡不一定有名稱在手上。
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
    if account_name and password.strip().lower() == account_name.lower():
        return "The password must not be the same as the account name."
    if password.isdigit():
        return "The password must not consist only of digits."
    if password.lower() in _WEAK_PASSWORDS:
        return "That password is too common. Please choose another one."
    return None


class RateLimiter:
    """單進程用的簡易滑動視窗計數器。

    MVP 是單一 uvicorn 進程，這樣就夠；多進程部署時要換成 Redis 或 DB 計數表。

    ⚠️ **v0.16（D38）：key 不得是 IP，也不得是任何可識別的東西。**
    這個類別本身不在乎 key 是什麼，但它會把 key 留在記憶體裡（一個視窗那麼久），
    而「系統不碰用戶端 IP」這句話寫在學生看得到的頁面上。現在唯一的呼叫者
    （`app/routes/auth.py`）用的是一個固定字串，理由與取捨見 `config.LOGIN_RATE_LIMIT`。
    `tests/test_web.py::test_nothing_in_the_app_reads_the_client_address` 盯著。
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
