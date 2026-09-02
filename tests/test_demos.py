"""展示區的 Web 流程與看守測試（PLAN.md §8，階段 2S）。

分成三組，每一組守的都是一件「壞掉的時候不會有人發現」的事：

1. **HTMX 禁令**——展示頁內不得有 `hx-*` 屬性（§8.2）。
2. **不說的話**——不得出現評分字眼（D17）、中日韓字元（D5）、
   以及進度／時程措辭（D24）。
3. **數值與版面**——每個展示頁的控制項、讀數、範例音檔與 JS 進入點。

⚠️ **v0.29（D57、D58）少了兩組，而它們是失去標的、不是被放寬**：
「登入」（展示沿用既有登入，§7 #33）與「`UsageLog`」（欄位零擴充、
sentinel 不變量，§8.7）——系統改為本機執行之後沒有帳號、也沒有資料庫。
`test_the_honest_note_covers_opening_a_demo` 也一併移除：登入頁沒有了，
而它守的那句話搬到 `base.html` 的頁尾，由
`tests/test_web.py::test_the_footer_promise_is_true_no_outbound_url_in_any_page`
用一個更強的方式守著——**不是檢查那句話還在，是檢查那句話是真的**。

第 5 組全部是「頁面上**不該**有某樣東西」的測試。這類測試看起來很消極，
但它們守的正是本專案反覆遇到的那種缺陷：**少寫一句話不會讓任何東西壞掉，
所以沒有人會發現規則被違反了**（D13 的收合、D17 的沉默都是同一類）。
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from tests.test_web import CJK, client  # noqa: F401  沿用既有 fixture

DEMOS_STATIC = Path(__file__).resolve().parent.parent / "app" / "static" / "demos"

ALIASING_URL = "/demos/sampling/aliasing"
SPECTRUM_URL = "/demos/spectrum/leakage"
FOURIER_URL = "/demos/fourier/series"
CONVOLUTION_URL = "/demos/lti/convolution"
PULSE_URL = "/demos/transform/pulse"
POLEZERO_URL = "/demos/filter/pole-zero"
DEMO_PAGES = (
    "/demos", ALIASING_URL, SPECTRUM_URL, FOURIER_URL, CONVOLUTION_URL, PULSE_URL,
    POLEZERO_URL,
)

#: 展示頁 → 它的進入點 JS。`test_every_element_the_javascript_looks_up_exists_in_the_page`
#: 逐頁檢查，因為 `lib/` 是共用的而進入點不是。
DEMO_ENTRY_POINTS = {
    ALIASING_URL: "aliasing.js",
    SPECTRUM_URL: "spectrum.js",
    FOURIER_URL: "fourier.js",
    CONVOLUTION_URL: "convolution.js",
    PULSE_URL: "pulse.js",
    POLEZERO_URL: "polezero.js",
}


# --- 0. 路由與索引頁 --------------------------------------------------------

def test_unknown_demo_returns_404(client):
    r = client.get("/demos/sampling/nope")
    assert r.status_code == 404


def test_demos_link_is_reachable_from_the_header(client):
    """使用者找得到它，否則等於沒做（§7 #34）。"""
    assert 'href="/demos"' in client.get("/").text


def test_demo_index_lists_every_demo_grouped_by_week(client):
    """索引頁必須列出**每一個**展示，而且依課程週次分組（D59）。

    ⚠️ 清單從 `DEMOS` 讀，不是手寫幾個標題：手寫的版本在新增第七個展示時
    不會變紅，而「新展示自動出現在索引上」正是這一項要守的事。
    """
    from app.curriculum import KIND_DEMO, item_for, weeks_with_content
    from app.routes.demos import DEMOS

    html = client.get("/demos").text
    assert html.count("demo-index-item") == len(DEMOS)
    for demo in DEMOS:
        assert demo.title in html, f"索引頁缺 {demo.title}"
        assert f'href="/demos/{demo.slug}"' in html

    for week in weeks_with_content(KIND_DEMO):
        assert f"Week {week.number} — {week.topic}" in html

    # 每一個展示都要落在它自己那一週的標題底下（不是隨便一個標題底下）
    for demo in DEMOS:
        item = item_for(demo.template_id)
        heading = html.index(f"Week {item.primary_week} — ")
        assert html.index(f'href="/demos/{demo.slug}"') > heading, (
            f"{demo.slug} 排在第 {item.primary_week} 週的標題前面"
        )


def test_aliasing_page_has_the_controls_and_the_readouts(client):
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


#: 展示頁 → (該頁預期有幾個 <details>, 必須出現的 summary 文字)。
#:
#: 數量寫死是刻意的：**多長出一個沒有人審過的收合區，這一項就要變紅**。
#: 加法合成頁有兩個（「剛才聽到了什麼」與「係數怎麼來的」），
#: 那是 2S5 特意加的第二層，不是不小心多出來的。
REVEALS = {
    ALIASING_URL: (1, ["<summary>What you just heard</summary>"]),
    SPECTRUM_URL: (1, ["<summary>What you just saw</summary>"]),
    FOURIER_URL: (2, [
        "<summary>What you just heard</summary>",
        "<summary>Where the coefficients come from</summary>",
    ]),
    CONVOLUTION_URL: (2, [
        "<summary>What you just heard</summary>",
        "<summary>Where the convolution sum comes from</summary>",
    ]),
    PULSE_URL: (2, [
        "<summary>What you just saw</summary>",
        "<summary>Where the numbers come from</summary>",
    ]),
}


def test_what_you_just_heard_is_collapsed(client):
    """規則 5 的引申（§8 對 D13 那一列）：結論不先寫在畫面上。

    展示沒有「答案」，但它有一個等價的東西——如果標題就寫著
    「4 kHz 會摺到 2 kHz」，學生就不必去拉滑桿、也就不會嚇一跳，
    而那一跳正是這個展示唯一的教學價值。

    加法合成頁（2S5）尤其如此：那一頁的兩句話——「改相位音色不變」與
    「過衝不會隨項數消失」——是它**唯二**值得學生自己動手發現的東西。
    """
    for url, (count, summaries) in REVEALS.items():
        html = client.get(url).text
        tags = re.findall(r"<details\b[^>]*>", html)
        assert len(tags) == count, f"{url} 預期 {count} 個 details，實際 {len(tags)} 個"
        for tag in tags:
            assert " open" not in tag, f"{url} 有一個說明預設展開了：{tag}"
        for summary in summaries:
            assert summary in html


def test_demo_static_assets_are_served(client):
    """展示頁引用的每個 /static/ 檔案都要真的取得得到。

    ES module 的 import 是**在瀏覽器裡**才解析的，所以少一個檔案在伺服器端
    完全看不出來——頁面回 200、然後畫面一片空白。
    """
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


# --- 1. HTMX 禁令（§8.2）----------------------------------------------------

HX_ATTRIBUTE = re.compile(r"\shx-[a-z-]+\s*=")


@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_use_no_htmx_attributes(client, path):
    """⛔ 一次 `hx-swap` 會把 canvas 換掉，留下還在發聲的孤兒節點。

    症狀是「換頁之後還有聲音」或「圖不動了但沒有錯誤」——兩者都是規則 4
    最討厭的那種靜默失敗。HTMX 仍用於展示**之間**的導覽，所以
    `base.html` 載入 htmx.min.js 是允許的；被禁的是 `hx-*` 屬性。
    """
    html = client.get(path).text
    found = HX_ATTRIBUTE.findall(html)
    assert not found, f"{path} 出現 HTMX 屬性：{found}"


def test_demo_javascript_does_not_touch_htmx(client):
    for source in DEMOS_STATIC.rglob("*.js"):
        text = source.read_text(encoding="utf-8").lower()
        assert "htmx" not in text, f"{source.name} 碰到了 htmx"


# --- 2. 不說的話 ------------------------------------------------------------

@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_say_nothing_about_grading(client, path):
    """D17：系統對評分保持沉默，正反皆然。"""
    text = client.get(path).text.lower()
    assert "grading" not in text
    assert "grade" not in text


