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
