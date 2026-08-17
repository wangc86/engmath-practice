"""一階線性方程 y' + p(x) y = q(x)（積分因子法）。

反向構造：p 與 q 都從白名單抽，保證積分因子 μ = e^{∫p} 是初等函數、
且 ∫μq 積得出來。通解由 y = (∫μq dx + C₁)/μ 組出，再代回原式驗證。
"""

from __future__ import annotations

import random

import sympy as sp

from .base import Problem, Step, register
from .pretty import is_pretty

x = sp.Symbol("x", positive=True)
C1 = sp.Symbol("C_1")

TEMPLATE_ID = "ode.first_order.linear"

NONZERO = (1, 2, 3, -1, -2, -3)


def _pick(rng: random.Random, difficulty: int) -> tuple[sp.Expr, sp.Expr]:
    """回傳 (p(x), q(x))。"""
    if difficulty == 1:
        # p 為常數、q 為低次多項式
        a = rng.choice(NONZERO)
        if rng.random() < 0.5:
            q = sp.Integer(rng.choice(NONZERO))
        else:
            q = rng.choice(NONZERO) * x + rng.choice((0, 1, 2, -1, -2))
        return sp.Integer(a), q

    if difficulty == 2:
        # p 為常數、q 含指數（刻意避開 m = -a 的共振情形，留給階段 2 的待定係數）
        a = rng.choice(NONZERO)
        m = rng.choice([v for v in (1, 2, 3, -1, -2, -3) if v != -a])
        k = rng.choice(NONZERO)
        return sp.Integer(a), k * sp.exp(m * x)

    # 難度 3：p = k/x，係數不是常數，積分因子為 x^k
    k = rng.choice((1, 2, 3, -1, -2))
    n = rng.choice((0, 1, 2))
    c = rng.choice(NONZERO)
    return sp.Integer(k) / x, c * x**n


def _lhs_latex(p: sp.Expr) -> str:
    """把 y' + p(x)y 排版成正常寫法，避免出現 y' + (-2) y 這種東西。"""
    if p.could_extract_minus_sign():
        sign, body = "-", sp.latex(-p)
    else:
        sign, body = "+", sp.latex(p)
    term = "y" if body == "1" else f"{body} y"
    return f"y' {sign} {term}"


DIFFICULTY_NOTES = {
    1: "$p(x)$ constant, $q(x)$ a polynomial",
    2: "$p(x)$ constant, $q(x)$ an exponential",
    3: "$p(x) = k/x$ (variable coefficient); integrating factor $x^{k}$",
}


@register(
    TEMPLATE_ID,
    name="First-Order Linear (Integrating Factor)",
    chapter="First-Order ODEs",
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    p, q = _pick(rng, difficulty)

    mu = sp.simplify(sp.exp(sp.integrate(p, x)))
    inner = sp.simplify(sp.integrate(sp.expand(mu * q), x))
    if inner.has(sp.Integral):
        return None

    sol = sp.simplify(sp.expand((inner + C1) / mu))

    limit = {1: 20, 2: 26, 3: 30}[difficulty]
    if not is_pretty(sol, limit):
        return None

    residual = sp.simplify(sp.diff(sol, x) + p * sol - q)

    statement_latex = rf"{_lhs_latex(p)} = {sp.latex(q)}"

    steps = [
        Step(
            "Write the equation in standard form",
            rf"y' + p(x)\,y = q(x),\quad p(x) = {sp.latex(p)},\ q(x) = {sp.latex(q)}",
            "First make sure the coefficient of $y'$ is $1$.",
        ),
        Step(
            "Compute the integrating factor",
            rf"\mu(x) = e^{{\int p\,dx}} = e^{{{sp.latex(sp.integrate(p, x))}}} = {sp.latex(mu)}",
        ),
        Step(
            "Multiply through by the integrating factor",
            rf"\frac{{d}}{{dx}}\left[{sp.latex(mu)}\,y\right] = {sp.latex(sp.expand(mu * q))}",
            "After multiplying by $\\mu$, the left-hand side is exactly the "
            "derivative of $\\mu y$ — this is the whole point of the method.",
        ),
        Step(
            "Integrate both sides",
            rf"{sp.latex(mu)}\,y = {sp.latex(inner)} + C_1",
        ),
        Step(
            "Solve for y",
            rf"y(x) = {sp.latex(sol)}",
        ),
    ]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params={"p": sp.srepr(p), "q": sp.srepr(q)},
        statement="Use the integrating factor method to find the general solution "
                  "of the following first-order linear equation.",
        statement_latex=statement_latex,
        answer_latex=rf"y(x) = {sp.latex(sol)}",
        answer_expr=sol,
        steps=steps,
        residual=residual,
    )
