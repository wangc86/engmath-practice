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

import os
import random
import re
from functools import lru_cache

import pytest
import sympy as sp

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
def test_residual_is_zero(template_id, difficulty):
    """核心驗證閘門：標準答案代回原方程後殘差必須為 0。"""
    for problem in _sample(template_id, difficulty):
        assert problem.residual_is_zero(), (
            f"殘差不為 0：{template_id} d{difficulty} seed={problem.seed}\n"
            f"  題目：{problem.statement_latex}\n"
            f"  答案：{problem.answer_latex}\n"
            f"  殘差：{sp.simplify(problem.check.residual_of(problem.answer_expr))}"
        )


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_answer_is_pretty(template_id, difficulty):
    """答案不得含特殊函數、未算完的積分，也不得有醜分數。"""
    limit = UGLINESS_LIMIT[difficulty]
    for problem in _sample(template_id, difficulty):
        ctx = f"{template_id} d{difficulty} seed={problem.seed}: {problem.answer_latex}"
        assert not has_special_function(problem.answer_expr), f"含特殊函數／未算完的積分 — {ctx}"
        assert not has_ugly_fraction(problem.answer_expr), f"含分母 > 12 的醜分數 — {ctx}"
        assert ugliness(problem.answer_expr) <= limit, (
            f"漂亮度 {ugliness(problem.answer_expr)} > {limit} — {ctx}"
        )


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

        # 最後一個「有算式」的步驟應該就是答案本身
        answer_body = problem.answer_latex.split("=", 1)[-1].strip()
        bodies = [s.latex.split("=")[-1].strip() for s in problem.steps if s.latex]
        assert answer_body in bodies, f"最後一步與答案對不起來 — {ctx}"


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_latex_is_katex_safe(template_id, difficulty):
    """避免用到 KaTeX 不支援的環境。"""
    forbidden = ("\\begin{cases}", "\\begin{align}", "\\intertext", "\\newcommand")
    for problem in _sample(template_id, difficulty, n=5):
        blob = problem.statement_latex + problem.answer_latex + "".join(
            s.latex for s in problem.steps
        )
        for token in forbidden:
            assert token not in blob, f"{template_id} d{difficulty} 用到 {token}"


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
        assert not mixes_function_families(problem.answer_expr), (
            f"答案混用了指數與雙曲寫法：{template_id} d{difficulty} "
            f"seed={problem.seed}\n  答案：{problem.answer_latex}"
        )


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_system_answers_are_written_with_exponentials(difficulty):
    """線性系統的答案與逐步解答一律是指數形式。

    逐步解答從特徵值一路寫到 $\\sum_i C_i e^{\\lambda_i t}\\mathbf{v}_i$，
    最後一行不能突然換成 sinh／cosh。
    """
    for problem in _sample("system.linear_2x2.real_distinct", difficulty):
        blob = problem.answer_latex + "".join(s.latex for s in problem.steps)
        for name in ("sinh", "cosh", "tanh"):
            assert name not in blob, (
                f"系統題出現 {name}：d{difficulty} seed={problem.seed}\n"
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
    assert ids == {
        "ode.first_order.separable",
        "ode.first_order.linear",
        "ode.second_order.homogeneous",
        "system.linear_2x2.real_distinct",
        # v0.24（階段 2A 的 2f）。⚠️ 這兩個檔案住在 `app/generator/ode/`，
        # 上面四個住在 `app/generator/`——**而註冊表看不出差別**，
        # 因為 `template_id` 與檔案路徑從來沒有耦合過（D16）。
        "ode.laplace.transform",
        "ode.laplace.ivp",
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


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        generate("ode.does_not_exist", 1)


def test_unsupported_difficulty_raises():
    with pytest.raises(ValueError):
        generate("ode.first_order.separable", 9)
