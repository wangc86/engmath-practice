r"""一階線性系統 $\mathbf{x}' = A\mathbf{x}$ 的其餘三種情況（PLAN.md §2.5(b)(c)(d)，
階段 2A 的工作項 **2d**）。

既有的 `system.linear_2x2.real_distinct` 只涵蓋實相異特徵值。這裡補上：

- **重根**（缺陷矩陣，需要廣義特徵向量）
- **複數特徵值**（答案必須是**實數形**）
- **非齊次**（待定係數；難度 3 是共振）

---

## 反向構造：三種情況共用同一個技巧，只換中間那個矩陣

取 $\det P = \pm 1$ 的小整數矩陣 $P$（則 $P^{-1}$ 也是整數矩陣），令 $A = PMP^{-1}$。
$M$ 換成什麼，就得到什麼情況：

| 情況 | $M$ | 副產品（**這是關鍵**） |
|---|---|---|
| 實相異 | $\operatorname{diag}(\lambda_1, \lambda_2)$ | $P$ 的兩個行**就是**兩個特徵向量 |
| 重根 | $\begin{pmatrix}\lambda & 1\\ 0 & \lambda\end{pmatrix}$ | $P_{:,1}$ 是特徵向量 $\mathbf{v}$，$P_{:,2}$ **就是**廣義特徵向量 $\mathbf{w}$ |
| 複數 | $\begin{pmatrix}\alpha & \beta\\ -\beta & \alpha\end{pmatrix}$ | $\mathbf{v} = P_{:,1} + i P_{:,2}$，所以實數形要用的 $\mathbf{a}, \mathbf{b}$ 也是 $P$ 的兩行 |

第三欄才是這個技巧真正的價值：**要在答案裡出現的那幾個向量，全部是 $P$ 的行，
所以全部是小整數**。若改成隨機生 $A$ 再去算，重根那一格要解一個奇異的線性系統
（`linsolve` 回一個帶自由參數的解，還要自己挑一組），複數那一格會拿到
$[b, \alpha - a + \beta i]^T$ 這種東西——都能算，但答案就開始有分數了。

⚠️ 重根那一格的第三欄**是一個需要檢查的宣稱，不是定義**：$AP = PM$ 的第二行
展開是 $A\mathbf{w} = \mathbf{v} + \lambda\mathbf{w}$，也就是
$(A - \lambda I)\mathbf{w} = \mathbf{v}$——正好是廣義特徵向量的定義式。
`test_the_generalized_eigenvector_really_satisfies_its_defining_equation` 盯著它。

---

## 非齊次為什麼選待定係數，不選參數變異

**選待定係數。** 理由不是「比較簡單」，是**反向構造在這個方法上是免費的，
在另一個方法上不成立**：

先挑一個漂亮的特解 $\mathbf{x}_p$，再令 $\mathbf{g} = \mathbf{x}_p' - A\mathbf{x}_p$。
$\mathbf{x}_p$ 的分量是小整數乘上 $e^{st}$，$A$ 是小整數矩陣，所以 $\mathbf{g}$
**必然**也是小整數乘上 $e^{st}$——不需要任何拒絕抽樣，不需要積分。

參數變異法要算 $\Phi(t)\int \Phi^{-1}(t)\mathbf{g}(t)\,\mathrm{d}t$。反向構造在這裡
幫不上忙：我們挑的是 $\mathbf{x}_p$，而學生要算的是那個積分——**一個漂亮的
$\mathbf{x}_p$ 完全不保證那個積分好算**，反過來也一樣。這正是 §7 #14 卡住
純量題型 2e 的同一件事（隨機的 $g$ 幾乎必然積不出初等形式），只是在系統上更嚴重：
$\Phi^{-1}$ 的每一項都會乘進去。

**代價，誠實地說**：這個題型完全沒有練到參數變異法。它的教學價值在
「$\Phi^{-1}$ 這條路對任意 $\mathbf{g}$ 都成立」，而待定係數只對指數／多項式／
三角這幾族成立。若老師要那一塊，它應該是一個**獨立的題型**、配一份
$\mathbf{g}$ 的白名單（做法與 §7 #14 給 2e 的建議相同），不是把它塞進這一個。

---

## ⛔ 複數那一格：答案不得出現 $i$

D11 的顯示形式規則原本只說「不得出現 $\sinh/\cosh$」（那條是為
`real_distinct` 難度 3 寫的）。複數特徵值把規則往外推了一格：
$\mathbf{x} = C_1 e^{(\alpha + i\beta)t}\mathbf{v}$ **在數學上完全正確**，
殘差是 0，驗證閘門會放行——但那不是這門課要的答案，而且學生代不回實數初值。

因此本模組直接組實數形（`_real_basis()`），**不走 `sp.exp(A*t)` 再 `rewrite`**
（§2.5(c) 實測那條路慢到不可接受）。守它的是
`test_complex_system_answers_are_real_valued`，而那一項檢查的是 `answer_expr`
裡有沒有 `I`——**不是**檢查 LaTeX 字串裡有沒有 `i`，因為 $\sin$ 裡面就有一個 `i`。
"""

