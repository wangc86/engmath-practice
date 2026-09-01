"""Web 流程測試：建立共用帳號 → 登入 → 出題 → 展開答案／詳解 → 全班活動頁。

v0.7（D12）：作答判定的測試（`test_grader.py`、`test_grader_sandbox.py`，
以及本檔案裡「作答判定」與「Attempt」兩組）已隨判定一起移除，保存在
tag `grading-v1`。

**v0.16（D35–D40）**：帳號改為兩組共用帳號，系統不再蒐集任何個人資料。
本檔案因此少了三組測試、多了三組：

- 少了**個資告知與同意閘門**（D33 的 `/consent`）——沒有個資就沒有告知義務。
  那一組測試的形狀留了下來，主詞從「同意」換成「登入」：
  `test_no_route_is_reachable_without_logging_in` 仍然列舉整張路由表。
- 少了**自行修改密碼**（D34 的 `/account/password`）——密碼是共用的，
  讓一個學生改掉它等於把全班鎖在門外。
- 少了**「只看得到自己的紀錄」**——系統已經不知道誰是誰，那個性質不再有
  意義；取而代之的是「**沒有任何欄位指得到人**」（D36）。
- 多了 **IP 不落地**的看守（D38）、**staff 限定**的存取控制（D39）、
  以及**誠實說明**的措辭（D40）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
TEMPLATES_DIR = APP_DIR / "templates"

CLASS_PASSWORD = "practice-ode-2026"
STAFF_PASSWORD = "staff-side-check-2026"

def _all_templates() -> list[str]:
    """所有已註冊的題型代號。

    ⚠️ **刻意從註冊表讀，不是手寫一份清單。**（v0.24 由手寫清單改成這樣）
    這一整組 Web 測試守的性質是「新增一個題型，UI 與紀錄會自動撿到它」——
    而手寫的清單會讓一個沒有被撿到的新題型**照樣全綠**，正好把要守的東西守掉了。
    """
    from app.generator import list_templates

    return sorted(t.template_id for t in list_templates())


ALL_TEMPLATES = _all_templates()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每個測試用一個乾淨的臨時 SQLite 檔。"""
    monkeypatch.setenv("PRACTICE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-for-production")

    import importlib

    from app import config as config_module

    importlib.reload(config_module)
    from app.db import session as session_module

    importlib.reload(session_module)
    from app import accounts as accounts_module
    from app import login_gate as login_gate_module
    from app import release as release_module
    from app import release_gate as release_gate_module
    from app.routes import auth as auth_module
    from app.routes import demos as demos_module
    from app.routes import deps as deps_module
    from app.routes import practice as practice_module
    from app.routes import release_admin as release_admin_module

    # 順序有意義：每個模組都在 import 時把 `engine` 綁進自己的命名空間，
    # 所以換了 DB 檔之後每一個都要重新載入，而且被依賴的要先載入
    # （practice 匯入 demos 的 DEMO_ACTION／DEMOS）。漏掉一個的症狀是
    # 「FOREIGN KEY constraint failed」——那個模組還在寫上一個測試的 DB。
    # v0.16：`app.consent_gate` 改名為 `app.login_gate`，它一樣自己查 DB。
    # v0.28：`app.release`（查 `ReleaseState`）與它的兩個使用者也在這條鏈上。
    # 順序：被依賴的先——`release` → `release_gate` → 路由。
    importlib.reload(deps_module)
    importlib.reload(accounts_module)
    importlib.reload(login_gate_module)
    importlib.reload(release_module)
    importlib.reload(release_gate_module)
    importlib.reload(demos_module)
    importlib.reload(auth_module)
    importlib.reload(practice_module)
    importlib.reload(release_admin_module)
    from app import main as main_module

    importlib.reload(main_module)

    auth_module.login_limiter.reset()

    with TestClient(main_module.app) as c:
        c.session_module = session_module
        # `TestClient.app` 是包了 middleware 之後的那一層，`.routes` 只看得到
        # 一個項目。要列舉真正的路由表必須拿到 FastAPI 物件本身。
        c.fastapi_app = main_module.app
        yield c


# --- 測試用的帳號流程（v0.16，D35）----------------------------------------

def make_accounts(client, class_password=CLASS_PASSWORD, staff_password=STAFF_PASSWORD):
    """用老師的那條路徑建兩組帳號（`app.accounts.ensure_account`）。

    刻意不直接 `session.add(Account(...))`：那樣測的就只是 SQLModel，
    而不是老師實際會執行的程式。整份測試因此把 `ensure_account()` 走了
    數百次，而不是只有 `test_accounts.py` 那幾項。
    """
    from app.accounts import ensure_account
    from app.db.models import ROLE_CLASS, ROLE_STAFF

    with Session(client.session_module.engine) as s:
        return [
            ensure_account(s, ROLE_CLASS, password=class_password),
            ensure_account(s, ROLE_STAFF, password=staff_password),
        ]


def log_in(client, name: str = "class", password: str = CLASS_PASSWORD):
    return client.post(
        "/login",
        data={"account": name, "password": password},
        follow_redirects=False,
    )


def open_all_content(client):
    """把全部內容對學生開放（v0.28，D54）。

    ⚠️ **這一行是 v0.28 加進 `sign_in()` 裡的，而它值得解釋一次。**
    開放的預設是**全關**（理由見 `app/release.py` 的模組說明），所以在這之後
    「登入」不再等於「看得到東西」。這一整份測試守的是別的性質
    （收合、洩題、IP 不落地、英文介面…），它們的前提是內容拿得到，
    因此預設起手式把內容打開。

    ⛔ **開放閘門本身刻意不在這裡驗證。** 那是 `tests/test_release.py`
    的事，而它用的是 `log_in()` 這條低階路徑——若閘門的測試也共用一個
    「先全部打開」的起手式，它就會驗不到任何東西。
    """
    from app.release import set_released
    from app.curriculum import ALL_CONTENT_IDS

    set_released(set(ALL_CONTENT_IDS))


def sign_in(client, name: str = "class", password: str = CLASS_PASSWORD):
    """建帳號 → 開放全部內容 → 登入。整份測試的預設起手式。"""
    make_accounts(client)
    open_all_content(client)
    return log_in(client, name, password)


def sign_in_as_staff(client):
    return sign_in(client, "staff", STAFF_PASSWORD)


# --- 認證 -----------------------------------------------------------------

