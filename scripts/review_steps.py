#!/usr/bin/env python3
"""2c 人工審題的**機器初篩**（PLAN 工作項 2c、`VERIFY-CHECKLIST.md` §A6）。

    python scripts/review_steps.py                 # 產出 2c-PRESCREEN.md
    python scripts/review_steps.py -n 8 -o /tmp/x.md

---

## 這支腳本**不做**什麼

⛔ **它不判斷任何一題出得好不好，也絕對不改任何敘述。** 2c 的判斷是老師的
——§A6 對「失敗長什麼樣」的描述是：「不會有錯誤訊息。你會在第 30 題突然
覺得『這題怪怪的』，而那個感覺就是這一輪的產出。」**那個感覺沒有辦法自動化。**

它做的是把 240 題（16 題型 × 3 難度 × n）先過一遍，把**機器讀得出來的
不一致**挑出來排序，讓老師從最可疑的那幾格開始看，而不是從第 1 題開始看。
換句話說：**它省的是老師的時間，不是老師的判斷。**

## 五項判準，以及每一項為什麼是「線索」而不是「結論」

| 判準 | 訊號 | ⚠️ 為什麼不能當結論 |
|---|---|---|
| C1 步驟顆粒度 | 每題的步驟數 | 「六步 vs 三步」可能是題型本來就不一樣難，不是切法不一致 |
| C2 `note` 在說「為什麼」還是「做了什麼」 | 與 `title` 的詞重疊、開頭是不是動作動詞、有沒有因果詞 | 一句好的 `note` 也可能不含任何因果詞；反過來，含 "because" 也可能只是廢話 |
| C3 難度階梯 | 敘述長度／步驟數／答案的 SymPy 運算元個數 | **長度不是難度。** 這一欄只回答「難度 2 有沒有在任何一個可量的向度上超過難度 1」 |
| C4 英文用語 | 敘述開頭的動詞、幾組競爭說法的分佈 | 不同題型用不同動詞可能是對的（§7 #11 要老師拍板的正是這個） |
| C5 附錄 C 的 $y$ vs $y(x)$ | 步驟裡有沒有「單獨站著」的 `y` | ⛔ **v0.37 換過判準**：舊的把 `y'` 與 `L\{y'\}` 也算成違反，而那兩個是附錄 C.1／C.3 明訂的寫法——`ode.laplace.ivp` 整格是誤報 |

⚠️ **C2 是五項裡最粗的一項**，而它也是老師這一輪特別點名的那一項。
它用的是關鍵詞與詞重疊，**沒有任何語意理解**——所以它的輸出是
「這幾句最像在重述步驟」，不是「這幾句是錯的」。
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import sympy as sp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.generator import generate, list_templates  # noqa: E402

#: `note` 若以這些字開頭，多半是在重述「做了什麼」而不是回答「為什麼」。
ACTION_VERBS = {
    "substitute", "integrate", "differentiate", "divide", "multiply", "apply",
    "take", "set", "solve", "compute", "write", "use", "expand", "factor",
    "rearrange", "collect", "plug", "insert", "evaluate", "separate", "move",
    "add", "subtract", "square", "cancel", "simplify", "replace", "let",
}

#: 因果／理由的訊號詞。⚠️ **有它不代表好，沒有它不代表壞**——見檔頭那張表。
REASON_MARKERS = (
    "because", "since", "so that", "which is why", "the reason", "reason is",
    " so ", " thus", "hence", "therefore", "means", "vanish", "why",
    "otherwise", "ensures", "guarantees", "must", "cannot", "would", "allows",
    "in order to", "this is", "that is why", "avoids", "keeps", "valid",
    "requires", "only if", "if and only if", "note that", "here", "we need",
    "needed", "necessary", "always", "never", "fails",
)

#: C4 的幾組競爭說法。§7 #11 明文說這件事要老師對著課本拍板。
RIVAL_PHRASES = (
    ("general solution", "complete solution"),
    ("initial condition", "initial value"),
    ("particular solution", "particular integral"),
    ("characteristic equation", "auxiliary equation"),
)

WORD = re.compile(r"[a-z]+")


def tokens(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def op_count(expr):
    """答案的 SymPy 運算元個數；量不到就回 `None`，**不要回 0**。

    ⚠️ 第一版寫的是 `try: expr.count_ops() except: return 0`，而
    `MutableDenseMatrix` **沒有** `count_ops` 這個方法（`ImmutableDenseMatrix`
    有）——於是四個系統題型的這一欄安靜地印出 `0→0→0`，看起來像
    「答案完全沒有變複雜」，其實是「根本沒量到」。那正是規則 4 說的無聲降級。
    改用模組層的 `sp.count_ops()`，它對 Matrix 也認得。
    """
    if expr is None:
        return None          # `classification` 的答案是一句話，本來就沒有算式
    return int(sp.count_ops(expr))


def collect(count: int):
    rows = []
    for tpl in list_templates():
        for difficulty in tpl.difficulties:
            for i in range(count):
                p = generate(tpl.template_id, difficulty, seed=1000 + i)
                rows.append(p)
    return rows


def note_flags(step) -> list[str]:
    """一個步驟的 `note` 有哪些「像在重述」的訊號。"""
    flags = []
    note = (step.note or "").strip()
    if not note:
        return ["empty"]
    first = WORD.findall(note.lower())[:1]
    if first and first[0] in ACTION_VERBS:
        flags.append("starts-with-action-verb")
    low = note.lower()
    if not any(m in low for m in REASON_MARKERS):
        flags.append("no-reason-marker")
    t_title, t_note = tokens(step.title), tokens(note)
    if t_title and t_note:
        overlap = len(t_title & t_note) / len(t_title)
        if overlap >= 0.6:
            flags.append(f"restates-title({overlap:.0%})")
    if len(note.split()) <= 4:
        flags.append("very-short")
    return flags


def per_ops(by_cell, t):
    """三個難度的平均運算元；那一格全部量不到就回 `None`（印成 `—`）。"""
    out = []
    for d in (1, 2, 3):
        vals = [op_count(p.answer_expr) for p in by_cell.get((t, d), [])]
        vals = [v for v in vals if v is not None]
        out.append(round(statistics.mean(vals), 1) if vals else None)
    return out


def build(count: int) -> str:
    rows = collect(count)
    by_tpl = defaultdict(list)
    by_cell = defaultdict(list)
    for p in rows:
        by_tpl[p.template_id].append(p)
        by_cell[(p.template_id, p.difficulty)].append(p)

    out: list[str] = []
    w = out.append
    #: 每個題型收到的線索，最後彙整成開頭那份「先看這幾個」。
    #: ⚠️ **刻意不加權、不算總分**：一個分數會讓人以為它排出了「品質高低」，
    #: 而這五項判準沒有一項有資格說那句話。這裡只是把線索的**條數**排一排，
    #: 而每一條都寫出來，讓老師自己決定哪一條重要。
    clues: defaultdict[str, list[str]] = defaultdict(list)
    w("# 2c 人工審題的機器初篩")
    w("")
    w(f"**自動產生**：`python scripts/review_steps.py -n {count}`。"
      "⛔ **這份不是判斷，是排序**——2c 的判斷是老師的（`VERIFY-CHECKLIST.md` §A6）。")
    w("")
    w(f"樣本：{len(list_templates())} 個題型 × 3 個難度 × {count} 題 = **{len(rows)} 題**。")
    w("題目本身請開 `preview.html`（`python scripts/preview.py -n 5`）對照著看。")
    w("")
    w("> ⚠️ **每一項都是線索不是結論**，每一節的開頭都寫著它為什麼可能誤報。")
    w("> 五項判準的完整說明在 `scripts/review_steps.py` 的檔頭。")
    w("")

    # ---------------- C1 步驟顆粒度 ----------------
    w("## C1 步驟顆粒度：每題幾步")
    w("")
    w("§7 #22 想訂的規則是「一步 = 課本上會單獨寫一行的一個動作」，"
      "而目前各題型是各憑感覺切的。")
    w("⚠️ **步驟數不一樣不一定是錯的**——有些題型本來就比較長。"
      "要看的是**同一個題型在三個難度之間**跳不跳，以及有沒有哪個題型明顯離群。")
    w("")
    counts = {t: statistics.mean(len(p.steps) for p in ps) for t, ps in by_tpl.items()}
    med = statistics.median(counts.values())
    w("| 題型 | d1 | d2 | d3 | 平均 | 離中位數 |")
    w("|---|---|---|---|---|---|")
    for t in sorted(by_tpl):
        per = [statistics.mean(len(p.steps) for p in by_cell[(t, d)]) if (t, d) in by_cell else None
               for d in (1, 2, 3)]
        cells = ["—" if v is None else f"{v:.1f}" for v in per]
        gap = counts[t] - med
        mark = " ⚠️" if abs(gap) >= 2 else ""
        if abs(gap) >= 2:
            clues[t].append(f"C1 步驟數離中位數 {gap:+.1f} 步")
        w(f"| `{t}` | {cells[0]} | {cells[1]} | {cells[2]} | {counts[t]:.1f} | {gap:+.1f}{mark} |")
    w("")
    w(f"中位數 **{med:.1f}** 步。⚠️ 標了 ⚠️ 的是離中位數 2 步以上的——**先看那幾個**。")
    w("")
    jumpy = [t for t in sorted(by_tpl)
             if len({round(statistics.mean(len(p.steps) for p in by_cell[(t, d)]))
                     for d in (1, 2, 3) if (t, d) in by_cell}) > 1
             and max(statistics.mean(len(p.steps) for p in by_cell[(t, d)])
                     for d in (1, 2, 3) if (t, d) in by_cell)
             - min(statistics.mean(len(p.steps) for p in by_cell[(t, d)])
                   for d in (1, 2, 3) if (t, d) in by_cell) >= 2]
    if jumpy:
        w("**同一題型在三個難度之間跳 2 步以上**（切法可能不一致，也可能是難度真的不同）：")
        for t in jumpy:
            w(f"- `{t}`")
            clues[t].append("C1 三個難度之間的步驟數跳 2 步以上")
        w("")

    # ---------------- C2 note ----------------
    w("## C2 `note` 是在回答「為什麼」還是在重述「做了什麼」")
    w("")
    w("⚠️ **這一節是五項裡最粗的。** 它只看四件表面的事：`note` 是不是空的、"
      "是不是以動作動詞開頭、有沒有任何因果詞、以及與 `title` 的詞重疊。"
      "**一句好的 `note` 完全可能三項都中**，所以這裡列的是「先看這幾句」。")
    w("")
    tally = defaultdict(Counter)
    examples = defaultdict(list)
    seen = defaultdict(set)
    for p in rows:
        for step in p.steps:
            fl = note_flags(step)
            for f in fl:
                tally[p.template_id][f.split("(")[0]] += 1
            # ⚠️ 同一個步驟會在多個抽樣的題目裡重複出現（`note` 是固定的文字），
            # 所以以 note 原文去重——不去重的話同一句會被列三遍，
            # 而那會讓「哪幾句最可疑」這件事完全讀不出來。
            if len(fl) >= 2 and step.note not in seen[p.template_id]:
                seen[p.template_id].add(step.note)
                examples[p.template_id].append((p.difficulty, step.title, step.note, fl))
    w("| 題型 | 步驟總數 | 空的 | 動作動詞開頭 | 沒有因果詞 | 重述 title | 很短 |")
    w("|---|---|---|---|---|---|---|")
    for t in sorted(by_tpl):
        total = sum(len(p.steps) for p in by_tpl[t])
        c = tally[t]
        w(f"| `{t}` | {total} | {c['empty']} | {c['starts-with-action-verb']} | "
          f"{c['no-reason-marker']} | {c['restates-title']} | {c['very-short']} |")
        if total and c["empty"] / total >= 0.3:
            clues[t].append(f"C2 有 {c['empty']}/{total} 個步驟根本沒有 note")
        if c["starts-with-action-verb"] or c["restates-title"]:
            clues[t].append("C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）")
    w("")
    w("### 命中兩項以上的 `note`（每個題型最多列三句，訊號多的排前面）")
    w("")
    for t in sorted(examples):
        if not examples[t]:
            continue
        w(f"**`{t}`**")
        w("")
        for d, title, note, fl in sorted(examples[t], key=lambda e: -len(e[3]))[:3]:
            w(f"- d{d}　*{title}*")
            w(f"  - note：{note or '（空）'}")
            w(f"  - 訊號：{', '.join(fl)}")
        w("")

    # ---------------- C3 難度階梯 ----------------
    w("## C3 難度階梯：難度 2 有沒有在任何一個可量的向度上超過難度 1")
    w("")
    w("⛔ **長度不是難度。** 這一節唯一能回答的是「有沒有任何一個可量的向度"
      "隨難度上升」；答案是「沒有」時**也可能是對的**（例如難度軸是"
      "共振重數，那件事量不出來——`ode.second_order.undetermined` 曾經是這樣，"
      "而它在 v0.35 被刪掉了）。")
    w("")
    w("| 題型 | 敘述長度 d1→d2→d3 | 步驟數 | 答案的運算元 | 有沒有單調上升 |")
    w("|---|---|---|---|---|")
    for t in sorted(by_tpl):
        def per(fn, t=t):
            return [round(statistics.mean(fn(p) for p in by_cell[(t, d)]), 1)
                    if (t, d) in by_cell else None for d in (1, 2, 3)]
        stmt = per(lambda p: len(p.statement_latex))
        steps = per(lambda p: len(p.steps))
        ops = per_ops(by_cell, t)
        def mono(v):
            v = [x for x in v if x is not None]
            if len(v) < 2:
                return False     # 量不到就不能說它上升（也不能說它沒上升）
            return all(b >= a for a, b in zip(v, v[1:])) and v[-1] > v[0]
        rising = [name for name, v in (("敘述", stmt), ("步驟", steps), ("運算元", ops)) if mono(v)]
        mark = "、".join(rising) if rising else "**都沒有** ⚠️"
        if not rising:
            clues[t].append("C3 三個可量的向度都沒有隨難度上升")
        fmt = lambda v: "→".join("—" if x is None else str(x) for x in v)
        w(f"| `{t}` | {fmt(stmt)} | {fmt(steps)} | {fmt(ops)} | {mark} |")
    w("")

    # ---------------- C4 英文用語 ----------------
    w("## C4 英文用語（§7 #11：這件事要對著課本拍板）")
    w("")
    w("⚠️ 不同題型用不同動詞**可能是對的**，這一節只是把分佈攤開。")
    w("")
    openers = Counter()
    for p in rows:
        first = (p.statement or "").strip().split()
        if first:
            openers[first[0]] += 1
    w("**敘述開頭的第一個字**：" + "、".join(f"`{k}` × {v}" for k, v in openers.most_common()))
    w("")
    text = "\n".join(
        [p.statement for p in rows]
        + [s.title for p in rows for s in p.steps]
        + [s.note for p in rows for s in p.steps]
    ).lower()
    w("**幾組競爭說法各出現幾次**（兩邊都 > 0 的那幾組要拍板）：")
    w("")
    for a, b in RIVAL_PHRASES:
        na, nb = text.count(a), text.count(b)
        mark = " ⚠️ **兩種都在用**" if na and nb else ""
        w(f"- `{a}` × {na}　vs　`{b}` × {nb}{mark}")
    w("")

    # ---------------- C5 y vs y(x) ----------------
    w("## C5 附錄 C：未知函數有沒有全程保留自變數（§7 #29）")
    w("")
    w("⛔ **v0.37 換掉了這一節的判準，因為舊的那個誤報過。** 舊版把「`y` 後面接 "
      "`\'` 或 `=`」都算成違反，於是 `y\'`（附錄 C.1 明訂的導數寫法）與 "
      "`L\\{y\'\\}`（附錄 C.3 **逐字**規定的變換寫法）都被標成違反——"
      "**`ode.laplace.ivp` 那一整格是誤報**。")
    w("")
    w("現在的判準與 `test_the_unknown_function_keeps_its_argument_in_every_step` "
      "**是同一個**：一個「單獨站著」的 `y`，而**含 `dy` 的那一步整步豁免**"
      "（附錄 C.1 明文允許分離變數的第一步用微分寫法）。")
    w("")
    bare = re.compile(r"(?<![A-Za-z\\{])y(?![A-Za-z_({\'])")
    named = re.compile(r"y\s*(?:\(|\{\\left\()\s*[xt]")
    w("| 題型 | 步驟出現單獨的 $y$ 的題數 | 答案寫 $y(x)$ 的題數 | 同一題兩者都有 |")
    w("|---|---|---|---|")
    for t in sorted(by_tpl):
        nb = na = both = 0
        for p in by_tpl[t]:
            in_steps = any(bare.search(s.latex or "")
                           for s in p.steps if "dy" not in (s.latex or ""))
            in_ans = bool(named.search(p.answer_latex or ""))
            nb += in_steps
            na += in_ans
            both += in_steps and in_ans
        mark = " ⚠️" if both else ""
        w(f"| `{t}` | {nb} | {na} | {both}{mark} |")
        if both:
            clues[t].append(f"C5 有 {both} 題的步驟出現單獨的 $y$，而答案寫 $y(x)$")
    w("")
    # ---------------- 開頭那份「先看這幾個」 ----------------
    head = ["## 先看這幾個（線索最多的排前面）", ""]
    head.append("⚠️ **排序不是評分。** 這裡排的是「機器讀得出來的線索有幾條」，"
                "不是「哪個題型比較差」——一條線索完全可能是誤報，"
                "每一節的開頭都寫著它為什麼會誤報。")
    head.append("")
    ranked = sorted(clues.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if not ranked:
        head.append("（沒有任何線索。）")
    for t, cs in ranked:
        head.append(f"- **`{t}`**（{len(cs)} 條）")
        for c in cs:
            head.append(f"  - {c}")
    head.append("")
    clean = [t for t in sorted(by_tpl) if t not in clues]
    if clean:
        head.append("**一條線索都沒有的題型**："
                    + "、".join(f"`{t}`" for t in clean)
                    + "。⚠️ 那不代表它們沒問題，只代表這五項判準看不出來。")
        head.append("")
    marker = "## C1 步驟顆粒度：每題幾步"
    out[out.index(marker):out.index(marker)] = head

    w("---")
    w("")
    w("## 這份初篩**沒有**回答的事")
    w("")
    w("- **「這題出得好不好」**——§A6 的三件事裡，「敘述像不像上課的講法」"
      "與「難度階梯合不合理」最後都要人看。")
    w("- **數學對不對**——那是 1394 項自動測試在守的，不在這裡。")
    w("- **`note` 說的理由對不對**——C2 只看它像不像理由，不看它是不是真的。")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", "--count", type=int, default=5,
                    help="每一格幾題（預設 5，與 preview.py 一致）")
    ap.add_argument("-o", "--output", default=str(ROOT / "2c-PRESCREEN.md"))
    args = ap.parse_args()
    text = build(args.count)
    Path(args.output).write_text(text, encoding="utf-8")
    print(f"寫入 {args.output}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
