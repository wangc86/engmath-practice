#!/usr/bin/env python3
"""批次產生題目樣本，輸出成可直接看的 HTML 或可編譯的 LaTeX。

用途：老師要一次審查大量題目的品質（難度分級對不對、敘述像不像上課的講法、
有沒有醜到不該出現的題目）時，在瀏覽器裡點五十次太慢。

用法
----
    # 產生 HTML，用專案內建的 KaTeX 渲染（跟學生看到的完全同一套）
    python scripts/preview.py
    open preview.html

    # 產生 LaTeX，再用 XeLaTeX 編譯成 PDF
    python scripts/preview.py --format tex
    xelatex preview.tex

    # 常用選項
    python scripts/preview.py -n 10                    # 每個組合 10 題（預設 5）
    python scripts/preview.py --no-steps               # 只要題目與答案
    python scripts/preview.py -t separable -d 3        # 只看某題型／某難度
    python scripts/preview.py -o /tmp/看看.html        # 換輸出路徑

`-t` 用的是題型代號的片段，例如 separable / linear / homogeneous / system。
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.generator import DIFFICULTY_LABELS, generate, list_templates  # noqa: E402


# --- 蒐集題目 -------------------------------------------------------------

def collect(count: int, only_template: str | None, only_difficulty: int | None):
    """回傳 [(模板, 難度, [題目, ...]), ...]。"""
    blocks = []
    for tpl in list_templates():
        if only_template and only_template.lower() not in tpl.template_id.lower():
            continue
        for difficulty in tpl.difficulties:
            if only_difficulty and difficulty != only_difficulty:
                continue
            problems = [generate(tpl.template_id, difficulty) for _ in range(count)]
            blocks.append((tpl, difficulty, problems))
    if not blocks:
        raise SystemExit("No topic matched. Check the values of -t / -d.")
    return blocks


# --- HTML 輸出 ------------------------------------------------------------

HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Problem Sample Review — {stamp}</title>
<link rel="stylesheet" href="{katex}/katex.min.css">
<script defer src="{katex}/katex.min.js"></script>
<script defer src="{katex}/contrib/auto-render.min.js"></script>
<style>
  body {{ max-width: 900px; margin: 2rem auto; padding: 0 1.5rem; line-height: 1.7;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         color: #1f2933; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2.5rem; padding-bottom: .3rem;
        border-bottom: 2px solid #2b6cb0; }}
  .note {{ color: #6b7280; font-size: .88rem; margin: .2rem 0 1rem; }}
  .prob {{ border-left: 3px solid #e2e6ea; padding: .2rem 0 .2rem 1rem;
           margin-bottom: 1.4rem; }}
  .label {{ display: inline-block; width: 2.4em; color: #6b7280; font-size: .85rem; }}
  .row {{ display: flex; align-items: baseline; gap: .3rem; }}
  .row > div {{ overflow-x: auto; }}
  details {{ margin-top: .4rem; }}
  summary {{ cursor: pointer; color: #2b6cb0; font-size: .85rem; }}
  ol {{ font-size: .92rem; }}
  li {{ margin-bottom: .5rem; }}
  .steptitle {{ font-weight: 600; }}
  .stepnote {{ color: #6b7280; font-size: .85rem; }}
  .stmt {{ font-weight: 600; margin: 0 0 .3rem; }}
  .seed {{ color: #b0b7bf; font-size: .75rem; }}
</style>
</head>
<body>
<h1>Problem Sample Review</h1>
<p class="note">Generated {stamp} · {count} problems per combination ·
Rendered with the project's own copy of KaTeX, exactly as students see it.</p>
"""


