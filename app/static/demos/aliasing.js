// 展示 1：取樣與混疊（PLAN.md §8.2.1 第 1 列，路線圖 2S3）。
//
// **這是唯一知道 DOM、AudioContext 與使用者手勢的一層。**
// 這裡不放任何數值演算法——所有算數都在 signal.js／transform.js／draw.js，
// 因為 `tests/test_dsp_js.py` 只測得到那三層（§8.2.3 表格最後一欄）。
//
// 狀態管理：一個普通物件 + 一個 render()。唯一的規則是
// **DOM 永遠不是真相的來源**——輸入事件只做「寫進 state」，
// render() 只做「把 state 畫出來」。
//
// 音訊圖（§8.5：能用原生節點就不要自己寫 worklet，所以只有取樣器是自訂的）：
//
//   OscillatorNode ─┬─────────────────────────────────────────► originalGain ─┐
//                   │                                                         ├─► master
//                   └─► antiAlias ─► zoh-sampler ─► recon1 ─► recon2 ─► sampledGain ─┘
//                       (BiquadLP)   (自訂 worklet)  (BiquadLP ×2)
//
// 防混疊濾波器**在取樣器之前**，重建濾波器在之後——這個順序就是這個展示要
// 教的其中一件事，所以程式的接線順序刻意與教材上的方塊圖一致。

import { DemoAudio, AudioFailure, rampParam, rampParamLinear } from './lib/audio.js';
import { createShell, bindNumberPair } from './lib/shell.js';
import {
  traceSine, sampleTimes, sineAt, viewWindowSeconds, clamp,
} from './lib/signal.js';
import {
  nyquist, aliasFrequency, signedAliasFrequency, isAliased,
} from './lib/transform.js';
import {
  makeScale, curvePoints, staircasePoints, fitCanvas,
  clear, strokeAxes, strokePolyline, strokeStems,
} from './lib/draw.js';

// ---------------------------------------------------------------- 狀態

const state = {
  tone: 1200,          // Hz
  rate: 8000,          // Hz
  listen: 'original',  // 'original' | 'sampled'
  antiAlias: false,
  running: false,
  deviceRate: null,    // ctx.sampleRate，由裝置決定
};

// 曲線的樣式。**不只用顏色區分**（§8.6 第 4 點）：實線／點／虛線／點線，
// 圖例上也寫著線型，因此色盲或黑白列印都讀得出來。
const STYLE = {
  axis: '#c7ccd4',
  original: { color: '#1f4fd8', width: 2, dash: [] },
  alias: { color: '#c2410c', width: 2.5, dash: [8, 5] },
  hold: { color: '#6b7280', width: 1.5, dash: [2, 4] },
  samples: { color: '#111827', radius: 3.5 },
};

const PAD = { left: 12, right: 12, top: 16, bottom: 16 };

// ---------------------------------------------------------------- DOM

const root = document.querySelector('.demo-layout');
const canvas = document.getElementById('scope');
const outTone = document.getElementById('out-tone');
const outRate = document.getElementById('out-rate');
const outNyquist = document.getElementById('out-nyquist');
const outAlias = document.getElementById('out-alias');
const verdict = document.getElementById('verdict');
const scopeDescription = document.getElementById('scope-description');

// ---------------------------------------------------------------- 音訊

let nodes = null;   // start() 之後才有；停止時不拆掉（重新開始很便宜）

const audio = new DemoAudio({
  workletModules: ['/static/demos/worklets/sampler-processor.js'],
  onFailure: (kind, message) => {
    shell.showMessage(message, kind === AudioFailure.MICROPHONE ? 'warning' : 'error');
    shell.setRunning(false);
    state.running = false;
    shell.scheduleRender();
  },
  onStateChange: (running, reason) => {
    state.running = running;
    shell.setRunning(running);
    shell.setSampleRate(running ? audio.sampleRate : null);
    if (!running && reason === 'hidden') {
      shell.showMessage(
        'Sound stopped because you left this tab. Press Start sound to '
        + 'continue.', 'notice',
      );
    }
    shell.scheduleRender();
  },
});

