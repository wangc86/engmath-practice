#!/usr/bin/env python3
"""依相依性挑測試：改了什麼，就只跑碰得到它的那些測試（D65）。

    python scripts/test_deps.py measure tests/test_web.py   # 量一個測試檔
    python scripts/test_deps.py select                      # 依目前未提交的變更挑
    python scripts/test_deps.py select --base HEAD~3        # 依與某個 commit 的差異挑
    python scripts/test_deps.py select -- app/generator/ode/separable.py
    python scripts/test_deps.py check                       # 地圖與現況還對不對得起來

---

## 這支腳本回答的問題

全套測試 **10–12 分鐘**，而一輪工作常常只動一兩個檔案。老師要的是：
**在已經跑過一遍全部的前提下，只跑與這次改動相關的那些。**

⛔ **它回答的不是「哪些測試會失敗」——那件事沒有辦法在跑之前知道。**
它回答的是一個保守得多的問題：**哪些測試在執行時碰過這次改動的檔案。**
碰不到的那些**不可能**因為這次改動而變色（除非它們依賴的是「不在檔案系統上」
的東西，見下面「這件事守不住的三個縫」）。

## 為什麼是量出來的，不是寫死的

一份手寫的「改 X 要跑 Y」對照表會在第一次搬檔案時安靜過期——而 v0.31 的
2a0 剛好就搬了四個檔案。所以這裡的地圖是**實跑量出來的**：把測試真的跑一遍，
記下它 import 了哪些模組、`open()` 了哪些檔案、`subprocess` 傳了哪些路徑。

⚠️ **量測本身要花一次全套測試的時間**，所以它不是每次都做的事。
什麼時候要重量，見 `CLAUDE.md`「只跑相關的測試」那一節。

## 這件事守不住的三個縫（⚠️ 不要假裝沒有）

1. **測試可能依賴一個它從來沒有讀過的檔案。** 例如一項斷言「路由表恰好有
   這幾條」的測試，改了 `app/main.py` 它會紅，而它確實 import 得到 main
   ——這個縫在實務上很窄，因為 Python 的相依幾乎都會經過 import 或 open。
   但**它不是零**，所以 `select` 的預設一律偏向多跑。
2. **新檔案還沒有被任何測試碰過。** 一個新寫的 generator 如果忘了加進
   `app/generator/__init__.py`，沒有任何測試會碰到它——而那正是它出錯的方式。
   所以 `select` 對「`app/`、`scripts/`、`tests/` 底下、但不在地圖裡的路徑」
   一律回答**全跑**（`tests/test_test_deps.py` 有一項守著這個方向）。
3. **環境變了。** 換一台機器、換 Python 或 SymPy 版本、動了
   `requirements.txt`——那時候地圖是對的而環境不是。
   ⛔ **這種時候一定要全跑**，見下面 `ALWAYS_FULL`。

## 為什麼 `-k` 的窄化是安全的

出題引擎那兩個檔案（`test_generators.py`、`test_web.py`）的參數化測試，
**測試 id 裡帶著完整的 `template_id`**（例如
`test_the_gate_passes_for_every_generated_problem[ode.first_order.separable-1]`）。
所以可以寫成：

    -k "<改到的 template_id> or not (<全部 16 個 template_id>)"

也就是**「這次改到的題型」加上「id 裡沒有提到任何題型的每一項」**。
一項專門針對某個題型、但名字裡沒有寫出 `template_id` 的測試
（例如 `test_the_resonance_multiplicity_is_what_the_difficulty_promises`）
會落在後面那一半，**照樣會跑**——窄化的誤差方向是多跑，不是少跑。

⛔ **只有在「改到的全部是題型模組」時才窄化。** `base.py`、`pretty.py`、
`plot.py`、`fourier/core.py` 這些沒有註冊任何題型的共用檔案一旦被改到，
窄化立刻關掉（哪些算共用是**從註冊表推出來的**，不是寫死的清單）。
"""

from __future__ import annotations

import argparse
import builtins
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "tests" / "data" / "test_deps.json"

