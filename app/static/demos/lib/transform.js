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

// ================================ Fourier 級數的係數（2S5，PLAN §8.2.1 第 3 列）
//
// 分工見 `signal.js` 那一段的開頭：**波形在 signal.js，係數在這裡**，
// 兩邊互不 import，接點是一個普通物件 `series`。
//
// ⚠️ **這裡的係數是閉合式，不是數值積分。** 這與 §8.4 的精神一致但方向相反：
// 展示端跑的是閉合式（快、精確、看得懂），而**驗證端**（`scripts/dsp_reference.py`）
// 用 SymPy 對定義式 `bₙ = (1/π)∫₀^{2π} x(θ) sin(nθ) dθ` 真的積一次分。
// 兩條路徑因此完全獨立：閉合式抄錯一個 π 或一個 (-1)^n，SymPy 那邊不會跟著錯。
//
// 慣例（整份專案只有這一組）：
//
//     x(θ) = a₀/2 + Σₙ ( aₙ cos nθ + bₙ sin nθ )       θ = 2π f₀ t
//          = dc   + Σₙ Aₙ sin(nθ + φₙ)
//     Aₙ = hypot(aₙ, bₙ)          φₙ = atan2(aₙ, bₙ)
//
// `atan2(a, b)`（不是 `atan2(b, a)`）是對的：把 A sin(nθ+φ) 展開得到
// b = A cos φ 與 a = A sin φ，所以 φ 的 tan 是 a/b。這一行寫反的症狀是
// 所有相位差 90°——頻譜完全不變，波形完全不對。

/** 支援的目標波形。鍵與 `signal.js` 的 `WAVEFORMS` 逐字相同。 */
export const FOURIER_KINDS = ['square', 'sawtooth', 'triangle', 'halfWave'];

/**
 * 第 n 次諧波的 (aₙ, bₙ)。四個波形的閉合式，逐個對照課本。
 *
 * 方波與鋸齒的 1/n、三角與半波整流的 1/n²——**這個差別就是收斂速度**，
 * 也是這一頁四個波形要學生對照的東西，所以四個都留著。
 */
function coefficientPair(kind, n) {
  const odd = n % 2 === 1;
  switch (kind) {
    // x = +1 on (0, π), -1 on (π, 2π)：奇函數，只有 sin，只有奇次。
    case 'square':
      return { cosine: 0, sine: odd ? 4 / (n * Math.PI) : 0 };

    // x = θ/π on (-π, π)：奇函數，每一次諧波都在，正負交替。
    // ⚠️ 分母的 π 不是裝飾：bₙ = (1/π²)∫₋π^π θ sin nθ dθ，而那個積分
    // 是 2π(-1)^{n+1}/n，所以 bₙ = 2(-1)^{n+1}/(πn)。第一版把 π 漏掉，
    // 症狀是基波振幅 2 而不是 0.637——部分和整整大三倍，卻仍然「長得像
    // 鋸齒波」（形狀對、尺度錯），畫面上看不出來。抓到它的是把部分和
    // 拿去量過衝：一個不該超過 1.18 的東西量出 2.9。
    case 'sawtooth':
      return { cosine: 0, sine: (2 * (odd ? 1 : -1)) / (Math.PI * n) };

    // 奇對稱三角波，峰值 +1 落在 θ = π/2：只有奇次，符號每兩次翻一次。
    case 'triangle':
      return {
        cosine: 0,
        sine: odd
          ? (8 * (((n - 1) / 2) % 2 === 0 ? 1 : -1)) / (Math.PI * Math.PI * n * n)
          : 0,
      };

    // 半波整流的 sin：直流 1/π、基波 1/2、其餘只有**偶次的 cos**。
    // 這一個是四個裡唯一同時有 cos 與 sin 的，所以它是「一般情況」的例子。
    case 'halfWave':
      if (n === 1) return { cosine: 0, sine: 0.5 };
      return {
        cosine: odd ? 0 : -2 / (Math.PI * (n * n - 1)),
        sine: 0,
      };

    default:
      throw new Error(`unknown waveform: ${kind}`);
  }
}

/** 直流項 a₀/2。只有半波整流不是 0（它整段都在零以上）。 */
function directCurrent(kind) {
  return kind === 'halfWave' ? 1 / Math.PI : 0;
}

/**
 * 前 `count` 次諧波的完整係數。
 *
 * ⚠️ **振幅為 0 的諧波仍然留在陣列裡**，不過濾掉。方波的長條圖上那一排
 * 空掉的偶數格是這一頁的教學內容之一（「為什麼方波沒有第 2 次諧波」），
 * 過濾掉之後那件事在畫面上就消失了。
 */
export function fourierCoefficients(kind, count) {
  if (!FOURIER_KINDS.includes(kind)) throw new Error(`unknown waveform: ${kind}`);
  const harmonics = [];
  for (let n = 1; n <= count; n += 1) {
    const { cosine, sine } = coefficientPair(kind, n);
    const amplitude = Math.hypot(cosine, sine);
    harmonics.push({
      n,
      cosine,
      sine,
      amplitude,
      phase: amplitude === 0 ? 0 : Math.atan2(cosine, sine),
    });
  }
  return { kind, dc: directCurrent(kind), harmonics };
}