function buildGraph() {
  const ctx = audio.ctx;
  const osc = ctx.createOscillator();
  osc.type = 'sine';
  osc.frequency.value = state.tone;

  const antiAlias = ctx.createBiquadFilter();
  antiAlias.type = 'lowpass';

  const sampler = new AudioWorkletNode(ctx, 'zoh-sampler');

  const recon1 = ctx.createBiquadFilter();
  recon1.type = 'lowpass';
  const recon2 = ctx.createBiquadFilter();
  recon2.type = 'lowpass';

  const originalGain = ctx.createGain();
  originalGain.gain.value = 0;
  const sampledGain = ctx.createGain();
  sampledGain.gain.value = 0;

  osc.connect(originalGain).connect(audio.master);
  osc.connect(antiAlias).connect(sampler).connect(recon1).connect(recon2)
    .connect(sampledGain).connect(audio.master);

  osc.start();
  return { osc, antiAlias, sampler, recon1, recon2, originalGain, sampledGain };
}

/**
 * 把 state 推到音訊節點上。**每一個變動都走斜坡**（§8.5：滑桿快速拖動時的
 * 爆音要處理）——直接寫 `.value` 是一個不連續跳變，聽起來是「喀」一聲。
 */
function applyAudio() {
  if (!nodes) return;
  const ctx = audio.ctx;
  // 濾波器轉角的上限刻意留一段餘裕，**不貼著裝置的奈奎斯特頻率**：
  // BiquadFilterNode 的係數在轉角逼近 fs/2 時會退化（不同瀏覽器的處理不一致，
  // 最壞的情況是輸出 NaN 之後整條音訊鏈永久靜音——正是規則 4 禁止的那種
  // 沒有訊息的失敗）。20 kHz 已經在聽覺上限之上，當「濾波器關掉」綽綽有餘。
  const maxCutoff = Math.min(20000, ctx.sampleRate * 0.45);

  rampParamLinear(nodes.osc.frequency, state.tone, ctx);

  // 防混疊濾波器：關掉的時候不拆節點，只把轉角推到聽不見的地方。
  // 拆接線會在音訊執行緒上產生一個不連續，而那正是我們在避免的東西。
  const aaCut = state.antiAlias
    ? clamp(state.rate / 2, 20, maxCutoff)
    : maxCutoff;
  rampParamLinear(nodes.antiAlias.frequency, aaCut, ctx);

  rampParamLinear(nodes.sampler.parameters.get('samplingRate'), state.rate, ctx);

  // 重建濾波器（D/A 那一顆）：兩級 lowpass 在 fs/2。
  const reconCut = clamp(state.rate / 2, 20, maxCutoff);
  rampParamLinear(nodes.recon1.frequency, reconCut, ctx);
  rampParamLinear(nodes.recon2.frequency, reconCut, ctx);

  const listeningToOriginal = state.listen === 'original';
  rampParam(nodes.originalGain.gain, listeningToOriginal ? 1 : 0, ctx);
  rampParam(nodes.sampledGain.gain, listeningToOriginal ? 0 : 1, ctx);
}

async function toggleSound() {
  if (state.running) {
    audio.stop();
    return;
  }
  shell.clearMessage();
  const ok = await audio.start();
  if (!ok) return;                 // 失敗訊息已經由 onFailure 放上畫面了
  if (!nodes) nodes = buildGraph();
  state.deviceRate = audio.sampleRate;
  applyAudio();
  shell.scheduleRender();
}

// ---------------------------------------------------------------- 外框與控制項

const shell = createShell({
  root,
  onToggle: toggleSound,
  onMuteChange: (muted) => audio.setMuted(muted),
  onVolumeChange: (v) => audio.setVolume(v),
});

audio.setVolume(shell.volume);