@pytest.mark.parametrize("path", DEMO_PAGES)
def test_demo_pages_contain_no_chinese(client, path):
    """D5：本課程全英語授課，介面不得出現中文。"""
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


@pytest.mark.parametrize("path", DEMO_PAGES + ("/", "/login"))
def test_pages_do_not_advertise_what_is_missing(client, path):
    """D24：不陳列目前有哪些功能、哪些待補，也不寫上線時程。

    誠實的義務是「不得寫假的」，不是「必須把進度攤開」。而一份手動維護的
    涵蓋範圍表會立刻開始腐化——每加一個題型就要記得回頭改一行，不改就變成
    頁面上一句假話。**會腐化的自述比沒有自述更不誠實**，這就是 D24。

    沉默同樣需要一個看守點，否則日後有人「順手補一句進度說明」不會有任何
    東西變紅（與 D17 的兩項沉默測試同一個理由）。
    """
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
    html = client.get(SPECTRUM_URL).text
    assert 'type="file"' in html

    # 把每一組 <form>…</form> 挖出來，確認裡面沒有 file input。
    for form in re.findall(r"<form\b.*?</form>", html, re.S):
        assert 'type="file"' not in form, "檔案選擇器被放進了一個 form"
    # ⚠️ v0.29（D57）：這一行從 `== 1` 變成 `== 0`，而它**變強了**。
    # 那個「唯一的 form」是 base.html 的登出按鈕，而登入整套已經移除——
    # 現在展示頁上一個 `<form>` 都沒有，所以「不小心送出去」連一個
    # 可以掛上去的元素都不存在。
    assert html.count("<form") == 0


def test_the_page_says_out_loud_that_the_file_stays_local(client):
    """個資面的承諾必須寫在學生看得到的地方，不是只寫在 PLAN 裡。"""
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


# ============================================================================
# 7. 加法合成展示（2S5）
#
# 這一組守的是「頁面上必須有的東西」與「頁面上必須說出口的話」。
# 數值本身不在這裡驗——那是 `tests/test_dsp_js.py` 的 74 項，
# 參考值由 SymPy 對定義式積分算出來。
# ============================================================================

def test_the_fourier_page_has_its_controls_and_readouts(client):
    html = client.get(FOURIER_URL).text

    # 每個值都有滑桿**和**數字輸入框（§8.6 第 1 點：不得有只能拖曳才能設定的值）
    for control in (
        "terms", "terms-number", "f0", "f0-number",
        "phase-harmonic", "phase-harmonic-number",
        "phase-offset", "phase-offset-number",
    ):
        assert f'id="{control}"' in html, f"缺少控制項 {control}"
    for control in ("waveform", "phase-mode", "reshuffle", "phase-clear", "show-harmonics"):
        assert f'id="{control}"' in html, f"缺少控制項 {control}"

    # 四個目標波形都要在選單裡，否則「1/n 對 1/n²」那一格的對照就不存在
    for value in ("square", "sawtooth", "triangle", "halfWave"):
        assert f'value="{value}"' in html, f"選單少了 {value}"

    for readout in ("out-f0", "out-terms", "out-decay", "out-overshoot",
                    "out-width", "out-band-limit"):
        assert f'id="{readout}"' in html

    # a11y：播報區 + 三張圖各自算出來的描述（§8.6 第 2、3 點）
    assert 'aria-live="polite"' in html
    for description in ("sum-description", "coefficients-description",
                        "decomposition-description"):
        assert f'id="{description}"' in html
        assert f'aria-describedby="{description}"' in html

    # 音訊安全：明確的 Start 按鈕（autoplay 政策）＋ 靜音 ＋ 音量
    assert "Start sound" in html
    assert 'data-shell="mute"' in html
    assert 'data-shell="volume"' in html
    assert '<script type="module" src="/static/demos/fourier.js">' in html


def test_the_fourier_page_can_adjust_a_single_harmonic_without_dragging(client):
    """§8.6 第 1 點在這一頁的具體形式。

    「改一個諧波的相位」是這個展示最有說服力的操作，而它若只能用滑桿拖，
    對鍵盤使用者與螢幕閱讀器使用者就等於不存在。兩個數字輸入框
    （選哪一個諧波、轉幾度）讓那條教學路徑走得完。
    """
    html = client.get(FOURIER_URL).text
    assert 'id="phase-harmonic-number"' in html and 'type="number"' in html
    assert 'aria-label="Which harmonic to turn"' in html
    assert 'aria-label="Phase offset in degrees"' in html


def test_the_gibbs_table_has_all_three_columns(client):
    """對照表的三欄必須都在。

    誤解正是由這三個數字的**不同步**構成的：高度幾乎不動、寬度每次減半、
    最大差距在有跳點時根本不下降。少任何一欄，這張表就有別的讀法——
    只留高度會讀成「什麼都沒改善」，只留寬度會讀成「所以還是收斂了」。
    """
    html = client.get(FOURIER_URL).text
    assert 'id="gibbs-rows"' in html
    assert 'id="gibbs-caption"' in html
    for header in (
        "Harmonics up to n",
        "Overshoot, as a share of the step",
        "Distance from the step to the highest point",
        "Largest gap from the target, anywhere",
    ):
        assert header in html, f"對照表少了「{header}」那一欄"


def test_the_fourier_page_says_out_loud_what_it_cannot_play(client):
    """兩個有意義的降級都必須寫在畫面上（規則 4）。

    1. **帶限**：目標波形聽到的是一個兩百項的部分和，不是理想波形。
    2. **直流**：半波整流的 a₀/2 看得到、聽不到（Web Audio 的合成式
       由 k = 1 開始）。

    兩者都不是 bug，但兩者若不說出口，學生看到的就是「畫面與聲音對不上」
    ——而他會相信自己聽到的，然後把一個錯誤的結論帶走。
    """
    html = client.get(FOURIER_URL).text
    assert "Nyquist" in html, "沒有提到帶限這件事"
    assert "cannot hear" in html or "cannot represent" in html
    assert "constant is not a sound" in html


def test_the_fourier_page_does_not_give_away_the_two_surprises(client):
    """規則 5 的分寸：兩個結論都不得出現在收合區**之外**。

    「相位改了音色不變」與「過衝不會消失」是這一頁唯二的教學價值，
    而它們一旦寫在標題或說明裡，學生就不會去動那兩個控制項。
    做法：把 <details> 整段挖掉之後，剩下的部分不得出現那幾個關鍵詞。
    """
    html = client.get(FOURIER_URL).text
    visible = re.sub(r"<details\b.*?</details>", "", html, flags=re.S)
    for phrase in ("Gibbs", "8.95", "sound the same", "does not change what you hear"):
        assert phrase not in visible, f"結論「{phrase}」直接寫在畫面上了"


def test_the_fourier_page_has_no_form_at_all(client):
    """這一頁不收任何輸入，所以整頁只該有 base.html 的登出那一個 form。

    與 D28 那一組同一個精神：**沒有結構就沒有風險**。這一頁本來就沒有
    檔案選擇器，而這一項擋的是日後有人「順手加一個儲存設定的表單」。
    """
    html = client.get(FOURIER_URL).text
    assert 'type="file"' not in html
    # ⚠️ v0.29（D57）：base.html 的登出表單隨帳號一起移除，所以現在是 0。
    assert html.count("<form") == 0


# ============================================================================
# 8. 冒煙測試：把展示的 JS 真的跑一遍（2S5 新增）
#
# §8.9 連續兩輪都把同一句話寫在「必須誠實說出來的事」的第一條：
# **瀏覽器裡沒有實際跑過**。那一類錯誤（module 一載入就對 null 取屬性、
# 或 `render()` 第一次跑就丟例外）的症狀是「一個沒有反應的畫面」，
# 而伺服器回 200、上面所有測試全綠。
#
# `scripts/run_demo_smoke.mjs` 在 node 裡搭一個很小的假 DOM，
# 從**真的範本檔**讀出每個控制項的初始值，把整支 `<demo>.js` 載入、
# 畫一次、再撥動幾個控制項。
#
# ⚠️ **它不是瀏覽器，也不是 `/demos/selftest` 的替代品**（2S7 仍然欠著）：
# 它不畫像素、沒有 AudioContext、沒有版面計算。它擋的是很窄的一件事，
# 而那件事在此之前完全沒有東西擋。
# ============================================================================

