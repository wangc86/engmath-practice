r"""判斷平衡點的類型（PLAN.md §6 的工作項 **2B8**，課綱 W10 與 W12–W13）。

學生看到一個 $2\times2$ 常係數矩陣 $A$，要判斷 $\mathbf{x}' = A\mathbf{x}$ 在
原點的平衡點是哪一種：鞍點、穩定／不穩定節點、中心、螺旋…

這是本專案第二個 `answer_kind = "classification"` 的題型（第一個是
`fourier/symmetry.py` 的奇偶性判斷），也是 §2.11.4 第三層所說的
`ClassificationCheck` 的落點。

---

## 反向構造：先挑類型，再造 $A$

正向的作法（隨機抽一個小整數矩陣，看它落在哪一格）有一個很實際的問題：
**格子的機率極度不均**。$\Delta = 0$（重根）與 $\det A = 0$（非孤立）
是判別式平面上的**測度零集合**——隨機抽整數矩陣抽得到，但要抽很久，
而且抽到的分佈由「小整數」這個限制決定，不由教學需要決定。

所以這裡照 §2.1 原則一反過來做：**先決定要哪一種平衡點，再挑一組特徵值
與一個 $\det P = \pm 1$ 的相似變換把它造出來。** 這讓每一格都出得出來，
而且出得出**指定難度的那一格**。

⚠️ **$\det P = \pm 1$ 讓 $P^{-1}$ 是整數矩陣**，所以 $A = PDP^{-1}$ 一定
是整數矩陣——這一點與 §2.5 的線性系統題型共用同一個理由，也共用
`real_distinct.P_CANDIDATES` 那份候選清單。

---

## 三個難度：軸是**要用到判別式平面的哪一部分**

| 難度 | 涵蓋的類型 | 學生要做的事 |
|---|---|---|
| 1 | 鞍點、穩定節點、不穩定節點 | $\det A$ 的正負就分得出鞍點；其餘看 $\operatorname{tr}A$。**兩個特徵值都是實數且相異**（$\Delta > 0$） |
| 2 | 穩定／不穩定螺旋、中心 | $\Delta < 0$。要先算判別式判斷實／複，中心那一格還要注意 $\operatorname{tr}A = 0$ |
| 3 | 退化節點、星形節點、非孤立平衡點 | **邊界情形**：$\Delta = 0$ 與 $\det A = 0$ |

⛔ **難度不是累積的：每一格只出它自己那一組。**

第一版寫成累積（難度 3 = 前三組全部），而看樣本的時候發現一件事：
**難度 3 抽到「真的是邊界情形」的機率只有 5/11**，也就是說一個選了難度 3
的學生有一半以上的機會拿到一道普通的節點題。而難度說明上寫著
「Boundary cases」——**那句話會變成一句假話，而每一題都完全正確**。

⚠️ 這與 `ode/undetermined.py` 的難度軸（共振重數 $m$）是同一個判準：
**難度是一個結構性的承諾，不是一個「比較難」的模糊感覺**。
累積式的分佈在別的題型上可能是對的，在這裡不是。

⚠️ **難度 3 的三種是「邊界」而不是「比較難算」。** $\Delta = 0$ 的計算量
其實比難度 2 的複數情形小。它們排在最後，是因為**課本通常把它們放在
判別式平面那張圖的最後才提**，而且學生最常犯的錯是把它們歸到鄰近的格子
（退化節點看成節點、星形看成退化、非孤立看成中心）。

⛔ **星形節點（$A = \lambda I$）與退化節點必須分開，不可以合成一格。**
兩者都是 $\Delta = 0$，但幾何完全不同：星形有無限多個特徵方向（每個向量
都是特徵向量），退化只有一個。`plot.classify()` 用 $b = c = 0$ 分辨它們，
而**如果這個題型把兩者當成同一個答案，那個分辨就沒有人在用了**。

---

## 驗證閘門：三層，而且第一層擋的東西與另外兩層不同

⚠️ **這個題型的風險與其他題型不同，要說清楚。**

其他題型的風險是「答案算錯了」。這裡的答案是一個從有限清單裡挑出來的
字串，`plot.classify()` 又已經有 `tests/test_plot.py` 的雙路徑一致性測試
（查表 vs `A.eigenvals()`，外加 19 個手算矩陣）在守——所以
「分類函式算錯」這件事**已經被別的地方守住了**。

**這裡真正的風險是反向構造造錯**：我要一個鞍點，而 `_build()` 因為某個
邊界條件回給我一個退化節點。那種錯**分類函式不會有意見**（它會忠實地回報
「這是退化節點」），而題目與答案仍然自洽——**只是難度 1 裡混進了一個
難度 3 的東西，而沒有任何人會發現**。

| 層 | 問的問題 | 它擋得到什麼 |
|---|---|---|
| 1 | 宣稱的類型 == `plot.classify(A)` 嗎？ | **反向構造造錯**（上面那一段）。這是這個題型的主閘門 |
| 2 | 用 `A.eigenvals()` 獨立重算一次，一致嗎？ | 查表那條路本身寫錯。⚠️ 與 `tests/test_plot.py` 同一個判準，但**它在執行期對每一道真的出出來的題目跑**，而測試只跑它自己挑的矩陣 |
| 3 | 這個類型真的屬於這個難度嗎？ | **難度軸失效**——症狀是「學生在難度 1 練到了退化節點」，而每一題都完全正確 |

⛔ **第 3 層不是型別檢查。** 它是這個題型唯一一個守著「難度是有意義的」
的東西，而那件事**沒有任何別的機制在守**：一道分類正確、敘述正確、
步驟正確的題目，可以完全不屬於它被放進去的那個難度。
（與 `ode/undetermined.py` 那條「難度 3 真的是重根共振」是同一型的看守。）
"""

