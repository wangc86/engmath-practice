#!/usr/bin/env python3
"""帳號配發工具（D32）——老師用的命令列介面。

v0.15 起學生不能自行註冊，帳號一律由老師預先建立、把「學號 ↔ 初始密碼」的
對照表發給修課學生。這支腳本是做那件事的地方；產生密碼與寫入資料庫的邏輯
在 `app/accounts.py`（那裡有格式與熵的完整說明），這裡只負責命令列、
對照表輸出、以及把「這份檔案含明碼」這件事講到不可能被忽略。

用法
----
```bash
# 0) 先設定資料庫位置（沒設就用專案根目錄的 practice.db，與 uvicorn 一致）
export PRACTICE_DB=/path/to/practice.db

# 1) 批次建立：一份學號清單（一行一個，允許空行與 # 註解）
python scripts/create_accounts.py batch students.txt

# 2) 先看看會發生什麼事，不寫入
python scripts/create_accounts.py batch students.txt --dry-run

# 3) 學期中加簽一個人
python scripts/create_accounts.py add 41047099

# 4) 學生忘記密碼，重設一筆
python scripts/create_accounts.py reset 41047001

# 5) 看目前有哪些帳號（只有學號與時間，沒有密碼——密碼是雜湊，撈不回來）
python scripts/create_accounts.py list

# 6) 重跑整份清單，且**強制**把已存在的帳號一併重設（危險，見下）
python scripts/create_accounts.py batch students.txt --reset-existing
```

三件必須知道的事
----------------
1. **重跑是安全的。** `batch` 預設**跳過**已存在的學號，不覆寫。加退選之後
   把整份新名單再跑一次是正確的用法，只有新的人會拿到新帳號。
   `--reset-existing` 會把**清單上每一個人**的密碼都換掉，等於讓全班手上的
   密碼同時失效——它存在是為了「對照表外流」這種場合，不是日常用的。

2. **對照表含明碼，發完就刪。** 檔名固定含 `DELETE-ME`，檔案權限設為 0600，
   檔頭有一段警告。這是系統裡唯一一個明碼會落地的地方，而它落地是因為
   老師需要有東西可以發——不是因為系統存了它（資料庫裡只有 argon2id 雜湊）。

3. **學生改了密碼之後，對照表就對不上了。** 這是刻意的（D34）：學生可以自行
   修改密碼，改完之後老師手上那份表對他就失效。學生忘記密碼時用 `reset`
   子指令重發一組，不要回頭去翻舊表。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# 讓腳本從專案根目錄以外的地方執行時也 import 得到 app 套件
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.accounts import (  # noqa: E402
    AccountResult,
    create_account,
    create_accounts,
    list_accounts,
    parse_student_list,
    password_entropy_bits,
)

WARNING_LINES = (
    "⚠️ 本檔案含**明碼密碼**。發給學生之後請立刻刪除，不要留在雲端硬碟或信箱裡。",
    "⚠️ 學生一旦自行修改密碼，本表對他即失效；忘記密碼請用 "
    "`python scripts/create_accounts.py reset <學號>` 重發。",
)

STATUS_LABEL = {
    "created": "已建立",
    "reset": "已重設",
    "skipped": "略過",
    "invalid": "格式錯誤",
}


# --- 對照表輸出 -----------------------------------------------------------

def default_handout_path(prefix: str = "ACCOUNTS") -> Path:
    """預設檔名。**`DELETE-ME` 寫在檔名裡**，這樣它在檔案總管、`ls`、
    雲端硬碟的清單裡都會自己喊出來，不必依賴有人記得打開檔案看檔頭。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(f"{prefix}-PLAINTEXT-DELETE-ME-{stamp}.csv")


def render_handout(results: list[AccountResult], fmt: str) -> str:
    """把有密碼的那些列渲染成對照表。

    只有 `created` 與 `reset` 有密碼；`skipped` 的帳號**撈不出舊密碼**
    （資料庫裡只有雜湊），所以它們不會出現在對照表裡——這一點要在 stdout
    的摘要上講清楚，否則老師會以為漏印了。
    """
    rows = [(r.student_no, r.password) for r in results if r.password]

    if fmt == "md":
        body = "\n".join(f"| {no} | `{pw}` |" for no, pw in rows)
        return (
            "\n".join(f"> {line}" for line in WARNING_LINES)
            + "\n\n| 學號 Student ID | 初始密碼 Initial password |\n"
            + "|---|---|\n"
            + body
            + "\n"
        )

    sep = "\t" if fmt == "tsv" else ","
    header = "\n".join(f"# {line}" for line in WARNING_LINES)
    body = "\n".join(f"{no}{sep}{pw}" for no, pw in rows)
    return f"{header}\n{'student_no'}{sep}{'initial_password'}\n{body}\n"


def write_handout(path: Path, text: str) -> None:
    """寫檔並把權限收緊為 0600。

    **權限失敗不靜默**（專案硬規則 #4）：Windows 上 `os.chmod` 對 0600 幾乎
    等於無效，那不是錯誤，但老師應該知道這件事——因為它決定了這個檔案在
    共用電腦上是不是別人也讀得到。
    """
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        print(
            f"⚠️ 無法把 {path} 的權限收緊為 600（{exc}）。"
            f"這個檔案含明碼密碼，請自行確認它不是別人讀得到的。",
            file=sys.stderr,
        )


# --- 摘要 -----------------------------------------------------------------

