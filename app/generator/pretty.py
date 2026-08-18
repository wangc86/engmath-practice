"""「漂亮解」的評分與檢查（PLAN.md §2.3），以及**顯示形式的一致性**（§2.9）。

三層防線的第三層：反向構造與參數白名單負責前兩層，這裡負責把漏網的醜答案擋下來。

「醜」與「不一致」是兩件不同的事，都在這裡處理：前者是單一個式子本身難看
（特殊函數、大分母），後者是**同一題的不同部分用不同的寫法**——見 `as_exponential`。
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


# --- 顯示形式的一致性（PLAN.md §2.9）---------------------------------------

HYPERBOLIC = (sp.sinh, sp.cosh, sp.tanh, sp.coth, sp.sech, sp.csch)


def as_exponential(expr):
    r"""把雙曲函數改寫回指數形式。**只影響顯示，不影響數學內容。**

    起因是一個很具體的症狀：線性系統帶初值、特徵值剛好是 $\pm 1$ 時，
    `sp.simplify` 會依它自己的評分逐項挑寫法，於是同一個向量的兩個分量
    一個被寫成 $3e^{t}-5e^{-t}$、另一個被寫成 $11\sinh t + \cosh t$。
    兩者都對，判定也完全不受影響（判的是代回原式），但學生看到的是同一個答案
    用兩套函數族書寫，會以為自己算錯了。

    統一往**指數**收（而不是往雙曲收）的理由：這門課教一階線性系統時，
    通解本來就寫成 $\sum_i C_i e^{\lambda_i t}\mathbf{v}_i$，逐步解答的每一步
    也都是指數；把最後一步改寫成 $\sinh/\cosh$ 等於在最後一行換一種語言。
    雙曲形式在工程數學裡有它的位置（懸鏈線、邊界值問題），但不是這裡。

    沒有雙曲函數就原樣回傳——特別是**不會**去動 $\sin/\cos$：二階常係數
    複數根的解本來就該寫成 $e^{\alpha x}(C_1\cos\beta x + C_2\sin\beta x)$，
    把它改寫成複指數才是真的難看。
    """
    if not expr.has(*HYPERBOLIC):
        return expr
    rewritten = expr.rewrite(sp.exp)
    if isinstance(rewritten, sp.MatrixBase):
        return rewritten.expand()
    return sp.expand(rewritten)


def mixes_function_families(expr) -> bool:
    """同一個答案裡同時出現指數與雙曲函數 → 書寫不一致（測試用的看守點）。"""
    atoms = _atoms(expr)
    has_exp = any(e.has(sp.exp) for e in atoms)
    has_hyp = any(e.has(*HYPERBOLIC) for e in atoms)
    return has_exp and has_hyp
