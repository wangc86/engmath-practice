// 展示 3：Fourier 級數的加法合成（PLAN.md §8.2.1 第 3 列，路線圖 2S5）。
//
// **這是唯一知道 DOM、AudioContext 與使用者手勢的一層。**
// 這裡不放任何數值演算法——係數在 transform.js、波形與過衝在 signal.js、
// 幾何在 draw.js，因為 `tests/test_dsp_js.py` 只測得到那三層。
//
// 音訊圖（§8.5：能用原生節點就不要自己寫 worklet，這一頁一個都不用）：
//
//   OscillatorNode ─► toneGain ─► master ─► destination
//   （setPeriodicWave 餵一組 real/imag 表）
//
// **為什麼是一個 OscillatorNode + PeriodicWave，而不是 N 個 OscillatorNode 疊加**
// （§8.8 對 2S5 的原文寫的是後者）：因為 `OscillatorNode` **沒有相位參數**。
// 疊加 N 個振盪器可以做出振幅正確的部分和，但每一個的起始相位由它 start()
// 的那一刻決定，我們控制不了——而這一頁一半的內容就是控制相位。
// `createPeriodicWave(real, imag)` 則是逐次諧波指定 cos 與 sin 的係數，
// 也就是逐次諧波指定振幅**與相位**，正好是我們要的東西。
// 附帶兩個好處：只有一個節點要管（不會有孤兒），而且瀏覽器自己會為
// `PeriodicWave` 做帶限——不過我們**仍然自己裁**（見 applyWave），
// 因為畫面上顯示的「播了幾次諧波」必須是我們自己算得出來的數字。
//
// ⚠️ 換波形（改 N、改相位、換目標）不能直接 setPeriodicWave 了事：
// 振盪器的相位是連續的，但波形本身會瞬間換掉，輸出因此有一個階躍——
// 就是「喀」一聲。方波與鋸齒的高諧波本來就刺耳，這一頁尤其不能有爆音。
// 作法見 `swapWave()`：先把音量斜坡降到 0，在那段**完全靜音**的窗裡換，
// 再斜坡升回來。

import { DemoAudio, rampParam, rampParamLinear } from './lib/audio.js';
import { createShell, bindNumberPair } from './lib/shell.js';
import {
  WAVEFORMS, clamp, traceIdealWaveform, tracePartialSum, traceHarmonic,
  measureOvershoot, maxDeviation, periodicWaveTables, highestActiveHarmonic,
} from './lib/signal.js';
import {
  fourierCoefficients, applyPhaseScheme, bandLimit, maxBandLimitedHarmonic,
  exponentialCoefficient,
} from './lib/transform.js';
import {
  makeScale, curvePoints, fitCanvas, clear, strokeAxes, strokePolyline,
  strokeAxisWithTicks, barRects, fillBars, markPoint,
} from './lib/draw.js';

// ---------------------------------------------------------------- 常數

/** N 的上限。64 次諧波在 110 Hz 的基頻下是 7 kHz，已經到聽覺的亮部。 */
const MAX_TERMS = 64;

/** 畫面上顯示幾個週期。兩個：一個看形狀，兩個才看得出它是週期的。 */
const PERIODS_SHOWN = 2;

/** 個別諧波分解圖最多畫幾條。再多就變成一團毛球，什麼都讀不出來。 */
const MAX_DRAWN_HARMONICS = 12;

/** 吉布斯對照表用的 N。刻意接近倍增，讓「寬度減半」一眼看得出來。 */
const GIBBS_LADDER = [3, 7, 15, 31, 63];

/** 換波形時的音量凹陷（秒）。靜音窗有 36 ms，容得下 setTimeout 的抖動。 */
const SWAP_DOWN_S = 0.012;
const SWAP_HOLD_S = 0.036;
const SWAP_UP_S = 0.012;

/** 連續拖滑桿時，換波形的動作最密就這麼密（毫秒）。 */
const SWAP_COALESCE_MS = 90;

const PAD = { left: 46, right: 14, top: 14, bottom: 24 };

