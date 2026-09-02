"""設定。

**v0.29（D57）之後這個檔案幾乎是空的，而那是一件好事。**

在這之前它有九組設定：資料庫路徑、session 金鑰、cookie 安全旗標、兩組共用
帳號的登入名稱、密碼長度規則、登入速率限制。**那九組全部是「一個公開網站」
才需要的東西**——系統改為學生自行在自己的電腦上安裝執行之後：

- 沒有資料庫（三張表全部移除，D58），所以沒有 `PRACTICE_DB`。
- 沒有登入（D57），所以沒有 `SESSION_SECRET`、`COOKIE_SECURE`、
  帳號名稱、密碼規則、速率限制。

剩下的只有一個，而且它與功能無關：log 的層級。

⚠️ **不要為了「將來也許要部署」把那些設定留著。** 一組沒有使用者的設定
會讓讀程式的人以為系統支援某件事，而它不支援；真的要回頭做站台版，
`git checkout hosted-v1 -- app/config.py` 一行就取得回來。
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

#: 想看更細的東西時設 `APP_LOG_LEVEL=DEBUG`。這是整個系統唯一的設定。
LOG_LEVEL = os.environ.get("APP_LOG_LEVEL", "INFO").upper()
