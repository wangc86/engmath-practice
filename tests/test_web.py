"""Web 流程測試：出題 → 展開答案／詳解 → 相圖的洩題防護 → 介面語言與資產。

## ⚠️ v0.29（D57、D58、D59）：這一份少了 108 項，而每一組都有名字

系統改為**學生自行在自己的電腦上安裝執行**之後，下面這些測試**不是被
放寬，是失去了標的**——它們守的東西已經不存在了：

- **認證與帳號**（登入、登出、密碼雜湊、帳號列舉、速率限制、大小寫正規化）
  → 沒有帳號了（D57）。
- **登入閘門**（列舉整張路由表、豁免清單、HX-Redirect、中介層順序）
  → 沒有閘門了（D57）。
- **IP 不落地**（五項，D38）→ 沒有伺服器了。唯一的用戶端是 `127.0.0.1`，
  而唯一看得到那行 log 的人就是本人。
- **用量紀錄**（欄位不得指向個人、學號掃描、staff 排除）→ 沒有資料庫了（D58）。
- **全班活動頁**（七項，D36／D39）→ 那一頁沒有了（D58）。
- **舊資料庫要大聲壞掉**（D35 的 `LegacySchemaError`）→ 沒有資料庫了。
- **內容開放閘門**（`test_release.py` 整份，47 項）→ 沒有閘門了（D59）；
  歸類本身的測試搬到 `test_curriculum.py`。

⛔ **這不是「測試變少了所以品質下降」。** 這一份現在守的是這個系統**唯一
還在做的事**：出題、遮蔽答案、不洩題、介面是英文、資產自架。
上面那些項目留著只會變成「守著不存在的東西的綠燈」，而那比沒有測試更糟
——它會讓測試總數看起來很安全。

保存版本在 tag `hosted-v1`。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
TEMPLATES_DIR = APP_DIR / "templates"


def _all_templates() -> list[str]:
    """所有已註冊的題型代號。

    ⚠️ **刻意從註冊表讀，不是手寫一份清單。**
    這一整組 Web 測試守的性質是「新增一個題型，UI 與畫面會自動撿到它」——
    而手寫的清單會讓一個沒有被撿到的新題型**照樣全綠**，正好把要守的東西守掉了。
    """
    from app.generator import list_templates

    return sorted(t.template_id for t in list_templates())


ALL_TEMPLATES = _all_templates()


@pytest.fixture()
def client():
    """一個 TestClient。

    ⚠️ **v0.29 之後這個 fixture 只有三行**，而那正是這一版最大的結構性改變：
    在這之前它要換掉 `PRACTICE_DB`、設 `SESSION_SECRET`、然後**依相依順序
    重新載入九個模組**（每個模組都在 import 時把 `engine` 綁進自己的命名空間，
    漏掉一個的症狀是「FOREIGN KEY constraint failed」——那個模組還在寫上
    一個測試的資料庫）。

    沒有資料庫、沒有 session 之後，那整套消失了。**應用程式現在沒有狀態**，
    所以測試之間不會互相汙染，也就不需要隔離。
    """
    from app import main as main_module

    with TestClient(main_module.app) as c:
        c.fastapi_app = main_module.app
        yield c


# --- 出題 -----------------------------------------------------------------

def test_practice_page_groups_topics_by_week(client):
    """下拉選單必須列出註冊表裡的**每一個**題型，而且依課程週次分組（D59）。

    名稱一樣從註冊表讀（理由見 `_all_templates`）：寫死幾個名字的版本
    在新增題型時不會變紅，而「新題型自動出現在選單上」正是這一項要守的事。

    ⚠️ v0.28 之前這裡驗的是 `optgroup` 用 `Template.chapter`；v0.29 改成
    週次（學生找的是「這週上課提到的那個」，§7 #34）。**兩者都驗過分組
    真的存在**——一個把 `optgroup` 整個拿掉的改動仍然會讓每個題型出現在
    選單上，所以「有分組」要單獨驗。
    """
    from markupsafe import escape

    from app.curriculum import KIND_PRACTICE, weeks_with_content
    from app.generator import list_templates

    r = client.get("/")
    assert r.status_code == 200
    for tpl in list_templates():
        assert tpl.template_id in r.text, f"選單缺 {tpl.template_id}"
        assert str(escape(tpl.name)) in r.text, f"選單缺 {tpl.name}"
    for label in ("Basic", "Standard", "Challenge"):
        assert label in r.text

    weeks = weeks_with_content(KIND_PRACTICE)
    assert weeks, "沒有任何一週有題型——歸類表可能壞了"
    for week in weeks:
        assert f'<optgroup label="Week {week.number} — ' in r.text, (
            f"選單缺第 {week.number} 週的分組"
        )


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_generate_returns_problem_fragment(client, template_id, difficulty):
    r = client.post(
        "/practice/generate",
        data={"template_id": template_id, "difficulty": difficulty},
    )
    assert r.status_code == 200
    assert "$$" in r.text                      # 有 LaTeX 供 KaTeX 渲染
    assert "Show Answer" in r.text             # D13 的第一層
    assert "Show Solution Steps" in r.text     # D13 的第二層


def test_generate_rejects_unknown_template(client):
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.nope", "difficulty": 1},
    )
    assert r.status_code == 400


def test_generate_rejects_a_difficulty_the_template_does_not_have(client):
    """`generate()` 對不支援的難度丟 `ValueError`，路由要把它變成 400。

    ⚠️ v0.29 新增。在這之前這條路徑**沒有測試**——它一直都在
    （`except (KeyError, ValueError)` 那一行），但只有 `KeyError` 那一半
    被驗過。拆掉登入之後這個端點是系統唯一接受外部輸入的地方，
    所以它的每一條錯誤路徑都該有人看著。
    """
    r = client.post(
        "/practice/generate",
        data={"template_id": ALL_TEMPLATES[0], "difficulty": 9},
    )
    assert r.status_code == 400
    assert "$$" not in r.text


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

    這是 D13 的核心：使用者一按 Generate 就同時看到題目和答案的話，
    這個工具就從「練習」退化成「範例集」。

    注意這裡驗的是「摺疊」而不是「不在 HTML 裡」——實作刻意選了 `<details>`，
    答案確實在原始碼裡（取捨見 PLAN.md §5.8）。因此測試盯的是**沒有任何一個
    `<details>` 帶 `open` 屬性**：漏掉 `open` 是這個實作唯一會靜默出錯的方式。
    """
    html, _ = _generate(client, template_id, difficulty=2)

    tags = DETAILS_TAG.findall(html)
    assert len(tags) == 2, f"預期兩層 details（答案、詳解），實際 {len(tags)} 個"
    for tag in tags:
        assert " open" not in tag, f"答案／詳解預設展開了：{tag}"

    # 兩個 summary 的文字也要在，否則使用者根本不知道有東西可以點
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
    html, _ = _generate(client)

    answer_open = html.index('class="reveal reveal-answer"')
    steps_open = html.index('class="reveal reveal-steps"')
    answer_close = html.rindex("</details>")
    assert answer_open < steps_open < answer_close


