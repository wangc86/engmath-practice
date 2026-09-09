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

// ============== 摺積與 LTI 系統（2S10，PLAN §8.2.1 第 4 列；課程 W2）
//
// **與 signal.js 的分工，與 Fourier 那一段同一條線：**
//
//   * signal.js ＝ **序列本身**：脈衝響應長什麼樣、輸入序列長什麼樣、
//     音訊用的 click／撥弦音怎麼合成。
//   * 這裡（transform.js）＝ **摺積這個運算**：定義式、快速版、逐項展開、
//     增益界、以及「這個系統是不是 LTI」的三個判準。
//
// 兩邊仍然互不 import（§8.2.3 的單向依賴：兩者都是純函式層的葉子）。
//
// ⚠️ **這一段有兩支做同一件事的函式，而那是刻意的**：`convolve()` 照定義寫
// （O(NM) 二重迴圈，短到可以逐字與課本核對），`fftConvolve()` 是執行期真正
// 在跑的那一支（一次頻域相乘）。這與 §8.4 第 1 類驗證「樸素 DFT vs 快速 FFT」
// 是**同一個模式的第二個實例**：兩條路徑必須相等，而錯的那一支不會被另一支
// 掩蓋。`tests/test_dsp_js.py` 對兩者跑同一組斷言。
//
// ⚠️ **摺積是這個專案裡最容易寫出「看起來對」的錯誤實作的東西**，
// 因為錯的結果通常仍然是一條形狀合理的曲線。四個最常見的錯法，
// 每一個都有測試盯著：輸出長度不是 N+M−1、邊界少算一格、
// 忘了翻轉（那會得到互相關）、以及索引寫成 `h[k−n]`。

/**
 * 摺積，照定義寫：y[n] = Σ_k x[k]·h[n−k]，n = 0 … N+M−2。
 *
 * 實作上把迴圈寫成「對每個 x[i]，把整條 h 加到 out[i…] 上」——那與定義式
 * 是同一件事（換一個求和次序），而且它就是這一頁要教的那句話：
 * **系統把輸入的每一個樣本各自敲一次，再把結果疊起來。**
 *
 * `x[i] === 0` 就跳過不是最佳化把戲：音訊那一側的 click 只有幾十個非零樣本，
 * 而 h 有好幾萬個，跳過之後這條路徑在瀏覽器裡是瞬間的。
 */
export function convolve(x, h) {
  const n = x.length;
  const m = h.length;
  if (n === 0 || m === 0) return new Float64Array(0);
  const out = new Float64Array(n + m - 1);
  for (let i = 0; i < n; i += 1) {
    const xi = x[i];
    if (xi === 0) continue;
    for (let j = 0; j < m; j += 1) out[i + j] += xi * h[j];
  }
  return out;
}

/** 把序列倒過來。「不翻轉會怎樣」那個開關用它，見下面的說明。 */
export function reverseSequence(x) {
  const out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i += 1) out[i] = x[x.length - 1 - i];
  return out;
}

/**
 * **一個 n 的完整展開：哪些 k 有重疊、每一項乘出什麼、加起來是多少。**
 *
 * 這一支是整個展示的核心——「翻轉—平移—相乘—求和」四個動作裡，
 * 後兩個就是它回傳的東西，而前兩個是 `flippedShiftedResponse()` 畫出來的。
 *
 * 重疊區間是 k ∈ [max(0, n−M+1), min(n, N−1)]：兩個條件分別來自
 * 「h[n−k] 要落在 0…M−1 之內」與「x[k] 要落在 0…N−1 之內」。
 * **這兩個上下限就是課本上那個令人困惑的求和上下限**，把它算出來、
 * 畫成一段陰影，比寫在公式底下有用得多。
 *
 * n 落在輸出範圍之外時回傳空的 terms 與 sum = 0（不是丟例外）——
 * 動畫會掃過整個 n 範圍，兩端本來就該是「沒有重疊」。
 */
export function convolutionStep(x, h, n) {
  const kStart = Math.max(0, n - (h.length - 1));
  const kEnd = Math.min(n, x.length - 1);
  const terms = [];
  // 與 x 等長、重疊區以外是 0。繪圖層要的是這一條（每個 k 一根棒子），
  // 而 `terms` 是表格與螢幕閱讀器要的那一份。**兩者由同一個迴圈填**，
  // 分開算的話總有一天會有一份忘了跟著改。
  const products = new Float64Array(x.length);
  let sum = 0;
  for (let k = kStart; k <= kEnd; k += 1) {
    const product = x[k] * h[n - k];
    terms.push({ k, x: x[k], h: h[n - k], product });
    products[k] = product;
    sum += product;
  }
  return {
    n, kStart, kEnd, terms, products, sum,
    overlap: Math.max(0, kEnd - kStart + 1),
  };
}

/**
 * 翻轉並平移之後的 h，取樣在 k = kFrom … kTo 上：k ↦ h[n−k]。
 *
 * 這是畫面上那條**會滑動的**曲線。範圍外補 0，因為 h 在它的支撐之外就是 0。
 *
 * ⚠️ 「不翻轉」那個開關**不在這裡實作**，它由呼叫端把 `reverseSequence(h)`
 * 傳進來達成。理由值得寫下來：把 h 先倒過來、再照常翻轉平移，畫出來
 * 恰好就是「h 保持原來的方向往右滑」——也就是學生以為的那個動作。
 * 於是**畫面與算式仍然是同一件事**，輸出長度也還是 N+M−1，
 * 不必為了一個開關多一套索引慣例（那才是真的會寫錯的地方）。
 */
export function flippedShiftedResponse(h, n, kFrom, kTo) {
  const out = new Float64Array(Math.max(0, kTo - kFrom + 1));
  for (let k = kFrom; k <= kTo; k += 1) {
    const index = n - k;
    out[k - kFrom] = (index >= 0 && index < h.length) ? h[index] : 0;
  }
  return out;
}

