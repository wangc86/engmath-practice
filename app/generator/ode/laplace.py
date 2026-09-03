r"""拉普拉斯變換（PLAN.md §2.4(g)、階段 2A 的 2f；課綱 W9）。

本檔註冊**兩個**題型：

- ``ode.laplace.transform`` — 正變換與反變換（定義、線性、表、部分分式、兩個位移定理）
- ``ode.laplace.ivp``       — 用拉普拉斯變換解初值問題

課綱 W9 的敘述是「定義與性質；如何把時域的微積分運算映射成 s 域的代數運算」，
兩件事各對應一個題型：前者練的是**表與性質本身**，後者練的是**那個映射的用途**。

---

## 為什麼是兩個題型而不是一個

一個題型只有三個難度，而 W9 要練的東西至少有五樣（表、線性、部分分式、
兩個位移定理、導數的變換）。硬塞進三格的後果是每一格都變成大雜燴，
而難度階梯會失去意義——難度 2 與難度 3 的差別會變成「題目比較長」。

切成兩個之後，兩條階梯各自單調：`transform` 沿「要用到幾條性質」上升，
`ivp` 沿「反變換有多難」上升。

## 為什麼**沒有**第三個「初值／終值定理」題型

那種題目的答案是一個數字，而不是一個算式。`Check` 驗的是「把答案代回某個
方程，殘差為 0」——一個數字沒有方程可以代回去，要驗它就得走 §2.2.1 規劃的
`Verifier` 協定，而那是階段 2B 的 2B0，不在 2f 的範圍裡。

**折衷**：初值定理改成 `ivp` 每一題的**最後一步**（"Check with the initial
value theorem"）。它在那裡的價值其實更高——它是一個學生可以自己做的驗算，
而不是又一道要交的題目。終值定理**刻意不放**：它有前提（極點都要在左半平面），
一個「有時候出現、有時候不出現」的步驟教出來的東西是錯的，而每次都出現又會
在前提不成立時說謊。

## 為什麼**沒有**脈衝（δ 函數）的題型

§2.6 的難度表寫「步階／脈衝函數」。步階做了，脈衝**沒有做，而且不是漏掉**：

$\delta(t-a)$ 外力會讓 $y'$ 在 $t=a$ 跳一階，於是 $y''$ 裡有一個真的
$\delta$，殘差必須「$\delta$ 對得起來」才是 0。下面把答案改寫成
`Piecewise` 的那個技巧在這裡**會給出錯的答案**——`Piecewise` 的微分只微分
各分支、直接忽略跳躍，於是那個 $\delta$ 會安靜地消失，殘差照樣是 0，
而閘門會對一個錯的答案說通過。**這正是規則 4 說的那種靜默失敗**，
所以脈衝這一格留白，不是用一個驗不了的閘門把它填掉。

---

## 驗證閘門：三種答案，三條路（PLAN.md §2.10 的核心認識）

§2.10 說閘門的本質是「用一條與生成路徑獨立的路徑重算」。這裡三個路徑的
獨立程度**不一樣**，寫在這裡而不是假裝它們一樣強：

| 題型 | 生成路徑 | 閘門路徑 | 有多獨立 |
|---|---|---|---|
| `ivp` | 先挑答案 $y(t)$，再倒推 ODE 係數與初值 | 把 $y$ 代回 ODE 算殘差 + 逐一驗初值 | **完全獨立**。閘門連一個拉普拉斯的函式都沒有呼叫，它只做微分與代入 |
| `transform`（正） | 本檔案手寫的變換表 + 線性 + 兩個位移定理 | `sp.LaplaceTransform(f, t, s).doit()` | **獨立的實作，但不是獨立的方法**——SymPy 的規則引擎與我們的表都是「查表」。見下 |
| `transform`（反） | 同上，反著用 | 同上（把答案 $f$ 正變換回去比對 $F$） | 同上 |

**`transform` 那兩格的誠實說明。** 最強的獨立路徑是**定義的積分**
$\int_0^\infty f(t)e^{-st}\,dt$——它與任何表都無關。實測（沙箱，SymPy 1.14）：
在難度 1、2 的函數族上 `sp.integrate` 幾乎都算得出來且只要 0.1–0.9 秒；
但在難度 3 的族（$e^{\alpha t}$ 乘上多項式，加上一個延遲項）上，
12 個樣本裡**有 2 個它算不出來**（留下未計算的 `Integral`），
而算得出來的那些最慢要 8.7 秒。所以定義積分**不能**當每題都要跑的閘門。

因此分工是：

- **每題都跑的閘門**用 `sp.LaplaceTransform(...).doit()`（規則引擎，0.05–0.25 秒）。
- **定義積分**降級成一項單獨的測試（`test_the_table_agrees_with_the_defining_integral`），
  在本檔案的基本函數上把「表 = 定義」證一次。

這樣的結果是：表本身有定義積分背書，每一題的組合有規則引擎背書。
**還剩下一個縫**：SymPy 的規則引擎與我們的表若對同一條性質有同一個錯，
兩邊會一起錯而閘門不會叫。那需要兩份表在同一格上同時寫錯，可能性很低，
但它不是零——**這件事寫在這裡，而不是說「閘門是獨立的」就算了**。

---

## 附錄 C.3 的符號：為什麼要自己組字串

C.3 規定變換寫成 ``L\{f\}``，不得出現 $F(s)$、$Y(s)$、`\mathcal{L}`。
`sp.latex()` 沒有這種輸出形式（`sp.latex(sp.LaplaceTransform(f, t, s))` 會印出
`\operatorname{LaplaceTransform}{\left(...\right)}`），所以本檔用 `_L()` / `_Linv()`
兩個小函式統一組字串，**七、八個步驟不各寫各的**。

同理，`sp.latex(sp.Heaviside(t-2))` 給的是 $\theta(t-2)$ 而 C.3 要求 $u(t-2)$，
所以本檔的 LaTeX 一律走 `_tex()`（一個 `LatexPrinter` 子類），不直接呼叫 `sp.latex()`。
`tests/test_generators.py` 有一組防回頭測試盯著這整組黑名單。

---

## 難度 3 的答案為什麼有兩個形狀

步階外力的答案含 $u(t-a)$。它有一個很具體的麻煩：

    y = u(t-a)·w(t-a)  →  y' 會生出一個 δ(t-a)·w(0) 項

$w(0)=0$ 所以那一項數學上是 0，但 **SymPy 不會自己把 $g(t)\delta(t-a)$
在 $g(a)=0$ 時化成 0**（實測留下 `3*(exp(2*t) - exp(2))*exp(-2*t)*DiracDelta(t - 1)/2`），
於是殘差化簡不掉，閘門會把一個完全正確的答案擋下來。

解法是讓**閘門看 `Piecewise` 形、學生看 $u(t-a)$ 形**：

    display_expr  = Heaviside(t-c) * w(t-c)          → 印給學生看
    answer_expr   = display_expr.rewrite(Piecewise)  → 交給 Check

⚠️ 這裡唯一的風險是**兩個形狀漂移**。所以 `answer_expr` 不是另外寫一遍的，
它是從 `display_expr` **機械地 rewrite 出來的**——一個字都沒有重打，
所以它們不可能不一致。（`rewrite` 之外還有一項測試在數值上比對兩者。）

⚠️ 連帶的一條：**`answer_expr` 不可以拿去 `sp.latex()`**，`Piecewise` 會印出
`\begin{cases}`，而 KaTeX 不支援它（`test_latex_is_katex_safe` 盯著）。
本檔的 `answer_latex` 一律從 `display_expr` 走 `_tex()` 產生。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import sympy as sp
from sympy.printing.latex import LatexPrinter

from ..base import Check, Problem, Step, register
from ..pretty import is_pretty

# --- 符號 ------------------------------------------------------------------
#
# t 與 s 都宣告 positive：
#   * t > 0 讓 Heaviside(t) 直接化成 1，也讓定義積分的下限行為明確；
#   * s > 0 是 LaplaceTransform().doit() 化簡收斂條件時要的。
# ⚠️ 這裡的 t 與 `systems/real_distinct.py` 的 `Symbol("t", real=True)`
#    **不是同一顆符號**
#    （assumptions 不同 → 不相等）。兩者不會在同一題裡相遇，但若日後有人想把
#    兩個題型的表達式湊在一起，這一行就是那個坑（PLAN §2.2 的第 3 點）。
t = sp.Symbol("t", positive=True)
s = sp.Symbol("s", positive=True)

#: 三種題型各自的「未知量」。`Check.residual_expr` 是一個含它的算式，
#: 代入答案後 `doit()` 就是殘差。
_Y_FN = sp.Function("y")(t)        # 初值問題：未知函數 y(t)
_F_FN = sp.Function("F")(s)        # 正變換題：未知的像函數（只在內部用，不印給學生）
_f_FN = sp.Function("f")(t)        # 反變換題：未知的原函數

#: 顯示延遲項時用的替身符號，見下面 `_tex()` 的說明。
_SHIFT = sp.Symbol("tau_shift")

TRANSFORM_ID = "ode.laplace.transform"
IVP_ID = "ode.laplace.ivp"

CHAPTER = "Laplace Transform"


# --- 附錄 C.3 的排版 --------------------------------------------------------

class _LaplacePrinter(LatexPrinter):
    r"""附錄 C.3 要求的兩處覆寫。

    1. `Heaviside(t-a)` → $u(t-a)$（SymPy 預設印 $\theta(t-a)$）。
    2. 一顆叫 `tau_shift` 的替身符號 → 呼叫端給的字串，通常是
       `\left(t - 2\right)`。

    第 2 點需要解釋，因為它看起來像是繞遠路。延遲項的答案要印成
    $u(t-2)\left(1 - 2e^{-(t-2)}\right)$，也就是**指數的指數裡要保留 $(t-2)$
    這個結構**；但 SymPy 一拿到 `exp(-(t-2))` 就會把它算成 `exp(2-t)`，
    印出來是 $e^{2-t}$——數值一樣，而**學生看不出第二位移定理用在哪裡**。

    試過而**不能用**的辦法：`sp.UnevaluatedExpr(t-2)`。它在 `exp(-2*τ)` 上
    印得對，但在 `exp(-τ)` 上印成 $e^{-t-2}$——**負號被分配進去了，
    印出來的東西是錯的**。一個「大部分時候對」的排版工具比沒有更危險，
    所以改用替身符號：`w.subs(t, _SHIFT)` 之後 SymPy 沒有東西可以化簡
    （`_SHIFT` 就是一顆普通符號），印的時候再把它換成該有的字串。
    """

    def __init__(self, shift_latex: str | None = None) -> None:
        super().__init__()
        #: 括號版與裸版。括號版是預設（`-\tau` 一定要括起來才不會變成 `-t-2`）；
        #: 裸版只用在「外面已經有一層括號」的地方，見 `_print_Function`。
        self._shift_latex = shift_latex
        self._shift_bare = None
        if shift_latex is not None:
            self._shift_bare = (
                shift_latex.removeprefix(r"\left(").removesuffix(r"\right)")
            )

    def _print_Heaviside(self, expr, exp=None):
        base = r"u\left(%s\right)" % self._print(expr.args[0])
        if exp is None:
            return base
        return r"\left(%s\right)^{%s}" % (base, exp)

    def _print_Symbol(self, expr, style="plain"):
        if self._shift_latex is not None and expr.name == _SHIFT.name:
            return self._shift_latex
        return super()._print_Symbol(expr, style)

    def _print_Function(self, expr, exp=None):
        """`\\cos{\\left(\\left(t-2\\right)\\right)}` 的那一層多餘括號。

        函數呼叫本來就會加一層括號，替身符號再加一層就變成 $\\cos((t-2))$。
        不會看錯，但也沒有理由讓它出現。只在**唯一的引數就是替身符號**時
        拿掉裡面那層——`\\sin(2(t-3))` 的括號是必要的，那一格不動。
        """
        if (self._shift_bare is not None and exp is None
                and len(expr.args) == 1 and expr.args[0] == _SHIFT):
            return r"\%s{\left(%s \right)}" % (expr.func.__name__, self._shift_bare)
        return super()._print_Function(expr, exp)


def _tex(expr, shift_latex: str | None = None) -> str:
    """本檔唯一的 LaTeX 出口。**不要在這個模組裡直接呼叫 `sp.latex()`**——
    那會讓 $\\theta(t-a)$ 溜出去，而它不會壞掉任何東西，只是換了一種語言。"""
    return _LaplacePrinter(shift_latex).doprint(expr)


def _L(body: str) -> str:
    r"""附錄 C.3 的正變換記號：``L\{...\}``。

    存在的理由只有一個——**SymPy 印不出這種形式**，而規範要求它。
    做成一個函式而不是在每個步驟裡各打一次，是為了讓「改寫法」是改一行
    （C.3 已經預留了改成 `\mathrm{L}` 的可能）。
    """
    return r"L\{" + body + r"\}"


def _Linv(body: str) -> str:
    r"""附錄 C.3 的逆變換記號：``L^{-1}\{...\}``。"""
    return r"L^{-1}\{" + body + r"\}"


def _shift_latex(c: int) -> str:
    return r"\left(t - %d\right)" % c


def _signed(value: int, body: str) -> str:
    """把一個帶正負號的項接在算式後面：`3` → `` + 3``，`-3` → `` - 3``，`0` → 空字串。

    存在的理由是三個很小、但**每一個都會被學生看到**的排版錯誤：
    `- -4`（雙負號）、`- 0`（沒有意義的零項）、`- -1s`（兩者一起）。
    這一類東西不會壞掉任何測試，只會讓那一行看起來像是程式印壞了。
    """
    if value == 0:
        return ""
    sign = " + " if value < 0 else " - "     # 呼叫端寫的是「減掉 value」
    magnitude = abs(value)
    if body and magnitude == 1:
        return sign + body
    return sign + str(magnitude) + body


# --- 我們自己的變換表 -------------------------------------------------------
#
# ⚠️ 這張表是**生成路徑**。驗證閘門刻意不碰它（見檔頭的表格）。

@dataclass(frozen=True)
class _Pair:
    """一組「時域 ↔ s 域」，係數分開放。

    `coeff` 分開放是為了讓步驟能寫成 `L\\{3e^{2t}\\} = 3\\cdot\\frac{1}{s-2}`
    ——線性那一步的教學重點就是係數提得出來。
    """

    coeff: sp.Expr
    time: sp.Expr          # 不含係數的時域函數
    freq: sp.Expr          # 不含係數的像函數
    rule: str              # 給步驟說明用的英文名稱

    @property
    def time_expr(self) -> sp.Expr:
        return self.coeff * self.time

    @property
    def freq_expr(self) -> sp.Expr:
        return self.coeff * self.freq


def _pair_one() -> _Pair:
    return _Pair(sp.Integer(1), sp.Integer(1), 1 / s, "constant")


def _pair_power(n: int) -> _Pair:
    return _Pair(sp.Integer(1), t**n, sp.factorial(n) / s ** (n + 1), "power")


def _pair_exp(a: int) -> _Pair:
    return _Pair(sp.Integer(1), sp.exp(a * t), 1 / (s - a), "exponential")


def _pair_sin(w: int) -> _Pair:
    return _Pair(sp.Integer(1), sp.sin(w * t), w / (s**2 + w**2), "sine")


def _pair_cos(w: int) -> _Pair:
    return _Pair(sp.Integer(1), sp.cos(w * t), s / (s**2 + w**2), "cosine")


#: 難度 1 的基本函數池。刻意**不含** $e^{at}\cos$ 這種已經要用位移定理的東西，
#: 那是難度 3 的內容。
def _basic_pool(rng: random.Random) -> list[_Pair]:
    return [
        _pair_one(),
        _pair_power(1),
        _pair_power(2),
        _pair_power(3),
        _pair_exp(rng.choice(NONZERO)),
        _pair_sin(rng.choice(OMEGA)),
        _pair_cos(rng.choice(OMEGA)),
    ]


NONZERO = (-3, -2, -1, 1, 2, 3)
OMEGA = (1, 2, 3)
COEFFS = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
SMALL = (-3, -2, -1, 1, 2, 3)


def _sum_latex(pairs: list[_Pair]) -> str:
    """把一串 `_Pair` 的時域函數排版成 $c_1 f_1(t) + c_2 f_2(t)$。

    不直接 `_tex(Add(...))` 的理由：SymPy 會依它自己的順序重排項，
    而題目敘述的項序應該與步驟裡逐項處理的順序一致，否則學生要在兩行之間
    重新配對。這是純粹的排版考量，不影響數學。
    """
    out = ""
    for i, p in enumerate(pairs):
        body = _tex(p.time_expr)
        if i == 0:
            out = body
        elif body.startswith("-"):
            out += " - " + body[1:].lstrip()
        else:
            out += " + " + body
    return out


# ===========================================================================
# 題型一：正變換與反變換
# ===========================================================================

TRANSFORM_NOTES = {
    1: "Forward transform of a linear combination of table functions",
    2: "Inverse transform: factor or complete the square, then use partial fractions",
    3: "Both shifting theorems: $e^{at}f(t)$ and $u(t-a)f(t-a)$",
}


def _transform_check(time_expr: sp.Expr, freq_expr: sp.Expr, forward: bool) -> Check:
    r"""閘門：宣稱的一對 $(f, F)$ 必須滿足 $L\{f\} = F$。

    正變換題的未知量是 $F$，反變換題的未知量是 $f$，但**驗的是同一個等式**
    ——這是刻意的：兩個方向共用一條閘門，就不可能出現「正變換的標準比反變換鬆」
    這種只在某些 seed 上發作的偏差。

    `sp.LaplaceTransform(...)` 放進 `residual_expr` 時是**未計算**的，
    `Check.residual_of()` 的 `.doit()` 才會去算——所以 `Check` 仍然是純資料。
    """
    if forward:
        residual = _F_FN - sp.LaplaceTransform(time_expr, t, s)
        unknown, var = _F_FN, s
    else:
        residual = sp.LaplaceTransform(_f_FN, t, s) - freq_expr
        unknown, var = _f_FN, t
    return Check(
        var=var,
        kind="scalar",
        n_constants=0,
        order=0,
        unknown=unknown,
        residual_expr=residual,
        linear=True,
    )


def _forward_problem(rng: random.Random, difficulty: int) -> Problem | None:
    """難度 1：線性 + 表。"""
    pool = _basic_pool(rng)
    chosen = rng.sample(pool, rng.choice((2, 3)))
    pairs = [
        _Pair(sp.Integer(rng.choice(COEFFS)), p.time, p.freq, p.rule) for p in chosen
    ]

    f_expr = sp.Add(*[p.time_expr for p in pairs])
    F_expr = sp.Add(*[p.freq_expr for p in pairs])
    if not is_pretty(F_expr, 40):
        return None

    statement_latex = "f(t) = " + _sum_latex(pairs)
    answer_latex = _L("f") + " = " + _tex(F_expr)

    term_lines = r",\quad ".join(
        _L(_tex(p.time)) + " = " + _tex(p.freq) for p in pairs
    )
    linear_terms = ""
    for i, p in enumerate(pairs):
        coeff = int(p.coeff)
        magnitude = "" if abs(coeff) == 1 else str(abs(coeff))
        body = magnitude + _L(_tex(p.time))
        if i == 0:
            linear_terms = ("-" if coeff < 0 else "") + body
        else:
            linear_terms += (" - " if coeff < 0 else " + ") + body

    steps = [
        Step(
            "Split the transform by linearity",
            _L("f") + " = " + linear_terms,
            "The Laplace transform is linear, so constants come out in front "
            "and a sum transforms term by term.",
        ),
        Step(
            "Look up each term in the transform table",
            term_lines,
            "These are the entries the table is built from; every other rule "
            "in this chapter is one of them combined with a property.",
        ),
        Step(
            "Put the terms back together",
            answer_latex,
            "The transform is defined for $s$ large enough that the defining "
            "integral converges; that is why each term carries its own "
            "restriction on $s$.",
        ),
    ]

    return Problem(
        template_id=TRANSFORM_ID,
        difficulty=difficulty,
        seed=0,
        params={
            "direction": "forward",
            "rules": [p.rule for p in pairs],
            "coefficients": [int(p.coeff) for p in pairs],
        },
        statement="Find the Laplace transform of the following function.",
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=F_expr,
        steps=steps,
        check=_transform_check(f_expr, F_expr, forward=True),
    )


def _inverse_problem(rng: random.Random, difficulty: int) -> Problem | None:
    """難度 2：反變換。三個情形各對應一種分母。

    反向構造：**先寫下 $f(t)$**（所以係數必然漂亮），再把對應的
    $F(s)$ 通分成一個分式——通分之後分母展開，學生才有「先因式分解」這一步可做。
    """
    case = rng.choice(("distinct", "repeated", "complex"))

    if case == "distinct":
        r1, r2 = rng.sample(SMALL, 2)
        A, B = rng.choice(SMALL), rng.choice(SMALL)
        f_expr = A * sp.exp(r1 * t) + B * sp.exp(r2 * t)
        parts = [(A, 1 / (s - r1)), (B, 1 / (s - r2))]
        setup = (
            "Two distinct real roots, so the decomposition has two simple "
            "fractions with unknown constants on top."
        )
        params = {"case": case, "roots": [r1, r2], "coefficients": [A, B]}

    elif case == "repeated":
        r = rng.choice(SMALL)
        A, B = rng.choice(SMALL), rng.choice(SMALL)
        f_expr = (A + B * t) * sp.exp(r * t)
        parts = [(A, 1 / (s - r)), (B, 1 / (s - r) ** 2)]
        setup = (
            "A repeated root needs one fraction for each power of the factor, "
            "here $(s-a)$ and $(s-a)^2$."
        )
        params = {"case": case, "roots": [r, r], "coefficients": [A, B]}

    else:
        alpha = rng.choice((-2, -1, 0, 1, 2))
        beta = rng.choice(OMEGA)
        A, B = rng.choice(SMALL), rng.choice(SMALL)
        f_expr = sp.exp(alpha * t) * (A * sp.cos(beta * t) + B * sp.sin(beta * t))
        parts = [
            (A, (s - alpha) / ((s - alpha) ** 2 + beta**2)),
            (B, beta / ((s - alpha) ** 2 + beta**2)),
        ]
        setup = (
            "The denominator has no real roots, so it stays as one quadratic; "
            "complete the square to read off $\\alpha$ and $\\beta$."
        )
        params = {"case": case, "alpha": alpha, "beta": beta,
                  "coefficients": [A, B]}

    decomposed = sp.Add(*[c * piece for c, piece in parts])
    F_expr = sp.cancel(sp.together(decomposed))
    num, den = sp.fraction(F_expr)
    den_expanded = sp.expand(den)
    if sp.degree(den_expanded, s) < 2:          # 分子分母約掉了 → 沒有題目
        return None
    F_shown = sp.expand(num) / den_expanded
    if not is_pretty(f_expr, 40):
        return None

    statement_latex = "f(t) = " + _Linv(_tex(F_shown))
    answer_latex = "f(t) = " + _tex(f_expr)

    if case == "complex":
        middle = Step(
            "Complete the square in the denominator",
            _tex(den_expanded) + " = " + _tex((s - params["alpha"]) ** 2)
            + " + " + _tex(sp.Integer(params["beta"] ** 2)),
            setup,
        )
    else:
        middle = Step(
            "Factor the denominator",
            _tex(den_expanded) + " = " + _tex(sp.factor(den_expanded)),
            setup,
        )

    steps = [
        Step(
            "Look at the denominator",
            _L("f") + " = " + _tex(F_shown),
            "The shape of the denominator decides which decomposition to use, "
            "so factor it before anything else.",
        ),
        middle,
        Step(
            "Split into partial fractions",
            _tex(F_shown) + " = " + _tex(decomposed),
            "Matching numerators gives a small linear system for the unknown "
            "constants; here they come out as small integers.",
        ),
        Step(
            "Invert each term with the table",
            r",\quad ".join(
                _Linv(_tex(piece)) + " = " + _tex(time_piece)
                for (_, piece), time_piece in zip(parts, _inverse_pieces(case, params))
            ),
            "Each fraction is one table entry read from right to left.",
        ),
        Step("Inverse transform", answer_latex),
    ]

    return Problem(
        template_id=TRANSFORM_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement="Find the inverse Laplace transform.",
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=f_expr,
        steps=steps,
        check=_transform_check(f_expr, F_shown, forward=False),
    )


def _inverse_pieces(case: str, params: dict) -> list[sp.Expr]:
    """反變換題裡，每一個部分分式對應的時域函數（不含係數）。"""
    if case == "distinct":
        r1, r2 = params["roots"]
        return [sp.exp(r1 * t), sp.exp(r2 * t)]
    if case == "repeated":
        r = params["roots"][0]
        return [sp.exp(r * t), t * sp.exp(r * t)]
    alpha, beta = params["alpha"], params["beta"]
    return [sp.exp(alpha * t) * sp.cos(beta * t), sp.exp(alpha * t) * sp.sin(beta * t)]


def _shifting_problem(rng: random.Random, difficulty: int) -> Problem | None:
    r"""難度 3：兩個位移定理各出現一次。

    $f(t) = A\,e^{\alpha t}b_1(t) + B\,u(t-c)\,b_2(t-c)$

    一題裡放兩個定理是刻意的：學生最常犯的錯就是把它們搞混
    （s 域位移換的是 $s$，t 域位移在 $s$ 域是乘上 $e^{-cs}$），
    而分成兩題出，他永遠不需要在同一頁上分辨它們。
    """
    alpha = rng.choice(NONZERO)
    w1 = rng.choice(OMEGA)
    base1 = rng.choice(
        [_pair_power(1), _pair_power(2), _pair_sin(w1), _pair_cos(w1)]
    )
    A = sp.Integer(rng.choice(SMALL))

    c = rng.choice((1, 2, 3))
    w2 = rng.choice(OMEGA)
    base2 = rng.choice(
        [_pair_one(), _pair_power(1), _pair_power(2), _pair_sin(w2), _pair_cos(w2),
         _pair_exp(rng.choice(NONZERO))]
    )
    B = sp.Integer(rng.choice(SMALL))

    # s 域位移：L{e^{at}g(t)} = G(s-a)
    shifted_freq = base1.freq.subs(s, s - alpha)
    # t 域位移：L{u(t-c)g(t-c)} = e^{-cs}G(s)
    delayed_freq = sp.exp(-c * s) * base2.freq

    F_expr = A * shifted_freq + B * delayed_freq
    f_expr = A * sp.exp(alpha * t) * base1.time + B * sp.Heaviside(t - c) * base2.time.subs(t, t - c)
    if not is_pretty(F_expr, 45):
        return None

    sh = _shift_latex(c)
    display_f = (
        A * sp.exp(alpha * t) * base1.time
        + B * sp.Heaviside(t - c) * base2.time.subs(t, _SHIFT)
    )
    statement_latex = "f(t) = " + _tex(display_f, sh)
    answer_latex = _L("f") + " = " + _tex(F_expr)

    steps = [
        Step(
            "Name the two building blocks",
            rf"g_1(t) = {_tex(base1.time)},\quad g_2(t) = {_tex(base2.time)}",
            "Each term is one table function that has had a property applied "
            "to it; find the plain function first.",
        ),
        Step(
            "Transform the building blocks",
            _L("g_1") + " = " + _tex(base1.freq) + r",\quad "
            + _L("g_2") + " = " + _tex(base2.freq),
        ),
        Step(
            "First shifting theorem: replace $s$ by $s - a$",
            _L(_tex(sp.exp(alpha * t) * base1.time)) + " = " + _tex(shifted_freq),
            "Multiplying by $e^{at}$ in the time domain only moves the "
            "argument of the transform; the shape of the transform does not "
            "change.",
        ),
        Step(
            "Second shifting theorem: a delay becomes a factor $e^{-as}$",
            _L(_tex(sp.Heaviside(t - c) * base2.time.subs(t, _SHIFT), sh))
            + " = " + _tex(delayed_freq),
            "A delay in time turns into the factor $e^{-as}$ in the $s$ "
            "domain. The unit step is what makes the delayed term zero "
            "before $t = a$.",
        ),
        Step("Add the two transforms", answer_latex),
    ]

    return Problem(
        template_id=TRANSFORM_ID,
        difficulty=difficulty,
        seed=0,
        params={
            "direction": "forward",
            "case": "shifting",
            "alpha": alpha,
            "delay": c,
            "rules": [base1.rule, base2.rule],
            "coefficients": [int(A), int(B)],
        },
        statement="Find the Laplace transform of the following function. "
                  "Here $u$ is the unit step function.",
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=F_expr,
        steps=steps,
        check=_transform_check(f_expr, F_expr, forward=True),
    )


@register(
    TRANSFORM_ID,
    name="Laplace Transform and Its Inverse",
    chapter=CHAPTER,
    difficulty_notes=TRANSFORM_NOTES,
)
def generate_transform(rng: random.Random, difficulty: int) -> Problem | None:
    if difficulty == 1:
        return _forward_problem(rng, difficulty)
    if difficulty == 2:
        return _inverse_problem(rng, difficulty)
    return _shifting_problem(rng, difficulty)


# ===========================================================================
# 題型二：用拉普拉斯變換解初值問題
# ===========================================================================

IVP_NOTES = {
    1: "First-order equation with a constant or exponential forcing term",
    2: "Second-order equation; the inverse transform needs partial fractions",
    3: "Forcing switched on at $t = a$ by a unit step, so the answer is delayed",
}

#: 外力係數的上限。反向構造是先挑答案再倒推外力，倒推出來的係數是
#: 兩個小整數的乘積，偶爾會跳到 30 以上——那種題目數學上完全正確，
#: 但沒有一本課本會把 $y'' + y' - 6y = 30e^{4t}$ 印出來。
MAX_FORCING = 12


def _lhs_latex(order: int, a1: int, a0: int) -> str:
    """把 ODE 的左邊排版成正常寫法（不出現 `+ -3`）。

    與 `second_order_homog._poly_latex` 是同一個小工具的兩個副本。
    刻意不提取到 `pretty.py`：兩邊的需求已經開始分岔（這裡要支援一階、
    要支援非齊次的右邊），而**一個被兩處各自往不同方向拉扯的共用函式，
    最後會長成一個誰都不好用的參數化怪物**（D21 那條「不要硬找共同抽象」
    的同一個判斷，只是規模小得多）。
    """
    terms = ["y''"] if order == 2 else ["y'"]
    coeffs = [(a1, "y'"), (a0, "y")] if order == 2 else [(a0, "y")]
    for coeff, name in coeffs:
        if coeff == 0:
            continue
        sign = "+" if coeff > 0 else "-"
        mag = abs(coeff)
        terms.append(f"{sign} {'' if mag == 1 else mag}{name}")
    return " ".join(terms)


def _ic_latex(order: int, y0: int, y1: int | None) -> str:
    if order == 1:
        return f"y(0) = {y0}"
    return rf"y(0) = {y0},\quad y'(0) = {y1}"


def _first_order(rng: random.Random):
    r"""難度 1 的反向構造。

    先寫答案 $y = A e^{rt} + B e^{mt}$（$m = 0$ 時第二項就是常數），
    再把它代進 $y' + a y$ 算出外力——齊次的那一項自動消掉，
    只剩 $B(m-r)e^{mt}$，所以外力必為漂亮的形式。
    """
    r = rng.choice(NONZERO)
    m = rng.choice([v for v in (-3, -2, -1, 0, 1, 2, 3) if v != r])
    A, B = rng.choice(SMALL), rng.choice(SMALL)

    k = B * (m - r)
    if abs(k) > MAX_FORCING:
        return None

    a0 = -r
    y_expr = A * sp.exp(r * t) + B * sp.exp(m * t)
    forcing = k * sp.exp(m * t)
    y0 = A + B
    return dict(order=1, a1=0, a0=a0, y_expr=y_expr, forcing=forcing,
                y0=y0, y1=None, roots=[r], forcing_rate=m, forcing_coeff=k,
                case="first_order")


def _second_order_real(rng: random.Random):
    """難度 2 的實相異根情形：反變換要做部分分式。"""
    r1, r2 = rng.sample(SMALL, 2)
    m = rng.choice([v for v in (-3, -2, -1, 0, 1, 2, 3) if v not in (r1, r2)])
    A, B, C = rng.choice(SMALL), rng.choice(SMALL), rng.choice(SMALL)

    k = C * (m - r1) * (m - r2)
    if abs(k) > MAX_FORCING:
        return None

    a1, a0 = -(r1 + r2), r1 * r2
    y_expr = A * sp.exp(r1 * t) + B * sp.exp(r2 * t) + C * sp.exp(m * t)
    forcing = k * sp.exp(m * t)
    y0 = A + B + C
    y1 = A * r1 + B * r2 + C * m
    return dict(order=2, a1=a1, a0=a0, y_expr=y_expr, forcing=forcing,
                y0=y0, y1=y1, roots=[r1, r2], forcing_rate=m, forcing_coeff=k,
                case="real")


def _second_order_complex(rng: random.Random):
    r"""難度 2 的複數根情形：反變換要先配方，再用 s 域位移。

    這一格是 `transform` 難度 2 的 `complex` 情形在初值問題裡的樣子。
    兩個題型都有它是刻意的——學生在 `transform` 練的是「認得配方」，
    在這裡練的是「配方出現在一條更長的流程中間」。
    """
    alpha = rng.choice((-2, -1, 1, 2))
    beta = rng.choice(OMEGA)
    m = rng.choice((-3, -2, -1, 0, 1, 2, 3))
    A, B, C = rng.choice(SMALL), rng.choice(SMALL), rng.choice(SMALL)

    k = C * ((m - alpha) ** 2 + beta**2)
    if abs(k) > MAX_FORCING:
        return None

    a1, a0 = -2 * alpha, alpha**2 + beta**2
    y_expr = (sp.exp(alpha * t) * (A * sp.cos(beta * t) + B * sp.sin(beta * t))
              + C * sp.exp(m * t))
    forcing = k * sp.exp(m * t)
    y0 = A + C
    y1 = alpha * A + beta * B + m * C
    return dict(order=2, a1=a1, a0=a0, y_expr=y_expr, forcing=forcing,
                y0=y0, y1=y1, roots=None, alpha=alpha, beta=beta,
                cos_coeff=A, sin_coeff=B,
                forcing_rate=m, forcing_coeff=k, case="complex")


def _step_response(r1: int, r2: int):
    r"""單位步階（高度 $k$）打進 $y'' + a_1y' + a_0y$ 時的響應 $w$，
    滿足 $w(0) = w'(0) = 0$。

    反向構造：**先寫下 $w$ 的形狀再算 $k$**，而不是解一個 2×2 線性方程組。
    令 $w(\tau) = P + Qe^{r_1\tau} + Re^{r_2\tau}$，兩個初始條件是

        P + Q + R = 0        （w(0) = 0）
        Q r_1 + R r_2 = 0    （w'(0) = 0）

    第二條的整數解取 $Q = -r_2/g$、$R = r_1/g$（$g = \gcd(|r_1|,|r_2|)$），
    第一條再定出 $P$。代回方程得到 $k = a_0 P$，**必為整數**。

    直接解方程組會得到分母是 $r_1r_2(r_1-r_2)$ 的係數（最大 54），
    幾乎每一題都會被「分母 > 12」的漂亮度門檻擋掉。
    """
    g = math.gcd(abs(r1), abs(r2))
    Q, R = sp.Integer(-r2 // g), sp.Integer(r1 // g)
    P = -(Q + R)
    if P < 0:                                   # 讓步階高度 k 的正負跟著 a0 走
        P, Q, R = -P, -Q, -R
    k = r1 * r2 * P
    w = P + Q * sp.exp(r1 * t) + R * sp.exp(r2 * t)
    return w, int(k)


def _step_forced(rng: random.Random):
    r"""難度 3：外力在 $t = c$ 被單位步階打開。

    答案 $y = y_h(t) + u(t-c)\,w(t-c)$，其中 $w$ 由 `_step_response()` 給。
    """
    r1, r2 = rng.sample(SMALL, 2)
    w, k = _step_response(r1, r2)
    if abs(k) > 8:                              # 課本不會印 $-30u(t-2)$
        return None

    c = rng.choice((1, 2, 3))
    A, B = rng.choice(SMALL), rng.choice(SMALL)
    a1, a0 = -(r1 + r2), r1 * r2

    y_hom = A * sp.exp(r1 * t) + B * sp.exp(r2 * t)
    y0 = A + B
    y1 = A * r1 + B * r2

    display = y_hom + sp.Heaviside(t - c) * w.subs(t, _SHIFT)
    exact = y_hom + sp.Heaviside(t - c) * w.subs(t, t - c)
    forcing_display = k * sp.Heaviside(t - c)

    return dict(order=2, a1=a1, a0=a0, y_expr=exact, display_expr=display,
                forcing=forcing_display, y0=y0, y1=y1, roots=[r1, r2],
                delay=c, step_height=k, step_response=w, case="step")


def _subsidiary(spec: dict) -> sp.Expr:
    r"""子式方程解出來的 $L\{y\}$。

    ⚠️ 這是**生成路徑**的一部分（步驟要印它），不是閘門。閘門完全不看它。
    """
    order, a1, a0 = spec["order"], spec["a1"], spec["a0"]
    y0, y1 = spec["y0"], spec["y1"]
    if order == 1:
        denom = s + a0
        poly_part = sp.Integer(y0)
    else:
        denom = s**2 + a1 * s + a0
        poly_part = y0 * s + y1 + a1 * y0
    if spec["case"] == "step":
        rhs = spec["step_height"] * sp.exp(-spec["delay"] * s) / s
    else:
        rhs = spec["forcing_coeff"] / (s - spec["forcing_rate"])
    return sp.together(poly_part / denom) + rhs / denom


def _ivp_steps(spec: dict) -> list[Step]:
    """逐步解答。顆粒度依 §7 #22：**一步 = 課本會單獨寫一行的動作**。"""
    order, a1, a0 = spec["order"], spec["a1"], spec["a0"]
    y0, y1 = spec["y0"], spec["y1"]
    Ly = _L("y")
    lhs = _lhs_latex(order, a1, a0)
    forcing_tex = _tex(spec["forcing"])
    denom = s + a0 if order == 1 else s**2 + a1 * s + a0

    left_terms: list[str] = []
    if order == 2:
        left_terms.append(_L("y''"))
        if a1:
            left_terms.append(("+ " if a1 > 0 else "- ")
                              + (f"{abs(a1)}" if abs(a1) != 1 else "") + _L("y'"))
    else:
        left_terms.append(_L("y'"))
    if a0:
        left_terms.append(("+ " if a0 > 0 else "- ")
                          + (f"{abs(a0)}" if abs(a0) != 1 else "") + _L("y"))
    steps = [
        Step(
            "Transform both sides of the equation",
            " ".join(left_terms) + " = " + _L(forcing_tex),
            "The transform is linear, so it goes through the sum and through "
            "the constant coefficients untouched.",
        ),
    ]

    if order == 1:
        steps.append(Step(
            "Replace the transform of the derivative",
            _L("y'") + f" = s\\,{Ly} - y(0) = s\\,{Ly}" + _signed(y0, ""),
            "This is the step that turns calculus into algebra, and it is "
            "also the only place where the initial value enters.",
        ))
    else:
        steps.append(Step(
            "Replace the transforms of the derivatives",
            _L("y'") + f" = s\\,{Ly}" + _signed(y0, "") + r",\quad "
            + _L("y''") + f" = s^2\\,{Ly}" + _signed(y0, "s") + _signed(y1, ""),
            "This is the step that turns calculus into algebra, and it is "
            "also the only place where the initial values enter.",
        ))

    if spec["case"] == "step":
        steps.append(Step(
            "Transform the right-hand side",
            _L(_tex(spec["forcing"])) + " = "
            + _tex(spec["step_height"] * sp.exp(-spec["delay"] * s) / s),
            "By the second shifting theorem a forcing term switched on at "
            "$t = a$ carries the factor $e^{-as}$.",
        ))
    else:
        steps.append(Step(
            "Transform the right-hand side",
            _L(_tex(spec["forcing"])) + " = "
            + _tex(spec["forcing_coeff"] / (s - spec["forcing_rate"])),
        ))

    Y = _subsidiary(spec)
    steps.append(Step(
        "Solve the subsidiary equation for the transform",
        f"\\left({_tex(denom)}\\right){Ly} = "
        + _tex(sp.expand(_numerator_of(spec)))
        + f",\\quad {Ly} = " + _tex(Y),
        "The differential equation has become an ordinary algebraic equation "
        "in $s$; that is the whole point of the method.",
    ))

    if spec["case"] == "step":
        steps.extend(_step_inversion_steps(spec, Y))
    else:
        steps.extend(_plain_inversion_steps(spec, Y))

    steps.append(Step(
        "Check with the initial value theorem",
        rf"\lim_{{s \to \infty}} s\,{Ly} = {y0} = y(0)",
        "The initial value theorem holds for every transform in this "
        "chapter, so it is a cheap check on the algebra above. It says "
        "nothing about whether the inverse transform was done correctly.",
    ))
    return steps


