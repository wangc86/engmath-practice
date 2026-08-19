"""展示區的 Web 流程與看守測試（PLAN.md §8，階段 2S）。

分成五組，每一組守的都是一件「壞掉的時候不會有人發現」的事：

1. **登入**——展示沿用既有登入（§7 #33）。
2. **`UsageLog`**——欄位零擴充、sentinel 不變量（§8.7）。
3. **個資告知**——告知必須涵蓋展示（§8.7「告知要改一行」）。
4. **HTMX 禁令**——展示頁內不得有 `hx-*` 屬性（§8.2）。
5. **不說的話**——不得出現評分字眼（D17）、中日韓字元（D5）、
   以及進度／時程措辭（D24）。

第 5 組全部是「頁面上**不該**有某樣東西」的測試。這類測試看起來很消極，
但它們守的正是本專案反覆遇到的那種缺陷：**少寫一句話不會讓任何東西壞掉，
所以沒有人會發現規則被違反了**（D13 的收合、D17 的沉默都是同一類）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from tests.test_web import CJK, REGISTER_FORM, client  # noqa: F401  沿用既有 fixture

DEMOS_STATIC = Path(__file__).resolve().parent.parent / "app" / "static" / "demos"

ALIASING_URL = "/demos/sampling/aliasing"
DEMO_PAGES = ("/demos", ALIASING_URL)


# --- 1. 登入 ----------------------------------------------------------------

@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_require_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_demo_index_lists_the_aliasing_demo(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.get("/demos")
    assert r.status_code == 200
    assert "Sampling and aliasing" in r.text
    assert f'href="{ALIASING_URL}"' in r.text


def test_unknown_demo_returns_404(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.get("/demos/sampling/nope")
    assert r.status_code == 404


def test_demos_link_is_reachable_from_the_header(client):
    """學生找得到它，否則等於沒做（§7 #34）。"""
    client.post("/register", data=REGISTER_FORM)
    assert 'href="/demos"' in client.get("/").text


def test_aliasing_page_has_the_controls_and_the_readouts(client):
    client.post("/register", data=REGISTER_FORM)
    html = client.get(ALIASING_URL).text

    # 每個值都有滑桿**和**數字輸入框（§8.6 第 1 點：不得有只能拖曳才能設定的值）
    for control in ('id="tone"', 'id="tone-number"', 'id="rate"', 'id="rate-number"'):
        assert control in html, f"缺少控制項 {control}"
    assert 'type="range"' in html and 'type="number"' in html

    # 讀數：f、fs、奈奎斯特、表觀頻率
    for readout in ("out-tone", "out-rate", "out-nyquist", "out-alias"):
        assert f'id="{readout}"' in html

    # a11y：狀態播報區與算出來的 canvas 描述（§8.6 第 2、3 點）
    assert 'aria-live="polite"' in html
    assert 'id="scope-description"' in html
    assert 'aria-describedby="scope-description"' in html

    # 音訊安全：明確的 Start 按鈕（autoplay 政策）＋ 靜音 ＋ 音量
    assert "Start sound" in html
    assert 'data-shell="mute"' in html
    assert 'data-shell="volume"' in html

    # ES module，且指向真的存在的檔案
    assert '<script type="module" src="/static/demos/aliasing.js">' in html


def test_what_you_just_heard_is_collapsed(client):
    """規則 5 的引申（§8 對 D13 那一列）：結論不先寫在畫面上。

    展示沒有「答案」，但它有一個等價的東西——如果標題就寫著
    「4 kHz 會摺到 2 kHz」，學生就不必去拉滑桿、也就不會嚇一跳，
    而那一跳正是這個展示唯一的教學價值。
    """
    client.post("/register", data=REGISTER_FORM)
    html = client.get(ALIASING_URL).text

    tags = re.findall(r"<details\b[^>]*>", html)
    assert len(tags) == 1, f"預期一個 details，實際 {len(tags)} 個"
    assert " open" not in tags[0], f"說明預設展開了：{tags[0]}"
    assert "<summary>What you just heard</summary>" in html


def test_demo_static_assets_are_served(client):
    """展示頁引用的每個 /static/ 檔案都要真的取得得到。

    ES module 的 import 是**在瀏覽器裡**才解析的，所以少一個檔案在伺服器端
    完全看不出來——頁面回 200、然後畫面一片空白。
    """
    client.post("/register", data=REGISTER_FORM)
    html = client.get(ALIASING_URL).text
    refs = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
    assert "/static/demos/aliasing.js" in refs
    assert "/static/demos/demos.css" in refs
    for ref in refs:
        r = client.get(ref)
        assert r.status_code == 200, f"{ref} 取不到（{r.status_code}）"
        assert len(r.content) > 0

    # aliasing.js 自己 import 的那幾支，以及 worklet
    for module in (
        "/static/demos/lib/signal.js", "/static/demos/lib/transform.js",
        "/static/demos/lib/draw.js", "/static/demos/lib/audio.js",
        "/static/demos/lib/shell.js",
        "/static/demos/worklets/sampler-processor.js",
    ):
        assert client.get(module).status_code == 200, f"{module} 取不到"


