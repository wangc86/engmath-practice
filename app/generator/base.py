"""出題引擎的核心資料結構與註冊表。

設計原則（見 PLAN.md §2.1）：
1. 反向構造優先於正向求解 —— 先決定答案長什麼樣，再倒推題目。
2. SymPy 是驗證閘門（gate），不是生成器 —— 每題出廠前都要通過殘差檢查。
3. 逐步解答由模板自己寫，中間量由 SymPy 算。

新增題型只要在 ``app/generator/`` 底下加一個檔案，用 ``@register(...)``
註冊生成函式，UI 下拉選單與 pytest 參數化測試都會自動撿到。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Literal

import sympy as sp

Difficulty = Literal[1, 2, 3]

DIFFICULTY_LABELS: dict[int, str] = {
    1: "Basic",
    2: "Standard",
    3: "Challenge",
}


@dataclass
class Step:
    """逐步解答的一個步驟。

    介面語言為英文（本課程全英語授課）。`note` 中若要出現數學式，
    一律用 $…$ 包起來，KaTeX 才會渲染——不要寫裸露的 e^{rx}。
    """

    title: str            # 例："Find the roots of the characteristic equation"
    latex: str = ""       # 該步驟的 LaTeX 內容（不含 $ 符號，範本會補上 $$）
    note: str = ""        # 補充說明（英文；內嵌數學用 $…$）


@dataclass
class Problem:
    """一道題目與它的完整解答。

    ``residual`` 是驗證閘門的核心：把標準答案代回原方程後應該恰為 0。
    它是可呼叫物件而非序列化欄位，因此不寫入資料庫（MVP 也不需要）。
    """

    template_id: str
    difficulty: int
    seed: int
    params: dict
    statement: str               # 題目的文字敘述（英文）
    statement_latex: str         # 題目的方程式（LaTeX）
    answer_latex: str            # 標準答案（LaTeX）
    answer_expr: sp.Expr | sp.Matrix
    steps: list[Step] = field(default_factory=list)
    residual: sp.Expr | sp.Matrix | None = field(default=None, repr=False)

    def residual_is_zero(self) -> bool:
        """驗證閘門：答案代回原方程後殘差是否為 0。"""
        if self.residual is None:
            return False
        r = sp.simplify(sp.expand(self.residual))
        if isinstance(r, sp.MatrixBase):
            return all(sp.simplify(c) == 0 for c in r)
        return r == 0


# --- 註冊表 ---------------------------------------------------------------

GenFn = Callable[[random.Random, int], Problem]


@dataclass
class Template:
    template_id: str
    name: str                          # 下拉選單顯示的名稱（英文）
    chapter: str                       # 章節分組（下拉選單的 optgroup，英文）
    difficulties: tuple[int, ...]
    fn: GenFn
    difficulty_notes: dict[int, str] = field(default_factory=dict)


REGISTRY: dict[str, Template] = {}


def register(
    template_id: str,
    name: str,
    chapter: str,
    difficulties: tuple[int, ...] = (1, 2, 3),
    difficulty_notes: dict[int, str] | None = None,
) -> Callable[[GenFn], GenFn]:
    """把一個生成函式註冊為可出題的模板。"""

    def deco(fn: GenFn) -> GenFn:
        if template_id in REGISTRY:
            raise ValueError(f"duplicate template id: {template_id}")
        REGISTRY[template_id] = Template(
            template_id=template_id,
            name=name,
            chapter=chapter,
            difficulties=difficulties,
            fn=fn,
            difficulty_notes=difficulty_notes or {},
        )
        return fn

    return deco


class GenerationError(RuntimeError):
    """在容許的嘗試次數內找不到夠漂亮的題目。"""


def generate(template_id: str, difficulty: int, seed: int | None = None) -> Problem:
    """出題的唯一對外入口。

    會重試若干組隨機參數，直到題目通過殘差檢查與漂亮度門檻為止
    （rejection sampling，見 PLAN.md §2.3）。
    """
    if template_id not in REGISTRY:
        raise KeyError(f"unknown topic: {template_id}")
    tpl = REGISTRY[template_id]
    if difficulty not in tpl.difficulties:
        raise ValueError(f"{template_id} does not support difficulty {difficulty}")

    if seed is None:
        seed = random.randrange(1, 2**31 - 1)

    rng = random.Random(seed)
    for _ in range(80):
        problem = tpl.fn(rng, difficulty)
        if problem is None:
            continue
        problem.seed = seed
        if problem.residual_is_zero():
            return problem
    raise GenerationError(
        f"could not generate a valid problem for {template_id} at difficulty {difficulty}"
    )


def list_templates() -> list[Template]:
    """依章節、代號排序的模板清單，供 UI 建立下拉選單。"""
    return sorted(REGISTRY.values(), key=lambda t: (t.chapter, t.template_id))
