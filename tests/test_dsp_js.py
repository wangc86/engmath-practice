"""瀏覽器端 DSP 純函式層的數值測試（PLAN.md §8.4，方案 B）。

**做法**：用 `subprocess` 跑 `node scripts/run_dsp_case.mjs <case>`，把 JSON 結果
與**同一支測試裡現算的參考值**比對。參考值一律用 SymPy 或明確寫出來的閉合式
在這裡算，**絕不從 node 那一側拿**——兩條路徑一旦在任何地方合流，交叉驗證就
不成立了（§8.4 第 1 項：「兩條獨立路徑必須相等」在 DSP 的形式）。

為什麼是 pytest 驅動 node，而不是 `node --test`：**`pytest` 要繼續是唯一的
測試入口**。單人維護的專案裡，一個沒有人記得跑的第二套測試會慢慢變紅然後被
跳過——這與 §6 對「留著沒有人呼叫的模組」是同一個論證。

⚠️ 機器上沒有 `node` 時，這一整檔會 **skip 並印出明確原因**，
**不得靜默通過**（硬規則 4）。Node 只是開發期相依，部署不需要它。

這一輪（2S3）**還沒有 FFT**：FFT 層排在 2S1，被 §7 #32 擋著。因此 §8.4 那五類
驗證裡，這裡兌現得到的是第 1 類的形狀（獨立路徑交叉比對）與第 2 類（解析解
對照）；Parseval、往返誤差、golden vector 要等 2S1／2S2。
"""

from __future__ import annotations

import cmath
import json
import math
import random
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest
import sympy as sp
from mpmath import mp

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "run_dsp_case.mjs"

NODE = shutil.which("node")

# skip 的原因要具體到「該做什麼才能跑」，否則它就是一則被忽略的雜訊。
_SKIP_REASON = (
    "找不到 node，因此瀏覽器端 DSP 的數值測試無法執行（PLAN.md §8.4 方案 B）。"
    "這不是通過，是沒有跑。請安裝 Node.js（開發期相依，部署不需要）後重跑。"
)

pytestmark = [pytest.mark.dsp_js, pytest.mark.skipif(NODE is None, reason=_SKIP_REASON)]


def run_case(name: str, **args):
    """跑一個 case，回傳解析後的 JSON。"""
    payload = json.dumps({"case": name, "args": args})
    # 由 stdin 餵進去，不走 argv：N = 4096 的 case 光是輸入陣列就超過 Linux
    # 單一 argv 的 128 KB 上限（`OSError: Argument list too long`），
    # 而那是一個與被測邏輯完全無關、卻只在大 N 才出現的失敗。
    result = subprocess.run(
        [NODE, str(RUNNER), "-"],
        input=payload, capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"node 執行 case {name!r} 失敗（returncode={result.returncode}）：\n"
            f"{result.stderr}"
        )
    return json.loads(result.stdout)


# --- 參考實作（Python 這一側，刻意與 JS 的寫法不同）--------------------------

def reference_signed_alias(f: int, fs: int) -> Fraction:
    """混疊頻率的參考值，用**掃描**而不是閉合式算。

    JS 那一側寫的是 `f - Math.round(f / fs) * fs`（一行閉合式）；這裡改成
    「掃過所有可能的 k，取 |f - k·fs| 最小的那一個」。兩者在數學上等價，
    但寫法完全不同，因此一邊寫錯不會被另一邊掩蓋。

    平手（f/fs 恰為半整數）時取**較大的 k**——這是 `Math.round` 對正數的
    行為，也是 `transform.js` 的註解寫明的慣例。
    """
    f_r, fs_r = Fraction(f), Fraction(fs)
    best_k = None
    best = None
    for k in range(0, int(f / fs) + 2):
        distance = abs(f_r - k * fs_r)
        if best is None or distance < best or (distance == best and k > best_k):
            best, best_k = distance, k
    return f_r - best_k * fs_r


def reference_hold_indices(n: int, ctx_rate: int, fs: int) -> list[int]:
    """零階保持的參考：哪些 frame 會抓一個新樣本。

    JS 用的是一個累積相位的迴圈（`phase += step; if (phase >= 1) ...`）。
    這裡改用等價但形式不同的判準：第 i 個 frame 抓樣本，若且唯若
    ``floor((i+1)·step) > floor(i·step)``。用 `Fraction` 算，沒有浮點誤差。
    """
    step = Fraction(fs, ctx_rate)
    # 第 0 格一定抓：實作把相位初始化成 1，讓「一開始就有一個樣本」，
    # 否則展示剛開始的前幾毫秒會輸出一個憑空的 0。
    return [0] + [
        i for i in range(1, n)
        if math.floor((i + 1) * step) > math.floor(i * step)
    ]


# --- 1. 混疊頻率 ------------------------------------------------------------

ALIAS_PAIRS = [
    (440, 8000),      # 遠低於奈奎斯特，不混疊
    (1200, 8000),
    (3999, 8000),     # 剛好在奈奎斯特下面
    (4000, 8000),     # 恰好在奈奎斯特上（半整數平手）
    (4001, 8000),     # 剛越過去，摺回 3999
    (5000, 8000),
    (7999, 8000),     # 幾乎等於 fs，摺到 1 Hz
    (8000, 8000),     # 整數倍：取樣點全在 0
    (9000, 8000),
    (1200, 1500),
    (1200, 900),
    (1200, 400),      # f 是 fs 的三倍
    (1234, 777),
]


def test_alias_frequency_matches_an_independent_scan():
    rows = run_case("aliasFrequency", pairs=[list(p) for p in ALIAS_PAIRS])
    assert len(rows) == len(ALIAS_PAIRS)
    for row, (f, fs) in zip(rows, ALIAS_PAIRS):
        expected_signed = reference_signed_alias(f, fs)
        assert row["f"] == f and row["fs"] == fs
        assert row["nyquist"] == pytest.approx(fs / 2)
        assert row["signed"] == pytest.approx(float(expected_signed), abs=1e-9), (
            f"f={f} fs={fs} 的有號混疊頻率不對"
        )
        assert row["apparent"] == pytest.approx(float(abs(expected_signed)), abs=1e-9)
        assert row["aliased"] is (f > fs / 2)
        assert row["sign"] == (-1 if expected_signed < 0 else 1)
        # 表觀頻率永遠落在 [0, fs/2]——這是「摺線」這個說法的內容。
        assert 0 <= row["apparent"] <= fs / 2 + 1e-9


def test_apparent_frequency_equals_f_when_there_is_no_aliasing():
    """解析解對照（§8.4 第 2 類）：f <= fs/2 時公式必須退化成 f 自己。

    這一條看起來太簡單而不值得測，但它守的是一個很貴的錯誤：
    如果哪天有人把公式寫成「總是摺一次」，畫面上每一個沒有混疊的情況
    都會顯示錯的數字，而那正是這個展示要學生相信的那個數字。
    """
    # 嚴格小於：f 恰好等於 fs/2 是一個**平手**（+fs/2 與 -fs/2 一樣近），
    # 有號的那個值就不再唯一。物理上這一格也沒有意義——正弦在
    # 奈奎斯特頻率上的取樣點全是 0，聽不出正負。它由上一項測試涵蓋。
    pairs = [(f, fs) for f, fs in ALIAS_PAIRS if f < fs / 2]
    rows = run_case("aliasFrequency", pairs=[list(p) for p in pairs])
    for row, (f, _fs) in zip(rows, pairs):
        assert row["apparent"] == pytest.approx(f)
        assert row["signed"] == pytest.approx(f)
        assert row["aliased"] is False


# --- 2. 這個展示的數學核心 --------------------------------------------------

@pytest.mark.parametrize("f,fs", [(4001, 8000), (5000, 8000), (7999, 8000),
                                  (1200, 900), (1200, 400), (9000, 8000)])
def test_alias_sine_passes_through_the_same_sample_points(f, fs):
    """混疊後那條正弦與原訊號**取樣點完全相同**——畫面上那條虛線的正當性。

    參考值用 SymPy 現算（規則 1：數學正確性只能來自 SymPy），而且是
    「先代入具體的 n 再求值」——與 JS 那一側「用有號混疊頻率重新合成一條
    正弦」是兩條不同的路徑。
    """
    count = 24
    data = run_case("aliasSamplesMatch", f=f, fs=fs, count=count)

    expected_signed = reference_signed_alias(f, fs)
    assert data["signed"] == pytest.approx(float(expected_signed), abs=1e-9)

    for n in range(count):
        exact = sp.sin(2 * sp.pi * sp.Integer(f) * sp.Rational(n, fs))
        reference = float(exact.evalf(30))
        assert data["original"][n] == pytest.approx(reference, abs=1e-12), (
            f"原訊號的第 {n} 個取樣點與 SymPy 不合"
        )
        # 這一行就是整個展示要教的事：兩個不同頻率、同一組取樣點。
        assert data["reconstructed"][n] == pytest.approx(
            data["original"][n], abs=1e-9
        ), f"f={f} fs={fs}：混疊正弦在第 {n} 個取樣點上與原訊號不合"


def test_unsigned_alias_would_be_wrong_for_the_reconstruction():
    """反面確認：若重建改用**無號**的混疊頻率，取樣點就會對不上。

    這一項存在的理由是 `transform.js` 裡那段註解——有號是重點，不是細節。
    沒有這一項的話，把 `signedAliasFrequency` 換成 `aliasFrequency` 不會有
    任何測試變紅，而畫面上只會出現一條「看起來也很像對的」曲線。
    """
    f, fs = 5000, 8000
    signed = reference_signed_alias(f, fs)
    assert signed < 0, "這個測試需要一組會反相的參數"

    data = run_case("aliasSamplesMatch", f=f, fs=fs, count=8)
    unsigned = float(abs(signed))
    mismatch = max(
        abs(math.sin(2 * math.pi * unsigned * n / fs) - data["original"][n])
        for n in range(1, 8)
    )
    assert mismatch > 1e-3, "無號版本竟然也對得上，這組參數選錯了"


# --- 3. 取樣時刻與零階保持 --------------------------------------------------

@pytest.mark.parametrize("fs,t0,duration", [
    (8000, 0.0, 0.01), (1500, 0.0, 0.02), (400, 0.003, 0.05), (2000, 0.0, 0.002),
])
def test_sample_times_lie_on_the_sampling_grid(fs, t0, duration):
    times = run_case("sampleTimes", fs=fs, t0=t0, duration=duration)

    first = math.ceil(t0 * fs)
    last = math.floor((t0 + duration) * fs)
    assert len(times) == max(0, last - first + 1)

    for index, t in enumerate(times):
        assert t == pytest.approx((first + index) / fs, abs=1e-12)
        assert t0 - 1e-12 <= t <= t0 + duration + 1e-12
    # 等距
    gaps = [b - a for a, b in zip(times, times[1:])]
    for gap in gaps:
        assert gap == pytest.approx(1 / fs, rel=1e-12)


@pytest.mark.parametrize("ctx_rate,fs", [(48000, 8000), (48000, 1500),
                                         (44100, 400), (48000, 7000)])
def test_zero_order_hold_holds_the_right_value(ctx_rate, fs):
    """零階保持：輸出必須是階梯，而且每一階的值等於該階起點抓到的輸入。"""
    n = 256
    # 用一個每格都不同的輸入，這樣「抓錯了哪一格」一定看得出來。
    input_signal = [math.sin(2 * math.pi * 3 * i / n) + i / n for i in range(n)]
    data = run_case("zeroOrderHold", input=input_signal, ctxRate=ctx_rate, fs=fs)
    output = data["output"]

    holds = reference_hold_indices(n, ctx_rate, fs)
    assert holds and holds[0] == 0, "第一個 frame 就該抓一個樣本"

    current = None
    for i in range(n):
        if i in set(holds):
            current = input_signal[i]
        assert output[i] == pytest.approx(current, abs=1e-12), (
            f"第 {i} 格的保持值不對（ctx={ctx_rate} fs={fs}）"
        )

    # 階數應該約等於「視窗長度 × fs」，差不超過 1（邊界）。
    assert abs(len(holds) - n * fs / ctx_rate) <= 1


@pytest.mark.parametrize("ctx_rate,fs", [(48000, 8000), (44100, 1500), (48000, 400)])
def test_worklet_zoh_matches_the_pure_function(ctx_rate, fs):
    """worklet 裡那份 ZOH 必須與 `signal.js` 裡那份逐格相同。

    兩份的重複是刻意的（worklet 不能 import ES module），而重複該付的代價
    就是這一項——改了其中一份就會紅燈。
    """
    n = 128
    input_signal = [math.cos(2 * math.pi * 5 * i / n) for i in range(n)]
    pure = run_case("zeroOrderHold", input=input_signal, ctxRate=ctx_rate, fs=fs)
    worklet = run_case(
        "workletZeroOrderHold", input=input_signal, ctxRate=ctx_rate, fs=fs
    )
    assert worklet["name"] == "zoh-sampler"
    for i, (a, b) in enumerate(zip(pure["output"], worklet["output"])):
        # worklet 的輸出是 Float32Array，所以只能要求到單精度。
        assert b == pytest.approx(a, abs=1e-6), f"第 {i} 格兩份實作不一致"


def test_worklet_outputs_silence_when_the_input_is_gone():
    """上游斷掉時輸出靜音，而不是繼續吐上一個保持值。

    保持值是一個直流偏移，在喇叭上是一聲悶響——而且它不會有人回報，
    因為「停止之後有一聲」很容易被當成正常。
    """
    data = run_case(
        "workletSilenceWithoutInput", blockSize=128, ctxRate=48000, fs=1000
    )
    assert any(abs(v) > 0 for v in data["first"]), "第一塊應該有聲音才對"
    assert all(v == 0 for v in data["second"])


# --- 4. 畫面時間窗 ----------------------------------------------------------

def test_view_window_tracks_the_alias_and_stays_bounded():
    pairs = [(1200, 8000), (1200, 1500), (4001, 8000), (7999, 8000),
             (8000, 8000), (1200, 400), (100, 16000), (5000, 5000)]
    rows = run_case("viewWindow", pairs=[list(p) for p in pairs])
    for row in rows:
        f, fs, seconds, alias = row["f"], row["fs"], row["seconds"], row["alias"]
        assert 0.002 - 1e-12 <= seconds <= 0.06 + 1e-12, "視窗長度超出上下限"
        # 這也順帶確認 signal.js 內部那份「只給視窗用」的混疊公式與
        # transform.js 的 aliasFrequency 一致（見 signal.js 的註解）。
        base = alias if alias > 1 else max(f, 1)
        expected = min(0.06, max(0.002, 3 / base))
        assert seconds == pytest.approx(expected, rel=1e-12), f"f={f} fs={fs}"


# --- 5. 繪製層：斷言資料，不斷言像素（§8.4）---------------------------------

GEOMETRY_ARGS = dict(
    t0=0.0, t1=0.02, vMin=-1.15, vMax=1.15, width=900, height=320,
    pad={"left": 12, "right": 12, "top": 16, "bottom": 16},
    times=[0.0, 0.004, 0.008, 0.012, 0.016],
    values=[0.0, 0.9, -0.5, 0.3, -1.0],
)


def test_curve_points_are_monotonic_in_x_and_inside_the_canvas():
    data = run_case("geometry", **GEOMETRY_ARGS)
    xs = [p["x"] for p in data["curve"]]
    ys = [p["y"] for p in data["curve"]]
    assert xs == sorted(xs), "x 座標必須隨時間單調遞增"
    pad = GEOMETRY_ARGS["pad"]
    assert min(xs) >= pad["left"] - 1e-9
    assert max(xs) <= GEOMETRY_ARGS["width"] - pad["right"] + 1e-9
    assert min(ys) >= pad["top"] - 1e-9
    assert max(ys) <= GEOMETRY_ARGS["height"] - pad["bottom"] + 1e-9


def test_y_axis_points_the_right_way():
    """canvas 的 y 是向下的，所以**資料值越大、像素 y 越小**。

    寫反了圖還是「看起來像個波形」，只是上下顛倒——而上下顛倒的正弦
    仍然是一個正弦。這是這一層唯一會靜默出錯的地方。
    """
    data = run_case("geometry", **GEOMETRY_ARGS)
    assert data["topY"] < data["zeroY"] < data["bottomY"]

    pairs = sorted(
        zip(GEOMETRY_ARGS["values"], (p["y"] for p in data["curve"]))
    )
    ys = [y for _v, y in pairs]
    assert ys == sorted(ys, reverse=True), "值遞增時像素 y 必須遞減"


def test_scale_round_trips_between_pixels_and_time():
    data = run_case("geometry", **GEOMETRY_ARGS)
    midpoint = (GEOMETRY_ARGS["t0"] + GEOMETRY_ARGS["t1"]) / 2
    assert data["roundTrip"] == pytest.approx(midpoint, abs=1e-12)
    assert data["leftX"] == pytest.approx(GEOMETRY_ARGS["pad"]["left"])
    assert data["rightX"] == pytest.approx(
        GEOMETRY_ARGS["width"] - GEOMETRY_ARGS["pad"]["right"]
    )


def test_staircase_is_a_staircase():
    """零階保持的路徑：每一階先水平、再垂直，而且水平段的 y 等於該樣本值。"""
    data = run_case("geometry", **GEOMETRY_ARGS)
    stairs = data["stairs"]
    assert len(stairs) == 2 * len(GEOMETRY_ARGS["times"])

    for index in range(0, len(stairs), 2):
        left, right = stairs[index], stairs[index + 1]
        assert left["y"] == pytest.approx(right["y"]), "水平段不水平"
        assert right["x"] > left["x"], "階梯必須往右走"
    for index in range(1, len(stairs) - 1, 2):
        assert stairs[index]["x"] == pytest.approx(stairs[index + 1]["x"]), (
            "垂直段不垂直"
        )

    xs = [p["x"] for p in stairs]
    assert xs == sorted(xs)


def test_trace_sine_covers_the_window_and_stays_in_range():
    """解析解對照的最小版本：正弦的值域是 [-1, 1]，端點落在視窗兩端。"""
    data = run_case("trace", f=1000, t0=0.0, duration=0.005, count=101)
    assert data["times"][0] == pytest.approx(0.0)
    assert data["times"][-1] == pytest.approx(0.005)
    assert max(data["values"]) <= 1.0 + 1e-12
    assert min(data["values"]) >= -1.0 - 1e-12
    for t, v in zip(data["times"], data["values"]):
        assert v == pytest.approx(math.sin(2 * math.pi * 1000 * t), abs=1e-12)
    assert data["clampCheck"] == 3


# ============================================================================
# 2S2：§8.4 的五類驗證
#
# 順序刻意由強到弱，而且**強的那兩項不可裁減**：樸素 DFT 交叉比對與解析解
# 對照。往返誤差排在後面並且附一項專門說明「它為什麼不能單獨當閘門」的測試。
#
# 每一項都對 `IMPLS` 做 parametrize：vendored 的 radix-4（執行期真的在跑的
# 那支）與 transform.js 裡標為教學用的 radix-2，**跑完全相同的斷言**。
# 這是 §8.3 那句「否則它就是一份說謊的教材」在測試裡的樣子。
# ============================================================================

IMPLS = ("vendor", "radix2")

GOLDEN_PATH = ROOT / "tests" / "data" / "dsp_golden.json"


def golden():
    """讀 `scripts/dsp_reference.py` 產生的 golden 檔。

    缺檔要**明確地失敗**（規則 4），不能 skip——它是 commit 進版本控制的
    資產，不見了就是有人刪錯東西，那不是「這台機器沒裝 node」那種情況。
    """
    assert GOLDEN_PATH.exists(), (
        f"找不到 {GOLDEN_PATH}。它應該在版本控制裡；"
        "重新產生的指令是 `python scripts/dsp_reference.py`。"
    )
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def naive_dft(values: list[complex]) -> list[complex]:
    """樸素 DFT：照定義的 O(N²) 二重迴圈。**§8.4 第 1 類的參考實作。**

        X[k] = Σ_n x[n] · exp(-2πi·kn/N)

    它有資格當參考值的全部理由就是**短到可以逐字與定義核對**。
    這裡刻意不呼叫 `numpy.fft`（那是另一支快速演算法，兩支快速演算法互相
    比對只能證明它們一樣，不能證明它們對），也刻意與 JS 那一側的寫法無關。
    """
    n = len(values)
    out = []
    for k in range(n):
        acc = 0j
        for i in range(n):
            acc += values[i] * cmath.exp(-2j * math.pi * k * i / n)
        out.append(acc)
    return out


def random_complex(n: int, seed: int) -> tuple[list[float], list[float]]:
    rng = random.Random(seed)
    return (
        [rng.uniform(-1.0, 1.0) for _ in range(n)],
        [rng.uniform(-1.0, 1.0) for _ in range(n)],
    )


def relative_error(got: list[complex], want: list[complex]) -> float:
    scale = max((abs(v) for v in want), default=1.0) or 1.0
    return max(abs(g - w) for g, w in zip(got, want)) / scale


# --- 第 1 類：樸素 DFT 交叉比對（最強的一項，不可裁減）----------------------

@pytest.mark.parametrize("impl", IMPLS)
@pytest.mark.parametrize("n", [8, 16, 32, 64, 128, 256, 512, 1024])
def test_fft_matches_a_naive_dft(impl, n):
    """兩條獨立路徑必須相等（§8.4 第 1 類）。

    這一項抓得到位元反轉錯位、twiddle 正負號、1/N 放錯邊——也就是
    §8.3 列出的那三種「產生出來的頻譜看起來都很像對的」錯誤。
    """
    re, im = random_complex(n, seed=n)
    data = run_case("forwardTransform", re=re, im=im, impl=impl)
    got = [complex(r, i) for r, i in zip(data["re"], data["im"])]
    want = naive_dft([complex(r, i) for r, i in zip(re, im)])
    assert relative_error(got, want) <= 1e-10