// 線型與顏色並用（§8.6 第 4 點：顏色不得是唯一的訊息載體）。
const STYLE = {
  axis: '#c7ccd4',
  axisText: '#6b7280',
  target: { color: '#6b7280', width: 1.5, dash: [6, 4] },
  sum: { color: '#1f4fd8', width: 2.2, dash: [] },
  harmonic: { color: '#94a3b8', width: 1, dash: [] },
  firstHarmonic: { color: '#c2410c', width: 1.6, dash: [] },
  envelope: { color: '#c2410c', width: 1.5, dash: [3, 3] },
  bar: '#1f4fd8',
  barOutline: '#0f2a75',
  mark: '#c2410c',
};

// ---------------------------------------------------------------- 狀態

const state = {
  kind: 'square',
  terms: 5,
  f0: 110,               // Hz
  phaseMode: 'series',
  phaseSeed: 1,
  phaseOffsets: {},      // 第 n 次諧波額外轉多少弧度
  editHarmonic: 1,
  listen: 'partial',     // 'partial' | 'target'
  showHarmonics: true,
  running: false,
  deviceRate: null,
  bandLimit: null,       // 目前實際播得出來的最高諧波
  dropped: 0,
};

// ---------------------------------------------------------------- DOM

const root = document.querySelector('.demo-layout');
const waveformSelect = document.getElementById('waveform');
const phaseModeSelect = document.getElementById('phase-mode');
const reshuffleButton = document.getElementById('reshuffle');
const phaseClearButton = document.getElementById('phase-clear');
const phaseHint = document.getElementById('phase-hint');
const showHarmonicsBox = document.getElementById('show-harmonics');
const outF0 = document.getElementById('out-f0');
const outTerms = document.getElementById('out-terms');
const outDecay = document.getElementById('out-decay');
const outOvershoot = document.getElementById('out-overshoot');
const outWidth = document.getElementById('out-width');
const outBandLimit = document.getElementById('out-band-limit');
const verdict = document.getElementById('verdict');
const waveCanvas = document.getElementById('sum-canvas');
const barsCanvas = document.getElementById('coefficients');
const partsCanvas = document.getElementById('decomposition');
const waveDescription = document.getElementById('sum-description');
const barsDescription = document.getElementById('coefficients-description');
const partsDescription = document.getElementById('decomposition-description');
const gibbsRows = document.getElementById('gibbs-rows');
const gibbsCaption = document.getElementById('gibbs-caption');
const derivation = document.getElementById('derivation');

// ---------------------------------------------------------------- 級數

/** 目前畫面上那條部分和的係數。**每次 render 都重算**——它很便宜，
 *  而快取一份係數就等於多一個真相來源（README 第三條）。 */
function currentSeries() {
  return applyPhaseScheme(fourierCoefficients(state.kind, state.terms), {
    mode: state.phaseMode,
    seed: state.phaseSeed,
    offsets: state.phaseOffsets,
  });
}

/**
 * 耳朵聽到的那一組係數。
 *
 * 兩件事：`listen === 'target'` 時把項數推到帶限的上限（那就是這一頁能
 * 誠實播出來的「目標波形」——它本身也是一個部分和，只是有兩百項），
 * 然後**一律**再裁一次帶限。
 */
function audibleSeries() {
  const rate = state.deviceRate;
  if (!rate) return null;
  const ceiling = maxBandLimitedHarmonic(state.f0, rate);
  const terms = state.listen === 'target'
    ? Math.max(1, Math.min(ceiling, 400))
    : state.terms;
  const series = applyPhaseScheme(fourierCoefficients(state.kind, terms), {
    mode: state.listen === 'target' ? 'series' : state.phaseMode,
    seed: state.phaseSeed,
    offsets: state.listen === 'target' ? {} : state.phaseOffsets,
  });
  return bandLimit(series, state.f0, rate);
}

// ---------------------------------------------------------------- 音訊

let osc = null;
let toneGain = null;
let swapTimer = 0;
let coalesceTimer = 0;
let lastSignature = '';

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
  toneGain = ctx.createGain();
  toneGain.gain.value = 0;
  osc = ctx.createOscillator();
  osc.frequency.value = state.f0;
  osc.connect(toneGain).connect(audio.master);
  osc.start();
}

/** 目前這一組聲音的識別字串。相同就不必換波形——那省下的是一次音量凹陷。 */
function signatureOf(limited) {
  return [
    state.kind, state.listen, state.phaseMode, state.phaseSeed,
    limited.series.harmonics.length,
    JSON.stringify(state.phaseOffsets),
  ].join('|');
}