def test_index_redirects_to_login_when_anonymous(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_sign_in_reaches_the_practice_page(client):
    make_accounts(client)
    r = log_in(client)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    r = client.get("/")
    assert r.status_code == 200
    assert "Signed in as class" in r.text


def test_password_is_hashed_not_plaintext(client):
    """最重要的一條：資料庫裡絕不能出現明碼。"""
    sign_in(client)

    from app.db.models import Account

    with Session(client.session_module.engine) as s:
        accounts = s.exec(select(Account)).all()

    assert len(accounts) == 2
    for account in accounts:
        assert account.password_hash.startswith("$argon2")

    # 整個 DB 檔案裡也不能有明碼
    db_bytes = client.session_module.DB_PATH.read_bytes()
    assert CLASS_PASSWORD.encode() not in db_bytes
    assert STAFF_PASSWORD.encode() not in db_bytes


def test_login_and_logout(client):
    sign_in(client)
    client.post("/logout")

    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/login"

    r = log_in(client)
    assert r.status_code == 303
    assert client.get("/").status_code == 200


def test_login_message_does_not_leak_account_existence(client):
    """帳號不存在與密碼錯誤要回傳同一則訊息。"""
    make_accounts(client)

    wrong_pw = client.post(
        "/login", data={"account": "class", "password": "totally-wrong-pw"}
    )
    no_such = client.post(
        "/login", data={"account": "nosuchaccount", "password": "totally-wrong-pw"}
    )
    assert "Incorrect account name or password" in wrong_pw.text
    assert "Incorrect account name or password" in no_such.text


def test_account_name_is_case_normalized(client):
    """手機輸入法會把第一個字母自動大寫，所以 `Class ` 也要進得去。"""
    make_accounts(client)
    assert log_in(client, " Class ").status_code == 303


def test_both_shared_accounts_can_log_in(client):
    make_accounts(client)
    assert log_in(client, "class", CLASS_PASSWORD).status_code == 303
    client.post("/logout")
    assert log_in(client, "staff", STAFF_PASSWORD).status_code == 303


# --- 沒有任何建立帳號的途徑（D32、D35）------------------------------------

@pytest.mark.parametrize("path", ["/register", "/account/password", "/consent"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_removed_account_endpoints_are_gone(client, path, method):
    """三個曾經存在的端點都必須是 404。

    與 D12 的 `test_grading_endpoints_are_gone` 同一種測試，理由也相同：
    **刪功能最常見的失敗是刪一半**。

    - `/register`（D32 移除）：還活著的話，不相干的人照樣進得來。
    - `/consent`（D37 移除）：一頁在講「我們蒐集了你的學號」的告知，
      而系統已經不蒐集了——留著它就是在頁面上說一句假話。
    - `/account/password`（D35 移除）：**這個最危險**。密碼是共用的，
      一個學生改掉它就把全班鎖在門外，而它不會拋任何錯誤。
    """
    sign_in(client)
    kwargs = {"data": {"whatever": "x"}} if method == "post" else {}
    r = getattr(client, method)(path, **kwargs, follow_redirects=False)
    assert r.status_code == 404, f"{path} 還在"


def test_no_page_links_to_a_removed_endpoint(client):
    """殘留的連結與其說是壞掉，不如說是說謊：它會把人帶到 404。"""
    pages = [client.get("/login").text]
    sign_in(client)
    pages.append(client.get("/").text)
    sign_in_as_staff(client)
    pages.append(client.get("/activity").text)
    for html in pages:
        for gone in ("/register", "/consent", "/account/password", "/progress"):
            assert f'href="{gone}"' not in html
            assert f'action="{gone}"' not in html


def test_no_template_file_mentions_a_removed_endpoint(client):
    """範本檔裡也不得殘留——包括沒有被上面那幾頁載到的片段。"""
    templates_dir = APP_DIR / "templates"
    offenders = {}
    for path in templates_dir.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for gone in ('"/register"', '"/consent"', '"/account/password"'):
            if gone in text:
                offenders.setdefault(str(path.relative_to(templates_dir)), []).append(gone)
    assert not offenders, f"範本裡還有指向已移除端點的東西：{offenders}"


# --- 登入閘門（D37，形狀沿用 D33）-----------------------------------------

PROTECTED_PATHS = ["/", "/activity", "/demos"]


def _registered_endpoints(app) -> set[tuple[str, str]]:
    """遞迴走完整個路由表，回傳 {(路徑, HTTP 方法)}。

    不能只看 `app.routes`：FastAPI 0.141 起 `include_router()` 掛上來的是
    一層 `_IncludedRouter` 包裝物件，它自己沒有 `path`，真正的路由在
    `original_router.routes` 裡。這個走訪法對兩種結構都成立，
    因此升級 FastAPI 不會讓這項測試安靜地變成「檢查了 0 條路由」。
    """
    found: set[tuple[str, str]] = set()

    def walk(routes) -> None:
        for route in routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None) or set()
            if path and methods:
                if "{" not in path:              # 帶參數的路由跳過
                    for method in methods & {"GET", "POST"}:
                        found.add((path, method))
                continue
            inner = getattr(route, "original_router", route)
            sub = getattr(inner, "routes", None)
            if sub and not hasattr(route, "app"):   # Mount（/static）不進去
                walk(sub)

    walk(app.routes)
    return found


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_login_gate_blocks_every_protected_page(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_no_route_is_reachable_without_logging_in(client):
    """**列舉 app 上所有已註冊的路由**，逐一確認未登入的人拿不到 200。

    這一項是 D33 那個測試的直系後代，主詞換了但用途沒變：逐頁列舉的測試
    （上面那一項）守的是今天存在的頁面；這一項守的是**明天才會被加上去的
    那一個**——新端點若忘了掛登入，它會直接紅燈，而不是安靜地開一個洞。

    豁免清單寫死在這裡，與 `app/login_gate.py` 各一份是刻意的：
    有人偷偷把某條路徑加進豁免清單時，這裡不會跟著變。
    """
    from app.login_gate import EXEMPT_PATHS

    assert EXEMPT_PATHS == {"/login", "/logout", "/healthz"}, (
        "豁免清單變了。每加一項都等於在登入閘門上開一個洞，"
        "請先確認那條路徑真的不吐出任何東西，再回來改這一行。"
    )

    checked = 0
    for path, method in sorted(_registered_endpoints(client.fastapi_app)):
        if path in EXEMPT_PATHS or path.startswith("/static"):
            continue
        r = client.request(method, path, follow_redirects=False)
        assert r.status_code != 200, f"{method} {path} 在尚未登入時就回了 200"
        checked += 1

    # 下限是防呆：列舉一旦壞掉（例如 FastAPI 換了內部結構），這個測試會
    # 變成「檢查了 0 條路由，全部通過」——一個永遠綠燈的假保證。
    assert checked >= 4, f"實際檢查到的路由太少（{checked}），列舉可能壞了"


def test_login_gate_uses_hx_redirect_for_htmx_requests(client):
    """HTMX 的請求要收到 `HX-Redirect`，不是 303。

    收到 303 的話 HTMX 會跟著跳轉、**把整頁登入表單塞進題目卡片的位置**——
    版面爛掉，而且學生看到的是一個嵌在頁面中間、沒有樣式的登入框。
    這不會拋錯，所以需要一項測試盯著。
    """
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert r.headers.get("HX-Redirect") == "/login"
    assert r.status_code == 204


def test_a_session_pointing_at_a_deleted_account_is_cleared(client):
    """老師砍掉 DB 重建之後，舊 session 裡的 id 會指向不存在的一列。

    不處理的話那個人會通過閘門、然後在某個路由裡拿到 None 而炸掉；
    而他能做的只有清 cookie，卻沒有人告訴他要這麼做。
    """
    from app.db.models import Account

    sign_in(client)
    with Session(client.session_module.engine) as s:
        for account in s.exec(select(Account)).all():
            s.delete(account)
        s.commit()

    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_middleware_order(client):
    """三層中介層的順序（`app/main.py` 有一張圖）。

    `SessionMiddleware` 必須在 `LoginGateMiddleware` 外面，否則每個請求都會
    拋 `AssertionError: SessionMiddleware must be installed`——會被立刻發現，
    所以這一項守的其實是另一件事：**不要有人為了「整理一下」而把幾行對調**。
    存取紀錄必須在最外層，否則被閘門擋掉的請求完全不會出現在紀錄裡，
    而那**不會有任何症狀**。
    """
    from starlette.middleware.sessions import SessionMiddleware

    from app.access_log import AccessLogMiddleware
    from app.login_gate import LoginGateMiddleware
    from app.release_gate import ReleaseGateMiddleware

    classes = [m.cls for m in client.fastapi_app.user_middleware]
    # user_middleware 的順序是「外層在前」
    assert classes.index(AccessLogMiddleware) < classes.index(SessionMiddleware)
    assert classes.index(SessionMiddleware) < classes.index(LoginGateMiddleware)
    # v0.28：開放閘門要在登入閘門**裡面**。反過來的話，一個未登入的人會先
    # 收到「這裡沒有東西」而不是被導去登入頁——不會壞掉，但那是錯的答案，
    # 而且他永遠找不到登入頁在哪。
    assert classes.index(LoginGateMiddleware) < classes.index(ReleaseGateMiddleware)


# --- IP 不落地（D38）------------------------------------------------------

def test_log_formats_contain_no_field_that_expands_to_an_ip():
    """設定裡不得出現任何會展開成用戶端位址的欄位。

    這一項守的是**格式字串**，而格式字串正是這條決定最容易被推翻的地方：
    uvicorn 的預設存取紀錄是 `'%(client_addr)s - "%(request_line)s" ...'`，
    任何一個「從網路上抄一份 log config 貼進來」的動作都會把 IP 帶回來，
    而且不會有任何東西壞掉——終端機上只是多了一欄。
    """
    from app.logging_setup import ACCESS_FORMAT, IP_BEARING_FIELDS, _FORMAT

    for fmt in (_FORMAT, ACCESS_FORMAT):
        lowered = fmt.lower()
        for field in IP_BEARING_FIELDS:
            assert field not in lowered, f"log 格式 {fmt!r} 含會展開成 IP 的 {field!r}"


def test_nothing_in_the_app_reads_the_client_address():
    """掃整個 `app/`：不得有任何地方讀得到用戶端位址。

    掃全部而不只是 `access_log.py`，理由與 D28 的 `UploadFile` 那一項相同：
    承諾的範圍是**這個伺服器**，不是某一個檔案。速率限制曾經用過
    `request.client.host`（v0.15 的 `client_ip()`），那正是這一項會抓到的
    那種「看起來無害而且有正當理由」的用法。
    """
    forbidden = (
        "request.client",
        "scope['client']",
        'scope["client"]',
        "x-forwarded-for",
        "x-real-ip",
        "client_ip",
        "getpeername",
    )
    offenders: dict[str, list[str]] = {}
    for source in APP_DIR.rglob("*.py"):
        if source.name == "logging_setup.py":
            # 這個檔案**就是那份黑名單**（`IP_BEARING_FIELDS`），所以它必然
            # 提到每一個被禁的字串。下面單獨檢查它只在那個 tuple 裡提到。
            continue
        text = source.read_text(encoding="utf-8")
        # 模組說明字串裡談論這件事是允許的（而且是必要的），所以先把
        # 三引號字串拿掉再掃。掃的是程式碼，不是文件。
        code = re.sub(r'"""(?:.|\n)*?"""', "", text)
        code = re.sub(r"#.*", "", code)
        lowered = code.lower()
        for name in forbidden:
            if name.lower() in lowered:
                offenders.setdefault(source.name, []).append(name)
    assert not offenders, f"應用層讀得到用戶端位址：{offenders}"


def test_the_blacklist_file_only_mentions_those_fields_in_the_blacklist():
    """`logging_setup.py` 是上一項唯一的豁免，所以它自己要被單獨盯著。

    豁免一整個檔案是有代價的：那個檔案裡出現一行
    `request.headers.get("x-forwarded-for")` 不會被任何測試抓到。
    因此這裡確認那些字串只出現在 `IP_BEARING_FIELDS` 這個 tuple 的字面值裡。
    """
    from app.logging_setup import IP_BEARING_FIELDS

    text = (APP_DIR / "logging_setup.py").read_text(encoding="utf-8")
    body = re.search(
        r"IP_BEARING_FIELDS:.*?\)\n", text, re.S
    )
    assert body, "找不到 IP_BEARING_FIELDS 的定義，這項測試已經失效"

    rest = text.replace(body.group(0), "")
    rest = re.sub(r'"""(?:.|\n)*?"""', "", rest)
    rest = re.sub(r"#.*", "", rest).lower()
    for field in IP_BEARING_FIELDS:
        if field.startswith("%"):          # "%h"／"%a" 太短，掃了只會誤判
            continue
        assert field not in rest, (
            f"logging_setup.py 在 IP_BEARING_FIELDS 以外的地方用到了 {field!r}"
        )


def test_ip_bearing_field_list_is_not_empty():
    """防呆：黑名單如果被清空，上面兩項會變成永遠綠燈的假保證。"""
    from app.logging_setup import IP_BEARING_FIELDS

    assert len(IP_BEARING_FIELDS) >= 6
    assert "client_addr" in IP_BEARING_FIELDS       # uvicorn 那一個
    assert "remote_ip" in IP_BEARING_FIELDS         # Caddy 那一個


def test_uvicorn_access_logger_is_taken_over(client):
    """`uvicorn.access` 必須被接管：handler 拔掉、不往 root 傳。

    這是 D38 在應用層唯一一個「別人的程式碼會印 IP」的缺口
    （uvicorn 的預設格式是 `'%(client_addr)s - "%(request_line)s" ...'`）。

    測試自己裝一個 handler 再叫接管函式拔掉它，而不是只檢查最終狀態：
    pytest 自己的 `caplog` 會往各個 logger 掛 handler，只看最終狀態的話
    這一項會隨測試執行順序時綠時紅——而那種測試遲早會被人加上 skip。
    """
    import sys

    from app.logging_setup import UVICORN_ACCESS_LOGGER, take_over_uvicorn_access_log

    access = logging.getLogger(UVICORN_ACCESS_LOGGER)
    spy = logging.StreamHandler(sys.stderr)          # uvicorn 裝的就是這種
    access.addHandler(spy)
    access.propagate = True

    assert take_over_uvicorn_access_log() is True
    assert spy not in access.handlers, "uvicorn 的 handler 沒有被拔掉"
    assert access.propagate is False, "紀錄還會往 root 傳，root 上可能有別人的 handler"
    assert any(isinstance(h, logging.NullHandler) for h in access.handlers)

    # 沒有任何 handler 還寫得到終端機
    leaks = [
        h for h in access.handlers
        if isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) in (sys.stderr, sys.stdout)
    ]
    assert not leaks, f"uvicorn.access 還印得到終端機：{leaks}"


def test_access_log_records_the_useful_fields_and_no_address(client, caplog):
    """我們自己的存取紀錄：有方法、路徑、狀態碼、耗時；沒有任何位址。"""
    from app.logging_setup import ACCESS_LOGGER_NAME

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER_NAME):
        client.get("/healthz")

    lines = [
        r.getMessage() for r in caplog.records if r.name == ACCESS_LOGGER_NAME
    ]
    assert lines, "存取紀錄一行都沒有——中介層可能沒有掛上去"

    line = next(ln for ln in lines if "/healthz" in ln)
    assert "GET" in line and "200" in line and "ms" in line
    # 沒有任何看起來像 IP 的東西（TestClient 的來源是 "testclient"，
    # 真實部署會是 127.0.0.1 之類，兩者都不該出現）
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", line), line
    assert "testclient" not in line.lower()


def test_a_request_blocked_by_the_gate_is_still_logged(client, caplog):
    """被閘門擋掉的請求也要有紀錄——否則「有人一直打某個網址」查不出來。

    這一項實際上驗的是中介層的順序（存取紀錄在最外層）。順序錯了不會壞掉，
    只會讓紀錄少一整類請求，而少了什麼是看不出來的。
    """
    from app.logging_setup import ACCESS_LOGGER_NAME

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER_NAME):
        client.get("/activity", follow_redirects=False)

    lines = [
        r.getMessage() for r in caplog.records if r.name == ACCESS_LOGGER_NAME
    ]
    assert any("/activity" in ln and "303" in ln for ln in lines), lines