/**
 * 這個系統可能把訊號放大幾倍：Σ|h[n]|（h 的 ℓ¹ 範數）。
 *
 * **這是一個上界，而且是取得到的上界**——輸入取 x[k] = sign(h[n−k]) 時
 * 輸出恰好等於它。所以它不是保守估計，它就是最壞情況的峰值增益。
 *
 * ⛔ **這一支是這個展示的音訊安全機制**（§8.5）。回音與殘響是這個功能區
 * 唯一會把訊號越疊越大的東西，而處理方式是結構性的：
 * **這一頁的系統全部是 FIR（有限長的 h），完全沒有回授**，
 * 所以增益一定有限、而且這一行就算得出來。真正的無限增益要有回授
 * （y[n] 依賴 y[n−D]）才會發生，而這一頁一條那樣的路徑都沒有。
 * 剩下的工作就只是「別讓它超過 1」，那是 `normaliseResponse()` 的事。
 */
export function convolutionGainBound(h) {
  let sum = 0;
  for (let i = 0; i < h.length; i += 1) sum += Math.abs(h[i]);
  return sum;
}

/**
 * 把 h 縮到「輸出峰值不會超過輸入峰值」。回傳 `{taps, scale, bound}`。
 *
 * `scale < 1` 時呼叫端**必須在畫面上說出來**（規則 4：有意義的降級也得說出口）。
 * 不縮的話，六次回音疊起來可以到 3 倍以上，而 Web Audio 在 ±1 之外會削波——
 * 那個削波聽起來像雜訊，而學生會以為是摺積本身的性質。
 */
export function normaliseResponse(h, ceiling = 1) {
  const bound = convolutionGainBound(h);
  const scale = bound > ceiling ? ceiling / bound : 1;
  if (scale === 1) return { taps: Float64Array.from(h), scale, bound };
  const taps = new Float64Array(h.length);
  for (let i = 0; i < h.length; i += 1) taps[i] = h[i] * scale;
  return { taps, scale, bound };
}

/**
 * 快速摺積：補零到 2 的次方 → 兩邊各一次 FFT → 逐格複數相乘 → 一次 IFFT。
 *
 * **這一支是執行期真正在跑的那一支**，因為音訊那一側的規模讓定義式跑不動：
 * 3.5 秒的語音（48 kHz 下 168000 個樣本）配 0.6 秒的殘響（28800 個）是
 * 48 億次乘加，而 FFT 的版本是三次 262144 點的變換。
 *
 * 它同時是一個教學點，而且正好把 W2 接到 W5：**時域摺積 ↔ 頻域相乘**。
 * 補零到 N+M−1 以上是必要的——不補的話得到的是**循環**摺積，
 * 尾巴會繞回開頭（那個錯誤在聲音上是「回音出現在句子開頭」，
 * 很難看出來是什麼問題）。
 *
 * `transform`／`inverse` 可注入，測試會把教學用的 radix-2 傳進來
 * （與 `spectrum()` 同一個接點）。
 */
export function fftConvolve(x, h, { transform = fft, inverse = ifft } = {}) {
  const n = x.length;
  const m = h.length;
  if (n === 0 || m === 0) return new Float64Array(0);
  const length = n + m - 1;
  // 長度 1 的輸入會讓 nextPowerOfTwo 回傳 1，而 1 不是合法的 FFT 長度。
  const size = Math.max(2, nextPowerOfTwo(length));
  const xr = new Float64Array(size);
  const hr = new Float64Array(size);
  xr.set(x, 0);
  hr.set(h, 0);
  const X = transform(xr);
  const H = transform(hr);
  const re = new Float64Array(size);
  const im = new Float64Array(size);
  for (let k = 0; k < size; k += 1) {
    re[k] = X.re[k] * H.re[k] - X.im[k] * H.im[k];
    im[k] = X.re[k] * H.im[k] + X.im[k] * H.re[k];
  }
  const y = inverse(re, im);
  return y.re.slice(0, length);
}

/**
 * |H(e^{jω})| 與 ∠H(e^{jω})，ω = 2π f / f_s。**直接照定義求和，不用 FFT。**
 *
 * 用它而不是 FFT 有兩個理由：它可以在**任意**一個頻率上求值（FFT 只給格點），
 * 而且它短到可以與定義核對。頻率響應在這一頁的角色是把
 * 「h 的形狀」翻譯成「聽起來怎樣」：移動平均在直流是 1、在 f_s/L 是 0
 * （所以聽起來悶），相鄰相減在直流是 0（所以低音全沒了）。
 */
export function responseAt(h, frequency, sampleRate) {
  const omega = (2 * Math.PI * frequency) / sampleRate;
  let re = 0;
  let im = 0;
  for (let n = 0; n < h.length; n += 1) {
    re += h[n] * Math.cos(omega * n);
    im -= h[n] * Math.sin(omega * n);
  }
  return { re, im, magnitude: Math.hypot(re, im), phase: Math.atan2(im, re) };
}

/**
 * |H| 在一整段頻帶上的平均值。
 *
 * ⚠️ **這一支存在的理由是一個被實際輸出抓到的問題**，值得寫下來：原本畫面上
 * 報的是單一頻率的 |H(f)|，而回音型的 h 的頻率響應是一把**梳子**——
 * 120 ms 的延遲配 200 Hz 與 4000 Hz 時，兩個探測點恰好都落在梳齒的頂上，
 * 於是兩欄都印 `1.000`，讀起來像「這個系統什麼都沒做」。
 * 那兩個數字都是對的，但它們**回答錯了問題**：學生想知道的是
 * 「低音／高音大致上過得去嗎」，而那是一段頻帶的事，不是一個點的事。
 *
 * 取平均而不是取最大或最小：平均對梳狀響應給出「有一半過得去」這個
 * 正確印象，而最大值會永遠是 1、最小值會永遠是 0。
 */
