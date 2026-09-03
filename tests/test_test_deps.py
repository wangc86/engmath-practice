"""依相依性挑測試的那份地圖，還對不對得起來（D65）。

⛔ **這一份守的是一個會安靜出錯的東西。** `scripts/test_deps.py` 的作用是
**少跑一些測試**，所以它壞掉的症狀不是「紅燈」，是**「綠燈，但那個綠燈
只涵蓋了一半」**——而那正是規則 4 講的靜默失敗，只是換到了測試這一層。

具體會出錯的四種方式，下面各有一項盯著：

1. 新增一個測試檔而沒有量測它 → 它永遠不會被挑到。
2. 搬檔案或改名（v0.31 的 2a0 就搬了四個）→ 地圖裡的路徑指不到東西，
   而改到那個檔案時 `select` 會說「地圖不認得」→ 全跑（安全），
   但地圖本身已經是壞的，下一次量測前都不準。
3. 分批量測漏掉一批 → 那一批裡的測試碰過的檔案整個從地圖上消失。
4. `NO_TEST_COVERS` 過期 → `select` 對一個其實有測試守著的檔案說「不必跑」。

⚠️ **這一份不驗「地圖是最新的」**，那件事沒有辦法便宜地驗——要驗就得把
全套測試再跑一遍，而那正是這整套機制要避免的事。什麼時候該重量，
寫在 `CLAUDE.md`「只跑相關的測試」那一節。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "test_deps.py"


def _module():
    spec = importlib.util.spec_from_file_location("_test_deps", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


td = _module()


def test_every_test_file_is_in_the_map_and_every_path_still_exists():
    """上面第 1 與第 2 種出錯方式。

    兩者放在同一項是因為它們的修法是同一個（重量），而分開只會讓
    「該跑哪一行指令」的訊息重複兩次。
    """
    problems = td.check()
    assert not problems, "\n".join(problems)


def test_each_batched_measurement_covered_every_test_in_its_file():
    """上面第 3 種：各批相加必須等於那個檔案現在的項數。

    ⛔ `test_generators.py` 是照 16 個 `template_id` 加上兩個互斥的兜底批
    量的，那 18 批**互斥且窮盡**——所以「相加 = 540」不只是必要條件，
    它就是覆蓋的證明。
    """
    problems = td.coverage_problems()
    assert not problems, "\n".join(problems)


def test_the_no_test_covers_list_has_not_gone_stale():
    """上面第 4 種，而它是四種裡最危險的。

    ⚠️ 「有人替 `preview.py` 寫了測試」與「`preview.py` 被改名了」
    兩件事都會讓那份清單說謊，而**說謊的方向是少跑測試**。
    """
    problems = td.stale_allowlist()
    assert not problems, "\n".join(problems)


def test_an_unknown_source_path_forces_a_full_run():
    """⛔ 守的是**失敗的方向**。

    地圖不認得的原始碼路徑（多半是還沒有被任何測試碰過的新檔案）必須
    回答「全跑」。若它改成「不必跑」，一個新寫的 generator 忘了註冊
    就會**在全綠的情況下**溜過去。
    """
    result = td.select(["app/generator/ode/a_brand_new_topic.py"])
    assert result["full"], result


def test_documentation_only_changes_select_nothing():
    """反過來的方向：只改文件不必跑任何測試。

    這一項與上一項是一對——**沒有它，「全部都全跑」也會通過上一項**，
    而那樣的話整套機制一點時間都省不下來。
    """
    result = td.select(["PLAN.md", "README.md", "dispatches/x.md"])
    assert not result["full"]
    assert result["tests"] == {}


def test_changing_how_the_tests_run_always_forces_a_full_run():
    """`requirements.txt`／`pytest.ini`／`conftest.py` 一動就全跑。

    判準是「它改變的是測試怎麼跑，而不是被測的是什麼」——地圖對這種
    改動完全沒有意見（相依一條都沒有變），而每一項的結果都可能變。
    """
    for path in ("requirements.txt", "pytest.ini", "tests/conftest.py"):
        assert td.select([path])["full"], path


@pytest.mark.parametrize("template_id", ["ode.first_order.separable", "fourier.series.full_range"])
def test_the_k_narrowing_keeps_every_test_that_names_no_template(template_id):
    """⛔ 窄化的正確性：**id 裡沒有提到任何題型的每一項都必須留下**。

    這是 `-k` 那條運算式唯一需要證明的事。一項專門針對某個題型、
    但名字裡沒有寫出 `template_id` 的測試（例如
    `test_the_resonance_multiplicity_is_what_the_difficulty_promises`）
    會落在後面那一半——**窄化的誤差方向必須是多跑，不是少跑。**

    ⚠️ 用 `--collect-only` 真的問 pytest，而不是自己剖那個運算式：
    自己剖等於把 `-k` 的語意再實作一次，然後兩份實作會分岔。
    """
    tmods = td.template_modules()
    all_ids = sorted({t for v in tmods.values() for t in v.split("|")})
    narrow = "%s or not (%s)" % (template_id, " or ".join(all_ids))

    def ids(extra):
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_generators.py",
             "--collect-only", "-q", *extra],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        return {l for l in r.stdout.splitlines() if l.startswith("tests/")}

    everything = ids([])
    kept = ids(["-k", narrow])
    nameless = {i for i in everything if not any(t in i for t in all_ids)}
    mine = {i for i in everything if template_id in i}

    assert nameless, "沒有任何一項的 id 不提到題型——那條運算式就沒有意義了"
    assert nameless <= kept, sorted(nameless - kept)[:5]
    assert mine <= kept, sorted(mine - kept)[:5]