def print_summary(results: list[AccountResult], handout: Path | None) -> None:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    print()
    print("處理結果：")
    for status in ("created", "reset", "skipped", "invalid"):
        if counts.get(status):
            print(f"  {STATUS_LABEL[status]:<6} {counts[status]:>4} 筆")

    for r in results:
        if r.status == "invalid":
            print(f"  ⚠️ {r.student_no or '(空白)'}：{r.detail}")

    if counts.get("skipped"):
        print(
            "\n註：略過的帳號**沒有出現在對照表裡**——資料庫只存密碼雜湊，"
            "撈不回舊密碼。要重發請用 reset 子指令。"
        )

    if handout is not None:
        print(f"\n對照表已寫入：{handout}")
        for line in WARNING_LINES:
            print(f"  {line}")


# --- 子指令 ---------------------------------------------------------------

def _session():
    from app.db.session import engine, init_db
    from sqlmodel import Session

    init_db()
    return Session(engine)


def cmd_batch(args: argparse.Namespace) -> int:
    text = Path(args.list_file).read_text(encoding="utf-8")
    student_nos = parse_student_list(text)
    if not student_nos:
        print(f"清單 {args.list_file} 裡沒有任何學號。", file=sys.stderr)
        return 1

    print(f"讀到 {len(student_nos)} 個學號。")
    if args.dry_run:
        print("（--dry-run：不寫入資料庫、不產生對照表）")
        for no in student_nos:
            print(f"  {no}")
        return 0

    with _session() as session:
        results = create_accounts(session, student_nos, reset=args.reset_existing)

    handout = _emit(results, args)
    print_summary(results, handout)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    with _session() as session:
        result = create_account(session, args.student_no, password=args.password)
    handout = _emit([result], args)
    print_summary([result], handout)
    return 0 if result.status in ("created", "reset") else 1


def cmd_reset(args: argparse.Namespace) -> int:
    with _session() as session:
        from sqlmodel import select
        from app.db.models import Student
        from app.security import normalize_student_no

        student_no = normalize_student_no(args.student_no)
        exists = session.exec(
            select(Student).where(Student.student_no == student_no)
        ).first()
        if exists is None:
            # 不靜默：重設一個不存在的帳號幾乎一定是打錯字，而預設建立它
            # 會讓那個錯字變成一個沒有人用得到的幽靈帳號。
            print(
                f"沒有這個帳號：{student_no}。"
                f"（要建立新帳號請用 add 子指令。）",
                file=sys.stderr,
            )
            return 1
        result = create_account(
            session, student_no, password=args.password, reset=True
        )
    handout = _emit([result], args)
    print_summary([result], handout)
    return 0 if result.status == "reset" else 1


def cmd_list(args: argparse.Namespace) -> int:
    with _session() as session:
        students = list_accounts(session)

    if not students:
        print("目前沒有任何帳號。")
        return 0

    # 用 " | " 分欄而不是靠空白對齊：中文欄名在終端機上是全形寬度，
    # Python 的 `{:<14}` 數的是字元數，對齊看起來一定是歪的。
    # 時間一律標 UTC——資料庫存的是 UTC，印成看起來像本地時間會讓人算錯。
    print("學號 | 建立時間(UTC) | 最後登入(UTC) | 已讀個資告知(UTC)")
    for s in students:
        fmt = lambda t: t.strftime("%Y-%m-%d %H:%M") if t else None  # noqa: E731
        created = fmt(s.created_at) or "-"
        last = fmt(s.last_login_at) or "尚未登入"
        consent = fmt(s.consent_at) or "尚未確認"
        print(f"{s.student_no} | {created} | {last} | {consent}")
    print(f"\n共 {len(students)} 個帳號。**這裡看不到密碼**——資料庫只存 argon2id 雜湊。")
    return 0


def _emit(results: list[AccountResult], args: argparse.Namespace) -> Path | None:
    """有密碼才產生對照表；一筆都沒有就不要留下一個空檔案。"""
    if not any(r.password for r in results):
        return None
    path = Path(args.out) if args.out else default_handout_path()
    write_handout(path, render_handout(results, args.format))
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="create_accounts.py",
        description=(
            "帳號配發工具。初始密碼格式為「字-字-字-兩位數字」"
            f"（約 {password_entropy_bits():.0f} bits 熵，格式的取捨見 app/accounts.py）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="資料庫位置由環境變數 PRACTICE_DB 決定（預設為專案根目錄的 practice.db）。",
    )
    parser.add_argument(
        "--out", help="對照表輸出路徑（預設自動命名為 ACCOUNTS-PLAINTEXT-DELETE-ME-*.csv）"
    )
    parser.add_argument(
        "--format", choices=("csv", "tsv", "md"), default="csv",
        help="對照表格式：csv（預設，可貼進 Excel／Moodle）、tsv、md（適合列印）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("batch", help="從一份學號清單批次建立帳號")
    p.add_argument("list_file", help="學號清單檔（一行一個，允許空行與 # 註解）")
    p.add_argument(
        "--reset-existing", action="store_true",
        help="⚠️ 連已存在的帳號也一併重設密碼（預設是跳過，不覆寫）",
    )
    p.add_argument("--dry-run", action="store_true", help="只印出會處理哪些學號，不寫入")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("add", help="單筆建立一個帳號")
    p.add_argument("student_no")
    p.add_argument("--password", help="指定密碼（不給就自動產生；一般不需要用）")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("reset", help="單筆重設密碼（學生忘記密碼時用）")
    p.add_argument("student_no")
    p.add_argument("--password", help="指定新密碼（不給就自動產生）")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("list", help="列出所有帳號（不含密碼）")
    p.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
