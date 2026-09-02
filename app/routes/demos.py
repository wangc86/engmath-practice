"""互動式訊號處理展示（PLAN.md §8，階段 2S）。

這是本專案的**第二個功能區**，與出題引擎的關係由 D21 限定得很死：
只共用 `base.html` 的版面與自架資產（v0.29 之前還共用登入與 `UsageLog`，
那兩樣現在都沒有了，所以共用面又更窄了一點）。
**這個檔案不 import `app.generator` 的任何東西**，也不碰 `REGISTRY`／`template_id`
的註冊表機制——刻意不去找共同抽象（D21 寫得很清楚為什麼）。

伺服器端在這裡做的事少得出奇，而那正是 D18 的重點：訊號產生、變換、繪圖、
即時音訊全部在瀏覽器裡跑。**v0.29 之後它只剩一件事：渲染一個靜態頁面。**

---

## v0.29（D57、D58）：登入與用量紀錄都沒有了

原本每一次開啟展示會寫一列 `UsageLog`（§8.7 的 `demo_open` 與那組
sentinel 約定）。系統改為學生自行在自己的電腦上安裝執行之後，
**系統這一側不再蒐集任何東西**——那張表移除了，`DEMO_ACTION`／
`DEMO_SENTINEL` 兩個常數與 `_log_demo_open()` 一併移除。

⚠️ 順帶一提，§8.7 花了不少篇幅論證「沿用既有五個欄位、一個都不加」，
而那整段推導**沒有白費**：它是 v0.16 那條「用量紀錄不得長出指得到人的
欄位」的落點，而現在達成同一件事的方式更徹底——**沒有欄位可以長**。
保存版本在 tag `hosted-v1`。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..curriculum import KIND_DEMO, ids_for_week, weeks_with_content
from ..logging_setup import get_logger
from .deps import templates

logger = get_logger(__name__)

router = APIRouter(prefix="/demos")


@dataclass(frozen=True)
class Demo:
    """一個展示。刻意是純資料，不是一個註冊表機制（D21：不共用抽象）。

    `template_id` 用 `demo.` 開頭，與出題的 `ode.`／`system.` 分屬不同命名空間，
    因此一個查詢就能把兩者分開，不需要多一個欄位。
    """

    slug: str            # 網址片段，例如 "sampling/aliasing"
    template_id: str     # 穩定識別碼，例如 "demo.sampling.aliasing"
    title: str           # 英文標題（D5）
    week: str            # 對應的課程週次，學生找的是「這週上課提到的那個」
    topic: str           # 課程主題
    summary: str         # 一句話說明，索引頁用
    template: str        # Jinja 範本路徑


#: ⚠️ **只列出現在真的點得進去的展示**（D24）。
#: 不放規劃中的項目、不寫 "coming soon"——一份會腐化的自述比沒有自述更不誠實。
#: `tests/test_demos.py` 有一項防回頭測試盯著這件事。
DEMOS: tuple[Demo, ...] = (
    Demo(
        slug="sampling/aliasing",
        template_id="demo.sampling.aliasing",
        title="Sampling and aliasing",
        week="Week 6",
        topic="Sampling theorem",
        summary=(
            "Lower the sampling rate past the Nyquist frequency and hear what "
            "happens to a pure tone."
        ),
        template="demos/aliasing.html",
    ),
    Demo(
        slug="spectrum/leakage",
        template_id="demo.spectrum.leakage",
        title="Spectrum, windows and leakage",
        week="Week 5",
        topic="DFT and FFT",
        summary=(
            "Watch a single tone spread across the spectrum when it does not "
            "line up with the analysis, and see what a window does about it."
        ),
        template="demos/spectrum.html",
    ),
    # ⚠️ 這一列的 `slug` 與 `template_id` **刻意不一致**（`fourier/series`
    # 對 `demo.fourier.additive`），前兩列則是一致的。理由值得寫下來，
    # 因為下一個人一定會想「順手改成一樣的」：
    #
    #   * `template_id` 是**穩定識別碼**，由老師指定。⚠️ v0.29 之前它會被
    #     寫進 `UsageLog`，所以「一旦有列存在就不能改」；那張表沒有了，
    #     但它現在是 `curriculum.py` 歸類表的鍵，約束因此換了個地方存在。
    #   * `slug` 只是網址，改它只會壞掉書籤。學生找的是「加法合成」那一頁，
    #     而 `/demos/fourier/series` 比 `/demos/fourier/additive` 好認。
    #
    # 也就是說兩者的**約束強度不同**，而前兩列的一致只是巧合，不是規則。
    Demo(
        slug="fourier/series",
        template_id="demo.fourier.additive",
        title="Fourier series: building a wave out of sines",
        week="Week 3",
        topic="Fourier series",
        summary=(
            "Add up sines until they look like a square wave, then change only "
            "their phases and listen to what does not change."
        ),
        template="demos/fourier.html",
    ),
    # 2S10。`template_id` 用老師指定的 `demo.lti.convolution`：命名空間的
    # 第二段是**課程主題**（`sampling`／`spectrum`／`fourier`／`lti`），
    # 而這一頁的主題確實是 LTI——摺積是那兩個假設的後果，不是反過來。
    #
    # ⚠️ 這一列的 `week` 是唯一一個橫跨兩週的。字串刻意寫成 `Weeks 1-2`
    # 而不是 `Week 1` + 另一個展示：W1（LTI 的定義）與 W2（摺積）在教材上
    # 是一條論證的兩半，拆成兩頁會讓「為什麼是摺積」這個問題沒有地方問。
    # 取捨與工作量的影響見 PLAN §8.9.4。
    Demo(
        slug="lti/convolution",
        template_id="demo.lti.convolution",
        title="Convolution: what a system does to every sample",
        week="Weeks 1-2",
        topic="LTI systems and convolution",
        # ⚠️ 這一句刻意**不寫出結論**（規則 5 的分寸）。草稿寫的是
        # 「…turn a click into an echo」，而那正好把這一頁三個要學生自己
        # 發現的東西之一直接印在索引頁上。索引頁說的是「你會做什麼」，
        # 不是「你會發現什麼」。
        summary=(
            "Slide one signal across another one sample at a time and watch the "
            "sum being built, then send real sound through the same operation."
        ),
        template="demos/convolution.html",
    ),
    # 2S11。`template_id` 的第二段仍然是**課程主題**，而這裡有一個必須說清楚
    # 的判斷：W3 的 Fourier 級數已經用掉了 `fourier`，而 W4 是**變換**，
    # 那是另一個主題（週期 vs 非週期），不是同一個主題的第二頁。
    # 沿用 `fourier` 會讓「一個查詢就分得開兩週的用量」這件事失效——
    # 而那正是老師會問的問題（哪一週的展示有人在用）。所以第二段是
    # `transform`，第三段是學生實際在拖的那個東西（`pulse`）。
    Demo(
        slug="transform/pulse",
        template_id="demo.transform.pulse",
        title="Pulse width and the time-frequency trade-off",
        week="Week 4",
        topic="Continuous Fourier transform",
        # ⚠️ 與 2S10 那一列同一個分寸（規則 5）：這一句說「你會做什麼」，
        # 不說「你會發現什麼」。草稿寫的是「…and watch the spectrum widen」，
        # 而「變窄就會變寬」正是這一頁要學生自己拖出來的第一件事。
        summary=(
            "Drag the width of a single pulse and watch what happens to its "
            "spectrum, computed by numerical integration as you go."
        ),
        template="demos/pulse.html",
    ),
    # 2S9。`template_id` 的第二段仍然是**課程主題**，而這一頁的判斷比
    # 2S11 那一次更需要寫下來，因為有兩個看起來都對的候選：
    #
    #   * `transform`（z 轉換也是一個變換）——⛔ **不行**，W4 已經用掉它了。
    #     沿用會讓「一個查詢就分得開兩週的用量」失效，而那正是 2S11 那一列
    #     費了一段篇幅避開的失敗方式。
    #   * `filter`——✅ 採用。課綱 W7 那一行的最後一項就是「FIR 與 IIR
    #     濾波器架構」，而這一頁的內容確實是濾波器：z 平面是地圖，
    #     濾波器是那塊地。它順帶也是 D22 允許它服務 W11 頻率響應直覺的
    #     那個身分（見 §8.1：那裡沒有受控體、沒有回饋、沒有設定值）。
    #
    # `slug` 用 `filter/pole-zero`（帶連字號，學生看得懂），`template_id`
    # 的第三段用 `polezero`（識別碼裡不放連字號，與其餘四列一致）。
    # 兩者的約束強度不同，見上面 2S5 那一列的說明。
    Demo(
        slug="filter/pole-zero",
        template_id="demo.filter.polezero",
        title="Poles, zeros and digital filters",
        week="Week 7",
        topic="Z-transform and digital filters",
        # ⚠️ 與前兩列同一個分寸（規則 5）：這一句說「你會做什麼」，
        # 不說「你會發現什麼」。草稿寫的是「…and hear a frequency
        # disappear」，而那正是這一頁要學生自己拖出來的第一件事。
        summary=(
            "Drag poles and zeros around the unit circle and hear what each "
            "position does to the sound passing through the filter they define."
        ),
        template="demos/polezero.html",
    ),
)

_BY_SLUG = {demo.slug: demo for demo in DEMOS}


@dataclass(frozen=True)
class Sample:
    """一個內建的範例音檔（D29）。

    這些 wav **由 `scripts/make_demo_samples.py` 產生並納入版本控制**，
    產生方式與理由寫在那支腳本的開頭。伺服器端對它們只做一件事：
    把檔名與英文標籤交給範本，讓 `<select>` 有東西可列。

    ⚠️ 順序就是下拉選單的順序，第一個是預設值。純正弦排第一是刻意的：
    它是唯一一個「頻譜上該有什麼」可以先在腦子裡想清楚的訊號。
    """

    file: str
    label: str


SAMPLES: tuple[Sample, ...] = (
    Sample("tone-440.wav", "Pure sine at 440 Hz"),
    Sample("two-tones-440-452.wav", "Two sines, 440 Hz and 452 Hz"),
    Sample("square-220.wav", "Square wave at 220 Hz"),
    Sample("sawtooth-220.wav", "Sawtooth wave at 220 Hz"),
    Sample("noise-white.wav", "White noise"),
    Sample("speech-welcome.wav", "A synthesised voice saying a sentence"),
)


def _weekly_groups() -> list[dict]:
    """索引頁的分組：每一週一個區塊（D52 的殘存用途，D59）。

    ⚠️ **標題從 `curriculum.py` 的週次表拿，展示的名稱從 `DEMOS` 拿。**
    `Demo.week` 那個字串（"Weeks 1-2"）仍然印在每一列旁邊，而
    `tests/test_curriculum.py` 有一項測試確認它與歸類算出來的一致——
    兩份真相刻意留著，但不准漂移。
    """
    by_id = {demo.template_id: demo for demo in DEMOS}
    groups = []
    for week in weeks_with_content(KIND_DEMO):
        rows = [
            by_id[cid] for cid in ids_for_week(week.number, KIND_DEMO)
            if cid in by_id
        ]
        if rows:
            groups.append({
                "number": week.number,
                "topic": week.topic,
                "demos": rows,
            })
    return groups


@router.get("", response_class=HTMLResponse)
def index(request: Request):
    """展示索引頁，依課程週次分組。

    ⚠️ **只列出現在真的點得進去的展示**（D24），而 v0.29 之後那句話
    回到它最原始的意思：「做出來了」。v0.28 那個「而且老師開放了」的
    附加條件隨開放閘門一起移除（D59）。
    """
    return templates.TemplateResponse(
        request, "demos/index.html", {"weeks": _weekly_groups()}
    )


@router.get("/{group}/{name}", response_class=HTMLResponse)
def demo_page(request: Request, group: str, name: str):
    demo = _BY_SLUG.get(f"{group}/{name}")
    if demo is None:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "There is no demo at this address."},
            status_code=404,
        )
    return templates.TemplateResponse(
        request, demo.template, {"demo": demo, "samples": SAMPLES}
    )
