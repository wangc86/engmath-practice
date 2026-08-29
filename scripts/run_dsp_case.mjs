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
  RESPONSE_SHAPES, impulseResponse, INPUT_SHAPES, inputSequence,
  nonZeroTaps, countNonZeroTaps, clickSignal, pluckSignal, padSilence,
  peakAmplitude, LTI_A, LTI_B, LTI_PROBE, LTI_SHIFT,
  PULSE_SHAPES, UNCERTAINTY_BOUND, pulseAt, pulseSupport, signalAt, tracePulse,
  pulseSamples, integrationSampleCount, spectrumPointCount, rmsWidths, pulseBurst,
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
  convolve, fftConvolve, convolutionStep, flippedShiftedResponse,
  reverseSequence, convolutionGainBound, normaliseResponse, responseAt,
  bandGain, directCurrentGain, SYSTEMS, CLIP_LEVEL, applySystem,
  shiftSequence, superpositionCurves, timeInvarianceCurves,
  sinc, fourierIntegral, normalisedPulseSpectrum, pulseArea,
  analyticSpectrum, firstNullFrequency, halfPowerBandwidth, maxAbsoluteGap,
  pairSection, polynomialFromPairs, filterCoefficients, responseFromCoefficients,
  responseFromPairs, responseCurve, peakGain, safetyGain, maxPoleRadius,
  isStable, isStableSecondOrder, filterSequence, filterImpulseResponse,
  blendCoefficients, halfPowerWidth, decaySamples, POLE_ZERO_MAX_RADIUS,
} from '../app/static/demos/lib/transform.js';
import {
  makeScale, curvePoints, staircasePoints, viridisColor, dbToUnit, relativeLuminance,
  barRects, regionRect, splitOnJumps, makeComplexScale, complexPoint, nearestHandle,
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
function loadWorkletProcessor(deviceRate, file = 'sampler-processor.js') {
  const source = readFileSync(
    join(here, '..', 'app', 'static', 'demos', 'worklets', file),
    'utf8',
  );
  let registered = null;
  const register = (name, ctor) => { registered = { name, ctor }; };
  // ⚠️ 2S9 的 processor 在建構式裡就掛 `this.port.onmessage`，所以 stub 的
  // 建構式必須先把 `port` 造出來。**送出去的訊息也要收下來**——
  // 那個 port 是第三層音訊防護唯一的回報路徑，測試要看得到它有沒有響。
  class AudioWorkletProcessorStub {
    constructor() {
      this.port = {
        onmessage: null,
        sent: [],
        postMessage(data) { this.sent.push(data); },
      };
    }
  }
  const run = new Function(
    'AudioWorkletProcessor', 'registerProcessor', 'sampleRate', source,
  );
  run(AudioWorkletProcessorStub, register, deviceRate);
  if (!registered) throw new Error('the worklet did not call registerProcessor');
  return registered;
}

/**
 * 把一條輸入餵給 2S9 的 worklet，一格 `blockSize` 個樣本。
 *
 * `messages` 是在開始之前送進去的那些 port 訊息（係數）。
 * 回傳輸出、以及 worklet 自己送回來的東西（過載回報）。
 */
function runPoleZeroWorklet({ b, a, x, blockSize = 128, immediate = true, then = null }) {
  const { ctor } = loadWorkletProcessor(48000, 'polezero-processor.js');
  const processor = new ctor();
  processor.port.onmessage({
    data: { type: 'coefficients', b, a, immediate },
  });
  const out = new Float32Array(x.length);
  for (let start = 0; start < x.length; start += blockSize) {
    const frames = Math.min(blockSize, x.length - start);
    if (then && then.at === start) {
      processor.port.onmessage({
        data: { type: 'coefficients', b: then.b, a: then.a, immediate: !!then.immediate },
      });
    }
    const input = Float32Array.from(x.slice(start, start + frames));
    const block = new Float32Array(frames);
    processor.process([[input]], [[block]], {});
    out.set(block, start);
  }
  return { output: toArray(out), sent: processor.port.sent };
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
  // ------------------------------------------------ 摺積與 LTI（2S10）

  /** 定義式的摺積。長度、邊界、交換律、與多項式乘法的對照全部由它來。 */
  convolve({ x, h, impl = 'direct' }) {
    const y = impl === 'fft' ? fftConvolve(x, h) : convolve(x, h);
    let total = 0;
    for (let i = 0; i < y.length; i += 1) total += y[i];
    return {
      y: toArray(y),
      length: y.length,
      swapped: toArray(impl === 'fft' ? fftConvolve(h, x) : convolve(h, x)),
      total,
      first: y.length > 0 ? y[0] : null,
      last: y.length > 0 ? y[y.length - 1] : null,
    };
  },

  /**
   * 兩支實作對同一組輸入的差距。**這是 §8.4 第 1 類驗證在摺積上的形式**：
   * 定義式的二重迴圈 vs 頻域相乘，兩條路徑除了答案以外沒有任何共同點。
   */
  convolveAgreement({ x, h }) {
    const direct = convolve(x, h);
    const fast = fftConvolve(x, h);
    let worst = 0;
    for (let i = 0; i < direct.length; i += 1) {
      const gap = Math.abs(direct[i] - fast[i]);
      if (gap > worst) worst = gap;
    }
    return {
      length: direct.length,
      fastLength: fast.length,
      worst,
      scale: Math.max(...Array.from(direct, Math.abs), 1e-12),
    };
  },

  /** 一個 n 的完整展開：上下限、每一項、總和，以及與整條 y 的對照。 */
  convolutionStep({ x, h, n }) {
    const step = convolutionStep(x, h, n);
    const y = convolve(x, h);
    return {
      n: step.n,
      kStart: step.kStart,
      kEnd: step.kEnd,
      overlap: step.overlap,
      terms: step.terms,
      products: toArray(step.products),
      sum: step.sum,
      yAtN: n < y.length ? y[n] : null,
    };
  },

  /** 翻轉平移之後的取樣，以及「不翻轉＝與倒過來的 h 摺積」那條等價關係。 */
  flipping({ x, h, n, kFrom, kTo }) {
    return {
      shifted: toArray(flippedShiftedResponse(h, n, kFrom, kTo)),
      reversed: toArray(reverseSequence(h)),
      flipped: toArray(convolve(x, h)),
      unflipped: toArray(convolve(x, reverseSequence(h))),
    };
  },

  /** 脈衝響應的六個形狀。 */
  impulseResponse({ shapes, delay, length, gain }) {
    return shapes.map((shape) => {
      const taps = impulseResponse(shape, { delay, length, gain });
      return {
        shape,
        uses: RESPONSE_SHAPES[shape].uses,
        taps: toArray(taps),
        nonZero: nonZeroTaps(taps).map((tap) => [tap.index, tap.value]),
        nonZeroCount: countNonZeroTaps(taps),
        dcGain: directCurrentGain(taps),
        bound: convolutionGainBound(taps),
      };
    });
  },

  /** 輸入序列的四個形狀。 */
  inputSequence({ shapes, length }) {
    return shapes.map((shape) => ({
      shape,
      label: INPUT_SHAPES[shape],
      values: toArray(inputSequence(shape, { length })),
    }));
  },

  /** 增益界與正規化：Σ|h| 是取得到的上界，正規化之後輸出不超過輸入。 */
  gainBound({ h, probe }) {
    const bound = convolutionGainBound(h);
    const normalised = normaliseResponse(h);
    // 取得到上界的那個最壞輸入：x[k] = sign(h[...])，讓每一項都同號。
    const worstInput = Array.from(reverseSequence(h), (v) => (v >= 0 ? 1 : -1));
    const worstOutput = convolve(worstInput, h);
    let worstPeak = 0;
    for (let i = 0; i < worstOutput.length; i += 1) {
      worstPeak = Math.max(worstPeak, Math.abs(worstOutput[i]));
    }
    const probed = convolve(probe, normalised.taps);
    let probePeak = 0;
    for (let i = 0; i < probed.length; i += 1) {
      probePeak = Math.max(probePeak, Math.abs(probed[i]));
    }
    return {
      bound,
      scale: normalised.scale,
      normalisedBound: convolutionGainBound(normalised.taps),
      worstPeak,
      probePeak,
      probeInputPeak: Math.max(...Array.from(probe, Math.abs)),
    };
  },

  /** 頻率響應：任意頻率上的 |H| 與相位，加上一段頻帶的平均。 */
  frequencyResponse({ h, sampleRate, frequencies, band = null }) {
    return {
      points: frequencies.map((f) => {
        const value = responseAt(h, f, sampleRate);
        return { f, magnitude: value.magnitude, re: value.re, im: value.im };
      }),
      dc: directCurrentGain(h),
      band: band ? bandGain(h, { ...band, sampleRate }) : null,
    };
  },

  /** 三個系統的兩項殘差，以及它們畫出來的那兩條曲線。 */
  ltiChecks({ h, clip = null }) {
    const level = clip === null ? CLIP_LEVEL : clip;
    return {
      clipLevel: CLIP_LEVEL,
      shift: LTI_SHIFT,
      probes: {
        a: toArray(LTI_A), b: toArray(LTI_B), probe: toArray(LTI_PROBE),
      },
      peaks: {
        a: peakAmplitude(LTI_A),
        b: peakAmplitude(LTI_B),
        sum: peakAmplitude(Float64Array.from(LTI_A, (v, i) => v + LTI_B[i])),
      },
      systems: Object.keys(SYSTEMS).map((kind) => {
        const system = { kind, h, clip: level };
        const superposition = superpositionCurves(system, LTI_A, LTI_B);
        const invariance = timeInvarianceCurves(system, LTI_PROBE, LTI_SHIFT);
        return {
          kind,
          label: SYSTEMS[kind],
          superposition: superposition.residual,
          invariance: invariance.residual,
          together: toArray(superposition.together),
          apart: toArray(superposition.apart),
          outputLength: applySystem(LTI_A, system).length,
        };
      }),
    };
  },

  /** 平移這個動作本身：往右推、兩端補零、長度不變。 */
  shiftSequence({ x, shifts }) {
    return shifts.map((d) => ({ d, values: toArray(shiftSequence(x, d)) }));
  },

  /** 音訊那一側的訊號產生器（取樣率一律由呼叫端給，絕不寫死）。 */
  audioSignals({ sampleRate, clickMillis, pluckSeconds, gapSeconds }) {
    const click = clickSignal(sampleRate, { millis: clickMillis });
    const pluck = pluckSignal(sampleRate, { seconds: pluckSeconds });
    const padded = padSilence(click, sampleRate, gapSeconds);
    return {
      clickLength: click.length,
      clickPeak: peakAmplitude(click),
      clickEnds: [click[0], click[click.length - 1]],
      clickSum: Array.from(click).reduce((a, b) => a + b, 0),
      pluckLength: pluck.length,
      pluckPeak: peakAmplitude(pluck),
      pluckFirstQuarterPeak: peakAmplitude(pluck.slice(0, Math.floor(pluck.length / 4))),
      pluckLastQuarterPeak: peakAmplitude(pluck.slice(Math.floor((3 * pluck.length) / 4))),
      paddedLength: padded.length,
      paddedTail: padded[padded.length - 1],
    };
  },

  /** 重疊區塊的幾何（§8.4：斷言資料，不斷言像素）。 */
  overlapRegion({ t0, t1, vMin, vMax, width, height, pad, spans }) {
    const scale = makeScale({ t0, t1, vMin, vMax, width, height, pad });
    return spans.map(([from, to]) => regionRect(scale, from, to));
  },

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

  // ---------------------------------------------------- 脈衝與時頻取捨（2S11）

  /** 時域的值：形狀本身、平移、以及載波。 */
  pulseShape({ shape, width, times, shift = 0, carrierHz = 0 }) {
    return {
      support: pulseSupport(shape, width),
      envelope: times.map((t) => pulseAt(shape, t, width)),
      signal: times.map((t) => signalAt(shape, t, { width, shift, carrierHz })),
      spec: {
        tails: PULSE_SHAPES[shape].tails,
        finiteSupport: PULSE_SHAPES[shape].finiteSupport,
        continuous: PULSE_SHAPES[shape].continuous,
      },
    };
  },

  /** 繪圖用的取樣（固定視窗），以及積分用的取樣（跟著支撐走）。 */
  pulseTrace({ shape, width, tFrom, tTo, count, shift = 0, carrierHz = 0 }) {
    const trace = tracePulse(shape, { width, shift, carrierHz }, tFrom, tTo, count);
    return { times: toArray(trace.times), values: toArray(trace.values) };
  },

  /**
   * **這一頁的核心 case**：對同一組參數，數值積分與閉合式各算一次。
   *
   * 兩者都吐出來，由 Python 那一側分別與 SymPy 的參考值比對——
   * 不在這裡比，否則兩條路徑就在 node 裡合流了。
   */
  pulseSpectrum({ shape, width, frequencies, shift = 0, carrierHz = 0, samples = null }) {
    const options = { width, shift, carrierHz };
    const count = samples || integrationSampleCount({ shape, width, carrierHz });
    const grid = pulseSamples(shape, options, count);
    const numeric = fourierIntegral(grid.values, grid.dt, grid.tStart, frequencies);
    const closed = analyticSpectrum(shape, options, frequencies);
    const unshifted = analyticSpectrum(shape, { ...options, shift: 0 }, frequencies);
    const peak = pulseArea(shape, width) * (carrierHz > 0 ? 0.5 : 1);
    return {
      samples: count,
      dt: grid.dt,
      tStart: grid.tStart,
      peak,
      numeric: {
        re: toArray(numeric.re),
        im: toArray(numeric.im),
        magnitude: toArray(numeric.magnitude),
        phase: toArray(numeric.phase),
      },
      closed: {
        re: toArray(closed.re),
        im: toArray(closed.im),
        magnitude: toArray(closed.magnitude),
        phase: toArray(closed.phase),
      },
      unshiftedMagnitude: toArray(unshifted.magnitude),
      shiftGap: maxAbsoluteGap(closed.magnitude, unshifted.magnitude),
      agreement: maxAbsoluteGap(numeric.magnitude, closed.magnitude) / peak,
    };
  },

  /** 無因次的正規化頻譜 g(u) = X(f)/X(0)。閉合式的骨架。 */
  pulseNormalised({ shape, us }) {
    return { g: us.map((u) => normalisedPulseSpectrum(shape, u)), sinc: us.map(sinc) };
  },

  /** 寬度、零點、半功率頻寬、RMS 展寬——讀數與那張階梯表用的全部數字。 */
  pulseWidths({ shape, widths }) {
    return widths.map((width) => {
      const rms = rmsWidths(shape, width);
      const bandwidth = halfPowerBandwidth(shape, width);
      return {
        width,
        area: pulseArea(shape, width),
        firstNull: firstNullFrequency(shape, width),
        bandwidth,
        bandwidthTimesWidth: bandwidth * width,
        deltaT: rms.deltaT,
        deltaF: rms.deltaF,
        product: rms.product,
        bound: rms.bound,
      };
    });
  },

  /** 兩個「一次重繪要做多少事」的預算函式。 */
  pulseBudget({ cases }) {
    return cases.map(({ shape, width, carrierHz }) => {
      const samples = integrationSampleCount({ shape, width, carrierHz });
      const points = spectrumPointCount(samples);
      return { shape, width, carrierHz, samples, points, work: samples * points };
    });
  },

  /** 音訊那一段：脈衝放在一段靜音的正中央。 */
  pulseAudio({ shape, width, carrierHz, seconds, sampleRate }) {
    const burst = pulseBurst(sampleRate, { shape, width, carrierHz, seconds });
    const frames = burst.length;
    const quarter = Math.floor(frames / 8);
    let edgePeak = 0;
    for (let i = 0; i < quarter; i += 1) {
      edgePeak = Math.max(edgePeak, Math.abs(burst[i]), Math.abs(burst[frames - 1 - i]));
    }
    let energy = 0;
    for (let i = 0; i < frames; i += 1) energy += burst[i] * burst[i];
    return {
      frames,
      peak: peakAmplitude(burst),
      edgePeak,
      energy: energy / sampleRate,
      bound: UNCERTAINTY_BOUND,
    };
  },

  /** 相位圖：在繞回 ±π 的地方切開，不要畫出假的垂直線。 */
  phaseSegments({ t0, t1, vMin, vMax, width, height, pad, times, values, maxRise }) {
    const scale = makeScale({ t0, t1, vMin, vMax, width, height, pad });
    const points = curvePoints(scale, times, values);
    return splitOnJumps(points, maxRise).map((segment) => segment.map((p) => [p.x, p.y]));
  },

  // ---------------------------------------------------- 極零點與數位濾波器（2S9）

  /**
   * 極零點 → 差分方程的係數。Python 那一側拿 SymPy 展開 ∏(1 − p_k z⁻¹)
   * 對照，那是一條完全不知道自己在處理濾波器的路徑。
   */
  polezeroCoefficients({ zeros = [], poles = [], gain = 1 }) {
    const { b, a } = filterCoefficients({ zeros, poles, gain });
    return {
      b: toArray(b),
      a: toArray(a),
      sections: {
        zeros: zeros.map((pair) => toArray(pairSection(pair))),
        poles: poles.map((pair) => toArray(pairSection(pair))),
      },
      // 未乘上增益的分子。`b` 是它乘上 gain 的結果，所以兩者一起吐出來
      // 讓「gain 到底乘在哪一邊」這件事有測試守得住。
      numeratorWithoutGain: toArray(polynomialFromPairs(zeros)),
      sliderMaxRadius: POLE_ZERO_MAX_RADIUS,
      maxPoleRadius: maxPoleRadius(poles),
      stable: isStable(poles),
      insideTriangle: isStableSecondOrder(a),
    };
  },

  /**
   * **這一頁的核心 case**：同一組 ω 上，兩條獨立路徑各算一次 H(e^{jω})。
   *
   * 一條先把根展開成多項式再求值，一條完全不展開（距離連乘）。
   * 兩者都吐出來，由 Python 那一側各自與解析式比對——**不在這裡比**，
   * 否則兩條路徑就在 node 裡合流了（§8.4 開頭那句話）。
   */
  polezeroResponse({ zeros = [], poles = [], gain = 1, omegas }) {
    const { b, a } = filterCoefficients({ zeros, poles, gain });
    const fromCoefficients = omegas.map((w) => responseFromCoefficients(b, a, w));
    const fromPairs = omegas.map((w) => responseFromPairs({ zeros, poles, gain }, w));
    const curve = responseCurve(b, a, Float64Array.from(omegas));
    return {
      b: toArray(b),
      a: toArray(a),
      coefficients: {
        re: fromCoefficients.map((h) => h.re),
        im: fromCoefficients.map((h) => h.im),
        magnitude: fromCoefficients.map((h) => h.magnitude),
        phase: fromCoefficients.map((h) => h.phase),
      },
      pairs: {
        re: fromPairs.map((h) => h.re),
        im: fromPairs.map((h) => h.im),
        magnitude: fromPairs.map((h) => h.magnitude),
        phase: fromPairs.map((h) => h.phase),
      },
      curve: { magnitude: toArray(curve.magnitude), phase: toArray(curve.phase) },
    };
  },

  /** 差分方程遞迴與衝激響應。 */
  polezeroSequence({ zeros = [], poles = [], gain = 1, x = null, count = 32 }) {
    const { b, a } = filterCoefficients({ zeros, poles, gain });
    const impulse = filterImpulseResponse(b, a, count);
    return {
      b: toArray(b),
      a: toArray(a),
      impulse: toArray(impulse),
      filtered: x ? toArray(filterSequence(b, a, x)) : null,
    };
  },

  /** 讀數列上那幾個量：峰值、安全增益、半功率寬度、衰減時間常數。 */
  polezeroMetrics({ zeros = [], poles = [], gain = 1 }) {
    const { b, a } = filterCoefficients({ zeros, poles, gain });
    const peak = peakGain(b, a);
    return {
      peakMagnitude: peak.magnitude,
      peakOmega: peak.omega,
      safetyGain: safetyGain(b, a),
      halfPowerWidth: halfPowerWidth(b, a, peak.omega),
      decaySamples: poles.map(({ r }) => {
        const value = decaySamples(r);
        return Number.isFinite(value) ? value : null;
      }),
    };
  },

  /** 一整批分母各自在不在穩定三角形裡。Python 那一側拿二次公式解根對照。 */
  polezeroTriangle({ denominators }) {
    return denominators.map((a) => ({
      a,
      insideTriangle: isStableSecondOrder(Float64Array.from(a)),
    }));
  },

  /**
   * 兩組係數之間的內插，以及**沿途每一個 t 的穩定性**。
   *
   * 這一 case 存在的理由是音訊安全的第三層：worklet 換係數時走的就是這條
   * 線段，而「線段整段都在穩定域內」是它不會爆的全部根據。
   */
  polezeroBlend({ cases }) {
    return cases.map(({ from, to, ts }) => ts.map((t) => {
      const blended = blendCoefficients(
        { b: Float64Array.from(from.b), a: Float64Array.from(from.a) },
        { b: Float64Array.from(to.b), a: Float64Array.from(to.a) },
        t,
      );
      return {
        t,
        b: toArray(blended.b),
        a: toArray(blended.a),
        insideTriangle: isStableSecondOrder(blended.a),
      };
    }));
  },

  /** worklet 的遞迴：與 `filterSequence()` 逐格比對用。 */
  polezeroWorklet({ b, a, x, blockSize = 128, then = null }) {
    const run = runPoleZeroWorklet({ b, a, x, blockSize, then });
    return {
      output: run.output,
      pure: toArray(filterSequence(Float64Array.from(b), Float64Array.from(a),
        Float64Array.from(x))),
      messages: run.sent,
    };
  },

  /** 第三層防護：故意送一組會發散的係數進去，看守必須跳。 */
  polezeroWorkletOverload({ b, a, x, blockSize = 128 }) {
    const run = runPoleZeroWorklet({ b, a, x, blockSize });
    return {
      output: run.output,
      messages: run.sent,
      peak: run.output.reduce((m, v) => Math.max(m, Math.abs(v)), 0),
    };
  },

  /**
   * z 平面的幾何：等比例、往返一致、以及命中測試。
   *
   * 「兩軸每單位像素數相同」是這張圖唯一不能妥協的性質——不等比例的話
   * 單位圓變成橢圓，而學生從圖上讀到的**角度**就是錯的，而角度就是頻率。
   */
  complexGeometry({ span, width, height, pad, points, probe, maxDistance }) {
    const scale = makeComplexScale({ span, width, height, pad });
    const mapped = points.map(([re, im]) => {
      const p = complexPoint(scale, re, im);
      const back = scale.at(p.x, p.y);
      return { re, im, x: p.x, y: p.y, backRe: back.re, backIm: back.im };
    });
    const handles = mapped.map((m, i) => ({ id: i, x: m.x, y: m.y }));
    const hit = probe
      ? nearestHandle(handles, { x: probe[0], y: probe[1] }, maxDistance)
      : null;
    return {
      unit: scale.unit,
      cx: scale.cx,
      cy: scale.cy,
      side: scale.side,
      // 兩軸的每單位像素數：一個資料單位在 x 上與在 y 上各佔幾個像素。
      unitX: scale.x(1) - scale.x(0),
      unitY: scale.y(0) - scale.y(1),
      mapped,
      hit: hit ? { id: hit.handle.id, distance: hit.distance } : null,
    };
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