def test_login_rate_limit_is_not_keyed_on_anything_identifying(client):
    """速率限制用的是一個固定字串，不是 IP、也不是帳號名稱。

    兩者都不能用，理由不同：IP 是 D38；帳號名稱是因為只有兩個帳號，
    一個人連打錯十次就把全班鎖在門外。取捨寫在 `config.LOGIN_RATE_LIMIT`。
    """
    from app.routes.auth import LOGIN_LIMIT_KEY, login_limiter

    assert LOGIN_LIMIT_KEY == "login"

    make_accounts(client)
    for _ in range(5):
        client.post("/login", data={"account": "class", "password": "nope-nope"})
    # 計數器裡只有那一個 key，沒有任何以來源或帳號分組的東西
    assert set(login_limiter._hits) == {LOGIN_LIMIT_KEY}


# --- 用量紀錄不得指向任何人（D36）-----------------------------------------

def test_usage_log_cannot_identify_a_person(client):
    """欄位清單寫死在這裡。

    v0.15 這一項叫 `test_notice_matches_the_fields_actually_stored`，守的是
    「告知的範圍等於實際蒐集的欄位」。告知沒有了（D37），但這個看守點必須
    留下來，理由換成更根本的一條：**這張表不得長出任何指得到特定個人的欄位**。
    加一個 session id、user agent、或 IP 進來的那一刻，「系統不知道你是誰」
    就變成假話，而**那句話寫在學生看得到的頁面上**。
    """
    from app.db.models import Account, UsageLog

    assert set(Account.__table__.columns.keys()) == {
        "id", "name", "role", "password_hash", "created_at", "last_login_at",
    }
    assert set(UsageLog.__table__.columns.keys()) == {
        "id", "account_id", "template_id", "difficulty",
        "seed", "action", "created_at",
    }

    # 反向：舊的個人欄位一個都不准回來
    for gone in ("student_no", "student_id", "consent_at", "email", "name_zh",
                 "ip", "user_agent", "session_id"):
        assert gone not in UsageLog.__table__.columns.keys()
        if gone != "name":
            assert gone not in Account.__table__.columns.keys()


