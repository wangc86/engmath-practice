"""符號等價判定的基本工具（PLAN.md §5.3）。

這裡只做「是不是 0」與「常數是不是獨立」兩件事；判定流程本身在 core.py。

**整個判分最容易做錯的地方**是拿學生答案去減標準答案。通解幾乎必然減不出 0：
學生的 $C_1$ 可能對應不同的基本解，甚至是重新參數化過的
（$(C_1{+}C_2)e^{3x} + (C_1{-}C_2)e^{-2x}$ 是完全正確的通解）。
因此我們判的是**數學性質**（代回原式成立、常數個數對、解族線性獨立），
不是字面形式——這同時也讓 $C$ 與 $e^{C}$ 的差異自動消失（§5.4）。
"""

from __future__ import annotations

import random

import sympy as sp

from ..logging_setup import get_logger

logger = get_logger(__name__)

# 數值佐證的抽樣設定。取值刻意壓在 (0.1, 12) 這種溫和的範圍，
# 免得 e^{3x} 在大 x 直接爆掉浮點數。
_TRIALS = 24
_MIN_SUCCESS = 8
_REL_TOL = sp.Float("1e-18")
_PRECISION = 30


def is_zero(expr, syms) -> bool:
    """``expr`` 是否恆為 0。

    兩層：先 `expand` / `simplify`；`simplify` 化不掉時（它不是完備的）改用
    隨機有理數抽樣佐證。抽樣有偽陽性的理論可能，但要讓一個非零的初等函數在
    二十幾個隨機有理點上全部歸零，機率低到可以忽略。
    """
    if expr is None:
        return True
    if isinstance(expr, sp.MatrixBase):
        return all(is_zero(component, syms) for component in expr)

    expr = sp.sympify(expr)
    if expr.is_zero:
        return True
    expanded = sp.expand(expr)
    if expanded == 0:
        return True
    simplified = sp.simplify(expanded)
    if simplified == 0:
        return True
    if simplified.is_number:                 # 是個非零常數，不必再抽樣
        return False
    return _numerically_zero(simplified, syms)


def _numerically_zero(expr, syms) -> bool:
    symbols = sorted(set(syms) | expr.free_symbols, key=str)
    rng = random.Random(20260818)
    successes = 0
    last_error: str | None = None
    for _ in range(_TRIALS):
        point = {
            s: sp.Rational(rng.randint(1, 12), rng.randint(1, 7)) for s in symbols
        }
        try:
            value = sp.N(expr.subs(point), _PRECISION)
            scale = max(
                [abs(sp.N(term.subs(point), _PRECISION))
                 for term in sp.Add.make_args(expr)] or [sp.Integer(1)]
            )
        except (TypeError, ValueError, ZeroDivisionError, AttributeError) as exc:
            # 抽到極點之類的壞點是預期內的，換一個點就好；記下最後一個原因，
            # 只有在整批都失敗、決定「不敢說它是 0」時才報出來（見下方）。
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if not value.is_number or value.has(sp.zoo, sp.nan, sp.oo):
            continue
        if not scale.is_number or scale.has(sp.zoo, sp.nan, sp.oo):
            continue
        successes += 1
        if abs(value) > _REL_TOL * max(sp.Integer(1), scale):
            return False
    # 樣本太少（例如處處是極點）→ 不敢說它是 0
    if successes < _MIN_SUCCESS:
        # 這是一次**保守的誤判可能**：式子也許真的是 0，只是取不到夠多好點，
        # 而學生會因此看到 wrong。不影響安全性，但值得留痕跡。
        logger.debug(
            "數值佐證取不到足夠的樣本（%d/%d 次成功，門檻 %d），保守判為不等於 0。"
            "最後一次失敗：%s",
            successes, _TRIALS, _MIN_SUCCESS, last_error or "（無例外，只是取到極點）",
        )
        return False
    return True


def constants_of(candidate, var: sp.Symbol) -> list[sp.Symbol]:
    """學生答案裡的任意常數 = 自變數以外的自由符號。"""
    if isinstance(candidate, sp.MatrixBase):
        free: set[sp.Symbol] = set()
        for component in candidate:
            free |= component.free_symbols
    else:
        free = set(candidate.free_symbols)
    return sorted(free - {var}, key=str)


def independent_constants(candidate, consts: list[sp.Symbol], check) -> bool:
    """對常數的偏導是否構成線性獨立的解族（Wronskian ≠ 0）。

    這一關擋掉 $C_1e^{3x} + C_2e^{3x}$ 這種「滿足方程、常數個數也對，
    但兩項其實是同一個解」的退化答案。
    """
    if not consts:
        return True

    parts = [sp.diff(candidate, c) for c in consts]
    if any(is_zero(p, [check.var] + consts) for p in parts):
        return False                                   # 有常數根本沒作用

    if check.kind == "system":
        matrix = sp.Matrix.hstack(*[sp.Matrix(p) for p in parts])
    else:
        matrix = sp.Matrix(
            [[sp.diff(p, check.var, k) for p in parts] for k in range(check.order)]
        )
    if matrix.rows != matrix.cols:
        return False
    return not is_zero(matrix.det(), [check.var] + consts)