from __future__ import annotations

import random

import sympy as sp

from .. import plot
from ..base import Problem, Step, register
from .real_distinct import P_CANDIDATES, _matrix_latex

TEMPLATE_ID = "system.linear_2x2.classification"

CHAPTER = "Systems of First-Order Linear ODEs"

DIFFICULTY_NOTES = {
    1: "Real distinct eigenvalues: saddle point or node",
    2: "Complex eigenvalues: spirals and centres",
    3: "Boundary cases: repeated eigenvalues and a zero eigenvalue",
}

STATEMENT = (
    "Classify the equilibrium point at the origin of the linear system below, "
    "and say whether it is stable."
)

#: 每個難度的類型。⛔ **不累積**——理由見檔頭那一段。
#:
#: ⚠️ **這裡列的是 `plot.py` 的字串常數，不是自己寫的字面值。**
#: 抄一份字面值過來就是第二真相，而漂移的症狀是閘門第一層永遠不通過
#: （那還好，看得見）或者更糟——某個 typo 讓某一格永遠抽不到，
#: 而那一格只是安靜地不出現。
TYPES: dict[int, tuple[str, ...]] = {
    1: (plot.SADDLE, plot.STABLE_NODE, plot.UNSTABLE_NODE),
    2: (plot.STABLE_SPIRAL, plot.UNSTABLE_SPIRAL, plot.CENTER),
    3: (plot.STABLE_DEGENERATE_NODE, plot.UNSTABLE_DEGENERATE_NODE,
        plot.STABLE_STAR_NODE, plot.UNSTABLE_STAR_NODE, plot.NON_ISOLATED),
}


def types_for(difficulty: int) -> tuple[str, ...]:
    """難度 d 出得到的類型。**恰好是那一組，不含別的難度的。**"""
    return TYPES[difficulty]


#: 實特徵值的候選。⚠️ 不含 0——`det = 0` 那一格由 `NON_ISOLATED` 單獨處理，
#: 而讓 0 混進一般的抽樣會讓「相異實根」那一格偶爾變成非孤立平衡點。
REAL_EIGENVALUES = (-4, -3, -2, -1, 1, 2, 3, 4)

#: 複數特徵值 $\alpha \pm \beta i$ 的候選。
ALPHAS = (-2, -1, 1, 2)
BETAS = (1, 2, 3)

#: $A$ 的元素上界。太大的矩陣會讓學生把時間花在算術上，而這一題考的是判讀。
ENTRY_BOUND = 9


def _bounded(A: sp.Matrix) -> bool:
    return max(abs(v) for v in A) <= ENTRY_BOUND


def _similar(rng: random.Random, D: sp.Matrix) -> sp.Matrix | None:
    r"""$A = PDP^{-1}$，$P$ 從 $\det P = \pm 1$ 的清單裡抽。

    ⚠️ **對角的 $A$ 回 `None`**：$A = \operatorname{diag}(2,-3)$ 的分類
    用看的就知道，而這一題要學生算 $\operatorname{tr}$ 與 $\det$。
    ⛔ **但星形節點是例外**——它本來就是 $\lambda I$，那是它的定義，
    所以那一族不走這個函式（見 `_build_star`）。
    """
    P = rng.choice(P_CANDIDATES)
    A = sp.Matrix(P * D * P.inv())
    if A.is_diagonal() or not _bounded(A):
        return None
    return A


