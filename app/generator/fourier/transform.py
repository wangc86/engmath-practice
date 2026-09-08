r"""Fourier 變換（連續、非週期）——課綱 W4，工作項 2B11。

===========================================================================
零、這個檔案為什麼到 v0.39 才出現
===========================================================================

PLAN §2.10.5 把整個題型擋在 **§7 #24** 後面十幾輪，理由不是難，是**慣例分歧**：
$2\pi$ 可以放進指數（$e^{-2\pi i\xi x}$）、放在前面當係數（$\frac1{2\pi}$）、
或對稱地拆成兩個 $\frac1{\sqrt{2\pi}}$。三種課本都在用，
而**做錯慣例等於整個題型重寫**——不是程式重寫，是學生的筆記對不上。

2026-09-08 老師拍板：**$2\pi$ 放在前面係數**，正向用 $e^{-i\omega x}$（D72）。

⛔ **拍板之後仍然把它做成一個可以翻的開關**，理由與 `core.A0_IS_HALVED`
完全相同，而且更強：老師答的是「哪一種課本慣例」，不是「哪一行程式」。
若日後發現課本其實是 Zill（正向 $e^{+i\alpha x}$），代價必須是改一個常數，
不是改一個題型。下面第一節就是那個開關。

===========================================================================
一、慣例：**整個題型只有這一段可以改**（D72、§7 #24）
===========================================================================

見 `FORWARD_EXP_SIGN` 與 `PREFACTOR_ON_INVERSE` 兩個常數，
以及它們底下那一句「誰從它導出」。
`test_the_transform_convention_lives_in_exactly_one_place` 會翻轉它們並逐一確認。

===========================================================================
二、反向構造：一張**手抄的變換對照表**，不是 `sp.integrate`
===========================================================================

與 Fourier 級數同一個道理（`core.py` 第二節）：拿定義式算一次再拿定義式驗一次，
證明不了任何事。所以答案來自 `_FAMILIES` 裡**寫死的封閉形式**，
而閘門走的是**真的把積分算出來**這條完全獨立的路。

⚠️ **那張表本身要有人負責。** 表是我抄的，抄錯了閘門也看不出來——
閘門只證明「這個封閉形式與這個積分一致」，證明不了「這個積分是課本要的那一個」。
守那件事的是 `tests/test_generators.py` 的
`test_the_transform_pairs_match_the_textbook_table`（一份逐條手算過的對照表）
與 `test_forward_and_inverse_definitions_really_invert`（兩條定義式互為反變換）。
⛔ **那兩項才是慣例的守門人**，本檔的三層閘門不是——它們與這裡用同一組常數。

===========================================================================
三、三層閘門，而且刻意**不是四層**
===========================================================================

`core.FourierCheck` 是四層，這裡是三層，而**少的那一層是刻意的**：

級數那邊的第二層是 Parseval，價值在於它是一條與係數積分完全獨立的路。
這裡的對應物是 Plancherel（$\int|f|^2 = \frac1{2\pi}\int|F|^2$），實測**符號上
算得出來而且會通過**（三角脈衝 4/3、調變 33/116 兩邊逐字相等），
但單一題就要 6–10 秒，而每個難度會生 30 題。
⛔ **所以它沒有被放進每題都跑的閘門，而是變成一項獨立的測試**
（`test_plancherel_holds_for_one_pair_of_each_family`），每個族抽一題跑。
⚠️ 這是一個**取捨，不是遺漏**——寫在這裡是為了讓日後覺得「怎麼少一層」的人
看得到理由，而不是以為有人忘了。

留在閘門裡的三層，各自擋的東西不同：

1. `_gate_definition_integral`——把 $\int f(x)e^{-i\omega x}dx$ **真的算出來**
   （高精度數值，30 位）在四個探測點上比對。擋「表抄錯了」「參數代錯了」。
2. `_gate_area`——$F(0) = \int_{-\infty}^{\infty} f(x)\,dx$，**精確符號**。
   擋整體倍率錯誤，而且它落在第 1 層**探不到的那一點**上：
   四個封閉形式裡有三個在 $\omega = 0$ 是可去奇異點。
3. `_gate_symmetry`——實偶 $\Rightarrow$ $F$ 實且偶；實奇 $\Rightarrow$ $F$ 純虛且奇；
   一般實值 $f$ $\Rightarrow$ $F(-\omega) = \overline{F(\omega)}$。**符號上對所有
   $\omega$ 成立**，不是四個點。擋封閉形式裡的共軛／正負號抄錯。

⚠️ **第 1 層是數值的，這是本專案第二個數值閘門**（第一個是級數的部分和那一層）。
容差 $10^{-20}$、mpmath 30 位；四個族的實測誤差是 0、0、$2\times10^{-31}$、
$1.5\times10^{-19}$。**不用符號積分的理由是速度**：`sp.integrate` 對調變那一族
單一個探測點要 25 秒。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import mpmath as mp
import sympy as sp

from ..base import Difficulty, Problem, Step, register
from ...logging_setup import get_logger

logger = get_logger(__name__)

TEMPLATE_ID = "fourier.transform.forward"
CHAPTER = "Fourier Transform"

x = sp.Symbol("x", real=True)

# --- §7 #24 / D72：慣例，**整個題型只有這兩個常數可以改** --------------------

#: 正向變換指數上的正負號：$F(\omega) = \int f(x)\,e^{s\,i\omega x}\,dx$ 的 $s$。
#:
#: * `-1` —— $e^{-i\omega x}$。**老師 2026-09-08 拍板的就是這一個**
#:   （O'Neil、Greenberg、多數 DSP 課本，也與本專案 W5 的 DFT 展示同號）。
#: * `+1` —— $e^{+i\alpha x}$（Zill《Advanced Engineering Mathematics》）。
#:
#: ⛔ **這個常數沒有辦法被本檔的閘門守住**，因為閘門用的是同一個常數——
#: 翻掉它，答案與閘門會一起翻，三層全綠。守它的是
#: `test_the_transform_pairs_match_the_textbook_table`：一份**手抄的**課本對照表，
#: 其中單邊指數 $e^{-3x}u(x) \mapsto \frac{1}{3+i\omega}$ 這一條會直接分辨正負號
#: （另一種慣例下它是 $\frac{1}{3-i\omega}$）。
FORWARD_EXP_SIGN = -1

#: $\frac{1}{2\pi}$ 放在反變換那一邊（`True`）還是正向那一邊（`False`）。
#:
#: ⚠️ **老師的答案「$2\pi$ 放在前面係數」指定的是這一個**，而它有一個容易被
#: 忽略的後果：**這個題型求的是正向變換，所以答案裡根本不會出現 $2\pi$。**
#: 慣例在這裡影響的是「印出來的定義式」與「反變換那一行」，不是任何一個答案。
#: 因此守它的必須是「兩條定義式互為反變換」那一項測試
#: （`test_forward_and_inverse_definitions_really_invert`），
#: 不可能是任何一個對答案的檢查。
PREFACTOR_ON_INVERSE = True

#: 頻率變數的符號。Zill 用 $\alpha$，多數 DSP 課本用 $\omega$。
FREQ_NAME = "omega"

W = sp.Symbol(FREQ_NAME, real=True)


def forward_kernel(freq: sp.Expr = W) -> sp.Expr:
    r"""正向變換的核 $e^{\pm i\omega x}$。"""
    return sp.exp(FORWARD_EXP_SIGN * sp.I * freq * x)


def forward_prefactor() -> sp.Expr:
    return sp.Integer(1) if PREFACTOR_ON_INVERSE else 1 / (2 * sp.pi)


def inverse_prefactor() -> sp.Expr:
    return 1 / (2 * sp.pi) if PREFACTOR_ON_INVERSE else sp.Integer(1)


def _pref_latex(pref: sp.Expr) -> str:
    return "" if pref == 1 else r"\frac{1}{2\pi}"


def _sign_latex(sign: int) -> str:
    return "-" if sign < 0 else ""


def forward_definition_latex() -> str:
    r"""正向變換的定義式（含左邊的 $F(\omega) =$）。"""
    return (
        r"F(\%s) = %s\int_{-\infty}^{\infty} f(x)\,e^{%si\%s x}\,dx"
        % (FREQ_NAME, _pref_latex(forward_prefactor()),
           _sign_latex(FORWARD_EXP_SIGN), FREQ_NAME)
    )


def inverse_definition_latex() -> str:
    r"""反變換的定義式（含左邊的 $f(x) =$）。**指數的正負號與正向相反。**"""
    return (
        r"f(x) = %s\int_{-\infty}^{\infty} F(\%s)\,e^{%si\%s x}\,d\%s"
        % (_pref_latex(inverse_prefactor()), FREQ_NAME,
           _sign_latex(-FORWARD_EXP_SIGN), FREQ_NAME, FREQ_NAME)
    )


def convention_note() -> str:
    """定義式底下那一句說明（英文，介面語言）。"""
    where = "inversion formula" if PREFACTOR_ON_INVERSE else "transform itself"
    return (
        f"Conventions differ between textbooks. This course puts the factor "
        f"$1/2\\pi$ in front of the {where}, and uses "
        f"$e^{{{_sign_latex(FORWARD_EXP_SIGN)}i\\{FREQ_NAME} x}}$ in the forward "
        f"direction. Check which convention your notes use before comparing answers."
    )


# --- 訊號：分段定義在 $\mathbb{R}$ 上，支撐外為 0 ---------------------------


@dataclass(frozen=True)
class Signal:
    """一個實值訊號 $f$。純資料、可 pickle（與 `Check` 相同的理由，§2.2）。

    `pieces` 是 $(\\text{expr}, lo, hi)$ 的序列，**區間外一律是 0**。
    端點可以是 $\\pm\\infty$。
    """

    pieces: tuple[tuple[sp.Expr, sp.Expr, sp.Expr], ...]
    latex: str                       # f(x) 印出來的樣子（不含 "f(x) ="）
    parity: str                      # "even" | "odd" | "none"
    family: str                      # 哪一族（給 params 與 log 看）

    def integral_of(self, weight: sp.Expr) -> sp.Expr:
        """$\\int f(x)\\,w(x)\\,dx$，精確符號。"""
        return sum(sp.integrate(expr * weight, (x, lo, hi))
                   for expr, lo, hi in self.pieces)


def _mp(value) -> mp.mpf:
    """SymPy 數 → mpmath 數（走 30 位十進位，不經過 float）。"""
    if value == sp.oo:
        return mp.inf
    if value == -sp.oo:
        return -mp.inf
    return mp.mpmathify(str(sp.N(value, 40)))


def _mpc(expr) -> mp.mpc:
    """SymPy 複數 → mpmath 複數。

    ⚠️ **不能直接 `mp.mpmathify(str(...))`**：SymPy 印複數是 `-0.96*I`，
    mpmath 不認得那個寫法，而它拋的是 `TypeError`——一個會讓整題掛掉、
    但看起來像「機器壞了」的錯誤。實部虛部分開轉是唯一可靠的路。
    """
    value = sp.N(expr, 40)
    return mp.mpc(mp.mpmathify(str(sp.N(sp.re(value), 40))),
                  mp.mpmathify(str(sp.N(sp.im(value), 40))))


def _numeric_transform(signal: Signal, freq) -> mp.mpc:
    """把 $\\int f(x)e^{\\pm i\\omega x}dx$ **真的算出來**（高精度數值求積）。"""
    total = mp.mpc(0)
    for expr, lo, hi in signal.pieces:
        f = sp.lambdify(x, expr, "mpmath")
        a, b = _mp(lo), _mp(hi)
        nodes = [a, mp.mpf(0), b] if a < 0 < b else [a, b]
        total += mp.quad(
            lambda t, f=f: f(t) * mp.e ** (FORWARD_EXP_SIGN * 1j * freq * t), nodes)
    return total * _mp(forward_prefactor())


# --- 三層閘門 ---------------------------------------------------------------

#: 第一層的容差。實測四個族的最大誤差是 $1.5\times10^{-19}$（mpmath 30 位）。
NUMERIC_TOLERANCE = mp.mpf("1e-16")


@dataclass(frozen=True)
class TransformCheck:
    """Fourier 變換題型的驗證閘門（`Verifier` 協定的實作）。

    三層，各擋不同的東西；為什麼是三層而不是四層，見本檔檔頭第三節。
    """

    signal: Signal
    claim: sp.Expr                                   # 宣稱的 $F(\omega)$
    probes: tuple[sp.Expr, ...] = (sp.Integer(1), sp.Rational(3, 2),
                                   sp.Integer(3), sp.Integer(-2))

    def verify(self, problem) -> tuple[bool, str]:
        for gate in (self._gate_definition_integral, self._gate_area,
                     self._gate_symmetry):
            ok, reason = gate()
            if not ok:
                return False, reason
        return True, ""

    # -- 第一層：把定義式真的算出來（獨立路徑）----------------------------

    def _gate_definition_integral(self) -> tuple[bool, str]:
        for freq in self.probes:
            wv = _mp(freq)
            try:
                reference = _numeric_transform(self.signal, wv)
            except Exception as exc:                       # 規則 4：不許靜默
                return False, f"閘門一：ω={freq} 的求積失敗（{type(exc).__name__}: {exc}）"
            claimed = _mpc(self.claim.subs(W, freq))
            if abs(claimed - reference) > NUMERIC_TOLERANCE:
                return False, (
                    f"閘門一：F(ω) 在 ω={freq} 對不上"
                    f"（封閉形式 {mp.nstr(claimed, 12)}，"
                    f"積分 {mp.nstr(reference, 12)}）"
                )
        return True, ""

    # -- 第二層：面積（精確符號，落在第一層探不到的那一點）----------------

    def _gate_area(self) -> tuple[bool, str]:
        r"""$F(0) = \int_{-\infty}^{\infty} f(x)\,dx$（乘上正向的前置因子）。

        ⚠️ **$F$ 在 $\omega = 0$ 多半是可去奇異點**（矩形脈衝的
        $\frac{2h\sin c\omega}{\omega}$、三角脈衝的 $\omega^2$ 分母），
        所以這裡取極限而不是代值——代值會拿到 `nan` 然後**安靜地**通過。
        """
        area = sp.simplify(forward_prefactor() * self.signal.integral_of(sp.Integer(1)))
        at_zero = sp.simplify(sp.limit(self.claim, W, 0))
        if at_zero.has(sp.nan, sp.zoo) or at_zero.is_finite is False:
            return False, f"閘門二：F(ω) 在 ω→0 沒有有限極限（得到 {at_zero}）"
        if sp.simplify(at_zero - area) != 0:
            return False, f"閘門二：F(0) = {at_zero}，但 ∫f dx = {area}"
        return True, ""

    # -- 第三層：對稱性（符號上對所有 ω 成立）------------------------------

    def _gate_symmetry(self) -> tuple[bool, str]:
        r"""實值 $f$ 的三條對稱性。**這一層是對所有 $\omega$，不是四個點。**"""
        flipped = sp.simplify(self.claim.subs(W, -W))
        conjugated = sp.simplify(sp.conjugate(self.claim))
        if sp.simplify(flipped - conjugated) != 0:
            return False, (
                "閘門三：實值 f 要求 F(-ω) = conj F(ω)，但兩者不等"
                f"（{flipped} vs {conjugated}）"
            )
        if self.signal.parity == "even":
            if sp.simplify(sp.im(self.claim)) != 0:
                return False, "閘門三：f 是實偶函數，F 必須是實的"
            if sp.simplify(flipped - self.claim) != 0:
                return False, "閘門三：f 是偶函數，F 必須是偶的"
        elif self.signal.parity == "odd":
            if sp.simplify(sp.re(self.claim)) != 0:
                return False, "閘門三：f 是實奇函數，F 必須是純虛的"
            if sp.simplify(flipped + self.claim) != 0:
                return False, "閘門三：f 是奇函數，F 必須是奇的"
        return True, ""


# --- 手抄的變換對照表（反向構造的來源）--------------------------------------
#
# ⛔ **這張表是用手抄的，閘門看不出它抄錯了什麼。** 三層閘門證明的是
# 「這個封閉形式與這條積分一致」，而三層都用同一組慣例常數；
# 「這條積分是不是課本要的那一條」由 `tests/test_generators.py` 的
# `test_the_transform_pairs_match_the_textbook_table` 逐條守著。
#
# 每一族回傳 `(Signal, F(ω), params)`。`F` 一律**由慣例常數導出**——正負號取自
# `FORWARD_EXP_SIGN`，前置因子取自 `forward_prefactor()`（現行慣例下它是 1，
# 所以乘上去對今天的輸出沒有任何影響）。⛔ **不得寫死任何一個**：寫死的話翻轉
# 常數會得到一個「答案沒跟著翻、閘門跟著翻」的系統，而那種不一致是安靜的。


def _coeff_latex(value: sp.Expr) -> str:
    """係數印出來的樣子。**$1$ 印成空字串。**

    ⚠️ 這不是排版潔癖，是實測抓回來的：三角脈衝的 $h=1$ 原本印成
    $1\left(1-\frac{|x|}{2}\right)$，而 $\frac{2h}{c}$ 在 $h=1,c=2$ 時
    被字串拼成 **$\frac{21}{2}$**——那不是難看，那是**讀成二十一分之二**。
    """
    return "" if value == 1 else sp.latex(value)


def _scaled_latex(coefficient: sp.Expr, body: str) -> str:
    """$c \times (\text{body})$。**係數是 1 的時候連括號一起省掉。**"""
    head = _coeff_latex(coefficient)
    return rf"{head}\left({body}\right)" if head else body


def _abs_x_latex(coefficient: sp.Expr, rate: sp.Expr) -> str:
    return rf"{_coeff_latex(coefficient)}e^{{-{sp.latex(rate)}\left|x\right|}}"


def _two_sided_exp(A: sp.Expr, a: sp.Expr) -> tuple[Signal, sp.Expr, dict]:
    r"""$A e^{-a|x|} \;\mapsto\; \dfrac{2Aa}{a^2+\omega^2}$（與正負號無關）。"""
    signal = Signal(
        pieces=((A * sp.exp(a * x), -sp.oo, 0), (A * sp.exp(-a * x), 0, sp.oo)),
        latex=_abs_x_latex(A, a), parity="even", family="two_sided_exp")
    return signal, forward_prefactor() * 2 * A * a / (a**2 + W**2), {"A": int(A), "a": int(a)}


def _one_sided_exp(A: sp.Expr, a: sp.Expr) -> tuple[Signal, sp.Expr, dict]:
    r"""$A e^{-ax}u(x) \;\mapsto\; \dfrac{A}{a + i\omega}$。

    ⛔ **這一條是整張表裡唯一分辨得出正負號慣例的**：另一種慣例下它是
    $\frac{A}{a - i\omega}$。`test_the_transform_pairs_match_the_textbook_table`
    就是靠它把 `FORWARD_EXP_SIGN` 釘住的。
    """
    head = "" if A == 1 else sp.latex(A)
    signal = Signal(
        pieces=((A * sp.exp(-a * x), 0, sp.oo),),
        latex=(r"\begin{cases} %se^{-%sx}, & x > 0 \\[2pt] 0, & x < 0 \end{cases}"
               % (head, sp.latex(a))),
        parity="none", family="one_sided_exp")
    return signal, forward_prefactor() * A / (a - FORWARD_EXP_SIGN * sp.I * W), {"A": int(A), "a": int(a)}


def _rect(h: sp.Expr, c: sp.Expr) -> tuple[Signal, sp.Expr, dict]:
    r"""高 $h$、支撐 $[-c,c]$ 的矩形脈衝 $\mapsto \dfrac{2h\sin c\omega}{\omega}$。"""
    signal = Signal(
        pieces=((h, -c, c),),
        latex=(r"\begin{cases} %s, & \left|x\right| < %s \\[2pt] "
               r"0, & \left|x\right| > %s \end{cases}"
               % (sp.latex(h), sp.latex(c), sp.latex(c))),
        parity="even", family="rect")
    return signal, forward_prefactor() * 2 * h * sp.sin(c * W) / W, {"h": int(h), "c": int(c)}


def _triangle(h: sp.Expr, c: sp.Expr) -> tuple[Signal, sp.Expr, dict]:
    r"""三角脈衝 $h\left(1-\frac{|x|}{c}\right)$ $\mapsto \dfrac{4h}{c}\dfrac{\sin^2(c\omega/2)}{\omega^2}$."""
    signal = Signal(
        pieces=((h * (1 + x / c), -c, 0), (h * (1 - x / c), 0, c)),
        latex=(r"\begin{cases} %s, & \left|x\right| < %s \\[2pt] "
               r"0, & \left|x\right| > %s \end{cases}"
               % (_scaled_latex(h, r"1 - \frac{\left|x\right|}{%s}" % sp.latex(c)),
                  sp.latex(c), sp.latex(c))),
        parity="even", family="triangle")
    claim = forward_prefactor() * 4 * h / c * sp.sin(c * W / 2)**2 / W**2
    return signal, claim, {"h": int(h), "c": int(c)}


def _modulated(A: sp.Expr, a: sp.Expr, w0: sp.Expr) -> tuple[Signal, sp.Expr, dict]:
    r"""$A e^{-a|x|}\cos\omega_0 x \;\mapsto\;$ 兩份平移的 Lorentz 峰（頻移性質）。"""
    signal = Signal(
        pieces=((A * sp.exp(a * x) * sp.cos(w0 * x), -sp.oo, 0),
                (A * sp.exp(-a * x) * sp.cos(w0 * x), 0, sp.oo)),
        latex=rf"{_abs_x_latex(A, a)}\cos {sp.latex(w0)}x",
        parity="even", family="modulated")
    claim = forward_prefactor() * (A * a / (a**2 + (W - w0)**2)
                                   + A * a / (a**2 + (W + w0)**2))
    return signal, claim, {"A": int(A), "a": int(a), "w0": int(w0)}


def _x_exp(A: sp.Expr, a: sp.Expr) -> tuple[Signal, sp.Expr, dict]:
    r"""$A x e^{-a|x|} \;\mapsto\; \mp\dfrac{4iAa\omega}{(a^2+\omega^2)^2}$（微分性質）。

    ⚠️ 這是本表裡唯一的**奇函數**，所以它是第三層閘門「$F$ 必須是純虛且奇」
    那一格唯一的使用者——沒有它，那一格是一段從來沒有被執行過的程式。
    """
    head = "" if A == 1 else sp.latex(A)
    signal = Signal(
        pieces=((A * x * sp.exp(a * x), -sp.oo, 0), (A * x * sp.exp(-a * x), 0, sp.oo)),
        latex=rf"{head}x\,{_abs_x_latex(sp.Integer(1), a)}",
        parity="odd", family="x_exp")
    claim = forward_prefactor() * FORWARD_EXP_SIGN * 4 * sp.I * A * a * W / (a**2 + W**2)**2
    return signal, claim, {"A": int(A), "a": int(a)}


#: 難度 → 這個難度可以抽到的族。⛔ **難度軸的意思要對得起難度說明**，
#: 而守它的是 `test_the_transform_family_is_what_the_difficulty_promises`。
FAMILIES_BY_DIFFICULTY: dict[int, tuple[str, ...]] = {
    1: ("two_sided_exp", "one_sided_exp"),
    2: ("rect", "triangle"),
    3: ("modulated", "x_exp"),
}

DIFFICULTY_NOTES = {
    1: "Exponential decay: two-sided $e^{-a|x|}$ and one-sided $e^{-ax}u(x)$.",
    2: "Pulses of finite duration: rectangular and triangular. The answers "
       "involve $\\sin$ rather than rational functions.",
    3: "One property applied on top of a known pair: modulation "
       "(a frequency shift) or multiplication by $x$.",
}

STATEMENT = (
    "Find the Fourier transform $F(\\%s)$ of the following function. "
    "Use the convention stated in the first step of the solution."
) % FREQ_NAME


# --- 逐步解答 ---------------------------------------------------------------


def _pm(sign: int) -> str:
    """把 $\\pm 1$ 印成 `+` 或 `-`（用在 $a \\pm i\\omega$ 這種地方）。"""
    return "+" if sign > 0 else "-"


def _si_latex() -> str:
    """$s\\,i$ 印出來的樣子（$s$ 是 `FORWARD_EXP_SIGN`）。"""
    return "i" if FORWARD_EXP_SIGN > 0 else "-i"


def _limits_latex(lo: sp.Expr, hi: sp.Expr) -> tuple[str, str]:
    def one(v):
        if v == sp.oo:
            return r"\infty"
        if v == -sp.oo:
            return r"-\infty"
        return sp.latex(v)
    return one(lo), one(hi)


def _setup_latex(signal: Signal) -> str:
    """第 2 步：把 $f$ 代進定義式，依支撐拆成幾段積分。"""
    kernel = rf"e^{{{_sign_latex(FORWARD_EXP_SIGN)}i\{FREQ_NAME} x}}"
    parts = []
    for expr, lo, hi in signal.pieces:
        a, b = _limits_latex(lo, hi)
        # ⛔ 被積函數是一個和的時候一定要括號。實測抓回來的：三角脈衝原本印成
        # `\int (x/2 + 1) e^{-iωx} dx` 少了那對括號，變成
        # `\int \frac{x}{2} + 1\,e^{-i\omega x}\,dx`——**KaTeX 照樣渲染得出來**，
        # 只是渲染出一個意思不同的式子。⚠️ 那正是自動測試看不見、要人眼才看得到的
        # 那一類缺陷（§2.11.4 第四層、工作項 2B10）。
        body = sp.latex(expr)
        if expr.is_Add:
            body = rf"\left({body}\right)"
        parts.append(rf"\int_{{{a}}}^{{{b}}} {body}\,{kernel}\,dx")
    body = " + ".join(parts)
    pref = _pref_latex(forward_prefactor())
    return rf"F(\{FREQ_NAME}) = {pref}{body}"


def _evaluation_step(signal: Signal, p: dict) -> Step:
    """第 3 步：真正動手算的那一步。**每一族的算法不同，所以分支是明示的。**"""
    fam = signal.family
    s = FORWARD_EXP_SIGN
    w = rf"\{FREQ_NAME}"
    if fam == "two_sided_exp":
        A, a = sp.Integer(p["A"]), sp.Integer(p["a"])
        return Step(
            title="Integrate each half",
            latex=(rf"F({w}) = \frac{{{sp.latex(A)}}}{{{sp.latex(a)} {_pm(s)} i{w}}}"
                   rf" + \frac{{{sp.latex(A)}}}{{{sp.latex(a)} {_pm(-s)} i{w}}}"),
            note="The two halves are complex conjugates of each other, so the "
                 "imaginary parts cancel and the sum is real — which is what "
                 "the evenness of $f$ predicts.")
    if fam == "one_sided_exp":
        A, a = sp.Integer(p["A"]), sp.Integer(p["a"])
        return Step(
            title="Integrate over $x > 0$",
            latex=(rf"F({w}) = \left[\frac{{{sp.latex(A)}\,"
                   rf"e^{{-({sp.latex(a)} {_pm(-s)} i{w})x}}}}"
                   rf"{{-({sp.latex(a)} {_pm(-s)} i{w})}}\right]_{{0}}^{{\infty}}"
                   rf" = \frac{{{sp.latex(A)}}}{{{sp.latex(a)} {_pm(-s)} i{w}}}"),
            note="The bracket vanishes at the upper limit because "
                 "$|e^{-(a \\mp i\\omega)x}| = e^{-ax} \\to 0$. "
                 "⚠️ This is the one function here that is neither even nor odd, "
                 "so its transform is genuinely complex.")
    if fam == "rect":
        h, c = sp.Integer(p["h"]), sp.Integer(p["c"])
        # ⚠️ 這裡不可以寫 `e^{-{_si_latex()}…}`：`_si_latex()` 在現行慣例下已經是
        # `-i`，前面再加一個負號就印成 `e^{--i\omega}`（實測抓到的）。
        # 兩個指數各自的字串要分別算，不是其中一個取反。
        arg = f"{_coeff_latex(c)}{w}"                      # c\omega
        same = "-i" if s < 0 else "i"                      # s\,i
        opposite = "i" if s < 0 else "-i"                  # -s\,i
        return Step(
            title="Integrate the constant over the pulse",
            latex=(rf"F({w}) = \frac{{{sp.latex(h)}}}{{{same}{w}}}"
                   rf"\left[e^{{{same}{arg}}} - e^{{{opposite}{arg}}}\right]"),
            note="Now use $e^{i\\theta} - e^{-i\\theta} = 2i\\sin\\theta$. "
                 "The $i$ cancels, leaving a real, even function of $\\omega$.")
    if fam == "triangle":
        h, c = sp.Integer(p["h"]), sp.Integer(p["c"])
        factor = sp.Rational(2 * int(h), int(c))
        collapsed = _scaled_latex(factor, r"1 - \cos %s%s" % (sp.latex(c), w))
        return Step(
            title="Use evenness to halve the work",
            latex=(rf"F({w}) = 2\int_{{0}}^{{{sp.latex(c)}}} {_coeff_latex(h)}"
                   rf"\left(1 - \frac{{x}}{{{sp.latex(c)}}}\right)"
                   rf"\cos {w} x\,dx"
                   rf" = \frac{{{collapsed}}}{{{w}^{{2}}}}"),
            note="For a real even $f$ the sine part of the kernel integrates to "
                 "zero, so $F(\\omega) = 2\\int_0^{c} f(x)\\cos\\omega x\\,dx$. "
                 "The last form uses $1 - \\cos\\theta = 2\\sin^2(\\theta/2)$.")
    if fam == "modulated":
        A, a, w0 = sp.Integer(p["A"]), sp.Integer(p["a"]), sp.Integer(p["w0"])
        G = 2 * A * a / (a**2 + W**2)
        return Step(
            title="Apply the modulation (frequency-shift) property",
            latex=(rf"g(x) = {_abs_x_latex(A, a)} \;\Longrightarrow\; "
                   rf"G({w}) = {sp.latex(G)}, \qquad "
                   rf"F({w}) = \tfrac{{1}}{{2}}\left[G({w} - {sp.latex(w0)})"
                   rf" + G({w} + {sp.latex(w0)})\right]"),
            note="Writing $\\cos\\omega_0 x = \\tfrac12(e^{i\\omega_0 x} + "
                 "e^{-i\\omega_0 x})$ turns the integral into two copies of the "
                 "same one, each evaluated at a shifted frequency. "
                 "Multiplying by a cosine in $x$ splits the spectrum into two "
                 "half-height copies.")
    if fam == "x_exp":
        A, a = sp.Integer(p["A"]), sp.Integer(p["a"])
        G = 2 * A * a / (a**2 + W**2)
        coefficient = "i" if s < 0 else "-i"
        return Step(
            title="Apply the multiplication-by-$x$ property",
            latex=(rf"g(x) = {_abs_x_latex(A, a)} \;\Longrightarrow\; "
                   rf"G({w}) = {sp.latex(G)}, \qquad "
                   rf"F({w}) = {coefficient}\,\frac{{d}}{{d{w}}}G({w})"),
            note="Differentiating the definition under the integral sign brings "
                 "down a factor of $\\pm i x$, so multiplying $f$ by $x$ "
                 "corresponds to differentiating $F$. ⚠️ This $f$ is **odd**, "
                 "so its transform must come out purely imaginary.")
    raise AssertionError(f"沒有第 3 步的族：{fam}")     # 規則 4：不許靜默


def _steps(signal: Signal, claim: sp.Expr, params: dict, answer_latex: str) -> list[Step]:
    area = sp.simplify(forward_prefactor() * signal.integral_of(sp.Integer(1)))
    at_zero = sp.simplify(sp.limit(claim, W, 0))
    return [
        Step(title="Recall the definition (and which convention this course uses)",
             latex=forward_definition_latex(), note=convention_note()),
        Step(title="Substitute $f$ and split the integral over its support",
             latex=_setup_latex(signal),
             note="Outside the interval(s) written above, $f$ is zero, so those "
                  "parts of the real line contribute nothing."),
        _evaluation_step(signal, params),
        Step(title="Simplify", latex=answer_latex),
        Step(title="Check: the value at $\\%s = 0$ is the area under $f$" % FREQ_NAME,
             latex=(rf"F(0) = {sp.latex(at_zero)} = \int_{{-\infty}}^{{\infty}}"
                    rf" f(x)\,dx = {sp.latex(area)}"),
             note="Setting $\\omega = 0$ removes the kernel entirely, so $F(0)$ "
                  "is just the total area. It is the cheapest check available "
                  "and it catches most algebra slips."),
    ]


# --- 出題 -------------------------------------------------------------------


#: 調變族的 $(a, \omega_0)$ **白名單**，不是一個範圍。
#:
#: ⚠️ **這不是潔癖，是實測抓回來的**：逐步解答最後一步印的是
#: $F(0) = \frac{2Aa}{a^2+\omega_0^2}$，而 $a^2 + \omega_0^2$ 是兩個平方和——
#: 隨機抽 $a \in [1,3]$、$\omega_0 \in [2,5]$ 有一大半會生出 $\frac{6}{13}$、
#: $\frac{4}{29}$ 這種分母，`test_no_step_shows_an_ugly_number`
#: （分母上限 12）就會紅。那一項是對的：**畫面上出現 $\frac{6}{13}$ 的時候，
#: 學生會先懷疑自己算錯了**。
#:
#: ⛔ **處理方式是縮小參數，不是替這個題型開一個例外。**
#: v0.30 的 Parseval 開過一個例外（因為 $\frac{\pi^4}{90}$ 那種分母是**答案本身
#: 的性質**，縮參數縮不掉），而這裡不是那種情形——換一組 $(a,\omega_0)$
#: 就沒事了，開例外等於把一整個題型移出那道檢查。
#:
#: 下面六組讓 $\frac{2a}{a^2+\omega_0^2}$ 的分母都不超過 5（再乘 $A \in \{1,2\}$
#: 也一樣）。**改這一組之前先算一次那個分數。**
MODULATED_RATES: tuple[tuple[sp.Integer, sp.Integer], ...] = tuple(
    (sp.Integer(a), sp.Integer(w0))
    for a, w0 in ((1, 2), (1, 3), (2, 2), (2, 4), (3, 3), (4, 2))
)


_BUILDERS = {
    "two_sided_exp": lambda rng: _two_sided_exp(
        sp.Integer(rng.randint(1, 3)), sp.Integer(rng.randint(1, 3))),
    "one_sided_exp": lambda rng: _one_sided_exp(
        sp.Integer(rng.randint(1, 3)), sp.Integer(rng.randint(1, 3))),
    "rect": lambda rng: _rect(
        sp.Integer(rng.randint(1, 3)), sp.Integer(rng.randint(1, 3))),
    "triangle": lambda rng: _triangle(
        sp.Integer(rng.choice([1, 2, 4])), sp.Integer(rng.choice([1, 2]))),
    "modulated": lambda rng: _modulated(
        sp.Integer(rng.randint(1, 2)), *MODULATED_RATES[
            rng.randrange(len(MODULATED_RATES))]),
    "x_exp": lambda rng: _x_exp(
        sp.Integer(rng.randint(1, 3)), sp.Integer(rng.randint(1, 3))),
}


@register(
    TEMPLATE_ID,
    name="Fourier Transform",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    family = rng.choice(FAMILIES_BY_DIFFICULTY[difficulty])
    signal, claim, params = _BUILDERS[family](rng)
    answer_latex = rf"F(\{FREQ_NAME}) = {sp.latex(claim)}"
    params = dict(params, family=family)
    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=STATEMENT,
        statement_latex=rf"f(x) = {signal.latex}",
        answer_latex=answer_latex,
        answer_expr=claim,
        steps=_steps(signal, claim, params, answer_latex),
        check=TransformCheck(signal=signal, claim=claim),
        answer_kind="expression",
    )
