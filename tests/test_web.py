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
    # 每個測試都有自己的 lifespan；每次都把判定子行程暖機一遍會拖慢整份測試，
    # 而且判定本身另有 tests/test_grader_sandbox.py 專門驗證。
    monkeypatch.setenv("GRADER_WARMUP", "0")

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
    assert "$$" in r.text                      # 有 LaTeX 供 KaTeX 渲染
    assert 'name="answer"' in r.text           # 可以作答
    assert "Show solution" in r.text           # 解答另外要（見 /practice/solution）


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


# --- 作答判定 -------------------------------------------------------------

def _generate_problem(client, template_id="ode.second_order.homogeneous", difficulty=1):
    """走一次出題端點，回傳可用來重現該題的表單欄位。"""
    html = client.post(
        "/practice/generate",
        data={"template_id": template_id, "difficulty": difficulty},
    ).text
    seed = int(re.search(r'name="seed" value="(\d+)"', html).group(1))
    from app.generator import generate

    return {
        "template_id": template_id,
        "difficulty": difficulty,
        "seed": seed,
    }, generate(template_id, difficulty, seed=seed)


def _reference_text(problem) -> str:
    import sympy as sp

    if problem.check.kind == "system":
        body = ", ".join(str(sp.expand(c)) for c in problem.answer_expr)
    else:
        body = str(problem.answer_expr)
    return body.replace("C_1", "C1").replace("C_2", "C2")


def test_problem_fragment_has_an_answer_box(client):
    client.post("/register", data=REGISTER_FORM)
    fields, _ = _generate_problem(client)
    html = client.post(
        "/practice/generate",
        data={"template_id": fields["template_id"], "difficulty": 1},
    ).text
    assert 'name="answer"' in html
    assert "Check my answer" in html
    assert "Show solution" in html


def test_solution_is_not_shipped_with_the_problem(client):
    """解答不得隨題目一起送到瀏覽器——否則按 F12 就看得到，作答就沒有意義了。"""
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    html = client.post("/practice/generate", data=fields).text
    assert "Step-by-step solution" not in html
    assert problem.answer_latex not in html


def test_submit_correct_answer(client):
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    r = client.post("/practice/submit",
                    data=dict(fields, answer=_reference_text(problem)))
    assert r.status_code == 200
    assert "Correct" in r.text
    assert "Your answer was read as" in r.text


def test_submit_reparametrised_answer_is_also_correct(client):
    """換一種寫法的等價答案，一樣要判對（這是判分的重點，見 PLAN.md §5.3）。"""
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    r1, r2 = problem.params["r1"], problem.params["r2"]
    r = client.post(
        "/practice/submit",
        data=dict(fields, answer=f"(A+B)*e^({r1}x) + (A-B)*e^({r2}x)"),
    )
    assert "Correct" in r.text


def test_submit_wrong_answer_does_not_reveal_the_solution(client):
    """答錯時只給提示，不爆雷。"""
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    r = client.post("/practice/submit", data=dict(fields, answer="C1*x + C2*x^2"))
    assert "Not correct yet" in r.text
    assert problem.answer_latex not in r.text
    assert "Step-by-step solution" not in r.text


def test_submit_partial_answer_says_what_is_missing(client):
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    r1 = problem.params["r1"]
    r = client.post("/practice/submit", data=dict(fields, answer=f"C1*e^({r1}x)"))
    assert "arbitrary constant is missing" in r.text
    assert "2 arbitrary constants" in r.text


def test_submit_unreadable_answer_gives_help(client):
    client.post("/register", data=REGISTER_FORM)
    fields, _ = _generate_problem(client)
    r = client.post("/practice/submit", data=dict(fields, answer="C1*e^(3x"))
    assert r.status_code == 200
    assert "Could not read your answer" in r.text