/**
 * 換掉振盪器的波形，中間不留爆音。
 *
 * 順序是：音量線性降到 0（12 ms）→ **在那段確實是 0 的 36 ms 裡換**
 * → 線性升回來（12 ms）。`setTimeout` 排在靜音窗的正中央，
 * 因此它抖個十幾毫秒仍然落在窗裡；抖出去的最壞後果也只是換波形時
 * 音量不是 0 而是接近 0，也就是一聲很小的「嗒」而不是「喀」。
 */
function swapWave(tables) {
  const ctx = audio.ctx;
  const now = ctx.currentTime;
  const gain = toneGain.gain;
  gain.cancelScheduledValues(now);
  gain.setValueAtTime(gain.value, now);
  gain.linearRampToValueAtTime(0, now + SWAP_DOWN_S);
  gain.setValueAtTime(0, now + SWAP_DOWN_S + SWAP_HOLD_S);
  gain.linearRampToValueAtTime(1, now + SWAP_DOWN_S + SWAP_HOLD_S + SWAP_UP_S);

  if (swapTimer) clearTimeout(swapTimer);
  swapTimer = setTimeout(() => {
    swapTimer = 0;
    if (!osc) return;
    // disableNormalization: true —— 預設的正規化會把每一次的波形都拉到
    // 峰值 1，於是「加了第 3 次諧波，整體變高了一點」在耳朵裡消失，
    // 而畫面上還在。畫面與聲音對不上是這一頁最不能有的東西。
    osc.setPeriodicWave(ctx.createPeriodicWave(tables.real, tables.imag, {
      disableNormalization: true,
    }));
  }, (SWAP_DOWN_S + SWAP_HOLD_S / 2) * 1000);
}

/** 把 state 推到音訊節點上。頻率走斜坡，波形走上面那個凹陷。 */
function applyWave() {
  if (!osc || !audio.ctx) return;
  rampParamLinear(osc.frequency, state.f0, audio.ctx);

  const limited = audibleSeries();
  if (!limited) return;
  state.bandLimit = limited.limit;
  state.dropped = state.listen === 'target' ? 0 : limited.dropped;

  const signature = signatureOf(limited);
  if (signature === lastSignature) return;   // 沒變就不要製造一次凹陷
  lastSignature = signature;

  if (limited.series.harmonics.length === 0) {
    // 基頻本身就在奈奎斯特之上——一個諧波都播不出來。
    // 這是有意義的降級，但**必須說出口**（規則 4）。
    rampParam(toneGain.gain, 0, audio.ctx);
    shell.showMessage(
      'The fundamental itself is above half the sampling rate, so there is '
      + 'nothing left to play. Lower the fundamental frequency.', 'warning',
    );
    return;
  }
  swapWave(periodicWaveTables(limited.series));
}

/** 連續拖滑桿時把換波形的動作合併，最密 SWAP_COALESCE_MS 一次。 */
function scheduleWaveUpdate() {
  if (!state.running || !osc) return;
  if (coalesceTimer) return;
  coalesceTimer = setTimeout(() => {
    coalesceTimer = 0;
    applyWave();
  }, SWAP_COALESCE_MS);
}

async function toggleSound() {
  if (state.running) {
    audio.stop();
    return;
  }
  shell.clearMessage();
  const ok = await audio.start();
  if (!ok) return;                     // 失敗訊息已經由 onFailure 放上畫面了
  if (!osc) buildGraph();
  state.deviceRate = audio.sampleRate;
  lastSignature = '';                  // 重新開始時一定要重貼一次波形
  applyWave();
  shell.scheduleRender();
}

// ---------------------------------------------------------------- 文字

const hz = (v) => (v >= 1000 ? `${(v / 1000).toFixed(2)} kHz` : `${Math.round(v)} Hz`);
const percent = (v) => `${(v * 100).toFixed(2)}%`;

/**
 * 一段很短的時間，以毫秒表示。
 *
 * ⚠️ **用有效位數而不是固定小數位**，而這是被冒煙測試抓出來的：
 * 對照表第三欄的數字每一列減半，f₀ = 440 Hz 時最後兩列是
 * 0.0710 ms 與 0.0355 ms——`toFixed(2)` 把它們印成 `0.07` 與 `0.04`，
 * 比值變成 1.75，**「每次減半」這件事在畫面上就不成立了**。
 * 表格沒有壞、沒有報錯，只是那一欄開始說一件不太真的話，
 * 而它恰好是這一頁三個論點裡的一個。
 */
