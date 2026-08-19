// 變換層（PLAN.md §8.2.3 第二段）。
//
// 與 signal.js 一樣是**純函式**，不知道 DOM 與 AudioContext 存在。
//
// 內容分成兩半：
//
//   * **頻率軸上的換算**（奈奎斯特、混疊）——2S3 混疊展示用的那組。
//   * **FFT 與頻譜**（2S1 新增）——vendored 的 radix-4 跑在執行期，
//     另有一支可讀的 radix-2 標為教學用。兩支**通過完全相同的測試**（§8.3）。
//
// ⚠️ **關於「兩支 FFT」這件事，唯一重要的紀律寫在這裡**：
// `radix2Fft` 是教材，不在熱路徑上；但它**不得**因此享有比較寬鬆的驗證。
// `tests/test_dsp_js.py` 的每一項數值斷言都對 `impl` 參數做 parametrize，
// 兩支各跑一次。一支說謊的教材比沒有教材更糟——學生會相信它。

// vendored 的 radix-4 FFT（fft.js 4.0.4，MIT）。選型與被淘汰的候選見 §8.3、D31。
// 這是這一層唯一的外部相依，走的是 app/static/vendor/ 既有的那套自架慣例。
import FFT from '../../vendor/fftjs/fft.js';

// ============================================================ 頻率軸上的換算

/** 奈奎斯特頻率。取樣率 fs 之下，能無歧義表示的最高頻率。 */
export function nyquist(fs) {
  return fs / 2;
}

/**
 * **有號**的混疊頻率：f - round(f/fs) * fs，落在 [-fs/2, fs/2]。
 *
 * 有號是重點，不是多餘的細節。取樣之後，
 *
 *     sin(2π f n/fs) = sin(2π (f - k fs) n/fs)
 *
 * 對任何整數 k 都成立；當 f - k·fs 是負的，那條穿過同一組取樣點的低頻正弦
 * 是**倒相**的（sin(-x) = -sin x）。畫重建波形時如果只用絕對值，
 * 波形會與取樣點對不上——而那是一個看得見、卻很容易被當成「畫錯了」的錯誤。
 */
export function signedAliasFrequency(f, fs) {
  if (fs <= 0) return f;
  return f - Math.round(f / fs) * fs;
}

/**
 * 混疊後的**表觀頻率**（人耳聽到、也是畫面上要顯示的那個數字），恆為非負。
 *
 * f <= fs/2 時它就等於 f 自己（沒有混疊，公式自動退化）。
 */
export function aliasFrequency(f, fs) {
  return Math.abs(signedAliasFrequency(f, fs));
}

/** 有沒有發生混疊：訊號頻率是否超過奈奎斯特頻率。 */
export function isAliased(f, fs) {
  return f > nyquist(fs);
}

/**
 * 摺疊的方向：混疊後的正弦相對原訊號是同相還是反相。
 * 回傳 +1 或 -1，供繪圖層決定重建波形的正負號。
 */
export function aliasSign(f, fs) {
  const signed = signedAliasFrequency(f, fs);
  return signed < 0 ? -1 : 1;
}

// ==================================================================== FFT
//
// 慣例（整份專案只有這一組，寫在這裡以免日後有第二種）：
//
//     X[k] = Σ_{n=0}^{N-1} x[n] · exp(-2πi·kn/N)        （正變換，無縮放）
//     x[n] = (1/N) Σ_{k=0}^{N-1} X[k] · exp(+2πi·kn/N)  （反變換，1/N 在這邊）
//
// 這與 vendored fft.js 的慣例相同（它的 twiddle 表是 cos - i·sin，
// `inverseTransform` 除以 size），也與 `scripts/dsp_reference.py` 與
// `tests/test_dsp_js.py` 的樸素 DFT 相同。**三處必須一致，否則交叉驗證
// 會在一個看起來很像對的地方失敗**（§8.3：FFT 的錯法都很安靜）。
//
// 複數一律用 `{re, im}` 兩個等長的 Float64Array 表示，不用交錯陣列——
// 交錯陣列（fft.js 內部用的那種）省一次配置，但 `x[2*k+1]` 這種索引是
// 差一錯誤的溫床，而這一層的可讀性比省下的幾微秒值錢得多。

