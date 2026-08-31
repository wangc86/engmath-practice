r"""待定係數法（PLAN.md §2.4(e)、階段 2A 的 2a；課綱 W11）。

本檔註冊**一個**題型 ``ode.second_order.undetermined``，三個難度就是
**共振重數 $m$ = 0 / 1 / 2**。

---

## 為什麼難度軸是 $m$ 而不是「右式有多複雜」

因為 $m$ 是這個題型唯一真正教的東西。右式從 $e^{sx}$ 換成
$k\cos\omega x$ 只是換一組基底，流程一個字都沒有變；而**忘記乘 $x^m$**
會讓學生得到一個矛盾式：

    y_p = A e^{3x} 代進 y'' - y' - 6y = 5e^{3x}
      →  A(9 - 3 - 6) e^{3x} = 5 e^{3x}
      →  0 = 5 e^{3x}          ← 無解，而學生通常會以為自己算錯係數

那個 $0 = k e^{sx}$ 正是課堂上要讓學生撞一次的牆。把它放在難度軸上，
學生從難度 1 練到難度 3 就是「不共振 → 單根共振 → 重根共振」這條線。

PLAN §2.4(e) 的原話也是這樣寫的：「`m` 這個變數就是難度旋鈕」。

## 三個難度底下的隨機來源

難度只固定 $m$，**不固定右式的形式**，所以同一個難度重抽會拿到不同的族：

| 難度 | $m$ | 可能的右式 | 特徵根 |
|---|---|---|---|
| 1 | 0 | $k e^{sx}$（$s$ 不是根）／多項式／$k\cos\omega x$、$k\sin\omega x$ | 兩相異實根 |
| 2 | 1 | $k e^{sx}$（$s$ **是**單根）／$k\cos\beta x$、$k\sin\beta x$（純共振） | 兩相異實根／$\pm\beta i$ |
| 3 | 2 | $k e^{rx}$（$r$ 是重根） | 重根 $r$ |

⚠️ **難度 2 的「純共振」那一格值得單獨看一眼**：特徵根是 $\pm\beta i$，
齊次解就是 $C_1\cos\beta x + C_2\sin\beta x$，而右式 $k\cos\beta x$ 恰好是
其中一項——這是物理上的共振（無阻尼系統被自然頻率驅動），答案裡的
$x\sin\beta x$ 就是振幅隨時間線性增長。它與指數那一格在數學上是同一件事，
但**學生第一次看到時通常不覺得是同一件事**，所以兩個都要出得到。

## 難度 3 為什麼只有指數一種

$m = 2$ 需要「重根，而且右式的指數恰好落在那個重根上」。

- 多項式版本的 $m=2$ 要 $0$ 是重根，也就是 $a_1 = a_0 = 0$，方程退化成
  $y'' = g(x)$——那不是待定係數法，那是積分兩次。
- 三角版本的 $m=2$ 要 $\pm\beta i$ 各是二重根，特徵方程是四次的，
  超出本課程二階常係數的範圍。

所以難度 3 留一種，**不是漏掉**。變化來自 $r$（六個值）與 $k$（十個值）。

## 初值問題：本檔的第二個隨機軸

每一題都有一半的機率帶初值條件 $y(0) = y_0$、$y'(0) = y_1$（求特解），
另一半求通解。**這一軸與難度正交**——難度仍然只由 $m$ 決定。

> ⚠️ **PLAN §6 說 2a「會第一次帶進純量的初值問題」，那句話現在是過期的。**
> v0.24 的 `ode/laplace.py` 已經先做了，`Check.ic_derivative_values`
> 也是那一輪為它加的。所以本檔**沒有**擴充驗證閘門，它是那個欄位的
> 第二個使用者——而這正是要確認的事情：同一個欄位在一個
> **不經過拉普拉斯**的題型上一樣夠用（`ic_residual_of()` 只做微分與代入，
> 它從來不知道答案是怎麼來的）。

---

## 驗證閘門

`Check` 直接可用，一行都不必改：

    residual_expr = y'' + a1 y' + a0 y - g(x)     （含 unknown = y(x)）
    ic_point = 0, ic_value = y0, ic_derivative_values = (y1,)

**閘門與生成路徑的獨立程度**：生成路徑是「解一組線性方程求待定係數」
（`sp.solve`），閘門路徑是「把答案代回去微分」——後者連一次 `solve`
都沒有呼叫。一個把 $x^m$ 忘掉的 bug 會讓 `sp.solve` 回傳空解（於是本檔
回 `None` 重抽），而一個把 $m$ 算大一號的 bug 會讓 `y_p` 多一個
齊次項——**那仍然是正確答案**（多出來的部分被 $C_1, C_2$ 吸收），
閘門不會叫，也不應該叫。守著 $m$ 本身的是
`test_the_resonance_multiplicity_is_what_the_difficulty_promises`。

## 漂亮度的拒絕抽樣在這裡做，不在 `base.generate()` 裡

待定係數的解是 $k / p(s)$ 這種東西，分母是特徵多項式在 $s$ 的值，
很容易跑出 $\frac{5}{50}$ 這種東西。`base.generate()` 只看驗證閘門
（醜答案照樣是正確答案），所以門檻要由本檔自己擋——不通過就回 `None`，
`generate()` 會換一組參數再來。實測通過率：指數 86%、多項式 87%、
三角 47%、共振的三格 100%（共振格的分母只有 $\pm(r_1-r_2)$ 或 $2\beta$）。
"""