from __future__ import annotations

import itertools
import random

import sympy as sp

from ..base import Check, Problem, Step, register
from ..plot import describe, phase_portrait_svg
from ..pretty import as_exponential

t = sp.Symbol("t", real=True)
C1, C2 = sp.symbols("C_1 C_2")

REPEATED_ID = "system.linear_2x2.repeated"
COMPLEX_ID = "system.linear_2x2.complex"
NONHOMOGENEOUS_ID = "system.linear_2x2.nonhomogeneous"

CHAPTER = "Systems of First-Order Linear ODEs"

_SMALL = (-2, -1, 0, 1, 2)
#: 與 `real_distinct.py` 同一份候選（104 個），逐項相同（實測 `a == b` 為真）。
#: ⚠️ **原本不 import 的理由已經過期**：那句話寫的是「那個模組是 2a0 要搬的檔案，
#: 讓新模組去 import 它等於在搬家前多綁一條線」，而 2a0 已經做完（v0.31）。
#: 這裡**刻意留著這份重複而不是順手合併**——合併是行為可能改變的變更
#: （抽樣走的是這個 list 的順序），不屬於「只搬檔案」那一項的範圍。
#: 要合併就要單獨做一次，並且用同一顆 seed 比對前後產生的題目。
#: 旁邊的 `classify.py` 已經是 import 的那一邊，所以兩種寫法現在並存。
P_CANDIDATES = [
    sp.Matrix([[a, b], [c, d]])
    for a, b, c, d in itertools.product(_SMALL, repeat=4)
    if abs(a * d - b * c) == 1
]

_IC_VALUES = (-3, -2, -1, 1, 2, 3)


def _matrix_latex(M: sp.Matrix) -> str:
    return sp.latex(M, mat_delim="(")


def _normalize_pair(v: sp.Matrix, w: sp.Matrix) -> tuple[sp.Matrix, sp.Matrix]:
    r"""讓 $\mathbf{v}$ 的第一個非零分量為正，**並且對 $\mathbf{w}$ 做同樣的翻轉**。

    ⛔ 只翻 $\mathbf{v}$ 是錯的，而且錯得很安靜：$(A - \lambda I)\mathbf{w}
    = \mathbf{v}$ 這個關係會斷掉，於是逐步解答第 4 步印出來的 $\mathbf{w}$
    **不滿足它自己那一行寫的方程**。答案的殘差仍然是 0（因為 $-\mathbf{v}$
    也是特徵向量、$-\mathbf{w}$ 也是對應的廣義特徵向量），所以驗證閘門
    不會攔它——只有讀解答的學生會發現。

    同樣的話對複數那一格成立：$\mathbf{v} = \mathbf{a} + i\mathbf{b}$，
    翻 $\mathbf{a}$ 不翻 $\mathbf{b}$ 得到的不是 $\pm\mathbf{v}$，是別的向量。
    """
    for component in v:
        if component != 0:
            return (-v, -w) if component < 0 else (v, w)
    return v, w


def _pretty_matrix(A: sp.Matrix, bound: int) -> bool:
    return max(abs(v) for v in A) <= bound


def _stability_step(A: sp.Matrix) -> Step:
    """每個題型最後那一步：用 tr 與 det 判斷原點的類型。

    ⚠️ 分類的字串來自 `plot.describe()`，也就是**畫在相圖上的同一份表**。
    共用是刻意的：若這一步自己寫一份，就會出現「文字說鞍點、圖畫成節點」
    的可能，而那種不一致沒有任何測試抓得到——兩邊都不會拋錯。
    """
    return Step(
        "(Optional) Classify the equilibrium at the origin",
        rf"\operatorname{{tr}}A = {sp.latex(A.trace())},\quad "
        rf"\det A = {sp.latex(A.det())},\quad "
        rf"\Delta = \operatorname{{tr}}^2 A - 4\det A = "
        rf"{sp.latex(A.trace()**2 - 4*A.det())}",
        f"The trace, the determinant and the discriminant together identify the "
        f"origin as {describe(A)}. Reveal the phase portrait below to check "
        f"this against the picture.",
    )