def _build_real(rng: random.Random, want: str) -> sp.Matrix | None:
    """相異實特徵值：鞍點、穩定節點、不穩定節點。"""
    if want == plot.SADDLE:
        lam1 = rng.choice([v for v in REAL_EIGENVALUES if v > 0])
        lam2 = rng.choice([v for v in REAL_EIGENVALUES if v < 0])
    else:
        pool = [v for v in REAL_EIGENVALUES
                if (v < 0 if want == plot.STABLE_NODE else v > 0)]
        lam1, lam2 = rng.sample(pool, 2)
    return _similar(rng, sp.diag(lam1, lam2))


def _build_complex(rng: random.Random, want: str) -> sp.Matrix | None:
    r"""複數特徵值 $\alpha \pm \beta i$。

    造法不經過複數：實 Jordan 形 $\begin{pmatrix}\alpha & -\beta\\
    \beta & \alpha\end{pmatrix}$ 的特徵值恰好是 $\alpha \pm \beta i$，
    而它是實矩陣，所以 $PDP^{-1}$ 全程都在整數裡。
    """
    alpha = 0 if want == plot.CENTER else rng.choice(
        [v for v in ALPHAS if (v < 0 if want == plot.STABLE_SPIRAL else v > 0)]
    )
    beta = rng.choice(BETAS)
    block = sp.Matrix([[alpha, -beta], [beta, alpha]])
    P = rng.choice(P_CANDIDATES)
    A = sp.Matrix(P * block * P.inv())
    # ⚠️ 這裡**不**排除對角矩陣：複數特徵值的實矩陣不可能是對角的
    # （對角矩陣的特徵值就是對角元素，是實的），所以那個檢查在這一支是
    # 恆真的死碼。寫下來以免有人「為了一致」把它加回去。
    return A if _bounded(A) else None


def _build_degenerate(rng: random.Random, want: str) -> sp.Matrix | None:
    r"""重根且**缺陷**（只有一個特徵方向）：Jordan 塊 $\begin{pmatrix}
    \lambda & 1\\ 0 & \lambda\end{pmatrix}$。"""
    lam = rng.choice(
        [v for v in REAL_EIGENVALUES
         if (v < 0 if want == plot.STABLE_DEGENERATE_NODE else v > 0)]
    )
    return _similar(rng, sp.Matrix([[lam, 1], [0, lam]]))


def _build_star(rng: random.Random, want: str) -> sp.Matrix:
    r"""星形節點：$A = \lambda I$。

    ⚠️ **它不經過 `_similar()`，而那不是抄漏了。** $P(\lambda I)P^{-1}
    = \lambda I$ 對任何 $P$ 都成立——相似變換對它完全沒有作用，
    而 `_similar()` 會因為「A 是對角的」把它整個擋掉。
    """
    lam = rng.choice(
        [v for v in REAL_EIGENVALUES
         if (v < 0 if want == plot.STABLE_STAR_NODE else v > 0)]
    )
    return sp.Matrix([[lam, 0], [0, lam]])


def _build_non_isolated(rng: random.Random) -> sp.Matrix | None:
    r"""$\det A = 0$：一個特徵值是 0，整條特徵直線都是平衡點。

    ⚠️ **另一個特徵值不可以也是 0**：$A$ 會變成零矩陣或一個冪零矩陣，
    而那時「平衡點」這個詞連討論的對象都沒有了。
    """
    lam = rng.choice([v for v in REAL_EIGENVALUES])
    return _similar(rng, sp.diag(lam, 0))


def _build(rng: random.Random, want: str) -> sp.Matrix | None:
    if want in (plot.SADDLE, plot.STABLE_NODE, plot.UNSTABLE_NODE):
        return _build_real(rng, want)
    if want in (plot.STABLE_SPIRAL, plot.UNSTABLE_SPIRAL, plot.CENTER):
        return _build_complex(rng, want)
    if want in (plot.STABLE_DEGENERATE_NODE, plot.UNSTABLE_DEGENERATE_NODE):
        return _build_degenerate(rng, want)
    if want in (plot.STABLE_STAR_NODE, plot.UNSTABLE_STAR_NODE):
        return _build_star(rng, want)
    if want == plot.NON_ISOLATED:
        return _build_non_isolated(rng)
    raise ValueError(f"沒有這一種平衡點：{want}")   # 規則 4：不靜默


# --- 閘門 -------------------------------------------------------------------