# --- 相圖的洩題防護（PLAN.md §2.2.1 第二條、§2.11.1；v0.26 的 2B7）--------
#
# 這一組是上面「答案遮蔽」那一組的同型延伸，而且理由一模一樣：
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
    # v0.30（2B8）。⚠️ **這一個對洩題最敏感**：它的題目就是「這是哪一種
    # 平衡點」，所以那張圖**就是答案本身**。其餘三個的圖只是附加的說明。
    "system.linear_2x2.classification",
]


@pytest.mark.parametrize("template_id", PORTRAIT_TEMPLATES)
def test_the_phase_portrait_never_escapes_the_collapsed_block(client, template_id):
    r"""⛔ 相圖只能出現在第二層 `<details>`（Show Solution Steps）裡面。

    三件事一起驗，缺一不可：

    1. 片段裡**真的有一張圖**（否則下面兩項恆綠）
    2. 第一個 `<details>` **之前**沒有 `<svg`（也就是題目敘述區塊乾淨）
    3. 圖在 `reveal-steps` 那一層的範圍內，不是在答案那一層
    """
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

    ⚠️ **這一項在 v0.29 之後更重要，不是更不重要。** 它原本的威脅模型是
    「一個公開網站上的 XSS」；現在系統跑在使用者自己的機器上，看起來風險
    降低了——但**那個範本渲染的內容來自 SymPy 與 generator，而它們沒有變**，
    而白名單真正在守的是「範本印得出什麼由範本決定」這件事本身。
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

    少了 `|safe` 的症狀是使用者看到一整段 SVG 原始碼印在頁面上。
    那不是靜默失敗（很醜、一眼看得到），但它值得一項測試，
    因為修好之後很容易在某次範本重構時再被拿掉。
    """
    html, _ = _generate(client, "system.linear_2x2.complex", difficulty=1)
    assert "&lt;svg" not in html
    assert "<polyline" in html and "<marker" in html


# --- 已移除的東西，不准回來 -----------------------------------------------
#
# 這一組守的是「刪乾淨了沒有」。它看起來很消極，但這個專案已經拆過四輪
# 大東西（D12 判分、D32／D35 註冊與帳號、D41 對話介面、D57–D59 站台化），
# 而每一輪都有東西差點被留下來——留著一個沒有人用、沒有測試在看的端點或
# 模組，比刪掉它危險。


def test_nothing_in_the_app_imports_a_database(client):
    """⛔ 系統沒有資料庫，而那是一個要守住的性質（D58）。

    最可能打破它的方式不是「有人加了一張表」（那看得見），是**有人為了
    一個看起來無害的小功能加了一行 `import sqlite3`**——例如「把上次選的
    題型記起來」。那一行會把「關掉它就什麼都不剩」這個承諾拿掉，
    而頁尾正寫著那句話。
    """
    banned = ("sqlmodel", "sqlalchemy", "sqlite3")
    offenders = []
    for source in APP_DIR.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and any(
                name in stripped for name in banned
            ):
                offenders.append(f"{source.relative_to(APP_DIR)}: {stripped}")
    assert not offenders, offenders


def test_the_footer_promise_is_true_no_outbound_url_in_any_page(client):
    """頁尾說「它從不把任何東西送出網路」，所以那必須是真的（第八條硬規則）。

    掃每一頁的 HTML：不得有任何 `http://` 或 `https://` 的資源引用。
    ⚠️ 只掃屬性值，不掃文字——`xmlns="http://www.w3.org/2000/svg"` 是
    命名空間宣告，不是一個會被抓取的網址，所以它在白名單上。
    """
    allowed = ("http://www.w3.org/",)      # XML／SVG 命名空間
    for path in ("/", "/demos", "/demos/fourier/series"):
        html = client.get(path).text
        for url in re.findall(r'(?:href|src|action)="(https?://[^"]+)"', html):
            assert url.startswith(allowed), f"{path} 引用了外部網址：{url}"


def test_healthz(client):
    """安裝說明用它確認伺服器真的起來了（`curl .../healthz`）。"""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- 自架的前端資產 -------------------------------------------------------

def test_referenced_static_assets_all_exist(client):
    """base.html 引用的每個 /static/ 資產都必須真的取得得到。

    升級 KaTeX／HTMX 時漏拷檔案，這個測試會直接抓到。
    """
    html = client.get("/").text

    refs = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
    assert len(refs) >= 5, f"引用的靜態資產太少，base.html 可能被改壞了：{refs}"

    for ref in refs:
        r = client.get(ref)
        assert r.status_code == 200, f"{ref} 取不到（{r.status_code}）"
        assert len(r.content) > 0, f"{ref} 是空檔"


def test_no_external_cdn_dependency(client):
    """資產一律自架。

    ⚠️ **v0.29 之後這條的理由更強了。** 原本是「校內網路連不到 CDN 時
    整頁數學會失效」；現在系統跑在使用者自己的電腦上，而它應該在**完全
    離線**的情況下也能用——一個學生在飛機上、在宿舍網路壞掉的時候
    打開它，數學仍然要排版得出來。
    """
    for path in ("/", "/demos"):
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


def test_vendor_licenses_are_kept():
    """vendoring 第三方程式碼時必須保留授權條款。

    ⚠️ **v0.29 之後這一項從「應該做」變成「必須做」**：專案要公開到 GitHub
    給學生下載，而那是一次真正的散布。
    """
    vendor = STATIC_DIR / "vendor"
    for name in ("katex/LICENSE", "htmx.LICENSE", "fftjs/LICENSE"):
        path = vendor / name
        assert path.exists(), f"缺少 {name}"
        assert path.stat().st_size > 0


def test_the_project_has_its_own_licence_and_it_names_the_vendored_ones():
    """⚠️ v0.30：專案自己也要有一份 `LICENSE`，而且要指出 vendored 的三份。

    **一份只講自己的授權條款會讓讀的人以為它涵蓋整個 repo**，
    而 `app/static/vendor/` 底下那三個不是我們的。GitHub 只會顯示根目錄那
    一份，所以「另外三份在哪裡」必須寫在它裡面——那是唯一一個讀得到的地方。
    """
    root = APP_DIR.parent
    licence = root / "LICENSE"
    assert licence.exists(), "根目錄缺少 LICENSE"
    text = licence.read_text(encoding="utf-8")
    assert "MIT" in text
    for name in ("katex/LICENSE", "htmx.LICENSE", "fftjs/LICENSE"):
        assert name in text, f"LICENSE 沒有指出 {name}"


# --- 介面語言 -------------------------------------------------------------

# 中日韓統一表意文字 + 全形標點。程式碼註解與規劃文件仍用中文，
# 但**使用者看得到的任何字串**都不得出現這些字元。
CJK = re.compile(r"[　-〿一-鿿＀-￯]")


def test_ui_pages_contain_no_chinese(client):
    """本課程全英語授課，介面不得出現中文（D5）。

    ⚠️ v0.29：要看的頁面又換了一輪——`/login`、`/activity`、`/admin/content`
    都沒有了，剩下的是出題頁、展示索引，以及每一個題型的題目卡片。
    """
    pages = {p: client.get(p).text for p in ("/", "/demos")}
    for template_id in ALL_TEMPLATES:
        pages[f"problem:{template_id}"] = client.post(
            "/practice/generate",
            data={"template_id": template_id, "difficulty": 3},
        ).text

    for where, text in pages.items():
        found = sorted(set(CJK.findall(text)))
        assert not found, f"{where} 出現中文字元: {''.join(found)}"


def test_error_messages_contain_no_chinese(client):
    """錯誤訊息也是使用者看得到的字串。

    ⚠️ v0.29：登入表單沒有了，所以使用者能撞到的錯誤只剩兩種，
    而兩種都在出題端點上（不認得的題型、不支援的難度）。
    """
    texts = [
        client.post(
            "/practice/generate",
            data={"template_id": "ode.nope", "difficulty": 1},
        ).text,
        client.post(
            "/practice/generate",
            data={"template_id": ALL_TEMPLATES[0], "difficulty": 9},
        ).text,
        client.get("/demos/nope/nope").text,
    ]
    for text in texts:
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
    使用者會看到裸露的 e^{rx}。"""
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

