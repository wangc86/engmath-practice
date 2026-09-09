r"""複數（指數）形式的 Fourier 級數——課綱 W3，工作項 2B12。

===========================================================================
零、這個題型補的是一個「看得到、練不到」的缺口
===========================================================================

**展示端從 v0.22 起就在教複數形式**：W3 的 `demo.fourier.additive`
會印出 $c_1$ 的實部與虛部，並解釋「$|c_n|$ 恰好是振幅的一半，因為能量被
分給了 $+n$ 與 $-n$ 兩邊」（`app/static/demos/lib/transform.js` 的
`exponentialCoefficient()`，那一段註解寫著「課綱第 3 週要求兩種形式的對應」）。

⛔ **而出題端一題都沒有。** §7 #28(b) 就是這一格，老師 2026-09-09 答「要含」。

⚠️ 同一輪老師也答了 §7 #28(c)（逐項微分／積分與收斂定理）：**不做**。
那不是「延後」，是**移出範圍**——理由與 D67 刪五個題型相同，是課程範圍的決定。

===========================================================================
一、慣例：與 D72 的 Fourier 變換同號
===========================================================================

$$f(x) \sim \sum_{n=-\infty}^{\infty} c_n\,e^{\,i n\pi x/L},
\qquad c_n = \frac{1}{2L}\int_{-L}^{L} f(x)\,e^{-i n\pi x/L}\,dx$$

⚠️ **正向（求係數）用 $e^{-in\pi x/L}$、展開式用 $e^{+in\pi x/L}$**
——與 D72 為 Fourier 變換定的方向**一致**，這不是巧合而是刻意的：
一個學生在 W3 學級數、W4 學變換，兩邊的指數如果反號，他會以為自己記錯。

由這個慣例導出的換算是

$$c_n = \frac{a_n - i\,b_n}{2}\ (n \ge 1),\qquad c_0 = \frac{a_0}{2},
\qquad c_{-n} = \overline{c_n}$$

⛔ **$c_0 = \frac{a_0}{2}$ 這一格直接踩在 D73 上**（老師 2026-09-08 拍板
「$a_0$ 要除 2」）。所以程式裡它寫成 `core.constant_term(a0)` 而不是 `a0/2`
——**不除 2 的慣例下 $c_0 = a_0$**，寫死的話翻轉 `A0_IS_HALVED`
會得到一個「級數常數項對、$c_0$ 錯」的系統，而兩個數字各自都很合理。

===========================================================================
二、生成路徑與驗證路徑
===========================================================================

* **生成**：`core.coefficients_of(fn)` 拿到 $a_0, a_n, b_n$，再換算成 $c_n$。
  這條路是刻意的——**課綱要的是「兩種形式的對應」**，不是「再積一次分」。
* **驗證**：直接對定義式積分 $\frac{1}{2L}\int f e^{-in\pi x/L}dx$，
  在具體的整數 $n$ 上比對。⛔ 那是一條與 $a_n, b_n$ **完全無關**的路。

⚠️ **探測點同時取正的與負的 $n$**，理由不只是多測一點：
$a_n$、$b_n$ 的封閉形式是對 $n \ge 1$ 導出來的，把它們代進
$c_n = \frac{a_n - ib_n}{2}$ 就等於**宣稱那個封閉形式延拓到負的 $n$ 仍然對**。
那個宣稱通常成立（$a_n$ 在 $n$ 上是偶的、$b_n$ 是奇的），但**它是一個宣稱**，
所以要有東西驗它。負的探測點就是驗它的東西。

===========================================================================
三、三層閘門
===========================================================================

1. `_gate_definition_integral`——$c_n$ 對定義式的積分，在 $n = \pm1, \pm2, 3$ 上。
2. `_gate_c0_is_the_mean`——$c_0$ 必須是 $f$ 在一週期上的平均值。
   ⚠️ **這是一個與慣例無關的數學事實**，所以它同時守住 D73 有沒有被寫對。
3. `_gate_conjugate_symmetry`——實值 $f$ 要求 $c_{-n} = \overline{c_n}$，
   **符號上對所有 $n$**，不是五個點。

⛔ **「$a_n = 2\operatorname{Re}c_n$、$b_n = -2\operatorname{Im}c_n$」不是閘門。**
$c_n$ 就是從 $a_n, b_n$ 算出來的，拿它回頭驗自己是恆真的。
它是**逐步解答的第 3 步**（教學內容），不是驗證。
寫在這裡是因為它看起來很像一層閘門，而它不是。
"""

from __future__ import annotations

import random

import sympy as sp

