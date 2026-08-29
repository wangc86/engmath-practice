"""`TURNAROUND.csv` 的看守測試。

**這個檔案存在的理由**：老師要知道 PLAN §6 估的 17.8 人週，實際請 AI 執行
要花多久牆鐘時間。那個問題只能靠一列一列累積回答，而一份**漏了幾列、
或某一列的數字沒跟上**的紀錄，答出來的比值是錯的——而且錯得看不出來
（它仍然是一個合理的數字）。

本專案的慣例是「會被忘記的流程等於沒有流程」，所以這裡不靠紀律，靠三層
（完整說明在 `scripts/turnaround.py` 的檔頭）：`CLAUDE.md` 的一條慣例、
`scripts/git-safe-commit.sh` 的提醒、以及這個檔案。

⛔ **這裡最重要的是最後一項** `test_the_last_row_knows_how_many_tests_there_are`：
它把紀錄綁在一個**程式量得到的事實**上。任何一次加了測試卻沒有更新紀錄的
變更都會讓它變紅——那是這三層裡唯一不依賴任何人記得的一層。

⚠️ 誠實的空白：它守得住「紀錄有沒有跟上」，**守不住「有沒有開一列」**。
一個完全沒有動到測試的任務（例如純文件的那幾輪）不會觸發它。
這個縫隙補不起來，寫在這裡而不是假裝已經解決。
"""

from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "TURNAROUND.csv"
SCRIPT_PATH = ROOT / "scripts" / "turnaround.py"


def _load_script():
    """把 `scripts/turnaround.py` 當模組載進來。

    ⚠️ 一致性檢查的邏輯**只寫一份**，住在那支腳本裡；這裡直接用它。
    在測試裡重寫一份檢查，就會有一天兩份對不上，而那時候沒有人知道
    該相信哪一份。
    """
    spec = importlib.util.spec_from_file_location("turnaround", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows() -> list[dict]:
    assert CSV_PATH.exists(), (
        f"找不到 {CSV_PATH.name}。它是版本控制裡的資產，不見了就是有人刪錯東西。"
    )
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_columns_are_exactly_the_agreed_ones():
    """欄位是這份紀錄的介面，所以它被釘住。

    多一欄少一欄不會讓任何東西壞掉——`report` 照樣印得出來、CSV 照樣讀得開，
    只是某一輪的資料悄悄少了一格。這與規則 3 對 `UsageLog` 的處理是同一件事：
    **欄位的變動必須是一個決定，不能是一次順手**。
    """
    module = _load_script()
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == module.FIELDS


def test_every_row_is_internally_consistent():
    """起訖時間、經過時數、精確度標記、各項計數。

    邏輯在 `scripts/turnaround.py` 的 `check_rows()` 裡，這裡只是把它接上
    `pytest`——理由與 §8.4 選「pytest 驅動 node」相同：
    **pytest 要繼續是唯一的測試入口**。
    """
    module = _load_script()
    problems = module.check_rows(rows())
    assert not problems, "TURNAROUND.csv 有問題：\n" + "\n".join(f"  - {p}" for p in problems)


def test_estimated_start_times_say_what_they_are_based_on():
    """⛔ 開始時間是估計值的列，備註必須寫出依據。

    這一條與 `check_rows()` 裡的那一項重複，是刻意的——它值得一個自己的
    名字，因為**它守的是這份紀錄唯一會說謊的地方**。一個標著
    `measured` 卻其實是猜的開始時間，會讓整份統計看起來比實際可信。
    """
    for row in rows():
        if row["start_accuracy"] == "estimated":
            note = row["note"].strip()
            assert note, f"{row['task']} 的開始時間是估計值，卻沒有說明依據"
            assert len(note) > 20, (
                f"{row['task']} 的備註太短，說不清楚估計的依據：{note!r}"
            )


def test_the_rows_are_in_chronological_order():
    """時間順序。亂序不會讓任何計算變錯，但它會讓人讀不出「越做越快嗎」——
    而那正是老師會問的第二個問題。"""
    starts = [row["start"] for row in rows()]
    assert starts == sorted(starts), "TURNAROUND.csv 的列沒有按開始時間排序"


def test_the_last_row_knows_how_many_tests_there_are():
    """⛔ **這一項是整個機制裡唯一不依賴任何人記得的一層。**

    最後一列的 `tests_after` 必須等於 `pytest` 實際收集到的項數。
    也就是說：**任何一次加了測試卻沒有更新紀錄的變更，都會讓這一項變紅**，
    而紅燈裡就寫著該做什麼。

    ⚠️ 用「收集」而不是「執行」：收集只 import 測試模組、不跑任何測試，
    因此它不需要 node，數字也不會隨機器上有沒有 node 而變動
    （缺 node 時執行結果會有一堆 skip，但收集到的項數是一樣的）。

    ⚠️ 這一項不會遞迴：`--collect-only` 只 import 這個模組，不會執行
    這個函式。
    """
    module = _load_script()
    try:
        collected = module.collected_test_count()
    except (subprocess.TimeoutExpired, RuntimeError) as err:
        # 規則 4：不做無聲降級。收集不起來是一個真的問題，不是「跳過」。
        pytest.fail(f"無法數出測試項數，因此無法驗證 TURNAROUND.csv：{err}")
    last = rows()[-1]
    assert int(last["tests_after"]) == collected, (
        f"TURNAROUND.csv 最後一列（{last['task']}）記的是 "
        f"{last['tests_after']} 項，但實際收集到 {collected} 項。"
        "動過測試就要更新那一列——指令見 scripts/turnaround.py 的檔頭。"
    )


def test_the_script_can_print_a_report():
    """`report` 跑得起來。

    它是老師唯一會用到的那個指令，而一支印報表的腳本壞掉是很安靜的——
    沒有人每天跑它，所以要有東西替他跑一次。
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "report"],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "total" in result.stdout
    assert "人週" in result.stdout