def _orphans_under(root: Path, loaded: set[Path]) -> tuple[list[str], str]:
    r"""`root` 底下有哪些 `.py` 不在 `loaded` 裡，以及要不要多印一句提示。

    ⚠️ **這個函式是被抽出來的，理由只有一個：讓下面那項檢查可以被證明會紅。**
    真正的檢查跑在真的 `app/` 上，而真的 `app/` 現在（也應該永遠）沒有孤兒，
    所以它平常永遠是綠的——**一項永遠綠的檢查，和一項寫錯了因而永遠不會紅的
    檢查，從外面看完全一樣。** 抽出來之後，`test_the_orphan_check_actually_goes_red`
    可以拿一棵合成的樹餵給它，當場看它變紅。

    回傳 `(孤兒的相對路徑清單, 提示字串)`；提示字串在孤兒含 `@register(` 時才非空。
    """
    loaded_resolved = {p.resolve() for p in loaded}
    on_disk = {p.resolve() for p in root.rglob("*.py")
               if "__pycache__" not in p.parts}

    orphans = sorted(p.relative_to(root.parent.resolve()).as_posix()
                     for p in on_disk - loaded_resolved)
    hint = ""
    for orphan in orphans:
        if "@register(" in (root.parent / orphan).read_text(encoding="utf-8"):
            hint = ("\n⛔ 其中至少一個含 `@register(`——那是一個註冊不起來的題型，"
                    "多半是漏了 `app/generator/__init__.py` 的那一行 import。")
    return orphans, hint


