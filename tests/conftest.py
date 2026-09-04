"""pytest 的共用設定。

除了讓 `app` 套件找得到，這裡還做一件事：**每一次 pytest 都順便更新相依地圖**
（v0.37、D69）。

⛔ **為什麼放在 conftest 而不是一個要記得加的旗標**：pytest **一定**會載入
conftest，所以不管是誰、用什麼方式發動測試，都會經過這裡。
v0.36 把「跑測試」與「更新地圖」綁在 `scripts/test_deps.py run` 這個子指令上，
而那是一條**靠人記得**的規則——直接打 `pytest` 照樣跑得動，只是地圖不會更新。
這個專案的立場是「會被忘記的流程等於沒有流程」，所以把它搬進機制裡。

⚠️ **它不是每一次都真的寫回去**，理由與細節寫在 `scripts/test_deps.py` 的
「自動記錄」那一節——一次跑多個測試檔時**沒有辦法知道哪一條相依屬於哪一個**，
而「都算進去」會讓每個檔案都相依於全世界，於是 `select` 從此永遠回答「全跑」。
那等於把整套機制關掉，**而且看起來還在運作**。不寫的時候會印一行說明（規則 4）。

環境變數 `TEST_DEPS_AUTOUPDATE=0` 可以關掉它。
"""

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 讓 `pytest` 從專案根目錄執行時找得到 app 套件
sys.path.insert(0, str(ROOT))

_state = None
_td = None


def _test_deps():
    """把 `scripts/test_deps.py` 依路徑載進來（`scripts/` 不是一個套件）。"""
    global _td
    if _td is None:
        spec = importlib.util.spec_from_file_location(
            "_test_deps_autorecord", ROOT / "scripts" / "test_deps.py")
        if spec is None or spec.loader is None:
            return None
        _td = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_td)
    return _td


def pytest_sessionstart(session):
    global _state
    if os.environ.get("TEST_DEPS_AUTOUPDATE") == "0":
        return
    if session.config.getoption("collectonly", False):
        # ⛔ `--collect-only` 沒有真的跑任何測試，記下來的相依只有「import 了
        # 哪些模組」——**那是一份不完整的相依集，寫回去會讓地圖變窄**。
        # ⚠️ 它同時擋掉一條遞迴：`_collected()` 就是用 `--collect-only` 數項數的。
        return
    try:
        module = _test_deps()
        _state = module.autorecord_start() if module else None
    except Exception as err:                       # noqa: BLE001
        # ⚠️ 規則 4：不做無聲降級。量測掛不上去不該讓測試跑不動，
        # 但也不該安靜地什麼都沒發生。
        print(f"⚠️ 相依地圖的自動記錄沒有啟動：{err}")
        _state = None


def pytest_sessionfinish(session, exitstatus):
    global _state
    if _state is None:
        return
    state, _state = _state, None
    try:
        files = sorted({
            Path(str(item.fspath)).resolve().relative_to(ROOT).as_posix()
            for item in session.items
        })
        message = _test_deps().autorecord_finish(
            state,
            files,
            session.config.getoption("keyword", "") or "",
            len(session.items),
            int(exitstatus),
        )
    except Exception as err:                       # noqa: BLE001
        message = f"⚠️ 相依地圖沒有更新（自動記錄本身出錯）：{err}"
    if message:
        print("\n" + message)
