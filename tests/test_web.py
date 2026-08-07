"""Web 流程測試：註冊 → 登入 → 出題 → 用量紀錄。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

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
    assert "請勿使用學校信箱或校務系統的密碼" in r.text
    assert "不是學校官方系統" in r.text
    assert "不用於評分" in r.text


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
    assert "勾選同意" in r.text


def test_register_rejects_mismatched_passwords(client):
    data = dict(REGISTER_FORM, password_confirm="something-else")
    r = client.post("/register", data=data)
    assert "兩次輸入的密碼不一致" in r.text


def test_register_rejects_short_password(client):
    data = dict(REGISTER_FORM, password="abc", password_confirm="abc")
    r = client.post("/register", data=data)
    assert "至少需要 8 個字元" in r.text


def test_register_rejects_duplicate_student_no(client):
    client.post("/register", data=REGISTER_FORM)
    client.post("/logout")
    r = client.post("/register", data=REGISTER_FORM)
    assert "已經註冊過了" in r.text


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
    assert "學號或密碼錯誤" in wrong_pw.text
    assert "學號或密碼錯誤" in no_such.text


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
    for name in ("可分離變數", "一階線性（積分因子）", "二階常係數齊次",
                 "一階線性系統 2×2（實相異特徵值）"):
        assert name in r.text
    for label in ("基礎", "標準", "挑戰"):
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
    assert "顯示逐步解答" in r.text
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
    assert "累計出題 <strong>0</strong>" in client.get("/").text

    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
    )
    assert 'hx-swap-oob="true"' in r.text
    assert "累計出題 <strong>1</strong>" in r.text


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}
