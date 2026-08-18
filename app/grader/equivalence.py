"""符號等價判定的基本工具（PLAN.md §5.3）。

這裡只做「是不是 0」與「常數是不是獨立」兩件事；判定流程本身在 core.py。

**整個判分最容易做錯的地方**是拿學生答案去減標準答案。通解幾乎必然減不出 0：
學生的 $C_1$ 可能對應不同的基本解，甚至是重新參數化過的
（$(C_1{+}C_2)e^{3x} + (C_1{-}C_2)e^{-2x}$ 是完全正確的通解）。
因此我們判的是**數學性質**（代回原式成立、常數個數對、解族線性獨立），
不是字面形式——這同時也讓 $C$ 與 $e^{C}$ 的差異自動消失（§5.4）。

三值判定：zero / nonzero / unknown（v0.6）
==========================================

舊版的 `is_zero` 是兩值的，而且**用數值抽樣證明「是 0」**：`simplify` 化不掉時，
在 24 個隨機有理點上代值，全部歸零就回 True。這是整個判定唯一不是「證明」的
環節，理論上可以把非零式誤判為零——也就是**把錯答判成對**。

偽陽性有方向性，兩個方向的傷害完全不對稱：

- 誤判成「零」＝把錯的答案判成對。學生帶著一個錯誤的解離開，而且系統告訴他
  這是對的。這是**不可接受**的：本系統唯一的產品承諾就是「說對的時候是真的對」。
- 誤判成「非零」＝把對的答案判成錯。學生會困惑，但他手上有逐步解答可以對照，
  而且會再試一次。這是**可以忍受**的。

因此改成三值，並且把抽樣的角色反過來用：

    抽樣只用來**反證**（找到一個明顯不為 0 的點 → 確定不是 0），
    永遠不用來**證明**是 0。

於是：

    zero     ← 符號上證明得出來（expand / cancel / simplify / rewrite …）
    nonzero  ← 找得到不為 0 的取值點
    unknown  ← 兩者都做不到：數值上看起來是 0，但證不出來

`unknown` 在 core.py 會變成一則新的判定 `unverified`，介面上顯示
「系統無法確認你的答案，請對照解答」——不說對、也不說錯。

副作用是**判定變快了**：錯答通常在第一個取樣點就被反證，根本不會進到
`simplify`；只有「數值上看起來是 0」的式子才需要付符號化簡的代價。
"""

from __future__ import annotations

import collections
import random

import sympy as sp

from ..logging_setup import get_logger

logger = get_logger(__name__)

# 三值結果
ZERO = "zero"
NONZERO = "nonzero"
UNKNOWN = "unknown"

# 數值反證的抽樣設定。
#
# 取值刻意只取**正的有理數**，而且範圍溫和：
# - 正值是因為 generator 的自變數多半帶 `positive=True`（見 app/generator/*.py），
#   代負值進去在數學上就不一致；含 log／sqrt 的式子還會踩到分支切割，
#   算出一個假的非零值——那正是我們最不想要的方向（把對的判成錯）。
#   只在正半軸取樣不損失反證能力：初等函數在一個區間上恆為 0 就是恆為 0。
# - 範圍溫和是因為 e^{3x} 在大 x 會直接吃掉浮點數的有效位數。
_TRIALS = 32
_PRECISION = 40                    # 有效位數。比舊版的 30 高，降低「把對的判成錯」的機率
_REL_TOL = sp.Float("1e-25")       # 相對門檻，會再乘上各項的量級
_MIN_NONZERO_HITS = 2              # 至少要有兩個點超過門檻才敢說「不是 0」

# 落到各條路徑的次數。判定跑在子行程裡，這些數字**不會**回到主行程；
# 它們是給 scripts/grader_sampling_report.py 用的（那支腳本直接呼叫 core.grade）。
_COUNTERS: collections.Counter = collections.Counter()


def stats() -> dict:
    """回傳目前的路徑計數（診斷用，見 scripts/grader_sampling_report.py）。"""
    return dict(_COUNTERS)


def reset_stats() -> None:
    _COUNTERS.clear()


# --- 符號證明的管線 ---------------------------------------------------------
#
# 由便宜到昂貴排列，任何一步化到 0 就收工。每一步都各自 try，因為 SymPy 的
# 化簡函式對某些輸入會拋例外（NotImplementedError、PolynomialError…），
# 一步失敗不該讓整條管線失敗。