#: 台灣的學號大致是 8–10 位數字，或一個字母開頭再接 8–9 位數字。
STUDENT_NO_LIKE = re.compile(r"^(?:\d{8,10}|[A-Za-z]\d{8,9})$")


def test_no_text_stored_in_the_database_looks_like_a_student_number(client):
    """把資料庫裡每一個文字欄位撈出來看：沒有一個長得像學號。

    這是 D35 最直接的驗收——`student_no` 那一欄拿掉之後，系統再也沒有地方
    可以寫進一個學號。與「密碼不得明碼落地」那一項是同一種測試，
    但**掃法不一樣，而且差別是踩過才知道的**：

    「掃整個 `.db` 檔的位元組」在這裡行不通。SQLite 的記錄格式裡欄位之間
    **沒有分隔**，所以兩個相鄰的時間戳
    （``2026-08-26 11:56:05.079101`` 與 ``2026-08-26 …``）在檔案裡是
    ``…079101 2026-08-26…`` 連在一起的位元組，正規表示式會從中間讀出
    ``0791012026`` 這個「10 位數字」。那不是資料，是兩個欄位的接縫——
    但測試不知道，於是它會**隨著時間戳的微秒數時綠時紅**。
    一項會偶爾紅的測試，最後一定會被人加上 skip。

    因此改成走 `sqlite3`：列舉所有資料表的所有欄位，只看真正的文字值。
    這同時比原本的版本**更嚴格**——它連 `template_id`、`action` 這些
    我們自己寫進去的欄位都會檢查到。
    """
    import sqlite3

    sign_in(client)
    _generate(client)
    client.get("/demos/sampling/aliasing")

    con = sqlite3.connect(client.session_module.DB_PATH)
    try:
        tables = [
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        # ⚠️ 這一行是刻意寫死的：**多一張表就要有人回來重新想一次**
        # 「它會不會存到指得到人的東西」。v0.28 的 `releasestate`（D53）
        # 就是這樣被逼著想過一遍的，結論寫在 `app/db/models.py` 裡
        # （它沒有 `account_id`，而那是一個決定不是遺漏）。
        assert set(tables) == {"account", "usagelog", "releasestate"}, tables

        offenders = []
        for table in tables:
            for row in con.execute(f"SELECT * FROM {table}"):  # noqa: S608
                for value in row:
                    if isinstance(value, str) and STUDENT_NO_LIKE.match(value.strip()):
                        offenders.append((table, value))
    finally:
        con.close()

    assert not offenders, f"資料庫裡有長得像學號的值：{offenders}"


def test_staff_usage_is_recorded_but_kept_out_of_the_class_numbers(client):
    """`account_id` 留著的唯一理由（D36），所以要有測試。

    老師改一頁版面會重新整理十幾次。那十幾列若混進統計，「這週學生練了幾題」
    就直接失真——而失真的方式是「數字大了一點」，沒有人看得出來。
    """
    from app.db.models import UsageLog

    make_accounts(client)
    open_all_content(client)          # v0.28：學生那一半要拿得到題目

    log_in(client, "staff", STAFF_PASSWORD)
    _generate(client, "ode.first_order.linear", 2)
    client.post("/logout")

    log_in(client, "class", CLASS_PASSWORD)
    _generate(client, "ode.first_order.separable", 1)
    client.post("/logout")

    with Session(client.session_module.engine) as s:
        assert len(s.exec(select(UsageLog)).all()) == 2   # 兩列都真的寫進去了

    log_in(client, "staff", STAFF_PASSWORD)
    html = client.get("/activity").text
    assert "Separable Equations" in html
    assert "First-Order Linear" not in html, "老師的測試流量混進了全班統計"
    assert "1 record(s) came from the staff account" in html


# --- 出題 -----------------------------------------------------------------

def test_practice_page_lists_all_templates(client):
    """下拉選單必須列出註冊表裡的**每一個**題型，含章節分組。

    名稱一樣從註冊表讀（理由見 `_all_templates`）：寫死四個名字的版本
    在新增第五、第六個題型時不會變紅，而「新題型自動出現在選單上」
    正是這一項要守的事。
    """
    from markupsafe import escape

    from app.generator import list_templates

    sign_in(client)
    r = client.get("/")
    for tpl in list_templates():
        assert tpl.template_id in r.text, f"選單缺 {tpl.template_id}"
        assert str(escape(tpl.name)) in r.text, f"選單缺 {tpl.name}"
        assert str(escape(tpl.chapter)) in r.text, f"選單缺章節 {tpl.chapter}"
    for label in ("Basic", "Standard", "Challenge"):
        assert label in r.text


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_generate_returns_problem_fragment(client, template_id, difficulty):
    sign_in(client)
    r = client.post(
        "/practice/generate",
        data={"template_id": template_id, "difficulty": difficulty},
    )
    assert r.status_code == 200
    assert "$$" in r.text                      # 有 LaTeX 供 KaTeX 渲染
    assert "Show Answer" in r.text             # D13 的第一層
    assert "Show Solution Steps" in r.text     # D13 的第二層


def test_generate_requires_login(client):
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_generate_rejects_unknown_template(client):
    sign_in(client)
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.nope", "difficulty": 1},
    )
    assert r.status_code == 400