def _portrait(A: sp.Matrix) -> dict[str, str]:
    r"""相圖，**只給齊次題型**。

    ⛔ **非齊次的題目刻意沒有相圖**，而這是一個判斷不是遺漏。
    $\mathbf{x}' = A\mathbf{x} + \mathbf{g}(t)$ 在 $\mathbf{g}$ 含 $t$ 時
    **根本不是自守系統**——相平面上的軌跡會互相穿越，「相圖」這個東西
    不存在。畫齊次部分的圖擺在旁邊，看起來完全合理（它是一張正確的圖），
    只是它畫的不是這一題的方程。

    PLAN §6 階段 2B 的交付寫的是「2×2 線性系統題型**全部**附相圖」，
    所以這是一處明確的規劃落差，記在 §2.11 的落地紀錄裡。
    """
    return {"phase_portrait_svg": phase_portrait_svg(A)}


# =========================================================================
# (b) 重根：缺陷矩陣與廣義特徵向量
# =========================================================================

REPEATED_EIGENVALUES = (-3, -2, -1, 1, 2, 3)

REPEATED_NOTES = {
    1: "Triangular matrix; the single eigenvector lies on a coordinate axis",
    2: "General matrix; both $\\mathbf{v}$ and $\\mathbf{w}$ must be computed",
    3: "General matrix with an initial condition; solve for $C_1$, $C_2$",
}

_REPEATED_BOUND = {1: 6, 2: 9, 3: 8}


