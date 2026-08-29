r"""奇偶性與係數消失（PLAN.md §2.10、階段 2B 的 2B4；課綱 W3）。

``template_id = "fourier.symmetry.parity"``

給 $f$，判斷它是偶函數、奇函數、還是兩者皆非，並說出哪一族 Fourier 係數
因此為 0。**不算任何係數。**

---

## 這個題型為什麼值得單獨存在

§2.10.3 把「判斷奇偶性」列為七步裡的第 2 步，並說那是**本題型最重要的一句
解說**——因為它直接讓一整族係數為 0，省掉一半的積分。而在全幅級數的題目裡，
那一步永遠被後面五步的積分蓋過去；學生真正練到的是分部積分，不是那個判斷。

把它切出來當一個題型，練的就只有那一件事。三十秒一題，可以連做十題。

## 它是本專案第一個 `answer_kind = "classification"` 的題型

答案是**一句判斷**，不是算式：

- `answer_expr` 是 `None`（沒有算式可以放）
- `check` 不是 `Check`（沒有方程可以代回去），也不是 `FourierCheck`
  （沒有宣稱的係數要交叉驗證），而是本檔的 `ParityCheck`

這正是 2B0 把 `Verifier` 泛化出來要接的第二種東西。⚠️ 連帶地，任何對
`answer_expr` 做事的地方（漂亮度、顯示形式一致性）都必須**明示地**跳過
這一種——「跳過」不可以是「`try/except` 剛好沒炸」（§2.2.1、規則 4）。

## 閘門：三件事，而第三件才是真正容易錯的那一件

1. 宣稱的標籤要與 `PiecewiseFn.parity()` **符號上**一致（第四層閘門）。
2. 宣稱為 0 的那一族，係數要**符號上恆為 0**——不是取樣為 0。
   $a_n = \frac{2((-1)^n-1)}{\pi n^2}$ 在所有偶數 $n$ 上都是 0，
   取樣法會對一個偶函數說「它是奇的」。
3. ⚠️ **宣稱「兩者皆非」時，兩族係數都必須真的不為 0。** 這一條看起來多餘，
   實際上它擋的是唯一一個會讓這個題型說謊的情況：一個既不奇也不偶、
   但某一族係數**碰巧**整族為 0 的 $f$。那時標準答案說「沒有任何係數消失」，
   而學生算出來會發現有一族全是 0——他是對的，題目是錯的。
   例如 $f$ 在 $(-L,L)$ 上等於 $x + c$ 這種、把常數項移掉之後就變成奇函數的，
   $a_n$（$n \ge 1$）會整族消失而 $a_0 \ne 0$。

## 為什麼**沒有**半波對稱（$f(x+L) = -f(x)$，只剩奇次諧波）

它是很自然的一個難度 3，教學價值也高。**沒做的理由是它需要第五個閘門**：
「只有奇次 $n$ 存活」這件事要驗的是 $a_{2m} = b_{2m} = 0$ 對所有 $m$
符號上成立，而那是一個對**子序列**的敘述，`FourierCheck` 的四層沒有一層
驗得了它。硬做的話會得到一個「宣稱半波對稱、而閘門其實沒看那件事」的題型，
那正是規則 4 說的靜默失敗。留給日後，連同它自己的那一層閘門一起做。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import sympy as sp

from ..base import Problem, Step, register
from . import core, series
from .core import Coefficients, PiecewiseFn, x

TEMPLATE_ID = "fourier.symmetry.parity"

HALF_PERIODS = (sp.Integer(1), sp.Integer(2), sp.pi)
COEFFS = (-3, -2, -1, 1, 2, 3)

DIFFICULTY_NOTES = {
    1: "A single power of $x$ on $(-L, L)$ — read the symmetry off the formula",
    2: "A two-piece definition — the symmetry has to be checked piece by piece",
    3: "Neither even nor odd — both families of coefficients survive",
}

#: 答案標籤 → 學生看到的那一句話（英文，介面語言）。
LABELS = {
    "even": "$f$ is even, so every $b_n = 0$ (a cosine series).",
    "odd": "$f$ is odd, so $a_0 = 0$ and every $a_n = 0$ (a sine series).",
    "none": ("$f$ is neither even nor odd, so no family of coefficients "
             "vanishes — all of $a_0$, $a_n$ and $b_n$ must be computed."),
}

ANSWER_LATEX = {
    "even": r"f(-x) = f(x) \quad\Longrightarrow\quad b_n = 0 \;\; (n \ge 1)",
    "odd": r"f(-x) = -f(x) \quad\Longrightarrow\quad a_0 = 0,\; a_n = 0 \;\; (n \ge 1)",
    "none": r"f(-x) \ne f(x) \;\text{ and }\; f(-x) \ne -f(x)"
            r"\quad\Longrightarrow\quad a_0,\, a_n,\, b_n \ne 0",
}


# --- 閘門 -------------------------------------------------------------------


@dataclass(frozen=True)
class ParityCheck:
    """`Verifier` 協定的第三個實作。三件事，見模組檔頭。"""

    fn: PiecewiseFn
    claimed: str                      # "even" | "odd" | "none"
    coefficients: Coefficients

    def verify(self, problem) -> tuple[bool, str]:
        actual = self.fn.parity()
        if actual != self.claimed:
            return False, f"奇偶性標錯：宣稱 {self.claimed}，符號上是 {actual}"
        c = self.coefficients
        if self.claimed == "odd" and (c.a0 != 0 or c.an != 0):
            return False, f"宣稱奇函數，但 a_0={c.a0}、a_n={c.an}"
        if self.claimed == "even" and c.bn != 0:
            return False, f"宣稱偶函數，但 b_n={c.bn}"
        if self.claimed == "none":
            # 見檔頭第 3 點：這一條擋的是「標準答案說沒有係數消失，
            # 而學生算出來發現有一族全是 0」。
            if c.an == 0 or c.bn == 0 or (c.an == 0 and c.a0 == 0):
                return False, (
                    f"宣稱兩者皆非，但有一族係數整族為 0（a_n={c.an}, b_n={c.bn}）"
                )
        return True, ""


# --- 函數族 -----------------------------------------------------------------


def _family_d1(rng: random.Random) -> tuple[PiecewiseFn, str]:
    """一項多項式，奇偶性直接從公式讀得出來。"""
    L = rng.choice(HALF_PERIODS)
    c = rng.choice(COEFFS)
    if rng.random() < 0.5:
        return PiecewiseFn.build([(c * x ** rng.choice((1, 3)), -L, L)], L), "odd"
    d = rng.choice((-3, -2, -1, 1, 2, 3))
    return PiecewiseFn.build([(c * x**2 + d, -L, L)], L), "even"


def _family_d2(rng: random.Random) -> tuple[PiecewiseFn, str] | None:
    """兩段，斷點在 $0$，由延拓建出來——所以奇偶性要逐段檢查才看得出來。

    ⚠️ **兩段相同要重抽。** 那時題目其實是一條式子，卻印成一個兩行的
    `cases` 區塊——難度掉回 1，而且看起來像是程式印壞了。
    這是本輪人工審題（§2.8）唯一抓到的一件事，而它**不會讓任何測試變紅**：
    每一個數學符號都是對的。
    """
    L = rng.choice(HALF_PERIODS)
    right = rng.choice(COEFFS) * x + rng.choice((-3, -2, -1, 0, 1, 2, 3))
    kind = rng.choice(("sine", "cosine"))
    mirrored = right.subs(x, -x)
    left = -mirrored if kind == "sine" else mirrored
    if sp.expand(left - right) == 0:
        return None
    fn = PiecewiseFn.build([(left, -L, 0), (right, 0, L)], L)
    return fn, ("odd" if kind == "sine" else "even")


def _family_d3(rng: random.Random) -> tuple[PiecewiseFn, str] | None:
    """兩者皆非。閘門的第 3 點會把「碰巧有一族消失」的那些擋回來重抽。"""
    L = rng.choice(HALF_PERIODS)
    if rng.random() < 0.5:
        poly = rng.choice(COEFFS) * x**2 + rng.choice((-2, -1, 1, 2)) * x
        return PiecewiseFn.build([(poly, -L, L)], L), "none"
    left = rng.choice(COEFFS) * x + rng.choice((-2, -1, 0, 1, 2))
    right = rng.choice(COEFFS) * x**2 + rng.choice((-2, -1, 0, 1, 2))
    return PiecewiseFn.build([(left, -L, 0), (right, 0, L)], L), "none"


# --- 組題 -------------------------------------------------------------------

STATEMENT = (
    "Decide whether the following $2L$-periodic function is even, odd, or "
    "neither, and state which family of Fourier coefficients vanishes as a "
    "result. Do not compute any coefficients."
)


@register(
    TEMPLATE_ID,
    name="Fourier Coefficients: Symmetry",
    chapter=series.CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    built = {1: _family_d1, 2: _family_d2, 3: _family_d3}[difficulty](rng)
    if built is None:
        return None
    fn, claimed = built

    # 閘門要的係數。這裡算它們**不是為了印出來**——題目明說不要算係數——
    # 而是為了讓「哪一族消失」這個宣稱有東西可以驗。
    c = core.coefficients_of(fn)

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params={
            "half_period": sp.srepr(fn.half_period),
            "pieces": [[sp.srepr(p.poly), sp.srepr(p.lo), sp.srepr(p.hi)]
                       for p in fn.pieces],
            "n_pieces": len(fn.pieces),
            "parity": claimed,
        },
        statement=STATEMENT,
        statement_latex="f(x) = " + fn.cases_latex(),
        answer_latex=ANSWER_LATEX[claimed],
        # ⚠️ classification 的答案是一句判斷，沒有算式。
        answer_expr=None,
        answer_kind="classification",
        steps=_steps(fn, claimed),
        check=ParityCheck(fn=fn, claimed=claimed, coefficients=c),
    )


def _steps(fn: PiecewiseFn, claimed: str) -> list[Step]:
    L = fn.half_period
    reflected = fn.reflected()
    rows = []
    for p in reflected.pieces:
        rows.append(r"%s, & %s < x < %s" % (
            sp.latex(p.poly), sp.latex(p.lo), sp.latex(p.hi)))
    mirror_latex = (r"f(-x) = \begin{cases} " + r" \\ ".join(rows) + r" \end{cases}"
                    if len(rows) > 1
                    else r"f(-x) = %s, \quad %s < x < %s" % (
                        sp.latex(reflected.pieces[0].poly),
                        sp.latex(reflected.pieces[0].lo),
                        sp.latex(reflected.pieces[0].hi)))
    return [
        Step(
            "Write down $f(-x)$",
            mirror_latex,
            "Replace $x$ by $-x$ everywhere — in the formula and also in the "
            "interval each piece is valid on. Forgetting to flip the intervals "
            "is the usual mistake, and it is invisible when $f$ is given by a "
            "single formula.",
        ),
        Step(
            "Compare $f(-x)$ with $f(x)$ and with $-f(x)$",
            _comparison_latex(claimed),
            "Both comparisons are needed. Checking only $f(-x) = f(x)$ tells "
            "you that $f$ is not even; it does not tell you that $f$ is odd.",
        ),
        Step(
            "Look at the integrand of each coefficient",
            _vanishing_latex(claimed, L),
            _vanishing_note(claimed),
        ),
        # ⚠️ 最後一步的 `latex` **必須逐字等於 `answer_latex`**：
        # `test_steps_are_complete` 對 classification 的檢查就是這件事，
        # 而它擋的是「答案與最後一步各寫一遍然後漂移」。
        Step(
            "State the conclusion",
            ANSWER_LATEX[claimed],
            LABELS[claimed],
        ),
    ]


def _comparison_latex(claimed: str) -> str:
    if claimed == "odd":
        return r"f(-x) = -f(x) \quad\text{for all } x"
    if claimed == "even":
        return r"f(-x) = f(x) \quad\text{for all } x"
    return r"f(-x) \ne f(x) \quad\text{and}\quad f(-x) \ne -f(x)"


def _vanishing_latex(claimed: str, L: sp.Expr) -> str:
    if claimed == "odd":
        return r"a_0 = 0, \qquad a_n = %s = 0" % core.coefficient_formula_latex(L, "cos")
    if claimed == "even":
        return r"b_n = %s = 0" % core.coefficient_formula_latex(L, "sin")
    return r"a_0 \ne 0, \qquad a_n \ne 0, \qquad b_n \ne 0"


def _vanishing_note(claimed: str) -> str:
    if claimed == "none":
        return (
            "Nothing is free here. Knowing that is still worth the thirty "
            "seconds it took: it tells you that both integrals genuinely have "
            "to be done, rather than leaving you wondering halfway through "
            "whether you have missed a shortcut."
        )
    partner = "cosine" if claimed == "odd" else "sine"
    return (
        f"An odd integrand over a symmetric interval integrates to zero. Here "
        f"$f$ is {claimed} and the {partner} factor is "
        f"{'even' if claimed == 'odd' else 'odd'}, so the product is odd and the "
        "whole family vanishes — without computing a single integral. That is "
        "half of the work in a full Fourier series problem."
    )