# --- 答案與詳解的收合（D13、PLAN.md §5.8）--------------------------------

def _generate(client, template_id="ode.second_order.homogeneous", difficulty=1):
    """走一次出題端點，回傳 (HTML 片段, 重現出來的 Problem)。"""
    html = client.post(
        "/practice/generate",
        data={"template_id": template_id, "difficulty": difficulty},
    ).text
    seed = int(re.search(r"#(\d+)</span>", html).group(1))
    from app.generator import generate

    return html, generate(template_id, difficulty, seed=seed)


# 抓出 <details ...> 的開頭標籤，用來檢查有沒有 open 屬性
DETAILS_TAG = re.compile(r"<details\b[^>]*>")


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
def test_answer_and_steps_are_collapsed_by_default(client, template_id):
    """出題當下，答案與詳解都必須是**摺疊**狀態。

    這是 D13 的核心：學生一按 Generate 就同時看到題目和答案的話，
    這個工具就從「練習」退化成「範例集」。

    注意這裡驗的是「摺疊」而不是「不在 HTML 裡」——實作刻意選了 `<details>`，
    答案確實在原始碼裡（取捨見 PLAN.md §5.8）。因此測試盯的是**沒有任何一個
    `<details>` 帶 `open` 屬性**：漏掉 `open` 是這個實作唯一會靜默出錯的方式。
    """
    sign_in(client)
    html, _ = _generate(client, template_id, difficulty=2)

    tags = DETAILS_TAG.findall(html)
    assert len(tags) == 2, f"預期兩層 details（答案、詳解），實際 {len(tags)} 個"
    for tag in tags:
        assert " open" not in tag, f"答案／詳解預設展開了：{tag}"

    # 兩個 summary 的文字也要在，否則學生根本不知道有東西可以點
    assert "<summary>Show Answer</summary>" in html
    assert "<summary>Show Solution Steps</summary>" in html


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
def test_revealed_content_actually_contains_the_answer_and_the_steps(
    client, template_id
):
    """展開後看得到東西：答案的 LaTeX 與逐步解答都必須真的在片段裡。

    與上一項互為一對——上一項守「預設看不到」，這一項守「點開有東西」。
    只有前者的話，一個把答案整段刪掉的 bug 會讓測試全綠。
    """
    sign_in(client)
    html, problem = _generate(client, template_id, difficulty=2)

    # 範本經 Jinja2 autoescape 輸出，所以比對的是跳脫後的字串
    # （`&` → `&amp;` 之類）。不要為了讓這一行好寫而在範本加 |safe。
    from markupsafe import escape

    assert str(escape(problem.answer_latex)) in html
    assert "Step-by-step solution" in html
    assert html.count("step-title") >= 3

    # 版面順序：答案要在詳解前面（先對答案，再看過程）
    assert html.index("Show Answer") < html.index("Show Solution Steps")


def test_steps_are_nested_inside_the_answer(client):
    """詳解是巢狀在答案裡的第二層，不是並排的第二個按鈕。

    並排會讓人以為兩者是二選一；巢狀才表達得出「先看答案，看不懂再看過程」。
    """
    sign_in(client)
    html, _ = _generate(client)

    answer_open = html.index('class="reveal reveal-answer"')
    steps_open = html.index('class="reveal reveal-steps"')
    answer_close = html.rindex("</details>")
    assert answer_open < steps_open < answer_close


