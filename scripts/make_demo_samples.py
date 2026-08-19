"""產生展示用的內建範例音檔（PLAN.md §8.2、D29）。

    python scripts/make_demo_samples.py            # 產生全部
    python scripts/make_demo_samples.py --list     # 只列出會產生什麼

輸出目錄：`app/static/demos/samples/`。檔案**納入版本控制**，理由與
`app/static/vendor/` 相同——clone 完就能離線啟動，不必先跑這支腳本。
這支腳本存在是為了**可重現**：日後想改長度、改頻率、或加一個新的範例，
不必猜當初是怎麼做出來的。

格式一律 **22.05 kHz、單聲道、16-bit PCM**（老師指定）。
理由：`decodeAudioData` 對 wav 的支援最一致（無壓縮、沒有編碼器差異），
22.05 kHz 的奈奎斯特是 11 kHz，涵蓋到第 25 次諧波都還在裡面，
對「看諧波梳狀結構」綽綽有餘，而檔案只有 48 kHz 立體聲的四分之一大。

---

## 兩件要特別說明的事

### 一、方波與鋸齒波是**帶限**合成的，不是直接取樣理想波形

直接對理想方波取樣會產生混疊——高次諧波超過奈奎斯特之後摺回來，
散落在不是諧波的位置上。那樣的檔案放進一個**專門在教頻譜**的頁面裡
會很難看：學生會看到一堆解釋不了的譜線，而那些線是我們自己造成的。

所以這裡用加法合成，只疊到奈奎斯特以下的諧波：
方波只有奇次（1, 3, 5, …，振幅 1/n），鋸齒波全部都有（振幅 1/n）。
**這順帶就是 Demo 3（加法合成，2S5）要教的東西**，所以這個選擇是雙贏的。

### 二、語音那一段是 eSpeak NG 合成的，不是真人錄音

`espeak-ng -v en-us -s 150 -w <out>.wav "<text>"`。
沙箱裡沒有 root，所以當初是用
`apt-get download espeak-ng libespeak-ng1 espeak-ng-data libpcaudio0 libsonic0`
把 .deb 抓下來、`dpkg-deb -x` 解到一個暫存目錄，再用
`LD_LIBRARY_PATH` 與 `ESPEAK_DATA_PATH` 指過去執行的。

**這支腳本不會幫你裝 espeak-ng。** 找不到它的時候，會明確說出「跳過了哪一個
檔案、為什麼、以及怎麼補」，**不會安靜地少產生一個檔案**（硬規則 4）——
committed 的 wav 已經在版本控制裡，所以少產生一個不會弄壞任何東西，
但你必須知道它沒有被重新產生。
"""

from __future__ import annotations

import argparse
import math
import random
import shutil
import struct
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "app" / "static" / "demos" / "samples"

SAMPLE_RATE = 22050
SECONDS = 1.0
AMPLITUDE = 0.5          # 留 6 dB 餘裕，疊加諧波之後也不會削波

#: 老師指定的那一句。
SPEECH_TEXT = (
    "Hello, welcome to this course, engineering mathematics. "
    "We're excited to learn together with you!"
)


def write_wav(path: Path, samples: list[float]) -> None:
    """16-bit PCM 單聲道。**寫檔前檢查有沒有削波**，不做靜默的夾制。"""
    peak = max(abs(v) for v in samples)
    if peak > 1.0:
        raise ValueError(f"{path.name} 的峰值 {peak:.3f} 超過 1.0，會削波")
    frames = b"".join(struct.pack("<h", int(round(v * 32767))) for v in samples)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)


def frame_count() -> int:
    return int(round(SAMPLE_RATE * SECONDS))


def check_loops_cleanly(frequency: float) -> None:
    """整數個週期才能無縫循環播放，否則接縫處會有一聲「喀」。

    這件事在這裡檢查而不是靠註解，是因為改 SECONDS 或改頻率的人
    很容易忘記它——而症狀（每秒一次的雜音）看起來像是播放程式的 bug。
    """
    cycles = frequency * SECONDS
    if abs(cycles - round(cycles)) > 1e-9:
        raise ValueError(
            f"{frequency} Hz 在 {SECONDS} 秒內不是整數個週期（{cycles}），"
            "循環播放時接縫會有喀聲"
        )


def sine(frequency: float, amplitude: float = AMPLITUDE) -> list[float]:
    check_loops_cleanly(frequency)
    return [
        amplitude * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)
        for i in range(frame_count())
    ]