def _numerator_of(spec: dict) -> sp.Expr:
    """子式方程整理成 $(\\text{denom})\\,L\\{y\\} = \\text{numerator}$ 時的右邊。"""
    order, a1 = spec["order"], spec["a1"]
    y0, y1 = spec["y0"], spec["y1"]
    poly = sp.Integer(y0) if order == 1 else y0 * s + y1 + a1 * y0
    if spec["case"] == "step":
        rhs = spec["step_height"] * sp.exp(-spec["delay"] * s) / s
    else:
        rhs = spec["forcing_coeff"] / (s - spec["forcing_rate"])
    return poly + rhs


def _table_entries_used(spec: dict) -> list[tuple[sp.Expr, sp.Expr]]:
    """這一題的反變換會用到哪幾條表（像函數, 原函數），依出現順序、去重。

    刻意**不**從 `sp.apart()` 的輸出反推：那要去剖 SymPy 印出來的形狀，
    而反向構造這邊本來就知道每一個極點是誰放進去的。從已知的參數列出來，
    比從輸出猜回去短、也不會在 SymPy 換一種寫法時壞掉。
    """
    entries: list[tuple[sp.Expr, sp.Expr]] = []

    def add(freq, time):
        if all(sp.simplify(freq - f) != 0 for f, _ in entries):
            entries.append((freq, time))

    if spec["case"] == "complex":
        alpha, beta = spec["alpha"], spec["beta"]
        quad = (s - alpha) ** 2 + beta**2
        add((s - alpha) / quad, sp.exp(alpha * t) * sp.cos(beta * t))
        add(beta / quad, sp.exp(alpha * t) * sp.sin(beta * t))
    else:
        for r in spec["roots"]:
            add(1 / (s - r), sp.exp(r * t))
    if spec["case"] != "step":
        m = spec["forcing_rate"]
        add(1 / (s - m), sp.exp(m * t))
    return entries