const milliseconds = (seconds) => `${(seconds * 1000).toPrecision(3)} ms`;
const degrees = (rad) => `${Math.round((rad * 180) / Math.PI)}`;

function shapeOf() {
  return WAVEFORMS[state.kind];
}

/** 一句給螢幕閱讀器的狀態播報（§8.6 第 2 點）。 */
function statusSentence(overshoot) {
  const shape = shapeOf();
  const base = `${shape.label}, harmonics up to ${state.terms}, fundamental `
    + `${hz(state.f0)}. Coefficients fall off like ${shape.decay}. `;
  if (overshoot.overshootFraction === null) {
    return `${base}This waveform has no jump, so there is no overshoot; the `
      + `partial sum peaks at ${overshoot.peak.toFixed(3)}.`;
  }
  return `${base}At the jump the partial sum overshoots by `
    + `${percent(overshoot.overshootFraction)} of the step.`;
}

/** Canvas 的文字替代是**算出來的**，不是靜態 alt（§8.6 第 3 點）。 */
function describeSum(overshoot) {
  const shape = shapeOf();
  const parts = [
    `${PERIODS_SHOWN} periods of a ${shape.label.toLowerCase()} at ${hz(state.f0)}, `
    + `drawn as a dashed line, with the sum of harmonics 1 to ${state.terms} `
    + 'drawn on top of it as a solid line.',
  ];
  if (overshoot.overshootFraction === null) {
    parts.push('The target has no jump in it, so the sum stays below it '
      + `everywhere, peaking at ${overshoot.peak.toFixed(3)} against a target `
      + 'peak of 1.');
  } else {
    parts.push(
      `Just past each step the sum rises to ${overshoot.peak.toFixed(3)}, which is `
      + `${percent(overshoot.overshootFraction)} of the step above the target, and `
      + `that ripple sits ${(overshoot.peakOffsetPeriods * 100).toFixed(2)} percent `
      + 'of a period away from the step.',
    );
  }
  return parts.join(' ');
}

function describeCoefficients(series) {
  const listed = series.harmonics
    .filter((h) => h.amplitude > 0)
    .slice(0, 5)
    .map((h) => `harmonic ${h.n} at amplitude ${h.amplitude.toFixed(3)} and phase `
      + `${degrees(h.phase)} degrees`)
    .join(', ');
  const missing = series.harmonics.filter((h) => h.amplitude === 0).map((h) => h.n);
  const tail = missing.length > 0
    ? ` Harmonics ${missing.slice(0, 6).join(', ')}${missing.length > 6 ? ' and so on' : ''} are absent.`
    : ' Every harmonic is present.';
  return `Amplitude of each harmonic: ${listed}.${tail}`;
}

function describeDecomposition(drawn) {
  if (drawn === 0) return 'The individual harmonics are not being drawn.';
  return `The first ${drawn} harmonics drawn separately, one sine each, with `
    + 'the fundamental highlighted. Adding these curves point by point gives the '
    + 'solid curve in the graph above.';
}

/**
 * 這一頁的「判決句」。**它不先講結論**（規則 5 的分寸）——它只報告
 * 學生剛剛做出來的那個設定處在什麼狀態，結論留在 <details> 裡。
 */
function verdictSentence(overshoot) {
  const shape = shapeOf();
  const highest = overshoot.highestHarmonic;
  const bits = [];
  if (shape.oddHarmonicsOnly) {
    bits.push(`Only odd harmonics appear, so the highest one actually used is ${highest}.`);
  }
  if (overshoot.overshootFraction === null) {
    bits.push(`This target has no jump in it, and the sum stays under the target `
      + `everywhere, peaking at ${overshoot.peak.toFixed(4)}.`);
  } else {
    bits.push(`The sum reaches ${overshoot.peak.toFixed(4)} beside a step of `
      + `${overshoot.jump}, which is ${percent(overshoot.overshootFraction)} of the step.`);
  }
  if (state.running && state.dropped > 0) {
    bits.push(`Only harmonics up to ${state.bandLimit} fit below half the sampling `
      + `rate, so ${state.dropped} of them are not being played.`);
  }
  return bits.join(' ');
}

// ---------------------------------------------------------------- 吉布斯對照表