from ..base import Problem, Step, register
from ..pretty import is_pretty_in_n
from . import core
from .core import N_INT, PiecewiseFn, ResonantIntegral, x
# ⚠️ **刻意共用全幅級數的函數族，不另寫一份。** 同一個 $f$ 出現在兩個題型裡
# 是好事（同一個函數的兩種寫法正是課綱要的對應），而複製一份族定義只會漂移。
from .series import HALF_PERIODS_D3, _family_d1, _family_d2, _family_d3  # noqa: F401

TEMPLATE_ID = "fourier.series.complex"
CHAPTER = "Fourier Series"

#: 係數的漂亮度上限。⚠️ 比全幅級數寬一點（12/20/30 → 16/26/36），
#: 因為 $c_n$ 是 $a_n$ 與 $b_n$ **兩者**的組合，項數本來就比較多。
#: ⛔ 這是「同一個 $f$ 在兩個題型裡」的直接後果，不是放水。
UGLINESS_LIMIT = {1: 16, 2: 26, 3: 36}

DIFFICULTY_NOTES = {
    1: "One polynomial on the whole interval, $L = \\pi$ — $c_n$ is either "
       "purely real or purely imaginary",
    2: "Two pieces meeting at $x = 0$, $L = \\pi$ — $c_n$ is genuinely complex",
    3: "Two or three pieces and a general half-period $L$",
}

STATEMENT = (
    "Find the complex (exponential) Fourier series of the following function, "
    "which is extended periodically with period $2L$."
)


# --- 慣例，由 D72 的方向與 D73 的 $a_0$ 一起導出 -----------------------------

#: 求係數那條積分裡指數的正負號。⛔ **與 `transform.FORWARD_EXP_SIGN` 同號**
#: （D72：正向用 $e^{-i\omega x}$），而那個一致性由
#: `test_the_two_fourier_conventions_point_the_same_way` 釘住。
COEFFICIENT_EXP_SIGN = -1


def basis_exponent_latex(L: sp.Expr, sign: int = 1) -> str:
    r"""展開式（`sign=+1`）或係數積分（`sign=-1`）裡 $e^{\cdots}$ 的指數。

    直接用 SymPy 印 $\pm i n\pi x/L$，所以 $L=\pi$ 自動收成 $inx$、
    $L=1$ 自動變成 $i\pi n x$——**不必為那兩個特例寫分支**
    （附錄 C.4 的「$L=\pi$ 時基底要收乾淨」那一條）。
    """
    return sp.latex(sign * sp.I * N_INT * sp.pi * x / L)


def cn_from_real_coefficients(a_n: sp.Expr, b_n: sp.Expr) -> sp.Expr:
    r"""$c_n = \frac{a_n - i b_n}{2}$（由本檔第一節的慣例導出）。

    ⛔ **收尾用 `core._tidy()` 而不是 `sp.simplify()`**，理由與附錄 C.4
    最後一列同一條：`simplify` 會把不同的 $n$ 冪次硬湊成一個大分式
    （實測本題型的難度 2 會生出
    $\frac{-(-1)^n - in((-1)^n\pi - \pi + 2)}{2\pi n^2}$ 這種東西），
    每一個字元都對，而學生要看出「$1/n$ 那一項」與「$1/n^2$ 那一項」
    得先自己拆回去。分組之後兩項的衰減速度一眼看得出來，
    **而那正是複數形式這個題型要教的事情之一**（頻譜隨 $n$ 怎麼掉）。
    """
    return core._tidy((a_n + COEFFICIENT_EXP_SIGN * sp.I * b_n) / 2)


def c0_from_a0(a_0: sp.Expr) -> sp.Expr:
    r"""$c_0$ 就是級數的常數項。

    ⛔ **走 `core.constant_term()`，不要寫 `a_0 / 2`。** 那個 $\frac12$ 屬於
    $a_0$ 的慣例（D73、`A0_IS_HALVED`），不屬於複數形式；寫死的話翻轉那個常數
    會得到「級數常數項對、$c_0$ 錯」的系統，而兩個數字各自都很合理。
    """
    return core.constant_term(a_0)


# --- 驗證閘門 ---------------------------------------------------------------


