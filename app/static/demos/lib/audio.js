// AudioContext 的生命週期（PLAN.md §8.2.3 的第一支基礎設施）。
//
// **這一支存在的唯一理由是硬規則 4（不許靜默失敗）。**
// 音訊有三種典型的失敗，而三者的預設症狀完全一樣——「按了按鈕，沒有聲音」：
//
//   1. 瀏覽器根本沒有 Web Audio（很舊的瀏覽器、或被企業政策關掉）
//   2. autoplay 政策擋掉了 AudioContext（沒有使用者手勢，或 resume() 被拒）
//   3. AudioWorklet 模組載入失敗（路徑錯、MIME 錯、非 secure context）
//
// 再加上一種只有麥克風展示才會遇到的：
//
//   4. 麥克風權限被拒（NotAllowedError）或裝置不存在（NotFoundError）
//
// 學生不會開 devtools，所以每一種都必須**在畫面上留一句英文訊息**，
// 不得只寫 console。把這四種集中在這裡處理一次，勝過在六個展示裡各漏一次。
//
// ⚠️ **`requestMicrophone()` 到現在仍然沒有呼叫者，而這是老師的明確決定
// （D27／D28），不是漏掉的。** §8.9 原本寫著「第一個呼叫者會是 2S4，
// 如果 2S4 沒有用到就該刪掉」——2S4 做完了，而它用的是**使用者選的音訊檔**
// 而不是麥克風（D28 把即時錄音換成了本機檔案）。老師仍要求保留這一段：
// 麥克風是這個功能區日後可能回頭用的東西，而它的價值在於「四種失敗集中
// 處理一次」這個規格，刪掉再寫一次不會比較便宜。
//
// 誠實地說一次：**它在真實瀏覽器上一次都沒有跑過**，所以它是一段
// 看起來對的程式碼，不是一段驗證過的程式碼。真的要接上去的時候，
// 第一件事是實測，不是假設它能動。

/** 失敗的種類。畫面訊息由這裡產生，展示只負責顯示。 */
export const AudioFailure = {
  UNSUPPORTED: 'unsupported',
  BLOCKED: 'blocked',
  WORKLET: 'worklet',
  MICROPHONE: 'microphone',
};

const MESSAGES = {
  [AudioFailure.UNSUPPORTED]:
    'This browser does not support the Web Audio API, so this page cannot play '
    + 'sound. The graphs still work. Try a recent version of Chrome, Firefox, '
    + 'Edge or Safari.',
  [AudioFailure.BLOCKED]:
    'The browser refused to start audio. Browsers only allow sound after you '
    + 'interact with the page — press Start sound again, and check that this '
    + 'tab is not muted.',
  [AudioFailure.WORKLET]:
    'The audio processor could not be loaded, so the sampled sound is not '
    + 'available. Reload the page; if it keeps happening, tell your instructor '
    + 'which browser you are using.',
  [AudioFailure.MICROPHONE]:
    'Microphone access was refused or no microphone was found, so the built-in '
    + 'test signal is used instead. Microphone input also needs a secure '
    + 'connection (https or localhost).',
};

/** 音量斜坡的時間常數（秒）。太短會有爆音，太長會覺得延遲。 */
const RAMP_TAU = 0.015;

/**
 * 把一個 AudioParam 平滑地帶到目標值。
 *
 * 直接寫 `param.value = x` 在音訊執行緒上是一個不連續的跳變，聽起來是
 * 「喀」一聲——滑桿快速拖動時會連續產生好幾十個。這是 §8.5 要求處理的
 * 那件事，處理方式就是這一個函式，全展示只准用它改參數。
 */
export function rampParam(param, value, ctx, tau = RAMP_TAU) {
  const now = ctx.currentTime;
  param.cancelScheduledValues(now);
  param.setTargetAtTime(value, now, tau);
}

/**
 * 線性斜坡到目標值，並且**確實到達**。
 *
 * 給那些「畫面上顯示的數字必須等於實際在用的數字」的參數用（取樣率、
 * 音高、濾波器轉角）。`setTargetAtTime` 是指數逼近，永遠差一點點——
 * 對音量無所謂，但對讀數就是一句小小的假話，而這個展示整頁都在教
 * 「畫面上那個數字是什麼意思」。
 */
export function rampParamLinear(param, value, ctx, seconds = 0.02) {
  const now = ctx.currentTime;
  param.cancelScheduledValues(now);
  param.setValueAtTime(param.value, now);
  param.linearRampToValueAtTime(value, now + seconds);
}

