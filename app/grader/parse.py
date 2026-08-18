"""學生輸入 → SymPy 運算式（PLAN.md §5.2）。

兩個目標，順序不能顛倒：

1. **安全**。`sympy.parsing.parse_expr` 底層走的是 `eval`，學生輸入是不可信輸入，
   所以這裡採「白名單思維」：先限制長度與**可用字元**，再限制可用名稱
   （`local_dict`／`global_dict` 都只放必要的東西），最後對解析結果再檢查一次
   複雜度。任何一關不過就丟 :class:`ParseError`，帶著**學生看得懂的英文訊息**。
   絕不 `eval`，也不接受屬性存取（`.` 只准出現在數字中間）。

2. **寬容**。學生不會打 LaTeX，也不該被逼著打。`C1e^{3x}`、`c_1 exp(3x)`、
   `y = ...`、`ln|y| = ...` 都要能吃下去。做不到的時候，錯誤訊息要說「該怎麼寫」，
   而不是丟一個 traceback。

判定端會把解析結果的 LaTeX 回顯給學生（"your answer was read as …"），
這比再多的 parser 補丁都有效——學生自己看得到系統理解成什麼。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from tokenize import TokenError

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from ..config import MAX_ANSWER_LENGTH
from ..generator.base import Check

TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

# global_dict 刻意只放 auto_symbol／auto_number 這兩個 transformation 自己會用到的
# 建構子。**特別是不放 `Function`**：這樣學生寫 `f(x)`、`g(2)` 這種未知函數呼叫時
# 會直接 NameError（我們轉成友善訊息），而不是被建成一個我們無法判定的物件。
SAFE_GLOBALS = {
    "Symbol": sp.Symbol,
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Rational": sp.Rational,
    "Number": sp.Number,
}

# 學生可以用的函數與常數，僅此而已
SAFE_FUNCTIONS = {
    "exp": sp.exp, "ln": sp.log, "log": sp.log, "sqrt": sp.sqrt,
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "arctan": sp.atan, "atan": sp.atan, "arcsin": sp.asin, "asin": sp.asin,
    "arccos": sp.acos, "acos": sp.acos,
    "e": sp.E, "pi": sp.pi,
}

ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "+-*/^=().,[]{}_|\\ \t\r\n"
)

# 明確禁止的片段（其實字元白名單已經擋掉大部分，這是第二道保險）
BANNED_SNIPPETS = ("__", "lambda", "import", "eval", "exec", "globals", "builtins")

MAX_OPS = 80                # 解析後的運算元個數上限
MAX_NUMBER = 10**6          # 數字大小上限
MAX_EXPONENT = 20           # 次方的指數上限（擋 x^999999 這種指數爆炸）
MAX_POWERS = 8              # `^` / `**` 出現次數上限（擋 2^2^2^2 這種塔）
MAX_EXTRA_SYMBOLS = 4       # 除了自變數以外，最多允許幾個符號（任意常數）

_DIGIT_RUN = re.compile(r"\d{7,}")
_BAD_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")
_EXPONENT = re.compile(r"(?:\^|\*\*)\s*\(?\s*[-+]?(\d+)")
# 次方塔（9^9^9^9）：parse_expr 會在**解析當下**就把它算出來，因此必須在進 parser
# 之前擋掉，光靠解析後的複雜度檢查來不及。
_POWER_TOWER = re.compile(r"(?:\^|\*\*)\s*\(?\s*[-+]?\d*\s*(?:\^|\*\*)")
_CONST_NAME = re.compile(r"^[A-Za-z]_?\d{0,2}$")
# C1 / c1 / C_1 / C_{1} / c_2 …（前面允許數字，因此 3C1x 也吃得下）
_CONST_TOKEN = re.compile(r"(?<![A-Za-z_])[Cc]_?\{?(\d{1,2})\}?(?![0-9])")
# e^3x 這種寫法的歧義：指數是數字、後面又緊接著變數
_AMBIGUOUS_POWER = re.compile(r"(?:\^|\*\*)\s*[-+]?\d+\s*[A-Za-z]")

SYNTAX_HELP = (
    "Use ^ or ** for powers, * for multiplication, and write the arbitrary "
    "constants as C1 and C2 — for example  y = C1*e^(3x) + C2*e^(-2x)  or  "
    "y = C1*exp(3*x) + C2*exp(-2*x)."
)


class ParseError(ValueError):
    """解析失敗。``message`` 是要顯示給學生的英文訊息，必須是可行動的。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class ParsedAnswer:
    """解析結果。

    ``candidates`` 通常只有一個元素；隱式解（例如 ``ln(y) = x^2/2 + C``）
    反解後可能有多個分支，任何一支判對就算對。
    """

    candidates: list                      # list[sp.Expr] 或 list[sp.Matrix]
    latex: str                            # 回顯給學生看「系統理解成什麼」
    warnings: list[str] = field(default_factory=list)
    implicit: bool = False


