r"""全幅 Fourier 級數（PLAN.md §2.10、階段 2B 的 2B2；課綱 W3）。

``template_id = "fourier.series.full_range"``

給 $f$ 在 $(-L, L)$ 上的定義（以 $2L$ 為週期延拓），求它的 Fourier 級數。

---

## 三個難度是三個**結構上的**旋鈕，不是「數字大一點」

| 難度 | 分段數 | $L$ | 這一格在練什麼 |
|---|---|---|---|
| 1 | 1（整段一條多項式） | $\pi$ | **奇偶性**：族內每一題不是奇就是偶，所以只要算一族係數 |
| 2 | 2（斷點在 $0$） | $\pi$ | 三族都要算；一半的題目有跳點，於是收斂值要討論 |
| 3 | 2 或 3（斷點在 $0$ 或 $\pm L/2$） | $1$、$2$ 或 $\pi$ | $\frac{n\pi x}{L}$ 真的要處理；三段的那些會生出 $\sin\frac{n\pi}{2}$ |

⚠️ **難度 1 只算一族係數這件事是結構決定的，不是事後篩選出來的**（§2.10.2 的
最後一段）。族裡只放單項式 $cx$（奇）與 $cx^2 + d$（偶），所以「難度 1 一定
只有一族」是抽樣前就成立的性質——靠事後篩選的話，某些 seed 會抽很久甚至抽不到。

## 為什麼難度 3 才允許 $\sin\frac{n\pi}{2}$

斷點在 $\pm L/2$ 的分段函數，係數必然含 $\sin\frac{n\pi}{2}$ 或
$\cos\frac{n\pi}{2}$——它們要按 $n \bmod 4$ 分四種情形討論。§2.10.2 說這
「在難度 3 有教學價值，但不能隨機跑出來」，所以 `ugliness_in_n()` 預設擋掉它，
只有難度 3 明示打開。

⚠️ **連帶的代價**：Parseval（第二層閘門）對這些係數收不出封閉形式，於是那些題目
只有三層閘門。這不是被容忍的意外，是 §6 驗收標準要求記錄的那個比例——
`tests/test_generators.py::test_how_often_parseval_is_skipped` 把它印出來。

## 為什麼**不做** $e^{ax}$

§2.10.2 把 $e^{ax}$ 列為「刻意保留的特例」。落地時實測後拿掉，理由是它讓
第二層閘門變成一個**看起來有跑、實際上沒有用**的東西：$a_n$ 的分母是
$n^2 + a^2L^2/\pi^2$，Parseval 的級數 `doit()` 回傳的是一個帶 $i$、
帶 $\tanh\pi$ 的十行表達式（本輪實測），`simplify` 化不到 0 也不報錯。
那會逼出一個「Parseval 這一層對 $e^{ax}$ 特別放寬」的分支，
而規則 4 說不做無聲降級。**寧可少一個函數族。**
（多項式族已經涵蓋課綱 W3 的全部教學內容；$e^{ax}$ 練的是「積兩次繞回自己」
那個技巧，它更適合出現在 Laplace 那一組。）
"""

from __future__ import annotations

import random

import sympy as sp

from ..base import Problem, Step, register
from ..pretty import is_pretty_in_n
from . import core
from .core import N_INT, Coefficients, FourierCheck, PiecewiseFn, ResonantIntegral, x

TEMPLATE_ID = "fourier.series.full_range"
CHAPTER = "Fourier Series"

#: 各段多項式的係數白名單（§2.3 第二層）。
COEFFS = (-3, -2, -1, 1, 2, 3)
#: 難度 3 的半週期。$\pi$ 也留著，否則三段的那些題目全都得用有理數 $L$。
HALF_PERIODS_D3 = (sp.Integer(1), sp.Integer(2), sp.pi)

DIFFICULTY_NOTES = {
    1: "One polynomial on the whole interval, $L = \\pi$ — one family of coefficients",
    2: "Two pieces meeting at $x = 0$, $L = \\pi$ — usually all three families",
    3: "Two or three pieces and a general half-period $L$",
}

#: 係數的漂亮度上限。與 `ugliness()` 的門檻**沒有可比性**（見 `pretty.py`）。
UGLINESS_LIMIT = {1: 12, 2: 20, 3: 30}


# --- 函數族 -----------------------------------------------------------------


