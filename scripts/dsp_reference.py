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

    return problems


def build() -> dict:
    mp.dps = DIGITS
    return {
        "generated_by": "scripts/dsp_reference.py",
        "convention": "X[k] = sum_n x[n] * exp(-2i*pi*k*n/N); inverse carries 1/N",
        "window_denominator": "N (periodic), not N-1",
        "sympy_version": sp.__version__,
        "digits": DIGITS,
        "windows": build_windows((8, 64)),
        "spectra": build_spectra(),
        "dirichlet": build_dirichlet(),
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
