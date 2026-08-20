"""設定（全部可用環境變數覆寫，見 README）。"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite 檔案位置。務必放在非 web root 的目錄，且權限設為 600。
DB_PATH = Path(os.environ.get("PRACTICE_DB", BASE_DIR / "practice.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Session cookie 的簽章金鑰。正式環境**必須**由環境變數提供，
# 否則每次重啟都會換一把新的，所有人都會被登出。
SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
SESSION_MAX_AGE = 14 * 24 * 3600          # 14 天

# 正式環境（HTTPS）請設 COOKIE_SECURE=1
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

# 密碼規則（刻意寬鬆，見 PLAN.md §4.3）
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# 速率限制：(次數, 秒數)
LOGIN_RATE_LIMIT = (10, 60)
# 修改密碼要驗舊密碼，等於是第二個可以猜密碼的地方（而且猜的人已經登入了）。
# 限制比登入寬鬆一點——打錯舊密碼是很常見的手滑，但仍然要有上限。
PASSWORD_CHANGE_RATE_LIMIT = (10, 300)

# v0.15（D32）：`REGISTER_RATE_LIMIT` 隨自行註冊一起移除。帳號改由老師用
# `scripts/create_accounts.py` 預先建立，沒有任何對外的帳號建立端點可以被灌。

# v0.7（D12）：作答判定已捨棄，`GRADER_*` 六個設定與 `MAX_ANSWER_LENGTH`
# 隨之移除。舊的設定值保存在 tag grading-v1；環境裡若還留著 GRADER_* 變數，
# 現在只會被忽略（不會報錯，也不會有任何效果）。
