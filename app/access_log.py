"""存取紀錄：記方法、路徑、狀態碼、耗時——**不記來源**（D38）。

老師的決定是「只記錄 IP 以外的其他欄位」。這個檔案是那句話的實作。

## 為什麼要自己寫一個，而不是改 uvicorn 的格式

兩個理由，第二個才是決定性的：

1. **uvicorn 的存取紀錄沒有耗時。** 它的 `record.args` 是
   `(client_addr, method, full_path, http_version, status_code)`，五個裡面
   一個是我們不要的、而我們想要的那個（耗時）不在裡面。要加耗時本來就得
   自己量，那不如整條自己做。

2. **「不記 IP」如果靠改格式來達成，它是可以被一行設定推翻的。**
   格式是設定，設定會被覆寫、會被抄一份舊的貼回來、會被 `--log-config`
   接管。而如果 IP 從來沒有進到我們的紀錄路徑裡，就沒有東西可以推翻——
   `app/logging_setup.py::take_over_uvicorn_access_log()` 負責把 uvicorn
   那條路徑封起來，這個中介層負責提供替代品。

## 這裡刻意不記的東西

- **用戶端位址**（`request.client`）——D38 的本體。
- **`X-Forwarded-For` / `X-Real-IP`**——反向代理放進來的同一件事。
  整個 `app/` 不讀這兩個標頭，`tests/test_web.py` 有一項掃全部原始碼。
- **User-Agent**——它不是 IP，但它是一個相當有效的瀏覽器指紋，而系統
  對外的說法是「不記錄任何指得到特定個人的東西」（D36）。
- **query string**——目前沒有任何端點用得到它，而它是最容易在日後某天
  夾帶識別資訊進來的地方。路徑只記 `request.url.path`。

## 為什麼路徑不做正規化

`/demos/spectrum/leakage` 就照原樣記。有人會建議把帶參數的路由收斂成
`/demos/{group}/{name}`（Prometheus 那一套的作法）以免 cardinality 爆炸——
這裡不做，因為這份紀錄的讀者是一個人、在一個終端機前面，他要看的是
「剛剛那一下打到哪裡」。
"""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logging_setup import ACCESS_LOGGER_NAME, get_logger

logger = get_logger(ACCESS_LOGGER_NAME)


class AccessLogMiddleware:
    """純 ASGI 中介層。

    刻意不用 `BaseHTTPMiddleware`：那一層會把回應包成一個 `StreamingResponse`
    再送出去，於是「耗時」量到的是**含下載時間**的數字，而且它會在背景任務
    與例外處理上多出幾個眉角。純 ASGI 版本只是攔一下 `http.response.start`
    拿狀態碼，其餘原封不動地傳下去。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "-")
        path = scope.get("path", "-")
        started = time.perf_counter()
        status: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # 例外會往上傳給 Starlette 的錯誤處理，但這一行要先留下來——
            # 否則一個 500 在存取紀錄裡會完全不存在（規則 4）。
            _log(method, path, "ERR", started)
            raise

        _log(method, path, status if status is not None else "-", started)


def _log(method: str, path: str, status: object, started: float) -> None:
    """實際寫一行。格式對應 `logging_setup.ACCESS_FORMAT`。

    用 `%` 佔位而不是 f-string：訊息在被 handler 取用之前不會被組出來，
    而且日後若要換成結構化輸出，欄位還是分開的。
    """
    logger.info(
        "%s %s -> %s in %.1fms",
        method, path, status, (time.perf_counter() - started) * 1000.0,
    )
