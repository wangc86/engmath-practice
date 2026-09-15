// 展示 4：摺積與 LTI（PLAN.md §8.2.1 第 4 列，路線圖 2S10；課程 **W2**）。
// ⚠️ v0.42 之前這裡寫的是 W1–W2；老師把它改列在第 2 週（歸類在 curriculum.py，
// 這一行只是註解——⛔ 它沒有任何測試守著，所以改歸類時要記得回來看一眼）。
//
// **這是唯一知道 DOM、AudioContext 與使用者手勢的一層。**
// 這裡不放任何數值演算法——摺積與 LTI 判準在 transform.js、序列與音訊訊號
// 在 signal.js、幾何在 draw.js，因為 `tests/test_dsp_js.py` 只測得到那三層。
//
// 音訊圖（§8.5：能用原生節點就不要自己寫 worklet，這一頁一個都不用）：
//
//   AudioBufferSourceNode ─► playGain ─► master ─► destination
//   （buffer 裡裝的就是 y = x * h，我們自己算出來的那一條）
//
// ⛔ **為什麼不用 `ConvolverNode`**，雖然瀏覽器原生就有一個做這件事的節點：
//
//   1. **它的 `normalize` 預設是 true**，會依 h 的能量把輸出縮放一次。
//      於是「回音加多了，整體變大聲」在耳朵裡消失、而畫面上的 Σ|h| 還在——
//      畫面與聲音對不上，正是 2S5 為了 `disableNormalization` 打過的同一場仗。
//   2. **這一頁的正當性建立在「你聽到的就是畫面上那條 y」。** 交給原生節點
//      算，聽到的東西就離開了 `tests/test_dsp_js.py` 的斷言範圍；自己算，
//      那個 `Float32Array` 逐格都是被測過的東西（§8.4 開頭那句話）。
//
// ⚠️ **無限增益的處理是結構性的，不是靠一個上限值**：這一頁的系統全部是 FIR
// （h 有限長、沒有任何 y[n] 依賴 y[n−D] 的路徑），所以峰值增益就是 Σ|h|，
// 由 `convolutionGainBound()` 算得出來、由 `normaliseResponse()` 壓回 1。
// 滑桿上的 g ≤ 0.95 是**另一件事**：它擋的不是發散（FIR 不會發散），
// 是「後面的回音比前面大聲」這個物理上說不通的形狀。

import { DemoAudio } from './lib/audio.js';
import { createShell, bindNumberPair } from './lib/shell.js';
import {
  RESPONSE_SHAPES, impulseResponse, inputSequence, nonZeroTaps,
  peakAmplitude, mixToMono, clamp,
  ROOMS, roomResponse, measuredRt60, normaliseToRms,
  LTI_A, LTI_B, LTI_PROBE, LTI_SHIFT,
} from './lib/signal.js';
import {
  convolve, fftConvolve, convolutionStep, flippedShiftedResponse,
  reverseSequence, directCurrentGain, bandGain, SYSTEMS, CLIP_LEVEL,
  superpositionCurves, timeInvarianceCurves,
} from './lib/transform.js';
import {
  makeScale, curvePoints, fitCanvas, clear, strokeAxes, strokePolyline,
  strokeAxisWithTicks, strokeStems, markPoint, regionRect, fillRegion,
} from './lib/draw.js';

// ---------------------------------------------------------------- 常數

/** 內建範例的目錄。**這是這一頁唯一會被 fetch 的東西**（GET，靜態資產）。 */
const SAMPLE_PREFIX = '/static/demos/samples/';

/** 語音範例。已經在 2S4 進版控了，這裡直接重用，不新增任何資產。 */
const SPEECH_SAMPLE = 'speech-welcome.wav';

/** 語音只取前面這幾秒。夠聽出殘響，而 FFT 摺積的長度還很舒服。 */
const SPEECH_SECONDS = 3.5;

/** 播出去的訊號一律縮到這個 RMS。**四個房間共用同一個目標**，見 `playSignal()`。 */
const TARGET_RMS = 0.11;

/** 乘積表最多列幾行。再多就不是給人讀的了。 */
const MAX_TERM_ROWS = 12;

/** h 的 tap 少於這個數就畫成棒棒糖，多於就畫成連續曲線（移動平均會很密）。 */
const STEM_LIMIT = 80;

/** 掃描時每幾格畫面推進一個 n。30 fps 除以 3 ≈ 每秒 10 個樣本，跟得上眼睛。 */
const SWEEP_EVERY = 3;

/** 殘差小於這個就當成「恰好是 0」。float64 的加法在這幾個數上沒有捨入。 */
const EXACT = 1e-12;

const PAD = { left: 46, right: 14, top: 16, bottom: 26 };

// 線型與顏色並用（§8.6 第 4 點：顏色不得是唯一的訊息載體）。
const STYLE = {
  axis: '#c7ccd4',
  axisText: '#6b7280',
  input: '#1f4fd8',
  response: '#c2410c',
  product: '#0f766e',
  total: '#111827',
  done: '#1f4fd8',
  pending: '#c7ccd4',
  mark: '#c2410c',
  overlap: 'rgba(31, 79, 216, 0.10)',
  overlapEdge: '#9db4ef',
  together: { color: '#1f4fd8', width: 2.2, dash: [] },
  apart: { color: '#c2410c', width: 1.6, dash: [6, 4] },
  dry: { color: '#6b7280', width: 1.2, dash: [5, 4] },
  wet: { color: '#1f4fd8', width: 1.6, dash: [] },
};

/** `prefers-reduced-motion` 時不自動掃描，改為按鍵推進（§8.6 第 5 點）。 */
const reducedMotion = typeof matchMedia === 'function'
  && matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------------------------------------------------------------- 狀態

const state = {
  inputShape: 'pulse',
  xLength: 4,
  responseShape: 'echo',
  delayTaps: 3,
  lengthTaps: 10,
  gain: 0.6,
  flip: true,
  shift: 4,
  sweeping: false,
  system: 'convolution',
  running: false,
  deviceRate: null,
  room: 'street',
  playing: null,        // 'dry' | 'response' | 'wet'，沒在播是 null
  building: false,      // 正在算摺積（第一次按下去會有幾百毫秒）
};

// ---------------------------------------------------------------- DOM