def _cancel(e):
    return sp.cancel(sp.together(e))


def _powsimp(e):
    return sp.expand(sp.powsimp(e, force=True))


def _rewrite_exp_expand(e):
    """把 sinh/cosh/sin/cos 全部拉到同一個函數族，然後只展開。

    這一步專治「兩邊寫法不同族」的殘差，例如學生寫 $\\sinh$、題目是 $e^{\\pm t}$。
    `simplify` 有時候化得掉、有時候化不掉，而且很貴；明確地 rewrite 一次再展開，
    既可靠又便宜（實測這一步就吃掉了絕大多數的不同族寫法，見
    scripts/grader_sampling_report.py）。所以它排在 `simplify` **前面**。
    """
    return sp.expand(e.rewrite(sp.exp))


def _rewrite_exp_simplify(e):
    """rewrite 之後再 simplify 一次——留給展開化不掉的少數情形。"""
    return sp.expand(sp.simplify(e.rewrite(sp.exp)))


def _expand_log(e):
    """可分離變數的隱式解常常長成 $\\ln$ 的組合，展開後才看得出抵銷。"""
    return sp.expand(sp.expand_log(e, force=True))


def _trig(e):
    return sp.trigsimp(sp.expand_trig(e))


def _radsimp(e):
    return sp.radsimp(sp.simplify(e))


_PIPELINE = (
    ("cancel", _cancel),
    ("powsimp", _powsimp),
    ("rewrite_exp", _rewrite_exp_expand),
    ("simplify", sp.simplify),
    ("rewrite_exp_simplify", _rewrite_exp_simplify),
    ("expand_log", _expand_log),
    ("trigsimp", _trig),
    ("radsimp", _radsimp),
)


def _prove_zero(expr) -> bool:
    """試著**證明** expr 恆為 0。證不出來回 False（不代表它不是 0）。"""
    for name, step in _PIPELINE:
        try:
            reduced = step(expr)
        except Exception as exc:                      # noqa: BLE001 - 換下一步就好
            # 化簡函式對某些輸入會拋例外，這是預期內的；但完全不留痕跡的話，
            # 「為什麼這題證不出來」就查不出原因了（規則 4：不許靜默失敗）。
            _COUNTERS[f"pipeline_error:{name}"] += 1
            logger.debug("化簡步驟 %s 失敗（%s: %s），換下一步。",
                         name, type(exc).__name__, exc)
            continue
        if reduced == 0 or reduced.is_zero:
            _COUNTERS[f"proved_by:{name}"] += 1
            return True
    return False


# --- 三值判定 ---------------------------------------------------------------

def zero_status(expr, syms) -> str:
    """``expr`` 恆為 0 嗎？回傳 :data:`ZERO` / :data:`NONZERO` / :data:`UNKNOWN`。

    **保證**：回傳 `ZERO` 一定是符號上證明出來的，不會是抽樣「看起來像」。
    """
    _COUNTERS["calls"] += 1
    if expr is None:
        _COUNTERS["fast_zero"] += 1
        return ZERO

    if isinstance(expr, sp.MatrixBase):
        results = [zero_status(component, syms) for component in expr]
        if any(r == NONZERO for r in results):
            return NONZERO
        if all(r == ZERO for r in results):
            return ZERO
        return UNKNOWN

    expr = sp.sympify(expr)
    if expr.is_zero:                                  # 結構上就是 0，最便宜的一條
        _COUNTERS["fast_zero"] += 1
        return ZERO
    expanded = sp.expand(expr)
    if expanded == 0:
        _COUNTERS["fast_zero"] += 1
        return ZERO

    if expanded.is_number:
        value = sp.N(expanded, _PRECISION)
        if value.is_number and not value.has(sp.zoo, sp.nan, sp.oo):
            if abs(value) > _REL_TOL:
                _COUNTERS["nonzero_constant"] += 1
                return NONZERO
        # 是個數，但數值上看起來是 0（例如 sqrt(8)-2*sqrt(2)）→ 還是要證
        if _prove_zero(expanded):
            _COUNTERS["proved_zero"] += 1
            return ZERO
        _COUNTERS["unknown"] += 1
        return UNKNOWN

    # 先用抽樣**反證**：錯答絕大多數在這裡就結束，完全不必付符號化簡的代價。
    _COUNTERS["sampled"] += 1
    if _numerically_nonzero(expanded, syms):
        _COUNTERS["disproved_by_sampling"] += 1
        return NONZERO

    # 數值上看起來是 0 → 現在才值得花力氣去證明它
    _COUNTERS["symbolic_pipeline"] += 1
    if _prove_zero(expanded):
        _COUNTERS["proved_zero"] += 1
        return ZERO

    # 證不出來。**絕不**因為「抽樣都是 0」就說它是 0——那正是舊版的偽陽性來源。
    # 這一則是要給老師看的：它代表判定管線遇到了它處理不了的寫法，
    # 而某個學生因此拿到「無法確認」。式子本身不記（它等同學生的作答，見規則 2），
    # 只記規模，足以判斷是不是同一類東西反覆出現。
    _COUNTERS["unknown"] += 1
    logger.warning(
        "判定無法確認一個式子是否為 0（數值上看起來是 0，但符號上證不出來）。"
        "學生會看到 unverified。運算元 %d 個、自由符號 %d 個。"
        "若這行反覆出現，請到 Attempt 表撈 verdict='unverified' 的作答，"
        "看是哪一種寫法沒被 app/grader/equivalence.py 的化簡管線涵蓋。",
        sp.count_ops(expanded), len(expanded.free_symbols),
    )
    return UNKNOWN


