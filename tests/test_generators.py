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

import pytest
import sympy as sp

from app.generator import DIFFICULTY_LABELS, generate, list_templates
from app.generator.pretty import has_special_function, has_ugly_fraction, ugliness

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


def _sample(template_id: str, difficulty: int, n: int = N_SAMPLES):
    rng = random.Random(f"{template_id}-{difficulty}")
    for _ in range(n):
        yield generate(template_id, difficulty, seed=rng.randrange(1, 2**31 - 1))


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


@pytest.mark.parametrize("template_id,difficulty", CASES)
def test_seed_is_reproducible(template_id, difficulty):
    """同一個 seed 必須生出完全相同的題目（紀錄可重現）。"""
    a = generate(template_id, difficulty, seed=20260807)
    b = generate(template_id, difficulty, seed=20260807)
    assert a.statement_latex == b.statement_latex
    assert a.answer_latex == b.answer_latex


def test_registry_is_wired_up():
    """四個 MVP 題型都要在註冊表裡，且每個都有中文名與難度說明。"""
    ids = {t.template_id for t in list_templates()}
    assert ids == {
        "ode.first_order.separable",
        "ode.first_order.linear",
        "ode.second_order.homogeneous",
        "system.linear_2x2.real_distinct",
    }
    for tpl in list_templates():
        assert tpl.name and tpl.chapter
        assert set(tpl.difficulties) <= set(DIFFICULTY_LABELS)
        for d in tpl.difficulties:
            assert tpl.difficulty_notes.get(d), f"{tpl.template_id} 缺難度 {d} 的說明"


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        generate("ode.does_not_exist", 1)


def test_unsupported_difficulty_raises():
    with pytest.raises(ValueError):
        generate("ode.first_order.separable", 9)
