#!/usr/bin/env python3
"""帳號設定工具（D35）——老師用的命令列介面。

v0.16 起系統只有**兩組共用帳號**：

- **`class`**：全班共用，發給所有修課學生。
- **`staff`**：老師與助教測試用。它的用量不計入全班統計（D36）。

沒有第三組，也沒有辦法建立第三組——這支腳本只認得這兩個角色，而網頁那一側
從 v0.15 起就沒有註冊頁了。產生密碼與寫入資料庫的邏輯在 `app/accounts.py`
（那裡有格式與熵的完整說明），這裡只負責命令列與把密碼印出來。

用法
----
```bash
# 0) 先設定資料庫位置（沒設就用專案根目錄的 practice.db，與 uvicorn 一致）
export PRACTICE_DB=/path/to/practice.db

# 1) 學期初：把兩組帳號都建起來，印出密碼
python scripts/create_accounts.py init

# 2) 密碼流出去了（或學期結束要換），重設全班那一組
python scripts/create_accounts.py reset class

# 3) 想自己指定一組好念的密碼
python scripts/create_accounts.py reset class --password "fourier-series-2026"

# 4) 看目前有哪些帳號（沒有密碼——資料庫只存 argon2id 雜湊，撈不回來）
python scripts/create_accounts.py list
```

三件必須知道的事
----------------
1. **重跑 `init` 是安全的。** 已經存在的帳號會被**跳過**，密碼不變。
   這比 v0.15 更要緊：覆寫一個逐人配發的帳號只鎖住一個人，覆寫共用帳號
   是**全班同時進不來**，而且是在老師只想確認帳號建好了沒的時候。
   要換密碼請明確使用 `reset`。

2. **密碼只印在終端機上，不寫檔。** v0.15 會產生一份含明碼的 CSV 對照表
   （`ACCOUNTS-PLAINTEXT-DELETE-ME-*.csv`）——那個檔案**不存在了**，因為
   兩組密碼用不著一份對照表。這是 D35 一個實際的安全性改善：
   系統這一側再也沒有任何含明碼的檔案。
   ⚠️ 但終端機的捲動紀錄仍然有它，公用電腦上請記得清掉。

3. **密碼會被轉傳，這件事擋不住。** 一個全班共用的密碼遲早會出現在 LINE
   群組、共筆、學長姐的筆記裡。緩解不是技術性的：換密碼很便宜（一行），
   而且系統裡本來就沒有值得偷的東西——沒有個人資料、沒有成績、沒有作答內容。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 讓腳本從專案根目錄以外的地方執行時也 import 得到 app 套件
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.accounts import (  # noqa: E402
    ROLE_DESCRIPTION,
    AccountResult,
    ensure_account,
    ensure_all_accounts,
    list_accounts,
    password_entropy_bits,
)
from app.db.models import ROLES  # noqa: E402

STATUS_LABEL = {
    "created": "已建立",
    "reset": "已重設",
    "skipped": "略過",
    "invalid": "設定有誤",
}


# --- 輸出 -----------------------------------------------------------------

def print_results(results: list[AccountResult]) -> None:
    """把結果印出來，密碼在這裡出現，而且只在這裡。

    刻意把密碼印得很顯眼（單獨一行、有框），因為它只會出現這一次：
    資料庫裡是雜湊，撈不回來；再跑一次 `init` 會跳過而不是重印。
    """
    print()
    for r in results:
        label = STATUS_LABEL.get(r.status, r.status)
        print(f"[{label}] 角色 {r.role}（{ROLE_DESCRIPTION.get(r.role, '')}）")
        print(f"    登入名稱：{r.name or '(無)'}")
        if r.password:
            print(f"    密　　碼：{r.password}")
        elif r.status == "skipped":
            print("    密　　碼：未變動（資料庫只存雜湊，撈不回來）")
        if r.detail and not r.password:
            print(f"    說　　明：{r.detail}")
        print()

    if any(r.password for r in results):
        print("⚠️ 上面的密碼只會出現這一次——資料庫裡只有 argon2id 雜湊。")
        print("⚠️ 這台電腦是公用的話，用完請清掉終端機的捲動紀錄。")
        print("   （忘記了也沒關係：`reset` 子指令隨時可以換一組。）")
        print()


# --- 子指令 ---------------------------------------------------------------

def _session():
    from sqlmodel import Session

    from app.db.session import engine, init_db

    init_db()
    return Session(engine)


def cmd_init(args: argparse.Namespace) -> int:
    """把兩組帳號都準備好。已存在的跳過。"""
    with _session() as session:
        results = ensure_all_accounts(session)
    print_results(results)

    if all(r.status == "skipped" for r in results):
        print("兩組帳號都已經存在，什麼都沒有改。要換密碼請用 reset 子指令。")
    return 0 if all(r.status != "invalid" for r in results) else 1


def cmd_reset(args: argparse.Namespace) -> int:
    """重設某一組的密碼。"""
    with _session() as session:
        result = ensure_account(
            session, args.role, password=args.password, reset=True
        )
    print_results([result])
    if result.status == "reset" and args.role == "class":
        print("⚠️ 全班的密碼換掉了：舊密碼**立刻失效**，記得在課堂上或公告裡通知。")
    return 0 if result.status in ("created", "reset") else 1


def cmd_list(args: argparse.Namespace) -> int:
    with _session() as session:
        accounts = list_accounts(session)

    if not accounts:
        print("目前沒有任何帳號。請先執行：python scripts/create_accounts.py init")
        return 0

    # 用 " | " 分欄而不是靠空白對齊：中文欄名在終端機上是全形寬度，
    # Python 的 `{:<14}` 數的是字元數，對齊看起來一定是歪的。
    # 時間一律標 UTC——資料庫存的是 UTC，印成看起來像本地時間會讓人算錯。
    print("角色 | 登入名稱 | 建立時間(UTC) | 最後有人登入(UTC)")
    for a in accounts:
        fmt = lambda t: t.strftime("%Y-%m-%d %H:%M") if t else None  # noqa: E731
        created = fmt(a.created_at) or "-"
        last = fmt(a.last_login_at) or "尚未有人登入"
        print(f"{a.role} | {a.name} | {created} | {last}")
    print(f"\n共 {len(accounts)} 組帳號。**這裡看不到密碼**——資料庫只存 argon2id 雜湊。")
    print("「最後有人登入」是這組帳號最後一次被使用的時間，不是某一個人的。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="create_accounts.py",
        description=(
            "共用帳號設定工具。系統只有兩組帳號："
            + "；".join(f"{role}（{ROLE_DESCRIPTION[role]}）" for role in ROLES)
            + f"。自動產生的密碼格式為「字-字-字-兩位數字」，約 "
            f"{password_entropy_bits():.0f} bits 熵（取捨見 app/accounts.py）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="資料庫位置由環境變數 PRACTICE_DB 決定（預設為專案根目錄的 practice.db）。",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="建立兩組帳號並印出密碼（已存在的會跳過）")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("reset", help="重設某一組的密碼")
    p.add_argument("role", choices=ROLES, help="要重設哪一組")
    p.add_argument("--password", help="指定密碼（不給就自動產生）")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("list", help="列出帳號（不含密碼）")
    p.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