@register(
    REPEATED_ID,
    name="Linear System 2×2 (Repeated Eigenvalue)",
    chapter=CHAPTER,
    difficulty_notes=REPEATED_NOTES,
)
def generate_repeated(rng: random.Random, difficulty: int) -> Problem | None:
    lam = rng.choice(REPEATED_EIGENVALUES)
    P = rng.choice(P_CANDIDATES)
    A = sp.Matrix(P * sp.Matrix([[lam, 1], [0, lam]]) * P.inv())

    if A.is_diagonal():                    # λI：每個向量都是特徵向量，題目沒有意義
        return None
    if not _pretty_matrix(A, _REPEATED_BOUND[difficulty]):
        return None
    triangular = A[0, 1] == 0 or A[1, 0] == 0
    if triangular != (difficulty == 1):
        return None

    v, w = _normalize_pair(sp.Matrix(P[:, 0]), sp.Matrix(P[:, 1]))
    sol = C1 * sp.exp(lam * t) * v + C2 * sp.exp(lam * t) * (t * v + w)

    steps = [
        Step(
            "Form the characteristic equation",
            rf"\det(A - \lambda I) = \lambda^2 - {sp.latex(A.trace())}\lambda "
            rf"+ ({sp.latex(A.det())}) = 0",
        ),
        Step(
            "Solve it — the root is repeated",
            rf"\lambda^2 - {sp.latex(A.trace())}\lambda + ({sp.latex(A.det())}) "
            rf"= (\lambda - ({lam}))^2 = 0,\quad \lambda = {lam}",
            "The discriminant $\\operatorname{tr}^2 A - 4\\det A$ is zero, so "
            "there is one eigenvalue of algebraic multiplicity $2$.",
        ),
        Step(
            "Find the eigenvector",
            rf"(A - ({lam})I)\mathbf{{v}} = \mathbf{{0}} \;\Rightarrow\; "
            rf"\mathbf{{v}} = {_matrix_latex(v)}",
            "Row-reducing $A - \\lambda I$ leaves a single equation, so the "
            "eigenspace is only one-dimensional. Such a matrix is called "
            "defective: two independent solutions cannot both come from "
            "eigenvectors.",
        ),
        Step(
            "Find a generalized eigenvector",
            rf"(A - ({lam})I)\mathbf{{w}} = \mathbf{{v}} \;\Rightarrow\; "
            rf"\mathbf{{w}} = {_matrix_latex(w)}",
            "This system is solvable precisely because $\\mathbf{v}$ lies in the "
            "range of $A - \\lambda I$. Any solution works; adding a multiple of "
            "$\\mathbf{v}$ to $\\mathbf{w}$ only shifts $C_1$.",
        ),
        Step(
            "Build the second solution",
            rf"\mathbf{{x}}_2(t) = e^{{{lam} t}}\left(t\,{_matrix_latex(v)} "
            rf"+ {_matrix_latex(w)}\right)",
            "Substituting $e^{\\lambda t}(t\\mathbf{v} + \\mathbf{w})$ into "
            "$\\mathbf{x}' = A\\mathbf{x}$ gives $\\mathbf{v} + \\lambda "
            "\\mathbf{w} = A\\mathbf{w}$, which is exactly the equation "
            "$\\mathbf{w}$ was chosen to satisfy. The bare $e^{\\lambda t}"
            "\\mathbf{v}t$ on its own is *not* a solution — the $\\mathbf{w}$ "
            "term is what fixes it up.",
        ),
        Step(
            "Assemble the general solution",
            rf"\mathbf{{x}}(t) = C_1 e^{{{lam} t}}{_matrix_latex(v)} "
            rf"+ C_2 e^{{{lam} t}}\left(t\,{_matrix_latex(v)} + {_matrix_latex(w)}\right)",
        ),
        Step("Write out the components", rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"),
        _stability_step(A),
    ]

    check = Check(var=t, kind="system", n_constants=2, matrix=A, linear=True)
    statement = ("Find the general solution of the following system of "
                 "first-order linear differential equations.")
    statement_latex = rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}}"
    answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"
    params = {"A": [[int(c) for c in A.row(i)] for i in range(2)],
              "eigenvalues": [lam, lam],
              "v": [int(c) for c in v], "w": [int(c) for c in w]}

    if difficulty == 3:
        x0 = sp.Matrix([rng.choice(_IC_VALUES) for _ in range(2)])
        consts = sp.solve(list(sol.subs(t, 0) - x0), [C1, C2], dict=True)
        if not consts:
            return None
        if consts[0][C2] == 0:            # 落在特徵方向上 → 少了 t 那一項，失去重點
            return None
        sol = as_exponential(sp.simplify(sol.subs(consts[0])))
        if any(sp.simplify(c).has(C1, C2) for c in sol):
            return None
        check = Check(var=t, kind="system", n_constants=0, matrix=A,
                      ic_point=sp.Integer(0), ic_value=x0, linear=True)
        statement = ("Solve the following initial value problem for a system of "
                     "first-order linear differential equations.")
        statement_latex = (
            rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}},\quad "
            rf"\mathbf{{x}}(0) = {_matrix_latex(x0)}"
        )
        answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"
        params["x0"] = [int(c) for c in x0]
        steps = steps[:-2] + [
            Step(
                "Apply the initial condition",
                rf"C_1 {_matrix_latex(v)} + C_2 {_matrix_latex(w)} = {_matrix_latex(x0)}",
                "At $t = 0$ the exponential is $1$ and the $t\\mathbf{v}$ term "
                "vanishes, so only $\\mathbf{v}$ and $\\mathbf{w}$ survive.",
            ),
            Step(
                "Solve for the constants",
                rf"C_1 = {sp.latex(consts[0][C1])},\quad C_2 = {sp.latex(consts[0][C2])}",
            ),
            Step("Solution of the initial value problem", answer_latex),
            steps[-1],
        ]

    return Problem(
        template_id=REPEATED_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=sol,
        steps=steps,
        check=check,
        assets=_portrait(A),
    )


# =========================================================================
# (c) 複數特徵值：答案一律寫成實數形
# =========================================================================

COMPLEX_NOTES = {
    1: "Purely imaginary eigenvalues ($\\operatorname{tr}A = 0$): a center, no exponential factor",
    2: "General complex pair $\\alpha \\pm \\beta i$: a spiral",
    3: "Complex pair with an initial condition; solve for $C_1$, $C_2$",
}

_ALPHA = {1: (0,), 2: (-2, -1, 1, 2), 3: (-1, 1)}
_BETA = {1: (1, 2), 2: (1, 2, 3), 3: (1, 2)}
_COMPLEX_BOUND = {1: 6, 2: 7, 3: 6}


def _real_basis(alpha: int, beta: int, a_vec: sp.Matrix, b_vec: sp.Matrix):
    r"""$\lambda = \alpha + i\beta$、$\mathbf{v} = \mathbf{a} + i\mathbf{b}$ 的實數基底。

    $e^{\lambda t}\mathbf{v}
     = e^{\alpha t}\bigl[(\mathbf{a}\cos\beta t - \mathbf{b}\sin\beta t)
       + i(\mathbf{a}\sin\beta t + \mathbf{b}\cos\beta t)\bigr]$，
    而實部與虛部各自都是解。
    """
    e = sp.exp(alpha * t)
    x1 = e * (a_vec * sp.cos(beta * t) - b_vec * sp.sin(beta * t))
    x2 = e * (a_vec * sp.sin(beta * t) + b_vec * sp.cos(beta * t))
    return sp.Matrix(x1), sp.Matrix(x2)