from __future__ import annotations

import random

import sympy as sp

from ..base import Check, Problem, Step, register
from ..pretty import has_special_function, has_ugly_fraction, ugliness

x = sp.Symbol("x", positive=True)
C1, C2 = sp.symbols("C_1 C_2")
_y = sp.Function("y")(x)          # 驗證閘門用的未知函數 y(x)

TEMPLATE_ID = "ode.second_order.undetermined"
CHAPTER = "Second-Order ODEs"

#: 特徵根的白名單。**不含 0**——$0$ 是根會讓 $a_0 = 0$，方程退化成
#: 一階（對 $y'$ 而言），而多項式右式在那裡的共振重數會偷偷變成 1。
ROOTS = (-3, -2, -1, 1, 2, 3)

#: 右式指數 $s$ 的候選。**不含 0**：$s=0$ 的 $ke^{0x}$ 就是常數右式，
#: 那是多項式那一格的事，而 $e^{0 \cdot x}$ 印出來也很怪。
EXPONENTS = (-4, -3, -2, -1, 1, 2, 3, 4)

BETAS = (1, 2, 3)
OMEGAS = (1, 2, 3)
FORCING_COEFFS = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
POLY_COEFFS = (-3, -2, -1, 1, 2, 3)
IC_VALUES = (-2, -1, 0, 1, 2)

#: 與 `tests/test_generators.py` 的 `UGLINESS_LIMIT` **刻意逐字相同**。
#: 生成端擋得比測試鬆，測試就會紅；擋得比測試嚴，測試就守不到東西。
UGLINESS_LIMIT = {1: 25, 2: 35, 3: 45}

DIFFICULTY_NOTES = {
    1: "No resonance (m = 0)",
    2: "Simple resonance (m = 1)",
    3: "Double resonance at a repeated root (m = 2)",
}


# --- 排版 -------------------------------------------------------------------


def _lhs_latex(a1: int, a0: int) -> str:
    """把 y'' + a₁y' + a₀y 排版成正常的數學寫法（不出現 `+ -3`）。"""
    parts = ["y''"]
    for coeff, term in ((a1, "y'"), (a0, "y")):
        if coeff == 0:
            continue
        sign = "+" if coeff > 0 else "-"
        magnitude = abs(coeff)
        head = "" if magnitude == 1 else str(magnitude)
        parts.append(f"{sign} {head}{term}")
    return " ".join(parts)


def _ic_latex(y0: int, y1: int) -> str:
    return rf"y(0) = {y0},\quad y'(0) = {y1}"


