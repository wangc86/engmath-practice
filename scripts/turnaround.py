#!/usr/bin/env python3
"""派送任務的牆鐘時間紀錄（`TURNAROUND.csv`）。

    python scripts/turnaround.py start 2S10 --title "..." --estimate 0.5
    python scripts/turnaround.py finish 2S10 --commits 5 --tests-before 471 \
        --tests-after 553 --files 2 --note "..."
    python scripts/turnaround.py report
    python scripts/turnaround.py check

**這支腳本回答的問題只有一個**：PLAN §6 估的 17.8 人週，實際請 AI 執行
總共要花多久牆鐘時間？兩者的比值是老師唯一拿得到的排程依據，
而它只能由實測累積出來——人週是一個估計，牆鐘時間不是。

---

## 為什麼是 CSV 而不是 Markdown 表格

因為這份紀錄存在的**全部目的**就是拿來加總與相除。Markdown 表格要人用眼睛
把數字抄出來（或寫一支 parser 去剖它），而 CSV 打開就是 `sum()`。

那人怎麼讀？`report` 子指令印出來給人看。**刻意不另外維護一份 `.md`**：
兩份會漂移，而一份會漂移的自述比沒有自述更不誠實（D24 的同一個論證）。

## 為什麼有一欄 `start_accuracy`

因為開始時間**常常拿不到精確值**。一個工作階段的真正起點是「老師按下送出」
的那一刻，而那個時間點在沙箱裡沒有留下任何痕跡——能拿到的最早證據是
沙箱開機或第一次寫檔。

把「估的」與「量的」混在同一欄裡，整份紀錄的可信度就等於最差的那一列，
而且沒有人看得出是哪一列。**所以誠實不是寫在備註裡，是寫成一個欄位**，
而 `check` 會要求估計值的那幾列必須說明依據（`tests/test_turnaround.py` 盯著）。

## 怎麼讓它不被忘記

本專案的慣例是「會被忘記的流程等於沒有流程」，所以這裡疊了三層，
一層比一層被動：

1. **`CLAUDE.md` 的一條慣例**——開工先 `start`、提交前 `finish`。
   這一層靠人（或 AI）記得，所以它最弱。
2. **`scripts/git-safe-commit.sh` 的提醒**——那支腳本是本專案**唯一**的
   提交途徑（沙箱不能 unlink，`git commit` 會卡在鎖檔上），所以每一次提交
   一定會經過它。沒有 `start` 過就印一行提醒。**刻意不擋提交**：
   為了一筆記帳而讓提交失敗，代價比漏一列大得多。
3. **`tests/test_turnaround.py`**——最後一列的 `tests_after` 必須等於
   `pytest` 實際收集到的項數。⛔ **這一層才是真正不依賴人記得的那一層**：
   任何一次加了測試卻沒有更新紀錄的變更，都會讓那一項變紅。

⚠️ 第 3 層守得住「紀錄有沒有跟上」，**守不住「有沒有開一列」**——
一個完全沒有動到測試的任務（純文件）不會觸發它。那個縫隙沒有辦法用
程式補起來，只能靠第 1、2 層，這件事寫在這裡而不是假裝已經解決。
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "TURNAROUND.csv"

#: 進行中的任務。**不進版本控制**（`.gitignore`），因為它是一個工作階段的
#: 暫存狀態，不是紀錄本身。
MARKER_PATH = ROOT / ".turnaround-current.json"

#: 欄位順序。改動它就要同步改 `tests/test_turnaround.py` 的那一項——
#: 那是刻意的，欄位是這份紀錄的介面。
FIELDS = [
    "task",            # PLAN 的工作項編號，例如 2S10
    "title",           # 一句話說明
    "estimate_pw",     # PLAN 估的人週
    "start",           # ISO 8601，含時區
    "end",             # 同上
    "elapsed_hours",   # 牆鐘小時，兩位小數
    "start_accuracy",  # measured | estimated
    "commits",         # 這一輪的 commit 數
    "tests_before",    # 這一輪之前的測試項數
    "tests_after",     # 這一輪之後的測試項數
    "files_added",     # 新增的檔案數（不含改動）
    "note",            # 影響時間的因素；estimated 的列必須說明依據
]

ACCURACY = ("measured", "estimated")


def now_iso() -> str:
    """帶時區的當下時間。**一定要帶時區**——沙箱與老師的機器不在同一個時區，
    而一個沒有時區的時間戳在相減的時候會安靜地錯八小時。"""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def read_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(rows: list[dict]) -> None:
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def elapsed_hours(start: str, end: str) -> float:
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return round(delta.total_seconds() / 3600, 2)


def collected_test_count() -> int:
    """`pytest --collect-only` 實際收集到幾項。

    ⚠️ 用**收集**而不是**執行**：收集只 import 測試模組、不跑任何測試，
    幾秒鐘就結束，而且不需要 node。缺 node 的機器上執行結果會有一堆 skip，
    但收集到的項數是一樣的——這一點很重要，否則這個數字會隨機器變動。
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.endswith("tests collected") or " tests collected" in line:
            return int(line.split()[0])
        if line.endswith("test collected"):
            return int(line.split()[0])
    raise RuntimeError(
        "無法從 pytest --collect-only 的輸出裡讀出項數。輸出結尾：\n"
        + "\n".join(result.stdout.splitlines()[-5:])
        + "\n" + result.stderr[-500:]
    )