def is_zero(expr, syms) -> bool:
    """兩值的方便包裝：`UNKNOWN` 一律視為「不敢說它是 0」。

    只給**輔助性**的用途（答錯提示、線性獨立性、齊次性判斷）。判定學生答對與否
    的那一步一定要用 :func:`zero_status`，否則 `unknown` 會被壓成「不是 0」，
    學生會拿到 wrong 而不是「無法確認」。
    """
    return zero_status(expr, syms) == ZERO


def _numerically_nonzero(expr, syms) -> bool:
    """在隨機有理點上取值，找得到明顯不為 0 的點就回 True。

    這是一個**反證**：回 True 表示 expr 確定不恆為 0；回 False 什麼都不代表
    （可能是 0，也可能只是取不到好點）。

    要求至少 :data:`_MIN_NONZERO_HITS` 個點超過門檻才下結論，是為了擋掉
    「某一個點碰巧算出雜訊」這種數值假象——那個方向會把對的答案判成錯。
    """
    symbols = sorted(set(syms) | expr.free_symbols, key=str)
    rng = random.Random(20260818)                     # 固定亂數：同一份作答一定得到同一個判定
    terms = sp.Add.make_args(expr)
    successes = 0
    hits = 0
    last_error: str | None = None
    for _ in range(_TRIALS):
        point = {
            s: sp.Rational(rng.randint(1, 12), rng.randint(1, 9)) for s in symbols
        }
        try:
            value = sp.N(expr.subs(point), _PRECISION)
            scale = max(
                [abs(sp.N(term.subs(point), _PRECISION)) for term in terms]
                or [sp.Integer(1)]
            )
        except (TypeError, ValueError, ZeroDivisionError, AttributeError) as exc:
            # 抽到極點之類的壞點是預期內的，換一個點就好；記下最後一個原因，
            # 只有在整批都失敗時才報出來（見下方）。
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if not value.is_number or value.has(sp.zoo, sp.nan, sp.oo):
            continue
        if not scale.is_number or scale.has(sp.zoo, sp.nan, sp.oo):
            continue
        successes += 1
        if abs(value) > _REL_TOL * max(sp.Integer(1), scale):
            hits += 1
            if hits >= min(_MIN_NONZERO_HITS, max(successes, 1)):
                return True
    if successes == 0:
        # 處處是極點。反證失敗，接下來會交給符號管線；記一行，否則「為什麼這題
        # 特別慢」查不出來。
        _COUNTERS["no_usable_sample"] += 1
        logger.debug(
            "數值反證取不到任何可用的點（%d 次全部失敗）。最後一次失敗：%s",
            _TRIALS, last_error or "（無例外，只是取到極點）",
        )
    return False


# --- 常數與線性獨立 ---------------------------------------------------------

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

    這裡刻意用兩值的 :func:`is_zero`（`unknown` → 「不是 0」→ 判為獨立）：
    走到這一步時，殘差為 0 已經**證明**過了，也就是這個答案確實滿足方程；
    在這個前提下，把「Wronskian 算不出來」倒向學生有利的一邊是合理的
    ——它最多讓一個退化的寫法被放過，不會讓一個不是解的東西被判對。
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
