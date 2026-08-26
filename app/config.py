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

# --- 兩組共用帳號的登入名稱（v0.16，D35）---------------------------------
#
# 系統裡只有這兩組帳號，而且**沒有任何途徑可以建立第三組**：沒有註冊頁、
# 沒有「新增帳號」的 CLI 子指令，`app/accounts.py` 只認得這兩個角色。
#
# 名稱可以改（老師想叫它 `engmath2026` 也行），但角色不能——排除老師的測試
# 流量靠的是 `Account.role`，不是名稱（理由寫在 `app/db/models.py`）。
CLASS_ACCOUNT_NAME = os.environ.get("CLASS_ACCOUNT_NAME", "class").strip().lower()
STAFF_ACCOUNT_NAME = os.environ.get("STAFF_ACCOUNT_NAME", "staff").strip().lower()

# 密碼規則（刻意寬鬆，見 PLAN.md §4.3）
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# --- 登入的速率限制（v0.16 大改，D35／D38）--------------------------------
#
# (次數, 秒數)。**這是一個全站共用的計數器，不分帳號、不分來源。**
#
# 舊版有兩個限制器：每 IP 每分鐘 10 次、每學號每分鐘 10 次。兩個都不能留：
#
# - **每 IP** 不能留，因為系統不再碰用戶端 IP（D38）。而且它本來就會出事：
#   一整班在校園 NAT 後面共用一個對外 IP，10 次／分鐘是**全班**的額度，
#   上課前大家同時登入就會互相把對方擋掉。
# - **每帳號**不能留，因為現在只有兩個帳號。一個人連打錯十次密碼，
#   就把全班鎖在門外了。
#
# 剩下的是一個全域計數器，門檻放寬到 120 次／分鐘。安全邊際仍然很夠：
# 初始密碼是 30 bits（`app/accounts.py`），以 120 次／分鐘猜完一半要
# 約 8,500 年。
#
# ⚠️ **代價要寫明**：全域計數器意味著一個人狂打就能讓所有人在那一分鐘內
# 登入失敗（訊息是 "Too many login attempts"，不是「密碼錯誤」，所以至少
# 不會讓人以為自己記錯密碼）。這是刻意接受的：視窗只有 60 秒、會自己恢復，
# 而換來的是「不會有人被別人的手滑鎖在外面一整節課」。
LOGIN_RATE_LIMIT = (120, 60)

# v0.16（D35）：`PASSWORD_CHANGE_RATE_LIMIT` 隨 `/account/password` 一起移除。
# 密碼是共用的，讓任何一個學生改掉它等於把全班鎖在門外——那個頁面在共用帳號
# 的前提下不是一個功能，是一個開關。改密碼改由老師用 CLI 執行。
#
# v0.15（D32）：`REGISTER_RATE_LIMIT` 隨自行註冊一起移除，至今沒有回來，
# 而且 D35 讓它更不可能回來——系統沒有「建立帳號」這個對外的概念了。

# v0.7（D12）：作答判定已捨棄，`GRADER_*` 六個設定與 `MAX_ANSWER_LENGTH`
# 隨之移除。舊的設定值保存在 tag grading-v1；環境裡若還留著 GRADER_* 變數，
# 現在只會被忽略（不會報錯，也不會有任何效果）。
