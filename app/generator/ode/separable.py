"""可分離變數方程 y' = f(x) g(y)。

反向構造：先挑一組「積得出來、也解得回顯式 y」的 (f, g) 白名單組合，
再由 SymPy 算出積分與顯式解，最後把解代回原式驗證殘差為 0。
"""

from __future__ import annotations

import random

import sympy as sp

from ..base import Check, Problem, Step, register
from ..pretty import is_pretty

x = sp.Symbol("x", positive=True)
yv = sp.Symbol("y")
C1 = sp.Symbol("C_1")
_y = sp.Function("y")(x)          # 判定用的未知函數 y(x)

TEMPLATE_ID = "ode.first_order.separable"

SMALL = (1, 2, 3, -1, -2, -3)


def _f_polynomial(rng: random.Random) -> sp.Expr:
    a = rng.choice(SMALL)
    n = rng.choice((0, 1, 2))
    return a * x**n


def _f_exponential(rng: random.Random) -> sp.Expr:
    a = rng.choice(SMALL)
    k = rng.choice((1, 2, -1, -2))
    return a * sp.exp(k * x)


def _f_trig(rng: random.Random) -> sp.Expr:
    a = rng.choice(SMALL)
    k = rng.choice((1, 2))
    return a * rng.choice((sp.cos(k * x), sp.sin(k * x)))


def _pick(rng: random.Random, difficulty: int) -> tuple[sp.Expr, sp.Expr]:
    """回傳 (f(x), g(y))。難度控制的是「積分與反解的難度」。"""
    if difficulty == 1:
        return _f_polynomial(rng), yv
    if difficulty == 2:
        if rng.random() < 0.5:
            return _f_polynomial(rng), yv**2
        return _f_exponential(rng), yv
    return rng.choice((_f_polynomial, _f_exponential, _f_trig))(rng), 1 + yv**2


def _solve_explicit(f_x: sp.Expr, g_y: sp.Expr) -> tuple[sp.Expr, sp.Expr, sp.Expr]:
    """回傳 (∫dy/g, ∫f dx, 顯式解 y(x))。"""
    lhs = sp.integrate(1 / g_y, yv)
    rhs = sp.integrate(f_x, x)

    if g_y == yv:
        # ln|y| = F(x) + C  →  y = C_1 e^{F(x)}（把 e^C 改寫為新的任意常數 C_1）
        return lhs, rhs, C1 * sp.exp(rhs)

    sols = sp.solve(sp.Eq(lhs, rhs + C1), yv)
    if not sols:
        return lhs, rhs, None
    return lhs, rhs, sp.simplify(sols[0])


def _tex(expr) -> str:
    r"""這個題型專用的 LaTeX 印法：反三角函數印 `\arctan`，不是 `\operatorname{atan}`。

    ⚠️ **實測抓回來的（v0.41）**：難度 3 的 $g(y) = 1 + y^2$，所以
    $\int \frac{dy}{g} = \arctan y$，而 `sp.latex()` 預設把它印成
    `\operatorname{atan}`——**那不是任何課本會寫的東西**（課本寫 $\arctan$
    或 $\tan^{-1}$）。它渲染得出來、也不影響任何驗證，所以每一道數學閘門
    都不會有意見；與 v0.39 那三個排版錯是同一類，靠人眼才看得到。

    ⛔ 掃過全部 12 個題型 × 三個難度 × 8 個 seed，`\operatorname{...}` 只出現兩種：
    這個 `atan`，以及線性系統的 `\operatorname{tr}`（跡，**那個是對的**）。
    """
    return sp.latex(expr, inv_trig_style="full")


def _rhs_latex(f_x: sp.Expr, g_y: sp.Expr) -> str:
    """保留 f(x)·g(y) 的乘積形式，不要讓 simplify 把它展開混在一起。"""
    g_part = rf"\left({sp.latex(g_y)}\right)" if g_y.is_Add else sp.latex(g_y)
    f_part = sp.latex(f_x)
    if f_part == "1":
        return g_part
    if f_part == "-1":
        return f"-{g_part}"
    return f"{f_part} {g_part}"


DIFFICULTY_NOTES = {
    1: "$y' = f(x)\\,y$; integrate, then exponentiate",
    2: "$g(y) = y^2$, or $f(x)$ involving an exponential",
    3: "$g(y) = 1 + y^2$; the arctangent is needed to invert",
}


