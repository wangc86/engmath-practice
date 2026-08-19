// 零階保持取樣器（AudioWorklet）。
//
// **這是整個展示區唯一的自訂 worklet**，而它之所以必須存在，是因為 Web Audio
// 沒有任何原生節點表達得出「刻意用比 ctx.sampleRate 更低的取樣率去取樣」
// 這件事（§8.5：能用原生節點就不要自己寫 worklet）。訊號產生用
// OscillatorNode、防混疊與重建濾波用 BiquadFilterNode，都是原生的。
//
// ⚠️ 這裡的迴圈必須與 `lib/signal.js` 的 `zeroOrderHold()` 逐行對應。
// 兩份的存在是刻意的——一份跑在音訊執行緒上（不能 import ES module，
// Safari 對 worklet 裡的 import 支援不一致），一份給測試與繪圖用。
// `tests/test_dsp_js.py::test_worklet_zoh_matches_the_pure_function` 會把
// 這個檔案讀進 node、注入 AudioWorklet 的那幾個全域，然後斷言兩份的輸出
// 逐格相等。**改了其中一份就會紅燈**，這正是重複該付的代價。
//
// 為什麼不用 ScriptProcessorNode：已廢棄，而且跑在主執行緒上，UI 一忙就爆音。

class SamplerProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{
      name: 'samplingRate',
      defaultValue: 8000,
      minValue: 20,
      maxValue: 192000,
      // k-rate 就夠了：取樣率一格（128 樣本 ≈ 2.7 ms）更新一次，
      // 遠快於人拖滑桿的速度，而且省掉每個樣本一次的參數查表。
      automationRate: 'k-rate',
    }];
  }

  constructor() {
    super();
    // 累加器（Bresenham）。初始化成滿格，讓第一個 frame 就抓一個樣本。
    // 累加 fs 而不是 fs/sampleRate 的理由見 lib/signal.js 的 zeroOrderHold()：
    // 前者在整數輸入下完全沒有捨入誤差，後者會慢慢漂掉。
    this.acc = sampleRate;
    this.held = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0] && inputs[0][0];
    const output = outputs[0][0];
    const fs = parameters.samplingRate[0];

    if (!input) {
      // 上游還沒接上或已經停了：輸出靜音，而不是輸出上一個保持值
      // （那會是一個持續的直流偏移，在喇叭上是一聲悶響）。
      output.fill(0);
      return true;
    }

    for (let i = 0; i < output.length; i += 1) {
      this.acc += fs;
      if (this.acc >= sampleRate) {
        while (this.acc >= sampleRate) this.acc -= sampleRate;
        this.held = input[i];
      }
      output[i] = this.held;
    }
    return true;
  }
}

registerProcessor('zoh-sampler', SamplerProcessor);