#: 這些路徑一動，地圖說什麼都不算數——一律全跑。
#: ⚠️ 判準是「它改變的是測試怎麼跑，而不是被測的是什麼」。
ALWAYS_FULL = (
    "requirements.txt",
    "pytest.ini",
    "tests/conftest.py",
    "scripts/test_deps.py",
    "tests/data/test_deps.json",
)

#: 這些前綴底下的檔案**不可能**讓任何測試變色，改了它們不必跑任何測試。
#: ⚠️ 這是一份白名單而不是黑名單：不在這裡、又不在地圖裡的東西一律全跑。
#: `LICENSE` **刻意不在這裡**（`test_web.py` 真的會讀它），
#: `TURNAROUND.csv` 也不在（`test_turnaround.py` 讀它）。
INERT_PREFIXES = (
    "dispatches/",
    ".attic/",
    ".gitignore",
    "PLAN.md",
    "README.md",
    "CLAUDE.md",
    "COLLABORATION-NOTES.md",
    "VERIFY-CHECKLIST.md",
    "PUBLISHING.md",
    "INSTALL-LINUX.md",
    "INSTALL-MACOS.md",
)

#: 「原始碼」的範圍：這些前綴底下出現地圖不認得的路徑，就是全跑。
SOURCE_PREFIXES = ("app/", "scripts/", "tests/")

#: **沒有任何自動測試碰得到它們**，而那是已知的、不是遺漏。
#: 改這些檔案不必跑測試——但也代表**沒有任何東西會告訴你改壞了**。
#: ⚠️ 這份清單會自我修正：`tests/test_test_deps.py` 有一項要求每一條
#: **仍然不在地圖裡**，所以哪一天有人替 `preview.py` 寫了測試，
#: 那一項就會變紅，逼人回來把它從這裡拿掉。
NO_TEST_COVERS = {
    "scripts/preview.py": "人工審題工具（§2.8）。改它要自己看輸出。",
    "scripts/review_steps.py": "2c 的機器初篩（§A6）。它的產出是給人讀的排序，不是斷言。",
    "scripts/dsp_reference.py": "產 golden vector 的工具；它產出的 JSON 有測試，它自己沒有。",
    "scripts/make_demo_samples.py": "產內建範例音檔的工具（需要 eSpeak NG，沙箱跑不動）。",
    "scripts/git-safe-commit.sh": "提交途徑。它壞掉的方式是提交失敗，當場就看得見。",
    "scripts/package.sh": "匯出 zip。驗收方式是解開來跑一次，不是單元測試。",
    "scripts/package-readme.md": "上面那支腳本塞進 zip 裡的說明文字。",
}


# --------------------------------------------------------------------------
# 量測
# --------------------------------------------------------------------------

