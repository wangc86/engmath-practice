"""Web 流程測試：註冊 → 登入 → 出題 → 展開答案／詳解 → 用量紀錄。

v0.7（D12）：作答判定的測試（`test_grader.py`、`test_grader_sandbox.py`，
以及本檔案裡「作答判定」與「Attempt」兩組）已隨判定一起移除，保存在
tag `grading-v1`。新增的是 D13 的答案遮蔽測試（見「答案與詳解的收合」一節）。
"""

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

ALL_TEMPLATES = [
    "ode.first_order.separable",
    "ode.first_order.linear",
    "ode.second_order.homogeneous",
    "system.linear_2x2.real_distinct",
]


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
    from app.routes import demos as demos_module
    from app.routes import deps as deps_module
    from app.routes import practice as practice_module

    # 順序有意義：每個模組都在 import 時把 `engine` 綁進自己的命名空間，
    # 所以換了 DB 檔之後每一個都要重新載入，而且被依賴的要先載入
    # （practice 匯入 demos 的 DEMO_ACTION／DEMOS）。漏掉一個的症狀是
    # 「FOREIGN KEY constraint failed」——那個模組還在寫上一個測試的 DB。
    importlib.reload(deps_module)
    importlib.reload(demos_module)
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
    # D17：系統對評分一事保持沉默——既不說「用於評分」也不說「不用於評分」。
    # 課程如何採計由老師在課堂上口頭宣布，頁面不得出現任何評分相關字眼。
    assert "grading" not in r.text.lower()
    assert "grade" not in r.text.lower()


def test_register_notice_no_longer_claims_to_collect_answers(client):
    """D12：系統不再蒐集作答內容，個資告知要跟著縮回（PLAN.md §4.4）。

    告知範圍比實際蒐集的還寬，本身就是一種不準確；而且這一句留著會讓
    「系統會不會偷偷記我打的東西」變成一個學生無法否證的疑問。
    """
    r = client.get("/register")
    assert "the answers you submit" not in r.text
    assert "Nothing you type while solving a problem is sent to the server" in r.text


def test_notice_matches_the_fields_actually_stored(client):
    """告知的範圍必須等於實際寫入資料庫的欄位——比實際寬或窄都是不準確。

    欄位清單刻意寫死在這裡。日後有人在 Student 或 UsageLog 加一個欄位，
    這一項就會紅燈，逼他回頭看一眼註冊頁的告知文字還算不算數。
    這是唯一會攔住「悄悄多蒐集了一項」的地方。
    """
    from app.db.models import Student, UsageLog

    assert set(Student.__table__.columns.keys()) == {
        "id", "student_no", "password_hash",
        "created_at", "last_login_at", "consent_at",
    }
    assert set(UsageLog.__table__.columns.keys()) == {
        "id", "student_id", "template_id", "difficulty",
        "seed", "action", "created_at",
    }

    text = client.get("/register").text
    for phrase in (
        "student ID",                       # student_no
        "password hash",                    # password_hash
        "times you registered",             # created_at
        "last logged in",                   # last_login_at
        "accepted this notice",             # consent_at
        "topic",                            # template_id
        "difficulty",                       # difficulty
        "which problem you were given",     # seed
        "and the time",                     # created_at
    ):
        assert phrase in text, f"個資告知漏了：{phrase}"


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


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_generate_returns_problem_fragment(client, template_id, difficulty):
    client.post("/register", data=REGISTER_FORM)
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
    client.post("/register", data=REGISTER_FORM)
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
    client.post("/register", data=REGISTER_FORM)
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
    client.post("/register", data=REGISTER_FORM)
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
    client.post("/register", data=REGISTER_FORM)
    html, _ = _generate(client)

    answer_open = html.index('class="reveal reveal-answer"')
    steps_open = html.index('class="reveal reveal-steps"')
    answer_close = html.rindex("</details>")
    assert answer_open < steps_open < answer_close


def test_generating_a_problem_does_not_log_a_view_solution_action(client):
    """`<details>` 展開不發請求，所以不會有 view_solution 這則紀錄。

    這是 D13 取捨的代價，寫在 PLAN.md §5.8。測試把它釘住，免得日後有人
    看到 `UsageLog.action` 這個欄位就以為還有第二種值。
    """
    client.post("/register", data=REGISTER_FORM)
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
    client.post("/register", data=REGISTER_FORM)
    for path in ("/practice/submit", "/practice/solution"):
        r = client.post(path, data={
            "template_id": "ode.second_order.homogeneous",
            "difficulty": 1, "seed": 1, "answer": "C1*e^(-x)",
        })
        assert r.status_code == 404, f"{path} 還在"


def test_attempt_table_is_gone(client):
    """D12：`Attempt` 模型必須整個消失，不是留著不用。"""
    import app.db.models as models

    assert not hasattr(models, "Attempt")

    from sqlmodel import SQLModel

    tables = set(SQLModel.metadata.tables)
    assert "attempt" not in tables
    assert {"student", "usagelog"} <= tables


def test_grader_package_is_gone():
    """D12：`app.grader` 不該再 import 得到（保存在 tag grading-v1）。"""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.grader")


# --- 我的紀錄 -------------------------------------------------------------

def test_progress_page_requires_login(client):
    r = client.get("/progress", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_progress_page_starts_empty(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.get("/progress")
    assert r.status_code == 200
    assert "not generated any problems yet" in r.text


def test_progress_page_shows_usage_only(client):
    """用量留著（D1，老師要看），正確率沒了（D12，沒有東西可以算）。"""
    client.post("/register", data=REGISTER_FORM)
    _generate(client)
    _generate(client, "ode.first_order.linear", 2)

    r = client.get("/progress")
    assert "Second-Order Homogeneous" in r.text
    assert "First-Order Linear" in r.text
    # D17：頁面（含 base.html 的頁尾）不得出現任何評分相關字眼。
    assert "grading" not in r.text.lower()
    assert "grade" not in r.text.lower()

    for gone in ("Correct rate", "Partly correct", "Your answer",
                 "verdict", "Submitted"):
        assert gone not in r.text, f"「我的紀錄」還留著判定相關的欄位：{gone}"


def test_progress_page_shows_only_my_own_data(client):
    """最重要的一條：別人的紀錄不得出現在我的頁面上。"""
    client.post("/register", data=REGISTER_FORM)
    _generate(client, "system.linear_2x2.real_distinct", 3)
    client.post("/logout")

    client.post("/register", data=dict(REGISTER_FORM, student_no="41047002"))
    _generate(client, "ode.first_order.separable", 1)

    r = client.get("/progress")
    assert "Separable Equations" in r.text
    assert "Linear System" not in r.text, "看到了別人練的題型"

    from app.db.models import UsageLog

    with Session(client.session_module.engine) as s:
        assert len(s.exec(select(UsageLog)).all()) == 2   # 兩筆都在，只是不互相看得到


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

    # 紀錄只有「誰、何時、題型、難度」，不含作答內容，也沒有任何分數欄位
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
    """v0.7（D12）：只證明進程活著。判定子行程池的狀態沒有了。"""
    body = client.get("/healthz").json()
    assert body == {"status": "ok"}


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
    for template_id in ALL_TEMPLATES:
        pages[f"problem:{template_id}"] = client.post(
            "/practice/generate",
            data={"template_id": template_id, "difficulty": 3},
        ).text
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
