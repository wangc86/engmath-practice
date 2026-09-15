"""網站首頁：十六週的課表。

**為什麼首頁不再是出題頁（v0.45）。** 在這之前 `/` 就是出題頁，而頁首右上角
那個「Practice」連的也是 `/`——也就是首頁沒有回答「這是什麼、裡面有什麼」，
它直接把人放在一個下拉選單前面。老師要的是先看見整學期：

    先列出 16 週的 schedule ，接著下面提示讀者頁面右上角有練習題及 demos。

所以 `/` 換成這一頁，出題頁搬到 `/practice`（`POST /practice/generate` 本來
就在那個前綴底下，兩邊因此對得起來）。

---

## ⛔ 這一頁**只有**課表，不註明哪一週有題目或展示

第一版我多加了一欄「這一週現在有什麼」（`3 practice topics · 1 demo`，
空的那幾週是一個破折號），理由是十六列看起來都一樣、讀的人會以為十六週都
做好了。**老師看過之後指示拿掉**：

    首頁請單純放 16 週課表即可，不需要加連結到特定的題組或 demo ，
    也不需在課表上註明有什麼題組或 demo。

⚠️ **那個理由沒有被推翻，是被一個更上位的決定取代了**——這是老師的課程頁，
課表要呈現的是**這門課教什麼**，不是這個工具做到哪裡。寫下來是為了下一個
讀到這裡的人：**不要「順手」把那一欄加回來**。⛔ 連帶的一件事是這一頁
**不 import 註冊表、也不 import `curriculum` 以外的任何東西**：一旦要算
「有幾個」，`list_templates()` 就會被拉進來，而那正是那一欄的入口。

⚠️ 頁面最下面那句指路仍然在（老師指定的），但它指的是**右上角那兩個連結**
這件事本身，不是任何一週有什麼。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..curriculum import WEEKS
from .deps import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    # ⛔ 直接把 `WEEKS` 交給範本，不抄一份、也不整形。抄一份就是第二真相，
    # 而課表是 D23 從老師的課程網頁抄下來的——它會改。
    return templates.TemplateResponse(request, "home.html", {"weeks": WEEKS})