def _collect_trig(vec: sp.Matrix, alpha: int, beta: int) -> sp.Matrix:
    r"""把每個分量整理成 $e^{\alpha t}\bigl(\square\cos\beta t + \square\sin\beta t\bigr)$。

    **這不是美化，是可讀性的實質差別。** 完全展開的分量長這樣：

    $$C_1 e^{2t}\sin t + C_1 e^{2t}\cos t + C_2 e^{2t}\sin t - C_2 e^{2t}\cos t$$

    四項、每一項都帶著同一個 $e^{2t}$，而學生要在這四項裡自己看出「其實是
    兩個相位」。整理過的版本是課本的寫法：

    $$e^{2t}\bigl[(C_1 - C_2)\cos t + (C_1 + C_2)\sin t\bigr]$$

    順帶把 `pretty.ugliness()` 的分數從 29–35 降到 16–22
    （**先有可讀性的理由，分數是附帶結果**——反過來就是為了讓測試變綠
    而改答案，那是規則 9 第 3 條在講的事）。
    """
    e = sp.exp(alpha * t)
    trig = [sp.cos(beta * t), sp.sin(beta * t)]
    out = []
    for component in vec:
        # ⚠️ 刻意用「乘上 $e^{-\alpha t}$ + `expand`」而不是 `simplify(component / e)`。
        # 兩者結果相同（SymPy 的 `Mul` 自己會把同底的冪次併掉），但 `simplify`
        # 在這個型別上要 0.7 秒一題，30 題的測試就多 20 秒——而它多做的事情
        # 這裡一件都用不到。
        body = sp.collect(sp.expand(component * sp.exp(-alpha * t)), trig)
        out.append(body if alpha == 0 else e * body)
    return sp.Matrix(out)


