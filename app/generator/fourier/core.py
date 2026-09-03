r"""Fourier 級數的共用機器：函數族、係數、**四層驗證閘門**、排版與步驟。

兩個題型（`series.py`／`half_range.py`）都只是在這裡挑參數、
組敘述。所有數學都在這一個檔案裡，所有閘門也是。

===========================================================================
一、為什麼不能沿用 ODE 那套閘門（PLAN §2.10.1）
===========================================================================

ODE 題目是「一條方程 + 一個滿足它的函數」，驗證有一個天然的定義：**代回方程**。
Fourier 題目是「一個函數 + 一組由積分定義的係數」——

    a_n = (1/L) ∫_{-L}^{L} f(x) cos(nπx/L) dx

**沒有方程可以代回去**，而那條積分**就是生成係數的路徑**。拿定義式重算一次，
只是把同一段程式再跑一遍，證明不了任何事。

閘門的本質因此要重新講一次：**用一條與生成路徑獨立的路徑重算，兩者必須相等。**
ODE 恰好有一條現成的獨立路徑，所以以前不必把這句話說出來。

===========================================================================
二、反向構造：不挑答案，挑一個「係數必然封閉」的函數族（PLAN §2.10.2）
===========================================================================

ODE 的反向構造是字面意義的倒推（先選特徵根，再算係數）。Fourier 做不到，
而且**不該勉強做**：

- 先挑係數再把級數加起來 → 有限三角和的 Fourier 係數就是它自己，一眼看穿。
- 隨機生一個 f 再算係數 → 退回正向求解，多數樣本會積出 Si、Ci 或積不出來。

正確的做法是把反向構造**往上提一層**：挑一個係數必然漂亮的**族**。
那個族有數學上的答案——$\cos\frac{n\pi x}{L}$ 與 $\sin\frac{n\pi x}{L}$
對**分部積分封閉**：多項式每分部積分一次降一次，$k$ 次多項式做 $k+1$ 次必然終止，
邊界項落在 $x=\pm L$ 上而 $\cos n\pi = (-1)^n$、$\sin n\pi = 0$。
於是結果**永遠是「$n$ 的有理函數 × $(-1)^n$ 或常數」**。

所以這裡的族是：**分段多項式**（`Piece`），三個旋鈕是半週期 $L$、分段數、
每段的次數。這不是「一個夠用的選擇」，是**唯一一個能保證封閉的選擇**。

⚠️ **這個族結構上排除了 §2.10.4 最擔心的那個失敗模式**，見下面第四節第 1 點。

===========================================================================
三、$a_0$ 要不要除 2：**這是暫定值，而且只有一處可以改**（§7 #23）
===========================================================================

見本檔 `A0_IS_HALVED` 那一段。老師尚未拍板，附錄 C 暫定除 2。

===========================================================================
四、四層閘門（PLAN §2.10.4），以及落地時與規劃的落差
===========================================================================

> 落差**一共六處**，完整清單在 PLAN §2.10.4a。這裡只記其中四處——
> 剩下兩處（第三層的取樣點要自動算跳點、第二層要先做積化和差才算得出來）
> 的說明寫在它們各自的方法旁邊，因為那是改到它們的人會看到的地方。

四層由強到弱：`_gate_coefficients`（主閘門）、`_gate_parseval`、
`_gate_partial_sums`、`_gate_parity`。**四層不是保守，是因為沒有一層是充分的**：
第一層抓「某個 $n$ 算錯」，第二層抓「整組係數系統性偏掉」，第三層抓「延拓或
區間搞錯」，第四層抓「奇偶性標錯」。⛔ **日後覺得「這麼多層太慢了」而想拿掉
其中三層的人，要先說得出剩下那一層為什麼是充分的。**

**落差 1（最重要）：`Piecewise` 會出現，但它不是規劃擔心的那種失敗。**
規劃寫的是「SymPy 對 $\int\sin kx\sin nx$ 有時會回傳 `Piecewise`，生成端若不小心
會挑錯分支，變成一個假的封閉形式」。SymPy 1.14 實測（本輪）：

    ∫_{-π}^{π} sin(x)sin(nx) dx  →  Piecewise((0, Ne(n, 1)), (π, True))
    ∫_{-π}^{π} cos(x)cos(nx) dx  →  Piecewise((0, Ne(n, 1)), (π, True))

也就是說 **SymPy 是誠實的**——它沒有給出一個在 $n=1$ 悄悄失效的封閉形式，
它明說了那一格是特例。規劃害怕的「只錯一個 $n$」需要**我們自己**去挑分支
才會發生。因此這裡的處理是結構性的兩道：(a) 族限定為分段多項式，多項式與
三角基底**不可能同頻**，所以這個 `Piecewise` 在本族內根本不會出現；
(b) 仍然檢查，遇到 `Piecewise` 一律判定為「這組參數不合格」——它是給日後
擴族的人準備的網子，而 `test_a_resonant_f_is_rejected_instead_of_guessed`
餵一個真的會共振的 $f$ 證明那張網子是通的。

**落差 2：分母的正整數零點——這個族裡是空集合。**
規劃要求「把封閉形式的分母因式分解，取它的正整數零點主動去撞」。實作照做了
（`_denominator_probe_points`），但誠實的說明是：本族的分母永遠是
$\pi^k n^m$，唯一的零點是 $n=0$，而 $n=0$ 正是 $a_0$——它由第 1 層的
另一個分支單獨處理。**所以這個探測點集合在目前每一題上都是空的。**
留著它的理由是擴族（例如日後加 $e^{ax}$，分母變 $a^2+(n\pi/L)^2$），
而不是它現在擋住了什麼。

**落差 3：規劃的「$a_n(0) \ne a_0$」在奇函數上是錯的。**
規劃寫「要驗 `an_claim.subs(n, 0)` **不等於** $a_0$，否則第 4 步的教學說明
會變成一句假話」。這個要求對**奇函數是錯的**：奇函數的 $a_0 = 0$ 且
$a_n \equiv 0$，封閉形式在 $n=0$ **確實**成立，而那時第 4 步不該說
「不能把 $n=0$ 代進去」。所以落地成一個雙向的檢查（見 `_gate_coefficients`）：
封閉形式在 $n=0$ 有定義時**必須**等於 $a_0$，沒有定義時 $a_0$ **必須**單獨算，
而步驟 4 的說明由同一個旗標決定。這比規劃的版本強，因為它兩個方向都擋。

**落差 4：閘門一的積分改走「不定積分 + 代邊界」，而且有快取。**
規劃寫的是「先把 $n$ 代成具體整數，再積分」。落地時實測 `sp.integrate` 的
定積分路徑一次要 0.13–0.45 秒，五個探測點就是每題一秒以上，30 題 × 9 格
會讓整份測試多七分鐘——**而測試變慢真正的代價不是等，是有人開始不跑它**。
改成「對單項式 $x^d$ 算一次不定積分（module 級快取），再代上下限」之後，
熱快取下十個積分只要 0.007 秒。

⚠️ **這個改動有沒有削弱獨立性？沒有，而且在一個方向上更強了。** 關鍵的獨立性
來自「代入與積分的順序相反」（規劃的原話），而那一點完全保留；
新增的差異是「不定積分 + 代邊界」vs「定積分」，那是**兩條不同的 SymPy 程式路徑**，
也正好是學生手算時走的那一條。**還剩下的縫**：兩條路徑底下仍然是同一個
`sp.integrate`。要完全補掉它得自己手寫分部積分，而規則 1 說數學正確性只能
來自 SymPy——所以這個縫是刻意留著的，寫在這裡而不是說「閘門是獨立的」就算了。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import sympy as sp
from sympy.simplify.fu import TR8

from ...logging_setup import get_logger
from ..base import Step

logger = get_logger(__name__)

# --- 符號 ------------------------------------------------------------------
#
# ⚠️ 這裡有**兩顆都叫 `n` 的符號**，而它們刻意同名。
#
#   N_INT —— Symbol("n", integer=True, positive=True)：真正的指標。
#            `integer=True` 不是裝飾，沒有它 `cos(nπ)` 化簡不掉（附錄 C.4 明文，
#            本輪實測確認：`cos(Symbol("n")*pi)` 原樣不動）。
#   N_GEN —— Symbol("n", positive=True)：**只在組步驟時用**的替身。
#            assumptions 不同 → SymPy 視為不同的符號 → `cos(nπ)` 不會被化簡，
#            於是分部積分的結果可以印成「還帶著 cos nπ 與 sin nπ」的樣子，
#            也就是課本上「代邊界之後、用 cos nπ = (-1)^n 之前」的那一行。
#
# 同名是為了印出來都是 $n$。⛔ **兩者絕不可以在同一個表達式裡並存**——
# 那會得到一個印出來看起來只有一個 n、實際上是兩個自由變數的算式，
# 而它化簡不掉的症狀是「步驟裡多出一個沒有意義的項」。
# 本檔唯一容許它們相遇的地方是 `.subs(N_GEN, N_INT)`，而那一行永遠緊接在
# 產生 N_GEN 表達式的下一行。
x = sp.Symbol("x", real=True)
N_INT = sp.Symbol("n", integer=True, positive=True)
N_GEN = sp.Symbol("n", positive=True)


# --- §7 #23：$a_0$ 的慣例，**整個專案只有這一段可以改** ----------------------

#: 級數寫成 $\frac{a_0}{2} + \sum(\dots)$（True）還是 $a_0 + \sum(\dots)$（False）。
#:
#: ⚠️ **這是暫定值，老師尚未拍板（PLAN §7 #23、附錄 C.4 的那一格）。**
#: 兩種課本都有，差別只在 $a_0$ 的定義差一個因子 2。暫定除 2 的理由是它讓
#: $a_0$ 與 $a_n$ 共用同一條積分公式（$a_n = \frac1L\int f\cos\frac{n\pi x}{L}$，
#: $n \ge 0$），也才撐得起逐步解答第 4 步的教學說明。
#:
#: **改的成本在哪裡**：程式上就是這一個布林值，`a0_from_period_integral()`、
#: `constant_term()`、`a0_definition_latex()`、`series_head_latex()`、`a0_meaning_note()`
#: **五個**全部從它導出，所以改一個地方就會全部跟著改，**不會有漏網的一處**。
#: `test_the_a0_convention_lives_in_exactly_one_place` 會翻轉它並逐一確認——
#: ⛔ **加第六個導出量的時候要一起加進那一項測試**，它有一行斷言個數。
#: 真正的成本不在程式——**題目一旦印給學生看過，他們的筆記就對不上了**。
#: 所以這件事要在開課前決定，不是在學期中決定。
A0_IS_HALVED = True


def a0_from_period_integral(integral: sp.Expr, L: sp.Expr) -> sp.Expr:
    r"""由 $\int_{-L}^{L} f\,dx$ 得到 $a_0$。"""
    return integral / L if A0_IS_HALVED else integral / (2 * L)


def constant_term(a0: sp.Expr) -> sp.Expr:
    """級數裡的常數項（$a_0/2$ 或 $a_0$）。"""
    return a0 / 2 if A0_IS_HALVED else a0


def a0_definition_latex(L: sp.Expr) -> str:
    r"""$a_0$ 的定義式（不含左邊的 ``a_0 =``）。

    ⚠️ **$a_0$ 的前置因子與 $a_n$ 的必須一致**，那正是 `A0_IS_HALVED = True`
    這個選擇的全部內容：除 2 的慣例下兩者都是 $\frac1L$，於是第 3 步寫下的
    公式對 $n \ge 0$ 一體適用。不除 2 的話 $a_0$ 要用 $\frac{1}{2L}$，
    而那是這個函式唯一需要分支的地方。
    """
    LL = sp.latex(L)
    if A0_IS_HALVED:
        return r"%s\int_{-%s}^{%s} f(x)\,dx" % (over_L_latex(1, L), LL, LL)
    return r"\frac{1}{2%s}\int_{-%s}^{%s} f(x)\,dx" % (LL, LL, LL)


def series_head_latex() -> str:
    r"""級數的常數項要怎麼印。"""
    return r"\frac{a_0}{2}" if A0_IS_HALVED else "a_0"


def a0_meaning_note() -> str:
    """第 4 步裡解釋 $a_0$ 幾何意義的那一句（英文，介面語言）。"""
    if A0_IS_HALVED:
        return (
            "With this convention the constant term of the series is $a_0/2$, "
            "which is exactly the mean value of $f$ over one period. Writing it "
            "this way lets $a_0$ and $a_n$ share the same integral formula."
        )
    return (
        "With this convention $a_0$ is itself the mean value of $f$ over one "
        "period, and it needs its own integral formula."
    )


# --- 函數族：分段多項式 -----------------------------------------------------


@dataclass(frozen=True)
class Piece:
    """$f$ 在 $[lo, hi]$ 上的一段多項式。純資料，可 pickle（§2.2 的第 2 點）。"""

    poly: sp.Expr
    lo: sp.Expr
    hi: sp.Expr


@dataclass(frozen=True)
class PiecewiseFn:
    """定義在 $(-L, L)$ 上、以 $2L$ 為週期延拓的分段多項式。

    `pieces` 必須首尾相接地蓋滿 $[-L, L]$，由 `build()` 保證。
    端點上的值不影響任何一個 Fourier 係數（那是測度零的集合），
    所以這裡不為端點爭論——**但跳點的位置很重要**，見 `jump_points()`。
    """

    pieces: tuple[Piece, ...]
    half_period: sp.Expr

    # -- 建構 --------------------------------------------------------------

    @staticmethod
    def build(raw: list[tuple[sp.Expr, sp.Expr, sp.Expr]], L: sp.Expr) -> "PiecewiseFn":
        pieces = tuple(Piece(sp.sympify(f), sp.sympify(lo), sp.sympify(hi))
                       for f, lo, hi in raw)
        assert pieces[0].lo == -L and pieces[-1].hi == L, "分段必須蓋滿 [-L, L]"
        for a, b in zip(pieces, pieces[1:]):
            assert a.hi == b.lo, "分段必須首尾相接"
        return PiecewiseFn(pieces, sp.sympify(L))

    # -- 基本查詢 ----------------------------------------------------------

    def poly_on(self, a: sp.Expr, b: sp.Expr) -> sp.Expr:
        """蓋住開區間 $(a,b)$ 的那一段多項式。"""
        for p in self.pieces:
            if p.lo <= a and b <= p.hi:
                return p.poly
        raise ValueError(f"({a}, {b}) 不落在任何一段裡")

    def value_at(self, xv: float) -> float:
        """數值求值（週期延拓）。只給第三層閘門用。"""
        L = float(self.half_period)
        v = xv
        while v >= L:
            v -= 2 * L
        while v < -L:
            v += 2 * L
        for p in self.pieces:
            if float(p.lo) <= v <= float(p.hi):
                return float(p.poly.subs(x, sp.Float(v)))
        raise ValueError(f"x={xv} 落在定義域外")

    def jump_points(self) -> tuple[sp.Expr, ...]:
        r"""所有不連續點（含週期延拓在 $\pm L$ 造成的那一個）。

        ⚠️ **這件事一定要算，不能由呼叫端手寫。** 本輪實測時就是因為手寫的
        清單漏掉了「兩段在 $x=0$ 接不上」那個跳點，第三層閘門立刻把一題
        完全正確的題目擋了下來——**而擋下來還算是好的失敗方向**。
        反過來（把一個真的跳點漏掉）的症狀是取樣點踩在 Gibbs 過衝裡，
        於是閘門開始擋正確的題目，而看起來像是「係數算錯了」。
        """
        L = self.half_period
        jumps: list[sp.Expr] = []
        for a, b in zip(self.pieces, self.pieces[1:]):
            if sp.simplify(a.poly.subs(x, a.hi) - b.poly.subs(x, b.lo)) != 0:
                jumps.append(a.hi)
        # 週期延拓：右端點接回左端點
        left = self.pieces[0].poly.subs(x, -L)
        right = self.pieces[-1].poly.subs(x, L)
        if sp.simplify(right - left) != 0:
            jumps.extend([-L, L])
        return tuple(jumps)

    @property
    def has_jump(self) -> bool:
        return bool(self.jump_points())

    def peak(self) -> sp.Expr:
        r"""$\max|f|$（取在各段端點與駐點上）。第三層閘門的容忍度按它縮放。"""
        best = sp.Integer(0)
        for p in self.pieces:
            candidates = [p.lo, p.hi]
            crit = sp.solve(sp.diff(p.poly, x), x)
            candidates += [c for c in crit if c.is_real and p.lo <= c <= p.hi]
            for c in candidates:
                best = sp.Max(best, abs(p.poly.subs(x, c)))
        return sp.nsimplify(sp.simplify(best))

    # -- 奇偶性 ------------------------------------------------------------

    def _breakpoints(self, other: "PiecewiseFn") -> list[sp.Expr]:
        pts = {p.lo for p in self.pieces} | {p.hi for p in self.pieces}
        pts |= {p.lo for p in other.pieces} | {p.hi for p in other.pieces}
        return sorted(pts, key=lambda e: float(e))

    def equals(self, other: "PiecewiseFn") -> bool:
        """兩個分段函數是否**逐段相等**（端點的值不算）。"""
        pts = self._breakpoints(other)
        for a, b in zip(pts, pts[1:]):
            if sp.expand(self.poly_on(a, b) - other.poly_on(a, b)) != 0:
                return False
        return True

    def reflected(self) -> "PiecewiseFn":
        r"""$f(-x)$。"""
        pieces = tuple(Piece(p.poly.subs(x, -x), -p.hi, -p.lo)
                       for p in reversed(self.pieces))
        return PiecewiseFn(pieces, self.half_period)

    def negated(self) -> "PiecewiseFn":
        r"""$-f(x)$。"""
        return PiecewiseFn(tuple(Piece(-p.poly, p.lo, p.hi) for p in self.pieces),
                           self.half_period)

    def parity(self) -> str:
        """``"even"`` / ``"odd"`` / ``"none"``，**符號上**判定，不是取樣。"""
        mirror = self.reflected()
        if self.equals(mirror):
            return "even"
        if self.negated().equals(mirror):
            return "odd"
        return "none"

    # -- 排版 --------------------------------------------------------------

    def cases_latex(self) -> str:
        r"""$f(x) = \begin{cases}\dots\end{cases}$ 的右半邊。

        ⚠️ KaTeX 0.16.11（本專案自架的那一份）**支援 `cases`**——本輪用 node
        載入 `app/static/vendor/katex/katex.min.js` 實際渲染確認過，
        `tests/test_generators.py::test_every_formula_renders_in_the_bundled_katex`
        會在每次測試時重新確認一次。
        """
        rows = []
        for p in self.pieces:
            rows.append(r"%s, & %s < x < %s" % (
                sp.latex(p.poly), sp.latex(p.lo), sp.latex(p.hi)))
        if len(rows) == 1:
            p = self.pieces[0]
            return r"%s, \quad %s < x < %s" % (
                sp.latex(p.poly), sp.latex(p.lo), sp.latex(p.hi))
        return r"\begin{cases} " + r" \\ ".join(rows) + r" \end{cases}"


# --- 生成路徑：對符號 n 積分 -------------------------------------------------


@dataclass(frozen=True)
class Coefficients:
    """一組宣稱的係數。`a_n` / `b_n` 是**對 `N_INT` 的封閉形式**。"""

    a0: sp.Expr
    an: sp.Expr
    bn: sp.Expr
    #: 分部積分之後、用 $\cos n\pi = (-1)^n$ 之前的樣子（含 `N_GEN`）。只供步驟顯示。
    an_raw: sp.Expr = field(default=sp.Integer(0), repr=False)
    bn_raw: sp.Expr = field(default=sp.Integer(0), repr=False)


class ResonantIntegral(RuntimeError):
    """積分回傳了 `Piecewise` —— 這組參數不合格，重抽（見檔頭落差 1）。"""


def _tidy(expr: sp.Expr) -> sp.Expr:
    r"""把係數收成課本會寫的樣子：**按 $n$ 的冪次分組，每一組各自化簡**。

    為什麼不直接用 `sp.simplify`：它會把不同冪次硬湊成一個分式，例如

        2(-4(-1)^n + π²n²(2(-1)^n + 1) + 4) / (π³n³)

    每一個字元都對，但沒有課本會這樣寫，而學生要從它看出「$1/n$ 那一項」
    與「$1/n^3$ 那一項」得先自己拆回去。分組之後同一個係數是

        2(2(-1)^n + 1)/(πn) + 8(1 - (-1)^n)/(π³n³)

    ——兩項的衰減速度一眼看得出來，而那正是這個題型要教的事情之一。
    """
    expr = sp.expand(expr)
    if expr == 0:
        return sp.Integer(0)
    groups: dict[int, sp.Expr] = {}
    for term in sp.Add.make_args(expr):
        denominator = sp.denom(sp.together(term))
        degree = sp.Poly(denominator, N_INT).degree() if denominator.has(N_INT) else 0
        groups[degree] = groups.get(degree, sp.Integer(0)) + term
    return sp.Add(*(sp.simplify(groups[k]) for k in sorted(groups)))


#: 生成路徑的單項式定積分快取，鍵是 (次數, 下限, 上限, L, cos/sin)。
#:
#: ⚠️ **這是效能措施，不是「聰明的化簡」。** 它做的只有兩件事：把每一段多項式
#: 按線性拆成單項式（$\int (3x^2 - 1)\cos = 3\int x^2\cos - \int\cos$），
#: 以及記住算過的結果。**走的仍然是符號 $n$ 的定積分**，也就是閘門要去對照的
#: 那一條路——⛔ 不可以為了再快一點而改成「不定積分 + 代邊界」，
#: 那會讓生成路徑與閘門路徑合流，交叉驗證就不成立了（見檔頭「落差 4」）。
#:
#: 命中率高的原因是上下限只有 $\{\pm L, 0, \pm L/2\}$ 幾種、次數只到 3、
#: $L$ 只有三個值，所以整份測試跑完大約只會真的積幾十次。
_GENERIC_DEFINITE: dict[tuple, sp.Expr] = {}


def _definite_monomial(degree: int, lo: sp.Expr, hi: sp.Expr,
                       L: sp.Expr, kind: str) -> sp.Expr:
    r"""$\int_{lo}^{hi} x^{d}\cos\frac{n\pi x}{L}dx$（或 $\sin$），對**符號 $n$**。"""
    key = (degree, sp.srepr(lo), sp.srepr(hi), sp.srepr(L), kind)
    if key not in _GENERIC_DEFINITE:
        basis = (sp.cos if kind == "cos" else sp.sin)(N_GEN * sp.pi * x / L)
        _GENERIC_DEFINITE[key] = sp.integrate(x**degree * basis, (x, lo, hi))
    return _GENERIC_DEFINITE[key]


def _integrate_over(fn: PiecewiseFn, kind: str) -> sp.Expr:
    """$\\frac1L\\sum_i \\int f_i \\cdot \\text{basis}$。回傳未化簡的結果。

    ⚠️ **非多項式的一段走沒有快取的整段積分，不是拋例外。** 這一條在目前的
    函數族上一次都不會執行到（族就是分段多項式），而它是本輪一個真的踩到的坑：
    加上單項式拆解的快取之後，`sp.Poly` 在 `sin(x)` 上直接丟 `PolynomialError`，
    於是 `coefficients_of()` 那張「遇到 `Piecewise` 就重抽」的網子**變成不可達**
    ——而那張網子的**唯一用途**就是保護日後擴到非多項式的族。
    症狀是測試紅燈，所以這一次被抓到了；但同一個改動若發生在沒有那項測試的
    地方，這裡會安靜地變成一段死碼。
    """
    total = sp.Integer(0)
    for p in fn.pieces:
        basis = (sp.cos if kind == "cos" else sp.sin)(N_GEN * sp.pi * x / fn.half_period)
        try:
            terms = sp.Poly(sp.expand(p.poly), x).terms()
        except sp.PolynomialError:
            total += sp.integrate(p.poly * basis, (x, p.lo, p.hi))
            continue
        for (degree,), coeff in terms:
            total += coeff * _definite_monomial(degree, p.lo, p.hi,
                                                fn.half_period, kind)
    return total / fn.half_period


def coefficients_of(fn: PiecewiseFn) -> Coefficients:
    r"""**生成路徑**：先對符號 $n$ 積分，再得封閉形式。

    ⚠️ 這是閘門要去對照的那一條路，所以它**刻意寫得很直接**——照定義積分，
    不做任何「聰明」的化簡或特例分支。任何在這裡加的捷徑都會削弱閘門。
    """
    L = fn.half_period
    a0 = sp.simplify(a0_from_period_integral(
        sum(sp.integrate(p.poly, (x, p.lo, p.hi)) for p in fn.pieces), L))

    an_raw = _integrate_over(fn, "cos")
    bn_raw = _integrate_over(fn, "sin")
    for raw in (an_raw, bn_raw):
        if raw.has(sp.Piecewise):
            # 見檔頭「落差 1」。**不要試著自己挑分支**——挑錯的症狀正是
            # 「只錯一個 n」，而那種題目印出來完全正常。
            raise ResonantIntegral(f"係數積分回傳 Piecewise：{raw}")

    an = _tidy(an_raw.subs(N_GEN, N_INT))
    bn = _tidy(bn_raw.subs(N_GEN, N_INT))
    return Coefficients(a0=a0, an=an, bn=bn,
                        an_raw=sp.simplify(an_raw), bn_raw=sp.simplify(bn_raw))


# --- 閘門路徑：先代入具體 n，再積分 -----------------------------------------
#
# 這裡的快取是 module 級的，鍵是 (單項式次數, 具體的 n, L, cos/sin)。
# 熱快取之後一次閘門只剩下代上下限的有理數運算（實測 0.007 秒 / 10 個積分）。
# ⚠️ **快取的是不定積分，不是題目的答案**——它與任何一題的參數無關，
# 所以共用不會讓兩題互相汙染。

_ANTIDERIVATIVE: dict[tuple, sp.Expr] = {}


def _antiderivative(degree: int, k: int, L: sp.Expr, kind: str) -> sp.Expr:
    r"""$\int x^{d}\cos\frac{k\pi x}{L}dx$（或 $\sin$），對**具體的整數 $k$**。"""
    key = (degree, k, sp.srepr(L), kind)
    if key not in _ANTIDERIVATIVE:
        basis = (sp.cos if kind == "cos" else sp.sin)(k * sp.pi * x / L)
        _ANTIDERIVATIVE[key] = sp.integrate(x**degree * basis, x)
    return _ANTIDERIVATIVE[key]


def coefficient_by_probe(fn: PiecewiseFn, k: int, kind: str) -> sp.Expr:
    r"""**閘門路徑**：把 $n$ 代成具體整數 $k$ 之後才積分。

    與 `coefficients_of()` 在三件事上不同，而第一件是關鍵：

    1. **代入與積分的順序相反**（規劃 §2.10.4 的核心）。
    2. 走的是「不定積分 + 代上下限」而不是定積分——那是學生手算的那條路。
    3. 逐單項式做，而不是把整段多項式丟給 SymPy。
    """
    L = fn.half_period
    total = sp.Integer(0)
    for p in fn.pieces:
        poly = sp.Poly(sp.expand(p.poly), x)
        for (degree,), coeff in poly.terms():
            F = _antiderivative(degree, k, L, kind)
            total += coeff * (F.subs(x, p.hi) - F.subs(x, p.lo))
    return sp.expand(total / L)


#: Parseval 級數的結果快取，鍵是**去掉有理係數之後的項形狀**。
#:
#: 這一層是本輪唯一一個為了速度而做的非顯然決定，所以理由寫清楚：
#: 直接對整個 $a_n^2 + b_n^2$ 呼叫 `Sum(...).doit()` 實測是這個題型最貴的一步
#: （八題 31.6 秒裡佔 19.5 秒，SymPy 走的是 `telescopic` + `solve` 那條通用路徑）。
#: **逐項相加之後每一項的形狀重複率極高**——只有 $1/n^2$、$(-1)^n/n^2$、
#: $1/n^4$、$(-1)^n/n^4$、$1/n^6$ 這幾種在輪流出現，變的只是前面的有理係數。
#:
#: ⚠️ **逐項相加改變的只有結合順序，不是數學**：級數絕對收斂（分母至少是 $n^2$
#: 而分子有界），所以重排與拆項都是合法的。⛔ 若日後把函數族擴到係數只衰減
#: 成 $1/n$ 的東西（例如帶 $\delta$ 的形式解），這個前提就不成立了——
#: 那時要回頭改這裡，而不是「反正一直都這樣算」。
_SUM_CACHE: dict[str, sp.Expr] = {}


def _sum_one_shape(shape: sp.Expr) -> sp.Expr:
    key = sp.srepr(shape)
    if key not in _SUM_CACHE:
        _SUM_CACHE[key] = sp.Sum(shape, (N_INT, 1, sp.oo)).doit()
    return _SUM_CACHE[key]


def _closed_form_sum(summand: sp.Expr) -> sp.Expr:
    r"""$\sum_{n=1}^{\infty}$ 的封閉形式；任何一項算不出來就回傳一個未計算的 `Sum`。

    回傳值裡若還有 `Sum`，呼叫端**必須明示地跳過那一層並記 log**（規則 4），
    不可以當作通過。
    """
    # ⚠️ **TR8（積化和差）不是修飾，它決定了這一層跑不跑得起來。**
    # 難度 3 的係數含 $\sin\frac{n\pi}{2}$，而 `Sum(...).doit()` 對
    # $\sin^2\frac{n\pi}{2}/n^4$ 原樣退回（實測）。TR8 把它降冪成
    # $\frac{1 - \cos n\pi}{2} = \frac{1 - (-1)^n}{2}$——後半段成立**正是因為
    # $n$ 帶著 `integer=True`**（附錄 C.4 那條 assumptions 的規定在這裡第二次兌現）。
    # 交叉項 $\sin\frac{n\pi}{2}\cos\frac{n\pi}{2}$ 同樣化成 $\frac{\sin n\pi}{2} = 0$。
    # 兩個都是恆等變形，不是近似。
    #
    # 實測的效果（30 樣本 × 6 格裡取 15 題／格）：**沒有這一行是 15/90 跳過**，
    # 全部集中在難度 3；**有了它是 7/90**，而剩下的 7 個全部來自
    # `half_range` 難度 3。那 7 個的原因與 TR8 無關，也不是它補得到的：
    # 半幅斷點在 $L/2$ 的係數平方會生出 $(-1)^n\cos\frac{n\pi}{2}$ 這種
    # **不是兩個三角函數相乘**的交叉項，積化和差對它沒有作用，
    # 而 SymPy 對 $\sum \cos\frac{n\pi}{2}/n^2$ 本來就給不出封閉形。
    # ⚠️ 那 7 題因此只有三層閘門——這件事記在 §6 的驗收數字裡，
    # 而不是靠「大部分都有跑」帶過去。
    summand = sp.expand(TR8(sp.expand(summand)))
    total = sp.Integer(0)
    for term in sp.Add.make_args(sp.powsimp(summand, force=False)):
        coefficient, shape = term.as_coeff_Mul()
        value = _sum_one_shape(shape)
        if value.has(sp.Sum):
            return sp.Sum(summand, (N_INT, 1, sp.oo))
        total += coefficient * value
    return total


def _denominator_probe_points(expr: sp.Expr, limit: int = 40) -> list[int]:
    r"""封閉形式分母的正整數零點——**閘門要主動去踩它自己最可能出錯的地方**。

    ⚠️ **在目前的函數族上這個集合永遠是空的**（分母是 $\pi^k n^m$，唯一的零點
    是 $n=0$，而 $n=0$ 由 $a_0$ 那一支單獨處理）。留著它是為了擴族——
    誠實的說明見檔頭「落差 2」。
    """
    if expr == 0:
        return []
    denominator = sp.denom(sp.together(expr))
    if not denominator.has(N_INT):
        return []
    try:
        poly = sp.Poly(denominator, N_INT)
    except sp.PolynomialError:
        logger.info("分母不是 n 的多項式，跳過零點探測：%s", denominator)
        return []
    roots = [r for r in sp.real_roots(poly) if r.is_Integer and 0 < int(r) <= limit]
    return sorted({int(r) for r in roots})


# --- 四層閘門 ---------------------------------------------------------------


@dataclass(frozen=True)
class FourierCheck:
    r"""Fourier 題型的驗證閘門（`Verifier` 協定的實作）。

    ⛔ **四層都要跑，而且每一層擋的東西不一樣。** 完整論證見本檔檔頭第四節。
    這裡只重複最重要的一句：**沒有任何單一一層是充分的**，所以「這麼多層太慢了」
    不是一個可以自己下的結論。

    純資料、frozen、不含 lambda —— 與 `Check` 相同的理由（§2.2 第 2 點）。
    """

    fn: PiecewiseFn
    coefficients: Coefficients
    parity: str                      # "even" | "odd" | "none"
    #: 這一題宣稱「$a_0$ 必須單獨算」（封閉形式在 $n=0$ 沒有定義）還是不必。
    a0_needs_separate_formula: bool
    #: 固定探測點。加上分母零點與一個由 seed 決定的隨機點，見 `probe_points()`。
    fixed_probes: tuple[int, ...] = (1, 2, 3, 4, 5)
    random_probe: int = 7
    partial_sum_terms: int = 60
    #: 取樣點要離每一個跳點多遠（以 $L$ 為單位）。理由見 `_gate_partial_sums`。
    jump_clearance: sp.Rational = sp.Rational(1, 4)

    # -- 對外 --------------------------------------------------------------

    def probe_points(self) -> list[int]:
        points = set(self.fixed_probes) | {self.random_probe}
        for claim in (self.coefficients.an, self.coefficients.bn):
            points |= set(_denominator_probe_points(claim))
        return sorted(points)

    def verify(self, problem) -> tuple[bool, str]:
        for gate in (self._gate_coefficients, self._gate_parity,
                     self._gate_parseval, self._gate_partial_sums):
            ok, reason = gate()
            if not ok:
                return False, reason
        return True, ""

    # -- 第一層：交叉驗證係數（主閘門，必過）------------------------------

    def _gate_coefficients(self) -> tuple[bool, str]:
        c = self.coefficients
        for k in self.probe_points():
            for claim, kind, name in ((c.an, "cos", "a"), (c.bn, "sin", "b")):
                reference = coefficient_by_probe(self.fn, k, kind)
                if sp.simplify(claim.subs(N_INT, k) - reference) != 0:
                    return False, (
                        f"閘門一：{name}_n 在 n={k} 對不上"
                        f"（封閉形式 {sp.simplify(claim.subs(N_INT, k))}，"
                        f"獨立路徑 {sp.simplify(reference)}）"
                    )

        # a_0 單獨驗：它是 n=0，而封閉形式在那裡通常沒有定義。
        reference_a0 = a0_from_period_integral(
            sum(sp.integrate(p.poly, (x, p.lo, p.hi)) for p in self.fn.pieces),
            self.fn.half_period)
        if sp.simplify(c.a0 - reference_a0) != 0:
            return False, f"閘門一：a_0 對不上（{c.a0} vs {sp.simplify(reference_a0)})"

        # 見檔頭「落差 3」：規劃只要求「不等於」，那在奇函數上是錯的。
        # 這裡兩個方向都擋，而步驟 4 的說明由同一個旗標決定。
        at_zero = c.an.subs(N_INT, 0)
        defined = at_zero.is_finite is not False and not at_zero.has(sp.zoo, sp.nan)
        if defined and self.a0_needs_separate_formula:
            return False, (
                f"閘門一：宣稱 a_0 要單獨算，但 a_n 的封閉形式在 n=0 有定義（={at_zero}）"
            )
        if not defined and not self.a0_needs_separate_formula:
            return False, "閘門一：宣稱 a_n 的封閉形式在 n=0 也成立，但它在那裡沒有定義"
        if defined and sp.simplify(at_zero - c.a0) != 0:
            return False, (
                f"閘門一：a_n 的封閉形式在 n=0 有定義卻不等於 a_0"
                f"（{sp.simplify(at_zero)} vs {c.a0}）"
            )
        return True, ""

    # -- 第二層：Parseval（獨立路徑）--------------------------------------

    def _gate_parseval(self) -> tuple[bool, str]:
        r"""$\frac1L\int_{-L}^{L} f^2 = \frac{a_0^2}{2} + \sum (a_n^2 + b_n^2)$。

        這一層與係數的積分**完全獨立**，所以價值很高。但級數不是每一組參數
        都收得出封閉形式（實測：係數含 $\sin\frac{n\pi}{2}$ 時 `doit()` 原樣退回）。

        ⚠️ **收不出來時跳過，而且要記一行 log**——規則 4 的「不做無聲降級」在這裡
        的意思是：一個本來會被 Parseval 擋下的錯誤，不可以因為級數剛好算不出來
        就安靜地通過。跳過的比例是 §6 驗收標準要記錄的數字之一
        （跳太多代表函數族選得不好，**不代表沒問題**）。
        """
        c = self.coefficients
        L = self.fn.half_period
        left = sp.simplify(
            sum(sp.integrate(p.poly**2, (x, p.lo, p.hi)) for p in self.fn.pieces) / L)
        series = _closed_form_sum(sp.expand(c.an**2 + c.bn**2))
        if series.has(sp.Sum):
            logger.info(
                "閘門二（Parseval）跳過：級數收不出封閉形式。a_n=%s, b_n=%s", c.an, c.bn)
            return True, ""
        residual = sp.simplify(left - c.a0**2 / 2 - series)
        if residual != 0:
            return False, f"閘門二：Parseval 不成立，差 {residual}"
        return True, ""

    # -- 第三層：部分和的數值反證（只准反證）------------------------------

    def _gate_partial_sums(self) -> tuple[bool, str]:
        r"""部分和與 $f$ 在若干連續點上比對。**只能否決，不能背書**（D9 的方向性）。

        兩個非做不可的特判，否則這一層會**把正確的題目擋下來**：

        - **跳點上級數收斂到左右極限的平均**，不是 $f$ 的值 → 取樣點避開跳點。
        - **Gibbs 現象**：跳點鄰域的過衝約 9%，而且**加再多項也不會消失**
          （它只會往跳點靠近）→ 取樣點要離跳點 $\ge L/4$。

        容忍度**按 $\max|f|$ 縮放**，不是一個固定的數字：要抓的錯誤
        （延拓寫錯、區間搞錯、少一段）都會造成 $O(\max|f|)$ 的偏離，
        而部分和本身的截斷誤差也隨振幅等比例放大。固定容忍度的話，
        振幅小的題目擋得太鬆、振幅大的題目擋掉正確答案。
        """
        c = self.coefficients
        L = float(self.fn.half_period)
        N = self.partial_sum_terms
        a_of = sp.lambdify(N_INT, c.an, "math")
        b_of = sp.lambdify(N_INT, c.bn, "math")
        A = [float(a_of(k)) for k in range(1, N + 1)]
        B = [float(b_of(k)) for k in range(1, N + 1)]
        const = float(constant_term(c.a0))

        def partial_sum(v: float) -> float:
            total = const
            for k in range(1, N + 1):
                total += (A[k - 1] * math.cos(k * math.pi * v / L)
                          + B[k - 1] * math.sin(k * math.pi * v / L))
            return total

        jumps = [float(j) for j in self.fn.jump_points()]
        clearance = float(self.jump_clearance) * L
        samples = []
        # 37 是刻意的奇數且與 2、3、4 互質：格點才不會系統性地踩在 L/2、L/3
        # 這些「剛好是斷點」的位置上，那會讓取樣點被排除得特別多。
        step = 2 * L / 37
        v = -L + step / 2
        while v < L:
            if all(abs(v - j) >= clearance for j in jumps):
                samples.append(v)
            v += step
        if len(samples) < 4:
            return False, (
                f"閘門三：離跳點 {clearance:.3f} 以外只剩 {len(samples)} 個取樣點，"
                "這個函數族的跳點太密，第三層失去意義"
            )

        scale = max(1.0, float(self.fn.peak()))
        tolerance = 0.06 * scale
        for v in samples:
            error = abs(partial_sum(v) - self.fn.value_at(v))
            if error > tolerance:
                return False, (
                    f"閘門三：x={v:.4f} 部分和 {partial_sum(v):.5f} 與 "
                    f"f={self.fn.value_at(v):.5f} 差 {error:.5f} > {tolerance:.5f}"
                )
        return True, ""

    # -- 第四層：宣稱的奇偶性要在符號上成立 --------------------------------

    def _gate_parity(self) -> tuple[bool, str]:
        r"""便宜到近乎免費，而它擋的是**延拓寫錯**這一類最容易發生的生成端 bug。

        ⚠️ 這裡驗的是**符號上**恆為 0，不是取樣為 0——後者對
        $a_n = \frac{2((-1)^n - 1)}{\pi n^2}$ 這種在偶數 $n$ 上剛好為 0 的
        係數會給出錯的結論。
        """
        actual = self.fn.parity()
        if actual != self.parity:
            return False, f"閘門四：宣稱 f 是 {self.parity}，實際上是 {actual}"
        c = self.coefficients
        if self.parity == "odd" and (c.an != 0 or c.a0 != 0):
            return False, f"閘門四：f 是奇函數，但 a_0={c.a0}、a_n={c.an} 不為 0"
        if self.parity == "even" and c.bn != 0:
            return False, f"閘門四：f 是偶函數，但 b_n={c.bn} 不為 0"
        return True, ""


# --- 排版與步驟 -------------------------------------------------------------


def basis_latex(L: sp.Expr, kind: str, index: str = "n") -> str:
    r"""$\cos\frac{n\pi x}{L}$ / $\sin\frac{n\pi x}{L}$，$L=\pi$ 時收成 $\cos nx$。"""
    if L == sp.pi:
        argument = "%s x" % index
    elif L == 1:
        argument = r"%s\pi x" % index
    else:
        argument = r"\frac{%s\pi x}{%s}" % (index, sp.latex(L))
    return r"\%s %s" % (kind, argument) if L == sp.pi else r"\%s\left(%s\right)" % (
        kind, argument)


def over_L_latex(numerator: int, L: sp.Expr) -> str:
    r"""$\frac{k}{L}$，但 $L = 1$ 時收成 ``k``（$k=1$ 時收成空字串）。

    存在的理由很小但很具體：$L = 1$ 的題目會印出 $\frac{1}{1}\int_{-1}^{1}\dots$，
    每一個字元都對，而學生看到的是「這個系統連 1/1 都沒有約掉」。
    §2.9 講的就是這一類——不會壞掉任何東西，只會讓人不信任畫面上的其他數字。
    """
    if L == 1:
        return "" if numerator == 1 else str(numerator)
    return r"\frac{%d}{%s}" % (numerator, sp.latex(L))


def series_latex(L: sp.Expr, has_a: bool, has_b: bool) -> str:
    r"""級數的一般式（$f(x) \sim \frac{a_0}{2} + \sum(\dots)$），照附錄 C.4。"""
    terms = []
    if has_a:
        terms.append("a_n %s" % basis_latex(L, "cos"))
    if has_b:
        terms.append("b_n %s" % basis_latex(L, "sin"))
    body = " + ".join(terms)
    head = series_head_latex() + " + " if has_a else ""
    if has_a and has_b:
        body = r"\left(%s\right)" % body
    return r"f(x) \sim %s\sum_{n=1}^{\infty} %s" % (head, body)


def coefficient_formula_latex(L: sp.Expr, kind: str) -> str:
    r"""$a_n = \frac1L\int_{-L}^{L} f(x)\cos\frac{n\pi x}{L}dx$。"""
    LL = sp.latex(L)
    return r"%s\int_{-%s}^{%s} f(x)\,%s\,dx" % (
        over_L_latex(1, L), LL, LL, basis_latex(L, kind))


def parity_note(parity: str) -> str:
    """第 2 步的 `note`——PLAN §2.10.3 說這是本題型最重要的一句解說。"""
    if parity == "odd":
        return (
            "Do this first, before computing anything. $f$ is odd, so "
            "$f(x)\\cos\\frac{n\\pi x}{L}$ is odd and integrates to zero over a "
            "symmetric interval. Every $a_n$ vanishes, and half of the work "
            "disappears before it starts."
        )
    if parity == "even":
        return (
            "Do this first, before computing anything. $f$ is even, so "
            "$f(x)\\sin\\frac{n\\pi x}{L}$ is odd and integrates to zero over a "
            "symmetric interval. Every $b_n$ vanishes, and half of the work "
            "disappears before it starts."
        )
    return (
        "Do this first, even when the answer is \"neither\". $f$ is neither even "
        "nor odd here, so no family of coefficients is free — but knowing that "
        "is what tells you that both integrals really have to be done."
    )


def _integral_split_latex(fn: PiecewiseFn, kind: str) -> str:
    """把 $\\int_{-L}^{L}$ 拆成各段的和；只有一段時不拆。"""
    parts = []
    for p in fn.pieces:
        parts.append(r"\int_{%s}^{%s} \left(%s\right) %s\,dx" % (
            sp.latex(p.lo), sp.latex(p.hi), sp.latex(p.poly),
            basis_latex(fn.half_period, kind)))
    joined = " + ".join(parts)
    if len(parts) > 1:
        joined = r"\left[ %s \right]" % joined
    return r"%s%s" % (over_L_latex(1, fn.half_period), joined)


def coefficient_steps(fn: PiecewiseFn, c: Coefficients, kind: str,
                      setup_latex: str | None = None) -> list[Step]:
    r"""$a_n$（或 $b_n$）的兩步：**列式並分部積分** → **用 $\cos n\pi = (-1)^n$ 化簡**。

    第二步為什麼值得單獨一步：$(-1)^n$ 是這個題型最常被學生問「從哪裡冒出來的」
    的東西，而它冒出來的位置就是這一行。把它併進上一步，那個瞬間就看不見了。

    ⚠️ 第一步印的**不是** `sp.integrate` 對整數 $n$ 的結果——那個結果裡
    $\cos n\pi$ 已經被化簡掉了，於是第二步會變成一句空話。這裡印的是用
    `N_GEN`（沒有 `integer=True` 的同名替身）算出來的版本，
    $\cos n\pi$ 與 $\sin n\pi$ 都還在。

    `setup_latex` 讓半幅展開換掉「$\frac1L\int_{-L}^{L}$」那一段——半幅的
    課本寫法是 $\frac2L\int_0^L$，而**兩者的值相同不代表可以印錯一個**：
    學生手上只有 $(0, L)$ 上的 $f$，印一個從 $-L$ 開始的積分等於要他去積
    一段題目沒有給的東西。
    """
    name = "a_n" if kind == "cos" else "b_n"
    raw = c.an_raw if kind == "cos" else c.bn_raw
    final = c.an if kind == "cos" else c.bn
    degree = max(sp.Poly(sp.expand(p.poly), x).degree() for p in fn.pieces)
    by_parts = (
        "The integrand is a polynomial times a trigonometric function, so "
        f"integration by parts terminates: each round lowers the degree by one, "
        f"and degree {degree} needs {degree + 1} of them. Take $u$ to be the "
        "polynomial factor and $dv$ to be the trigonometric factor."
    )
    setup = setup_latex if setup_latex is not None else _integral_split_latex(fn, kind)
    return [
        Step(
            f"Set up ${name}$ and integrate by parts",
            r"%s = %s = %s" % (name, setup, sp.latex(raw)),
            by_parts,
        ),
        Step(
            f"Simplify ${name}$ using $\\cos n\\pi = (-1)^n$",
            r"%s = %s" % (name, sp.latex(final)),
            "The boundary terms are evaluated at $x = \\pm L$, where the "
            "arguments become integer multiples of $\\pi$. That is where "
            "$\\cos n\\pi = (-1)^n$ and $\\sin n\\pi = 0$ enter, and it is the "
            "only place they can enter.",
        ),
    ]


def vanishing_step(parity: str) -> Step:
    """奇偶性讓一整族係數消失時，用一步交代它——而不是讓它悄悄不見。"""
    if parity == "odd":
        return Step(
            "All $a_n$ vanish by symmetry",
            r"a_0 = 0, \qquad a_n = 0 \quad (n \ge 1)",
            "No integral is needed here: $f$ is odd and $\\cos\\frac{n\\pi x}{L}$ "
            "is even, so their product is odd and integrates to zero over "
            "$[-L, L]$.",
        )
    return Step(
        "All $b_n$ vanish by symmetry",
        r"b_n = 0 \quad (n \ge 1)",
        "No integral is needed here: $f$ is even and $\\sin\\frac{n\\pi x}{L}$ "
        "is odd, so their product is odd and integrates to zero over $[-L, L]$.",
    )


def a0_step(fn: PiecewiseFn, c: Coefficients, needs_separate: bool,
            formula_latex: str | None = None) -> Step:
    r"""第 4 步：$a_0$ 單獨算。**`note` 由 `needs_separate` 決定，不是寫死的。**

    寫死的話會在奇函數上說一句假話：那時 $a_n \equiv 0$ 的封閉形式在 $n=0$
    **確實**成立（見檔頭「落差 3」）。閘門一會把兩個方向都擋下來，
    所以這個旗標與現實一致是有測試保證的。
    """
    L = fn.half_period
    if needs_separate:
        why = (
            "This one cannot be obtained by putting $n = 0$ into the formula for "
            "$a_n$: that closed form has $n$ in its denominator, so $n = 0$ is "
            "exactly the point where it stops being valid. "
        )
    else:
        why = (
            "Here the closed form for $a_n$ happens to remain valid at $n = 0$, "
            "because it has no $n$ in a denominator. That is a property of this "
            "particular $f$, not a general rule — usually $a_0$ must be computed "
            "on its own. "
        )
    formula = formula_latex if formula_latex is not None else a0_definition_latex(L)
    return Step(
        "Compute $a_0$ on its own",
        r"a_0 = %s = %s" % (formula, sp.latex(c.a0)),
        why + a0_meaning_note(),
    )


def assembly_step(fn: PiecewiseFn, c: Coefficients, answer_latex: str) -> Step:
    """最後一步：組裝級數，並在有跳點時說明收斂到中點。"""
    if fn.has_jump:
        note = (
            "The symbol $\\sim$ is not an equals sign. At a point of "
            "discontinuity the series converges to the average of the "
            "left-hand and right-hand limits, not to the value of $f$ there. "
            "This is the one place where the series and $f$ genuinely disagree."
        )
    else:
        note = (
            "$f$ is continuous and piecewise smooth here, so the series "
            "converges to $f(x)$ at every point of the interval."
        )
    return Step("Assemble the series", answer_latex, note)