/** 2 的次方判斷。FFT 的長度限制，錯了要早點說出來而不是算出垃圾。 */
export function isPowerOfTwo(n) {
  return Number.isInteger(n) && n > 1 && (n & (n - 1)) === 0;
}

/** 不小於 n 的最小 2 次方。zero-padding 的目標長度用得到。 */
export function nextPowerOfTwo(n) {
  let p = 1;
  while (p < n) p *= 2;
  return p;
}

// fft.js 的實例會預先算好 twiddle 表，所以**按長度快取**，不要每格重建。
// 長度只有五、六種（256…8192），這個 Map 不會長大。
const _plans = new Map();

function planFor(n) {
  if (!isPowerOfTwo(n)) {
    throw new Error(`FFT length must be a power of two, got ${n}`);
  }
  let plan = _plans.get(n);
  if (!plan) {
    plan = new FFT(n);
    _plans.set(n, plan);
  }
  return plan;
}

function toInterleaved(re, im, n) {
  const buf = new Array(2 * n);
  for (let i = 0; i < n; i += 1) {
    buf[2 * i] = re[i];
    buf[2 * i + 1] = im ? im[i] : 0;
  }
  return buf;
}

function fromInterleaved(buf, n) {
  const re = new Float64Array(n);
  const im = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    re[i] = buf[2 * i];
    im[i] = buf[2 * i + 1];
  }
  return { re, im };
}

/**
 * 正變換（執行期用的那一支，vendored radix-4）。
 *
 * @param {ArrayLike<number>} re 實部
 * @param {ArrayLike<number>} [im] 虛部；省略視為全 0
 * @returns {{re: Float64Array, im: Float64Array}} 長度 N 的完整頻譜
 */
export function fft(re, im = null) {
  const n = re.length;
  const plan = planFor(n);
  const out = plan.createComplexArray();
  plan.transform(out, toInterleaved(re, im, n));
  return fromInterleaved(out, n);
}

/** 反變換。1/N 在這一邊（見上面的慣例）。 */
export function ifft(re, im = null) {
  const n = re.length;
  const plan = planFor(n);
  const out = plan.createComplexArray();
  plan.inverseTransform(out, toInterleaved(re, im, n));
  return fromInterleaved(out, n);
}

/**
 * **教學用的 radix-2 Cooley–Tukey**（§8.3：教學透明度換一個位置兌現）。
 *
 * `// teaching reference — not on the hot path`
 *
 * 執行期跑的是上面那支 vendored 的；這一支存在是為了讓學生（與助教）
 * 能打開來讀完整個演算法。它做的事就三步：
 *
 *   1. **位元反轉重排**。長度 8 的輸入 x[0..7] 先重排成
 *      x[0], x[4], x[2], x[6], x[1], x[5], x[3], x[7]——
 *      索引寫成二進位之後把位元順序倒過來（0=000→000, 1=001→100, …）。
 *      這麼做之後，接下來的蝴蝶運算就可以完全就地（in-place）進行。
 *   2. **log2(N) 層蝴蝶運算**。第 s 層把長度 2^s 的子變換兩兩合併成
 *      長度 2^(s+1) 的：對每一對 (a, b)，
 *          a' = a + w·b,   b' = a - w·b
 *      這一對加減就是「蝴蝶」的名字來源（畫成訊號流圖是一個交叉的 X）。
 *   3. **twiddle factor** w = exp(∓2πi·j/m)，正變換取負號。
 *      N=8 時第一層用 w=1，第二層用 {1, -i}，第三層用
 *      {1, (1-i)/√2, -i, -(1+i)/√2}——這八個點就是單位圓上的八等分。
 *
 * ⚠️ 它**不是**一個放寬過的版本：`tests/test_dsp_js.py` 的每一項數值斷言
 * 都會拿它跑一次（與 vendored 那支完全相同的測試）。
 *
 * @param {ArrayLike<number>} reIn
 * @param {ArrayLike<number>} [imIn]
 * @param {{inverse?: boolean}} [options]
 */
