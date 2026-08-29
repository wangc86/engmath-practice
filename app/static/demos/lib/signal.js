// 訊號產生層（PLAN.md §8.2.3 第一段）。
//
// 這一層是**純函式**：吃數字與陣列、吐陣列，完全不知道 DOM 與 AudioContext
// 存在。它是四段分離裡唯一可以在 node 裡直接 import 並斷言數值的一層
// （`tests/test_dsp_js.py` 就是這樣測它的），所以任何演算法都應該落在這裡，
// 而不是落在 <demo>.js 裡——落在那裡就測不到了。
//
// ⛔ 這個檔案不得 import 任何會碰 `window`、`document`、`AudioContext` 的東西。
//
// 註解用繁體中文（開發文件語言），但**所有字串常值一律英文**——這一層雖然
// 不直接輸出文字，規則仍然一致（D5），`tests/test_demos.py` 有一項掃過
// 整個 app/static/demos/ 確認字串裡沒有中日韓字元。

/** 把 v 夾在 [lo, hi] 之間。 */
export function clamp(v, lo, hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

/**
 * 連續正弦在給定時間點上的值：sin(2π f t + φ)。
 *
 * 「連續」是相對於取樣而言——這裡仍然是在離散的 `times` 上求值，
 * 但那組時間點的密度由呼叫端（繪圖）決定，與取樣率無關。
 */
export function sineAt(f, t, phase = 0) {
  return Math.sin(2 * Math.PI * f * t + phase);
}

/**
 * 在 [t0, t0 + duration) 上以 `count` 個等距點畫出連續波形的取樣。
 * 回傳 {times, values} 兩個等長的 Float64Array。
 *
 * 這**不是**取樣定理意義下的取樣，是「把曲線畫出來」用的密集求值；
 * 兩者刻意用不同的函式名稱，因為混淆這兩件事正是這個展示要糾正的誤解之一。
 */
export function traceSine(f, t0, duration, count, phase = 0) {
  const times = new Float64Array(count);
  const values = new Float64Array(count);
  for (let i = 0; i < count; i += 1) {
    const t = t0 + (duration * i) / (count - 1 || 1);
    times[i] = t;
    values[i] = sineAt(f, t, phase);
  }
  return { times, values };
}

/**
 * 取樣定理意義下的取樣：以取樣率 fs 在 [t0, t0 + duration] 上取點。
 *
 * 第一個取樣點取在 t0 之後第一個落在取樣網格 n/fs 上的時刻，
 * 而不是 t0 本身——這樣拖動 t0（或改變 fs）時取樣點不會黏著畫面左緣移動，
 * 學生看到的是一組固定的取樣時刻，那才是取樣的樣子。
 */
export function sampleTimes(fs, t0, duration) {
  const first = Math.ceil(t0 * fs);
  const last = Math.floor((t0 + duration) * fs);
  const n = Math.max(0, last - first + 1);
  const times = new Float64Array(n);
  for (let i = 0; i < n; i += 1) times[i] = (first + i) / fs;
  return times;
}

/**
 * 零階保持（zero-order hold）降取樣。
 *
 * 這是自訂 worklet 存在的唯一理由（§8.5：能用原生節點就不要自己寫 worklet）——
 * Web Audio 沒有「刻意用比 ctx.sampleRate 低的取樣率取樣」這種節點。
 * 這裡是同一個演算法的純函式版本，給測試與繪圖用；worklet 裡那份
 * （`worklets/sampler-processor.js`）必須與這裡逐行對應。
 *
 * **累加的是 fs 本身，不是 fs/ctxRate。** 這不是風格問題：
 * `phase += fs / ctxRate` 每一格都吃一次浮點捨入，誤差會累積，
 * 幾秒之後實際的取樣率就與畫面上顯示的數字對不上了——而這個展示整頁都在教
 * 「畫面上那個數字是什麼意思」。改成累加整數 fs、每次滿 ctxRate 就扣掉
 * （Bresenham 那一套），在 fs 與 ctxRate 都是整數時**完全沒有誤差**。
 *
 * @param {ArrayLike<number>} input  以 ctxRate 取樣的輸入
 * @param {number} ctxRate           AudioContext 的實際取樣率
 * @param {number} fs                我們要模擬的取樣率
 * @param {{acc?: number, held?: number}} state  跨區塊延續用（worklet 需要）
 * @returns {{output: Float64Array, acc: number, held: number}}
 */
export function zeroOrderHold(input, ctxRate, fs, state = {}) {
  const output = new Float64Array(input.length);
  let acc = state.acc ?? ctxRate;     // 預設滿格：第一個 frame 就抓一個樣本
  let held = state.held ?? 0;
  for (let i = 0; i < input.length; i += 1) {
    acc += fs;
    if (acc >= ctxRate) {
      // while 而不是 if：fs 可能大於 ctxRate（過取樣），那時一格要扣好幾次。
      while (acc >= ctxRate) acc -= ctxRate;
      held = input[i];
    }
    output[i] = held;
  }
  return { output, acc, held };
}

/**
 * 畫面要顯示多長的時間窗（秒）。
 *
 * 規則：對齊**混疊後**那條慢波，因為它才是這個展示要學生看見的東西；
 * 沒有混疊時（f <= fs/2）混疊頻率就等於 f 本身，規則自動退化成「畫三個週期」。
 * 上下限是為了避免 f 接近 fs 的整數倍時（混疊頻率趨近 0）視窗爆長。
 */
export function viewWindowSeconds(f, fs, cycles = 3) {
  const fa = aliasFrequencyForWindow(f, fs);
  const base = fa > 1 ? fa : Math.max(f, 1);
  return clamp(cycles / base, 0.002, 0.06);
}

// ================================================ 使用者選的音訊檔（2S4，D28）
//
// ⛔ **這一段處理的資料絕對不離開瀏覽器。** 檔案由 `<input type="file">` 取得、
// 用 `file.arrayBuffer()` 讀進記憶體、交給 `decodeAudioData` 解碼，
// 全程在使用者自己的機器上。**沒有 fetch、沒有 FormData、沒有 XHR、
// 沒有 WebSocket、沒有 sendBeacon**——`tests/test_demos.py` 有一組測試掃過
// 整個 `app/static/demos/` 確認這件事，另有一項確認伺服器端根本沒有能收檔案
// 的路由。D28 的整個正當性就架在這一條上面，所以它由測試看守，不是由紀律看守。
//
// 下面這兩支是那條路徑上**唯一有邏輯的部分**，所以它們住在這裡（純函式層）
// 而不是住在 spectrum.js——住在那裡就測不到了。

/**
 * 多聲道混成單聲道，並截斷到最多 maxFrames 格。
 *
 * 三個決定，各有理由：
 *
 * * **混音而不是取第一軌。** 取左聲道在立體聲錄音上會漏掉只出現在右邊的
 *   東西（很多錄音的人聲偏一邊），而這一頁的重點是「看見你自己那段聲音裡
 *   有什麼」。平均會讓反相的成分互相抵消，但那是罕見情況，且比漏掉一半好。
 * * **截斷而不是拒絕。** 使用者選了一首五分鐘的歌，正確的回應不是
 *   「檔案太長」——他要看的東西在前幾秒就有了。截斷之後**要說出來**
 *   （見 describeAudioBuffer），這才是有意義的降級而不是靜默降級（規則 4）。
 * * **先解碼再截斷。** `decodeAudioData` 沒有「只解前 N 秒」這種選項，
 *   所以順序只能是這樣；擋在前面的是檔案大小的上限（在 spectrum.js）。
 *
 * @param {Array<ArrayLike<number>>} channels 每個聲道一個陣列，長度相同
 * @param {number} maxFrames
 * @returns {Float32Array}
 */
export function mixToMono(channels, maxFrames) {
  if (channels.length === 0) return new Float32Array(0);
  const frames = Math.min(channels[0].length, maxFrames);
  const out = new Float32Array(frames);
  for (const channel of channels) {
    for (let i = 0; i < frames; i += 1) out[i] += channel[i];
  }
  if (channels.length > 1) {
    for (let i = 0; i < frames; i += 1) out[i] /= channels.length;
  }
  return out;
}

/**
 * 一句描述解碼結果的英文，給畫面與螢幕閱讀器用。
 *
 * 寫成純函式是刻意的：這幾句話是**這個功能唯一會被學生讀到的輸出**，
 * 而「多聲道被混掉了」「檔案被截短了」「取樣率不是原本那個」這三件事
 * 若沒有說出來，就是三種靜默降級。放在這裡它們有測試盯著。
 *
 * @param {object} info
 * @param {number} info.sampleRate  解碼後的取樣率（＝ AudioContext 的取樣率）
 * @param {number} info.channels    原始聲道數
 * @param {number} info.seconds     原始長度（秒）
 * @param {number} info.keptSeconds 實際保留的長度（秒）
 */
export function describeAudioBuffer({ sampleRate, channels, seconds, keptSeconds }) {
  const parts = [`Decoded ${seconds.toFixed(1)} seconds of audio.`];
  if (channels > 1) {
    parts.push(
      `The ${channels === 2 ? 'two channels were' : `${channels} channels were`} `
      + 'mixed down to one, because the spectrum is computed from a single '
      + 'signal.',
    );
  }
  if (keptSeconds < seconds - 1e-6) {
    parts.push(
      `Only the first ${keptSeconds.toFixed(0)} seconds are kept, which is `
      + 'more than enough to look at, and keeps the page responsive.',
    );
  }
  parts.push(
    `The browser resampled it to ${Math.round(sampleRate)} Hz, the rate your `
    + 'audio device is running at, so that is the rate the spectrum is '
    + 'measured against.',
  );
  parts.push('This file stays on your computer. Nothing is uploaded.');
  return parts.join(' ');
}

// ============================== Fourier 級數：目標波形、合成、吉布斯（2S5）
//
// **這一段與 transform.js 的分工，寫在這裡以免日後有人把它們合併：**
//
//   * 這裡（signal.js）＝ **波形本身**：目標波形長什麼樣、部分和怎麼算出來、
//     不連續點在哪裡、過衝有多大、送進 `PeriodicWave` 的那兩張表怎麼填。
//   * transform.js ＝ **係數**：a_n／b_n 的閉合式、相位方案、帶限裁切、
//     三角形式 ↔ 指數形式的換算。
//
// 兩邊**互不 import**（維持 §8.2.3 的單向依賴：兩者都是純函式層的葉子）。
// 接點是一個普通物件——transform.js 產生 `series`，這裡消費它：
//
//     series = { kind, dc, harmonics: [{ n, cosine, sine, amplitude, phase }] }
//     x(t) ≈ dc + Σ_n amplitude_n · sin(2π n f₀ t + phase_n)
//
// **統一寫成「振幅 + 相位」而不是「a_n cos + b_n sin」是這個展示的關鍵設計。**
// 相位擾亂那一格要教的事情是「改相位、波形全變、音色幾乎不變」，
// 而它只有在振幅與相位是**兩個可以分開動的東西**時才表達得出來。
// a_n／b_n 仍然一起帶著（教材上是那個形式），但它們是從 (A, φ) 導出的，
// 不是第二份真相。

/**
 * 四個目標波形。
 *
 * 每一個都以**相位** θ = 2π f₀ t 定義，週期 2π，因此與 f₀ 無關——
 * f₀ 只在把時間換成 θ 的時候出現一次。這樣做的好處是不連續點的位置
 * （`jumpPhase`）是一個常數，不必隨頻率重算。
 *
 * `jump` 是**不連續處的落差**，吉布斯過衝的百分比就是以它為分母
 * （課本上那個「約 9%」的 9% 指的是落差的 9%，不是振幅的 9%——
 * 這是學生最常搞混的一件事，所以程式裡的分母必須是它）。
 * 連續的波形 `jump` 為 0，`measureOvershoot()` 會據此回報「沒有落差」，
 * 而不是回報一個沒有意義的百分比。
 */
export const WAVEFORMS = {
  square: {
    label: 'Square wave',
    decay: '1/n',
    oddHarmonicsOnly: true,
    continuous: false,
    jump: 2,
    jumpPhase: 0,          // 由 -1 跳到 +1 的那一點
    jumpSpacing: Math.PI,  // 下一個跳點在 θ = π（方波一個週期跳兩次）
    limitBefore: -1,
    limitAfter: 1,
    peak: 1,
    at(theta) {
      return wrapPhase(theta) < Math.PI ? 1 : -1;
    },
  },
  sawtooth: {
    label: 'Sawtooth wave',
    decay: '1/n',
    oddHarmonicsOnly: false,
    continuous: false,
    jump: 2,
    jumpPhase: Math.PI,        // 由 +1 掉回 -1 的那一點
    jumpSpacing: 2 * Math.PI,  // 一個週期只跳一次
    limitBefore: 1,
    limitAfter: -1,
    peak: 1,
    at(theta) {
      const u = wrapPhase(theta);
      return (u <= Math.PI ? u : u - 2 * Math.PI) / Math.PI;
    },
  },
  triangle: {
    label: 'Triangle wave',
    decay: '1/n^2',
    oddHarmonicsOnly: true,
    continuous: true,
    jump: 0,
    jumpPhase: 0,
    jumpSpacing: 2 * Math.PI,
    limitBefore: 0,
    limitAfter: 0,
    peak: 1,
    at(theta) {
      const u = wrapPhase(theta);
      if (u <= Math.PI / 2) return (2 * u) / Math.PI;
      if (u <= (3 * Math.PI) / 2) return 2 - (2 * u) / Math.PI;
      return (2 * u) / Math.PI - 4;
    },
  },
  halfWave: {
    label: 'Half-wave rectified sine',
    decay: '1/n^2',
    oddHarmonicsOnly: false,
    continuous: true,
    jump: 0,
    jumpPhase: 0,
    jumpSpacing: 2 * Math.PI,
    limitBefore: 0,
    limitAfter: 0,
    peak: 1,
    at(theta) {
      const u = wrapPhase(theta);
      return u < Math.PI ? Math.sin(u) : 0;
    },
  },
};

/** 把任意相位摺回 [0, 2π)。負數也要對，所以不能只用 `%`。 */
export function wrapPhase(theta) {
  const period = 2 * Math.PI;
  const u = theta % period;
  return u < 0 ? u + period : u;
}

/** 目標波形在相位 θ 上的值。 */
export function idealWaveformAt(kind, theta) {
  const shape = WAVEFORMS[kind];
  if (!shape) throw new Error(`unknown waveform: ${kind}`);
  return shape.at(theta);
}

/**
 * 部分和在相位 θ 上的值：dc + Σ Aₙ sin(nθ + φₙ)。
 *
 * ⚠️ 直接照定義逐項加，**不做任何遞迴或角度加法定理的加速**。
 * 這一層的正確性是整個展示的地基（畫面、聲音、過衝的數字全部由它來），
 * 而遞迴式的正弦產生器會累積誤差——那正是 §8.9 落差 5 已經踩過一次的坑。
 */
export function partialSumAt(series, theta) {
  let sum = series.dc || 0;
  for (const h of series.harmonics) {
    if (h.amplitude === 0) continue;
    sum += h.amplitude * Math.sin(h.n * theta + h.phase);
  }
  return sum;
}

/** 單一諧波在相位 θ 上的值。個別諧波分解圖用它。 */
export function harmonicAt(harmonic, theta) {
  return harmonic.amplitude * Math.sin(harmonic.n * theta + harmonic.phase);
}

/**
 * 在 [t0, t0 + duration] 上等距求值，回傳 {times, values}。
 *
 * `evaluate` 吃相位、吐值——三種曲線（目標、部分和、單一諧波）因此共用
 * 同一支取樣器，時間軸一定對得起來。三份各自寫一次的話，
 * 只要有一份把 `count - 1` 寫成 `count`，兩條曲線就會差半個像素而沒有人發現。
 */
export function traceByPhase(evaluate, f0, t0, duration, count) {
  const times = new Float64Array(count);
  const values = new Float64Array(count);
  for (let i = 0; i < count; i += 1) {
    const t = t0 + (duration * i) / (count - 1 || 1);
    times[i] = t;
    values[i] = evaluate(2 * Math.PI * f0 * t);
  }
  return { times, values };
}

export function traceIdealWaveform(kind, f0, t0, duration, count) {
  return traceByPhase((theta) => idealWaveformAt(kind, theta), f0, t0, duration, count);
}

export function tracePartialSum(series, f0, t0, duration, count) {
  return traceByPhase((theta) => partialSumAt(series, theta), f0, t0, duration, count);
}

export function traceHarmonic(harmonic, f0, t0, duration, count) {
  return traceByPhase((theta) => harmonicAt(harmonic, theta), f0, t0, duration, count);
}

/** 級數裡真正有值的最高次諧波。過衝的**寬度**由它決定，不是由 N 決定。 */
export function highestActiveHarmonic(series) {
  let highest = 0;
  for (const h of series.harmonics) {
    if (h.amplitude !== 0 && h.n > highest) highest = h.n;
  }
  return highest;
}

/**
 * 量測不連續點附近的過衝——**吉布斯現象的那個數字**。
 *
 * 這一支存在的理由是教學上的：學生看得到角落翹起來，但「翹了多少」
 * 用眼睛讀不出來，而整個誤解（「加更多項就會收斂到完美」）就活在那個
 * 讀不出來的縫隙裡。把它印成一個百分比，誤解才有機會被戳破。
 *
 * **三個實作決定，每一個都影響那個數字對不對：**
 *
 * 1. **分母是落差（jump），不是振幅。** 課本的「約 9%」指的是落差的 9%。
 *    方波由 -1 跳到 +1，落差是 2，而部分和的峰值約 1.179——
 *    (1.179 - 1) / 2 ≈ 0.0895。若拿振幅 1 當分母就會印出 17.9%，
 *    那個數字在任何課本上都找不到，而學生會相信畫面。
 * 2. **只掃不連續點附近，不掃整個週期。** 第一個極大值落在距離跳點
 *    約 π/n_max 的地方，所以掃 ±4π/n_max 一定涵蓋得到；
 *    在這個小窗裡放 2048 點，格距是 n_max 無關的常數，
 *    因此**過衝的數值精度不隨 N 變差**。掃整個週期則相反：
 *    N 越大峰越窄，固定點數會越來越量不準——而那恰好會**製造出
 *    「過衝隨 N 下降」的假象**，也就是我們要糾正的那個誤解。
 * 3. **連續波形回傳 `overshootFraction: null`，不回傳 0。**
 *    三角波沒有不連續點，所以「過衝佔落差的百分之幾」這個問題
 *    本身不成立。回傳 0 會讓畫面顯示「0%」，而那讀起來像是
 *    「過衝存在但等於零」——它其實是「這個問題不適用」。
 *
 * @param {string} kind
 * @param {object} series
 * @param {{points?: number, widthFactor?: number}} [options]
 */
export function measureOvershoot(kind, series, { points = 2048, widthFactor = 4 } = {}) {
  const shape = WAVEFORMS[kind];
  if (!shape) throw new Error(`unknown waveform: ${kind}`);
  const highest = highestActiveHarmonic(series);

  if (shape.jump === 0 || highest === 0) {
    // 連續波形：仍然回報峰值（「部分和最高到 0.998，目標是 1」是有用的訊息），
    // 但**不回報百分比**——見上面的第 3 點。
    let peak = -Infinity;
    for (let i = 0; i < points; i += 1) {
      const theta = (2 * Math.PI * i) / points;
      const value = partialSumAt(series, theta);
      if (value > peak) peak = value;
    }
    return {
      jump: shape.jump,
      limit: shape.peak,
      peak,
      overshoot: null,
      overshootFraction: null,
      peakPhase: null,
      peakOffsetPeriods: null,
      highestHarmonic: highest,
      points,
    };
  }

  // 搜尋窗的半寬。兩道上限，第二道是被實際輸出抓出來的：
  //   * `widthFactor · π / n_max`——第一個極大值落在約 π/n_max，取四倍很夠。
  //   * **不得超過「到下一個跳點的一半距離」**。方波一個週期跳兩次
  //     （θ = 0 與 θ = π），N 很小時第一道算出來的窗會比 π 還寬，
  //     於是它會越過中線、量到**另一個跳點**的過衝。高度剛好一樣
  //     （方波對稱），所以百分比看起來完全正常——錯的是
  //     `peakOffsetPeriods`，它會回報 0.375 個週期，而那一欄的標題
  //     寫著「離跳點多遠」。一個對的數字配一個錯的數字，最難發現。
  const halfWidth = Math.min(
    (shape.jumpSpacing || 2 * Math.PI) / 2,
    (widthFactor * Math.PI) / highest,
  );
  const limit = Math.max(shape.limitBefore, shape.limitAfter);
  let peak = -Infinity;
  let peakPhase = shape.jumpPhase;
  for (let i = 0; i < points; i += 1) {
    const theta = shape.jumpPhase - halfWidth + (2 * halfWidth * i) / (points - 1);
    const value = partialSumAt(series, theta);
    if (value > peak) {
      peak = value;
      peakPhase = theta;
    }
  }
  return {
    jump: shape.jump,
    limit,
    peak,
    overshoot: peak - limit,
    overshootFraction: (peak - limit) / shape.jump,
    peakPhase,
    // 峰**離跳點多遠**，用週期的比例表示。過衝的高度不隨 N 下降，
    // 但這個數字會——它就是「越來越窄」在畫面上的那個量。
    peakOffsetPeriods: Math.abs(peakPhase - shape.jumpPhase) / (2 * Math.PI),
    highestHarmonic: highest,
    points,
  };
}

/**
 * 部分和與目標波形在一整個週期上的**最大差距**。
 *
 * 這一支與 `measureOvershoot()` 是一對，而且它們回答的是兩個不同的問題：
 *
 *   * 過衝問的是「角落翹起來多少」——那是一個**局部**的量。
 *   * 這裡問的是「最糟的一點差多少」——那是**一致收斂**的量。
 *
 * 兩個數字在連續波形上一起往下掉（三角波是 1/N²），在有跳點的波形上
 * 卻分道揚鑣：過衝穩定在落差的 9% 左右，而最大差距**根本不下降**——
 * 它停在跳點那一格上（部分和在跳點恆為兩個單邊極限的中點，
 * 因此差距永遠是落差的一半）。
 *
 * 這正是「加更多項就會收斂到完美」錯在哪裡的最精確說法，
 * 所以它值得一個自己的數字，而不是被塞進過衝的註腳裡。
 *
 * ⚠️ 取樣點數用**偶數**，並且從 θ = 0 開始等距——這樣 0 與 π 都會落在
 * 格子上，也就是兩個跳點都被取到。奇數點會恰好跳過它們，
 * 而症狀是這個數字看起來在收斂（一個很有說服力的錯誤）。
 */
export function maxDeviation(kind, series, { points = 4096 } = {}) {
  const even = points % 2 === 0 ? points : points + 1;
  let worst = 0;
  for (let i = 0; i < even; i += 1) {
    const theta = (2 * Math.PI * i) / even;
    const gap = Math.abs(partialSumAt(series, theta) - idealWaveformAt(kind, theta));
    if (gap > worst) worst = gap;
  }
  return worst;
}

/**
 * 產生 `AudioContext.createPeriodicWave()` 要的那兩張表。
 *
 * Web Audio 的合成式是
 *
 *     x(t) = Σ_{k≥1} ( real[k]·cos(2πkt) + imag[k]·sin(2πkt) )
 *
 * 而我們的一項是 Aₙ sin(nθ + φₙ) = Aₙcos φₙ·sin(nθ) + Aₙsin φₙ·cos(nθ)，
 * 所以 **real ← a 係數（cos 那邊）、imag ← b 係數（sin 那邊）**。
 * 這兩者寫反不會爆錯、也不會改變頻譜——只會讓每個諧波的相位差 90°，
 * 而那**恰好就是這一頁在教的東西**，所以它是這個檔案裡最不能出錯的一行。
 * `tests/test_dsp_js.py` 因此把這兩張表餵回合成式，逐點與 `partialSumAt()` 比對。
 *
 * ⚠️ **索引 0（直流）一律填 0。** Web Audio 的合成式從 k = 1 開始，
 * 直流項根本不會被播出來。這不是我們的取捨——半波整流的那個 1/π
 * 在畫面上有、在聲音裡沒有，頁面上必須說出這件事（規則 4）。
 */
export function periodicWaveTables(series) {
  const count = series.harmonics.length;
  const real = new Float32Array(count + 1);
  const imag = new Float32Array(count + 1);
  for (const h of series.harmonics) {
    if (h.n > count) continue;
    real[h.n] = h.amplitude * Math.sin(h.phase);   // cos 的係數
    imag[h.n] = h.amplitude * Math.cos(h.phase);   // sin 的係數
  }
  return { real, imag };
}

// ================== 摺積與 LTI：序列與音訊訊號（2S10，PLAN §8.2.1 第 4 列）
//
// 分工見 `transform.js` 那一段的開頭：**序列在這裡，摺積這個運算在那裡。**
// 兩邊互不 import。
//
// ⚠️ **同一組脈衝響應要在兩個尺度上使用**，這是這個展示結構上唯一的講究：
// 上半頁的離散圖用 6–16 個 tap（看得見每一根），下半頁的聲音用幾萬個
// （聽得見那是一個房間）。**兩者由同一支 `impulseResponse()` 產生**，
// 差別只在呼叫端把 delay／length 從「格」換成「毫秒 × 取樣率」。
// 寫成兩支函式的話，「畫面上那個 h 就是耳朵裡那個 h」這句話會慢慢變成假的。

/**
 * 六種脈衝響應。`uses` 是這個形狀真正用得到哪些參數——畫面上據此說明
 * 哪一支滑桿現在有作用，而不是讓學生拖一支沒有反應的滑桿（那是靜默失敗
 * 的一種很溫和但很惱人的形式）。
 */
export const RESPONSE_SHAPES = {
  impulse: { label: 'A single impulse', uses: [] },
  delay: { label: 'A pure delay', uses: ['delay'] },
  echo: { label: 'An impulse plus one quieter copy', uses: ['delay', 'gain'] },
  repeat: { label: 'A train of impulses, each quieter', uses: ['delay', 'gain', 'length'] },
  average: { label: 'A flat block of L equal taps', uses: ['length'] },
  difference: { label: 'Plus one, then minus one', uses: [] },
};

/**
 * 產生一個脈衝響應。回傳 Float64Array（tap 的值，索引就是延遲的格數）。
 *
 * 六個形狀，每一個都是一句話說得完的東西——**這是刻意的**：學生要能
 * 在腦子裡先猜出「這個 h 會讓聲音變成什麼樣」，再按下播放去對答案。
 * 一個看不懂的 h 只會讓摺積看起來更神秘。
 *
 * ⚠️ `repeat` 的 tap 數由 `length` 決定而不是寫死幾個：離散圖只放得下
 * 三、四個回音，而聲音那一側要六個以上才聽得出「殘響」而不是「回音」。
 * 同一個公式、兩個 length，這樣兩邊仍然是同一個 h。
 */
export function impulseResponse(shape, { delay = 3, length = 6, gain = 0.6 } = {}) {
  const d = Math.max(1, Math.round(delay));
  const L = Math.max(1, Math.round(length));
  switch (shape) {
    case 'impulse':
      return Float64Array.from([1]);

    case 'delay': {
      const out = new Float64Array(d + 1);
      out[d] = 1;
      return out;
    }

    // 1 在 0（原音）＋ gain 在 d（一次回音）。這是最小的「有記憶」系統。
    case 'echo': {
      const out = new Float64Array(d + 1);
      out[0] = 1;
      out[d] = gain;
      return out;
    }

    // gain^k 在 k·d。⚠️ 這是**梳狀**的 FIR，不是回授——見 transform.js 的
    // `convolutionGainBound()`：沒有回授就不可能有無限增益。
    case 'repeat': {
      const count = Math.max(1, Math.floor((L - 1) / d) + 1);
      const out = new Float64Array((count - 1) * d + 1);
      for (let k = 0; k < count; k += 1) out[k * d] = gain ** k;
      return out;
    }

    // 1/L，L 格。直流增益恰好 1（見 directCurrentGain），所以音量不變，
    // 變的只有高頻——這正是「低通」在時域裡長什麼樣。
    case 'average': {
      const out = new Float64Array(L);
      out.fill(1 / L);
      return out;
    }

    // [1, −1]。直流增益恰好 0，所以常數輸入完全消失。
    // **這就是影像邊緣偵測在一維上的樣子**——課堂上的 convolve2d 邊緣核
    // 是同一個東西鋪成二維，只是這裡只有兩格，看得完。
    case 'difference':
      return Float64Array.from([1, -1]);

    default:
      throw new Error(`unknown impulse response: ${shape}`);
  }
}

/** 四種離散輸入。短、好認、而且各自對應一個要看的現象。 */
export const INPUT_SHAPES = {
  impulse: 'A single impulse',
  pulse: 'A rectangular pulse',
  ramp: 'A ramp',
  wiggle: 'A short wiggle',
};

/** 固定的那一個。刻意有正有負，讓「乘出來的那一格是負的」也看得到。 */
const WIGGLE = [1, 0.55, -0.4, -0.75, -0.2, 0.5, 0.3];

export function inputSequence(shape, { length = 4 } = {}) {
  const L = Math.max(1, Math.round(length));
  switch (shape) {
    // 長度 1。**這一個是整頁最重要的輸入**：y = x * δ = h，也就是
    // 「脈衝響應」這個名字的由來，而它在畫面上是一個可以直接對照的等式。
    case 'impulse':
      return Float64Array.from([1]);

    // 兩個矩形的摺積是梯形，這是課本上唯一一個學生可以完全手算的例子，
    // 也是 `tests/test_dsp_js.py` 拿來對解析解的那一個。
    case 'pulse': {
      const out = new Float64Array(L);
      out.fill(1);
      return out;
    }

    case 'ramp': {
      const out = new Float64Array(L);
      for (let i = 0; i < L; i += 1) out[i] = (i + 1) / L;
      return out;
    }

    case 'wiggle':
      return Float64Array.from(WIGGLE);

    default:
      throw new Error(`unknown input shape: ${shape}`);
  }
}

/**
 * 非零的 tap，最多 `limit` 個。回傳 `[{index, value}]`。
 *
 * 兩個用途，都不是最佳化：音訊那一側的 h 有幾萬格而其中只有六格非零
 * （畫成幾萬根棒子就是一片黑），以及螢幕閱讀器要的那句
 * 「h has 4 taps: at 0, 120, 240 and 360 milliseconds」（§8.6 第 3 點）。
 */
export function nonZeroTaps(h, { limit = 64, epsilon = 1e-9 } = {}) {
  const taps = [];
  for (let i = 0; i < h.length; i += 1) {
    if (Math.abs(h[i]) > epsilon) {
      taps.push({ index: i, value: h[i] });
      if (taps.length >= limit) break;
    }
  }
  return taps;
}

/**
 * 只數個數，不造陣列。
 *
 * 分成兩支不是潔癖：移動平均在 48 kHz 下有近千個 tap，而畫面每一格都要
 * 報一次「有幾個」——用 `nonZeroTaps()` 去數就是每秒配置三萬個小物件，
 * 而那正是 §8.5 說的「在音訊執行緒上製造 GC」的鄰居。
 */
export function countNonZeroTaps(h, { epsilon = 1e-9 } = {}) {
  let count = 0;
  for (let i = 0; i < h.length; i += 1) if (Math.abs(h[i]) > epsilon) count += 1;
  return count;
}

// ---------------------------------------------------- LTI 檢驗用的測試訊號
//
// **這三條序列是寫死的，而且不該變成滑桿。** 理由是它們必須同時滿足三個
// 條件，而那不是拖滑桿拖得出來的：
//
//   1. `LTI_A + LTI_B` 的峰值要**超過** `CLIP_LEVEL`（否則削波根本不動作，
//      而畫面會顯示「削波是線性的」——一個完全錯誤、卻很有說服力的結論）。
//   2. 兩條各自的峰值要**低於** `CLIP_LEVEL`（否則連 T(x₁) 都被削掉，
//      殘差還是非零，但原因就不再是疊加性了）。
//   3. `LTI_PROBE` 尾巴要留夠平移用的零，理由見 `timeInvarianceResidual()`。
//
// 三個條件互相牽制，所以它們由測試盯著（`tests/test_dsp_js.py` 有一項
// 直接斷言這三件事），不是靠註解提醒。

export const LTI_SHIFT = 2;

/** 峰值 0.45 < CLIP_LEVEL(0.5)。 */
export const LTI_A = Float64Array.from([0.45, 0.45, 0.45, 0, 0, 0, 0, 0]);

/** 峰值 0.4；與 LTI_A 相加後峰值 0.85 > CLIP_LEVEL。 */
export const LTI_B = Float64Array.from([0.4, 0, 0.4, 0.35, 0.35, 0, 0, 0]);

/** 非時變檢驗用。**後 4 格是留給平移的零**，見上面第 3 點。 */
export const LTI_PROBE = Float64Array.from([0.6, 0.3, -0.5, 0.2, 0, 0, 0, 0, 0, 0, 0, 0]);

// ------------------------------------------------------------ 音訊那一側
//
// ⚠️ **絕不寫死取樣率**（§8.5）：每一支都吃 `sampleRate`，而呼叫端一律傳
// `ctx.sampleRate`。這一頁尤其不能作弊——延遲是以毫秒指定的，
// 換算成格數就要用真的取樣率，錯了的話畫面上寫 120 ms 而耳朵聽到 110 ms。

/**
 * 一個很短的 click：升餘弦包絡的一個半週期。
 *
 * **為什麼不用單一個樣本的理想脈衝**：一個 1/48000 秒的樣本在喇叭上
 * 幾乎聽不見（它的能量太小），而聽不見會讓「y = x * δ = h」這件事
 * 在耳朵裡不成立。1 ms 的 click 相對於幾百毫秒的 h 仍然「幾乎是」脈衝，
 * 而它清楚可聞。**頁面上要把這個「幾乎」說出來**（規則 4）。
 */
export function clickSignal(sampleRate, { millis = 1 } = {}) {
  const n = Math.max(1, Math.round((millis * sampleRate) / 1000));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    out[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * (i + 0.5)) / n);
  }
  return out;
}