def _inversion_latex(spec: dict) -> str:
    return r",\quad ".join(
        _Linv(_tex(freq)) + " = " + _tex(time)
        for freq, time in _table_entries_used(spec)
    )


def _shifted_numerator_latex(cos_coeff: int, sin_coeff: int,
                             alpha: int, beta: int) -> str:
    r"""$\dfrac{As + B}{(s-\alpha)^2+\beta^2}
        = \dfrac{A(s-\alpha)}{\cdots} + \dfrac{B\beta}{\cdots}$

    ⚠️ **這一行只能自己組字串**，不能交給 `sp.latex()`。SymPy 會把
    `-2*(s+1)` 自動乘開成 `-2*s - 2`，而 $(s-\alpha)$ 這個結構**正是這一步
    要給學生看的東西**——乘開之後那一步就什麼都沒說。

    （這與檔頭那個 `_SHIFT` 替身符號是同一類問題的兩個實例：SymPy 的自動
    化簡對數值是對的，對「這一行想表達什麼」是沒有意見的。）
    """
    quad = _tex((s - alpha) ** 2) + " + " + _tex(sp.Integer(beta**2))
    shifted = r"\left(" + _tex(s - alpha) + r"\right)"

    magnitude = "" if abs(cos_coeff) == 1 else str(abs(cos_coeff))
    first = ("-" if cos_coeff < 0 else "") + magnitude + shifted
    second = sin_coeff * beta

    # `factor` 而不是 `expand`：上一步的 `sp.apart()` 會把 `2s + 6` 印成
    # `2(s + 3)`，兩行接在一起看，同一個分子用兩種寫法會讓人停下來確認。
    # 這只是排版的對齊，不保證在每一組係數上都印得一模一樣。
    left = r"\frac{%s}{%s}" % (
        _tex(sp.factor(sp.expand(cos_coeff * (s - alpha) + second))), quad
    )
    right = (r"\frac{%s}{%s}" % (first, quad)
             + (" + " if second > 0 else " - ")
             + r"\frac{%d}{%s}" % (abs(second), quad))
    return left + " = " + right