def test_every_import_in_the_demo_js_resolves(client):
    """把 `import ... from './x.js'` 逐一解析，確認檔案存在。

    這一項與上一項互補：上一項測「HTML 引用的」，這一項測「JS 互相引用的」。
    後者在伺服器端完全沒有痕跡。
    """
    client.post("/register", data=REGISTER_FORM)
    for source in DEMOS_STATIC.rglob("*.js"):
        text = source.read_text(encoding="utf-8")
        for target in re.findall(r"from\s+'([^']+)'", text):
            resolved = (source.parent / target).resolve()
            assert resolved.exists(), f"{source.name} import 不存在的 {target}"


GET_BY_ID = re.compile(r"getElementById\('([^']+)'\)")
DATA_SHELL = re.compile(r'data-shell="([a-z-]+)"')


def test_every_element_the_javascript_looks_up_exists_in_the_page(client):
    """JS 抓的每一個 id 與 data-shell 都必須真的在頁面上。

    這是這個功能區**最容易靜默失敗的一種方式**，而且伺服器端完全看不出來：
    改個 id、忘了改另一邊，頁面照樣回 200，但 module 在瀏覽器裡一載入就
    對 null 取屬性而中止——學生看到的是一個沒有反應的畫面，沒有任何訊息。
    在有瀏覽器測試（§8.4 方案 C，開學前的 `/demos/selftest`）之前，
    這一項是唯一擋得住它的東西。
    """
    client.post("/register", data=REGISTER_FORM)
    html = client.get(ALIASING_URL).text

    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (DEMOS_STATIC / "aliasing.js", *(DEMOS_STATIC / "lib").iterdir())
        if path.suffix == ".js"
    )
    ids = set(GET_BY_ID.findall(sources))
    assert ids, "沒有抓到任何 getElementById，這個測試大概失效了"
    for element_id in ids:
        assert f'id="{element_id}"' in html, f"JS 找 #{element_id}，頁面上沒有"

    for name in set(DATA_SHELL.findall(sources)):
        assert f'data-shell="{name}"' in html, f"JS 找 data-shell={name}，頁面上沒有"


# --- 2. UsageLog（§8.7）-----------------------------------------------------

def _logs(client):
    from app.db.models import UsageLog

    with Session(client.session_module.engine) as s:
        return s.exec(select(UsageLog)).all()


def test_opening_a_demo_writes_exactly_one_row(client):
    client.post("/register", data=REGISTER_FORM)
    client.get(ALIASING_URL)

    logs = _logs(client)
    assert len(logs) == 1
    log = logs[0]
    assert log.template_id == "demo.sampling.aliasing"
    assert log.action == "demo_open"
    assert log.difficulty == 0
    assert log.seed == 0
    assert log.student_id is not None
    assert log.created_at is not None


def test_the_index_page_is_not_logged(client):
    """只記「打開了哪個展示」（§8.7）。索引頁不是一個展示。"""
    client.post("/register", data=REGISTER_FORM)
    client.get("/demos")
    assert _logs(client) == []


def test_demo_usage_does_not_add_any_field(client):
    """規則 3：欄位不得擴充。展示沿用既有五欄，一個都不加。"""
    from app.db.models import UsageLog

    assert set(UsageLog.model_fields) == {
        "id", "student_id", "template_id", "difficulty",
        "seed", "action", "created_at",
    }
    from sqlmodel import SQLModel

    assert "demousagelog" not in set(SQLModel.metadata.tables), (
        "多了一張展示專用的表——那會擴大蒐集範圍，等於繞過規則 3（§8.7 (c)）"
    )


def test_sentinel_invariant_holds_across_both_kinds_of_row(client):
    """§8.7 的不變量測試，逐字照那一段寫。

    `difficulty` 與 `seed` 是非空整數，而展示沒有這兩個概念，所以寫 0。
    這**不是多存了資料**（0 不攜帶任何關於這個學生的資訊），但它是那種
    「約定寫在註解裡、三個月後沒有人記得」的東西——所以要有測試。
    """
    client.post("/register", data=REGISTER_FORM)
    client.get(ALIASING_URL)
    client.get(ALIASING_URL)
    client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.linear", "difficulty": 2},
    )

    logs = _logs(client)
    assert len(logs) == 3
    demo_rows = [log for log in logs if log.action.startswith("demo")]
    generate_rows = [log for log in logs if log.action == "generate"]
    assert len(demo_rows) == 2 and len(generate_rows) == 1

    for log in demo_rows:
        assert log.difficulty == 0, "展示的列不得帶難度"
        assert log.seed == 0, "展示的列不得帶題號"
        assert log.template_id.startswith("demo."), (
            "展示的 template_id 必須用 demo. 命名空間，否則兩個功能區分不開"
        )
    for log in generate_rows:
        assert 1 <= log.difficulty <= 3
        assert log.seed != 0
        assert not log.template_id.startswith("demo.")