bindNumberPair({
  range: document.getElementById('tone'),
  number: document.getElementById('tone-number'),
  onChange: (value) => {
    state.tone = value;
    applyAudio();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('rate'),
  number: document.getElementById('rate-number'),
  onChange: (value) => {
    state.rate = value;
    applyAudio();
    shell.scheduleRender();
  },
});

for (const radio of document.querySelectorAll('input[name="listen"]')) {
  radio.addEventListener('change', () => {
    if (!radio.checked) return;
    state.listen = radio.value;
    applyAudio();
    shell.scheduleRender();
  });
}

document.getElementById('antialias').addEventListener('change', (event) => {
  state.antiAlias = event.target.checked;
  applyAudio();
  shell.scheduleRender();
});

// ---------------------------------------------------------------- 文字

const hz = (v) => `${Math.round(v)} Hz`;

/**
 * 一句給螢幕閱讀器的狀態播報（§8.6 第 2 點）：內容就是視力正常的學生
 * 從讀數區看到的那一行數字，不多也不少。
 */
function statusSentence() {
  const apparent = aliasFrequency(state.tone, state.rate);
  return `Sampling rate ${hz(state.rate)}. Tone ${hz(state.tone)}. `
    + (isAliased(state.tone, state.rate)
      ? `Above the Nyquist frequency ${hz(nyquist(state.rate))}, heard as ${hz(apparent)}.`
      : `Below the Nyquist frequency ${hz(nyquist(state.rate))}, heard unchanged.`);
}

/**
 * Canvas 的文字替代是**算出來的**，不是靜態 alt（§8.6 第 3 點）。
 * 它寫的就是學生應該從圖上讀出來的結論，因此對所有人都有用。
 */
function scopeSentence(sampleCount, windowSeconds) {
  const apparent = aliasFrequency(state.tone, state.rate);
  const cycles = state.tone * windowSeconds;
  const inverted = signedAliasFrequency(state.tone, state.rate) < 0;
  return `Over ${(windowSeconds * 1000).toFixed(1)} milliseconds the graph shows `
    + `${cycles.toFixed(1)} cycles of the ${hz(state.tone)} tone, `
    + `${sampleCount} sample points taken at ${hz(state.rate)}, and a `
    + `${hz(apparent)} wave${inverted ? ', inverted,' : ''} drawn through those `
    + 'same sample points.';
}

// ---------------------------------------------------------------- 繪製

function render() {
  const { width, height, ctx } = fitCanvas(canvas, window.devicePixelRatio || 1);
  const windowSeconds = viewWindowSeconds(state.tone, state.rate);
  const scale = makeScale({
    t0: 0, t1: windowSeconds, vMin: -1.15, vMax: 1.15, width, height, pad: PAD,
  });

  // 原始連續波形：每個 CSS 像素兩個點，足夠密到看不出折線。
  const traceCount = clamp(Math.round(width * 2), 200, 4000);
  const trace = traceSine(state.tone, 0, windowSeconds, traceCount);

  // 取樣點
  const times = sampleTimes(state.rate, 0, windowSeconds);
  const values = new Float64Array(times.length);
  for (let i = 0; i < times.length; i += 1) values[i] = sineAt(state.tone, times[i]);

  // 重建：穿過同一組取樣點的那條低頻正弦。**用有號的混疊頻率**，
  // 否則反相的那半邊會與取樣點對不上（見 transform.js 的說明）。
  const signed = signedAliasFrequency(state.tone, state.rate);
  const reconstruction = traceSine(signed, 0, windowSeconds, traceCount);

  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);
  strokePolyline(ctx, staircasePoints(scale, times, values, windowSeconds),
    STYLE.hold);
  strokePolyline(ctx, curvePoints(scale, trace.times, trace.values),
    STYLE.original);
  strokePolyline(ctx,
    curvePoints(scale, reconstruction.times, reconstruction.values), STYLE.alias);
  strokeStems(ctx, curvePoints(scale, times, values), scale.y(0), STYLE.samples);

  const apparent = aliasFrequency(state.tone, state.rate);
  outTone.textContent = hz(state.tone);
  outRate.textContent = hz(state.rate);
  outNyquist.textContent = hz(nyquist(state.rate));
  outAlias.textContent = hz(apparent);

  if (isAliased(state.tone, state.rate)) {
    verdict.textContent = `f is above f_s/2, so what comes out is a clean tone `
      + `at ${hz(apparent)} instead of ${hz(state.tone)}.`;
    verdict.dataset.aliased = 'true';
  } else {
    verdict.textContent = 'f is below f_s/2, so the samples still describe the '
      + 'original tone.';
    verdict.dataset.aliased = 'false';
  }

  scopeDescription.textContent = scopeSentence(times.length, windowSeconds);
  shell.announce(statusSentence());
}

shell.onRender(render);

// ---------------------------------------------------------------- 起始

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。圖仍然能用，所以這是說明而不是致命錯誤——
  // 但它必須出現在畫面上，學生不會去開 devtools。
  shell.showMessage(
    'This browser does not support the Web Audio API, so this page cannot play '
    + 'sound. The graphs below still work.', 'warning',
  );
  document.querySelector('[data-shell="toggle"]').disabled = true;
}

shell.setSampleRate(null);
shell.scheduleRender();