@register(
    COMPLEX_ID,
    name="Linear System 2×2 (Complex Eigenvalues)",
    chapter=CHAPTER,
    difficulty_notes=COMPLEX_NOTES,
)
def generate_complex(rng: random.Random, difficulty: int) -> Problem | None:
    alpha = rng.choice(_ALPHA[difficulty])
    beta = rng.choice(_BETA[difficulty])
    P = rng.choice(P_CANDIDATES)
    R = sp.Matrix([[alpha, beta], [-beta, alpha]])
    A = sp.Matrix(P * R * P.inv())

    if not _pretty_matrix(A, _COMPLEX_BOUND[difficulty]):
        return None
    if A[0, 1] == 0 or A[1, 0] == 0:
        # 三角矩陣的特徵值是對角線元素，不可能是複數 —— 這個分支其實到不了，
        # 但留著它比留一句註解可靠：哪天 R 的形狀被動了，這裡會擋下來。
        return None
    if difficulty == 1 and 0 not in P[:, 0] and 0 not in P[:, 1]:
        # 難度 1 要求 $\mathbf{a}$ 或 $\mathbf{b}$ 其中一個是座標方向。
        # 這與 `real_distinct` 難度 1 用三角矩陣是同一個念頭：**讓最簡單的那一格
        # 真的最簡單**。副作用是有一個分量只剩單一個三角項，答案短一半。
        return None

    a_vec, b_vec = _normalize_pair(sp.Matrix(P[:, 0]), sp.Matrix(P[:, 1]))
    x1, x2 = _real_basis(alpha, beta, a_vec, b_vec)
    sol = _collect_trig(sp.Matrix(C1 * x1 + C2 * x2), alpha, beta)

    lam_latex = (rf"\lambda = \pm {beta}i" if alpha == 0
                 else rf"\lambda = {alpha} \pm {beta}i")
    trig = rf"{beta} t" if beta != 1 else "t"
    e_factor = "" if alpha == 0 else rf"e^{{{alpha} t}}"

    steps = [
        Step(
            "Form the characteristic equation",
            rf"\det(A - \lambda I) = \lambda^2 - {sp.latex(A.trace())}\lambda "
            rf"+ ({sp.latex(A.det())}) = 0",
        ),
        Step(
            "Solve it — the roots are a complex conjugate pair",
            rf"\Delta = \operatorname{{tr}}^2 A - 4\det A = "
            rf"{sp.latex(A.trace()**2 - 4*A.det())} < 0,\quad {lam_latex}",
            "A negative discriminant means no real eigenvalue exists, so there "
            "is no real direction that the flow leaves invariant — the "
            "trajectories rotate.",
        ),
        Step(
            "Find the eigenvector for $\\lambda = "
            + (rf"{beta}i$" if alpha == 0 else rf"{alpha} + {beta}i$"),
            rf"\mathbf{{v}} = {_matrix_latex(a_vec)} + i\,{_matrix_latex(b_vec)}"
            rf" = \mathbf{{a}} + i\mathbf{{b}}",
            "Only one of the two conjugate eigenvalues needs to be handled; the "
            "other one contributes the complex conjugate and produces no new "
            "real solution.",
        ),
        Step(
            "Split $e^{\\lambda t}\\mathbf{v}$ into its real and imaginary parts",
            rf"e^{{({alpha} + {beta}i)t}}\mathbf{{v}} = {e_factor}\left[\left("
            rf"\mathbf{{a}}\cos {trig} - \mathbf{{b}}\sin {trig}\right) + i\left("
            rf"\mathbf{{a}}\sin {trig} + \mathbf{{b}}\cos {trig}\right)\right]",
            "Euler's formula $e^{i\\beta t} = \\cos\\beta t + i\\sin\\beta t$ does "
            "the work. Because $A$ is real, the real and the imaginary part of a "
            "complex solution are each a real solution on their own.",
        ),
        Step(
            "Take those two parts as the real basis",
            rf"\mathbf{{x}}_1(t) = {_matrix_latex(sp.expand(x1))},\quad "
            rf"\mathbf{{x}}_2(t) = {_matrix_latex(sp.expand(x2))}",
        ),
        Step(
            "Assemble the general solution",
            rf"\mathbf{{x}}(t) = C_1\mathbf{{x}}_1(t) + C_2\mathbf{{x}}_2(t)",
            "Written this way the answer contains no $i$ at all, which is what "
            "lets a real initial condition be matched by real constants.",
        ),
        Step(
            "Write out the components",
            rf"\mathbf{{x}}(t) = {_matrix_latex(sol)}",
            "Grouping each component by $\\cos$ and $\\sin$ (rather than leaving "
            "four separate terms) is what makes the amplitude and the phase of "
            "each oscillation readable.",
        ),
        _stability_step(A),
    ]

    check = Check(var=t, kind="system", n_constants=2, matrix=A, linear=True)
    statement = ("Find the general solution of the following system of "
                 "first-order linear differential equations. Write the answer "
                 "in real form.")
    statement_latex = rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}}"
    answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sol)}"
    params = {"A": [[int(c) for c in A.row(i)] for i in range(2)],
              "alpha": alpha, "beta": beta,
              "a": [int(c) for c in a_vec], "b": [int(c) for c in b_vec]}

    if difficulty == 3:
        x0 = sp.Matrix([rng.choice(_IC_VALUES) for _ in range(2)])
        consts = sp.solve(list(sol.subs(t, 0) - x0), [C1, C2], dict=True)
        if not consts:
            return None
        if consts[0][C1] == 0 or consts[0][C2] == 0:
            return None
        # ⛔ **這裡刻意不呼叫 `sp.simplify`**，而這是實測抓到的：
        # 它會把 $a\cos\beta t + b\sin\beta t$ 併成
        # $-2\sqrt{2}\,e^{t}\sin(2t + \tfrac{\pi}{4})$——數學上完全正確，
        # 殘差是 0，閘門放行，但它是**第三種**書寫方式（振幅－相位形），
        # 而逐步解答從頭到尾寫的是 $\cos$ 與 $\sin$ 的線性組合。
        # 這與 D11 那個 $\sinh/\cosh$ 的症狀是同一件事，只是換了一個函數族。
        # 常數已經是數字了，`expand` 就夠。
        # `test_the_answer_never_uses_the_amplitude_phase_form` 盯著它。
        sol = _collect_trig(as_exponential(sp.expand(sol.subs(consts[0]))), alpha, beta)
        if any(sp.simplify(c).has(C1, C2) for c in sol):
            return None
        check = Check(var=t, kind="system", n_constants=0, matrix=A,
                      ic_point=sp.Integer(0), ic_value=x0, linear=True)
        statement = ("Solve the following initial value problem for a system of "
                     "first-order linear differential equations. Write the "
                     "answer in real form.")
        statement_latex = (
            rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}},\quad "
            rf"\mathbf{{x}}(0) = {_matrix_latex(x0)}"
        )
        answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sol)}"
        params["x0"] = [int(c) for c in x0]
        steps = steps[:-2] + [
            Step(
                "Apply the initial condition",
                rf"C_1 {_matrix_latex(a_vec)} + C_2 {_matrix_latex(b_vec)} "
                rf"= {_matrix_latex(x0)}",
                "At $t = 0$ we have $\\cos 0 = 1$ and $\\sin 0 = 0$, so "
                "$\\mathbf{x}_1(0) = \\mathbf{a}$ and $\\mathbf{x}_2(0) = "
                "\\mathbf{b}$.",
            ),
            Step(
                "Solve for the constants",
                rf"C_1 = {sp.latex(consts[0][C1])},\quad C_2 = {sp.latex(consts[0][C2])}",
            ),
            Step("Solution of the initial value problem", answer_latex),
            steps[-1],
        ]

    return Problem(
        template_id=COMPLEX_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=sol,
        steps=steps,
        check=check,
        assets=_portrait(A),
    )


