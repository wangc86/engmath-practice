#!/usr/bin/env python3
"""量測判定管線各條路徑的使用比例（PLAN.md §5.3）。

**這支腳本回答的問題**：有多少比例的判定會落到數值抽樣？其中有多少最後變成
「無法確認」（`unverified`）？後者就是學生會被卡住的比例，必須接近 0。

用法：

    python scripts/grader_sampling_report.py            # 每個組合 10 個 seed
    python scripts/grader_sampling_report.py 30         # 每個組合 30 個 seed

它直接呼叫 `grader.core.grade`（不經子行程），所以 `equivalence` 的計數器讀得到。
語料是對每一題自動造出來的六種作答，涵蓋「對、換寫法也對、錯」三類：

    reference     標準答案原樣
    reparam       C_1 → C_1+C_2、C_2 → C_1-C_2（重新參數化，仍然正確）
    hyperbolic    把指數改寫成 sinh/cosh（仍然正確，但寫法完全不同族）
    plus_one      整體加 1（多數題型會變錯）
    doubled       整體乘 2（通解仍正確，初值問題會錯）
    shifted       自變數平移一格（幾乎必錯）

改動 `equivalence.py` 之後請重跑，把「unverified」那一列貼進 PLAN.md。
"""

from __future__ import annotations

import collections
import pathlib
import random
import sys
import time

import sympy as sp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import app.generator  # noqa: F401,E402  觸發題型註冊
from app.config import MAX_ANSWER_LENGTH  # noqa: E402
from app.generator import base  # noqa: E402
from app.grader import core, equivalence  # noqa: E402


def _as_text(expr) -> str:
    if isinstance(expr, sp.MatrixBase):
        return ", ".join(sp.sstr(c) for c in expr)
    return sp.sstr(expr)


def _free_symbols(expr) -> set:
    if isinstance(expr, sp.MatrixBase):
        out: set = set()
        for c in expr:
            out |= c.free_symbols
        return out
    return set(expr.free_symbols)


def _variants(problem) -> list[tuple[str, str]]:
    answer = problem.answer_expr
    var = problem.check.var
    out = [("reference", _as_text(answer))]

    consts = sorted(_free_symbols(answer) - {var}, key=str)
    if len(consts) == 2:
        c1, c2 = consts
        out.append(("reparam", _as_text(sp.expand(
            answer.subs({c1: c1 + c2, c2: c1 - c2}, simultaneous=True)))))

    # 同一個解、完全不同的函數族（e^u → cosh u + sinh u）。
    # 這是最能逼出「化簡管線夠不夠強」的一種寫法：數學上完全相等，
    # 但 `expand` 化不掉，一定要走到符號管線才證得出來。
    try:
        hyperbolic = answer.replace(sp.exp, lambda u: sp.cosh(u) + sp.sinh(u))
        if hyperbolic.has(sp.sinh, sp.cosh):
            out.append(("hyperbolic", _as_text(hyperbolic)))
    except Exception:                                    # noqa: BLE001 - 造不出來就跳過
        pass

    one = sp.ones(answer.rows, 1) if isinstance(answer, sp.MatrixBase) else sp.Integer(1)
    out.append(("plus_one", _as_text(answer + one)))
    out.append(("doubled", _as_text(sp.expand(2 * answer))))
    out.append(("shifted", _as_text(sp.expand(answer.subs(var, var + 1)))))
    return out


def main(n_seeds: int) -> None:
    equivalence.reset_stats()
    verdicts: collections.Counter = collections.Counter()
    skipped = 0
    graded = 0
    started = time.monotonic()

    for template_id, tpl in base.REGISTRY.items():
        for difficulty in tpl.difficulties:
            rng = random.Random(f"{template_id}-{difficulty}")
            for _ in range(n_seeds):
                seed = rng.randrange(1, 2**31 - 1)
                problem = base.generate(template_id, difficulty, seed=seed)
                for label, text in _variants(problem):
                    if len(text) > MAX_ANSWER_LENGTH:
                        skipped += 1
                        continue
                    verdict = core.grade(problem.check, problem.answer_expr, text)
                    verdicts[(label, verdict.code)] += 1
                    graded += 1

    elapsed = time.monotonic() - started
    stats = equivalence.stats()
    calls = stats.get("calls", 0)
    sampled = stats.get("sampled", 0)
    pipeline = stats.get("symbolic_pipeline", 0)
    unknown = stats.get("unknown", 0)

    print(f"作答語料 {graded} 筆（略過過長的 {skipped} 筆），耗時 {elapsed:.1f} 秒")
    print()
    print("判定結果")
    print("-" * 60)
    for (label, code), n in sorted(verdicts.items()):
        print(f"  {label:12s} {code:28s} {n}")
    print()
    print("zero_status 的路徑分佈")
    print("-" * 60)
    for key in sorted(stats):
        print(f"  {key:34s} {stats[key]}")
    print()
    print("關鍵比例")
    print("-" * 60)
    print(f"  zero_status 呼叫次數                {calls}")
    print(f"  落到數值抽樣                        {sampled}"
          f"  ({100 * sampled / max(calls, 1):.1f}%)")
    print(f"  抽樣反證不了、需要符號證明          {pipeline}"
          f"  ({100 * pipeline / max(calls, 1):.2f}%)")
    print(f"  最後仍無法判定（unknown）           {unknown}"
          f"  ({100 * unknown / max(calls, 1):.2f}%)")
    print(f"  學生看到 unverified 的作答數        "
          f"{sum(n for (_, code), n in verdicts.items() if code == 'unverified')}"
          f" / {graded}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
