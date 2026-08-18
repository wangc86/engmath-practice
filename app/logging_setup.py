"""應用層的 logging 設定。

這個系統是**單人維護、校內自架**的。維護者唯一會看到的東西就是 uvicorn 那個
終端機（或 systemd 的 journal），所以「有沒有印出來」等同「有沒有人知道」。
因此本專案的規則是：

    任何被 `except` 吞掉的錯誤，都必須留下一行 log。

uvicorn 的預設 logging 設定只掛了 `uvicorn.*` 幾個 logger，root 上沒有 handler。
若不做任何事，`app.*` 的訊息會落到 `logging.lastResort`——只印 WARNING 以上、
沒有時間戳、沒有 logger 名稱，出事時完全查不出是什麼時候、哪個模組講的。
:func:`configure_logging` 就是補這一段，刻意做得很小：

- 只碰 `app` 這一個 logger，不動 root，也不動 uvicorn 自己的設定；
- 已經有 handler 就什麼都不做（部署時若有人用 `--log-config` 接管，我們讓路）。
"""

from __future__ import annotations

import logging
import os
import sys

LOGGER_NAME = "app"

# 想看更細的東西（例如判定為什麼給不出提示）時設 APP_LOG_LEVEL=DEBUG
DEFAULT_LEVEL = os.environ.get("APP_LOG_LEVEL", "INFO").upper()

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None) -> logging.Logger:
    """把 `app` logger 接到 stderr，回傳它。重複呼叫是安全的。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level or DEFAULT_LEVEL)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """模組用：`logger = get_logger(__name__)`。"""
    return logging.getLogger(name)