export function radix2Fft(reIn, imIn = null, { inverse = false } = {}) {
  const n = reIn.length;
  if (!isPowerOfTwo(n)) {
    throw new Error(`FFT length must be a power of two, got ${n}`);
  }
  const re = Float64Array.from(reIn);
  const im = new Float64Array(n);
  if (imIn) for (let i = 0; i < n; i += 1) im[i] = imIn[i];

  // --- 1. 位元反轉重排 -----------------------------------------------------
  // j 是「i 的位元反轉」，用增量的方式維護：從最高位開始進位。
  for (let i = 1, j = 0; i < n; i += 1) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      let t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }

  // --- 2. log2(N) 層蝴蝶運算 ----------------------------------------------
  const sign = inverse ? +1 : -1;          // 正變換是 exp(-2πi…)
  for (let len = 2; len <= n; len <<= 1) {
    const step = (sign * 2 * Math.PI) / len;
    for (let start = 0; start < n; start += len) {
      for (let k = 0; k < len / 2; k += 1) {
        // --- 3. twiddle factor
        const angle = step * k;
        const wr = Math.cos(angle);
        const wi = Math.sin(angle);
        const a = start + k;
        const b = a + len / 2;
        const xr = re[b] * wr - im[b] * wi;   // w · x[b]
        const xi = re[b] * wi + im[b] * wr;
        re[b] = re[a] - xr;                   // 蝴蝶的下半：a - w·b
        im[b] = im[a] - xi;
        re[a] += xr;                          // 蝴蝶的上半：a + w·b
        im[a] += xi;
      }
    }
  }

  // 反變換的 1/N（見本節開頭的慣例）。
  if (inverse) {
    for (let i = 0; i < n; i += 1) { re[i] /= n; im[i] /= n; }
  }
  return { re, im };
}

// ============================================================== 視窗函數
//
// **分母是 N，不是 N-1**（週期版，periodic）。這不是一個可以隨手選的細節：
// DFT 假設訊號以 N 為週期地重複，而週期版的視窗是唯一能讓「視窗本身的 DFT
// 只有少數幾格非零」成立的定義——對稱版（分母 N-1，濾波器設計用的那個）
// 會讓 Hann 窗的頻譜多出一點點洩漏，看起來像我們自己算錯了。
// §8.4 第 2 類驗證（解析解對照）就是拿來抓這種差一錯誤的。

/** 支援的視窗。鍵是程式用的名字，值是英文顯示名（D5）。 */
export const WINDOWS = {
  rectangular: 'Rectangular (no window)',
  hann: 'Hann',
  hamming: 'Hamming',
  blackman: 'Blackman',
};

/**
 * 視窗的係數。回傳長度 n 的 Float64Array。
 *
 * 矩形窗回傳全 1——它**是**一個視窗，只是係數都是 1。把「不加窗」寫成
 * 一個特例會讓下游到處都是 if；寫成全 1 的陣列則讓「不加窗其實就是
 * 乘上一個矩形」這件事在程式裡也是明白的，而那正是這個展示要教的。
 */
export function windowCoefficients(name, n) {
  const w = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const x = (2 * Math.PI * i) / n;        // ← 分母 N，見上面
    switch (name) {
      case 'hann':     w[i] = 0.5 - 0.5 * Math.cos(x); break;
      case 'hamming':  w[i] = 0.54 - 0.46 * Math.cos(x); break;
      case 'blackman': w[i] = 0.42 - 0.5 * Math.cos(x) + 0.08 * Math.cos(2 * x); break;
      case 'rectangular': w[i] = 1; break;
      default: throw new Error(`unknown window: ${name}`);
    }
  }
  return w;
}

/**
 * 相干增益（coherent gain）＝視窗係數的平均值。
 *
 * 加窗會把訊號整體壓小（Hann 壓到一半），所以要讓「畫面上的峰值高度等於
 * 訊號的振幅」，必須除掉這個數。矩形窗是 1，Hann 是 0.5，Hamming 是 0.54，
 * Blackman 是 0.42——這四個數字剛好就是各自公式裡的常數項，
 * 因為其餘各項都是整週期的餘弦，平均為 0。**這是一個可以用眼睛驗證的結果**，
 * 所以測試裡直接斷言它。
 */