import shutil
import subprocess

SMOKE_RUNNER = Path(__file__).resolve().parent.parent / "scripts" / "run_demo_smoke.mjs"
NODE = shutil.which("node")

_SMOKE_SKIP = (
    "找不到 node，因此展示 JS 的冒煙測試無法執行。這不是通過，是沒有跑。"
    "請安裝 Node.js（開發期相依，部署不需要）後重跑。"
)


def run_smoke(name):
    result = subprocess.run(
        [NODE, str(SMOKE_RUNNER), name],
        capture_output=True, text=True, timeout=120,
        cwd=SMOKE_RUNNER.parent.parent,
    )
    assert result.returncode == 0, (
        f"{name}.js 在假 DOM 裡跑不起來（returncode={result.returncode}）。\n"
        "這正是這一項存在的理由：伺服器端看不出來，學生會看到一個沒有反應的畫面。\n"
        f"{result.stderr}"
    )
    import json

    return json.loads(result.stdout)


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
@pytest.mark.parametrize(
    "name", ["aliasing", "spectrum", "fourier", "convolution", "pulse"],
)
def test_the_demo_module_loads_and_renders_without_throwing(name):
    """三個展示都要能載入、畫一次、並吃得下一串控制項操作。"""
    data = run_smoke(name)
    assert data["consoleErrors"] == [], f"{name}.js 在載入或重繪時寫了 console.error"
    assert data["frames"] > 0, "一格都沒有畫"
    missing = [step for step in data["interactions"] if step.startswith("missing:")]
    assert not missing, f"{name}.js 綁的控制項在範本裡不存在：{missing}"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
@pytest.mark.parametrize("name", ["aliasing", "fourier", "convolution", "pulse"])
def test_rendering_actually_puts_something_on_the_canvas(name):
    """`render()` 不得安靜地什麼都不畫。

    只驗「有沒有下過繪圖指令」，不驗任何幾何——幾何由
    `tests/test_dsp_js.py` 對 `draw.js` 的純函式半邊斷言
    （§8.4：斷言資料，不斷言像素）。

    頻譜展示不在這一項裡，而那是**正確的行為**：它的畫面完全來自
    `AnalyserNode` 的樣本，音訊沒開就沒有樣本，於是它清空畫布後就返回。
    """
    calls = run_smoke(name)["drawCalls"]
    assert calls.get("clearRect", 0) > 0
    assert calls.get("stroke", 0) > 10, f"{name} 幾乎沒有畫任何線"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
@pytest.mark.parametrize(
    "name", ["aliasing", "spectrum", "fourier", "convolution", "pulse"],
)
def test_no_web_audio_leaves_a_message_on_the_screen(name):
    """規則 4：三種音訊失敗都不得只寫 console。

    假 DOM 裡刻意沒有 `window.AudioContext`，所以走的正是
    「這個瀏覽器不支援 Web Audio」那條路徑——而那條路徑在真實世界裡
    幾乎不會被觸發，也就幾乎不會被人看到寫錯。這裡讓它每次都跑一遍。
    """
    data = run_smoke(name)
    assert data["shellMessageHidden"] is False, f"{name} 沒有把訊息顯示出來"
    assert "Web Audio" in data["shellMessage"]
    assert data["toggleDisabled"] is True, "按不出聲音的按鈕仍然可以按"
    assert not CJK.search(data["shellMessage"]), "畫面訊息出現中文（D5）"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_gibbs_table_really_gets_filled_in():
    """對照表是 JS 生出來的，所以伺服器端的 HTML 裡它是空的。

    這一項是唯一看得到那張表實際內容的地方，而那張表是這一頁
    糾正誤解的主要工具——空的、或欄數不對，在別的測試裡都不會變紅。
    """
    data = run_smoke("fourier")
    assert data["gibbsRowCount"] == 5
    for row in data["gibbsCells"]:
        assert len(row) == 4, f"對照表的欄數不對：{row}"

    # 載入時的預設是方波，但互動腳本最後把它切回方波，所以這裡讀到的是方波。
    counts = [int(row[0]) for row in data["gibbsCells"]]
    assert counts == [3, 7, 15, 31, 63]
    overshoots = [float(row[1].rstrip("%")) for row in data["gibbsCells"]]
    widths = [float(row[2].split()[0]) for row in data["gibbsCells"]]
    gaps = [float(row[3]) for row in data["gibbsCells"]]

    # ⛔ 這三行就是這一頁的教學論點，寫成三個斷言。
    assert overshoots[0] > overshoots[-1] > 8.9, "過衝應該降到 8.95% 附近就停住"
    assert overshoots[-1] < 9.0
    for previous, current in zip(widths, widths[1:]):
        assert 1.8 < previous / current < 2.2, "過衝的寬度應該每次減半"
    assert all(abs(gap - 1.0) < 1e-3 for gap in gaps), (
        "有跳點時與目標的最大差距不該下降——它停在跳點那一格上"
    )


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_readouts_are_filled_in_and_stay_english():
    """讀數區與三段 canvas 描述都要真的寫進東西，而且全部是英文。

    `test_the_fourier_page_has_its_controls_and_readouts` 只看得到
    伺服器送出去的 `—`；這裡看得到 JS 寫進去的內容。
    """
    readouts = run_smoke("fourier")["readouts"]
    for element_id in (
        "out-f0", "out-terms", "out-decay", "out-overshoot", "out-width",
        "verdict", "sum-description", "coefficients-description",
        "decomposition-description", "gibbs-caption", "derivation", "phase-hint",
    ):
        text = readouts.get(element_id, "")
        assert text and text != "—", f"{element_id} 沒有被填上任何內容"
        assert not CJK.search(text), f"{element_id} 出現中文：{text}"
        assert "grade" not in text.lower(), f"{element_id} 出現了評分字眼（D17）"
        assert "NaN" not in text and "undefined" not in text, (
            f"{element_id} 印出了 NaN 或 undefined：{text}"
        )


# ============================================================================
# 9. 瀏覽器支援訊息（D45，v0.20）
#
# 老師決定官方只支援 Chrome 與 Firefox（macOS 上裝得到 Chrome）。
# **這一組守的是「不支援」這件事有沒有真的被說出來。**
#
# 為什麼不能只在首頁寫一句話：Safari 的學生遇到的不是「頁面壞掉」，
# 而是「頁面看起來正常、按鈕按得下去、圖畫得出來，只是聲音不對」——
# 首頁那句話他早就捲過去了。這與 D13 的收合、D17 的沉默是同一類缺陷：
# **少說一句話不會讓任何東西壞掉，所以沒有人會發現。**
#
# 判斷邏輯本身（引擎白名單、能力偵測）是純函式，正反案例在
# `tests/test_dsp_js.py` 的第 9 組；這裡測的是「它有沒有被接到頁面上」
# 與「那句話的措辭有沒有越線」。
# ============================================================================

BROWSER_JS = DEMOS_STATIC / "lib" / "browser.js"
BROWSER_CHECK_JS = DEMOS_STATIC / "lib" / "browser-check.js"

#: 訊息裡**不得出現**的字。前七個沿用 `PROGRESS_WORDS`（D24），
#: 後面幾個是 D45 自己的：一句「暫時不支援」就是一個沒有人打算兌現的承諾。
NO_PROMISE_WORDS = PROGRESS_WORDS + (
    "for now", "at the moment", "currently not", "temporarily", "we plan",
    "in a future", "support for safari will",
)