export function bandGain(h, { from, to, sampleRate, points = 33 }) {
  let sum = 0;
  for (let i = 0; i < points; i += 1) {
    const f = from + ((to - from) * i) / (points - 1 || 1);
    sum += responseAt(h, f, sampleRate).magnitude;
  }
  return sum / points;
}

/** 直流增益 Σh[n]：常數輸入會被放大幾倍。相鄰相減的那一個恰好是 0。 */
export function directCurrentGain(h) {
  let sum = 0;
  for (let i = 0; i < h.length; i += 1) sum += h[i];
  return sum;
}

// ------------------------------------------------- 三個系統：一個 LTI，兩個不是
//
// **這一組存在的理由是 W1，而 W1 是 W2 的前提**：摺積不是一個憑空的公式，
// 它是「線性 + 非時變」這兩個假設的**唯一**後果。所以這一頁必須讓學生
// 看到那兩個假設**不成立**時會發生什麼——否則「為什麼是摺積」這個問題
// 根本沒有被問出來。
//
// 三個系統刻意選成一張 2×2 的表：
//
//   | 系統                    | 疊加性 | 非時變 |
//   |------------------------|-------|-------|
//   | 與 h 摺積               |   ✓   |   ✓   |
//   | 削波 clamp(x, ±c)       |   ✗   |   ✓   |
//   | 隨時間增強的增益         |   ✓   |   ✗   |
//
// 兩個「✗」各自只壞掉一格，這比「一個什麼都不對的系統」有用得多：
// 它讓兩個性質變成**可以分開檢驗的兩件事**，而不是一團叫做「乖」的東西。

/** 系統的顯示名（英文，D5）。鍵是程式用的名字。 */
export const SYSTEMS = {
  convolution: 'Convolution with the impulse response h',
  clip: 'Clipping: anything past a limit is cut off',
  fade: 'A gain that grows with time',
};

/** 削波的門檻。要比測試訊號的**和**低、比單獨一個高，否則測不出東西來。 */
export const CLIP_LEVEL = 0.5;

/**
 * 把一個系統套到輸入上。
 *
 * ⚠️ **三個系統的輸出長度必須一致**，否則殘差根本比不了。摺積會長出
 * M−1 個尾巴，所以另外兩個也把輸入補到同樣長度再處理——**補的是 0，
 * 而 0 對這三個系統都對映到 0**（削波：clamp(0)=0；漸強增益：任何倍數乘 0
 * 還是 0），所以這個補零不會偷偷改變任何一個系統的行為。
 */
export function applySystem(x, { kind, h = null, clip = CLIP_LEVEL }) {
  if (kind === 'convolution') {
    if (!h) throw new Error('the convolution system needs an impulse response');
    return convolve(x, h);
  }
  const tail = h ? h.length - 1 : 0;
  const out = new Float64Array(x.length + tail);
  for (let i = 0; i < x.length; i += 1) {
    const v = x[i];
    if (kind === 'clip') {
      out[i] = v > clip ? clip : (v < -clip ? -clip : v);
    } else if (kind === 'fade') {
      // 線性（乘一個數）但**與 n 有關**——這正是「時變」的最小例子。
      out[i] = v * (i / (out.length - 1 || 1));
    } else {
      throw new Error(`unknown system: ${kind}`);
    }
  }
  return out;
}

/** 往右平移 d 格，超出兩端的東西丟掉（長度不變）。 */
export function shiftSequence(x, d) {
  const out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i += 1) {
    const j = i - d;
    if (j >= 0 && j < x.length) out[i] = x[j];
  }
  return out;
}

function addSequences(a, b) {
  const n = Math.max(a.length, b.length);
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = (a[i] || 0) + (b[i] || 0);
  return out;
}

function maxAbsoluteDifference(a, b) {
  const n = Math.max(a.length, b.length);
  let worst = 0;
  for (let i = 0; i < n; i += 1) {
    const gap = Math.abs((a[i] || 0) - (b[i] || 0));
    if (gap > worst) worst = gap;
  }
  return worst;
}

/**
 * 疊加性的殘差：max |T(x₁+x₂) − (T(x₁) + T(x₂))|。
 *
 * LTI 的那一個回傳的是**浮點捨入的量級（1e−16 上下），不是 0**——
 * `0.45 + 0.4` 在 float64 裡是 `0.8500000000000001`，而那 1 ulp 會一路
 * 帶到輸出。這件事必須說清楚，因為它有兩個後果：
 *
 *   * **測試的界要拉到 1e−12 而不是隨手一個 1e−6。** 寬鬆的界會讓一個
 *     真的壞掉的實作也通過，而這一組殘差的訊號強度是 0.1 以上——
 *     兩者之間有十個數量級的空間，沒有理由不用滿。
 *   * **畫面上不得寫「exactly zero」**。這一頁整頁在教「殘差是一個量，
 *     不是一個評語」，而寫一個做不到的「恰好」會是這一頁唯一的假話。
 */
export function superpositionCurves(system, x1, x2) {
  const together = applySystem(addSequences(x1, x2), system);
  const apart = addSequences(applySystem(x1, system), applySystem(x2, system));
  return { together, apart, residual: maxAbsoluteDifference(together, apart) };
}

export function superpositionResidual(system, x1, x2) {
  return superpositionCurves(system, x1, x2).residual;
}

/**
 * 非時變的殘差：max |T(x 平移 d) − (T(x) 平移 d)|。
 *
 * ⚠️ **x 的尾巴必須留夠 d 格的零**，否則「先做系統再平移」會把輸出的尾巴
 * 推出陣列外，而那個被截掉的東西會被算成殘差——一個與時變完全無關的
 * 假陽性。測試訊號（`signal.js` 的 `LTI_PROBE`）因此刻意補了尾巴，
 * 而不是靠這裡多一段補償邏輯。
 */
export function timeInvarianceCurves(system, x, d) {
  const shiftedFirst = applySystem(shiftSequence(x, d), system);
  const shiftedAfter = shiftSequence(applySystem(x, system), d);
  return {
    shiftedFirst,
    shiftedAfter,
    residual: maxAbsoluteDifference(shiftedFirst, shiftedAfter),
  };
}

