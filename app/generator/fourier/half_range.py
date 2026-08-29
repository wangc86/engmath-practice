r"""半幅展開（PLAN.md §2.10、階段 2B 的 2B3；課綱 W3）。

``template_id = "fourier.series.half_range"``

$f$ **只定義在 $(0, L)$ 上**，要求它的半幅正弦級數或餘弦級數。

---

## 這個題型與全幅的關係：只多了「延拓」這一層

半幅展開不是一套新的數學，它是「**先把 $f$ 延拓到 $(-L, 0)$，再做全幅級數**」，
而延拓的方式決定了要算哪一族：

- **正弦級數** ← 奇延拓 $f(-x) = -f(x)$ ← 於是 $a_0 = a_n = 0$
- **餘弦級數** ← 偶延拓 $f(-x) = f(x)$ ← 於是 $b_n = 0$

所以本模組**沒有自己的積分、沒有自己的閘門**：它建出延拓後的 `PiecewiseFn`，
其餘全部交給 `core.py` 與 `series.py`。這正是 PLAN §2.10 預期的
「2B3 大量重用 2B2 的機器，實質新增的只有奇／偶延拓這一層」。

⚠️ **一個很容易寫錯、而且錯了不會有任何東西壞掉的地方**：奇延拓是
$-g(-x)$，不是 $-g(x)$ 也不是 $g(-x)$。三者在 $g$ 是奇函數或偶函數時
**剛好會有兩個相等**，所以「用一個 $g = x$ 試一下看起來對」完全證明不了什麼。
擋這件事的是第四層閘門（宣稱的奇偶性要在符號上成立）加上
`test_the_odd_extension_is_not_just_a_sign_flip`——那一項故意用一個
既不奇也不偶的 $g$，三種寫法在它身上互不相等。

## 課本的公式為什麼寫成 $\frac{2}{L}\int_0^L$

延拓之後被積函數是偶的，所以 $\frac1L\int_{-L}^{L} = \frac2L\int_0^L$。
兩者的值相同，但**印給學生看的必須是後者**：他手上只有 $(0, L)$ 上的 $f$，
一個從 $-L$ 開始的積分等於要他去積一段題目沒有給的東西。
`core.coefficient_steps()` 的 `setup_latex` 參數就是為了這件事存在的。
"""

from __future__ import annotations

import random

import sympy as sp

from ..base import Problem, Step, register
from ..pretty import is_pretty_in_n
from . import core, series
from .core import N_INT, Coefficients, FourierCheck, PiecewiseFn, x

TEMPLATE_ID = "fourier.series.half_range"

HALF_PERIODS = (sp.Integer(1), sp.Integer(2), sp.pi)
COEFFS = (-3, -2, -1, 1, 2, 3)

DIFFICULTY_NOTES = {
    1: "$L = \\pi$ and a linear $f$ — the two classic textbook expansions",
    2: "A general half-period $L$ and a linear $f$",
    3: "A quadratic $f$, or two pieces meeting at $x = L/2$",
}

UGLINESS_LIMIT = {1: 12, 2: 20, 3: 30}


# --- 延拓 -------------------------------------------------------------------


def extend(pieces_on_right: list[tuple[sp.Expr, sp.Expr, sp.Expr]],
           L: sp.Expr, kind: str) -> PiecewiseFn:
    r"""把 $(0, L)$ 上的分段定義延拓到 $(-L, L)$。

    `kind` 是 ``"sine"``（奇延拓）或 ``"cosine"``（偶延拓）。

    ⚠️ 奇延拓是 $-g(-x)$。見模組檔頭那一段警告。
    """
    left = []
    for poly, lo, hi in reversed(pieces_on_right):
        mirrored = poly.subs(x, -x)
        left.append(((-mirrored if kind == "sine" else mirrored), -hi, -lo))
    return PiecewiseFn.build(left + list(pieces_on_right), L)


# --- 函數族 -----------------------------------------------------------------


def _half_period(rng: random.Random, difficulty: int, quadratic: bool) -> sp.Expr:
    r"""⚠️ 二次的 $f$ 配 $L = \pi$ 會在係數的分子裡留下 $\pi^2$，理由與
    `series._family_d3` 那一段完全相同（人工審題抓到的，測試抓不到）。

    所以形狀要先決定、$L$ 才決定——反過來的話那個組合擋不掉。"""
    if difficulty == 1:
        return sp.pi
    if quadratic:
        return rng.choice((sp.Integer(1), sp.Integer(2)))
    return rng.choice(HALF_PERIODS)


def _right_half(rng: random.Random, difficulty: int, L: sp.Expr, quadratic: bool):
    """$(0, L)$ 上的定義。回傳 `[(poly, lo, hi), ...]`。"""
    if difficulty < 3:
        c = rng.choice(COEFFS)
        d = rng.choice((0, 0, 1, 2, -1) if difficulty == 1
                       else (-3, -2, -1, 0, 1, 2, 3))
        return [(c * x + d, sp.Integer(0), L)]
    if quadratic:
        c = rng.choice(COEFFS)
        d = rng.choice((-2, -1, 0, 1, 2))
        return [(c * x**2 + d, sp.Integer(0), L)]
    inner = rng.choice((-2, -1, 1, 2)) * x
    outer = sp.Integer(rng.choice((-2, -1, 1, 2)))
    return [(inner, sp.Integer(0), L / 2), (outer, L / 2, L)]


# --- 組題 -------------------------------------------------------------------


def _formula_latex(L: sp.Expr, kind: str) -> str:
    r"""半幅的係數公式：$\frac{2}{L}\int_0^L f(x)\dots dx$。"""
    return r"%s\int_{0}^{%s} f(x)\,%s\,dx" % (
        core.over_L_latex(2, L), sp.latex(L),
        core.basis_latex(L, "cos" if kind == "cosine" else "sin"))