@pytest.mark.parametrize("path", DEMO_PAGES)
def test_every_demo_page_carries_the_browser_notice(client, path):
    """四個頁面（索引 + 三個展示）都要有那個訊息區與偵測腳本。

    ⚠️ 索引頁也在裡面是刻意的：學生從那裡進來，早一頁知道要換瀏覽器，
    比按了 Start sound 之後才知道好。
    """
    html = client.get(path).text
    assert 'id="browser-notice"' in html, f"{path} 沒有瀏覽器支援訊息區"
    assert 'role="alert"' in html, "訊息是事後填進去的，沒有 role=alert 就不會被播報"
    assert '<script type="module" src="/static/demos/lib/browser-check.js">' in html


@pytest.mark.parametrize("path", DEMO_PAGES)
def test_the_browser_notice_starts_hidden(client, path):
    """預設收起來，由 JS 判斷之後才顯示。

    ⚠️ 反過來（預設顯示）看起來比較安全，實際上更糟：一個所有人都看得到的
    常駐橫幅會在兩週內被所有人的眼睛跳過，而那正好抵銷它存在的理由。
    這與 D13 的收合是**相反方向**的同一個判斷——重點都是「讓該被看到的
    東西真的被看到」。
    """
    html = client.get(path).text
    tag = re.search(r"<p[^>]*id=\"browser-notice\"[^>]*>", html)
    assert tag, f"{path} 上找不到那個 <p>"
    assert " hidden" in tag.group(0), (
        f"{path} 的瀏覽器訊息預設就顯示出來了：{tag.group(0)}"
    )


def test_the_browser_notice_is_not_inside_a_details(client):
    """它不得被塞進收合區——收合的東西等於沒有說。"""
    for path in DEMO_PAGES:
        html = client.get(path).text
        inside = re.sub(r"<details\b.*?</details>", "", html, flags=re.S)
        assert 'id="browser-notice"' in inside, f"{path} 把支援訊息藏進了 <details>"


def test_the_notice_names_the_two_supported_browsers_and_names_safari():
    """措辭的三個硬性要求，逐條檢查。

    1. **點名 Chrome 與 Firefox**——只說「你的瀏覽器不支援」而不說要用什麼，
       學生沒有下一步可以走。
    2. **點名 Safari**——不點名的話，Mac 上的學生不會認為那句話在說他。
    3. **說出失敗長什麼樣**（看起來正常但沒有聲音）。少了這一句，
       一個「圖都畫得出來」的學生會直接忽略它。
    """
    text = BROWSER_JS.read_text(encoding="utf-8")
    for phrase in ("Chrome", "Firefox", "Safari"):
        assert phrase in text, f"訊息裡沒有點名 {phrase}"
    assert "wrong or silent" in text or "silent" in text, (
        "訊息沒有說出「看起來正常但沒有聲音」這個失敗的樣子"
    )


def _message_literals():
    """把 `browser.js` 那幾段 `export const … = '…';` 的文字挖出來。

    ⚠️ **刻意不掃整個檔案**：那幾個被禁的詞**本來就會出現在說明為什麼不准
    用它們的註解裡**（`test_the_demo_javascript_has_no_way_to_send_anything_out`
    也是為了同一件事先剝註解）。掃註解等於禁止把理由寫下來，
    而在這個專案裡理由比程式碼還重要。
    """
    text = BROWSER_JS.read_text(encoding="utf-8")
    messages = re.findall(r"^export const [A-Z_]+ =\s*(.*?);\s*$", text, re.S | re.M)
    assert len(messages) >= 3, "找不到那三段訊息常值，這個測試大概失效了"
    return " ".join(messages)


def test_the_notice_promises_nothing_about_the_future():
    """⛔ D45 是一條決定，不是一個待辦事項。

    「Safari 之後會支援」這種話一旦寫上去，它就是一個沒有人打算兌現的承諾，
    而且它會讓學生**等**而不是**換瀏覽器**。同時這也是 D24 在這一段的形式：
    頁面不陳列待補項目。
    """
    lowered = _message_literals().lower()
    for word in NO_PROMISE_WORDS:
        assert word not in lowered, f"瀏覽器訊息出現了承諾／進度措辭：{word}"
    # "yet" 要當成一個字來找，否則會誤中英文裡一堆別的字。
    assert not re.search(r"\byet\b", lowered), "訊息裡出現了 yet"


def test_the_notice_is_not_a_feature_list(client):
    """D24 的張力點：支援聲明**不得變成變相的功能清單**。

    分界線很實際：這段話說的是「跑這一頁需要什麼」（前提條件），
    而 D24 禁的是「這個系統現在有什麼、還缺什麼」（進度表）。
    落到程式上就是——訊息裡不得出現任何展示的名字、題型或數量。
    """
    blob = _message_literals()
    for forbidden in (
        "aliasing", "Fourier", "spectrum", "leakage", "sampling",
        "practice", "problem", "topic",
    ):
        assert forbidden.lower() not in blob.lower(), (
            f"支援訊息裡出現了功能名稱「{forbidden}」——那讓它變成一份清單"
        )


def test_the_check_script_is_a_separate_entry_point():
    """⚠️ 偵測腳本刻意**不是**從展示的進入點裡呼叫的。

    理由正好是它要擋的東西：某個 API 不在的時候，展示的 module 很可能在
    載入途中就拋例外而中止——**於是最需要那句訊息的時候，那句訊息反而
    印不出來**。獨立的 <script type="module"> 各自載入、各自失敗。

    這一項把那個結構釘住：三支展示進入點都不准 import 它。
    """
    assert BROWSER_CHECK_JS.exists()
    for entry in DEMO_ENTRY_POINTS.values():
        text = (DEMOS_STATIC / entry).read_text(encoding="utf-8")
        assert "browser-check" not in text, (
            f"{entry} 把支援偵測接進了自己的載入路徑——那會讓它跟著一起掛掉"
        )


def test_the_check_script_writes_to_the_screen_not_to_the_console():
    """規則 4 在這一支上的形式：訊息必須進 DOM，不得只寫 console。"""
    text = BROWSER_CHECK_JS.read_text(encoding="utf-8")
    stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))
    assert "console." not in stripped, "偵測結果只寫進了 console"
    assert "textContent" in stripped and "hidden = false" in stripped


# ============================================================================
# 10. 摺積與 LTI 展示（2S10）
#
# 這一組守的是「頁面上必須有的東西」與「頁面上必須說出口的話」。
# 數值本身不在這裡驗——那是 `tests/test_dsp_js.py` 那一組的事，參考值由
# SymPy 的多項式乘法算出來（摺積 ≡ 多項式係數相乘）。
# ============================================================================

def test_the_convolution_page_has_its_controls_and_readouts(client):
    html = client.get(CONVOLUTION_URL).text

    # 每個值都有滑桿**和**數字輸入框（§8.6 第 1 點：不得有只能拖曳才能設定的值）
    for control in (
        "x-length", "x-length-number", "delay-taps", "delay-taps-number",
        "length-taps", "length-taps-number", "gain", "gain-number",
        "shift", "shift-number", "delay-ms", "delay-ms-number",
        "smooth-ms", "smooth-ms-number",
    ):
        assert f'id="{control}"' in html, f"缺少控制項 {control}"
    for control in (
        "input-shape", "response-shape", "flip", "sweep",
        "source", "listen", "lti-system",
    ):
        assert f'id="{control}"' in html, f"缺少控制項 {control}"

    # 六個脈衝響應與四個輸入都要在選單裡，否則頁面上那些對照就不存在
    for value in ("impulse", "delay", "echo", "repeat", "average", "difference"):
        assert f'value="{value}"' in html, f"脈衝響應的選單少了 {value}"
    for value in ("pulse", "ramp", "wiggle"):
        assert f'value="{value}"' in html, f"輸入的選單少了 {value}"

    for readout in ("out-x-length", "out-h-length", "out-y-length",
                    "out-overlap", "out-sum", "out-dc",
                    "out-taps", "out-bound", "out-low", "out-high"):
        assert f'id="{readout}"' in html

    # a11y：播報區 + 六張圖各自算出來的描述（§8.6 第 2、3 點）
    assert 'aria-live="polite"' in html
    for description in ("overlap-description", "products-description",
                        "output-description", "response-description",
                        "wave-description", "lti-description"):
        assert f'id="{description}"' in html
        assert f'aria-describedby="{description}"' in html

    # 音訊安全：明確的 Start 按鈕（autoplay 政策）＋ 靜音 ＋ 音量
    assert "Start sound" in html
    assert 'data-shell="mute"' in html
    assert 'data-shell="volume"' in html
    assert '<script type="module" src="/static/demos/convolution.js">' in html


