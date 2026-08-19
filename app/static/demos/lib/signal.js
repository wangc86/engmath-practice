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

// viewWindowSeconds 需要混疊頻率，但混疊頻率住在 transform.js。
// 為了不讓 signal.js 反向依賴 transform.js（那會讓兩層互相 import），
// 這裡放一份**只給視窗計算用**的最小版本，並在測試裡斷言它與
// transform.js 的 `aliasFrequency` 對所有測試輸入都相等。
// 這是刻意的重複：一份 5 行的重複，換掉一個循環相依。
function aliasFrequencyForWindow(f, fs) {
  if (fs <= 0) return f;
  return Math.abs(f - Math.round(f / fs) * fs);
}
