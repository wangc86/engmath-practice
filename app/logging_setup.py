"""應用層的 logging 設定。

系統跑在**使用者自己的電腦上**，而他唯一會看到的東西就是啟動它的那個終端機。
所以「有沒有印出來」等同「有沒有人知道」，本專案的規則因此是：

    任何被 `except` 吞掉的錯誤，都必須留下一行 log。

uvicorn 的預設 logging 設定只掛了 `uvicorn.*` 幾個 logger，root 上沒有 handler。
若不做任何事，`app.*` 的訊息會落到 `logging.lastResort`——只印 WARNING 以上、
沒有時間戳、沒有 logger 名稱，出事時完全查不出是什麼時候、哪個模組講的。
:func:`configure_logging` 就是補這一段，刻意做得很小。

---

## v0.29（D58）：「接管 uvicorn 存取紀錄」那一整套拆掉了

v0.16 的 D38 要求存取紀錄不得含用戶端 IP，因此這個檔案曾經有
`take_over_uvicorn_access_log()`、一份 `IP_BEARING_FIELDS` 黑名單、
以及一個自製的 `app/access_log.py` 中介層。**那整套的前提是「很多人連到
同一台伺服器，而它們的位址是個人資料」。**

系統改為本機執行之後那個前提消失了：唯一的用戶端是 `127.0.0.1`，
而唯一看得到那行 log 的人就是本人。留著它反而有害——它會讓讀程式的人
以為系統在保護什麼，而實際上它保護的是一個不存在的情境。

**現在 uvicorn 印它自己的存取紀錄，我們不碰。** 對一個在自己機器上除錯的
學生來說，那一行 `INFO: 127.0.0.1:54321 - "POST /practice/generate HTTP/1.1" 200`
是有用的，不是風險。

原本的實作保存在 tag `hosted-v1`（`app/access_log.py` 與這個檔案的舊版）。
"""

from __future__ import annotations

import logging
import sys

from .config import LOG_LEVEL

LOGGER_NAME = "app"

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None) -> logging.Logger:
    """把 `app` logger 接到 stderr，回傳它。重複呼叫是安全的。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level or LOG_LEVEL)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """模組用：`logger = get_logger(__name__)`。"""
    return logging.getLogger(name)