def _equation_latex(a1: int, a0: int, g: sp.Expr) -> str:
    return f"{_lhs_latex(a1, a0)} = {sp.latex(g)}"


# --- 待定係數的核心：試解、代入、比較係數 -----------------------------------


def _multiplicity(roots: tuple, value) -> int:
    """`value` 在特徵根裡出現幾次。這就是要乘上去的 $x^m$ 的 $m$。"""
    return sum(1 for r in roots if sp.simplify(r - value) == 0)


def _matching_equations(residual: sp.Expr, carriers: list, unknowns: list):
    """把「代入後令殘差為 0」拆成一組對未知係數的線性方程。

    殘差一定寫得成 $\\sum_c P_c(x)\\, c$ 的形式，其中 $c$ 跑遍 `carriers`
    （指數那一格是 $\\{e^{sx}\\}$、多項式是 $\\{1\\}$、三角是
    $\\{\\cos\\omega x, \\sin\\omega x\\}$），$P_c$ 是 $x$ 的多項式。
    每一個 $P_c$ 的每一個係數都必須是 0，那就是要比較的那組方程。

    ⚠️ **刻意不用 `sp.solve` 的回傳值反推方程**：那樣印出來的是解，
    而學生要看的是**他自己動手時會寫下的那幾行**。
    """
    equations: list[sp.Eq] = []
    expanded = sp.expand(residual)
    for carrier in carriers:
        part = expanded if carrier == 1 else expanded.coeff(carrier)
        if part == 0:
            continue
        for coefficient in sp.Poly(part, x).all_coeffs():
            if not any(coefficient.has(u) for u in unknowns):
                continue                      # 恆等式，沒有東西要比較
            constant = coefficient.subs({u: 0 for u in unknowns})
            equations.append(sp.Eq(sp.expand(coefficient - constant),
                                   sp.expand(-constant)))
    return equations


def _system_latex(equations: list) -> str:
    return r",\quad ".join(sp.latex(eq) for eq in equations)


def _solved_latex(unknowns: list, solution: dict) -> str:
    return r",\quad ".join(
        sp.latex(sp.Eq(u, sp.nsimplify(solution[u]))) for u in unknowns
    )


def _solve_particular(a1: int, a0: int, basis: list, g: sp.Expr, m: int,
                      unknowns: list, carriers: list):
    """求特解。回傳 `(y_p, 比較係數的方程, 解出來的係數)`，失敗回 `None`。"""
    trial = sum(u * x**m * b for u, b in zip(unknowns, basis))
    residual = sp.expand(sp.diff(trial, x, 2) + a1 * sp.diff(trial, x)
                         + a0 * trial - g)
    equations = _matching_equations(residual, carriers, unknowns)
    solutions = sp.solve(equations, unknowns, dict=True)
    if not solutions:
        return None                            # $m$ 算錯時會走到這裡（無解）
    solution = solutions[0]
    if any(u not in solution for u in unknowns):
        return None                            # 係數沒有被唯一決定
    return sp.expand(trial.subs(solution)), equations, solution


def _apply_initial_conditions(general: sp.Expr, y0: int, y1: int):
    """代入 $y(0)=y_0$、$y'(0)=y_1$ 解出 $C_1, C_2$。失敗回 `None`。"""
    residuals = [
        sp.expand(general.subs(x, 0) - y0),
        sp.expand(sp.diff(general, x).subs(x, 0) - y1),
    ]
    matrix, rhs = sp.linear_eq_to_matrix(residuals, [C1, C2])
    if matrix.det() == 0:
        return None
    values = matrix.solve(rhs)
    constants = {C1: sp.nsimplify(values[0]), C2: sp.nsimplify(values[1])}
    return sp.expand(general.subs(constants)), constants


# --- 三種右式的參數抽樣 -----------------------------------------------------