/**
 * 一個撥弦似的短音：指數衰減的正弦。
 *
 * 挑它而不是持續音，是因為**回音要在靜音的背景上才聽得見**。
 * 一個一直響著的正弦被加上 120 ms 的回音之後，聽起來只是「大聲了一點」。
 */
export function pluckSignal(sampleRate, { frequency = 330, seconds = 0.35, decay = 7 } = {}) {
  const n = Math.max(1, Math.round(seconds * sampleRate));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    const t = i / sampleRate;
    out[i] = Math.exp(-decay * t) * Math.sin(2 * Math.PI * frequency * t);
  }
  return out;
}

/**
 * 在尾巴接上一段靜音。
 *
 * 播放是 `loop = true` 的，而回音的尾巴會被下一輪的開頭蓋過去——
 * **那正好把這一頁要聽的東西剪掉**。補一段比 h 還長的靜音就解決了。
 */
export function padSilence(x, sampleRate, seconds) {
  const extra = Math.max(0, Math.round(seconds * sampleRate));
  const out = new Float32Array(x.length + extra);
  out.set(x, 0);
  return out;
}

/** 峰值絕對值。播放前的音量正規化與畫面上的縱軸都用它。 */
export function peakAmplitude(x) {
  let peak = 0;
  for (let i = 0; i < x.length; i += 1) {
    const v = Math.abs(x[i]);
    if (v > peak) peak = v;
  }
  return peak;
}

// viewWindowSeconds 需要混疊頻率，但混疊頻率住在 transform.js。
// 為了不讓 signal.js 反向依賴 transform.js（那會讓兩層互相 import），
// 這裡放一份**只給視窗計算用**的最小版本，並在測試裡斷言它與
// transform.js 的 `aliasFrequency` 對所有測試輸入都相等。
// 這是刻意的重複：一份 5 行的重複，換掉一個循環相依。
function aliasFrequencyForWindow(f, fs) {
  if (fs <= 0) return f;
  return Math.abs(f - Math.round(f / fs) * fs);
}