const root = document.querySelector('.demo-layout');
const inputShapeSelect = document.getElementById('input-shape');
const responseShapeSelect = document.getElementById('response-shape');
const usesHint = document.getElementById('uses-hint');
const flipBox = document.getElementById('flip');
const sweepButton = document.getElementById('sweep');
const shiftRange = document.getElementById('shift');
const shiftNumber = document.getElementById('shift-number');
const roomSelect = document.getElementById('room');
const playDryButton = document.getElementById('play-dry');
const playResponseButton = document.getElementById('play-response');
const playWetButton = document.getElementById('play-wet');
const stopAllButton = document.getElementById('stop-all');
const systemSelect = document.getElementById('lti-system');
const outXLength = document.getElementById('out-x-length');
const outHLength = document.getElementById('out-h-length');
const outYLength = document.getElementById('out-y-length');
const outOverlap = document.getElementById('out-overlap');
const outSum = document.getElementById('out-sum');
const outDc = document.getElementById('out-dc');
const outRt60 = document.getElementById('out-rt60');
const outFirst = document.getElementById('out-first');
const outDirect = document.getElementById('out-direct');
const outTreble = document.getElementById('out-treble');
const outHTaps = document.getElementById('out-h-taps');
const verdict = document.getElementById('verdict');
const audioStatus = document.getElementById('audio-status');
const overlapCanvas = document.getElementById('overlap-canvas');
const productsCanvas = document.getElementById('products-canvas');
const outputCanvas = document.getElementById('output-canvas');
const dryCanvas = document.getElementById('dry-canvas');
const roomCanvas = document.getElementById('room-canvas');
const wetCanvas = document.getElementById('wet-canvas');
const ltiCanvas = document.getElementById('lti-canvas');
const overlapDescription = document.getElementById('overlap-description');
const productsDescription = document.getElementById('products-description');
const outputDescription = document.getElementById('output-description');
const dryDescription = document.getElementById('dry-description');
const roomDescription = document.getElementById('room-description');
const wetDescription = document.getElementById('wet-description');
const ltiDescription = document.getElementById('lti-description');
const termsRows = document.getElementById('terms-rows');
const termsCaption = document.getElementById('terms-caption');
const ltiRows = document.getElementById('lti-rows');
const ltiCaption = document.getElementById('lti-caption');

// ---------------------------------------------------------------- 目前的序列
//
// **每次 render 都重算，不快取。** 它們是幾十個元素的陣列，重算的成本
// 遠低於「多一份可能與 state 不同步的真相」（README 第三條）。

function currentInput() {
  return inputSequence(state.inputShape, { length: state.xLength });
}

/** 離散那一半的 h。單位是「格」。 */
function currentResponse() {
  return impulseResponse(state.responseShape, {
    delay: state.delayTaps,
    length: state.lengthTaps,
    gain: state.gain,
  });
}

/**
 * 真正被滑過去的那一條。
 *
 * 「不翻轉」是把 h 先倒過來再照常翻轉——畫出來就是 h 保持原方向往右滑，
 * 而輸出長度與索引慣例一個字都不用改。理由寫在
 * `transform.js` 的 `flippedShiftedResponse()` 上面。
 */
function slidingResponse() {
  const h = currentResponse();
  return state.flip ? h : reverseSequence(h);
}

function outputLength() {
  return currentInput().length + currentResponse().length - 1;
}

// ---------------------------------------------------------------- 音訊那一側

let playGain = null;
let currentNode = null;
let speechBuffer = null;        // 解碼過一次就留著
let recomputeTimer = 0;

const audio = new DemoAudio({
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
      state.audioTaps = null;
      disposeSource();
    }
    if (!running && reason === 'hidden') {
      shell.showMessage(
        'Sound stopped because you left this tab. Press one of the play '
        + 'buttons to continue.', 'notice',
      );
    }
    shell.scheduleRender();
  },
});

function ensureGraph() {
  if (playGain) return;
  playGain = audio.ctx.createGain();
  playGain.gain.value = 1;
  playGain.connect(audio.master);
}

/** 拆掉目前的音源。**一定要 disconnect**，否則就是 §8.2 說的孤兒節點。 */
function disposeSource() {
  if (!currentNode) return;
  try {
    currentNode.stop();
  } catch (err) {
    // 已經停過的節點再 stop 會丟 InvalidStateError；不是錯誤，
    // 但按規則 4 仍然留一行，免得日後有別的原因掉進這裡而沒有人知道。
    console.warn('[convolution] stopping the previous source node:', err);
  }
  currentNode.disconnect();
  currentNode = null;
}

async function loadSpeech() {
  if (speechBuffer) return speechBuffer;
  // ⛔ 這是這一頁唯一的 fetch：GET 一個靜態資產。沒有 method、沒有 body。
  const response = await fetch(SAMPLE_PREFIX + SPEECH_SAMPLE);
  if (!response.ok) {
    throw new Error(`sample responded with ${response.status}`);
  }
  speechBuffer = await audio.ctx.decodeAudioData(await response.arrayBuffer());
  return speechBuffer;
}

// ⛔ **這一頁沒有 Start sound，所以沒有 `toggleSound()`**（v0.45）。
// 開音訊這件事由三顆播放鍵各自負責（見 `playPart()` 開頭那一段）——
// autoplay 政策要的是一個明確的使用者手勢，而按「Play the voice」就是。
// ⚠️ 舊版另外有一顆 Start sound，它做的事只有「把 AudioContext 打開」，
// 打開之後畫面上什麼都不會發生，於是它變成一顆要人去猜的按鈕。

// ---------------------------------------------------------------- 文字

/**
 * 固定小數位，而且**不印出「負零」**。
 *
 * `(-1e-17).toFixed(3)` 是 `"-0.000"`，而這一頁到處都在報「恰好抵消」的
 * 數字（相鄰相減的直流增益、殘差、空的求和）。一個 `-0.000` 讀起來像
 * 「有一點點，而且是負的」，那正好是它想否定的意思。
 */
function fixed(v, digits = 3) {
  const text = v.toFixed(digits);
  return text === `-${(0).toFixed(digits)}` ? (0).toFixed(digits) : text;
}

const ms = (v) => `${v.toPrecision(3)} ms`;