def _draw_case(rng: random.Random, difficulty: int) -> dict | None:
    """抽一組參數。回傳的字典描述整題，之後的組裝完全由它決定。"""
    if difficulty == 1:
        family = rng.choice(("exponential", "polynomial", "trigonometric"))
    elif difficulty == 2:
        family = rng.choice(("exponential", "trigonometric"))
    else:
        family = "exponential"

    A, B = sp.symbols("A B")

    if family == "exponential":
        if difficulty == 1:
            r1, r2 = rng.sample(ROOTS, 2)
            s = rng.choice([e for e in EXPONENTS if e not in (r1, r2)])
        elif difficulty == 2:
            r1, r2 = rng.sample(ROOTS, 2)
            s = r1
        else:
            r1 = r2 = rng.choice(ROOTS)
            s = r1
        k = rng.choice(FORCING_COEFFS)
        roots = (r1, r2)
        return {
            "family": "exponential", "roots": roots, "s": s, "k": k,
            "g": k * sp.exp(s * x),
            "basis": [sp.exp(s * x)], "carriers": [sp.exp(s * x)],
            "unknowns": [A],
            "m": _multiplicity(roots, s),
            "resonance_symbol": sp.latex(sp.Eq(sp.Symbol("s"), s)),
        }

    if family == "polynomial":
        r1, r2 = rng.sample(ROOTS, 2)
        degree = rng.choice((1, 2))
        coefficients = [rng.choice(POLY_COEFFS) for _ in range(degree)]
        coefficients.append(rng.choice(POLY_COEFFS + (0,)))
        g = sum(c * x**(degree - i) for i, c in enumerate(coefficients))
        unknowns = list(sp.symbols(f"A_0:{degree + 1}"))
        return {
            "family": "polynomial", "roots": (r1, r2), "s": 0,
            "degree": degree, "g": sp.expand(g),
            "basis": [x**j for j in range(degree + 1)], "carriers": [1],
            "unknowns": unknowns,
            "m": _multiplicity((r1, r2), 0),
            "resonance_symbol": r"s = 0",
        }

    # trigonometric
    if difficulty == 1:
        r1, r2 = rng.sample(ROOTS, 2)
        omega = rng.choice(OMEGAS)
        roots = (r1, r2)
        m = 0
    else:
        omega = rng.choice(BETAS)
        roots = (sp.I * omega, -sp.I * omega)
        m = 1
    k = rng.choice(FORCING_COEFFS)
    use_cosine = rng.random() < 0.5
    g = k * (sp.cos(omega * x) if use_cosine else sp.sin(omega * x))
    return {
        "family": "trigonometric", "roots": roots, "omega": omega, "k": k,
        "use_cosine": use_cosine, "g": g,
        "basis": [sp.cos(omega * x), sp.sin(omega * x)],
        "carriers": [sp.cos(omega * x), sp.sin(omega * x)],
        "unknowns": [sp.Symbol("A"), sp.Symbol("B")],
        "m": m,
        "resonance_symbol": rf"s = \pm {omega}i" if omega != 1 else r"s = \pm i",
    }


def _homogeneous(spec: dict):
    """齊次解、特徵根的 LaTeX、以及 $(a_1, a_0)$。"""
    roots = spec["roots"]
    if spec["family"] == "trigonometric" and spec["m"] == 1:
        beta = spec["omega"]
        a1, a0 = 0, beta**2
        y_h = C1 * sp.cos(beta * x) + C2 * sp.sin(beta * x)
        roots_latex = rf"r = \pm {beta}i" if beta != 1 else r"r = \pm i"
        return a1, a0, y_h, roots_latex, "a pair of purely imaginary roots"

    r1, r2 = int(roots[0]), int(roots[1])
    if r1 == r2:
        a1, a0 = -2 * r1, r1**2
        y_h = (C1 + C2 * x) * sp.exp(r1 * x)
        return a1, a0, y_h, rf"r_1 = r_2 = {r1}\quad(\text{{repeated}})", "a repeated root"
    a1, a0 = -(r1 + r2), r1 * r2
    y_h = C1 * sp.exp(r1 * x) + C2 * sp.exp(r2 * x)
    return a1, a0, y_h, rf"r_1 = {r1},\quad r_2 = {r2}", "two distinct real roots"