def to_html(blocks, count: int, out_path: Path, with_steps: bool) -> str:
    # 用相對路徑指到專案內已自架的 KaTeX，離線也能開
    katex = Path("app/static/vendor/katex")
    try:
        rel = Path("..") / katex if out_path.resolve().parent != ROOT else katex
        if out_path.resolve().parent == ROOT:
            rel = katex
        else:
            rel = (ROOT / katex).resolve().as_uri()
    except Exception:  # pragma: no cover
        rel = (ROOT / katex).resolve().as_uri()

    parts = [HTML_HEAD.format(katex=rel, count=count,
                              stamp=datetime.now().strftime("%Y-%m-%d %H:%M"))]

    for tpl, difficulty, problems in blocks:
        parts.append(
            f"<h2>{html.escape(tpl.name)}"
            f" &mdash; Difficulty {difficulty} ({DIFFICULTY_LABELS[difficulty]})</h2>"
        )
        parts.append(
            f'<p class="note">{html.escape(tpl.chapter)} &middot; '
            f'{html.escape(tpl.difficulty_notes.get(difficulty, ""))} &middot; '
            f'<code>{html.escape(tpl.template_id)}</code></p>'
        )
        for p in problems:
            parts.append('<div class="prob">')
            parts.append(f'<p class="stmt">{html.escape(p.statement)}</p>')
            parts.append(
                f'<div class="row"><span class="label">Q</span>'
                f'<div>$${p.statement_latex}$$</div></div>'
            )
            parts.append(
                f'<div class="row"><span class="label">A</span>'
                f'<div>$${p.answer_latex}$$</div></div>'
            )
            if with_steps:
                parts.append("<details><summary>Step-by-step solution</summary><ol>")
                for s in p.steps:
                    parts.append(
                        f'<li><span class="steptitle">{html.escape(s.title)}</span>'
                    )
                    if s.latex:
                        parts.append(f"<div>$${s.latex}$$</div>")
                    if s.note:
                        parts.append(f'<div class="stepnote">{html.escape(s.note)}</div>')
                    parts.append("</li>")
                parts.append("</ol></details>")
            parts.append(f'<div class="seed">seed {p.seed}</div>')
            parts.append("</div>")

    parts.append("""
<script>
window.addEventListener('DOMContentLoaded', function () {
  renderMathInElement(document.body, {
    delimiters: [{left:'$$', right:'$$', display:true},
                 {left:'$',  right:'$',  display:false}],
    throwOnError: false
  });
});
</script>
</body></html>""")
    return "\n".join(parts)


# --- LaTeX 輸出 -----------------------------------------------------------

TEX_SPECIALS = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
    "&": r"\&", "#": r"\#", "^": r"\textasciicircum{}", "_": r"\_",
    "%": r"\%", "~": r"\textasciitilde{}",
}

