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

import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest
import sympy as sp

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
    result = subprocess.run(
        [NODE, str(RUNNER), payload],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
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