# =========================================================================
# (d) 非齊次：待定係數（難度 3 是共振）
# =========================================================================

NONHOMOGENEOUS_NOTES = {
    1: "Constant forcing $\\mathbf{g}$; the particular solution is the equilibrium",
    2: "Exponential forcing $\\mathbf{c}e^{st}$ with $s$ not an eigenvalue",
    3: "Resonance: $s$ is itself an eigenvalue, so the trial form needs a $t$ term",
}

_NH_EIGENVALUES = (-3, -2, -1, 1, 2, 3)
_NH_BOUND = 7
_NH_COEFF = (-2, -1, 1, 2)


def _homogeneous_pair(rng: random.Random):
    """一組實相異、非三角、元素夠小的 $(A, \\lambda_1, \\lambda_2, P)$，或 None。"""
    lam1, lam2 = rng.sample(_NH_EIGENVALUES, 2)
    P = rng.choice(P_CANDIDATES)
    A = sp.Matrix(P * sp.diag(lam1, lam2) * P.inv())
    if A.is_diagonal() or not _pretty_matrix(A, _NH_BOUND):
        return None
    if A[0, 1] == 0 or A[1, 0] == 0:
        return None
    return A, lam1, lam2, P


def _vector_latex_with_exp(vec: sp.Matrix) -> str:
    return _matrix_latex(sp.simplify(vec))


