"""作答判定的測試（PLAN.md §5）。

三組東西各自要守住不同的性質：

- **解析**（`parse.py`）：寬容地吃下學生的各種寫法，但危險輸入一律擋掉，
  且錯誤訊息要是可行動的英文句子，不是 traceback。
- **判定**（`core.py`）：判的是數學性質，不是字面形式。因此**重新參數化的
  答案必須判對**（這是最容易寫錯的一項），而「滿足方程但常數不足」要判成
  部分正確、不是錯。
- **安全**（`sandbox.py`）：惡意或病態輸入不得讓判定跑不完。

判定直接呼叫 `core.grade`（不經子行程），測試才跑得快；子行程與 timeout
另有專門的測試。
"""

from __future__ import annotations

import time

import pytest
import sympy as sp

from app.generator import generate
from app.grader.core import grade
from app.grader.parse import ParseError, parse_answer

x = sp.Symbol("x", positive=True)
t = sp.Symbol("t", real=True)


def verdict_for(problem, text):
    return grade(problem.check, problem.answer_expr, text)


def code_for(problem, text):
    return verdict_for(problem, text).code


# --- 每個題型的標準答案都要判對 -------------------------------------------

REFERENCE_CASES = [
    ("ode.first_order.separable", 1),
    ("ode.first_order.separable", 2),
    ("ode.first_order.separable", 3),
    ("ode.first_order.linear", 1),
    ("ode.first_order.linear", 2),
    ("ode.first_order.linear", 3),
    ("ode.second_order.homogeneous", 1),
    ("ode.second_order.homogeneous", 2),
    ("ode.second_order.homogeneous", 3),
    ("system.linear_2x2.real_distinct", 1),
    ("system.linear_2x2.real_distinct", 2),
    ("system.linear_2x2.real_distinct", 3),
]


def _as_text(problem) -> str:
    """把標準答案轉回學生會打的純文字（含 C1／C2 的寫法）。"""
    expr = problem.answer_expr
    if problem.check.kind == "system":
        body = ", ".join(str(sp.expand(c)) for c in expr)
    else:
        body = str(expr)
    return body.replace("C_1", "C1").replace("C_2", "C2")


@pytest.mark.parametrize("template_id,difficulty", REFERENCE_CASES)
def test_reference_answer_is_accepted(template_id, difficulty):
    """最基本的一條：標準答案原封不動貼回去，必須判對。"""
    for seed in (101, 202, 303):
        problem = generate(template_id, difficulty, seed=seed)
        verdict = verdict_for(problem, _as_text(problem))
        assert verdict.correct, (
            f"{template_id} d{difficulty} seed={seed} 判成 {verdict.code}\n"
            f"  題目：{problem.statement_latex}\n"
            f"  送出：{_as_text(problem)}\n  訊息：{verdict.detail}"
        )


@pytest.mark.parametrize("template_id,difficulty", REFERENCE_CASES)
def test_tiny_coefficient_error_is_rejected(template_id, difficulty):
    """把答案整個加上一個非零常數，就不再是解（初值題也會壞掉初始條件）。"""
    for seed in (101, 202):
        problem = generate(template_id, difficulty, seed=seed)
        text = _as_text(problem)
        if problem.check.kind == "system":
            first, rest = text.split(",", 1)
            broken = f"{first} + 1,{rest}"
        else:
            broken = f"({text}) + 1"
        assert not verdict_for(problem, broken).correct, (
            f"{template_id} d{difficulty} seed={seed}：加了 1 竟然還判對"
        )


# --- 二階齊次：PLAN.md §5.3 的那張表 --------------------------------------