# 中文敘述裡用了 Unicode 下標（C₁、C₂、λᵢ）。多數中文字型沒有這些字符，
# 直接輸出會變成缺字空白，所以改用 LaTeX 的數學下標。
TEX_SPECIALS.update({c: f"$_{i}$" for i, c in enumerate("₀₁₂₃₄₅₆₇₈₉")})
TEX_SPECIALS.update({c: f"$^{i}$" for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")})
TEX_SPECIALS.update({"ᵢ": "$_i$", "ⱼ": "$_j$", "ₙ": "$_n$"})

_MATH_SPAN = re.compile(r"\$[^$]*\$")


def tex_escape(text: str) -> str:
    """把純文字裡的 ^ { } 等符號跳脫，避免編譯失敗。"""
    return "".join(TEX_SPECIALS.get(c, c) for c in text)


def tex_text(text: str) -> str:
    """敘述文字中夾雜 $…$ 數學片段時，只跳脫數學以外的部分。

    題目敘述與步驟說明裡會出現 $C_1$、$e^{rx}$ 這類片段（讓 KaTeX 在網頁上
    渲染）。整段丟進 tex_escape 會把反斜線與大括號全部跳脫，數學就變成亂碼；
    這裡把 $…$ 原樣保留，其餘才跳脫。
    """
    out, last = [], 0
    for m in _MATH_SPAN.finditer(text):
        out.append(tex_escape(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(tex_escape(text[last:]))
    return "".join(out)


TEX_HEAD = r"""%% 用 XeLaTeX 編譯（不是 pdflatex）： xelatex preview.tex
\documentclass[11pt]{article}
\usepackage[margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{fontspec}

%% 中文字型。預設是 macOS 內建的 PingFang TC；
%% 要換字型不必改這裡，用 --cjk-font 選項即可，例如
%%   python scripts/preview.py -f tex --cjk-font "Noto Sans CJK TC"
%% 有 xeCJK（MacTeX、完整 TeX Live 都有）就用它，中文斷行才正確；
%% 沒有的話退回純 fontspec，一樣編得過，只是中英混排的斷行較差。
%% 注意 xeCJK.sty 可能單獨存在但缺少相依的 ctexhook.sty，所以兩個都要檢查。
\newif\ifUseXeCJK
\IfFileExists{xeCJK.sty}{\IfFileExists{ctexhook.sty}{\UseXeCJKtrue}{}}{}
\ifUseXeCJK
  \usepackage{xeCJK}
  \setCJKmainfont{%(font)s}
\else
  \setmainfont{%(font)s}
\fi

\usepackage{enumitem}
\setlength{\parindent}{0pt}
\setlength{\parskip}{.4em}
\title{Problem Sample Review}
\date{%(stamp)s}
\begin{document}
\maketitle
\noindent %(count)d problems per combination. Generated by \texttt{scripts/preview.py}.
"""


def to_tex(blocks, count: int, with_steps: bool, cjk_font: str) -> str:
    parts = [TEX_HEAD % {"count": count, "font": cjk_font,
                         "stamp": datetime.now().strftime("%Y-%m-%d %H:%M")}]

    for tpl, difficulty, problems in blocks:
        parts.append(
            r"\section*{%s\quad Difficulty %d --- %s}"
            % (tex_escape(tpl.name), difficulty, DIFFICULTY_LABELS[difficulty])
        )
        parts.append(
            r"\noindent\textit{\small %s | %s | \texttt{%s}}\par"
            % (tex_escape(tpl.chapter),
               tex_text(tpl.difficulty_notes.get(difficulty, "")),
               tex_escape(tpl.template_id))
        )
        for i, p in enumerate(problems, 1):
            parts.append(r"\textbf{%d.} %s" % (i, tex_text(p.statement)))
            parts.append(r"\[ %s \]" % p.statement_latex)
            parts.append(r"Answer:")
            parts.append(r"\[ %s \]" % p.answer_latex)
            if with_steps:
                parts.append(r"\begin{enumerate}[leftmargin=2em,itemsep=.2em]")
                for s in p.steps:
                    parts.append(r"\item \textbf{%s}" % tex_text(s.title))
                    if s.latex:
                        parts.append(r"\[ %s \]" % s.latex)
                    if s.note:
                        parts.append(r"{\small %s}" % tex_text(s.note))
                parts.append(r"\end{enumerate}")
            parts.append(r"{\footnotesize seed %d}\par\medskip" % p.seed)

    parts.append(r"\end{document}")
    return "\n".join(parts)


# --- 主程式 ---------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a batch of sample problems for manual review")
    ap.add_argument("-f", "--format", choices=("html", "tex"), default="html")
    ap.add_argument("-n", "--count", type=int, default=5, help="problems per combination (default 5)")
    ap.add_argument("-t", "--template", help="only topics whose id contains this fragment, e.g. separable")
    ap.add_argument("-d", "--difficulty", type=int, choices=(1, 2, 3), help="only this difficulty")
    ap.add_argument("-o", "--output", help="output path (default preview.html / preview.tex)")
    ap.add_argument("--no-steps", dest="steps", action="store_false",
                    help="omit the step-by-step solutions")
    ap.add_argument("--cjk-font", default="PingFang TC",
                    help="font for the LaTeX output (default PingFang TC, built into macOS)")
    args = ap.parse_args()

    out = Path(args.output) if args.output else ROOT / f"preview.{args.format}"

    print(f"Generating… ({args.count} per combination)", file=sys.stderr)
    blocks = collect(args.count, args.template, args.difficulty)

    if args.format == "html":
        text = to_html(blocks, args.count, out, args.steps)
    else:
        text = to_tex(blocks, args.count, args.steps, args.cjk_font)

    out.write_text(text, encoding="utf-8")

    total = sum(len(p) for _, _, p in blocks)
    print(f"Wrote {out} ({len(blocks)} combinations, {total} problems)", file=sys.stderr)
    if args.format == "html":
        print(f"Open it in a browser:  open {out}", file=sys.stderr)
    else:
        print(f"Compile to PDF:  cd {out.parent} && xelatex {out.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