/**
 * 「加更多項，過衝會不會消失？」——這張表就是答案。
 *
 * 三欄刻意放在一起，因為誤解正是由它們的**不同步**構成的：
 * 過衝的高度幾乎不動、寬度每次減半、而與目標的最大差距在有跳點時
 * 根本不收斂（它停在跳點本身那一格上）。少任何一欄，這張表都變成
 * 一個可以有別種讀法的東西。
 */
function fillGibbsTable() {
  const shape = shapeOf();
  const period = 1 / state.f0;
  while (gibbsRows.firstChild) gibbsRows.removeChild(gibbsRows.firstChild);

  for (const terms of GIBBS_LADDER) {
    const series = fourierCoefficients(state.kind, terms);
    const over = measureOvershoot(state.kind, series);
    const gap = maxDeviation(state.kind, series);
    const row = document.createElement('tr');
    if (terms === state.terms) row.className = 'is-current';
    const cells = [
      String(terms),
      over.overshootFraction === null ? 'no step' : percent(over.overshootFraction),
      over.peakOffsetPeriods === null
        ? '—'
        : milliseconds(over.peakOffsetPeriods * period),
      gap.toFixed(4),
    ];
    for (const text of cells) {
      const cell = document.createElement('td');
      cell.textContent = text;
      row.appendChild(cell);
    }
    gibbsRows.appendChild(row);
  }

  gibbsCaption.textContent = shape.continuous
    ? `${shape.label}: the target has no jump in it, so there is no overshoot to `
      + 'measure. Watch the last column instead, and compare it with what a '
      + 'square wave does there.'
    // 鋸齒波在項數很少時這一欄是**負的**（部分和還沒碰到目標的峰），
    // 所以標題要先講一句，否則「-4.07%」讀起來像程式壞了。
    : `${shape.label}: a step of ${shape.jump}, at ${hz(state.f0)}, so one period `
      + `is ${milliseconds(period)}. A negative figure in the second `
      + 'column means the sum has not reached the target yet at that number of '
      + 'harmonics.';
}

// ---------------------------------------------------------------- 繪製

function drawSum(series, overshoot) {
  const { width, height, ctx } = fitCanvas(waveCanvas, window.devicePixelRatio || 1);
  const duration = PERIODS_SHOWN / state.f0;
  const span = Math.max(1.35, Math.abs(overshoot.peak) + 0.2);
  const scale = makeScale({
    t0: 0, t1: duration, vMin: -span, vMax: span, width, height, pad: PAD,
  });
  const count = clamp(Math.round(width * 4), 400, 8000);

  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  const target = traceIdealWaveform(state.kind, state.f0, 0, duration, count);
  strokePolyline(ctx, curvePoints(scale, target.times, target.values), STYLE.target);

  const sum = tracePartialSum(series, state.f0, 0, duration, count);
  strokePolyline(ctx, curvePoints(scale, sum.times, sum.values), STYLE.sum);

  // 過衝的位置標出來。那一格只有幾個像素寬，不標的話學生找不到我們在說哪裡。
  if (overshoot.peakPhase !== null) {
    const t = overshoot.peakPhase / (2 * Math.PI * state.f0);
    const wrapped = ((t % duration) + duration) % duration;
    markPoint(ctx, { x: scale.x(wrapped), y: scale.y(overshoot.peak) }, {
      color: STYLE.mark,
    });
  }

  strokeAxisWithTicks(
    ctx, scale,
    [0, duration / 2, duration],
    (v) => `${(v * 1000).toFixed(2)} ms`,
    STYLE,
  );
}

function drawCoefficients(series) {
  const { width, height, ctx } = fitCanvas(barsCanvas, window.devicePixelRatio || 1);
  clear(ctx, width, height);

  const amplitudes = series.harmonics.map((h) => h.amplitude);
  const peak = Math.max(...amplitudes, 1e-9);
  const scale = makeScale({
    t0: 0.5, t1: state.terms + 0.5, vMin: 0, vMax: peak * 1.12,
    width, height, pad: PAD,
  });

  fillBars(ctx, barRects(scale, amplitudes), {
    color: STYLE.bar, outline: STYLE.barOutline,
  });

  // 1/n 或 1/n² 的包絡。**收斂速度就是這條線的陡度**，而把它畫出來
  // 比在文字裡寫「1/n²」有用得多——兩個波形換著看，兩條線的形狀不一樣。
  const shape = shapeOf();
  const first = amplitudes.find((v) => v > 0) || 0;
  const envelopeX = [];
  const envelopeY = [];
  for (let n = 1; n <= state.terms; n += 1) {
    envelopeX.push(n);
    envelopeY.push(shape.decay === '1/n' ? first / n : first / (n * n));
  }
  strokePolyline(ctx, curvePoints(scale, envelopeX, envelopeY), STYLE.envelope);

  const step = Math.max(1, Math.round(state.terms / 8));
  const ticks = [];
  for (let n = 1; n <= state.terms; n += step) ticks.push(n);
  strokeAxisWithTicks(ctx, scale, ticks, (v) => String(Math.round(v)), STYLE);
}

