"""Web 流程測試：註冊 → 登入 → 出題 → 用量紀錄。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"

REGISTER_FORM = {
    "student_no": "41047001",
    "password": "practice-ode-2026",
    "password_confirm": "practice-ode-2026",
    "consent": "on",
}


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
    from app.routes import auth as auth_module
    from app.routes import deps as deps_module
    from app.routes import practice as practice_module

    importlib.reload(deps_module)
    importlib.reload(auth_module)
    importlib.reload(practice_module)
    from app import main as main_module

    importlib.reload(main_module)

    auth_module.login_limiter.reset()
    auth_module.register_limiter.reset()

    with TestClient(main_module.app) as c:
        c.session_module = session_module
        yield c


# --- 認證 -----------------------------------------------------------------

def test_index_redirects_to_login_when_anonymous(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_register_page_shows_password_reuse_warning(client):
    r = client.get("/register")
    assert r.status_code == 200
    assert "Do not reuse your university email or campus system password" in r.text
    assert "not an official university system" in r.text
    assert "not used for grading" in r.text


def test_register_then_logged_in(client):
    r = client.post("/register", data=REGISTER_FORM, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    r = client.get("/")
    assert r.status_code == 200
    assert "41047001" in r.text


def test_password_is_hashed_not_plaintext(client):
    """最重要的一條：資料庫裡絕不能出現明碼。"""
    client.post("/register", data=REGISTER_FORM)

    from app.db.models import Student

    with Session(client.session_module.engine) as s:
        student = s.exec(select(Student)).one()

    assert student.password_hash.startswith("$argon2")
    assert REGISTER_FORM["password"] not in student.password_hash
    assert student.consent_at is not None

    # 整個 DB 檔案裡也不能有明碼
    db_bytes = client.session_module.DB_PATH.read_bytes()
    assert REGISTER_FORM["password"].encode() not in db_bytes


def test_register_requires_consent(client):
    data = dict(REGISTER_FORM)
    data.pop("consent")
    r = client.post("/register", data=data)
    assert r.status_code == 200
    assert "accept the data collection notice" in r.text


def test_register_rejects_mismatched_passwords(client):
    data = dict(REGISTER_FORM, password_confirm="something-else")
    r = client.post("/register", data=data)
    assert "two passwords do not match" in r.text


def test_register_rejects_short_password(client):
    data = dict(REGISTER_FORM, password="abc", password_confirm="abc")
    r = client.post("/register", data=data)
    assert "at least 8 characters" in r.text


def test_register_rejects_duplicate_student_no(client):
    client.post("/register", data=REGISTER_FORM)
    client.post("/logout")
    r = client.post("/register", data=REGISTER_FORM)
    assert "already registered" in r.text


def test_login_and_logout(client):
    client.post("/register", data=REGISTER_FORM)
    client.post("/logout")

    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/login"

    r = client.post(
        "/login",
        data={"student_no": "41047001", "password": REGISTER_FORM["password"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.get("/").status_code == 200


def test_login_message_does_not_leak_account_existence(client):
    """帳號不存在與密碼錯誤要回傳同一則訊息。"""
    client.post("/register", data=REGISTER_FORM)
    client.post("/logout")

    wrong_pw = client.post(
        "/login", data={"student_no": "41047001", "password": "totally-wrong-pw"}
    )
    no_such = client.post(
        "/login", data={"student_no": "99999999", "password": "totally-wrong-pw"}
    )
    assert "Incorrect student ID or password" in wrong_pw.text
    assert "Incorrect student ID or password" in no_such.text


def test_student_no_is_case_normalized(client):
    client.post("/register", data=dict(REGISTER_FORM, student_no="b10901001"))
    client.post("/logout")
    r = client.post(
        "/login",
        data={"student_no": " B10901001 ", "password": REGISTER_FORM["password"]},
        follow_redirects=False,
    )
    assert r.status_code == 303


# --- 出題 -----------------------------------------------------------------

def test_practice_page_lists_all_templates(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.get("/")
    for name in ("Separable Equations",
                 "First-Order Linear (Integrating Factor)",
                 "Second-Order Homogeneous (Constant Coefficients)",
                 "Linear System 2×2 (Distinct Real Eigenvalues)"):
        assert name in r.text
    for label in ("Basic", "Standard", "Challenge"):
        assert label in r.text


@pytest.mark.parametrize(
    "template_id",
    [
        "ode.first_order.separable",
        "ode.first_order.linear",
        "ode.second_order.homogeneous",
        "system.linear_2x2.real_distinct",
    ],
)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_generate_returns_problem_fragment(client, template_id, difficulty):
    client.post("/register", data=REGISTER_FORM)
    r = client.post(
        "/practice/generate",
        data={"template_id": template_id, "difficulty": difficulty},
    )
    assert r.status_code == 200
    assert "Show step-by-step solution" in r.text
    assert "$$" in r.text                      # 有 LaTeX 供 KaTeX 渲染
    assert r.text.count("step-title") >= 3     # 逐步解答至少三步


def test_generate_requires_login(client):
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_generate_rejects_unknown_template(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.nope", "difficulty": 1},
    )
    assert r.status_code == 400


# --- 用量紀錄 -------------------------------------------------------------

def test_usage_is_logged(client):
    client.post("/register", data=REGISTER_FORM)
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
    assert all(log.student_id is not None for log in logs)
    assert all(log.created_at is not None for log in logs)
    assert all(log.seed > 0 for log in logs)

    # 紀錄只有「誰、何時、題型、難度」，不含作答內容
    assert set(UsageLog.model_fields) == {
        "id", "student_id", "template_id", "difficulty",
        "seed", "action", "created_at",
    }


def test_usage_panel_updates_after_generate(client):
    client.post("/register", data=REGISTER_FORM)
    assert "<strong>0</strong> problems generated" in client.get("/").text

    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
    )
    assert 'hx-swap-oob="true"' in r.text
    assert "<strong>1</strong> problems generated" in r.text


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


# --- 自架的前端資產 -------------------------------------------------------

def test_referenced_static_assets_all_exist(client):
    """base.html 引用的每個 /static/ 資產都必須真的取得得到。

    升級 KaTeX／HTMX 時漏拷檔案，這個測試會直接抓到。
    """
    client.post("/register", data=REGISTER_FORM)
    html = client.get("/").text

    refs = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
    assert len(refs) >= 5, f"引用的靜態資產太少，base.html 可能被改壞了：{refs}"

    for ref in refs:
        r = client.get(ref)
        assert r.status_code == 200, f"{ref} 取不到（{r.status_code}）"
        assert len(r.content) > 0, f"{ref} 是空檔"


def test_no_external_cdn_dependency(client):
    """資產一律自架：頁面不得再引用外部 CDN（校內離線環境要能用）。"""
    client.post("/register", data=REGISTER_FORM)
    for path in ("/", "/login", "/register"):
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
    """本課程全英語授課，介面不得出現中文。"""
    client.post("/register", data=REGISTER_FORM)
    pages = {p: client.get(p).text for p in ("/", "/login", "/register")}
    pages["fragment"] = client.post(
        "/practice/generate",
        data={"template_id": "system.linear_2x2.real_distinct", "difficulty": 3},
    ).text
    for where, text in pages.items():
        found = sorted(set(CJK.findall(text)))
        assert not found, f"{where} 出現中文字元: {''.join(found)}"


def test_error_messages_contain_no_chinese(client):
    """錯誤訊息也是使用者看得到的字串。"""
    bad = [
        ("/register", dict(REGISTER_FORM, password="abc", password_confirm="abc")),
        ("/register", {k: v for k, v in REGISTER_FORM.items() if k != "consent"}),
        ("/register", dict(REGISTER_FORM, password_confirm="different-one")),
        ("/register", dict(REGISTER_FORM, student_no="!!")),
        ("/login", {"student_no": "99999999", "password": "nope-nope-nope"}),
    ]
    for path, data in bad:
        text = client.post(path, data=data).text
        found = sorted(set(CJK.findall(text)))
        assert not found, f"{path} 的錯誤訊息出現中文: {''.join(found)}"


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