def test_the_convolution_page_can_step_the_shift_without_dragging(client):
    """§8.6 第 1 點在這一頁的具體形式。

    平移量是這一頁**唯一一個真正要「動」的東西**，所以它特別不能只有滑桿：
    用鍵盤的人要能打一個精確的 n，而 `prefers-reduced-motion` 的人要有
    一個「往前一格」的按鈕而不是一段自己跑的動畫（§8.6 第 5 點）。
    """
    html = client.get(CONVOLUTION_URL).text
    assert 'id="shift-number"' in html
    assert 'type="number"' in html
    assert 'id="sweep"' in html
    # 掃描是一個 <button>，不是一段自動播放的東西——它必須由使用者發動。
    assert re.search(r'<button[^>]*id="sweep"', html)


def test_the_product_table_has_all_four_columns(client):
    """乘積表的四欄。

    少任何一欄它就不再是「學生在紙上會寫的那幾行」：沒有 k 就讀不出
    上下限，沒有 h[n-k] 就看不到翻轉，沒有乘積就只剩一個總和——
    而那個總和正是這一頁想拆開的東西。
    """
    html = client.get(CONVOLUTION_URL).text
    for column in ("k", "x[k]", "h[n-k]", "Product"):
        assert f"<th scope=\"col\">{column}</th>" in html, f"乘積表少了「{column}」那一欄"
    assert 'id="terms-rows"' in html
    assert 'id="terms-caption"' in html


def test_the_lti_table_reports_two_properties_separately(client):
    """⛔ 疊加性與非時變**必須是兩欄，不是一個綜合評語**。

    這一頁第三段的整個設計就架在這上面：三個系統各自只壞掉一格，
    所以兩個性質是**可以分開檢驗的兩件事**。併成一欄「是不是 LTI」
    的話，「削波哪裡不對」與「漸強增益哪裡不對」就變成同一句話，
    而它們其實完全不同。
    """
    html = client.get(CONVOLUTION_URL).text
    assert "Superposition" in html
    assert "Time invariance" in html
    assert 'id="lti-rows"' in html
    assert 'id="lti-caption"' in html


def test_the_convolution_page_says_out_loud_what_it_assumes_and_what_it_scales(client):
    """規則 4：兩件會靜默發生的事都要有畫面上的出口。

    （1）音訊還沒開始時，下半頁的數字是用一個**宣告過的**取樣率算的，
    不是裝置真正的那個（§8.5 禁止寫死取樣率，而「安靜地假設」與
    「寫死」是同一件事）。
    （2）Σ|h| 超過 1 的脈衝響應會被縮小之後才播——那是一個有意義的降級，
    但它得說出口，否則學生會以為回音本來就那麼小聲。

    ⚠️ 這一項比對的是 `convolution.js` 裡的字串，不是渲染後的 HTML：
    那兩句話是 JS 填進去的，頁面原始碼裡只有一個 `—`。
    """
    source = (DEMOS_STATIC / "convolution.js").read_text(encoding="utf-8")
    stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", source))
    assert "Sound has not started" in stripped
    assert "may run at a different rate" in stripped
    assert "scaled down by a factor of" in stripped
    # 頁面上也要有那個讀數本身，否則上面那句話沒有對照的數字。
    html = client.get(CONVOLUTION_URL).text
    assert "Largest possible gain" in html


def test_the_convolution_page_does_not_give_away_the_three_surprises(client):
    """⚠️ 規則 5 的分寸：這一頁有三件事不得先寫在畫面上。

    （1）**延遲的脈衝響應就是回音**——所以脈衝響應的選單只描述 h 的
    *形狀*（"an impulse plus one quieter copy"），不描述它的*效果*。
    （2）**為什麼要翻轉**——翻轉那個開關的標籤只說它做什麼動作。
    （3）**摺積是線性 + 非時變的唯一後果**——第三段只報數字，不下結論。

    三個結論全部住在 `<details>` 裡（那兩個由
    `test_what_you_just_heard_is_collapsed` 確認沒有 open）。
    這一項掃的是 `<details>` **以外**的部分。
    """
    html = client.get(CONVOLUTION_URL).text
    visible = re.sub(r"<details\b.*?</details>", "", html, flags=re.S)
    # ⚠️ 標籤要剝掉才掃。學生讀的是**文字**，而 `<option value="echo">` 的
    # 那個 `echo` 是程式用的鍵，畫面上顯示的是
    # 「an impulse plus one quieter copy」。不剝的話這一項會因為一個
    # 看不見的屬性值而變紅——一個沒有人看得懂的紅燈比沒有測試更糟。
    lowered = re.sub(r"<[^>]*>", " ", visible).lower()
    for word in ("echo", "reverb", "cross-correlation", "correlation"):
        assert word not in lowered, f"結論「{word}」洩漏到了收合區之外"
    # 反過來確認那些字**真的在**收合區裡——否則這一項會因為「頁面上根本
    # 沒講」而假裝通過，而那是一個很容易發生的退化。
    assert "echo" in html.lower()
    assert "cross-correlation" in html.lower()


def test_the_convolution_page_has_no_form_at_all(client):
    """這一頁不收任何輸入，所以整頁只該有 base.html 的登出那一個 form。

    與 D28 那一組同一個精神：**沒有結構就沒有風險**。這一頁本來就沒有
    檔案選擇器，而這一項擋的是日後有人「順手加一個上傳自己的脈衝響應」——
    那正是這個題目最容易長出上傳功能的地方（真實房間的 IR 是一個 wav 檔）。
    """
    html = client.get(CONVOLUTION_URL).text
    assert 'type="file"' not in html
    # ⚠️ v0.29（D57）：base.html 的登出表單隨帳號一起移除，所以現在是 0。
    assert html.count("<form") == 0


def test_the_convolution_demo_reuses_the_existing_sample_and_adds_no_new_asset():
    """⛔ 這一頁**不新增任何二進位資產**，它重用 2S4 已經進版控的語音範例。

    寫成測試而不是註解，是因為「順手加一個自己錄的房間脈衝響應 wav」
    是這個題目最自然的下一步，而那會繞過 D29 的「範例音檔的內容要與
    標籤相符」那一組測試（新檔案不會自動被納入）。
    """
    source = (DEMOS_STATIC / "convolution.js").read_text(encoding="utf-8")
    stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", source))
    referenced = set(re.findall(r"'([\w.-]+\.wav)'", stripped))
    assert referenced == {"speech-welcome.wav"}, (
        f"摺積展示引用了預期以外的音檔：{referenced}"
    )
    on_disk = {path.name for path in (DEMOS_STATIC / "samples").glob("*.wav")}
    assert referenced <= on_disk


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_product_table_really_gets_filled_in():
    """乘積表不是空的，而且最後一列是總和。

    與加法合成那一頁的吉布斯表同一個理由：**表格住在展示層**，
    而展示層照設計是沒有數值測試的。它不會拋錯，只會安靜地空著。
    """
    data = run_smoke("convolution")
    readouts = data["readouts"]
    assert readouts["out-sum"], "求和的讀數是空的"
    assert readouts["terms-caption"], "乘積表的說明是空的"
    for key in ("out-x-length", "out-h-length", "out-y-length", "out-overlap"):
        assert readouts[key], f"{key} 是空的"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_sweep_button_runs_and_then_stops_by_itself():
    """⛔ 自動掃描要跑得完，而且跑完會自己停。

    ⚠️ **這一項抓到過兩個 bug，兩個都在假環境的那一側**：
    冒煙腳本原本每格只把時間推進 33 ms，而 `shell.js` 的節流是 33.33 ms，
    於是 `startLoop()` 的回呼**一次都沒有跑過**；修好之後又發現
    `cancelAnimationFrame` 是一個 no-op，於是「在回呼裡停掉迴圈」
    這個完全正常的用法會對已經清空的 `loopFn` 呼叫。
    兩者在真的瀏覽器裡都不會發生——**假環境的偷懶會製造假的紅燈**，
    而這一項是唯一會發現它的東西。
    """
    data = run_smoke("convolution")
    assert "click:sweep" in data["interactions"]
    assert data["consoleErrors"] == []
    # 跑完之後按鈕的字要回到「開始掃描」，否則它就是卡在掃描中。
    assert data["readouts"].get("sweep") == "Sweep n from start to end"