# --- 前置檢查與正規化 -------------------------------------------------------

def _pre_checks(raw: str) -> str:
    """在丟進 parser 之前先擋掉不該進來的東西。"""
    if raw is None:
        raise ParseError("Please type your answer first.")
    text = raw.strip()
    if not text:
        raise ParseError("Please type your answer first.")
    if len(text) > MAX_ANSWER_LENGTH:
        raise ParseError(
            f"Your answer is too long ({len(text)} characters; the limit is "
            f"{MAX_ANSWER_LENGTH}). Please simplify it before submitting."
        )

    bad = sorted({c for c in text if c not in ALLOWED_CHARS})
    if bad:
        # 只回顯可見的 ASCII 字元。非 ASCII 一律不回顯：一來看不出所以然，
        # 二來介面不得出現中日韓字元（D5），回顯等於把它放回頁面上。
        if all(c.isprintable() and c.isascii() for c in bad):
            shown = " ".join(repr(c) for c in bad[:5])
            raise ParseError(
                f"Your answer contains characters that cannot be used here: "
                f"{shown}. " + SYNTAX_HELP
            )
        raise ParseError(
            "Your answer contains characters outside the basic Latin alphabet "
            "(for example full-width or accented characters). Please retype it "
            "using plain ASCII. " + SYNTAX_HELP
        )

    lowered = text.lower()
    for snippet in BANNED_SNIPPETS:
        if snippet in lowered:
            raise ParseError(
                f"'{snippet}' is not allowed in an answer. " + SYNTAX_HELP
            )

    if _BAD_DOT.search(text):
        raise ParseError(
            "A '.' may only appear inside a decimal number, such as 0.5. "
            + SYNTAX_HELP
        )
    if _DIGIT_RUN.search(text):
        raise ParseError("The numbers in your answer are unexpectedly large.")
    if text.count("^") + text.count("**") > MAX_POWERS:
        raise ParseError("Your answer contains too many powers.")
    if _POWER_TOWER.search(text):
        raise ParseError(
            "A power of a power is not expected here. Please write the exponent "
            "out, for example x^6 instead of x^2^3."
        )
    for match in _EXPONENT.finditer(text):
        if int(match.group(1)) > MAX_EXPONENT:
            raise ParseError(
                f"Exponents larger than {MAX_EXPONENT} are not expected here."
            )
    return text