export function windowCoherentGain(name, n) {
  const w = windowCoefficients(name, n);
  let sum = 0;
  for (let i = 0; i < n; i += 1) sum += w[i];
  return sum / n;
}

/** 逐點相乘。長度不符是呼叫端的錯，早點爆掉比默默算錯好。 */
export function applyWindow(samples, name) {
  const n = samples.length;
  const w = windowCoefficients(name, n);
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = samples[i] * w[i];
  return out;
}

/**
 * 補零到 targetLength。
 *
 * ⚠️ **這不會提高頻率解析度**，這正是 Demo 2 要糾正的第二個誤解。
 * 解析度由觀測時間 T = N/fs 決定（兩個頻率要分得開，必須 |f1 - f2| > 1/T）；
 * 補零只是把同一條連續頻譜在更多點上取值，也就是**畫得比較密**。
 * 這句話寫在這裡是因為改這個函式的人最需要知道它。
 */
export function zeroPad(samples, targetLength) {
  if (targetLength < samples.length) {
    throw new Error('zeroPad cannot shorten the signal');
  }
  const out = new Float64Array(targetLength);
  out.set(samples, 0);
  return out;
}

// ========================================================== 幅度與頻率軸

/**
 * 單邊幅度譜，已經換算成**訊號的振幅**。
 *
 * 三件事一起做，因為分開做就會有人只做一半：
 *   1. 只取 k = 0…N/2（實數訊號的頻譜是共軛對稱的，右半是左半的鏡像）
 *   2. 除以 N，再乘 2（把負頻率那一半的能量折回來）——
 *      **DC (k=0) 與奈奎斯特 (k=N/2) 不乘 2**，它們沒有對應的負頻率夥伴
 *   3. 除以視窗的相干增益（見 windowCoherentGain）
 *
 * 結果的意義很具體：一個振幅 A、頻率剛好落在 bin 中心的正弦，
 * 在那一格上讀到的就是 A。§8.4 第 2 類驗證斷言的就是這件事。
 */
export function amplitudeSpectrum({ re, im }, { coherentGain = 1 } = {}) {
  const n = re.length;
  const half = n / 2;
  const out = new Float64Array(half + 1);
  for (let k = 0; k <= half; k += 1) {
    const mag = Math.hypot(re[k], im[k]);
    const fold = (k === 0 || k === half) ? 1 : 2;
    out[k] = (fold * mag) / (n * coherentGain);
  }
  return out;
}

/** 每一格對應的頻率：k·fs/N，k = 0…N/2。**分母是 N，不是 N-1**。 */
export function binFrequencies(n, fs) {
  const half = n / 2;
  const out = new Float64Array(half + 1);
  for (let k = 0; k <= half; k += 1) out[k] = (k * fs) / n;
  return out;
}

/** 頻率解析度（相鄰兩格的間隔）Δf = fs/N，也就是 1/T。 */
export function binSpacing(n, fs) {
  return fs / n;
}

/** 觀測時間 T = N/fs。解析度真正的來源——補零改不了它。 */
export function observationSeconds(n, fs) {
  return n / fs;
}

/** 最接近 f 的 bin 中心頻率。「把頻率對準格線」那個按鈕用它。 */
export function nearestBinFrequency(f, fs, n) {
  const spacing = binSpacing(n, fs);
  return Math.round(f / spacing) * spacing;
}

/** dB 下限。-120 dB 已經在任何裝置的雜訊底下，再低只是畫空氣。 */
export const DB_FLOOR = -120;

/**
 * 換算成 dB（幅度，所以是 20log10）。
 *
 * 夾在 DB_FLOOR 是**繪圖的需要**，不是資料的性質——所以它有一個明確的
 * 參數而不是寫死，而且 §8.4 說「凡是要斷言的數字都不能經過被夾過的路徑」。
 */
export function toDecibels(value, floor = DB_FLOOR) {
  if (!(value > 0)) return floor;
  const db = 20 * Math.log10(value);
  return db < floor ? floor : db;
}

