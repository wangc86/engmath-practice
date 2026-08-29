// 展示 6：極零點與數位濾波器（PLAN.md §8.2.1 第 6 列，路線圖 2S9；課程 W7）。
//
// **這是唯一知道 DOM、AudioContext 與使用者手勢的一層。**
// 這裡不放任何數值演算法——極零點 → 係數 → 頻率響應 → 差分方程全部在
// `lib/transform.js`，幾何在 `lib/draw.js`，因為 `tests/test_dsp_js.py`
// 只測得到那兩層。
//
// 音訊圖：
//
//   AudioBufferSourceNode(loop) ─► AudioWorkletNode('pole-zero-filter')
//                                 ─► playGain ─► master ─► destination
//
// ============================================================================
// ⛔ **這一頁是整個展示區唯一有可能真的把喇叭弄壞的一頁。**
//
// 三層防護，擋的是不同的東西（完整說明在 `worklets/polezero-processor.js`
// 的檔頭）。這一層負責的是第一層與第二層：
//
//   * **第一層：極點跑出單位圓就停止音訊、並且說出原因。**
//     不是靜默靜音——那是規則 4 明文禁止的無聲降級，而且在這裡它還會
//     毀掉教學：極點跑出去「所以爆掉了」正是要教的事，得說出來。
//     ⚠️ 這件事在這一頁**不是一個錯誤處理，是一段教材**：
//     因果系統的收斂域是 |z| > max|p|，而它不再包含單位圓，
//     所以那條 |H(e^{jω})| 曲線**不再是任何跑得起來的系統的頻率響應**。
//     畫面上那條線因此改成灰色虛線並附一句話，而不是照常畫。
//   * **第二層：`safetyGain()` 把 |H| 的峰值壓回 1，只衰減不放大。**
//     r = 0.999 的共振是 1000 倍增益。
//
// ⚠️ 第二層有一個必須寫在畫面上的代價：學生聽到的不是「共振變大聲」，
//    是「共振以外的一切變小聲」。兩者是同一個濾波器，差別只在乘上哪一個
//    常數。所以讀數列印出**未經正規化的峰值增益（dB）**——
//    耳朵聽不到的那個數字，眼睛看得到。
// ============================================================================

import { DemoAudio } from './lib/audio.js';
import { createShell, bindNumberPair } from './lib/shell.js';
import { clamp } from './lib/signal.js';
import {
  POLE_ZERO_MAX_RADIUS, filterCoefficients, responseFromCoefficients,
  responseCurve, peakGain, safetyGain, maxPoleRadius, isStable,
  isStableSecondOrder, filterImpulseResponse, halfPowerWidth, decaySamples,
  toDecibels,
} from './lib/transform.js';
import {
  makeScale, makeComplexScale, complexPoint, nearestHandle, curvePoints,
  fitCanvas, clear, strokeAxes, strokePolyline, strokeAxisWithTicks,
  strokeComplexPlane, strokeRadial, markZero, markPole, strokeStems,
  splitOnJumps,
} from './lib/draw.js';

// ---------------------------------------------------------------- 常數

/** 內建範例的目錄。**這是這一頁唯一會被 fetch 的東西**（GET，靜態資產）。 */
const SAMPLE_PREFIX = '/static/demos/samples/';

/**
 * 沒有 AudioContext 時，用來把 ω 換算成赫茲的**宣告過的假設**。
 *
 * ⚠️ 這**不是**寫死取樣率（§8.5 明文禁止）。差別在於它有沒有被說出來：
 * 音訊還沒開始時畫面上明講「以下的赫茲是以 48000 Hz 換算的」，
 * 按下 Start sound 之後就換成 `ctx.sampleRate` 重算。作法與 2S10 相同。
 *
 * ⚠️ **而這一頁比其他頁更需要這句話**：z 平面上的角度是**正規化頻率**，
 * 它本身與赫茲無關。同一個極點在 8 kHz 取樣下是 1 kHz、在 48 kHz 下是
 * 6 kHz——那是 W7 的內容之一，不是一個實作細節。
 */
const PREVIEW_RATE = 48000;

/** 頻率響應曲線的取值點數。夠密到 r = 0.99 的尖峰不會被跳過。 */
const RESPONSE_POINTS = 1400;

/** 衝激響應畫幾格。64 格在 r = 1.02 下成長到 3.6 倍，看得出來但不會爆表。 */
const IMPULSE_COUNT = 64;

/**
 * dB 軸的下限。**固定**，這樣凹口有多深是跨設定可比的。
 *
 * ⚠️ 名字裡的 `AXIS` 不是贅字：`transform.js` 也 export 了一個 `DB_FLOOR`
 * （−120，頻譜展示用的），而這裡是**繪圖的選擇**，不是同一個東西。
 */
const AXIS_DB_FLOOR = -60;

/** 拖曳的命中半徑（像素）。比記號本身大一點，否則很難抓。 */
const GRAB_RADIUS = 18;

/** 方向鍵一次動多少。半徑用等差、角度用 π 的等分。 */
const KEY_RADIUS_STEP = 0.01;
const KEY_ANGLE_STEP = Math.PI / 100;

const PLANE_PAD = { left: 34, right: 34, top: 16, bottom: 16 };
const CURVE_PAD = { left: 62, right: 14, top: 14, bottom: 26 };
const STEM_PAD = { left: 62, right: 14, top: 14, bottom: 26 };

// 線型與顏色並用（§8.6 第 4 點：顏色不得是唯一的訊息載體）。
// 零點是空心圓、極點是叉——那是全世界課本共用的慣例，換成兩個顏色不同的
// 圓點會同時失去無障礙與「這就是課本上那張圖」兩件事。
const STYLE = {
  axis: '#c7ccd4',
  axisText: '#6b7280',
  circle: '#111827',
  zero: '#1f4fd8',
  pole: '#c2410c',
  response: { color: '#1f4fd8', width: 2.2, dash: [] },
  unusable: { color: '#94a3b8', width: 1.8, dash: [6, 4] },
  phase: { color: '#1f4fd8', width: 1.8, dash: [] },
  stem: '#1f4fd8',
  marker: '#94a3b8',
};