def test_no_python_file_under_app_is_an_orphan():
    r"""⛔ `app/` 底下的每一個 `.py` 都必須真的被 `app.main` 拉進來。

    **這一項守的是一個沒有任何東西會抱怨的錯誤。** 最具體的走法：有人寫了一個
    新的 generator，`@register(...)` 也寫好了，**但忘了在
    `app/generator/__init__.py` 加那一行 import**。結果是——

    * 那個題型不在註冊表裡，所以選單上沒有、`CASES` 展不出它、
      `test_every_registered_template_has_a_week` 也不會紅（它只走註冊表）；
    * `app/curriculum.py` 那一列如果也忘了補，同樣不會紅；
    * **1162 項測試全綠，而那個檔案是死的。**

    ⚠️ **相依地圖也看不見它**（v0.36、D68）：地圖記的是「測試執行時碰過哪些
    檔案」，而沒有人 import 的檔案永遠不會被碰到。那一格目前由「地圖不認得的
    原始碼路徑一律全跑」這條保守規則兜著——**全跑**會發生，但**沒有人會被告知
    那個檔案是死的**。這一項就是那個告知。

    ⚠️ 這是 v0.37 新增的兩道結構性看守之一（老師問「能不能建立規則，讓這類
    問題在 AI 實作時不會發生」）。**答案是：這一類與是誰在打字無關**
    ——AI 一樣會忘記加那一行——所以它需要的是一項測試，不是一條慣例。

    ⚠️ 這一項在正常的 repo 上永遠是綠的，所以它自己不會示範自己還會動；
    那件事由下面的 `test_the_orphan_check_actually_goes_red` 負責（v0.38、D71）。
    """
    import sys
    import app.main  # noqa: F401  匯入以觸發整個相依樹

    loaded = {Path(m.__file__)
              for m in list(sys.modules.values())
              if getattr(m, "__file__", None)}

    orphans, hint = _orphans_under(APP_DIR, loaded)
    assert not orphans, (
        f"這些檔案在 app/ 底下，但 `import app.main` 之後沒有被載入：{orphans}"
        f"{hint}\n"
        "要嘛把它接上去，要嘛把它刪掉——⚠️ **留著一個沒有人 import 的檔案，"
        "讀程式的人會以為那個功能存在。**"
    )


