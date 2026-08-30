"""一階線性系統 x' = A x（2×2 齊次，實相異特徵值）。

反向構造的關鍵技巧（PLAN.md §2.5）：取行列式為 ±1 的小整數矩陣 P，
令 A = P D P⁻¹。因為 det P = ±1，P⁻¹ 也是整數矩陣，所以 A 必為整數矩陣，
而 P 的兩個行向量**就是**特徵向量，必為小整數 —— 這正是「漂亮題目」的定義。

若改成隨機生 A 再算特徵向量，得到的多半是 [11/20, 1]ᵀ 這種東西。

---

**v0.26（2B6/2B7）改了兩處，都很小：**

1. 掛上相圖（`assets["phase_portrait_svg"]`）。它渲染在**逐步解答裡面**
   ——一張鞍點圖等於直接告訴學生兩個特徵值異號（§2.11.1）。
2. 原本的 `_classify()` 換成 `plot.describe()`。它只涵蓋三種情形
   （det<0 / tr<0 / else），這對只有實相異非零特徵值的本模組是**夠的**，
   但現在圖上也印分類，**兩份表就會有兩份表的問題**：文字說鞍點、
   圖畫成節點的時候不會有任何東西拋錯。

⚠️ **這個檔案的位置沒有動**（工作項 2a0 仍然保留給老師，沙箱不能 unlink）。
其餘三種情況在 `app/generator/systems/linear_2x2.py`。
"""

from __future__ import annotations

import itertools
import random

import sympy as sp

from .base import Check, Problem, Step, register
from .plot import describe, phase_portrait_svg
from .pretty import as_exponential

t = sp.Symbol("t", real=True)
C1, C2 = sp.symbols("C_1 C_2")

TEMPLATE_ID = "system.linear_2x2.real_distinct"

_SMALL = (-2, -1, 0, 1, 2)
P_CANDIDATES = [
    sp.Matrix([[a, b], [c, d]])
    for a, b, c, d in itertools.product(_SMALL, repeat=4)
    if abs(a * d - b * c) == 1
]

EIGENVALUES = (-3, -2, -1, 1, 2, 3)

DIFFICULTY_NOTES = {
    1: "Triangular matrix; one eigenvector lies on a coordinate axis",
    2: "General matrix; both eigenvectors must be computed",
    3: "General matrix with an initial condition; solve for $C_1$, $C_2$",
}

_BOUNDS = {1: 5, 2: 9, 3: 7}


def _shape_ok(A: sp.Matrix, difficulty: int) -> bool:
    """難度 1 用三角矩陣（有一個特徵向量是 e₁ 或 e₂，計算量明顯較小），
    難度 2、3 則要求兩個非對角元素都不為 0。"""
    triangular = A[0, 1] == 0 or A[1, 0] == 0
    return triangular if difficulty == 1 else not triangular


def _normalize_sign(v: sp.Matrix) -> sp.Matrix:
    """讓特徵向量的第一個非零分量為正，避免出現 [-1, -1]ᵀ 這種寫法。"""
    for c in v:
        if c != 0:
            return -v if c < 0 else v
    return v


def _matrix_latex(M: sp.Matrix) -> str:
    return sp.latex(M, mat_delim="(")