export function timeInvarianceResidual(system, x, d) {
  return timeInvarianceCurves(system, x, d).residual;
}

// ======== 連續 Fourier 變換：數值積分與四個閉合式（2S11；課程 W4）
//
// **與 signal.js 的分工**：脈衝本身在那邊，變換在這邊（見該檔那一段的開頭）。
//
// ⚠️ **這一段有兩條算 X(f) 的路徑，而那是刻意的**，與 `convolve` / `fftConvolve`
// 是同一個模式（§8.4 第 1 類）：
//
//   * `fourierIntegral()`——**數值積分**，執行期真正在畫的那一條。
//     它就是課綱對 W4 指定的那件事（「用數值積分模擬連續傅立葉變換」），
//     而且它可以在**任意**頻率上求值。
//   * `pulseSpectrumAt()`——**閉合式**，四個形狀各一行。
//
// 兩條路徑在畫面上疊在一起（實線是積分、虛線是公式），差距印成一個數字。
// 那個數字不是除錯訊息，它**就是這一頁的一項內容**：數值積分是一個近似，
// 而近似有多好是量得出來的。
//
// 慣例：X(f) = ∫ x(t) e^{−2πi f t} dt，**指數裡沒有 ω，只有 f**——
// 與 §8.3 那一組 DFT 慣例同一個方向的負號，也與課本上的 f 版本一致。
// 用 f 而不是 ω 讓「高斯自對偶」寫得出來（ω 版本會多一個 √(2π)）。

/** sinc(u) = sin(πu)/(πu)，sinc(0) = 1。四個閉合式全部靠它。 */
export function sinc(u) {
  if (u === 0) return 1;
  const x = Math.PI * u;
  return Math.sin(x) / x;
}

/**
 * **數值積分**：X(f) = ∫ x(t) e^{−2πi f t} dt，中點法則。
 *
 * ⚠️ **`sinc(f·dt)` 那一項不是修正係數，它讓這個和變成一個精確的積分。**
 * 中點和 `dt·Σ x(t_m) e^{−2πi f t_m}` 是把 x 當成在每一小段上是常數；
 * 而那個「階梯函數」的變換**算得出來**——每一小段貢獻
 * ∫ e^{−2πift}dt = dt·sinc(f·dt)·e^{−2πi f t_m}。
 * 少了它，誤差是 (πf·dt)²/6，**與頻率有關**：畫面右緣的旁瓣會安靜地
 * 低 1% 左右，而那正好是這一頁要學生讀的地方。乘上去之後，
 * 剩下的誤差只來自「用中點的值代表那一小段的 x」，與 f 無關。
 *
 * @param {ArrayLike<number>} values 中點上的取樣值
 * @param {number} dt 格距
 * @param {number} tStart **第一個格點的時刻**（不是區間左端）
 * @param {ArrayLike<number>} frequencies 要求值的頻率（可以是負的）
 */
export function fourierIntegral(values, dt, tStart, frequencies) {
  const n = values.length;
  const count = frequencies.length;
  const re = new Float64Array(count);
  const im = new Float64Array(count);
  const magnitude = new Float64Array(count);
  const phase = new Float64Array(count);
  for (let k = 0; k < count; k += 1) {
    const f = frequencies[k];
    const step = -2 * Math.PI * f * dt;
    let sumRe = 0;
    let sumIm = 0;
    for (let i = 0; i < n; i += 1) {
      const v = values[i];
      if (v === 0) continue;          // 支撐之外一整片 0，跳過（矩形省一半）
      const angle = -2 * Math.PI * f * tStart + step * i;
      sumRe += v * Math.cos(angle);
      sumIm += v * Math.sin(angle);
    }
    const weight = dt * sinc(f * dt);
    re[k] = sumRe * weight;
    im[k] = sumIm * weight;
    magnitude[k] = Math.hypot(re[k], im[k]);
    phase[k] = Math.atan2(im[k], re[k]);
  }
  return { re, im, magnitude, phase };
}

/** 單一頻率的版本。讀數與測試用它，不必為一個點造陣列。 */
export function fourierIntegralAt(values, dt, tStart, f) {
  const one = fourierIntegral(values, dt, tStart, [f]);
  return { re: one.re[0], im: one.im[0], magnitude: one.magnitude[0], phase: one.phase[0] };
}

/**
 * 四個形狀的**正規化**頻譜：g(u) = X(f)/X(0)，u = f·T（無因次）。
 *
 * 寫成無因次的形式有一個實際的好處：**T 只出現在 u 裡面**，
 * 所以「把 T 減半就是把整條曲線橫向拉成兩倍」這件事在程式裡也是明白的，
 * 而那正是這一頁的主張。半功率頻寬與零點位置因此都是常數 ÷ T。
 *
 * 四條式子（`scripts/dsp_reference.py` 用 SymPy 對定義式各積一次分驗過）：
 *
 *   矩形       g = sinc(u)                     第一個零點 u = 1
 *   三角       g = sinc²(u/2)                  第一個零點 u = 2
 *   升餘弦     g = sinc(u)/(1 − u²)            第一個零點 u = 2（u = ±1 可去）
 *   高斯       g = exp(−πu²)                   沒有零點
 */