def harmonic_stack(fundamental: float, odd_only: bool) -> list[float]:
    """帶限的方波（odd_only）或鋸齒波。振幅 1/n，只疊到奈奎斯特以下。

    兩者的頻譜差別就是這一個 `odd_only`：方波只有奇次諧波，
    鋸齒波全部都有。**這是這兩個檔案在教學上唯一的存在理由**，
    所以它在程式裡也應該只有這一個差別。
    """
    check_loops_cleanly(fundamental)
    nyquist = SAMPLE_RATE / 2
    n = frame_count()
    out = [0.0] * n
    total = 0.0
    harmonic = 1
    while fundamental * harmonic < nyquist:
        weight = 1.0 / harmonic
        total += weight
        for i in range(n):
            out[i] += weight * math.sin(
                2 * math.pi * fundamental * harmonic * i / SAMPLE_RATE
            )
        harmonic += 2 if odd_only else 1
    # 正規化到 AMPLITUDE：諧波和的峰值不等於係數和，所以用實際峰值來縮放。
    peak = max(abs(v) for v in out)
    scale = AMPLITUDE / peak
    return [v * scale for v in out]


def two_tones(f1: float, f2: float) -> list[float]:
    """兩個相近的頻率。**解析度展示的主角。**

    22.05 kHz 之下：N = 1024 的格距是 21.5 Hz（分不開），
    N = 2048 是 10.8 Hz（勉強），N = 4096 是 5.4 Hz（分得開）。
    12 Hz 的間距刻意挑在這三格中間，讓學生拉 N 的時候看到兩個峰長出來。
    """
    a = sine(f1, AMPLITUDE / 2)
    b = sine(f2, AMPLITUDE / 2)
    return [x + y for x, y in zip(a, b)]


def white_noise(seed: int = 20260819) -> list[float]:
    """白雜訊。固定亂數種子——範例訊號要可重現，這樣才對得上截圖與說明。"""
    rng = random.Random(seed)
    return [AMPLITUDE * rng.uniform(-1.0, 1.0) for _ in range(frame_count())]


#: (檔名, 說明, 產生函式)。說明會印出來，也抄進 README 的表。
SYNTHETIC = (
    ("tone-440.wav", "Pure sine, 440 Hz — one line in the spectrum",
     lambda: sine(440)),
    ("square-220.wav", "Band-limited square, 220 Hz — odd harmonics only",
     lambda: harmonic_stack(220, odd_only=True)),
    ("sawtooth-220.wav", "Band-limited sawtooth, 220 Hz — every harmonic",
     lambda: harmonic_stack(220, odd_only=False)),
    ("noise-white.wav", "White noise — flat on average, never flat in one frame",
     white_noise),
    ("two-tones-440-452.wav", "440 Hz and 452 Hz — 12 Hz apart, for resolution",
     lambda: two_tones(440, 452)),
)

SPEECH_FILE = "speech-welcome.wav"


def make_speech(destination: Path) -> bool:
    """用 eSpeak NG 合成那一句。回傳有沒有成功。

    找不到 espeak-ng 不是致命錯誤（committed 的 wav 還在），但**必須說出來**。
    """
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if binary is None:
        print(
            f"  略過 {SPEECH_FILE}：找不到 espeak-ng。\n"
            "    這不是失敗，只是沒有重新產生——版本控制裡那份仍然有效。\n"
            "    要重新產生的話：`apt install espeak-ng`（或見本檔開頭的免 root 作法）。"
        )
        return False
    subprocess.run(
        [binary, "-v", "en-us", "-s", "150", "-w", str(destination), SPEECH_TEXT],
        check=True, capture_output=True,
    )
    with wave.open(str(destination), "rb") as handle:
        rate, channels, width = handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
        seconds = handle.getnframes() / rate
    print(f"  {SPEECH_FILE}: {rate} Hz, {channels} ch, {width * 8}-bit, {seconds:.2f} s")
    if (rate, channels, width) != (SAMPLE_RATE, 1, 2):
        print(
            f"    ⚠️ 格式與其他範例不同（預期 {SAMPLE_RATE} Hz 單聲道 16-bit）。"
            "eSpeak NG 1.50 的預設輸出剛好就是這個格式；換了版本要自己轉。"
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="產生展示用的內建範例音檔")
    parser.add_argument("--list", action="store_true", help="只列出會產生什麼，不寫檔")
    args = parser.parse_args()

    if args.list:
        for name, description, _ in SYNTHETIC:
            print(f"{name}: {description}")
        print(f"{SPEECH_FILE}: eSpeak NG, \"{SPEECH_TEXT}\"")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"寫入 {OUTPUT_DIR.relative_to(ROOT)}/")
    for name, description, build in SYNTHETIC:
        path = OUTPUT_DIR / name
        write_wav(path, build())
        print(f"  {name}: {path.stat().st_size / 1024:.0f} KB — {description}")
    make_speech(OUTPUT_DIR / SPEECH_FILE)

    total = sum(p.stat().st_size for p in OUTPUT_DIR.glob("*.wav"))
    print(f"合計 {total / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