# ============================================================================
# 展示 5：脈衝寬度與時頻取捨（2S11，PLAN §8.2.1 第 5 列；課程 W4）
#
# 與前四個展示同一組看守，加上這一頁特有的三件事：
#
#   * **兩個座標軸的範圍是使用者選的**，頁面上必須有那兩個控制項——
#     它們是 `pulse.js` 檔頭那條「軸不得自動縮放」的規則在 HTML 這一側
#     的落點（沒有控制項的話，唯一合理的實作就是自動縮放）。
#   * **沒有載波就沒有聲音**，而那必須是一句寫出來的話，不是一個沒有反應
#     的按鈕（規則 4）。
#   * **數值積分與閉合式的差距**要出現在畫面上。它不是除錯訊息，
#     是這一頁對「數值積分是一個近似」的兌現。
# ============================================================================

def test_the_pulse_page_has_its_controls_and_readouts(client):
    html = client.get(PULSE_URL).text

    # 每個值都有滑桿**和**數字輸入框（§8.6 第 1 點）
    for control in (
        'id="width"', 'id="width-number"',
        'id="shift"', 'id="shift-number"',
        'id="carrier"', 'id="carrier-number"',
    ):
        assert control in html, f"缺少控制項 {control}"

    # 形狀、載波開關、以及**兩個軸的範圍**
    for control in ('id="shape"', 'id="carrier-on"', 'id="fmax"', 'id="show-formula"'):
        assert control in html, f"缺少控制項 {control}"
    for shape in ("rectangle", "triangle", "cosine", "gaussian"):
        assert f'value="{shape}"' in html, f"下拉選單缺少 {shape}"

    # 讀數：寬度、峰高、零點、頻寬、乘積、不確定性、位移、以及那個差距
    for readout in (
        "out-width", "out-area", "out-null", "out-bandwidth",
        "out-product", "out-uncertainty", "out-shift", "out-agreement",
    ):
        assert f'id="{readout}"' in html

    # 三張圖，每一張都有算出來的文字替代（§8.6 第 3 點）
    for canvas, description in (
        ("time-canvas", "time-description"),
        ("magnitude-canvas", "magnitude-description"),
        ("phase-canvas", "phase-description"),
    ):
        assert f'id="{canvas}"' in html
        assert f'aria-describedby="{description}"' in html

    assert 'aria-live="polite"' in html
    assert "Start sound" in html
    assert '<script type="module" src="/static/demos/pulse.js">' in html


def test_the_pulse_page_lets_you_choose_both_axis_ranges(client):
    """⛔ **這一項守的是 `pulse.js` 檔頭那條規則在 HTML 這一側的形式。**

    軸若自動縮放，這一頁就沒有內容了（脈衝與頻譜都會看起來一樣寬）。
    「不自動縮放」的另一面是「使用者要能自己選」，而那是一個
    看得見的控制項。控制項不見了的話，下一個人唯一合理的實作
    就是自動縮放——所以這一項盯著的其實是那條規則會不會被繞過。
    """
    html = client.get(PULSE_URL).text
    assert 'id="fmax"' in html
    for span in ("500", "2000", "8000"):
        assert f'value="{span}"' in html, f"頻率軸缺少 {span} Hz 這一檔"
    # 時間軸是固定的，所以它不該有控制項——但頁面必須說出來它是固定的，
    # 否則學生會以為脈衝真的只有那麼寬。
    assert "fixed window" in html
    assert "Neither axis moves on its own" in html


def test_the_pulse_page_says_why_there_is_no_sound_without_a_carrier(client):
    """規則 4：不做靜默降級。

    載波關掉時播放是停用的，而**停用的理由必須寫在畫面上**——
    一個按不動的按鈕與一個壞掉的按鈕在學生眼裡是同一件事。
    這裡只驗那個容器存在（實際文字由 JS 依狀態填），以及頁面本身
    有把「0 Hz 不是聲音」這件事講出來。
    """
    html = client.get(PULSE_URL).text
    assert 'id="sound-note"' in html
    assert "Hz is not a sound" in html


def test_the_pulse_page_is_honest_about_the_numerical_integral(client):
    """這一頁**同時畫兩條曲線**（數值積分與閉合式），而且把差距印出來。

    ⚠️ 這不是除錯訊息。課綱對 W4 指定的 Python 實作就是「用數值積分
    模擬連續傅立葉變換」，而一個不說自己有多準的數值方法，教出來的
    正是「電腦算的就是對的」。
    """
    html = client.get(PULSE_URL).text
    assert "numerical integration" in html
    assert "closed form" in html
    assert 'id="out-agreement"' in html
    # 重複播放對頻譜的影響也要說出來（連續變換 vs 級數，W3 接 W4）。
    assert "line spectrum" in html


def test_the_pulse_page_does_not_give_away_the_three_surprises(client):
    """規則 5 的分寸：三個結論都不得出現在收合區**外面**。

    這一頁值得學生自己拖出來的有三件事：變窄就會變寬、位移完全不動
    幅度譜、以及很短的音聽不出音高。索引頁的一句話、頁首的提示、
    以及讀數區都不得先講。
    """
    html = client.get(PULSE_URL).text
    # ⚠️ 只看**看得見的文字**：`id="out-uncertainty"` 是一個識別碼，
    # 不是說給學生聽的話。連標籤一起掃的話，這一項會擋掉一個
    # 完全合理的 id，而繞過它的方式（改 id）沒有讓任何人受益。
    before = re.sub(r"<[^>]+>", " ", html.split("<details")[0])
    for giveaway in (
        "widen", "wider", "uncertainty", "no pitch", "cannot hear",
        "self-dual", "its own transform",
    ):
        assert giveaway not in before.lower(), f"「{giveaway}」在收合區外面就講了"

    index = client.get("/demos").text
    for giveaway in ("widen", "wider", "uncertainty"):
        assert giveaway not in index.lower()


def test_the_pulse_template_id_is_in_its_own_topic(client):
    """⚠️ `demo.transform.pulse` 而不是 `demo.fourier.pulse`。

    命名空間的第二段是**課程主題**，而 W3 的 Fourier 級數與 W4 的
    Fourier 變換是兩個主題（週期 vs 非週期）。沿用 `fourier` 會讓
    「一個查詢就分得開兩週的用量」失效，而那正是老師會問的問題。
    """
    from app.routes.demos import DEMOS

    ids = {demo.template_id for demo in DEMOS}
    assert "demo.transform.pulse" in ids
    assert "demo.fourier.pulse" not in ids
    # 兩週的展示因此分得開，而且分法是一個字首。
    assert len([i for i in ids if i.startswith("demo.fourier.")]) == 1
    assert len([i for i in ids if i.startswith("demo.transform.")]) == 1


def test_the_pulse_page_has_no_form_at_all(client):
    """D28 的對稱面：這一頁完全不送任何東西出去。

    它連檔案輸入都沒有（訊號是算出來的），所以「沒有 form」是一個
    可以直接斷言的強條件。
    """
    html = client.get(PULSE_URL).text
    assert 'type="file"' not in html
    # ⚠️ v0.29（D57）：base.html 的登出表單隨帳號一起移除，所以現在是 0。
    assert html.count("<form") == 0