def test_submit_requires_login(client):
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    answer = _reference_text(problem)
    client.post("/logout")

    r = client.post("/practice/submit", data=dict(fields, answer=answer),
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    from app.db.models import Attempt

    with Session(client.session_module.engine) as s:
        assert s.exec(select(Attempt)).all() == []


def test_submit_rejects_a_bogus_seed(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.post("/practice/submit", data={
        "template_id": "ode.second_order.homogeneous",
        "difficulty": 1, "seed": 0, "answer": "C1*e^(-x)",
    })
    assert r.status_code == 400


def test_attempt_is_recorded(client):
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    answer = _reference_text(problem)
    client.post("/practice/submit", data=dict(fields, answer=answer))
    client.post("/practice/submit", data=dict(fields, answer="C1*x"))

    from app.db.models import Attempt

    with Session(client.session_module.engine) as s:
        attempts = s.exec(select(Attempt).order_by(Attempt.id)).all()

    assert len(attempts) == 2
    first, second = attempts
    assert first.is_correct and first.verdict == "correct"
    assert not second.is_correct
    assert first.submitted_raw == answer          # 存的是學生的原始輸入
    assert second.submitted_raw == "C1*x"
    assert first.template_id == fields["template_id"]
    assert first.seed == fields["seed"]           # 題目可由 seed 完整重現
    assert first.duration_ms >= 0
    assert first.created_at is not None
    assert first.params_json                      # 當初的出題參數


def test_attempt_table_has_no_score_column(client):
    """依 D1 不計分：Attempt 不得出現任何分數欄位。"""
    from app.db.models import Attempt

    assert set(Attempt.model_fields) == {
        "id", "student_id", "template_id", "difficulty", "seed", "params_json",
        "submitted_raw", "verdict", "is_correct", "is_partial",
        "duration_ms", "created_at",
    }


# --- 顯示解答 -------------------------------------------------------------

def test_show_solution_returns_steps_and_is_logged(client):
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)

    r = client.post("/practice/solution", data=fields)
    assert r.status_code == 200
    assert "Step-by-step solution" in r.text
    assert r.text.count("step-title") >= 3
    assert problem.answer_latex in r.text

    from app.db.models import UsageLog

    with Session(client.session_module.engine) as s:
        actions = [log.action for log in s.exec(select(UsageLog)).all()]
    assert actions.count("view_solution") == 1


def test_show_solution_requires_login(client):
    r = client.post("/practice/solution", data={
        "template_id": "ode.second_order.homogeneous", "difficulty": 1, "seed": 1,
    }, follow_redirects=False)
    assert r.status_code == 303


# --- 我的紀錄 -------------------------------------------------------------

def test_progress_page_requires_login(client):
    r = client.get("/progress", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_progress_page_starts_empty(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.get("/progress")
    assert r.status_code == 200
    assert "not submitted any answers yet" in r.text


def test_progress_page_shows_history_and_accuracy(client):
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    client.post("/practice/submit", data=dict(fields, answer=_reference_text(problem)))
    client.post("/practice/submit", data=dict(fields, answer="C1*x"))

    r = client.get("/progress")
    assert "Second-Order Homogeneous" in r.text
    assert "50%" in r.text                        # 兩題對一題
    assert "C1*x" in r.text                       # 作答歷史
    assert "not used for grading" in r.text


def test_progress_page_shows_only_my_own_data(client):
    """最重要的一條：別人的作答紀錄不得出現在我的頁面上。"""
    client.post("/register", data=REGISTER_FORM)
    fields, problem = _generate_problem(client)
    client.post("/practice/submit",
                data=dict(fields, answer="C1*secret_of_student_one"))
    client.post("/logout")

    other = dict(REGISTER_FORM, student_no="41047002")
    client.post("/register", data=other)
    fields2, problem2 = _generate_problem(client)
    client.post("/practice/submit", data=dict(fields2, answer="C2*only_mine"))

    r = client.get("/progress")
    assert "only_mine" in r.text
    assert "secret_of_student_one" not in r.text

    from app.db.models import Attempt

    with Session(client.session_module.engine) as s:
        assert len(s.exec(select(Attempt)).all()) == 2      # 兩筆都在，只是不互相看得到


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
    pages = {p: client.get(p).text for p in ("/", "/login", "/register", "/progress")}
    pages["problem"] = client.post(
        "/practice/generate",
        data={"template_id": "system.linear_2x2.real_distinct", "difficulty": 3},
    ).text
    fields, problem = _generate_problem(client)
    pages["feedback_correct"] = client.post(
        "/practice/submit", data=dict(fields, answer=_reference_text(problem))
    ).text
    pages["feedback_wrong"] = client.post(
        "/practice/submit", data=dict(fields, answer="C1*x")
    ).text
    pages["feedback_unreadable"] = client.post(
        "/practice/submit", data=dict(fields, answer="C1*e^(3x")
    ).text
    pages["solution"] = client.post("/practice/solution", data=fields).text
    pages["progress_filled"] = client.get("/progress").text
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
