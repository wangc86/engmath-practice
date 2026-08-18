"""判定結果 → 給學生看的回饋文字（PLAN.md §5.5）。

三個原則：

1. **分層級**，不是只有對／錯。最常見的部分正確是「漏了一個任意常數」，
   那和「代進去根本不成立」是完全不同的學習狀態，必須講清楚。
2. **不爆雷**。答錯時給的是下一步該檢查什麼，不是答案；要看答案得自己按
   "Show solution"（那個動作會另外被記錄下來，見 UsageLog.action）。
3. **全部英文**（D5），且由程式規則產生，不經過 LLM。

文字集中在這裡，是為了讓「介面不得出現中日韓字元」那條測試有單一個看守點。
"""

from __future__ import annotations

# code → (是否正確, 是否部分正確, 標題)
_HEADLINES = {
    "correct": (True, False, "Correct"),
    "partial_missing_constants": (False, True, "Almost — an arbitrary constant is missing"),
    "too_many_constants": (False, True, "Too many arbitrary constants"),
    "dependent_constants": (False, True, "Your two terms are not independent"),
    "unexpected_constants": (False, True, "This is an initial value problem"),
    "initial_condition": (False, True, "The equation is satisfied, but not the initial condition"),
    "wrong": (False, False, "Not correct yet"),
    "unverified": (False, False, "The system could not confirm your answer"),
    "parse_error": (False, False, "Could not read your answer"),
    "timeout": (False, False, "Checking your answer took too long"),
    "busy": (False, False, "The checker is busy right now"),
    "internal_error": (False, False, "Something went wrong while checking"),
}


def headline(code: str) -> str:
    return _HEADLINES.get(code, _HEADLINES["internal_error"])[2]


def is_correct(code: str) -> bool:
    return _HEADLINES.get(code, (False, False, ""))[0]


def is_partial(code: str) -> bool:
    return _HEADLINES.get(code, (False, False, ""))[1]


# 「無法確認」既不是對也不是錯，UI 用中性的樣式（見 _feedback.html、style.css）
_UNVERIFIED_CODES = frozenset({"unverified"})


def is_unverified(code: str) -> bool:
    return code in _UNVERIFIED_CODES


def missing_constants(found: int, needed: int) -> str:
    return (
        f"Your expression does satisfy the differential equation, so the shape "
        f"of your solution is right. But the general solution of this problem "
        f"needs {needed} arbitrary constants and yours has {found}. What you "
        f"have written is one particular solution, not the whole family."
    )


def too_many_constants(found: int, needed: int) -> str:
    return (
        f"Your expression satisfies the differential equation, but it contains "
        f"{found} arbitrary constants where {needed} are expected. Some of them "
        f"can be absorbed into the others."
    )


def dependent_constants(needed: int) -> str:
    return (
        f"Your expression satisfies the differential equation and has {needed} "
        f"constants, but the two terms are multiples of one another, so they do "
        f"not form a basis of solutions. Check that the two exponents (or the "
        f"two eigenvalues) really are different."
    )


def unexpected_constants(names: list[str]) -> str:
    shown = ", ".join(names[:4])
    return (
        f"This problem gives an initial condition, so the answer must be one "
        f"specific function with no arbitrary constants left. Yours still "
        f"contains {shown}. Substitute the initial condition to determine them."
    )


def initial_condition() -> str:
    return (
        "Your expression solves the differential equation, but it does not "
        "match the initial condition. Substitute the initial value and solve "
        "for the constants again."
    )


WRONG_BASE = (
    "Substituting your expression back into the equation does not give zero, "
    "so it is not a solution."
)

HINT_SIGN = " Check your signs — the answer is exactly the negative of a solution."

HINT_CONSTANT_OFF = (
    " Your expression differs from a solution by a constant. Look at the "
    "constant of integration or at the particular solution."
)

HINT_TERMS_PARTIAL = (
    " Part of your answer is fine: {good} of your {total} terms do satisfy the "
    "equation on their own, the other one does not. Re-check that term."
)

HINT_TERMS_NONE = (
    " None of the individual terms satisfies the equation on its own, so it is "
    "worth going back to the characteristic equation (or the eigenvalues) "
    "rather than adjusting coefficients."
)

HINT_GENERIC = (
    " Differentiate your expression and substitute it into the left-hand side "
    "step by step; comparing coefficients usually shows where it breaks."
)

TIMEOUT_DETAIL = (
    "The check was stopped after the time limit. This usually means the "
    "expression is far more complicated than expected. Please simplify it and "
    "submit again."
)

UNVERIFIED_DETAIL = (
    "Your expression behaves like a solution everywhere the system tested it, "
    "but the system could not prove it symbolically, so it will not claim that "
    "it is right. Please compare your answer with the worked solution — it may "
    "well be correct. Writing it in a simpler or more standard form usually "
    "lets the check go through."
)

BUSY_DETAIL = (
    "Too many answers are being checked at the same moment, so yours had to "
    "wait. Nothing is wrong with what you wrote — please submit it again in a "
    "few seconds."
)

INTERNAL_DETAIL = (
    "Your answer could not be checked this time. Please try again, and let "
    "your instructor know if it keeps happening."
)

CORRECT_GENERAL = (
    "Your expression satisfies the differential equation, has the right number "
    "of arbitrary constants, and those constants give independent solutions."
)

CORRECT_IVP = (
    "Your expression satisfies both the differential equation and the initial "
    "condition."
)

CORRECT_REPARAMETRISED = (
    " (It is written differently from the reference answer, but it describes "
    "the same family of solutions — that is equally correct.)"
)
