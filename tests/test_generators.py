"""出題引擎的回歸測試（PLAN.md §2.7）。

這是整個系統最重要的測試：它保證進到學生眼前的每一題都有正確答案。
每個模板 × 每個難度都會隨機生成 N 題，逐題檢查：

1. 把解代回原方程，殘差恰為 0（最關鍵的一項）
2. 沒有特殊函數、沒有未算完的積分
3. 沒有醜分數（分母 > 12）
4. 出題參數落在合理範圍
5. 逐步解答非空，且最後一步就是答案

改動 SymPy 版本後務必重跑。
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import random
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest
import sympy as sp

ROOT = Path(__file__).resolve().parent.parent

from app.generator import DIFFICULTY_LABELS, generate, list_templates
from app.generator.pretty import (
    as_exponential,
    has_special_function,
    has_ugly_fraction,
    mixes_function_families,
    ugliness,
)

# 每個 (模板, 難度) 組合要生成的題數。
# 平時 30 題約需兩分鐘；改動 SymPy 版本時可用 GEN_TEST_SAMPLES=200 跑完整回歸。
N_SAMPLES = int(os.environ.get("GEN_TEST_SAMPLES", "30"))

# 各難度的漂亮度上限
UGLINESS_LIMIT = {1: 25, 2: 35, 3: 45}

#: v0.30：平衡點分類題型的代號。
CLASSIFY_ID = "system.linear_2x2.classification"

CASES = [
    (tpl.template_id, difficulty)
    for tpl in list_templates()
    for difficulty in tpl.difficulties
]


@lru_cache(maxsize=None)
def _cached_sample(template_id: str, difficulty: int, n: int) -> tuple:
    """同一組 (題型, 難度, 題數) 只真的生成一次。

    ⚠️ **這是快取，不是省略。** 下面每一項測試都用同一個 `random.Random(f"{tid}-{d}")`
    起頭，所以它們拿到的本來就是**逐字相同**的那 N 題（`test_seed_is_reproducible`
    就是在守這件事）；在沒有快取的版本裡，那 N 題會被重新生成六次以上。

    加這一層的直接原因是 v0.24 的 Laplace 題型：它的驗證閘門要跑
    `sp.LaplaceTransform(...).doit()`，一題約 0.05–0.25 秒，重生六次就是
    整個測試檔多兩百秒。**測試變慢的真正代價不是等，是有人開始不跑它。**

    快取的東西是不可變的（`Problem` 生成後沒有任何一項測試會改它），
    所以共用是安全的；真要說有代價，是記憶體多留住幾百個 `Problem`。
    """
    rng = random.Random(f"{template_id}-{difficulty}")
    return tuple(
        generate(template_id, difficulty, seed=rng.randrange(1, 2**31 - 1))
        for _ in range(n)
    )


def _sample(template_id: str, difficulty: int, n: int = N_SAMPLES):
    return _cached_sample(template_id, difficulty, n)


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_the_gate_passes_for_every_generated_problem(template_id, difficulty):
    """**核心驗證閘門**：每一題都必須通過它自己的 `Verifier`。

    v0.25（2B0）之前這一項叫 `test_residual_is_zero`，而「驗證 = 算殘差」
    這件事寫死在它的訊息裡。Fourier 沒有殘差可以算（PLAN §2.10.1），
    所以改成問 `verify_answer()`，**並且把它回傳的原因印出來**——
    那個原因字串正是 `Verifier` 協定回傳它的理由。
    """
    for problem in _sample(template_id, difficulty):
        ok, reason = problem.verify_answer()
        assert ok, (
            f"沒過閘門：{template_id} d{difficulty} seed={problem.seed}\n"
            f"  題目：{problem.statement_latex}\n"
            f"  答案：{problem.answer_latex}\n"
            f"  原因：{reason}"
        )


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_answer_is_pretty(template_id, difficulty):
    """答案不得含特殊函數、未算完的積分，也不得有醜分數。

    ⚠️ **四種 `answer_kind` 走三條路，而分支是明示的**（§2.2.1、規則 4）：

    - `expression`     —— `ugliness()`，原本就是為它寫的
    - `implicit`       —— **與 `expression` 同一條路**（v0.27）。位勢函數 $F$
                          就是一個普通的算式，`ugliness()` 對它完全適用；
                          `base.AnswerKind` 那段說明寫了為什麼這裡刻意不分支
    - `coefficients`   —— 係數是對 $n$ 的表達式，門檻在 `ugliness_in_n()`，
                          由 `test_fourier_coefficients_are_pretty_in_n` 管；
                          這裡只驗「不含特殊函數與未算完的積分」那一半
    - `classification` —— `answer_expr` 是 `None`，整項不適用

    寫成一個 `if/elif/else` 而不是 `try/except`：後者在**應該檢查卻沒檢查到**
    的時候也一樣是綠的。

    ---

    ## ⚠️ v0.35：這裡曾經有一個明示的例外，而它隨題型一起走了

    `fourier.parseval.series_sum` 的答案是 $\pi^2/6$、$\pi^4/90$ 這一類
    **有名字的常數**，而 `has_ugly_fraction()` 看到分母 90 就會擋下來——
    那個啟發式在那個題型上**問錯了問題**。當時的作法是開一個明示的例外，
    再用一項更嚴格的測試接手（答案必須恰好是白名單上那四個常數之一）。

    ⚠️ **記在這裡是因為那個模式還會再用到**：一個「這個題型不檢查」的例外
    本身就是一個洞，所以它必須換來一項**更嚴格**的測試，而不是單純的豁免。
    """
    for problem in _sample(template_id, difficulty):
        ctx = f"{template_id} d{difficulty} seed={problem.seed}: {problem.answer_latex}"
        if problem.answer_kind == "classification":
            assert problem.answer_expr is None, f"分類題不該有 answer_expr — {ctx}"
            continue
        assert not has_special_function(problem.answer_expr), f"含特殊函數／未算完的積分 — {ctx}"
        if problem.answer_kind == "coefficients":
            continue
        assert not has_ugly_fraction(problem.answer_expr), f"含分母 > 12 的醜分數 — {ctx}"
        assert ugliness(problem.answer_expr) <= UGLINESS_LIMIT[difficulty], (
            f"漂亮度 {ugliness(problem.answer_expr)} > {UGLINESS_LIMIT[difficulty]} — {ctx}"
        )


# --- Parseval（v0.30，階段 2B 的 2B5）--------------------------------------


# --- 平衡點分類（v0.30，階段 2B 的 2B8）------------------------------------


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_equilibrium_type_is_what_the_difficulty_promises(difficulty):
    r"""⛔ **難度軸的唯一看守點。**

    難度說明對學生承諾了 d1 = 實相異、d2 = 複數、d3 = 邊界情形。
    一道分類正確、敘述正確、步驟正確的題目**可以完全不屬於它被放進去的
    那個難度**——而那時每一題都仍然是對的，只是「難度 3 練得到退化節點」
    這件事悄悄變成假的。

    ⚠️ 這與 `test_resonance_is_present_exactly_where_the_difficulty_says_it_is`
    （待定係數的共振重數）是同一型的看守：**閘門對難度沒有意見，所以難度
    需要自己的測試。**
    """
    from app.generator import plot
    from app.generator.systems.classify import types_for

    allowed = set(types_for(difficulty))
    seen = set()
    for problem in _sample(CLASSIFY_ID, difficulty):
        A = problem.params["A"]
        label = plot.classify(A)
        assert label in allowed, (
            f"難度 {difficulty} 出了 {label}，而這個難度只有 {sorted(allowed)}"
            f"（seed={problem.seed}）"
        )
        seen.add(label)
    # 每一格都要抽得到，否則「這個難度涵蓋 N 種」是一句空話。
    assert seen == allowed, f"難度 {difficulty} 沒有抽到：{sorted(allowed - seen)}"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_two_classification_paths_agree_on_every_generated_matrix(difficulty):
    r"""查表（$\operatorname{tr}$、$\det$、$\Delta$）與特徵值兩條路必須一致。

    `tests/test_plot.py` 已經在 19 個手挑的矩陣上比過這兩條路；這一項的差別是
    **它比的是真的被出出來的那些矩陣**。手挑的集合證明不了生成器不會造出一個
    落在兩條路分歧處的矩陣——而那正是「手挑的樣本」與「產品的樣本」之間
    反覆出現的落差（v0.26 相圖的容差就是這樣量錯過一次）。
    """
    from app.generator import plot
    from app.generator.systems.classify import classify_by_eigenvalues

    for problem in _sample(CLASSIFY_ID, difficulty):
        A = problem.params["A"]
        assert plot.classify(A) == classify_by_eigenvalues(A), (
            f"兩條路對 {A.tolist()} 不一致（seed={problem.seed}）"
        )


def test_a_star_node_is_never_reported_as_a_degenerate_one():
    r"""星形節點與退化節點都是 $\Delta = 0$，但幾何完全不同。

    星形（$A = \lambda I$）的每一個向量都是特徵向量；退化只有一個特徵方向。
    ⛔ **把兩者合成一格會讓 `plot.classify()` 裡那個 `b == 0 and c == 0`
    的分辨沒有人在用**，而它是分辨這兩者的唯一根據。
    """
    from app.generator import plot

    star_seen = degenerate_seen = 0
    for problem in _sample(CLASSIFY_ID, 3):
        A = problem.params["A"]
        label = plot.classify(A)
        if label in (plot.STABLE_STAR_NODE, plot.UNSTABLE_STAR_NODE):
            assert A[0, 1] == 0 and A[1, 0] == 0, f"星形節點不是 λI：{A.tolist()}"
            assert len((A - A[0, 0] * sp.eye(2)).nullspace()) == 2
            star_seen += 1
        elif label in (plot.STABLE_DEGENERATE_NODE,
                       plot.UNSTABLE_DEGENERATE_NODE):
            lam = list(A.eigenvals())[0]
            assert len((A - lam * sp.eye(2)).nullspace()) == 1, (
                f"退化節點卻有兩個特徵方向：{A.tolist()}"
            )
            degenerate_seen += 1
    assert star_seen and degenerate_seen, (
        f"樣本裡缺一種（星形 {star_seen}、退化 {degenerate_seen}）"
    )


def test_the_classification_gate_rejects_a_mismatched_claim():
    r"""**突變測試**：宣稱一個錯的類型，閘門必須說不。

    這裡改的是 `claimed`，模擬的是「反向構造造出了別的東西」——
    這個題型真正的風險（見 `classify.py` 檔頭）。
    """
    from app.generator import plot
    from app.generator.systems.classify import ClassificationCheck

    problem = generate(CLASSIFY_ID, 1, seed=20260903)
    A = problem.params["A"]
    truth = plot.classify(A)
    wrong = next(t for t in (plot.SADDLE, plot.STABLE_NODE, plot.UNSTABLE_NODE)
                 if t != truth)

    ok, reason = ClassificationCheck(A=A, claimed=wrong, difficulty=1).verify(problem)
    assert not ok and "閘門一" in reason, reason

    # 對的類型但放錯難度 → 第三層擋下來
    ok, reason = ClassificationCheck(A=A, claimed=truth, difficulty=3).verify(problem)
    assert not ok and "閘門三" in reason, reason


def test_answer_kind_and_answer_expr_agree_everywhere():
    """`answer_expr is None` 與 `answer_kind == "classification"` 必須同進同出。

    這一項守的是 2B0 那個約定的**兩個方向**。只驗一個方向的話，
    一個忘了設 `answer_kind` 的分類題會安靜地被當成算式題送進
    `ugliness()`，然後在 `None` 上炸掉——那還算好的；反過來
    （設了 `classification` 卻留著算式）會讓上面那一項整個跳過，
    **而跳過是沒有聲音的**。
    """
    for template_id, difficulty in CASES:
        for problem in _sample(template_id, difficulty, n=3):
            ctx = f"{template_id} d{difficulty} seed={problem.seed}"
            assert (problem.answer_expr is None) == (
                problem.answer_kind == "classification"), ctx


def _numbers(expr) -> list[sp.Rational]:
    if isinstance(expr, sp.MatrixBase):
        atoms = set().union(*(e.atoms(sp.Number) for e in expr)) if len(expr) else set()
    else:
        atoms = expr.atoms(sp.Number)
    return [n for n in atoms if n.is_Rational]


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_separable_coefficients_in_range(difficulty):
    """f(x) 與 g(y) 的係數必須是絕對值 ≤ 3 的整數。"""
    for problem in _sample("ode.first_order.separable", difficulty):
        f_x = sp.sympify(problem.params["f"])
        ctx = f"d{difficulty} seed={problem.seed}: {problem.statement_latex}"
        for n in _numbers(f_x):
            assert n.is_Integer and abs(n) <= 3, f"f(x) 係數超出範圍 {n} — {ctx}"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_linear_coefficients_in_range(difficulty):
    """p(x) 與 q(x) 的係數必須是絕對值 ≤ 3 的整數。"""
    for problem in _sample("ode.first_order.linear", difficulty):
        ctx = f"d{difficulty} seed={problem.seed}: {problem.statement_latex}"
        for key in ("p", "q"):
            for n in _numbers(sp.sympify(problem.params[key])):
                assert n.is_Integer and abs(n) <= 3, f"{key} 係數超出範圍 {n} — {ctx}"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_second_order_roots_in_range(difficulty):
    """特徵根必須落在白名單內，且不得為 0（否則退化成一階）。"""
    for problem in _sample("ode.second_order.homogeneous", difficulty):
        p = problem.params
        ctx = f"d{difficulty} seed={problem.seed}: {problem.statement_latex}"
        if p["case"] == "real_distinct":
            assert p["r1"] != p["r2"], ctx
            assert all(0 < abs(p[k]) <= 3 for k in ("r1", "r2")), ctx
        elif p["case"] == "repeated":
            assert 0 < abs(p["r"]) <= 3, ctx
        else:
            assert abs(p["alpha"]) <= 2 and 1 <= p["beta"] <= 3, ctx


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_system_matrix_is_small_integer(difficulty):
    """A 必為整數矩陣、元素夠小、特徵值相異且非零，且不是對角矩陣。"""
    bound = {1: 5, 2: 9, 3: 7}[difficulty]
    for problem in _sample("system.linear_2x2.real_distinct", difficulty):
        A = problem.params["A"]
        lam = problem.params["eigenvalues"]
        ctx = f"d{difficulty} seed={problem.seed}: A={A}, λ={lam}"
        flat = [c for row in A for c in row]
        assert all(isinstance(c, int) for c in flat), f"A 不是整數矩陣 — {ctx}"
        assert max(abs(c) for c in flat) <= bound, f"A 元素超出上限 {bound} — {ctx}"
        assert lam[0] != lam[1], f"特徵值不相異 — {ctx}"
        assert all(0 < abs(v) <= 3 for v in lam), f"特徵值超出範圍 — {ctx}"
        assert not (A[0][1] == 0 and A[1][0] == 0), f"A 是對角矩陣 — {ctx}"
        # 難度 1 為三角矩陣、難度 2/3 兩個非對角元素都不為 0
        triangular = A[0][1] == 0 or A[1][0] == 0
        assert triangular == (difficulty == 1), f"矩陣形狀與難度不符 — {ctx}"


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_steps_are_complete(template_id, difficulty):
    """逐步解答必須非空，且最後一步的內容就是答案。"""
    for problem in _sample(template_id, difficulty):
        ctx = f"{template_id} d{difficulty} seed={problem.seed}"
        assert len(problem.steps) >= 3, f"步驟太少 — {ctx}"
        assert all(s.title for s in problem.steps), f"有步驟沒有標題 — {ctx}"

        if problem.answer_kind in ("classification", "implicit"):
            # 分類題的答案是一句判斷，沒有「等號右邊」可以比。要守的東西沒有變
            # ——答案與最後一步不可以各寫一遍然後漂移——所以改成**逐字相等**。
            #
            # ⚠️ **隱式解走同一條路，而理由不同、但更迫切**（v0.27）：
            # 它的等號右邊永遠是 $C_1$，所以下面那個「比等號右邊」的作法
            # **會恆真**——任何一個以 `= C_1` 結尾的步驟都能讓它通過，
            # 包括一個算錯的位勢函數。逐字比對才真的在守東西。
            assert problem.answer_latex in [s.latex for s in problem.steps], (
                f"答案沒有出現在任何一步裡 — {ctx}"
            )
            continue

        # 最後一個「有算式」的步驟應該就是答案本身
        answer_body = problem.answer_latex.split("=", 1)[-1].strip()
        bodies = [s.latex.split("=")[-1].strip() for s in problem.steps if s.latex]
        assert answer_body in bodies, f"最後一步與答案對不起來 — {ctx}"


#: KaTeX 真的不支援的環境。
#:
#: ⚠️ **`\begin{cases}` 在 v0.25 從這份清單移到下面那一份**，因為
#: 「KaTeX 不支援 cases」這句話**是錯的**：本專案自架的 KaTeX 0.16.11
#: 支援它（`defineEnvironment` 的 `names:["cases"]`），本輪用 node 載入
#: `app/static/vendor/katex/katex.min.js` 實際渲染過，而且
#: `test_every_formula_renders_in_the_bundled_katex` 每次測試都會再確認一次。
#:
#: 那 Laplace 為什麼還是不准用它？**理由不一樣，而且那個理由沒有變**：
#: `ode/laplace.py` 難度 3 的 `answer_expr` 是 `Piecewise`（閘門形），
#: 顯示形必須是 $u(t-a)$。一旦 `\begin{cases}` 出現在那個題型的輸出裡，
#: 就代表有人把閘門形拿去 `sp.latex()` 了——**那是一個真的 bug 的徵兆**，
#: 只是它以前借用了一句錯誤的理由被擋著。
KATEX_UNSUPPORTED = ("\\begin{align}", "\\intertext", "\\newcommand")

#: 只有 Fourier 那三個題型可以印 `\begin{cases}`（分段定義的 $f$）。
CASES_ALLOWED_PREFIX = "fourier."


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_latex_is_katex_safe(template_id, difficulty):
    """避免用到 KaTeX 不支援的環境。"""
    for problem in _sample(template_id, difficulty, n=5):
        blob = problem.statement_latex + problem.answer_latex + "".join(
            s.latex for s in problem.steps
        )
        for token in KATEX_UNSUPPORTED:
            assert token not in blob, f"{template_id} d{difficulty} 用到 {token}"
        if not template_id.startswith(CASES_ALLOWED_PREFIX):
            assert "\\begin{cases}" not in blob, (
                f"{template_id} d{difficulty} 出現 \\begin{{cases}}——"
                "非 Fourier 的題型出現它，通常代表有人把驗證閘門用的 "
                "Piecewise 拿去 sp.latex() 了"
            )


# --- 顯示形式的一致性（PLAN.md §2.9）---------------------------------------
#
# 這一組守的不是數學正確性（那由 test_residual_is_zero 守），而是「同一題的答案
# 只能用一套函數族書寫」。原本的症狀：線性系統帶初值、特徵值恰為 ±1 時，
# sp.simplify 把一個分量寫成 3e^t − 5e^{-t}、另一個寫成 11 sinh t + cosh t。
# 兩者都對，判定也不受影響，只是學生會以為自己算錯了——所以它不會拋錯、
# 只會讓人困惑，正是最需要測試盯著的那種缺陷。

@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_answer_does_not_mix_function_families(template_id, difficulty):
    """同一個答案裡不得同時出現指數與雙曲函數。"""
    for problem in _sample(template_id, difficulty):
        if problem.answer_kind == "classification":
            continue                       # 沒有算式（明示分支，見 §2.2.1）
        assert not mixes_function_families(problem.answer_expr), (
            f"答案混用了指數與雙曲寫法：{template_id} d{difficulty} "
            f"seed={problem.seed}\n  答案：{problem.answer_latex}"
        )


#: 全部四個線性系統題型。**用字首篩而不是手寫清單**：手寫的那份會在
#: 新增第五個題型時安靜地漏掉它，而漏掉的症狀是「那個題型沒有被檢查」。
SYSTEM_TEMPLATES = sorted(
    tpl.template_id for tpl in list_templates()
    if tpl.template_id.startswith("system.")
)


@pytest.mark.parametrize("template_id", SYSTEM_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_system_answers_are_written_with_exponentials(template_id, difficulty):
    """線性系統的答案與逐步解答一律是指數形式。

    逐步解答從特徵值一路寫到 $\\sum_i C_i e^{\\lambda_i t}\\mathbf{v}_i$，
    最後一行不能突然換成 sinh／cosh。

    ⚠️ **v0.26 把範圍從一個題型擴大到四個**（附錄 C.2 那一列的原文就是
    「一階線性系統」，不是「實相異的那一個」）。複數特徵值那一格的
    $\\sin/\\cos$ **不在此限**——附錄 C.2 明文寫著實數形的三角函數是標準寫法，
    而下面那一項 `test_complex_system_answers_are_real_valued` 才是管它的。
    """
    for problem in _sample(template_id, difficulty):
        blob = problem.answer_latex + "".join(s.latex for s in problem.steps)
        for name in ("sinh", "cosh", "tanh"):
            assert name not in blob, (
                f"系統題出現 {name}：{template_id} d{difficulty} seed={problem.seed}\n"
                f"  答案：{problem.answer_latex}"
            )


def test_as_exponential_leaves_trigonometric_answers_alone():
    """只改寫雙曲函數。二階複數根的 $e^{\\alpha x}(C_1\\cos\\beta x + \\dots)$
    是這門課的標準寫法，改寫成複指數才是真的難看。"""
    x = sp.Symbol("x")
    trig = sp.exp(-x) * (sp.cos(2 * x) + sp.sin(2 * x))
    assert as_exponential(trig) == trig

    hyperbolic = 3 * sp.sinh(x) + sp.cosh(x)
    rewritten = as_exponential(hyperbolic)
    assert not rewritten.has(sp.sinh, sp.cosh)
    assert sp.simplify(rewritten - hyperbolic) == 0        # 只換寫法，不換內容


# --- 線性系統的其餘兩種情況（v0.26，階段 2A 的 2d）------------------------
#
# 每題都要跑的驗證閘門不在這裡（`test_the_gate_passes_for_every_generated_problem`
# 對這兩個題型一樣適用，`CASES` 是從註冊表展開的）。這一組管的是**閘門看不到的
# 東西**——殘差為 0 完全不代表逐步解答裡印出來的中間量是對的。
#
# ⚠️ **v0.35：第三種情況（非齊次）連同它的三項測試已由老師刪除。**

REPEATED_ID = "system.linear_2x2.repeated"
COMPLEX_ID = "system.linear_2x2.complex"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_complex_system_answers_are_real_valued(difficulty):
    r"""⛔ 複數特徵值的答案必須是**實數形**（D11 在 v0.26 擴充到的那一格）。

    $\mathbf{x} = C_1 e^{(\alpha + i\beta)t}\mathbf{v}$ 數學上完全正確，
    殘差是 0，**驗證閘門會放行**——所以這件事只有靠一項專門的測試守得住。

    檢查的是 `answer_expr` 裡有沒有 `sp.I`，**不是** LaTeX 字串裡有沒有 `i`：
    後者會被 `\sin` 這個字裡的 `i` 弄成假警報，而為了繞過假警報而放寬的
    字串比對通常最後什麼都擋不住。
    """
    for problem in _sample(COMPLEX_ID, difficulty):
        ctx = f"d{difficulty} seed={problem.seed}: {problem.answer_latex}"
        assert not problem.answer_expr.has(sp.I), f"答案含虛數單位 — {ctx}"
        for step in problem.steps:
            assert "sinh" not in step.latex and "cosh" not in step.latex, ctx


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_answer_never_uses_the_amplitude_phase_form(difficulty):
    r"""三角函數的引數必須恰好是 $\beta t$，不得出現相位平移。

    **這一項是實測抓回來的，不是預想的。** 難度 3 原本走
    `sp.simplify(sol.subs(constants))`，而 SymPy 依它自己的評分把
    $a\cos 2t + b\sin 2t$ 併成 $-2\sqrt{2}\,e^{t}\sin\!\left(2t +
    \frac{\pi}{4}\right)$——數學上完全正確、殘差是 0、閘門放行，
    但那是**第三種**書寫方式（振幅－相位形），而逐步解答從第 4 步
    一路寫的都是 $\cos$ 與 $\sin$ 的線性組合。

    這與 D11 那個 $\sinh/\cosh$ 的症狀是同一件事（§2.9：同一題的不同部分
    用了不同的寫法），只是換了一個函數族——所以它與那一組測試放在一起。
    """
    for problem in _sample(COMPLEX_ID, difficulty):
        beta = problem.params["beta"]
        var = problem.check.var
        expected = beta * var
        for component in problem.answer_expr:
            for node in component.atoms(sp.sin, sp.cos):
                assert node.args[0] == expected, (
                    f"三角函數的引數不是 β t：d{difficulty} "
                    f"seed={problem.seed} 得到 {node}\n"
                    f"  答案：{problem.answer_latex}"
                )


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_complex_pair_really_is_the_alpha_beta_that_was_advertised(difficulty):
    r"""$A$ 的特徵值必須恰好是 `params` 裡宣稱的 $\alpha \pm \beta i$。

    這是一條**獨立的路**：`params` 來自我們挑的 $R$，這裡問的是 SymPy 對
    $A = PRP^{-1}$ 算出來的特徵值。$P^{-1}$ 算錯、$R$ 的正負號寫反這類事
    都會在這裡現形，而它們**不會**讓殘差不為 0（相似變換之後仍然是一個
    合法的線性系統，只是不是我們以為的那一個）。
    """
    for problem in _sample(COMPLEX_ID, difficulty, n=10):
        A = sp.Matrix(problem.params["A"])
        alpha, beta = problem.params["alpha"], problem.params["beta"]
        ctx = f"d{difficulty} seed={problem.seed}: A={problem.params['A']}"
        assert (A.trace() ** 2 - 4 * A.det()) < 0, f"判別式不是負的 — {ctx}"
        assert set(A.eigenvals()) == {alpha + beta * sp.I, alpha - beta * sp.I}, ctx
        assert beta > 0, f"β 必須為正（實數基底的公式假設它為正）— {ctx}"
        if difficulty == 1:
            assert alpha == 0, f"難度 1 應該是中心（α = 0）— {ctx}"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_generalized_eigenvector_really_satisfies_its_defining_equation(difficulty):
    r"""重根那一格：$(A-\lambda I)\mathbf{v} = \mathbf{0}$ 且
    $(A-\lambda I)\mathbf{w} = \mathbf{v}$。

    ⛔ **這一項守的是逐步解答，不是答案。** 第 4 步印出一個 $\mathbf{w}$
    並且寫著它滿足 $(A-\lambda I)\mathbf{w} = \mathbf{v}$；若正負號在
    正規化的時候只翻了一半，那一行就變成假的——而**答案的殘差照樣是 0**
    （$-\mathbf{v}$ 也是特徵向量），閘門一句話都不會說。
    """
    for problem in _sample(REPEATED_ID, difficulty, n=10):
        A = sp.Matrix(problem.params["A"])
        lam = problem.params["eigenvalues"][0]
        v = sp.Matrix(problem.params["v"])
        w = sp.Matrix(problem.params["w"])
        ctx = f"d{difficulty} seed={problem.seed}: A={problem.params['A']}, λ={lam}"
        M = A - lam * sp.eye(2)
        assert (M * v) == sp.zeros(2, 1), f"v 不是特徵向量 — {ctx}"
        assert (M * w) == v, f"w 不滿足 (A-λI)w = v — {ctx}"
        assert sp.Matrix.hstack(v, w).det() != 0, f"v 與 w 線性相依 — {ctx}"
        # 逐步解答印的就是這兩個向量，所以它們也得真的出現在裡面
        blob = "".join(s.latex for s in problem.steps)
        assert sp.latex(v, mat_delim="(") in blob, f"v 沒有印在步驟裡 — {ctx}"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_repeated_case_is_really_defective(difficulty):
    r"""重根必須是**缺陷**的：代數重數 2、幾何重數 1。

    若 $A = \lambda I$，每個向量都是特徵向量，「廣義特徵向量」這一步整個
    沒有意義——而那樣的題目看起來完全正常（$\Delta = 0$、答案也對），
    只是它教不到這個題型要教的東西。
    """
    for problem in _sample(REPEATED_ID, difficulty, n=10):
        A = sp.Matrix(problem.params["A"])
        ctx = f"d{difficulty} seed={problem.seed}: A={problem.params['A']}"
        assert (A.trace() ** 2 - 4 * A.det()) == 0, f"判別式不是 0 — {ctx}"
        vects = A.eigenvects()
        assert len(vects) == 1, f"不是重根 — {ctx}"
        lam, algebraic, basis = vects[0]
        assert algebraic == 2, f"代數重數不是 2 — {ctx}"
        assert len(basis) == 1, f"幾何重數不是 1（矩陣沒有缺陷）— {ctx}"
        flat = [c for row in problem.params["A"] for c in row]
        assert max(abs(c) for c in flat) <= {1: 6, 2: 9, 3: 8}[difficulty], ctx
        triangular = A[0, 1] == 0 or A[1, 0] == 0
        assert triangular == (difficulty == 1), f"矩陣形狀與難度不符 — {ctx}"


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_seed_is_reproducible(template_id, difficulty):
    """同一個 seed 必須生出完全相同的題目（紀錄可重現）。"""
    a = generate(template_id, difficulty, seed=20260807)
    b = generate(template_id, difficulty, seed=20260807)
    assert a.statement_latex == b.statement_latex
    assert a.answer_latex == b.answer_latex


def test_registry_is_wired_up():
    """所有題型都要在註冊表裡，且每個都有顯示名稱與難度說明。"""
    ids = {t.template_id for t in list_templates()}
    # ⛔ 寫死的清單，不是「有幾個就幾個」。少一個或多一個都要有人回來改這裡，
    # 而那正是它存在的意義——⚠️ **v0.35 由 16 個降為 11 個**（老師刪了五個
    # 題型，見那一輪的 dispatch），而這一項是當時第一個變紅的東西。
    assert ids == {
        "ode.first_order.separable",
        "ode.first_order.linear",
        "ode.second_order.homogeneous",
        "system.linear_2x2.real_distinct",
        # v0.24（階段 2A 的 2f）。
        "ode.laplace.transform",
        "ode.laplace.ivp",
        # v0.25（階段 2B 的 2B2–2B3）。兩個都住在 `app/generator/fourier/`。
        "fourier.series.full_range",
        "fourier.series.half_range",
        # v0.26（階段 2A 的 2d）。⚠️ 這兩個與 `system.linear_2x2.real_distinct`
        # 住在不同的檔案裡，**而註冊表看不出差別**——因為 `template_id`
        # 與檔案路徑從來沒有耦合過（D16）。
        "system.linear_2x2.repeated",
        "system.linear_2x2.complex",
        # v0.30（階段 2B 的 2B8）。
        "system.linear_2x2.classification",
    }
    for tpl in list_templates():
        assert tpl.name and tpl.chapter
        assert set(tpl.difficulties) <= set(DIFFICULTY_LABELS)
        for d in tpl.difficulties:
            assert tpl.difficulty_notes.get(d), f"{tpl.template_id} 缺難度 {d} 的說明"


# --- 拉普拉斯變換（v0.24，階段 2A 的 2f）----------------------------------
#
# 這一組分成三件事，一件比一件不明顯：
#
#   1. 符號合不合附錄 C.3（純字串黑名單，最容易測）
#   2. 我們手寫的變換表對不對（拿**定義的積分**去證，這是最強的一條路）
#   3. 難度 3 那三個形狀的答案是同一個函數（顯示形／精確形／閘門形）
#
# 每題都要跑的驗證閘門不在這裡——它在 `test_residual_is_zero`，
# 對這兩個題型一樣適用（`CASES` 是從註冊表展開的）。

LAPLACE_TEMPLATES = ("ode.laplace.transform", "ode.laplace.ivp")

#: 附錄 C.3 的防回頭黑名單。每一項都是**改對之後最容易被順手改回去**的那種東西，
#: 而它們的共同點是不會壞掉任何功能——頁面照樣渲染，只是換了一種語言。
FORBIDDEN_NOTATION = (
    r"\mathcal{L}",                     # v0.9 從規範降級成禁用
    r"\operatorname{LaplaceTransform}",  # sp.latex() 的預設輸出
    r"\theta(",                         # sp.latex(Heaviside) 的預設輸出
    r"\theta{",                         # 同上，帶大括號的形式
    "F(s)",                             # C.3：像函數不寫成 F(s)
    "Y(s)",
    r"\dot{",                           # 本課程不用點記號
    "Heaviside",                        # srepr 洩漏
    "DiracDelta",
)


def _all_display_text(problem) -> str:
    """一題裡所有會被學生看到的字。"""
    return "\n".join(
        [problem.statement, problem.statement_latex, problem.answer_latex]
        + [s.title for s in problem.steps]
        + [s.latex for s in problem.steps]
        + [s.note for s in problem.steps]
    )


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_notation_blacklist_of_appendix_c(template_id, difficulty):
    """附錄 C.3 的黑名單對**所有**題型成立，不只 Laplace 那兩個。

    對既有四個題型而言這一項本來就會過；留著它們是因為黑名單的價值在於
    「日後任何人寫的任何一步都不會溜過去」，而把範圍縮到 Laplace
    等於預先假設只有那裡會出錯。
    """
    for problem in _sample(template_id, difficulty, n=5):
        blob = _all_display_text(problem)
        for token in FORBIDDEN_NOTATION:
            assert token not in blob, (
                f"{template_id} d{difficulty} seed={problem.seed} 出現 {token!r}"
            )


@pytest.mark.parametrize("template_id", LAPLACE_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_laplace_writes_the_transform_as_L_braces(template_id, difficulty):
    r"""C.3 的正面條款：變換一定要寫成 ``L\{...\}``。

    與上面的黑名單互補。只有黑名單的話，一個把變換符號整段刪掉的改動
    會全綠——「沒有寫錯」與「有寫」是兩件事。
    """
    for problem in _sample(template_id, difficulty, n=5):
        blob = _all_display_text(problem)
        assert r"L\{" in blob, (
            f"{template_id} d{difficulty} seed={problem.seed} 完全沒有出現 L\\{{...\\}}"
        )


def test_the_transform_table_agrees_with_the_defining_integral():
    r"""**最強的那一條獨立路徑**：手寫的表 vs $\int_0^\infty f e^{-st}dt$。

    出題用的表在 `app/generator/ode/laplace.py` 裡是硬寫的（`_pair_*`），
    每題的閘門用的是 SymPy 的規則引擎——兩者都是「查表」，
    所以它們**有可能一起錯**。這一項把表釘在定義上，
    那是唯一一條與任何表都無關的路。

    刻意只跑一次、只跑基本函數：定義的積分在複雜一點的組合上
    要好幾秒、甚至算不出來（見該模組的檔頭），所以它適合當一次性的錨，
    不適合當每題都跑的閘門。
    """
    from app.generator.ode import laplace as lp

    pairs = (
        [lp._pair_one()]
        + [lp._pair_power(n) for n in (1, 2, 3)]
        + [lp._pair_exp(a) for a in (-3, -1, 1, 2)]
        + [lp._pair_sin(w) for w in (1, 2, 3)]
        + [lp._pair_cos(w) for w in (1, 2, 3)]
    )
    for pair in pairs:
        by_definition = sp.integrate(
            pair.time * sp.exp(-lp.s * lp.t), (lp.t, 0, sp.oo), conds="none"
        )
        assert sp.simplify(by_definition - pair.freq) == 0, (
            f"表與定義的積分不符：L{{{pair.time}}} 表說 {pair.freq}，"
            f"定義的積分說 {sp.simplify(by_definition)}"
        )


def test_the_two_shifting_theorems_agree_with_the_defining_integral():
    r"""兩個位移定理也要釘在定義上，理由與上一項相同。

    分開成兩項是因為它們會用不同的方式壞掉：表錯了是一格數字錯，
    位移定理錯了是**每一題的同一個位置**都錯（例如把 $e^{-as}$ 寫成 $e^{as}$），
    而後者在難度 3 的每一題裡都出現。
    """
    from app.generator.ode import laplace as lp

    t, s = lp.t, lp.s
    for base in (lp._pair_power(2), lp._pair_sin(2), lp._pair_cos(3)):
        for a in (-2, 2):
            # 第一位移定理：L{e^{at}g(t)} = G(s-a)
            claimed = base.freq.subs(s, s - a)
            actual = sp.integrate(
                sp.exp(a * t) * base.time * sp.exp(-s * t), (t, 0, sp.oo),
                conds="none",
            )
            assert sp.simplify(actual - claimed) == 0, f"s 域位移錯了：{base.time}, a={a}"
        for c in (1, 2):
            # 第二位移定理：L{u(t-c)g(t-c)} = e^{-cs}G(s)
            claimed = sp.exp(-c * s) * base.freq
            actual = sp.integrate(
                sp.Heaviside(t - c) * base.time.subs(t, t - c) * sp.exp(-s * t),
                (t, 0, sp.oo), conds="none",
            )
            assert sp.simplify(actual - claimed) == 0, f"t 域位移錯了：{base.time}, c={c}"


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_laplace_transform_coefficients_are_small_integers(difficulty):
    """題目與答案裡的參數必須落在白名單內（§2.3 第二層）。"""
    for problem in _sample("ode.laplace.transform", difficulty):
        p = problem.params
        ctx = f"d{difficulty} seed={problem.seed}: {problem.statement_latex}"
        for c in p["coefficients"]:
            assert isinstance(c, int) and 0 < abs(c) <= 5, f"係數超出範圍 {c} — {ctx}"
        if difficulty == 3:
            assert 0 < abs(p["alpha"]) <= 3, ctx
            assert p["delay"] in (1, 2, 3), ctx
        if difficulty == 2:
            assert p["case"] in ("distinct", "repeated", "complex"), ctx


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_laplace_ivp_coefficients_are_small_integers(difficulty):
    """ODE 的係數、初值、外力強度都要是小整數。

    外力那一項是最值得盯的：它是**倒推出來的**（先挑答案再算外力），
    所以它是唯一一個可以在不違反任何數學的情況下長到 90 的量。
    """
    for problem in _sample("ode.laplace.ivp", difficulty):
        p = problem.params
        ctx = f"d{difficulty} seed={problem.seed}: {problem.statement_latex}"
        assert p["order"] == (1 if difficulty == 1 else 2), ctx
        # a1、a0 的上限不是一個統一的數字，因為它們是由根算出來的：
        # 實根是 -(r1+r2) 與 r1·r2（≤ 9），複數根是 -2α 與 α²+β²（≤ 13）。
        # 寫成一個「反正 15 都夠」的鬆界限會讓這一項幾乎擋不住東西。
        if p["case"] == "complex":
            assert abs(p["a1"]) == 2 * abs(p["alpha"]), ctx
            assert p["a0"] == p["alpha"] ** 2 + p["beta"] ** 2, ctx
        elif p["case"] == "first_order":
            assert p["a1"] == 0 and 0 < abs(p["a0"]) <= 3, ctx
        else:
            r1, r2 = p["roots"]
            assert p["a1"] == -(r1 + r2) and p["a0"] == r1 * r2, ctx
        assert abs(p["y0"]) <= 9, ctx
        if p["y1"] is not None:
            assert abs(p["y1"]) <= 12, ctx
        if p["case"] == "step":
            assert p["delay"] in (1, 2, 3), ctx
            assert 0 < abs(p["step_height"]) <= 8, ctx
        else:
            assert 0 < abs(p["forcing_coeff"]) <= 12, ctx
        if p["case"] == "complex":
            assert 0 < abs(p["alpha"]) <= 2 and 1 <= p["beta"] <= 3, ctx
        else:
            assert all(0 < abs(r) <= 3 for r in p["roots"]), ctx


#: `\frac{7}{6}` 這種**分子分母都是數字**的片段。`\frac{1}{s + 2}` 不會match，
#: 因為它的分母不是數字——這正是我們要的分辨方式。
NUMERIC_FRACTION = re.compile(r"\\frac\{(\d+)\}\{(\d+)\}")


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_no_step_shows_an_ugly_number(template_id, difficulty):
    """**中間步驟**也不得出現分母 > 12 的數字係數。

    這一項與 `test_answer_is_pretty` **不重複**：那一項看的是最後的答案，
    這一項看的是路上。反向構造保證答案漂亮，但 `sp.apart()` 之類的中間量
    是實際算出來的——一組漂亮的答案完全可能經過一個分母 35 的中間步驟，
    而學生真正要動手算的正是那一步。
    """
    from app.generator.pretty import MAX_DENOMINATOR

    for problem in _sample(template_id, difficulty, n=min(N_SAMPLES, 15)):
        for step in problem.steps:
            for _, denominator in NUMERIC_FRACTION.findall(step.latex):
                assert int(denominator) <= MAX_DENOMINATOR, (
                    f"{template_id} d{difficulty} seed={problem.seed} 的"
                    f"「{step.title}」出現分母 {denominator}：{step.latex}"
                )


#: 哪幾格**一定**要有部分分式那一步。
#: 寫成一份明確的清單而不是「有就檢查」：後者在部分分式被整段刪掉時會全綠。
#: 正變換的兩格（transform d1、d3）本來就沒有這一步，它們不在清單上。
PARTIAL_FRACTION_CASES = [
    ("ode.laplace.transform", 2),
    ("ode.laplace.ivp", 1),
    ("ode.laplace.ivp", 2),
    ("ode.laplace.ivp", 3),
]


@pytest.mark.parametrize("template_id,difficulty", PARTIAL_FRACTION_CASES)
def test_partial_fractions_really_are_a_step(template_id, difficulty):
    """部分分式是反變換的主要技術障礙，所以它必須是**自己的一步**。"""
    for problem in _sample(template_id, difficulty, n=5):
        titles = [s.title.lower() for s in problem.steps]
        assert any("partial fraction" in title for title in titles), (
            f"{template_id} d{difficulty} seed={problem.seed} 少了部分分式那一步："
            f"{titles}"
        )


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_laplace_ivp_answers_have_no_distributions(difficulty):
    """答案裡不得出現 δ 函數。

    這不是排版偏好，是檔頭那個決定的看守點：脈衝外力**刻意沒有做**，
    因為 `Piecewise` 的微分會安靜地吃掉跳躍，閘門會對錯的答案說通過。
    哪天有人加了脈衝的題目，這一項會先變紅。
    """
    for problem in _sample("ode.laplace.ivp", difficulty, n=5):
        assert not problem.answer_expr.has(sp.DiracDelta), (
            f"d{difficulty} seed={problem.seed}: {problem.answer_latex}"
        )


def test_the_delayed_answer_has_one_meaning_in_all_three_forms():
    r"""難度 3 的答案有三個形狀，這一項把它們串起來。

    - **顯示形**：$u(t-a)$ 與 $(t-a)$，印給學生看（含替身符號 `tau_shift`）
    - **精確形**：把替身換回 $t-a$ 之後的真實算式
    - **閘門形**：`Piecewise`，`answer_expr`，驗證閘門看的就是它

    三者必須是同一個函數。這是本題型唯一一處「同一件事寫了兩遍」的地方
    （顯示不能用 `Piecewise`——KaTeX 沒有 `cases`；閘門不能用 `Heaviside`
    ——微分會生出一個化簡不掉的 δ），所以它也是唯一一處會漂移的地方。

    ⚠️ 這一項刻意在**跳點兩側**都取樣。只在 $t > a$ 取樣的話，
    一個把 $u(t-a)$ 整個漏掉的錯誤會完全看不出來。
    """
    from app.generator.ode.laplace import _SHIFT, t as t_sym

    for problem in _sample("ode.laplace.ivp", 3, n=min(N_SAMPLES, 12)):
        p = problem.params
        c = p["delay"]
        display = sp.sympify(p["answer_display_srepr"])
        exact = sp.sympify(p["answer_exact_srepr"])
        ctx = f"seed={problem.seed}: {problem.answer_latex}"

        # 顯示形換回真實的位移之後，就是精確形
        assert sp.simplify(display.subs(_SHIFT, t_sym - c) - exact) == 0, (
            f"顯示形與精確形不一致 — {ctx}"
        )

        # 精確形與閘門形在跳點兩側都要一樣
        for value in (sp.Rational(1, 2), c - sp.Rational(1, 4),
                      c + sp.Rational(1, 4), c + 2):
            a = complex(sp.N(exact.subs(t_sym, value)))
            b = complex(sp.N(problem.answer_expr.subs(t_sym, value)))
            assert abs(a - b) < 1e-9, f"t={value} 時兩形不一致（{a} vs {b}）— {ctx}"

        # 步階響應在自己的開關時刻必須是「零位置、零速度」。
        # 這是「可以用 Piecewise 當閘門形」的前提，而且它是一個**精確**的
        # 敘述，所以這裡精確地驗——不是用一個要調容差的數值極限去逼近它。
        # 不成立的話 y 或 y' 會在 t=a 跳，y'' 裡就有一個真的 δ，
        # 而 Piecewise 的微分會安靜地把它忽略掉，閘門照樣說通過。
        w = sp.sympify(p["step_response_srepr"])
        assert sp.simplify(w.subs(t_sym, 0)) == 0, f"w(0) ≠ 0 — {ctx}"
        assert sp.simplify(sp.diff(w, t_sym).subs(t_sym, 0)) == 0, f"w'(0) ≠ 0 — {ctx}"


@pytest.mark.parametrize("difficulty", [1, 2])
def test_the_initial_value_theorem_step_is_true(difficulty):
    r"""最後一步印的 $\lim_{s\to\infty} sL\{y\} = y(0)$ 必須真的成立。

    那一步的數字是**由生成端寫上去的**（就是 `y0`），不是算出來的——
    所以它是一句宣稱。這一項把它算一次：把答案正變換回去、取極限，
    再與步驟裡印的那個數字比對。

    ⚠️ **難度 3 沒有涵蓋在這一項裡**，這是一個誠實的空白：那裡的答案是
    `Piecewise`，`sp.laplace_transform` 對它給不出封閉形。難度 3 的
    $y(0)$ 仍然由驗證閘門（`Check.ic_residual_of`）盯著，只是這條
    「用變換再驗一次」的路走不通。
    """
    from app.generator.ode.laplace import s as s_sym, t as t_sym

    for problem in _sample("ode.laplace.ivp", difficulty, n=3):
        Y = sp.laplace_transform(problem.answer_expr, t_sym, s_sym, noconds=True)
        assert sp.limit(s_sym * Y, s_sym, sp.oo) == problem.params["y0"]

        step = [s for s in problem.steps if "initial value theorem" in s.title.lower()]
        assert len(step) == 1, f"seed={problem.seed} 缺少初值定理那一步"
        printed = re.search(r"= (-?\d+) = y\(0\)", step[0].latex)
        assert printed and int(printed.group(1)) == problem.params["y0"], (
            f"步驟印的數字與 y(0) 對不起來：{step[0].latex}"
        )


# =========================================================================
# Fourier 級數（v0.25，階段 2B 的 2B0–2B4）
# =========================================================================
#
# 上面那些通用檢查（閘門、步驟、KaTeX、可重現）對這三個題型自動適用，
# 因為 `CASES` 是從註冊表展開的。這一節加的是**只有 Fourier 才有意義**的東西，
# 而它分成四類，重要性由高到低：
#
#   1. **四層閘門真的擋得住東西**（突變測試）。這一類最重要，因為
#      「閘門有跑」與「閘門有用」是兩件事——一個永遠回 True 的 verify()
#      會讓上面每一項都全綠。
#   2. **規劃裡那些「⚠️ 需實測」的 SymPy 行為**，把實測結果釘住。
#   3. 係數的漂亮度（對 $n$ 的那一套門檻）。
#   4. $a_0$ 慣例（§7 #23）真的只有一處可以改。

# ⚠️ v0.35：`fourier.symmetry.parity` 已由老師刪除，所以這兩個 tuple 現在
# 一樣長。**刻意留著兩個名字**：`SERIES_TEMPLATES` 的語意是「有係數可以驗的
# 那些」，日後若再加一個像 parity 那樣答案是一句判斷的題型，分野會立刻回來。
FOURIER_TEMPLATES = (
    "fourier.series.full_range",
    "fourier.series.half_range",
)
SERIES_TEMPLATES = FOURIER_TEMPLATES


def _fourier_core():
    from app.generator.fourier import core
    return core


# --- 1. 四層閘門真的擋得住東西 -------------------------------------------


def _mutated_check(problem, **changes):
    """把一題的 `FourierCheck` 換掉某一個宣稱，其餘原樣。"""
    core = _fourier_core()
    check = problem.check
    fields = {
        "a0": check.coefficients.a0,
        "an": check.coefficients.an,
        "bn": check.coefficients.bn,
        "parity": check.parity,
        "a0_needs_separate_formula": check.a0_needs_separate_formula,
    }
    fields.update(changes)
    return core.FourierCheck(
        fn=check.fn,
        coefficients=core.Coefficients(fields["a0"], fields["an"], fields["bn"]),
        parity=fields["parity"],
        a0_needs_separate_formula=fields["a0_needs_separate_formula"],
    )


#: 每一個突變都對應一種真的會發生的生成端 bug。
#: `n=3` 那一個是規劃 §2.10.4 的核心情境：**只錯一個 $n$** 的封閉形式，
#: 印出來完全正常，學生算到那一項才會發現對不上。
FOURIER_MUTATIONS = [
    "a_n 整族乘 2",
    "b_n 整族乘 2",
    "a_0 加 1",
    "a_n 只在 n=3 錯",
    "奇偶性標成 even",
]


@pytest.mark.parametrize("mutation", FOURIER_MUTATIONS)
def test_the_fourier_gate_rejects_a_mutated_answer(mutation):
    """⛔ **這一項才是「閘門有用」的證據。**

    上面每一項通用檢查驗的都是「正確的題目會通過」。那件事一個
    `def verify(self, p): return True, ""` 也做得到——**而它會讓整份測試全綠**。
    這裡反過來驗：把一個正確的答案改壞，閘門必須說不。
    """
    n = _fourier_core().N_INT
    problem = generate("fourier.series.full_range", 2, seed=12345)
    coefficients = problem.check.coefficients
    changes = {
        "a_n 整族乘 2": {"an": coefficients.an * 2},
        "b_n 整族乘 2": {"bn": coefficients.bn * 2},
        "a_0 加 1": {"a0": coefficients.a0 + 1},
        # KroneckerDelta 在 n≠3 時是 0，所以這個 a_n 只有 n=3 那一格是錯的。
        "a_n 只在 n=3 錯": {"an": coefficients.an + sp.KroneckerDelta(n, 3)},
        "奇偶性標成 even": {"parity": "even"},
    }[mutation]
    ok, reason = _mutated_check(problem, **changes).verify(problem)
    assert not ok, f"閘門放過了「{mutation}」"
    assert reason, "閘門擋下來了卻沒有給原因（規則 4）"


def test_the_parseval_gate_on_its_own_rejects_a_wrong_coefficient():
    r"""第二層單獨拿出來驗一次。

    ⚠️ **必要性**：在整條 `verify()` 裡，第一層永遠先擋下所有係數錯誤，
    所以第二層即使整段壞掉（例如 `_closed_form_sum` 永遠回傳一個未計算的
    `Sum`，於是每一題都「跳過」）**上面那一項仍然全綠**。
    第二層存在的價值是它與係數積分**完全獨立**——那個價值只有在
    第一層失效時才兌現，而失效的時候沒有人會知道。所以要單獨驗它一次。
    """
    problem = generate("fourier.series.full_range", 2, seed=12345)
    good = problem.check
    assert good._gate_parseval() == (True, ""), "正確的題目沒過 Parseval"
    bad = _mutated_check(problem, bn=good.coefficients.bn * 2)
    ok, reason = bad._gate_parseval()
    assert not ok and "Parseval" in reason, f"Parseval 放過了係數乘 2：{reason}"


def test_the_partial_sum_gate_on_its_own_rejects_a_wrong_extension():
    r"""第三層單獨拿出來驗一次，理由與上一項相同。

    這裡用的突變是**把 $b_n$ 整族變號**——它相當於「延拓的方向寫反了」，
    也就是 §2.10.4 說第三層要抓的那一類。
    """
    problem = generate("fourier.series.full_range", 2, seed=12345)
    good = problem.check
    assert good._gate_partial_sums()[0], "正確的題目沒過部分和"
    bad = _mutated_check(problem, bn=-good.coefficients.bn)
    ok, reason = bad._gate_partial_sums()
    assert not ok and "閘門三" in reason, f"部分和放過了 b_n 變號：{reason}"


def test_the_partial_sum_gate_keeps_away_from_jumps_and_gibbs():
    r"""第三層的**取樣點**要真的避開跳點，否則它會擋掉正確的題目。

    Gibbs 過衝約 9%，而且加再多項也不會消失——所以「$N$ 開大一點就好」
    是錯的。這一項直接驗那條淨空距離：每一個取樣點離每一個跳點都要
    $\ge L/4$，而且至少要留下四個點（太少的話這一層等於沒有跑）。
    """
    core = _fourier_core()
    problem = generate("fourier.series.full_range", 3, seed=98765)
    fn = problem.check.fn
    jumps = [float(j) for j in fn.jump_points()]
    L = float(fn.half_period)
    ok, reason = problem.check._gate_partial_sums()
    assert ok, reason
    # 重建它用的那組取樣點，逐點檢查淨空距離。
    clearance = float(problem.check.jump_clearance) * L
    step = 2 * L / 37
    v = -L + step / 2
    kept = []
    while v < L:
        if all(abs(v - j) >= clearance for j in jumps):
            kept.append(v)
        v += step
    assert len(kept) >= 4, f"取樣點只剩 {len(kept)} 個"
    for point in kept:
        for jump in jumps:
            assert abs(point - jump) >= clearance


def test_a_resonant_f_is_rejected_instead_of_guessed():
    r"""§2.10.4 那個「只錯一個 $n$」的失敗模式：**這張網子是通的**。

    目前的函數族（分段多項式）結構上不可能與三角基底同頻，所以這個
    `Piecewise` 在正常出題時**一次都不會出現**——也就是說，
    `coefficients_of()` 裡那個檢查是一段**沒有被任何一題執行過**的程式，
    而那正是它需要一項專屬測試的原因。這裡直接餵一個 $f = \sin x$ 進去。

    順帶把規劃與現實的落差釘住：SymPy 1.14 回傳的是一個**誠實的**
    `Piecewise`（明說 $n=1$ 是特例），不是一個在 $n=1$ 悄悄失效的封閉形式。
    """
    core = _fourier_core()
    resonant = core.PiecewiseFn.build([(sp.sin(core.x), -sp.pi, sp.pi)], sp.pi)
    with pytest.raises(core.ResonantIntegral):
        core.coefficients_of(resonant)

    raw = sp.integrate(sp.sin(core.x) * sp.sin(core.N_GEN * core.x),
                       (core.x, -sp.pi, sp.pi))
    assert raw.has(sp.Piecewise), "SymPy 的行為變了，core.py 檔頭的落差 1 要重寫"


def test_generate_refuses_a_problem_with_no_verifier():
    """⛔ §2.2.1 那句「唯一不可妥協」：沒有驗證器 = 不通過，不是通過。

    這一項守的是**失敗的方向**。`check is None` 若被當成通過，
    症狀會是「新題型的每一題都完美無瑕」，而沒有任何東西看起來不對。
    """
    from app.generator.base import Problem

    naked = Problem(
        template_id="test.no.verifier", difficulty=1, seed=0, params={},
        statement="", statement_latex="", answer_latex="", answer_expr=sp.Integer(0),
    )
    ok, reason = naked.verify_answer()
    assert not ok and "check is None" in reason


# --- 2. 把規劃裡「⚠️ 需實測」的 SymPy 行為釘住 ----------------------------


def test_the_index_symbol_must_carry_its_assumptions():
    r"""附錄 C.4：$n$ 一定要帶 `integer=True`，否則 $\cos n\pi$ 化簡不掉。

    這不是一句提醒，是一個可以被驗證的事實——而它的反面
    （少寫 assumptions）**不會拋錯**，只會讓每一個係數多帶一個
    $\cos(\pi n)$ 因子，於是答案看起來像是「化簡到一半」。
    """
    core = _fourier_core()
    assert sp.cos(core.N_INT * sp.pi) == (-1) ** core.N_INT
    assert sp.sin(core.N_INT * sp.pi) == 0
    # 替身符號**刻意**不化簡——步驟裡「用 cos nπ = (-1)^n 之前」那一行靠它。
    assert sp.cos(core.N_GEN * sp.pi).has(sp.cos)
    assert core.N_INT != core.N_GEN, "兩顆符號同名但必須不相等"
    assert core.N_INT.name == core.N_GEN.name == "n", "印出來必須都是 n"


def test_the_two_index_symbols_never_coexist_in_a_coefficient():
    r"""⛔ `N_INT` 與 `N_GEN` 同名，所以並存的話**印出來看不出來**。

    症狀會是一個「有兩個自由變數、卻只印出一個 $n$」的算式，
    而它化簡不掉的表現是步驟裡多出一個沒有意義的項。
    """
    core = _fourier_core()
    for template_id in SERIES_TEMPLATES:
        for difficulty in (1, 2, 3):
            for problem in _sample(template_id, difficulty, n=3):
                c = problem.check.coefficients
                for claim in (c.a0, c.an, c.bn):
                    assert core.N_GEN not in claim.free_symbols, (
                        f"{template_id} d{difficulty} seed={problem.seed} 的係數"
                        f"含替身符號：{claim}"
                    )
                for raw in (c.an_raw, c.bn_raw):
                    assert core.N_INT not in raw.free_symbols, (
                        f"{template_id} d{difficulty} seed={problem.seed} 的"
                        f"未化簡形含真正的指標：{raw}"
                    )


def test_the_denominator_probe_finds_the_roots_it_is_supposed_to_find():
    r"""§2.10.4 第 1 點：閘門要主動去踩分母的正整數零點。

    ⚠️ **這一項用的是合成的表達式，不是題目**，而那是誠實的說明的一部分：
    目前的函數族裡分母永遠是 $\pi^k n^m$，所以這個探測點集合**在每一題上
    都是空的**（core.py 檔頭的「落差 2」）。留著這段程式是為了擴族，
    所以驗它的方式也只能是合成的。
    """
    core = _fourier_core()
    n = core.N_INT
    assert core._denominator_probe_points(1 / (n**2 - 1)) == [1]
    assert core._denominator_probe_points(1 / ((n**2 - 4) * (n - 7))) == [2, 7]
    assert core._denominator_probe_points(1 / (n**2 + 1)) == []
    assert core._denominator_probe_points(4 * (-1) ** n / (sp.pi * n**2)) == []


def test_jump_points_are_computed_not_declared():
    r"""跳點必須算出來，包含**週期延拓在 $\pm L$ 造成的那一個**。

    漏掉後者的症狀特別壞：取樣點會踩進 $x = \pm L$ 附近的 Gibbs 過衝，
    於是第三層開始擋**正確**的題目，而看起來像是係數算錯了。
    """
    core = _fourier_core()
    x = core.x
    L = sp.pi
    # 兩段在 0 接得上、但週期延拓在 ±π 接不上（f(-π)=−π ≠ π=f(π)）
    continuous_inside = core.PiecewiseFn.build([(x, -L, 0), (x, 0, L)], L)
    assert set(continuous_inside.jump_points()) == {-L, L}
    # 兩段在 0 接不上，而週期延拓接得上
    jump_at_zero = core.PiecewiseFn.build(
        [(x + 1, -L, 0), (x - 1, 0, L)], L)
    assert 0 in jump_at_zero.jump_points()
    # 完全連續（三角波）
    triangle = core.PiecewiseFn.build([(-x, -L, 0), (x, 0, L)], L)
    assert triangle.jump_points() == ()


def test_the_odd_extension_is_not_just_a_sign_flip():
    r"""奇延拓是 $-g(-x)$，不是 $-g(x)$ 也不是 $g(-x)$。

    ⚠️ 這三個寫法在 $g$ 是奇函數或偶函數時**剛好會有兩個相等**，
    所以「拿 $g = x$ 試一下看起來對」證明不了任何事。這裡用一個
    既不奇也不偶的 $g$，三者在它身上互不相等。
    """
    from app.generator.fourier import half_range as hr

    core = _fourier_core()
    x, L = core.x, sp.pi
    g = x**2 + x                                  # 既不奇也不偶
    odd = hr.extend([(g, sp.Integer(0), L)], L, "sine")
    even = hr.extend([(g, sp.Integer(0), L)], L, "cosine")
    assert odd.parity() == "odd"
    assert even.parity() == "even"
    left_of_odd = odd.pieces[0].poly
    assert sp.expand(left_of_odd - (-g.subs(x, -x))) == 0        # 正確的寫法
    assert sp.expand(left_of_odd - (-g)) != 0                    # 只變號 → 錯
    assert sp.expand(left_of_odd - g.subs(x, -x)) != 0           # 只鏡射 → 錯


# --- 3. 係數的漂亮度（對 $n$ 的那一套門檻）--------------------------------


@pytest.mark.parametrize("template_id", SERIES_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_fourier_coefficients_are_pretty_in_n(template_id, difficulty):
    r"""係數是對 $n$ 的表達式，門檻在 `ugliness_in_n()`。

    ⚠️ 這一項與 `test_answer_is_pretty` **不重複，也不能合併**：
    $(-1)^n$ 在 `ugliness()` 眼裡是一個 Pow，在這裡卻是這個題型的重點。
    兩套門檻沒有可比性（§2.10.2 的原話）。
    """
    from app.generator.fourier import core, half_range, series
    from app.generator.pretty import has_quarter_period_factor, ugliness_in_n

    limits = (series if template_id.endswith("full_range") else half_range)
    limit = limits.UGLINESS_LIMIT[difficulty]
    for problem in _sample(template_id, difficulty):
        c = problem.check.coefficients
        ctx = f"{template_id} d{difficulty} seed={problem.seed}"
        for name, claim in (("a_n", c.an), ("b_n", c.bn)):
            score = ugliness_in_n(claim, core.N_INT, allow_quarter_period=True)
            assert score <= limit, f"{name} 漂亮度 {score} > {limit} — {ctx}：{claim}"
            if difficulty < 3:
                # $\sin\frac{n\pi}{2}$ 要按 n mod 4 分四種情形討論。
                # §2.10.2：「在難度 3 有教學價值，但不能隨機跑出來」。
                assert not has_quarter_period_factor(claim, core.N_INT), (
                    f"{name} 在難度 {difficulty} 出現四分之一週期因子 — {ctx}：{claim}"
                )


def test_ugliness_in_n_is_not_the_same_scale_as_ugliness():
    """兩支評分函式的判準不同，這一項把「不同」寫下來。

    共用一支的話會逼出一堆 `if is_fourier:` 分支，而那種分支最後一定會被讀錯。
    """
    from app.generator.pretty import ugliness, ugliness_in_n

    core = _fourier_core()
    n = core.N_INT
    friendly = 2 * ((-1) ** n - 1) / (sp.pi * n**2)      # 標準的方波係數
    assert ugliness_in_n(friendly, n) < 12
    assert ugliness_in_n(sp.Integer(0), n) == 0
    # 分母 n^6 → 擋掉
    assert ugliness_in_n(1 / n**6, n) >= 100
    # 四分之一週期因子：預設擋、明示允許時放行
    quarter = 6 * sp.sin(sp.pi * n / 2) / (sp.pi * n)
    assert ugliness_in_n(quarter, n) >= 100
    assert ugliness_in_n(quarter, n, allow_quarter_period=True) < 100
    # ⚠️ 兩支函式的差別**不在分數大小**，在「擋什麼」。這裡挑兩個
    # `ugliness()` 覺得很正常、而 `ugliness_in_n()` 必須擋掉的式子——
    # 免得日後有人「順手」把其中一支改成呼叫另一支。
    for blocked in (1 / n**6, quarter):
        assert ugliness(blocked) < 20, f"ugliness() 本來就不管這個：{blocked}"
        assert ugliness_in_n(blocked, n) >= 100, f"ugliness_in_n() 必須擋：{blocked}"


def test_coefficients_are_grouped_by_power_of_n():
    r"""`_tidy()`：按 $n$ 的冪次分組，不要湊成一個大分式。

    `sp.simplify` 會把不同冪次硬湊成
    $\frac{2(-4(-1)^n + \pi^2n^2(2(-1)^n+1) + 4)}{\pi^3 n^3}$——每個字元都對，
    而沒有課本會這樣寫。學生要看出「$1/n$ 那一項」與「$1/n^3$ 那一項」
    得先自己拆回去，而那正是這個題型要教的事情之一。
    """
    core = _fourier_core()
    n = core.N_INT
    messy = (4 * (-1) ** n / (sp.pi * n) - 8 * (-1) ** n / (sp.pi**3 * n**3)
             + 2 / (sp.pi * n) + 8 / (sp.pi**3 * n**3))
    tidy = core._tidy(messy)
    assert sp.simplify(tidy - messy) == 0, "整理過的式子與原式必須相等"
    # 分成兩個加項，一個是 1/n、一個是 1/n^3
    terms = sp.Add.make_args(tidy)
    assert len(terms) == 2, f"沒有分組：{tidy}"
    from app.generator.pretty import _index_denominator_degree

    degrees = sorted(_index_denominator_degree(t, n) for t in terms)
    assert degrees == [1, 3], f"分組的冪次不對：{tidy}"


# --- 4. $a_0$ 的慣例（§7 #23）真的只有一處可以改 --------------------------


def test_the_a0_convention_lives_in_exactly_one_place():
    r"""§7 #23 尚未拍板，所以「改起來只動一個地方」必須是真的。

    四個導出函式全部從 `A0_IS_HALVED` 讀，所以翻轉那個布林值之後
    **四個都要跟著變**。漏掉任何一個的症狀是：級數的常數項與 $a_0$ 的
    定義式對不起來，而**兩者各自都印得很正常**——學生會以為自己算錯了。

    ⚠️ 這一項會暫時改一個 module 級常數，用 try/finally 還原。
    """
    core = _fourier_core()
    a0 = sp.Symbol("a_0")
    integral = sp.Symbol("I")
    original = core.A0_IS_HALVED

    def derived():
        return (core.a0_from_period_integral(integral, sp.pi),
                core.constant_term(a0),
                core.series_head_latex(),
                core.a0_definition_latex(sp.pi),
                core.a0_meaning_note())

    try:
        core.A0_IS_HALVED = True
        halved = derived()
        core.A0_IS_HALVED = False
        whole = derived()
    finally:
        core.A0_IS_HALVED = original

    assert len(halved) == 5, "導出量的個數變了，PLAN §7 #23 與 core.py 的註解要一起改"
    for index, (a, b) in enumerate(zip(halved, whole)):
        assert a != b, f"第 {index} 個導出量沒有跟著 A0_IS_HALVED 改變：{a}"
    assert halved[1] == a0 / 2 and whole[1] == a0
    assert core.A0_IS_HALVED is original, "測試沒有把常數還原"


@pytest.mark.parametrize("template_id", SERIES_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_constant_term_of_the_series_is_the_mean_value(template_id, difficulty):
    r"""不管慣例怎麼選，**級數的常數項一定是 $f$ 在一週期上的平均值**。

    這是一個與慣例無關的數學事實，所以它是檢驗慣例有沒有被寫對的最好方式：
    $a_0$ 的定義與級數開頭那一項若不一致，這一項就會紅——**而畫面上
    不會有任何東西看起來不對**（兩個數字各自都很合理）。
    """
    core = _fourier_core()
    for problem in _sample(template_id, difficulty, n=5):
        fn = problem.check.fn
        mean = sum(sp.integrate(p.poly, (core.x, p.lo, p.hi)) for p in fn.pieces) / (
            2 * fn.half_period)
        constant = core.constant_term(problem.check.coefficients.a0)
        assert sp.simplify(constant - mean) == 0, (
            f"{template_id} d{difficulty} seed={problem.seed}："
            f"常數項 {constant} ≠ 平均值 {sp.simplify(mean)}"
        )


@pytest.mark.parametrize("template_id", SERIES_TEMPLATES)
@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_the_a0_step_says_something_true(template_id, difficulty):
    r"""第 4 步那句「不能把 $n=0$ 代進 $a_n$」必須與現實一致。

    ⚠️ 規劃（§2.10.4 第 2 點）要求的是單向的「$a_n(0) \ne a_0$」，
    而那**在奇函數上是錯的**：奇函數的 $a_n \equiv 0$ 在 $n=0$ 確實成立。
    所以這裡驗的是雙向：旗標說要單獨算 ⟺ 封閉形式在 $n=0$ 真的沒有定義。
    """
    core = _fourier_core()
    for problem in _sample(template_id, difficulty, n=5):
        check = problem.check
        at_zero = check.coefficients.an.subs(core.N_INT, 0)
        undefined = bool(at_zero.has(sp.zoo, sp.nan)) or at_zero.is_finite is False
        ctx = f"{template_id} d{difficulty} seed={problem.seed}"
        assert check.a0_needs_separate_formula == undefined, ctx
        note = " ".join(s.note for s in problem.steps if "a_0" in s.title)
        if not note:
            continue                      # 奇函數的題目沒有 a_0 那一步
        if undefined:
            assert "cannot be obtained by putting $n = 0$" in note, ctx
        else:
            assert "remain valid at $n = 0$" in note, ctx


# --- 驗收標準：Parseval 被跳過的比例要記錄下來（PLAN §6 階段 2B）----------


def test_how_often_the_parseval_gate_is_skipped():
    r"""§6 的驗收標準之一：**跳過的比例要記錄下來，跳太多代表函數族選得不好**。

    ⚠️ 這一項刻意**不是**「跳過率必須是 0」。第二層本來就有一部分參數
    收不出封閉形式（難度 3 的三段函數，係數含 $\sin\frac{n\pi}{2}$），
    而規則 4 要的是「跳過必須是明示的、而且被記錄下來」，
    不是「不准跳過」。上限訂在 40%：超過的話這一層就不再是一層閘門，
    而是一個偶爾會跑的東西。
    """
    core = _fourier_core()
    skipped = total = 0
    lines = []
    for template_id in SERIES_TEMPLATES:
        for difficulty in (1, 2, 3):
            here = 0
            problems = _sample(template_id, difficulty, n=min(N_SAMPLES, 15))
            for problem in problems:
                c = problem.check.coefficients
                series = core._closed_form_sum(sp.expand(c.an**2 + c.bn**2))
                total += 1
                if series.has(sp.Sum):
                    skipped += 1
                    here += 1
            lines.append(f"  {template_id} d{difficulty}: {here}/{len(problems)}")
    report = "Parseval 跳過率\n" + "\n".join(lines) + f"\n  總計 {skipped}/{total}"
    print(report)
    assert skipped / total <= 0.40, report


# --- `Check.ic_derivative_values` 承不承重（v0.24 加的那個欄位）------------
#
# ⚠️ **v0.35：這一節原本是「待定係數」那一整組的最後一項**，而那個題型
# （`ode.second_order.undetermined`）已由老師刪除。**這一項沒有跟著刪，
# 是刻意的**：它守的不是那個題型，是 `base.Check` 的一個欄位，
# 而 `ode.laplace.ivp` 的難度 2 與 3（二階初值問題）仍然靠它。
# 刪掉它等於讓一個還在用的欄位失去唯一的證明。改寫成用 `ode.laplace.ivp`。


def _homogeneous_solution_vanishing_at_zero(a1: int, a0: int) -> sp.Expr:
    """一個滿足 $h(0)=0$、$h'(0)\\ne 0$ 的齊次解。下面的突變測試用它。

    ⚠️ 自變數是 $t$（拉普拉斯那邊用的符號），v0.35 之前是 $x$。
    """
    tv = sp.Symbol("t", positive=True)
    discriminant = a1**2 - 4 * a0
    if discriminant > 0:
        root = sp.sqrt(sp.Integer(discriminant))
        r1, r2 = (-a1 + root) / 2, (-a1 - root) / 2
        return sp.exp(r1 * tv) - sp.exp(r2 * tv)
    if discriminant == 0:
        return tv * sp.exp(sp.Rational(-a1, 2) * tv)
    beta = sp.sqrt(sp.Integer(-discriminant)) / 2
    return sp.exp(sp.Rational(-a1, 2) * tv) * sp.sin(beta * tv)


def test_the_gate_would_miss_a_wrong_y_prime_at_zero_without_that_field():
    r"""**`Check.ic_derivative_values` 是承重的，這一項證明它承重。**

    作法是造一個「只錯在 $y'(0)$」的答案：把一個滿足 $h(0)=0$ 的齊次解加上去。
    它仍然滿足原方程、仍然滿足 $y(0)=y_0$，**只有 $y'(0)$ 是錯的**。

    兩個斷言缺一不可：

    * 現在的閘門**擋得下來** —— 否則那個欄位沒有在做事；
    * 把 `ic_derivative_values` 拿掉之後閘門**放它過去** —— 否則這一項
      擋下來的其實是別的東西，而那個欄位刪掉也不會有人發現。

    這正是 v0.24 加那個欄位時寫的理由（`base.Check.ic_residual_of` 的註解）：
    在那之前，純量的二階初值問題只驗得了 $y(t_0)$。

    ⚠️ **只有 `order == 2` 的那幾格適用**——一階的初值問題沒有 $y'(0)$
    這個條件，`ic_derivative_values` 是空的。
    """
    tv = sp.Symbol("t", positive=True)
    checked = 0
    for difficulty in (1, 2, 3):
        for problem in _sample("ode.laplace.ivp", difficulty):
            if problem.params.get("order") != 2:
                continue
            bump = _homogeneous_solution_vanishing_at_zero(
                problem.params["a1"], problem.params["a0"])
            wrong = dataclasses.replace(
                problem, answer_expr=sp.expand(problem.answer_expr + bump))
            ctx = f"d{difficulty} seed={problem.seed}"

            assert sp.simplify(bump.subs(tv, 0)) == 0, f"造出來的擾動不是 0 起步 — {ctx}"
            ok, reason = problem.check.verify(wrong)
            assert not ok, f"閘門對一個 y'(0) 錯掉的答案說通過 — {ctx}"
            assert "初值" in reason, f"擋下來的理由不是初值條件：{reason} — {ctx}"

            blind = dataclasses.replace(problem.check, ic_derivative_values=())
            ok_blind, _ = blind.verify(wrong)
            assert ok_blind, (
                f"拿掉 ic_derivative_values 之後閘門居然還是擋得住 — {ctx}；"
                "這表示上面那個斷言其實是被別的東西擋下來的")
            checked += 1
            break                          # 每個難度一題就夠，這一項很慢
    assert checked == 2, f"應該有兩個難度是二階的，實際 {checked} 個"



# --- KaTeX：不要用字串黑名單猜，直接用自架的那一份渲染一次 ----------------

_KATEX = ROOT / "app" / "static" / "vendor" / "katex" / "katex.min.js"
_NODE = shutil.which("node")


@pytest.mark.skipif(
    _NODE is None,
    reason=("找不到 node，因此無法用自架的 KaTeX 實際渲染公式。"
            "這不是通過，是沒有跑。裝 Node.js（開發期相依，部署不需要）後重跑。"),
)
def test_every_formula_renders_in_the_bundled_katex():
    r"""把每一個題型的敘述、答案、每一步都丟進**自架的那一份 KaTeX** 渲染。

    在這之前，「KaTeX 支不支援這個」是由一份手寫的字串黑名單回答的，
    而那份清單裡有一項是錯的——它禁止 `\begin{cases}`，理由寫著
    「KaTeX 不支援」，但 0.16.11 支援它。**一個猜錯的黑名單同時做錯兩件事**：
    擋掉可以用的東西，而且對它沒想到的東西完全沒有意見。

    這一項不是要取代黑名單（黑名單守的是**規範**——附錄 C 不准寫 $F(s)$，
    那與渲染得出來無關），而是把「渲染得出來」這一件事交給唯一有資格回答它的東西。
    """
    payload = []
    for template_id, difficulty in CASES:
        for problem in _sample(template_id, difficulty, n=2):
            label = f"{template_id} d{difficulty} seed={problem.seed}"
            payload.append([f"{label} statement", problem.statement_latex])
            payload.append([f"{label} answer", problem.answer_latex])
            for index, step in enumerate(problem.steps):
                if step.latex:
                    payload.append([f"{label} step{index}", step.latex])

    # 路徑走環境變數而不是 argv：`node -e` 的 `process.argv` 不含腳本本身，
    # 於是索引會差一格，而差錯的症狀是一句與 KaTeX 無關的 ERR_INVALID_ARG_TYPE。
    script = r"""
      const katex = require(process.env.KATEX_PATH);
      const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
      const bad = [];
      for (const [label, tex] of items) {
        try { katex.renderToString(tex, {throwOnError: true, strict: 'error'}); }
        catch (e) { bad.push(label + ' :: ' + e.message + ' :: ' + tex); }
      }
      process.stdout.write(JSON.stringify(bad));
    """
    result = subprocess.run(
        [_NODE, "-e", script], input=json.dumps(payload),
        capture_output=True, text=True, timeout=180,
        env={**os.environ, "KATEX_PATH": str(_KATEX)},
    )
    assert result.returncode == 0, result.stderr[:2000]
    failures = json.loads(result.stdout)
    assert not failures, "KaTeX 渲染失敗：\n" + "\n".join(failures[:10])


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        generate("ode.does_not_exist", 1)


def test_unsupported_difficulty_raises():
    with pytest.raises(ValueError):
        generate("ode.first_order.separable", 9)
