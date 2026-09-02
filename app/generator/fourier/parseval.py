r"""Parseval 恆等式求級數和（PLAN.md §6 的工作項 **2B5**，課綱 W3）。

學生看到一個函數與一個級數，要用 Parseval 恆等式把那個級數的封閉形式算出來
——例如從 $f(x)=x$ 得到 $\sum 1/n^2 = \pi^2/6$。

---

## 為什麼這個題型的反向構造特別乾淨

PLAN §6 說它「反向構造特別乾淨：先挑目標級數，再回推該用哪個 $f$」。
落地之後那句話**只對了一半，而修正的方向值得寫下來**：

真正乾淨的是**驗證**，不是構造。構造這一側其實是一份**白名單**——
四個函數配三個半週期，就這樣。理由與 §7 #14（參數變異法的 $g(x)$ 白名單）
完全相同，而且更絕對：

⛔ **隨機的 $f$ 幾乎必然給不出一個「有名字」的級數。**
Parseval 對**任何**平方可積的 $f$ 都成立，所以隨機抽一個分段多項式一定
會得到一個等式——但右邊會是
$\sum \frac{(\text{一堆有理數})}{n^4} + \frac{(\text{另一堆})(-1)^n}{n^6} + \cdots$，
而那不是一道題目，那是一個沒有人想看的算式。**題目的價值來自左邊那個
級數本身值得認識**（$\zeta(2)$、$\zeta(4)$、只取奇數項的版本），
而那件事沒有辦法從參數裡抽出來。

因此這個檔案的隨機性只有三個旋鈕：**哪一族、半週期 $L$、振幅**。
⚠️ **而其中兩個不影響答案**——這是刻意的，見下面「$L$ 為什麼可以動」。

---

## 三個難度

| 難度 | $f$ | 目標級數 | 為什麼排在這裡 |
|---|---|---|---|
| 1 | 方波（$\pm c$） | $\sum_{n\ \text{odd}} \frac{1}{n^2} = \frac{\pi^2}{8}$ | $f$ 是奇函數所以 $a_n=a_0=0$，Parseval 只剩一項。**左邊的積分是常數的積分**，連微積分都不太需要 |
| 2 | $f(x)=cx$ | $\sum \frac{1}{n^2} = \frac{\pi^2}{6}$ | 仍然只有 $b_n$，但係數要分部積分，而且級數是**全部的 $n$**（不是只有奇數） |
| 3 | $f(x)=cx^2$ 或 $c\lvert x\rvert$ | $\sum \frac{1}{n^4} = \frac{\pi^4}{90}$ 或 $\sum_{n\ \text{odd}} \frac{1}{n^4} = \frac{\pi^4}{96}$ | $f$ 是偶函數，所以 **$a_0$ 這一項第一次真的參與計算**——而它是這個題型唯一一個學生會漏掉的地方 |

⚠️ **難度 3 的重點不是「次方比較高」，是 $a_0$。** 難度 1、2 的 $f$ 都是奇函數，
$a_0=0$，所以 Parseval 右邊的 $\frac{a_0^2}{2}$ 整項消失——一個從難度 1 一路
做上來的學生會很自然地以為那一項不存在。難度 3 是它第一次不為零，
而漏掉它的症狀是「算出來的和差了一個常數」，不是「算不出來」。

## $L$ 為什麼可以動，而答案不動

$\sum 1/n^2 = \pi^2/6$ 與 $L$ 無關——左邊的積分與右邊的係數平方**各自都含
$L$，而它們恰好約掉**。所以動 $L$ 只改變中間的算式，不改變答案。

**這件事看起來像一個缺點（同一個難度的每一題答案都一樣），實際上它是
這個題型最好的一個教學點**，而它寫在解題步驟的最後一步裡：
若學生算出來的答案裡還留著 $L$，那就是某一邊的 $L$ 抄錯了。

⚠️ 所以**不要為了「讓答案有變化」而把 $L$ 塞進答案**。那需要改題目問法
（例如問 $\sum L^2/n^2$），而那個問法沒有教學意義。

---

## 驗證閘門：四層，而且**一層都不准跳過**

⚠️ **這一點與 `FourierCheck` 不同，差別要說清楚。** `FourierCheck` 的第二層
（Parseval）在少數參數上算不出封閉形式時**允許跳過並記一行 log**——因為
那一層只是它四層裡的一層，而題目的內容是係數。

**這個題型不行：題目的內容就是那個和。** 一個「算不出封閉形式」的樣本不是
「少驗一層」，是「這一題根本沒有答案」。所以這裡的作法是**重抽**，
不是跳過。

| 層 | 問的問題 | 為什麼它擋得到別人擋不到的東西 |
|---|---|---|
| 1 | 係數對不對？ | 走 `core.coefficient_by_probe()`——**先代具體 $n$ 再積分**，與生成路徑的順序相反 |
| 2 | Parseval 的兩邊真的相等嗎？ | 這一層驗的是**題目做得出來**：左邊的積分、右邊的級數和，兩邊獨立算 |
| 3 | 宣稱的和真的是那個封閉形式嗎？ | **完全不經過 Parseval**——直接對 $\sum$ 求封閉形式。第 2 層通過而第 3 層不通過，代表白名單那一列寫錯了 |
| 4 | 數值上收斂到那個值嗎？ | 完全不用 SymPy 的符號求和。它擋的是「`Sum().doit()` 給了一個錯的封閉形式」——那種錯**符號上自洽**，前三層都看不出來 |

⛔ **第 4 層不是為了保險而加的。** 前三層有一個共同的單點失效：
它們全部依賴 `sp.Sum(...).doit()`。第 4 層是唯一一條不經過它的路。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import sympy as sp

from ..base import Problem, Step, register
from . import core
from .core import N_INT, Coefficients, PiecewiseFn, coefficient_by_probe, x
from .series import CHAPTER

TEMPLATE_ID = "fourier.parseval.series_sum"

DIFFICULTY_NOTES = {
    1: "Square wave; only the sine coefficients survive",
    2: "f(x) = cx; the series runs over every n",
    3: "Even f, so the constant term a0 takes part as well",
}

STATEMENT = (
    "Use Parseval's identity for the Fourier series of the function below to "
    "evaluate the series that follows it."
)

#: 半週期的候選。⚠️ **答案與它無關**（見檔頭），它只改變中間的算式。
#: $\pi$ 放在裡面是因為課本的經典寫法就是 $L=\pi$，而學生會想認出它。
HALF_PERIODS: tuple[sp.Expr, ...] = (sp.Integer(1), sp.Integer(2), sp.pi, sp.Integer(3))

#: 振幅。⚠️ 不含 0——那會讓 $f \equiv 0$，而 Parseval 變成 $0=0$：
#: 一個完全正確、完全沒有內容的等式，而且**前三層閘門都會放它過去**。
AMPLITUDES: tuple[int, ...] = (1, 2, 3)


@dataclass(frozen=True)
class Target:
    """一個「有名字」的級數：要求和的那一項，與它的封閉形式。

    純資料（§2.2 第 2 點）。`summand` 與 `closed_form` **都寫在白名單裡**，
    而閘門的第 3 層會去驗證兩者真的相等——**不是相信這張表**。
    """

    summand: sp.Expr        # 對 N_INT 的一項，例如 1/n**2
    closed_form: sp.Expr    # 例如 pi**2/6
    latex: str              # 題目上印的那一行


def _odd_only(term: sp.Expr) -> sp.Expr:
    r"""只取奇數 $n$ 的寫法：乘上 $\frac{1-(-1)^n}{2}$。

    ⚠️ **刻意用這個形式，而不是把和寫成 $\sum_{k} f(2k-1)$。**
    兩者數學上相同，但這一個讓 `core._closed_form_sum()` 直接吃得下去
    （它會拆成 $1/n^m$ 與 $(-1)^n/n^m$ 兩個它認得的形狀），
    而換元的那一個會讓 SymPy 走上一條它答不出來的路。
    """
    return (1 - (-1) ** N_INT) / 2 * term


TARGETS: dict[str, Target] = {
    "zeta2_odd": Target(
        summand=_odd_only(1 / N_INT**2),
        closed_form=sp.pi**2 / 8,
        latex=r"\sum_{\substack{n=1\\ n\ \text{odd}}}^{\infty} \frac{1}{n^{2}}",
    ),
    "zeta2": Target(
        summand=1 / N_INT**2,
        closed_form=sp.pi**2 / 6,
        latex=r"\sum_{n=1}^{\infty} \frac{1}{n^{2}}",
    ),
    "zeta4": Target(
        summand=1 / N_INT**4,
        closed_form=sp.pi**4 / 90,
        latex=r"\sum_{n=1}^{\infty} \frac{1}{n^{4}}",
    ),
    "zeta4_odd": Target(
        summand=_odd_only(1 / N_INT**4),
        closed_form=sp.pi**4 / 96,
        latex=r"\sum_{\substack{n=1\\ n\ \text{odd}}}^{\infty} \frac{1}{n^{4}}",
    ),
}


# --- 白名單：四個函數族 -----------------------------------------------------
#
# ⚠️ 每一族都附一句「它為什麼給得出那個級數」。那一句不是註解，是這張表
# 唯一可以被人審查的部分——閘門驗得了「這一題是對的」，驗不了
# 「這一題是不是我們想出的那一題」。


def _square_wave(L: sp.Expr, c: int) -> PiecewiseFn:
    r"""$f = -c$ 在 $(-L,0)$、$+c$ 在 $(0,L)$。

    $b_n = \frac{2c(1-(-1)^n)}{n\pi}$，奇數 $n$ 才不為零，所以
    $\sum b_n^2 = \frac{16c^2}{\pi^2}\sum_{n\ \text{odd}}\frac{1}{n^2}$，
    而左邊是 $\frac{1}{L}\int_{-L}^{L} c^2 = 2c^2$。
    """
    return PiecewiseFn.build(
        [(sp.Integer(-c), -L, sp.Integer(0)), (sp.Integer(c), sp.Integer(0), L)], L
    )


def _linear(L: sp.Expr, c: int) -> PiecewiseFn:
    r"""$f = cx$。奇函數，$b_n = \frac{2cL(-1)^{n+1}}{n\pi}$，
    所以 $\sum b_n^2 = \frac{4c^2L^2}{\pi^2}\zeta(2)$，左邊是 $\frac{2c^2L^2}{3}$。"""
    return PiecewiseFn.build([(c * x, -L, L)], L)


def _quadratic(L: sp.Expr, c: int) -> PiecewiseFn:
    r"""$f = cx^2$。偶函數，$a_0 = \frac{2cL^2}{3}$、
    $a_n = \frac{4cL^2(-1)^n}{n^2\pi^2}$——**$a_0$ 第一次真的參與計算**。"""
    return PiecewiseFn.build([(c * x**2, -L, L)], L)


def _absolute(L: sp.Expr, c: int) -> PiecewiseFn:
    r"""$f = c\lvert x\rvert$，寫成兩段。偶函數，$a_n$ 只有奇數項不為零，
    所以它給的是 $\sum_{n\ \text{odd}} 1/n^4$。"""
    return PiecewiseFn.build([(-c * x, -L, sp.Integer(0)), (c * x, sp.Integer(0), L)], L)


#: (難度) → [(建構函式, 目標級數的鍵, 給人看的族名)]
FAMILIES: dict[int, tuple[tuple, ...]] = {
    1: ((_square_wave, "zeta2_odd", "square wave"),),
    2: ((_linear, "zeta2", "f(x) = cx"),),
    3: ((_quadratic, "zeta4", "f(x) = cx^2"),
        (_absolute, "zeta4_odd", "f(x) = c|x|")),
}


# --- 閘門 -------------------------------------------------------------------


@dataclass(frozen=True)
class ParsevalCheck:
    r"""四層閘門（`Verifier` 協定的實作）。逐層的理由見檔頭那張表。

    ⛔ **一層都不准跳過。** `FourierCheck` 允許它的 Parseval 那一層在算不出
    封閉形式時跳過並記 log；這裡不行，因為**題目的內容就是那個和**。
    算不出來的樣本要重抽，不是少驗一層。
    """

    fn: PiecewiseFn
    coefficients: Coefficients
    summand: sp.Expr
    claimed: sp.Expr
    probes: tuple[int, ...] = (1, 2, 3, 4, 5, 7)
    #: 第四層的部分和項數。⚠️ 它與容差是綁在一起的，見 `_gate_numeric`。
    partial_terms: int = 4000

    def verify(self, problem) -> tuple[bool, str]:
        for gate in (self._gate_coefficients, self._gate_parseval,
                     self._gate_closed_form, self._gate_numeric):
            ok, reason = gate()
            if not ok:
                return False, reason
        return True, ""

    # -- 第一層：係數（先代 n 再積分，與生成路徑順序相反）-----------------

    def _gate_coefficients(self) -> tuple[bool, str]:
        c = self.coefficients
        for k in self.probes:
            for claim, kind, name in ((c.an, "cos", "a"), (c.bn, "sin", "b")):
                reference = coefficient_by_probe(self.fn, k, kind)
                if sp.simplify(claim.subs(N_INT, k) - reference) != 0:
                    return False, (
                        f"閘門一：{name}_n 在 n={k} 對不上"
                        f"（封閉形式 {sp.simplify(claim.subs(N_INT, k))}，"
                        f"獨立路徑 {sp.simplify(reference)}）"
                    )
        return True, ""

    # -- 第二層：Parseval 的兩邊 ------------------------------------------

    def mean_square(self) -> sp.Expr:
        r"""$\frac{1}{L}\int_{-L}^{L} f^2$。這是 Parseval 的左邊。"""
        L = self.fn.half_period
        total = sum(sp.integrate(p.poly**2, (x, p.lo, p.hi)) for p in self.fn.pieces)
        return sp.simplify(total / L)

    def _gate_parseval(self) -> tuple[bool, str]:
        c = self.coefficients
        rhs_sum = core._closed_form_sum(sp.expand(c.an**2 + c.bn**2))
        if rhs_sum.has(sp.Sum):
            # ⛔ 不是「跳過這一層」——這一題沒有答案，重抽。
            return False, "閘門二：係數平方的級數算不出封閉形式（這一題沒有答案）"
        rhs = core.constant_term(c.a0) * c.a0 + rhs_sum
        if sp.simplify(self.mean_square() - rhs) != 0:
            return False, (
                f"閘門二：Parseval 兩邊不相等"
                f"（左 {self.mean_square()}，右 {sp.simplify(rhs)}）"
            )
        return True, ""

    # -- 第三層：宣稱的和（完全不經過 Parseval）---------------------------

    def _gate_closed_form(self) -> tuple[bool, str]:
        value = core._closed_form_sum(self.summand)
        if value.has(sp.Sum):
            return False, f"閘門三：目標級數算不出封閉形式（{self.summand}）"
        if sp.simplify(value - self.claimed) != 0:
            return False, (
                f"閘門三：宣稱的和不對（宣稱 {self.claimed}，算出 {sp.simplify(value)}）"
            )
        return True, ""

    # -- 第四層：數值（唯一一條不經過 sp.Sum().doit() 的路）---------------

    def _gate_numeric(self) -> tuple[bool, str]:
        r"""部分和要逼近宣稱的封閉形式。

        ⚠️ **容差與項數是綁在一起的，不要單獨動其中一個。**
        這裡的級數尾巴至少像 $\sum_{n>N} 1/n^2 \approx 1/N$，
        所以 $N=4000$ 的相對誤差上界約 $1/(4000 \times 1.64) \approx 1.5\times10^{-4}$。
        容差取 $10^{-3}$ 留了將近一個數量級的餘裕——**餘裕是給尾巴估計用的，
        不是給錯誤用的**：一個真的算錯的封閉形式會差好幾個百分點，不會差 0.05%。
        """
        f = sp.lambdify(N_INT, self.summand, "math")
        total = math.fsum(f(k) for k in range(1, self.partial_terms + 1))
        target = float(self.claimed)
        if target == 0:
            return False, "閘門四：目標值是 0，這不是一道題目"
        error = abs(total - target) / abs(target)
        if error > 1e-3:
            return False, (
                f"閘門四：部分和（{self.partial_terms} 項）是 {total:.8f}，"
                f"封閉形式是 {target:.8f}，相對誤差 {error:.2e}"
            )
        return True, ""


# --- 題目 -------------------------------------------------------------------


def _steps(fn: PiecewiseFn, c: Coefficients, target: Target,
           check: ParsevalCheck) -> list[Step]:
    """五步。切法照 §7 #22：一步 = 課本上會單獨寫一行的一個動作。

    ⚠️ 最後一步刻意不是「所以答案是 …」，而是一句檢查的方法（$L$ 必須消掉）。
    §6「解說品質」第 3 點說 `note` 要回答「為什麼」；這一題的「為什麼」
    正好是一個學生自己用得上的驗算。
    """
    L = fn.half_period
    lhs = check.mean_square()
    head = core.series_head_latex()
    return [
        Step(
            "Write down the Fourier coefficients of f",
            r"a_0 = %s, \qquad a_n = %s, \qquad b_n = %s"
            % (sp.latex(c.a0), sp.latex(c.an), sp.latex(c.bn)),
            "Parseval's identity needs the coefficients, so this is the same "
            "work as an ordinary Fourier series problem. "
            + core.parity_note(fn.parity()),
        ),
        Step(
            "Compute the mean square of f over one period",
            r"\frac{1}{L}\int_{-L}^{L} \left[f(x)\right]^{2}\,dx = %s"
            % sp.latex(lhs),
            "This is the left-hand side of Parseval's identity. It is an "
            "ordinary definite integral of a polynomial — no Fourier series "
            "is involved yet.",
        ),
        Step(
            "State Parseval's identity",
            r"\frac{1}{L}\int_{-L}^{L}\left[f(x)\right]^{2}\,dx"
            r" = \frac{a_0^{2}}{2} + \sum_{n=1}^{\infty}\left(a_n^{2} + b_n^{2}\right)",
            "The identity says that the mean square of $f$ equals the sum of "
            "the squares of its coefficients. Note the $\\tfrac{a_0^2}{2}$ "
            "term: it is easy to forget, and it is not zero whenever $f$ has "
            "a non-zero average. (The $\\tfrac{1}{2}$ is there because this "
            "course writes the series with $%s$.)" % head,
        ),
        Step(
            "Substitute the coefficients and pull out the constants",
            r"%s = %s" % (sp.latex(lhs),
                          sp.latex(core.constant_term(c.a0) * c.a0)
                          + " + " + sp.latex(sp.expand(c.an**2 + c.bn**2))
                          + r"\ \text{summed over } n \ge 1"),
            "Every factor that does not depend on $n$ comes outside the sum. "
            "What is left inside is exactly the series you were asked about.",
        ),
        Step(
            "Solve for the series",
            r"%s = %s" % (target.latex, sp.latex(target.closed_form)),
            "Check your work with this: the half-period $L$ must cancel "
            "completely. It appears on both sides — inside the integral on "
            "the left, and inside the coefficients on the right — and the two "
            "occurrences must remove each other. If your answer still "
            "contains $L$, one of the two sides was copied wrongly.",
        ),
    ]


@register(
    TEMPLATE_ID,
    name="Parseval's Identity: Summing a Series",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    build, target_key, family_name = rng.choice(FAMILIES[difficulty])
    L = rng.choice(HALF_PERIODS)
    c = rng.choice(AMPLITUDES)
    target = TARGETS[target_key]

    fn = build(L, c)
    try:
        coefficients = core.coefficients_of(fn)
    except core.ResonantIntegral as exc:
        # 這個白名單上的四族都不會走到這裡（它們都是分段多項式），
        # 但擴族時會——而靜默地回 None 會讓那件事沒有人知道（規則 4）。
        core.logger.info("Parseval：係數積分不封閉，重抽：%s", exc)
        return None

    params = {
        "family": family_name,
        "target": target_key,
        "half_period": sp.srepr(L),
        "amplitude": c,
    }

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=STATEMENT,
        statement_latex=(
            "f(x) = " + fn.cases_latex()
            + r",\qquad \text{find}\quad " + target.latex
        ),
        # ⚠️ **答案只放封閉形式，不重複那個 $\sum$。** 兩個理由：
        # （1）題目敘述裡已經寫了要求哪一個級數，答案卡片再抄一次是雜訊；
        # （2）`test_steps_are_complete` 對 `expression` 走的是「比等號右邊」，
        #     而 `\sum_{n=1}^{\infty}` 這個寫法**本身就含一個等號**——
        #     把整條等式放進 `answer_latex` 會讓那項測試在 `n=1` 那個等號上
        #     切開，於是它比的是兩段沒有意義的字串。這是踩到才知道的。
        answer_latex=sp.latex(target.closed_form),
        # ⚠️ `answer_kind` 用預設的 `expression`，不是 `coefficients`：
        # 答案是一個**數**（$\pi^2/6$），不是一組以 $n$ 為參數的封閉形式。
        # 這件事決定了顯示形式與漂亮度檢查走哪一條路（見 `base.AnswerKind`）。
        answer_expr=target.closed_form,
        steps=_steps(fn, coefficients, target,
                     ParsevalCheck(fn=fn, coefficients=coefficients,
                                   summand=target.summand,
                                   claimed=target.closed_form)),
        check=ParsevalCheck(
            fn=fn,
            coefficients=coefficients,
            summand=target.summand,
            claimed=target.closed_form,
        ),
    )
