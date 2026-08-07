"""一階線性系統 x' = A x（2×2 齊次，實相異特徵值）。

反向構造的關鍵技巧（PLAN.md §2.5）：取行列式為 ±1 的小整數矩陣 P，
令 A = P D P⁻¹。因為 det P = ±1，P⁻¹ 也是整數矩陣，所以 A 必為整數矩陣，
而 P 的兩個行向量**就是**特徵向量，必為小整數 —— 這正是「漂亮題目」的定義。

若改成隨機生 A 再算特徵向量，得到的多半是 [11/20, 1]ᵀ 這種東西。
"""

from __future__ import annotations

import itertools
import random

import sympy as sp

from .base import Problem, Step, register

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
    1: "三角矩陣，其中一個特徵向量落在座標軸上",
    2: "一般矩陣，兩個特徵向量都要自己解",
    3: "一般矩陣 + 初始條件，需再解出 C₁、C₂",
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


def _classify(A: sp.Matrix) -> str:
    tr, det = A.trace(), A.det()
    if det < 0:
        return "鞍點（saddle，不穩定）"
    return "穩定節點（stable node）" if tr < 0 else "不穩定節點（unstable node）"


def _matrix_latex(M: sp.Matrix) -> str:
    return sp.latex(M, mat_delim="(")


@register(
    TEMPLATE_ID,
    name_zh="一階線性系統 2×2（實相異特徵值）",
    chapter="一階線性系統",
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
            "求特徵方程式",
            rf"\det(A - \lambda I) = \lambda^2 - {sp.latex(A.trace())}\lambda "
            rf"+ ({sp.latex(A.det())}) = 0",
            "特徵多項式的係數就是 -tr(A) 與 det(A)。",
        ),
        Step("求特徵值", rf"\lambda_1 = {lam1},\quad \lambda_2 = {lam2}"),
        Step(
            "求特徵向量",
            rf"\mathbf{{v}}_1 = {_matrix_latex(v1)},\quad "
            rf"\mathbf{{v}}_2 = {_matrix_latex(v2)}",
            "分別解 (A - λᵢI)v = 0。特徵向量差一個非零倍數都算對。",
        ),
        Step(
            "組出通解",
            rf"\mathbf{{x}}(t) = C_1 e^{{{lam1} t}}{_matrix_latex(v1)} "
            rf"+ C_2 e^{{{lam2} t}}{_matrix_latex(v2)}",
            "兩個相異實特徵值各給一個解，兩者線性獨立。",
        ),
        Step(
            "展開成分量形式",
            rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}",
        ),
        Step(
            "（補充）平衡點的穩定性",
            rf"\operatorname{{tr}}A = {sp.latex(A.trace())},\quad "
            rf"\det A = {sp.latex(A.det())}",
            f"由 tr 與 det 的符號可判定原點為{_classify(A)}。",
        ),
    ]

    residual = sp.simplify(sp.diff(sol, t) - A * sol)
    statement_zh = "求下列一階線性系統的通解："
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
        sol = sp.simplify(sol.subs(consts[0]))
        if any(sp.simplify(c).has(C1, C2) for c in sol):
            return None
        residual = sp.Matrix.vstack(
            sp.simplify(sp.diff(sol, t) - A * sol),
            sp.simplify(sol.subs(t, 0) - x0),
        )
        statement_latex = (
            rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}},\quad "
            rf"\mathbf{{x}}(0) = {_matrix_latex(x0)}"
        )
        statement_zh = "求下列一階線性系統初值問題的解："
        answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"
        params["x0"] = [int(c) for c in x0]
        steps = steps[:-1] + [
            Step(
                "代入初始條件",
                rf"C_1 {_matrix_latex(v1)} + C_2 {_matrix_latex(v2)} = {_matrix_latex(x0)}",
                "在 t = 0 時 e^{λt} = 1，因此得到一組 C₁、C₂ 的二元一次方程。",
            ),
            Step(
                "解出常數",
                rf"C_1 = {sp.latex(consts[0][C1])},\quad C_2 = {sp.latex(consts[0][C2])}",
            ),
            Step("初值問題的解", answer_latex),
            steps[-1],
        ]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement_zh=statement_zh,
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=sol,
        steps=steps,
        residual=residual,
    )