def _family_d1(rng: random.Random) -> tuple[PiecewiseFn, str]:
    """一段多項式，$L = \\pi$，而且**結構上**不是奇就是偶。"""
    L = sp.pi
    c = rng.choice(COEFFS)
    if rng.random() < 0.5:
        return PiecewiseFn.build([(c * x, -L, L)], L), "odd"
    d = rng.choice((-2, -1, 0, 1, 2))
    return PiecewiseFn.build([(c * x**2 + d, -L, L)], L), "even"


def _linear(rng: random.Random) -> sp.Expr:
    """$cx + d$，$c$ 可以是 0（於是這一段是常數）。"""
    c = rng.choice((-2, -1, 0, 0, 1, 2))
    d = rng.choice((-3, -2, -1, 0, 1, 2, 3))
    return c * x + d


def _family_d2(rng: random.Random) -> PiecewiseFn:
    """兩段，斷點在 $0$，$L = \\pi$。"""
    L = sp.pi
    left, right = _linear(rng), _linear(rng)
    if sp.expand(left - right) == 0:      # 兩段一樣就退化成難度 1
        return None
    return PiecewiseFn.build([(left, -L, 0), (right, 0, L)], L)


def _family_d3(rng: random.Random) -> PiecewiseFn:
    r"""兩段（可含二次項）或三段（斷點在 $\pm L/2$）。

    ⚠️ **二次項那一支刻意排除 $L = \pi$。** $L=\pi$ 配上 $x^2$ 會讓係數長出
    $\pi^2$（例如 $\frac{(-1)^n\pi(3\pi - 1) + \dots}{\pi n}$）——每一個字元都對，
    而沒有課本會把一個 $\pi^2$ 留在 $b_n$ 的分子裡。這是本輪人工審題
    （§2.8）抓到的兩件事之一，`ugliness_in_n()` 抓不到它
    （它只看 $n$ 的冪次與四分之一週期因子，$\pi$ 的冪次不在它的判準裡）。
    """
    if rng.random() < 0.5:
        L = rng.choice((sp.Integer(1), sp.Integer(2)))
        left = rng.choice(COEFFS) * x**2 + rng.choice((-1, 0, 1))
        right = _linear(rng)
        return PiecewiseFn.build([(left, -L, 0), (right, 0, L)], L)
    L = rng.choice(HALF_PERIODS_D3)
    outer = rng.choice((-2, -1, 0, 1, 2))
    inner = _linear(rng)
    if sp.expand(inner - outer) == 0:
        return None
    return PiecewiseFn.build(
        [(sp.Integer(outer), -L, -L / 2), (inner, -L / 2, L / 2),
         (sp.Integer(outer), L / 2, L)], L)


# --- 組題 -------------------------------------------------------------------


def answer_latex_of(fn: PiecewiseFn, c: Coefficients) -> str:
    r"""級數本身，把 $a_0$、$a_n$、$b_n$ 都代進去。"""
    L = fn.half_period
    terms = []
    if c.an != 0:
        terms.append(r"%s\,%s" % (_wrap(c.an), core.basis_latex(L, "cos")))
    if c.bn != 0:
        terms.append(r"%s\,%s" % (_wrap(c.bn), core.basis_latex(L, "sin")))
    body = " + ".join(terms) if terms else "0"
    if len(terms) > 1:
        body = r"\left[%s\right]" % body
    head = ""
    constant = core.constant_term(c.a0)
    if constant != 0:
        head = sp.latex(constant) + " + "
    if not terms:
        return r"f(x) \sim %s" % (sp.latex(constant))
    return r"f(x) \sim %s\sum_{n=1}^{\infty} %s" % (head, body)


def _wrap(expr: sp.Expr) -> str:
    r"""係數要不要括起來。

    兩種情況要括：**相加的**（否則 $\cos$ 看起來只乘到最後一項）與
    **負的**（$\sum -\frac{8(-1)^n}{n^2}\cos nx$ 那個減號緊跟在 $\sum$ 後面，
    看起來像是「減去整個級數」）。
    """
    latex = sp.latex(expr)
    if isinstance(expr, sp.Add) or expr.could_extract_minus_sign():
        return r"\left(%s\right)" % latex
    return latex