/** 整條頻譜換成 dB。 */
export function spectrumToDecibels(amplitudes, floor = DB_FLOOR) {
  const out = new Float64Array(amplitudes.length);
  for (let i = 0; i < amplitudes.length; i += 1) out[i] = toDecibels(amplitudes[i], floor);
  return out;
}

/**
 * 找出最高的幾個**局部**峰值，回傳 {bin, value} 由大到小。
 *
 * 只取局部極大值（比左右鄰居都高），否則一根譜線的裙擺會佔滿前三名，
 * 而「畫面上算出來的那句描述」（§8.6 第 3 點）就會變成
 * `440 Hz, 441 Hz, 439 Hz`——技術上正確，教學上毫無用處。
 */
export function findPeaks(amplitudes, count = 3) {
  const peaks = [];
  for (let k = 1; k < amplitudes.length - 1; k += 1) {
    if (amplitudes[k] > amplitudes[k - 1] && amplitudes[k] >= amplitudes[k + 1]) {
      peaks.push({ bin: k, value: amplitudes[k] });
    }
  }
  peaks.sort((a, b) => b.value - a.value);
  return peaks.slice(0, count);
}

/**
 * 峰值的次格內插（拋物線）。
 *
 * 峰值真正的頻率幾乎不會剛好落在格子上，所以直接讀 `bin * fs / N` 會有
 * 最多半格的誤差——在 N = 1024、fs = 48 kHz 時那是 23 Hz，
 * 對一個標著「你聽到的頻率」的讀數來說太大了。
 * 用峰值與左右兩個鄰居配一條拋物線，取頂點的位置，誤差降到一格的百分之幾。
 *
 * 回傳的是**分數格號**，呼叫端自己乘 fs/N。
 */
export function interpolatePeakBin(amplitudes, k) {
  if (k <= 0 || k >= amplitudes.length - 1) return k;
  const a = amplitudes[k - 1];
  const b = amplitudes[k];
  const c = amplitudes[k + 1];
  const denom = a - 2 * b + c;
  if (denom === 0) return k;
  const delta = (0.5 * (a - c)) / denom;
  // 拋物線頂點理論上落在 ±0.5 格內；超出就是資料不成峰形，別亂修。
  if (!(delta > -1 && delta < 1)) return k;
  return k + delta;
}

/**
 * 一次做完「加窗 → 補零 → FFT → 幅度譜」。
 *
 * 這是展示層真正呼叫的那一支；上面那些小函式是它的零件，也是測試的把手。
 *
 * @param {ArrayLike<number>} samples 時域樣本（長度不必是 2 的次方）
 * @param {object} options
 * @param {string} options.window 視窗名稱
 * @param {number} options.fs 取樣率（Hz）
 * @param {number} [options.padTo] 補零後的長度；省略則用 samples 的長度
 * @param {(re: ArrayLike<number>) => {re: Float64Array, im: Float64Array}} [options.transform]
 *        變換的實作。預設是 vendored 的那支；測試會把教學用的 radix-2 傳進來，
 *        **這就是「兩支必須通過完全相同的測試」在程式裡的接點**。
 */
export function spectrum(samples, {
  window = 'hann', fs, padTo = null, transform = fft,
} = {}) {
  const windowed = applyWindow(samples, window);
  const length = padTo || samples.length;
  const padded = length === windowed.length ? windowed : zeroPad(windowed, length);
  const spec = transform(padded);
  // ⚠️ 相干增益用**視窗本身的長度**算，不是補零後的長度——補的那些 0
  // 不屬於視窗，把它們算進平均會讓峰值高度隨補零倍率縮水。
  const gain = windowCoherentGain(window, samples.length);
  // 同理，正規化的分母應該是視窗的長度而不是補零後的長度。amplitudeSpectrum
  // 除的是 padded 的長度 N，所以這裡把比例乘回來。
  const amplitudes = amplitudeSpectrum(spec, { coherentGain: gain });
  const ratio = length / samples.length;
  if (ratio !== 1) {
    for (let i = 0; i < amplitudes.length; i += 1) amplitudes[i] *= ratio;
  }
  return {
    amplitudes,
    frequencies: binFrequencies(length, fs),
    length,
    coherentGain: gain,
  };
}
