"""可分離變數方程 y' = f(x) g(y)。

反向構造：先挑一組「積得出來、也解得回顯式 y」的 (f, g) 白名單組合，
再由 SymPy 算出積分與顯式解，最後把解代回原式驗證殘差為 0。
"""

from __future__ import annotations

import random

import sympy as sp

from .base import Problem, Step, register
from .pretty import is_pretty

x = sp.Symbol("x", positive=True)
yv = sp.Symbol("y")
C1 = sp.Symbol("C_1")

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
    1: "y' = f(x)·y，兩邊積分後取指數",
    2: "g(y) 為 y² 或 f(x) 含指數函數",
    3: "g(y) = 1 + y²，需用反正切函數反解",
}


@register(
    TEMPLATE_ID,
    name_zh="可分離變數",
    chapter="一階常微分方程",
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

    residual = sp.simplify(sp.diff(sol, x) - f_x * g_y.subs(yv, sol))

    statement_latex = rf"\frac{{dy}}{{dx}} = {_rhs_latex(f_x, g_y)}"

    steps = [
        Step(
            "分離變數",
            rf"\frac{{dy}}{{{sp.latex(g_y)}}} = {sp.latex(f_x)}\,dx",
            "把只含 y 的部分移到左邊、只含 x 的部分移到右邊。",
        ),
        Step(
            "兩邊積分",
            rf"\int \frac{{dy}}{{{sp.latex(g_y)}}} = \int {sp.latex(f_x)}\,dx",
        ),
        Step(
            "計算積分",
            rf"{sp.latex(lhs)} = {sp.latex(rhs)} + C",
            "左右兩邊各出現一個積分常數，可合併成一個 C。",
        ),
    ]

    if g_y == yv:
        steps.append(
            Step(
                "兩邊取指數",
                rf"y = e^{{{sp.latex(rhs)} + C}} = C_1 e^{{{sp.latex(rhs)}}}",
                "把 e^C 重新命名為新的任意常數 C₁（因為 e^C 可以是任意非零數）。",
            )
        )
    else:
        steps.append(
            Step(
                "解出 y",
                rf"y = {sp.latex(sol)}",
                "把隱式解對 y 反解，得到顯式的通解。",
            )
        )

    steps.append(Step("通解", rf"y(x) = {sp.latex(sol)}"))

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params={"f": sp.srepr(f_x), "g": sp.srepr(g_y)},
        statement_zh="求下列微分方程的通解（請以 C₁ 表示任意常數）：",
        statement_latex=statement_latex,
        answer_latex=rf"y(x) = {sp.latex(sol)}",
        answer_expr=sol,
        steps=steps,
        residual=residual,
    )
