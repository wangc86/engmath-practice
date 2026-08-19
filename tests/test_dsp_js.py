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