def test_the_pulse_demo_adds_no_new_binary_asset():
    """這一頁一個新的二進位資產都沒有加——訊號全部是算出來的。

    與 2S10 那一項同一個用意：新增資產會把 D29「內容與標籤相符」
    那一組測試的範圍撐大，而這一頁根本不需要。
    """
    source = (DEMOS_STATIC / "pulse.js").read_text(encoding="utf-8")
    assert "samples/" not in source
    assert "fetch(" not in source


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_width_ladder_really_gets_filled_in():
    """寬度階梯那張表：五列、四欄，而**最後一欄五列完全相同**。

    ⚠️ 最後一欄是這張表唯一的論點（B·T 只與形狀有關），而它是
    「什麼都沒發生」的樣子——一張沒有被填的表、或一個把那一欄
    算成隨寬度變化的實作，兩者在畫面上都不會報錯。
    """
    data = run_smoke("pulse")
    rows = data["widthRows"]
    assert len(rows) == 5, f"寬度階梯應該有五列，實際 {len(rows)}"
    for row in rows:
        assert len(row) == 4
        for cell in row:
            assert cell and "NaN" not in cell and "undefined" not in cell
    products = {row[3] for row in rows}
    assert len(products) == 1, f"B·T 那一欄應該五列相同，實際有 {products}"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_pulse_readouts_survive_every_shape_and_axis():
    """撥完所有控制項之後，每一列讀數都還是有內容的英文。

    ⚠️ 特別盯著高斯：它是唯一一個 `firstNull` 是 null 的形狀，
    而 `null` 印到畫面上就是字串 "null"——一個不會報錯、
    只是說了一句沒有意義的話的失敗。
    """
    data = run_smoke("pulse")
    readouts = data["readouts"]
    for key in (
        "out-width", "out-area", "out-null", "out-bandwidth",
        "out-product", "out-uncertainty", "out-shift", "out-agreement",
        "verdict", "width-caption", "derivation",
    ):
        assert key in readouts, f"{key} 沒有被填"
        text = readouts[key]
        assert "NaN" not in text and "undefined" not in text and "null" not in text
        assert not CJK.search(text), f"{key} 出現中日韓字元：{text}"


# ============================================================================
# 展示 6：極零點與數位濾波器（2S9，課程 W7）
#
# 這一頁與前五頁有一個結構上的差別，而它決定了這一節多出來的那幾項：
# **它的核心互動是在 canvas 上拖曳**，而拖曳在伺服器端與靜態 HTML 上
# 都留不下痕跡。因此這裡有兩項是別的展示沒有的——
# 一項確認鍵盤那條路真的存在（§8.6 第 1 點），
# 一項在假 DOM 裡真的拖一次並斷言讀數變了。
#
# 另外兩件這一頁特有的事：
#   * **音訊安全**。這是唯一一頁有可能真的把喇叭弄壞的，所以「頁面有沒有
#     把音量的處理說出來」是一項測試，不是一句註解。
#   * **不穩定不是錯誤處理，是教材**。極點跑出單位圓時頁面要說出 ROC，
#     而不是只顯示一個錯誤。
# ============================================================================

