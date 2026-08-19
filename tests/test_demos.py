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

import math
import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from tests.test_web import CJK, REGISTER_FORM, client  # noqa: F401  沿用既有 fixture

DEMOS_STATIC = Path(__file__).resolve().parent.parent / "app" / "static" / "demos"

ALIASING_URL = "/demos/sampling/aliasing"
SPECTRUM_URL = "/demos/spectrum/leakage"
DEMO_PAGES = ("/demos", ALIASING_URL, SPECTRUM_URL)

#: 展示頁 → 它的進入點 JS。`test_every_element_the_javascript_looks_up_exists_in_the_page`
#: 逐頁檢查，因為 `lib/` 是共用的而進入點不是。
DEMO_ENTRY_POINTS = {
    ALIASING_URL: "aliasing.js",
    SPECTRUM_URL: "spectrum.js",
}


# --- 1. 登入 ----------------------------------------------------------------

@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_require_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_demo_index_lists_both_demos(client):
    client.post("/register", data=REGISTER_FORM)
    r = client.get("/demos")
    assert r.status_code == 200
    assert "Sampling and aliasing" in r.text
    assert "Spectrum, windows and leakage" in r.text
    for url in (ALIASING_URL, SPECTRUM_URL):
        assert f'href="{url}"' in r.text


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
    for url, summary in (
        (ALIASING_URL, "<summary>What you just heard</summary>"),
        (SPECTRUM_URL, "<summary>What you just saw</summary>"),
    ):
        html = client.get(url).text
        tags = re.findall(r"<details\b[^>]*>", html)
        assert len(tags) == 1, f"{url} 預期一個 details，實際 {len(tags)} 個"
        assert " open" not in tags[0], f"{url} 的說明預設展開了：{tags[0]}"
        assert summary in html


def test_demo_static_assets_are_served(client):
    """展示頁引用的每個 /static/ 檔案都要真的取得得到。

    ES module 的 import 是**在瀏覽器裡**才解析的，所以少一個檔案在伺服器端
    完全看不出來——頁面回 200、然後畫面一片空白。
    """
    client.post("/register", data=REGISTER_FORM)
    for url, entry in DEMO_ENTRY_POINTS.items():
        html = client.get(url).text
        refs = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
        assert f"/static/demos/{entry}" in refs
        assert "/static/demos/demos.css" in refs
        for ref in refs:
            r = client.get(ref)
            assert r.status_code == 200, f"{ref} 取不到（{r.status_code}）"
            assert len(r.content) > 0

    # JS 之間互相 import 的那幾支、worklet、以及 vendored 的 FFT
    for module in (
        "/static/demos/lib/signal.js", "/static/demos/lib/transform.js",
        "/static/demos/lib/draw.js", "/static/demos/lib/audio.js",
        "/static/demos/lib/shell.js",
        "/static/demos/worklets/sampler-processor.js",
        "/static/vendor/fftjs/fft.js",
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
    for url, entry in DEMO_ENTRY_POINTS.items():
        html = client.get(url).text
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (DEMOS_STATIC / entry, *(DEMOS_STATIC / "lib").iterdir())
            if path.suffix == ".js"
        )
        ids = set(GET_BY_ID.findall(sources))
        assert ids, f"{entry} 沒有抓到任何 getElementById，這個測試大概失效了"
        for element_id in ids:
            assert f'id="{element_id}"' in html, f"{entry} 找 #{element_id}，{url} 上沒有"

        for name in set(DATA_SHELL.findall(sources)):
            assert f'data-shell="{name}"' in html, (
                f"{entry} 找 data-shell={name}，{url} 上沒有"
            )


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


