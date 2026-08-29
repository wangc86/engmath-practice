// 展示 4：摺積與 LTI（PLAN.md §8.2.1 第 4 列，路線圖 2S10；課程 W1–W2）。
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
  RESPONSE_SHAPES, impulseResponse, inputSequence, nonZeroTaps, countNonZeroTaps,
  clickSignal, pluckSignal, padSilence, peakAmplitude, mixToMono, clamp,
  LTI_A, LTI_B, LTI_PROBE, LTI_SHIFT,
} from './lib/signal.js';
import {
  convolve, fftConvolve, convolutionStep, flippedShiftedResponse,
  reverseSequence, convolutionGainBound, normaliseResponse,
  bandGain, directCurrentGain, SYSTEMS, CLIP_LEVEL,
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

/** 迴圈播放時尾巴補的靜音。**必須比最長的 h 還長**，否則回音會被下一輪蓋掉。 */
const LOOP_GAP_SECONDS = 0.8;

/**
 * 沒有 AudioContext 時，用來畫 h 與算頻率響應的**繪圖格線**。
 *
 * ⚠️ 這**不是**「假設裝置是 48 kHz」（§8.5 明文禁止寫死取樣率）。差別在於
 * 它有沒有被說出來：畫面上的狀態列在音訊還沒開始時會明講「以下數字是以
 * 48000 Hz 算的，你的裝置可能不同」，按下 Start sound 之後就換成
 * `ctx.sampleRate` 重算。**寫死是靜默地假設，這裡是有聲明的假設。**
 */
const PREVIEW_RATE = 48000;

/**
 * 兩段探測頻帶。低的蓋住人聲基頻，高的蓋住「亮度」那一段。
 *
 * ⚠️ **是頻帶不是單一頻率**，理由見 `transform.js` 的 `bandGain()`：
 * 回音的頻率響應是一把梳子，而單一探測點會剛好落在齒頂或齒底，
 * 印出一個對的、但完全誤導的數字。
 */
const PROBE_LOW = { from: 150, to: 250, label: '200 Hz' };
const PROBE_HIGH = { from: 3000, to: 5000, label: '4 kHz' };

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
  source: 'click',
  listen: 'output',
  delayMs: 120,
  smoothMs: 4,
  system: 'convolution',
  running: false,
  deviceRate: null,
  audioTaps: null,      // 目前實際在用的音訊 h 的 tap 數（沒有音訊時是 null）
  audioScale: 1,        // normaliseResponse 縮了多少
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
const sourceSelect = document.getElementById('source');
const listenSelect = document.getElementById('listen');
const systemSelect = document.getElementById('lti-system');
const outXLength = document.getElementById('out-x-length');
const outHLength = document.getElementById('out-h-length');
const outYLength = document.getElementById('out-y-length');
const outOverlap = document.getElementById('out-overlap');
const outSum = document.getElementById('out-sum');
const outDc = document.getElementById('out-dc');
const outTaps = document.getElementById('out-taps');
const outBound = document.getElementById('out-bound');
const outLow = document.getElementById('out-low');
const outHigh = document.getElementById('out-high');
const verdict = document.getElementById('verdict');
const audioStatus = document.getElementById('audio-status');
const overlapCanvas = document.getElementById('overlap-canvas');
const productsCanvas = document.getElementById('products-canvas');
const outputCanvas = document.getElementById('output-canvas');
const responseCanvas = document.getElementById('response-canvas');
const waveCanvas = document.getElementById('wave-canvas');
const ltiCanvas = document.getElementById('lti-canvas');
const overlapDescription = document.getElementById('overlap-description');
const productsDescription = document.getElementById('products-description');
const outputDescription = document.getElementById('output-description');
const responseDescription = document.getElementById('response-description');
const waveDescription = document.getElementById('wave-description');
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

/**
 * 音訊用的 h。`rate` 是**真的取樣率**（沒有音訊時是宣告過的 PREVIEW_RATE）。
 *
 * 與離散那一半是同一支 `impulseResponse()`，差別只在把毫秒換成格數——
 * 這一行就是「畫面上那個 h 就是耳朵裡那個 h」這句話的全部內容。
 */
function audioResponse(rate) {
  const delay = Math.max(1, Math.round((state.delayMs * rate) / 1000));
  const smooth = Math.max(1, Math.round((state.smoothMs * rate) / 1000));
  // `repeat` 用「六個回音」而不是另一支滑桿：離散那一半的 L 在這裡沒有
  // 對應的意義（16 格在 48 kHz 下是三分之一毫秒），而六個是聽得出
  // 「一串」而不是「一次」的最小數量。
  const length = state.responseShape === 'average' ? smooth : delay * 6;
  return impulseResponse(state.responseShape, {
    delay, length, gain: state.gain,
  });
}

/** 目前該用哪個取樣率算數字。沒有音訊時是宣告過的假設，見 PREVIEW_RATE。 */
function analysisRate() {
  return state.deviceRate || PREVIEW_RATE;
}

/**
 * 音訊那一側每一格畫面都要用到的那組東西，**算一次就留著**。
 *
 * ⚠️ 這個快取不是提早最佳化，它是被算出來的：`repeat` 配 400 ms 的延遲在
 * 48 kHz 下是一條十一萬格的 `Float64Array`，而 `render()` 一秒會跑三十次
 * （掃描的時候）——不快取就是每秒配置三十幾 MB，GC 會在畫面上看得出來。
 *
 * **快取的鍵是它全部的輸入**，所以它不構成第二個真相來源（README 第三條）：
 * 任何一個輸入變了，鍵就變了，值就重算。這與 `fourier.js` 的
 * `lastSignature` 是同一個作法。
 */
let audioModelCache = { key: '', value: null };

function audioModel() {
  const rate = analysisRate();
  const key = [
    state.responseShape, state.delayMs, state.smoothMs, state.gain, rate,
  ].join('|');
  if (audioModelCache.key === key) return audioModelCache.value;
  const raw = audioResponse(rate);
  const normalised = normaliseResponse(raw);
  const value = {
    rate,
    raw,
    taps: normalised.taps,
    scale: normalised.scale,
    bound: normalised.bound,
    tapCount: countNonZeroTaps(normalised.taps),
    lowGain: bandGain(normalised.taps, { ...PROBE_LOW, sampleRate: rate }),
    highGain: bandGain(normalised.taps, { ...PROBE_HIGH, sampleRate: rate }),
  };
  audioModelCache = { key, value };
  return value;
}

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
        'Sound stopped because you left this tab. Press Start sound to '
        + 'continue.', 'notice',
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

/** 依 state.source 造出輸入訊號（單聲道 Float32Array，取樣率＝裝置的）。 */
async function buildInput(rate) {
  if (state.source === 'click') return clickSignal(rate, { millis: 1 });
  if (state.source === 'pluck') return pluckSignal(rate, { frequency: 330 });
  const decoded = await loadSpeech();
  const channels = [];
  for (let c = 0; c < decoded.numberOfChannels; c += 1) {
    channels.push(decoded.getChannelData(c));
  }
  return mixToMono(channels, Math.round(SPEECH_SECONDS * decoded.sampleRate));
}

/**
 * 算出要播的那一段，塞進 AudioBuffer，接上去播。
 *
 * ⚠️ **輸入與輸出用同一個正規化係數**，不是各自正規化到峰值 1。
 * 各自正規化的話，切換「聽輸入／聽輸出」就變成一次音量比較而不是
 * 一次效果比較——而這一頁的 A/B 對照唯一的意義就是「除了 h 以外都一樣」。
 */
async function rebuildSound() {
  if (!audio.ctx || !state.running) return;
  ensureGraph();
  const rate = audio.sampleRate;
  state.deviceRate = rate;

  let x;
  try {
    x = await buildInput(rate);
  } catch (err) {
    // 規則 4：載入失敗要在畫面上說出來，不得只寫 console。
    console.error('[convolution] could not load the speech sample:', err);
    shell.showMessage(
      'The built-in speech recording could not be loaded, so the click is '
      + 'used instead. Reload the page to try again.', 'warning',
    );
    sourceSelect.value = 'click';
    state.source = 'click';
    x = clickSignal(rate, { millis: 1 });
  }

  audioModelCache = { key: '', value: null };   // 取樣率變了，快取失效
  const { taps, scale } = audioModel();
  state.audioTaps = taps.length;
  state.audioScale = scale;

  // 定義式在這個規模上跑不動（3.5 秒語音 × 0.7 秒殘響是數十億次乘加），
  // 所以這裡走頻域那一條。兩條路徑由 `tests/test_dsp_js.py` 比對過。
  const wet = fftConvolve(x, taps);
  const chosen = state.listen === 'input' ? x : wet;

  // 兩者共用同一個係數（見上面的 ⚠️），而係數取自**輸出**的峰值——
  // 輸出一定不小於輸入（Σ|h| ≤ 1 之後也可能接近 1），所以以它為準
  // 兩邊都不會削波。
  const peak = Math.max(peakAmplitude(wet), peakAmplitude(x), 1e-9);
  const level = 0.9 / peak;
  const padded = padSilence(chosen, rate, LOOP_GAP_SECONDS);
  for (let i = 0; i < padded.length; i += 1) padded[i] *= level;

  const buffer = audio.ctx.createBuffer(1, padded.length, rate);
  buffer.copyToChannel(padded, 0);

  disposeSource();
  const node = audio.ctx.createBufferSource();
  node.buffer = buffer;
  node.loop = true;
  node.connect(playGain);
  node.start();
  currentNode = node;

  shell.scheduleRender();
}

/** 連續拖滑桿時把重算合併起來——一次 FFT 摺積是幾十毫秒，不能每格都做。 */
function scheduleSoundUpdate() {
  if (!state.running) return;
  if (recomputeTimer) clearTimeout(recomputeTimer);
  recomputeTimer = setTimeout(() => {
    recomputeTimer = 0;
    rebuildSound().catch((err) => {
      console.error('[convolution] rebuilding the sound failed:', err);
      shell.showMessage(
        'The sound could not be rebuilt after that change. Press Stop sound '
        + 'and then Start sound again.', 'error',
      );
    });
  }, 180);
}

async function toggleSound() {
  if (state.running) {
    audio.stop();
    return;
  }
  shell.clearMessage();
  const ok = await audio.start();
  if (!ok) return;               // 失敗訊息已經由 onFailure 放上畫面了
  await rebuildSound();
  shell.scheduleRender();
}

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

/**
 * 音訊那一側的 h，橫軸是**毫秒**。
 *
 * 用 `analysisRate()` 造 h 之後把索引換成毫秒，所以這張圖與取樣率無關——
 * 而那正是它該有的性質：120 ms 的回音就是 120 ms，跟裝置沒有關係。
 */
function drawResponse(h, rate) {
  const { width, height, ctx } = fitCanvas(responseCanvas, window.devicePixelRatio || 1);
  const totalMs = ((h.length - 1) / rate) * 1000;
  const peak = Math.max(peakAmplitude(h), 1e-9);
  const scale = makeScale({
    t0: 0, t1: Math.max(totalMs, 1), vMin: -peak * 0.15, vMax: peak * 1.2,
    width, height, pad: PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  const taps = nonZeroTaps(h, { limit: STEM_LIMIT + 1 });
  if (taps.length <= STEM_LIMIT) {
    const times = taps.map((tap) => (tap.index / rate) * 1000);
    const values = taps.map((tap) => tap.value);
    strokeStems(ctx, curvePoints(scale, times, values), scale.y(0), {
      color: STYLE.response, radius: 4,
    });
  } else {
    // 移動平均在 48 kHz 下有上千個 tap；畫成一條線比畫成一千根棒子誠實
    // （棒子會糊成一片黑，讀起來像一個實心方塊而不是一段等高的係數）。
    const stride = Math.max(1, Math.ceil(h.length / 1200));
    const times = [];
    const values = [];
    for (let i = 0; i < h.length; i += stride) {
      times.push((i / rate) * 1000);
      values.push(h[i]);
    }
    strokePolyline(ctx, curvePoints(scale, times, values), {
      color: STYLE.response, width: 2,
    });
  }

  strokeAxisWithTicks(
    ctx, scale, [0, totalMs / 2, totalMs],
    (v) => `${v.toPrecision(2)} ms`, STYLE,
  );
}

/**
 * 音訊的輸入與輸出波形。
 *
 * ⚠️ 這裡**不畫實際在播的那幾十萬個樣本**，而是用同一組參數在一個
 * 較低的繪圖格線上重算一次——理由與 `drawResponse()` 相同（畫得出來、
 * 而且在音訊還沒開始時也有東西可看）。畫面與聲音的一致性靠的是
 * 「同一支 `impulseResponse()` 與同一支摺積」，不是靠同一個陣列。
 */
/** 波形預覽的繪圖格線。九百像素寬的畫面看不出比這更細的東西。 */
const WAVE_DRAW_RATE = 3000;

/**
 * 波形預覽的資料。與 `audioModel()` 同一個理由快取：它與平移滑桿無關，
 * 而掃描的時候每秒會重繪三十次。
 */
let waveCache = { key: '', value: null };

function waveModel() {
  const key = [
    state.source, state.responseShape, state.delayMs, state.smoothMs, state.gain,
  ].join('|');
  if (waveCache.key === key) return waveCache.value;
  const rate = WAVE_DRAW_RATE;
  // 語音沒有預覽波形可畫（它的樣本要等解碼），所以用撥弦音代表「一段聲音」。
  const x = state.source === 'click'
    ? clickSignal(rate, { millis: 4 })
    : pluckSignal(rate, { frequency: 110, seconds: 0.35 });
  const delay = Math.max(1, Math.round((state.delayMs * rate) / 1000));
  const smooth = Math.max(1, Math.round((state.smoothMs * rate) / 1000));
  const length = state.responseShape === 'average' ? smooth : delay * 6;
  const h = normaliseResponse(impulseResponse(state.responseShape, {
    delay, length, gain: state.gain,
  })).taps;
  // 頻域那一條：撥弦音配 400 ms 的殘響在這個格線上仍然是七百萬次乘加，
  // 而它每一格畫面都要算一次。兩條路徑由 `tests/test_dsp_js.py` 比對過。
  const value = { x, h, y: fftConvolve(x, h), rate };
  waveCache = { key, value };
  return value;
}

function drawWave() {
  const { width, height, ctx } = fitCanvas(waveCanvas, window.devicePixelRatio || 1);
  const { x, y, rate: drawRate } = waveModel();
  const seconds = y.length / drawRate;
  const span = Math.max(peakAmplitude(y), peakAmplitude(x), 1e-9) * 1.15;
  const scale = makeScale({
    t0: 0, t1: seconds, vMin: -span, vMax: span, width, height, pad: PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  const times = [];
  const dry = [];
  for (let i = 0; i < y.length; i += 1) {
    times.push(i / drawRate);
    dry.push(i < x.length ? x[i] : 0);
  }
  strokePolyline(ctx, curvePoints(scale, times, dry), STYLE.dry);
  strokePolyline(ctx, curvePoints(scale, times, Array.from(y)), STYLE.wet);
  strokeAxisWithTicks(
    ctx, scale, [0, seconds / 2, seconds],
    (v) => `${(v * 1000).toPrecision(3)} ms`, STYLE,
  );
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

function describeResponse(model) {
  const taps = nonZeroTaps(model.taps, { limit: 6 });
  const listed = listWords(taps.map(
    (tap) => `size ${fixed(tap.value)} at `
      + `${((tap.index / model.rate) * 1000).toPrecision(3)} milliseconds`,
  ));
  const total = model.tapCount;
  const head = `The impulse response used for the sound, drawn against time in `
    + `milliseconds. It has ${total} non-zero tap${total === 1 ? '' : 's'}`;
  if (taps.length === 0) return `${head}.`;
  const more = total > taps.length ? ', and more after those' : '';
  return `${head}, at ${listed}${more}.`;
}

function describeWave() {
  return 'The input, drawn as a dashed line, and the output of the same '
    + 'convolution drawn solid on the same time axis. Where the impulse '
    + 'response has separate taps, the shape of the input appears once for each '
    + 'of them, at the tap size.';
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

  const model = audioModel();
  drawResponse(model.taps, model.rate);
  drawWave();
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

  outTaps.textContent = ms(((model.taps.length - 1) / model.rate) * 1000);
  outBound.textContent = `${fixed(convolutionGainBound(model.raw), 2)} times`;
  outLow.textContent = fixed(model.lowGain);
  outHigh.textContent = fixed(model.highGain);

  verdict.textContent = verdictSentence(step, y);
  usesHint.textContent = usesSentence();
  overlapDescription.textContent = describeOverlap(x, sliding, step);
  productsDescription.textContent = describeProducts(step);
  outputDescription.textContent = describeOutput(y);
  responseDescription.textContent = describeResponse(model);
  waveDescription.textContent = describeWave();
  ltiDescription.textContent = describeLti(ltiCount);
  audioStatus.textContent = audioStatusSentence(model);
  shell.announce(statusSentence(step, y));
}

/**
 * 音訊那一段的狀態列。三件事都必須說出口（規則 4）：
 * 用的是哪個取樣率、h 有沒有被縮過、以及 click 只是「幾乎」是脈衝。
 */
function audioStatusSentence(model) {
  const bits = [];
  bits.push(state.running
    ? `Sound is running at ${Math.round(model.rate)} Hz, the rate your device `
      + `chose, and h is ${model.tapCount} non-zero taps long at that rate, so `
      + 'the numbers below are exact for it.'
    : `Sound has not started, so the numbers below are worked out for a `
      + `${PREVIEW_RATE} Hz device. Your own device may run at a different rate, `
      + 'and the readouts will change to it when you press Start sound.');
  if (model.scale < 1) {
    bits.push(`This impulse response could multiply a signal by as much as `
      + `${fixed(model.bound, 2)}, so it is scaled down by a factor of `
      + `${fixed(1 / model.scale, 2)} before playing, to keep the output `
      + 'inside what the sound card can represent.');
  }
  if (state.source === 'click') {
    bits.push('The click lasts one millisecond, which is short compared with h '
      + 'but is not literally a single sample, so what you hear is very close '
      + 'to h rather than exactly h.');
  }
  return bits.join(' ');
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
    scheduleSoundUpdate();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('delay-ms'),
  number: document.getElementById('delay-ms-number'),
  onChange: (value) => {
    state.delayMs = value;
    scheduleSoundUpdate();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('smooth-ms'),
  number: document.getElementById('smooth-ms-number'),
  onChange: (value) => {
    state.smoothMs = value;
    scheduleSoundUpdate();
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
  scheduleSoundUpdate();
  shell.scheduleRender();
});

flipBox.addEventListener('change', () => {
  state.flip = flipBox.checked;
  shell.scheduleRender();
});

sourceSelect.addEventListener('change', () => {
  state.source = sourceSelect.value;
  scheduleSoundUpdate();
  shell.scheduleRender();
});

listenSelect.addEventListener('change', () => {
  state.listen = listenSelect.value;
  scheduleSoundUpdate();
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
state.source = sourceSelect.value;
state.listen = listenSelect.value;
state.system = systemSelect.value;
state.xLength = Number(document.getElementById('x-length').value);
state.delayTaps = Number(document.getElementById('delay-taps').value);
state.lengthTaps = Number(document.getElementById('length-taps').value);
state.gain = Number(document.getElementById('gain').value);
state.delayMs = Number(document.getElementById('delay-ms').value);
state.smoothMs = Number(document.getElementById('smooth-ms').value);
state.shift = Number(shiftRange.value);
syncShiftBounds();
stopSweep();

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。這一頁的第一段與第三段完全不需要 AudioContext，
  // 所以說法要準確——壞掉的是中間那一段，不是整頁。
  shell.showMessage(
    'This browser does not support the Web Audio API, so the middle section of '
    + 'this page cannot play anything. The sliding sum at the top and the two '
    + 'checks at the bottom still work. Try a recent version of Chrome or '
    + 'Firefox on a desktop computer.', 'warning',
  );
  document.querySelector('[data-shell="toggle"]').disabled = true;
}

shell.setSampleRate(null);
shell.scheduleRender();