def test_progress_page_shows_demo_usage(client):
    """學生有權看到系統存了什麼（§4.4 當事人權利、§8.7）。"""
    client.post("/register", data=REGISTER_FORM)
    client.get(ALIASING_URL)
    client.get(ALIASING_URL)

    r = client.get("/progress")
    assert r.status_code == 200
    assert "Demos opened" in r.text
    assert "Sampling and aliasing" in r.text
    assert "2" in r.text
    # 展示的次數不得混進出題的總數裡（兩個數字的分母不同）
    assert "not generated any problems yet" in r.text


def test_progress_page_shows_only_my_own_demo_usage(client):
    client.post("/register", data=REGISTER_FORM)
    client.get(ALIASING_URL)
    client.post("/logout")

    client.post("/register", data=dict(REGISTER_FORM, student_no="41047002"))
    r = client.get("/progress")
    assert "Demos opened" not in r.text, "看到了別人開過的展示"


# --- 3. 個資告知（§8.7「告知要改一行」）------------------------------------

def test_notice_covers_opening_a_demo(client):
    """告知窄於實際儲存與 §4.4 第 1 點的逐一對應不符。

    這一行**必須在展示的紀錄上線之前先改**，不是之後補——所以它有自己的
    一項測試，而不是只靠 `test_notice_matches_the_fields_actually_stored`
    的片語清單。
    """
    text = client.get("/register").text
    assert "interactive demo" in text
    # 既有的欄位片語一個都不能因為改寫而掉了
    for phrase in ("topic", "difficulty", "which problem you were given",
                   "and the time"):
        assert phrase in text


# --- 4. HTMX 禁令（§8.2）----------------------------------------------------

HX_ATTRIBUTE = re.compile(r"\shx-[a-z-]+\s*=")


@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_use_no_htmx_attributes(client, path):
    """⛔ 一次 `hx-swap` 會把 canvas 換掉，留下還在發聲的孤兒節點。

    症狀是「換頁之後還有聲音」或「圖不動了但沒有錯誤」——兩者都是規則 4
    最討厭的那種靜默失敗。HTMX 仍用於展示**之間**的導覽，所以
    `base.html` 載入 htmx.min.js 是允許的；被禁的是 `hx-*` 屬性。
    """
    client.post("/register", data=REGISTER_FORM)
    html = client.get(path).text
    found = HX_ATTRIBUTE.findall(html)
    assert not found, f"{path} 出現 HTMX 屬性：{found}"


def test_demo_javascript_does_not_touch_htmx(client):
    for source in DEMOS_STATIC.rglob("*.js"):
        text = source.read_text(encoding="utf-8").lower()
        assert "htmx" not in text, f"{source.name} 碰到了 htmx"


# --- 5. 不說的話 ------------------------------------------------------------

@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_say_nothing_about_grading(client, path):
    """D17：系統對評分保持沉默，正反皆然。"""
    client.post("/register", data=REGISTER_FORM)
    text = client.get(path).text.lower()
    assert "grading" not in text
    assert "grade" not in text


@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_contain_no_chinese(client, path):
    """D5：本課程全英語授課，介面不得出現中文。"""
    client.post("/register", data=REGISTER_FORM)
    found = sorted(set(CJK.findall(client.get(path).text)))
    assert not found, f"{path} 出現中文字元: {''.join(found)}"


# 把 // 與 /* */ 註解剝掉。這個剝法很樸素（不處理字串裡的 "//"），
# 對本目錄的程式碼夠用；有一天不夠用的時候，症狀是誤報而不是漏報，
# 那是這裡想要的方向。
LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def test_demo_javascript_strings_contain_no_chinese():
    """註解用繁體中文（開發文件語言），**字串常值一律英文**（D5）。

    這一項存在的理由：外部 .js 檔的內容不在頁面 HTML 裡，所以
    `test_demo_pages_contain_no_chinese` 掃不到它——而學生看到的錯誤訊息
    大半住在 `lib/audio.js` 裡。
    """
    offenders = {}
    for source in DEMOS_STATIC.rglob("*.js"):
        text = source.read_text(encoding="utf-8")
        stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))
        found = sorted(set(CJK.findall(stripped)))
        if found:
            offenders[source.name] = "".join(found)
    assert not offenders, f"註解以外的地方出現中文：{offenders}"


PROGRESS_WORDS = (
    "coming soon", "not yet available", "under construction",
    "in progress", "planned for", "will be added", "roadmap",
)


@pytest.mark.parametrize("path", DEMO_PAGES + ("/", "/progress"))
def test_pages_do_not_advertise_what_is_missing(client, path):
    """D24：不陳列目前有哪些功能、哪些待補，也不寫上線時程。

    誠實的義務是「不得寫假的」，不是「必須把進度攤開」。而一份手動維護的
    涵蓋範圍表會立刻開始腐化——每加一個題型就要記得回頭改一行，不改就變成
    頁面上一句假話。**會腐化的自述比沒有自述更不誠實**，這就是 D24。

    沉默同樣需要一個看守點，否則日後有人「順手補一句進度說明」不會有任何
    東西變紅（與 D17 的兩項沉默測試同一個理由）。
    """
    client.post("/register", data=REGISTER_FORM)
    text = client.get(path).text.lower()
    for word in PROGRESS_WORDS:
        assert word not in text, f"{path} 出現了進度／時程措辭：{word}"