# ============================================================================
# 6. 頻譜展示（2S4）與**檔案不得外流**（D28）
#
# 這一整組是 D28 的正當性所在。老師的決定推翻了 D20（不開放上傳），
# 而推翻的前提是一句很具體的話：**檔案完全在瀏覽器端處理，絕不上傳**。
# 個資風險來自「檔案送到伺服器」，不是來自「使用者選了一個檔案」——
# 因此這個區分必須由測試強制，不能只寫在文件裡。
#
# 從兩個方向夾：**前端沒有送出的手段**，**後端沒有接收的地方**。
# ============================================================================

def test_the_spectrum_page_has_its_controls_and_readouts(client):
    client.post("/register", data=REGISTER_FORM)
    html = client.get(SPECTRUM_URL).text

    # 值都有滑桿**和**數字輸入框（§8.6 第 1 點）
    for control in ('id="tone"', 'id="tone-number"'):
        assert control in html
    # 這一頁的四個變因
    for control in ("fft-size", "window", "zero-pad", "fmax", "db-axis"):
        assert f'id="{control}"' in html, f"缺少控制項 {control}"
    # 四個視窗都要在選單裡，否則「切視窗比較旁瓣」這一格就不存在
    for window in ("Rectangular", "Hann", "Hamming", "Blackman"):
        assert window in html
    for readout in ("out-fs", "out-n", "out-time", "out-spacing", "out-peak", "out-offset"):
        assert f'id="{readout}"' in html

    # a11y：播報區 + 兩張圖各自算出來的描述（§8.6 第 2、3 點）
    assert 'aria-live="polite"' in html
    for description in ("waveform-description", "spectrum-description",
                        "spectrogram-description"):
        assert f'id="{description}"' in html
        assert f'aria-describedby="{description}"' in html
    assert '<script type="module" src="/static/demos/spectrum.js">' in html


def test_the_built_in_samples_are_listed_and_served(client):
    """內建範例（D29）：選單列得出來，而且每一個都真的取得到。"""
    from app.routes import demos as demos_module

    client.post("/register", data=REGISTER_FORM)
    html = client.get(SPECTRUM_URL).text
    assert demos_module.SAMPLES, "沒有任何內建範例，那個選單會是空的"
    for sample in demos_module.SAMPLES:
        assert f'value="{sample.file}"' in html
        assert sample.label in html
        r = client.get(f"/static/demos/samples/{sample.file}")
        assert r.status_code == 200, f"{sample.file} 取不到"
        assert r.content[:4] == b"RIFF", f"{sample.file} 不是 wav"


SAMPLES_DIR = DEMOS_STATIC / "samples"


def _read_wav(name):
    """把 wav 讀成 (取樣率, [-1,1] 的 float list)。標準函式庫就夠了。"""
    import struct
    import wave

    with wave.open(str(SAMPLES_DIR / name), "rb") as handle:
        assert handle.getnchannels() == 1, f"{name} 不是單聲道"
        assert handle.getsampwidth() == 2, f"{name} 不是 16-bit"
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    values = struct.unpack(f"<{len(raw) // 2}h", raw)
    return rate, [v / 32768.0 for v in values]


def _amplitude_at(name, frequency):
    """在**單一頻率**上求 DFT，回傳訊號在那個頻率上的振幅。

    這是 DFT 定義本身，只是不掃過所有 k、只算我們關心的那一個：

        A(f) = 2 · |Σ_n w[n]·x[n]·exp(-2πi f n / f_s)| / (N · 相干增益)

    **為什麼不算整條頻譜**：這幾項測試問的問題是「220 Hz 的方波裡到底有沒有
    第 2 次諧波」，而那是一個關於**特定頻率**的問題。直接在那個頻率上求值，
    每次只要 O(N)，而且這 5 行可以逐字與定義核對——比先算一整條頻譜、
    再從裡面找峰、再判斷峰算不算峰，少掉兩層可能出錯的判斷。

    Hann 窗是必要的：檔案的長度不見得讓每個頻率都落在 bin 中心，
    不加窗的話洩漏會讓「不存在的諧波」看起來有一點點值（見同一頁的教學內容）。
    """
    import cmath

    rate, samples = _read_wav(name)
    n = len(samples)
    acc = 0j
    for i in range(n):
        window = 0.5 - 0.5 * math.cos(2 * math.pi * i / n)
        acc += samples[i] * window * cmath.exp(-2j * math.pi * frequency * i / rate)
    return 2 * abs(acc) / (n * 0.5)