/**
 * 音源。三個都是 2S4 就已經進版控的檔案（D29），**這一頁零新增資產**。
 *
 * 白雜訊排第一是刻意的：它在每一個頻率上都有能量，所以「某個頻率被挖掉」
 * 與「某個頻率被抬起來」兩件事在它身上都聽得見。單一樂音聽不出凹口
 * （凹口沒有東西可以挖），而語音只有在共振很尖的時候才明顯。
 */
const SOURCES = {
  noise: { file: 'noise-white.wav', label: 'White noise' },
  sawtooth: { file: 'sawtooth-220.wav', label: 'Sawtooth at 220 Hz' },
  speech: { file: 'speech-welcome.wav', label: 'A synthesised voice' },
};

/**
 * 預設按鈕（§8.6 第 6 點）。
 *
 * ⚠️ 這一組**不是便利功能，是無障礙的兌現**。§8.6 第 6 點誠實地寫著
 * 「一個即時拖曳的極零點平面沒有辦法對全盲學生做到完全等價」，
 * 而緩解就是這裡：不必拖曳也走得完整條教學路徑，而**那條路徑的 payoff
 * 是聲音，他拿得到**。所以每一個按鈕都對應教材上的一站，不是隨機的樣本。
 */
const PRESETS = {
  'preset-notch': { zero: { r: 1, theta: 0.5 * Math.PI }, pole: { r: 0.5, theta: 0.5 * Math.PI }, usePoles: true },
  'preset-resonator': { zero: { r: 0, theta: 0 }, pole: { r: 0.99, theta: 0.12 * Math.PI }, usePoles: true },
  'preset-fir': { zero: { r: 1, theta: Math.PI }, pole: { r: 0, theta: 0 }, usePoles: false },
  'preset-unstable': { zero: { r: 0, theta: 0 }, pole: { r: 1.02, theta: 0.25 * Math.PI }, usePoles: true },
};

// ---------------------------------------------------------------- 狀態

const state = {
  zero: { r: 1, theta: 0.55 * Math.PI },
  pole: { r: 0.9, theta: 0.15 * Math.PI },
  usePoles: true,
  source: 'noise',
  listen: 'filtered',
  selected: 'pole',           // 鍵盤與方向鍵動的是哪一個
  running: false,
  deviceRate: null,
};

// ---------------------------------------------------------------- DOM

const root = document.querySelector('.demo-layout');
const usePolesBox = document.getElementById('use-poles');
const sourceSelect = document.getElementById('source');
const listenSelect = document.getElementById('listen');
const selectedSelect = document.getElementById('selected');
const planeCanvas = document.getElementById('plane-canvas');
const magnitudeCanvas = document.getElementById('magnitude-canvas');
const phaseCanvas = document.getElementById('phase-canvas');
const impulseCanvas = document.getElementById('impulse-canvas');
const planeDescription = document.getElementById('plane-description');
const magnitudeDescription = document.getElementById('magnitude-description');
const phaseDescription = document.getElementById('phase-description');
const impulseDescription = document.getElementById('impulse-description');
const equation = document.getElementById('equation');
const outStability = document.getElementById('out-stability');
const outPeak = document.getElementById('out-peak');
const outNotch = document.getElementById('out-notch');
const outBandwidth = document.getElementById('out-bandwidth');
const outDecay = document.getElementById('out-decay');
const outScale = document.getElementById('out-scale');
const outNumerator = document.getElementById('out-numerator');
const outDenominator = document.getElementById('out-denominator');
const outKind = document.getElementById('out-kind');
const verdict = document.getElementById('verdict');
const rateNote = document.getElementById('rate-note');
const poleFields = document.getElementById('pole-fields');

// ---------------------------------------------------------------- 模型

/** 目前該用哪個取樣率換算赫茲。沒有音訊時是宣告過的假設，見 PREVIEW_RATE。 */
function analysisRate() {
  return state.deviceRate || PREVIEW_RATE;
}

/** ω（rad/sample）→ Hz。整條「角度就是頻率」的換算只有這一行。 */
function toHertz(omega) {
  return (omega * analysisRate()) / (2 * Math.PI);
}

/** 目前的極零點集合。FIR 模式下極點那一串是空的。 */
function pairs() {
  return {
    zeros: [{ ...state.zero }],
    poles: state.usePoles ? [{ ...state.pole }] : [],
  };
}

/**
 * 一次算完這一格畫面要的所有東西。
 *
 * ⚠️ 這裡算**兩組係數**：`raw`（增益 1，畫面上與課本對得起來的那一組）
 * 與 `safe`（乘上安全增益，真的送進 worklet 的那一組）。兩組都留著是
 * 刻意的——畫面顯示的是前者，聲音用的是後者，而**兩者的比值就是
 * 那個「耳朵聽不到的數字」**，它印在讀數列上。
 */
function model() {
  const shape = pairs();
  const raw = filterCoefficients({ ...shape, gain: 1 });
  const stable = isStable(shape.poles);
  const peak = peakGain(raw.b, raw.a);
  const gain = stable ? safetyGain(raw.b, raw.a) : 0;
  const safe = filterCoefficients({ ...shape, gain });

  const omegas = new Float64Array(RESPONSE_POINTS);
  for (let i = 0; i < RESPONSE_POINTS; i += 1) {
    omegas[i] = (Math.PI * i) / (RESPONSE_POINTS - 1);
  }
  const curve = responseCurve(raw.b, raw.a, omegas);
  const impulse = filterImpulseResponse(raw.b, raw.a, IMPULSE_COUNT);

  let impulsePeak = 0;
  let impulsePeakAt = 0;
  for (let i = 0; i < impulse.length; i += 1) {
    if (Math.abs(impulse[i]) > impulsePeak) {
      impulsePeak = Math.abs(impulse[i]);
      impulsePeakAt = i;
    }
  }

  return {
    shape, raw, safe, gain, stable, peak, omegas, curve, impulse,
    impulsePeak, impulsePeakAt,
    maxPole: maxPoleRadius(shape.poles),
    // 零點的角度上 |H| 有多低：那就是凹口的深度，而它是這一頁最容易
    // 用耳朵確認的一個數字。
    notch: responseFromCoefficients(raw.b, raw.a, state.zero.theta).magnitude,
    width: state.usePoles
      ? halfPowerWidth(raw.b, raw.a, peak.omega)
      : null,
    decay: state.usePoles ? decaySamples(state.pole.r) : 0,
  };
}

