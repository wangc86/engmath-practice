"""帳號配發的測試（D32）：初始密碼、批次建立、重跑、重設、對照表。

分成三組：

1. **初始密碼的格式** —— 熵是可以被算出來的，所以就把它算出來斷言，
   而不是在文件裡寫一個沒有人驗過的數字。
2. **`create_account()` 的行為** —— 重跑不覆寫是這支工具最重要的一條性質：
   覆寫一個已存在的帳號等於把那個學生鎖在門外，而**他不會收到任何錯誤訊息**，
   只會發現密碼突然不能用了。
3. **CLI 與對照表** —— 明碼落地的唯一一處，因此檔名、權限、警告都要有測試。

`client` fixture 是從 `test_web.py` 借來的：它會把 `PRACTICE_DB` 指到一個
乾淨的臨時檔並重新載入所有綁著 `engine` 的模組。這裡不需要 HTTP 用戶端，
但需要那個環境——重寫一份只會多一個必須同步維護的 fixture。
"""

from __future__ import annotations

import re
import stat
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, select

from tests.test_web import client, log_in  # noqa: F401  沿用既有 fixture

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


# --- 1. 初始密碼的格式 ------------------------------------------------------

def test_wordlist_is_exactly_256_distinct_clean_words():
    """字典必須恰好 256 個相異的字，且全部是 4–6 個小寫字母。

    256 是刻意的：熵才會是整數（每個字 8 bits），文件裡那個「30 bits」
    才是算得出來的而不是估的。長度上限 6 是為了讓密碼抄得動。
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
    """`0`、`1` 與大寫一律不出現——初始密碼是要用手抄、用嘴巴念的。

    `l/1/I` 與 `O/0` 是抄錯的兩大來源。字典全小寫、數字只用 2–9，
    因此整個密碼裡不存在任何一對長得像的字元。
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

    這是一條推論（夠長、不是純數字、不等於學號、不在弱密碼清單裡），
    但推論會因為規則改動而失效——例如日後加一條「必須含大寫」，
    整批配發的帳號會在建立的當下全部失敗。所以把它釘住。
    """
    from app.accounts import generate_password
    from app.security import validate_password

    for _ in range(200):
        assert validate_password(generate_password(), "41047001") is None


def test_generated_passwords_do_not_repeat():
    """200 組不該撞在一起。撞了代表用的不是 CSPRNG（或字典壞了）。"""
    from app.accounts import generate_password

    passwords = {generate_password() for _ in range(200)}
    assert len(passwords) == 200


# --- 2. create_account() 的行為 ---------------------------------------------

def _students(client):
    from app.db.models import Student

    with Session(client.session_module.engine) as s:
        return list(s.exec(select(Student)).all())


def test_create_account_creates_a_login_that_works(client):
    from app.accounts import create_account

    with Session(client.session_module.engine) as s:
        result = create_account(s, "41047001")

    assert result.status == "created"
    assert result.password                      # 明碼只在回傳值裡
    assert log_in(client, "41047001", result.password).status_code == 303


def test_create_account_stores_only_a_hash(client):
    from app.accounts import create_account

    with Session(client.session_module.engine) as s:
        result = create_account(s, "41047001")

    student = _students(client)[0]
    assert student.password_hash.startswith("$argon2")
    assert result.password not in student.password_hash

    db_bytes = client.session_module.DB_PATH.read_bytes()
    assert result.password.encode() not in db_bytes


def test_new_accounts_have_not_consented_yet(client):
    """CLI 建的帳號 `consent_at` 必須是 None——那是 D33 閘門唯一的依據。

    如果建帳號時順手填了 `consent_at`，個資告知就再也不會顯示給任何人看，
    而且**沒有任何東西會壞掉**：學生直接進到出題頁，一切正常。
    這正是需要測試盯著的那種缺陷。
    """
    from app.accounts import create_account

    with Session(client.session_module.engine) as s:
        create_account(s, "41047001")

    assert _students(client)[0].consent_at is None


def test_rerunning_does_not_overwrite_an_existing_account(client):
    """重跑必須跳過，不得覆寫。

    老師會重跑（加退選、補發、手滑）。覆寫等於把那個學生鎖在門外，而他
    收不到任何說明——只會發現密碼突然不能用了。
    """
    from app.accounts import create_account

    with Session(client.session_module.engine) as s:
        first = create_account(s, "41047001")
    before = _students(client)[0].password_hash

    with Session(client.session_module.engine) as s:
        again = create_account(s, "41047001")

    assert again.status == "skipped"
    assert again.password is None, "略過的帳號不該吐出任何密碼"
    assert _students(client)[0].password_hash == before
    assert len(_students(client)) == 1
    # 舊密碼仍然有效，這才是「沒有覆寫」的意思
    assert log_in(client, "41047001", first.password).status_code == 303


def test_reset_replaces_the_password_but_keeps_consent(client):
    from app.accounts import create_account
    from datetime import datetime, timezone
    from app.db.models import Student

    with Session(client.session_module.engine) as s:
        first = create_account(s, "41047001")
        row = s.exec(select(Student)).one()
        row.consent_at = datetime.now(timezone.utc)
        s.add(row)
        s.commit()
        consented_at = row.consent_at

    with Session(client.session_module.engine) as s:
        again = create_account(s, "41047001", reset=True)

    assert again.status == "reset"
    assert again.password and again.password != first.password
    assert log_in(client, "41047001", first.password).status_code == 200   # 舊的失效
    assert log_in(client, "41047001", again.password).status_code == 303

    # 重設密碼與「讀過個資告知」是兩件事，不該把人再擋一次
    assert _students(client)[0].consent_at == consented_at


def test_invalid_student_numbers_are_reported_not_created(client):
    from app.accounts import create_accounts

    with Session(client.session_module.engine) as s:
        results = create_accounts(s, ["41047001", "!!", "", "ab"])

    by_no = {r.student_no: r for r in results}
    assert by_no["41047001"].status == "created"
    assert by_no["!!"].status == "invalid"
    assert by_no[""].status == "invalid"
    assert by_no["AB"].status == "invalid"        # 太短（規則是 4–20）
    assert len(_students(client)) == 1


def test_batch_deduplicates_within_one_list(client):
    """同一份清單裡重複的學號只處理一次，而且訊息要說實話。

    不去重的話第二次會走到「帳號已存在」，訊息讀起來像「本來就有這個人」
    ——老師會以為名單有問題，而問題其實在名單裡有兩行一樣的字。
    """
    from app.accounts import create_accounts

    with Session(client.session_module.engine) as s:
        results = create_accounts(s, ["41047001", "41047001", " 41047001 "])

    assert [r.status for r in results] == ["created", "skipped", "skipped"]
    assert "重複" in results[1].detail
    assert len(_students(client)) == 1


def test_parse_student_list_is_forgiving():
    from app.accounts import parse_student_list

    text = (
        "# 114-1 工程數學 修課名單\n"
        "41047001\n"
        "\n"
        "41047002, 41047003\n"
        "41047004\t41047005\n"
        "41047006  # 已退選\n"
    )
    assert parse_student_list(text) == [
        "41047001", "41047002", "41047003", "41047004", "41047005", "41047006",
    ]


# --- 3. CLI 與對照表 --------------------------------------------------------

def _run_cli(argv: list[str]) -> int:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        import importlib

        module = importlib.import_module("create_accounts")
        importlib.reload(module)      # 讓它接上 fixture 換掉的 engine
        return module.main(argv)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_cli_batch_creates_accounts_and_a_handout(client, tmp_path, capsys):
    listing = tmp_path / "students.txt"
    listing.write_text("41047001\n41047002\n", encoding="utf-8")
    handout = tmp_path / "handout.csv"

    assert _run_cli(["--out", str(handout), "batch", str(listing)]) == 0

    assert {s.student_no for s in _students(client)} == {"41047001", "41047002"}

    text = handout.read_text(encoding="utf-8")
    assert "student_no,initial_password" in text
    rows = dict(
        line.split(",")
        for line in text.splitlines()
        if line and not line.startswith("#") and not line.startswith("student_no")
    )
    assert set(rows) == {"41047001", "41047002"}
    # 對照表裡的密碼真的能登入——這才是這份檔案的用途
    assert log_in(client, "41047001", rows["41047001"]).status_code == 303


def test_handout_warns_that_it_contains_plaintext(client, tmp_path):
    listing = tmp_path / "students.txt"
    listing.write_text("41047001\n", encoding="utf-8")
    handout = tmp_path / "handout.csv"
    _run_cli(["--out", str(handout), "batch", str(listing)])

    text = handout.read_text(encoding="utf-8")
    assert "明碼密碼" in text
    assert "刪除" in text


def test_handout_is_not_world_readable(client, tmp_path):
    """對照表權限收緊為 0600。它是系統裡唯一一處明碼落地的地方。"""
    listing = tmp_path / "students.txt"
    listing.write_text("41047001\n", encoding="utf-8")
    handout = tmp_path / "handout.csv"
    _run_cli(["--out", str(handout), "batch", str(listing)])

    mode = stat.S_IMODE(handout.stat().st_mode)
    assert mode & (stat.S_IRGRP | stat.S_IROTH) == 0, f"權限是 {oct(mode)}"


def test_default_handout_filename_shouts_delete_me():
    """檔名本身就要喊出來——不能依賴有人打開檔案看檔頭。"""
    from importlib import import_module

    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        name = import_module("create_accounts").default_handout_path().name
    finally:
        sys.path.remove(str(SCRIPTS_DIR))

    assert "PLAINTEXT" in name and "DELETE-ME" in name


def test_cli_rerun_skips_and_leaves_them_out_of_the_handout(client, tmp_path):
    """重跑時已存在的帳號不出現在對照表裡——資料庫撈不回舊密碼。"""
    listing = tmp_path / "students.txt"
    listing.write_text("41047001\n", encoding="utf-8")
    first = tmp_path / "first.csv"
    _run_cli(["--out", str(first), "batch", str(listing)])
    hash_before = _students(client)[0].password_hash

    listing.write_text("41047001\n41047002\n", encoding="utf-8")
    second = tmp_path / "second.csv"
    _run_cli(["--out", str(second), "batch", str(listing)])

    assert _students(client)[0].password_hash == hash_before
    body = second.read_text(encoding="utf-8")
    assert "41047002" in body
    assert "41047001" not in body


def test_cli_reset_existing_flag_does_replace(client, tmp_path):
    listing = tmp_path / "students.txt"
    listing.write_text("41047001\n", encoding="utf-8")
    _run_cli(["--out", str(tmp_path / "a.csv"), "batch", str(listing)])
    hash_before = _students(client)[0].password_hash

    _run_cli([
        "--out", str(tmp_path / "b.csv"),
        "batch", str(listing), "--reset-existing",
    ])
    assert _students(client)[0].password_hash != hash_before


def test_cli_dry_run_writes_nothing(client, tmp_path):
    listing = tmp_path / "students.txt"
    listing.write_text("41047001\n", encoding="utf-8")
    handout = tmp_path / "handout.csv"

    assert _run_cli(["--out", str(handout), "batch", str(listing), "--dry-run"]) == 0
    assert _students(client) == []
    assert not handout.exists()


def test_cli_add_and_reset_single_account(client, tmp_path):
    added = tmp_path / "added.csv"
    assert _run_cli(["--out", str(added), "add", "41047001"]) == 0
    assert len(_students(client)) == 1

    reset = tmp_path / "reset.csv"
    assert _run_cli(["--out", str(reset), "reset", "41047001"]) == 0
    pw = reset.read_text(encoding="utf-8").splitlines()[-1].split(",")[1]
    assert log_in(client, "41047001", pw).status_code == 303


def test_cli_reset_refuses_an_unknown_student(client, tmp_path, capsys):
    """重設一個不存在的帳號幾乎一定是打錯字。

    預設幫他建立會讓那個錯字變成一個沒有人用得到的幽靈帳號，而老師會以為
    密碼已經發出去了。所以回非 0 並說明（規則 4：不靜默）。
    """
    assert _run_cli(["reset", "41047099"]) == 1
    assert _students(client) == []
    assert "沒有這個帳號" in capsys.readouterr().err


def test_cli_list_never_prints_a_password(client, tmp_path, capsys):
    _run_cli(["--out", str(tmp_path / "a.csv"), "add", "41047001"])
    plaintext = (tmp_path / "a.csv").read_text(encoding="utf-8").splitlines()[-1]
    password = plaintext.split(",")[1]
    capsys.readouterr()

    assert _run_cli(["list"]) == 0
    out = capsys.readouterr().out
    assert "41047001" in out
    assert "尚未登入" in out
    assert "尚未確認" in out          # consent_at 還是 None
    assert password not in out