#: 閘門用的單項式定積分快取，鍵是 (次數, 下限, 上限, L, k)。
#:
#: ⚠️ **與 `core._GENERIC_DEFINITE` 同一個作法，也同一條紅線**：它只做兩件事
#: ——把每段多項式按線性拆成單項式、記住算過的結果。**走的仍然是定積分**，
#: 也就是與生成路徑（$a_n$、$b_n$ 的封閉形式再換算）完全無關的那一條路。
#: ⛔ 不可以為了再快一點而改成「從 $a_n$、$b_n$ 推回去」——那會讓兩條路合流，
#: 交叉驗證就不成立了，而且**它仍然會全綠**。
#:
#: 命中率高的原因與 core 那一份相同：上下限只有 $\{\pm L, 0, \pm L/2\}$ 幾種、
#: 次數只到 2、$L$ 只有三個值、$k$ 只有四個。實測 30 題的難度 3 從約 81 秒
#: 降到約 12 秒。
_PROBE_DEFINITE: dict[tuple, sp.Expr] = {}


def _definite_monomial_exp(degree: int, lo: sp.Expr, hi: sp.Expr,
                           L: sp.Expr, k: int) -> sp.Expr:
    r"""$\int_{lo}^{hi} x^{d}\,e^{-ik\pi x/L}\,dx$（指數的正負號由慣例決定）。"""
    key = (degree, sp.srepr(lo), sp.srepr(hi), sp.srepr(L), k)
    if key not in _PROBE_DEFINITE:
        kernel = sp.exp(COEFFICIENT_EXP_SIGN * sp.I * k * sp.pi * x / L)
        _PROBE_DEFINITE[key] = sp.integrate(x**degree * kernel, (x, lo, hi))
    return _PROBE_DEFINITE[key]


def coefficient_by_probe(fn: PiecewiseFn, k: int) -> sp.Expr:
    r"""**獨立路徑**：$c_k = \frac{1}{2L}\int_{-L}^{L} f(x)e^{-ik\pi x/L}dx$，
    在具體的整數 $k$ 上照定義積一次。

    ⚠️ 刻意寫得很直接、不做任何「聰明」的化簡——與 `core.coefficient_by_probe`
    同一個理由：任何捷徑都會削弱閘門。
    """
    L = fn.half_period
    total = sp.Integer(0)
    for piece in fn.pieces:
        # ⚠️ 非多項式的一段走沒有快取的整段積分，**不是拋例外**——理由與
        # `core._integrate_over()` 那一段逐字相同：這條分支在目前的函數族上
        # 一次都不會執行到，而它是日後擴族時唯一的活路；拿掉它會讓這裡
        # 安靜地變成「只支援多項式」。
        try:
            terms = sp.Poly(sp.expand(piece.poly), x).terms()
        except sp.PolynomialError:
            kernel = sp.exp(COEFFICIENT_EXP_SIGN * sp.I * k * sp.pi * x / L)
            total += sp.integrate(piece.poly * kernel, (x, piece.lo, piece.hi))
            continue
        for (degree,), coefficient in terms:
            total += coefficient * _definite_monomial_exp(
                degree, piece.lo, piece.hi, L, k)
    return sp.simplify(total / (2 * L))


