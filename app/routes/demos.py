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

from ..db.models import Student, UsageLog
from ..db.session import engine
from ..logging_setup import get_logger
from .deps import current_student, templates

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
)

_BY_SLUG = {demo.slug: demo for demo in DEMOS}


def _log_demo_open(student_id: int, template_id: str) -> None:
    """一次頁面載入 = 一列。**不記參數變動**（§8.7：滑桿軌跡超出用量的範圍）。

    代價老實說一句：重新整理頁面會多算一列，因此「開啟次數」略為高估。
    不做去重（那需要額外狀態），這件事寫在這裡與 §8.7。
    """
    with Session(engine) as session:
        session.add(
            UsageLog(
                student_id=student_id,
                template_id=template_id,
                difficulty=DEMO_SENTINEL,
                seed=DEMO_SENTINEL,
                action=DEMO_ACTION,
            )
        )
        session.commit()


@router.get("", response_class=HTMLResponse)
def index(request: Request, student: Student = Depends(current_student)):
    """展示索引頁。**不寫進 `UsageLog`**——只記「打開了哪個展示」（§8.7）。"""
    return templates.TemplateResponse(
        request, "demos/index.html", {"student": student, "demos": DEMOS}
    )


@router.get("/{group}/{name}", response_class=HTMLResponse)
def demo_page(
    request: Request,
    group: str,
    name: str,
    student: Student = Depends(current_student),
):
    demo = _BY_SLUG.get(f"{group}/{name}")
    if demo is None:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "There is no demo at this address."},
            status_code=404,
        )
    _log_demo_open(student.id, demo.template_id)
    return templates.TemplateResponse(
        request, demo.template, {"student": student, "demo": demo}
    )
