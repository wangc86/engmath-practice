// pytest 用來驅動 node 的執行器（PLAN.md §8.4「沒有 npm，JS 測試怎麼跑」方案 B）。
//
// 用法：
//     node scripts/run_dsp_case.mjs '{"case": "aliasFrequency", "args": {...}}'
//     echo '{"case": ...}' | node scripts/run_dsp_case.mjs -
//
// 它把結果以 JSON 印到 stdout，由 `tests/test_dsp_js.py` 讀進去、與**同一支
// 測試裡用 SymPy／閉合式現算的參考值**比對。選這個做法而不是 `node --test`
// 的理由寫在 §8.4：**pytest 仍是唯一的測試入口**——單人維護的專案裡，
// 一個沒有人記得跑的第二套測試會慢慢變紅然後被跳過。
//
// ⚠️ 這個檔案本身**不做任何斷言、也不放任何參考值**。它只負責「把被測的
// 那三層純函式跑起來，把數字吐出來」。參考值一律留在 Python 那一側，
// 否則兩條路徑會在這裡合流，交叉驗證就不成立了。

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  traceSine, sampleTimes, sineAt, zeroOrderHold, viewWindowSeconds, clamp,
  WAVEFORMS, wrapPhase, idealWaveformAt, partialSumAt, harmonicAt,
  traceIdealWaveform, tracePartialSum, traceHarmonic, highestActiveHarmonic,
  measureOvershoot, maxDeviation, periodicWaveTables,
} from '../app/static/demos/lib/signal.js';
import {
  nyquist, aliasFrequency, signedAliasFrequency, isAliased, aliasSign,
  fft, ifft, radix2Fft, isPowerOfTwo, nextPowerOfTwo,
  windowCoefficients, windowCoherentGain, applyWindow, zeroPad, WINDOWS,
  amplitudeSpectrum, binFrequencies, binSpacing, observationSeconds,
  nearestBinFrequency, toDecibels, spectrumToDecibels, findPeaks,
  interpolatePeakBin, spectrum, DB_FLOOR,
  FOURIER_KINDS, fourierCoefficients, exponentialCoefficient, PHASE_MODES,
  applyPhaseScheme, maxBandLimitedHarmonic, bandLimit,
} from '../app/static/demos/lib/transform.js';
import {
  makeScale, curvePoints, staircasePoints, viridisColor, dbToUnit, relativeLuminance,
  barRects,
} from '../app/static/demos/lib/draw.js';
import {
  Engine, REQUIRED_CAPABILITIES, missingCapabilities, identifyEngine,
  isSupportedEngine, supportNotice, inspect as inspectScope,
} from '../app/static/demos/lib/browser.js';

const here = dirname(fileURLToPath(import.meta.url));

/**
 * 挑一支 FFT 實作。
 *
 * `'vendor'` 是執行期真正在跑的那支（fft.js，radix-4）；
 * `'radix2'` 是 `transform.js` 裡標為教學用的那支。
 * Python 那一側對這個字串做 parametrize，**兩支跑完全相同的斷言**——
 * 一支說謊的教材比沒有教材更糟（§8.3）。
 */
function pickTransform(impl) {
  if (impl === 'vendor') return (re, im) => fft(re, im);
  if (impl === 'radix2') return (re, im) => radix2Fft(re, im);
  throw new Error(`unknown FFT implementation: ${impl}`);
}

function pickInverse(impl) {
  if (impl === 'vendor') return (re, im) => ifft(re, im);
  if (impl === 'radix2') return (re, im) => radix2Fft(re, im, { inverse: true });
  throw new Error(`unknown FFT implementation: ${impl}`);
}

const toArray = (typed) => Array.from(typed);

/**
 * 把 worklet 檔案載進來。
 *
 * worklet 不是 ES module（Safari 對 worklet 裡的 import 支援不一致，
 * 所以那個檔案刻意寫成不 import 任何東西的普通腳本），因此這裡用
 * `new Function` 注入 AudioWorkletGlobalScope 的那三個全域，
 * 把 registerProcessor 攔下來拿到 class 本身。
 *
 * 這樣做的目的只有一個：讓「worklet 裡那份 ZOH 迴圈」與
 * 「signal.js 裡那份」可以被逐格比對。那兩份的重複是刻意的，
 * 而重複該付的代價就是一項盯著它們的測試。
 */