def classify_by_eigenvalues(A: sp.Matrix) -> str:
    r"""**獨立路徑**：從 `A.eigenvals()` 的實部符號與虛部重新分類一次。

    ⚠️ 這一支刻意**不看** $\operatorname{tr}$、$\det$、$\Delta$——那是
    `plot.classify()` 走的路。兩條路都對的時候結果當然一樣；有意義的是
    它們錯的時候不會一起錯。

    ⛔ **判斷順序與 `plot.classify()` 相反是刻意的**：那一支先看 $\det$，
    這一支先看重根。一模一樣的順序會讓「順序寫錯」這種 bug 在兩邊同時發生。
    """
    eigen = A.eigenvals()                       # {特徵值: 重數}
    values = list(eigen.keys())

    if len(values) == 1 and eigen[values[0]] == 2:      # 重根
        lam = values[0]
        if lam == 0:
            return plot.NON_ISOLATED
        # 幾何重數：2 → 星形（每個向量都是特徵向量），1 → 退化
        geometric = len((A - lam * sp.eye(2)).nullspace())
        if geometric == 2:
            return plot.STABLE_STAR_NODE if lam < 0 else plot.UNSTABLE_STAR_NODE
        return (plot.STABLE_DEGENERATE_NODE if lam < 0
                else plot.UNSTABLE_DEGENERATE_NODE)

    if any(v == 0 for v in values):
        return plot.NON_ISOLATED

    if all(sp.im(v) == 0 for v in values):             # 兩個相異實根
        signs = {sp.sign(sp.re(v)) for v in values}
        if signs == {1, -1}:
            return plot.SADDLE
        return plot.STABLE_NODE if signs == {-1} else plot.UNSTABLE_NODE

    alpha = sp.re(values[0])                            # 共軛對，實部相同
    if alpha == 0:
        return plot.CENTER
    return plot.STABLE_SPIRAL if alpha < 0 else plot.UNSTABLE_SPIRAL


class ClassificationCheck:
    """三層閘門（`Verifier` 協定的實作）。逐層的理由見檔頭那張表。

    ⚠️ **它不是 frozen dataclass，因為它要存一個 `sp.Matrix`**，
    而 Matrix 不可雜湊。純資料的性質（可 pickle、不含 lambda）仍然維持
    ——§2.2 第 2 點要的是後者，不是 `frozen=True` 本身。
    """

    def __init__(self, A: sp.Matrix, claimed: str, difficulty: int):
        self.A = A
        self.claimed = claimed
        self.difficulty = difficulty

    def __repr__(self) -> str:                  # pragma: no cover - 診斷用
        return f"ClassificationCheck({self.claimed!r}, d{self.difficulty})"

    def verify(self, problem) -> tuple[bool, str]:
        table = plot.classify(self.A)
        if table != self.claimed:
            return False, (
                f"閘門一：反向構造造出來的不是要的那一種"
                f"（要 {self.claimed}，造出 {table}）"
            )

        independent = classify_by_eigenvalues(self.A)
        if independent != self.claimed:
            return False, (
                f"閘門二：兩條分類路徑不一致"
                f"（查表 {table}，特徵值 {independent}）"
            )

        allowed = types_for(self.difficulty)
        if self.claimed not in allowed:
            return False, (
                f"閘門三：{self.claimed} 不屬於難度 {self.difficulty}"
                f"（這個難度恰好只有 {allowed}）"
            )
        return True, ""


# --- 題目 -------------------------------------------------------------------


#: 最後一步（也就是答案）的句子。**答案與那一步共用這一個函式，不是各寫一遍。**
#:
#: ⚠️ `test_steps_are_complete` 對 `classification` 走的是**逐字比對**
#: （分類題沒有「等號右邊」可以比），所以兩邊只要差一個句點就會紅。
#: 那項測試守的正是「答案與最後一步不可以各寫一遍然後漂移」——
#: 讓它們共用同一個函式，是把那件事變成結構上做不到，而不是靠紀律。
def final_latex(A: sp.Matrix) -> str:
    return r"\text{The origin is %s.}" % plot.describe(A)


def _steps(A: sp.Matrix, label: str) -> list[Step]:
    """四步。切法照 §7 #22：一步 = 課本上會單獨寫一行的一個動作。"""
    tr, det, disc = plot.invariants(A)
    eigen = ", ".join(sorted(sp.latex(v) for v in A.eigenvals()))
    return [
        Step(
            "Compute the trace and the determinant",
            r"\operatorname{tr}A = %s, \qquad \det A = %s" % (tr, det),
            "Everything about the equilibrium of a $2\\times2$ linear system "
            "follows from these two numbers together with the discriminant "
            "below — you never need the eigenvectors to classify it.",
        ),
        Step(
            "Compute the discriminant",
            r"\Delta = (\operatorname{tr}A)^{2} - 4\det A = %s^{2} - 4(%s) = %s"
            % (tr, det, disc),
            "The sign of $\\Delta$ decides whether the eigenvalues are real "
            "($\\Delta > 0$), repeated ($\\Delta = 0$) or a complex conjugate "
            "pair ($\\Delta < 0$). That is the first branch of the "
            "classification, not the last.",
        ),
        Step(
            "Read off the eigenvalues",
            r"\lambda = %s" % eigen,
            "Shown here as a check on the previous two steps. "
            + _eigen_note(det, disc),
        ),
        Step(
            "Classify the equilibrium",
            final_latex(A),
            _final_note(A, label),
        ),
    ]


