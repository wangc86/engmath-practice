"""出題引擎。

import 這個套件會自動載入所有題型模組並完成註冊。
新增題型只要在對應的章節子目錄（``ode/``、``systems/``、``fourier/``）下加一個
檔案，並把它加進下面的 import 清單。

⛔ **檔案路徑與 ``template_id`` 從來沒有耦合過**（D16），所以往後搬檔案仍然很便宜
——但反過來說，**搬檔案也不得順手改 ``template_id``**：註冊表以它為鍵，
而改掉它的症狀是安靜的。
"""

from .base import (  # noqa: F401
    ASSET_KEYS,
    DIFFICULTY_LABELS,
    AnswerKind,
    Check,
    GenerationError,
    Problem,
    Step,
    Template,
    Verifier,
    generate,
    list_templates,
    register,
)

# 匯入以觸發 @register（順序不影響行為，list_templates() 會自行排序）。
# v0.31（工作項 2a0，D16／D64）：全部題型都住在章節子目錄裡了，
# 平面結構的過渡狀態結束。⛔ 這一輪一個 `template_id` 都沒有改。
from .ode import separable  # noqa: F401,E402
from .ode import first_order_linear  # noqa: F401,E402
from .ode import second_order_homog  # noqa: F401,E402
from .ode import laplace  # noqa: F401,E402
from .systems import real_distinct  # noqa: F401,E402
from .systems import linear_2x2  # noqa: F401,E402
from .systems import classify  # noqa: F401,E402
from .fourier import series  # noqa: F401,E402
from .fourier import half_range  # noqa: F401,E402
from .fourier import complex_form  # noqa: F401,E402
from .fourier import transform  # noqa: F401,E402

__all__ = [
    "ASSET_KEYS",
    "DIFFICULTY_LABELS",
    "AnswerKind",
    "Check",
    "GenerationError",
    "Problem",
    "Step",
    "Template",
    "Verifier",
    "generate",
    "list_templates",
    "register",
]
