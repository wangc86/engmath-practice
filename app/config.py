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
# 常駐 worker 的數量，同時也是**判定的併發上限**（判定是 CPU 密集工作，
# 讓它無限並行只會讓所有人一起變慢）。尖峰估算與調法見 README「運維」。
GRADER_WORKERS = int(os.environ.get("GRADER_WORKERS", "2"))
# 所有 worker 都在忙時，一個請求最多排隊多久。超過就回「系統忙碌」給學生，
# 而不是讓 HTTP 連線一直掛著。全班同時交卷時會用到這條路徑。
GRADER_QUEUE_TIMEOUT = float(os.environ.get("GRADER_QUEUE_TIMEOUT", "20"))
# 啟動時先把判定用的子行程叫起來（省掉第一位學生等 sympy import 的 1 秒）。
# 這同時是一個**啟動自檢**：暖機失敗代表這台機器開不了子行程，判定就沒有 timeout，
# 服務會直接拒絕啟動（D8，見 app/grader/sandbox.py 的說明）。
# 測試裡會關掉：每個測試都有自己的 lifespan，每次都暖機一遍反而拖慢整份測試。
GRADER_WARMUP = os.environ.get("GRADER_WARMUP", "1") == "1"
# 暖機的時間上限。給得很寬鬆，因為它要涵蓋子行程 import sympy 的時間，
# 而部署當下的機器可能正在忙別的事；超過這個時間才算「這台機器有問題」。
GRADER_WARMUP_TIMEOUT = float(os.environ.get("GRADER_WARMUP_TIMEOUT", "60"))
MAX_ANSWER_LENGTH = 300                   # 學生輸入的硬上限（字元）