function drawDecomposition(series) {
  const { width, height, ctx } = fitCanvas(partsCanvas, window.devicePixelRatio || 1);
  clear(ctx, width, height);
  if (!state.showHarmonics) return 0;

  const duration = PERIODS_SHOWN / state.f0;
  const active = series.harmonics.filter((h) => h.amplitude > 0);
  const drawn = active.slice(0, MAX_DRAWN_HARMONICS);
  if (drawn.length === 0) return 0;

  const peak = Math.max(...drawn.map((h) => h.amplitude));
  const scale = makeScale({
    t0: 0, t1: duration, vMin: -peak * 1.1, vMax: peak * 1.1, width, height, pad: PAD,
  });
  const count = clamp(Math.round(width * 3), 400, 6000);
  strokeAxes(ctx, scale, STYLE);

  // 由高到低畫，讓基波（最粗、顏色不同）留在最上面。
  for (let i = drawn.length - 1; i >= 0; i -= 1) {
    const trace = traceHarmonic(drawn[i], state.f0, 0, duration, count);
    strokePolyline(ctx, curvePoints(scale, trace.times, trace.values),
      i === 0 ? STYLE.firstHarmonic : STYLE.harmonic);
  }
  strokeAxisWithTicks(
    ctx, scale, [0, duration / 2, duration],
    (v) => `${(v * 1000).toFixed(2)} ms`, STYLE,
  );
  return drawn.length;
}

function updateDerivation(series) {
  const shape = shapeOf();
  const first = series.harmonics.find((h) => h.amplitude > 0);
  if (!first) return;
  const exponential = exponentialCoefficient(first);
  derivation.textContent =
    `For this waveform the first non-zero term is harmonic ${first.n}: `
    + `a_${first.n} = ${first.cosine.toFixed(4)}, b_${first.n} = ${first.sine.toFixed(4)}, `
    + `so its amplitude is ${first.amplitude.toFixed(4)} and its phase is `
    + `${degrees(first.phase)} degrees. In the exponential form the same term is `
    + `c_${first.n} = ${exponential.re.toFixed(4)} ${exponential.im < 0 ? '-' : '+'} `
    + `${Math.abs(exponential.im).toFixed(4)}i, whose size is `
    + `${exponential.magnitude.toFixed(4)} — exactly half the amplitude, because `
    + `c_-${first.n} carries the other half. The coefficients fall off like `
    + `${shape.decay}.`;
}

// ---------------------------------------------------------------- render

