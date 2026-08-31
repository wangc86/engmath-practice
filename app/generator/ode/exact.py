r"""恰當方程與積分因子（PLAN.md §2.4(c)、階段 2A 的 2b；課綱 W10）。

本檔註冊**一個**題型 ``ode.first_order.exact``：

| 難度 | 內容 |
|---|---|
| 1 | 恰當方程，位勢函數兩項 |
| 2 | 恰當方程，位勢函數三項（含一個超越函數項） |
| 3 | **不**恰當，要先找出只含 $x$ 或只含 $y$ 的積分因子 $\mu$ |

---

## 反向構造：先寫位勢函數，恰當性自動成立

$M\,dx + N\,dy = 0$ 恰當的定義就是「存在 $F$ 使 $F_x = M$、$F_y = N$」，
所以**先寫 $F$、再令 $M = F_x$、$N = F_y$**，$M_y = N_x = F_{xy}$ 這件事
由 Clairaut 定理白送。PLAN §2.4(c) 說這是全部題型裡反向構造最漂亮的一個，
落地之後可以確認：難度 1、2 完全不需要拒絕抽樣。

## 難度 3 的積分因子：也是反向構造，但要繞一個彎

規劃的原話是「生成非恰當的式子，再乘上積分因子」。直接除會讓 $M, N$
變成有理式或帶指數，所以本檔的做法是**把除法吸收進參數化**：

    μ = e^{ax}   取 H(x,y) 為多項式，  M = aH + H_x,    N = H_y,        F = e^{ax} H
    μ = x^k      取 P(x,y) 為多項式，  M = (k+1)P + xP_x, N = xP_y,      F = x^{k+1} P
    μ = e^{by}   取 H(x,y) 為多項式，  M = H_x,         N = bH + H_y,    F = e^{by} H
    μ = y^k      取 Q(x,y) 為多項式，  M = yQ_x,        N = (k+1)Q + yQ_y, F = y^{k+1} Q

四組都是 $F = \mu H$ 展開後除以 $\mu$ 的結果，**而 $M, N$ 全是整係數多項式**
——學生看到的題目乾乾淨淨，指數或冪次只出現在他自己求出來的 $\mu$ 裡。

四組各自的判別比也是乾淨的常數或 $k/x$、$k/y$：

    e^{ax}: (M_y - N_x)/N = a        x^k: (M_y - N_x)/N = k/x
    e^{by}: (N_x - M_y)/M = b        y^k: (N_x - M_y)/M = k/y

⚠️ **兩個方向都要出得到，而那不是為了湊變化。** 課本教的流程是「先試
只含 $x$ 的，不行再試只含 $y$ 的」；如果系統出的題目永遠是 $\mu(x)$，
學生會學成「積分因子就是對 $x$ 積」，而那在期中考遇到 $\mu(y)$ 時會安靜地
給出錯誤答案（比值裡還留著另一個變數，他照樣積得下去）。

⚠️ **題目敘述刻意不說是哪一種。** 說了就等於把第一步做完了。

---

## 隱式解怎麼過驗證閘門（本檔的主要設計問題）

答案是一個**關係式** $F(x,y) = C_1$，不是一個 $y(x)$。既有的 `Check`
做的是「把 $y(x)$ 代回方程算殘差」，在這裡完全用不上——沒有 $y(x)$ 可以代。

所以本檔提供 `ExactCheck`，`Verifier` 協定的第四個實作
（前三個：`Check`、`fourier.core.FourierCheck`、`fourier.symmetry.ParityCheck`）。
它有**四層**，而四層擋的是四件不同的事：

1. **隱式解的定義**：沿 $F(x,y) = C$ 隱微分得 $y' = -F_x/F_y$，代進
   $M + Ny' = 0$，通分後的分子是 $M F_y - N F_x$，它必須**恰為 0**。
   這是「$F=C$ 是 $M\,dx + N\,dy = 0$ 的隱式解」的充分必要條件。
2. **非退化**：$F_y \not\equiv 0$、$M \not\equiv 0$、$N \not\equiv 0$。
   ⛔ **這一層不是裝飾**：$F$ 若退化成常數，$F_x = F_y = 0$，
   第 1 層的分子恆為 0——**閘門會對一個什麼都沒說的「答案」說通過**。
   第 1 層自己看不出這件事，因為它問的是比例關係，而 $(0,0)$ 與任何
   $(M,N)$ 都成比例。
3. **恰當性**：$(\mu M)_y = (\mu N)_x$。難度 1、2 的 $\mu = 1$，
   這一層驗的就是題目敘述那句 "the equation is exact"。
4. **難度 3 專屬**：$M_y \ne N_x$，也就是題目說的「它**不**恰當」必須是真的。
   ⚠️ 少了這一層，一個把 $a$ 抽成 0 的 bug 會生出一個已經恰當的方程，
   然後理直氣壯地要學生去找一個等於 1 的積分因子——**答案完全正確，
   步驟完全正確，只有題目是假的**，而那是不會有任何東西變紅的失敗。

**第 1 層與生成路徑有多獨立？** 生成路徑是「微分 $F$ 得到 $M, N$」，
閘門路徑是「用 $M, N, F$ 算 $MF_y - NF_x$」——它會再微分 $F$ 一次，
所以它不是一條完全獨立的路。**這件事寫在這裡，不假裝它是。**
真正獨立的那一條是數值的：沿著 $y' = -M/N$ 用 RK4 走一段，
確認 $F$ 在路徑上不變——它只把 $M, N, F$ 當成三個可以代數值的函數，
一次都沒有做符號微分。那條路太慢，不適合每題都跑，所以它降級成
`tests/test_generators.py::test_the_implicit_answer_is_constant_along_the_flow`。
（同樣的分工方式見 `ode/laplace.py` 的「表 vs 定義的積分」。）

---

## 附錄 C 的兩個落點

* **常數寫 $C_1$，不寫 $C$。** C.1 明文禁止「最終答案出現裸露的 $C$」。
  隱式解的教科書寫法通常是 $F(x,y)=C$，本專案一律寫 $F(x,y) = C_1$。
* **$y$ 在這裡是一個變數不是一個函數。** C.1 要求純量 ODE 全程寫 $y(x)$，
  那條規則的對象是「未知函數」；恰當方程的答案裡 $x$ 與 $y$ 是對稱的兩個
  變數（微分形式 $M\,dx + N\,dy$ 本來就沒有偏袒誰），寫成 $F(x, y) = C_1$
  才是課本的寫法。**這是 C.1 那一格的一個例外，寫在這裡以免下一個人以為是漏的。**
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import sympy as sp

from ..base import Problem, Step, register
from ..pretty import has_special_function, has_ugly_fraction, ugliness

x = sp.Symbol("x", positive=True)
y = sp.Symbol("y", positive=True)
C1 = sp.Symbol("C_1")

TEMPLATE_ID = "ode.first_order.exact"
CHAPTER = "First-Order ODEs"

COEFFS = (-3, -2, -1, 1, 2, 3)

#: 位勢函數的交叉項（同時含 $x$ 與 $y$）。**至少要有一個**，否則
#: $N$ 不含 $x$、$M$ 不含 $y$，方程退化成兩個各自獨立的積分——
#: 仍然是恰當的，但學生學不到「$h(y)$ 是從哪裡冒出來的」。
CROSS_TERMS = (x * y, x * y**2, x**2 * y, x**2 * y**2, x**3 * y, x * y**3)

PURE_X_TERMS = (x, x**2, x**3)
PURE_Y_TERMS = (y, y**2, y**3)

#: 難度 2 才會出現的超越項。刻意只有三種、而且都只含一個變數——
#: 它們的作用是讓 $\int M\,dx$ 那一步不再只是「多項式次數加一」。
TRANSCENDENTAL_X = (sp.sin(x), sp.cos(x), sp.exp(x))
TRANSCENDENTAL_Y = (sp.sin(y), sp.cos(y), sp.exp(y))

UGLINESS_LIMIT = {1: 25, 2: 35, 3: 45}

DIFFICULTY_NOTES = {
    1: "Exact as it stands",
    2: "Exact, with a transcendental term",
    3: "Not exact — an integrating factor is needed",
}


# --- 排版 -------------------------------------------------------------------


def _equation_latex(M: sp.Expr, N: sp.Expr) -> str:
    r"""印成 $\left(M\right)dx + \left(N\right)dy = 0$。

    兩邊一律加括號，這樣 $N$ 是負的時候也不會印出 `+ -x^{2}`。
    """
    return (rf"\left({sp.latex(M)}\right)\,dx "
            rf"+ \left({sp.latex(N)}\right)\,dy = 0")


# --- 驗證閘門 ---------------------------------------------------------------


@dataclass(frozen=True)
class ExactCheck:
    """隱式解 $F(x,y) = C_1$ 的驗證閘門（`Verifier` 協定的第四個實作）。

    四層與它們各自擋什麼，見本檔檔頭。**刻意是純資料**（不含 lambda、
    可 pickle），與 `Check` 的理由相同（§2.2 的第二個註記）。
    """

    var_x: sp.Symbol
    var_y: sp.Symbol
    M: sp.Expr
    N: sp.Expr
    potential: sp.Expr
    #: 積分因子。難度 1、2 是 `S.One`，難度 3 是 $e^{ax}$、$x^k$、$e^{by}$、$y^k$。
    mu: sp.Expr = sp.S.One
    #: 題目是否宣稱「原式不恰當」。只有難度 3 是 True，第 4 層才會跑。
    claims_not_exact: bool = False

    def verify(self, problem: "Problem") -> tuple[bool, str]:
        X, Y = self.var_x, self.var_y
        F = problem.answer_expr
        if F is None:
            return False, "隱式解沒有位勢函數"
        Fx, Fy = sp.diff(F, X), sp.diff(F, Y)

        # 第 2 層先跑：它是第 1 層有沒有意義的前提。
        if sp.simplify(Fy) == 0:
            return False, "位勢函數不含 y，F(x,y)=C 定義不出 y"
        if sp.simplify(self.M) == 0 or sp.simplify(self.N) == 0:
            return False, "M 或 N 恆為 0，這不是一個一階方程"

        # 第 1 層：隱式解的定義。
        residual = sp.simplify(sp.expand(self.M * Fy - self.N * Fx))
        if residual != 0:
            return False, f"F(x,y)=C 不是這個方程的隱式解：M·F_y - N·F_x = {residual}"

        # 第 3 層：乘上積分因子之後必須恰當。
        exactness = sp.simplify(sp.diff(self.mu * self.M, Y)
                                - sp.diff(self.mu * self.N, X))
        if exactness != 0:
            return False, f"乘上 μ 之後仍然不恰當：(μM)_y - (μN)_x = {exactness}"

        # 第 4 層：難度 3 的題目說原式不恰當，那必須是真的。
        if self.claims_not_exact:
            original = sp.simplify(sp.diff(self.M, Y) - sp.diff(self.N, X))
            if original == 0:
                return False, "題目說原式不恰當，但它本來就是恰當的"
        return True, ""


# --- 難度 1、2：先寫位勢函數 ------------------------------------------------


def _draw_potential(rng: random.Random, difficulty: int) -> sp.Expr:
    cross = rng.choice(CROSS_TERMS)
    terms = [rng.choice(COEFFS) * cross]
    if difficulty == 1:
        # ⚠️ **只從 PURE_Y 抽，不抽 PURE_X**，而這不是排版偏好。
        # 一個只含 $x$ 的項會被 $\int M\,dx$ 一起還原，於是 $h'(y) = 0$，
        # 第三、四步變成「$h(y) = 0$」——**整個題型真正要教的那一步就空了**，
        # 而頁面看起來完全正常。落地時第一批樣本三題全是這樣。
        terms.append(rng.choice(COEFFS) * rng.choice(PURE_Y_TERMS))
        return sp.expand(sum(terms))

    # 難度 2：三項，其中恰好一項是超越的。
    if rng.random() < 0.5:
        terms.append(rng.choice(COEFFS) * rng.choice(TRANSCENDENTAL_X))
        terms.append(rng.choice(COEFFS) * rng.choice(PURE_Y_TERMS))
    else:
        terms.append(rng.choice(COEFFS) * rng.choice(TRANSCENDENTAL_Y))
        terms.append(rng.choice(COEFFS) * rng.choice(PURE_X_TERMS))
    return sp.expand(sum(terms))


# --- 難度 3：積分因子的四個族 ------------------------------------------------


#: 難度 3 的多項式只從這個**比較小的**池子抽。
#:
#: ⚠️ 理由是難度 3 的 $M, N$ 不是這個多項式本身，是它經過
#: 「乘上參數、再微分一次、再乘上一個變數」之後的東西——用 `CROSS_TERMS`
#: 那個池子（含 $x^3y$、$x^2y^2$）抽出來的題目，$N$ 會長到四項、
#: 而「乘上 $\mu$」那一步的算式會超出一行。**難度 3 難的地方是積分因子，
#: 不是抄寫。**
SMALL_TERMS = (x, y, x * y, x**2, y**2, x**2 * y, x * y**2)

SMALL_COEFFS = (-2, -1, 1, 2, 3)


def _draw_polynomial(rng: random.Random, needs: sp.Symbol) -> sp.Expr | None:
    """兩項的小多項式，保證對 `needs` 的偏導不恆為 0、而且真的有兩項。

    「真的有兩項」是刻意檢查的：兩次抽到同一個單項式會合併成一項，
    而單項的題目通常同時也是可分離的——那不是這個題型要練的東西，
    而它不會讓任何測試變紅。
    """
    for _ in range(20):
        terms = [rng.choice(SMALL_COEFFS) * rng.choice(SMALL_TERMS)
                 for _ in range(2)]
        candidate = sp.expand(sum(terms))
        if candidate == 0 or sp.diff(candidate, needs) == 0:
            continue
        if len(candidate.as_ordered_terms()) < 2:
            continue
        return candidate
    return None


def _draw_non_exact(rng: random.Random) -> dict | None:
    """抽一個不恰當的方程，連同它的積分因子與位勢函數。"""
    family = rng.choice(("exp_x", "power_x", "exp_y", "power_y"))

    if family == "exp_x":
        a = rng.choice((-2, -1, 1, 2))
        H = _draw_polynomial(rng, y)
        if H is None:
            return None
        M, N = sp.expand(a * H + sp.diff(H, x)), sp.expand(sp.diff(H, y))
        return {"family": family, "mu": sp.exp(a * x), "M": M, "N": N,
                "potential": sp.exp(a * x) * H, "in_x": True, "parameter": a}

    if family == "power_x":
        k = rng.choice((1, 2))
        P = _draw_polynomial(rng, y)
        if P is None:
            return None
        M = sp.expand((k + 1) * P + x * sp.diff(P, x))
        N = sp.expand(x * sp.diff(P, y))
        return {"family": family, "mu": x**k, "M": M, "N": N,
                "potential": sp.expand(x**(k + 1) * P), "in_x": True,
                "parameter": k}

    if family == "exp_y":
        b = rng.choice((-2, -1, 1, 2))
        H = _draw_polynomial(rng, x)
        if H is None:
            return None
        M, N = sp.expand(sp.diff(H, x)), sp.expand(b * H + sp.diff(H, y))
        return {"family": family, "mu": sp.exp(b * y), "M": M, "N": N,
                "potential": sp.exp(b * y) * H, "in_x": False, "parameter": b}

    k = rng.choice((1, 2))
    Q = _draw_polynomial(rng, x)
    if Q is None:
        return None
    M = sp.expand(y * sp.diff(Q, x))
    N = sp.expand((k + 1) * Q + y * sp.diff(Q, y))
    return {"family": family, "mu": y**k, "M": M, "N": N,
            "potential": sp.expand(y**(k + 1) * Q), "in_x": False,
            "parameter": k}


def _factors_apart(expr: sp.Expr) -> bool:
    r"""`expr` 是否寫得成 $f(x)g(y)$。

    判準是 $u\,u_{xy} - u_x u_y \equiv 0$（等價於 $\partial_x\partial_y \ln u = 0$，
    但不必碰對數，所以對多項式來說只是一次 `expand`）。

    ⚠️ **只用 `expand` 不用 `simplify`，而失敗的方向是刻意選的。** 判不出來
    的時候這個函式回 `False`＝「不可分離」＝**留下這一題**。它是一道品質篩，
    不是正確性閘門；漏掉一題可分離的題目只是那一題比較弱，
    而誤判成可分離只會多重抽一次。反過來寫（判不出來就丟掉）會在
    難度 2 的超越項上安靜地把通過率壓到很低。
    """
    return sp.expand(expr * sp.diff(expr, x, y)
                     - sp.diff(expr, x) * sp.diff(expr, y)) == 0


def _is_also_separable(M: sp.Expr, N: sp.Expr) -> bool:
    r"""$M\,dx + N\,dy = 0$ 是不是也可以用分離變數做掉。

    ⚠️ **這是 PLAN §2.4(b) 那個顧慮的落點**：「若你想出某個題型但生成的式子
    同時屬於另一個題型，可以選擇避開（避免學生用別的方法做完，
    逐步解答卻是另一套）」。

    對這個題型它特別重要，因為**難度 3 的整個重點就是積分因子**——
    一道同時可分離的題目，學生兩行就做完了，一次都沒有碰到 $\mu$，
    而他不會知道自己跳過了什麼。實測（未加這道篩之前）：
    難度 1 有 33%、難度 3 有 60% 同時是可分離的。
    """
    numerator, denominator = sp.fraction(sp.cancel(sp.together(M / N)))
    return _factors_apart(numerator) and _factors_apart(denominator)


def _derive_integrating_factor(M: sp.Expr, N: sp.Expr, in_x: bool):
    """**照學生的作法把 $\\mu$ 算出來**，不使用抽樣時記下來的那一個。

    回傳 `(判別比, μ)`；判別比若還含另一個變數就回 `None`
    ——那表示這一族的參數化壞了，該重抽而不是硬印一個算不出來的步驟。
    """
    if in_x:
        ratio = sp.simplify((sp.diff(M, y) - sp.diff(N, x)) / N)
        if ratio.has(y) or ratio == 0:
            return None
        return ratio, sp.powsimp(sp.simplify(sp.exp(sp.integrate(ratio, x))))
    ratio = sp.simplify((sp.diff(N, x) - sp.diff(M, y)) / M)
    if ratio.has(x) or ratio == 0:
        return None
    return ratio, sp.powsimp(sp.simplify(sp.exp(sp.integrate(ratio, y))))


# --- 逐步解答 ---------------------------------------------------------------


def _exactness_step(M: sp.Expr, N: sp.Expr, exact: bool) -> Step:
    My, Nx = sp.expand(sp.diff(M, y)), sp.expand(sp.diff(N, x))
    if exact:
        return Step(
            "Test for exactness",
            rf"\frac{{\partial M}}{{\partial y}} = {sp.latex(My)} "
            rf"= \frac{{\partial N}}{{\partial x}}",
            "The two mixed partials agree, so the left-hand side is the total "
            "differential $dF$ of some potential function $F(x,y)$.",
        )
    return Step(
        "Test for exactness",
        rf"\frac{{\partial M}}{{\partial y}} = {sp.latex(My)} "
        rf"\ne {sp.latex(Nx)} = \frac{{\partial N}}{{\partial x}}",
        "The mixed partials disagree, so the equation is not exact as it "
        "stands and no potential function exists yet.",
    )


def _potential_steps(M: sp.Expr, N: sp.Expr, F: sp.Expr) -> list[Step]:
    """恰當方程的核心四步：積分 $M$ → 對 $y$ 微分 → 求 $h(y)$ → 寫下解。"""
    antiderivative = sp.expand(sp.integrate(M, x))
    h = sp.simplify(F - antiderivative)
    h_prime = sp.simplify(sp.diff(F, y) - sp.diff(antiderivative, y))
    steps = [
        Step(
            "Integrate $M$ with respect to $x$",
            rf"F(x, y) = \int M\,dx = {sp.latex(antiderivative)} + h(y)",
            "Integrating $M$ with respect to $x$ treats $y$ as a constant, so "
            "the constant of integration may still depend on $y$ — that is "
            "what $h(y)$ stands for.",
        ),
    ]
    if h_prime == 0:
        # $h'(y) = 0$ 表示 $F$ 沒有任何一個「只含 $y$」的項。什麼時候會這樣：
        #
        # * **難度 1、2 永遠不會**——`_draw_potential()` 保證有一個純 $y$ 的項。
        # * **難度 3 的 $\mu(x)$ 兩族（`exp_x`、`power_x`）一定會**，而那是
        #   構造上的必然：$F = \mu(x)H$，$\mu(x)$ 乘在每一項上，所以沒有一項
        #   還能只含 $y$。（試著在 $F$ 上加一個 $G(y)$：$N = F_y/\mu$ 就會冒出
        #   $\mu(x)^{-1}G'(y)$，題目上的 $N$ 立刻不是多項式了。）
        # * **難度 3 的 $\mu(y)$ 兩族（`exp_y`、`power_y`）看 $H$ 有沒有純 $y$ 項**
        #   ——$\mu(y)$ 乘上一個只含 $y$ 的項仍然只含 $y$，所以兩種都出得到。
        #
        # 所以這裡不硬湊出一個 $h(y)$，而是把這一步講成它真正的意思：
        # **它是積分因子對不對的驗算**。
        steps.append(Step(
            "Differentiate with respect to $y$ and compare with $N$",
            rf"\frac{{\partial F}}{{\partial y}} "
            rf"= {sp.latex(sp.expand(sp.diff(antiderivative, y)))} + h'(y) "
            rf"= {sp.latex(N)} \quad\Longrightarrow\quad h'(y) = 0",
            "Nothing is left over, so $h$ is a constant and gets absorbed into "
            "the arbitrary constant on the right. This step is also the check "
            "on the previous work: if anything containing $x$ had survived "
            "here, the integrating factor would have been wrong.",
        ))
    else:
        steps.append(Step(
            "Differentiate with respect to $y$ and compare with $N$",
            rf"\frac{{\partial F}}{{\partial y}} "
            rf"= {sp.latex(sp.expand(sp.diff(antiderivative, y)))} + h'(y) "
            rf"= {sp.latex(N)}",
            "Whatever is left over after cancelling must be $h'(y)$; if a term "
            "containing $x$ survived here, the earlier integration would be "
            "wrong.",
        ))
        steps.append(Step(
            "Solve for $h(y)$",
            rf"h'(y) = {sp.latex(sp.expand(h_prime))}"
            rf"\quad\Longrightarrow\quad h(y) = {sp.latex(h)}",
        ))
    steps.append(Step(
        "Write the solution in implicit form",
        rf"{sp.latex(F)} = {sp.latex(C1)}",
        "The solution of an exact equation is the level curve of its potential "
        "function. Solving for $y$ explicitly is usually neither possible nor "
        "useful.",
    ))
    return steps


def _integrating_factor_steps(spec: dict, ratio: sp.Expr, mu: sp.Expr) -> list[Step]:
    M, N = spec["M"], spec["N"]
    if spec["in_x"]:
        test = (rf"\frac{{M_y - N_x}}{{N}} = {sp.latex(ratio)}")
        note = ("This quotient contains no $y$, so an integrating factor "
                "depending on $x$ alone exists. (Had it still contained $y$, "
                "the next thing to try would be $(N_x - M_y)/M$ as a function "
                "of $y$ alone.)")
        formula = (rf"\mu(x) = \exp\left(\int {sp.latex(ratio)}\,dx\right) "
                   rf"= {sp.latex(mu)}")
    else:
        test = (rf"\frac{{N_x - M_y}}{{M}} = {sp.latex(ratio)}")
        note = ("This quotient contains no $x$, so an integrating factor "
                "depending on $y$ alone exists. Trying $(M_y - N_x)/N$ first "
                "would have left an $x$ behind, which is the signal to switch "
                "to the other variable.")
        formula = (rf"\mu(y) = \exp\left(\int {sp.latex(ratio)}\,dy\right) "
                   rf"= {sp.latex(mu)}")
    return [
        Step("Look for an integrating factor", test, note),
        Step("Build the integrating factor", formula),
        Step(
            "Multiply the equation through by $\\mu$",
            _equation_latex(sp.expand(sp.simplify(mu * M)),
                            sp.expand(sp.simplify(mu * N))),
            "This new equation has exactly the same solutions as the original "
            "one, and it is exact — so the standard procedure now applies.",
        ),
    ]


@register(
    TEMPLATE_ID,
    name="Exact Equations and Integrating Factors",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    if difficulty in (1, 2):
        F = _draw_potential(rng, difficulty)
        M, N = sp.expand(sp.diff(F, x)), sp.expand(sp.diff(F, y))
        if sp.simplify(N) == 0 or sp.simplify(M) == 0:
            return None
        if sp.diff(N, x) == 0 or sp.diff(M, y) == 0:
            # $N$ 不含 $x$（或 $M$ 不含 $y$）→ 方程退化成兩個各自獨立的積分。
            # `CROSS_TERMS` 保證不會發生，這裡是第二道（規則 4：不靜默）。
            return None
        mu = sp.S.One
        spec = {"family": "exact", "M": M, "N": N, "potential": F}
        steps = [_exactness_step(M, N, exact=True)] + _potential_steps(M, N, F)
        statement = ("Verify that the following equation is exact, and find "
                     "its general solution in implicit form.")
        claims_not_exact = False
    else:
        spec = _draw_non_exact(rng)
        if spec is None:
            return None
        M, N, F = spec["M"], spec["N"], spec["potential"]
        if sp.simplify(M) == 0 or sp.simplify(N) == 0:
            return None
        derived = _derive_integrating_factor(M, N, spec["in_x"])
        if derived is None:
            return None
        ratio, mu = derived
        if sp.simplify(mu - spec["mu"]) != 0:
            return None                       # 導出來的 μ 與參數化的不一致
        exact_M, exact_N = sp.expand(sp.simplify(mu * M)), sp.expand(sp.simplify(mu * N))
        steps = ([_exactness_step(M, N, exact=False)]
                 + _integrating_factor_steps(spec, ratio, mu)
                 + _potential_steps(exact_M, exact_N, F))
        statement = ("The following equation is not exact. Find a suitable "
                     "integrating factor, and then solve the equation.")
        claims_not_exact = True

    if _is_also_separable(M, N):
        return None
    if has_special_function(F) or has_ugly_fraction(F):
        return None
    if ugliness(F) > UGLINESS_LIMIT[difficulty]:
        return None
    for step in steps:
        if "\\int" in step.latex and "Integral" in step.latex:
            return None                       # 積不出來的東西不出給學生

    params = {
        "family": spec["family"],
        "difficulty_case": "exact" if difficulty in (1, 2) else spec["family"],
        "M": str(M),
        "N": str(N),
        "potential": str(F),
        "mu": str(mu),
    }
    if difficulty == 3:
        params["parameter"] = spec["parameter"]
        params["factor_in_x"] = spec["in_x"]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=_equation_latex(M, N),
        answer_latex=rf"{sp.latex(F)} = {sp.latex(C1)}",
        answer_expr=F,
        answer_kind="implicit",
        steps=steps,
        check=ExactCheck(var_x=x, var_y=y, M=M, N=N, potential=F, mu=mu,
                         claims_not_exact=claims_not_exact),
    )