def _plain_inversion_steps(spec: dict, Y: sp.Expr) -> list[Step]:
    Ly = _L("y")
    steps = [
        Step(
            "Split into partial fractions",
            f"{Ly} = " + _tex(sp.apart(Y, s)),
            "The irreducible quadratic keeps a linear numerator; only the "
            "real factors give single constants."
            if spec["case"] == "complex" else
            "Every factor of the denominator is a simple real root here, so "
            "each fraction is one table entry.",
        ),
    ]
    if spec["case"] == "complex":
        alpha, beta = spec["alpha"], spec["beta"]
        quad = s**2 + spec["a1"] * s + spec["a0"]
        steps.append(Step(
            "Complete the square in the quadratic",
            _tex(quad) + " = " + _tex((s - alpha) ** 2) + " + "
            + _tex(sp.Integer(beta**2)),
            "Written this way the quadratic is the transform of "
            "$e^{\\alpha t}\\cos\\beta t$ and $e^{\\alpha t}\\sin\\beta t$, "
            "which is the first shifting theorem read backwards.",
        ))
        steps.append(Step(
            "Match the numerator to the same shift",
            _shifted_numerator_latex(spec["cos_coeff"], spec["sin_coeff"],
                                     alpha, beta),
            "The cosine entry needs $s - \\alpha$ on top and the sine entry "
            "needs $\\beta$, so split the numerator into exactly those two "
            "pieces. Skipping this line is where the sine term usually goes "
            "missing.",
        ))
    steps.append(Step(
        "Invert term by term",
        _inversion_latex(spec),
        "Read the table from right to left; the constants in front are "
        "carried along unchanged because the inverse transform is linear too.",
    ))
    steps.append(Step("Solution of the initial value problem",
                      "y(t) = " + _tex(spec["y_expr"])))
    return steps


