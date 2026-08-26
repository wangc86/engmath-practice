"""兩組共用帳號的建立與密碼重設（D35）。

v0.16 起系統**只有兩組帳號**：

- **`class`** —— 全班共用，發給所有修課學生。
- **`staff`** —— 老師與助教測試用。它的用量不計入全班統計（D36）。

沒有第三組，也沒有任何途徑可以長出第三組：沒有註冊頁（v0.15 就移除了）、
沒有「新增任意帳號」的 CLI 子指令，這個模組只認得 `ROLES` 裡的那兩個角色。
命令列介面在 `scripts/create_accounts.py`，只是這裡的一層薄包裝。

---

## 與 v0.15 的差別：少了什麼，以及為什麼

v0.15 的這個模組是**逐人配發**：一份學號清單 → 一人一組初始密碼 →
一份含明碼的 CSV 對照表。那整套東西在共用帳號之下全部沒有意義，因此拿掉了
`create_accounts()`（批次）、`parse_student_list()`（解析名單）、
以及 `scripts/` 那一側的對照表輸出。

**最有價值的一項副作用：明碼不再落地成檔案。** v0.15 的 §4.4 第 6 點寫著
「系統多了一個明碼會落地的地方，而且只有一個：老師的對照表」——那個地方
現在沒有了。密碼只印在終端機上一次，老師念給全班聽或貼進 Moodle 公告，
系統這一側**不存在任何含明碼的檔案**。

---

## 初始密碼的格式與取捨（大致沿用，但威脅模型換了）

格式仍是 **`字-字-字-兩位數字`**，例如 `cedar-otter-flint-47`。

- **字典 256 個字、三個字、兩位數字（2–9）**
  → 熵 = log2(256³ × 8²) = 24 + 6 = **恰好 30 bits**。

- **「好念、好抄」這個需求在共用帳號之下更強，不是更弱。** v0.15 的密碼是
  一人一組、寫在紙上發下去；v0.16 的密碼是**老師在課堂上念出來、全班當場
  打進去的一個字串**。念錯一次，三十個人一起打錯。因此字典全小寫、
  只用 a–z、數字只用 2–9，整個密碼裡不存在任何一對長得像的字元
  （`l/1/I`、`O/0`），連字號讓「三個字」在視覺上就是三個字。

- **30 bits 夠不夠？威脅模型變了，但結論沒變。** 舊的威脅是「有人猜某個
  學生的密碼」；新的威脅是「不相干的人猜到那個全班共用的密碼」——後者的
  價值高一點（進得去就看得到整個系統），但代價一樣是線上猜測，而登入端點
  的速率限制是**全站** 120 次／分鐘（`config.LOGIN_RATE_LIMIT`）。
  以 120 次／分鐘計，猜完 2³⁰ 的一半要約 **8,500 年**。夠。

  ⚠️ 真正的風險不是被猜到，是**被轉傳**：一個共用密碼會出現在 LINE 群組、
  共筆、學長姐的筆記裡。這件事技術上擋不住，緩解是換密碼很便宜
  （`create_accounts.py reset class`，一行），而且系統裡本來就沒有值得偷的東西
  ——沒有個人資料、沒有成績、沒有作答內容。

- **`validate_password()` 一定過**：夠長、不是純數字、不等於帳號名稱、
  不在弱密碼清單裡。`generate_password()` 產出的密碼在寫進資料庫前仍然會
  再驗一次，因為「一定過」是一個推論，不是一個保證。

---

## 明碼只存在於一個地方，而且是暫時的

`ensure_account()` 會把產生的明碼放在回傳值裡——那是老師唯一的來源。
**它不進資料庫、不進日誌、不進錯誤訊息**（專案硬規則 #2）。
CLI 把它印在終端機上，然後就沒有了；資料庫裡只有 argon2id 雜湊。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlmodel import Session, select

from .config import CLASS_ACCOUNT_NAME, STAFF_ACCOUNT_NAME
from .db.models import ROLE_CLASS, ROLE_STAFF, ROLES, Account
from .logging_setup import get_logger
from .security import (
    hash_password,
    normalize_account_name,
    validate_account_name,
    validate_password,
)

logger = get_logger(__name__)

#: 角色 → 預設登入名稱。名稱可由環境變數改，角色不行（`db/models.py` 說明了為什麼）。
ROLE_NAMES: dict[str, str] = {
    ROLE_CLASS: CLASS_ACCOUNT_NAME,
    ROLE_STAFF: STAFF_ACCOUNT_NAME,
}

#: 角色的一句話說明，CLI 與錯誤訊息共用（中文，讀者是老師）。
ROLE_DESCRIPTION: dict[str, str] = {
    ROLE_CLASS: "全班共用，發給所有修課學生",
    ROLE_STAFF: "老師與助教測試用（用量不計入全班統計）",
}

# --- 初始密碼 -------------------------------------------------------------

#: 256 個常見英文字，長度 4–6，全小寫、只含 a–z。
#: **數量必須恰好是 256**（= 2^8），熵的算法才是整數；`test_accounts.py` 盯著。
#: 挑字的標準：具體、常見、好念、不帶感情色彩，避免縮寫與專有名詞。
WORDLIST: tuple[str, ...] = (
    "alder", "amber", "anchor", "apple", "arrow", "aspen", "atlas", "autumn",
    "azure", "badger", "bamboo", "basil", "basket", "beacon", "beige", "berry",
    "birch", "bison", "brave", "bread", "breeze", "bridge", "bright", "brisk",
    "bronze", "brook", "bucket", "butter", "cactus", "calm", "camel", "candle",
    "canvas", "canyon", "castle", "cavern", "cedar", "chapel", "cheese", "cherry",
    "chill", "chisel", "cider", "city", "clever", "cliff", "cloud", "clover",
    "coast", "cobalt", "cobra", "cocoa", "copper", "coral", "cradle", "crane",
    "crayon", "creek", "crisp", "crown", "dagger", "daisy", "dawn", "delta",
    "dock", "drift", "drum", "dune", "dusk", "eager", "eagle", "easel",
    "ember", "engine", "fair", "falcon", "fennel", "fern", "ferret", "fjord",
    "flint", "flute", "fresh", "frost", "gale", "garnet", "gecko", "gentle",
    "ginger", "glad", "golden", "green", "grove", "gust", "hammer", "happy",
    "haze", "hazel", "helmet", "heron", "honey", "ibex", "indigo", "ingot",
    "ivory", "jacket", "jade", "jaguar", "jolly", "keen", "kettle", "khaki",
    "kind", "ladder", "laurel", "lemon", "lemur", "lever", "lilac", "lime",
    "lively", "llama", "lotus", "lucky", "mallet", "mango", "maple", "marble",
    "maroon", "marsh", "marten", "mauve", "melon", "merry", "mesa", "mirror",
    "mist", "moss", "navy", "neat", "needle", "noble", "nutmeg", "oasis",
    "ochre", "olive", "orchid", "otter", "paddle", "palm", "panda", "peach",
    "pear", "pearl", "pebble", "pecan", "pepper", "pillar", "pine", "plain",
    "plank", "plum", "poppy", "prism", "proud", "purple", "quail", "quartz",
    "quick", "quiet", "quince", "quiver", "rain", "raisin", "rapid", "raven",
    "ready", "reef", "ribbon", "rice", "ridge", "river", "rocket", "ruby",
    "rudder", "russet", "saddle", "sage", "salmon", "scroll", "sepia", "shade",
    "sharp", "shore", "shovel", "sickle", "sienna", "silver", "slate", "sleet",
    "smart", "snow", "solid", "spade", "spool", "sprout", "steady", "stone",
    "storm", "sturdy", "summer", "sunny", "swift", "syrup", "tablet", "tapir",
    "teal", "thaw", "thorn", "thread", "thyme", "tide", "tidy", "timber",
    "tinder", "tomato", "torch", "toucan", "trowel", "tulip", "tunnel", "umber",
    "vale", "velvet", "vine", "violet", "vivid", "wagon", "walnut", "walrus",
    "warm", "weasel", "wheat", "white", "willow", "wind", "winter", "witty",
    "wombat", "wrench", "yarn", "yogurt", "yucca", "zebra", "zephyr", "zipper",
)

#: 數字刻意不含 0 與 1——它們與字母 O、l 混淆的機率最高，而密碼是要用嘴巴念的。
DIGIT_ALPHABET = "23456789"

PASSWORD_WORDS = 3
PASSWORD_DIGITS = 2
PASSWORD_SEPARATOR = "-"


def password_entropy_bits() -> float:
    """初始密碼的熵（bits）。目前的參數下恰好是 30.0。

    寫成函式而不是常數，是為了讓它跟著實際參數走：日後有人改了字典長度或
    位數，文件與測試裡的數字會一起變，不會留下一個過期的 30。
    """
    from math import log2

    return (
        PASSWORD_WORDS * log2(len(WORDLIST))
        + PASSWORD_DIGITS * log2(len(DIGIT_ALPHABET))
    )


def generate_password() -> str:
    """產生一組密碼，例如 ``cedar-otter-flint-47``。

    用 `secrets`（CSPRNG）而不是 `random`：這是真的要拿來當密碼的。
    """
    words = [secrets.choice(WORDLIST) for _ in range(PASSWORD_WORDS)]
    digits = "".join(secrets.choice(DIGIT_ALPHABET) for _ in range(PASSWORD_DIGITS))
    return PASSWORD_SEPARATOR.join([*words, digits])


# --- 建立與重設 -----------------------------------------------------------

Status = Literal["created", "reset", "skipped", "invalid"]


@dataclass(frozen=True)
class AccountResult:
    """一個角色處理完的結果。

    `password` **只有在真的產生了新密碼時**才非 None（`created` 與 `reset`）。
    `skipped` 與 `invalid` 一律是 None——沒有新密碼可以印，也沒有辦法從資料庫
    把舊密碼撈回來（那正是雜湊的意義）。
    """

    role: str
    name: str
    status: Status
    password: Optional[str] = None
    detail: str = ""


def account_name_for(role: str) -> str:
    return normalize_account_name(ROLE_NAMES[role])


def ensure_account(
    session: Session,
    role: str,
    *,
    password: Optional[str] = None,
    reset: bool = False,
) -> AccountResult:
    """建立某個角色的帳號；已存在時預設**跳過**，`reset=True` 才重設密碼。

    「預設跳過」在共用帳號之下比在逐人配發之下**更**重要：覆寫一個已存在的
    帳號，代價從「一個學生被鎖在門外」變成「**全班**同時被鎖在門外，而且是
    在老師只是想確認帳號建好了沒的時候」。因此覆寫必須是一個明確的動作
    （`reset=True` / CLI 的 `reset` 子指令）。
    """
    if role not in ROLES:
        # 這條路徑在 CLI 上走不到（argparse 的 choices 擋著），留著是因為
        # 這個函式也被測試與日後可能的其他呼叫者用。
        logger.warning("未知的角色，略過：%s（只有 %s）", role, "、".join(ROLES))
        return AccountResult(role, "", "invalid", None, f"unknown role: {role}")

    name = account_name_for(role)
    if (err := validate_account_name(name)) is not None:
        # 名稱來自設定，所以這裡是老師打錯環境變數。**不靜默**（規則 4）：
        # 名稱不合法就等於這個角色永遠登入不了，而畫面上不會有任何提示。
        logger.error(
            "帳號名稱不合法：角色 %s 的名稱是 %r（%s）。"
            "請檢查環境變數 CLASS_ACCOUNT_NAME／STAFF_ACCOUNT_NAME。",
            role, name, err,
        )
        return AccountResult(role, name, "invalid", None, err)

    plaintext = password if password is not None else generate_password()

    if (err := validate_password(plaintext, name)) is not None:
        logger.warning(
            "密碼不符合規則，略過角色 %s：%s（此處不記錄密碼本身）", role, err
        )
        return AccountResult(role, name, "invalid", None, err)

    existing = session.exec(select(Account).where(Account.role == role)).first()

    if existing is not None and not reset:
        return AccountResult(role, existing.name, "skipped", None, "帳號已存在，未變動")

    if existing is not None:
        existing.name = name          # 老師改了環境變數就跟著改
        existing.password_hash = hash_password(plaintext)
        session.add(existing)
        session.commit()
        logger.info("已重設密碼：角色 %s（登入名稱 %s）", role, name)
        return AccountResult(role, name, "reset", plaintext, "已重設密碼")

    account = Account(name=name, role=role, password_hash=hash_password(plaintext))
    session.add(account)
    session.commit()
    logger.info("已建立帳號：角色 %s（登入名稱 %s）", role, name)
    return AccountResult(role, name, "created", plaintext, "已建立")


def ensure_all_accounts(
    session: Session, *, reset: bool = False
) -> list[AccountResult]:
    """把兩個角色都準備好。順序固定：先 class 再 staff。"""
    return [ensure_account(session, role, reset=reset) for role in ROLES]


def list_accounts(session: Session) -> list[Account]:
    """列出所有帳號（不含任何密碼資訊）。給 CLI 的 `list` 子指令用。"""
    return list(session.exec(select(Account).order_by(Account.role)).all())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