export function normalisedPulseSpectrum(shape, u) {
  switch (shape) {
    case 'rectangle':
      return sinc(u);
    case 'triangle':
      return sinc(u / 2) ** 2;
    case 'cosine': {
      // ⚠️ u = ±1 是**可去奇異點**（分子分母同時歸零），而它的極限是 **1/2**。
      //
      // 兩件事都要處理，而且第二件比第一件危險得多：
      //   * 直接算會得到 0/0。實際上 `Math.sin(Math.PI)` 是 1.2e−16 而不是 0，
      //     所以結果是一個很大的數字或 Infinity，不一定是 NaN——
      //     也就是說它**不一定會在畫面上留下缺口**。
      //   * 極限值本身。第一版寫成 π/4，而那是一個看起來很合理的錯誤：
      //     它只在 u 恰好等於 ±1 的那一格上生效，其餘每一格都是對的。
      //     f_max·T 恰好等於 1 時（例如 0.5 ms 的脈衝配 2 kHz 的軸）
      //     軸的兩端就落在那裡，於是曲線的兩端各翹起一格，
      //     高度是峰值的 28%。抓到它的是「數值積分與閉合式的差距」
      //     那個讀數——**那一列不是除錯訊息，它就是這樣用的**。
      //
      // 極限用羅必達算：分子 sinc(u) 在 u = 1 的導數是 −1，
      // 分母 1 − u² 的導數是 −2u = −2，所以極限是 (−1)/(−2) = 1/2。
      // 另一條算法給同一個答案：X = (T/2)sinc(u) + (T/4)[sinc(u−1) + sinc(u+1)]，
      // 在 u = 1 是 (T/4)·1，而 X(0) = T/2。
      const d = 1 - u * u;
      if (Math.abs(d) < 1e-9) return 0.5;
      return sinc(u) / d;
    }
    case 'gaussian':
      return Math.exp(-Math.PI * u * u);
    default:
      throw new Error(`unknown pulse shape: ${shape}`);
  }
}

/**
 * X(0)，也就是**曲線下的面積** ∫x dt。矩形與高斯是 T，三角與升餘弦是 T/2。
 *
 * 這個值在畫面上有一個直接的意義，值得單獨拿出來：頻譜的高度就是面積。
 * 把脈衝變窄一半，尖峰就矮一半——而寬度變成兩倍。面積守恆是
 * 「時頻取捨」在這一頁最容易看見的形式。
 */
export function pulseArea(shape, width) {
  if (shape === 'rectangle' || shape === 'gaussian') return width;
  if (shape === 'triangle' || shape === 'cosine') return width / 2;
  throw new Error(`unknown pulse shape: ${shape}`);
}

/** 閉合式的 X(f)（實數；未平移、未調變的脈衝是實偶函數）。 */
export function pulseSpectrumAt(shape, width, f) {
  return pulseArea(shape, width) * normalisedPulseSpectrum(shape, f * width);
}

/**
 * 完整的閉合式：平移 + 調變都套上去。
 *
 * 兩條性質各對應一行，而這一頁的第三、第四個教學主張就是它們：
 *
 *   * **位移**  x(t − t₀) ↔ X(f)·e^{−2πi f t₀}
 *     ——只乘上一個模為 1 的東西，所以 |X| 一個字都不變。
 *   * **調變**  x(t)·cos(2πf_c t) ↔ ½[X(f − f_c) + X(f + f_c)]
 *     ——整條頻譜搬到 ±f_c，各一半高。
 *
 * ⚠️ 順序是「先調變、後位移」，而且 `signal.js` 的 `signalAt()` 也是
 * 這樣造訊號的（載波的相位跟著脈衝走）。反過來寫**不會壞掉、只會不一樣**：
 * 那時位移就不再是一個純延遲，|X| 會隨 t₀ 晃動。見 `signalAt()` 的說明。
 */
export function analyticSpectrumAt(shape, { width, shift = 0, carrierHz = 0 }, f) {
  const base = carrierHz > 0
    ? 0.5 * (pulseSpectrumAt(shape, width, f - carrierHz)
             + pulseSpectrumAt(shape, width, f + carrierHz))
    : pulseSpectrumAt(shape, width, f);
  const angle = -2 * Math.PI * f * shift;
  const re = base * Math.cos(angle);
  const im = base * Math.sin(angle);
  return { re, im, magnitude: Math.abs(base), phase: Math.atan2(im, re) };
}

/** 整條軸的閉合式，形狀與 `fourierIntegral()` 的回傳值相同。 */
export function analyticSpectrum(shape, options, frequencies) {
  const count = frequencies.length;
  const re = new Float64Array(count);
  const im = new Float64Array(count);
  const magnitude = new Float64Array(count);
  const phase = new Float64Array(count);
  for (let k = 0; k < count; k += 1) {
    const point = analyticSpectrumAt(shape, options, frequencies[k]);
    re[k] = point.re;
    im[k] = point.im;
    magnitude[k] = point.magnitude;
    phase[k] = point.phase;
  }
  return { re, im, magnitude, phase };
}

/** 頻譜第一個零點的位置（Hz）。高斯沒有零點，回傳 null。 */
export function firstNullFrequency(shape, width) {
  const factors = { rectangle: 1, triangle: 2, cosine: 2, gaussian: null };
  if (!(shape in factors)) throw new Error(`unknown pulse shape: ${shape}`);
  const factor = factors[shape];
  return factor === null ? null : factor / width;
}

/**
 * 半功率（−3 dB）頻寬：|X| 掉到峰值的 1/√2 的那兩點之間的距離。
 *
 * ⛔ **用閉合式二分找，不從畫面上那條曲線量。** 從曲線量的話，數字會隨著
 * 頻率軸的縮放而變（格點變粗，內插的落點就變），而**那是一個沒有人
 * 看得出來的錯誤**：讀數看起來一直都很合理。這與 `rmsWidths()` 不從
 * 畫面量是同一個理由。
 *
 * g(u) 在 [0, 第一個零點] 上單調遞減（四個形狀都是），所以二分一定收斂。
 * 回傳的是**整個**頻寬（兩側各 u_half 除以 T），因此 B·T 是一個只與形狀有關的常數
 * ——那就是「拖寬度時 B·T 不動」那一欄。
 */
export function halfPowerBandwidth(shape, width) {
  const target = Math.SQRT1_2;
  const hi = { rectangle: 1, triangle: 2, cosine: 2, gaussian: 3 }[shape];
  if (hi === undefined) throw new Error(`unknown pulse shape: ${shape}`);
  let lo = 0;
  let high = hi;
  for (let i = 0; i < 80; i += 1) {
    const mid = (lo + high) / 2;
    if (normalisedPulseSpectrum(shape, mid) > target) lo = mid;
    else high = mid;
  }
  return (2 * ((lo + high) / 2)) / width;
}

