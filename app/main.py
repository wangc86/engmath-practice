"""FastAPI 進入點。

啟動方式（安裝步驟見 `INSTALL-LINUX.md` 或 `INSTALL-MACOS.md`）：

    uvicorn app.main:app

---

## v0.29（D57–D59）：這個檔案短了一半，而短掉的每一行都有名字

在這之前它有三層中介層、兩個例外處理器、一個會建資料表的 lifespan。
系統改為**學生自行在自己的電腦上安裝執行**之後：

- `SessionMiddleware`、`LoginGateMiddleware`、`NotLoggedIn`／`NotStaff`
  —— 沒有登入了（D57）。本機單人使用，登入沒有守護對象：能執行
  `uvicorn` 的人本來就讀得到整個資料夾。
- `AccessLogMiddleware` —— 沒有要保護的位址了（D58）。
- `ReleaseGateMiddleware` —— 沒有「老師控制學生看得到什麼」這件事了（D59）。
  學生擁有自己那一份安裝，任何閘門都是他自己可以改掉的。
- `init_db()` —— 三張表全部移除，沒有資料庫（D58）。

⚠️ **`openapi_url=None` 留著。** 它與登入無關：這個系統沒有 API 消費者，
互動式文件也早就關了，掛著一條會回傳整張路由表的端點只是多一個沒有人
維護的出口。（順帶一提，它是 v0.28 那項「每一條路由都要被分類」的測試
逼出來的，而那項測試已經隨閘門一起移除了——所以理由改記在這裡。）

**現在它是一個沒有狀態的應用程式**：沒有資料庫、沒有 session、沒有任何
會被寫到磁碟上的東西。關掉它就什麼都不剩，而那正是 D57 想要的性質。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .logging_setup import configure_logging
from .routes import demos, practice

STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = configure_logging()

app = FastAPI(
    title="Engineering Mathematics Practice",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(practice.router)
# 第二個功能區（PLAN.md §8）。與出題引擎只共用版面與自架資產（D21）。
app.include_router(demos.router)


@app.get("/healthz")
def healthz():
    """存活檢查。

    留著的理由與 v0.28 之前不同：那時它是給監控用的。現在沒有監控，
    它剩下一個用途——**安裝說明裡用它確認伺服器真的起來了**
    （`curl http://127.0.0.1:8000/healthz`），而那比叫學生去看瀏覽器可靠：
    瀏覽器連不上時分不出是伺服器沒起來還是網址打錯。
    """
    return {"status": "ok"}