/**
 * 三角形式 → 指數形式：cₙ = (aₙ - i bₙ)/2。
 *
 * 課綱第 3 週要求兩種形式的對應，而學生最常記錯的是**那個 1/2**
 * （|cₙ| 是振幅的一半，因為能量被分給了 +n 與 -n 兩邊）與
 * **c₋ₙ = conj(cₙ)**（實數訊號的頻譜共軛對稱，這也正是
 * `amplitudeSpectrum()` 把負頻率那一半乘 2 折回來的同一件事）。
 * 兩者都由 `tests/test_dsp_js.py` 對 SymPy 的積分結果驗過。
 */
export function exponentialCoefficient(harmonic) {
  return {
    n: harmonic.n,
    re: harmonic.cosine / 2,
    im: -harmonic.sine / 2,
    magnitude: harmonic.amplitude / 2,
    // arg(cₙ) = φₙ - π/2。φ 是 sin 的相位，而 cₙ 是以 exp 為基底寫的。
    phase: harmonic.amplitude === 0 ? 0 : harmonic.phase - Math.PI / 2,
  };
}

/** 相位方案。值是英文顯示名（D5）。 */
export const PHASE_MODES = {
  series: 'As the series says',
  zero: 'All harmonics in sine phase',
  random: 'Randomised',
};

/**
 * 決定性的 PRNG（mulberry32）。
 *
 * 用它而不是 `Math.random()` 的理由很實際：**同一個 seed 必須畫出同一張圖**。
 * 否則每次重繪（改音量、換分頁回來、視窗縮放）波形都會跳一次，
 * 而學生會以為那是自己動到了什麼。「再抽一次」是一個明確的按鈕。
 */
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * 換一組相位，**振幅一個都不動**。
 *
 * ⛔ 「振幅不動」不是實作細節，它就是這一頁的論點：改相位之後波形面目全非、
 * 而頻譜（也就是長條圖，也就是音色）逐格相同。所以這支函式**只准寫 phase**，
 * 而 `tests/test_dsp_js.py` 有一項逐格比對振幅、確認這件事沒有被破壞。
 *
 * @param {object} series
 * @param {{mode?: string, seed?: number, offsets?: Record<number, number>}} options
 *        `offsets` 是「在方案之上，再把第 n 次諧波轉多少弧度」，
 *        給「個別調整某一次諧波」那個控制項用。
 */
export function applyPhaseScheme(series, { mode = 'series', seed = 1, offsets = {} } = {}) {
  const random = mulberry32(seed);
  const harmonics = series.harmonics.map((h) => {
    let phase = h.phase;
    if (mode === 'zero') phase = 0;
    // ⚠️ 即使這一格振幅是 0 也要抽一次亂數，否則同一個 seed 在方波
    // （偶次全空）與鋸齒波（每次都有）之間會抽到不同的序列，
    // 而「換個波形，第 3 次諧波的相位卻變了」是一個沒有人解釋得了的行為。
    const draw = random() * 2 * Math.PI;
    if (mode === 'random') phase = draw;
    phase += offsets[h.n] || 0;
    return {
      n: h.n,
      amplitude: h.amplitude,               // ← 一個字都不准改
      phase,
      cosine: h.amplitude * Math.sin(phase),
      sine: h.amplitude * Math.cos(phase),
    };
  });
  return { kind: series.kind, dc: series.dc, harmonics };
}

/**
 * 在取樣率 `sampleRate` 之下，**嚴格低於**奈奎斯特的最高諧波次數。
 *
 * 等號那一格刻意排除（n·f₀ = f_s/2 的成分在取樣之後只剩一個常數振幅，
 * 相位資訊全丟——它已經不是一個能聽的諧波了）。
 */
export function maxBandLimitedHarmonic(f0, sampleRate) {
  if (!(f0 > 0) || !(sampleRate > 0)) return 0;
  return Math.max(0, Math.ceil(nyquist(sampleRate) / f0) - 1);
}

/**
 * 把級數裁到帶限之內。
 *
 * ⛔ **這一步不能省。** 這一頁在教 Fourier 級數，而若它自己合成的聲音
 * 因為諧波超過奈奎斯特而混疊，畫面上第 40 次諧波的長條就會在耳朵裡
 * 變成一個位置錯誤的音——在一個下週要教混疊的課裡，那會很難看。
 * 混疊展示（2S3）與範例音檔的產生腳本都已經處理過同一件事。
 *
 * 回傳 `dropped > 0` 時，呼叫端**必須在畫面上說出來**（規則 4：
 * 「只播了前 12 次諧波」是一個有意義的降級，但它得說出口）。
 */
export function bandLimit(series, f0, sampleRate) {
  const limit = maxBandLimitedHarmonic(f0, sampleRate);
  const kept = series.harmonics.filter((h) => h.n <= limit);
  return {
    series: { kind: series.kind, dc: series.dc, harmonics: kept },
    limit,
    dropped: series.harmonics.length - kept.length,
  };
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