# --- 逐步解答 ---------------------------------------------------------------

_RESONANCE_NOTES = {
    0: (
        "The exponent on the right-hand side is not a characteristic root, so "
        "$m = 0$ and the trial solution needs no extra factor of $x$."
    ),
    1: (
        "The exponent on the right-hand side **is** a characteristic root, so "
        "$m = 1$. Without the factor of $x$ the trial solution would only "
        "reproduce a homogeneous solution: substituting it would annihilate "
        "the left-hand side and leave the contradiction $0 = g(x)$."
    ),
    2: (
        "The exponent on the right-hand side is a *repeated* characteristic "
        "root, so $m = 2$. Both $Ae^{rx}$ and $Axe^{rx}$ already solve the "
        "homogeneous equation, so either of them would give the contradiction "
        "$0 = g(x)$; two extra factors of $x$ are needed."
    ),
}


def _steps(spec: dict, a1: int, a0: int, y_h, roots_latex: str, case_name: str,
           trial_latex: str, equations: list, solution: dict,
           y_p, general, particular) -> list[Step]:
    r = sp.Symbol("r")
    steps = [
        Step(
            "Solve the homogeneous equation first",
            sp.latex(sp.Eq(r**2 + a1 * r + a0, 0)),
            "The method of undetermined coefficients needs the characteristic "
            "roots before anything else — they are what decides whether the "
            "trial solution has to be multiplied by a power of $x$.",
        ),
        Step(f"Find the characteristic roots ({case_name})", roots_latex),
        Step("Write the homogeneous solution", rf"y_h(x) = {sp.latex(y_h)}"),
        Step(
            "Compare the right-hand side with the characteristic roots",
            rf"{spec['resonance_symbol']},\quad m = {spec['m']}",
            _RESONANCE_NOTES[spec["m"]],
        ),
        Step(
            "Set up the trial particular solution",
            rf"y_p(x) = {trial_latex}",
            "Every function that appears when the trial solution is "
            "differentiated has to be included, which is why the "
            "cosine and the sine always travel together."
            if spec["family"] == "trigonometric" else
            "The trial solution keeps the shape of the right-hand side, "
            "with the undetermined coefficients left to be found.",
        ),
        Step(
            "Substitute and compare coefficients",
            _system_latex(equations),
            "Substitute $y_p$ into the left-hand side, collect like terms, and "
            "match them against the right-hand side.",
        ),
        Step("Solve for the undetermined coefficients",
             _solved_latex(spec["unknowns"], solution)),
        Step("Particular solution", rf"y_p(x) = {sp.latex(y_p)}"),
    ]
    if particular is None:
        steps.append(Step(
            "General solution",
            rf"y(x) = {sp.latex(general)}",
            "The general solution is the homogeneous solution plus any one "
            "particular solution.",
        ))
        return steps

    answer, constants, y0, y1 = particular
    steps.append(Step(
        "General solution",
        rf"y(x) = {sp.latex(general)}",
        "The general solution is the homogeneous solution plus any one "
        "particular solution.",
    ))
    steps.append(Step(
        "Apply the initial conditions",
        r",\quad ".join([
            sp.latex(sp.Eq(sp.Symbol("y(0)"), sp.Integer(y0), evaluate=False)),
            sp.latex(sp.Eq(sp.Symbol("y'(0)"), sp.Integer(y1), evaluate=False)),
            sp.latex(sp.Eq(C1, constants[C1])),
            sp.latex(sp.Eq(C2, constants[C2])),
        ]),
        "Both conditions are applied to the *general* solution — the "
        "particular solution $y_p$ contributes to $y(0)$ and $y'(0)$ as well, "
        "so the constants cannot be read off from $y_h$ alone.",
    ))
    steps.append(Step("Solution of the initial-value problem",
                      rf"y(x) = {sp.latex(answer)}"))
    return steps