@register(
    TEMPLATE_ID,
    name="Linear System 2×2 (Distinct Real Eigenvalues)",
    chapter="Systems of First-Order Linear ODEs",
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    lam1, lam2 = rng.sample(EIGENVALUES, 2)
    P = rng.choice(P_CANDIDATES)
    A = sp.Matrix(P * sp.diag(lam1, lam2) * P.inv())

    if A.is_diagonal():                       # 對角矩陣的題目沒有教學價值
        return None
    if max(abs(v) for v in A) > _BOUNDS[difficulty]:
        return None
    if not _shape_ok(A, difficulty):
        return None

    v1 = _normalize_sign(sp.Matrix(P[:, 0]))
    v2 = _normalize_sign(sp.Matrix(P[:, 1]))

    sol = C1 * sp.exp(lam1 * t) * v1 + C2 * sp.exp(lam2 * t) * v2

    steps = [
        Step(
            "Form the characteristic equation",
            rf"\det(A - \lambda I) = \lambda^2 - {sp.latex(A.trace())}\lambda "
            rf"+ ({sp.latex(A.det())}) = 0",
            "The coefficients of the characteristic polynomial are "
            "$-\\operatorname{tr}A$ and $\\det A$.",
        ),
        Step("Find the eigenvalues", rf"\lambda_1 = {lam1},\quad \lambda_2 = {lam2}"),
        Step(
            "Find the eigenvectors",
            rf"\mathbf{{v}}_1 = {_matrix_latex(v1)},\quad "
            rf"\mathbf{{v}}_2 = {_matrix_latex(v2)}",
            "Solve $(A - \\lambda_i I)\\mathbf{v} = \\mathbf{0}$ for each "
            "eigenvalue. Any nonzero scalar multiple of an eigenvector is "
            "equally correct.",
        ),
        Step(
            "Assemble the general solution",
            rf"\mathbf{{x}}(t) = C_1 e^{{{lam1} t}}{_matrix_latex(v1)} "
            rf"+ C_2 e^{{{lam2} t}}{_matrix_latex(v2)}",
            "Two distinct real eigenvalues give two linearly independent "
            "solutions.",
        ),
        Step(
            "Write out the components",
            rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}",
        ),
        Step(
            "(Optional) Classify the equilibrium at the origin",
            rf"\operatorname{{tr}}A = {sp.latex(A.trace())},\quad "
            rf"\det A = {sp.latex(A.det())}",
            f"The signs of the trace and determinant identify the origin as "
            f"{describe(A)}. Reveal the phase portrait below to check this "
            f"against the picture.",
        ),
    ]

    check = Check(var=t, kind="system", n_constants=2, matrix=A, linear=True)
    statement = ("Find the general solution of the following system of "
                 "first-order linear differential equations.")
    answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"
    params = {"A": [[int(c) for c in A.row(i)] for i in range(2)],
              "eigenvalues": [lam1, lam2]}

    statement_latex = rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}}"

    if difficulty == 3:
        x0 = sp.Matrix([rng.choice((-3, -2, -1, 1, 2, 3)) for _ in range(2)])
        consts = sp.solve(list(sol.subs(t, 0) - x0), [C1, C2], dict=True)
        if not consts:
            return None
        # 初始向量剛好落在某個特徵方向上時，答案只剩一項，失去教學價值
        if consts[0][C1] == 0 or consts[0][C2] == 0:
            return None
        # 這裡刻意不用 `sp.simplify` 的結果直接當答案：λ = ±1 時它會把某些分量
        # 改寫成 sinh/cosh，同一個向量的兩個分量就用了兩套函數族（PLAN.md §2.9）。
        # 先 simplify 收斂係數，再一律改寫回指數形式。
        sol = as_exponential(sp.simplify(sol.subs(consts[0])))
        if any(sp.simplify(c).has(C1, C2) for c in sol):
            return None
        # 初值問題：常數已被定值，因此 n_constants = 0，判定改為嚴格等價
        check = Check(var=t, kind="system", n_constants=0, matrix=A,
                      ic_point=sp.Integer(0), ic_value=x0, linear=True)
        statement_latex = (
            rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}},\quad "
            rf"\mathbf{{x}}(0) = {_matrix_latex(x0)}"
        )
        statement = ("Solve the following initial value problem for a system of "
                     "first-order linear differential equations.")
        answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"
        params["x0"] = [int(c) for c in x0]
        steps = steps[:-1] + [
            Step(
                "Apply the initial condition",
                rf"C_1 {_matrix_latex(v1)} + C_2 {_matrix_latex(v2)} = {_matrix_latex(x0)}",
                "At $t = 0$ every exponential equals $1$, which leaves a "
                "$2\\times 2$ linear system for $C_1$ and $C_2$.",
            ),
            Step(
                "Solve for the constants",
                rf"C_1 = {sp.latex(consts[0][C1])},\quad C_2 = {sp.latex(consts[0][C2])}",
            ),
            Step("Solution of the initial value problem", answer_latex),
            steps[-1],
        ]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=sol,
        steps=steps,
        check=check,
        # v0.26（2B6/2B7）：⛔ 這張圖只能出現在 `<details>` 裡（§2.11.1）。
        assets={"phase_portrait_svg": phase_portrait_svg(A)},
    )
