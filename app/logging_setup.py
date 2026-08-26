"""應用層的 logging 設定，以及「存取紀錄不得含 IP」的實作（D38）。

這個系統是**單人維護、校內自架**的。維護者唯一會看到的東西就是 uvicorn 那個
終端機（或 systemd／rc.d 的 log 檔），所以「有沒有印出來」等同「有沒有人知道」。
因此本專案的規則是：

    任何被 `except` 吞掉的錯誤，都必須留下一行 log。

uvicorn 的預設 logging 設定只掛了 `uvicorn.*` 幾個 logger，root 上沒有 handler。
若不做任何事，`app.*` 的訊息會落到 `logging.lastResort`——只印 WARNING 以上、
沒有時間戳、沒有 logger 名稱，出事時完全查不出是什麼時候、哪個模組講的。
:func:`configure_logging` 就是補這一段，刻意做得很小。

---

## v0.16（D38）：uvicorn 的存取紀錄被我們接管了

老師的決定是「存取紀錄保留，但**不得寫入用戶端 IP**」。這件事不能只在
應用層做，因為**uvicorn 自己就會記 IP**——它的預設格式是

    '%(client_addr)s - "%(request_line)s" %(status_code)s'

`client_addr` 就是用戶端 IP 與埠號。也就是說：應用層一個 IP 都不碰，
終端機上照樣一行一個 IP，而且沒有人會覺得哪裡不對（規則 4 最討厭的那種
失敗——它不會壞，只會安靜地做一件你以為沒在做的事）。

**作法**：`take_over_uvicorn_access_log()` 把 `uvicorn.access` 這個 logger
的 handler 全部拔掉、關掉 propagate，改由我們自己的
`app/access_log.py` 中介層產生存取紀錄——它記方法、路徑、狀態碼、耗時，
就是不記來源。

三個刻意的選擇：

1. **不是「換一個 formatter」，是整個接管。** 換 formatter 的話，
   uvicorn 仍然把 IP 放進 `record.args`，而任何一個「順手加回預設設定」
   的部署動作（例如 `--log-config` 指一份抄來的 YAML）都會讓它重新出現。
   拔掉 handler 之後，那條資料在我們這一側根本沒有出口。

2. **它在 lifespan 裡跑，不是只在 import 時跑。** uvicorn 是在
   `Server.run()` 裡設定 logging 的，那個時點在 `app` 模組被 import **之後**。
   只在 import 時做等於白做。`app/main.py` 的 lifespan 會再呼叫一次。

3. **接管這件事本身會印一行 log。** 我們動了別人的設定，這是使用者
   （老師）應該知道的事——尤其是他明明下了 `--log-config` 卻沒看到效果的時候。

⚠️ **這一層的努力在反向代理前面會全部作廢。** Caddy／nginx 的預設存取紀錄
一樣含來源 IP，而那一層在我們的行程外面。怎麼關、怎麼濾，寫在
`FREEBSD-DEPLOY.md` §5.7；那一節不是可選的補充說明，是這條決定的另外一半。
"""

from __future__ import annotations

import logging
import os
import sys

LOGGER_NAME = "app"

#: 存取紀錄用的子 logger。與應用層訊息分開，部署時才可以只轉走其中一種。
ACCESS_LOGGER_NAME = "app.access"

# 想看更細的東西時設 APP_LOG_LEVEL=DEBUG
DEFAULT_LEVEL = os.environ.get("APP_LOG_LEVEL", "INFO").upper()

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

#: 存取紀錄的欄位。**這裡沒有來源位址，而且不可以有**（D38）。
#:
#: 寫成一個常數而不是散在 f-string 裡，是為了讓
#: `tests/test_web.py::test_log_formats_contain_no_field_that_expands_to_an_ip`
#: 有一個明確的東西可以掃——那項測試把 `client_addr`、`remote_addr`、
#: `%h`、`%a`、`X-Forwarded-For` 這些會展開成 IP 的欄位名列成黑名單。
ACCESS_FORMAT = "%(method)s %(path)s -> %(status)s in %(duration_ms).1fms"

#: 會展開成用戶端位址的欄位名。黑名單集中在這裡，測試與文件共用同一份。
IP_BEARING_FIELDS: tuple[str, ...] = (
    "client_addr",      # uvicorn 的存取紀錄
    "remote_addr",      # nginx／WSGI 慣例
    "remote_ip",        # Caddy 的 JSON 存取紀錄
    "client_ip",        # Caddy（信任代理之後的那個）
    "x-forwarded-for",
    "x-real-ip",
    "%h",               # Apache／common log format
    "%a",
)

#: uvicorn 那個會印出 IP 的 logger。
UVICORN_ACCESS_LOGGER = "uvicorn.access"


def configure_logging(level: str | None = None) -> logging.Logger:
    """把 `app` logger 接到 stderr，回傳它。重複呼叫是安全的。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level or DEFAULT_LEVEL)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        logger.addHandler(handler)
    return logger


def take_over_uvicorn_access_log() -> bool:
    """拔掉 uvicorn 存取紀錄的出口，回傳「是否真的動到了東西」。

    回傳值是給測試與 log 訊息用的：第一次呼叫會是 True（uvicorn 已經掛好了
    handler），之後是 False。用 `logger.disabled` 那種一刀切的旗標也做得到，
    但它會讓「為什麼沒有 log」變成一個查不出來的問題；把 handler 清掉並留下
    一個 `NullHandler` 至少在 `logging` 的狀態裡看得出是誰做的。
    """
    access = logging.getLogger(UVICORN_ACCESS_LOGGER)
    had_handlers = bool(access.handlers)
    for handler in list(access.handlers):
        access.removeHandler(handler)
    if not any(isinstance(h, logging.NullHandler) for h in access.handlers):
        access.addHandler(logging.NullHandler())
    # propagate 也要關：不關的話那筆紀錄會往 root 跑，而 root 上可能有別人
    # 掛的 handler（例如 systemd 的設定、或老師自己加的 basicConfig）。
    access.propagate = False
    return had_handlers


def configure_access_logging() -> logging.Logger:
    """設定 `app.access`，並接管 uvicorn 的存取紀錄。"""
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    logger.setLevel(DEFAULT_LEVEL)

    if take_over_uvicorn_access_log():
        # 動了別人的設定就要說（規則 4）。老師若下了 `--log-config` 卻發現
        # 格式不是他寫的那一份，這一行是唯一查得到原因的地方。
        logging.getLogger(LOGGER_NAME).info(
            "已接管 uvicorn 的存取紀錄：它的預設格式含用戶端位址，"
            "改由 app.access 產生不含來源位址的紀錄（PLAN.md D38）。"
            "反向代理那一層要另外處理，見 FREEBSD-DEPLOY.md §5.7。"
        )
    return logger


def get_logger(name: str) -> logging.Logger:
    """模組用：`logger = get_logger(__name__)`。"""
    return logging.getLogger(name)