@register(
    TEMPLATE_ID,
    name="Separable Equations",
    chapter="First-Order ODEs",
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    f_x, g_y = _pick(rng, difficulty)

    lhs, rhs, sol = _solve_explicit(f_x, g_y)
    if sol is None:
        return None

    limit = {1: 14, 2: 24, 3: 30}[difficulty]
    if not is_pretty(sol, limit):
        return None

    # y' - f(x)g(y) = 0。g 含 y² 或 1+y² 時對 y 是非線性的，逐項診斷不適用。
    check = Check(
        var=x,
        kind="scalar",
        n_constants=1,
        order=1,
        unknown=_y,
        residual_expr=sp.Derivative(_y, x) - f_x * g_y.subs(yv, _y),
        linear=(g_y == yv),
    )

    statement_latex = rf"\frac{{dy}}{{dx}} = {_rhs_latex(f_x, g_y)}"

    steps = [
        Step(
            "Separate the variables",
            rf"\frac{{dy}}{{{sp.latex(g_y)}}} = {sp.latex(f_x)}\,dx",
            "Collect everything involving $y$ on the left and everything "
            "involving $x$ on the right.",
        ),
        Step(
            "Integrate both sides",
            rf"\int \frac{{dy}}{{{sp.latex(g_y)}}} = \int {sp.latex(f_x)}\,dx",
        ),
        Step(
            "Evaluate the integrals",
            # ⛔ 附錄 C.1：未知函數**全程保留自變數**，中間步驟也不例外。
            # `lhs` 是對 `yv`（一個裸的 Symbol）積出來的，所以印之前先換成
            # `_y`（也就是 $y(x)$）——⚠️ **換的是印出來的那一份，不是拿去驗算的那一份**。
            rf"{_tex(lhs.subs(yv, _y))} = {sp.latex(rhs)} + C",
            "Each side contributes a constant of integration; they combine "
            "into the single constant $C$.",
        ),
    ]

    if g_y == yv:
        steps.append(
            Step(
                "Exponentiate both sides",
                rf"{sp.latex(_y)} = e^{{{sp.latex(rhs)} + C}} = C_1 e^{{{sp.latex(rhs)}}}",
                "Rename $e^{C}$ as a new arbitrary constant $C_1$, since "
                "$e^{C}$ can be any nonzero number.",
            )
        )
    else:
        # ⛔ **這一步要把「反解」這個動作做出來，不能只印結果**（v0.41、D74）。
        #
        # 以前這裡印的是 `y(x) = sol`，而下一步「General solution」印的也是
        # `y(x) = sol`——**同一個 f-string，兩張卡片逐字相同**，第二張還沒有
        # 說明文字。實測 20 題：d1 0/20、**d2 12/20**、d3 20/20 會這樣。
        #
        # ⚠️ **為什麼另一個分支沒有這個問題**：它印的是一條鏈
        # `y(x) = e^{F+C} = C_1 e^{F}`，示範了「把 e^C 改名成 C_1」這個動作，
        # 所以後面再有一行乾淨的結論是合理的。這個分支以前直接跳到結論，
        # 於是那行結論被印了兩次。
        #
        # 老師選的作法是**加內容而不是刪行**：把隱式關係與反解後的結果
        # 用 ⟹ 串起來，兩個分支因此長得一樣（示範動作 → 乾淨結論）。
        # `sol` 本來就是 `solve(Eq(lhs, rhs + C_1), y)` 的解，所以左邊這一式
        # **不是為了排版寫出來的，它就是被解的那一式**。
        steps.append(
            Step(
                "Solve for y",
                rf"{_tex(lhs.subs(yv, _y))} = {sp.latex(rhs)} + C_1"
                rf" \quad\Longrightarrow\quad {sp.latex(_y)} = {sp.latex(sol)}",
                "Apply the inverse of the left-hand side to both sides. The two "
                "constants of integration have already been combined, so the "
                "single arbitrary constant is written $C_1$ from here on.",
            )
        )

    steps.append(Step("General solution", rf"{sp.latex(_y)} = {sp.latex(sol)}"))

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params={"f": sp.srepr(f_x), "g": sp.srepr(g_y)},
        statement="Find the general solution of the following differential equation. "
                  "Write the arbitrary constant as $C_1$.",
        statement_latex=statement_latex,
        answer_latex=rf"y(x) = {sp.latex(sol)}",
        answer_expr=sol,
        steps=steps,
        check=check,
    )
