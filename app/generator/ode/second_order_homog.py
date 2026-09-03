"""二階常係數齊次方程 y'' + a₁y' + a₀y = 0。

反向構造的教科書範例：**先選特徵根，再算係數**。
- 實相異根 r₁ ≠ r₂ → a₁ = -(r₁+r₂), a₀ = r₁r₂
- 重根 r        → a₁ = -2r,        a₀ = r²
- 複數根 α ± βi → a₁ = -2α,        a₀ = α² + β²

三種情況的係數必為整數，答案必為漂亮形式，完全不需要拒絕抽樣。
"""

from __future__ import annotations

import random

import sympy as sp

from ..base import Check, Problem, Step, register

x = sp.Symbol("x", positive=True)
C1, C2 = sp.symbols("C_1 C_2")
_y = sp.Function("y")(x)          # 判定用的未知函數 y(x)

TEMPLATE_ID = "ode.second_order.homogeneous"

ROOTS = (-3, -2, -1, 1, 2, 3)
ALPHAS = (-2, -1, 0, 1, 2)
BETAS = (1, 2, 3)


def _poly_latex(a1: int, a0: int) -> str:
    """把 y'' + a₁y' + a₀y = 0 排版成正常的數學寫法（不出現 + -3）。"""
    parts = ["y''"]
    for coeff, term in ((a1, "y'"), (a0, "y")):
        if coeff == 0:
            continue
        sign = "+" if coeff > 0 else "-"
        mag = abs(coeff)
        mag_str = "" if mag == 1 else str(mag)
        parts.append(f"{sign} {mag_str}{term}")
    return " ".join(parts) + " = 0"


DIFFICULTY_NOTES = {
    1: "Two distinct real roots",
    2: "A repeated root",
    3: "A pair of complex conjugate roots",
}


@register(
    TEMPLATE_ID,
    name="Second-Order Homogeneous (Constant Coefficients)",
    chapter="Second-Order ODEs",
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    r = sp.Symbol("r")

    if difficulty == 1:
        r1, r2 = rng.sample(ROOTS, 2)
        a1, a0 = -(r1 + r2), r1 * r2
        sol = C1 * sp.exp(r1 * x) + C2 * sp.exp(r2 * x)
        case_name = "two distinct real roots"
        root_latex = rf"r_1 = {r1},\quad r_2 = {r2}"
        basis_note = ("Each distinct real root contributes one exponential "
                      "solution, and the two are linearly independent.")
        params = {"case": "real_distinct", "r1": r1, "r2": r2}

    elif difficulty == 2:
        r1 = rng.choice(ROOTS)
        r2 = r1
        a1, a0 = -2 * r1, r1**2
        sol = (C1 + C2 * x) * sp.exp(r1 * x)
        case_name = "a repeated root"
        root_latex = rf"r_1 = r_2 = {r1}\quad(\text{{repeated}})"
        basis_note = ("A repeated root yields only one solution $e^{rx}$; the "
                      "second linearly independent solution needs an extra "
                      "factor of $x$.")
        params = {"case": "repeated", "r": r1}

    else:
        alpha = rng.choice(ALPHAS)
        beta = rng.choice(BETAS)
        a1, a0 = -2 * alpha, alpha**2 + beta**2
        sol = sp.exp(alpha * x) * (C1 * sp.cos(beta * x) + C2 * sp.sin(beta * x))
        case_name = "complex conjugate roots"
        root_latex = rf"r = {alpha} \pm {beta}i"
        basis_note = ("Use Euler's formula to rewrite the complex exponentials "
                      "in real form, so that no $i$ appears in the answer.")
        params = {"case": "complex", "alpha": alpha, "beta": beta}
        r1 = r2 = None

    char_latex = sp.latex(sp.Eq(r**2 + a1 * r + a0, 0))
    check = Check(
        var=x,
        kind="scalar",
        n_constants=2,           # 二階通解要兩個任意常數
        order=2,
        unknown=_y,
        residual_expr=sp.Derivative(_y, (x, 2)) + a1 * sp.Derivative(_y, x) + a0 * _y,
        linear=True,             # 齊次且線性 → 判錯時可做逐項診斷
    )

    steps = [
        Step(
            "Write the characteristic equation",
            char_latex,
            "Substituting $y = e^{rx}$ into the homogeneous equation lets the "
            "exponential cancel, leaving a quadratic in $r$.",
        ),
        Step(f"Find the characteristic roots ({case_name})", root_latex),
        Step("Write the corresponding basis of solutions",
             rf"y(x) = {sp.latex(sol)}", basis_note),
        Step("General solution", rf"y(x) = {sp.latex(sp.simplify(sol))}"),
    ]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement="Find the general solution of the following second-order "
                  "homogeneous equation with constant coefficients.",
        statement_latex=_poly_latex(int(a1), int(a0)),
        answer_latex=rf"y(x) = {sp.latex(sol)}",
        answer_expr=sol,
        steps=steps,
        check=check,
    )