// ---------------------------------------------------------------- 音訊

let playGain = null;
let filterNode = null;
let currentNode = null;
const buffers = new Map();          // 解碼過一次就留著
let lastSent = '';

const audio = new DemoAudio({
  workletModules: ['/static/demos/worklets/polezero-processor.js'],
  onFailure: (kind, message) => {
    shell.showMessage(message, 'error');
    shell.setRunning(false);
    state.running = false;
    shell.scheduleRender();
  },
  onStateChange: (running, reason) => {
    state.running = running;
    shell.setRunning(running);
    shell.setSampleRate(running ? audio.sampleRate : null);
    if (!running) {
      state.deviceRate = null;
      lastSent = '';
      disposeSource();
    }
    if (!running && reason === 'hidden') {
      shell.showMessage(
        'Sound stopped because you left this tab. Press Start sound to '
        + 'continue.', 'notice',
      );
    }
    shell.scheduleRender();
  },
});

/** 拆掉目前的音源。**一定要 disconnect**，否則就是 §8.2 說的孤兒節點。 */
function disposeSource() {
  if (!currentNode) return;
  try {
    currentNode.stop();
  } catch (err) {
    // 已經停過的節點再 stop 會丟 InvalidStateError；不是錯誤，但按規則 4
    // 仍然留一行，免得日後有別的原因掉進這裡而沒有人知道。
    console.warn('[polezero] stopping the previous source node:', err);
  }
  currentNode.disconnect();
  currentNode = null;
}

function ensureGraph() {
  if (playGain) return;
  playGain = audio.ctx.createGain();
  playGain.gain.value = 1;
  playGain.connect(audio.master);

  filterNode = new AudioWorkletNode(audio.ctx, 'pole-zero-filter');
  filterNode.connect(playGain);
  // 第三層防護的回報路徑。**收到就停，並且說出來**（規則 4）。
  filterNode.port.onmessage = (event) => {
    if ((event.data || {}).type !== 'overload') return;
    audio.stop('overload');
    shell.showMessage(
      'The filter output ran away and the sound was stopped by a safety check '
      + 'inside the audio thread. This should not happen while the poles are '
      + 'inside the unit circle, so please tell your instructor what you had '
      + 'set when it happened.', 'error',
    );
  };
}

async function loadSample(name) {
  if (buffers.has(name)) return buffers.get(name);
  // ⛔ 這是這一頁唯一的 fetch：GET 一個靜態資產。沒有 method、沒有 body。
  const response = await fetch(SAMPLE_PREFIX + SOURCES[name].file);
  if (!response.ok) throw new Error(`sample responded with ${response.status}`);
  const decoded = await audio.ctx.decodeAudioData(await response.arrayBuffer());
  buffers.set(name, decoded);
  return decoded;
}

/**
 * 把係數送進 worklet。
 *
 * ⚠️ **不穩定的時候什麼都不送，而是停止音訊。** 送一組會發散的係數過去，
 * 靠 worklet 的看守接住它，在技術上也行得通——但那會讓「第三層」變成
 * 日常路徑，而它存在的意義正是「日常路徑不該走到這裡」。
 */
function pushCoefficients(data) {
  if (!filterNode || !state.running) return;
  if (!data.stable) {
    audio.stop('unstable');
    shell.showMessage(
      'Sound stopped: a pole is on or outside the unit circle, so this filter '
      + 'does not settle. Bring the pole radius back below 1 and press Start '
      + 'sound again. The graphs below keep working, and the one showing the '
      + 'impulse response is worth a look while you are here.', 'warning',
    );
    return;
  }
  // 「聽原始訊號」＝把濾波器設成一個常數，**而且是同一個常數**。
  // 兩邊乘上同一個數字，A/B 的差別才只剩下濾波器的形狀。
  const send = state.listen === 'filtered'
    ? { b: Array.from(data.safe.b), a: Array.from(data.safe.a) }
    : { b: [data.gain], a: [1] };
  const key = JSON.stringify(send);
  if (key === lastSent) return;         // 沒變就不送，省下每格一次 postMessage
  lastSent = key;
  filterNode.port.postMessage({ type: 'coefficients', ...send });
}

async function startSource() {
  ensureGraph();
  let buffer;
  try {
    buffer = await loadSample(state.source);
  } catch (err) {
    console.error('[polezero] loading the sample failed:', err);
    shell.showMessage(
      `The sound sample "${SOURCES[state.source].label}" could not be loaded, `
      + 'so there is nothing to filter. The graphs below still work. Reload the '
      + 'page, and tell your instructor if it keeps happening.', 'error',
    );
    return false;
  }
  disposeSource();
  const node = audio.ctx.createBufferSource();
  node.buffer = buffer;
  node.loop = true;
  node.connect(filterNode);
  node.start();
  currentNode = node;
  return true;
}

async function toggleSound() {
  if (state.running) {
    audio.stop();
    return;
  }
  shell.clearMessage();
  // 第一層防護，**在開始之前**：不穩定就根本不啟動（§8.4 的「穩定性前置檢查」）。
  if (!isStable(pairs().poles)) {
    shell.showMessage(
      'Sound is not available with a pole on or outside the unit circle: the '
      + 'output of that filter grows without limit. Reduce the pole radius '
      + 'below 1 and try again.', 'warning',
    );
    return;
  }
  const ok = await audio.start();
  if (!ok) return;                 // 失敗訊息已經由 onFailure 放上畫面了
  state.deviceRate = audio.sampleRate;
  if (!await startSource()) {
    audio.stop();
    return;
  }
  lastSent = '';
  pushCoefficients(model());
  shell.scheduleRender();
}