def _split_latex(right: list, L: sp.Expr, kind: str) -> str:
    parts = []
    for poly, lo, hi in right:
        parts.append(r"\int_{%s}^{%s} \left(%s\right) %s\,dx" % (
            sp.latex(lo), sp.latex(hi), sp.latex(poly),
            core.basis_latex(L, "cos" if kind == "cosine" else "sin")))
    joined = " + ".join(parts)
    if len(parts) > 1:
        joined = r"\left[ %s \right]" % joined
    return r"%s%s" % (core.over_L_latex(2, L), joined)


def _right_cases_latex(right: list, L: sp.Expr) -> str:
    if len(right) == 1:
        poly, lo, hi = right[0]
        return r"%s, \quad %s < x < %s" % (sp.latex(poly), sp.latex(lo), sp.latex(hi))
    rows = [r"%s, & %s < x < %s" % (sp.latex(p), sp.latex(lo), sp.latex(hi))
            for p, lo, hi in right]
    return r"\begin{cases} " + r" \\ ".join(rows) + r" \end{cases}"


STATEMENTS = {
    "sine": ("Find the half-range sine series of the following function, "
             "defined on $0 < x < L$. Extend it as an odd function of period $2L$."),
    "cosine": ("Find the half-range cosine series of the following function, "
               "defined on $0 < x < L$. Extend it as an even function of "
               "period $2L$."),
}


@register(
    TEMPLATE_ID,
    name="Fourier Series (Half Range)",
    chapter=series.CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    quadratic = difficulty == 3 and rng.random() < 0.5
    L = _half_period(rng, difficulty, quadratic)
    kind = rng.choice(("sine", "cosine"))
    right = _right_half(rng, difficulty, L, quadratic)
    fn = extend(right, L, kind)

    c = core.coefficients_of(fn)
    allow_quarter = difficulty == 3
    limit = UGLINESS_LIMIT[difficulty]
    for claim in (c.an, c.bn):
        if not is_pretty_in_n(claim, N_INT, limit, allow_quarter):
            return None
    # 整族都是 0 的題目沒有內容（例如 g ≡ 0 的餘弦級數）。
    if c.an == 0 and c.bn == 0:
        return None

    parity = "odd" if kind == "sine" else "even"
    at_zero = c.an.subs(N_INT, 0)
    needs_separate = bool(at_zero.has(sp.zoo, sp.nan)) or at_zero.is_finite is False

    answer = series.answer_latex_of(fn, c)
    steps = _steps(right, fn, c, kind, needs_separate, answer)

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params={
            "half_period": sp.srepr(L),
            "extension": kind,
            "right_half": [[sp.srepr(p), sp.srepr(lo), sp.srepr(hi)]
                           for p, lo, hi in right],
            "n_pieces": len(right),
            "parity": parity,
            "has_jump": fn.has_jump,
        },
        statement=STATEMENTS[kind],
        statement_latex="f(x) = " + _right_cases_latex(right, L),
        answer_latex=answer,
        answer_expr=sp.Tuple(c.a0, c.an, c.bn),
        answer_kind="coefficients",
        steps=steps,
        check=FourierCheck(
            fn=fn,
            coefficients=c,
            parity=parity,
            a0_needs_separate_formula=needs_separate,
        ),
    )


def _steps(right: list, fn: PiecewiseFn, c: Coefficients, kind: str,
           needs_separate: bool, answer: str) -> list[Step]:
    L = fn.half_period
    other = "cosine" if kind == "sine" else "sine"
    vanishing = "a_n" if kind == "sine" else "b_n"
    steps = [
        Step(
            "Write down the extension that the question asks for",
            "f(-x) = %sf(x) \\quad \\text{for } -L < x < 0, \\qquad L = %s"
            % ("-" if kind == "sine" else "", sp.latex(L)),
            f"A function given only on $(0, L)$ has no Fourier series yet — a "
            f"series needs a full period. Choosing the "
            f"{'odd' if kind == 'sine' else 'even'} extension is what makes the "
            f"answer a pure {kind} series; the {other} extension of the same $f$ "
            f"would give a completely different, and equally correct, series.",
        ),
        Step(
            f"All ${vanishing}$ vanish, so only one family is left",
            (r"a_0 = 0, \qquad a_n = 0" if kind == "sine" else r"b_n = 0"),
            "This is the whole point of the extension: the extended $f$ is "
            f"{'odd' if kind == 'sine' else 'even'}, so the integrand of "
            f"${vanishing}$ is odd over a symmetric interval and vanishes "
            "without any computation.",
        ),
        Step(
            "Write the half-range formula",
            r"%s = %s" % ("b_n" if kind == "sine" else "a_n",
                          _formula_latex(L, kind)),
            "Because the integrand is even after the extension, the integral "
            "over $[-L, L]$ is twice the integral over $[0, L]$ — which is the "
            "only part of $f$ the question actually gives you.",
        ),
    ]
    if kind == "cosine":
        # ⚠️ a_0 的公式也要換成半幅的寫法，理由與 `_split_latex` 相同：
        # 學生手上沒有 $(-L, 0)$ 上的 $f$。
        steps.append(core.a0_step(
            fn, c, needs_separate,
            formula_latex=r"%s\int_{0}^{%s} f(x)\,dx" % (
                core.over_L_latex(2 if core.A0_IS_HALVED else 1, L), sp.latex(L))))
    steps.extend(core.coefficient_steps(
        fn, c, "cos" if kind == "cosine" else "sin",
        setup_latex=_split_latex(right, L, kind)))
    steps.append(core.assembly_step(fn, c, answer))
    return steps