/**
 * 兩條曲線最大的逐點差距。
 *
 * 這一頁用它兩次，而兩次都是把一句話變成一個數字：
 * 「平移沒有動到幅度譜」與「數值積分與閉合式相符到多少」。
 */
export function maxAbsoluteGap(a, b) {
  return maxAbsoluteDifference(a, b);
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

// ================================================ 極零點與數位濾波器（2S9，W7）
//
// 這一段把「z 平面上的一個位置」翻譯成三樣學生在課本上看得到的東西：
// 差分方程的係數、頻率響應、以及衝激響應。三者是同一件事的三種說法，
// 而這一頁的全部內容就是讓那個「同一件事」變成看得見、聽得見的。
//
// ⚠️ **實係數的濾波器，極零點必須共軛成對**，所以這一層的基本單位不是
// 「一個點」而是**一個共軛對** `{r, theta}`。這不是為了少寫程式：
// 拿掉這個約束，係數就會變成複數，而複數係數的差分方程**在真實硬體上
// 不存在**——課本上那串 a_k、b_k 全部是實數，是有理由的。
//
// ⚠️ **θ = 0 或 θ = π 時，「一個共軛對」退化成一個二重實根**
// （1 − 2r z⁻¹ + r² z⁻² = (1 − r z⁻¹)²），這是正確的數學而不是邊界瑕疵。
// 頁面上明講了這件事，因為它是「共軛對」這個概念唯一會讓人愣住的地方。

/** 極點半徑的上限。**刻意大於 1**——把極點推出單位圓正是這一頁要教的事。 */
export const POLE_ZERO_MAX_RADIUS = 1.2;

/**
 * 一個共軛對展成一個二階多項式的係數：`[1, −2r cos θ, r²]`。
 *
 * 推導只有一行：(1 − r e^{jθ} z⁻¹)(1 − r e^{−jθ} z⁻¹)
 *              = 1 − r(e^{jθ} + e^{−jθ}) z⁻¹ + r² z⁻²
 *              = 1 − 2r cos θ · z⁻¹ + r² z⁻²
 *
 * ⚠️ **中間那一項的負號是這一段最容易寫錯、而且錯了圖還是好看的地方**：
 * 寫成 +2r cos θ 得到的是把共軛對鏡射到左半平面的濾波器，
 * 曲線形狀完全正常，只是共振跑到了另一個頻率。
 * `tests/test_dsp_js.py` 拿 SymPy 展開 ∏(1 − p_k z⁻¹) 逐項對照它。
 */
export function pairSection({ r, theta }) {
  return Float64Array.from([1, -2 * r * Math.cos(theta), r * r]);
}

/**
 * 把一串共軛對乘起來，得到一個多項式的係數（第 0 項恆為 1）。
 *
 * 多項式相乘就是係數摺積——所以這裡直接用上面那支 `convolve()`，
 * 不另外寫一份。**這不是省事，是 W2 與 W7 之間的一條線**：
 * 上一個展示教的「摺積」，在這一頁是「把根乘起來」這個動作本身。
 */
export function polynomialFromPairs(pairs) {
  let poly = Float64Array.from([1]);
  for (const pair of pairs) poly = convolve(poly, pairSection(pair));
  return poly;
}

/**
 * 極零點 → 差分方程的係數。
 *
 *     H(z) = g · B(z) / A(z),  B 由零點來、A 由極點來，兩者都以 1 開頭
 *     y[n] = g·(b₀x[n] + b₁x[n−1] + …) − a₁y[n−1] − a₂y[n−2] − …
 *
 * ⚠️ `a[0]` 恆為 1 是一個**約定**而不是巧合：把 A(z) 寫成首項為 1，
 * 差分方程才解得出 y[n]（否則兩邊都有 y[n]）。所有吃 `{b, a}` 的函式
 * 都假設這件事，所以這裡是唯一產生它的地方。
 */
export function filterCoefficients({ zeros = [], poles = [], gain = 1 } = {}) {
  const b = polynomialFromPairs(zeros);
  const a = polynomialFromPairs(poles);
  const scaled = new Float64Array(b.length);
  for (let i = 0; i < b.length; i += 1) scaled[i] = gain * b[i];
  return { b: scaled, a };
}

/** 複數乘法與除法，只在這一段裡用，所以不 export。 */
function cMul(a, b) {
  return { re: a.re * b.re - a.im * b.im, im: a.re * b.im + a.im * b.re };
}

function cDiv(a, b) {
  const d = b.re * b.re + b.im * b.im;
  if (d === 0) return { re: Infinity, im: 0 };
  return { re: (a.re * b.re + a.im * b.im) / d, im: (a.im * b.re - a.re * b.im) / d };
}

/** 多項式在 z = e^{jω} 上的值：Σ c_k e^{−jkω}。 */
function polynomialAt(coefficients, omega) {
  let re = 0;
  let im = 0;
  for (let k = 0; k < coefficients.length; k += 1) {
    re += coefficients[k] * Math.cos(k * omega);
    im -= coefficients[k] * Math.sin(k * omega);
  }
  return { re, im };
}

/**
 * H(e^{jω})，**由展開後的係數求值**。這是執行期畫圖用的那一條路。
 */
export function responseFromCoefficients(b, a, omega) {
  const num = polynomialAt(b, omega);
  const den = polynomialAt(a, omega);
  const h = cDiv(num, den);
  return {
    re: h.re, im: h.im,
    magnitude: Math.hypot(h.re, h.im),
    phase: Math.atan2(h.im, h.re),
  };
}

/**
 * H(e^{jω})，**由極零點的因式連乘求值**。這是與上一支獨立的第二條路。
 *
 * §8.4 第 1 類驗證（「兩條獨立路徑必須相等」）在這一頁的形式就是這一對：
 * 一條先把根展開成多項式再求值，一條完全不展開。展開那一步是這一段
 * 最容易出錯的地方（見 `pairSection()` 的警告），而它只出現在其中一條路上。
 *
 * ⚠️ 幾何上這支還有第二個用途，而那正是這一頁的核心直覺：
 * |H| = g · ∏|e^{jω} − z_k| / ∏|e^{jω} − p_k|，
 * 也就是**單位圓上那一點到每個零點的距離連乘，除以到每個極點的距離連乘**。
 * 零點靠近圓 → 分子有一項趨近 0 → 那個頻率被壓掉；極點靠近圓 → 分母趨近 0
 * → 那個頻率被抬起來。學生拖著點看到的就是這一行。
 */
export function responseFromPairs({ zeros = [], poles = [], gain = 1 } = {}, omega) {
  // e^{−jω}，因式寫成 (1 − root·e^{−jω}) 與多項式那條路同一個慣例。
  const w = { re: Math.cos(-omega), im: Math.sin(-omega) };
  const accumulate = (pairs) => {
    let acc = { re: 1, im: 0 };
    for (const { r, theta } of pairs) {
      for (const sign of [1, -1]) {
        const root = { re: r * Math.cos(sign * theta), im: r * Math.sin(sign * theta) };
        const factor = { re: 1 - (root.re * w.re - root.im * w.im),
          im: -(root.re * w.im + root.im * w.re) };
        acc = cMul(acc, factor);
      }
    }
    return acc;
  };
  const num = accumulate(zeros);
  const den = accumulate(poles);
  const h = cDiv({ re: gain * num.re, im: gain * num.im }, den);
  return {
    re: h.re, im: h.im,
    magnitude: Math.hypot(h.re, h.im),
    phase: Math.atan2(h.im, h.re),
  };
}

/**
 * 一整條頻率響應曲線。ω 由呼叫端給（通常是 0…π 的等分）。
 *
 * 相位回傳的是繞回 (−π, π] 的值——`draw.js` 的 `splitOnJumps()` 會處理
 * 那些跳，不在這裡做展開（unwrap）。理由是展開需要一個門檻，
 * 而門檻是繪圖的事，不是數學的事。
 */
export function responseCurve(b, a, omegas) {
  const n = omegas.length;
  const magnitude = new Float64Array(n);
  const phase = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const h = responseFromCoefficients(b, a, omegas[i]);
    magnitude[i] = h.magnitude;
    phase[i] = h.phase;
  }
  return { magnitude, phase };
}