// ---------------------------------------------------------------- 文字

const hz = (v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(2)} kHz` : `${v.toFixed(0)} Hz`);
const piUnits = (omega) => `${(omega / Math.PI).toFixed(3)}π`;

/**
 * 固定小數位，而且**不印出「負零」**。
 *
 * `(-1e-17).toFixed(3)` 是 `"-0.000"`，讀起來像「有一點點，而且是負的」。
 * 這一頁到處都在報恰好抵消的係數（θ = π/2 時 b₁ 就是 0），
 * 2S10 與 2S11 各記過一次，這是第三個實例。
 */
function fixed(v, digits = 3) {
  const text = v.toFixed(digits);
  return text === `-${(0).toFixed(digits)}` ? (0).toFixed(digits) : text;
}

/**
 * dB，**而且說出來什麼時候是地板而不是量測值**。
 *
 * ⚠️ 零點落在單位圓上時 |H| 在那個角度上解析地等於 0，浮點算出來是 1e−16，
 * 換算是 −320 dB，夾到軸的下限之後印出 `-60.0 dB`——**那讀起來像一個
 * 量到的數字，而它是一個夾子**。這一頁整頁在教「零點落在圓上就是完全
 * 挖掉」，印一個有限的數字正好否定了那句話。
 * 這是 2S10「Σ|h| 的讀數落在梳齒頂上」那一類的第三個實例：
 * 數字沒有錯，但它回答了另一個問題。
 */
function decibels(magnitude) {
  const db = toDecibels(magnitude, AXIS_DB_FLOOR);
  if (db <= AXIS_DB_FLOOR) return `below ${AXIS_DB_FLOOR} dB`;
  return `${db.toFixed(1)} dB`;
}

/** 毫秒，位數跟著大小走。`toFixed(1)` 對 0.029 ms 會印出一個沒有內容的 0.0。 */
function millis(seconds) {
  return `${(seconds * 1000).toPrecision(2)} ms`;
}

/**
 * 差分方程，寫成學生在課本上看到的那一行。
 *
 * ⚠️ 刻意用純文字而不是 KaTeX。三個理由：這一行每一格畫面都會變，
 * 而 KaTeX 每次重排一個式子並不便宜；螢幕閱讀器唸得出這一行，
 * 唸不出 KaTeX 生出來的那一堆 span；而且它與讀數列的其餘部分
 * **是同一種東西**——一個會動的數字，不是一段排版好的數學。
 */
function equationText(data) {
  const { b, a } = data.raw;
  const term = (coefficient, name, first) => {
    const sign = coefficient < 0 ? '−' : '+';
    const magnitude = fixed(Math.abs(coefficient));
    if (first) return `${coefficient < 0 ? '−' : ''}${magnitude} ${name}`;
    return ` ${sign} ${magnitude} ${name}`;
  };
  const parts = [];
  for (let k = 0; k < b.length; k += 1) {
    const name = k === 0 ? 'x[n]' : `x[n−${k}]`;
    parts.push(term(b[k], name, parts.length === 0));
  }
  // ⚠️ 差分方程裡 a 那一側的符號是**反過來的**：
  // A(z)Y = B(z)X ⟹ y[n] = Σb·x[n−k] − Σa·y[n−k]。
  // 這個負號是這一段唯一會被寫錯的地方，而寫錯的結果是一個仍然穩定、
  // 仍然畫得出漂亮曲線、只是共振跑到別處的濾波器。
  for (let k = 1; k < a.length; k += 1) {
    parts.push(term(-a[k], `y[n−${k}]`, false));
  }
  return `y[n] = ${parts.join('')}`;
}

function coefficientText(values) {
  return values.map((v, i) => `${i}: ${fixed(v, 4)}`).join('   ');
}

/** 一句給螢幕閱讀器的狀態播報（§8.6 第 2 點）。 */
function statusSentence(data) {
  const parts = [
    `Zero pair at radius ${fixed(state.zero.r, 2)}, angle ${piUnits(state.zero.theta)}, `
    + `which is ${hz(toHertz(state.zero.theta))}.`,
  ];
  if (state.usePoles) {
    parts.push(`Pole pair at radius ${fixed(state.pole.r, 3)}, angle `
      + `${piUnits(state.pole.theta)}, which is ${hz(toHertz(state.pole.theta))}.`);
  } else {
    parts.push('No poles: this is an FIR filter.');
  }
  parts.push(data.stable
    ? `Stable. Peak gain ${decibels(data.peak.magnitude)}.`
    : 'Not stable: a pole is on or outside the unit circle.');
  return parts.join(' ');
}

/** Canvas 的文字替代是**算出來的**，不是靜態 alt（§8.6 第 3 點）。 */
function describePlane() {
  const parts = [
    'The complex z plane with the unit circle drawn on it. A pair of zeros, '
    + `drawn as circles, sits at radius ${fixed(state.zero.r, 2)} and angle plus `
    + `and minus ${piUnits(state.zero.theta)}.`,
  ];
  if (state.usePoles) {
    parts.push('A pair of poles, drawn as crosses, sits at radius '
      + `${fixed(state.pole.r, 3)} and angle plus and minus `
      + `${piUnits(state.pole.theta)}, which is `
      + `${state.pole.r < 1 ? 'inside' : (state.pole.r > 1 ? 'outside' : 'exactly on')} `
      + 'the unit circle.');
  } else {
    parts.push('Both poles are at the origin, so the filter has no feedback.');
  }
  parts.push('Each pair is symmetric about the real axis, which is what keeps '
    + 'the difference equation real.');
  return parts.join(' ');
}

function describeMagnitude(data) {
  if (!data.stable) {
    return 'The magnitude of H on the unit circle, drawn as a grey dashed line '
      + 'because it is not the frequency response of anything that runs: with a '
      + 'pole at radius '
      + `${fixed(data.maxPole, 3)} the region of convergence of the causal system `
      + 'is everything outside that radius, and the unit circle is not in it.';
  }
  const parts = [
    'The magnitude of the frequency response in decibels, from zero to the '
    + `Nyquist frequency. It is loudest at ${piUnits(data.peak.omega)}, which is `
    + `${hz(toHertz(data.peak.omega))}, where it reaches `
    + `${decibels(data.peak.magnitude)}.`,
  ];
  parts.push(`At the angle of the zeros, ${piUnits(state.zero.theta)}, it drops to `
    + `${decibels(data.notch)}.`);
  if (data.width !== null) {
    parts.push(`The peak is ${piUnits(data.width)} wide at the half-power points.`);
  }
  return parts.join(' ');
}

function describePhase() {
  return 'The phase of H on the unit circle, wrapped into plus or minus 180 '
    + 'degrees. It turns most quickly near the angle of the poles, and jumps by '
    + '180 degrees where the magnitude passes through a zero.';
}

function describeImpulse(data) {
  const kind = state.usePoles ? 'infinite' : 'finite';
  const parts = [
    `The impulse response, the first ${IMPULSE_COUNT} samples of what comes out `
    + `when a single 1 goes in. It is ${kind} in length.`,
  ];
  if (!state.usePoles) {
    parts.push(`Every sample after n equals ${data.raw.b.length - 1} is exactly `
      + 'zero, because there is nothing feeding the output back in.');
  } else if (data.stable) {
    parts.push('It rings and dies away, falling by a factor of e every '
      + `${data.decay.toFixed(1)} samples. The largest sample is at n equals `
      + `${data.impulsePeakAt}.`);
  } else {
    parts.push('It grows instead of dying away: the largest sample in this '
      + `window is the one at n equals ${data.impulsePeakAt}, near the right-hand `
      + 'edge, and it keeps going past the edge of the picture.');
  }
  return parts.join(' ');
}

/**
 * 這一頁的「判決句」。**它不先講結論**（規則 5 的分寸）——它報告學生剛剛
 * 做出來的那個設定處在什麼狀態，結論留在 <details> 裡。
 */
function verdictSentence(data) {
  if (!data.stable) {
    return `The poles are at radius ${fixed(data.maxPole, 3)}, which is not less `
      + 'than 1. The impulse response below is the thing to look at.';
  }
  const bits = [];
  if (state.usePoles) {
    bits.push(`Poles at radius ${fixed(state.pole.r, 3)}, zeros at radius `
      + `${fixed(state.zero.r, 2)}. Peak gain ${decibels(data.peak.magnitude)} at `
      + `${hz(toHertz(data.peak.omega))}, and ${decibels(data.notch)} at `
      + `${hz(toHertz(state.zero.theta))}.`);
  } else {
    bits.push(`Zeros at radius ${fixed(state.zero.r, 2)}, no poles. The impulse `
      + `response is ${data.raw.b.length} samples long and then exactly zero.`);
  }
  return bits.join(' ');
}

// ---------------------------------------------------------------- 拖曳的把手

/**
 * 目前畫面上可以抓的四個記號（共軛對各兩個）。
 *
 * ⚠️ **共軛的那一個也是把手**，這不是多做的：學生抓下半平面那一個往下拖，
 * 它就該往下走。反過來（下面那個只是一個唯讀的鏡像）會讓「共軛對是
 * 一起動的」變成一句需要解釋的話，而不是一件試出來的事。
 * 抓住哪一個就記下它的正負號，角度照那個號存回去。
 */
function handles(scale) {
  const list = [];
  for (const sign of [1, -1]) {
    const { r, theta } = state.zero;
    const point = complexPoint(scale, r * Math.cos(sign * theta), r * Math.sin(sign * theta));
    list.push({ kind: 'zero', sign, ...point });
  }
  if (state.usePoles) {
    for (const sign of [1, -1]) {
      const { r, theta } = state.pole;
      const point = complexPoint(scale, r * Math.cos(sign * theta), r * Math.sin(sign * theta));
      list.push({ kind: 'pole', sign, ...point });
    }
  }
  return list;
}

function planeScale() {
  const rect = planeCanvas.getBoundingClientRect();
  return makeComplexScale({
    span: 1.35,
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
    pad: PLANE_PAD,
  });
}

let dragging = null;

function pointerPosition(event) {
  const rect = planeCanvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

/**
 * 把一個值對齊到對應那支滑桿的 `step`。
 *
 * ⚠️ **這不是為了好看，是為了讓「畫面上的數字」只有一個。** 拖曳給出的是
 * 連續的值，而 `<input type="range">` 在瀏覽器裡會把寫進去的值**吸到最近
 * 的 step 上**（那是 HTML 的值淨化規則，不是我們寫的）——不先對齊的話，
 * 拖完之後 `state` 是 0.765593、滑桿是 0.766、數字框是 0.765593，
 * 三個地方三個數字。那正是 §8.2.3 那條「DOM 不是真相的來源」要擋的東西，
 * 只是這一次是反過來的方向。
 *
 * step 從 DOM 讀而不是寫死在這裡，因為它本來就寫在範本上；
 * 抄一份到 JS 就會有兩份會漂移的設定。
 */
function quantise(kind, field, value) {
  const control = document.getElementById(`${kind}-${field}`);
  const step = Number(control && control.step);
  if (!(step > 0)) return value;
  return Math.round(value / step) * step;
}

/** 半徑與角度的上下限。角度只存 [0, π]，下半平面靠共軛得到。 */
function setPair(kind, r, theta) {
  const limit = kind === 'pole' ? POLE_ZERO_MAX_RADIUS : 1.5;
  state[kind].r = quantise(kind, 'radius', clamp(r, 0, limit));
  // 角度的滑桿單位是 π，所以對齊也在 π 的單位上做。
  state[kind].theta = quantise(kind, 'angle', clamp(theta, 0, Math.PI) / Math.PI) * Math.PI;
  syncInputs();
  scheduleSoundUpdate();
  shell.scheduleRender();
}

function onPointerDown(event) {
  const scale = planeScale();
  const point = pointerPosition(event);
  const hit = nearestHandle(handles(scale), point, GRAB_RADIUS);
  if (!hit) return;
  event.preventDefault();
  dragging = hit.handle;
  state.selected = hit.handle.kind;
  if (selectedSelect.value !== state.selected) selectedSelect.value = state.selected;
  if (planeCanvas.setPointerCapture && event.pointerId !== undefined) {
    planeCanvas.setPointerCapture(event.pointerId);
  }
  moveTo(event);
}

function moveTo(event) {
  if (!dragging) return;
  const scale = planeScale();
  const point = pointerPosition(event);
  const z = scale.at(point.x, point.y);
  const r = Math.hypot(z.re, z.im);
  // 抓住的是哪一個成員，角度就照那個成員的方向走——存回去的永遠是
  // 上半平面的那個角度（見 `handles()`）。
  const theta = Math.abs(Math.atan2(z.im * dragging.sign, z.re));
  setPair(dragging.kind, r, theta);
}

function onPointerUp(event) {
  if (!dragging) return;
  dragging = null;
  if (planeCanvas.releasePointerCapture && event.pointerId !== undefined) {
    try {
      planeCanvas.releasePointerCapture(event.pointerId);
    } catch (err) {
      // 指標已經離開時放開一個沒有捕捉到的 id 會丟 NotFoundError。
      // 不是錯誤，但按規則 4 仍然留一行。
      console.warn('[polezero] releasing the pointer capture:', err);
    }
  }
}

/**
 * 鍵盤替代（§8.6 第 1 點，而這一頁是它最重要的一次）。
 *
 * 這一頁的核心互動是拖曳，所以鍵盤這條路**不是補丁，是第二條完整的路**：
 *   * 左右鍵改角度、上下鍵改半徑，一次一小格（按住 Shift 是十格）
 *   * `Z` 與 `P` 在兩個共軛對之間切換
 * 再加上旁邊四組滑桿與數字框、以及那一排預設按鈕，
 * 整條教學路徑不必碰滑鼠就走得完。
 */
function onPlaneKeyDown(event) {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key;
  if (key === 'z' || key === 'Z' || key === 'p' || key === 'P') {
    const next = (key === 'z' || key === 'Z') ? 'zero' : 'pole';
    if (next === 'pole' && !state.usePoles) return;
    event.preventDefault();
    state.selected = next;
    selectedSelect.value = next;
    shell.scheduleRender();
    return;
  }
  const steps = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowDown: [-1, 0], ArrowUp: [1, 0] };
  const step = steps[key];
  if (!step) return;
  event.preventDefault();
  const kind = (state.selected === 'pole' && state.usePoles) ? 'pole' : 'zero';
  const scale = event.shiftKey ? 10 : 1;
  setPair(
    kind,
    state[kind].r + step[0] * KEY_RADIUS_STEP * scale,
    state[kind].theta + step[1] * KEY_ANGLE_STEP * scale,
  );
}

// ---------------------------------------------------------------- 繪製

function drawPlane(data) {
  const { width, height, ctx } = fitCanvas(planeCanvas, window.devicePixelRatio || 1);
  const scale = makeComplexScale({ span: 1.35, width, height, pad: PLANE_PAD });

  clear(ctx, width, height);
  strokeComplexPlane(ctx, scale, STYLE);

  // 角度 → 頻率的兩條細線。它們是「拖著轉的那個角度」與「響應圖上動的
  // 那一段」之間的連線，沒有它們兩張圖看起來是各自獨立的。
  strokeRadial(ctx, scale, state.zero.theta, { color: STYLE.zero });
  if (state.usePoles) strokeRadial(ctx, scale, state.pole.theta, { color: STYLE.pole });

  for (const handle of handles(scale)) {
    const selected = handle.kind === state.selected;
    const options = { color: handle.kind === 'zero' ? STYLE.zero : STYLE.pole, selected };
    if (handle.kind === 'zero') markZero(ctx, handle, options);
    else markPole(ctx, handle, options);
  }

  if (!data.stable) {
    // 不穩定時把單位圓外圍那一句話畫出來——不是裝飾，是這一頁的內容。
    ctx.save();
    ctx.fillStyle = STYLE.pole;
    ctx.font = '12px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('pole outside the unit circle', PLANE_PAD.left, PLANE_PAD.top);
    ctx.restore();
  }
}

/**
 * dB 軸的上限走一個**階梯**（0, 20, 40, 60…），不連續地跟著峰值跑。
 *
 * 2S11 記過「軸跟著資料縮放會把整頁內容刪掉」。這一頁的處境不同——
 * 峰值增益跨越 60 dB，軸完全固定的話 r = 0.5 那一帶會是一條貼在中間
 * 的直線——所以折衷是**讓上限跳格而不是連續移動**：拖滑桿的時候軸
 * 大部分時間不動，而動的時候是一次一格，看得出來它動了。
 * ⚠️ 下限是**固定的 −60 dB**，沒有例外：凹口有多深必須是跨設定可比的。
 */
function decibelCeiling(peak) {
  const db = toDecibels(peak, AXIS_DB_FLOOR);
  return Math.max(20, Math.ceil((db + 6) / 20) * 20);
}

function drawMagnitude(data) {
  const { width, height, ctx } = fitCanvas(magnitudeCanvas, window.devicePixelRatio || 1);
  const top = decibelCeiling(data.peak.magnitude);
  const scale = makeScale({
    t0: 0, t1: Math.PI, vMin: AXIS_DB_FLOOR, vMax: top,
    width, height, pad: CURVE_PAD,
  });

  clear(ctx, width, height);

  const db = new Float64Array(data.curve.magnitude.length);
  for (let i = 0; i < db.length; i += 1) {
    db[i] = toDecibels(data.curve.magnitude[i], AXIS_DB_FLOOR);
  }
  strokePolyline(
    ctx, curvePoints(scale, data.omegas, db),
    data.stable ? STYLE.response : STYLE.unusable,
  );

  const ticks = [0, Math.PI / 4, Math.PI / 2, (3 * Math.PI) / 4, Math.PI];
  strokeAxisWithTicks(ctx, scale, ticks, (v) => piUnits(v), STYLE);
}

function drawPhase(data) {
  const { width, height, ctx } = fitCanvas(phaseCanvas, window.devicePixelRatio || 1);
  const scale = makeScale({
    t0: 0, t1: Math.PI, vMin: -Math.PI, vMax: Math.PI,
    width, height, pad: CURVE_PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  // 相位繞回來的地方要切開，否則每一次繞過 ±π 都會畫出一條假的垂直線。
  const points = curvePoints(scale, data.omegas, data.curve.phase);
  const maxRise = Math.abs(scale.y(0) - scale.y(Math.PI));
  for (const segment of splitOnJumps(points, maxRise)) {
    strokePolyline(ctx, segment, data.stable ? STYLE.phase : STYLE.unusable);
  }

  const ticks = [0, Math.PI / 4, Math.PI / 2, (3 * Math.PI) / 4, Math.PI];
  strokeAxisWithTicks(ctx, scale, ticks, (v) => piUnits(v), STYLE);
}

function drawImpulse(data) {
  const { width, height, ctx } = fitCanvas(impulseCanvas, window.devicePixelRatio || 1);
  // ⚠️ 縱軸跟著這一段的峰值走，而**不穩定時峰值在最右邊**——於是左邊那些
  // 早期的樣本被壓平。那不是一個顯示瑕疵：那正是「發散」在一張固定寬度
  // 的圖上的樣子，而文字替代與讀數都明講峰值落在第幾格。
  const top = Math.max(1e-6, data.impulsePeak) * 1.15;
  const scale = makeScale({
    t0: -0.5, t1: IMPULSE_COUNT - 0.5, vMin: -top, vMax: top,
    width, height, pad: STEM_PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  const times = new Float64Array(IMPULSE_COUNT);
  for (let i = 0; i < IMPULSE_COUNT; i += 1) times[i] = i;
  strokeStems(
    ctx, curvePoints(scale, times, data.impulse), scale.y(0),
    { color: STYLE.stem, radius: 2.5 },
  );

  const ticks = [0, 16, 32, 48, 64].filter((v) => v <= IMPULSE_COUNT);
  strokeAxisWithTicks(ctx, scale, ticks, (v) => `n = ${v}`, STYLE);
}

// ---------------------------------------------------------------- render

function render() {
  const data = model();

  drawPlane(data);
  drawMagnitude(data);
  drawPhase(data);
  drawImpulse(data);

  equation.textContent = equationText(data);
  outNumerator.textContent = coefficientText(Array.from(data.raw.b));
  outDenominator.textContent = coefficientText(Array.from(data.raw.a));
  outKind.textContent = state.usePoles
    ? `IIR, order ${data.raw.a.length - 1}: the output feeds back`
    : `FIR, order ${data.raw.b.length - 1}: no feedback at all`;
  outStability.textContent = data.stable
    ? `stable: the poles are at radius ${fixed(data.maxPole, 3)}, inside the circle`
    : `not stable: a pole sits at radius ${fixed(data.maxPole, 3)}`;
  outPeak.textContent = data.stable
    ? `${decibels(data.peak.magnitude)} at ${piUnits(data.peak.omega)}, `
      + `which is ${hz(toHertz(data.peak.omega))}`
    : 'not meaningful while a pole is outside the circle';
  outNotch.textContent = `${decibels(data.notch)} at ${piUnits(state.zero.theta)}, `
    + `which is ${hz(toHertz(state.zero.theta))}`;
  // ⚠️ 量到的與課本那個近似式**並排**印出來。近似式只在 r → 1 時才準，
  // 而這一頁的滑桿從 r = 0 開始；把兩個數字放在一起，「近似」兩個字就是
  // 一個讀得出來的量，不是一句免責聲明（與 2S11 的積分誤差同一個作法）。
  outBandwidth.textContent = data.width === null
    ? 'the largest gain is at an end of the axis, so it has no two-sided width'
    : `${piUnits(data.width)} measured, against ${piUnits(2 * (1 - state.pole.r))} `
      + 'from the usual approximation';
  outDecay.textContent = !state.usePoles
    ? 'no feedback, so nothing rings'
    : (Number.isFinite(data.decay)
      ? `${data.decay.toFixed(1)} samples, which is `
        + `${millis(data.decay / analysisRate())}`
      : 'it never dies away');
  outScale.textContent = data.stable
    ? `× ${data.gain.toExponential(2)} before it reaches the speakers`
    : 'muted';

  rateNote.textContent = state.running
    ? `Hertz below are from your device's rate of ${Math.round(analysisRate())} Hz.`
    : `Hertz below assume ${PREVIEW_RATE} Hz; press Start sound to use your `
      + "device's actual rate.";

  verdict.textContent = verdictSentence(data);
  planeDescription.textContent = describePlane();
  magnitudeDescription.textContent = describeMagnitude(data);
  phaseDescription.textContent = describePhase();
  impulseDescription.textContent = describeImpulse(data);
  shell.announce(statusSentence(data));

  pushCoefficients(data);
}

