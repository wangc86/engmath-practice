"""出題引擎。

import 這個套件會自動載入所有題型模組並完成註冊。
新增題型只要在本目錄下加一個檔案，並把檔名加進下面的 import 清單。
"""

from .base import (  # noqa: F401
    DIFFICULTY_LABELS,
    Check,
    GenerationError,
    Problem,
    Step,
    Template,
    generate,
    list_templates,
    register,
)

# 匯入以觸發 @register（順序不影響行為，list_templates() 會自行排序）
from . import separable  # noqa: F401,E402
from . import first_order_linear  # noqa: F401,E402
from . import second_order_homog  # noqa: F401,E402
from . import system_2x2  # noqa: F401,E402

__all__ = [
    "DIFFICULTY_LABELS",
    "Check",
    "GenerationError",
    "Problem",
    "Step",
    "Template",
    "generate",
    "list_templates",
    "register",
]
