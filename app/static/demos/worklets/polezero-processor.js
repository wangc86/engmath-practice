// 任意極零點的 IIR 濾波器（AudioWorklet）。2S9。
//
// **這是展示區的第二支自訂 worklet**，而 §8.5 那條「能用原生節點就不要自己
// 寫 worklet」的原則在這裡是被**明文豁免**的：§8.5 自己寫著自訂 worklet
// 只留給兩件事，其中一件就是「Demo 6 超過雙二階的任意極零點濾波器」。
//
// 為什麼不用原生的 `IIRFilterNode`：📄 它的係數在建構之後**不可更改**，
// 所以拖曳一次極點就要拆一個節點、建一個新的。那條路有三個問題，
// 而第三個是致命的：
//
//   1. 每次重建都要正確地 disconnect 舊節點，否則就是 §8.2 那種
//      「換頁之後還有聲音」的孤兒。拖一次滑桿會產生幾十個。
//   2. 新節點的內部狀態是零，於是每一格都從靜止重新開始——
//      共振的「鈴聲」正好是狀態的記憶，那是這一頁要聽的東西。
//   3. **它沒有地方放執行期看守。** §8.4 要求「worklet 內偵測到非有限值或
//      超過門檻的輸出樣本就停止並回報」，而原生節點的內部我們碰不到。
//
// ⚠️ 這裡的遞迴必須與 `lib/transform.js` 的 `filterSequence()` 逐行對應。
// 兩份的存在是刻意的（worklet 不能 import ES module，理由與 2S3 的 ZOH 相同），
// 而 `tests/test_dsp_js.py::test_the_worklet_recursion_matches_the_pure_function`
// 會把這個檔案讀進 node 逐格比對。**改了其中一份就會紅燈。**
//
// ============================================================================
// ⛔ **音訊安全：這一頁是整個展示區唯一有可能真的把喇叭弄壞的一頁，
//    所以防護有三層，而三層擋的是不同的東西。**
//
//   第一層（主執行緒，`polezero.js`）：極點跑出單位圓就**不送係數過來、
//     並且停止音訊**。使用者看得到一句說明——這是規則 4 要的，
//     而且它同時是 W7 的教學內容（ROC 不再包含單位圓）。
//   第二層（主執行緒，`transform.js` 的 `safetyGain()`）：把 |H| 的峰值
//     壓回 1，**只衰減不放大**。r = 0.999 的共振是 1000 倍增益，
//     那不是音量問題，是喇叭問題。
//   第三層（這裡）：**逐樣本看守**。上面兩層都在主執行緒上，而主執行緒
//     可能卡住、可能有 bug、可能被我改壞；音訊執行緒仍然在跑。
//     所以這裡不假設上游是對的，只看實際流出去的那個數字。
//
// ⚠️ 三層是刻意重疊的。任何一層單獨看起來都「應該夠了」，
//    而這正是它們必須同時存在的理由。
// ============================================================================

/** 輸出樣本的絕對值上限。超過就是有人算錯了，不是一個很大聲的訊號。 */
const OVERLOAD_LIMIT = 4;

/** 係數陣列的長度上限。目前用到 3（二階），留一點餘裕但不留無限。 */
const MAX_TAPS = 8;

class PoleZeroProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 一開始是「直通」：b = [1]、a = [1]。**不是靜音**——靜音的初始狀態
    // 會讓「按下 Start 之後沒有聲音」同時是正常與異常的症狀。
    this.current = { b: new Float64Array([1]), a: new Float64Array([1]) };
    this.target = { b: new Float64Array([1]), a: new Float64Array([1]) };
    this.blending = false;
    this.xHistory = new Float64Array(MAX_TAPS);
    this.yHistory = new Float64Array(MAX_TAPS);
    this.tripped = false;

    this.port.onmessage = (event) => {
      const data = event.data || {};
      if (data.type === 'coefficients') {
        this.target = {
          b: Float64Array.from(data.b),
          a: Float64Array.from(data.a),
        };
        if (data.immediate) {
          this.current = {
            b: Float64Array.from(data.b),
            a: Float64Array.from(data.a),
          };
          this.blending = false;
        } else {
          this.blending = true;
        }
      } else if (data.type === 'reset') {
        this.xHistory.fill(0);
        this.yHistory.fill(0);
        this.tripped = false;
      }
    };
  }

  /**
   * 一格 128 個樣本。
   *
   * 係數在這一格之內從 `current` 線性走到 `target`，**而中途每一個瞬間
   * 仍然是穩定的**——二階的穩定域（Jury 三角形）由三條線性不等式圍出來，
   * 因此是凸的，兩個穩定點之間的線段整段都在裡面。
   * 證明與它只對二階成立這件事寫在 `transform.js` 的 `isStableSecondOrder()`。
   */
  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    const output = outputs[0][0];
    const frames = output.length;

    if (this.tripped) {
      output.fill(0);
      return true;
    }

    if (!input) {
      // 上游還沒接上：輸出靜音，但**保留狀態**——重接的時候共振應該
      // 接得下去，而不是從零重新開始。
      output.fill(0);
      return true;
    }

    const { b: b0, a: a0 } = this.current;
    const { b: b1, a: a1 } = this.target;
    const bLength = Math.max(b0.length, b1.length);
    const aLength = Math.max(a0.length, a1.length);

    for (let i = 0; i < frames; i += 1) {
      const t = this.blending ? (i + 1) / frames : 1;

      let acc = 0;
      for (let k = 0; k < bLength; k += 1) {
        const coefficient = (1 - t) * (b0[k] || 0) + t * (b1[k] || 0);
        acc += coefficient * (k === 0 ? input[i] : this.xHistory[k - 1]);
      }
      for (let k = 1; k < aLength; k += 1) {
        const coefficient = (1 - t) * (a0[k] || 0) + t * (a1[k] || 0);
        acc -= coefficient * this.yHistory[k - 1];
      }
      const lead = (1 - t) * (a0[0] || 1) + t * (a1[0] || 1);
      const y = acc / (lead || 1);

      // ⛔ 第三層看守。**先檢查再寫出去**——寫出去之後才發現，
      //    那個樣本已經到喇叭了。
      if (!Number.isFinite(y) || Math.abs(y) > OVERLOAD_LIMIT) {
        this.tripped = true;
        output.fill(0);
        // 規則 4：不做靜默靜音。主執行緒收到之後會停止音訊並在畫面上
        // 說明發生了什麼——「安靜下來」與「沒有聲音」必須分得出來。
        this.port.postMessage({
          type: 'overload',
          value: Number.isFinite(y) ? y : null,
          limit: OVERLOAD_LIMIT,
        });
        return true;
      }

      for (let k = MAX_TAPS - 1; k > 0; k -= 1) {
        this.xHistory[k] = this.xHistory[k - 1];
        this.yHistory[k] = this.yHistory[k - 1];
      }
      this.xHistory[0] = input[i];
      this.yHistory[0] = y;
      output[i] = y;
    }

    if (this.blending) {
      this.current = { b: Float64Array.from(b1), a: Float64Array.from(a1) };
      this.blending = false;
    }
    return true;
  }
}

registerProcessor('pole-zero-filter', PoleZeroProcessor);