/**
 * 掃過 [0, π] 找 |H| 的最大值，回傳 `{magnitude, omega}`。
 *
 * ⚠️ **這支是音訊安全的第一道防線，所以格點數不是隨便給的。**
 * r = 0.999 的極點，−3 dB 頻寬約 2(1−r) = 0.002 rad——1024 格的間距是
 * 0.003 rad，會**整個跳過那個峰**，於是量到的峰值偏低、正規化不足、
 * 而輸出比預期大聲。預設 4096 格（間距 0.00077 rad）配上滑桿的
 * r ≤ 1.2 與下面 `safetyGain()` 的「只衰減不放大」，兩層一起才夠。
 */
export function peakGain(b, a, points = 4096) {
  let best = 0;
  let bestOmega = 0;
  for (let i = 0; i <= points; i += 1) {
    const omega = (Math.PI * i) / points;
    const m = responseFromCoefficients(b, a, omega).magnitude;
    if (m > best) { best = m; bestOmega = omega; }
  }
  return { magnitude: best, omega: bestOmega };
}

/**
 * 音訊要乘上的安全增益：把最大的那個頻率壓回 1。
 *
 * ⛔ **只衰減，不放大**（`Math.min(1, …)`）。一個純粹的凹口濾波器峰值本來
 * 就是 1，放大它沒有意義；而「自動把音量拉滿」會讓一件事在耳朵裡消失——
 * 把極點推向單位圓時，真正發生的是**共振以外的一切都變小聲**，
 * 不是共振變大聲。兩者是同一個濾波器，差別只在乘上哪一個常數。
 *
 * ⚠️ 這個取捨有代價，而代價必須寫在畫面上：學生聽到的動態範圍變化，
 * 有一部分是這一行造成的。所以這一頁把**未經正規化的峰值增益（dB）
 * 印出來**——耳朵聽不到的那個數字，眼睛看得到。
 * 這與 2S5 的 `disableNormalization`、2S10 不用 `ConvolverNode` 是同一場仗，
 * 但**結論相反**，因為這一次正規化是安全需求而不是便利：
 * r = 0.999 的極點峰值增益是 1000 倍，那不是一個音量問題，是喇叭問題。
 */
export function safetyGain(b, a, points = 4096) {
  const peak = peakGain(b, a, points).magnitude;
  if (!Number.isFinite(peak) || peak <= 0) return 0;
  return Math.min(1, 1 / peak);
}

/** 極點半徑的最大值。共軛對的兩個成員半徑相同，所以看 r 就夠。 */
export function maxPoleRadius(poles) {
  let max = 0;
  for (const { r } of poles) if (r > max) max = r;
  return max;
}

/**
 * 因果系統的穩定性：**所有極點都要嚴格落在單位圓內**。
 *
 * ⚠️ `r === 1` 算**不穩定**，不是「臨界穩定所以放行」。臨界的極點給出一個
 * 永不衰減的正弦（純振盪），而那在一條會被反覆疊加的音訊路徑上與發散
 * 沒有實際差別——更重要的是，浮點的 r 幾乎不可能剛好是 1，
 * 一個「等於就放行」的判斷式在真實使用中只會在 r 略大於 1 時才生效。
 */
export function isStable(poles) {
  return maxPoleRadius(poles) < 1;
}