export class DemoAudio {
  /**
   * @param {object} options
   * @param {(kind: string, message: string) => void} options.onFailure
   *        畫面訊息的出口。**必填**——沒有它就等於允許靜默失敗。
   * @param {(running: boolean, reason: string) => void} [options.onStateChange]
   * @param {string[]} [options.workletModules] 要載入的 worklet 模組 URL
   */
  constructor({ onFailure, onStateChange, workletModules = [] }) {
    if (typeof onFailure !== 'function') {
      // 這是開發期的錯誤，不是執行期的失敗——大聲一點比較好。
      throw new Error('DemoAudio requires an onFailure callback (rule 4).');
    }
    this.onFailure = onFailure;
    this.onStateChange = onStateChange || (() => {});
    this.workletModules = workletModules;
    this.ctx = null;
    this.master = null;
    this.running = false;
    this.muted = false;
    this.volume = 0.15;          // 保守的預設音量（§8.5：音訊安全）
    this._workletsLoaded = false;
    this._onVisibility = () => {
      if (document.hidden && this.running) this.stop('hidden');
    };
    document.addEventListener('visibilitychange', this._onVisibility);
  }

  static get supported() {
    return typeof window !== 'undefined'
      && Boolean(window.AudioContext || window.webkitAudioContext);
  }

  /** 裝置實際的取樣率。**絕不寫死 44100**（§8.5），而且它本身就是教材。 */
  get sampleRate() {
    return this.ctx ? this.ctx.sampleRate : null;
  }

  /**
   * 開始發聲。**必須在使用者手勢的 handler 裡直接呼叫**（autoplay 政策）。
   * 回傳是否成功；失敗時已經透過 onFailure 報告過了。
   */
  async start() {
    if (!DemoAudio.supported) {
      this._fail(AudioFailure.UNSUPPORTED);
      return false;
    }
    try {
      if (!this.ctx) {
        const Ctor = window.AudioContext || window.webkitAudioContext;
        this.ctx = new Ctor();
        this.master = this.ctx.createGain();
        this.master.gain.value = 0;
        this.master.connect(this.ctx.destination);
      }
      if (this.ctx.state === 'suspended') await this.ctx.resume();
      if (this.ctx.state !== 'running') {
        this._fail(AudioFailure.BLOCKED);
        return false;
      }
    } catch (err) {
      this._fail(AudioFailure.BLOCKED, err);
      return false;
    }

    if (!this._workletsLoaded && this.workletModules.length > 0) {
      try {
        if (!this.ctx.audioWorklet) throw new Error('AudioWorklet is not available');
        for (const url of this.workletModules) {
          await this.ctx.audioWorklet.addModule(url);
        }
        this._workletsLoaded = true;
      } catch (err) {
        this._fail(AudioFailure.WORKLET, err);
        return false;
      }
    }

    this.running = true;
    this._applyGain();
    this.onStateChange(true, 'started');
    return true;
  }

  /** 乾淨地停止：先把音量降下來再斷開，避免結束時的爆音。 */
  stop(reason = 'stopped') {
    if (!this.ctx) return;
    this.running = false;
    rampParam(this.master.gain, 0, this.ctx);
    this.onStateChange(false, reason);
  }

  setVolume(v) {
    this.volume = v;
    this._applyGain();
  }

  setMuted(muted) {
    this.muted = muted;
    this._applyGain();
  }

  _applyGain() {
    if (!this.ctx) return;
    const target = (this.running && !this.muted) ? this.volume : 0;
    rampParam(this.master.gain, target, this.ctx);
  }

  /**
   * 麥克風。權限被拒時**不是靜默降級**：訊息會出現在畫面上，
   * 而且呼叫端拿到 null 之後應該明確地退回內建訊號（§8.5 稱這種
   * 「功能明確變窄且說出來了」的降級是有意義的降級）。
   *
   * ⚠️ 目前沒有呼叫者，見檔案開頭。
   */
  async requestMicrophone() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this._fail(AudioFailure.MICROPHONE, new Error('getUserMedia is unavailable'));
      return null;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      return this.ctx.createMediaStreamSource(stream);
    } catch (err) {
      this._fail(AudioFailure.MICROPHONE, err);
      return null;
    }
  }

  dispose() {
    document.removeEventListener('visibilitychange', this._onVisibility);
    this.stop('disposed');
  }

  _fail(kind, err) {
    // 兩個出口都要走：畫面給學生看，console 給維護的人看（規則 4）。
    if (err) console.error(`[demo audio] ${kind}:`, err);
    else console.error(`[demo audio] ${kind}`);
    this.onFailure(kind, MESSAGES[kind]);
  }
}