# --- 相圖的洩題防護（PLAN.md §2.2.1 第二條、§2.11.1；v0.26 的 2B7）--------
#
# 這一組是 §1.7「答案遮蔽」那一組的同型延伸，而且理由一模一樣：
# **它是相圖唯一會靜默出錯的方式**。一張鞍點圖等於直接告訴學生兩個特徵值
# 異號、一張同心橢圓圖等於告訴學生 tr A = 0；圖跑到題目敘述旁邊的話，
# 頁面不會壞、不會拋錯、每一條線都還是畫對的，只是這一題白出了。
# 而改程式的人（已經知道答案）不會覺得哪裡不對。

#: 會附相圖的題型。**寫死成一份清單**，不是「有圖就檢查」——
#: 後者在圖整個消失時會全綠。
PORTRAIT_TEMPLATES = [
    "system.linear_2x2.real_distinct",
    "system.linear_2x2.repeated",
    "system.linear_2x2.complex",
]


@pytest.mark.parametrize("template_id", PORTRAIT_TEMPLATES)
def test_the_phase_portrait_never_escapes_the_collapsed_block(client, template_id):
    r"""⛔ 相圖只能出現在第二層 `<details>`（Show Solution Steps）裡面。

    三件事一起驗，缺一不可：

    1. 片段裡**真的有一張圖**（否則下面兩項恆綠）
    2. 第一個 `<details>` **之前**沒有 `<svg`（也就是題目敘述區塊乾淨）
    3. 圖在 `reveal-steps` 那一層的範圍內，不是在答案那一層
    """
    sign_in(client)
    html, _ = _generate(client, template_id, difficulty=2)

    assert html.count("<svg") == 1, "相圖不見了，或出現了不只一張"

    first_details = html.index("<details")
    assert "<svg" not in html[:first_details], (
        "題目敘述區塊裡出現了 <svg——這張圖正在洩題"
    )

    steps_open = html.index('class="reveal reveal-steps"')
    assert html.index("<svg") > steps_open, "相圖跑到逐步解答的外面了"
    assert html.index("<svg") < html.rindex("</details>")


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
def test_no_template_leaks_an_svg_into_the_statement(client, template_id):
    """上一項只看三個有圖的題型；這一項看**全部**。

    範圍要涵蓋沒有圖的題型，是因為這一條守的其實是範本：
    哪天有人在 `_problem.html` 加了一個渲染 asset 的區塊，
    它會對所有題型同時生效。
    """
    sign_in(client)
    html, _ = _generate(client, template_id, difficulty=1)
    head = html[: html.index("<details")]
    assert "<svg" not in head, f"{template_id} 的題目敘述區塊裡有 SVG"
    assert "phase_portrait" not in head


def test_the_template_only_ever_renders_a_whitelisted_asset_key(client):
    r"""範本裡的 `|safe` 只准接白名單上的鍵，而且必須是**明示的**。

    `|safe` 關掉的正是 Jinja 唯一那道 XSS 防線，所以「範本印得出什麼」
    不可以取決於 generator 塞了什麼進 `assets`。寫成
    `{% for key, value in problem.assets.items() %}{{ value|safe }}{% endfor %}`
    的話，新增一個鍵就自動有了一個沒有人審過的 `|safe` 出口。
    """
    from app.generator import ASSET_KEYS

    source = (TEMPLATES_DIR / "_solution.html").read_text(encoding="utf-8")
    assert "problem.assets" in source
    # 範本碰得到的 asset 鍵，逐個列出來
    used = set(re.findall(r"problem\.assets\.([a-z_]+)", source))
    used |= set(re.findall(r"problem\.assets\[['\"]([a-z_]+)['\"]\]", source))
    assert used, "範本沒有引用任何 asset 鍵"
    assert used <= set(ASSET_KEYS), f"範本用了白名單外的鍵：{used - set(ASSET_KEYS)}"
    # 不得用迴圈把 assets 整包印出來
    assert not re.search(r"problem\.assets(\.items\(\)|\.values\(\)|\s*%})", source), (
        "範本在對 assets 做迴圈——白名單就失效了"
    )


def test_an_unknown_asset_key_is_refused_when_the_problem_is_built():
    """白名單在 `Problem` 建構的當下就擋，不是等到渲染。

    門的守衛放在「東西被造出來」那一刻，比放在「東西被印出來」那一刻早一步
    ——而且例外會炸，靜默忽略不會（規則 4）。
    """
    from app.generator import Problem

    with pytest.raises(ValueError, match="白名單"):
        Problem(
            template_id="x", difficulty=1, seed=1, params={},
            statement="s", statement_latex="s", answer_latex="a",
            answer_expr=None, answer_kind="classification",
            assets={"arbitrary_html": "<b>hi</b>"},
        )


def test_the_portrait_survives_a_round_trip_through_jinja_unescaped(client):
    """`|safe` 真的有生效——SVG 不可以被跳脫成 `&lt;svg`。

    少了 `|safe` 的症狀是學生看到一整段 SVG 原始碼印在頁面上。
    那不是靜默失敗（很醜、一眼看得到），但它值得一項測試，
    因為修好之後很容易在某次範本重構時再被拿掉。
    """
    sign_in(client)
    html, _ = _generate(client, "system.linear_2x2.complex", difficulty=1)
    assert "&lt;svg" not in html
    assert "<polyline" in html and "<marker" in html


def test_generating_a_problem_does_not_log_a_view_solution_action(client):
    """`<details>` 展開不發請求，所以不會有 view_solution 這則紀錄。

    這是 D13 取捨的代價，寫在 PLAN.md §5.8。測試把它釘住，免得日後有人
    看到 `UsageLog.action` 這個欄位就以為還有第二種值。
    """
    sign_in(client)
    _generate(client)

    from app.db.models import UsageLog

    with Session(client.session_module.engine) as s:
        actions = {log.action for log in s.exec(select(UsageLog)).all()}
    assert actions == {"generate"}


def test_grading_endpoints_are_gone(client):
    """D12：判定與看解答的端點都不該再存在。

    留著一個沒有人用、沒有測試在看的端點，比刪掉它危險——尤其
    `/practice/submit` 當初是這個系統唯一會執行不可信輸入的地方。
    """
    sign_in(client)
    for path in ("/practice/submit", "/practice/solution"):
        r = client.post(path, data={
            "template_id": "ode.second_order.homogeneous",
            "difficulty": 1, "seed": 1, "answer": "C1*e^(-x)",
        })
        assert r.status_code == 404, f"{path} 還在"


def test_old_tables_are_gone(client):
    """D12 的 `Attempt` 與 D35 的 `Student` 都必須整個消失，不是留著不用。"""
    import app.db.models as models

    assert not hasattr(models, "Attempt")
    assert not hasattr(models, "Student")

    from sqlmodel import SQLModel

    tables = set(SQLModel.metadata.tables)
    assert "attempt" not in tables
    assert "student" not in tables
    assert {"account", "usagelog"} <= tables


