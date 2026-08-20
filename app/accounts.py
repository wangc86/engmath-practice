"""帳號配發：產生初始密碼、批次建立帳號、重設密碼（D32）。

v0.15 起學生**不能自行註冊**（`/register` 已移除），帳號一律由老師預先建立、
把「學號 ↔ 初始密碼」的對照表發給修課學生。這個模組是那件事的核心邏輯；
命令列介面在 `scripts/create_accounts.py`，只是這裡的一層薄包裝。

**為什麼邏輯放在 `app/` 而不是直接寫在 `scripts/` 裡**：這樣測試才 import 得到
（`tests/test_accounts.py`），而且 `tests/test_web.py` 的每一個測試都是用
`create_account()` 建帳號的——也就是說老師實際要走的那條路徑，在整份測試裡
被走了數百次。寫在腳本裡就只能靠複製一份邏輯來測，那份複製品遲早會分岔。

---

## 初始密碼的格式與取捨

格式是 **`字-字-字-兩位數字`**，例如 `cedar-otter-flint-47`。

- **字典 256 個字、三個字、兩位數字（2–9）**
  → 熵 = log2(256³ × 8²) = 24 + 6 = **恰好 30 bits**。
  這個數字是刻意湊整的，好讓它可以被寫進文件、也可以被測試斷言
  （`test_accounts.py` 會檢查字典真的是 256 個相異的字）。

- **30 bits 夠不夠？** 這裡的威脅模型是**線上猜測**，不是離線破解
  （離線那一側由 argon2id 擋，見 `security.py`）。登入端點的速率限制是
  每 IP 每分鐘 10 次、每個學號每分鐘 10 次（`config.LOGIN_RATE_LIMIT`），
  以每分鐘 10 次計，猜完 2³⁰ 的一半要 **約 100 年**。夠。

- **為什麼不用隨機字元（如 `Xk7#pQ2m`）**：初始密碼要用嘴巴念、用眼睛從紙上
  抄、或從 Moodle 訊息裡手打。隨機字元在這三件事上都很糟，而它換來的熵
  （8 個字元 × 約 6 bits ≈ 48 bits）在**線上猜測**的威脅模型下毫無用處——
  30 bits 已經遠遠超過需要。付出可用性去買一個用不到的安全邊際，不划算。

- **為什麼排除 `0`、`1`（以及大寫）**：`l/1/I` 與 `O/0` 是手抄與口述時最常出錯的
  兩組。字典全小寫、只用 a–z，數字只用 2–9，因此**整個密碼裡不存在任何一對
  長得像的字元**。連字號用來斷字，讓「三個字」在視覺上是三個字。

- **長度**：字典的字都是 4–6 個字母，所以密碼長度落在 `4×3+3+2 = 17` 到
  `6×3+3+2 = 23` 個字元之間，遠高於 `MIN_PASSWORD_LENGTH`（8）。

- **`validate_password()` 一定過**：不是純數字、不等於學號、不在弱密碼清單裡。
  `generate_password()` 產出的密碼在寫進資料庫前仍然會再驗一次
  （見 `create_account()`），因為「一定過」是一個推論，不是一個保證。

---

## 明碼只存在於一個地方，而且是暫時的

`create_account()` 會把產生的明碼放在回傳值裡——那是老師印對照表唯一的來源。
**它不進資料庫、不進日誌、不進錯誤訊息**（專案硬規則 #2）。
對照表檔案本身含明碼，因此 `scripts/create_accounts.py` 會把檔名標成
`DELETE-ME`、權限設成 0600，並在檔案開頭印一段中文警告。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal, Optional

from sqlmodel import Session, select

from .db.models import Student
from .logging_setup import get_logger
from .security import (
    hash_password,
    normalize_student_no,
    validate_password,
    validate_student_no,
)

logger = get_logger(__name__)

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

#: 數字刻意不含 0 與 1——它們與字母 O、l 混淆的機率最高，而密碼是要用手抄的。
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
    """產生一組初始密碼，例如 ``cedar-otter-flint-47``。

    用 `secrets`（CSPRNG）而不是 `random`：這是真的要拿來當密碼的。
    """
    words = [secrets.choice(WORDLIST) for _ in range(PASSWORD_WORDS)]
    digits = "".join(secrets.choice(DIGIT_ALPHABET) for _ in range(PASSWORD_DIGITS))
    return PASSWORD_SEPARATOR.join([*words, digits])


# --- 建立與重設 -----------------------------------------------------------

Status = Literal["created", "reset", "skipped", "invalid"]


@dataclass(frozen=True)
class AccountResult:
    """一個學號處理完的結果。

    `password` **只有在真的產生了新密碼時**才非 None（`created` 與 `reset`）。
    `skipped` 與 `invalid` 一律是 None——沒有新密碼可以印，也沒有辦法從資料庫
    把舊密碼撈回來（那正是雜湊的意義）。
    """

    student_no: str
    status: Status
    password: Optional[str] = None
    detail: str = ""


def create_account(
    session: Session,
    student_no: str,
    *,
    password: Optional[str] = None,
    reset: bool = False,
) -> AccountResult:
    """建立一個帳號；已存在時預設**跳過**，`reset=True` 才重設密碼。

    「預設跳過」是刻意的，而且是這支工具最重要的一條安全性質：老師會重跑它
    （加退選、補發、手滑重跑），而**覆寫一個已存在的帳號等於把那個學生鎖在
    門外**——他手上的密碼突然失效，而且沒有任何錯誤訊息告訴他為什麼。
    因此覆寫必須是一個明確的動作（`reset=True` / CLI 的 `--reset-existing`）。

    `reset` **不會動 `consent_at`**：重設密碼與「有沒有讀過個資告知」是兩件事，
    已經同意過的人不該因為忘記密碼而被要求再同意一次。
    """
    student_no = normalize_student_no(student_no)

    if (err := validate_student_no(student_no)) is not None:
        # 這裡的 err 是給學生看的英文訊息，直接轉給老師看也讀得懂。
        logger.warning("學號格式不合，略過：%s（%s）", student_no or "(空白)", err)
        return AccountResult(student_no, "invalid", None, err)

    plaintext = password if password is not None else generate_password()

    # 「產生的密碼一定通過 validate_password」是一個推論，不是保證——而且老師
    # 也可能用 --password 指定一個自己想好的密碼。所以一律再驗一次。
    if (err := validate_password(plaintext, student_no)) is not None:
        logger.warning("密碼不符合規則，略過 %s：%s（此處不記錄密碼本身）",
                       student_no, err)
        return AccountResult(student_no, "invalid", None, err)

    existing = session.exec(
        select(Student).where(Student.student_no == student_no)
    ).first()

    if existing is not None and not reset:
        return AccountResult(student_no, "skipped", None, "帳號已存在，未變動")

    if existing is not None:
        existing.password_hash = hash_password(plaintext)
        session.add(existing)
        session.commit()
        logger.info("已重設密碼：%s", student_no)
        return AccountResult(student_no, "reset", plaintext, "已重設密碼")

    student = Student(
        student_no=student_no,
        password_hash=hash_password(plaintext),
        # consent_at 刻意留白：學生第一次登入時必須讀過個資告知才進得了系統
        # （D33）。這一欄是那道閘門唯一的依據。
        consent_at=None,
    )
    session.add(student)
    session.commit()
    logger.info("已建立帳號：%s", student_no)
    return AccountResult(student_no, "created", plaintext, "已建立")


def create_accounts(
    session: Session,
    student_nos: Iterable[str],
    *,
    reset: bool = False,
) -> list[AccountResult]:
    """批次版本。順序與輸入相同；重複的學號只處理第一次。

    重複的第二次之後會走到「帳號已存在 → skipped」，這是對的行為，但訊息會
    讀起來像「本來就有這個人」。因此在這裡先去重，讓訊息說實話。
    """
    seen: set[str] = set()
    results: list[AccountResult] = []
    for raw in student_nos:
        normalized = normalize_student_no(raw)
        if normalized in seen:
            results.append(
                AccountResult(normalized, "skipped", None, "清單裡重複出現，只處理一次")
            )
            continue
        seen.add(normalized)
        results.append(create_account(session, normalized, reset=reset))
    return results


def parse_student_list(text: str) -> list[str]:
    """從一份文字清單解析出學號。

    刻意寬鬆：一行一個，允許空行、允許 `#` 開頭的註解、允許用逗號或空白分隔
    （老師很可能是從 Excel 或校務系統複製貼上的）。行內 `#` 之後視為註解，
    這讓 `41047001  # 已退選` 這種寫法可以用。
    """
    out: list[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        for token in line.replace(",", " ").replace("\t", " ").split():
            out.append(token)
    return out


def list_accounts(session: Session) -> list[Student]:
    """列出所有帳號（不含任何密碼資訊）。給 CLI 的 `list` 子指令用。"""
    return list(session.exec(select(Student).order_by(Student.student_no)).all())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