def _eigen_note(det: int, disc: int) -> str:
    if det == 0:
        return ("One eigenvalue is zero, so the origin is not an isolated "
                "equilibrium: every point on the corresponding eigenline is "
                "an equilibrium too.")
    if disc < 0:
        return ("The real part decides stability and the imaginary part is "
                "what makes the trajectories rotate.")
    if disc == 0:
        return ("A repeated eigenvalue. Whether the node is degenerate or a "
                "star depends on how many independent eigenvectors it has — "
                "see the last step.")
    return "Two distinct real eigenvalues, so the trajectories do not rotate."


def _final_note(A: sp.Matrix, label: str) -> str:
    """最後一步的說明——**回答「為什麼」，不重述「做了什麼」**（§6 第 3 點）。"""
    _tr, det, disc = plot.invariants(A)
    if det < 0:
        return ("A negative determinant means the eigenvalues have opposite "
                "signs, and that alone forces a saddle point. You do not need "
                "the trace or the discriminant for this case.")
    if det == 0:
        return ("With a zero eigenvalue there is a whole line of equilibria, "
                "so asking whether *the* origin is stable is not quite the "
                "right question: nearby points on that line stay where they "
                "are rather than returning to the origin.")
    if disc == 0:
        star = A[0, 1] == 0 and A[1, 0] == 0
        if star:
            return ("Both off-diagonal entries are zero and the two "
                    "eigenvalues are equal, so $A = \\lambda I$: *every* "
                    "non-zero vector is an eigenvector. That is a star node, "
                    "not a degenerate one — the trajectories are straight "
                    "lines in every direction.")
        return ("There is only one independent eigenvector, so this is a "
                "degenerate node: the trajectories all become tangent to that "
                "single direction. Compare it with a star node, where every "
                "direction is an eigendirection.")
    if disc < 0:
        return ("The trace is twice the real part of the eigenvalues, so its "
                "sign is exactly what decides whether the spiral winds in or "
                "out. A zero trace gives closed orbits — a centre — and that "
                "is the one case where the linear classification is fragile: "
                "a small change to $A$ turns it into a spiral either way.")
    return ("Both eigenvalues have the same sign, so the trajectories leave "
            "or approach the origin without rotating. The trace tells you "
            "which, because it is the sum of the two eigenvalues.")


@register(
    TEMPLATE_ID,
    name="Linear System 2×2: Classify the Equilibrium",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    want = rng.choice(types_for(difficulty))
    A = _build(rng, want)
    if A is None:
        return None

    label = plot.classify(A)

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        # ⚠️ **鍵用 `A`，與其餘四個 `system.*` 題型一致**（它們存的也是
        # 一個 `sp.Matrix`）。`tests/test_plot.py` 的兩項跨題型測試直接讀
        # `params["A"]`——換一個鍵名會讓它們對這個題型**安靜地跳過**。
        params={"A": A, "wanted": want},
        statement=STATEMENT,
        statement_latex=r"\mathbf{x}' = %s\,\mathbf{x}" % _matrix_latex(A),
        answer_latex=final_latex(A),
        # ⛔ `classification` 的 `answer_expr` 是 `None`（見 `base.AnswerKind`）。
        # 任何碰 `answer_expr` 的程式都要有一個**明示的分支**跳過它。
        answer_expr=None,
        answer_kind="classification",
        steps=_steps(A, plot.describe(A)),
        # ⚠️ 相圖放在 `assets` 裡，而 `assets` 只渲染在第二層 `<details>` 內
        # （D13、§2.11.1）。**這一題的相圖就是答案本身**，所以它比其他題型
        # 更需要那道防護：一張鞍點圖出現在題目敘述旁邊，這一題就白出了。
        # `tests/test_web.py::test_no_template_leaks_an_svg_into_the_statement`
        # 對**每一個**題型都跑，所以這件事不靠這裡的紀律。
        assets={"phase_portrait_svg": plot.phase_portrait_svg(A)},
        check=ClassificationCheck(A=A, claimed=want, difficulty=difficulty),
    )