@register(
    TEMPLATE_ID,
    name="Undetermined Coefficients (Second-Order)",
    chapter=CHAPTER,
    difficulty_notes=DIFFICULTY_NOTES,
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    spec = _draw_case(rng, difficulty)
    expected_m = {1: 0, 2: 1, 3: 2}[difficulty]
    if spec["m"] != expected_m:
        return None                      # 抽壞了（不該發生，但擋在這裡最便宜）

    a1, a0, y_h, roots_latex, case_name = _homogeneous(spec)
    solved = _solve_particular(a1, a0, spec["basis"], spec["g"], spec["m"],
                               spec["unknowns"], spec["carriers"])
    if solved is None:
        return None
    y_p, equations, solution = solved
    if not equations:
        return None                      # 沒有東西可以比較 → 不是這個題型
    general = sp.expand(y_h + y_p)

    wants_ic = rng.random() < 0.5
    particular = None
    if wants_ic:
        y0, y1 = rng.choice(IC_VALUES), rng.choice(IC_VALUES)
        applied = _apply_initial_conditions(general, y0, y1)
        if applied is None:
            return None
        answer_expr, constants = applied
        particular = (answer_expr, constants, y0, y1)
    else:
        answer_expr = general

    # 漂亮度的拒絕抽樣（見檔頭）。特解本身也要看——一個漂亮的通解
    # 完全可能經過一個分母 50 的 $y_p$，而那正是學生要動手算的東西。
    for expression in (answer_expr, y_p):
        if has_special_function(expression) or has_ugly_fraction(expression):
            return None
    if ugliness(answer_expr) > UGLINESS_LIMIT[difficulty]:
        return None

    trial_latex = sp.latex(
        sum(u * x**spec["m"] * b for u, b in zip(spec["unknowns"], spec["basis"]))
    )

    if particular is None:
        statement = ("Find the general solution of the following second-order "
                     "equation using the method of undetermined coefficients.")
        statement_latex = _equation_latex(a1, a0, spec["g"])
        n_constants = 2
        check = Check(
            var=x, kind="scalar", n_constants=2, order=2, unknown=_y,
            residual_expr=(sp.Derivative(_y, (x, 2)) + a1 * sp.Derivative(_y, x)
                           + a0 * _y - spec["g"]),
            linear=True,
        )
    else:
        _, _, y0, y1 = particular
        statement = ("Solve the following initial-value problem using the "
                     "method of undetermined coefficients.")
        statement_latex = (f"{_equation_latex(a1, a0, spec['g'])},"
                          rf"\quad {_ic_latex(y0, y1)}")
        n_constants = 0
        check = Check(
            var=x, kind="scalar", n_constants=0, order=2, unknown=_y,
            residual_expr=(sp.Derivative(_y, (x, 2)) + a1 * sp.Derivative(_y, x)
                           + a0 * _y - spec["g"]),
            ic_point=sp.Integer(0),
            ic_value=sp.Integer(y0),
            ic_derivative_values=(sp.Integer(y1),),
            linear=True,
        )

    params = {
        "family": spec["family"],
        "m": spec["m"],
        "a1": int(a1),
        "a0": int(a0),
        "roots": [str(r) for r in spec["roots"]],
        "is_ivp": particular is not None,
        "n_constants": n_constants,
    }
    for key in ("s", "k", "omega", "degree", "use_cosine"):
        if key in spec:
            params[key] = spec[key] if not isinstance(spec[key], sp.Basic) else str(spec[key])
    if particular is not None:
        params["y0"], params["y1"] = particular[2], particular[3]

    return Problem(
        template_id=TEMPLATE_ID,
        difficulty=difficulty,
        seed=0,
        params=params,
        statement=statement,
        statement_latex=statement_latex,
        answer_latex=rf"y(x) = {sp.latex(answer_expr)}",
        answer_expr=answer_expr,
        steps=_steps(spec, a1, a0, y_h, roots_latex, case_name, trial_latex,
                     equations, solution, y_p, general, particular),
        check=check,
    )