/**
 * 殘差的顯示。
 *
 * ⚠️ **不寫 "exactly zero"**：通過的那幾格實際上是 1e−16 上下的浮點捨入
 * （`0.45 + 0.4` 在 float64 裡就不是 `0.85`），理由寫在
 * `transform.js` 的 `superpositionResidual()` 上面。這一頁整頁在教
 * 「殘差是一個量，不是一個評語」，寫一個做不到的「恰好」會是唯一的假話。
 */
function residualText(value) {
  return value < EXACT ? '0, to rounding' : fixed(value, 4);
}

function shapeUses(shape) {
  return RESPONSE_SHAPES[shape].uses;
}

/** 「and」串接，兩個以上加逗號。文法錯的句子會讓人懷疑數字。 */
function listWords(words) {
  if (words.length <= 1) return words.join('');
  if (words.length === 2) return `${words[0]} and ${words[1]}`;
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

function usesSentence() {
  const uses = shapeUses(state.responseShape);
  const names = { delay: 'D', length: 'L', gain: 'g' };
  const idle = ['delay', 'length', 'gain'].filter((key) => !uses.includes(key));
  const idleWords = idle.map((key) => names[key]);
  const tail = idle.length === 0
    ? ''
    : ` ${listWords(idleWords)} ${idle.length === 1 ? 'does' : 'do'} nothing right now.`;
  if (uses.length === 0) return `This shape has no parameters.${tail}`;
  return `This shape uses ${listWords(uses.map((key) => names[key]))}.${tail}`;
}

/** 一句給螢幕閱讀器的狀態播報（§8.6 第 2 點）。 */
function statusSentence(step, y) {
  return `Input of ${currentInput().length} samples, impulse response of `
    + `${currentResponse().length} samples, output of ${y.length}. At shift `
    + `${state.shift}, ${step.overlap} sample${step.overlap === 1 ? '' : 's'} `
    + `overlap and the sum is ${fixed(step.sum)}.`;
}

/**
 * 這一頁的「判決句」。**它不先講結論**（規則 5 的分寸）——它報告學生
 * 目前這個設定處在什麼狀態，為什麼會這樣留在 <details> 裡。
 */
function verdictSentence(step, y) {
  const x = currentInput();
  const h = currentResponse();
  const bits = [
    `The output is ${x.length} + ${h.length} - 1 = ${y.length} samples long.`,
  ];
  if (step.overlap === 0) {
    bits.push('At this shift the two signals do not overlap at all, so every '
      + 'product is zero and so is the sum.');
  } else {
    bits.push(`The sum at n = ${state.shift} runs over k from ${step.kStart} to `
      + `${step.kEnd}, which is ${step.overlap} term`
      + `${step.overlap === 1 ? '' : 's'}, and comes to ${fixed(step.sum)}.`);
  }
  if (!state.flip) {
    bits.push('The flip is switched off, so h is being slid across in its '
      + 'original orientation.');
  }
  if (state.inputShape === 'impulse') {
    bits.push('The input is a single impulse, so compare the output row with '
      + 'the impulse response above it.');
  }
  return bits.join(' ');
}

// ---------------------------------------------------------------- 表格

function fillTermsTable(step) {
  while (termsRows.firstChild) termsRows.removeChild(termsRows.firstChild);
  const shown = step.terms.slice(0, MAX_TERM_ROWS);
  for (const term of shown) {
    const row = document.createElement('tr');
    for (const text of [
      String(term.k), fixed(term.x), fixed(term.h), fixed(term.product),
    ]) {
      const cell = document.createElement('td');
      cell.textContent = text;
      row.appendChild(cell);
    }
    termsRows.appendChild(row);
  }
  // 總和自己一列，而且標成 is-current——它是這張表存在的理由。
  const total = document.createElement('tr');
  total.className = 'is-current';
  for (const text of ['Sum', '', '', fixed(step.sum)]) {
    const cell = document.createElement('td');
    cell.textContent = text;
    total.appendChild(cell);
  }
  termsRows.appendChild(total);

  const hidden = step.terms.length - shown.length;
  termsCaption.textContent = step.overlap === 0
    ? `At n = ${step.n} nothing overlaps, so the sum is empty and y[${step.n}] is zero.`
    : `Every term of y[${step.n}], written out. `
      + `${hidden > 0 ? `${hidden} further rows are not shown. ` : ''}`
      + 'These are the numbers you would write down doing it by hand.';
}

function currentSystem(h) {
  return { kind: state.system, h, clip: CLIP_LEVEL };
}

function fillLtiTable(h) {
  while (ltiRows.firstChild) ltiRows.removeChild(ltiRows.firstChild);
  for (const kind of Object.keys(SYSTEMS)) {
    const system = { kind, h, clip: CLIP_LEVEL };
    const superposition = superpositionCurves(system, LTI_A, LTI_B).residual;
    const invariance = timeInvarianceCurves(system, LTI_PROBE, LTI_SHIFT).residual;
    const row = document.createElement('tr');
    if (kind === state.system) row.className = 'is-current';
    for (const text of [
      SYSTEMS[kind], residualText(superposition), residualText(invariance),
    ]) {
      const cell = document.createElement('td');
      cell.textContent = text;
      row.appendChild(cell);
    }
    ltiRows.appendChild(row);
  }
  ltiCaption.textContent =
    'Both checks report how far the system misses by, so a system that passes '
    + 'reports zero apart from floating-point rounding, which is around '
    + '0.0000000000000002 here. '
    + `The two test signals peak at ${fixed(peakAmplitude(LTI_A), 2)} and `
    + `${fixed(peakAmplitude(LTI_B), 2)} on their own, and at `
    + `${fixed(peakAmplitude(addPointwise(LTI_A, LTI_B)), 2)} added together, `
    + `against a clipping limit of ${fixed(CLIP_LEVEL, 2)}.`;
}

/** 兩條等長序列逐點相加。表格說明裡要用一次峰值，只有這一個用途。 */
function addPointwise(a, b) {
  const out = new Float64Array(Math.max(a.length, b.length));
  for (let i = 0; i < out.length; i += 1) out[i] = (a[i] || 0) + (b[i] || 0);
  return out;
}

// ---------------------------------------------------------------- 繪製

/** 離散圖共用的縱軸範圍：對稱、至少 ±1，留一成的頂空。 */
function symmetricSpan(...arrays) {
  let peak = 1;
  for (const array of arrays) {
    const p = peakAmplitude(array);
    if (p > peak) peak = p;
  }
  return peak * 1.15;
}

function drawOverlap(x, sliding, step) {
  const { width, height, ctx } = fitCanvas(overlapCanvas, window.devicePixelRatio || 1);
  const kMax = Math.max(x.length - 1, 1);
  const span = symmetricSpan(x, sliding);
  const scale = makeScale({
    t0: -0.5, t1: kMax + 0.5, vMin: -span, vMax: span, width, height, pad: PAD,
  });
  clear(ctx, width, height);

  // 先畫重疊區的陰影：它在最底下，因為它是「哪些 k 有貢獻」的背景資訊。
  fillRegion(ctx, regionRect(scale, step.kStart - 0.4, step.kEnd + 0.4), {
    color: STYLE.overlap, outline: STYLE.overlapEdge,
  });
  strokeAxes(ctx, scale, STYLE);

  const indices = [];
  for (let k = 0; k < x.length; k += 1) indices.push(k);

  // 翻轉平移後的 h，取樣在同一組 k 上——**兩條線畫在同一個 k 軸上**
  // 正是這張圖唯一要說的事。
  const shifted = flippedShiftedResponse(sliding, step.n, 0, x.length - 1);
  strokeStems(ctx, curvePoints(scale, indices, shifted), scale.y(0), {
    color: STYLE.response, radius: 4.5,
  });
  strokeStems(ctx, curvePoints(scale, indices, x), scale.y(0), {
    color: STYLE.input, radius: 3,
  });

  const ticks = [];
  const step2 = Math.max(1, Math.round(x.length / 8));
  for (let k = 0; k < x.length; k += step2) ticks.push(k);
  strokeAxisWithTicks(ctx, scale, ticks, (v) => String(Math.round(v)), STYLE);
}

function drawProducts(x, step) {
  const { width, height, ctx } = fitCanvas(productsCanvas, window.devicePixelRatio || 1);
  const kMax = Math.max(x.length - 1, 1);
  const span = symmetricSpan(step.products);
  const scale = makeScale({
    t0: -0.5, t1: kMax + 0.5, vMin: -span, vMax: span, width, height, pad: PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  const indices = [];
  for (let k = 0; k < x.length; k += 1) indices.push(k);
  strokeStems(ctx, curvePoints(scale, indices, step.products), scale.y(0), {
    color: STYLE.product, radius: 3.5,
  });

  // 總和畫成一條水平線：把「這些棒子加起來」變成一個看得見的高度，
  // 而下一張圖裡的那一根棒子就是它。
  strokePolyline(ctx, [
    { x: scale.x(-0.5), y: scale.y(step.sum) },
    { x: scale.x(kMax + 0.5), y: scale.y(step.sum) },
  ], { color: STYLE.total, width: 1.6, dash: [2, 3] });

  strokeAxisWithTicks(ctx, scale, indices.filter((k) => k % Math.max(1, Math.round(x.length / 8)) === 0),
    (v) => String(Math.round(v)), STYLE);
}

function drawOutput(y) {
  const { width, height, ctx } = fitCanvas(outputCanvas, window.devicePixelRatio || 1);
  const span = symmetricSpan(y);
  const nMax = Math.max(y.length - 1, 1);
  const scale = makeScale({
    t0: -0.5, t1: nMax + 0.5, vMin: -span, vMax: span, width, height, pad: PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  // 已經掃過的部分與還沒到的部分分兩批畫。**這就是「累積出來的輸出」**——
  // 拖著滑桿往右走，實心的那一段長出來。
  const doneIndices = [];
  const doneValues = [];
  const pendingIndices = [];
  const pendingValues = [];
  for (let n = 0; n < y.length; n += 1) {
    if (n <= state.shift) { doneIndices.push(n); doneValues.push(y[n]); } else { pendingIndices.push(n); pendingValues.push(y[n]); }
  }
  strokeStems(ctx, curvePoints(scale, pendingIndices, pendingValues), scale.y(0), {
    color: STYLE.pending, radius: 2.5,
  });
  strokeStems(ctx, curvePoints(scale, doneIndices, doneValues), scale.y(0), {
    color: STYLE.done, radius: 3.5,
  });

  if (state.shift < y.length) {
    markPoint(ctx, { x: scale.x(state.shift), y: scale.y(y[state.shift]) }, {
      color: STYLE.mark,
    });
  }

  const ticks = [];
  const gap = Math.max(1, Math.round(y.length / 10));
  for (let n = 0; n < y.length; n += gap) ticks.push(n);
  strokeAxisWithTicks(ctx, scale, ticks, (v) => String(Math.round(v)), STYLE);
}

function drawLti(h) {
  const { width, height, ctx } = fitCanvas(ltiCanvas, window.devicePixelRatio || 1);
  const { together, apart } = superpositionCurves(currentSystem(h), LTI_A, LTI_B);
  const span = symmetricSpan(together, apart);
  const nMax = Math.max(together.length - 1, 1);
  const scale = makeScale({
    t0: -0.5, t1: nMax + 0.5, vMin: -span, vMax: span, width, height, pad: PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  const indices = [];
  for (let n = 0; n < together.length; n += 1) indices.push(n);
  strokePolyline(ctx, curvePoints(scale, indices, Array.from(apart)), STYLE.apart);
  strokePolyline(ctx, curvePoints(scale, indices, Array.from(together)), STYLE.together);

  const ticks = [];
  const gap = Math.max(1, Math.round(together.length / 10));
  for (let n = 0; n < together.length; n += gap) ticks.push(n);
  strokeAxisWithTicks(ctx, scale, ticks, (v) => String(Math.round(v)), STYLE);
  return together.length;
}

// ---------------------------------------------------------------- 描述文字
//
// Canvas 的文字替代是**算出來的**，不是靜態 alt（§8.6 第 3 點）。

function describeOverlap(x, sliding, step) {
  const shifted = flippedShiftedResponse(sliding, step.n, 0, x.length - 1);
  const nonZero = nonZeroTaps(shifted, { limit: 8 })
    .map((tap) => `k equals ${tap.index}`)
    .join(', ');
  if (step.overlap === 0) {
    return `The input occupies k from 0 to ${x.length - 1}. The shifted impulse `
      + `response has moved clear of it, so nothing overlaps at n = ${step.n}.`;
  }
  return `The input occupies k from 0 to ${x.length - 1}, drawn as filled stems. `
    + `The impulse response, flipped and shifted to n = ${step.n}, is non-zero at `
    + `${nonZero || 'no sample inside this window'}. The two overlap for k from `
    + `${step.kStart} to ${step.kEnd}, which is the shaded band.`;
}

function describeProducts(step) {
  if (step.overlap === 0) {
    return `Every product is zero at n = ${step.n}, so their total is zero.`;
  }
  const listed = step.terms.slice(0, 6)
    .map((term) => `at k equals ${term.k}, ${fixed(term.x)} times ${fixed(term.h)} `
      + `gives ${fixed(term.product)}`)
    .join('; ');
  return `The products at each k: ${listed}. Their total, drawn as the `
    + `horizontal line, is ${fixed(step.sum)}, and that is y at n equals ${step.n}.`;
}

function describeOutput(y) {
  const peak = peakAmplitude(y);
  let peakAt = 0;
  for (let n = 0; n < y.length; n += 1) if (Math.abs(y[n]) === peak) { peakAt = n; break; }
  return `The whole output, ${y.length} samples long, from n equals 0 to `
    + `${y.length - 1}. Its largest value is ${fixed(y[peakAt])} at n equals `
    + `${peakAt}. The first ${state.shift + 1} of them are drawn filled, because `
    + 'the slider has reached them.';
}

function describeLti(count) {
  const h = currentResponse();
  const { residual } = superpositionCurves(currentSystem(h), LTI_A, LTI_B);
  return `Two curves, each ${count} samples long: the system's answer to the two `
    + 'test signals added together, drawn solid, and the sum of its two separate '
    + `answers, drawn dashed. They differ by at most ${residualText(residual)}`
    + `${residual < EXACT ? ', so the two curves lie on top of each other' : ''}.`;
}

// ---------------------------------------------------------------- render

function render() {
  const x = currentInput();
  const h = currentResponse();
  const sliding = slidingResponse();
  const y = convolve(x, sliding);
  const n = clamp(state.shift, 0, Math.max(0, y.length - 1));
  const step = convolutionStep(x, sliding, n);

  drawOverlap(x, sliding, step);
  drawProducts(x, step);
  drawOutput(y);
  fillTermsTable(step);

  const room = roomModel();
  drawRoom(room);
  drawWaveforms();
  const ltiCount = drawLti(h);
  fillLtiTable(h);

  outXLength.textContent = `${x.length} samples`;
  outHLength.textContent = `${h.length} samples`;
  outYLength.textContent = `${y.length} samples`;
  outOverlap.textContent = step.overlap === 0
    ? 'none at this shift'
    : `${step.overlap} of ${x.length}`;
  outSum.textContent = fixed(step.sum);
  outDc.textContent = fixed(directCurrentGain(h));

  outRt60.textContent = `${fixed(room.rt60, 2)} s`;
  outFirst.textContent = ms(room.firstMs);
  outDirect.textContent = `${fixed(room.earlyDb, 1)} dB`;
  outTreble.textContent = `${fixed(room.trebleRatio, 2)} times`;
  outHTaps.textContent = `${room.h.length} samples at ${Math.round(room.rate)} Hz`;

  verdict.textContent = verdictSentence(step, y);
  usesHint.textContent = usesSentence();
  overlapDescription.textContent = describeOverlap(x, sliding, step);
  productsDescription.textContent = describeProducts(step);
  outputDescription.textContent = describeOutput(y);
  roomDescription.textContent = describeRoom(room);
  dryDescription.textContent = describeWaveform('dry');
  wetDescription.textContent = describeWaveform('wet');
  ltiDescription.textContent = describeLti(ltiCount);
  audioStatus.textContent = audioStatusSentence();
  shell.announce(statusSentence(step, y));
}

// ---------------------------------------------------------------- 房間
//
// ⛔ **這一段是這一頁的主角**（2S10b、v0.44）。三顆按鈕、一個選單，沒有滑桿。
//
// ⚠️ 四個房間都是**誠實的 LTI 系統**：聽到的差別完全來自 h。
// 尤其是 `street`——它聽起來不像馬路，因為**車聲是加上去的，不是摺積出來的**
// （y = x*h + n 的那個 n）。頁面上有一段 <details> 專門講這件事。

/**
 * 還沒開音訊時，畫 h 用的取樣率。
 *
 * ⚠️ 這**不是**寫死取樣率（§8.5 禁止的那件事），差別在有沒有說出來：
 * 狀態列在音訊還沒開始時會明講「以下的長度是以 48000 Hz 算的」，
 * 按下任何一顆播放鍵之後就換成 `ctx.sampleRate` 重算。
 */
const PREVIEW_RATE = 48000;

let speechCache = { rate: 0, value: null };
let roomCache = { key: '', value: null };
let renderCache = { key: '', value: null };
let activeNode = null;

/** 目前該用哪個取樣率。沒有音訊時是**宣告過的**假設，見 PREVIEW_RATE。 */
function currentRate() {
  return state.deviceRate || PREVIEW_RATE;
}

/**
 * 目前房間的 h 與**量出來的**幾個數字。
 *
 * ⛔ `rt60` 是 `measuredRt60(h)` 量出來的，**不是** `ROOMS[kind].rt60`。
 * 那兩個是不同的東西：一個是造 h 用的參數，一個是拿造好的 h 回頭量。
 * 印參數等於印出自己的輸入，證明不了任何事——而這條獨立的路**當場就
 * 抓到了一個錯**：第一版的 `decayTau()` 把係數寫成 6 而不是 3，
 * 於是四個房間量出來整整齊齊都是參數的一半。
 */
function roomModel() {
  const rate = currentRate();
  const key = `${state.room}|${rate}`;
  if (roomCache.key === key) return roomCache.value;
  const h = roomResponse(state.room, rate);
  const spec = ROOMS[state.room];
  const peak = peakAmplitude(h);
  let firstIndex = 0;
  for (let i = 1; i < h.length; i += 1) {
    if (Math.abs(h[i]) > 0.05 * peak) { firstIndex = i; break; }
  }
  const earlyCut = Math.min(h.length, Math.round(0.020 * rate));
  let earlyEnergy = 0;
  let totalEnergy = 0;
  for (let i = 0; i < h.length; i += 1) {
    const e = h[i] * h[i];
    totalEnergy += e;
    if (i < earlyCut) earlyEnergy += e;
  }
  const value = {
    rate,
    h,
    spec,
    rt60: measuredRt60(h, rate),
    firstMs: (firstIndex / rate) * 1000,
    // 前 20 毫秒佔了整條 h 多少能量。
    // ⛔ **不是「h[0] 有多大」**：棉被那一個把直接音抹開成一整毫秒，
    // 於是 h[0] 變小而聲音一點也沒有變遠——一個只看第一個樣本的讀數
    // 會說「這個空間很大」，那是錯的。前 20 毫秒是聽覺上「直接聽到」的那一段。
    earlyDb: 10 * Math.log10(Math.max(earlyEnergy / Math.max(totalEnergy, 1e-30), 1e-12)),
    // 高頻留下多少（相對於低頻）。**這是棉被唯一會動的那一個數字**：
    // 四個空間都接近 1，棉被大約 0.1。
    trebleRatio: bandGain(h, { from: 3000, to: 5000, sampleRate: rate })
      / Math.max(bandGain(h, { from: 150, to: 250, sampleRate: rate }), 1e-9),
  };
  roomCache = { key, value };
  return value;
}

/** 語音樣本，解碼一次就留著（換取樣率才重算）。 */
async function speechAt(rate) {
  if (speechCache.rate === rate && speechCache.value) return speechCache.value;
  const decoded = await loadSpeech();
  const channels = [];
  for (let c = 0; c < decoded.numberOfChannels; c += 1) {
    channels.push(decoded.getChannelData(c));
  }
  const mono = mixToMono(channels, Math.round(SPEECH_SECONDS * decoded.sampleRate));
  speechCache = { rate, value: mono };
  return mono;
}

/**
 * 算好這個房間要播的三段（x、h、y），**一個房間只算一次**。
 *
 * ⚠️ 一次 FFT 摺積在這個規模上是 100–350 毫秒（3.5 秒語音 × 最長 1.9 秒的 h）。
 * 舊版每動一次滑桿就重算並重新開始迴圈播放；現在是按下按鈕才算，
 * 而且算過的留著——**切回同一個房間不會再等一次**。
 */
async function ensureRendered() {
  const rate = audio.sampleRate;
  const key = `${state.room}|${rate}`;
  if (renderCache.key === key) return renderCache.value;
  state.building = true;
  shell.scheduleRender();
  try {
    const x = await speechAt(rate);
    const h = roomResponse(state.room, rate);
    const y = fftConvolve(x, h);
    const value = { x, h, y, rate };
    renderCache = { key, value };
    return value;
  } finally {
    state.building = false;
  }
}

/** 拆掉正在播的那個節點。**一定要 disconnect**，否則就是 §8.2 的孤兒節點。 */
function stopPlayback() {
  if (activeNode) {
    try {
      activeNode.onended = null;
      activeNode.stop();
    } catch (err) {
      // 已經停過的節點再 stop 會丟 InvalidStateError。不是錯誤，但按規則 4
      // 仍然留一行，免得日後有別的原因掉進這裡而沒有人知道。
      console.warn('[convolution] stopping the previous source node:', err);
    }
    activeNode.disconnect();
    activeNode = null;
  }
  state.playing = null;
}

/**
 * 播一段訊號一次（不迴圈）。
 *
 * ⛔ **三段都縮到同一個 RMS**（`TARGET_RMS`），不是各自縮到峰值 1。
 * 這一頁唯一的意義是 A/B 對照，而各自正規化到峰值會把對照變成
 * **一次音量比較**——殘響長的那些峰值高、平均能量低，峰值對齊之後
 * 隧道會明顯比街道小聲，於是學生聽到的是「變小聲了」而不是「變遠了」。
 * ⚠️ 峰值仍然有上限（`normaliseToRms` 的 `peakCeiling`），削到的那一題
 * 會在狀態列說出來——規則 4：不得靜默降級。
 */
function playSignal(signal, rate, label) {
  ensureGraph();
  stopPlayback();
  const { scale, clipped } = normaliseToRms(signal, TARGET_RMS);
  const data = new Float32Array(signal.length);
  for (let i = 0; i < signal.length; i += 1) data[i] = signal[i] * scale;
  const buffer = audio.ctx.createBuffer(1, data.length, rate);
  buffer.copyToChannel(data, 0);
  const node = audio.ctx.createBufferSource();
  node.buffer = buffer;
  node.connect(playGain);
  node.onended = () => {
    if (activeNode === node) {
      activeNode = null;
      state.playing = null;
      shell.scheduleRender();
    }
  };
  node.start();
  activeNode = node;
  state.playing = label;
  if (clipped) {
    shell.showMessage(
      'That version was loud enough to clip, so it is playing a little quieter '
      + 'than the others. The comparison between rooms is still fair for '
      + 'everything except the very loudest moments.', 'notice',
    );
  }
  shell.scheduleRender();
}

/** 三顆播放鍵共用的入口：確定音訊開著、算好、播出去。 */
async function playPart(which) {
  // ⛔ 瀏覽器沒有 Web Audio 時**直接返回**，不要每按一次就試一次。
  // 頁面載入時已經放了一則說明在畫面上（見檔尾的啟動那一段），
  // 而每按一次就呼叫一次 `audio.start()` 只會在 console 疊一堆同樣的警告
  // ——那不是「說出來」，那是噪音。
  if (!DemoAudio.supported) return;
  if (!state.running) {
    const ok = await audio.start();
    if (!ok) return;             // 失敗訊息已經由 onFailure 放上畫面了
  }
  shell.clearMessage();
  try {
    const { x, h, y, rate } = await ensureRendered();
    if (which === 'dry') playSignal(x, rate, 'dry');
    else if (which === 'response') playSignal(h, rate, 'response');
    else playSignal(y, rate, 'wet');
  } catch (err) {
    // 規則 4：載入或計算失敗要在畫面上說出來，不得只寫 console。
    console.error('[convolution] could not prepare that sound:', err);
    shell.showMessage(
      'The built-in speech recording could not be loaded, so there is nothing '
      + 'to play. Reload the page to try again.', 'error',
    );
  }
  shell.scheduleRender();
}

// ---------------------------------------------------------------- 房間的圖

/** 把一條很長的訊號抽成畫得動的包絡（每段取絕對值的最大）。 */
function envelope(signal, buckets) {
  const out = new Float64Array(buckets);
  const per = signal.length / buckets;
  for (let b = 0; b < buckets; b += 1) {
    const from = Math.floor(b * per);
    const to = Math.min(signal.length, Math.floor((b + 1) * per) + 1);
    let peak = 0;
    for (let i = from; i < to; i += 1) {
      const v = Math.abs(signal[i]);
      if (v > peak) peak = v;
    }
    out[b] = peak;
  }
  return out;
}

/**
 * h 的圖：橫軸毫秒，縱軸是每一小段的峰值包絡。
 *
 * ⛔ **縱軸固定在 [0, 1]，不隨房間自動縮放。** 自動縮放會讓每個房間的第一根
 * 都頂到天花板，於是「直接音佔多少」這個一眼看得出來的差別就消失了
 * ——而那正是乾與濕的差別本身。單位能量的 h 讓這件事成立：h[0] 就是
 * 直接音對整條響應的比值。
 */
function drawRoom(model) {
  const { width, height, ctx } = fitCanvas(roomCanvas, window.devicePixelRatio || 1);
  const totalMs = (model.h.length / model.rate) * 1000;
  const scale = makeScale({
    t0: 0, t1: Math.max(totalMs, 1), vMin: -0.05, vMax: 1,
    width, height, pad: PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);
  const buckets = Math.max(80, Math.round(width - PAD.left - PAD.right));
  const env = envelope(model.h, buckets);
  const times = [];
  const values = [];
  for (let b = 0; b < buckets; b += 1) {
    times.push(((b + 0.5) / buckets) * totalMs);
    values.push(env[b]);
  }
  strokeStems(ctx, curvePoints(scale, times, values), scale.y(0), {
    color: STYLE.response, radius: 0,
  });
}

/**
 * 上下兩張波形圖：乾的與濕的。
 *
 * ⚠️ **兩張共用同一個縱軸，而且不各自正規化。** 濕的那一條的尾巴要看得出來
 * 比乾的長——那個長出來的部分恰好是 h 的長度，也是「最後一個樣本還有
 * 一整條脈衝響應要走完」這句話在畫面上的樣子。
 */
function drawWaveforms() {
  const cached = renderCache.value;
  const longest = cached ? Math.max(cached.x.length, cached.y.length) : 1;
  for (const [canvas, signal, color] of [
    [dryCanvas, cached && cached.x, STYLE.input],
    [wetCanvas, cached && cached.y, STYLE.response],
  ]) {
    const { width, height, ctx } = fitCanvas(canvas, window.devicePixelRatio || 1);
    const seconds = cached ? longest / cached.rate : 1;
    const scale = makeScale({
      t0: 0, t1: seconds, vMin: -1, vMax: 1, width, height, pad: PAD,
    });
    clear(ctx, width, height);
    strokeAxes(ctx, scale, STYLE);
    if (!signal) continue;
    const buckets = Math.max(80, Math.round(width - PAD.left - PAD.right));
    const env = envelope(signal, buckets);
    let peak = 0;
    for (const v of env) if (v > peak) peak = v;
    const norm = peak > 0 ? 1 / peak : 1;
    const span = signal.length / cached.rate;
    const times = [];
    const upper = [];
    const lower = [];
    for (let b = 0; b < buckets; b += 1) {
      times.push(((b + 0.5) / buckets) * span);
      upper.push(env[b] * norm);
      lower.push(-env[b] * norm);
    }
    strokePolyline(ctx, curvePoints(scale, times, upper), { color, width: 1 });
    strokePolyline(ctx, curvePoints(scale, times, lower), { color, width: 1 });
  }
}

// ---------------------------------------------------------------- 房間的文字

function describeRoom(model) {
  return `${model.spec.label}. The impulse response lasts `
    + `${fixed(model.h.length / model.rate, 2)} seconds in total; its `
    + `time to fade by sixty decibels, measured from the response itself, is `
    + `${fixed(model.rt60, 2)} seconds. The next arrival after the direct `
    + `sound is ${ms(model.firstMs)} later; the first twenty milliseconds `
    + `carry ${fixed(model.earlyDb, 1)} decibels of the whole response, and `
    + `four kilohertz comes through ${fixed(model.trebleRatio, 2)} times as `
    + `strongly as two hundred hertz.`;
}

function describeWaveform(which) {
  const cached = renderCache.value;
  if (!cached) {
    return 'Nothing has been computed yet. Press one of the play buttons.';
  }
  const signal = which === 'dry' ? cached.x : cached.y;
  const seconds = signal.length / cached.rate;
  return which === 'dry'
    ? `The outline of the original recording, ${fixed(seconds, 2)} seconds long.`
    : `The outline of the same recording after the room, `
      + `${fixed(seconds, 2)} seconds long — longer than the input by the `
      + `length of h, because the last sample of the voice still has a whole `
      + `impulse response to finish.`;
}

/**
 * 狀態列。三件事都必須說出口（規則 4）：
 * 取樣率是誰決定的、h 的長度是以哪個取樣率算的、以及正在算的時候有沒有在等。
 */
function audioStatusSentence() {
  if (state.building) {
    return 'Working out the convolution for this room — a few hundred '
      + 'milliseconds the first time each room is used.';
  }
  if (!state.running) {
    return `Sound has not started. The lengths below are worked out for a `
      + `${PREVIEW_RATE} Hz device, and your own device `
      + 'may run at a different rate; they are recomputed when sound starts.';
  }
  const playing = {
    dry: 'Playing the original recording.',
    response: "Playing the room's impulse response on its own.",
    wet: 'Playing the recording after the room.',
  }[state.playing];
  return `Sound is running at ${Math.round(audio.sampleRate)} Hz, the rate `
    + `your device chose. ${playing || 'Nothing is playing right now.'}`;
}

// ---------------------------------------------------------------- 外框與控制項

const shell = createShell({
  root,
  // ⛔ 刻意不傳 `onToggle`：這一頁沒有 Start/Stop 按鈕。
  // `createShell()` 會檢查這兩件事一致，不一致就當場丟（規則 4）。
  onMuteChange: (muted) => audio.setMuted(muted),
  onVolumeChange: (v) => audio.setVolume(v),
});

audio.setVolume(shell.volume);
shell.onRender(render);

/**
 * 平移滑桿的上下界跟著 y 的長度走。
 *
 * ⚠️ 這裡直接寫 DOM，而不是走 `bindNumberPair` 的 onChange——走 onChange 會
 * 再排一次重繪，而這支函式**本來就是在處理一次變更的途中**被呼叫的。
 * 「DOM 不是真相的來源」沒有被放寬：`state.shift` 仍然是真相，
 * 這幾行只是把它與它的上界同步到畫面上。
 */
function syncShiftBounds() {
  const maxN = Math.max(0, outputLength() - 1);
  shiftRange.max = String(maxN);
  shiftNumber.max = String(maxN);
  if (state.shift > maxN) state.shift = maxN;
  shiftRange.value = String(state.shift);
  shiftNumber.value = String(state.shift);
}

const shiftPair = bindNumberPair({
  range: shiftRange,
  number: shiftNumber,
  onChange: (value) => {
    state.shift = Math.round(value);
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('x-length'),
  number: document.getElementById('x-length-number'),
  onChange: (value) => {
    state.xLength = Math.round(value);
    syncShiftBounds();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('delay-taps'),
  number: document.getElementById('delay-taps-number'),
  onChange: (value) => {
    state.delayTaps = Math.round(value);
    syncShiftBounds();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('length-taps'),
  number: document.getElementById('length-taps-number'),
  onChange: (value) => {
    state.lengthTaps = Math.round(value);
    syncShiftBounds();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('gain'),
  number: document.getElementById('gain-number'),
  onChange: (value) => {
    state.gain = value;
    shell.scheduleRender();
  },
});

inputShapeSelect.addEventListener('change', () => {
  state.inputShape = inputShapeSelect.value;
  syncShiftBounds();
  shell.scheduleRender();
});

responseShapeSelect.addEventListener('change', () => {
  state.responseShape = responseShapeSelect.value;
  syncShiftBounds();
  shell.scheduleRender();
});

flipBox.addEventListener('change', () => {
  state.flip = flipBox.checked;
  shell.scheduleRender();
});

systemSelect.addEventListener('change', () => {
  state.system = systemSelect.value;
  shell.scheduleRender();
});

// ---------------------------------------------------------------- 掃描
//
// §8.6 第 5 點：`prefers-reduced-motion` 時不自動播動畫，改為按鍵推進。
// **兩種模式共用同一個 `advance()`**，所以「按一下走一格」與「自己走」
// 走的是同一條程式碼路徑，不會有一邊悄悄壞掉。

let sweepFrames = 0;

function advance() {
  const last = Math.max(0, outputLength() - 1);
  const next = state.shift >= last ? 0 : state.shift + 1;
  shiftPair.set(next);
  return next;
}

function stopSweep() {
  state.sweeping = false;
  shell.stopLoop();
  sweepButton.textContent = reducedMotion
    ? 'Step n forward one sample'
    : 'Sweep n from start to end';
}

sweepButton.addEventListener('click', () => {
  if (reducedMotion) {
    advance();
    return;
  }
  if (state.sweeping) {
    stopSweep();
    return;
  }
  state.sweeping = true;
  sweepFrames = 0;
  sweepButton.textContent = 'Stop the sweep';
  shiftPair.set(0);
  shell.startLoop(() => {
    sweepFrames += 1;
    if (sweepFrames % SWEEP_EVERY !== 0) return;
    const next = advance();
    if (next === 0) stopSweep();      // 繞回起點就停，不無限重播
  });
});

// ---------------------------------------------------------------- 起始
//
// **初始值一律從 DOM 讀一次**（範本是那些數字的唯一來源），之後 state 才是
// 真相。冒煙測試就是靠這一段驗「範本寫 value=4 而 JS 期待 value=40」這種
// 不一致的——它從真的範本檔讀初始值。

state.inputShape = inputShapeSelect.value;
state.responseShape = responseShapeSelect.value;
state.flip = flipBox.checked;
state.room = roomSelect.value;
state.system = systemSelect.value;
state.xLength = Number(document.getElementById('x-length').value);
state.delayTaps = Number(document.getElementById('delay-taps').value);
state.lengthTaps = Number(document.getElementById('length-taps').value);
state.gain = Number(document.getElementById('gain').value);
state.shift = Number(shiftRange.value);
syncShiftBounds();
stopSweep();

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。這一頁的第一段與第三段完全不需要 AudioContext，
  // 所以說法要準確——壞掉的是中間那一段，不是整頁。
  shell.showMessage(
    'This browser does not support the Web Audio API, so none of the three '
    + 'play buttons can do anything. The impulse response is still drawn, and '
    + 'the mathematics at the bottom of the page still works. Try a recent '
    + 'version of Chrome or Firefox on a desktop computer.', 'warning',
  );
  // ⚠️ 這一頁沒有 Start sound 可以關掉（v0.45），要關的就是這四顆。
  for (const button of [playDryButton, playResponseButton, playWetButton,
                        stopAllButton]) {
    button.disabled = true;
  }
}

shell.setSampleRate(null);
shell.scheduleRender();

// ---------------------------------------------------------------- 房間的接線
//
// ⚠️ 放在最後面，因為它們要用到上面才建好的 `shell`。

roomSelect.addEventListener('change', () => {
  state.room = roomSelect.value;
  // ⛔ 換房間**不會自動播**。舊版是一動就重算並繼續播，而那正是
  // 「不曉得要從何調起」的一部分——畫面自己在動，人就不會去按。
  stopPlayback();
  shell.scheduleRender();
});

playDryButton.addEventListener('click', () => { playPart('dry'); });
playResponseButton.addEventListener('click', () => { playPart('response'); });
playWetButton.addEventListener('click', () => { playPart('wet'); });
stopAllButton.addEventListener('click', () => {
  stopPlayback();
  shell.scheduleRender();
});