@register(
    NONHOMOGENEOUS_ID,
    name="Linear System 2×2 (Nonhomogeneous)",
    chapter=CHAPTER,
    difficulty_notes=NONHOMOGENEOUS_NOTES,
)
def generate_nonhomogeneous(rng: random.Random, difficulty: int) -> Problem | None:
    made = _homogeneous_pair(rng)
    if made is None:
        return None
    A, lam1, lam2, P = made

    v1, _ = _normalize_pair(sp.Matrix(P[:, 0]), sp.Matrix(P[:, 0]))
    v2, _ = _normalize_pair(sp.Matrix(P[:, 1]), sp.Matrix(P[:, 1]))
    homogeneous = C1 * sp.exp(lam1 * t) * v1 + C2 * sp.exp(lam2 * t) * v2

    # --- 反向構造特解，g 是算出來的 --------------------------------------
    if difficulty == 1:
        s = 0
        a_vec = sp.Matrix([rng.choice(_NH_COEFF) for _ in range(2)])
        xp = a_vec
        trial = r"\mathbf{x}_p = \mathbf{k}"
        trial_note = (
            "A constant forcing calls for a constant trial vector. Note that "
            "$\\mathbf{x}_p$ is exactly the equilibrium of the system: it is "
            "the point where $A\\mathbf{x} + \\mathbf{g} = \\mathbf{0}$."
        )
    elif difficulty == 2:
        choices = [k for k in (-3, -2, -1, 1, 2, 3) if k not in (lam1, lam2)]
        s = rng.choice(choices)
        a_vec = sp.Matrix([rng.choice(_NH_COEFF) for _ in range(2)])
        xp = sp.exp(s * t) * a_vec
        trial = rf"\mathbf{{x}}_p = \mathbf{{k}}e^{{{s} t}}"
        trial_note = (
            f"Because $s = {s}$ is not an eigenvalue of $A$, the matrix "
            f"$A - sI$ is invertible and a plain exponential trial vector "
            f"works. Substituting gives $(sI - A)\\mathbf{{k}} = \\mathbf{{c}}$."
        )
    else:
        s = lam1
        k = rng.choice((1, 2))
        b_vec = sp.Matrix([rng.choice((-2, -1, 0, 1, 2)) for _ in range(2)])
        # b 與 v1 平行的話，e^{λt}b 整個併進齊次解，特解只剩 t 那一項
        if sp.Matrix.hstack(v1, b_vec).det() == 0:
            return None
        xp = sp.exp(s * t) * (k * v1 * t + b_vec)
        trial = rf"\mathbf{{x}}_p = \left(\mathbf{{k}}t + \mathbf{{m}}\right)e^{{{s} t}}"
        trial_note = (
            f"Here $s = {s}$ is itself an eigenvalue, so $A - sI$ is singular and "
            f"$\\mathbf{{k}}e^{{st}}$ alone cannot work — substituting it would "
            f"force $(sI - A)\\mathbf{{k}} = \\mathbf{{c}}$, which has no "
            f"solution for a general $\\mathbf{{c}}$. Multiplying by $t$ and "
            f"keeping a constant vector as well repairs it."
        )

    g = sp.Matrix(sp.simplify(sp.expand(sp.Matrix(xp).diff(t) - A * sp.Matrix(xp))))
    if all(component == 0 for component in g):        # 特解剛好是齊次解
        return None
    if any(abs(c) > 24 for c in sp.Matrix(g).subs(t, 0)):
        return None                                   # g 的係數太大就不像考題

    sol = sp.Matrix(homogeneous + sp.Matrix(xp))

    steps = [
        Step(
            "Solve the homogeneous system first",
            rf"\det(A - \lambda I) = \lambda^2 - {sp.latex(A.trace())}\lambda "
            rf"+ ({sp.latex(A.det())}) = 0 \;\Rightarrow\; "
            rf"\lambda_1 = {lam1},\ \lambda_2 = {lam2}",
            "The general solution of a nonhomogeneous linear system is "
            "$\\mathbf{x}_h + \\mathbf{x}_p$, so the homogeneous part has to be "
            "in hand before the forcing is touched.",
        ),
        Step(
            "Find the eigenvectors",
            rf"\mathbf{{v}}_1 = {_matrix_latex(v1)},\quad "
            rf"\mathbf{{v}}_2 = {_matrix_latex(v2)}",
        ),
        Step(
            "Write down the homogeneous solution",
            rf"\mathbf{{x}}_h(t) = C_1 e^{{{lam1} t}}{_matrix_latex(v1)} "
            rf"+ C_2 e^{{{lam2} t}}{_matrix_latex(v2)}",
        ),
        Step("Choose the trial form for a particular solution", trial, trial_note),
        Step(
            "Substitute and match coefficients",
            rf"\mathbf{{x}}_p'(t) - A\mathbf{{x}}_p(t) = {_vector_latex_with_exp(g)}",
            "Every term on both sides carries the same exponential, so it "
            "cancels and what is left is a linear system for the unknown "
            "constant vectors.",
        ),
        Step(
            "The particular solution",
            rf"\mathbf{{x}}_p(t) = {_matrix_latex(sp.expand(sp.Matrix(xp)))}",
        ),
        Step(
            "Add the two parts",
            rf"\mathbf{{x}}(t) = \mathbf{{x}}_h(t) + \mathbf{{x}}_p(t) "
            rf"= {_matrix_latex(sp.expand(sol))}",
            "A different $\\mathbf{x}_p$ that differs from this one by a "
            "homogeneous solution is equally correct — it only renames "
            "$C_1$ and $C_2$.",
        ),
    ]

    check = Check(var=t, kind="system", n_constants=2, matrix=A,
                  forcing=sp.Matrix(g), linear=True)
    statement = ("Find the general solution of the following nonhomogeneous "
                 "system of first-order linear differential equations.")
    statement_latex = (
        rf"\mathbf{{x}}' = {_matrix_latex(A)}\mathbf{{x}} + {_vector_latex_with_exp(g)}"
    )
    answer_latex = rf"\mathbf{{x}}(t) = {_matrix_latex(sp.expand(sol))}"
    params = {"A": [[int(c) for c in A.row(i)] for i in range(2)],
              "eigenvalues": [lam1, lam2], "s": int(s),
              "resonant": bool(difficulty == 3)}

    return Problem(
        template_id=NONHOMOGENEOUS_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=statement_latex,
        answer_latex=answer_latex,
        answer_expr=sol,
        steps=steps,
        check=check,
        # ⛔ 刻意沒有相圖，理由見 `_portrait()` 的 docstring。
    )
