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


def _is_zero_exact(expr) -> bool:
    """符號上恰為 0。驗證閘門唯一接受的答案——證不出來就當作沒過，換一組重抽。"""
    if expr is None:
        return True
    if isinstance(expr, sp.MatrixBase):
        return all(_is_zero_exact(c) for c in expr)
    return sp.simplify(sp.expand(expr)) == 0


@dataclass(frozen=True)
class Check:
    """判定「一個表達式是不是這題的解」所需的全部資訊。

    這是**出題引擎的驗證閘門**：`base.generate()` 用它把標準答案代回原方程，
    殘差不是 0 就換一組參數重抽。它是「進到學生眼前的題目 100% 有正確答案」
    這條承諾的實作，**每個 generator 都必須提供，不可省略**。

    > v0.4–v0.6 期間，`app/grader` 也用同一個物件驗證學生的答案（共用是為了杜絕
    > 「閘門與判分對同一題有不同標準」這種最難查的 bug）。判定已隨 D12 捨棄，
    > 但 `Check` 的角色一點都沒變——判分只是它的附帶用途，驗證閘門才是本業。

    刻意設計成**純資料**（picklable，不含 lambda／closure）。原本的理由是判定要
    pickle 進子行程，那個理由已經消失；仍然保持純資料，是因為它讓 `Check` 可序列化
    ——日後要做離線預生成（把題目存進資料庫）時直接就能用。

    純量 ODE 用 ``residual_expr``（一個含 ``unknown`` = y(x) 的算式，代入後
    ``doit()`` 就是殘差）；一階線性系統用 ``matrix``（A）與 ``forcing``（g）。
    """

    var: sp.Symbol                                  # 自變數（x 或 t，含 generator 的 assumptions）
    kind: str = "scalar"                            # "scalar" | "system"
    n_constants: int = 1                            # 通解需要的任意常數個數；IVP 為 0
    order: int = 1                                  # 純量 ODE 的階數（Wronskian 要微分到 order-1）
    unknown: sp.Expr | None = None                  # scalar：y(x)
    residual_expr: sp.Expr | None = None            # scalar：L[y] - g，含 unknown
    matrix: sp.Matrix | None = None                 # system：A
    forcing: sp.Matrix | None = None                # system：g(t)；齊次為 None
    ic_point: sp.Expr | None = None                 # 初值問題：t₀（None 表示求通解）
    ic_value: sp.Expr | sp.Matrix | None = None     # 初值問題：y(t₀)
    #: 高階初值問題的其餘初始條件，依序是 y'(t₀), y''(t₀), …（v0.24 新增）
    ic_derivative_values: tuple = ()
    linear: bool = True                             # L 對 y 是否線性（決定能否逐項診斷）

    @property
    def is_ivp(self) -> bool:
        return self.ic_point is not None

    @property
    def dim(self) -> int:
        return 1 if self.kind == "scalar" else self.matrix.shape[0]

    def residual_of(self, candidate):
        """把 candidate 代回原方程，回傳殘差（純量式或向量）。"""
        if self.kind == "scalar":
            return self.residual_expr.subs(self.unknown, candidate).doit()
        v = sp.Matrix(candidate)
        r = v.diff(self.var) - self.matrix * v
        if self.forcing is not None:
            r = r - self.forcing
        return r

    def ic_residual_of(self, candidate):
        """初值條件的殘差；不是初值問題則回傳 None。

        ``ic_derivative_values`` 非空時回傳一個向量（每一列一個條件），
        `_is_zero_exact` 對 Matrix 本來就是逐項檢查，所以呼叫端不必改。

        > **v0.24 為什麼加這一欄**（拉普拉斯的初值問題，階段 2A 的 2f）：
        > 在這之前，純量的初值問題只驗得了 $y(t_0)$。二階的初值問題有兩個條件，
        > 而 $y'(t_0)$ 沒有被驗到——閘門會對一個 $y'(0)$ 錯掉的答案說「通過」。
        > 這不是理論上的顧慮：反向構造是先挑答案再算 $y(t_0)$ 與 $y'(t_0)$，
        > 兩個值都由同一段程式算出來，**所以一個下標寫錯就會同時錯在答案與條件上，
        > 而殘差仍然是 0**。§2.1 原則二說閘門的預設必須是擋下來，
        > 少驗一個條件正是「預設放過去」。
        >
        > 刻意做成有預設值的新欄位而不是改 `ic_value` 的型別：既有四個 generator
        > 一行都不用動（§2.2.1 對 `Check` 的第一個取捨），而 `dataclass(frozen=True)`
        > 配 tuple 仍然是純資料、仍然可 pickle。
        """
        if not self.is_ivp:
            return None
        residuals = [candidate.subs(self.var, self.ic_point) - self.ic_value]
        for k, value in enumerate(self.ic_derivative_values, start=1):
            residuals.append(
                sp.diff(candidate, (self.var, k)).subs(self.var, self.ic_point) - value
            )
        if len(residuals) == 1:
            return residuals[0]
        return sp.Matrix(residuals)


@dataclass
class Problem:
    """一道題目與它的完整解答。

    ``check`` 是驗證閘門的核心：把標準答案代回原方程後殘差應恰為 0。
    它不寫入資料庫——題目由 (template_id, difficulty, seed) 即可完整重現。
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
    check: Check | None = field(default=None, repr=False)

    def residual_is_zero(self) -> bool:
        """驗證閘門：答案代回原方程（含初值條件）後殘差是否為 0。"""
        if self.check is None:
            return False
        if not _is_zero_exact(self.check.residual_of(self.answer_expr)):
            return False
        return _is_zero_exact(self.check.ic_residual_of(self.answer_expr))


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