class _Recorder:
    """記下一次測試執行碰過專案裡的哪些檔案。

    三條管道，缺一不可：

    * ``import``——大部分的相依走這裡（跑完之後掃 ``sys.modules``）。
    * ``open()``／``Path.read_text()``——範本、靜態資產、`rglob` 掃出來的
      每一個檔案都走這裡。**這條是 `test_web.py` 那種「掃整個 app/」的測試
      唯一會留下痕跡的地方。**
    * ``subprocess``——`test_dsp_js.py` 與 `test_demos.py` 用 node 跑 JS，
      那些 ``.mjs`` 與它們讀的資產在本行程裡完全看不到，只能從 argv 撈。
      ⚠️ **node 自己再去開的檔案撈不到**，所以 `.mjs` 的相依由它的 argv
      加上「整個 `app/static/demos/`」概括——寧可多算。
    """

    def __init__(self) -> None:
        self.paths: set[str] = set()
        #: 這次執行有沒有另外開一個行程去跑 pytest。
        #: `test_turnaround.py` 會（它數整份測試有幾項），而那讓它相依於
        #: **每一個測試檔**——那件事在檔案系統上完全看不見，argv 裡只有
        #: `-m pytest --collect-only`，一個路徑都沒有。
        self.runs_pytest = False

    def note(self, raw: object) -> None:
        if isinstance(raw, int):          # open(fd)
            return
        try:
            text = os.fsdecode(raw)
        except Exception:
            return
        # ⚠️ `subprocess` 的 argv 裡什麼都有。`node -e <一整段 JS>` 會丟進來一個
        # 幾百字、含換行的字串，而把它當路徑去 `stat()` 會拋 ENAMETOOLONG
        # ——**而那個例外會從測試裡冒出來，讓一項本來會過的測試變紅**
        # （這是實際發生過的：`test_every_formula_renders_in_the_bundled_katex`）。
        # 所以在這裡就擋掉明顯不是路徑的東西，不要靠下面的 try 兜。
        if "\n" in text or len(text) > 400:
            return
        try:
            p = Path(text)
        except Exception:
            return
        try:
            rel = p.resolve().relative_to(ROOT)
        except Exception:
            return
        s = rel.as_posix()
        if s.startswith((".venv/", ".git/", ".attic/")) or "__pycache__" in s:
            return
        if s.endswith(".pyc") or s == "scripts/test_deps.py":
            # ⚠️ 排除量測工具自己：它出現在每一列裡只是因為它是正在跑的那支程式，
            # 不是被測的東西。（它一動就全跑，那件事由 `ALWAYS_FULL` 管。）
            return
        # ⚠️ 只記真的存在的檔案。這一行同時擋掉 subprocess argv 裡的旗標與
        # `-`（`run_dsp_case.mjs` 用 `-` 代表「從 stdin 讀」，而 `-` 會被
        # 解成一個相對路徑），以及測試自己寫出來的暫存檔。
        try:
            if not (ROOT / s).is_file():
                return
        except OSError:
            # 路徑太長、或有 NUL 之類的字元——那就不是這個 repo 裡的檔案。
            return
        self.paths.add(s)


def _install_hooks(rec: _Recorder):
    real_open = builtins.open
    real_p_open = Path.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_run = subprocess.run
    real_popen = subprocess.Popen.__init__

    def open_(file, *a, **kw):
        rec.note(file)
        return real_open(file, *a, **kw)

    def p_open(self, *a, **kw):
        rec.note(self)
        return real_p_open(self, *a, **kw)

    def p_read_text(self, *a, **kw):
        rec.note(self)
        return real_read_text(self, *a, **kw)

    def p_read_bytes(self, *a, **kw):
        rec.note(self)
        return real_read_bytes(self, *a, **kw)

    def _note_argv(args):
        seq = args if isinstance(args, (list, tuple)) else [args]
        for item in seq:
            if isinstance(item, (str, bytes, os.PathLike)):
                rec.note(item)
                try:
                    if os.fsdecode(item) == "pytest":
                        rec.runs_pytest = True
                except Exception:
                    pass

    def _note_env(kw):
        # ⚠️ 路徑不一定在 argv 裡。`test_generators.py` 用
        # `env={"KATEX_PATH": str(_KATEX)}` 把自架的 KaTeX 交給 node，
        # 而那條路徑在 argv 裡一個字都沒有——**只掃 argv 會漏掉它，
        # 而漏掉的症狀是「升級 KaTeX 之後選不到那項渲染測試」。**
        env = kw.get("env")
        if isinstance(env, dict):
            for v in env.values():
                if isinstance(v, (str, bytes, os.PathLike)):
                    rec.note(v)

    def run_(args, *a, **kw):
        _note_argv(args)
        _note_env(kw)
        return real_run(args, *a, **kw)

    def popen_(self, args, *a, **kw):
        _note_argv(args)
        _note_env(kw)
        return real_popen(self, args, *a, **kw)

    builtins.open = open_
    Path.open = p_open
    Path.read_text = p_read_text
    Path.read_bytes = p_read_bytes
    subprocess.run = run_
    subprocess.Popen.__init__ = popen_

    def restore():
        builtins.open = real_open
        Path.open = real_p_open
        Path.read_text = real_read_text
        Path.read_bytes = real_read_bytes
        subprocess.run = real_run
        subprocess.Popen.__init__ = real_popen

    return restore