class ComplexSeriesCheck:
    """複數形式的驗證閘門（`Verifier` 協定的實作）。

    ⚠️ **不是 frozen dataclass，因為它要拿一個 `FourierCheck` 當欄位**——
    不對，它是；寫成一般 class 只是為了讓 `__init__` 讀起來直接一點。
    仍然是純資料、不含 lambda、可 pickle（與 `Check` 相同的理由，§2.2）。
    """

    #: 探測點。⛔ **正負都要有**，理由見檔頭第二節（負的那個驗的是
    #: 「$a_n$、$b_n$ 的封閉形式延拓到負的 $n$ 仍然對」這個宣稱）。
    #:
    #: ⚠️ **為什麼只有一個負的，而不是對稱地放兩三個**：第三層已經**符號上**
    #: 證明了 $c_{-n} = \overline{c_n}$ 對所有 $n$ 成立，而 $f$ 是實值的
    #: 所以參考值本身也滿足 $c^{\text{ref}}_{-n} = \overline{c^{\text{ref}}_n}$
    #: ——兩者一合，「在 $+n$ 上對」就蘊含「在 $-n$ 上對」。
    #: ⛔ **那是一個證明，不是一句「應該夠了」**（同 D68 那個歸納法論證）。
    #: 留一個負探測點是因為它便宜（約 0.4 秒），而且它讓上面那個論證
    #: 萬一哪天被改壞了仍然有一道獨立的防線。
    #: 實測：五個探測點時每題閘門約 3.4 秒，四個時約 2.6 秒，而每個難度生 30 題。
    PROBES = (1, 2, 3, -1)

    def __init__(self, fn: PiecewiseFn, coefficients, cn: sp.Expr, c0: sp.Expr):
        self.fn = fn
        self.coefficients = coefficients      # 實數形式的 a0/an/bn（步驟要用）
        self.cn = cn
        self.c0 = c0

    def verify(self, problem) -> tuple[bool, str]:
        for gate in (self._gate_definition_integral, self._gate_c0_is_the_mean,
                     self._gate_conjugate_symmetry):
            ok, reason = gate()
            if not ok:
                return False, reason
        return True, ""

    def _gate_definition_integral(self) -> tuple[bool, str]:
        for k in self.PROBES:
            claimed = sp.simplify(self.cn.subs(N_INT, k))
            reference = coefficient_by_probe(self.fn, k)
            if sp.simplify(claimed - reference) != 0:
                return False, (
                    f"閘門一：c_n 在 n={k} 對不上"
                    f"（封閉形式 {claimed}，定義的積分 {reference}）"
                )
        return True, ""

    def _gate_c0_is_the_mean(self) -> tuple[bool, str]:
        r"""$c_0$ 必須是 $f$ 在一週期上的平均值。

        ⛔ **這是一個與慣例無關的數學事實**，所以它同時守住 D73（$a_0$ 除 2）
        有沒有被寫對：若 `c0_from_a0()` 被改成寫死的 `a_0`，
        這一層會在 `A0_IS_HALVED` 為 `True` 時立刻紅。
        """
        L = self.fn.half_period
        mean = sp.simplify(
            sum(sp.integrate(p.poly, (x, p.lo, p.hi)) for p in self.fn.pieces)
            / (2 * L))
        if sp.simplify(self.c0 - mean) != 0:
            return False, f"閘門二：c_0 = {self.c0}，但 f 的平均值是 {mean}"
        return True, ""

    def _gate_conjugate_symmetry(self) -> tuple[bool, str]:
        r"""實值 $f$ $\Rightarrow$ $c_{-n} = \overline{c_n}$，**對所有 $n$**。

        ⚠️ `N_INT` 帶著 `integer=True, positive=True`，所以 `conjugate()`
        化簡得動 $(-1)^n$ 這一類因子；把 assumptions 拿掉會讓這一層
        **變成永遠算不出來而不是永遠不成立**——那是最糟的一種失效。
        """
        # ⚠️ **只 simplify 差**，不要先各自 simplify 再相減：實測那樣是三次
        # `simplify` 而不是一次，這一層的時間因此多了兩倍（1.6 秒 → 0.6 秒）。
        flipped = self.cn.subs(N_INT, -N_INT)
        conjugated = sp.conjugate(self.cn)
        if sp.simplify(flipped - conjugated) != 0:
            return False, (
                f"閘門三：實值 f 要求 c_{{-n}} = conj(c_n)，"
                f"但 {flipped} ≠ {conjugated}"
            )
        return True, ""


# --- 組題 -------------------------------------------------------------------


def _wrap(expr: sp.Expr) -> str:
    """係數是相加的或帶負號時要括起來（與 `series._wrap` 同一個理由）。"""
    latex = sp.latex(expr)
    if isinstance(expr, sp.Add) or expr.could_extract_minus_sign():
        return r"\left(%s\right)" % latex
    return latex


def answer_latex_of(fn: PiecewiseFn, cn: sp.Expr, c0: sp.Expr) -> str:
    r"""$f(x) \sim c_0 + \sum_{n \ne 0} c_n e^{in\pi x/L}$，係數都代進去。

    ⚠️ **$c_0$ 寫在 $\sum$ 外面而不是併進去**，兩個理由：
    (1) $c_n$ 的封閉形式在 $n=0$ 幾乎一定沒有定義（分母有 $n$）；
    (2) 這樣整個字串裡**一個 `=` 都沒有**，而 `test_steps_are_complete`
    是用 `=` 切字串來比對「最後一步就是答案」的——
    寫成 `c_n = \dots,\ c_0 = \dots` 會有兩個 `=`，那個比對就對不起來了。
    ⛔ 第 (2) 點是遷就一個測試的啟發式，**而它剛好與 (1) 指向同一個寫法**，
    所以這裡沒有為了測試而扭曲輸出；若哪天兩者衝突，要改的是那個啟發式。
    """
    exponent = basis_exponent_latex(fn.half_period, +1)
    head = f"{sp.latex(c0)} + " if c0 != 0 else ""
    return r"f(x) \sim %s\sum_{n \ne 0} %s\,e^{%s}" % (head, _wrap(cn), exponent)


