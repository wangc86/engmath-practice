"""共用的 Jinja2 環境。

**v0.29（D57）之後這個檔案只剩三行有作用的程式碼。**

它原本住著登入相依注入（`current_account`／`staff_account`）與兩個例外
（`NotLoggedIn`／`NotStaff`）。系統改為本機單人執行之後那些全部沒有標的了
——能執行 `uvicorn app.main:app` 的人本來就讀得到整個資料夾，一道問他
「你是誰」的門擋不住任何人，只會多一個要輸入的密碼。

檔案本身留下來（沒有併進 `main.py`）是因為兩個路由模組都 import 它拿
`templates`，而那是一個真的共用點。保存版本見 tag `hosted-v1`。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# autoescape 預設開啟。⚠️ 範本中唯一的 `|safe` 是相圖的 SVG，
# 而它的鍵受 `generator.base.ASSET_KEYS` 白名單管制（見該處說明）。
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
