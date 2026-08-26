"""共用帳號的測試（D35）：密碼格式、建立、重跑、重設、CLI。

分成三組：

1. **密碼的格式** —— 熵是可以被算出來的，所以就把它算出來斷言，
   而不是在文件裡寫一個沒有人驗過的數字。
2. **`ensure_account()` 的行為** —— 重跑不覆寫是這支工具最重要的一條性質，
   而且它在共用帳號之下**比 v0.15 更要緊**：覆寫一個逐人配發的帳號只鎖住
   一個人，覆寫共用帳號是**全班同時進不來**。
3. **CLI** —— 密碼唯一一次出現的地方。v0.15 的對照表檔案（含明碼的 CSV）
   沒有了，因此這一組的重點從「檔案權限與警告」換成「明碼不落地成檔案」。

`client` fixture 是從 `test_web.py` 借來的：它會把 `PRACTICE_DB` 指到一個
乾淨的臨時檔並重新載入所有綁著 `engine` 的模組。這裡不需要 HTTP 用戶端，
但需要那個環境——重寫一份只會多一個必須同步維護的 fixture。
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, select

from tests.test_web import client, log_in  # noqa: F401  沿用既有 fixture

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


# --- 1. 密碼的格式 ----------------------------------------------------------

def test_wordlist_is_exactly_256_distinct_clean_words():
    """字典必須恰好 256 個相異的字，且全部是 4–6 個小寫字母。

    256 是刻意的：熵才會是整數（每個字 8 bits），文件裡那個「30 bits」
    才是算得出來的而不是估的。長度上限 6 是為了讓密碼念得動。
    """
    from app.accounts import WORDLIST

    assert len(WORDLIST) == 256
    assert len(set(WORDLIST)) == 256, "字典裡有重複的字，實際熵比宣稱的低"
    for word in WORDLIST:
        assert word.isalpha() and word.islower()
        assert 4 <= len(word) <= 6, word


def test_password_entropy_is_thirty_bits():
    from app.accounts import password_entropy_bits

    assert password_entropy_bits() == pytest.approx(30.0)


def test_generated_passwords_avoid_confusable_characters():
    """`0`、`1` 與大寫一律不出現。

    v0.15 的理由是「密碼要用手從紙上抄」。v0.16 的理由更強：密碼是
    **老師在課堂上念出來、三十個人同時打進去**的一個字串——念錯一次，
    三十個人一起打錯。`l/1/I` 與 `O/0` 因此仍然是不能有的東西。
    """
    from app.accounts import generate_password

    pattern = re.compile(r"^[a-z]{4,6}-[a-z]{4,6}-[a-z]{4,6}-[2-9]{2}$")
    for _ in range(200):
        pw = generate_password()
        assert pattern.match(pw), pw
        assert "0" not in pw and "1" not in pw
        assert pw == pw.lower()


def test_generated_passwords_pass_the_sites_own_password_rules():
    """產生的密碼一定通過 `validate_password()`。

    這是一條推論（夠長、不是純數字、不等於帳號名稱、不在弱密碼清單裡），
    但推論會因為規則改動而失效——例如日後加一條「必須含大寫」，帳號會在
    建立的當下失敗。所以把它釘住。
    """
    from app.accounts import generate_password
    from app.security import validate_password

    for _ in range(200):
        assert validate_password(generate_password(), "class") is None


def test_generated_passwords_do_not_repeat():
    """200 組不該撞在一起。撞了代表用的不是 CSPRNG（或字典壞了）。"""
    from app.accounts import generate_password

    passwords = {generate_password() for _ in range(200)}
    assert len(passwords) == 200


# --- 2. ensure_account() 的行為 ---------------------------------------------

def _accounts(client):
    from app.db.models import Account

    with Session(client.session_module.engine) as s:
        return list(s.exec(select(Account).order_by(Account.role)).all())


def test_there_are_exactly_two_roles_and_no_way_to_add_a_third():
    """系統裡只有兩組帳號，而且沒有任何途徑長出第三組（D35）。

    「沒有途徑」是這條決定的實質內容，不是它的附註：只要有一個地方能建
    任意帳號，「共用帳號」就退化成「預設有兩個帳號」。
    """
    from app.db.models import ROLE_CLASS, ROLE_STAFF, ROLES

    assert ROLES == (ROLE_CLASS, ROLE_STAFF)
    assert len(ROLES) == 2


def test_init_creates_both_accounts_and_they_can_log_in(client):
    from app.accounts import ensure_all_accounts
    from app.db.models import ROLE_CLASS, ROLE_STAFF

    with Session(client.session_module.engine) as s:
        results = ensure_all_accounts(s)

    assert [r.role for r in results] == [ROLE_CLASS, ROLE_STAFF]
    assert all(r.status == "created" for r in results)
    assert all(r.password for r in results)          # 明碼只在回傳值裡

    for r in results:
        client.post("/logout")
        assert log_in(client, r.name, r.password).status_code == 303


def test_accounts_store_only_a_hash(client):
    from app.accounts import ensure_all_accounts

    with Session(client.session_module.engine) as s:
        results = ensure_all_accounts(s)

    for account, result in zip(_accounts(client), results):
        assert account.password_hash.startswith("$argon2")
        assert result.password not in account.password_hash

    db_bytes = client.session_module.DB_PATH.read_bytes()
    for result in results:
        assert result.password.encode() not in db_bytes


def test_accounts_carry_no_personal_field(client):
    """帳號那一列裡沒有人（D35）。

    這是整個 v0.16 的核心斷言：`student_no` 那一欄是系統裡唯一一項個人資料，
    拿掉之後**資料庫裡不再有任何欄位指得到特定的人**。
    """
    from app.accounts import ensure_all_accounts
    from app.db.models import Account

    with Session(client.session_module.engine) as s:
        ensure_all_accounts(s)

    assert not hasattr(Account, "student_no")
    assert not hasattr(Account, "consent_at")
    for account in _accounts(client):
        assert account.name in ("class", "staff")
        assert account.role in ("class", "staff")


def test_rerunning_does_not_overwrite_an_existing_account(client):
    """重跑必須跳過，不得覆寫。

    老師會重跑（想確認帳號建好了沒、忘記自己跑過了）。覆寫等於把**全班**
    鎖在門外，而沒有人收得到任何說明——只會發現密碼突然不能用了。
    """
    from app.accounts import ensure_account
    from app.db.models import ROLE_CLASS

    with Session(client.session_module.engine) as s:
        first = ensure_account(s, ROLE_CLASS)
    before = _accounts(client)[0].password_hash

    with Session(client.session_module.engine) as s:
        again = ensure_account(s, ROLE_CLASS)

    assert again.status == "skipped"
    assert again.password is None, "略過的帳號不該吐出任何密碼"
    assert _accounts(client)[0].password_hash == before
    assert len(_accounts(client)) == 1
    # 舊密碼仍然有效，這才是「沒有覆寫」的意思
    assert log_in(client, first.name, first.password).status_code == 303


def test_reset_replaces_the_password(client):
    from app.accounts import ensure_account
    from app.db.models import ROLE_CLASS

    with Session(client.session_module.engine) as s:
        first = ensure_account(s, ROLE_CLASS)

    with Session(client.session_module.engine) as s:
        again = ensure_account(s, ROLE_CLASS, reset=True)

    assert again.status == "reset"
    assert again.password and again.password != first.password
    assert log_in(client, "class", first.password).status_code == 200   # 舊的失效
    client.post("/logout")
    assert log_in(client, "class", again.password).status_code == 303
    assert len(_accounts(client)) == 1, "reset 不該多建一列"


def test_teacher_can_choose_the_password(client):
    """老師自行設定密碼的能力必須留著（老師的要求）。"""
    from app.accounts import ensure_account
    from app.db.models import ROLE_CLASS

    with Session(client.session_module.engine) as s:
        result = ensure_account(
            s, ROLE_CLASS, password="fourier-series-2026"
        )

    assert result.status == "created"
    assert result.password == "fourier-series-2026"
    assert log_in(client, "class", "fourier-series-2026").status_code == 303


def test_a_teacher_chosen_password_still_has_to_pass_the_rules(client):
    """老師指定的密碼一樣要驗，而且失敗時**不寫入**。

    不驗的話一個 `--password 123` 會安靜地成立，然後那個密碼要用一整個學期。
    """
    from app.accounts import ensure_account
    from app.db.models import ROLE_CLASS

    with Session(client.session_module.engine) as s:
        result = ensure_account(s, ROLE_CLASS, password="12345678")

    assert result.status == "invalid"
    assert result.password is None
    assert _accounts(client) == []


def test_an_unknown_role_is_refused(client):
    from app.accounts import ensure_account

    with Session(client.session_module.engine) as s:
        result = ensure_account(s, "admin")

    assert result.status == "invalid"
    assert _accounts(client) == []


def test_account_names_come_from_configuration(client, monkeypatch):
    """名稱可由環境變數改，角色不行——排除 staff 流量靠的是角色。"""
    monkeypatch.setenv("CLASS_ACCOUNT_NAME", "engmath-2026")
    importlib.reload(importlib.import_module("app.config"))
    accounts_module = importlib.reload(importlib.import_module("app.accounts"))

    from app.db.models import ROLE_CLASS

    with Session(client.session_module.engine) as s:
        result = accounts_module.ensure_account(s, ROLE_CLASS)

    assert result.name == "engmath-2026"
    assert result.role == ROLE_CLASS
    assert log_in(client, "engmath-2026", result.password).status_code == 303

    monkeypatch.delenv("CLASS_ACCOUNT_NAME")
    importlib.reload(importlib.import_module("app.config"))
    importlib.reload(importlib.import_module("app.accounts"))


def test_a_bad_account_name_in_the_configuration_is_refused_loudly(
    client, monkeypatch, caplog
):
    """名稱不合法 = 那個角色永遠登入不了，而畫面上不會有任何提示（規則 4）。"""
    monkeypatch.setenv("CLASS_ACCOUNT_NAME", "a b c!")
    importlib.reload(importlib.import_module("app.config"))
    accounts_module = importlib.reload(importlib.import_module("app.accounts"))

    from app.db.models import ROLE_CLASS

    with caplog.at_level("ERROR"):
        with Session(client.session_module.engine) as s:
            result = accounts_module.ensure_account(s, ROLE_CLASS)

    assert result.status == "invalid"
    assert _accounts(client) == []
    assert any("CLASS_ACCOUNT_NAME" in r.getMessage() for r in caplog.records)

    monkeypatch.delenv("CLASS_ACCOUNT_NAME")
    importlib.reload(importlib.import_module("app.config"))
    importlib.reload(importlib.import_module("app.accounts"))


# --- 3. CLI -----------------------------------------------------------------

def _run_cli(argv: list[str]) -> int:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        module = importlib.import_module("create_accounts")
        importlib.reload(module)      # 讓它接上 fixture 換掉的 engine
        return module.main(argv)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def _password_from(output: str) -> str:
    match = re.search(r"密　　碼：(\S+)", output)
    assert match, f"CLI 沒有印出密碼：\n{output}"
    return match.group(1)


def test_cli_init_creates_both_accounts_and_prints_the_passwords(client, capsys):
    assert _run_cli(["init"]) == 0
    out = capsys.readouterr().out

    assert {a.role for a in _accounts(client)} == {"class", "staff"}
    assert "class" in out and "staff" in out
    # 兩組密碼各印一次，而且真的能登入
    passwords = re.findall(r"密　　碼：(\S+)", out)
    assert len(passwords) == 2
    for name, pw in zip(("class", "staff"), passwords):
        client.post("/logout")
        assert log_in(client, name, pw).status_code == 303


def test_cli_writes_no_file_with_a_plaintext_password(client, tmp_path, capsys):
    """v0.16 最實際的一個安全性改善：**明碼不再落地成檔案**（D35）。

    v0.15 會產生一份 `ACCOUNTS-PLAINTEXT-DELETE-ME-*.csv`，而 §4.4 第 6 點
    寫著「系統多了一個明碼會落地的地方，而且只有一個」。兩組密碼用不著一份
    對照表，所以那個檔案整個沒有了——這一項確認它真的沒有偷偷回來。
    """
    before = {p.name for p in tmp_path.iterdir()}
    monkey_cwd = tmp_path

    import os

    cwd = os.getcwd()
    os.chdir(monkey_cwd)
    try:
        _run_cli(["init"])
    finally:
        os.chdir(cwd)

    after = {p.name for p in tmp_path.iterdir()}
    assert after == before, f"CLI 在工作目錄裡留下了檔案：{after - before}"

    password = _password_from(capsys.readouterr().out)
    # 專案裡任何一個檔案都不該含那組密碼
    root = Path(__file__).resolve().parent.parent
    for path in list(root.glob("*.csv")) + list(root.glob("*.txt")):
        assert password not in path.read_text(encoding="utf-8", errors="ignore")


def test_cli_rerun_of_init_changes_nothing(client, capsys):
    _run_cli(["init"])
    capsys.readouterr()
    hashes = [a.password_hash for a in _accounts(client)]

    assert _run_cli(["init"]) == 0
    out = capsys.readouterr().out

    assert [a.password_hash for a in _accounts(client)] == hashes
    assert "略過" in out
    assert "兩組帳號都已經存在" in out
    assert not re.findall(r"密　　碼：\S+-\S+", out), "略過的帳號不該印出密碼"


def test_cli_reset_replaces_only_that_role(client, capsys):
    _run_cli(["init"])
    capsys.readouterr()
    before = {a.role: a.password_hash for a in _accounts(client)}

    assert _run_cli(["reset", "class"]) == 0
    out = capsys.readouterr().out
    after = {a.role: a.password_hash for a in _accounts(client)}

    assert after["class"] != before["class"]
    assert after["staff"] == before["staff"], "reset class 不該動到 staff"
    assert log_in(client, "class", _password_from(out)).status_code == 303
    # 換全班密碼是一件要通知全班的事，CLI 要說出來（規則 4 的精神）
    assert "舊密碼**立刻失效**" in out


def test_cli_reset_accepts_a_password_from_the_teacher(client, capsys):
    _run_cli(["init"])
    capsys.readouterr()

    assert _run_cli(["reset", "class", "--password", "wave-equation-2026"]) == 0
    assert log_in(client, "class", "wave-equation-2026").status_code == 303


def test_cli_refuses_an_unknown_role(client):
    with pytest.raises(SystemExit):        # argparse 的 choices 擋下來
        _run_cli(["reset", "everyone"])


def test_cli_list_never_prints_a_password(client, capsys):
    _run_cli(["init"])
    password = _password_from(capsys.readouterr().out)

    assert _run_cli(["list"]) == 0
    out = capsys.readouterr().out
    assert "class" in out and "staff" in out
    assert "尚未有人登入" in out
    assert password not in out
    assert "雜湊" in out


def test_cli_list_says_the_login_time_is_not_a_persons(client, capsys):
    """措辭要說實話：那是「這組帳號最後被使用的時間」，不是某個人的。"""
    _run_cli(["init"])
    capsys.readouterr()
    _run_cli(["list"])
    assert "不是某一個人的" in capsys.readouterr().out


def test_cli_has_no_subcommand_that_creates_an_arbitrary_account():
    """CLI 不得長出 `add`／`batch` 這種可以建任意帳號的子指令（D35）。

    v0.15 有 `add` 與 `batch`，它們正是「共用帳號」這條決定會被安靜地
    繞過的地方——多建一個帳號不會讓任何測試變紅。
    """
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        module = importlib.reload(importlib.import_module("create_accounts"))
        parser = module.build_parser()
    finally:
        sys.path.remove(str(SCRIPTS_DIR))

    actions = [
        a for a in parser._actions if hasattr(a, "choices") and a.dest == "command"
    ]
    assert actions, "找不到子指令，parser 可能被改壞了"
    assert set(actions[0].choices) == {"init", "reset", "list"}