def test_the_orphan_check_actually_goes_red(tmp_path: Path):
    r"""⛔ 上面那項檢查，拿一個真的孤兒餵給它，它必須紅。

    **為什麼要有這一項。** 上面那項在正常的 repo 上永遠是綠的——那正是它該有的
    樣子，但也表示**它平常不會示範自己還會動**。如果哪天有人把 `rglob("*.py")`
    寫成 `glob("*.py")`（只掃第一層）、或把集合相減的方向寫反，它會**安靜地
    變成一項永遠綠的檢查**，而測試總數不會少一項，CI 也不會有任何顏色改變。
    這一項就是把「它會紅」這件事本身變成一項會紅的測試。

    ⚠️ **刻意用 `tmp_path` 造一棵合成的樹，不碰真的 `app/`。**
    本專案已經在相依地圖那邊踩過一次：拿真的資料去驗一項檢查，環境的變動
    會讓它時紅時綠——**一項會自己閃爍的測試比沒有測試更糟**（v0.36 的教訓）。

    三個案例，對應三種寫錯的方式：
    1. 全部都載入了 → 沒有孤兒（不能誤報，否則沒人敢留著它）；
    2. 有一個沒載入 → 必須抓到，而且**要抓到巢狀目錄底下那一個**
       （這一格擋的就是 `rglob` 被寫成 `glob`）；
    3. 那個孤兒含 `@register(` → 必須多印那句提示（提示本身也會爛掉）。
    """
    root = tmp_path / "app"
    (root / "generator" / "ode").mkdir(parents=True)
    live_top = root / "main.py"
    live_nested = root / "generator" / "base.py"
    dead_nested = root / "generator" / "ode" / "forgotten.py"
    live_top.write_text("x = 1\n", encoding="utf-8")
    live_nested.write_text("y = 2\n", encoding="utf-8")
    dead_nested.write_text("z = 3\n", encoding="utf-8")

    everything = {live_top, live_nested, dead_nested}

    # 1. 全部載入 → 乾淨
    orphans, hint = _orphans_under(root, everything)
    assert orphans == [], f"沒有孤兒時不得報警，卻報了 {orphans}"
    assert hint == ""

    # 2. 巢狀目錄底下漏掉一個 → 必須抓到
    orphans, hint = _orphans_under(root, {live_top, live_nested})
    assert orphans == ["app/generator/ode/forgotten.py"], (
        f"巢狀目錄底下的孤兒沒被抓到（拿到 {orphans}）——"
        "⚠️ 最可能的原因是掃描只走了第一層。"
    )
    assert hint == "", "這個孤兒沒有 `@register(`，不該印那句提示"

    # 3. 孤兒是一個註冊不起來的題型 → 要多印那句提示
    dead_nested.write_text(
        '@register("ode.first_order.ghost", name="G", chapter="C")\n'
        "def gen(difficulty):\n    ...\n",
        encoding="utf-8",
    )
    orphans, hint = _orphans_under(root, {live_top, live_nested})
    assert orphans == ["app/generator/ode/forgotten.py"]
    assert "@register(" in hint and "__init__.py" in hint, (
        f"含 `@register(` 的孤兒沒有印出那句指路的提示（拿到 {hint!r}）"
    )