// ---------------------------------------------------------------- 外框與控制項

const shell = createShell({
  root,
  onToggle: toggleSound,
  onMuteChange: (muted) => audio.setMuted(muted),
  onVolumeChange: (v) => audio.setVolume(v),
});

audio.setVolume(shell.volume);
shell.onRender(render);

/** 連續拖曳時把 postMessage 合併起來。worklet 自己會把係數斜坡過去。 */
let soundTimer = 0;

function scheduleSoundUpdate() {
  if (!state.running) return;
  if (soundTimer) clearTimeout(soundTimer);
  soundTimer = setTimeout(() => {
    soundTimer = 0;
    pushCoefficients(model());
  }, 60);
}

const inputs = {};

/** `syncInputs()` 正在回寫嗎。宣告在這裡是為了避開 TDZ，見下面的說明。 */
let syncing = false;

/**
 * 一組「滑桿 + 數字框」，綁到某個共軛對的半徑或角度上。
 *
 * ⚠️ 角度那兩組的**單位是 π**（滑桿上 0 到 1），不是弧度也不是度。
 * 選 π 的倍數是因為 z 平面上的角度在課本上就是這樣寫的（ω = 0.25π），
 * 而且它讓「一半是 π/2」這件事在滑桿的中點上是看得見的。
 * 赫茲那一欄是**換算出來的讀數**，不是控制項——它取決於取樣率，
 * 而 z 平面不知道取樣率是什麼。
 */