@pytest.mark.parametrize("impl", IMPLS)
def test_real_input_gives_a_conjugate_symmetric_spectrum(impl):
    """實數輸入 → X[N-k] = conj(X[k])。

    這是「頻譜的右半是左半的鏡像」那句話的精確版本，也是
    `amplitudeSpectrum` 只取 k = 0…N/2 的正當性。
    """
    n = 256
    re, _ = random_complex(n, seed=7)
    data = run_case("forwardTransform", re=re, impl=impl)
    spec = [complex(r, i) for r, i in zip(data["re"], data["im"])]
    for k in range(1, n // 2):
        assert spec[n - k] == pytest.approx(spec[k].conjugate(), abs=1e-9)
    assert abs(spec[0].imag) < 1e-9
    assert abs(spec[n // 2].imag) < 1e-9


def test_the_two_implementations_agree_with_each_other():
    """vendored 與教學用的 radix-2 逐點相等。

    上面那一項已經分別把兩支釘在樸素 DFT 上，所以這一項嚴格說是多餘的——
    留著是因為它**失敗時的訊息比較好讀**：兩支不合，一眼就知道問題在
    「我們自己寫的那支」而不是在參考值。
    """
    n = 512
    re, im = random_complex(n, seed=99)
    a = run_case("forwardTransform", re=re, im=im, impl="vendor")
    b = run_case("forwardTransform", re=re, im=im, impl="radix2")
    for key in ("re", "im"):
        for x, y in zip(a[key], b[key]):
            assert x == pytest.approx(y, abs=1e-9)


# --- 第 2 類：解析解對照（同樣不可裁減）-------------------------------------

@pytest.mark.parametrize("impl", IMPLS)
def test_a_unit_impulse_transforms_to_a_flat_spectrum(impl):
    """δ[n] → 每一格都是 1。縮放因子放錯邊的話這一項立刻紅。"""
    n = 64
    re = [1.0] + [0.0] * (n - 1)
    data = run_case("forwardTransform", re=re, impl=impl)
    for k in range(n):
        assert data["re"][k] == pytest.approx(1.0, abs=1e-12)
        assert data["im"][k] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("impl", IMPLS)
def test_a_constant_transforms_to_dc_only(impl):
    """常數 A → 只有 k=0 一格是 N·A，其餘全 0。"""
    n, amplitude = 64, 0.25
    data = run_case("forwardTransform", re=[amplitude] * n, impl=impl)
    assert data["re"][0] == pytest.approx(n * amplitude, abs=1e-12)
    for k in range(1, n):
        assert abs(complex(data["re"][k], data["im"][k])) < 1e-11


@pytest.mark.parametrize("impl", IMPLS)
@pytest.mark.parametrize("window", ["rectangular", "hann", "hamming", "blackman"])
def test_a_bin_centred_sine_reads_back_its_own_amplitude(impl, window):
    """落在 bin 中心的正弦：那一格的讀數**就是振幅本身**。

    這一項同時看守三件容易各自寫錯、又會互相掩蓋的事：
    折疊時的 ×2、除以 N、以及除以視窗的相干增益。
    加窗之後峰會變寬（能量分到鄰格），所以斷言寫成「峰值格 ±1 的總和」。
    """
    n, fs, amplitude, k0 = 256, 8000, 0.7, 20
    tone = k0 * fs / n
    samples = [amplitude * math.sin(2 * math.pi * tone * i / fs) for i in range(n)]
    data = run_case("spectrumPath", samples=samples, fs=fs, window=window, impl=impl)

    assert data["frequencies"][k0] == pytest.approx(tone)
    # 峰值格**恰好**等於振幅。加窗會讓鄰格也有值（那是視窗自己的頻譜），
    # 但峰值格本身不受影響——這正是相干增益那個除法在做的事。
    assert data["amplitudes"][k0] == pytest.approx(amplitude, rel=1e-9)
    far = sum(v for i, v in enumerate(data["amplitudes"]) if abs(i - k0) > 2)
    assert far < 1e-9, "落在 bin 中心的正弦不該有遠處洩漏"


@pytest.mark.parametrize("impl", IMPLS)
def test_a_rectangular_pulse_is_a_dirichlet_kernel(impl):
    """長度 L 的矩形脈衝 → Dirichlet 核，零點落在 k = m·N/L。

    §8.4 第 2 類特別點名的那個差一錯誤（把 bin k 標成 k·fs/N 還是
    k·fs/(N-1)）就是被這一項抓住的：零點的位置只由 L 與 N 決定，
    軸標定差一格，零點就對不上。
    """
    n, length = 64, 8
    re = [1.0] * length + [0.0] * (n - length)
    data = run_case("forwardTransform", re=re, impl=impl)
    magnitude = [abs(complex(r, i)) for r, i in zip(data["re"], data["im"])]

    assert magnitude[0] == pytest.approx(length, abs=1e-12)
    for k in range(1, n):
        want = abs(math.sin(math.pi * k * length / n) / math.sin(math.pi * k / n))
        assert magnitude[k] == pytest.approx(want, abs=1e-10)
    for m in range(1, length):
        assert magnitude[m * n // length] < 1e-10


@pytest.mark.parametrize("n,fs", [(256, 8000), (1024, 48000), (512, 44100)])
def test_the_frequency_axis_is_labelled_with_n_not_n_minus_one(n, fs):
    """頻率軸：k·fs/N，最後一格恰好是奈奎斯特頻率。"""
    data = run_case("frequencyAxis", n=n, fs=fs, probe=[440.0, 1000.0])
    freqs = data["frequencies"]
    assert len(freqs) == n // 2 + 1
    assert freqs[0] == 0.0
    assert freqs[-1] == pytest.approx(fs / 2)
    for k, f in enumerate(freqs):
        assert f == pytest.approx(k * fs / n)
    assert data["spacing"] == pytest.approx(fs / n)
    assert data["observation"] == pytest.approx(n / fs)
    # 解析度就是 1/T，這兩者是同一個數字的兩種說法。
    assert data["spacing"] == pytest.approx(1.0 / data["observation"])
    for f, nearest in zip([440.0, 1000.0], data["nearest"]):
        assert abs(nearest - f) <= data["spacing"] / 2 + 1e-9
        assert nearest / data["spacing"] == pytest.approx(
            round(nearest / data["spacing"]), abs=1e-9
        )


def test_powers_of_two_are_recognised():
    data = run_case("frequencyAxis", n=256, fs=8000, probe=[])
    assert data["powerOfTwo"] == [True, False, False]
    assert data["nextPow2"] == [256, 256, 512]


# --- 第 3 類：Parseval／能量守恆 --------------------------------------------

@pytest.mark.parametrize("impl", IMPLS)
@pytest.mark.parametrize("n", [16, 128, 1024])
def test_parseval_energy_is_conserved(impl, n):
    """Σ|x[n]|² = (1/N)·Σ|X[k]|²。便宜，而且對每個新加的變換都適用。

    ⚠️ 它抓不到相位錯誤（能量對、相位可以全錯），所以它排在第 3 而不是第 1。
    """
    re, im = random_complex(n, seed=n + 1)
    data = run_case("parseval", re=re, im=im, impl=impl)
    assert data["freqEnergy"] / n == pytest.approx(data["timeEnergy"], rel=1e-10)


# --- 第 4 類：往返誤差（**不得單獨當閘門**）---------------------------------

@pytest.mark.parametrize("impl", IMPLS)
@pytest.mark.parametrize("n", [16, 256, 4096])
def test_round_trip_returns_the_original(impl, n):
    """‖IFFT(FFT(x)) − x‖∞ ≤ C·N·ε。

    ⚠️ **這一項單獨看沒有意義**，理由見下一項測試。它在這裡是因為
    「1/N 只放了一次、或放了兩次」這類錯誤它抓得到，而且很便宜。
    """
    re, im = random_complex(n, seed=n + 2)
    data = run_case("roundTrip", re=re, im=im, impl=impl)
    tolerance = 1e-15 * n * 8
    for got, want in zip(data["re"], re):
        assert got == pytest.approx(want, abs=tolerance)
    for got, want in zip(data["im"], im):
        assert got == pytest.approx(want, abs=tolerance)


def test_round_trip_alone_cannot_catch_a_flipped_twiddle():
    """**這一項不測產品，它測「第 4 類為什麼不能單獨當閘門」這個論斷。**

    §8.4 寫著：twiddle 的正負號**一致地**寫反，往返仍然完美。
    這裡把那個反例真的做出來——一支正負號全寫反的 DFT 與它對應的反變換，
    往返誤差是機器精度等級的 0，但它算出來的頻譜是共軛的，也就是錯的。

    寫成測試而不是寫成註解，是因為註解裡的論斷沒有人會去驗證，
    而這一項一旦哪天不成立（例如有人把公差放寬到荒謬的程度），它會紅。
    """
    n = 32
    re, im = random_complex(n, seed=5)
    x = [complex(r, i) for r, i in zip(re, im)]

    def flipped_forward(values):
        return [
            sum(values[i] * cmath.exp(+2j * math.pi * k * i / n) for i in range(n))
            for k in range(n)
        ]

    def flipped_inverse(values):
        return [
            sum(values[k] * cmath.exp(-2j * math.pi * k * i / n) for k in range(n)) / n
            for i in range(n)
        ]

    back = flipped_inverse(flipped_forward(x))
    assert max(abs(a - b) for a, b in zip(back, x)) < 1e-12, "往返居然不完美？"

    correct = naive_dft(x)
    wrong = flipped_forward(x)
    assert relative_error(wrong, correct) > 0.1, (
        "正負號寫反卻算出相同的頻譜，這個反例失效了"
    )


# --- 第 5 類：SymPy 產生的 golden vector ------------------------------------

def test_the_golden_file_still_passes_its_own_self_check():
    """golden 檔的自我一致性（§8.4 對第 5 類的但書：它本身若產錯就一路錯）。

    直接呼叫 `scripts/dsp_reference.py` 裡的 `self_check`，因此
    「產生時檢查過」與「用之前再檢查一次」走的是同一段程式碼。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dsp_reference", ROOT / "scripts" / "dsp_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.self_check(golden()) == []


@pytest.mark.parametrize("size", ["8", "64"])
def test_window_coefficients_match_sympy(size):
    """視窗係數與 SymPy 逐項相等，而且相干增益是那四個可以心算的數字。"""
    data = golden()["windows"][size]
    n = int(size)
    got = run_case("windows", names=list(data["coefficients"]), n=n)
    for name, coefficients in data["coefficients"].items():
        assert got[name]["coefficients"] == pytest.approx(coefficients, abs=1e-12)
        assert got[name]["coherentGain"] == pytest.approx(
            data["coherent_gain"][name], abs=1e-12
        )
        assert got[name]["displayName"], "每個視窗都要有英文顯示名（D5）"


@pytest.mark.parametrize("impl", IMPLS)
def test_windowed_sine_spectra_match_the_sympy_golden_vectors(impl):
    """加窗正弦的整條幅度譜與 SymPy 逐格相等，on-bin 與 off-bin 各四個視窗。"""
    for case in golden()["spectra"]:
        n, fs = case["n"], case["fs"]
        samples = [
            case["amplitude"] * math.sin(2 * math.pi * case["tone_hz"] * i / fs)
            for i in range(n)
        ]
        data = run_case(
            "spectrumPath", samples=samples, fs=fs, window=case["window"], impl=impl
        )
        assert data["amplitudes"] == pytest.approx(case["amplitudes"], abs=1e-9), (
            f"{case['label']} 與 golden 不符"
        )


def test_the_dirichlet_golden_vector_matches_node():
    data = golden()["dirichlet"]
    n, length = data["n"], data["pulse_length"]
    re = [1.0] * length + [0.0] * (n - length)
    got = run_case("forwardTransform", re=re, impl="vendor")
    magnitude = [abs(complex(r, i)) for r, i in zip(got["re"], got["im"])]
    assert magnitude == pytest.approx(data["magnitude"], abs=1e-10)


# --- 教學上的三個斷言：它們是這個展示的內容本身 ------------------------------

def test_leakage_gets_smaller_as_the_window_gets_gentler():
    """洩漏的排序：矩形 ≫ Hamming > Hann > Blackman。

    **這一項守的是展示的教學內容，不只是程式的正確性。** 學生在畫面上
    切換視窗時看到的差別，就是這四個數字的差別；順序若哪天反了，
    頁面不會壞、不會拋錯，只是那一格教錯了——這正是本專案最在意的那種缺陷。
    """
    far = {}
    for case in golden()["spectra"]:
        if case["on_bin"]:
            continue
        centre = case["tone_hz"] * case["n"] / case["fs"]
        far[case["window"]] = sum(
            v for i, v in enumerate(case["amplitudes"]) if abs(i - centre) > 2.5
        )
    assert far["rectangular"] > far["hamming"] > far["hann"] > far["blackman"]
    # 級距也要夠大，否則「排序對」可能只是浮點雜訊排出來的。
    # 實測值（N=64、off-bin 半格）：0.711 / 0.084 / 0.0246 / 0.0062。
    assert far["rectangular"] > 5 * far["hamming"]
    assert far["hamming"] > 3 * far["hann"]
    assert far["hann"] > 3 * far["blackman"]


def test_an_off_bin_tone_reads_low_and_the_rectangular_window_is_the_worst():
    """扇貝損失（scalloping loss）：頻率不落在格子上時，峰值讀數會偏低。

    這是實務上「訊號明明有 0.7，頻譜卻只顯示 0.46」的來源，
    也是為什麼不能把頻譜的峰值直接當成振幅來抄進報告。
    """
    peaks = {}
    amplitude = None
    for case in golden()["spectra"]:
        if case["on_bin"]:
            continue
        peaks[case["window"]] = max(case["amplitudes"])
        amplitude = case["amplitude"]
    for window, peak in peaks.items():
        assert peak < amplitude, f"{window}：off-bin 的峰值不該達到真正的振幅"
    assert peaks["rectangular"] < peaks["hamming"] < peaks["blackman"]


@pytest.mark.parametrize("impl", IMPLS)
def test_zero_padding_does_not_improve_resolution(impl):
    """**Demo 2 要糾正的第二個誤解，寫成一項測試。**

    兩個相距 0.5/T 的頻率（也就是不到一格）——補零到四倍長之後，
    頻譜上仍然只有一個峰。補零只是把同一條連續頻譜畫得比較密，
    真正能分開它們的只有把觀測時間 T 加長。

    對照組在下一項：把 T 加長為兩倍，兩個峰就出來了。
    """
    n, fs = 256, 8000
    spacing = fs / n
    f1, f2 = 20 * spacing, 20 * spacing + 0.5 * spacing
    samples = [
        math.sin(2 * math.pi * f1 * i / fs) + math.sin(2 * math.pi * f2 * i / fs)
        for i in range(n)
    ]
    padded = run_case(
        "spectrumPath", samples=samples, fs=fs, window="hann", padTo=4 * n, impl=impl
    )
    peaks = run_case("peaks", amplitudes=list(padded["amplitudes"]), count=4)["peaks"]
    strong = [p for p in peaks if p["value"] > 0.2 * peaks[0]["value"]]
    assert len(strong) == 1, "補零居然把兩個頻率分開了——那會推翻這一頁的教學內容"
    assert padded["length"] == 4 * n


@pytest.mark.parametrize("impl", IMPLS)
def test_a_longer_observation_does_improve_resolution(impl):
    """對照組：同樣兩個頻率，觀測時間加長為兩倍就分得開了。"""
    n, fs = 512, 8000
    spacing = 8000 / 256
    f1, f2 = 20 * spacing, 20 * spacing + 0.5 * spacing
    samples = [
        math.sin(2 * math.pi * f1 * i / fs) + math.sin(2 * math.pi * f2 * i / fs)
        for i in range(n)
    ]
    data = run_case("spectrumPath", samples=samples, fs=fs, window="hann", impl=impl)
    peaks = run_case("peaks", amplitudes=list(data["amplitudes"]), count=4)["peaks"]
    strong = [p for p in peaks if p["value"] > 0.3 * peaks[0]["value"]]
    assert len(strong) == 2, "觀測時間加倍之後應該看得到兩個峰"


def test_padding_after_windowing_is_not_the_same_as_windowing_after_padding():
    """順序不能反：**先加窗再補零**。

    反過來做（先補零再加窗）等於把視窗套在一段更長的訊號上，
    視窗的兩端會落在補的那些 0 上面，實際訊號反而被中間那段壓縮——
    這是一個會安靜地產生錯誤頻譜的順序錯誤，所以釘一項測試。
    """
    samples = [1.0] * 8
    data = run_case("windowThenPad", samples=samples, window="hann", padTo=16)
    assert data["windowedThenPadded"][8:] == [0.0] * 8
    assert data["windowedThenPadded"][:8] != pytest.approx(
        data["paddedThenWindowed"][:8]
    )


def test_peak_interpolation_lands_between_the_neighbouring_bins():
    """次格內插：頂點必須落在峰值格的 ±1 格內，而且對稱資料回到整數格。"""
    symmetric = [0.0, 1.0, 4.0, 1.0, 0.0]
    data = run_case("peaks", amplitudes=symmetric, count=1)
    assert data["peaks"][0]["bin"] == 2
    assert data["interpolated"][0] == pytest.approx(2.0)

    skewed = [0.0, 1.0, 4.0, 3.0, 0.0]
    data = run_case("peaks", amplitudes=skewed, count=1)
    assert 2.0 < data["interpolated"][0] < 3.0


def test_decibels_are_twenty_log_ten_and_the_floor_really_clamps():
    values = [1.0, 0.5, 0.1, 0.0, -0.0]
    data = run_case("decibels", values=values, floor=-80)
    assert data["db"][0] == pytest.approx(0.0)
    assert data["db"][1] == pytest.approx(20 * math.log10(0.5))
    assert data["db"][2] == pytest.approx(-20.0)
    assert data["db"][3] == -80.0, "0 必須落在底線上，不得是 -inf 或 NaN"
    assert data["db"][4] == -80.0
    assert data["defaultFloor"] == -120


def test_the_colour_scale_is_monotonic_in_brightness():
    """§8.6 第 4 點：顏色不得是唯一的訊息載體。

    viridis 的亮度隨強度單調上升，所以色盲學生、黑白列印、投影機色偏
    之下都還讀得出強弱。jet 沒有這個性質——這一項就是不讓人換回 jet。
    """
    data = run_case("colormap", steps=32, floor=-100, ceiling=0, dbProbe=[-120, -50, 0])
    lums = [c["luminance"] for c in data["colors"]]
    for a, b in zip(lums, lums[1:]):
        assert b > a, "色階的亮度必須嚴格遞增"
    for colour in data["colors"]:
        for channel in colour["rgb"]:
            assert 0 <= channel <= 255
    assert data["units"] == [0.0, 0.5, 1.0]


# ============================================================================
# 2S5：Fourier 級數的加法合成
#
# 這一組的參考值全部來自 `scripts/dsp_reference.py`，而那支腳本**對定義式
# 真的積一次分**（`(1/π)∫₀^{2π} x(θ) sin(nθ) dθ`），不抄 `transform.js` 的
# 閉合式。兩條路徑因此連方法都不同：一邊查表、一邊積分。
#
# 這不是形式上的講究——2S5 開發當下，鋸齒波的 bₙ 就漏了一個 π，
# 而那個錯誤**在畫面上完全看不出來**（形狀對、尺度錯三倍）。
# 抓到它的是把部分和拿去量過衝：一個不該超過 1.18 的東西量出 2.9。
# ============================================================================

FOURIER_KINDS = ("square", "sawtooth", "triangle", "halfWave")

#: 與 `fourier.js` 的 `GIBBS_LADDER`、`dsp_reference.py` 的同名常數一致。
GIBBS_LADDER = (3, 7, 15, 31, 63)

#: 吉布斯過衝的極限，佔落差的比例。課本上那個「約 8.95%」。
GIBBS_FRACTION = 0.08948987223608756

#: 中日韓字元。`tests/test_web.py` 有同一個常數，但這一檔刻意不 import
#: 那邊的東西（它會一併拉進 FastAPI 的 fixture，而這一檔只跑 node），
#: 所以在這裡放一份三行的重複，換掉一個不必要的相依。
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")


def fourier_golden():
    return golden()["fourier"]


# --- 係數：對照 SymPy 積出來的值 --------------------------------------------

@pytest.mark.parametrize("kind", FOURIER_KINDS)
def test_trig_coefficients_match_the_integrals(kind):
    """aₙ、bₙ、a₀/2 逐項等於 SymPy 對定義式積出來的值。

    **這是這一組最強的一項**（§8.4 第 1 類在 Fourier 級數上的形式）：
    展示端跑閉合式，參考端跑積分，兩者沒有共用任何一行程式碼。
    """
    reference = fourier_golden()["trig"][kind]
    count = fourier_golden()["trig_count"]
    data = run_case("fourierSeries", kind=kind, count=count)

    assert data["dc"] == pytest.approx(reference["dc"], abs=1e-12)
    for i, harmonic in enumerate(data["harmonics"]):
        assert harmonic["n"] == i + 1
        assert harmonic["cosine"] == pytest.approx(reference["cosine"][i], abs=1e-12), (
            f"{kind} 的 a_{i + 1}"
        )
        assert harmonic["sine"] == pytest.approx(reference["sine"][i], abs=1e-12), (
            f"{kind} 的 b_{i + 1}"
        )


@pytest.mark.parametrize("kind", FOURIER_KINDS)
def test_amplitude_and_phase_rebuild_the_original_coefficients(kind):
    """(A, φ) 與 (a, b) 必須是同一件事的兩種寫法。

    `atan2(a, b)` 寫成 `atan2(b, a)` 是這裡最容易犯、也最難看出來的錯：
    所有相位差 90°，**頻譜完全不變**，只有波形不對。
    """
    data = run_case("fourierSeries", kind=kind, count=12)
    for harmonic in data["harmonics"]:
        amplitude, phase = harmonic["amplitude"], harmonic["phase"]
        assert amplitude == pytest.approx(
            math.hypot(harmonic["cosine"], harmonic["sine"]), abs=1e-12
        )
        assert amplitude * math.cos(phase) == pytest.approx(harmonic["sine"], abs=1e-12), (
            "b 應該是 A·cos φ"
        )
        assert amplitude * math.sin(phase) == pytest.approx(harmonic["cosine"], abs=1e-12), (
            "a 應該是 A·sin φ"
        )


@pytest.mark.parametrize("kind", FOURIER_KINDS)
def test_exponential_coefficients_match_a_separate_integral(kind):
    """cₙ 對照**另一個獨立積出來的** SymPy 值，不是由 aₙ、bₙ 換算的。

    順帶把課綱第 3 週要的兩件事釘住：|cₙ| = Aₙ/2（振幅分給 ±n 兩邊），
    以及 c₋ₙ = conj(cₙ)（實訊號的頻譜共軛對稱）。
    """
    reference = fourier_golden()["exponential"][kind]
    count = fourier_golden()["exponential_count"]
    data = run_case("fourierSeries", kind=kind, count=count)

    for i in range(count):
        got = data["exponential"][i]
        assert got["re"] == pytest.approx(reference["re"][i], abs=1e-12)
        assert got["im"] == pytest.approx(reference["im"][i], abs=1e-12)
        assert got["magnitude"] == pytest.approx(
            data["harmonics"][i]["amplitude"] / 2, abs=1e-12
        ), "|c_n| 必須恰好是振幅的一半"
        # c₋ₙ = conj(cₙ)：這裡只存正的 n，所以斷言的是「取共軛之後
        # 兩者的模相同、實部相同、虛部相反」——也就是共軛對稱本身。
        assert abs(complex(got["re"], -got["im"])) == pytest.approx(got["magnitude"])


def test_the_square_wave_has_no_even_harmonics_and_the_sawtooth_has_them_all():
    """哪些諧波在、哪些不在——這是長條圖上學生第一眼會問的事。"""
    square = run_case("fourierSeries", kind="square", count=12)["harmonics"]
    for h in square:
        if h["n"] % 2 == 0:
            assert h["amplitude"] == 0, f"方波不該有第 {h['n']} 次諧波"
        else:
            assert h["amplitude"] == pytest.approx(4 / (h["n"] * math.pi))

    sawtooth = run_case("fourierSeries", kind="sawtooth", count=12)["harmonics"]
    for h in sawtooth:
        assert h["amplitude"] == pytest.approx(2 / (h["n"] * math.pi)), (
            f"鋸齒波第 {h['n']} 次諧波"
        )


@pytest.mark.parametrize(
    "kind,power",
    [("square", 1), ("sawtooth", 1), ("triangle", 2), ("halfWave", 2)],
)
def test_the_coefficients_decay_at_the_advertised_rate(kind, power):
    """1/n 對 1/n²——**收斂速度**這一格的教學內容就是這兩個指數。

    畫面上那條包絡線畫的是同一件事，所以它錯了這裡要變紅。
    比對方式是「振幅乘上 n^power 應該幾乎是常數」。
    """
    data = run_case("fourierSeries", kind=kind, count=24)
    active = [h for h in data["harmonics"] if h["amplitude"] > 0 and h["n"] > 2]
    scaled = [h["amplitude"] * h["n"] ** power for h in active]
    assert scaled, "沒有可用的諧波，這個測試大概失效了"
    assert max(scaled) / min(scaled) < 1.15, (
        f"{kind} 的振幅乘 n^{power} 之後不像常數：{scaled[:6]}"
    )
    assert data["shape"]["decay"] == ("1/n" if power == 1 else "1/n^2")


# --- 部分和：由係數組出來的曲線真的逼近目標 ---------------------------------

@pytest.mark.parametrize("kind", FOURIER_KINDS)
def test_the_partial_sum_approaches_the_target_away_from_any_jump(kind):
    """遠離不連續點的地方，項數越多越接近目標。**逐點收斂**。

    刻意避開跳點：在跳點上部分和恆等於兩個單邊極限的中點，永遠不收斂，
    而那是下一項測試的內容。
    """
    probes = [0.4, 1.1, 2.0, 2.6, 4.0, 5.3]
    target = run_case("idealWaveform", kind=kind, thetas=probes)["values"]
    previous = None
    for count in (8, 32, 128):
        sums = run_case("partialSum", kind=kind, count=count, thetas=probes)["sum"]
        worst = max(abs(a - b) for a, b in zip(sums, target))
        if previous is not None:
            assert worst < previous, f"{kind}：加到 {count} 項反而更差了"
        previous = worst
    assert previous < 0.02, f"{kind}：128 項之後最差還有 {previous}"


@pytest.mark.parametrize("kind", ["square", "sawtooth"])
def test_at_a_jump_the_partial_sum_sits_exactly_at_the_midpoint(kind):
    """跳點上部分和恆為兩個單邊極限的中點，**與項數無關**。

    這是 Dirichlet 的結論，也是「級數收斂到哪裡」最精確的一句話——
    而它同時解釋了為什麼「與目標的最大差距」那一欄永遠是落差的一半。
    """
    jump_phase = 0.0 if kind == "square" else math.pi
    for count in (1, 5, 33, 129):
        value = run_case(
            "partialSum", kind=kind, count=count, thetas=[jump_phase]
        )["sum"][0]
        assert value == pytest.approx(0.0, abs=1e-9), (
            f"{kind} 在跳點上的 {count} 項部分和應該是 0（±1 的中點）"
        )


@pytest.mark.parametrize("kind", FOURIER_KINDS)
def test_the_three_traces_share_one_time_axis(kind):
    """目標、部分和、單一諧波三條曲線畫在同一張圖上，時間軸必須逐點相同。

    它們各自呼叫一次取樣器，而只要有一份把 `count - 1` 寫成 `count`，
    兩條曲線就會整體平移半個像素——看起來像「重建有一點點延遲」，
    而那是一個學生會信以為真的假象。
    """
    data = run_case(
        "traces", kind=kind, count=9, f0=100, t0=0, duration=0.02, points=41,
    )
    assert data["times"] == data["sumTimes"] == data["harmonicTimes"]
    assert data["times"][0] == pytest.approx(0.0)
    assert data["times"][-1] == pytest.approx(0.02)
    assert len(data["idealValues"]) == 41


# --- 吉布斯現象 --------------------------------------------------------------

@pytest.mark.parametrize("kind", ["square", "sawtooth"])
def test_the_overshoot_matches_its_exact_value(kind):
    """量出來的過衝對照 SymPy 算出來的**精確**峰值。

    參考值不是掃出來的：峰的位置有閉合式（方波 π/2M、鋸齒 π-π/(N+1)），
    `dsp_reference.py` 直接在那一點求值，並用一次密集掃描背書那個位置。
    """
    reference = {row["count"]: row for row in fourier_golden()["gibbs"][kind]}
    data = run_case("overshoot", kind=kind, counts=list(GIBBS_LADDER), points=8192)
    for row in data:
        want = reference[row["count"]]
        assert row["peak"] == pytest.approx(want["peak"], abs=2e-4), (
            f"{kind} N={row['count']} 的峰值"
        )
        assert row["overshootFraction"] == pytest.approx(want["fraction"], abs=1e-4)


@pytest.mark.parametrize("kind", ["square", "sawtooth"])
def test_the_overshoot_heads_for_nine_percent_and_not_for_zero(kind):
    """⛔ **這一項就是這個展示的論點。**

    多數學生以為加更多項過衝就會消失。實際上兩個有跳點的波形都收斂到
    落差的 8.95%——方波由上面下來，鋸齒波由下面上去，但**都不是往 0 去**。

    這一項若哪天變紅而有人「順手放寬」它，這一頁就從糾正誤解變成製造誤解。
    """
    data = run_case("overshoot", kind=kind, counts=[15, 31, 63, 127, 255])
    fractions = [row["overshootFraction"] for row in data]
    deltas = [b - a for a, b in zip(fractions, fractions[1:])]
    assert all(d > 0 for d in deltas) or all(d < 0 for d in deltas), (
        f"{kind} 的過衝序列不是單調的：{fractions}"
    )
    assert abs(fractions[-1] - GIBBS_FRACTION) < 0.005, (
        f"{kind} 加到 255 項之後過衝是 {fractions[-1]}，應該逼近 {GIBBS_FRACTION}"
    )
    assert fractions[-1] > 0.08, "過衝不得看起來像在收斂到 0"


@pytest.mark.parametrize("kind", ["square", "sawtooth"])
def test_the_overshoot_gets_narrower_even_though_it_does_not_get_smaller(kind):
    """高度不動，**寬度每加倍項數就減半**——這是對照表第三欄。

    兩件事必須一起成立才教得對：只講高度會讓學生以為「什麼都沒改善」，
    只講寬度會讓他以為「所以還是收斂了」。
    """
    data = run_case("overshoot", kind=kind, counts=[15, 31, 63, 127])
    offsets = [row["peakOffsetPeriods"] for row in data]
    for previous, current in zip(offsets, offsets[1:]):
        assert 1.8 < previous / current < 2.2, (
            f"{kind}：峰的距離由 {previous} 變成 {current}，預期減半"
        )


@pytest.mark.parametrize("kind", ["triangle", "halfWave"])
def test_a_continuous_target_reports_no_overshoot_at_all(kind):
    """連續的波形沒有跳點，所以「過衝佔落差的百分之幾」不成立。

    回傳 `null` 而不是 0 是刻意的（見 `measureOvershoot` 的註解）：
    畫面顯示 0% 讀起來像「過衝存在但等於零」，而它其實是「不適用」。
    """
    data = run_case("overshoot", kind=kind, counts=[5, 25, 125])
    for row in data:
        assert row["jump"] == 0
        assert row["overshootFraction"] is None
        assert row["overshoot"] is None
        assert row["peakOffsetPeriods"] is None
    peaks = [row["peak"] for row in data]
    assert peaks[0] < peaks[1] < peaks[2] or all(p < 1.05 for p in peaks)


def test_a_jump_stops_the_worst_error_from_shrinking_at_all():
    """**一致收斂 vs 逐點收斂**，一句話一個數字。

    有跳點時「與目標的最大差距」不隨項數下降——它停在跳點那一格上，
    永遠是落差的一半。連續的波形則確實在下降。這一組對照就是
    「加更多項會不會收斂到完美」最精確的答案。
    """
    for kind in ("square", "sawtooth"):
        gaps = [row["gap"] for row in
                run_case("overshoot", kind=kind, counts=[5, 25, 125])]
        for gap in gaps:
            assert gap == pytest.approx(1.0, abs=1e-6), (
                f"{kind} 的最大差距應該恆為落差的一半（1.0），實際 {gap}"
            )

    for kind in ("triangle", "halfWave"):
        gaps = [row["gap"] for row in
                run_case("overshoot", kind=kind, counts=[5, 25, 125])]
        assert gaps[0] > gaps[1] > gaps[2], f"{kind} 的最大差距應該下降：{gaps}"
        assert gaps[-1] < 0.01


# --- 相位：這一頁真正獨佔的教學點 -------------------------------------------

@pytest.mark.parametrize("kind", FOURIER_KINDS)
@pytest.mark.parametrize("mode", ["zero", "random"])
def test_changing_phase_never_changes_a_single_amplitude(kind, mode):
    """⛔ **「改相位、波形全變、音色幾乎不變」的程式版本。**

    振幅逐格相同（因此長條圖不動、因此音色不動），而波形確實變了。
    這一項守的是這一頁**唯一一個 Octave 給不了**的教學點，
    所以它同時斷言兩件事——只斷言前一半，一個把振幅也歸零的實作也會過。
    """
    data = run_case("phaseScheme", kind=kind, count=16, mode=mode, seed=7)
    assert data["movedAmplitudes"] == data["baseAmplitudes"], (
        "換相位動到了振幅——這一頁的論點就不成立了"
    )
    if mode == "random":
        moved = [
            abs(a - b) for a, b in zip(data["basePhases"], data["movedPhases"])
        ]
        assert max(moved) > 0.5, "隨機相位卻幾乎沒有動"
        changed = [
            abs(a - b) for a, b in zip(data["sampledBase"], data["sampledMoved"])
        ]
        assert max(changed) > 0.1, "相位變了，波形卻沒變——那不可能"


def test_the_same_seed_always_gives_the_same_phases():
    """同一個 seed 必須畫出同一張圖。

    否則每一次重繪（改音量、切回分頁、縮放視窗）波形都會跳一次，
    而學生會以為是自己動到了什麼。「再抽一次」是一個明確的按鈕。
    """
    data = run_case("phaseScheme", kind="sawtooth", count=12, mode="random", seed=42)
    assert data["movedPhases"] == data["repeatPhases"]

    other = run_case("phaseScheme", kind="sawtooth", count=12, mode="random", seed=43)
    assert other["movedPhases"] != data["movedPhases"], "換了 seed 卻抽到同一組"


def test_a_seed_gives_the_same_phases_whichever_waveform_it_is_used_on():
    """換波形不該讓某一次諧波的相位跟著跳。

    方波的偶次諧波振幅是 0，若實作「振幅為 0 就不抽亂數」，
    同一個 seed 在方波與鋸齒波上就會走出不同的序列——症狀是
    「我只換了目標波形，第 3 次諧波的相位怎麼也變了」，沒有人解釋得了。
    """
    square = run_case("phaseScheme", kind="square", count=12, mode="random", seed=5)
    sawtooth = run_case("phaseScheme", kind="sawtooth", count=12, mode="random", seed=5)
    assert square["movedPhases"] == sawtooth["movedPhases"]


def test_turning_one_harmonic_by_hand_only_moves_that_one():
    """個別調整某一次諧波：只動它，而且仍然不動振幅。"""
    quarter = math.pi / 2
    data = run_case(
        "phaseScheme", kind="square", count=9, mode="series", seed=1,
        offsets={"3": quarter},
    )
    assert data["movedAmplitudes"] == data["baseAmplitudes"]
    for i, (before, after) in enumerate(
        zip(data["basePhases"], data["movedPhases"]), start=1
    ):
        expected = before + (quarter if i == 3 else 0)
        assert after == pytest.approx(expected, abs=1e-12), f"第 {i} 次諧波"


def test_the_phase_modes_all_have_english_labels():
    """D5：介面文字一律英文，而這三個字串會直接出現在選單裡。"""
    data = run_case("phaseScheme", kind="square", count=4, mode="series", seed=1)
    assert set(data["modes"]) == {"series", "zero", "random"}
    for label in data["modes"].values():
        assert label and not CJK.search(label)


# --- 帶限：這一頁不許自己先混疊 ----------------------------------------------

@pytest.mark.parametrize("sample_rate", [44100, 48000])
@pytest.mark.parametrize("f0", [55, 110, 440, 880, 3000])
def test_every_harmonic_that_survives_is_below_the_nyquist_frequency(f0, sample_rate):
    """⛔ 合成的每一個諧波都必須**嚴格低於** f_s/2。

    在一個教 Fourier 級數的頁面上讓自己的合成先混疊，會很難看：
    畫面上第 40 根長條會在耳朵裡變成一個位置錯誤的音。
    參考值在 Python 這一側直接由定義算，不呼叫被測的那一支。
    """
    data = run_case(
        "bandLimitSeries", kind="sawtooth", count=64, f0=f0, sampleRate=sample_rate,
    )
    nyquist = sample_rate / 2
    expected = [n for n in range(1, 65) if n * f0 < nyquist]
    assert data["kept"] == expected
    assert data["dropped"] == 64 - len(expected)
    assert data["nyquist"] == nyquist
    for n in data["kept"]:
        assert n * f0 < nyquist
    if data["dropped"] > 0:
        assert (data["kept"][-1] + 1) * f0 >= nyquist, "還有一個諧波塞得下卻被丟了"


def test_a_harmonic_landing_exactly_on_the_nyquist_frequency_is_dropped():
    """恰好等於 f_s/2 的那一格排除掉。

    取樣之後它只剩一個常數振幅、相位資訊全丟——已經不是一個能聽的諧波了，
    而留著它會讓「最高播了第幾次諧波」那個讀數說一句不太真的話。
    """
    # 44100 / 2 = 22050 = 第 2 次諧波 × 11025 Hz，剛好踩在線上。
    data = run_case(
        "bandLimitSeries", kind="sawtooth", count=6, f0=11025, sampleRate=44100,
    )
    assert data["kept"] == [1]
    assert data["maxHarmonic"] == 1


def test_when_the_fundamental_is_too_high_nothing_survives():
    """基頻本身就在奈奎斯特之上：一個諧波都不剩，而且不是靜默失敗。

    展示層對這個回傳值會在畫面上留一句英文訊息（規則 4）；
    這裡守的是它真的回傳空的，而不是回傳一個混疊的諧波。
    """
    data = run_case(
        "bandLimitSeries", kind="square", count=8, f0=30000, sampleRate=44100,
    )
    assert data["kept"] == []
    assert data["maxHarmonic"] == 0


# --- PeriodicWave：real/imag 兩張表 ------------------------------------------

@pytest.mark.parametrize("kind", FOURIER_KINDS)
@pytest.mark.parametrize("mode", ["series", "random"])
def test_the_periodic_wave_tables_rebuild_the_same_waveform(kind, mode):
    """⛔ real 與 imag 寫反是這個檔案裡最不能出的錯。

    寫反不會爆錯、不會改變頻譜，只會讓**每個諧波的相位差 90°**——
    而相位正是這一頁在教的東西。所以這裡把那兩張表餵回 Web Audio
    的合成式 `Σ real[k]cos(kθ) + imag[k]sin(kθ)`，逐點與部分和比對。
    """
    thetas = [0.0, 0.3, 1.0, 2.2, 3.5, 4.9, 6.0]
    data = run_case(
        "periodicWave", kind=kind, count=10, mode=mode, seed=3, thetas=thetas,
    )
    for got, want in zip(data["rebuilt"], data["direct"]):
        assert got == pytest.approx(want, abs=1e-6)


def test_the_periodic_wave_tables_leave_the_constant_term_out():
    """Web Audio 的合成式由 k = 1 開始，直流播不出來。

    半波整流有一個 1/π 的直流項，**畫面上有、聲音裡沒有**。
    這不是我們的取捨（規格如此），但它必須是刻意的而不是漏掉的，
    所以有一項測試釘住它；頁面上也寫了這件事。
    """
    data = run_case(
        "periodicWave", kind="halfWave", count=8, mode="series", seed=1, thetas=[0.0],
    )
    assert data["real"][0] == 0.0 and data["imag"][0] == 0.0
    assert data["dc"] == pytest.approx(1 / math.pi)


# --- 長條圖的幾何（§8.4：斷言資料，不斷言像素）-----------------------------

def test_the_coefficient_bars_are_inside_the_canvas_and_do_not_overlap():
    values = [1.0, 0.0, 0.33, 0.0, 0.2, 0.0, 0.14]
    pad = {"left": 40, "right": 10, "top": 10, "bottom": 20}
    data = run_case("bars", values=values, width=600, height=200, pad=pad, vMax=1.2)
    rects = data["rects"]

    assert [r["index"] for r in rects] == list(range(1, len(values) + 1))
    for rect in rects:
        assert rect["x"] >= pad["left"] - 1
        assert rect["x"] + rect["width"] <= 600 - pad["right"] + 1
        assert rect["y"] >= pad["top"] - 1e-9
        assert rect["y"] + rect["height"] <= data["baseY"] + 1e-9
    for previous, current in zip(rects, rects[1:]):
        assert previous["x"] + previous["width"] <= current["x"] + 1e-9, "長條重疊了"


def test_a_zero_coefficient_draws_a_bar_of_zero_height():
    """振幅 0 的諧波不得畫出任何高度。

    方波的偶次諧波就是這一格，而「為什麼方波沒有第 2 次諧波」
    是這張圖要回答的問題之一——畫出一根一像素高的長條就答錯了。
    """
    data = run_case(
        "bars", values=[1.0, 0.0, 0.5], width=400, height=150,
        pad={"left": 30, "right": 10, "top": 10, "bottom": 20}, vMax=1.0,
    )
    assert data["rects"][1]["height"] == pytest.approx(0.0, abs=1e-9)
    assert data["rects"][0]["height"] > data["rects"][2]["height"] > 0


def test_bar_heights_are_proportional_to_the_values():
    """兩倍的振幅畫成兩倍高。長條圖唯一該保證的事。"""
    data = run_case(
        "bars", values=[0.25, 0.5, 1.0], width=400, height=160,
        pad={"left": 30, "right": 10, "top": 10, "bottom": 20}, vMax=1.0,
    )
    heights = [r["height"] for r in data["rects"]]
    assert heights[1] == pytest.approx(2 * heights[0])
    assert heights[2] == pytest.approx(4 * heights[0])


# ============================================================================
# 9. 瀏覽器支援偵測（D45，v0.20）
#
# `lib/browser.js` 的判斷邏輯是純函式，所以它跑得到這條既有的管線上。
# **這一組與上面所有組不同的地方是：它沒有「參考值」。** 上面每一項都在
# 問「這個數字對不對」，這一組問的是「這個判斷該給哪一個答案」，
# 因此寫法是**成對的正反案例**，而不是公差。
#
# ⚠️ 誠實地說一次：下面那些 UA 字串是抄下來的樣本，不是從真的 Safari 上
# 讀到的。這一組能證明的是「拿到這個字串時邏輯會這樣判」，
# 不是「真的 Safari 會送出這個字串」。後者只有一台 Mac 驗得掉。
# ============================================================================

#: 三個引擎的樣本。**`label` 只是給失敗訊息用的**，不參與判斷。
ENGINE_SAMPLES = [
    # --- 正面：應該被認出來的 ---
    {
        "label": "chrome-mac",
        "expect": "chromium",
        "userAgent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    },
    {
        "label": "chrome-linux",
        "expect": "chromium",
        "userAgent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    },
    {
        "label": "edge",
        "expect": "chromium",
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
        ),
    },
    {
        "label": "firefox-linux",
        "expect": "gecko",
        "userAgent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
        ),
    },
    {
        "label": "firefox-mac",
        "expect": "gecko",
        "userAgent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) "
            "Gecko/20100101 Firefox/127.0"
        ),
    },
    # --- 反面：不得被認成支援的 ---
    {
        "label": "safari-mac",
        "expect": "other",
        "userAgent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
    },
    {
        "label": "safari-tp",
        "expect": "other",
        "userAgent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/618.1.1 "
            "(KHTML, like Gecko) Version/18.0 Safari/618.1.1"
        ),
    },
    {
        "label": "empty-ua",
        "expect": "other",
        "userAgent": "",
    },
    {
        "label": "no-ua-at-all",
        "expect": "other",
    },
]


def test_the_three_engines_are_told_apart():
    """正反案例一次跑完。**Safari 必須落在 `other`。**"""
    rows = run_case(
        "browserEngine",
        samples=[{k: v for k, v in s.items() if k != "expect"} for s in ENGINE_SAMPLES],
    )
    assert len(rows) == len(ENGINE_SAMPLES)
    for row, sample in zip(rows, ENGINE_SAMPLES):
        assert row["engine"] == sample["expect"], (
            f"{sample['label']} 判成了 {row['engine']}，應該是 {sample['expect']}"
        )
        assert row["supported"] is (sample["expect"] in ("chromium", "gecko"))


def test_safari_is_not_rescued_by_the_like_gecko_in_its_user_agent():
    """⛔ 這一項守的是整條判準最容易被改壞的一行。

    Safari 的 UA 裡有 `(KHTML, like Gecko)` 也有 `Safari/`。若 Gecko 那條
    判準寫成裸的 `Gecko`（而不是 `Gecko/<數字>`），**Safari 會被判成
    Firefox 而完全不出訊息**——而那個錯誤在 Chrome 與 Firefox 上都看不出來。
    """
    safari = next(s for s in ENGINE_SAMPLES if s["label"] == "safari-mac")
    assert "like Gecko" in safari["userAgent"], "樣本失效了：這個 UA 裡沒有 Gecko"
    assert "Safari/" in safari["userAgent"]
    row = run_case("browserEngine", samples=[{"userAgent": safari["userAgent"]}])[0]
    assert row["engine"] == "other"


def test_the_structured_brands_api_is_enough_on_its_own():
    """`navigator.userAgentData` 是 Chromium 專屬的，所以它出現就是結論。

    ⚠️ 這一項刻意把 UA 字串換成一句垃圾：判準若真的靠結構化資料，
    UA 是什麼都不該影響結果。
    """
    row = run_case("browserEngine", samples=[{
        "userAgent": "totally made up",
        "userAgentData": {"brands": [
            {"brand": "Not/A)Brand", "version": "99"},
            {"brand": "Chromium", "version": "126"},
        ]},
    }])[0]
    assert row["engine"] == "chromium"


def test_a_moz_prefixed_css_property_identifies_gecko():
    """`-moz-` 前綴只有 Gecko 認得——同樣是問「你做得到什麼」。"""
    row = run_case("browserEngine", samples=[{
        "userAgent": "totally made up", "mozAppearance": True,
    }])[0]
    assert row["engine"] == "gecko"


def test_an_unknown_engine_falls_into_other_rather_than_being_waved_through():
    """⚠️ 白名單的失效方向：認不出來就警告，不是認不出來就放行。

    黑名單漏掉一個引擎的結果是**沒有訊息**（安靜地壞掉）；白名單誤判的
    結果是**多一句訊息**（吵）。這個專案一律選吵的那一邊，而這一項
    就是那個選擇本身——把它改成黑名單，這一項會紅。
    """
    for ua in ("", "Mozilla/5.0 (Something Entirely New) SomeEngine/1.0"):
        row = run_case("browserEngine", samples=[{"userAgent": ua}])[0]
        assert row["engine"] == "other"
        assert row["supported"] is False


# --- 能力偵測 ---------------------------------------------------------------

FULL_SUPPORT = {
    "webAudio": True, "audioWorklet": True, "periodicWave": True,
    "analyser": True, "audioParamRamps": True,
}


def test_a_complete_browser_reports_nothing_missing():
    data = run_case("browserCapabilities", flags=dict(FULL_SUPPORT))
    assert data["missing"] == []
    assert data["notice"] is None, "什麼都不缺卻還是跳了訊息"


@pytest.mark.parametrize("dropped", sorted(FULL_SUPPORT))
def test_dropping_any_single_capability_is_noticed(dropped):
    """五個能力逐一拿掉，每一個都必須被抓到。

    這一項的形狀（逐一拿掉）是刻意的：只測「全有」與「全無」的話，
    一條寫錯的判準（例如永遠回 true）仍然全綠。
    """
    flags = dict(FULL_SUPPORT)
    flags[dropped] = False
    data = run_case("browserCapabilities", flags=flags)
    assert dropped in data["missing"], f"拿掉 {dropped} 卻沒有被發現"
    assert data["notice"] is not None
    assert data["notice"]["level"] == "error"
    assert data["notice"]["reason"] == "capability"


def test_the_capability_list_is_exactly_the_five_we_use():
    """⚠️ 清單只准列**真的在用**的東西。

    多列一個沒有人呼叫的 API，它就會在某天某個瀏覽器上把一個其實跑得動的
    頁面擋掉——而那種誤擋沒有人查得出來（訊息說的是「你的瀏覽器不行」，
    而學生沒有辦法反駁它）。`IIRFilterNode` 因此不在裡面：Demo 6 還沒寫。
    """
    data = run_case("browserCapabilities", flags=dict(FULL_SUPPORT))
    assert data["knownKeys"] == [
        "webAudio", "audioWorklet", "periodicWave", "analyser", "audioParamRamps",
    ]


def test_a_missing_audio_param_method_counts_as_missing_ramps():
    """`AudioParam` 在、但少一個方法——這是「介面在、行為不全」的最輕微版本。

    展示每改一次參數都會走 `rampParam`，少任何一個方法都是一路拋例外。
    """
    flags = dict(FULL_SUPPORT)
    flags["dropParamMethod"] = "exponentialRampToValueAtTime"
    data = run_case("browserCapabilities", flags=flags)
    assert data["missing"] == ["audioParamRamps"]


def test_the_webkit_prefixed_audio_context_still_counts():
    """`webkitAudioContext` 也算數——這一條與 `audio.js` 的 `supported` 一致。"""
    flags = dict(FULL_SUPPORT)
    flags["webkitPrefixed"] = True
    data = run_case("browserCapabilities", flags=flags)
    assert data["missing"] == []


# --- ⚠️ D43：非安全脈絡的那條路徑 -------------------------------------------

def test_an_insecure_context_looks_exactly_like_a_missing_audio_worklet():
    """⛔ 這一項是 D43 在測試裡的樣子。

    `AudioWorklet` 只在安全脈絡（https，或 localhost）下取得到。也就是說
    **純 HTTP 加上一個非 localhost 的位址，展示區直接不能用**——而症狀
    與「瀏覽器太舊」一模一樣。分不出來的話，老師會去查瀏覽器版本，
    而問題其實在網址列上。所以訊息要多一句提到 https。
    """
    flags = dict(FULL_SUPPORT)
    flags["audioWorklet"] = False
    flags["insecure"] = True
    data = run_case("browserCapabilities", flags=flags)
    assert data["missing"] == ["audioWorklet"]
    assert "https" in data["notice"]["text"], (
        "非安全脈絡下的訊息沒有提到 https——老師會去查錯的東西"
    )


def test_a_secure_context_does_not_mention_https():
    """反面：東西真的缺的時候不要亂扯網址列。"""
    flags = dict(FULL_SUPPORT)
    flags["audioWorklet"] = False
    data = run_case("browserCapabilities", flags=flags)
    assert "https" not in data["notice"]["text"]


# --- 兩層的優先順序 ---------------------------------------------------------

def test_a_real_failure_outranks_the_engine_warning():
    """兩層同時有話說時，**能力那一層優先**。

    「真的動不了」與「可能安靜地不對」同時印兩段，人只會讀第一段——
    而該讀的是第一段。
    """
    data = run_case(
        "browserNotice", missing=["audioWorklet"], engine="other", secureContext=True,
    )
    assert data["notice"]["reason"] == "capability"
    assert data["notice"]["level"] == "error"


def test_a_supported_engine_with_everything_present_says_nothing():
    """Chrome 與 Firefox 上這一整段永遠不出現。"""
    for engine in ("chromium", "gecko"):
        data = run_case("browserNotice", missing=[], engine=engine, secureContext=True)
        assert data["notice"] is None, f"{engine} 上不該有任何訊息"


def test_safari_with_every_api_present_still_gets_a_warning():
    """⛔ **這一項是 D45 的核心，也是「為什麼能力偵測不夠」的證明。**

    現代 Safari 有 `AudioWorklet`、有 `createPeriodicWave`、有 `AudioParam`
    的斜坡方法——所以能力偵測在它身上**全部通過**。它的問題是實作的行為
    不同，而那是介面看不到的。若哪天有人把引擎那一層刪掉、只留能力偵測，
    這一項會紅，而紅燈裡就寫著理由。
    """
    data = run_case(
        "browserNotice", missing=[], engine="other", secureContext=True,
    )
    assert data["notice"] is not None, "能力全通過就完全不提醒了——Safari 會靜默失敗"
    assert data["notice"]["reason"] == "engine"
    assert data["notice"]["level"] == "warning"
    assert "Safari" in data["notice"]["text"]
    assert "Chrome" in data["notice"]["text"] and "Firefox" in data["notice"]["text"]


def test_the_real_node_global_has_no_web_audio_at_all():
    """完全不造假的一項：node 自己的 global 餵進 `inspect()`。

    它的價值在於**一行 mock 都沒有**，所以 `inspect()` 讀 `navigator`／`CSS`／
    `isSecureContext` 的那條路徑真的被跑過一次——上面每一項走的都是
    `missingCapabilities()` 與 `identifyEngine()`，跳過了那一層。
    """
    data = run_case("browserRealScope")
    assert data["missing"] == [
        "webAudio", "audioWorklet", "periodicWave", "analyser", "audioParamRamps",
    ]
    assert data["engine"] == "other"


# ============================================================================
# 摺積與 LTI（2S10，PLAN §8.2.1 第 4 列；課程 W1–W2）
#
# ⚠️ **摺積是這份專案裡最容易寫出「看起來對」的錯誤實作的東西**，因為錯的
# 結果通常仍然是一條形狀合理的曲線——2S5 那個「漏掉一個 π 的鋸齒波」是同一類
# 失敗（形狀對、尺度錯，畫面上完全看不出來）。這一組因此把四種典型錯法各配
# 一項測試，而且**參考值一律用與 JS 完全不同的方法算**：
#
#   * 輸出長度不是 N+M−1        → `test_the_output_is_always_n_plus_m_minus_one`
#   * 邊界少算一格               → `test_the_two_end_samples_are_single_products`
#   * 忘了翻轉（變成互相關）      → `test_not_flipping_gives_the_reversed_response`
#   * 索引寫成 h[k−n]            → 對多項式乘法的逐格比對
#
# 參考值的獨立路徑是**多項式係數相乘**：把序列讀成多項式的係數，乘積的
# z^n 係數就是 Σ_k x[k] h[n−k]。這條路徑連「這是一個求和」都不知道，
# 它只是 SymPy 在展開一個乘積。
# ============================================================================


def polynomial_convolution(x: list, h: list) -> list[float]:
    """摺積的參考值：多項式相乘（與 `scripts/dsp_reference.py` 同一條路）。

    刻意在這裡再寫一次而不是 import 那支腳本：**測試不該相依於產生
    golden 檔的程式碼**，否則兩者一起錯的時候沒有東西會變紅。
    """
    z = sp.Symbol("z")
    px = sum(sp.nsimplify(c, rational=True) * z**i for i, c in enumerate(x))
    ph = sum(sp.nsimplify(c, rational=True) * z**j for j, c in enumerate(h))
    poly = sp.Poly(sp.expand(px * ph), z)
    return [float(poly.coeff_monomial(z**n)) for n in range(len(x) + len(h) - 1)]


#: 拿來反覆餵的幾組序列。長度刻意都不一樣（含長度 1），因為
#: **長度相等時很多差一錯誤會互相抵消**。
CONV_PAIRS = [
    ([1], [1]),
    ([1], [0, 0, 1]),
    ([1, 1, 1], [1, 1, 1, 1, 1]),
    ([1, 1, 1, 1], [1, 1, 1, 1]),
    ([0.25, 0.5, 0.75, 1.0], [1, -1]),
    ([1, 0.55, -0.4, -0.75], [1, 0, 0.6, 0, 0.36]),
    ([1, 0.55, -0.4, -0.75, 0.2], [0.25, 0.25, 0.25, 0.25]),
    ([2, -3, 0, 1, 4, -1, 5], [1, 2]),
]


@pytest.mark.parametrize("x,h", CONV_PAIRS)
def test_convolution_matches_a_polynomial_product(x, h):
    """⛔ **這一組裡最強的一項**：對照一條完全不同的路徑。

    SymPy 展開 `(Σ x_i z^i)(Σ h_j z^j)` 的時候，它不知道自己在做摺積——
    它在做多項式乘法。兩者相等是一個數學事實，而正因為兩邊沒有共用任何
    程式碼、任何求和次序、甚至任何語言，一邊寫錯不會被另一邊掩蓋。
    """
    data = run_case("convolve", x=x, h=h)
    expected = polynomial_convolution(x, h)
    assert len(data["y"]) == len(expected)
    for n, (got, want) in enumerate(zip(data["y"], expected)):
        assert got == pytest.approx(want, abs=1e-12), f"y[{n}] 不對"


@pytest.mark.parametrize("x,h", CONV_PAIRS)
def test_the_output_is_always_n_plus_m_minus_one(x, h):
    """長度是 N+M−1。

    這是最常見的第一個錯誤（寫成 N+M 或 max(N,M)），而它在畫面上是
    「尾巴多一格 0」或「尾巴少一格」——沒有人會注意到。
    """
    data = run_case("convolve", x=x, h=h)
    assert data["length"] == len(x) + len(h) - 1


@pytest.mark.parametrize("x,h", CONV_PAIRS)
def test_the_two_end_samples_are_single_products(x, h):
    """兩端各只有一項：y[0] = x[0]h[0]，y[N+M−2] = x[N−1]h[M−1]。

    **邊界是差一錯誤唯一藏得住的地方**——中間那些格子有很多項在加，
    少算一項只會讓數字小一點；兩端只有一項，錯了就是完全錯。
    """
    data = run_case("convolve", x=x, h=h)
    assert data["first"] == pytest.approx(x[0] * h[0], abs=1e-12)
    assert data["last"] == pytest.approx(x[-1] * h[-1], abs=1e-12)


@pytest.mark.parametrize("x,h", CONV_PAIRS)
def test_convolution_commutes(x, h):
    """x * h 與 h * x 逐格相同。

    交換律在課本上是一行證明，在程式裡是一個很好的看守：一個把 x 與 h
    的角色寫得不對稱的實作（例如只從 h 的支撐掃、忘了 x 也有邊界）
    會在這裡爆掉，而它在單一方向的測試裡可能完全正常。
    """
    data = run_case("convolve", x=x, h=h)
    assert data["y"] == pytest.approx(data["swapped"], abs=1e-12)


@pytest.mark.parametrize("x,h", CONV_PAIRS)
def test_the_total_of_the_output_is_the_product_of_the_totals(x, h):
    """Σy = (Σx)(Σh)。

    在 z = 1 上求值就是這一條。它很便宜，卻是一個**整體**不變量——
    任何「少加一項」或「多加一項」都會讓它失衡，不管錯在哪一格。
    """
    data = run_case("convolve", x=x, h=h)
    assert data["total"] == pytest.approx(sum(x) * sum(h), abs=1e-12)


def test_convolving_with_a_unit_impulse_returns_the_signal():
    """x * δ = x，逐格相同。

    **這是頁面上最重要的那個等式**（「脈衝響應就是系統」那一段），
    所以它必須是被斷言的，不是被相信的。
    """
    x = [1, 0.55, -0.4, -0.75, 0.2]
    data = run_case("convolve", x=x, h=[1])
    assert data["y"] == pytest.approx(x, abs=0)
    # 反過來也要對：δ * h = h。這一格是「單一 click 播出來就是 h」那句話。
    h = [1, 0, 0, 0.6, 0, 0, 0.36]
    data = run_case("convolve", x=[1], h=h)
    assert data["y"] == pytest.approx(h, abs=0)


@pytest.mark.parametrize("delay", [1, 3, 7])
def test_convolving_with_a_delayed_impulse_shifts_the_signal(delay):
    """x * δ[n−D] 就是 x 往後推 D 格，前面補 D 個 0。"""
    x = [1, 0.55, -0.4, -0.75, 0.2]
    h = [0] * delay + [1]
    data = run_case("convolve", x=x, h=h)
    assert data["y"][:delay] == pytest.approx([0] * delay, abs=0)
    assert data["y"][delay:] == pytest.approx(x, abs=1e-15)


@pytest.mark.parametrize("l1,l2", [(3, 5), (4, 4), (2, 7), (6, 1), (8, 3)])
def test_two_rectangular_pulses_give_a_trapezium(l1, l2):
    """⛔ **課本上唯一一個學生完全手算得出來的例子**，所以它是解析解對照。

    長度 L₁ 與 L₂ 的全 1 序列摺積起來是一個梯形：爬 min(L₁,L₂) 步、
    在 |L₁−L₂|+1 格上維持峰值 min(L₁,L₂)、再對稱降回去。
    三個數字全部寫得出來，而且**與多項式乘法那條路徑無關**——
    它們是從幾何推出來的，所以兩條路互相驗得了對方。
    """
    data = run_case("convolve", x=[1] * l1, h=[1] * l2)
    y = data["y"]
    peak = min(l1, l2)
    assert len(y) == l1 + l2 - 1
    assert max(y) == pytest.approx(peak, abs=1e-12)
    plateau = [v for v in y if abs(v - peak) < 1e-12]
    assert len(plateau) == abs(l1 - l2) + 1
    # 對稱：梯形是偶對稱的（兩個矩形都是常數）。
    assert y == pytest.approx(list(reversed(y)), abs=1e-12)
    # 爬升段嚴格遞增（一次多一項），這一條抓得到「平台算得太寬」。
    rise = y[: peak - 1]
    assert all(b > a for a, b in zip(rise, rise[1:])), "爬升段應該嚴格遞增"


def test_the_moving_average_and_the_difference_have_the_gains_they_claim():
    """移動平均的直流增益是 1，相鄰相減是 0。

    這兩個數字**寫在畫面上**（「Gain for a constant input」那一格），
    而它們正是「低通」與「高通」在時域裡最短的說法。
    相鄰相減那一個必須是**恰好** 0：[1, −1] 的和在 float64 裡沒有捨入。
    """
    data = run_case(
        "impulseResponse",
        shapes=["average", "difference", "impulse", "echo"],
        delay=3, length=8, gain=0.6,
    )
    by_shape = {entry["shape"]: entry for entry in data}
    assert by_shape["average"]["dcGain"] == pytest.approx(1.0, abs=1e-15)
    assert by_shape["difference"]["dcGain"] == 0.0
    assert by_shape["impulse"]["dcGain"] == 1.0
    assert by_shape["echo"]["dcGain"] == pytest.approx(1.6, abs=1e-15)


def test_a_constant_input_comes_out_flat_through_a_moving_average():
    """常數輸入經過移動平均，**中段逐格等於那個常數**。

    邊界那幾格會低一些（視窗還沒填滿），而那是對的——但中段不是近似，
    是恰好。這一項與上一項是一對：上一項測係數，這一項測它真的做到了。
    """
    length = 4
    x = [0.75] * 12
    h = [1 / length] * length
    data = run_case("convolve", x=x, h=h)
    middle = data["y"][length - 1: len(x)]
    assert middle == pytest.approx([0.75] * len(middle), abs=1e-15)
    # 相鄰相減：同樣的常數輸入，中段必須恰好是 0。
    data = run_case("convolve", x=x, h=[1, -1])
    assert data["y"][1:len(x)] == pytest.approx([0] * (len(x) - 1), abs=1e-15)


# --- 直接式 vs 頻域式：§8.4 第 1 類在摺積上的形式 ----------------------------

@pytest.mark.parametrize("n,m", [(1, 1), (1, 64), (7, 5), (16, 16), (100, 37), (513, 128)])
def test_the_fast_convolution_agrees_with_the_definition(n, m):
    """⛔ **執行期跑的是頻域那一支，所以它必須被獨立驗過。**

    這與 §8.4 第 1 類（樸素 DFT vs 快速 FFT）是同一個模式的第二個實例：
    定義式的二重迴圈與「補零 → 兩次 FFT → 逐格相乘 → 一次 IFFT」除了
    答案以外沒有任何共同點，而**頻域那一支最典型的錯法是忘了補零**，
    症狀是循環摺積——尾巴繞回開頭，聲音上是「回音出現在句子的開頭」。
    """
    random.seed(9000 + n * 31 + m)
    x = [random.uniform(-1, 1) for _ in range(n)]
    h = [random.uniform(-1, 1) for _ in range(m)]
    data = run_case("convolveAgreement", x=x, h=h)
    assert data["length"] == n + m - 1
    assert data["fastLength"] == n + m - 1
    # FFT 的誤差隨長度成長，所以界是相對的；1e−10 對這些長度仍然很緊。
    assert data["worst"] <= 1e-10 * max(1.0, data["scale"])


@pytest.mark.parametrize("l1,l2", [(3, 5), (32, 8)])
def test_the_fast_convolution_also_gives_the_trapezium(l1, l2):
    """頻域那一支也要通得過解析解，不是只要「與另一支一致」。

    兩支互相一致但**一起錯**是可能的（例如兩邊都用了同一個錯的長度），
    所以解析解那一關要兩支各過一次——與 §8.3 對兩支 FFT 的要求相同。
    """
    data = run_case("convolve", x=[1] * l1, h=[1] * l2, impl="fft")
    y = data["y"]
    assert len(y) == l1 + l2 - 1
    assert max(y) == pytest.approx(min(l1, l2), abs=1e-9)
    assert y == pytest.approx(polynomial_convolution([1] * l1, [1] * l2), abs=1e-9)


# --- 逐項展開：畫面上那張表與那張圖 ------------------------------------------

#: x 長 4、h 長 5，所以 y 有 4+5−1 = 8 格，合法的 n 是 0…7。
#: 範圍外的那條路徑由 `test_no_overlap_gives_an_empty_sum_rather_than_an_error`
#: 單獨守——混在這裡的話，參考值本身會先 IndexError，而那是測試的 bug 不是實作的。
@pytest.mark.parametrize("n", list(range(0, 8)))
def test_every_step_sums_to_the_output_at_that_index(n):
    """`convolutionStep(x, h, n).sum` 必須逐格等於 `convolve(x, h)[n]`。

    畫面上那張乘積表與那條輸出曲線是**兩個不同的計算**，而學生會拿它們
    互相對照——對不上的話這一頁的整個論證就垮了。
    """
    x = [1, 0.55, -0.4, -0.75]
    h = [1, 0, 0.6, 0, 0.36]
    data = run_case("convolutionStep", x=x, h=h, n=n)
    expected = polynomial_convolution(x, h)
    assert data["sum"] == pytest.approx(expected[n], abs=1e-12)
    assert data["yAtN"] == pytest.approx(expected[n], abs=1e-12)
    # 每一項也要對得起來：k、x[k]、h[n−k]、乘積。
    for term in data["terms"]:
        k = term["k"]
        assert term["x"] == pytest.approx(x[k], abs=0)
        assert term["h"] == pytest.approx(h[n - k], abs=0)
        assert term["product"] == pytest.approx(x[k] * h[n - k], abs=1e-15)
    assert sum(t["product"] for t in data["terms"]) == pytest.approx(data["sum"], abs=1e-12)


#: x 長 4、h 長 5，所以 y 有 4+5−1 = 8 格，合法的 n 是 0…7。
#: 範圍外的那條路徑由 `test_no_overlap_gives_an_empty_sum_rather_than_an_error`
#: 單獨守——混在這裡的話，參考值本身會先 IndexError，而那是測試的 bug 不是實作的。
@pytest.mark.parametrize("n", list(range(0, 8)))
def test_the_overlap_limits_are_the_ones_in_the_textbook(n):
    """求和的上下限是 k ∈ [max(0, n−M+1), min(n, N−1)]。

    **這兩個上下限就是課本上那一行最勸退的東西**，而畫面上它們是一段
    陰影。參考值在這裡用「掃過所有 k，留下兩邊索引都合法的」算——
    與 JS 那兩行 `Math.max`／`Math.min` 的寫法完全不同。
    """
    x = [1, 0.55, -0.4, -0.75]
    h = [1, 0, 0.6, 0, 0.36]
    data = run_case("convolutionStep", x=x, h=h, n=n)
    legal = [k for k in range(len(x)) if 0 <= n - k < len(h)]
    assert [t["k"] for t in data["terms"]] == legal
    assert data["overlap"] == len(legal)
    if legal:
        assert data["kStart"] == legal[0]
        assert data["kEnd"] == legal[-1]


def test_no_overlap_gives_an_empty_sum_rather_than_an_error():
    """n 掃到範圍外時是「沒有重疊」，不是例外。

    動畫會掃過整個 n 範圍，兩端本來就該是空的——而回傳 0 讓繪製端
    不必寫特例（特例正是最容易漏測的東西）。
    """
    data = run_case("convolutionStep", x=[1, 2, 3], h=[1, 1], n=99)
    assert data["terms"] == []
    assert data["overlap"] == 0
    assert data["sum"] == 0
    assert data["products"] == [0, 0, 0]


def test_the_products_row_is_the_terms_scattered_back_onto_the_k_axis():
    """`products` 與 `terms` 是同一組數字的兩種排法，不得不一致。

    圖用前者、表用後者，而兩者由同一個迴圈填——這一項就是在守那件事。
    """
    x = [1, 0.55, -0.4, -0.75]
    h = [1, 0, 0.6]
    data = run_case("convolutionStep", x=x, h=h, n=3)
    assert len(data["products"]) == len(x)
    scattered = [0.0] * len(x)
    for term in data["terms"]:
        scattered[term["k"]] = term["product"]
    assert data["products"] == pytest.approx(scattered, abs=0)


# --- 翻轉：頁面上「為什麼要翻轉」那一格 ---------------------------------------

def test_the_flipped_response_is_h_read_backwards_from_n():
    """k ↦ h[n−k]，範圍外補 0。

    參考值在這裡用**逐 k 查表**算（含明確的界外判斷），
    與 JS 那一行 `n - k` 的算術寫法不同。
    """
    h = [1, 0.2, 0.6, 0.36]
    n = 4
    data = run_case("flipping", x=[1, 1, 1], h=h, n=n, kFrom=0, kTo=6)
    expected = [h[n - k] if 0 <= n - k < len(h) else 0 for k in range(7)]
    assert data["shifted"] == pytest.approx(expected, abs=0)


def test_not_flipping_gives_the_reversed_response():
    """⛔ 「不翻轉」＝「與倒過來的 h 摺積」，而**那不是同一個答案**。

    這一項守的是頁面上那個開關的正當性：如果兩者恰好相等，那個開關就
    什麼都沒教到。用一個不對稱的 h（純延遲）確保它們真的不同——
    而且不同的方式很具體：純延遲的 h 倒過來是「不延遲」。
    """
    x = [1, 0.55, -0.4, -0.75]
    h = [0, 0, 0, 1]              # 純延遲三格，倒過來是 [1, 0, 0, 0]
    data = run_case("flipping", x=x, h=h, n=3, kFrom=0, kTo=3)
    assert data["reversed"] == pytest.approx([1, 0, 0, 0], abs=0)
    assert data["flipped"] != pytest.approx(data["unflipped"], abs=1e-9)
    # 翻轉：x 被推後三格。不翻轉：x 原地不動。
    assert data["flipped"][:3] == pytest.approx([0, 0, 0], abs=0)
    assert data["flipped"][3:] == pytest.approx(x, abs=1e-15)
    assert data["unflipped"][:len(x)] == pytest.approx(x, abs=1e-15)


def test_a_symmetric_response_does_not_care_about_the_flip():
    """對稱的 h 翻不翻都一樣——這是上一項的對照組。

    寫下來是因為它防的是一個很好懂的誤解：「翻轉會改變答案」不是永遠成立，
    它只在 h 不對稱時成立。移動平均剛好是對稱的，所以在那個形狀上
    這個開關看不出差別，而學生會以為開關壞了。
    """
    x = [1, 0.55, -0.4, -0.75]
    h = [0.25, 0.25, 0.25, 0.25]
    data = run_case("flipping", x=x, h=h, n=2, kFrom=0, kTo=3)
    assert data["flipped"] == pytest.approx(data["unflipped"], abs=1e-15)


# --- 六個脈衝響應的形狀 -------------------------------------------------------

def test_each_impulse_response_has_the_taps_it_says_it_has():
    """六個形狀逐一對照它們的定義。

    這一項的性質與 D29 的「範例音檔內容與標籤相符」相同：**標錯了不會有
    任何東西壞掉，而學生會相信標籤**。這裡的「標籤」是頁面上那句
    「A train of impulses, each quieter」，而它必須真的是那樣。
    """
    delay, length, gain = 3, 10, 0.5
    data = run_case(
        "impulseResponse",
        shapes=["impulse", "delay", "echo", "repeat", "average", "difference"],
        delay=delay, length=length, gain=gain,
    )
    by_shape = {entry["shape"]: entry for entry in data}

    assert by_shape["impulse"]["taps"] == [1]
    assert by_shape["delay"]["taps"] == [0, 0, 0, 1]
    assert by_shape["echo"]["taps"] == [1, 0, 0, gain]
    # k·D < L 的每一個 k：0, 3, 6, 9 → 四個，值 g^0…g^3。
    assert by_shape["repeat"]["nonZero"] == [
        [0, 1.0], [3, 0.5], [6, 0.25], [9, 0.125],
    ]
    assert by_shape["average"]["taps"] == [0.1] * 10
    assert by_shape["difference"]["taps"] == [1, -1]

    # `uses` 必須與形狀真的用到的參數一致——畫面上那句「L does nothing
    # right now」是照它寫的，而一句錯的提示會讓學生以為滑桿壞了。
    assert by_shape["impulse"]["uses"] == []
    assert by_shape["delay"]["uses"] == ["delay"]
    assert by_shape["echo"]["uses"] == ["delay", "gain"]
    assert by_shape["repeat"]["uses"] == ["delay", "gain", "length"]
    assert by_shape["average"]["uses"] == ["length"]
    assert by_shape["difference"]["uses"] == []


@pytest.mark.parametrize("shape", ["impulse", "delay", "echo", "average", "difference"])
def test_the_parameters_a_shape_does_not_use_really_do_nothing(shape):
    """`uses` 沒有列到的參數，改了不得改變 h。

    這是上一項那句「L does nothing right now」的另一半：**畫面上說它沒作用，
    那就必須真的沒作用**。反過來的錯誤（其實有作用卻說沒有）是靜默的。
    """
    first = run_case(
        "impulseResponse", shapes=[shape], delay=3, length=10, gain=0.5,
    )[0]
    uses = first["uses"]
    changed = {"delay": 3, "length": 10, "gain": 0.5}
    for key, other in (("delay", 6), ("length", 15), ("gain", 0.9)):
        if key in uses:
            continue
        probe = dict(changed)
        probe[key] = other
        second = run_case("impulseResponse", shapes=[shape], **probe)[0]
        assert second["taps"] == first["taps"], f"{shape} 說它不用 {key}，但改了 {key} 之後 h 變了"


def test_the_input_sequences_are_what_the_menu_says():
    """四個輸入序列。理由與上面那一項相同——標籤必須是真的。"""
    data = run_case(
        "inputSequence", shapes=["impulse", "pulse", "ramp", "wiggle"], length=4,
    )
    by_shape = {entry["shape"]: entry for entry in data}
    assert by_shape["impulse"]["values"] == [1]
    assert by_shape["pulse"]["values"] == [1, 1, 1, 1]
    assert by_shape["ramp"]["values"] == pytest.approx([0.25, 0.5, 0.75, 1.0], abs=1e-15)
    assert len(by_shape["wiggle"]["values"]) == 7
    # 「wiggle」必須真的有正有負，否則乘積圖上永遠看不到負的那一格。
    values = by_shape["wiggle"]["values"]
    assert max(values) > 0 and min(values) < 0


# --- 增益：這一頁特有的音訊安全風險 -------------------------------------------

@pytest.mark.parametrize("h", [
    [1, 0, 0.9],
    [1, 0.9, 0.81, 0.729, 0.6561, 0.59049],
    [0.125] * 8,
    [1, -1],
])
def test_the_gain_bound_is_the_l1_norm_and_it_is_attained(h):
    """⛔ **這一頁的音訊安全機制**：峰值增益恰好是 Σ|h|。

    「上界」與「取得到的上界」是兩件事，而只有後者能拿來當保護。
    這裡實際造出取得到它的那個輸入（x[k] = sign(h[...])），
    驗證輸出真的到達 Σ|h|——如果它只是一個保守估計，
    那麼「正規化之後不會削波」這個承諾就沒有根據。
    """
    probe = [1, 0.55, -0.4, -0.75, 0.2]
    data = run_case("gainBound", h=h, probe=probe)
    assert data["bound"] == pytest.approx(sum(abs(v) for v in h), abs=1e-15)
    assert data["worstPeak"] == pytest.approx(data["bound"], abs=1e-12)


@pytest.mark.parametrize("h", [
    [1, 0, 0.9],
    [1, 0.9, 0.81, 0.729, 0.6561, 0.59049],
    [0.125] * 8,
])
def test_normalising_keeps_the_output_inside_the_input(h):
    """正規化之後，輸出的峰值不超過輸入的峰值。

    這正是「回音疊起來不會削波」那句承諾的內容。⚠️ 注意界是
    **輸入的峰值**而不是 1——正規化保證的是增益 ≤ 1，不是輸出 ≤ 1。
    """
    probe = [1, 0.55, -0.4, -0.75, 0.2]
    data = run_case("gainBound", h=h, probe=probe)
    assert data["normalisedBound"] <= 1 + 1e-12
    assert data["probePeak"] <= data["probeInputPeak"] * (1 + 1e-12)
    # 本來就不會超過 1 的 h 不該被動到（移動平均 Σ|h| = 1）。
    if sum(abs(v) for v in h) <= 1:
        assert data["scale"] == 1


# --- 頻率響應：h 的形狀翻譯成「聽起來怎樣」 -----------------------------------

def test_the_moving_average_has_its_nulls_where_the_theory_says():
    """長度 L 的移動平均在 f = m·f_s/L 上的響應恰好是 0（Dirichlet 核的零點）。

    這是「移動平均是低通」最精確的版本，也是 `responseAt()` 的解析對照：
    Σ_{n<L} e^{-jωn} 是一個等比級數，在 ωL 為 2π 的倍數時分子歸零。
    """
    rate, length = 48000, 8
    h = [1 / length] * length
    nulls = [rate * m / length for m in (1, 2, 3)]
    between = [rate / (2 * length), rate * 1.5 / length]
    data = run_case(
        "frequencyResponse", h=h, sampleRate=rate, frequencies=nulls + between,
    )
    magnitudes = [p["magnitude"] for p in data["points"]]
    for value in magnitudes[: len(nulls)]:
        assert value == pytest.approx(0.0, abs=1e-12)
    for value in magnitudes[len(nulls):]:
        assert value > 0.1, "零點之間不該也是零，否則它就不是一把梳子了"
    assert data["dc"] == pytest.approx(1.0, abs=1e-15)


def test_the_difference_filter_kills_the_low_frequencies_and_keeps_the_high():
    """[1, −1]：直流恰好 0，奈奎斯特恰好 2，中間單調上升。

    |H(ω)| = 2|sin(ω/2)|，所以這三件事是閉式解，不是「大概是這樣」。
    """
    rate = 48000
    h = [1, -1]
    probes = [0, 100, 1000, 6000, 12000, 24000]
    data = run_case("frequencyResponse", h=h, sampleRate=rate, frequencies=probes)
    magnitudes = [p["magnitude"] for p in data["points"]]
    for f, got in zip(probes, magnitudes):
        want = 2 * abs(math.sin(math.pi * f / rate))
        assert got == pytest.approx(want, abs=1e-12), f"{f} Hz 的 |H| 不對"
    assert magnitudes[0] == 0.0
    assert magnitudes[-1] == pytest.approx(2.0, abs=1e-12)
    assert all(b > a for a, b in zip(magnitudes, magnitudes[1:]))


def test_a_band_average_does_not_land_on_a_comb_tooth():
    """⛔ **這一項守的是一個被實際輸出抓到的問題。**

    畫面上原本報的是單一頻率的 |H(f)|，而回音的頻率響應是一把梳子：
    120 ms 的延遲配 200 Hz 與 4000 Hz 時，兩個探測點**恰好都落在齒頂**，
    於是兩欄都印 1.000，讀起來像「這個系統什麼都沒做」。
    改成一整段頻帶的平均之後，數字才回答得了學生真正在問的問題。

    這裡驗兩件事：齒頂那個點確實是 1（所以問題是真的），
    而同一段頻帶的平均明顯小於 1（所以修法是有效的）。
    """
    rate = 48000
    delay = round(0.120 * rate)
    h = [0.0] * (delay + 1)
    h[0], h[delay] = 0.5, 0.5
    data = run_case(
        "frequencyResponse", h=h, sampleRate=rate, frequencies=[200.0, 4000.0],
        band={"from": 150, "to": 250, "points": 33},
    )
    tooth = [p["magnitude"] for p in data["points"]]
    assert tooth[0] == pytest.approx(1.0, abs=1e-9), "200 Hz 應該剛好落在齒頂"
    assert tooth[1] == pytest.approx(1.0, abs=1e-9), "4 kHz 也剛好落在齒頂"
    assert data["band"] < 0.8, "一整段頻帶的平均不該還是 1"
    assert data["band"] > 0.3


# --- LTI：W1 的那張 2×2 表 ---------------------------------------------------

def test_only_the_convolution_passes_both_checks():
    """⛔ **這是第三段整段的內容，也是「為什麼是摺積」的答案。**

    三個系統剛好各自壞在不同的地方，而那是刻意挑的：兩個「✗」各只壞一格，
    所以「線性」與「非時變」在畫面上是**兩件可以分開檢驗的事**，
    不是一團叫做「乖」的東西。

    ⚠️ 界用 1e−12 而不是隨手一個 1e−6：通過的那幾格是浮點捨入的量級
    （1e−16），而失敗的那幾格是 0.1 以上——中間有十個數量級的空間。
    """
    h = [1, 0, 0.6]
    data = run_case("ltiChecks", h=h)
    by_kind = {entry["kind"]: entry for entry in data["systems"]}
    assert set(by_kind) == {"convolution", "clip", "fade"}

    assert by_kind["convolution"]["superposition"] < 1e-12
    assert by_kind["convolution"]["invariance"] < 1e-12

    assert by_kind["clip"]["superposition"] > 0.1, "削波必須明顯地不滿足疊加"
    assert by_kind["clip"]["invariance"] < 1e-12, "削波是逐點的，它是非時變的"

    assert by_kind["fade"]["superposition"] < 1e-12, "漸強增益是線性的"
    assert by_kind["fade"]["invariance"] > 0.05, "漸強增益必須明顯地時變"


def test_the_lti_test_signals_are_chosen_so_the_checks_can_see_anything():
    """⛔ **三個互相牽制的條件，全部由這一項盯著。**

    這一組測試訊號是寫死的，理由是它們必須同時滿足：

      1. 兩條**相加之後**要超過削波門檻——否則削波根本不動作，
         而畫面會顯示「削波是線性的」，一個完全錯誤卻很有說服力的結論。
      2. 兩條**各自**要低於門檻——否則連 T(x₁) 都被削掉，殘差雖然還是非零，
         但原因就不再是疊加性了。
      3. 平移用的那一條尾巴要留夠零——否則「先做系統再平移」會把輸出推出
         陣列外，而那個被截掉的東西會被算成殘差：一個與時變完全無關的假陽性。

    三個條件互相牽制，改動任何一條序列都可能悄悄破壞其中一個，
    **而破壞的症狀是一個看起來很合理的數字**。
    """
    data = run_case("ltiChecks", h=[1, 0, 0.6])
    level = data["clipLevel"]
    assert data["peaks"]["a"] < level, "x1 單獨不得被削"
    assert data["peaks"]["b"] < level, "x2 單獨不得被削"
    assert data["peaks"]["sum"] > level, "x1+x2 必須被削，否則測不出東西"

    probe = data["probes"]["probe"]
    shift = data["shift"]
    assert probe[-shift:] == [0] * shift, "平移探針的尾巴要留夠零"
    assert any(v != 0 for v in probe), "探針不能是全零"


def test_all_three_systems_produce_the_same_length_output():
    """三個系統的輸出長度必須一致，否則殘差根本比不了。

    摺積會長出 M−1 個尾巴，另外兩個因此也把輸入補到同樣長——**補的是 0，
    而 0 對這三個系統都對映到 0**，所以這個補零不會偷偷改變任何一個
    系統的行為。這一項就是在守那句話。
    """
    for h in ([1], [1, 0, 0.6], [0.25] * 4):
        data = run_case("ltiChecks", h=h)
        lengths = {entry["outputLength"] for entry in data["systems"]}
        assert len(lengths) == 1, f"h={h} 時三個系統的輸出長度不一致：{lengths}"
        assert lengths.pop() == len(data["probes"]["a"]) + len(h) - 1


def test_the_two_superposition_curves_coincide_only_for_a_linear_system():
    """畫面上那兩條曲線：LTI 的疊在一起，削波的分得開。"""
    data = run_case("ltiChecks", h=[1, 0, 0.6])
    by_kind = {entry["kind"]: entry for entry in data["systems"]}
    lti = by_kind["convolution"]
    assert lti["together"] == pytest.approx(lti["apart"], abs=1e-12)
    clipped = by_kind["clip"]
    assert clipped["together"] != pytest.approx(clipped["apart"], abs=1e-6)
    # 削波的那一條**不會超過門檻**，而分開做的那一條會——這就是差在哪裡。
    assert max(abs(v) for v in clipped["together"]) <= data["clipLevel"] + 1e-12


@pytest.mark.parametrize("d", [0, 1, 3, 20])
def test_shifting_pushes_right_and_pads_with_zeros(d):
    """平移這個動作本身：往右推 d 格，兩端補零，長度不變。"""
    x = [1, 0.55, -0.4, -0.75, 0.2]
    data = run_case("shiftSequence", x=x, shifts=[d])[0]
    expected = ([0.0] * d + x)[: len(x)]
    assert data["values"] == pytest.approx(expected, abs=0)


# --- 音訊那一側的訊號 ---------------------------------------------------------

@pytest.mark.parametrize("rate", [44100, 48000])
def test_the_audio_signals_are_built_at_the_rate_they_are_given(rate):
    """⛔ **絕不寫死取樣率**（§8.5）。

    同一組毫秒參數在兩個取樣率下必須給出**不同的樣本數、相同的秒數**——
    這是「畫面上寫 120 ms 而耳朵聽到 110 ms」那個錯誤唯一的看守點。
    """
    data = run_case(
        "audioSignals", sampleRate=rate,
        clickMillis=1, pluckSeconds=0.35, gapSeconds=0.8,
    )
    assert data["clickLength"] == round(rate / 1000)
    assert data["pluckLength"] == round(0.35 * rate)
    assert data["paddedLength"] == data["clickLength"] + round(0.8 * rate)
    assert data["paddedTail"] == 0, "補的必須是靜音"


def test_the_click_is_a_smooth_bump_rather_than_a_step():
    """click 是升餘弦的一個半週期：兩端接近 0、峰值接近 1、面積為長度的一半。

    兩端不歸零的話，播放的迴圈接縫上會有一個階躍——那是一聲真的爆音，
    而且它會被誤認成「摺積的結果」。

    ⚠️ **峰值是 0.9997 而不是 1，這是對的**，而且它值得寫下來：包絡取樣在
    半格上（`(i + 0.5) / n`），所以沒有任何一個樣本落在餘弦的頂點。
    半格偏移是刻意的——不偏的話第一個樣本恰好是 0，那一格白給。
    代價就是峰值差了 0.03%，而那在聽覺上不存在。
    """
    rate = 48000
    data = run_case(
        "audioSignals", sampleRate=rate,
        clickMillis=2, pluckSeconds=0.1, gapSeconds=0.1,
    )
    assert 0.999 < data["clickPeak"] <= 1.0
    for value in data["clickEnds"]:
        assert abs(value) < 0.02, "click 的兩端必須接近 0"
    # 0.5 − 0.5cos 在一個週期上的平均恰好是 0.5。
    assert data["clickSum"] == pytest.approx(data["clickLength"] / 2, rel=1e-6)


def test_the_plucked_note_actually_dies_away():
    """撥弦音必須真的衰減——回音只有在安靜的背景上才聽得見。

    這不是美感問題：一個一直響著的正弦被加上 120 ms 的回音之後，
    聽起來只是「大聲了一點」，而這一頁的第二段就白做了。
    """
    data = run_case(
        "audioSignals", sampleRate=48000,
        clickMillis=1, pluckSeconds=0.4, gapSeconds=0.1,
    )
    assert data["pluckPeak"] > 0.5
    assert data["pluckLastQuarterPeak"] < 0.15 * data["pluckFirstQuarterPeak"]


# --- 繪製層：重疊區塊的幾何（§8.4：斷言資料，不斷言像素）--------------------

def test_the_overlap_band_covers_the_right_part_of_the_canvas():
    """陰影帶的左右緣要落在對應的資料座標上，上下要撐滿繪圖區。"""
    pad = {"left": 40, "right": 10, "top": 12, "bottom": 20}
    data = run_case(
        "overlapRegion",
        t0=-0.5, t1=7.5, vMin=-1, vMax=1, width=800, height=200, pad=pad,
        spans=[[1, 4], [0, 0], [2.5, 6.5]],
    )
    inner_width = 800 - pad["left"] - pad["right"]
    for rect, (from_, to) in zip(data, ([1, 4], [0, 0], [2.5, 6.5])):
        assert rect["y"] == pad["top"]
        assert rect["height"] == 200 - pad["top"] - pad["bottom"]
        expected_x = pad["left"] + ((from_ + 0.5) / 8) * inner_width
        assert rect["x"] == pytest.approx(expected_x, abs=1e-9)
        assert rect["width"] == pytest.approx(((to - from_) / 8) * inner_width, abs=1e-9)
        # 一定要留在畫布內，否則它會蓋掉座標軸標籤。
        assert rect["x"] >= pad["left"] - 1e-9
        assert rect["x"] + rect["width"] <= 800 - pad["right"] + 1e-9


def test_an_empty_overlap_has_zero_width_rather_than_a_negative_one():
    """沒有重疊時寬度是 0，不是負數也不是 null。

    動畫會掃過兩端，而那裡本來就沒有重疊。回傳 0 讓繪製端不必寫特例——
    負寬度在 canvas 上會畫出一個往左長的矩形，看起來像陰影跑到別的地方去了。
    """
    pad = {"left": 40, "right": 10, "top": 12, "bottom": 20}
    data = run_case(
        "overlapRegion",
        t0=0, t1=10, vMin=-1, vMax=1, width=800, height=200, pad=pad,
        spans=[[5, 3], [7, 2]],
    )
    for rect in data:
        assert rect["width"] == 0
        assert rect["height"] == 200 - pad["top"] - pad["bottom"]


# --- 第 5 類：golden vector（SymPy 的多項式乘法）-----------------------------

def test_the_golden_convolutions_match_the_javascript():
    """golden 檔裡每一筆摺積都要與 JS 逐格相符。

    這一項與上面「對照多項式乘法」那一組**不重複**：那一組是每次跑測試
    現算的，這一項比的是一份**commit 進版本控制的**答案。前者守的是
    「今天的實作對不對」，後者守的是「今天的實作與當初驗過的那一版一樣」——
    也就是回歸。
    """
    payload = golden()["convolution"]
    assert payload["cases"], "golden 檔裡沒有摺積的 case"
    for case in payload["cases"]:
        data = run_case("convolve", x=case["x"], h=case["h"])
        assert data["y"] == pytest.approx(case["y"], abs=1e-12), case["label"]
        assert data["length"] == len(case["y"])
        assert data["total"] == pytest.approx(
            case["sum_x"] * case["sum_h"], abs=1e-12,
        ), case["label"]


def test_the_golden_trapezium_shapes_match_the_javascript():
    """golden 檔的梯形三個數字（長度、峰值、平台寬）逐一對 JS。"""
    payload = golden()["convolution"]["trapezium"]
    for key, want in payload.items():
        l1, l2 = (int(part) for part in key.split("x"))
        data = run_case("convolve", x=[1] * l1, h=[1] * l2)
        y = data["y"]
        assert len(y) == want["length"], key
        assert max(y) == pytest.approx(want["peak"], abs=1e-12), key
        plateau = sum(1 for v in y if abs(v - want["peak"]) < 1e-12)
        assert plateau == want["plateau_width"], key


def test_the_golden_moving_average_nulls_are_really_nulls_in_the_javascript():
    """golden 檔算出來的零點位置，在 JS 的 `responseAt()` 上必須也是零。"""
    payload = golden()["convolution"]["moving_average_nulls"]
    length = payload["length"]
    h = [1 / length] * length
    data = run_case(
        "frequencyResponse", h=h, sampleRate=payload["sample_rate"],
        frequencies=payload["null_hz"],
    )
    for point in data["points"]:
        assert point["magnitude"] == pytest.approx(0.0, abs=1e-12), point["f"]


# ============================================================================
# 脈衝寬度與時頻取捨（2S11，PLAN §8.2.1 第 5 列；課程 W4）
#
# ⚠️ **這一組與前面每一組有一個結構上的差別，先講清楚容忍度怎麼定的。**
#
# 前面幾組比的是**離散的和**：兩邊都是有限次加法，所以界拉到 1e−12 是合理的
# （2S10 那一輪還特地把一個隨手的 1e−6 收緊到 1e−12）。這裡不一樣——
# 瀏覽器那一側跑的是**中點法則的數值積分**，它本來就有一個與格距有關的誤差。
#
# 所以這一組分成兩層，而**兩層的界差十個數量級**：
#
#   1. **閉合式**（`normalisedPulseSpectrum` 那四行）對照 **SymPy 對定義式
#      積出來的精確值**——這一層要求 1e−12。它抓的是「係數抄錯」。
#   2. **數值積分**對照閉合式——這一層的界是 0.1%–1%，而**那個界本身就是
#      展示的內容**（頁面上有一列讀數印著它）。它抓的是「積分寫錯」。
#
# 把兩層混成一項的話只能取比較鬆的界，於是第 1 類的錯誤會躲在第 2 類的
# 誤差後面——而那正是這一頁最不能有的失敗方式。
# ============================================================================

PULSE_SHAPES_ALL = ["rectangle", "triangle", "cosine", "gaussian"]


def symbolic_transform(shape: str, width, frequency):
    """X(f) = ∫x(t)e^{−2πift}dt，**由 SymPy 對定義式積分**。

    ⛔ 刻意與 `scripts/dsp_reference.py` 用不同的方法（那邊是 mpmath 的
    tanh-sinh 數值積分，這邊是符號積分），也刻意不 import 它——
    測試相依於產生 golden 檔的程式碼的話，兩者一起錯的時候沒有東西會變紅。
    """
    t = sp.Symbol("t", real=True)
    T = sp.nsimplify(width, rational=True)
    f = sp.nsimplify(frequency, rational=True)
    kernel = sp.exp(-2 * sp.pi * sp.I * f * t)
    if shape == "rectangle":
        expr = sp.integrate(kernel, (t, -T / 2, T / 2))
    elif shape == "triangle":
        expr = (sp.integrate((1 + 2 * t / T) * kernel, (t, -T / 2, 0))
                + sp.integrate((1 - 2 * t / T) * kernel, (t, 0, T / 2)))
    elif shape == "cosine":
        expr = sp.integrate(sp.cos(sp.pi * t / T) ** 2 * kernel, (t, -T / 2, T / 2))
    elif shape == "gaussian":
        expr = sp.integrate(sp.exp(-sp.pi * t**2 / T**2) * kernel, (t, -sp.oo, sp.oo))
    else:
        raise ValueError(shape)
    return complex(sp.N(sp.simplify(expr), 30))


# --- 第 1 層：四個閉合式對照定義式的積分 -------------------------------------

@pytest.mark.parametrize("shape", PULSE_SHAPES_ALL)
def test_the_closed_form_matches_the_defining_integral(shape):
    """⛔ **這一組裡最強的一項。**

    畫面上那條虛線是四行閉合式；這裡把同一個 X(f) 交給 SymPy 對
    ∫x(t)e^{−2πift}dt 真的積一次分。兩條路徑沒有共用任何程式碼，
    所以「sinc 的分母寫成 πfT 還是 2πfT」「三角是 sinc² 還是 sinc」
    「高斯的 π 正規化跑掉了」這幾種錯法都躲不掉。
    """
    width = 0.004
    probes = [0.0, 125.0, 250.0, 375.0, 640.0]
    data = run_case("pulseSpectrum", shape=shape, width=width, frequencies=probes)
    for f, got in zip(probes, data["closed"]["re"]):
        want = symbolic_transform(shape, width, f).real
        assert got == pytest.approx(want, abs=1e-12 * width), f"{shape} 在 {f} Hz"
    # 實偶函數的變換是實的。虛部不是 0 就是指數的正負號或原點放錯了。
    for value in data["closed"]["im"]:
        assert abs(value) < 1e-18


def test_the_raised_cosine_is_one_half_where_its_formula_divides_by_zero():
    """⛔ **這一項守著一個實際發生過的錯誤，而且它只在一格上出錯。**

    升餘弦的閉合式是 sinc(u)/(1 − u²)，在 u = ±1 分子分母同時歸零。
    極限是 **1/2**（羅必達：sinc 在 u = 1 的導數是 −1，分母的是 −2），
    而第一版寫成 π/4 ≈ 0.785。

    那個錯誤只在 u 恰好等於 ±1 的那一格生效，其餘每一格都是對的——
    也就是說**它只在 f_max·T 剛好是 1 的時候現形**（0.5 ms 的脈衝配
    2 kHz 的頻率軸就是），症狀是曲線兩端各翹起一格。
    抓到它的是「數值積分與閉合式的差距」那個讀數跳到 28%。
    """
    data = run_case("pulseNormalised", shape="cosine", us=[-1.0, -0.999, 0.999, 1.0])
    assert data["g"][0] == pytest.approx(0.5, abs=1e-12)
    assert data["g"][3] == pytest.approx(0.5, abs=1e-12)
    # 兩側逼近的值要與極限連得起來，否則那一格就是一個孤立的補丁。
    assert data["g"][1] == pytest.approx(0.5, abs=1e-3)
    assert data["g"][2] == pytest.approx(0.5, abs=1e-3)


def test_the_gaussian_is_its_own_transform():
    """自對偶：T = 1 時 exp(−πt²) 的變換**逐點等於它自己**。

    這是這一頁最漂亮的一格，而它只在 π 正規化之下成立——換成
    exp(−t²/2σ²) 就會差一個 σ√(2π)。所以這一項同時是「別去動那個正規化」
    的看守。
    """
    probes = [0.0, 0.25, 0.5, 1.0, 1.5]
    data = run_case("pulseSpectrum", shape="gaussian", width=1.0, frequencies=probes)
    for f, got in zip(probes, data["closed"]["re"]):
        assert got == pytest.approx(math.exp(-math.pi * f * f), abs=1e-12)
    # 而且它就是時域那條曲線在同一個引數上的值。
    shaped = run_case("pulseShape", shape="gaussian", width=1.0, times=probes)
    assert shaped["envelope"] == pytest.approx(data["closed"]["re"], abs=1e-12)


# --- 第 2 層：數值積分對照閉合式 ---------------------------------------------

@pytest.mark.parametrize("shape", PULSE_SHAPES_ALL)
def test_the_numerical_integral_lands_on_the_closed_form(shape):
    """執行期畫的是中點法則的積分，它必須落在閉合式上——**到一個說得出口
    的精度**，而那個精度就是畫面上那一列讀數。

    界取 1%：實測最差的是「高斯配 2 kHz 載波」的 0.5%（格點數被
    效能預算擋在 3072），最好的是「矩形不平移」的 1e−13
    （格線恰好落在兩個邊緣上，所以階梯函數就是矩形本身）。
    """
    frequencies = [i * 50.0 for i in range(-40, 41)]
    data = run_case(
        "pulseSpectrum", shape=shape, width=0.006, frequencies=frequencies,
        shift=0.0015, carrierHz=880,
    )
    assert data["agreement"] < 0.01, f"{shape} 的數值積分與閉合式差太多"


@pytest.mark.parametrize("shape", PULSE_SHAPES_ALL)
def test_refining_the_grid_moves_the_numerical_integral_closer(shape):
    """⛔ **這一項比「差距小於某個界」強，而那個差別值得寫下來。**

    一個界只說「現在夠準」。收斂性說的是「**它是同一個積分**」——
    一個係數寫錯的實作可以碰巧落在界內，但它不會隨著格點加密而
    越來越接近閉合式，它會停在自己那個錯的值上。
    """
    frequencies = [i * 100.0 for i in range(-8, 9)]
    coarse = run_case(
        "pulseSpectrum", shape=shape, width=0.006, frequencies=frequencies,
        shift=0.0015, carrierHz=880, samples=384,
    )
    fine = run_case(
        "pulseSpectrum", shape=shape, width=0.006, frequencies=frequencies,
        shift=0.0015, carrierHz=880, samples=6144,
    )
    assert fine["agreement"] < coarse["agreement"] / 4, (
        f"{shape}：格點加密 16 倍，誤差沒有跟著掉"
    )


# --- 教學主張一：窄與寬是同一件事 ---------------------------------------------

@pytest.mark.parametrize("shape", PULSE_SHAPES_ALL)
def test_halving_the_width_doubles_every_frequency_in_the_spectrum(shape):
    """縮放性質 x(at) ↔ X(f/a)/|a|：**這一頁的第一個、也是主要的主張。**

    三個量一起檢查，因為單獨看任何一個都可以被別的錯誤湊出來：
    半功率頻寬加倍、第一個零點加倍、而峰值（＝面積）減半。
    """
    data = run_case("pulseWidths", shape=shape, widths=[0.008, 0.004, 0.002])
    for wide, narrow in zip(data, data[1:]):
        assert narrow["bandwidth"] == pytest.approx(2 * wide["bandwidth"], rel=1e-12)
        assert narrow["area"] == pytest.approx(wide["area"] / 2, rel=1e-12)
        if wide["firstNull"] is not None:
            assert narrow["firstNull"] == pytest.approx(2 * wide["firstNull"], rel=1e-12)


@pytest.mark.parametrize("shape", PULSE_SHAPES_ALL)
def test_the_bandwidth_times_the_width_is_a_constant_of_the_shape(shape):
    """B·T 只與形狀有關，與寬度無關——**那就是表格最後一欄不動的原因**。

    參考值不是抄來的：這裡用 Python 自己在閉合式上二分找一次
    （JS 那一側也是二分，但寫在另一個語言、另一個迴圈裡），
    再確認 B·T 對五個寬度都是同一個數字。
    """
    def g(u):
        if u == 0:
            return 1.0
        s = math.sin(math.pi * u) / (math.pi * u)
        if shape == "rectangle":
            return s
        if shape == "triangle":
            half = u / 2
            return (math.sin(math.pi * half) / (math.pi * half)) ** 2
        if shape == "cosine":
            return s / (1 - u * u) if abs(1 - u * u) > 1e-9 else 0.5
        return math.exp(-math.pi * u * u)

    lo, hi = 0.0, {"rectangle": 1.0, "triangle": 2.0, "cosine": 2.0, "gaussian": 3.0}[shape]
    for _ in range(200):
        mid = (lo + hi) / 2
        if g(mid) > 1 / math.sqrt(2):
            lo = mid
        else:
            hi = mid
    expected = 2 * (lo + hi) / 2

    widths = [0.0005, 0.002, 0.008, 0.014, 0.020]
    data = run_case("pulseWidths", shape=shape, widths=widths)
    for row in data:
        assert row["bandwidthTimesWidth"] == pytest.approx(expected, rel=1e-9)


def test_a_narrower_pulse_really_does_widen_the_spectrum_on_a_fixed_axis():
    """⛔ **這一項守的是 `pulse.js` 檔頭那條規則：座標軸不得自動縮放。**

    「把座標軸縮到剛好裝得下資料」是繪圖程式最像好意的一個改動，
    而它會把這一頁的內容刪掉——脈衝與頻譜都會看起來一樣寬。
    這裡檢查的是那件事在數字上的形式：**同一個頻率軸**之下，
    脈衝變窄時落在軸內的能量比例必須上升。
    """
    frequencies = [i * 25.0 for i in range(-40, 41)]      # 固定的 ±1 kHz
    shares = []
    for width in (0.016, 0.008, 0.004, 0.002):
        data = run_case(
            "pulseSpectrum", shape="rectangle", width=width, frequencies=frequencies,
        )
        peak = data["peak"]
        inside = sum(m for m in data["closed"]["magnitude"] if m > peak / 100)
        shares.append(inside / (peak * len(frequencies)))
    assert all(b > a for a, b in zip(shares, shares[1:])), (
        f"脈衝變窄時頻譜沒有變寬：{shares}"
    )


# --- 教學主張二：位移只改相位 -------------------------------------------------

@pytest.mark.parametrize("shape", PULSE_SHAPES_ALL)
@pytest.mark.parametrize("shift", [0.001, -0.0025])
def test_a_shift_leaves_every_magnitude_alone(shape, shift):
    """位移性質的前半：|X(f)e^{−2πift₀}| = |X(f)|，**逐點**。

    界用 0（精確相等）而不是一個小數：閉合式那一側是把同一個實數乘上
    cos 與 sin 再取 hypot，而 `Math.hypot(a·cosθ, a·sinθ)` 對 |a| 是
    精確的嗎？不保證，所以留 1e−18 的餘裕——但那已經比任何真實的
    幅度變化小十幾個數量級。
    """
    frequencies = [i * 50.0 for i in range(-30, 31)]
    data = run_case(
        "pulseSpectrum", shape=shape, width=0.005, frequencies=frequencies, shift=shift,
    )
    assert data["shiftGap"] < 1e-18
    assert data["closed"]["magnitude"] == pytest.approx(
        data["unshiftedMagnitude"], abs=1e-18,
    )


def test_a_shift_tilts_the_phase_by_exactly_minus_two_pi_f_t_nought():
    """位移性質的後半：相位多的**恰好**是那條直線，而斜率就是 −2πt₀。

    只驗「幅度沒動」是不夠的——一個把相位也一起丟掉的實作會通過那一項。
    這裡對每一格檢查 φ_shifted − φ_unshifted ≡ −2πft₀ (mod 2π)。
    """
    shift = 0.0017
    frequencies = [i * 37.0 for i in range(-12, 13)]
    shifted = run_case(
        "pulseSpectrum", shape="gaussian", width=0.004,
        frequencies=frequencies, shift=shift,
    )
    still = run_case(
        "pulseSpectrum", shape="gaussian", width=0.004, frequencies=frequencies,
    )
    for f, a, b in zip(frequencies, shifted["closed"]["phase"], still["closed"]["phase"]):
        gap = (a - b + math.pi) % (2 * math.pi) - math.pi
        want = (-2 * math.pi * f * shift + math.pi) % (2 * math.pi) - math.pi
        assert gap == pytest.approx(want, abs=1e-9), f"{f} Hz 的相位斜率不對"


def test_the_numerical_integral_sees_the_shift_the_same_way():
    """同一件事，換數值積分那一條路徑再驗一次。

    ⚠️ **這一項不是重複**：閉合式那一側的「位移只乘一個相位因子」是**寫死的**
    （`analyticSpectrumAt` 就是那樣寫的），所以它證明不了訊號真的被移動了。
    數值積分那一側是把**平移過的樣本**餵進去積分——它會抓到
    「`signalAt()` 移動了包絡卻沒有移動載波」這種錯誤，而那正是
    `signal.js` 註解裡點名的那個會讓幅度譜隨 t₀ 晃動的寫法。
    """
    frequencies = [i * 60.0 for i in range(-20, 21)]
    common = dict(shape="cosine", width=0.006, frequencies=frequencies, carrierHz=800)
    still = run_case("pulseSpectrum", shift=0.0, **common)
    moved = run_case("pulseSpectrum", shift=0.002, **common)
    peak = still["peak"]
    for a, b in zip(still["numeric"]["magnitude"], moved["numeric"]["magnitude"]):
        assert abs(a - b) < 0.01 * peak, "平移之後數值積分的幅度譜動了"


# --- 教學主張三：調變把頻譜搬走 -----------------------------------------------

def test_the_carrier_moves_the_spectrum_and_halves_it():
    """調變性質：x·cos(2πf_c t) ↔ ½[X(f−f_c) + X(f+f_c)]。

    兩件事一起驗，因為只驗一件會漏掉另一件：**位置**搬到 ±f_c，
    而**高度**是一半。少了後者，一個「搬過去但沒有除以 2」的實作會通過。

    ⚠️ **用高斯而不是矩形，理由不是方便，是下一項測的那件事**：兩份拷貝
    會相加，所以「恰好一半」只在另一份拷貝在這裡等於 0 時才成立。
    高斯的尾巴衰減得比任何冪次都快（f = 2f_c 處是 1e−300 的量級），
    所以它是唯一一個可以用 1e−12 這種界去驗的形狀。
    """
    carrier = 900.0
    width = 0.004
    offsets = [0.0, 125.0, 250.0, 375.0]
    plain = run_case("pulseSpectrum", shape="gaussian", width=width, frequencies=offsets)
    moved = run_case(
        "pulseSpectrum", shape="gaussian", width=width, carrierHz=carrier,
        frequencies=[carrier + d for d in offsets],
    )
    for base, shifted in zip(plain["closed"]["magnitude"], moved["closed"]["magnitude"]):
        assert shifted == pytest.approx(base / 2, abs=1e-15)
    # 而且原本的位置現在幾乎是空的（兩個邊帶之間隔得夠遠）。
    middle = run_case(
        "pulseSpectrum", shape="gaussian", width=width, carrierHz=carrier,
        frequencies=[0.0],
    )
    assert middle["closed"]["magnitude"][0] < plain["peak"] / 20


def test_the_two_sidebands_add_up_instead_of_ignoring_each_other():
    """⛔ **這一項守著一個被測試抓出來的錯誤，而那個錯誤原本印在畫面上。**

    調變的等式是**兩份拷貝相加**，而不是「把頻譜搬過去」。矩形的旁瓣
    以 1/f 衰減，所以在 f = +f_c 那裡，下邊帶 ½X(f + f_c) 還剩下
    ½X(2f_c) 沒有歸零。T = 4 ms 配 900 Hz 時，上邊帶的峰值因此是
    面積的一半**再少 2.6%**。

    原本 `pulse.js` 把峰值寫成 `area / 2`，於是三件事同時安靜地錯掉：
    縱軸的頂端與曲線對不上、讀數印出一個比實際高 2.6% 的高度、
    而「數值積分與閉合式的差距」那一列因為分母不對而整列偏低。
    現在峰值是求值求出來的，而畫面上把兩個數字並排顯示。

    這裡驗的是那個差額**恰好等於**另一份拷貝的貢獻——也就是說它不是
    誤差，是一項可以寫下來的東西。
    """
    carrier = 900.0
    width = 0.004
    offsets = [0.0, 125.0, 375.0]
    plain = run_case(
        "pulseSpectrum", shape="rectangle", width=width,
        frequencies=[d for d in offsets] + [2 * carrier + d for d in offsets],
    )
    moved = run_case(
        "pulseSpectrum", shape="rectangle", width=width, carrierHz=carrier,
        frequencies=[carrier + d for d in offsets],
    )
    near = plain["closed"]["re"][: len(offsets)]
    far = plain["closed"]["re"][len(offsets):]
    for base, other, got in zip(near, far, moved["closed"]["re"]):
        assert got == pytest.approx((base + other) / 2, abs=1e-15)

    # 而那個差額是看得見的大小，不是捨入——這正是它必須被說出來的理由。
    assert abs(moved["closed"]["magnitude"][0] - plain["peak"] / 2) > 0.02 * plain["peak"] / 2


# --- 不確定性：Δt·Δf 與那個下界 -----------------------------------------------

@pytest.mark.parametrize("shape", ["triangle", "cosine", "gaussian"])
def test_the_rms_widths_match_the_integrals_that_define_them(shape):
    """Δt 與 Δf 的閉合式係數，對照 SymPy 對定義式積分。

    Δf 用的是 Parseval 的形式（∫f²|X|²df = ∫|x′|²dt/4π²），因為在時域
    積分不必截斷；而**這正是矩形不在這張清單上的原因**，見下一項。
    """
    t = sp.Symbol("t", real=True)
    T = sp.Symbol("T", positive=True)
    if shape == "gaussian":
        expr = sp.exp(-sp.pi * t**2 / T**2)
        limits, factor = (t, -sp.oo, sp.oo), 1
    else:
        expr = (1 - 2 * t / T) if shape == "triangle" else sp.cos(sp.pi * t / T) ** 2
        limits, factor = (t, 0, T / 2), 2
    energy = factor * sp.integrate(expr**2, limits)
    delta_t = sp.sqrt(factor * sp.integrate(t**2 * expr**2, limits) / energy)
    delta_f = sp.sqrt(factor * sp.integrate(sp.diff(expr, t) ** 2, limits) / energy) / (2 * sp.pi)

    width = 0.004
    data = run_case("pulseWidths", shape=shape, widths=[width])[0]
    assert data["deltaT"] == pytest.approx(float(delta_t.subs(T, width)), rel=1e-12)
    assert data["deltaF"] == pytest.approx(float(delta_f.subs(T, width)), rel=1e-12)


def test_the_rectangle_reports_no_rms_bandwidth_rather_than_zero():
    """⛔ **這一項守的是一個會給出「恰好相反」的答案的陷阱。**

    Δf² = (1/4π²)∫|x′|²dt / ∫|x|²dt 這個式子，套在矩形上會得到 **0**——
    它只積得到支撐**內部**，而矩形在內部的導數恆為 0；兩個邊緣是
    delta 函數，符號積分與格點上的差分都看不到它們。
    於是畫面上會出現「矩形的頻寬是零」，而事實是它的 RMS 頻寬**發散**
    （旁瓣只以 1/f 衰減，∫f²|X|²df 不收斂）。

    ⚠️ 這不是一個假想的風險：本輪用 SymPy 產生這幾個係數時，
    矩形那一格吐出來的就是 0。所以 `PULSE_SHAPES` 裡寫的是 `null`，
    而畫面上顯示的是 "not finite" 加上原因。
    """
    data = run_case("pulseWidths", shape="rectangle", widths=[0.004])[0]
    assert data["deltaF"] is None, "矩形的 RMS 頻寬不得是一個數字，尤其不得是 0"
    assert data["product"] is None
    # Δt 仍然是有限的、而且是對的：發散的只有頻域那一半。
    assert data["deltaT"] == pytest.approx(0.004 / (2 * math.sqrt(3)), rel=1e-12)


def test_only_the_gaussian_reaches_the_uncertainty_floor():
    """Δt·Δf ≥ 1/(4π)，而**高斯取到等號**——那是它為什麼特別。

    順帶驗一件教學上同樣重要的事：三個有限的乘積由小到大就是
    「時域越平滑，越接近下界」的順序。這條線把四個形狀串成一句話，
    而不是四個各自為政的例子。
    """
    bound = 1 / (4 * math.pi)
    products = {}
    for shape in ["triangle", "cosine", "gaussian"]:
        row = run_case("pulseWidths", shape=shape, widths=[0.004])[0]
        assert row["bound"] == pytest.approx(bound, rel=1e-15)
        assert row["product"] >= bound - 1e-15, f"{shape} 掉到下界以下了"
        products[shape] = row["product"]
    assert products["gaussian"] == pytest.approx(bound, rel=1e-14)
    assert products["gaussian"] < products["cosine"] < products["triangle"]


# --- 第一個零點 ---------------------------------------------------------------

@pytest.mark.parametrize("shape,factor", [("rectangle", 1), ("triangle", 2), ("cosine", 2)])
def test_the_first_zero_is_where_the_readout_says_it_is(shape, factor):
    """讀數說「第一個零點在 n/T」，那裡的 |X| 就必須真的是 0。

    這一項把兩件事綁在一起：`firstNullFrequency()` 回報的位置，
    與閉合式在那個位置的值。分開的話，一個「位置對、值不對」或
    「值對、位置差一倍」的實作都測不出來。
    """
    width = 0.004
    data = run_case("pulseWidths", shape=shape, widths=[width])[0]
    assert data["firstNull"] == pytest.approx(factor / width, rel=1e-12)
    at_null = run_case(
        "pulseSpectrum", shape=shape, width=width,
        frequencies=[data["firstNull"], data["firstNull"] / 2],
    )
    assert at_null["closed"]["magnitude"][0] < 1e-15 * data["area"]
    assert at_null["closed"]["magnitude"][1] > 0.05 * data["area"], (
        "零點之間不該也是零"
    )


def test_the_gaussian_has_no_zero_at_all():
    """高斯的 `firstNull` 是 null，不是一個很大的數字。

    回一個大數字的話，畫面上會出現「第一個零點在 87 kHz」——
    一句聽起來很精確的假話。
    """
    data = run_case("pulseWidths", shape="gaussian", widths=[0.004])[0]
    assert data["firstNull"] is None


# --- 計算預算：兩支決定「一次重繪要做多少事」的純函式 -------------------------

def test_the_work_per_redraw_stays_inside_its_budget():
    """⛔ 這兩支函式決定重繪要花多久，而 §8.5 給的預算是 30–50 ms。

    三個性質，每一個都對應一種會安靜地壞掉的方式：
      * 載波越高，積分格點越多（否則被積函數自己取樣不足，
        症狀是頻譜的高頻端偏低——沒有人看得出來）。
      * 格點越多，頻率點數越少（總工作量有上限，否則拖滑桿會卡）。
      * 頻率點數恆為奇數（f = 0 必須落在格點上，峰值就在那裡）。
    """
    cases = [
        {"shape": "rectangle", "width": 0.0005, "carrierHz": 0},
        {"shape": "rectangle", "width": 0.020, "carrierHz": 0},
        {"shape": "rectangle", "width": 0.020, "carrierHz": 2000},
        {"shape": "gaussian", "width": 0.020, "carrierHz": 0},
        {"shape": "gaussian", "width": 0.020, "carrierHz": 2000},
        {"shape": "cosine", "width": 0.008, "carrierHz": 880},
    ]
    rows = run_case("pulseBudget", cases=cases)
    by_key = {(r["shape"], r["width"], r["carrierHz"]): r for r in rows}
    quiet = by_key[("rectangle", 0.020, 0)]
    loud = by_key[("rectangle", 0.020, 2000)]
    assert loud["samples"] > quiet["samples"], "載波變高，格點數必須跟著變多"
    assert loud["points"] <= quiet["points"], "格點變多，頻率點數必須讓位"
    for row in rows:
        assert row["points"] % 2 == 1, "頻率點數必須是奇數"
        assert 240 <= row["points"] <= 901
        assert 512 <= row["samples"] <= 3072
        assert row["work"] <= 1.4e6, f"{row} 的重繪成本超出預算"


# --- 音訊那一側 ---------------------------------------------------------------

@pytest.mark.parametrize("rate", [44100, 48000])
def test_the_burst_sits_in_the_middle_with_silence_at_both_ends(rate):
    """⛔ **絕不寫死取樣率**（§8.5），而且兩端一定要是靜音。

    兩端不靜音的話，`loop = true` 的接縫上會有一個階躍——那是一聲爆音，
    而它會被誤認成「這就是短脈衝的聲音」，也就是這一頁要教的東西。
    """
    data = run_case(
        "pulseAudio", shape="gaussian", width=0.004, carrierHz=880,
        seconds=0.6, sampleRate=rate,
    )
    assert data["frames"] == round(0.6 * rate)
    assert 0.9 < data["peak"] <= 1.0
    assert data["edgePeak"] < 1e-6, "迴圈的接縫上必須是靜音"


def test_a_wider_pulse_carries_more_energy_at_the_same_height():
    """脈衝變寬，能量變多——**而這正是「聽起來變大聲」的原因**。

    寫成一項測試是因為 `rebuildSound()` 刻意**不做**逐次正規化，
    而那個決定只有在「能量真的隨寬度變化」時才有意義。
    自動增益會把這一格抹掉（2S5 與 2S10 都為同一件事打過一次）。
    """
    energies = []
    for width in (0.001, 0.004, 0.016):
        data = run_case(
            "pulseAudio", shape="gaussian", width=width, carrierHz=880,
            seconds=0.6, sampleRate=48000,
        )
        energies.append(data["energy"])
    assert all(b > 3 * a for a, b in zip(energies, energies[1:]))


def test_without_a_carrier_the_buffer_is_completely_silent():
    """沒有載波就沒有聲音，而且是**乾淨的零**，不是很小的東西。

    這一頁在載波關掉時會停用播放並說明原因（規則 4：不做靜默降級）。
    這一項確認那個說明不是裝飾——底下真的沒有東西可播。
    """
    data = run_case(
        "pulseAudio", shape="rectangle", width=0.008, carrierHz=0,
        seconds=0.6, sampleRate=48000,
    )
    assert data["peak"] == 0.0
    assert data["energy"] == 0.0


# --- 繪製層：斷言幾何，不斷言像素（§8.4）--------------------------------------

def test_the_phase_curve_is_cut_where_it_wraps_round():
    """相位在 ±π 之間繞回來，而那些跳不得被畫成一條垂直線。

    畫成垂直線的話，圖上會出現一排根本不存在的直線，而學生要讀的
    斜率就被蓋掉了。這裡驗三件事：段數等於跳的次數加一、
    每一段內部沒有任何一步超過門檻、以及所有的點都還在
    （切開不得順手扔掉資料）。
    """
    pad = {"left": 40, "right": 10, "top": 12, "bottom": 20}
    height, span = 200, 2 * math.pi
    times = [i * 1.0 for i in range(9)]
    values = [-3.0, -1.0, 1.0, 3.0, -3.0, -1.0, 1.0, 3.0, -3.0]   # 兩次繞回
    inner = height - pad["top"] - pad["bottom"]
    max_rise = (math.pi / span) * inner
    segments = run_case(
        "phaseSegments", t0=0, t1=8, vMin=-math.pi, vMax=math.pi,
        width=800, height=height, pad=pad, times=times, values=values,
        maxRise=max_rise,
    )
    assert len(segments) == 3
    # 分割的性質：點一個都沒有少。長度 1 的段畫不出線，但它仍然要回傳，
    # 否則這一行就斷言不了任何東西（見 `splitOnJumps()` 的說明）。
    assert sum(len(s) for s in segments) == len(times)
    assert len(segments[-1]) == 1
    for segment in segments:
        for a, b in zip(segment, segment[1:]):
            assert abs(b[1] - a[1]) <= max_rise + 1e-9


def test_a_curve_with_no_jumps_comes_back_as_one_piece():
    """沒有跳點時不得被切開——切開是為了跳點，不是為了每一段都短。"""
    pad = {"left": 40, "right": 10, "top": 12, "bottom": 20}
    times = [i * 1.0 for i in range(6)]
    values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    segments = run_case(
        "phaseSegments", t0=0, t1=5, vMin=-1, vMax=1,
        width=800, height=200, pad=pad, times=times, values=values, maxRise=50,
    )
    assert len(segments) == 1
    assert len(segments[0]) == len(times)


# --- 第 5 類：golden vector（mpmath 的高精度積分）-----------------------------

def test_the_golden_pulse_spectra_match_the_javascript():
    """golden 檔裡每一格 X(f) 都要與 JS 的閉合式相符。

    ⚠️ 與上面「對照 SymPy 符號積分」那一組**不重複**：那一組是每次跑
    測試現算的（守「今天的實作對不對」），這一項比的是一份 commit
    進版本控制的答案（守「今天的實作與當初驗過的那一版一樣」）。
    而且 golden 那一側用的是 mpmath 的 tanh-sinh 數值積分，
    與符號積分又是不同的一條路。
    """
    payload = golden()["pulse"]
    assert payload["spectra"], "golden 檔裡沒有脈衝的 case"
    for case in payload["spectra"]:
        data = run_case(
            "pulseSpectrum", shape=case["shape"], width=case["width"],
            frequencies=case["frequencies"],
        )
        for f, want, got in zip(
            case["frequencies"], case["real"], data["closed"]["re"],
        ):
            assert got == pytest.approx(want, abs=1e-12 * case["width"]), (
                f"{case['shape']} T={case['width']} f={f}"
            )


def test_the_golden_widths_and_half_power_points_match_the_javascript():
    """golden 檔的 Δt、Δf 與半功率點，逐個對 JS。

    半功率那一組特別值得綁在一起：golden 用的是 mpmath 的割線法求根，
    JS 用的是自己寫的二分法——**兩個不同的演算法找同一個根**。
    """
    payload = golden()["pulse"]
    width = 0.004
    for shape, entry in payload["widths"].items():
        row = run_case("pulseWidths", shape=shape, widths=[width])[0]
        assert row["deltaT"] == pytest.approx(entry["delta_t_factor"] * width, rel=1e-12)
        if entry["delta_f_factor"] is None:
            assert row["deltaF"] is None
        else:
            assert row["deltaF"] == pytest.approx(
                entry["delta_f_factor"] / width, rel=1e-12,
            )
        want_bandwidth = 2 * payload["half_power_u"][shape] / width
        assert row["bandwidth"] == pytest.approx(want_bandwidth, rel=1e-9)


# ============================================================================
# 極零點與數位濾波器（2S9，課程 W7）
#
# §8.4 的五類驗證在這一頁的形狀：
#
#   第 1 類（兩條獨立路徑必須相等）在這裡有**三個**實例，而三個都是必要的：
#     (a) 係數展開 vs 因式連乘——`responseFromCoefficients` 與
#         `responseFromPairs` 對同一組 ω 各算一次。展開那一步只在其中
#         一條路上，而它正是最容易寫錯的地方。
#     (b) JS 展開的係數 vs **SymPy 展開 ∏(1 − p_k z⁻¹)**。SymPy 完全不知道
#         自己在處理一個濾波器，它只是在乘多項式。
#     (c) 差分方程遞迴 vs 頻率響應——把 δ 餵進遞迴、對輸出做 DTFT，
#         必須回到 H(e^{jω})。這一條把「係數」與「曲線」綁在一起，
#         而前兩條都只驗其中一邊。
#
#   第 2 類（解析解對照）：r = 0 的共振器在 ω = θ 上的增益是 1/(1 − r²)，
#   單位圓上的零點在 ω = θ 上的增益恰好是 0。兩個都是一行閉合式。
#
# ⚠️ **另外三項與正確性無關，與安全有關**，而它們是這一頁特有的：
#   穩定三角形要與真正的根一致、兩組穩定係數之間的線段要整段穩定
#   （worklet 換係數時走的就是那條線）、以及 worklet 的看守要真的會跳。
# ============================================================================

def reference_polynomial(pairs: list[dict]) -> list[float]:
    """∏_k (1 − r e^{jθ}z⁻¹)(1 − r e^{−jθ}z⁻¹) 的係數，**用 SymPy 展開**。

    JS 那一側是「先把每一對寫成 [1, −2r cos θ, r²]，再把它們摺積起來」。
    這裡完全不走那條路：把每個根寫成一個複數指數，讓 SymPy 去乘、
    去展開、去合併同類項——它連「這是一個濾波器」都不知道。

    ⚠️ 回傳的係數必須是實數。虛部不為 0 就代表共軛配對錯了，
    而那是這一段最根本的一件事，所以這裡直接斷言在函式裡。
    """
    z = sp.Symbol("z")
    product = sp.Integer(1)
    for pair in pairs:
        r = sp.nsimplify(pair["r"], rational=True)
        theta = sp.Float(pair["theta"], 30)
        for sign in (1, -1):
            root = r * sp.exp(sp.I * sign * theta)
            product *= 1 - root * z
    poly = sp.Poly(sp.expand(product), z)
    coefficients = list(reversed(poly.all_coeffs()))
    out = []
    for coefficient in coefficients:
        value = complex(sp.N(coefficient, 30))
        assert abs(value.imag) < 1e-20, (
            f"共軛對展開之後出現虛部 {value.imag}，配對一定錯了"
        )
        out.append(value.real)
    return out


def reference_response(b: list[float], a: list[float], omega: float) -> complex:
    """H(e^{jω})，**用 mpmath 在 40 位精度上算**，與 JS 的 float64 無關。

    精度拉高的用意不是「更準」——被測的那一側本來就只有 float64。
    是為了讓參考值**不含任何與被測者共用的誤差來源**：兩邊都用 float64
    的話，一個把指數的正負號寫反、而恰好對稱的錯誤有機會兩邊一起犯。
    """
    mp.dps = 40
    def evaluate(coefficients):
        total = mp.mpc(0)
        for k, coefficient in enumerate(coefficients):
            total += mp.mpf(coefficient) * mp.exp(mp.mpc(0, -omega * k))
        return total
    return complex(evaluate(b) / evaluate(a))


def reference_root_radius(a: list[float]) -> float:
    """1 + a₁z⁻¹ + a₂z⁻² 的根的最大模，用二次公式直接算。

    這是穩定三角形（三條線性不等式）的**獨立路徑**：一個看係數的區域、
    一個真的把根解出來。
    """
    a1 = a[1] if len(a) > 1 else 0.0
    a2 = a[2] if len(a) > 2 else 0.0
    if a2 == 0:
        return abs(a1)
    discriminant = cmath.sqrt(complex(a1 * a1 - 4 * a2))
    return max(abs((-a1 + discriminant) / 2), abs((-a1 - discriminant) / 2))


#: 幾組涵蓋不同情況的極零點設定。每一組都有一個明確的用途，不是隨機取樣。
POLE_ZERO_CASES = [
    # 單位圓上的零點 + 圓內的極點：頁面的預設，也是最典型的一組
    ({"r": 1.0, "theta": 0.55 * math.pi}, {"r": 0.9, "theta": 0.15 * math.pi}),
    # 尖銳共振
    ({"r": 0.0, "theta": 0.0}, {"r": 0.99, "theta": 0.12 * math.pi}),
    # θ = π/2：cos θ = 0，中間那一項恰好抵消，**負零最容易在這裡出現**
    ({"r": 1.0, "theta": 0.5 * math.pi}, {"r": 0.7, "theta": 0.5 * math.pi}),
    # θ = 0：共軛對退化成二重實根，不是邊界瑕疵而是同一條公式
    ({"r": 1.0, "theta": 0.0}, {"r": 0.6, "theta": 0.0}),
    # θ = π：另一個退化端
    ({"r": 1.0, "theta": math.pi}, {"r": 0.5, "theta": math.pi}),
    # 零點跑到圓外（非最小相位）——合法而且不影響穩定性
    ({"r": 1.3, "theta": 0.3 * math.pi}, {"r": 0.8, "theta": 0.7 * math.pi}),
]


@pytest.mark.parametrize("zero,pole", POLE_ZERO_CASES)
def test_the_coefficients_match_sympy_expanding_the_product(zero, pole):
    """§8.4 第 1 類，實例 (b)：JS 的展開對 SymPy 的展開。

    ⚠️ 這一項盯著的是 `pairSection()` 中間那一項的**負號**。
    寫成 +2r cos θ 得到的是把共軛對鏡射到左半平面的濾波器——
    曲線形狀完全正常，只是共振跑到了另一個頻率，
    而畫面上不會有任何東西看起來不對。
    """
    data = run_case("polezeroCoefficients", zeros=[zero], poles=[pole], gain=1)

    def compare(got, want, name):
        # ⚠️ 長度可以不同，而那是對的：r = 0 時 SymPy 展開 (1 − 0·z)² 得到
        # 一個常數 1，而 JS 留著 [1, 0, 0]。兩者是同一個多項式，
        # 但 JS 那一份**應該**留著那兩個 0——畫面上印的是差分方程，
        # 而「y[n] = x[n] + 0·x[n−1] + 0·x[n−2]」說出了這個濾波器的結構。
        # 所以這裡補零到等長再比，不是斷言長度相同。
        length = max(len(got), len(want))
        for k in range(length):
            a = got[k] if k < len(got) else 0.0
            b = want[k] if k < len(want) else 0.0
            assert a == pytest.approx(b, abs=1e-12), f"{name} 的第 {k} 項"

    compare(data["b"], reference_polynomial([zero]), "b")
    compare(data["a"], reference_polynomial([pole]), "a")


def test_the_gain_multiplies_the_numerator_and_leaves_the_denominator_alone():
    """增益乘在哪一邊。

    乘錯邊的結果是 H 變成 1/g 倍——**而這一頁的增益是音訊安全用的**，
    乘反了就是把該衰減的訊號放大了同樣的倍數。所以這一項不是形式檢查。
    """
    zero, pole = POLE_ZERO_CASES[0]
    plain = run_case("polezeroCoefficients", zeros=[zero], poles=[pole], gain=1)
    scaled = run_case("polezeroCoefficients", zeros=[zero], poles=[pole], gain=0.25)
    assert scaled["a"] == plain["a"]
    for got, want in zip(scaled["b"], plain["b"]):
        assert got == pytest.approx(0.25 * want, abs=1e-14)
    # 未乘增益的分子也要對得起來，否則「乘在哪裡」這件事只驗到了一半。
    for got, want in zip(scaled["numeratorWithoutGain"], plain["b"]):
        assert got == pytest.approx(want, abs=1e-14)


@pytest.mark.parametrize("zero,pole", POLE_ZERO_CASES)
def test_the_two_response_paths_agree(zero, pole):
    """§8.4 第 1 類，實例 (a)：展開後求值 vs 因式連乘。

    兩者在數學上恆等，而它們在程式裡沒有共用任何一行——展開那一步
    只出現在其中一條路上。
    """
    omegas = [math.pi * i / 40 for i in range(41)]
    data = run_case(
        "polezeroResponse", zeros=[zero], poles=[pole], gain=1, omegas=omegas,
    )
    peak = max(data["coefficients"]["magnitude"])
    for i, omega in enumerate(omegas):
        want = data["pairs"]["magnitude"][i]
        got = data["coefficients"]["magnitude"][i]
        assert got == pytest.approx(want, rel=1e-9, abs=1e-12), f"ω = {omega}"
        # ⚠️ **|H| 幾乎是 0 的地方不比相位，而那不是在放水。**
        # 零點落在單位圓上時，它的角度上 H 恰好是 0，而 0 的輻角
        # 沒有定義——兩條路各自算出來的是兩個 1e−16 的比值，
        # 那個比值本來就可以是任何東西。比它只會得到一個假的紅燈。
        if got < peak * 1e-9:
            continue
        # 避開「兩者都在 ±π 附近但差一圈」那個假失敗。
        gap = abs(data["pairs"]["phase"][i] - data["coefficients"]["phase"][i])
        assert min(gap, abs(gap - 2 * math.pi)) < 1e-9, f"相位在 ω = {omega} 不合"
    # `responseCurve()` 是展示層真正呼叫的那一支，它不得與逐點求值分岔。
    for got, want in zip(data["curve"]["magnitude"], data["coefficients"]["magnitude"]):
        assert got == pytest.approx(want, rel=1e-12)


@pytest.mark.parametrize("zero,pole", POLE_ZERO_CASES[:4])
def test_the_response_matches_a_high_precision_evaluation(zero, pole):
    """§8.4 第 2 類：對照 mpmath 在 40 位精度下算的同一個比值。

    這一條與上一條不重疊：上一條驗「JS 內部兩條路一致」，
    這一條驗「JS 算出來的東西對」——兩條都錯成同一個樣子的可能性
    是上一條唯一漏得掉的東西。
    """
    omegas = [0.0, 0.3, 1.0, math.pi / 2, 2.4, math.pi]
    data = run_case(
        "polezeroResponse", zeros=[zero], poles=[pole], gain=1, omegas=omegas,
    )
    for i, omega in enumerate(omegas):
        want = reference_response(data["b"], data["a"], omega)
        assert data["coefficients"]["re"][i] == pytest.approx(want.real, abs=1e-9)
        assert data["coefficients"]["im"][i] == pytest.approx(want.imag, abs=1e-9)


def test_a_zero_on_the_unit_circle_removes_exactly_that_frequency():
    """§8.4 第 2 類：|H| 在零點的角度上恰好是 0。

    「恰好」在這裡是有意義的——零點在圓上就是完全挖掉，而不是挖得很深。
    這是這一頁最容易用耳朵確認的一句話，所以它值得一個界很緊的斷言：
    浮點下它是 1e−16 的量級，而**任何一個真的寫錯的實作都會差好幾個
    數量級**，中間有很大的空間，沒有理由把界放寬。
    """
    theta = 0.4 * math.pi
    data = run_case(
        "polezeroResponse",
        zeros=[{"r": 1.0, "theta": theta}], poles=[{"r": 0.8, "theta": 0.2 * math.pi}],
        gain=1, omegas=[theta],
    )
    assert abs(data["coefficients"]["magnitude"][0]) < 1e-14
    assert abs(data["pairs"]["magnitude"][0]) < 1e-14


@pytest.mark.parametrize("radius", [0.5, 0.8, 0.95, 0.99])
def test_a_resonator_has_the_gain_the_closed_form_says(radius):
    """§8.4 第 2 類，一行閉合式。

    極點在 ±jr（θ = π/2）、沒有零點時，分母是 1 + r²z⁻²，
    而在 ω = π/2 上 z⁻² = e^{−jπ} = −1，所以

        |H(e^{jπ/2})| = 1 / |1 − r²|

    這是整頁唯一一個可以用一行手算驗證的點，所以它值得一項測試。
    """
    data = run_case(
        "polezeroResponse", zeros=[], poles=[{"r": radius, "theta": math.pi / 2}],
        gain=1, omegas=[math.pi / 2],
    )
    want = 1 / (1 - radius * radius)
    assert data["coefficients"]["magnitude"][0] == pytest.approx(want, rel=1e-12)


def test_the_peak_climbs_and_narrows_as_the_pole_approaches_the_circle():
    """半徑 ↔ 增益 ↔ 頻寬，這一頁的核心關係之一。

    ⚠️ 三件事綁在同一項裡是刻意的：它們是**同一個關係的三種讀法**，
    分開驗會讓「峰變高但沒有變窄」這種不可能的組合看起來像兩個獨立
    的通過。峰的位置也一併驗——它必須落在極點的角度附近。
    """
    theta = 0.3 * math.pi
    peaks = []
    widths = []
    offsets = []
    for radius in (0.8, 0.95, 0.99, 0.999):
        data = run_case(
            "polezeroMetrics", zeros=[], poles=[{"r": radius, "theta": theta}], gain=1,
        )
        peaks.append(data["peakMagnitude"])
        widths.append(data["halfPowerWidth"])
        offsets.append(abs(data["peakOmega"] - theta))
    assert all(b > a for a, b in zip(peaks, peaks[1:])), f"峰值沒有隨 r 上升：{peaks}"
    assert all(b < a for a, b in zip(widths, widths[1:])), f"峰沒有隨 r 變窄：{widths}"
    # 峰值的位置**趨近**極點的角度，但在 r 小的時候會偏一點——那是真的，
    # 不是誤差，所以斷言的是「越來越靠近」而不是「等於」。
    #
    # ⚠️ 而它只能趨近到 `peakGain()` 的格點為止：那一支掃 [0, π] 上的
    # 4096 格，所以 r = 0.99 與 r = 0.999 會停在**同一個格點**上。
    # 因此這裡是「不會變遠」加上「最後落在一格之內」，不是嚴格遞減——
    # 寫成嚴格遞減會在下一次調整格點數時變成一個看起來很神祕的紅燈。
    assert all(b <= a + 1e-12 for a, b in zip(offsets, offsets[1:])), (
        f"峰值的位置沒有隨 r 趨近極點的角度：{offsets}"
    )
    assert offsets[0] > offsets[-1]
    assert offsets[-1] <= math.pi / 4096

    # ⚠️ r 更小的時候半功率點會落到軸外，於是量不到寬度——而**那不是失敗，
    # 是讀數列上真的會出現的一格**。把它一起驗掉，那一行文案才有根據。
    flat = run_case(
        "polezeroMetrics", zeros=[], poles=[{"r": 0.5, "theta": theta}], gain=1,
    )
    assert flat["halfPowerWidth"] is None


def test_the_measured_width_approaches_the_textbook_approximation():
    """頁面把量到的頻寬與 Δω ≈ 2(1−r) 並排印出來，所以那個「≈」要是真的。

    ⚠️ 這一項驗的是**兩件事同時成立**：近似在 r → 1 時越來越準
    （否則把它印在旁邊是誤導），而在 r 小的時候差很多
    （否則把兩欄並排印就沒有意義了，直接印近似式就好）。
    這是 2S11 那個「數值積分與閉合式的差距」欄位的同一個作法。
    """
    # θ = π/2 是唯一一個在 r = 0.5 時兩側的半功率點都還落在軸內的角度，
    # 而這一項需要 r 小的那一格才說得出「近似式在那裡不準」。
    theta = 0.5 * math.pi
    errors = {}
    for radius in (0.5, 0.9, 0.99, 0.999):
        data = run_case(
            "polezeroMetrics", zeros=[], poles=[{"r": radius, "theta": theta}], gain=1,
        )
        approximation = 2 * (1 - radius)
        errors[radius] = abs(data["halfPowerWidth"] - approximation) / approximation
    assert errors[0.999] < 0.01, f"r = 0.999 時近似式應該很準，實際差 {errors[0.999]}"
    assert errors[0.99] < 0.05
    assert errors[0.5] > 0.2, (
        f"r = 0.5 時近似式應該明顯不準，實際只差 {errors[0.5]}——"
        "如果它其實很準，那把兩欄並排印在畫面上就沒有意義了"
    )
    assert errors[0.5] > errors[0.9] > errors[0.99] > errors[0.999]


@pytest.mark.parametrize("radius,stable", [
    (0.0, True), (0.5, True), (0.999, True), (1.0, False), (1.02, False), (1.2, False),
])
def test_stability_is_decided_by_the_largest_pole_radius(radius, stable):
    """⚠️ `r == 1` 算**不穩定**，不是「臨界所以放行」。

    臨界的極點給出一個永不衰減的正弦，而在一條會被反覆疊加的音訊路徑上
    那與發散沒有實際差別。更實際的一點：浮點的 r 幾乎不可能剛好是 1，
    所以一個「等於就放行」的判斷式在真實使用中只會在 r 略大於 1 時生效。
    """
    data = run_case(
        "polezeroCoefficients", zeros=[{"r": 1.0, "theta": 1.0}],
        poles=[{"r": radius, "theta": 0.3 * math.pi}], gain=1,
    )
    assert data["stable"] is stable
    assert data["maxPoleRadius"] == pytest.approx(radius)


def test_the_stability_triangle_agrees_with_the_actual_roots():
    """Jury 的三條線性不等式 vs 真的把根解出來。

    ⚠️ 這一項是音訊安全那條「線段整段穩定」論證的地基：那個論證用的是
    **三角形是凸的**，而三角形是凸的只有在那三條不等式真的圈出穩定域
    的時候才有用。所以三角形本身要先對。
    """
    random.seed(20260829)
    # ⚠️ 一次 node 呼叫驗一整批。四百組各叫一次 node 要跑一分鐘以上，
    # 而這一項要的是**覆蓋面**，不是每一組各自的隔離——一組不合就會
    # 印出是哪一組，而那已經夠定位了。
    denominators = [
        [1, random.uniform(-3, 3), random.uniform(-1.5, 1.5)] for _ in range(400)
    ]
    rows = run_case("polezeroTriangle", denominators=denominators)
    checked = 0
    for a, row in zip(denominators, rows):
        radius = reference_root_radius(a)
        # 邊界附近兩邊都可能因為浮點而擺盪，所以那一小圈不比對。
        if abs(radius - 1) < 1e-9:
            continue
        assert row["insideTriangle"] == (radius < 1), (
            f"a1 = {a[1]}, a2 = {a[2]}：三角形說 {row['insideTriangle']}，"
            f"根的模是 {radius}"
        )
        checked += 1
    assert checked > 300, f"只實際比對了 {checked} 組，這個測試大概失效了"
    # 兩邊都要出現過，否則「一致」可能只是「兩邊都說不穩定」。
    inside = sum(1 for row in rows if row["insideTriangle"])
    assert 0 < inside < len(rows), f"四百組裡只有 {inside} 組落在三角形內"


def test_a_straight_line_between_two_stable_filters_stays_stable():
    """⛔ **這是 worklet 換係數時不會爆掉的全部根據。**

    穩定域由三條**線性**不等式圍出來，所以它是凸的，兩個穩定點之間的
    線段整段都在裡面。worklet 在一格（128 個樣本）之內就是沿著這條線段走。

    ⚠️ 這個保證**只對二階成立**，而這一頁的分母恰好只有一個共軛對——
    那是一個設計約束，不是巧合。想加第二個極點對的人會先撞到這一項。
    """
    random.seed(20260830)

    def draw_stable():
        while True:
            a1 = random.uniform(-2, 2)
            a2 = random.uniform(-1, 1)
            if reference_root_radius([1, a1, a2]) < 0.999:
                return [1, a1, a2]

    ts = [i / 16 for i in range(17)]
    cases = [
        {"from": {"b": [1], "a": draw_stable()},
         "to": {"b": [1], "a": draw_stable()}, "ts": ts}
        for _ in range(120)
    ]
    for case, rows in zip(cases, run_case("polezeroBlend", cases=cases)):
        for row in rows:
            assert row["insideTriangle"], (
                f"{case['from']['a']} → {case['to']['a']} 在 t = {row['t']} "
                f"跑出了穩定域：{row['a']}"
            )
            assert reference_root_radius(row["a"]) < 1, (
                f"t = {row['t']} 的根跑到單位圓上或外面：{row['a']}"
            )


@pytest.mark.parametrize("zero,pole", POLE_ZERO_CASES)
def test_the_safety_gain_only_attenuates_and_pins_the_peak_to_one(zero, pole):
    """音訊安全的第二層。

    兩個承諾，而**第二個比第一個重要**：峰值被壓到 1（不會太大聲），
    而且增益不超過 1（不會把一個本來就安靜的濾波器放大）。
    只驗第一個的話，一個「總是把音量拉滿」的實作會通過。
    """
    metrics = run_case("polezeroMetrics", zeros=[zero], poles=[pole], gain=1)
    gain = metrics["safetyGain"]
    assert 0 < gain <= 1, f"安全增益 {gain} 不在 (0, 1] 裡"
    scaled_peak = gain * metrics["peakMagnitude"]
    if metrics["peakMagnitude"] > 1:
        assert scaled_peak == pytest.approx(1.0, rel=1e-9)
    else:
        assert gain == 1.0
    assert scaled_peak <= 1 + 1e-9


def test_an_fir_impulse_response_stops_dead_and_an_iir_one_does_not():
    """FIR 與 IIR 的差別，用「有限」這兩個字的字面意思驗。

    ⚠️ FIR 那一半的界是**恰好 0**，不是「很小」：沒有回授就沒有東西
    可以讓輸出在第 3 格之後還有值。這是這一頁上少數幾個可以斷言
    「恰好」的地方之一，所以就斷言它。
    """
    zero = {"r": 0.9, "theta": 0.3 * math.pi}
    fir = run_case("polezeroSequence", zeros=[zero], poles=[], gain=1, count=32)
    assert len(fir["b"]) == 3
    assert all(value == 0.0 for value in fir["impulse"][3:])
    assert any(value != 0.0 for value in fir["impulse"][:3])

    iir = run_case(
        "polezeroSequence", zeros=[zero], poles=[{"r": 0.95, "theta": 0.3 * math.pi}],
        gain=1, count=64,
    )
    assert all(value != 0.0 for value in iir["impulse"][3:])
    # 而且它是在衰減，不是在亂跑
    tail = max(abs(v) for v in iir["impulse"][48:])
    head = max(abs(v) for v in iir["impulse"][:16])
    assert 0 < tail < head


@pytest.mark.parametrize("zero,pole", POLE_ZERO_CASES[:3])
def test_the_impulse_response_transforms_back_into_the_frequency_response(zero, pole):
    """§8.4 第 1 類，實例 (c)：**遞迴與曲線必須是同一個系統。**

    把 δ 餵進差分方程，對輸出做一次照定義的 DTFT，結果必須回到
    H(e^{jω})。這一條把「係數」與「曲線」綁在一起——前面兩條獨立路徑
    各自只驗其中一邊，而一個「係數對、遞迴寫錯」的實作會通過它們兩個。

    ⚠️ 截斷會帶來誤差，而誤差的大小取決於尾巴還剩多少。這裡用
    2048 格，並把容忍度訂在**尾巴的量級**而不是一個隨手的數字。
    """
    count = 2048
    data = run_case(
        "polezeroSequence", zeros=[zero], poles=[pole], gain=1, count=count,
    )
    h = data["impulse"]
    # 截斷的殘量：容忍度應該由它決定，不是由習慣決定。
    tail = sum(abs(v) for v in h[count - 64:])
    omegas = [math.pi * i / 12 for i in range(13)]
    response = run_case(
        "polezeroResponse", zeros=[zero], poles=[pole], gain=1, omegas=omegas,
    )
    for i, omega in enumerate(omegas):
        total = sum(v * cmath.exp(-1j * omega * n) for n, v in enumerate(h))
        assert total.real == pytest.approx(
            response["coefficients"]["re"][i], abs=max(1e-9, 10 * tail),
        ), f"ω = {omega}"
        assert total.imag == pytest.approx(
            response["coefficients"]["im"][i], abs=max(1e-9, 10 * tail),
        ), f"ω = {omega}"


def test_the_recursion_agrees_with_convolution_when_there_is_no_feedback():
    """沒有分母時，差分方程就是一次摺積——所以拿摺積來驗它。

    這是**上一個展示的內容當成這一個展示的參考實作**，而它是一條真的
    獨立的路：`filterSequence()` 一格一格往前跑，摺積是把 b 疊上去。
    """
    b = [0.4, -0.2, 0.35, 0.1]
    x = [1.0, -0.5, 0.25, 0.75, 0.0, -1.0, 0.3, 0.2, -0.4, 0.9]
    # ⚠️ 走 worklet 那個 case 是因為它吃的是**原始係數**（`polezeroSequence`
    # 的 b 由極零點算出來，任意一組 b 未必有對應的實根對）。
    # `pure` 那一欄是同一支 `filterSequence()` 跑出來的。
    direct = run_case("polezeroWorklet", b=b, a=[1], x=x, blockSize=4)
    want = [
        sum(b[k] * x[n - k] for k in range(len(b)) if n - k >= 0)
        for n in range(len(x))
    ]
    for n, (got, expected) in enumerate(zip(direct["pure"], want)):
        assert got == pytest.approx(expected, abs=1e-14), f"n = {n}"
    assert len(direct["pure"]) == len(x)


@pytest.mark.parametrize("radius", [0.9, 0.99])
def test_the_decay_constant_is_when_the_ringing_falls_to_one_over_e(radius):
    """讀數列上的「衰減時間常數」要真的是那件事。

    −1/ln r 是一行閉合式，而這裡不拿閉合式驗閉合式：把衝激響應跑出來，
    找它的包絡掉到 1/e 的那一格，兩者要對得上。
    """
    theta = 0.25 * math.pi
    metrics = run_case(
        "polezeroMetrics", zeros=[], poles=[{"r": radius, "theta": theta}], gain=1,
    )
    tau = metrics["decaySamples"][0]
    assert tau == pytest.approx(-1 / math.log(radius), rel=1e-12)

    count = int(tau * 8) + 64
    h = run_case(
        "polezeroSequence", zeros=[], poles=[{"r": radius, "theta": theta}],
        gain=1, count=count,
    )["impulse"]
    # 包絡：每半個週期取一次區域極大，避開正弦本身的過零點。
    peak = max(abs(v) for v in h[:16])
    window = max(1, int(math.pi / theta))
    crossing = None
    for n in range(0, count - window):
        local = max(abs(v) for v in h[n:n + window])
        if local < peak / math.e:
            crossing = n
            break
    assert crossing is not None, "包絡在整段裡都沒有掉到 1/e"
    assert abs(crossing - tau) < tau * 0.35 + window, (
        f"包絡在第 {crossing} 格掉到 1/e，而時間常數說是 {tau}"
    )


def test_the_worklet_recursion_matches_the_pure_function():
    """⚠️ **worklet 裡那份遞迴與 `filterSequence()` 是刻意的重複。**

    worklet 不能 import ES module（Safari 對此支援不一致），所以那一行
    差分方程在這個專案裡存在兩份。重複該付的代價就是這一項：
    改了其中一份就會紅燈。作法與 2S3 的 ZOH 逐字相同。

    ⚠️ 特意跨好幾格：狀態要在格與格之間活下來，而「每格重新開始」
    的實作在單格測試裡完全正常。
    """
    b = [0.5, 0.2, 0.3]
    a = [1, -1.2, 0.5]
    random.seed(4242)
    x = [random.uniform(-1, 1) for _ in range(517)]
    for block in (16, 128):
        data = run_case("polezeroWorklet", b=b, a=a, x=x, blockSize=block)
        assert len(data["output"]) == len(x)
        for n, (got, want) in enumerate(zip(data["output"], data["pure"])):
            # worklet 的輸出走過 Float32Array，所以界是 float32 的解析度。
            assert got == pytest.approx(want, abs=1e-6), f"block = {block}, n = {n}"
        assert data["messages"] == [], "沒有理由的情況下 worklet 回報了東西"


def test_the_worklet_ramps_coefficients_instead_of_jumping():
    """換係數不得在輸出上留一個不連續——拖一次滑桿會產生幾十個。

    ⚠️ 這一項比「有沒有內插」強：它把**同一次切換**做兩遍，一次立即、
    一次斜坡，然後比兩者輸出的最大單步落差。只驗斜坡那一邊的話，
    一個什麼都沒做的實作也可能剛好通過（如果那次切換本來就很平順）。
    """
    # 輸入用常數 1，讓兩邊的數字都是可以先算出來的：切換前輸出恆為 +1，
    # 切換後恆為 −1。立即切換的落差因此**恰好是 2**，斜坡則把那個 2
    # 攤在 128 個樣本上，一步 2/128 ≈ 0.0156。
    # 用一段正弦也做得到，但那樣兩個數字都變成「大概多少」，
    # 而這一項想斷言的正是它們差多少倍。
    a = [1, 0, 0]
    x = [1.0] * 512
    switch = {"b": [-1, 0, 0], "a": a, "at": 256}
    ramped = run_case(
        "polezeroWorklet", b=[1, 0, 0], a=a, x=x, blockSize=128,
        then={**switch, "immediate": False},
    )["output"]
    jumped = run_case(
        "polezeroWorklet", b=[1, 0, 0], a=a, x=x, blockSize=128,
        then={**switch, "immediate": True},
    )["output"]

    def biggest_step(values):
        return max(abs(b - a_) for a_, b in zip(values[250:300], values[251:301]))

    assert biggest_step(jumped) == pytest.approx(2.0, abs=1e-6), "立即切換應該恰好跳 2"
    assert biggest_step(ramped) == pytest.approx(2 / 128, abs=1e-4), (
        f"斜坡沒有把那個 2 攤在一整格上：一步 {biggest_step(ramped)}"
    )
    # 兩邊最後都要走到 −1，否則「平順」可能只是「沒有真的切換」。
    assert jumped[-1] == pytest.approx(-1.0, abs=1e-6)
    assert ramped[-1] == pytest.approx(-1.0, abs=1e-6)


def test_the_worklet_stops_and_reports_when_the_output_runs_away():
    """⛔ 音訊安全的第三層：**逐樣本看守**。

    上面兩層都在主執行緒上，而主執行緒可能卡住、可能有 bug、可能被我
    改壞；音訊執行緒仍然在跑。所以這裡不假設上游是對的。

    ⚠️ 三個承諾一起驗：輸出停下來、**回報只送一次**（送一百次會把
    主執行緒淹掉）、而且沒有任何一個超過上限的樣本流出去。
    最後那一項是重點——先寫出去再發現的話，那個樣本已經到喇叭了。
    """
    x = [1.0] + [0.0] * 511
    data = run_case(
        "polezeroWorkletOverload", b=[1], a=[1, -3.0, 1.0], x=x, blockSize=128,
    )
    assert len(data["messages"]) == 1, f"回報送了 {len(data['messages'])} 次"
    message = data["messages"][0]
    assert message["type"] == "overload"
    assert message["limit"] == 4
    assert data["peak"] <= 4, f"有樣本超過上限流了出去：{data['peak']}"
    assert all(value == 0.0 for value in data["output"][128:]), "跳掉之後還在出聲"


# --- 繪製層：斷言幾何，不斷言像素（§8.4）--------------------------------------

PLANE_GEOMETRY = {
    "span": 1.35,
    "width": 900,
    "height": 360,
    "pad": {"left": 34, "right": 34, "top": 16, "bottom": 16},
}


def test_the_z_plane_keeps_both_axes_at_the_same_scale():
    """⛔ **單位圓必須是圓，因為學生要從圖上讀角度，而角度就是頻率。**

    一張畫得漂亮但角度說謊的 z 平面比沒有這張圖更糟：它不會報錯，
    而且看起來完全正常。這一項驗兩軸的每單位像素數相同，
    並且驗那個正方形真的塞得進版面（不是超出去然後被裁掉）。
    """
    data = run_case(
        "complexGeometry", **PLANE_GEOMETRY, points=[[1, 0], [0, 1]], probe=None,
        maxDistance=10,
    )
    assert data["unitX"] == pytest.approx(data["unitY"], rel=1e-12)
    assert data["unitX"] == pytest.approx(data["unit"], rel=1e-12)
    # 正方形取的是較短的那一邊，而這個版面的短邊是高度。
    inner_height = PLANE_GEOMETRY["height"] - 32
    assert data["side"] == pytest.approx(inner_height)
    assert data["unit"] == pytest.approx(inner_height / (2 * PLANE_GEOMETRY["span"]))
    # 單位圓的兩端都要落在畫布裡面。
    for point in data["mapped"]:
        assert 0 <= point["x"] <= PLANE_GEOMETRY["width"]
        assert 0 <= point["y"] <= PLANE_GEOMETRY["height"]


def test_a_point_survives_the_trip_to_pixels_and_back():
    """反向轉換是拖曳唯一的入口，而寫錯的症狀是「點會跳」。

    ⚠️ 「點會跳」很容易被當成滑鼠事件抓錯而往別的地方找，所以這一項
    直接盯著往返：資料 → 像素 → 資料必須回到原處。
    虛軸的方向也在這裡驗到——y 是**向上**的（數學慣例），
    而 canvas 的 y 是向下的，寫反了圖仍然像一張 z 平面，
    只是所有的角度都變成了負的。
    """
    points = [[0, 0], [1, 0], [0, 1], [-0.7, 0.4], [0.3, -1.2]]
    data = run_case(
        "complexGeometry", **PLANE_GEOMETRY, points=points, probe=None, maxDistance=10,
    )
    for point in data["mapped"]:
        assert point["backRe"] == pytest.approx(point["re"], abs=1e-12)
        assert point["backIm"] == pytest.approx(point["im"], abs=1e-12)
    # 虛部為正的點畫在中心線**上方**（像素 y 比較小）。
    centre = data["cy"]
    up = next(p for p in data["mapped"] if p["im"] == 1)
    assert up["y"] < centre


def test_the_nearest_mark_is_the_one_a_click_picks_up():
    """命中測試：抓錯把手的症狀是「拖零點結果極點動了」。

    那在一張兩種記號長得不一樣的圖上，使用者只會覺得程式很怪——
    不會報錯，也不會有任何一項別的測試變紅。
    """
    points = [[0.9, 0.4], [0.9, -0.4], [-0.2, 0.8], [-0.2, -0.8]]
    data = run_case(
        "complexGeometry", **PLANE_GEOMETRY, points=points, probe=None, maxDistance=18,
    )
    marks = data["mapped"]
    # 正中在第 2 個記號上
    near = run_case(
        "complexGeometry", **PLANE_GEOMETRY, points=points,
        probe=[marks[2]["x"] + 3, marks[2]["y"] - 2], maxDistance=18,
    )
    assert near["hit"]["id"] == 2
    assert near["hit"]["distance"] < 18
    # 離每一個都很遠：抓不到任何東西，而不是抓到最近的那一個
    far = run_case(
        "complexGeometry", **PLANE_GEOMETRY, points=points,
        probe=[marks[2]["x"] + 60, marks[2]["y"] + 60], maxDistance=18,
    )
    assert far["hit"] is None


# --- 第 5 類：golden vector（SymPy 的符號展開 + mpmath 的因式求值）-----------

def test_the_golden_filter_coefficients_match_the_javascript():
    """golden 檔裡每一組 b 與 a 都要與 JS 算出來的相同。

    ⚠️ 與上面「對照 SymPy 現算」那一組**不重複**：那一組每次跑測試都重算
    （守「今天的實作對不對」），這一項比的是一份 commit 進版本控制的答案
    （守「今天的實作與當初驗過的那一版一樣」）。兩者會在不同的情況下變紅——
    改壞了實作是前者，改對了實作但忘了重新產生 golden 是後者。
    """
    payload = golden()["polezero"]
    assert payload["filters"], "golden 檔裡沒有極零點的 case"
    for case in payload["filters"]:
        data = run_case(
            "polezeroCoefficients",
            zeros=[{"r": r, "theta": t} for r, t in case["zeros"]],
            poles=[{"r": r, "theta": t} for r, t in case["poles"]],
            gain=1,
        )
        assert data["b"] == pytest.approx(case["b"], abs=1e-12)
        assert data["a"] == pytest.approx(case["a"], abs=1e-12)
        assert data["maxPoleRadius"] == pytest.approx(case["max_pole_radius"])


def test_the_golden_responses_match_the_javascript():
    """golden 檔的 H(e^{jω}) 逐點對 JS。

    golden 那一側算的是**因式形式**（mpmath，40 位），而 JS 這一側
    比的是**展開後的係數**那條路——所以這一項同時是一次跨語言的
    獨立路徑比對，而不只是一份回歸快照。
    """
    payload = golden()["polezero"]
    for case in payload["filters"]:
        data = run_case(
            "polezeroResponse",
            zeros=[{"r": r, "theta": t} for r, t in case["zeros"]],
            poles=[{"r": r, "theta": t} for r, t in case["poles"]],
            gain=1, omegas=case["omegas"],
        )
        for i, omega in enumerate(case["omegas"]):
            scale = max(1.0, case["magnitude"][i])
            assert data["coefficients"]["re"][i] == pytest.approx(
                case["real"][i], abs=1e-10 * scale,
            ), f"ω = {omega}"
            assert data["coefficients"]["im"][i] == pytest.approx(
                case["imaginary"][i], abs=1e-10 * scale,
            ), f"ω = {omega}"
            assert data["coefficients"]["magnitude"][i] == pytest.approx(
                case["magnitude"][i], abs=1e-10 * scale,
            ), f"ω = {omega}"
