"""用 SymPy 產生 DSP 的 golden vector（PLAN.md §8.4 第 5 類驗證）。

    python scripts/dsp_reference.py            # 寫進 tests/data/dsp_golden.json
    python scripts/dsp_reference.py --check    # 只驗證，不寫檔（CI 用）

**這支腳本存在的理由，一句話**：讓「學生在瀏覽器裡看到的數字仍可追溯到
SymPy」這句話有實質內容。出題端的每一題都由 `Check` 逐題驗過（規則 1），
展示端做不到逐幀驗證——SymPy 不在瀏覽器的迴圈裡。能做到的是
**演算法本身經一條與它獨立的路徑驗證過**，而這裡就是那條路徑的一端。

⚠️ **三件寫在最前面的注意事項**：

1. **這個檔案要盡量短、盡量直接照定義寫。** golden 檔本身若產錯就一路錯下去
   （§8.4 第 5 類的「抓不到什麼」欄）。所以這裡的 DFT 是一個
   照定義的二重迴圈，不用 `numpy.fft`、不用任何快速演算法——
   **快的那一支是被測者，不是參考值**。
2. **精度用 mpmath 拉到 40 位再落回 float。** float64 的二重迴圈在 N = 64
   時誤差約 1e-15，本來也夠用；拉高是為了讓 golden 檔的值不依賴於
   「產生它的那台機器的浮點行為」——它會被 commit 進版本控制，
   日後在別的機器上比對。
3. **JSON 是產出物，但仍要 commit。** 理由與 vendored 資產相同：
   clone 完就能跑測試，不需要先執行這支腳本。改了這支腳本就要重跑並
   把新的 JSON 一起 commit。

慣例（與 `app/static/demos/lib/transform.js` 逐字相同，三處必須一致）：

    X[k] = Σ_{n=0}^{N-1} x[n] · exp(-2πi·kn/N)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import sympy as sp
from mpmath import mp

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "tests" / "data" / "dsp_golden.json"

#: 內部計算的位數。40 位遠超過 float64 的 16 位，落回 float 時的誤差
#: 因此完全來自最後那一次四捨五入，與計算過程無關。
DIGITS = 40

WINDOW_NAMES = ("rectangular", "hann", "hamming", "blackman")


def window_value(name: str, n: int, i: int):
    """視窗係數，**用 SymPy 的符號常數算**（π 是精確的 π，不是 3.14159…）。

    分母是 N 不是 N-1（週期版）——與 `transform.js` 的註解同一件事，
    寫兩次是因為這正是 §8.4 第 2 類驗證要抓的那種差一錯誤。
    """
    x = 2 * sp.pi * i / n
    if name == "rectangular":
        return sp.Integer(1)
    if name == "hann":
        return sp.Rational(1, 2) - sp.Rational(1, 2) * sp.cos(x)
    if name == "hamming":
        return sp.Rational(54, 100) - sp.Rational(46, 100) * sp.cos(x)
    if name == "blackman":
        return (
            sp.Rational(42, 100)
            - sp.Rational(1, 2) * sp.cos(x)
            + sp.Rational(8, 100) * sp.cos(2 * x)
        )
    raise ValueError(f"unknown window: {name}")


def naive_dft(samples: list) -> list:
    """照定義的 O(N²) 二重迴圈。**這 6 行是整個驗證體系的地基。**

    它短到可以逐字與定義核對，這就是它有資格當參考實作的全部理由
    （§8.3：自己寫的快速 FFT 沒有這個性質——它的錯法都很安靜）。
    """
    n = len(samples)
    out = []
    for k in range(n):
        acc = mp.mpc(0)
        for i in range(n):
            acc += samples[i] * mp.e ** (-2j * mp.pi * k * i / n)
        out.append(acc)
    return out


def single_sided_amplitude(spectrum: list, coherent_gain) -> list[float]:
    """完整頻譜 → 單邊幅度譜（已還原成訊號的振幅）。

    折疊規則與 `transform.js` 的 `amplitudeSpectrum` 相同：
    k = 0 與 k = N/2 不乘 2（它們沒有對應的負頻率夥伴），其餘乘 2。
    """
    n = len(spectrum)
    half = n // 2
    out = []
    for k in range(half + 1):
        fold = 1 if k in (0, half) else 2
        out.append(float(fold * abs(spectrum[k]) / (n * coherent_gain)))
    return out


def build_windows(sizes: tuple[int, ...]) -> dict:
    data = {}
    for n in sizes:
        entry = {"coefficients": {}, "coherent_gain": {}}
        for name in WINDOW_NAMES:
            coeffs = [window_value(name, n, i) for i in range(n)]
            entry["coefficients"][name] = [float(c.evalf(DIGITS)) for c in coeffs]
            # 相干增益用 SymPy 化簡後求值：整週期的餘弦和恰為 0，
            # 所以答案應該正好是公式裡的常數項（1、1/2、0.54、0.42）。
            gain = sp.simplify(sum(coeffs) / n)
            entry["coherent_gain"][name] = float(gain.evalf(DIGITS))
        data[str(n)] = entry
    return data


def build_spectra() -> list[dict]:
    """加窗正弦的幅度譜。**兩種頻率各做一次，這是這一組的重點。**

    * **落在 bin 中心**（tone = k·fs/N）：頻譜應該只有那一格是滿的。
    * **落在兩格中間**（tone = (k+0.5)·fs/N）：能量散開來，這就是洩漏。
      矩形窗散得最寬、Blackman 最窄——展示要學生看到的正是這個差別，
      所以它必須有 golden 值盯著，不能只靠「看起來對」。
    """
    n, fs, amplitude = 64, 6400, sp.Rational(7, 10)
    cases = []
    for label, bin_offset in (("on-bin", sp.Integer(0)), ("off-bin", sp.Rational(1, 2))):
        k0 = sp.Integer(8) + bin_offset
        tone = k0 * fs / n
        for name in WINDOW_NAMES:
            samples = []
            for i in range(n):
                value = amplitude * sp.sin(2 * sp.pi * tone * i / fs)
                samples.append(mp.mpf(str((value * window_value(name, n, i)).evalf(DIGITS))))
            gain = mp.mpf(str(sp.simplify(
                sum(window_value(name, n, i) for i in range(n)) / n
            ).evalf(DIGITS)))
            cases.append({
                "label": f"{label}/{name}",
                "window": name,
                "on_bin": bin_offset == 0,
                "n": n,
                "fs": fs,
                "amplitude": float(amplitude),
                "tone_hz": float(tone.evalf(DIGITS)),
                "amplitudes": single_sided_amplitude(naive_dft(samples), gain),
            })
    return cases


def build_dirichlet() -> dict:
    """長度 L 的矩形脈衝在長度 N 的 DFT 裡：Dirichlet 核。

    閉式解 |X[k]| = |sin(πkL/N) / sin(πk/N)|，零點落在 k = m·N/L。
    這是 §8.4 第 2 類最乾淨的一個例子：**零點的位置只由 L 與 N 決定**，
    所以頻率軸標定只要差一格就會被抓到。
    """
    n, length = 64, 8
    samples = [mp.mpf(1) if i < length else mp.mpf(0) for i in range(n)]
    spectrum = naive_dft(samples)
    closed_form = []
    for k in range(n):
        if k == 0:
            closed_form.append(float(length))
        else:
            value = sp.Abs(sp.sin(sp.pi * k * length / n) / sp.sin(sp.pi * k / n))
            closed_form.append(float(value.evalf(DIGITS)))
    return {
        "n": n,
        "pulse_length": length,
        "magnitude": [float(abs(c)) for c in spectrum],
        "closed_form": closed_form,
        "zero_bins": [k for k in range(1, n) if (k * length) % n == 0],
    }


# ======================================================= Fourier 級數（2S5）
#
# ⚠️ **這一段刻意不抄 `transform.js` 的閉合式。** 它對定義式真的積一次分：
#
#     aₙ = (1/π) ∫₀^{2π} x(θ) cos(nθ) dθ      bₙ = (1/π) ∫₀^{2π} x(θ) sin(nθ) dθ
#     cₙ = (1/2π) ∫₀^{2π} x(θ) e^{-inθ} dθ
#
# 這就是 §8.4 開頭那句「一條與它獨立的路徑」在 Fourier 級數上的樣子：
# 瀏覽器跑的是查表式的閉合式（快、看得懂），而這裡跑的是積分本身。
# 閉合式抄錯一個 π 或一個 (-1)^n，這一側不會跟著錯——**而且這件事
# 在 2S5 當下就發生過一次**（鋸齒波的 bₙ 漏了一個 π，見 transform.js 的註解）。

#: 展示上的四個目標波形，寫成 SymPy 的分段定義。
#: 每一項是 (區間下界, 區間上界, 該區間上的 x(θ))，θ 由 0 掃到 2π。
def waveform_pieces(kind: str, theta):
    pi = sp.pi
    if kind == "square":
        return [(0, pi, sp.Integer(1)), (pi, 2 * pi, sp.Integer(-1))]
    if kind == "sawtooth":
        # x = θ/π 定義在 (-π, π)；平移到 (0, 2π) 之後是兩段。
        return [(0, pi, theta / pi), (pi, 2 * pi, (theta - 2 * pi) / pi)]
    if kind == "triangle":
        return [
            (0, pi / 2, 2 * theta / pi),
            (pi / 2, 3 * pi / 2, 2 - 2 * theta / pi),
            (3 * pi / 2, 2 * pi, 2 * theta / pi - 4),
        ]
    if kind == "halfWave":
        return [(0, pi, sp.sin(theta)), (pi, 2 * pi, sp.Integer(0))]
    raise ValueError(f"unknown waveform: {kind}")


def trig_coefficients(kind: str, count: int) -> dict:
    """對定義式積分，得到 a₀、aₙ、bₙ。**逐個 n 積，不做符號的 n**。

    符號 n 會讓 SymPy 吐出一堆帶條件的 Piecewise，讀起來比積分本身還難
    核對——而這支腳本的可信度完全來自「短到可以逐字核對」（§8.4 注意事項 1）。
    """
    theta = sp.Symbol("theta", real=True)
    pieces = waveform_pieces(kind, theta)

    def integrate(expr):
        return sum(sp.integrate(piece * expr, (theta, lo, hi)) for lo, hi, piece in pieces)

    a0 = sp.simplify(integrate(sp.Integer(1)) / sp.pi)
    cosines, sines = [], []
    for n in range(1, count + 1):
        cosines.append(sp.simplify(integrate(sp.cos(n * theta)) / sp.pi))
        sines.append(sp.simplify(integrate(sp.sin(n * theta)) / sp.pi))
    return {
        "dc": float((a0 / 2).evalf(DIGITS)),
        "cosine": [float(c.evalf(DIGITS)) for c in cosines],
        "sine": [float(s.evalf(DIGITS)) for s in sines],
    }


def exponential_coefficients(kind: str, count: int) -> dict:
    """再走一次完全不同的路：cₙ = (1/2π)∫ x(θ) e^{-inθ} dθ。

    這一組**不是**從 aₙ、bₙ 換算來的（那樣就只是同一條路徑的兩種寫法）。
    它獨立地積出來，因此 `cₙ = (aₙ - i bₙ)/2` 這條課本上的關係在測試裡
    是一個**被驗證的斷言**，不是一個被套用的公式。
    """
    theta = sp.Symbol("theta", real=True)
    pieces = waveform_pieces(kind, theta)
    re_parts, im_parts = [], []
    for n in range(1, count + 1):
        total = sum(
            sp.integrate(piece * sp.exp(-sp.I * n * theta), (theta, lo, hi))
            for lo, hi, piece in pieces
        ) / (2 * sp.pi)
        value = sp.simplify(sp.expand(total))
        re_parts.append(float(sp.re(value).evalf(DIGITS)))
        im_parts.append(float(sp.im(value).evalf(DIGITS)))
    return {"re": re_parts, "im": im_parts}


#: 吉布斯過衝的極限，(2/π)·Si(π) - 1，佔落差 2 的比例。
#: 這就是課本上那個「約 8.95%」，而它在這裡是 SymPy 算出來的，不是抄的。
def gibbs_limit() -> dict:
    peak = 2 * sp.Si(sp.pi) / sp.pi
    return {
        "peak": float(peak.evalf(DIGITS)),
        "overshoot": float((peak - 1).evalf(DIGITS)),
        "fraction": float(((peak - 1) / 2).evalf(DIGITS)),
    }


def gibbs_exact(kind: str, count: int) -> dict:
    """有限項時**第一個極大值**的精確位置與高度。

    位置有閉合式，兩個波形各推一次（推導寫在下面），因此這裡不必做數值搜尋
    ——數值搜尋的參考值與被測者用的是同一種方法，那不構成獨立路徑。

    * **方波**（只有奇次，設 M = (N+1)/2 項）：部分和的導數是
      (4/π)Σcos((2k-1)θ) = (2/π)·sin(2Mθ)/sin θ，第一個零點在 θ = π/(2M)。
    * **鋸齒**（N 項）：在 θ = π - u 附近部分和等於 (2/π)Σ sin(nu)/n，
      其導數 Σcos(nu) = sin(Nu/2)cos((N+1)u/2)/sin(u/2)，
      第一個零點在 u = π/(N+1)。
    """
    if kind == "square":
        terms = (count + 1) // 2
        theta = sp.pi / (2 * terms)
        peak = 4 / sp.pi * sum(
            sp.sin((2 * k - 1) * theta) / (2 * k - 1) for k in range(1, terms + 1)
        )
    elif kind == "sawtooth":
        u = sp.pi / (count + 1)
        theta = sp.pi - u
        peak = 2 / sp.pi * sum(sp.sin(n * u) / n for n in range(1, count + 1))
    else:
        raise ValueError(f"{kind} has no jump, so it has no overshoot")
    return {
        "count": count,
        "peak": float(peak.evalf(DIGITS)),
        "phase": float(theta.evalf(DIGITS)),
        "fraction": float(((peak - 1) / 2).evalf(DIGITS)),
    }


#: 對照表用的 N，與 `fourier.js` 的 `GIBBS_LADDER` 相同。
GIBBS_LADDER = (3, 7, 15, 31, 63)

FOURIER_KINDS = ("square", "sawtooth", "triangle", "halfWave")


def build_fourier() -> dict:
    trig_count, exp_count = 12, 6
    return {
        "kinds": list(FOURIER_KINDS),
        "trig_count": trig_count,
        "exponential_count": exp_count,
        "trig": {k: trig_coefficients(k, trig_count) for k in FOURIER_KINDS},
        "exponential": {k: exponential_coefficients(k, exp_count) for k in FOURIER_KINDS},
        "gibbs_limit": gibbs_limit(),
        "gibbs": {
            kind: [gibbs_exact(kind, n) for n in GIBBS_LADDER]
            for kind in ("square", "sawtooth")
        },
    }


def _partial_sum(trig: dict, dc: float, theta: float) -> float:
    """由**積分算出來的**係數組出部分和。golden 的自我檢查用它。"""
    total = dc
    for i, (a, b) in enumerate(zip(trig["cosine"], trig["sine"]), start=1):
        total += a * math.cos(i * theta) + b * math.sin(i * theta)
    return total


def self_check(payload: dict) -> list[str]:
    """對 golden 檔本身套用第 1–3 類驗證（§8.4 對第 5 類的但書）。

    golden 檔沒有第二個產生者可以比對，所以它的可信度只能來自
    **內部的自我一致性**：閉式解對得上、能量守恆、已知的解析值正確。
    這裡回傳問題清單而不是 assert，因為 `--check` 要能一次印出全部。
    """
    problems = []

    for size, entry in payload["windows"].items():
        for name, expected in (
            ("rectangular", 1.0), ("hann", 0.5), ("hamming", 0.54), ("blackman", 0.42),
        ):
            got = entry["coherent_gain"][name]
            if abs(got - expected) > 1e-12:
                problems.append(f"N={size} {name} 的相干增益 {got} != {expected}")

    dirichlet = payload["dirichlet"]
    for k, (got, want) in enumerate(zip(dirichlet["magnitude"], dirichlet["closed_form"])):
        if abs(got - want) > 1e-9 * max(1.0, want):
            problems.append(f"Dirichlet k={k}: 樸素 DFT {got} 與閉式解 {want} 不符")
    for k in dirichlet["zero_bins"]:
        if dirichlet["magnitude"][k] > 1e-9:
            problems.append(f"Dirichlet 在 k={k} 應為零，實際 {dirichlet['magnitude'][k]}")

    for case in payload["spectra"]:
        if not case["on_bin"]:
            continue
        peak_bin = round(case["tone_hz"] * case["n"] / case["fs"])
        peak = case["amplitudes"][peak_bin]
        if abs(peak - case["amplitude"]) > 1e-9:
            problems.append(
                f"{case['label']}：落在 bin 中心的正弦峰值 {peak} != 振幅 {case['amplitude']}"
            )
        leaked = sum(v for i, v in enumerate(case["amplitudes"]) if abs(i - peak_bin) > 2)
        if leaked > 1e-9:
            problems.append(f"{case['label']}：bin 中心的正弦不該有遠處洩漏，卻有 {leaked}")

    problems.extend(_check_fourier(payload["fourier"]))
    problems.extend(_check_convolution(payload["convolution"]))
    problems.extend(_check_pulse(payload["pulse"]))
    problems.extend(_check_polezero(payload["polezero"]))
    return problems


def _check_fourier(fourier: dict) -> list[str]:
    """Fourier 那一組的自我一致性（§8.4 對第 5 類的但書）。

    四項，每一項都用**與產生它的方法不同的方法**檢查：

    1. `cₙ = (aₙ - i bₙ)/2` —— 兩組係數是分別積出來的，這條關係因此
       是一個真的檢查，不是恆等式的重述。
    2. **部分和逼近目標波形** —— 在遠離不連續點的地方，由積分係數組出來的
       部分和必須貼近目標值。這一項抓的是「係數對，但整體差一個常數倍」。
    3. **吉布斯峰值真的是那個窗裡的最大值** —— 閉合式的位置是我推導的，
       推導錯了就整組錯，所以這裡用密集掃描實際找一次最大值來對。
    4. **過衝的極限是 8.95%** —— 有限項的值必須朝它收斂。
    """
    problems = []

    for kind in fourier["kinds"]:
        trig = fourier["trig"][kind]
        exponential = fourier["exponential"][kind]
        for i in range(fourier["exponential_count"]):
            want_re = trig["cosine"][i] / 2
            want_im = -trig["sine"][i] / 2
            if abs(exponential["re"][i] - want_re) > 1e-12:
                problems.append(
                    f"{kind} n={i + 1}: Re(c) {exponential['re'][i]} != (a/2) {want_re}"
                )
            if abs(exponential["im"][i] - want_im) > 1e-12:
                problems.append(
                    f"{kind} n={i + 1}: Im(c) {exponential['im'][i]} != (-b/2) {want_im}"
                )

        # 遠離不連續點的三個相位上，部分和應該已經相當接近目標。
        # 容差放寬到 0.06 是因為只有 12 項，而方波的收斂本來就慢。
        for theta, want in _far_from_jump_probes(kind):
            got = _partial_sum(trig, trig["dc"], theta)
            if abs(got - want) > 0.06:
                problems.append(
                    f"{kind} 在 θ={theta:.4f} 的 12 項部分和 {got:.4f} 離目標 {want} 太遠"
                )

    limit = fourier["gibbs_limit"]["fraction"]
    if abs(limit - 0.0894898722) > 1e-9:
        problems.append(f"吉布斯極限 {limit} 不是 0.08948987…")

    # 吉布斯那一組的檢查是**單調 + 收斂**，不是「每一項都接近極限」。
    #
    # ⚠️ 第一版寫的是後者，而它立刻就變紅了——**那不是 bug，是我把教學內容
    # 講得太滿**：兩個波形都收斂到 8.95%，但方波由上面下來
    # （N=3 是 10.02%），鋸齒波由下面上去（N=3 是 -4.07%，部分和連目標的
    # 峰都還沒碰到）。兩者都對，而「過衝永遠是 9%」是錯的。
    # 頁面上的措辭因此也一起改成「朝 8.95% 去，而不是朝 0 去」。
    for kind, rows in fourier["gibbs"].items():
        scanned_problems = []
        for row in rows:
            scanned = _scan_peak(kind, row["count"], row["phase"])
            if abs(scanned - row["peak"]) > 1e-9:
                scanned_problems.append(
                    f"{kind} N={row['count']}：閉合式峰值 {row['peak']} "
                    f"與密集掃描 {scanned} 不符（峰的位置可能推導錯了）"
                )
        problems.extend(scanned_problems)

        fractions = [row["fraction"] for row in rows]
        deltas = [b - a for a, b in zip(fractions, fractions[1:])]
        if not (all(d > 0 for d in deltas) or all(d < 0 for d in deltas)):
            problems.append(f"{kind} 的過衝序列不是單調的：{fractions}")
        if abs(fractions[-1] - limit) > 0.01:
            problems.append(
                f"{kind} 的過衝在 N={rows[-1]['count']} 時是 {fractions[-1]}，"
                f"還沒有靠近極限 {limit}"
            )
        # 收斂的**方向**是往極限，不是往 0——這一條就是整個教學論點，
        # 所以它要有一個看守點：最大的 N 上仍然要有可觀的過衝。
        if fractions[-1] < 0.07:
            problems.append(
                f"{kind} 的過衝在最大的 N 上只有 {fractions[-1]}，"
                "看起來像是在收斂到 0——那會讓對照表教錯"
            )

        # 過衝的**寬度**必須每加一倍項數就減半（這是「越來越窄」那一欄）。
        for previous, current in zip(rows, rows[1:]):
            gap_previous = abs(previous["phase"] - (math.pi if kind == "sawtooth" else 0))
            gap_current = abs(current["phase"] - (math.pi if kind == "sawtooth" else 0))
            ratio = gap_previous / gap_current
            if not 1.8 < ratio < 2.2:
                problems.append(
                    f"{kind} 由 N={previous['count']} 到 {current['count']}，"
                    f"峰的距離只縮成 1/{ratio:.2f}，預期約 1/2"
                )

    return problems


def _far_from_jump_probes(kind: str) -> list[tuple[float, float]]:
    """遠離不連續點的取樣相位與目標值。手寫，不呼叫任何被測的程式碼。"""
    pi = math.pi
    if kind == "square":
        return [(pi / 2, 1.0), (3 * pi / 2, -1.0)]
    if kind == "sawtooth":
        return [(pi / 2, 0.5), (3 * pi / 2, -0.5)]
    if kind == "triangle":
        return [(pi / 2, 1.0), (3 * pi / 2, -1.0), (0.0, 0.0)]
    if kind == "halfWave":
        return [(pi / 2, 1.0), (3 * pi / 2, 0.0)]
    raise ValueError(kind)


def _scan_peak(kind: str, count: int, near: float) -> float:
    """在 `near` 附近密集掃一次最大值。

    ⚠️ **它背書的是「峰在哪裡」，不是「係數對不對」。** 這裡用的係數與
    `gibbs_exact()` 是同一組閉合式，所以兩者對係數不構成交叉驗證——
    係數那一關由上面的積分（n ≤ 12）負責。這一支要擋的是另一件事：
    我推導出來的峰位置 π/(2M) 與 π-π/(N+1) 若寫錯，`gibbs_exact()`
    會算出一個**比真正的峰低**的值，而那個值仍然是一個看起來合理的百分比。
    密集掃描找得到真正的峰，因此位置錯了這裡就會不符。
    """
    if kind == "square":
        def value(theta):
            return (4 / math.pi) * sum(
                math.sin(n * theta) / n for n in range(1, count + 1, 2)
            )
    elif kind == "sawtooth":
        def value(theta):
            return (2 / math.pi) * sum(
                ((-1) ** (n + 1)) * math.sin(n * theta) / n
                for n in range(1, count + 1)
            )
    else:
        raise ValueError(kind)

    span = math.pi / (2 * count)
    best = -math.inf
    steps = 20001
    for i in range(steps):
        theta = near - span + (2 * span * i) / (steps - 1)
        best = max(best, value(theta))
    return best


# ================================ 摺積（2S10，§8.4 第 5 類）

#: 摺積的 golden case。刻意都是**有理數**，所以 SymPy 那一側是精確的，
#: 而 JS 那一側的誤差全部來自 float64 的加乘——比對的界因此可以拉得很緊。
CONVOLUTION_CASES: tuple[dict, ...] = (
    # 兩個矩形：課本上唯一一個學生完全手算得出來的例子，答案是梯形。
    {"label": "rect3 * rect5", "x": [1, 1, 1], "h": [1, 1, 1, 1, 1]},
    {"label": "rect4 * rect4", "x": [1, 1, 1, 1], "h": [1, 1, 1, 1]},
    # 單位脈衝：y 必須逐格等於 h。
    {"label": "impulse * echo", "x": [1], "h": [1, 0, 0, "3/5"]},
    # 一般情況，有正有負：抓得到「少加一項」與「索引寫成 h[k-n]」。
    {"label": "wiggle * comb", "x": ["1", "11/20", "-2/5", "-3/4"],
     "h": [1, 0, "3/5", 0, "9/25"]},
    # 相鄰相減：直流增益 0，常數輸入的輸出中段必須恰好全 0。
    {"label": "ramp * difference", "x": ["1/4", "1/2", "3/4", "1"], "h": [1, -1]},
    # 移動平均：直流增益 1。
    {"label": "wiggle * average4", "x": ["1", "11/20", "-2/5", "-3/4", "1/5"],
     "h": ["1/4", "1/4", "1/4", "1/4"]},
)


def polynomial_convolution(x: list, h: list) -> list:
    """摺積的參考值，用**多項式相乘**算。

    這是一條與被測實作真正獨立的路徑，而不是同一個二重迴圈換個寫法：
    把序列讀成多項式的係數，
    ``(Σ x[i] z^i)(Σ h[j] z^j)`` 的 z^n 係數就是 ``Σ_k x[k] h[n-k]``。
    也就是說**摺積與多項式乘法是同一件事**，而 SymPy 的多項式乘法
    是它自己實作的、與我們無關的程式碼。

    順帶一提這也是一個值得在課堂上講的事實：學生做過的「兩個多項式相乘」
    就是他們現在覺得很陌生的那個運算。
    """
    z = sp.Symbol("z")
    px = sum(sp.Rational(c) * z**i for i, c in enumerate(x))
    ph = sum(sp.Rational(c) * z**j for j, c in enumerate(h))
    product = sp.Poly(sp.expand(px * ph), z)
    length = len(x) + len(h) - 1
    coefficients = [product.coeff_monomial(z**n) for n in range(length)]
    return [float(c) for c in coefficients]


def trapezium_plateau(l1: int, l2: int) -> dict:
    """兩個矩形脈衝的摺積：梯形。上底、下底與高，全部寫得出來。

    長度 L₁ 與 L₂ 的全 1 序列摺積起來，是一個爬 min(L₁,L₂) 步、
    平 |L₁−L₂|+1 格、再降回去的梯形，峰值恰好是 min(L₁, L₂)。
    這幾個數字是**閉合式**，與上面的多項式乘法無關，所以它們互相驗得了對方。
    """
    return {
        "length": l1 + l2 - 1,
        "peak": min(l1, l2),
        "plateau_width": abs(l1 - l2) + 1,
    }


def build_convolution() -> dict:
    cases = []
    for case in CONVOLUTION_CASES:
        x = [float(sp.Rational(v)) for v in case["x"]]
        h = [float(sp.Rational(v)) for v in case["h"]]
        cases.append({
            "label": case["label"],
            "x": x,
            "h": h,
            "y": polynomial_convolution(case["x"], case["h"]),
            "sum_x": float(sum(sp.Rational(v) for v in case["x"])),
            "sum_h": float(sum(sp.Rational(v) for v in case["h"])),
        })
    return {
        "method": "coefficients of the product of two polynomials (SymPy)",
        "cases": cases,
        "trapezium": {
            f"{l1}x{l2}": trapezium_plateau(l1, l2)
            for l1, l2 in ((3, 5), (4, 4), (2, 7), (6, 1))
        },
        # 移動平均的頻率響應在 f = m·f_s/L 上恰好是 0（Dirichlet 核的零點）。
        # 這是「移動平均是低通」那句話最精確的版本，也是 JS 那一側
        # `responseAt()` 的解析對照。
        "moving_average_nulls": {
            "length": 8,
            "sample_rate": 48000,
            "null_hz": [48000 * m / 8 for m in (1, 2, 3)],
        },
    }


def _check_convolution(convolution: dict) -> list[str]:
    """摺積那一組的自我一致性（§8.4 對第 5 類的但書）。

    四項，每一項都用**與產生它的方法不同的方法**檢查：

    1. **長度** —— N+M−1，直接數。
    2. **全和** —— Σy = (Σx)(Σh)。多項式相乘在 z = 1 求值就是這條，
       所以它是一個很便宜、卻抓得到「少加一項」的整體不變量。
    3. **交換律** —— x*h 與 h*x 必須逐格相同。
    4. **梯形** —— 兩個矩形的那兩筆，拿閉合式對峰值與平台寬度。
    """
    problems = []
    for case in convolution["cases"]:
        y = case["y"]
        expected = len(case["x"]) + len(case["h"]) - 1
        if len(y) != expected:
            problems.append(f"{case['label']}：長度 {len(y)} != {expected}")
        total = sum(y)
        want = case["sum_x"] * case["sum_h"]
        if abs(total - want) > 1e-12 * max(1.0, abs(want)):
            problems.append(f"{case['label']}：Σy = {total} != (Σx)(Σh) = {want}")
        swapped = polynomial_convolution(case["h"], case["x"])
        if any(abs(a - b) > 1e-15 for a, b in zip(y, swapped)):
            problems.append(f"{case['label']}：x*h 與 h*x 不同")

    for key, want in convolution["trapezium"].items():
        l1, l2 = (int(part) for part in key.split("x"))
        y = polynomial_convolution([1] * l1, [1] * l2)
        if len(y) != want["length"]:
            problems.append(f"梯形 {key}：長度 {len(y)} != {want['length']}")
        if abs(max(y) - want["peak"]) > 1e-12:
            problems.append(f"梯形 {key}：峰值 {max(y)} != {want['peak']}")
        plateau = sum(1 for v in y if abs(v - want["peak"]) < 1e-12)
        if plateau != want["plateau_width"]:
            problems.append(f"梯形 {key}：平台寬 {plateau} != {want['plateau_width']}")
    return problems


# ===================== 脈衝與連續 Fourier 變換（2S11；課程 W4）
#
# ⚠️ **這一組的參考路徑與前面幾組不同，值得說清楚是哪裡不同。**
#
# 前面幾組比的是「離散的和」，兩邊都是有限次加法，可以要求到 1e−15。
# 這裡比的是**連續的積分**，而瀏覽器那一側跑的是中點法則——它本來就有
# 一個與格距有關的誤差。所以這一組分成兩層，兩層的容忍度差十個數量級：
#
#   1. **閉合式**（四個形狀各一行）對照 **mpmath 的高精度數值積分**。
#      兩者都應該是「正確的答案」，容忍度 1e−12。
#      mpmath 的 tanh-sinh 積分與我們的中點法則沒有任何共同點，
#      而它與 SymPy 的符號積分也不是同一段程式碼——這是三條路。
#   2. **JS 的中點法則**對照閉合式，容忍度是**看情況的**，
#      而那個「情況」本身就是展示的內容（見頁面上那一列讀數）。
#
# 分成兩層是刻意的：把它們混成一項的話，只能取比較鬆的那個界，
# 而閉合式抄錯一個係數就會躲在中點法則的誤差後面。

#: (形狀, 在 [-half, half] 上的 x(t)) —— half 用 T 表示。
#: 高斯是唯一一個 half 是 ∞ 的。
PULSE_KINDS = ("rectangle", "triangle", "cosine", "gaussian")


def pulse_expression(kind: str, t, T):
    """x(t)，**只寫支撐內部**（外面是 0，積分區間自己處理掉）。"""
    if kind == "rectangle":
        return sp.Integer(1)
    if kind == "triangle":
        return 1 - 2 * sp.Abs(t) / T
    if kind == "cosine":
        return sp.cos(sp.pi * t / T) ** 2
    if kind == "gaussian":
        return sp.exp(-sp.pi * t**2 / T**2)
    raise ValueError(f"unknown pulse shape: {kind}")


def pulse_half_support(kind: str, width: float) -> float:
    """積分區間的半寬。高斯用 ∞（mpmath 處理得了）。"""
    return math.inf if kind == "gaussian" else width / 2


def pulse_transform_quad(kind: str, width: float, frequency: float) -> complex:
    """X(f)，用 **mpmath 的高精度數值積分**照定義算。

    ⛔ 這是這一組的參考路徑，所以它必須**照定義寫**，不得引用任何閉合式
    （§8.4 對第 5 類的但書：golden 檔沒有第二個產生者，可信度只能來自
    「參考值本身是用另一種方法算的」）。
    """
    from mpmath import cos as mcos, exp as mexp, mpf, pi as mpi, quad, sin as msin

    T = mpf(width)
    f = mpf(frequency)

    def envelope(t):
        if kind == "rectangle":
            return mpf(1)
        if kind == "triangle":
            return 1 - 2 * abs(t) / T
        if kind == "cosine":
            return mcos(mpi * t / T) ** 2
        return mexp(-mpi * t**2 / T**2)

    def real(t):
        return envelope(t) * mcos(-2 * mpi * f * t)

    def imag(t):
        return envelope(t) * msin(-2 * mpi * f * t)

    if kind == "gaussian":
        # 分段（−∞, 0, ∞）讓 tanh-sinh 在峰值附近取夠密的點。
        points = [-mp.inf, 0, mp.inf]
    else:
        # 三角在 t = 0 有折點，所以那裡也要當一個分段點——否則積分器
        # 會以為被積函數是光滑的，而在折點附近少算幾位。
        points = [-T / 2, mpf(0), T / 2]
    return complex(float(quad(real, points)), float(quad(imag, points)))


def pulse_widths_symbolic(kind: str) -> dict:
    """Δt 與 Δf 的閉合式係數，由 SymPy **對定義式積分**得到。

    Δt² = ∫t²x²dt / ∫x²dt，Δf² = (1/4π²)·∫|x′|²dt / ∫x²dt
    （第二式是 Parseval 用在導數上：x′ 的變換是 2πif·X(f)）。

    ⛔ **矩形回傳 delta_f = None，而這一行是這一整段最重要的一行。**
    上面那個 Δf 的式子在矩形上會給出 **0**——它只積得到支撐**內部**，
    而矩形在內部的導數恆為 0；兩個邊緣是 delta 函數，符號積分看不到它們。
    也就是說：**照著公式做，會得到「矩形的頻寬是零」，恰好是事實的反面**
    （矩形的旁瓣只以 1/f 衰減，∫f²|X|²df 發散）。
    這不是一個假想的風險，本輪產生這一段時 SymPy 吐出來的就是 0。
    """
    t = sp.Symbol("t", real=True)
    T = sp.Symbol("T", positive=True)
    expr = pulse_expression(kind, t, T)

    if kind == "gaussian":
        limits = (t, -sp.oo, sp.oo)
    else:
        # 只積正半邊再乘 2（四個形狀都是偶函數），避免 Abs 讓積分器打結。
        expr = pulse_expression(kind, t, T).subs(sp.Abs(t), t)
        limits = (t, 0, T / 2)

    factor = 1 if kind == "gaussian" else 2
    energy = sp.simplify(factor * sp.integrate(expr**2, limits))
    second = sp.simplify(factor * sp.integrate(t**2 * expr**2, limits))
    delta_t = sp.simplify(sp.sqrt(second / energy))

    if kind == "rectangle":
        return {"delta_t_factor": float(delta_t / T), "delta_f_factor": None}

    slope = sp.simplify(factor * sp.integrate(sp.diff(expr, t) ** 2, limits))
    delta_f = sp.simplify(sp.sqrt(slope / energy) / (2 * sp.pi))
    return {
        "delta_t_factor": float(delta_t / T),
        "delta_f_factor": float(delta_f * T),
    }


def pulse_half_power_u(kind: str) -> float:
    """g(u) = 1/√2 的第一個正根，u = f·T。**用 mpmath 的求根器**，不是二分。

    JS 那一側是自己寫的二分法，這裡用 `findroot`（割線法）——
    兩個不同的演算法找同一個根。
    """
    from mpmath import findroot, mpf

    def g(u):
        from mpmath import cos as mcos, exp as mexp, mpf as m, pi as mpi, sin as msin

        u = m(u)
        if u == 0:
            return m(1)
        s = msin(mpi * u) / (mpi * u)
        if kind == "rectangle":
            value = s
        elif kind == "triangle":
            half = u / 2
            value = (msin(mpi * half) / (mpi * half)) ** 2
        elif kind == "cosine":
            value = s / (1 - u**2)
        else:
            value = mexp(-mpi * u**2)
        return value - 1 / mp.sqrt(2)

    guess = {"rectangle": 0.44, "triangle": 0.6, "cosine": 0.6, "gaussian": 0.33}[kind]
    return float(findroot(g, mpf(guess)))


#: golden 檔要涵蓋的 (形狀, 寬度, 頻率)。頻率刻意包含
#: **零點、零點之間、以及遠處的旁瓣**——三種位置的失敗方式不一樣。
PULSE_CASES = (
    ("rectangle", 0.004, [0.0, 125.0, 250.0, 375.0, 500.0, 1000.0, 1875.0]),
    ("rectangle", 0.001, [0.0, 500.0, 1000.0, 1500.0, 2000.0]),
    ("triangle", 0.004, [0.0, 250.0, 500.0, 750.0, 1000.0, 1500.0]),
    ("cosine", 0.004, [0.0, 250.0, 500.0, 625.0, 750.0, 1000.0]),
    ("gaussian", 0.004, [0.0, 100.0, 250.0, 400.0, 600.0]),
    ("gaussian", 0.002, [0.0, 200.0, 500.0, 800.0]),
)


def build_pulse() -> dict:
    spectra = []
    for kind, width, frequencies in PULSE_CASES:
        values = [pulse_transform_quad(kind, width, f) for f in frequencies]
        spectra.append({
            "shape": kind,
            "width": width,
            "frequencies": frequencies,
            # 這四個形狀未平移、未調變時是實偶函數，所以虛部應該是 0；
            # 仍然把它存下來，因為「它是不是 0」本身就是一項檢查。
            "real": [v.real for v in values],
            "imaginary": [v.imag for v in values],
        })
    return {
        "method": "mpmath tanh-sinh quadrature of the defining integral",
        "spectra": spectra,
        "widths": {kind: pulse_widths_symbolic(kind) for kind in PULSE_KINDS},
        "half_power_u": {kind: pulse_half_power_u(kind) for kind in PULSE_KINDS},
        "first_null_u": {
            "rectangle": 1.0, "triangle": 2.0, "cosine": 2.0, "gaussian": None,
        },
        "uncertainty_bound": float(1 / (4 * sp.pi)),
        # 自對偶：T = 1 時 exp(−πt²) 的變換逐點等於它自己。
        "gaussian_self_dual": {
            "width": 1.0,
            "probes": [0.0, 0.25, 0.5, 1.0, 1.5],
            "values": [
                pulse_transform_quad("gaussian", 1.0, f).real
                for f in (0.0, 0.25, 0.5, 1.0, 1.5)
            ],
        },
    }


def _check_pulse(pulse: dict) -> list[str]:
    """脈衝那一組的自我一致性（§8.4 對第 5 類的但書）。

    五項，每一項都用**與產生它的方法不同的方法**檢查：

    1. **閉合式** —— 四個形狀各一行，對照 mpmath 積出來的每一格。
    2. **X(0) = 面積** —— 面積另外積一次，這是一條完全不同的積分。
    3. **虛部是 0** —— 實偶函數的變換是實偶的。抓得到「指數的正負號寫反」
       以外的一整類錯誤（例如把 t 的原點放錯）。
    4. **不確定性下界** —— 每個有限的乘積都要 ≥ 1/(4π)，而高斯要取到等號。
    5. **自對偶** —— T = 1 的高斯，X(f) 與 x(f) 逐點相同。
    """
    problems = []
    t = sp.Symbol("t", real=True)
    T = sp.Symbol("T", positive=True)

    def closed_form(kind: str, width: float, f: float) -> float:
        u = f * width
        area = width if kind in ("rectangle", "gaussian") else width / 2
        if kind == "rectangle":
            g = 1.0 if u == 0 else math.sin(math.pi * u) / (math.pi * u)
        elif kind == "triangle":
            half = u / 2
            g = 1.0 if half == 0 else (math.sin(math.pi * half) / (math.pi * half)) ** 2
        elif kind == "cosine":
            if abs(1 - u * u) < 1e-9:
                g = 0.5
            else:
                s = 1.0 if u == 0 else math.sin(math.pi * u) / (math.pi * u)
                g = s / (1 - u * u)
        else:
            g = math.exp(-math.pi * u * u)
        return area * g

    for case in pulse["spectra"]:
        kind, width = case["shape"], case["width"]
        for f, got, imag in zip(case["frequencies"], case["real"], case["imaginary"]):
            want = closed_form(kind, width, f)
            if abs(got - want) > 1e-12 * max(1.0, abs(want) / width):
                problems.append(
                    f"{kind} T={width} f={f}：積分 {got} 與閉合式 {want} 不符"
                )
            if abs(imag) > 1e-15:
                problems.append(f"{kind} T={width} f={f}：虛部應為 0，實際 {imag}")

        expr = pulse_expression(kind, t, T).subs(sp.Abs(t), t)
        if kind == "gaussian":
            area = float(sp.integrate(expr, (t, -sp.oo, sp.oo)).subs(T, width))
        else:
            area = float(2 * sp.integrate(expr, (t, 0, T / 2)).subs(T, width))
        if abs(case["real"][0] - area) > 1e-12:
            problems.append(f"{kind} T={width}：X(0) = {case['real'][0]} != 面積 {area}")

    bound = pulse["uncertainty_bound"]
    for kind, entry in pulse["widths"].items():
        if entry["delta_f_factor"] is None:
            continue
        product = entry["delta_t_factor"] * entry["delta_f_factor"]
        if product < bound - 1e-15:
            problems.append(f"{kind}：Δt·Δf = {product} 低於下界 {bound}")
        if kind == "gaussian" and abs(product - bound) > 1e-15:
            problems.append(f"高斯應該恰好取到下界，實際 {product} vs {bound}")

    dual = pulse["gaussian_self_dual"]
    for f, value in zip(dual["probes"], dual["values"]):
        want = math.exp(-math.pi * f * f)
        if abs(value - want) > 1e-12:
            problems.append(f"高斯自對偶在 f={f} 不成立：{value} != {want}")
    return problems


# ============================================================ 極零點（2S9，W7）
#
# ⚠️ 這一組與上面每一組的差別是：**參考值有兩條路，而兩條都在這個檔案裡**。
# 係數走 SymPy 的**符號**展開（r 是有理數、θ 是 π 的有理倍，所以 cos θ
# 是一個精確的根式，不是一個浮點數）；響應走 mpmath 在**因式形式**上的
# 40 位求值，完全不碰展開後的係數。
#
# `_check_polezero()` 因此可以做一件別組做不到的事：拿展開後的多項式在
# 同一組 ω 上再算一次，與因式那一條比。**golden 檔的可信度在這一組裡
# 不是靠「用了另一種方法」，是靠兩種方法都寫在這裡而且互相對得上。**

#: (零點, 極點, ω/π)。零點與極點寫成 (r, θ/π)，兩者都用有理數，
#: 好讓 SymPy 那一側是精確的。
POLEZERO_CASES = (
    # 單位圓上的零點 + 圓內的極點：頁面的預設
    ((("1", "11/20"),), (("9/10", "3/20"),), ["0", "1/8", "1/4", "11/20", "3/4", "1"]),
    # 尖銳共振，沒有零點
    ((), (("99/100", "3/25"),), ["0", "1/10", "3/25", "1/4", "1/2", "1"]),
    # θ = π/2：cos θ = 0，中間那一項恰好抵消
    ((("1", "1/2"),), (("7/10", "1/2"),), ["0", "1/4", "1/2", "3/4", "1"]),
    # 沒有極點：FIR
    ((("1", "1"),), (), ["0", "1/4", "1/2", "3/4", "1"]),
    # 零點在圓外（非最小相位），極點在圓內
    ((("13/10", "3/10"),), (("4/5", "7/10"),), ["0", "3/10", "1/2", "7/10", "1"]),
)


def polezero_section(r, theta):
    """一個共軛對的二階係數 [1, −2r cos θ, r²]，**用 SymPy 符號算**。

    θ 是 π 的有理倍，所以 `sp.cos` 給的是一個精確的值（π/2 給 0、
    π 給 −1、11π/20 給一個根式），而不是一個先四捨五入過的浮點數。
    """
    return [sp.Integer(1), -2 * r * sp.cos(theta), r**2]


def polezero_polynomial(pairs) -> list:
    """把幾個共軛對乘起來（係數摺積），回傳 SymPy 的精確係數。"""
    poly = [sp.Integer(1)]
    for r, theta in pairs:
        section = polezero_section(r, theta)
        product = [sp.Integer(0)] * (len(poly) + len(section) - 1)
        for i, u in enumerate(poly):
            for j, v in enumerate(section):
                product[i + j] += u * v
        poly = [sp.expand(value) for value in product]
    return poly


def polezero_response_factored(zeros, poles, omega) -> complex:
    """H(e^{jω})，用 **mpmath 在因式形式上**算，完全不碰展開後的係數。

    ⛔ 這是這一組的參考路徑之一，所以它不得引用 `polezero_polynomial()`
    的任何結果——那正是它要獨立於的東西。
    """
    from mpmath import exp as mexp, mpc, mpf

    w = mexp(mpc(0, -float(omega)))

    def accumulate(pairs):
        total = mpc(1)
        for r, theta in pairs:
            radius = mpf(float(r))
            angle = mpf(float(theta))
            for sign in (1, -1):
                root = radius * mexp(mpc(0, sign * angle))
                total *= 1 - root * w
        return total

    return complex(accumulate(zeros) / accumulate(poles))


def build_polezero() -> dict:
    filters = []
    for zeros, poles, omega_fractions in POLEZERO_CASES:
        zero_pairs = [(sp.Rational(r), sp.Rational(t) * sp.pi) for r, t in zeros]
        pole_pairs = [(sp.Rational(r), sp.Rational(t) * sp.pi) for r, t in poles]
        omegas = [float(sp.Rational(f) * sp.pi) for f in omega_fractions]
        values = [
            polezero_response_factored(zero_pairs, pole_pairs, w) for w in omegas
        ]
        filters.append({
            "zeros": [[float(r), float(t)] for r, t in zero_pairs],
            "poles": [[float(r), float(t)] for r, t in pole_pairs],
            "b": [float(sp.N(v, DIGITS)) for v in polezero_polynomial(zero_pairs)],
            "a": [float(sp.N(v, DIGITS)) for v in polezero_polynomial(pole_pairs)],
            "omegas": omegas,
            "real": [v.real for v in values],
            "imaginary": [v.imag for v in values],
            "magnitude": [abs(v) for v in values],
            "max_pole_radius": max((float(r) for r, _ in pole_pairs), default=0.0),
        })
    return {
        "convention": (
            "H(z) = B(z)/A(z) with a[0] = 1; each pair (r, theta) contributes "
            "1 - 2 r cos(theta) z^-1 + r^2 z^-2"
        ),
        "coefficient_method": "sympy symbolic expansion of the product of sections",
        "response_method": "mpmath evaluation of the factored form on the unit circle",
        "filters": filters,
    }


def _check_polezero(polezero: dict) -> list[str]:
    """極零點那一組的自我一致性（§8.4 對第 5 類的但書）。

    四項，而第一項是這一組的重點：

    1. **展開後的多項式在同一組 ω 上再算一次，必須等於因式那一條。**
       兩條路都寫在這個檔案裡，但它們沒有共用任何一行。
    2. **係數必須是實數。** 共軛配對錯了會在這裡冒出虛部。
    3. **單位圓上的零點在它的角度上把 |H| 壓到 0。**
       這是這一頁最容易用耳朵確認的一句話，所以它值得一項檢查。
    4. **Jury 三角形與極點半徑必須說同一件事。** 這一項守的是音訊安全，
       不是數學：worklet 的係數內插靠三角形是凸的，而三角形要先對。
    """
    from mpmath import exp as mexp, mpc, mpf

    problems = []
    for entry in polezero["filters"]:
        b, a = entry["b"], entry["a"]

        for name, coefficients in (("b", b), ("a", a)):
            for k, value in enumerate(coefficients):
                if not isinstance(value, float) or value != value:
                    problems.append(f"{name}[{k}] 不是一個實數：{value!r}")

        for omega, want_re, want_im in zip(
            entry["omegas"], entry["real"], entry["imaginary"],
        ):
            def evaluate(coefficients):
                total = mpc(0)
                for k, coefficient in enumerate(coefficients):
                    total += mpf(coefficient) * mexp(mpc(0, -omega * k))
                return total

            got = complex(evaluate(b) / evaluate(a))
            scale = max(1.0, abs(complex(want_re, want_im)))
            if abs(got.real - want_re) > 1e-12 * scale:
                problems.append(
                    f"ω = {omega}：展開後 {got.real} 與因式 {want_re} 不符"
                )
            if abs(got.imag - want_im) > 1e-12 * scale:
                problems.append(
                    f"ω = {omega}：展開後的虛部 {got.imag} 與因式 {want_im} 不符"
                )

        for radius, theta in entry["zeros"]:
            if abs(radius - 1) > 1e-12:
                continue
            value = polezero_response_factored(
                [(sp.Float(radius), sp.Float(theta))],
                [(sp.Float(r), sp.Float(t)) for r, t in entry["poles"]],
                theta,
            )
            if abs(value) > 1e-25:
                problems.append(
                    f"單位圓上的零點在 θ = {theta} 沒有把 |H| 壓到 0，而是 {abs(value)}"
                )

        a1 = a[1] if len(a) > 1 else 0.0
        a2 = a[2] if len(a) > 2 else 0.0
        inside = abs(a2) < 1 and 1 + a1 + a2 > 0 and 1 - a1 + a2 > 0
        if inside != (entry["max_pole_radius"] < 1):
            problems.append(
                f"Jury 三角形說 {inside}，而極點半徑是 {entry['max_pole_radius']}"
            )
    return problems


def build() -> dict:
    mp.dps = DIGITS
    return {
        "generated_by": "scripts/dsp_reference.py",
        "convention": "X[k] = sum_n x[n] * exp(-2i*pi*k*n/N); inverse carries 1/N",
        "window_denominator": "N (periodic), not N-1",
        "fourier_convention": "x = a0/2 + sum(a_n cos + b_n sin); c_n = (a_n - i b_n)/2",
        "sympy_version": sp.__version__,
        "digits": DIGITS,
        "windows": build_windows((8, 64)),
        "spectra": build_spectra(),
        "dirichlet": build_dirichlet(),
        "fourier": build_fourier(),
        "convolution": build_convolution(),
        "pulse": build_pulse(),
        "polezero": build_polezero(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只驗證既有的 JSON，不重新產生")
    args = parser.parse_args()

    if args.check:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        payload = build()

    problems = self_check(payload)
    if problems:
        print("golden 檔沒有通過自我一致性檢查：")
        for line in problems:
            print(f"  - {line}")
        return 1

    if not args.check:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"寫入 {OUTPUT.relative_to(ROOT)}（{OUTPUT.stat().st_size} bytes）")
    else:
        print("golden 檔通過自我一致性檢查。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
