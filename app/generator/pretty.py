"""「漂亮解」的評分與檢查（PLAN.md §2.3）。

三層防線的第三層：反向構造與參數白名單負責前兩層，這裡負責把漏網的醜答案擋下來。
"""

from __future__ import annotations

import sympy as sp

# dsolve 解不乾淨時會冒出來的特殊函數
UGLY_FUNCS = (
    sp.erf, sp.Ei, sp.li, sp.Si, sp.Ci, sp.gamma,
    sp.besselj, sp.bessely, sp.hyper, sp.LambertW,
)

# 分母大於這個值就算「醜分數」
MAX_DENOMINATOR = 12


def _atoms(expr) -> list[sp.Expr]:
    if isinstance(expr, sp.MatrixBase):
        return list(expr)
    return [expr]


def ugliness(expr) -> int:
    """分數越低越漂亮。一階題型建議 <= 20，二階與系統 <= 40。"""
    total = 0
    for e in _atoms(expr):
        e = sp.simplify(e)
        total += int(sp.count_ops(e))
        if e.has(sp.Integral):                      # 未算完的積分
            total += 100
        if any(e.has(f) for f in UGLY_FUNCS):       # 特殊函數
            total += 100
        for n in e.atoms(sp.Rational):
            if getattr(n, "q", 1) > MAX_DENOMINATOR:
                total += 8
        for p in e.atoms(sp.Pow):
            if p.exp.is_Rational and not p.exp.is_Integer:
                total += 6
    return total


def has_ugly_fraction(expr, max_denominator: int = MAX_DENOMINATOR) -> bool:
    """是否含有分母過大的有理數。"""
    for e in _atoms(expr):
        for n in sp.simplify(e).atoms(sp.Rational):
            if getattr(n, "q", 1) > max_denominator:
                return True
    return False


def has_special_function(expr) -> bool:
    for e in _atoms(expr):
        if any(e.has(f) for f in UGLY_FUNCS) or e.has(sp.Integral):
            return True
    return False


def is_pretty(expr, limit: int) -> bool:
    """通過漂亮度門檻才放行。"""
    return (
        not has_special_function(expr)
        and not has_ugly_fraction(expr)
        and ugliness(expr) <= limit
    )