def test_grader_package_is_gone():
    """D12：`app.grader` 不該再 import 得到（保存在 tag grading-v1）。"""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.grader")


def test_consent_gate_module_is_gone():
    """D37：`app.consent_gate` 改名為 `app.login_gate`，舊名字不該還在。"""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.consent_gate")


# --- 全班活動頁（D36、D39）------------------------------------------------

def test_activity_page_requires_login(client):
    r = client.get("/activity", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_activity_page_is_refused_to_the_class_account(client):
    """D39：學生看不到全班統計。

    藏起導覽連結不算存取控制，所以直接打網址也必須被擋。回 403 而不是 404
    是刻意的（`routes/deps.py::staff_account` 寫了理由）：這裡沒有東西需要
    隱藏，而假裝那一頁不存在會讓一個點錯連結的人以為系統壞了。
    """
    sign_in(client)
    r = client.get("/activity")
    assert r.status_code == 403
    assert "course staff account" in r.text


def test_activity_link_is_only_in_the_staff_header(client):
    sign_in(client)
    assert 'href="/activity"' not in client.get("/").text

    sign_in_as_staff(client)
    assert 'href="/activity"' in client.get("/").text


def test_activity_page_starts_empty(client):
    sign_in_as_staff(client)
    r = client.get("/activity")
    assert r.status_code == 200
    assert "Nobody has generated a problem or opened a demo yet" in r.text


def test_activity_page_shows_class_totals(client):
    """用量留著（D1，老師要看），正確率沒了（D12，沒有東西可以算）。"""
    sign_in(client)
    _generate(client)
    _generate(client, "ode.first_order.linear", 2)
    client.post("/logout")

    log_in(client, "staff", STAFF_PASSWORD)
    r = client.get("/activity")
    assert "Second-Order Homogeneous" in r.text
    assert "First-Order Linear" in r.text
    # D17：頁面（含 base.html 的頁尾）不得出現任何評分相關字眼。
    assert "grading" not in r.text.lower()
    assert "grade" not in r.text.lower()

    for gone in ("Correct rate", "Partly correct", "Your answer",
                 "verdict", "Submitted", "My Progress"):
        assert gone not in r.text, f"全班活動頁還留著舊的東西：{gone}"


def test_activity_page_has_no_per_row_timestamps(client):
    """D36：不列逐筆紀錄。

    逐列的時間戳是這個系統裡最接近可識別資訊的東西——知道某個人幾點在教室的
    人，可以從一列 14:32 的紀錄推回去。彙總數字沒有這個性質。
    """
    sign_in(client)
    for _ in range(3):
        _generate(client)
    client.post("/logout")

    log_in(client, "staff", STAFF_PASSWORD)
    html = client.get("/activity").text
    assert "Recent practice" not in html
    assert not re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", html), (
        "全班活動頁上出現了逐筆的時間戳"
    )


def test_no_page_promises_a_personal_record(client):
    """D35／D40：整站不得出現暗示系統在追蹤個人的措辭。

    這一項是 D17「對評分保持沉默」那兩項測試的同類：**少改一句話不會讓任何
    東西壞掉**，所以留著的舊文案會一直在頁面上說一件不成立的事。
    """
    forbidden = (
        "your progress", "my progress", "your record", "your practice",
        "student id", "only you and your instructor", "how much you have",
    )
    sign_in(client)
    pages = {p: client.get(p).text for p in ("/", "/demos", "/login")}
    client.post("/logout")
    log_in(client, "staff", STAFF_PASSWORD)
    pages["/activity"] = client.get("/activity").text

    for where, html in pages.items():
        lowered = html.lower()
        for phrase in forbidden:
            assert phrase not in lowered, f"{where} 還寫著「{phrase}」"


# --- 誠實說明（D40）-------------------------------------------------------

def test_login_page_says_what_the_site_is_and_what_it_records(client):
    """法律上不再需要告知，但誠實原則仍然適用。

    兩個錯誤的預設要被糾正，而糾正它們各只要一句話：（1）「登入了所以系統
    知道我是誰」——不對，帳號是全班共用的；（2）「這是學校的系統」——不對，
    而且密碼是老師發的，這個誤會現在比 v0.15 更容易發生。
    """
    text = client.get("/login").text
    assert "not an official university system" in text
    assert "shared by the whole class" in text
    for phrase in (
        "no way to tell who you are",
        "for the class as a whole",
        "does not store your name",
        "does not check",
    ):
        assert phrase in text, f"登入頁的誠實說明漏了：{phrase}"

    # D17：說明裡不得出現任何評分字眼，正反皆然。
    assert "grading" not in text.lower()
    assert "grade" not in text.lower()


def test_the_honest_note_says_it_does_not_store_the_ip(client):
    """D38 的承諾必須寫在使用者看得到的地方，不是只寫在 PLAN 裡。

    與 D28 的 `test_the_page_says_out_loud_that_the_file_stays_local` 同一種
    測試：一個只寫在文件裡的承諾，使用者沒有辦法據以判斷要不要相信這個網站。
    """
    assert "your IP address" in client.get("/login").text


def test_every_page_footer_repeats_the_shared_account_fact(client):
    sign_in(client)
    for path in ("/", "/demos"):
        text = client.get(path).text
        assert "shares one account" in text
        assert "does not know who you are" in text


# --- 用量紀錄 -------------------------------------------------------------

def test_usage_is_logged(client):
    sign_in(client)
    client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.linear", "difficulty": 2},
    )
    client.post(
        "/practice/generate",
        data={"template_id": "ode.second_order.homogeneous", "difficulty": 1},
    )

    from app.db.models import UsageLog

    with Session(client.session_module.engine) as s:
        logs = s.exec(select(UsageLog)).all()

    assert len(logs) == 2
    assert {log.template_id for log in logs} == {
        "ode.first_order.linear",
        "ode.second_order.homogeneous",
    }
    assert all(log.account_id is not None for log in logs)
    assert all(log.created_at is not None for log in logs)
    assert all(log.seed > 0 for log in logs)

    # 紀錄只有「哪組帳號、何時、題型、難度」，不含作答內容，也沒有分數欄位
    assert set(UsageLog.model_fields) == {
        "id", "account_id", "template_id", "difficulty",
        "seed", "action", "created_at",
    }


def test_healthz(client):
    """v0.7（D12）：只證明進程活著。判定子行程池的狀態沒有了。"""
    body = client.get("/healthz").json()
    assert body == {"status": "ok"}


# --- 舊資料庫要大聲壞掉（D35）---------------------------------------------