def test_the_pure_tone_sample_really_is_one_line_at_440_hz():
    """內建範例的內容必須與它的標籤相符。

    這一組測試存在的理由與 D13 的收合測試相同：**標錯了不會有任何東西壞掉**
    ——頁面照樣跑、圖照樣畫，只是那個標著「Pure sine at 440 Hz」的選項
    其實是別的東西，而學生會相信標籤。
    """
    rate, _ = _read_wav("tone-440.wav")
    assert rate == 22050
    fundamental = _amplitude_at("tone-440.wav", 440)
    assert fundamental > 0.4, "440 Hz 上幾乎沒有東西"
    for other in (220, 880, 1320, 1760):
        assert _amplitude_at("tone-440.wav", other) < 0.01 * fundamental, (
            f"純正弦在 {other} Hz 上不該有可觀的成分"
        )


def test_the_square_wave_sample_has_only_odd_harmonics():
    """方波：奇次諧波振幅約 1/n，偶次諧波應該幾乎是零。"""
    name = "square-220.wav"
    fundamental = _amplitude_at(name, 220)
    assert fundamental > 0.2
    for order in (3, 5, 7, 9):
        got = _amplitude_at(name, 220 * order) / fundamental
        assert got == pytest.approx(1 / order, rel=0.05), f"第 {order} 次諧波"
    for order in (2, 4, 6, 8):
        assert _amplitude_at(name, 220 * order) < 0.01 * fundamental, (
            f"方波不該有第 {order} 次諧波"
        )


def test_the_sawtooth_sample_has_every_harmonic():
    """鋸齒波：每一次諧波都在，振幅同樣約 1/n。這與方波的唯一差別就是偶次。"""
    name = "sawtooth-220.wav"
    fundamental = _amplitude_at(name, 220)
    assert fundamental > 0.2
    for order in (2, 3, 4, 5, 6, 7):
        got = _amplitude_at(name, 220 * order) / fundamental
        assert got == pytest.approx(1 / order, rel=0.05), f"第 {order} 次諧波"


def test_the_two_tone_sample_really_has_two_tones_twelve_hertz_apart():
    """解析度展示的主角：440 Hz 與 452 Hz 兩個等強度的成分。

    12 Hz 這個間距是刻意的——22.05 kHz 之下，N = 1024 的格距是 21.5 Hz
    （分不開）、N = 2048 是 10.8 Hz（勉強）、N = 4096 是 5.4 Hz（分得開）。
    學生在頁面上拉 N 的時候，兩個峰就是在這三格之間長出來的。
    """
    name = "two-tones-440-452.wav"
    low = _amplitude_at(name, 440)
    high = _amplitude_at(name, 452)
    assert low > 0.2 and high > 0.2
    assert low == pytest.approx(high, rel=0.05), "兩個成分應該等強度"
    for absent in (300, 446 - 40, 600, 880):
        assert _amplitude_at(name, absent) < 0.05 * low


def test_no_sample_is_silent_or_clipped():
    """全部六個：不是靜音、也沒有削波。兩者都是「檔案壞了但頁面照跑」。"""
    for path in sorted(SAMPLES_DIR.glob("*.wav")):
        rate, samples = _read_wav(path.name)
        assert rate == 22050, f"{path.name} 的取樣率是 {rate}"
        peak = max(abs(v) for v in samples)
        assert peak > 0.05, f"{path.name} 幾乎是靜音（峰值 {peak:.3f}）"
        assert peak < 0.999, f"{path.name} 削波了（峰值 {peak:.3f}）"


