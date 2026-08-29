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


# --- Fourier 係數的漂亮度（PLAN.md §2.10.2，v0.25 新增）---------------------
#
# 上面那一支 `ugliness()` 是對 **x 的表達式**評分。Fourier 的答案是對 **n 的
# 表達式**，而「醜」的定義完全不一樣：
#
#   * `(-1)**n` 在這裡是**漂亮的**（它是這個題型的重點之一），
#     但在上面那一支眼裡它是一個 Pow，會被算進 count_ops。
#   * 上面那一支擋 `Integral` 與特殊函數；這裡真正要擋的是**分母的冪次太高**
#     與**需要按 n mod 4 分四種情形討論**的東西。
#   * 兩者的門檻沒有可比性——一個五項的係數式很正常，一個五項的 ODE 解很可疑。
#
# 所以這是一支新的函式，**不是去改既有那一支**（§2.10.2 的原話）。
# 共用只會逼出一堆 `if is_fourier:` 特例分支，而那種分支最後一定會被讀錯。

#: $\cos\frac{n\pi}{2}$、$\sin\frac{n\pi}{2}$ 這一類「要按 $n \bmod 4$ 分四種
#: 情形討論」的因子。它在難度 3 有教學價值（斷點在 $\pm L/2$ 的脈衝就一定會
#: 生出它），但**不能隨機跑出來**，所以由呼叫端明示允許。
QUARTER_PERIOD_FACTORS = (sp.sin, sp.cos)

#: 分母的 $n$ 冪次上限。$n^4$ 已經是三次多項式的結果，再高就不像考題了。
MAX_INDEX_POWER = 4


def _index_denominator_degree(expr, index) -> int:
    """係數式裡分母的 $n$ 最高冪次。"""
    best = 0
    for term in sp.Add.make_args(sp.expand(expr)):
        denominator = sp.denom(sp.together(term))
        if denominator.has(index):
            try:
                best = max(best, sp.Poly(denominator, index).degree())
            except sp.PolynomialError:
                return MAX_INDEX_POWER + 99      # 分母不是多項式 → 直接算它醜
    return best


def has_quarter_period_factor(expr, index) -> bool:
    r"""是否含 $\cos\frac{n\pi}{2}$ 或 $\sin\frac{n\pi}{2}$ 這類因子。

    判準是「三角函數的引數含 $n$」——$\cos n\pi$ 不會走到這裡，
    因為帶 `integer=True` 的 $n$ 讓 SymPy 早就把它化成 $(-1)^n$ 了
    （這正是附錄 C.4 要求 assumptions 一定要帶的原因）。
    """
    for f in QUARTER_PERIOD_FACTORS:
        for node in expr.atoms(f):
            if node.args[0].has(index):
                return True
    return False


def ugliness_in_n(expr, index, allow_quarter_period: bool = False) -> int:
    """Fourier 係數的漂亮度。分數越低越漂亮；建議門檻見各 generator。

    `allow_quarter_period` 只在難度 3 打開——見上面的說明。
    """
    if expr == 0:
        return 0
    total = int(sp.count_ops(expr))
    if expr.has(sp.Integral):                       # 積不出來
        total += 100
    if expr.has(sp.Piecewise):                      # 生成端挑過分支？一律擋（§2.10.4）
        total += 100
    if any(expr.has(f) for f in UGLY_FUNCS):
        total += 100
    degree = _index_denominator_degree(expr, index)
    if degree > MAX_INDEX_POWER:
        total += 100
    if has_quarter_period_factor(expr, index) and not allow_quarter_period:
        total += 100
    for number in expr.atoms(sp.Rational):
        if getattr(number, "q", 1) > MAX_DENOMINATOR:
            total += 8
    return total


def is_pretty_in_n(expr, index, limit: int, allow_quarter_period: bool = False) -> bool:
    return ugliness_in_n(expr, index, allow_quarter_period) <= limit


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