function render() {
  const series = currentSeries();
  const overshoot = measureOvershoot(state.kind, series);
  const shape = shapeOf();

  drawSum(series, overshoot);
  drawCoefficients(series);
  const drawn = drawDecomposition(series);
  fillGibbsTable();
  updateDerivation(series);

  outF0.textContent = hz(state.f0);
  outTerms.textContent = `${state.terms} (highest used: ${highestActiveHarmonic(series)})`;
  outDecay.textContent = shape.decay;
  outOvershoot.textContent = overshoot.overshootFraction === null
    ? 'no jump in this target'
    : `${percent(overshoot.overshootFraction)} of the step`;
  outWidth.textContent = overshoot.peakOffsetPeriods === null
    ? '—'
    : `${milliseconds(overshoot.peakOffsetPeriods / state.f0)} from the step`;
  outBandLimit.textContent = state.running && state.bandLimit !== null
    ? `${state.bandLimit} harmonics fit`
    : 'starts with the sound';

  verdict.textContent = verdictSentence(overshoot);
  waveDescription.textContent = describeSum(overshoot);
  barsDescription.textContent = describeCoefficients(series);
  partsDescription.textContent = describeDecomposition(drawn);
  updatePhaseHint();
  shell.announce(statusSentence(overshoot));
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

const termsPair = bindNumberPair({
  range: document.getElementById('terms'),
  number: document.getElementById('terms-number'),
  onChange: (value) => {
    state.terms = Math.round(value);
    if (state.editHarmonic > state.terms) phaseHarmonicPair.set(state.terms);
    scheduleWaveUpdate();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('f0'),
  number: document.getElementById('f0-number'),
  onChange: (value) => {
    state.f0 = Math.round(value);
    if (osc && audio.ctx) rampParamLinear(osc.frequency, state.f0, audio.ctx);
    scheduleWaveUpdate();
    shell.scheduleRender();
  },
});

const phaseHarmonicPair = bindNumberPair({
  range: document.getElementById('phase-harmonic'),
  number: document.getElementById('phase-harmonic-number'),
  onChange: (value) => {
    state.editHarmonic = Math.round(value);
    phaseOffsetPair.set(degrees(state.phaseOffsets[state.editHarmonic] || 0));
    shell.scheduleRender();
  },
});

const phaseOffsetPair = bindNumberPair({
  range: document.getElementById('phase-offset'),
  number: document.getElementById('phase-offset-number'),
  onChange: (value) => {
    const radians = (value * Math.PI) / 180;
    if (radians === 0) delete state.phaseOffsets[state.editHarmonic];
    else state.phaseOffsets[state.editHarmonic] = radians;
    scheduleWaveUpdate();
    shell.scheduleRender();
  },
});

waveformSelect.addEventListener('change', () => {
  state.kind = waveformSelect.value;
  scheduleWaveUpdate();
  shell.scheduleRender();
});

phaseModeSelect.addEventListener('change', () => {
  state.phaseMode = phaseModeSelect.value;
  reshuffleButton.disabled = state.phaseMode !== 'random';
  scheduleWaveUpdate();
  shell.scheduleRender();
});

reshuffleButton.addEventListener('click', () => {
  state.phaseSeed += 1;
  scheduleWaveUpdate();
  shell.scheduleRender();
});

phaseClearButton.addEventListener('click', () => {
  state.phaseOffsets = {};
  phaseOffsetPair.set(0);
  scheduleWaveUpdate();
  shell.scheduleRender();
});

showHarmonicsBox.addEventListener('change', () => {
  state.showHarmonics = showHarmonicsBox.checked;
  shell.scheduleRender();
});

for (const radio of document.querySelectorAll('input[name="listen"]')) {
  radio.addEventListener('change', () => {
    if (!radio.checked) return;
    state.listen = radio.value;
    scheduleWaveUpdate();
    shell.scheduleRender();
  });
}

function updatePhaseHint() {
  const edited = Object.keys(state.phaseOffsets).length;
  const own = state.phaseOffsets[state.editHarmonic] || 0;
  phaseHint.textContent = `Harmonic ${state.editHarmonic} is turned by `
    + `${degrees(own)} degrees. ${edited === 0 ? 'No harmonic has been turned by hand.'
      : `${edited} harmonic${edited === 1 ? ' has' : 's have'} been turned by hand.`} `
    + 'Turning a harmonic never changes the bar chart.';
}

// ---------------------------------------------------------------- 起始

state.kind = waveformSelect.value;
state.phaseMode = phaseModeSelect.value;
state.showHarmonics = showHarmonicsBox.checked;
state.terms = clamp(Number(document.getElementById('terms').value), 1, MAX_TERMS);
state.f0 = Number(document.getElementById('f0').value);
reshuffleButton.disabled = state.phaseMode !== 'random';
termsPair.set(state.terms);

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。這一頁的圖仍然全部能用（它們不需要 AudioContext），
  // 所以說法與頻譜展示不同——那一頁沒有音訊就沒有內容，這一頁有一半。
  shell.showMessage(
    'This browser does not support the Web Audio API, so this page cannot play '
    + 'sound. Every graph below still works, but the part of this page that is '
    + 'about hearing phase will not. Try a recent version of Chrome, Firefox, '
    + 'Edge or Safari on a desktop computer.', 'warning',
  );
  document.querySelector('[data-shell="toggle"]').disabled = true;
}

shell.setSampleRate(null);
shell.scheduleRender();