def _second_order(seed=7):
    """固定取一題實相異根的二階題，並回傳它的兩個特徵根。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=seed)
    return problem, problem.params["r1"], problem.params["r2"]


def test_general_solution_standard_form():
    problem, r1, r2 = _second_order()
    assert code_for(problem, f"C1*exp({r1}*x) + C2*exp({r2}*x)") == "correct"


def test_general_solution_renamed_and_reordered_constants():
    """換常數名稱、換項次順序，都還是同一個通解。"""
    problem, r1, r2 = _second_order()
    assert code_for(problem, f"A*exp({r2}*x) + B*exp({r1}*x)") == "correct"


def test_reparametrised_general_solution_is_accepted():
    """**這是判分最容易做錯的一項**：重新參數化的答案必須判對。

    (C1+C2)e^{r1 x} + (C1-C2)e^{r2 x} 描述的是同一個解族，
    但它和標準答案相減永遠不會是 0——所以不能用「相減」來判。
    """
    problem, r1, r2 = _second_order()
    verdict = verdict_for(problem, f"(C1+C2)*e^({r1}x) + (C1-C2)*e^({r2}x)")
    assert verdict.correct, verdict.detail
    assert "written differently" in verdict.detail


def test_missing_constant_is_partial_not_wrong():
    """漏掉一個任意常數是最常見的部分正確，必須明講、不能只說「錯」。"""
    problem, r1, _ = _second_order()
    verdict = verdict_for(problem, f"C1*exp({r1}*x)")
    assert verdict.code == "partial_missing_constants"
    assert not verdict.correct and verdict.partial
    assert "2 arbitrary constants" in verdict.detail
    assert "1" in verdict.detail


def test_duplicated_basis_is_not_independent():
    """滿足方程、常數個數也對，但兩項是同一個解 → 不是通解。"""
    problem, r1, _ = _second_order()
    assert code_for(problem, f"C1*exp({r1}*x) + C2*exp({r1}*x)") == "dependent_constants"


def test_extra_constant_is_rejected():
    problem, r1, r2 = _second_order()
    code = code_for(problem, f"C1*exp({r1}*x) + C2*exp({r2}*x) + A*x")
    assert code in {"wrong", "too_many_constants"}
    assert code != "correct"


def test_wrong_exponent_is_rejected():
    problem, r1, r2 = _second_order()
    wrong_root = max(r1, r2) + 5          # 保證不等於 r1、r2
    verdict = verdict_for(problem, f"C1*exp({r1}*x) + C2*exp({wrong_root}*x)")
    assert verdict.code == "wrong"
    # 逐項診斷應該指出「有一項是對的」
    assert "1 of your 2 terms" in verdict.detail


# 用一個**合成的** Check 來測那些現有四個題型還碰不到的分支
# （非齊次的純量初值問題——待定係數與 Laplace 進來以後就會用到）。
def _nonhomogeneous_ivp_check():
    """y' + y = 1, y(0) = 2 → y = 1 + e^{-x}"""
    from app.generator.base import Check

    var = sp.Symbol("x", positive=True)
    unknown = sp.Function("y")(var)
    check = Check(
        var=var,
        kind="scalar",
        n_constants=0,
        order=1,
        unknown=unknown,
        residual_expr=sp.Derivative(unknown, var) + unknown - 1,
        ic_point=sp.Integer(0),
        ic_value=sp.Integer(2),
        linear=True,
    )
    return check, 1 + sp.exp(-var)


def test_sign_error_hint():
    """整個答案差一個負號時，提示要講「檢查正負號」。"""
    check, reference = _nonhomogeneous_ivp_check()
    verdict = grade(check, reference, "-(1 + e^(-x))")
    assert verdict.code == "wrong"
    assert "signs" in verdict.detail


def test_off_by_a_constant_hint():
    """差一個常數時，提示要指向積分常數／特解。"""
    check, reference = _nonhomogeneous_ivp_check()
    verdict = grade(check, reference, "6 + e^(-x)")
    assert verdict.code == "wrong"
    assert "differs from a solution by a constant" in verdict.detail


def test_nonhomogeneous_ivp_reference_is_accepted():
    check, reference = _nonhomogeneous_ivp_check()
    assert grade(check, reference, "1 + e^(-x)").correct
    assert grade(check, reference, "y = 1 + exp(-1*x)").correct


def test_repeated_root_needs_the_x_factor():
    """重根題漏掉 x 這個因子 → 兩項相同 → 常數不獨立。"""
    problem = generate("ode.second_order.homogeneous", 2, seed=5)
    r = problem.params["r"]
    assert code_for(problem, f"C1*exp({r}*x) + C2*exp({r}*x)") == "dependent_constants"
    assert code_for(problem, f"(C1 + C2*x)*exp({r}*x)") == "correct"


def test_complex_root_answer_in_real_form():
    problem = generate("ode.second_order.homogeneous", 3, seed=9)
    a, b = problem.params["alpha"], problem.params["beta"]
    assert code_for(problem, f"e^({a}x)*(C1*cos({b}x) + C2*sin({b}x))") == "correct"
    # 把 cos 和 sin 對調仍是同一個解族
    assert code_for(problem, f"e^({a}x)*(C1*sin({b}x) + C2*cos({b}x))") == "correct"
    # 少了 e^{αx} 這個包絡（α ≠ 0 時）就不是解
    if a != 0:
        assert code_for(problem, f"C1*cos({b}x) + C2*sin({b}x)") == "wrong"


# --- 一階：C 與 e^C、隱式解 -----------------------------------------------

def test_constant_reparametrised_as_exponential():
    """y = C1·e^{F} 與 y = e^{F+C} 是同一件事（PLAN.md §5.4）。"""
    problem = generate("ode.first_order.separable", 1, seed=11)
    F = sp.integrate(sp.sympify(problem.params["f"]), x)
    assert code_for(problem, f"C1*exp({F})") == "correct"
    assert code_for(problem, f"e^({F} + C1)") == "correct"