function pairControl(kind, field) {
  const id = `${kind}-${field}`;
  const isRadius = field === 'radius';
  inputs[id] = bindNumberPair({
    range: document.getElementById(id),
    number: document.getElementById(`${id}-number`),
    onChange: (value) => {
      state[kind][isRadius ? 'r' : 'theta'] = isRadius ? value : value * Math.PI;
      // ⚠️ **只有使用者自己動的時候才改「方向鍵動哪一個」。**
      // 拖曳與預設按鈕會呼叫 `syncInputs()` 把四個框全部寫一遍，而
      // `bindNumberPair.set()` 每一次都會走這個 onChange——不擋的話，
      // 最後被寫的那一個（極點角度）就會**永遠**變成被選中的那一個，
      // 於是按 Z 選了零點、方向鍵動的卻是極點。
      // 這是一個不會報錯、只會讓人覺得「這程式很怪」的失敗。
      if (!syncing) {
        state.selected = kind;
        selectedSelect.value = kind;
        scheduleSoundUpdate();
        shell.scheduleRender();
      }
    },
  });
}

pairControl('zero', 'radius');
pairControl('zero', 'angle');
pairControl('pole', 'radius');
pairControl('pole', 'angle');

/**
 * 把 `state` 寫回控制項。**DOM 不是真相的來源**（§8.2.3），這是回寫的方向。
 *
 * 回寫是必要的而不是禮貌：拖曳與預設按鈕改的是 `state`，而數字框是
 * 鍵盤使用者讀值的地方——不同步的話，同一個濾波器在圖上與在框裡
 * 是兩個不同的數字，而**框裡那個還是可以被編輯的**。
 */
