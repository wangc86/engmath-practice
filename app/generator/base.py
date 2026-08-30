"""出題引擎的核心資料結構與註冊表。

設計原則（見 PLAN.md §2.1）：
1. 反向構造優先於正向求解 —— 先決定答案長什麼樣，再倒推題目。
2. SymPy 是驗證閘門（gate），不是生成器 —— 每題出廠前都要通過殘差檢查。
3. 逐步解答由模板自己寫，中間量由 SymPy 算。

新增題型只要在 ``app/generator/`` 底下加一個檔案，用 ``@register(...)``
註冊生成函式，UI 下拉選單與 pytest 參數化測試都會自動撿到。

---

## v0.25（工作項 2B0）：驗證閘門泛化成一個協定

在這之前，`generate()` 直接讀 `Check.residual_expr` 算殘差——也就是說
**「驗證」這個概念被寫死成「代回方程」**。Fourier 沒有方程可以代回去
（PLAN §2.10.1），所以那個假設要拆掉。

拆的方式是 §2.2.1 規劃的 `Verifier` 協定：`generate()` 只呼叫
`problem.verify_answer()`，不知道也不在乎底下是殘差、是四層閘門、
還是一個符號上的奇偶性檢查。

**既有四個 generator 一行都沒有動**，這是刻意的——2B0 是加東西，
不該讓已經在跑的東西承擔風險。

---

## v0.26（工作項 2B7）：`assets` 補上了，連同它的第一個使用者

2B0 刻意把 `Problem.assets` 延後（理由見上一版的這段 docstring 與 PLAN
§2.2.1 的落地紀錄：白名單與洩題測試在沒有產出者的時候會**恆綠而且什麼都沒驗**）。
相圖（2B6）落地之後那個前提消失了，所以這一輪把三條約定一起做完：

1. **鍵是有限的白名單**（`ASSET_KEYS`），而且**在 `Problem` 建構的當下就檢查**
   ——不是在範本裡。範本渲染 asset 一定要 `|safe`，而 `|safe` 是 XSS 的門；
   門的守衛放在「東西被造出來」那一刻，比放在「東西被印出來」那一刻早一步。
2. **一律渲染在 `<details>` 裡**（`_solution.html`），由 `tests/test_web.py`
   的洩題測試盯著。
3. **不進資料庫、不參與重現**——它由 `params` 完全決定，`generate()` 重跑即得。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, runtime_checkable

import sympy as sp

from ..logging_setup import get_logger

logger = get_logger(__name__)

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


#: 答案是哪一種東西。決定「哪些顯示形式與漂亮度檢查適用」。
#:
#: * ``expression``     —— 一個算式或向量（既有四個 ODE 題型 + Laplace）
#: * ``coefficients``   —— 一組以 $n$ 為參數的封閉形式（Fourier 級數）
#: * ``classification`` —— 一句判斷，`answer_expr` 是 `None`（奇偶性；日後的平衡點分類）
#:
#: > **與 PLAN §2.2.1 那張表的一處落差（v0.25 落地時決定）。** 規劃寫的是
#: > 五個值：`general` / `ivp` / `vector` / `coefficients` / `classification`。
#: > 落地時把前三個併成一個 `expression`，理由是**前三者是可以從 `Check` 推出來的**
#: > （`check.is_ivp`、`check.kind == "system"`），而那張表列出的三個使用者
#: > （顯示形式檢查、漂亮度、驗證路徑）**對這三者的處理完全相同**。
#: > 存下來就是同一個事實的第二份副本，而兩份副本會漂移——一個把初值條件
#: > 拿掉卻忘了改 `answer_kind` 的改動不會讓任何東西變紅。
#: > 真正需要分辨的界線只有兩條：**有沒有算式**（classification 沒有）、
#: > **算式是對 $x$ 還是對 $n$**（coefficients 是對 $n$，`ugliness()` 的門檻不適用）。
AnswerKind = Literal["expression", "coefficients", "classification"]

#: `Problem.assets` 允許的鍵，**一份可以逐條檢查的清單**（PLAN §2.2.1 第一條）。
#:
#: ⛔ **這不是型別檢查，是安全邊界。** 範本要用 `|safe` 才印得出一段 SVG，
#: 而 `|safe` 關掉的正是 Jinja 唯一那道 XSS 防線。因此範本能認得的鍵必須是
#: 一份**有限的、逐條看過的**清單——不能讓 generator 隨手發明一個鍵，
#: 然後靠寫範本的人記得去審它。
#:
#: 加一個新鍵的成本刻意留得很高：要改這裡、改 `_solution.html`（明示的
#: `{% if %}`，不是 for 迴圈），還要在 `tests/test_web.py` 加一條對應的
#: 洩題測試。**那個成本就是它的功能。**
ASSET_KEYS: frozenset[str] = frozenset({"phase_portrait_svg"})


@runtime_checkable
class Verifier(Protocol):
    """**驗證閘門的共同介面**（PLAN.md §2.2.1 第三點）。

    `base.generate()` 對每一題呼叫 `check.verify(problem)`，回傳
    `(通過與否, 原因)`——**原因是給 log 看的**（規則 4：不許靜默失敗）。

    ---

    ## 為什麼是一個協定，而不是在 `Check` 上加十個 `None` 欄位

    Fourier 需要的欄位（$f$ 的分段、半週期 $L$、宣稱的 $a_0/a_n/b_n$、
    奇偶性）與 `Check` 現有的 12 個欄位**沒有一個重疊**。硬塞成同一個
    dataclass 會得到一個任何時候都有一大半是 `None` 的型別，而讀錯欄位的
    症狀是「所有題目都通過閘門」——**失敗的方向是錯的**。閘門的預設必須是
    擋下來，不是放過去。

    ## 為什麼回傳原因字串而不是只回 bool

    出題是拒絕抽樣，重抽本來就正常；但「某個 (題型, 難度) 一直重抽到上限」
    是需要診斷的事，而 Fourier 的失敗原因有四種（係數在某個 $n$ 對不上、
    Parseval 不合、部分和偏離、奇偶性標錯）。只回 bool 等於把診斷資訊丟掉。

    ## 為什麼實作者仍然是純資料

    `verify()` 是方法不是欄位，所以 `Check`／`FourierCheck` 仍然可以是
    frozen dataclass、仍然不含 lambda、仍然可 pickle（§2.2 註記的第二個理由：
    日後離線預生成用得到）。**不要為了方便在 Check 裡塞一個 callable。**

    ---

    ⛔ **唯一不可妥協的一點**：泛化之後，「進到學生眼前的題目 100% 有正確答案」
    這條承諾必須對**每一種** `answer_kind` 都成立。因此 `generate()` 在
    `check is None` 時**直接拋例外**，不是視為通過——新增一個沒有驗證器的題型，
    等於在這條承諾上開一個洞，而那個洞是安靜的。
    """

    def verify(self, problem: "Problem") -> tuple[bool, str]:  # pragma: no cover - 協定
        ...


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

    def verify(self, problem: "Problem") -> tuple[bool, str]:
        """`Verifier` 協定的實作（v0.25、2B0）。**行為與 v0.24 逐字相同。**

        以前這段邏輯寫在 `Problem.residual_is_zero()` 裡，`generate()` 直接呼叫它。
        搬到這裡之後，`generate()` 不再知道「驗證 = 算殘差」——它只知道
        「問 check 過不過」，於是 Fourier 那條完全不同的路才接得上去。
        既有四個 generator 一行都不用動（§2.2.1 的第一個取捨）。
        """
        residual = self.residual_of(problem.answer_expr)
        if not _is_zero_exact(residual):
            return False, f"殘差不為 0：{sp.simplify(residual)}"
        ic_residual = self.ic_residual_of(problem.answer_expr)
        if not _is_zero_exact(ic_residual):
            return False, f"初值條件的殘差不為 0：{ic_residual}"
        return True, ""


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
    answer_expr: sp.Expr | sp.Matrix | None
    steps: list[Step] = field(default_factory=list)
    check: Verifier | None = field(default=None, repr=False)
    #: 答案是哪一種東西（v0.25、2B0）。預設 ``"expression"`` 讓既有五個 generator
    #: 一行都不用動；Fourier 用 ``"coefficients"``，奇偶性判斷用 ``"classification"``。
    #:
    #: ⚠️ **`"classification"` 的 `answer_expr` 是 `None`**，因為答案是一句判斷，
    #: 沒有算式。任何對 `answer_expr` 做事的地方（漂亮度、顯示形式一致性）
    #: 都必須**明示地**跳過這一種，不可以靠 `try/except` 剛好沒炸（規則 4）。
    answer_kind: AnswerKind = "expression"
    #: 非 LaTeX 的附加呈現（v0.26、2B7）。目前只有 `"phase_portrait_svg"`。
    #:
    #: ⛔ **鍵必須在 `ASSET_KEYS` 裡**（`__post_init__` 檢查），
    #: 而值一律渲染在 `<details>` 內（D13、§2.11.1）——一張鞍點圖等於
    #: 直接告訴學生兩個特徵值異號。
    #:
    #: **不進資料庫**：它由 `params` 完全決定，`generate()` 重跑即得，
    #: 存起來只會多一份會過期的副本（§2.2.1 第三條）。
    assets: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """白名單檢查。**在建構的當下拋，不是在渲染的當下。**

        寫成例外而不是「不認得的鍵就忽略」是刻意的：忽略是靜默的（規則 4），
        而它靜默失敗的樣子是「圖沒有出現」——而寫程式的人多半是在
        `-n 1` 的樣本上看一眼就過去了。
        """
        unknown = set(self.assets) - ASSET_KEYS
        if unknown:
            raise ValueError(
                f"{self.template_id} 用了不在白名單裡的 asset 鍵：{sorted(unknown)}；"
                f"允許的是 {sorted(ASSET_KEYS)}。新增一個鍵要同時改 base.ASSET_KEYS、"
                "app/templates/_solution.html 與 tests/test_web.py 的洩題測試。"
            )

    def verify_answer(self) -> tuple[bool, str]:
        """驗證閘門的唯一入口：問 `check` 過不過，並把原因帶回來。

        ⚠️ **`check is None` 是失敗，不是通過。** 這是 §2.2.1 那句
        「唯一不可妥協」的落點——沒有驗證器的題型必須進不了學生眼前。
        """
        if self.check is None:
            return False, "這一題沒有驗證器（check is None）"
        return self.check.verify(self)

    def residual_is_zero(self) -> bool:
        """向後相容的薄殼：`verify_answer()` 的第一個回傳值。

        名字保留是因為 README 的「新增一個題型」與既有測試都用它；
        但**新的程式碼請用 `verify_answer()`**——對 Fourier 而言
        「殘差」這個詞根本不適用（沒有方程可以代回去），繼續用這個名字
        會讓人以為 `check.residual_of()` 一定存在。
        """
        return self.verify_answer()[0]


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
    reasons: list[str] = []
    for _ in range(80):
        problem = tpl.fn(rng, difficulty)
        if problem is None:
            continue
        problem.seed = seed
        ok, reason = problem.verify_answer()
        if ok:
            return problem
        # 重抽本身是正常的（拒絕抽樣），所以這裡是 DEBUG 不是 WARNING。
        # 但**原因一定要留下來**：一個 (題型, 難度) 抽到上限時，
        # 下面那則 ERROR 要說得出它是為什麼過不了（規則 4）。
        reasons.append(reason)
        logger.debug("出題重抽 %s d%s：%s", template_id, difficulty, reason)
    logger.error(
        "出題失敗 %s d%s seed=%s，%d 次嘗試都沒過閘門。最後五個原因：%s",
        template_id, difficulty, seed, len(reasons), reasons[-5:],
    )
    raise GenerationError(
        f"could not generate a valid problem for {template_id} at difficulty {difficulty}"
    )


def list_templates() -> list[Template]:
    """依章節、代號排序的模板清單，供 UI 建立下拉選單。"""
    return sorted(REGISTRY.values(), key=lambda t: (t.chapter, t.template_id))