def test_implicit_answer_is_solved_for_y():
    """ln(y) = F(x) + C 這種隱式寫法要能反解後判定。"""
    problem = generate("ode.first_order.separable", 1, seed=11)
    F = sp.integrate(sp.sympify(problem.params["f"]), x)
    assert code_for(problem, f"ln(y) = {F} + C1") == "correct"
    assert code_for(problem, f"ln|y| = {F} + C1") == "correct"
    assert code_for(problem, f"ln(y) = {F}") == "partial_missing_constants"


def test_particular_solution_of_general_problem_is_partial():
    """通解題目送出一個特解 → 部分正確，不是錯。"""
    problem = generate("ode.first_order.separable", 1, seed=11)
    F = sp.integrate(sp.sympify(problem.params["f"]), x)
    assert code_for(problem, f"exp({F})") == "partial_missing_constants"


def test_first_order_linear_general_solution():
    problem = generate("ode.first_order.linear", 1, seed=17)
    assert code_for(problem, str(problem.answer_expr).replace("C_1", "C1")) == "correct"
    # 漏掉齊次解那一項（只剩特解）→ 部分正確
    without_c = sp.expand(problem.answer_expr.subs(sp.Symbol("C_1"), 0))
    assert code_for(problem, str(without_c)) == "partial_missing_constants"


# --- 系統：向量答案 --------------------------------------------------------

def test_system_accepts_several_input_shapes():
    problem = generate("system.linear_2x2.real_distinct", 2, seed=13)
    c1, c2 = (str(sp.expand(c)).replace("C_1", "C1").replace("C_2", "C2")
              for c in problem.answer_expr)
    for text in (f"{c1}, {c2}", f"{c1}\n{c2}", f"[{c1}, {c2}]",
                 f"x1 = {c1}\nx2 = {c2}"):
        assert code_for(problem, text) == "correct", text


def test_system_rejects_wrong_component_count():
    problem = generate("system.linear_2x2.real_distinct", 2, seed=13)
    c1 = str(sp.expand(problem.answer_expr[0])).replace("C_", "C")
    verdict = verdict_for(problem, c1)
    assert verdict.code == "parse_error"
    assert "2 components" in verdict.detail


def test_system_scaled_eigenvector_is_still_correct():
    """特徵向量差一個非零純量仍然正確——常數會把倍率吸收掉。"""
    problem = generate("system.linear_2x2.real_distinct", 2, seed=13)
    C1, C2 = sp.symbols("C_1 C_2")
    scaled = sp.expand(problem.answer_expr.subs({C1: 2 * C1, C2: -3 * C2}))
    text = ", ".join(str(c) for c in scaled).replace("C_1", "C1").replace("C_2", "C2")
    assert code_for(problem, text) == "correct"


def test_system_ivp_rejects_leftover_constants():
    problem = generate("system.linear_2x2.real_distinct", 3, seed=13)
    text = ", ".join(f"C1*({sp.expand(c)})" for c in problem.answer_expr)
    verdict = verdict_for(problem, text)
    assert verdict.code == "unexpected_constants"
    assert verdict.partial


def test_system_ivp_wrong_initial_condition():
    """滿足方程但不滿足初始條件 → 要能分辨出來，訊息也不一樣。"""
    problem = generate("system.linear_2x2.real_distinct", 3, seed=13)
    doubled = ", ".join(str(sp.expand(2 * c)) for c in problem.answer_expr)
    verdict = verdict_for(problem, doubled)
    assert verdict.code == "initial_condition"
    assert "initial condition" in verdict.detail


# --- 輸入解析的寬容度 ------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "C1*exp(3*x) + C2*exp(-2*x)",
        "C1e^(3x)+C2e^(-2x)",
        "c_1e^(3x) + c_2e^(-2x)",
        "C_1 exp(3x) + C_2 exp(-2x)",
        "y = C1*e^(3x) + C2*e^(-2x)",
        "y(x) = C1*e^(3x) + C2*e^(-2x)",
        r"C_1 \exp(3x) + C_2 \exp(-2x)",
        "C1e^{3x}+C2e^{-2x}",
        "  C1 e^(3 x)  +  C2 e^(-2 x)  ",
    ],
)
def test_equivalent_spellings_all_parse_to_the_same_thing(text):
    """學生的各種寫法都要解析成同一個式子（PLAN.md §5.2 的實測表）。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    parsed = parse_answer(text, problem.check)
    expected = sp.Symbol("C_1") * sp.exp(3 * x) + sp.Symbol("C_2") * sp.exp(-2 * x)
    assert sp.simplify(parsed.candidates[0] - expected) == 0, parsed.candidates[0]


def test_parsed_answer_is_echoed_back_as_latex():
    """回顯「系統理解成什麼」比任何 parser 補丁都有效。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    verdict = verdict_for(problem, "C1e^{3x}+C2e^{-2x}")
    assert "C_{1}" in verdict.parsed_latex and "e^{3 x}" in verdict.parsed_latex


