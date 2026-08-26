"""互動式訊號處理展示（PLAN.md §8，階段 2S）。

這是本專案的**第二個功能區**，與出題引擎的關係由 D21 限定得很死：
只共用 `routes/deps.py` 的登入、`UsageLog`、以及 `base.html` 的版面與自架資產。
**這個檔案不 import `app.generator` 的任何東西**，也不碰 `REGISTRY`／`template_id`
的註冊表機制——刻意不去找共同抽象（D21 寫得很清楚為什麼）。

伺服器端在這裡做的事少得出奇，而那正是 D18 的重點：訊號產生、變換、繪圖、
即時音訊全部在瀏覽器裡跑。這個檔案只負責「檢查登入 → 渲染一個靜態頁面 →
寫一列用量紀錄」。

用量紀錄的作法見 §8.7：**沿用 `UsageLog` 既有的五個欄位，一個都不加**
（規則 3）。`difficulty` 與 `seed` 是非空整數而展示沒有這兩個概念，
所以寫 0 當 sentinel；`tests/test_demos.py` 有一項不變量測試盯著這個約定，
免得三個月後沒有人記得 0 是什麼意思。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..db.models import Account, UsageLog
from ..db.session import engine
from ..logging_setup import get_logger
from .deps import current_account, templates

logger = get_logger(__name__)

router = APIRouter(prefix="/demos")

#: 展示用的 `UsageLog.action`。§8.7 的不變量測試靠這個前綴認出展示的列。
DEMO_ACTION = "demo_open"

#: `difficulty` 與 `seed` 的 sentinel。展示沒有難度、也沒有題號。
DEMO_SENTINEL = 0


@dataclass(frozen=True)
class Demo:
    """一個展示。刻意是純資料，不是一個註冊表機制（D21：不共用抽象）。

    `template_id` 用 `demo.` 開頭，與出題的 `ode.`／`system.` 分屬不同命名空間，
    因此一個查詢就能把兩者分開，不需要多一個欄位。
    """

    slug: str            # 網址片段，例如 "sampling/aliasing"
    template_id: str     # UsageLog 用，例如 "demo.sampling.aliasing"
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


def _log_demo_open(account_id: int, template_id: str) -> None:
    """一次頁面載入 = 一列。**不記參數變動**（§8.7：滑桿軌跡超出用量的範圍）。

    代價老實說一句：重新整理頁面會多算一列，因此「開啟次數」略為高估。
    不做去重（那需要額外狀態），這件事寫在這裡與 §8.7。
    """
    with Session(engine) as session:
        session.add(
            UsageLog(
                account_id=account_id,
                template_id=template_id,
                difficulty=DEMO_SENTINEL,
                seed=DEMO_SENTINEL,
                action=DEMO_ACTION,
            )
        )
        session.commit()


@router.get("", response_class=HTMLResponse)
def index(request: Request, account: Account = Depends(current_account)):
    """展示索引頁。**不寫進 `UsageLog`**——只記「打開了哪個展示」（§8.7）。"""
    return templates.TemplateResponse(
        request, "demos/index.html", {"account": account, "demos": DEMOS}
    )


@router.get("/{group}/{name}", response_class=HTMLResponse)
def demo_page(
    request: Request,
    group: str,
    name: str,
    account: Account = Depends(current_account),
):
    demo = _BY_SLUG.get(f"{group}/{name}")
    if demo is None:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "There is no demo at this address."},
            status_code=404,
        )
    _log_demo_open(account.id, demo.template_id)
    return templates.TemplateResponse(
        request,
        demo.template,
        {"account": account, "demo": demo, "samples": SAMPLES},
    )