function syncInputs() {
  syncing = true;
  inputs['zero-radius'].set(state.zero.r);
  inputs['zero-angle'].set(state.zero.theta / Math.PI);
  inputs['pole-radius'].set(state.pole.r);
  inputs['pole-angle'].set(state.pole.theta / Math.PI);
  syncing = false;
}

usePolesBox.addEventListener('change', () => {
  state.usePoles = usePolesBox.checked;
  poleFields.hidden = !state.usePoles;
  if (!state.usePoles && state.selected === 'pole') {
    state.selected = 'zero';
    selectedSelect.value = 'zero';
  }
  scheduleSoundUpdate();
  shell.scheduleRender();
});

sourceSelect.addEventListener('change', async () => {
  state.source = sourceSelect.value;
  if (state.running) await startSource();
  shell.scheduleRender();
});

listenSelect.addEventListener('change', () => {
  state.listen = listenSelect.value;
  lastSent = '';
  scheduleSoundUpdate();
  shell.scheduleRender();
});

selectedSelect.addEventListener('change', () => {
  state.selected = selectedSelect.value;
  shell.scheduleRender();
});

for (const [id, preset] of Object.entries(PRESETS)) {
  document.getElementById(id).addEventListener('click', () => {
    state.zero = { ...preset.zero };
    state.pole = { ...preset.pole };
    state.usePoles = preset.usePoles;
    usePolesBox.checked = preset.usePoles;
    poleFields.hidden = !preset.usePoles;
    state.selected = preset.usePoles ? 'pole' : 'zero';
    selectedSelect.value = state.selected;
    syncInputs();
    scheduleSoundUpdate();
    shell.scheduleRender();
  });
}

