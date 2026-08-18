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
REGISTER_RATE_LIMIT = (5, 300)

# v0.7（D12）：作答判定已捨棄，`GRADER_*` 六個設定與 `MAX_ANSWER_LENGTH`
# 隨之移除。舊的設定值保存在 tag grading-v1；環境裡若還留著 GRADER_* 變數，
# 現在只會被忽略（不會報錯，也不會有任何效果）。