def _step_inversion_steps(spec: dict, Y: sp.Expr) -> list[Step]:
    Ly = _L("y")
    c, k = spec["delay"], spec["step_height"]
    a1, a0 = spec["a1"], spec["a0"]
    denom = s**2 + a1 * s + a0
    free_part = (spec["y0"] * s + spec["y1"] + a1 * spec["y0"]) / denom
    step_part = k / (s * denom)
    sh = _shift_latex(c)
    return [
        Step(
            "Separate the delayed part",
            f"{Ly} = " + _tex(free_part) + " + e^{-" + str(c) + "s}\\left("
            + _tex(step_part) + r"\right)",
            "Everything that comes from the initial values is undelayed; the "
            "whole effect of the switch sits inside the factor $e^{-as}$.",
        ),
        Step(
            "Partial fractions for each piece",
            _tex(free_part) + " = " + _tex(sp.apart(free_part, s))
            + r",\quad " + _tex(step_part) + " = " + _tex(sp.apart(step_part, s)),
        ),
        Step(
            "Invert, delaying the second piece",
            _Linv(_tex(step_part)) + " = " + _tex(spec["step_response"])
            + r"\;\Rightarrow\;"
            + _Linv("e^{-" + str(c) + "s}\\left(" + _tex(step_part) + r"\right)")
            + " = " + _tex(sp.Heaviside(t - c) * spec["step_response"].subs(t, _SHIFT), sh),
            "The second shifting theorem run backwards: the factor $e^{-as}$ "
            "delays the whole response and multiplies it by the unit step, so "
            "nothing happens before $t = a$.",
        ),
        Step(
            "Solution of the initial value problem",
            "y(t) = " + _tex(spec["display_expr"], sh),
            "Before $t = a$ the answer is the free response alone; the second "
            "term switches on at $t = a$ and is continuous there.",
        ),
    ]