def _expand_latex_frac(s: str) -> str:
    r"""把 ``\frac{a}{b}`` 改寫成 ``((a)/(b))``（學生從講義複製貼上時很常見）。"""
    out = []
    i = 0
    while True:
        j = s.find("\\frac", i)
        if j < 0:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:j])
        k = j + len("\\frac")
        parts = []
        for _ in range(2):
            while k < len(s) and s[k] == " ":
                k += 1
            if k >= len(s) or s[k] != "{":
                raise ParseError(
                    r"Could not read a \frac{...}{...} in your answer. "
                    "Please write it as a / b instead."
                )
            depth, start = 0, k
            while k < len(s):
                if s[k] == "{":
                    depth += 1
                elif s[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if depth != 0:
                raise ParseError("Unbalanced { } in your answer.")
            parts.append(s[start + 1:k])
            k += 1
        out.append(f"(({_expand_latex_frac(parts[0])})/({_expand_latex_frac(parts[1])}))")
        i = k


def _bars_to_parens(s: str) -> str:
    """把成對的 ``|`` 當成括號：``ln|y|`` → ``ln(y)``。

    ODE 課本寫 $\\ln|y|$ 只是為了涵蓋 y < 0 的分支，判定上不影響
    （我們判的是「代回原式是否成立」，兩個分支都成立）。
    """
    out, open_bar = [], False
    for ch in s:
        if ch == "|":
            out.append(")" if open_bar else "(")
            open_bar = not open_bar
        else:
            out.append(ch)
    if open_bar:
        raise ParseError("Unbalanced | | in your answer.")
    return "".join(out)


def _normalize_constants(s: str) -> str:
    """C1 / c_1 / C_{2} → C_1 / C_2，並補上被省略的乘號。

    補乘號是關鍵：若直接把 ``C1e^(3x)`` 換成 ``C_1e^(3x)``，tokenizer 會把
    ``C_1e`` 讀成**一個**符號名稱，整個式子就錯了（PLAN.md §5.2 的已知邊界情形）。
    """
    out, last = [], 0
    for m in _CONST_TOKEN.finditer(s):
        head = s[last:m.start()]
        if head[-1:].isalnum() or head[-1:] == ")":
            head += "*"
        out.append(head + "C_" + m.group(1))
        last = m.end()
        nxt = s[last:last + 1]
        if nxt.isalnum() or nxt == "(":
            out.append("*")
    out.append(s[last:])
    return "".join(out)


def normalize(text: str) -> str:
    """把常見的手寫／LaTeX 寫法轉成 parser 吃得下的形式。"""
    s = text.replace("−", "-")                     # unicode 減號
    s = s.replace("\\left", "").replace("\\right", "")
    s = _expand_latex_frac(s)
    s = _bars_to_parens(s)
    s = _normalize_constants(s)                    # 要在 { } → ( ) 之前，才吃得到 C_{1}
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = s.replace("\\", "")                        # \exp → exp、\sin → sin
    s = s.replace("{", "(").replace("}", ")")
    return s


# --- 解析 -------------------------------------------------------------------

def _parse_one(source: str, local_dict: dict) -> sp.Expr:
    """呼叫 SymPy 的 parser，並把它各式各樣的例外翻成一句人話。"""
    try:
        expr = parse_expr(
            source,
            local_dict=local_dict,
            global_dict=dict(SAFE_GLOBALS),
            transformations=TRANSFORMS,
            evaluate=True,
        )
    except NameError as exc:                        # 未知函數呼叫，例如 f(x)
        raise ParseError(
            f"'{_name_from_error(exc)}' is not a function you can use here. "
            "Available functions: exp, ln, sqrt, sin, cos, tan. " + SYNTAX_HELP
        ) from exc
    except (SyntaxError, TypeError, AttributeError, ValueError, TokenError) as exc:
        raise ParseError(
            "Could not read your answer — please check the brackets and "
            "operators. " + SYNTAX_HELP
        ) from exc
    except RecursionError as exc:
        raise ParseError("Your answer is nested too deeply.") from exc

    if not isinstance(expr, sp.Basic):
        raise ParseError("Your answer is not a mathematical expression. " + SYNTAX_HELP)
    if expr.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        raise ParseError("Your answer contains a division by zero or an infinity.")
    return expr


def _name_from_error(exc: Exception) -> str:
    m = re.search(r"'([^']+)'", str(exc))
    return m.group(1) if m else "that name"


def _post_checks(expr: sp.Expr, allowed_symbols: set[sp.Symbol]) -> None:
    """解析成功之後的複雜度與符號檢查（擋 x^(12^12) 這類東西）。"""
    extras = [s for s in expr.free_symbols if s not in allowed_symbols]
    if len(extras) > MAX_EXTRA_SYMBOLS:
        raise ParseError(
            "Your answer contains too many unknown letters: "
            + ", ".join(sorted(str(s) for s in extras)[:6])
        )
    for sym in extras:
        if not _CONST_NAME.match(sym.name):
            raise ParseError(
                f"'{sym.name}' is not a valid name here. " + SYNTAX_HELP
            )
    if sp.count_ops(expr) > MAX_OPS:
        raise ParseError(
            "Your answer is more complicated than this exercise expects. "
            "Please simplify it before submitting."
        )
    for number in expr.atoms(sp.Number):
        if number.is_finite and abs(number) > MAX_NUMBER:
            raise ParseError("The numbers in your answer are unexpectedly large.")
    for power in expr.atoms(sp.Pow):
        if power.exp.is_Number and abs(power.exp) > MAX_EXPONENT:
            raise ParseError(
                f"Exponents larger than {MAX_EXPONENT} are not expected here."
            )


def _split_equation(text: str) -> tuple[str | None, str]:
    """``y = ...`` → ``(lhs, rhs)``；沒有等號則 lhs 為 None。"""
    if text.count("=") > 1:
        raise ParseError("Your answer contains more than one '=' sign.")
    if "=" not in text:
        return None, text
    lhs, rhs = text.split("=", 1)
    if not lhs.strip() or not rhs.strip():
        raise ParseError("There is nothing on one side of the '=' sign.")
    return lhs.strip(), rhs.strip()


_UNKNOWN_LHS = {"y", "y(x)", "y(t)", "f(x)", "u", "u(x)", "x", "x(t)"}


def _is_unknown_lhs(lhs: str) -> bool:
    return lhs.replace(" ", "").lower() in _UNKNOWN_LHS


def _split_components(text: str) -> list[str]:
    """把向量答案切成分量：換行、分號，或最外層的逗號都可以。"""
    stripped = text.strip()
    if stripped[:1] in "([" and stripped[-1:] in ")]":
        inner = stripped[1:-1]
        if _top_level_commas(inner):
            stripped = inner
    parts = [p for p in re.split(r"[\n;]+", stripped) if p.strip()]
    if len(parts) == 1:
        idx = _top_level_commas(parts[0])
        if idx:
            chunks, prev = [], 0
            for i in idx:
                chunks.append(parts[0][prev:i])
                prev = i + 1
            chunks.append(parts[0][prev:])
            parts = chunks
    return [p.strip() for p in parts if p.strip()]


def _top_level_commas(s: str) -> list[int]:
    depth, out = 0, []
    for i, ch in enumerate(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(i)
    return out


def parse_answer(raw: str, check: Check) -> ParsedAnswer:
    """把學生的原始輸入轉成一組候選答案。

    失敗一律丟 :class:`ParseError`，訊息可以直接顯示給學生。
    """
    text = _pre_checks(raw)
    warnings: list[str] = []
    if _AMBIGUOUS_POWER.search(text):
        warnings.append(
            "Note: e^3x is read as (e^3)·x. Write e^(3x) if you meant the "
            "exponent to include x."
        )
    if "|" in text:
        warnings.append("Absolute value bars were read as ordinary brackets.")

    local = dict(SAFE_FUNCTIONS)
    local[check.var.name] = check.var          # 用 generator 的同一顆符號（含 assumptions）

    if check.kind == "system":
        return _parse_system(text, check, local, warnings)
    return _parse_scalar(text, check, local, warnings)


def _parse_scalar(text, check, local, warnings) -> ParsedAnswer:
    lhs, rhs = _split_equation(text)
    allowed = {check.var}

    if lhs is None or _is_unknown_lhs(lhs):
        expr = _parse_one(normalize(rhs), dict(local))
        _post_checks(expr, allowed)
        if any(s.name == "y" for s in expr.free_symbols):
            raise ParseError(
                "Your answer still contains y on the right-hand side. Please "
                "solve for y explicitly, or write the whole relation as an "
                "equation such as  ln(y) = x^2/2 + C1."
            )
        return ParsedAnswer([expr], sp.latex(expr), warnings)

    # 隱式解：F(x, y) = G(x, y)。先反解出 y，再用「代回原式」的標準流程判定，
    # 這對 C 與 e^C 的重新參數化完全免疫（PLAN.md §5.4）。
    yv = sp.Symbol("y")
    local_impl = dict(local, y=yv)
    left = _parse_one(normalize(lhs), local_impl)
    right = _parse_one(normalize(rhs), local_impl)
    relation = left - right
    _post_checks(relation, {check.var, yv})
    if yv not in relation.free_symbols:
        raise ParseError(
            "Your answer does not involve y. Please write it as  y = ...  or as "
            "an implicit relation containing y."
        )
    try:
        solutions = sp.solve(sp.Eq(left, right), yv)
    except (NotImplementedError, RecursionError, TypeError) as exc:
        raise ParseError(
            "Could not solve your relation for y. Please give the explicit "
            "solution in the form  y = ..."
        ) from exc
    solutions = [s for s in solutions if not s.has(yv)]
    if not solutions:
        raise ParseError(
            "Could not solve your relation for y. Please give the explicit "
            "solution in the form  y = ..."
        )
    for sol in solutions:
        _post_checks(sol, {check.var})
    latex = sp.latex(sp.Eq(left, right))
    return ParsedAnswer(solutions, latex, warnings, implicit=True)


def _parse_system(text, check, local, warnings) -> ParsedAnswer:
    parts = _split_components(text)
    if len(parts) != check.dim:
        raise ParseError(
            f"This system has {check.dim} components, but {len(parts)} were "
            "found. Write one component per line, or separate them with a "
            "comma — for example  x1 = C1*e^(2t) + C2*e^(-t),  "
            "x2 = C1*e^(2t) - C2*e^(-t)."
        )

    exprs = []
    for part in parts:
        lhs, rhs = _split_equation(part)
        if lhs is not None and not re.fullmatch(
            r"[xy]_?\d?(\(\s*[a-z]\s*\))?", lhs.replace(" ", ""), re.IGNORECASE
        ):
            raise ParseError(
                f"'{lhs}' is not a component name. Use x1 and x2 (or leave the "
                "left-hand side out entirely)."
            )
        expr = _parse_one(normalize(rhs), dict(local))
        _post_checks(expr, {check.var})
        exprs.append(expr)

    vec = sp.Matrix(exprs)
    return ParsedAnswer([vec], sp.latex(vec, mat_delim="("), warnings)