def test_the_speech_sample_is_a_few_seconds_of_something_that_varies():
    """語音那一段（D29）：長度合理，而且**不是一個穩定的音**。

    無法在測試裡斷言「它說了什麼」，所以斷言一件可驗證的替代性質：
    語音的短時能量會起伏（有音節、有停頓），純音與雜訊都不會。
    """
    rate, samples = _read_wav("speech-welcome.wav")
    seconds = len(samples) / rate
    assert 3 < seconds < 15, f"語音長度 {seconds:.1f} 秒不像那一句話"

    frame = rate // 20                       # 50 ms 一格
    energies = [
        sum(v * v for v in samples[i:i + frame]) / frame
        for i in range(0, len(samples) - frame, frame)
    ]
    loud = max(energies)
    quiet = sorted(energies)[len(energies) // 10]
    assert loud > 20 * quiet, "能量幾乎沒有起伏，這聽起來不像一句話"


# --- D28：前端沒有把檔案送出去的手段 ----------------------------------------

#: 任何一個都足以把資料送出瀏覽器。展示區的 JS 一個都不准出現。
UPLOAD_PRIMITIVES = (
    "FormData", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource",
    "navigator.clipboard", "createObjectURL", "requestFileSystem",
)


def test_the_demo_javascript_has_no_way_to_send_anything_out():
    """⛔ D28 的第一半：**前端連送出的原語都沒有引用**。

    這比「檢查有沒有 POST」強：連 `FormData` 都不出現的話，
    要加上傳就得先加一個新的識別字，而那會讓這一項測試變紅。
    """
    offenders = {}
    for source in DEMOS_STATIC.rglob("*.js"):
        text = source.read_text(encoding="utf-8")
        # 註解要先剝掉：這幾個名字**本來就會出現在說明為什麼不用它們的註解裡**
        # （signal.js 開頭那一段就是），而那不是違規，是文件。
        stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))
        found = [name for name in UPLOAD_PRIMITIVES if name in stripped]
        if found:
            offenders[source.name] = found
    assert not offenders, f"展示的 JS 出現了可以送出資料的原語：{offenders}"


FETCH_CALL = re.compile(r"fetch\s*\(([^;]*?)\)\s*;")


def test_every_fetch_in_the_demo_javascript_is_a_plain_get_of_a_static_asset():
    """⛔ D28 的第二半：唯一允許的 fetch 是「下載一個 /static/ 的資產」。

    判準有兩條，都很粗暴而且刻意如此：
      * 呼叫裡不得出現 `method:` 或 `body:`（有了就不是單純的 GET）
      * URL 必須看得出來是 `/static/` 底下的東西

    粗暴的代價是誤報（日後某個合法的 fetch 被擋下來），而誤報的處理方式是
    「回來看一眼、確認它真的只是下載、再放行」——那正是我們希望發生的事。
    """
    for source in DEMOS_STATIC.rglob("*.js"):
        text = source.read_text(encoding="utf-8")
        stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))
        for call in FETCH_CALL.findall(stripped):
            assert "method" not in call and "body" not in call, (
                f"{source.name} 的 fetch 帶了 method／body：{call.strip()}"
            )
            assert "/static/" in call or "SAMPLE_PREFIX" in call, (
                f"{source.name} 的 fetch 目標不明：{call.strip()}"
            )


def test_the_file_input_is_not_inside_a_form(client):
    """檔案選擇器不在任何 <form> 裡——所以「不小心送出去」在結構上做不到。"""
    client.post("/register", data=REGISTER_FORM)
    html = client.get(SPECTRUM_URL).text
    assert 'type="file"' in html

    # 把每一組 <form>…</form> 挖出來，確認裡面沒有 file input。
    for form in re.findall(r"<form\b.*?</form>", html, re.S):
        assert 'type="file"' not in form, "檔案選擇器被放進了一個 form"
    # 頁面上唯一的 form 是 base.html 的登出按鈕。
    assert html.count("<form") == 1