function loadWorkletProcessor(deviceRate) {
  const source = readFileSync(
    join(here, '..', 'app', 'static', 'demos', 'worklets', 'sampler-processor.js'),
    'utf8',
  );
  let registered = null;
  const register = (name, ctor) => { registered = { name, ctor }; };
  class AudioWorkletProcessorStub {}
  const run = new Function(
    'AudioWorkletProcessor', 'registerProcessor', 'sampleRate', source,
  );
  run(AudioWorkletProcessorStub, register, deviceRate);
  if (!registered) throw new Error('the worklet did not call registerProcessor');
  return registered;
}

const CASES = {
  /** 有號與無號的混疊頻率、奈奎斯特、是否混疊。 */
  aliasFrequency({ pairs }) {
    return pairs.map(([f, fs]) => ({
      f, fs,
      nyquist: nyquist(fs),
      signed: signedAliasFrequency(f, fs),
      apparent: aliasFrequency(f, fs),
      aliased: isAliased(f, fs),
      sign: aliasSign(f, fs),
    }));
  },

  /**
   * 這個展示的數學核心：以 fs 取樣頻率 f 的正弦，與取樣「有號混疊頻率」的
   * 正弦，取樣點必須**完全相同**。畫面上那條重建曲線的正當性就是這一條。
   */
  aliasSamplesMatch({ f, fs, count }) {
    const original = [];
    const reconstructed = [];
    const signed = signedAliasFrequency(f, fs);
    for (let n = 0; n < count; n += 1) {
      const t = n / fs;
      original.push(sineAt(f, t));
      reconstructed.push(sineAt(signed, t));
    }
    return { signed, original, reconstructed };
  },

  /** signal.js 的取樣時刻：落在取樣網格上、在視窗內、等距。 */
  sampleTimes({ fs, t0, duration }) {
    return toArray(sampleTimes(fs, t0, duration));
  },

  /** 零階保持（純函式版）。 */
  zeroOrderHold({ input, ctxRate, fs }) {
    const { output, acc, held } = zeroOrderHold(
      Float64Array.from(input), ctxRate, fs,
    );
    return { output: toArray(output), acc, held };
  },

  /** worklet 裡那份 ZOH，與上面那份比對用。 */
  workletZeroOrderHold({ input, ctxRate, fs }) {
    const { name, ctor } = loadWorkletProcessor(ctxRate);
    const processor = new ctor();
    const output = new Float32Array(input.length);
    const params = { samplingRate: [fs] };
    processor.process([[Float32Array.from(input)]], [[output]], params);
    return { name, output: toArray(output) };
  },

  /** worklet 在沒有輸入時必須輸出靜音，而不是上一個保持值。 */
  workletSilenceWithoutInput({ blockSize, ctxRate, fs }) {
    const { ctor } = loadWorkletProcessor(ctxRate);
    const processor = new ctor();
    const primed = new Float32Array(blockSize).fill(0.5);
    const first = new Float32Array(blockSize);
    processor.process([[primed]], [[first]], { samplingRate: [fs] });
    const second = new Float32Array(blockSize);
    processor.process([[]], [[second]], { samplingRate: [fs] });
    return { first: toArray(first), second: toArray(second) };
  },

  /** 畫面時間窗。 */
  viewWindow({ pairs }) {
    return pairs.map(([f, fs]) => ({
      f, fs, seconds: viewWindowSeconds(f, fs), alias: aliasFrequency(f, fs),
    }));
  },

  /** 繪製層的幾何：座標轉換與路徑（§8.4「斷言資料，不斷言像素」）。 */
  geometry({ t0, t1, vMin, vMax, width, height, pad, times, values }) {
    const scale = makeScale({ t0, t1, vMin, vMax, width, height, pad });
    const curve = curvePoints(scale, times, values);
    const stairs = staircasePoints(scale, times, values, t1);
    return {
      curve,
      stairs,
      zeroY: scale.y(0),
      topY: scale.y(vMax),
      bottomY: scale.y(vMin),
      leftX: scale.x(t0),
      rightX: scale.x(t1),
      roundTrip: scale.timeAt(scale.x((t0 + t1) / 2)),
    };
  },

  /** clamp 與 traceSine 的基本性質。 */
  trace({ f, t0, duration, count }) {
    const { times, values } = traceSine(f, t0, duration, count);
    return { times: toArray(times), values: toArray(values), clampCheck: clamp(5, 1, 3) };
  },

  // ------------------------------------------------------------------ 2S1／2S2
  //
  // 以下每一個 case 都吃一個 `impl` 參數（'vendor' 或 'radix2'）。
  // Python 那一側對它做 parametrize，因此**兩支 FFT 跑的是完全相同的斷言**
  // ——這就是 §8.3「教學用的那支必須通過與 vendored 相同的測試」的落實方式。

  /** 正變換。 */
  forwardTransform({ re, im = null, impl }) {
    const out = pickTransform(impl)(Float64Array.from(re), im ? Float64Array.from(im) : null);
    return { re: toArray(out.re), im: toArray(out.im) };
  },

  /** 往返：IFFT(FFT(x))。⚠️ 這一項**不得單獨當閘門**，見 test_dsp_js.py。 */
  roundTrip({ re, im = null, impl }) {
    const x = Float64Array.from(re);
    const y = im ? Float64Array.from(im) : new Float64Array(x.length);
    const spec = pickTransform(impl)(x, y);
    const back = pickInverse(impl)(spec.re, spec.im);
    return { re: toArray(back.re), im: toArray(back.im) };
  },

  /** Parseval：時域能量與頻域能量，兩個數字都吐出來，比對留給 Python。 */
  parseval({ re, im = null, impl }) {
    const x = Float64Array.from(re);
    const y = im ? Float64Array.from(im) : new Float64Array(x.length);
    let timeEnergy = 0;
    for (let i = 0; i < x.length; i += 1) timeEnergy += x[i] * x[i] + y[i] * y[i];
    const spec = pickTransform(impl)(x, y);
    let freqEnergy = 0;
    for (let k = 0; k < spec.re.length; k += 1) {
      freqEnergy += spec.re[k] * spec.re[k] + spec.im[k] * spec.im[k];
    }
    return { timeEnergy, freqEnergy, n: x.length };
  },

  /** 視窗係數與相干增益。 */
  windows({ names, n }) {
    const out = {};
    for (const name of names) {
      out[name] = {
        coefficients: toArray(windowCoefficients(name, n)),
        coherentGain: windowCoherentGain(name, n),
        displayName: WINDOWS[name],
      };
    }
    return out;
  },

  /** 加窗 → 補零 → 變換 → 幅度譜，一整條路徑。 */
  spectrumPath({ samples, fs, window, padTo = null, impl }) {
    const result = spectrum(Float64Array.from(samples), {
      fs, window, padTo, transform: pickTransform(impl),
    });
    return {
      amplitudes: toArray(result.amplitudes),
      frequencies: toArray(result.frequencies),
      coherentGain: result.coherentGain,
      length: result.length,
      decibels: toArray(spectrumToDecibels(result.amplitudes)),
    };
  },

  /** 頻率軸的標定與相關換算（差一錯誤最愛住的地方）。 */
  frequencyAxis({ n, fs, probe }) {
    return {
      frequencies: toArray(binFrequencies(n, fs)),
      spacing: binSpacing(n, fs),
      observation: observationSeconds(n, fs),
      nearest: probe.map((f) => nearestBinFrequency(f, fs, n)),
      powerOfTwo: [n, n + 1, n - 1].map((v) => isPowerOfTwo(v)),
      nextPow2: [n - 1, n, n + 1].map((v) => nextPowerOfTwo(v)),
    };
  },

  /** dB 換算與底線夾制。 */
  decibels({ values, floor }) {
    return {
      db: values.map((v) => toDecibels(v, floor)),
      defaultFloor: DB_FLOOR,
    };
  },

  /** 補零與加窗的組合律：先加窗再補零 ≠ 先補零再加窗（後者是錯的）。 */
  windowThenPad({ samples, window, padTo }) {
    const windowed = applyWindow(Float64Array.from(samples), window);
    return {
      windowedThenPadded: toArray(zeroPad(windowed, padTo)),
      paddedThenWindowed: toArray(
        applyWindow(zeroPad(Float64Array.from(samples), padTo), window),
      ),
    };
  },

  /** 峰值搜尋與次格內插。 */
  peaks({ amplitudes, count }) {
    const found = findPeaks(Float64Array.from(amplitudes), count);
    return {
      peaks: found,
      interpolated: found.map(
        (p) => interpolatePeakBin(Float64Array.from(amplitudes), p.bin),
      ),
    };
  },

  // ------------------------------------------------------------------ 2S5
  //
  // Fourier 級數的加法合成。參考值一律在 Python 那一側用 SymPy 現算——
  // 特別是係數（**對定義式真的積一次分**，不抄這邊的閉合式）與
  // 吉布斯過衝（有閉式的峰值位置，見 test_dsp_js.py）。

  /** 係數本身：aₙ、bₙ、振幅、相位、直流，以及指數形式的 cₙ。
   *
   *  ⚠️ case 的名字刻意與被呼叫的函式**不同名**。物件字面值的方法名不會
   *  進入自己的作用域，所以同名其實也能跑——但那是一個「讀起來像遞迴、
   *  其實不是」的陷阱，不值得為了省一個字留著。 */
  fourierSeries({ kind, count }) {
    const series = fourierCoefficients(kind, count);
    return {
      kind: series.kind,
      dc: series.dc,
      harmonics: series.harmonics,
      exponential: series.harmonics.map((h) => exponentialCoefficient(h)),
      shape: {
        label: WAVEFORMS[kind].label,
        decay: WAVEFORMS[kind].decay,
        jump: WAVEFORMS[kind].jump,
        jumpPhase: WAVEFORMS[kind].jumpPhase,
        continuous: WAVEFORMS[kind].continuous,
        oddHarmonicsOnly: WAVEFORMS[kind].oddHarmonicsOnly,
      },
      kinds: FOURIER_KINDS,
    };
  },

  /** 目標波形在指定相位上的值。與 SymPy 的分段定義比對。 */
  idealWaveform({ kind, thetas }) {
    return {
      values: thetas.map((theta) => idealWaveformAt(kind, theta)),
      wrapped: thetas.map((theta) => wrapPhase(theta)),
    };
  },

  /** 部分和在指定相位上的值，以及單一諧波的值。 */
  partialSum({ kind, count, thetas }) {
    const series = fourierCoefficients(kind, count);
    return {
      sum: thetas.map((theta) => partialSumAt(series, theta)),
      first: thetas.map((theta) => harmonicAt(series.harmonics[0], theta)),
      highest: highestActiveHarmonic(series),
    };
  },

  /** 三支 trace 的時間軸必須逐點相同——它們畫在同一張圖上。 */
  traces({ kind, count, f0, t0, duration, points }) {
    const series = fourierCoefficients(kind, count);
    const ideal = traceIdealWaveform(kind, f0, t0, duration, points);
    const sum = tracePartialSum(series, f0, t0, duration, points);
    const one = traceHarmonic(series.harmonics[0], f0, t0, duration, points);
    return {
      times: toArray(ideal.times),
      idealValues: toArray(ideal.values),
      sumTimes: toArray(sum.times),
      sumValues: toArray(sum.values),
      harmonicTimes: toArray(one.times),
      harmonicValues: toArray(one.values),
    };
  },

  /** 吉布斯過衝與最大差距。 */
  overshoot({ kind, counts, points }) {
    return counts.map((count) => {
      const series = fourierCoefficients(kind, count);
      const measured = measureOvershoot(kind, series, points ? { points } : {});
      return { count, ...measured, gap: maxDeviation(kind, series) };
    });
  },

  /**
   * 相位方案。**回傳的重點是振幅**：測試要斷言換相位之後振幅逐格不變，
   * 那是這一頁教學論點的程式版本。
   */
  phaseScheme({ kind, count, mode, seed, offsets }) {
    const base = fourierCoefficients(kind, count);
    const moved = applyPhaseScheme(base, { mode, seed, offsets: offsets || {} });
    const again = applyPhaseScheme(base, { mode, seed, offsets: offsets || {} });
    return {
      modes: PHASE_MODES,
      baseAmplitudes: base.harmonics.map((h) => h.amplitude),
      movedAmplitudes: moved.harmonics.map((h) => h.amplitude),
      basePhases: base.harmonics.map((h) => h.phase),
      movedPhases: moved.harmonics.map((h) => h.phase),
      repeatPhases: again.harmonics.map((h) => h.phase),
      // 重新導出的 aₙ／bₙ 必須與新的 (A, φ) 一致。
      cosines: moved.harmonics.map((h) => h.cosine),
      sines: moved.harmonics.map((h) => h.sine),
      // 換相位不得改變波形以外的東西，但**波形本身應該真的變了**。
      sampledBase: [0, 0.5, 1, 1.5, 2, 2.5].map((u) => partialSumAt(base, u)),
      sampledMoved: [0, 0.5, 1, 1.5, 2, 2.5].map((u) => partialSumAt(moved, u)),
    };
  },

  /** 帶限：最高諧波必須嚴格低於奈奎斯特。 */
  bandLimitSeries({ kind, count, f0, sampleRate }) {
    const series = fourierCoefficients(kind, count);
    const limited = bandLimit(series, f0, sampleRate);
    return {
      limit: limited.limit,
      dropped: limited.dropped,
      kept: limited.series.harmonics.map((h) => h.n),
      highestHz: limited.series.harmonics.length
        ? limited.series.harmonics[limited.series.harmonics.length - 1].n * f0
        : 0,
      nyquist: nyquist(sampleRate),
      maxHarmonic: maxBandLimitedHarmonic(f0, sampleRate),
    };
  },

  /**
   * `PeriodicWave` 的兩張表，**再用 Web Audio 的合成式重建一次**。
   *
   * 重建的那一步是這個 case 的重點：real／imag 寫反不會爆錯、
   * 不會改變頻譜，只會讓每個諧波差 90°——而那正是這一頁在教的東西。
   */
  periodicWave({ kind, count, mode, seed, thetas }) {
    const series = applyPhaseScheme(fourierCoefficients(kind, count), {
      mode: mode || 'series', seed: seed || 1,
    });
    const { real, imag } = periodicWaveTables(series);
    const rebuilt = thetas.map((theta) => {
      let sum = 0;
      for (let k = 1; k < real.length; k += 1) {
        sum += real[k] * Math.cos(k * theta) + imag[k] * Math.sin(k * theta);
      }
      return sum;
    });
    return {
      real: toArray(real),
      imag: toArray(imag),
      rebuilt,
      // 直流不含在 Web Audio 的合成式裡，所以比對時要把它扣掉。
      direct: thetas.map((theta) => partialSumAt(series, theta) - series.dc),
      dc: series.dc,
    };
  },

  /** 長條圖的幾何（§8.4「斷言資料，不斷言像素」）。 */
  bars({ values, width, height, pad, vMax }) {
    const scale = makeScale({
      t0: 0.5, t1: values.length + 0.5, vMin: 0, vMax, width, height, pad,
    });
    return {
      rects: barRects(scale, values),
      baseY: scale.y(0),
      topY: scale.y(vMax),
      left: scale.pad.left,
      right: width - scale.pad.right,
    };
  },

  // --- 瀏覽器支援偵測（D45）------------------------------------------------
  //
  // ⚠️ 這幾個 case 與上面的數值 case 性質不同：它們沒有「參考值」可以對，
  // 對的是**判斷結果**。Python 那一側寫的是正反案例，不是公差。

  /**
   * 引擎判定。每個 sample 是 `{userAgent, userAgentData, mozAppearance}`。
   *
   * `supportsCss` 在這裡由一個布林旗標合成——真正的 `CSS.supports` 在 node
   * 裡不存在，而我們要測的是「拿到 true 時會怎麼判」，不是 CSS 引擎。
   */
  browserEngine({ samples }) {
    return samples.map((sample) => {
      const engine = identifyEngine({
        userAgent: sample.userAgent,
        userAgentData: sample.userAgentData,
        supportsCss: (property) => Boolean(sample.mozAppearance)
          && property === '-moz-appearance',
      });
      return { label: sample.label, engine, supported: isSupportedEngine(engine) };
    });
  },

  /**
   * 能力偵測。`flags` 開關的是一個假 window 上有沒有那幾個東西。
   *
   * 假的建構子刻意做成真的 class + prototype 成員，而不是回一個 `true`：
   * `missingCapabilities()` 問的正是「prototype 上有沒有這個名字」，
   * 用 `true` 代替就等於繞過了被測的那一行。
   */
  browserCapabilities({ flags }) {
    const scope = fakeAudioScope(flags || {});
    const missing = missingCapabilities(scope);
    return {
      missing,
      notice: supportNotice({
        missing,
        engine: flags && flags.engine ? flags.engine : Engine.CHROMIUM,
        secureContext: !(flags && flags.insecure),
      }),
      knownKeys: REQUIRED_CAPABILITIES.map((c) => c.key),
    };
  },

  /** 只測訊息的組裝（哪一層優先、缺幾個時怎麼串成一句話）。 */
  browserNotice({ missing, engine, secureContext }) {
    return {
      notice: supportNotice({ missing, engine, secureContext }),
    };
  },

  /**
   * 完全不造假：把 node 自己的 global 餵進 `inspect()`。
   *
   * node 沒有 AudioContext，所以正確的答案是「全部缺」——這一項的價值在於
   * 它一行 mock 都沒有，因此 `inspect()` 的讀取路徑真的被跑過一次。
   */
  browserRealScope() {
    return inspectScope(globalThis);
  },

  /** 頻譜圖的色階：亮度必須單調（§8.6 第 4 點）。 */
  colormap({ steps, floor, ceiling, dbProbe }) {
    const colors = [];
    for (let i = 0; i < steps; i += 1) {
      const t = i / (steps - 1);
      const rgb = viridisColor(t);
      colors.push({ t, rgb, luminance: relativeLuminance(rgb) });
    }
    return { colors, units: dbProbe.map((db) => dbToUnit(db, floor, ceiling)) };
  },
};