def build_problem(
    fn: PiecewiseFn,
    difficulty: int,
    params: dict,
    statement: str,
    template_id: str = TEMPLATE_ID,
) -> Problem | None:
    """把一個 `PiecewiseFn` 變成一道完整的題目。`half_range.py` 也用這一支。"""
    try:
        c = core.coefficients_of(fn)
    except ResonantIntegral as exc:
        # 分段多項式不會走到這裡（見 core 檔頭「落差 1」），但擴族時會。
        core.logger.info("係數積分不封閉，重抽：%s", exc)
        return None

    allow_quarter = difficulty == 3
    limit = UGLINESS_LIMIT[difficulty]
    for claim in (c.an, c.bn):
        if not is_pretty_in_n(claim, N_INT, limit, allow_quarter):
            return None

    parity = fn.parity()
    at_zero = c.an.subs(N_INT, 0)
    needs_separate = bool(at_zero.has(sp.zoo, sp.nan)) or at_zero.is_finite is False

    answer = answer_latex_of(fn, c)
    steps = _steps(fn, c, parity, needs_separate, answer)

    return Problem(
        template_id=template_id,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex="f(x) = " + fn.cases_latex(),
        answer_latex=answer,
        answer_expr=sp.Tuple(c.a0, c.an, c.bn),
        answer_kind="coefficients",
        steps=steps,
        check=FourierCheck(
            fn=fn,
            coefficients=c,
            parity=parity,
            a0_needs_separate_formula=needs_separate,
        ),
    )


def _steps(fn: PiecewiseFn, c: Coefficients, parity: str,
           needs_separate: bool, answer: str) -> list[Step]:
    """§2.10.3 的七步，按 §7 #22「一步 = 課本會單獨寫一行的動作」再拆細。

    每一族係數拆成「列式並分部積分」與「用 $\\cos n\\pi = (-1)^n$ 化簡」兩步，
    因為那是課本上真的分成兩行寫的兩件事；一族係數整族消失時則收成一步。
    """
    L = fn.half_period
    period = sp.latex(2 * L)
    steps = [
        Step(
            "Identify the period and the half-period",
            r"2L = %s, \qquad L = %s" % (period, sp.latex(L)),
            "Everything downstream — the basis functions, the limits of "
            "integration, the factor in front — is fixed by $L$, so it is worth "
            "writing down before anything else.",
        ),
        Step(
            "Check the symmetry of $f$",
            _parity_latex(parity),
            core.parity_note(parity),
        ),
        Step(
            "Write down the coefficient formulas for this $L$",
            r"a_n = %s, \qquad b_n = %s" % (
                core.coefficient_formula_latex(L, "cos"),
                core.coefficient_formula_latex(L, "sin")),
            "These are the definitions with $L$ already substituted. The "
            "$\\frac{1}{L}$ in front is what makes the basis functions "
            "orthonormal on an interval of length $2L$.",
        ),
    ]

    if parity == "odd":
        steps.append(core.vanishing_step("odd"))
    else:
        steps.append(core.a0_step(fn, c, needs_separate))
        steps.extend(core.coefficient_steps(fn, c, "cos"))

    if parity == "even":
        steps.append(core.vanishing_step("even"))
    else:
        steps.extend(core.coefficient_steps(fn, c, "sin"))

    steps.append(core.assembly_step(fn, c, answer))
    return steps


def _parity_latex(parity: str) -> str:
    if parity == "odd":
        return r"f(-x) = -f(x) \quad \Rightarrow \quad f \text{ is odd}"
    if parity == "even":
        return r"f(-x) = f(x) \quad \Rightarrow \quad f \text{ is even}"
    return r"f(-x) \ne \pm f(x) \quad \Rightarrow \quad f \text{ is neither}"


STATEMENT = (
    "Find the Fourier series of the following function, which is extended "
    "periodically with period $2L$."
)


@register(
    TEMPLATE_ID,
    name="Fourier Series (Full Range)",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    if difficulty == 1:
        fn, _ = _family_d1(rng)
    elif difficulty == 2:
        fn = _family_d2(rng)
    else:
        fn = _family_d3(rng)
    if fn is None:
        return None
    params = {
        "half_period": sp.srepr(fn.half_period),
        "pieces": [[sp.srepr(p.poly), sp.srepr(p.lo), sp.srepr(p.hi)]
                   for p in fn.pieces],
        "n_pieces": len(fn.pieces),
        "parity": fn.parity(),
        "has_jump": fn.has_jump,
    }
    return build_problem(fn, difficulty, params, STATEMENT)