/**
 * 二階分母的穩定三角形（Jury 判準）：a = [1, a₁, a₂] 穩定 ⟺
 *
 *     |a₂| < 1,   1 + a₁ + a₂ > 0,   1 − a₁ + a₂ > 0
 *
 * 三條**全部是線性不等式**，所以可行域是一個三角形，而三角形是**凸的**。
 * 這件事不是趣聞，它是這一頁音訊安全的第三層：worklet 在換係數時
 * 對新舊兩組做線性內插，而凸性保證**中途每一個瞬間仍然是穩定的**
 * （見 `blendCoefficients()`）。
 *
 * ⚠️ **這個保證只對二階成立。** 三階以上的穩定域不是凸的，兩組穩定的
 * 係數之間的直線可以跑出去。這一頁的分母恰好只有一個共軛對（二階），
 * 而那**是一個設計約束，不是巧合**——想加第二個極點對之前先讀這一段。
 */
export function isStableSecondOrder(a) {
  const a1 = a[1] || 0;
  const a2 = a[2] || 0;
  return Math.abs(a2) < 1 && 1 + a1 + a2 > 0 && 1 - a1 + a2 > 0;
}

/**
 * 差分方程，照定義跑一遍（direct form I）：
 *
 *     y[n] = Σ_k b_k x[n−k] − Σ_{k≥1} a_k y[n−k]
 *
 * **這一支就是課本上那一行，也就是老師 Python 作業要學生自己寫的那一行。**
 * 它是這一頁與作業之間的接點，所以它照定義寫，不做任何加速。
 *
 * ⚠️ 它與 `worklets/polezero-processor.js` 裡那一份是**刻意的重複**，
 * 理由與 2S3 的 ZOH 相同（worklet 不能 import ES module）。
 * `tests/test_dsp_js.py` 有一項把 worklet 讀進 node 逐格比對這一支，
 * **改了其中一份就會紅燈**。
 */
export function filterSequence(b, a, x) {
  const y = new Float64Array(x.length);
  for (let n = 0; n < x.length; n += 1) {
    let acc = 0;
    for (let k = 0; k < b.length; k += 1) {
      if (n - k >= 0) acc += b[k] * x[n - k];
    }
    for (let k = 1; k < a.length; k += 1) {
      if (n - k >= 0) acc -= a[k] * y[n - k];
    }
    y[n] = acc / (a[0] || 1);
  }
  return y;
}

/**
 * 衝激響應：把 δ[n] 餵進差分方程。
 *
 * **FIR 與 IIR 的差別在這張圖上是看得完的**：沒有極點時 h 在 b 的長度之後
 * 就是一排精確的 0；有極點時它永遠不到 0，只是越來越小（或越來越大）。
 * 「有限」與「無限」這兩個字是這裡的字面意思。
 */
export function filterImpulseResponse(b, a, count) {
  const x = new Float64Array(count);
  x[0] = 1;
  return filterSequence(b, a, x);
}

/**
 * 兩組係數之間的線性內插。worklet 換係數時每一格（128 樣本）走一次。
 *
 * 為什麼要內插而不是直接換：直接換會在輸出上留一個不連續，聽起來是
 * 一聲「喀」，而拖一次滑桿會產生好幾十個。為什麼內插是安全的：
 * 見 `isStableSecondOrder()` 的凸性說明。
 */
export function blendCoefficients(from, to, t) {
  const s = t < 0 ? 0 : (t > 1 ? 1 : t);
  const blend = (u, v) => {
    const n = Math.max(u.length, v.length);
    const out = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      out[i] = (1 - s) * (u[i] || 0) + s * (v[i] || 0);
    }
    return out;
  };
  return {
    b: blend(from.b, to.b),
    a: blend(from.a, to.a),
  };
}

/**
 * 峰值兩側掉到 −3 dB 的那兩個 ω 之間的距離，**量出來的**。
 *
 * ⚠️ 刻意不用課本那個 Δω ≈ 2(1−r) 的近似式。那個近似在 r → 1 時才準，
 * 而這一頁的滑桿從 r = 0 開始——在 r = 0.5 上它差了將近一倍。
 * 頁面把量到的值與近似式**並排印出來**，這樣「近似」兩個字是一個可以
 * 讀出來的量，而不是一句免責聲明（與 2S11 的數值積分那一列同一個作法）。
 *
 * 找不到（峰值在端點、或整條曲線都在 −3 dB 以上）時回傳 null。
 */
export function halfPowerWidth(b, a, omegaPeak, points = 4096) {
  const peak = responseFromCoefficients(b, a, omegaPeak).magnitude;
  if (!(peak > 0) || !Number.isFinite(peak)) return null;
  const target = peak * Math.SQRT1_2;
  const step = Math.PI / points;
  const edge = (direction) => {
    let previous = omegaPeak;
    for (let i = 1; i <= points; i += 1) {
      const omega = omegaPeak + direction * i * step;
      if (omega < 0 || omega > Math.PI) return null;
      const m = responseFromCoefficients(b, a, omega).magnitude;
      if (m <= target) {
        // 找到區間之後二分，讓答案不受格點粗細影響。
        let lo = previous;
        let hi = omega;
        for (let k = 0; k < 60; k += 1) {
          const mid = (lo + hi) / 2;
          if (responseFromCoefficients(b, a, mid).magnitude > target) lo = mid;
          else hi = mid;
        }
        return (lo + hi) / 2;
      }
      previous = omega;
    }
    return null;
  };
  const left = edge(-1);
  const right = edge(1);
  if (left === null || right === null) return null;
  return right - left;
}

/**
 * 共振的衰減時間常數，單位是**樣本**：極點 r^n 掉到 1/e 要走幾格。
 *
 *     r^n = 1/e  ⟹  n = −1 / ln r
 *
 * r = 0 回傳 0（沒有記憶），r ≥ 1 回傳 Infinity（不衰減，或發散）。
 * 這個數字乘上取樣週期就是耳朵聽到的那個「鈴聲」有多長。
 */
export function decaySamples(r) {
  if (!(r > 0)) return 0;
  if (r >= 1) return Infinity;
  return -1 / Math.log(r);
}