/**
 * 造一個「長得像 window」的物件給 D45 的能力偵測用。
 *
 * 每個旗標對應 `browser.js` 的 `REQUIRED_CAPABILITIES` 裡的一條。
 * 預設全部關掉：測試要打開什麼就寫什麼，**漏寫的意思是「沒有」**，
 * 這個方向讓「忘了寫」的結果是紅燈而不是綠燈。
 */
function fakeAudioScope(flags) {
  const scope = { isSecureContext: !flags.insecure };

  if (flags.webAudio) {
    class FakeAudioContext {}
    if (flags.audioWorklet) FakeAudioContext.prototype.audioWorklet = {};
    if (flags.periodicWave) FakeAudioContext.prototype.createPeriodicWave = () => ({});
    scope[flags.webkitPrefixed ? 'webkitAudioContext' : 'AudioContext'] = FakeAudioContext;
  }
  if (flags.audioWorklet) scope.AudioWorkletNode = class {};
  if (flags.periodicWave) scope.PeriodicWave = class {};
  if (flags.analyser) scope.AnalyserNode = class {};
  if (flags.audioParamRamps) {
    class FakeAudioParam {}
    for (const name of [
      'setValueAtTime', 'linearRampToValueAtTime', 'exponentialRampToValueAtTime',
      'setTargetAtTime', 'cancelScheduledValues',
    ]) {
      if (flags.dropParamMethod === name) continue;
      FakeAudioParam.prototype[name] = () => {};
    }
    scope.AudioParam = FakeAudioParam;
  }
  return scope;
}

function main() {
  // 大一點的 case（N = 4096 的往返）JSON 會超過 Linux 單一 argv 的 128 KB 上限，
  // 症狀是 `OSError: Argument list too long`——所以參數改由 stdin 進來，
  // argv 那條路留著供手動執行時方便。傳 `-` 表示「從 stdin 讀」。
  const arg = process.argv[2];
  const raw = (!arg || arg === '-') ? readFileSync(0, 'utf8') : arg;
  if (!raw) throw new Error('missing case JSON (pass it on argv or on stdin)');
  const request = JSON.parse(raw);
  const runner = CASES[request.case];
  if (!runner) throw new Error(`unknown case: ${request.case}`);
  process.stdout.write(JSON.stringify(runner(request.args || {})));
}

main();
