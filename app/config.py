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
SUBMIT_RATE_LIMIT = (60, 60)              # 每位學生每分鐘的作答提交上限

# 作答判定（PLAN.md §5）
GRADER_TIMEOUT_SECONDS = float(os.environ.get("GRADER_TIMEOUT", "5"))
GRADER_WORKERS = int(os.environ.get("GRADER_WORKERS", "2"))
# 啟動時先把判定用的子行程叫起來（省掉第一位學生等 sympy import 的 1 秒）。
# 測試裡會關掉：每個測試都有自己的 lifespan，每次都暖機一遍反而拖慢整份測試。
GRADER_WARMUP = os.environ.get("GRADER_WARMUP", "1") == "1"
MAX_ANSWER_LENGTH = 300                   # 學生輸入的硬上限（字元）