# ------------------------------------------------------------------ 子指令

def cmd_start(args: argparse.Namespace) -> int:
    marker = {
        "task": args.task,
        "title": args.title,
        "estimate_pw": args.estimate,
        "start": args.at or now_iso(),
        "start_accuracy": "measured" if args.at is None else "estimated",
    }
    MARKER_PATH.write_text(json.dumps(marker, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    print(f"{marker['task']} 開始於 {marker['start']}（{marker['start_accuracy']}）")
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    marker = {}
    if MARKER_PATH.exists():
        marker = json.loads(MARKER_PATH.read_text(encoding="utf-8"))

    if marker.get("task") == args.task and args.start is None:
        start = marker["start"]
        accuracy = marker.get("start_accuracy", "measured")
    else:
        # 沒有 marker（或 marker 是別的任務）就必須自己給開始時間，
        # 而那一定是估的——所以強制標記，並強制附上依據。
        if args.start is None:
            print("找不到這個任務的開始紀錄，請用 --start 給一個估計值，"
                  "並在 --note 裡說明依據。", file=sys.stderr)
            return 1
        start = args.start
        accuracy = "estimated"

    if accuracy == "estimated" and not args.note:
        print("開始時間是估計值，--note 必須說明依據（規則 4：不許靜默失敗）。",
              file=sys.stderr)
        return 1

    end = args.end or now_iso()
    row = {
        "task": args.task,
        "title": args.title or marker.get("title", ""),
        "estimate_pw": args.estimate if args.estimate is not None
        else marker.get("estimate_pw", ""),
        "start": start,
        "end": end,
        "elapsed_hours": f"{elapsed_hours(start, end):.2f}",
        "start_accuracy": accuracy,
        "commits": args.commits,
        "tests_before": args.tests_before,
        "tests_after": args.tests_after,
        "files_added": args.files,
        "note": args.note or "",
    }
    rows = [r for r in read_rows() if r["task"] != args.task]
    rows.append(row)
    write_rows(rows)
    # marker 用覆寫而不是刪除：沙箱不能 unlink（CLAUDE.md）。
    MARKER_PATH.write_text("{}\n", encoding="utf-8")
    print(f"已寫入 {CSV_PATH.name}：{args.task}，牆鐘 {row['elapsed_hours']} 小時")
    return 0


def cmd_report(_args: argparse.Namespace) -> int:
    rows = read_rows()
    if not rows:
        print("TURNAROUND.csv 還沒有任何一列。")
        return 0

    width = max(len(r["task"]) for r in rows)
    print(f"{'task'.ljust(width)}  {'PW':>5}  {'hours':>6}  {'h/PW':>6}  acc        title")
    print("-" * (width + 60))
    total_pw = 0.0
    total_hours = 0.0
    for row in rows:
        pw = float(row["estimate_pw"])
        hours = float(row["elapsed_hours"])
        total_pw += pw
        total_hours += hours
        ratio = hours / pw if pw else float("nan")
        print(f"{row['task'].ljust(width)}  {pw:5.2f}  {hours:6.2f}  {ratio:6.2f}  "
              f"{row['start_accuracy']:<9}  {row['title']}")
    print("-" * (width + 60))
    print(f"{'total'.ljust(width)}  {total_pw:5.2f}  {total_hours:6.2f}  "
          f"{total_hours / total_pw if total_pw else float('nan'):6.2f}")
    print()
    if total_pw:
        rate = total_hours / total_pw
        print(f"目前的換算：PLAN 上每 1 人週 ≈ {rate:.2f} 牆鐘小時。")
        print(f"依此推算，剩下的工作量（PLAN §6 總量 17.8 PW 扣掉已完成的 "
              f"{total_pw:.2f}）約需 {(17.8 - total_pw) * rate:.0f} 牆鐘小時。")
        print("⚠️ 這是一個外插，而樣本數是 "
              f"{len(rows)} 列——不同性質的工作項（出題引擎 vs 前端展示 vs 文件）"
              "很可能有完全不同的比值，不要拿它當承諾。")
    estimated = [r["task"] for r in rows if r["start_accuracy"] == "estimated"]
    if estimated:
        print(f"⚠️ 開始時間為估計值的列：{', '.join(estimated)}（見各列的 note）。")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    problems = check_rows(read_rows())
    if problems:
        print("TURNAROUND.csv 有問題：")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("TURNAROUND.csv 沒有問題。")
    return 0


def check_rows(rows: list[dict]) -> list[str]:
    """一致性檢查。`tests/test_turnaround.py` 直接用這一支，所以它回傳
    問題清單而不是 assert——要能一次印出全部。"""
    problems: list[str] = []
    seen = set()
    for row in rows:
        task = row.get("task", "?")
        if task in seen:
            problems.append(f"{task}：重複的任務編號")
        seen.add(task)
        try:
            start = datetime.fromisoformat(row["start"])
            end = datetime.fromisoformat(row["end"])
        except ValueError as err:
            problems.append(f"{task}：時間格式不是 ISO 8601（{err}）")
            continue
        if start.tzinfo is None or end.tzinfo is None:
            problems.append(f"{task}：時間戳沒有帶時區")
        if end <= start:
            problems.append(f"{task}：結束時間不晚於開始時間")
        want = round((end - start).total_seconds() / 3600, 2)
        if abs(float(row["elapsed_hours"]) - want) > 0.011:
            problems.append(
                f"{task}：elapsed_hours 是 {row['elapsed_hours']}，"
                f"但由起訖時間算出來是 {want:.2f}"
            )
        if row["start_accuracy"] not in ACCURACY:
            problems.append(f"{task}：start_accuracy 只能是 {ACCURACY}")
        if row["start_accuracy"] == "estimated" and not row["note"].strip():
            problems.append(f"{task}：開始時間是估計值，note 必須說明依據")
        try:
            if float(row["estimate_pw"]) <= 0:
                problems.append(f"{task}：estimate_pw 必須為正")
        except ValueError:
            problems.append(f"{task}：estimate_pw 不是數字")
        for key in ("commits", "tests_before", "tests_after", "files_added"):
            try:
                if int(row[key]) < 0:
                    problems.append(f"{task}：{key} 不能是負的")
            except ValueError:
                problems.append(f"{task}：{key} 不是整數")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="記錄一個任務的開始時間")
    start.add_argument("task")
    start.add_argument("--title", default="")
    start.add_argument("--estimate", type=float, required=True, help="PLAN 估的人週")
    start.add_argument("--at", default=None,
                       help="覆寫開始時間（ISO 8601）。用了就會被標成 estimated。")
    start.set_defaults(func=cmd_start)

    finish = subparsers.add_parser("finish", help="收尾並寫入 TURNAROUND.csv")
    finish.add_argument("task")
    finish.add_argument("--title", default=None)
    finish.add_argument("--estimate", type=float, default=None)
    finish.add_argument("--start", default=None, help="沒有 start 紀錄時的估計開始時間")
    finish.add_argument("--end", default=None)
    finish.add_argument("--commits", type=int, required=True)
    finish.add_argument("--tests-before", type=int, required=True)
    finish.add_argument("--tests-after", type=int, required=True)
    finish.add_argument("--files", type=int, required=True, help="新增的檔案數")
    finish.add_argument("--note", default="")
    finish.set_defaults(func=cmd_finish)

    report = subparsers.add_parser("report", help="印出給人看的報表")
    report.set_defaults(func=cmd_report)

    check = subparsers.add_parser("check", help="只做一致性檢查")
    check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