def test_the_page_says_out_loud_that_the_file_stays_local(client):
    """個資面的承諾必須寫在學生看得到的地方，不是只寫在 PLAN 裡。"""
    client.post("/register", data=REGISTER_FORM)
    html = client.get(SPECTRUM_URL).text
    assert "never leaves this computer" in html


# --- D28：後端沒有接收的地方 -------------------------------------------------

def test_the_demo_routes_accept_nothing_but_get():
    """⛔ 展示區的路由**只有 GET**。"""
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/demos"):
            continue
        assert set(getattr(route, "methods", set())) <= {"GET", "HEAD"}, (
            f"{path} 接受 {route.methods}，展示區只該有 GET"
        )


def test_the_whole_application_has_no_file_upload_endpoint():
    """整個 `app/` 都不 import `UploadFile`／`File`——伺服器根本收不了檔案。

    這一項刻意掃**整個應用程式**而不只是 `app/routes/demos.py`：
    D28 的承諾是「檔案不會到伺服器上」，而承諾的範圍是這個伺服器，
    不是某一個檔案。
    """
    app_dir = Path(__file__).resolve().parent.parent / "app"
    offenders = {}
    for source in app_dir.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        stripped = re.sub(r'"""ature.*?"""', "", text, flags=re.S)
        for name in ("UploadFile", "File(", "multipart/form-data"):
            if name in stripped:
                offenders.setdefault(source.name, []).append(name)
    assert not offenders, f"伺服器端出現了收檔案的東西：{offenders}"


# --- vendored FFT 的完整性（2S1、D31）---------------------------------------

VENDOR_FFT = Path(__file__).resolve().parent.parent / "app" / "static" / "vendor" / "fftjs"

#: `fft.js` 4.0.4 的 `lib/fft.js`，只改了 `module.exports` 那一行之後的 sha256。
#: 產生方式與上游 sha256 都寫在該檔的標頭裡。
VENDORED_BODY_SHA256 = "f7036b3e8f9df2a5f694418200b9b9413fe372d4a8512456d92ec9cf2b444df9"
VENDOR_MARKER = "// --- vendored source begins ---\n"


def test_the_vendored_fft_is_the_upstream_file_with_exactly_one_line_changed():
    """⛔ 沒有人可以「順手改一下」vendored 的程式碼。

    §8.3 選 vendored 而不是自己寫，理由是「一支安靜地錯掉的 FFT 會產生
    看起來合理的頻譜」。那個理由只在**它真的是上游那份**的前提下成立——
    改過一行之後它就是我們自己的程式碼了，而我們對它沒有上游那樣的信心。
    所以這裡把它釘死。
    """
    import hashlib

    text = (VENDOR_FFT / "fft.js").read_text(encoding="utf-8")
    assert VENDOR_MARKER in text, "vendored 檔案的標頭標記不見了"
    body = text.split(VENDOR_MARKER, 1)[1]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == VENDORED_BODY_SHA256, (
        "vendored 的 fft.js 被改過了。若這是一次升級，請更新這裡的 sha256 "
        "並在該檔標頭記下新的上游版本與改動；若不是，請還原它。"
    )
    assert "export default FFT;" in body
    # 只看行首：`module.exports` 這幾個字仍然出現在那一行的 EDIT 註解裡，
    # 而那正是我們**希望**它留著的東西（它記錄了改掉的是哪一行）。
    assert re.search(r"^module\.exports", body, re.M) is None, (
        "CommonJS 的那一行在瀏覽器裡會爆"
    )


def test_the_vendored_fft_ships_its_licence():
    """授權全文必須附得出來（§7 #32 的三個條件之一）。"""
    licence = (VENDOR_FFT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in licence
    assert "Copyright Fedor Indutny" in licence
    assert "WITHOUT WARRANTY OF ANY KIND" in licence
