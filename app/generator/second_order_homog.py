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

from .base import Problem, Step, register

x = sp.Symbol("x", positive=True)
C1, C2 = sp.symbols("C_1 C_2")

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
    1: "特徵方程式有兩相異實根",
    2: "特徵方程式有重根",
    3: "特徵方程式有一對共軛複數根",
}


@register(
    TEMPLATE_ID,
    name_zh="二階常係數齊次",
    chapter="二階常微分方程",
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    r = sp.Symbol("r")

    if difficulty == 1:
        r1, r2 = rng.sample(ROOTS, 2)
        a1, a0 = -(r1 + r2), r1 * r2
        sol = C1 * sp.exp(r1 * x) + C2 * sp.exp(r2 * x)
        case_zh = "兩相異實根"
        root_latex = rf"r_1 = {r1},\quad r_2 = {r2}"
        basis_note = "兩個相異實根各給一個指數解，兩者線性獨立。"
        params = {"case": "real_distinct", "r1": r1, "r2": r2}

    elif difficulty == 2:
        r1 = rng.choice(ROOTS)
        r2 = r1
        a1, a0 = -2 * r1, r1**2
        sol = (C1 + C2 * x) * sp.exp(r1 * x)
        case_zh = "重根"
        root_latex = rf"r_1 = r_2 = {r1}\quad(\text{{重根}})"
        basis_note = "重根只給得出一個解 e^{rx}，第二個線性獨立解要再乘上 x。"
        params = {"case": "repeated", "r": r1}

    else:
        alpha = rng.choice(ALPHAS)
        beta = rng.choice(BETAS)
        a1, a0 = -2 * alpha, alpha**2 + beta**2
        sol = sp.exp(alpha * x) * (C1 * sp.cos(beta * x) + C2 * sp.sin(beta * x))
        case_zh = "共軛複數根"
        root_latex = rf"r = {alpha} \pm {beta}i"
        basis_note = "用尤拉公式把複數指數解改寫成實數形式，避免答案裡出現 i。"
        params = {"case": "complex", "alpha": alpha, "beta": beta}
        r1 = r2 = None

    char_latex = sp.latex(sp.Eq(r**2 + a1 * r + a0, 0))
    residual = sp.simplify(sp.diff(sol, x, 2) + a1 * sp.diff(sol, x) + a0 * sol)

    steps = [
        Step(
            "寫出特徵方程式",
            char_latex,
            "把 y = e^{rx} 代入齊次方程，指數項可以約掉，剩下 r 的二次式。",
        ),
        Step(f"求特徵根（{case_zh}）", root_latex),
        Step("寫出對應的基本解", rf"y(x) = {sp.latex(sol)}", basis_note),
        Step("通解", rf"y(x) = {sp.latex(sp.simplify(sol))}"),
    ]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement_zh="求下列二階常係數齊次方程的通解：",
        statement_latex=_poly_latex(int(a1), int(a0)),
        answer_latex=rf"y(x) = {sp.latex(sol)}",
        answer_expr=sol,
        steps=steps,
        residual=residual,
    )
