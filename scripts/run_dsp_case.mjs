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
} from '../app/static/demos/lib/signal.js';
import {
  nyquist, aliasFrequency, signedAliasFrequency, isAliased, aliasSign,
  fft, ifft, radix2Fft, isPowerOfTwo, nextPowerOfTwo,
  windowCoefficients, windowCoherentGain, applyWindow, zeroPad, WINDOWS,
  amplitudeSpectrum, binFrequencies, binSpacing, observationSeconds,
  nearestBinFrequency, toDecibels, spectrumToDecibels, findPeaks,
  interpolatePeakBin, spectrum, DB_FLOOR,
} from '../app/static/demos/lib/transform.js';
import {
  makeScale, curvePoints, staircasePoints, viridisColor, dbToUnit, relativeLuminance,
} from '../app/static/demos/lib/draw.js';

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