@register(
    IVP_ID,
    name="Initial Value Problems via the Laplace Transform",
    chapter=CHAPTER,
    difficulty_notes=IVP_NOTES,
)
def generate_ivp(rng: random.Random, difficulty: int) -> Problem | None:
    if difficulty == 1:
        spec = _first_order(rng)
    elif difficulty == 2:
        spec = (_second_order_real(rng) if rng.random() < 0.5
                else _second_order_complex(rng))
    else:
        spec = _step_forced(rng)
    if spec is None:
        return None

    order = spec["order"]
    y_exact = spec["y_expr"]
    display_expr = spec.get("display_expr", y_exact)

    # ⚠️ 閘門看 Piecewise 形、學生看 u(t-a) 形，理由見檔頭。
    # answer_expr 是從 y_exact 機械地 rewrite 來的，不是另外寫一遍。
    answer_expr = y_exact.rewrite(sp.Piecewise) if spec["case"] == "step" else y_exact
    forcing_math = (spec["forcing"].rewrite(sp.Piecewise)
                    if spec["case"] == "step" else spec["forcing"])

    if not is_pretty(answer_expr, {1: 25, 2: 40, 3: 45}[difficulty]):
        return None

    if order == 1:
        residual = sp.Derivative(_Y_FN, t) + spec["a0"] * _Y_FN - forcing_math
        ic_derivatives: tuple = ()
    else:
        residual = (sp.Derivative(_Y_FN, (t, 2))
                    + spec["a1"] * sp.Derivative(_Y_FN, t)
                    + spec["a0"] * _Y_FN - forcing_math)
        ic_derivatives = (sp.Integer(spec["y1"]),)

    check = Check(
        var=t,
        kind="scalar",
        n_constants=0,                      # 初值問題：常數已被定值
        order=order,
        unknown=_Y_FN,
        residual_expr=residual,
        ic_point=sp.Integer(0),
        ic_value=sp.Integer(spec["y0"]),
        ic_derivative_values=ic_derivatives,
        linear=True,
    )

    sh = _shift_latex(spec["delay"]) if spec["case"] == "step" else None
    statement_latex = (
        _lhs_latex(order, spec["a1"], spec["a0"]) + " = " + _tex(spec["forcing"])
        + r",\quad " + _ic_latex(order, spec["y0"], spec["y1"])
    )
    answer_latex = "y(t) = " + _tex(display_expr, sh)

    params = {
        "case": spec["case"],
        "order": order,
        "a1": int(spec["a1"]),
        "a0": int(spec["a0"]),
        "y0": int(spec["y0"]),
        "y1": None if spec["y1"] is None else int(spec["y1"]),
    }
    for key in ("roots", "alpha", "beta", "forcing_rate", "forcing_coeff",
                "delay", "step_height"):
        if key in spec and spec[key] is not None:
            params[key] = spec[key]
    if spec["case"] == "step":
        # 難度 3 的答案有三個形狀（印給學生的、精確的、交給閘門的）。
        # 前兩個放進 params 是**為了讓測試看得到它們**——
        # `test_the_delayed_answer_has_one_meaning_in_all_three_forms`
        # 把三者串起來，那是「顯示形與閘門形不會漂移」唯一的保證。
        params["answer_display_srepr"] = sp.srepr(display_expr)
        params["answer_exact_srepr"] = sp.srepr(y_exact)
        # 步階響應 w。$w(0) = w'(0) = 0$ 是「可以把答案改寫成 `Piecewise`
        # 交給閘門」的**前提**：$w(0) \ne 0$ 的話 $y$ 在 $t=a$ 會跳，
        # $y'$ 裡就有一個真的 δ，而 `Piecewise` 的微分會安靜地把它忽略掉。
        # 放進 params 是為了讓那個前提可以被測試**精確地**驗證，
        # 而不是用一個要調容差的數值極限去猜。
        params["step_response_srepr"] = sp.srepr(spec["step_response"])

    statement = (
        "Solve the following initial value problem with the Laplace "
        "transform. Here $u$ is the unit step function."
        if spec["case"] == "step" else
        "Solve the following initial value problem with the Laplace transform."
    )

    return Problem(
        template_id=IVP_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=answer_expr,
        steps=_ivp_steps(spec),
        check=check,
    )