def test_a_v015_database_is_refused_at_startup(tmp_path, monkeypatch):
    """舊的 `practice.db` 接上新程式必須**拒絕啟動**，不是等到有人出題才壞。

    `create_all()` 只建缺少的表、不改既有的表，所以一個 v0.15 的資料庫會
    「看起來正常」直到第一次寫用量紀錄——那是一個半夜出現在某個學生螢幕上的
    500，而不是老師在啟動時看到的一行字（規則 4：不做無聲降級）。
    """
    import importlib
    import sqlite3

    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE student (id INTEGER PRIMARY KEY, student_no TEXT);"
        "CREATE TABLE usagelog (id INTEGER PRIMARY KEY, student_id INTEGER,"
        " template_id TEXT, difficulty INTEGER, seed INTEGER, action TEXT,"
        " created_at TEXT);"
    )
    con.commit()
    con.close()

    monkeypatch.setenv("PRACTICE_DB", str(db))
    from app import config as config_module

    importlib.reload(config_module)
    from app.db import session as session_module

    importlib.reload(session_module)

    with pytest.raises(session_module.LegacySchemaError) as excinfo:
        session_module.init_db()

    message = str(excinfo.value)
    assert "student" in message
    assert "rm " in message, "錯誤訊息要直接給出解決辦法，不是只說壞了"


# --- 自架的前端資產 -------------------------------------------------------

def test_referenced_static_assets_all_exist(client):
    """base.html 引用的每個 /static/ 資產都必須真的取得得到。

    升級 KaTeX／HTMX 時漏拷檔案，這個測試會直接抓到。
    """
    sign_in(client)
    html = client.get("/").text

    refs = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
    assert len(refs) >= 5, f"引用的靜態資產太少，base.html 可能被改壞了：{refs}"

    for ref in refs:
        r = client.get(ref)
        assert r.status_code == 200, f"{ref} 取不到（{r.status_code}）"
        assert len(r.content) > 0, f"{ref} 是空檔"


def test_no_external_cdn_dependency(client):
    """資產一律自架：頁面不得再引用外部 CDN（校內離線環境要能用）。"""
    sign_in(client)
    for path in ("/", "/login", "/demos"):
        html = client.get(path).text
        for host in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
            assert host not in html, f"{path} 仍引用外部 CDN：{host}"


def test_katex_fonts_referenced_by_css_are_present():
    """katex.min.css 裡列到的 woff2 字型檔都必須存在，否則數學會用錯字形。"""
    katex_dir = STATIC_DIR / "vendor" / "katex"
    css = (katex_dir / "katex.min.css").read_text(encoding="utf-8")

    woff2 = set(re.findall(r"url\((fonts/[^)]+\.woff2)\)", css))
    assert len(woff2) >= 15, f"解析到的字型太少：{len(woff2)}"

    missing = [f for f in sorted(woff2) if not (katex_dir / f).exists()]
    assert not missing, f"缺少字型檔：{missing}"


# --- 介面語言 -------------------------------------------------------------

# 中日韓統一表意文字 + 全形標點。程式碼註解與規劃文件仍用中文，
# 但**使用者看得到的任何字串**都不得出現這些字元。
CJK = re.compile(r"[　-〿一-鿿＀-￯]")


def test_ui_pages_contain_no_chinese(client):
    """本課程全英語授課，介面不得出現中文。

    v0.16：要看的頁面換了一輪——`/consent` 與 `/account/password` 沒有了，
    多了 `/activity`（只有 staff 進得去，所以它單獨走一次）。
    """
    sign_in(client)
    pages = {p: client.get(p).text for p in ("/", "/login")}
    for template_id in ALL_TEMPLATES:
        pages[f"problem:{template_id}"] = client.post(
            "/practice/generate",
            data={"template_id": template_id, "difficulty": 3},
        ).text
    pages["/activity:denied"] = client.get("/activity").text
    client.post("/logout")

    log_in(client, "staff", STAFF_PASSWORD)
    pages["/activity"] = client.get("/activity").text
    # v0.28：管理頁只有老師看得到，但 D5 沒有為它開例外——一個中英夾雜的
    # 介面會讓「不得出現中文」變成「除了某些頁面以外不得出現中文」。
    pages["/admin/content"] = client.get("/admin/content").text

    for where, text in pages.items():
        found = sorted(set(CJK.findall(text)))
        assert not found, f"{where} 出現中文字元: {''.join(found)}"


def test_error_messages_contain_no_chinese(client):
    """錯誤訊息也是使用者看得到的字串。

    v0.16：註冊、告知、改密碼的表單全部沒有了，學生唯一還會打錯字的地方
    就剩登入。速率限制那一則也一併看一次——它是這一版新的訊息。
    """
    make_accounts(client)

    text = client.post(
        "/login", data={"account": "nosuchthing", "password": "nope-nope-nope"}
    ).text
    assert not CJK.findall(text)

    from app.routes.auth import login_limiter

    for _ in range(login_limiter.limit):
        login_limiter.allow("login")
    text = client.post(
        "/login", data={"account": "class", "password": CLASS_PASSWORD}
    ).text
    assert "Too many login attempts" in text
    assert not CJK.findall(text)
    login_limiter.reset()

    # staff 限定頁的 403 訊息
    log_in(client)
    text = client.get("/activity").text
    assert not CJK.findall(text)


def test_generator_display_strings_contain_no_chinese():
    """題型名稱、難度說明、題目敘述、步驟標題與說明都必須是英文。"""
    from app.generator import generate, list_templates

    for tpl in list_templates():
        for field in (tpl.name, tpl.chapter, *tpl.difficulty_notes.values()):
            assert not CJK.search(field), f"{tpl.template_id}: {field}"
        for difficulty in tpl.difficulties:
            p = generate(tpl.template_id, difficulty)
            texts = [p.statement] + [s.title for s in p.steps] + \
                    [s.note for s in p.steps]
            for t in texts:
                assert not CJK.search(t), f"{tpl.template_id} d{difficulty}: {t}"


def test_step_notes_wrap_math_in_dollars():
    """步驟說明裡的數學片段要包在 $…$ 中，否則 KaTeX 不會渲染，
    學生會看到裸露的 e^{rx}。"""
    from app.generator import generate, list_templates

    for tpl in list_templates():
        for difficulty in tpl.difficulties:
            for p in [generate(tpl.template_id, difficulty) for _ in range(5)]:
                for s in p.steps:
                    for text in (s.title, s.note):
                        stripped = re.sub(r"\$[^$]*\$", "", text)
                        bad = [c for c in "^{}\\" if c in stripped]
                        assert not bad, (
                            f"{tpl.template_id} d{difficulty} 有未包進 $…$ 的數學："
                            f"{text!r}（裸露字元 {bad}）"
                        )


def test_vendor_licenses_are_kept():
    """vendoring 第三方程式碼時必須保留授權條款。"""
    vendor = STATIC_DIR / "vendor"
    for name in ("katex/LICENSE", "htmx.LICENSE"):
        path = vendor / name
        assert path.exists(), f"缺少 {name}"
        assert path.stat().st_size > 0
