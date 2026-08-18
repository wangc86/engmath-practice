"""判定流程（PLAN.md §5.3）。

本模組的函式會在**子行程**裡執行（見 sandbox.py），因此：

- 只能收 picklable 的參數（`Check`、SymPy 運算式、字串），不能收 closure；
- 不碰資料庫、不碰 session、不碰任何個資——判定是純函式。

判定的核心是「驗證性質，不比對形式」：

    通解正確  ⇔  (a) 代回原方程殘差為 0
                 且 (b) 任意常數個數 = 方程階數
                 且 (c) 對常數的偏導線性獨立（Wronskian ≠ 0）

初值問題則因為解唯一，改為「殘差為 0 + 滿足初始條件 + 沒有殘留的任意常數」，
這在數學上等價於與標準答案嚴格相同，但比直接相減穩健得多
（相減要靠 simplify 化到 0，而 simplify 並不完備）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp

from ..generator.base import Check
from . import feedback
from .equivalence import constants_of, independent_constants, is_zero
from .parse import ParsedAnswer, ParseError, parse_answer


@dataclass
class Verdict:
    """一次判定的結果。所有文字都是英文，可直接顯示給學生。"""

    code: str
    headline: str
    detail: str
    correct: bool = False
    partial: bool = False
    parsed_latex: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, code: str, detail: str, **kwargs) -> "Verdict":
        return cls(
            code=code,
            headline=feedback.headline(code),
            detail=detail,
            correct=feedback.is_correct(code),
            partial=feedback.is_partial(code),
            **kwargs,
        )


def grade(check: Check, reference, raw: str) -> Verdict:
    """判定一次作答。這是跑在子行程裡的進入點。"""
    try:
        parsed = parse_answer(raw, check)
    except ParseError as exc:
        return Verdict.of("parse_error", exc.message)

    best: Verdict | None = None
    for candidate in parsed.candidates:
        verdict = _judge(check, reference, candidate, parsed)
        if verdict.correct:                       # 隱式解可能有多個分支，一支對就算對
            return verdict
        if best is None or _rank(verdict) > _rank(best):
            best = verdict
    return best


def _rank(verdict: Verdict) -> int:
    """挑「最接近正確」的那個分支來回報，免得學生看到最沒幫助的一則訊息。"""
    if verdict.correct:
        return 3
    if verdict.partial:
        return 2
    if verdict.code == "wrong":
        return 1
    return 0


def _judge(check: Check, reference, candidate, parsed: ParsedAnswer) -> Verdict:
    common = {"parsed_latex": parsed.latex, "warnings": list(parsed.warnings)}
    consts = constants_of(candidate, check.var)
    residual = check.residual_of(candidate)
    satisfies = is_zero(residual, [check.var] + consts)

    # --- 初值問題：解唯一，常數必須已被定值 -------------------------------
    if check.is_ivp:
        if consts:
            return Verdict.of(
                "unexpected_constants",
                feedback.unexpected_constants([str(c) for c in consts]),
                **common,
            )
        if not satisfies:
            return Verdict.of("wrong", _wrong_detail(check, reference, candidate, consts),
                              **common)
        if not is_zero(check.ic_residual_of(candidate), [check.var]):
            return Verdict.of("initial_condition", feedback.initial_condition(), **common)
        return Verdict.of("correct", feedback.CORRECT_IVP, **common)

    # --- 通解 -------------------------------------------------------------
    if not satisfies:
        return Verdict.of("wrong", _wrong_detail(check, reference, candidate, consts),
                          **common)

    needed = check.n_constants
    if len(consts) < needed:
        return Verdict.of(
            "partial_missing_constants",
            feedback.missing_constants(len(consts), needed),
            **common,
        )
    if len(consts) > needed:
        return Verdict.of(
            "too_many_constants",
            feedback.too_many_constants(len(consts), needed),
            **common,
        )
    if not independent_constants(candidate, consts, check):
        return Verdict.of("dependent_constants", feedback.dependent_constants(needed),
                          **common)

    detail = feedback.CORRECT_GENERAL
    if _looks_reparametrised(reference, candidate, check):
        detail += feedback.CORRECT_REPARAMETRISED
    return Verdict.of("correct", detail, **common)


# --- 答錯時的提示（不爆雷，只說下一步該檢查什麼）---------------------------

def _wrong_detail(check: Check, reference, candidate, consts) -> str:
    detail = feedback.WRONG_BASE

    if not consts:                       # 沒有自由常數才有辦法和標準答案直接比
        try:
            if is_zero(_add(candidate, reference), [check.var]):
                return detail + feedback.HINT_SIGN
            difference = _sub(candidate, reference)
            if not _has_var(difference, check.var) and not is_zero(difference, [check.var]):
                return detail + feedback.HINT_CONSTANT_OFF
        except (TypeError, ValueError, sp.SympifyError):
            pass

    hint = _term_hint(check, candidate, consts)
    return detail + (hint or feedback.HINT_GENERIC)


def _term_hint(check: Check, candidate, consts) -> str | None:
    """逐項診斷：把答案拆成加法項，逐項代回原方程。

    只有在方程是**線性且齊次**時這件事才成立（此時解的線性組合仍是解，
    因此「每一項各自都要是解」是對的）。可分離變數這種非線性題型不適用，
    一階線性非齊次也不適用（特解那一項單獨代回去不會是 0）。
    """
    if not check.linear or not consts:
        return None
    zero = sp.zeros(check.dim, 1) if check.kind == "system" else sp.Integer(0)
    if not is_zero(check.residual_of(zero), [check.var]):     # g ≠ 0 → 非齊次
        return None

    terms = _additive_terms(candidate, consts)
    if len(terms) < 2:
        return None
    good = sum(1 for term in terms
               if is_zero(check.residual_of(term), [check.var] + consts))
    if good == 0:
        return feedback.HINT_TERMS_NONE
    if good < len(terms):
        return feedback.HINT_TERMS_PARTIAL.format(good=good, total=len(terms))
    return None


def _additive_terms(candidate, consts) -> list:
    """依「每個任意常數各自帶著的那一項」拆解，而不是盲目拆 Add。"""
    terms = []
    for c in consts:
        part = sp.diff(candidate, c) * c
        if not is_zero(part, list(consts)):
            terms.append(sp.expand(part) if not isinstance(part, sp.MatrixBase)
                         else part.expand())
    return terms


def _looks_reparametrised(reference, candidate, check: Check) -> bool:
    """只是用來決定要不要多加一句「寫法不同但一樣正確」，判定結果不受影響。"""
    try:
        return not is_zero(_sub(candidate, reference), [check.var])
    except (TypeError, ValueError, sp.SympifyError):
        return False


def _sub(a, b):
    if isinstance(a, sp.MatrixBase) or isinstance(b, sp.MatrixBase):
        return sp.Matrix(a) - sp.Matrix(b)
    return a - b


def _add(a, b):
    if isinstance(a, sp.MatrixBase) or isinstance(b, sp.MatrixBase):
        return sp.Matrix(a) + sp.Matrix(b)
    return a + b


def _has_var(expr, var) -> bool:
    if isinstance(expr, sp.MatrixBase):
        return any(var in e.free_symbols for e in expr)
    return var in expr.free_symbols