#: node 跑的那些 `.mjs` 在本行程裡看不到自己開了什麼檔，所以只要相依裡出現
#: 任何一支 `scripts/*.mjs`，就把它們吃得到的兩棵樹整個算進去。
#: ⚠️ **這是刻意粗的一種概括**：寧可把整個 `app/static/demos/` 算成相依
#: （代價是改一支展示的 JS 會多跑 `test_dsp_js.py`），也不要漏掉一個
#: `readFileSync(join(here, '..', 'app', 'static', 'demos', 'worklets', file))`
#: 這種**靜態讀不出來**的路徑。用「整棵樹」而不是「一份檔案清單」也是刻意的
#: ——清單會在有人加一支新的 JS 時安靜過期，樹不會。
_MJS_WIDENS_TO = ("app/static/demos/", "app/static/vendor/fftjs/")


def _widen(paths: set[str], runs_pytest: bool = False) -> set[str]:
    out = set(paths)
    if any(p.startswith("scripts/") and p.endswith(".mjs") for p in out):
        for prefix in _MJS_WIDENS_TO:
            base = ROOT / prefix
            if base.is_dir():
                for f in base.rglob("*"):
                    if f.is_file():
                        out.add(f.relative_to(ROOT).as_posix())
    if runs_pytest:
        # 另開行程跑 pytest ⇒ 相依於整個 tests/ 目錄。
        for f in (ROOT / "tests").glob("test_*.py"):
            out.add(f.relative_to(ROOT).as_posix())
        out.add("tests/conftest.py")
        out.add("pytest.ini")
    return out