def visible_text(html: str) -> str:
    """把標記剝掉、把空白壓成一個空格，只留下學生真的讀得到的字。

    ⚠️ **這一支解決的是兩個各自出過一次的問題，而兩個都是假的紅燈：**

      * **識別碼會被掃到。** `id="preset-notch"` 裡的 `notch` 不是一句
        寫給學生看的話，但一個直接掃 HTML 原文的「結論不得先講」測試
        會把它算進去。2S11 的 `id="out-uncertainty"` 踩過同一件事。
      * **片語會被換行切開。** 範本裡的一句話會依版面折行，於是
        `everything else getting quieter` 在原文裡是
        `everything\\n          else getting quieter`。
        2S11 的落地紀錄把這件事列為「第二次」，這裡是第三次——
        所以這一次把它變成一支共用的函式，而不是再繞一次。
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()


def test_the_polezero_page_has_its_controls_and_readouts(client):
    html = client.get(POLEZERO_URL).text

    # 四個值各有滑桿**和**數字輸入框（§8.6 第 1 點）
    for control in (
        'id="zero-radius"', 'id="zero-radius-number"',
        'id="zero-angle"', 'id="zero-angle-number"',
        'id="pole-radius"', 'id="pole-radius-number"',
        'id="pole-angle"', 'id="pole-angle-number"',
    ):
        assert control in html, f"缺少控制項 {control}"

    for control in ('id="use-poles"', 'id="source"', 'id="listen"', 'id="selected"'):
        assert control in html, f"缺少控制項 {control}"

    # 讀數：種類、穩定性、兩組係數、峰值、凹口、寬度、衰減、以及那個縮放
    for readout in (
        "out-kind", "out-stability", "out-numerator", "out-denominator",
        "out-peak", "out-notch", "out-bandwidth", "out-decay", "out-scale",
    ):
        assert f'id="{readout}"' in html

    # 差分方程是這一頁與老師 Python 作業之間的接點，它必須在畫面上
    assert 'id="equation"' in html

    # 四張圖，每一張都有算出來的文字替代（§8.6 第 3 點）
    for canvas, description in (
        ("plane-canvas", "plane-description"),
        ("magnitude-canvas", "magnitude-description"),
        ("phase-canvas", "phase-description"),
        ("impulse-canvas", "impulse-description"),
    ):
        assert f'id="{canvas}"' in html
        assert description in html

    assert 'aria-live="polite"' in html
    assert "Start sound" in html
    assert '<script type="module" src="/static/demos/polezero.js">' in html


def test_the_polezero_page_can_be_driven_without_dragging(client):
    """⛔ **這一項是這一頁的無障礙承諾在 HTML 這一側的形式。**

    §8.6 第 1 點寫著「不得有任何只能拖曳才能設定的值」，而這一頁是
    整個展示區裡唯一一頁的**主要互動就是拖曳**——也就是說，
    這一條規則在別的頁面上是預防性的，在這一頁上是實質的。

    三條路都要在：數字框（上一項已經驗過）、鍵盤（可聚焦的圖 + 說明），
    以及一排預設按鈕（§8.6 第 6 點對「沒辦法完全等價」那件事的緩解）。
    """
    html = client.get(POLEZERO_URL).text

    # 圖本身要能被鍵盤聚焦，否則方向鍵沒有地方送
    assert 'id="plane-canvas"' in html
    plane = re.search(r"<canvas\b[^>]*id=\"plane-canvas\"[^>]*>", html)
    assert plane is not None
    assert 'tabindex="0"' in plane.group(0), "z 平面不能用鍵盤聚焦"

    # 按鍵要說明在畫面上，不是只寫在程式裡
    assert "arrow keys" in html.lower()

    # 預設按鈕：四顆，各對應教材上的一站
    for button in (
        "preset-notch", "preset-resonator", "preset-fir", "preset-unstable",
    ):
        assert f'id="{button}"' in html, f"缺少預設按鈕 {button}"


def test_the_polezero_page_says_out_loud_what_it_does_to_the_volume(client):
    """音訊安全的第二層有代價，而**代價必須寫在學生看得到的地方**。

    把峰值壓回 1 之後，學生聽到的不是「共振變大聲」而是「其餘變小聲」。
    那是一個關於這一頁的事實，不是一個實作細節——不講的話，
    這一頁對「極點靠近單位圓會怎樣」這個問題給的是一個經過修飾的答案。
    這與 2S5 的 `disableNormalization`、2S10 不用 `ConvolverNode` 是同一場仗。
    """
    html = client.get(POLEZERO_URL).text
    text = visible_text(html)
    assert "divided by the peak gain" in text
    assert "everything else getting quieter" in text
    # 而那個被壓掉的數字要有一個落點
    assert 'id="out-scale"' in html
    assert 'id="out-peak"' in html


def test_the_polezero_page_treats_an_unstable_pole_as_teaching_not_as_an_error(client):
    """極點跑出單位圓不是一個錯誤狀態，是 W7 的收斂域那一段。

    ⚠️ 這一項盯著的是一個很容易發生的退化：把不穩定處理成
    「顯示一個紅色錯誤、什麼都不畫」。那在工程上完全合理，
    而它會刪掉這一頁最值得看的一格。
    """
    html = client.get(POLEZERO_URL).text
    text = visible_text(html).lower()
    assert "region of convergence" in text
    # 曲線不是消失，是改成灰色虛線並說明理由
    assert "grey and dashed" in text
    # 而那一格要有東西可以看：衝激響應
    assert 'id="impulse-canvas"' in html


def test_the_polezero_page_does_not_give_away_the_three_surprises(client):
    """規則 5 的分寸：三個結論都只能出現在收合區裡面。

    這一頁要學生自己拖出來的是：零點靠近圓會挖掉一個頻率、
    極點靠近圓會抬起一個頻率並讓它拖尾、以及拿掉極點就是 FIR。
    """
    html = client.get(POLEZERO_URL).text
    # ⚠️ 只掃**看得見的字**：`id="preset-notch"` 這種識別碼不是一句
    # 寫給學生看的話，而它會讓這一項在完全正確的頁面上變紅。
    before = visible_text(html.split("<details", 1)[0]).lower()
    for giveaway in (
        "notch", "resonance", "ringing", "finite impulse response",
        "product of distances",
    ):
        assert giveaway not in before, f"「{giveaway}」在收合區外面就講了"

    index = visible_text(client.get("/demos").text).lower()
    for giveaway in ("notch", "resonance", "unstable"):
        assert giveaway not in index


def test_the_polezero_template_id_is_in_its_own_topic(client):
    """⚠️ `demo.filter.polezero` 而不是 `demo.transform.polezero`。

    命名空間的第二段是**課程主題**，而 W4 的連續 Fourier 變換已經用掉了
    `transform`。沿用它會讓「一個查詢就分得開兩週的用量」失效——
    這與 2S11 那一列避開 `fourier` 是同一個理由的第二次適用。

    順帶斷言**每一個字首各只有一頁**：這個性質才是那句話的實質內容，
    而它會在下一個展示不小心撞名的時候變紅。
    """
    from app.routes.demos import DEMOS

    ids = {demo.template_id for demo in DEMOS}
    assert "demo.filter.polezero" in ids
    assert "demo.transform.polezero" not in ids
    prefixes = [i.rsplit(".", 1)[0] for i in ids]
    assert len(prefixes) == len(set(prefixes)), f"有兩頁共用同一個主題字首：{prefixes}"


def test_the_polezero_page_has_no_form_at_all(client):
    """D28 的對稱面：這一頁完全不送任何東西出去。"""
    html = client.get(POLEZERO_URL).text
    assert 'type="file"' not in html
    # ⚠️ v0.29（D57）：登出表單隨帳號一起移除，所以現在是 0 不是 1。
    assert html.count("<form") == 0


def test_the_polezero_demo_reuses_the_existing_samples_and_adds_no_new_asset():
    """三個音源全部是 2S4 就進版控的檔案（D29），**零新增資產**。

    與 2S10 那一項同一個用意，但這一頁引用三個檔案而不是一個，
    所以斷言的形式是「引用到的每一個都必須已經存在」。
    """
    source = (DEMOS_STATIC / "polezero.js").read_text(encoding="utf-8")
    referenced = set(re.findall(r"'([\w-]+\.wav)'", source))
    assert referenced, "polezero.js 沒有引用任何範例音檔，這個測試大概失效了"
    for name in referenced:
        assert (DEMOS_STATIC / "samples" / name).exists(), f"{name} 不存在"


def test_the_polezero_worklet_is_served_and_is_not_a_module():
    """worklet 要拿得到，而且**不得含有 import**。

    ⚠️ 第二半不是風格問題：Safari 對 worklet 裡的 ES module import 支援
    不一致，所以 `sampler-processor.js` 當初就刻意寫成一支不 import 任何
    東西的普通腳本。這一支沿用同一個約束，而約束需要一個看守——
    加一行 import 在開發機的 Chrome 上會正常，在別人的機器上不會。
    """
    path = DEMOS_STATIC / "worklets" / "polezero-processor.js"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    stripped = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))
    assert "import " not in stripped and "export " not in stripped
    assert "registerProcessor('pole-zero-filter'" in stripped


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_dragging_on_the_plane_really_moves_a_pole():
    """⛔ **假 DOM 裡真的拖一次，並且斷言讀數變了。**

    這一項存在的理由很具體：冒煙腳本裡那組拖曳的座標是**算出來寫死的**
    （見 `run_demo_smoke.mjs` 的 polezero 那一段），而改了 padding 或
    平面的範圍就會抓空。**抓空的症狀是「一步都沒有拖到，而輸出完全正常」**
    ——只看有沒有跑完的話，這一項會永遠是綠的。
    所以這裡比的是拖曳前後的極點半徑。
    """
    data = run_smoke("polezero")
    steps = [s for s in data["interactions"] if s.startswith("pointer")]
    assert steps == [
        "pointerdown:plane-canvas",
        "pointermove:plane-canvas",
        "pointerup:plane-canvas",
    ], f"拖曳那三步沒有跑完：{steps}"
    moves = data["polezeroTrace"]
    before = moves["beforeDrag"]
    after = moves["afterDrag"]
    assert before != after, (
        "拖曳之後極點沒有動——冒煙腳本裡的座標大概抓空了，"
        f"前後都是 {before}"
    )
    # 往左上拖＝半徑變小、角度變大，兩個都要動到，否則只驗到了一半。
    assert after["r"] < before["r"]
    assert after["theta"] > before["theta"]


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_arrow_keys_move_the_same_marks_as_the_mouse():
    """鍵盤那條路不是裝飾，它要真的改得動同一組狀態。

    ⚠️ 這一項與上一項是一對，而**它們必須分開**：拖曳壞掉與鍵盤壞掉是
    兩件互不相關的事，合成一項的話只會知道「有一條路壞了」。
    """
    data = run_smoke("polezero")
    keys = [s for s in data["interactions"] if s.startswith("keydown")]
    assert len(keys) == 5, f"鍵盤步驟沒有跑完：{keys}"
    trace = data["polezeroTrace"]
    assert trace["afterKeys"] != trace["afterDrag"], "方向鍵沒有改變任何東西"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_polezero_readouts_survive_every_preset():
    """撥完四顆預設按鈕與所有控制項之後，每一列讀數都還是有內容的英文。

    ⚠️ 特別盯著兩個容易印出沒有意義的字的地方：不穩定那一顆按鈕
    （`halfPowerWidth` 回傳 null）與 FIR 那一顆（沒有極點，衰減時間
    沒有意義）。`null` 印到畫面上就是字串 "null"——一個不會報錯、
    只是說了一句沒有意義的話的失敗，2S11 記過同一件事。
    """
    data = run_smoke("polezero")
    readouts = data["readouts"]
    for key in (
        "out-kind", "out-stability", "out-numerator", "out-denominator",
        "out-peak", "out-notch", "out-bandwidth", "out-decay", "out-scale",
        "equation", "verdict", "rate-note",
    ):
        assert key in readouts, f"{key} 沒有被填"
        text = readouts[key]
        assert "NaN" not in text and "undefined" not in text and "null" not in text
        assert not CJK.search(text), f"{key} 出現中日韓字元：{text}"


@pytest.mark.dsp_js
@pytest.mark.skipif(NODE is None, reason=_SMOKE_SKIP)
def test_the_difference_equation_is_written_out_with_real_numbers():
    """差分方程那一行是這一頁與老師 Python 作業之間的接點。

    所以它不能只是存在，它要**看起來就是課本上那一行**：
    左邊 y[n]、右邊有 x 的項與 y 的過去項。
    """
    data = run_smoke("polezero")
    text = data["readouts"]["equation"]
    assert text.startswith("y[n] = ")
    assert "x[n]" in text
    # 最後一次互動把極點打開了，所以右邊必須有回授項
    assert "y[n−1]" in text or "y[n-1]" in text