def _steps(fn: PiecewiseFn, c, cn: sp.Expr, c0: sp.Expr, answer: str) -> list[Step]:
    L = fn.half_period
    forward = basis_exponent_latex(L, +1)
    backward = basis_exponent_latex(L, COEFFICIENT_EXP_SIGN)
    real_form = core.series_latex(L, c.an != 0, c.bn != 0)
    return [
        Step(
            "Write down the form you are aiming for",
            # ⛔ **前置因子要走 `core.over_L_latex(1, 2L)`，不可以自己拼字串。**
            # ⚠️ 實測抓到的：原本寫 `\frac{1}{2` + `sp.latex(L)` + `}`，
            # 而 $L = 1$ 時它印出 **$\frac{1}{21}$**——讀成二十一分之一。
            # 這與 v0.39 的 $\frac{21}{2}$ 是**同一個錯的第二次發生**
            # （字串拼接把兩個數字黏在一起），所以這一次不是就地補一個特例，
            # 而是改用 core 那支本來就為了這件事存在的函式。
            rf"f(x) \sim \sum_{{n=-\infty}}^{{\infty}} c_n\,e^{{{forward}}},"
            rf"\qquad c_n = {core.over_L_latex(1, 2 * L)}"
            rf"\int_{{-{sp.latex(L)}}}^{{{sp.latex(L)}}} f(x)\,e^{{{backward}}}\,dx",
            "Note the sign: the expansion uses $e^{+in\\pi x/L}$ and the "
            "coefficient integral uses $e^{-in\\pi x/L}$. This is the same "
            "direction the Fourier transform uses later in the course.",
        ),
        Step(
            "Start from the real form",
            real_form,
            "You may either integrate the definition above directly, or compute "
            "$a_n$ and $b_n$ first and convert. The conversion is the point of "
            "this exercise, so that is the route shown here.",
        ),
        Step(
            "The real coefficients",
            rf"a_0 = {sp.latex(c.a0)},\qquad a_n = {sp.latex(c.an)},"
            rf"\qquad b_n = {sp.latex(c.bn)}",
        ),
        Step(
            "Convert to the exponential form",
            rf"c_n = \frac{{a_n - i\,b_n}}{{2}} = {_wrap(cn)},"
            rf"\qquad c_0 = \frac{{a_0}}{{2}} = {sp.latex(c0)}",
            "Euler's formula turns $a_n\\cos + b_n\\sin$ into two exponentials, "
            "one at $+n$ and one at $-n$. ⚠️ Each carries **half** the "
            "amplitude — that factor of $\\tfrac12$ is the step students most "
            "often drop.",
        ),
        Step("Complex Fourier series", answer),
        Step(
            "Check: the two halves are conjugates",
            rf"c_{{-n}} = \overline{{c_n}} = {_wrap(sp.simplify(sp.conjugate(cn)))}",
            "$f$ is real, so the $-n$ term must be the complex conjugate of the "
            "$+n$ term; together they add up to something real. If your $c_n$ "
            "does not have this property, something went wrong.",
        ),
    ]


def build_problem(fn: PiecewiseFn, difficulty: int, params: dict) -> Problem | None:
    try:
        c = core.coefficients_of(fn)
    except ResonantIntegral as exc:
        core.logger.info("係數積分不封閉，重抽：%s", exc)
        return None

    cn = cn_from_real_coefficients(c.an, c.bn)
    c0 = c0_from_a0(c.a0)
    if cn == 0:
        return None                      # 整個級數只剩常數項，不是一道題目

    allow_quarter = difficulty == 3
    if not is_pretty_in_n(cn, N_INT, UGLINESS_LIMIT[difficulty], allow_quarter):
        return None

    answer = answer_latex_of(fn, cn, c0)
    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=STATEMENT,
        statement_latex="f(x) = " + fn.cases_latex(),
        answer_latex=answer,
        answer_expr=sp.Tuple(c0, cn),
        answer_kind="coefficients",
        steps=_steps(fn, c, cn, c0, answer),
        check=ComplexSeriesCheck(fn=fn, coefficients=c, cn=cn, c0=c0),
    )


@register(
    TEMPLATE_ID,
    name="Fourier Series (Complex Form)",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    if difficulty == 1:
        fn, _parity = _family_d1(rng)
    elif difficulty == 2:
        fn = _family_d2(rng)
    else:
        fn = _family_d3(rng)
    if fn is None:
        return None
    params = {
        "half_period": sp.srepr(fn.half_period),
        "pieces": [[sp.srepr(p.poly), sp.srepr(p.lo), sp.srepr(p.hi)]
                   for p in fn.pieces],
        "n_pieces": len(fn.pieces),
        "parity": fn.parity(),
        "has_jump": fn.has_jump,
    }
    return build_problem(fn, difficulty, params)