def test_ambiguous_power_produces_a_warning():
    """e^3x 會被讀成 (e^3)·x —— 一定要告訴學生，不能默默判錯。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    verdict = verdict_for(problem, "C1e^3x + C2e^-2x")
    assert any("e^(3x)" in w for w in verdict.warnings)


def test_frac_from_latex_is_understood():
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    parsed = parse_answer(r"C1*e^(3x) + \frac{C2}{e^{2x}}", problem.check)
    expected = sp.Symbol("C_1") * sp.exp(3 * x) + sp.Symbol("C_2") * sp.exp(-2 * x)
    assert sp.simplify(parsed.candidates[0] - expected) == 0


# --- 解析失敗時的訊息 ------------------------------------------------------

@pytest.mark.parametrize(
    "text,fragment",
    [
        ("", "type your answer"),
        ("   ", "type your answer"),
        ("C1*e^(3x", "check the brackets"),
        ("y = C1 = C2", "more than one"),
        ("y =", "nothing on one side"),
        ("f(x) + C1", "not a function you can use"),
        ("C1 . x", "decimal number"),
        ("x^2^3", "power of a power"),
        ("x**99999999", "unexpectedly large"),
        ("lambda x: x", "cannot be used here"),      # ':' 先被字元白名單擋下
        ("lambda(x)", "not allowed"),
        ("().__class__", "not allowed"),
        ("C1*e^(3x) + 我的答案", "basic Latin alphabet"),
        ("C1*e^(3x) ; import os", "cannot be used here"),
        ("import os", "not allowed"),
    ],
)
def test_parse_errors_are_actionable(text, fragment):
    """解析失敗要給出可行動的英文訊息，而不是丟 traceback。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    verdict = verdict_for(problem, text)
    assert verdict.code == "parse_error"
    assert fragment in verdict.detail, verdict.detail
    assert not verdict.correct and not verdict.partial


def test_parse_error_never_echoes_cjk():
    """錯誤訊息會被放回頁面上，因此不得回顯中日韓字元（D5）。

    這一項守的是一個很容易犯的錯：「把學生打錯的字元原樣回顯給他看」是好的
    UX，但只要學生打的是中文，介面就出現中文了。
    """
    import re

    cjk = re.compile(r"[　-〿一-鿿＀-￯]")
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    for text in ("答案是 C1*e^(3x)", "C1・e^(3x)", "ｙ＝C1"):
        verdict = verdict_for(problem, text)
        assert verdict.code == "parse_error"
        assert not cjk.search(verdict.detail), verdict.detail


def test_parse_error_mentions_the_syntax_help():
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    verdict = verdict_for(problem, "C1*e^(3x")
    assert "C1" in verdict.detail and "^" in verdict.detail


# --- 安全性 ---------------------------------------------------------------

MALICIOUS = [
    "__import__('os').system('id')",
    "().__class__.__bases__",
    "eval('1+1')",
    "exec('x=1')",
    "globals()",
    "lambda: 1",
    "open('/etc/passwd')",
    "9**9**9**9**9",
    "2^2^2^2^2^2",
    "x" * 500,
    "(" * 200,
    "1" * 400,
    "9999999999999999999999 ^ 9999999999",
    "C1*x" * 200,
]


@pytest.mark.parametrize("text", MALICIOUS)
def test_malicious_input_is_rejected_quickly(text):
    """惡意／超長輸入必須被擋下來，而且要快——不能靠 timeout 兜底。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    started = time.monotonic()
    verdict = verdict_for(problem, text)
    elapsed = time.monotonic() - started
    assert verdict.code == "parse_error", f"{text[:40]!r} 竟然沒被擋下：{verdict.code}"
    assert elapsed < 3.0, f"{text[:40]!r} 花了 {elapsed:.1f} 秒才被擋下"


def test_input_length_is_capped():
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    with pytest.raises(ParseError) as excinfo:
        parse_answer("1+" * 400 + "1", problem.check)
    assert "too long" in excinfo.value.message


def test_no_attribute_access_is_possible():
    """`.` 只准出現在數字中間，屬性存取一律擋掉。"""
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    for text in ("x.real", "(1).bit_length", "x . y"):
        assert code_for(problem, text) == "parse_error"
    # 但小數點要能正常使用
    assert parse_answer("0.5*C1*e^(3x)", problem.check).candidates


def test_unknown_symbols_are_capped():
    problem = generate("ode.second_order.homogeneous", 1, seed=1)
    verdict = verdict_for(problem, "a+b+c+d+f+g+h")
    assert verdict.code == "parse_error"
    assert "too many unknown letters" in verdict.detail