planeCanvas.addEventListener('pointerdown', onPointerDown);
planeCanvas.addEventListener('pointermove', moveTo);
planeCanvas.addEventListener('pointerup', onPointerUp);
planeCanvas.addEventListener('pointercancel', onPointerUp);
planeCanvas.addEventListener('keydown', onPlaneKeyDown);

// ---------------------------------------------------------------- 起始

state.usePoles = usePolesBox.checked;
state.source = sourceSelect.value;
state.listen = listenSelect.value;
state.selected = selectedSelect.value;
state.zero.r = Number(document.getElementById('zero-radius').value);
state.zero.theta = Number(document.getElementById('zero-angle').value) * Math.PI;
state.pole.r = Number(document.getElementById('pole-radius').value);
state.pole.theta = Number(document.getElementById('pole-angle').value) * Math.PI;
poleFields.hidden = !state.usePoles;

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。這一頁沒有聲音仍然有內容（四張圖、係數、
  // 差分方程都在），所以說法與頻譜展示不同——那一頁沒有音訊就沒有內容。
  shell.showMessage(
    'This browser does not support the Web Audio API, so this page cannot play '
    + 'sound. Every graph below still works, and only the part about hearing '
    + 'what a pole does is lost. Try a recent version of Chrome or Firefox on a '
    + 'desktop computer.', 'warning',
  );
  document.querySelector('[data-shell="toggle"]').disabled = true;
}

shell.setSampleRate(null);
shell.scheduleRender();

// 一個給 `isStableSecondOrder()` 的存在理由留下的註腳：這一頁的分母永遠是
// 二階，所以 worklet 的係數內插一定安全。**加第二個極點對之前先讀那一段。**
if (!isStableSecondOrder(filterCoefficients(pairs()).a)) {
  console.warn('[polezero] the starting denominator is not inside the stability triangle');
}