def measure(test_file: str, k: str | None = None, merge: bool = False,
            bootstrap: bool = False) -> int:
    """跑一次測試並記下它碰過的檔案。

    ⚠️ **`--k` 與 `--merge` 是為了沙箱的單次指令上限存在的**（約 180 秒，而
    `test_generators.py` 要 10 分鐘）：分批跑、每批把相依**聯集**進去，
    結果與一次跑完相同——因為聯集不在乎順序，而每一項都跑到了。
    ⛔ **但那要求各批加起來真的涵蓋每一項。** 所以分批量測的檔案會在地圖裡
    記下 `batches` 與 `collected`，而 `collected` 必須等於該檔案的總項數；
    `tests/test_test_deps.py` 有一項盯著這件事。
    """
    import pytest  # 只有量測用得到，放在函式裡

    rel = Path(test_file).resolve().relative_to(ROOT).as_posix()
    rec = _Recorder()
    restore = _install_hooks(rec)
    argv = [str(ROOT / rel), "-q", "-p", "no:cacheprovider"]
    if k:
        argv += ["-k", k]
    started = time.monotonic()
    try:
        code = pytest.main(argv)
    finally:
        restore()
    seconds = round(time.monotonic() - started, 1)

    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if f:
            rec.note(f)
    rec.paths = _widen(rec.paths, rec.runs_pytest)

    if int(code) != 0 and not bootstrap:
        print(f"⛔ {rel} 沒有全綠（pytest exit {int(code)}），不寫入地圖。", file=sys.stderr)
        return int(code)
    if int(code) != 0:
        # ⚠️ `--bootstrap` 存在的唯一理由是一個真的自我指涉：
        # `tests/test_test_deps.py` 會檢查「地圖涵蓋了每一個測試檔的每一項」，
        # 所以在它自己被量進地圖之前，它**必然**是紅的——而 `measure` 又
        # 只肯寫綠的。這一個旗標打破那個環，然後**要再跑一次不帶旗標的**，
        # 那一次才是真的驗收。
        print(f"⚠️ {rel} 是紅的，但 --bootstrap 要求照寫。"
              "寫完之後請再跑一次不帶 --bootstrap 的 measure。", file=sys.stderr)

    ran = _collected(rel, k)
    data = _load_map()
    entry = data.setdefault("files", {}).get(rel)
    if entry is None or not merge:
        entry = {"batches": {}}
        data["files"][rel] = entry
    # ⚠️ **以 `-k` 運算式當鍵**，所以重跑同一批是覆寫而不是累加。
    # 累加的版本會讓「各批相加 = 總項數」這個檢查在重量一批之後安靜地失真。
    entry["batches"][k or ""] = {
        "collected": ran,
        "seconds": seconds,
        "deps": sorted(rec.paths),
    }
    data["measured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _save_map(data)
    print(f"{rel}: 相依 {len(deps_of(entry))} 條、"
          f"合計 {collected_of(entry)} 項 / {len(entry['batches'])} 批、"
          f"{seconds_of(entry)}s")
    return 0


def deps_of(entry: dict) -> list[str]:
    out: set[str] = set()
    for b in entry["batches"].values():
        out.update(b["deps"])
    return sorted(out)


def collected_of(entry: dict) -> int:
    return sum(b["collected"] for b in entry["batches"].values())


def seconds_of(entry: dict) -> float:
    return round(sum(b["seconds"] for b in entry["batches"].values()), 1)


def _collected(rel: str, k: str | None) -> int:
    """這一批實際跑了幾項（用另一個行程數，避免污染本行程的 sys.modules）。"""
    argv = [sys.executable, "-m", "pytest", rel, "--collect-only", "-q"]
    if k:
        argv += ["-k", k]
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    for line in reversed(r.stdout.splitlines()):
        if "collected" in line:
            for tok in line.replace("/", " ").split():
                if tok.isdigit():
                    return int(tok)
    return 0


def _load_map() -> dict:
    if MAP_PATH.exists():
        return json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return {"files": {}}


def _save_map(data: dict) -> None:
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(
        json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# 選擇
# --------------------------------------------------------------------------

def template_modules() -> dict[str, str]:
    """``app/generator/...`` 的相對路徑 → 它註冊的 template_id（以 ``|`` 分隔）。

    ⚠️ **從註冊表推出來而不是寫死**——寫死的話 v0.31 那種搬檔案會讓它安靜過期。
    """
    sys.path.insert(0, str(ROOT))
    from app.generator.base import REGISTRY  # noqa: E402
    import app.generator  # noqa: F401,E402

    out: dict[str, list[str]] = {}
    for tid, tpl in REGISTRY.items():
        mod = sys.modules[tpl.fn.__module__]
        rel = Path(mod.__file__).resolve().relative_to(ROOT).as_posix()
        out.setdefault(rel, []).append(tid)
    return {k: "|".join(sorted(v)) for k, v in out.items()}


def changed_paths(base: str | None) -> list[str]:
    def git(*args: str) -> list[str]:
        r = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} 失敗：{r.stderr.strip()}")
        return [l for l in r.stdout.splitlines() if l.strip()]

    if base:
        paths = git("diff", "--name-only", base)
    else:
        paths = git("diff", "--name-only", "HEAD")
    paths += git("ls-files", "--others", "--exclude-standard")
    return sorted(set(paths))


def select(paths: list[str]) -> dict:
    data = _load_map()
    files = data.get("files", {})
    if not files:
        return {"full": True, "why": "地圖是空的（沒有量測過）", "tests": None}

    deps = {t: set(deps_of(info)) for t, info in files.items()}

    reasons: list[str] = []
    for p in paths:
        if p in ALWAYS_FULL:
            return {"full": True, "why": f"{p} 一動就全跑（它改變的是測試怎麼跑）", "tests": None}

    selected: dict[str, list[str]] = {}
    unexplained: list[str] = []
    for p in paths:
        if p.startswith(INERT_PREFIXES):
            continue
        hit = [t for t in files if p in deps[t]]
        if hit:
            for t in hit:
                selected.setdefault(t, []).append(p)
        elif p in NO_TEST_COVERS:
            reasons.append(f"（{p}：{NO_TEST_COVERS[p]}）")
        elif p.startswith(SOURCE_PREFIXES):
            unexplained.append(p)
        else:
            reasons.append(f"（{p} 不在地圖裡，也不在原始碼範圍內——忽略）")

    if unexplained:
        return {
            "full": True,
            "why": "地圖不認得這些原始碼路徑（多半是新檔案）：" + "、".join(unexplained),
            "tests": None,
        }

    # -k 窄化：只有在「改到的全部是題型模組」時才做。
    tmods = template_modules()
    gen_changed = [p for p in paths if p.startswith("app/generator/") and p.endswith(".py")]
    narrow = None
    touched: list[str] = []
    if gen_changed and all(p in tmods for p in gen_changed):
        touched[:] = sorted({t for p in gen_changed for t in tmods[p].split("|")})
        all_ids = sorted({t for v in tmods.values() for t in v.split("|")})
        narrow = "%s or not (%s)" % (" or ".join(touched), " or ".join(all_ids))

    out = {
        "full": False,
        "tests": {t: sorted(set(v)) for t, v in sorted(selected.items())},
        "narrow": narrow,
        "notes": reasons,
        "seconds": round(sum(seconds_of(files[t]) for t in selected), 1),
        "total_seconds": round(sum(seconds_of(i) for i in files.values()), 1),
    }
    if narrow:
        out["narrow_seconds"] = _narrow_seconds(files, selected, touched)
    return out


def _narrow_seconds(files: dict, selected: dict, touched: list[str]) -> float:
    """窄化之後大概要跑多久。

    `test_generators.py` 是**照 template 分批量的**，所以這個數字是把
    「改到的那幾批」加上「兩個兜底批」的秒數相加——**量出來的，不是推的**。
    其餘檔案沒有分批資料，只能按項數比例粗估，那一半是推的。
    ⚠️ 兩者混在同一個數字裡，所以它只拿來看數量級。
    """
    total = 0.0
    for t in selected:
        entry = files[t]
        batches = entry["batches"]
        if len(batches) > 1:
            for key, b in batches.items():
                if key in touched or key.startswith("not ("):
                    total += b["seconds"]
        elif t in ("tests/test_generators.py", "tests/test_web.py"):
            total += seconds_of(entry) * 0.4   # 粗估：窄化大約留下四成
        else:
            total += seconds_of(entry)
    return round(total, 1)


def print_selection(result: dict) -> None:
    if result["full"]:
        print("⛔ 全跑：" + result["why"])
        print()
        print("    pytest -q        # 沙箱裡要分批，切法見 CLAUDE.md")
        return
    if not result["tests"]:
        print("這次的變更碰不到任何測試（只有文件）。不必跑測試。")
        for n in result.get("notes", []):
            print("   " + n)
        return

    narrowable = {"tests/test_generators.py", "tests/test_web.py"}
    print("要跑的測試：")
    for t, why in result["tests"].items():
        print(f"  {t}  ← {'、'.join(why)}")
    print()
    if result.get("narrow") and narrowable & set(result["tests"]):
        wide = [t for t in result["tests"] if t not in narrowable]
        thin = [t for t in result["tests"] if t in narrowable]
        if wide:
            print("    pytest -q " + " ".join(wide))
        print('    pytest -q %s -k "%s"' % (" ".join(thin), result["narrow"]))
    else:
        print("    pytest -q " + " ".join(result["tests"]))
    print()
    if result.get("narrow_seconds") is not None:
        print(f"約 {result['narrow_seconds']}s（選到的檔案不窄化是 {result['seconds']}s，"
              f"全套是 {result['total_seconds']}s）")
    else:
        print(f"約 {result['seconds']}s（全套是 {result['total_seconds']}s）")
    print("⚠️ 這些是量測當時的秒數，只拿來看數量級。")
    for n in result.get("notes", []):
        print("   " + n)


# --------------------------------------------------------------------------
# check（`tests/test_test_deps.py` 用它，也可以自己跑）
# --------------------------------------------------------------------------

def check() -> list[str]:
    """回傳問題清單；空的表示地圖與現況對得起來。"""
    problems: list[str] = []
    data = _load_map()
    files = data.get("files", {})
    if not files:
        return ["地圖是空的：跑 python scripts/test_deps.py measure tests/<檔案>.py"]

    on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py")}
    missing = on_disk - set(files)
    if missing:
        problems.append("這些測試檔不在地圖裡（改到它們碰的東西會選不到它們）："
                        + "、".join(sorted(missing)))
    extra = set(files) - on_disk
    if extra:
        problems.append("地圖裡有已經不存在的測試檔：" + "、".join(sorted(extra)))

    for t, info in files.items():
        gone = [d for d in deps_of(info) if not (ROOT / d).exists()]
        if gone:
            problems.append(f"{t} 的相依有 {len(gone)} 條指不到東西了"
                            f"（改名或刪檔之後地圖會安靜過期）：{'、'.join(gone[:5])}")
    return problems


def stale_allowlist() -> list[str]:
    """`NO_TEST_COVERS` 裡有沒有已經過期的條目。

    兩種過期方式，各自的症狀不一樣：

    * **檔案不見了**（改名或刪掉）——那一條變成一句對著空氣說的話。
    * **有測試碰它了**——那一條會讓 `select` 說「不必跑測試」，
      **而其實有一項測試守著它**。這一種比較危險，因為它是靜默的。
    """
    problems: list[str] = []
    data = _load_map()
    known: set[str] = set()
    for info in data.get("files", {}).values():
        known.update(deps_of(info))
    for path in NO_TEST_COVERS:
        if not (ROOT / path).exists():
            problems.append(f"NO_TEST_COVERS 裡的 {path} 已經不存在了。")
        if path in known:
            problems.append(
                f"NO_TEST_COVERS 說沒有測試碰 {path}，但地圖說有。"
                "把它從那份清單裡拿掉——留著會讓 select 少挑一個測試。"
            )
    return problems


def coverage_problems() -> list[str]:
    """量測時「各批相加」是不是等於那個檔案實際的項數。

    ⛔ **這是分批量測唯一的正確性保證**：`test_generators.py` 是照
    16 個 `template_id` 加上兩個互斥的兜底批量的，那 18 批**互斥且窮盡**，
    所以相加必須恰好等於 540。相加少了就代表有一批沒跑到，
    而**沒跑到的那些測試的相依會整個從地圖上消失**——症狀是
    「改了某個檔案，`select` 說不用跑任何測試」。
    """
    problems: list[str] = []
    data = _load_map()
    for t, info in data.get("files", {}).items():
        actual = _collected(t, None)
        got = collected_of(info)
        if got != actual:
            problems.append(
                f"{t}：量測時各批相加是 {got} 項，但這個檔案現在有 {actual} 項。"
                "重量它（指令見 CLAUDE.md「只跑相關的測試」）。"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure")
    m.add_argument("test_file")
    m.add_argument("--k", default=None, help="只跑這一批（沙箱的 180 秒上限用）")
    m.add_argument("--merge", action="store_true",
                   help="把這一批的相依聯集進既有那一列，而不是覆寫")
    m.add_argument("--bootstrap", action="store_true",
                   help="紅的也寫（只有 tests/test_test_deps.py 那個自我指涉用得到）")

    s = sub.add_parser("select")
    s.add_argument("--base", default=None,
                   help="與哪一個 commit 比（預設：目前未提交的變更）")
    s.add_argument("paths", nargs="*", help="直接給路徑（給了就不看 git）")

    sub.add_parser("check")

    args = ap.parse_args(argv)
    if args.cmd == "measure":
        return measure(args.test_file, args.k, args.merge, args.bootstrap)
    if args.cmd == "select":
        paths = args.paths or changed_paths(args.base)
        if not paths:
            print("沒有任何變更。")
            return 0
        print("這次改到的檔案：" + "、".join(paths))
        print()
        print_selection(select(paths))
        return 0
    problems = check()
    for p in problems:
        print("⛔ " + p)
    print("地圖與現況對得起來。" if not problems else "")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
