// 展示 5：脈衝寬度與時頻取捨（PLAN.md §8.2.1 第 5 列，路線圖 2S11；課程 W4）。
//
// **這是唯一知道 DOM、AudioContext 與使用者手勢的一層。**
// 這裡不放任何數值演算法——脈衝與時寬在 signal.js、數值積分與閉合式在
// transform.js、幾何在 draw.js，因為 `tests/test_dsp_js.py` 只測得到那三層。
//
// 音訊圖（§8.5：能用原生節點就不要自己寫 worklet，這一頁一個都不用）：
//
//   AudioBufferSourceNode ─► playGain ─► master ─► destination
//   （buffer 裡裝的就是畫面上那個脈衝，重複播放）
//
// ============================================================================
// ⛔ **兩個座標軸的範圍都由使用者選，絕不自動縮放。這是這一頁最重要的一條。**
//
// 「自動把座標軸縮到剛好裝得下資料」是繪圖程式最常見、也最像好意的一個改動，
// 而在這一頁它會**把整頁的教學內容刪掉**：脈衝變窄的同時時間軸也跟著變窄，
// 於是脈衝看起來一樣寬；頻譜變寬的同時頻率軸也跟著變寬，於是頻譜看起來
// 一樣寬。兩張圖都還在動、都沒有報錯、每一個數字都仍然正確——
// 只是「窄與寬」這個唯一要看的東西不見了。
//
// 這正是規則 4 那類「安靜的失敗」在繪圖層的樣子，所以它寫在這裡，
// 而 `tests/test_dsp_js.py` 有一項盯著「同一個軸範圍下，脈衝變窄時
// 頻譜的半功率頻寬確實變大」。
// ============================================================================

import { DemoAudio } from './lib/audio.js';
import { createShell, bindNumberPair } from './lib/shell.js';
import {
  PULSE_SHAPES, UNCERTAINTY_BOUND, clamp, tracePulse, pulseSamples,
  pulseSupport, integrationSampleCount, spectrumPointCount, rmsWidths, pulseBurst,
} from './lib/signal.js';
import {
  fourierIntegral, analyticSpectrum, analyticSpectrumAt, pulseArea,
  firstNullFrequency, halfPowerBandwidth, maxAbsoluteGap,
} from './lib/transform.js';
import {
  makeScale, curvePoints, fitCanvas, clear, strokeAxes, strokePolyline,
  strokeAxisWithTicks, strokeVerticalMarker, markPoint, splitOnJumps, niceTicks,
} from './lib/draw.js';

// ---------------------------------------------------------------- 常數

/** 時間軸的固定半寬（秒）。**不隨脈衝寬度改變**，見檔頭。 */
const TIME_HALF_WINDOW = 0.025;

/** 音訊每隔多久重播一次脈衝。0.6 s 的譜線間隔是 1.67 Hz，見 `pulseBurst()`。 */
const REPEAT_SECONDS = 0.6;

/** 寬度階梯每一列是上一列的兩倍。四列剛好跨一個數量級。 */
const WIDTH_LADDER = [0.25, 0.5, 1, 2, 4];

const TIME_PAD = { left: 52, right: 14, top: 14, bottom: 24 };
const FREQ_PAD = { left: 62, right: 14, top: 14, bottom: 24 };

// 線型與顏色並用（§8.6 第 4 點：顏色不得是唯一的訊息載體）。
const STYLE = {
  axis: '#c7ccd4',
  axisText: '#6b7280',
  signal: { color: '#1f4fd8', width: 2.2, dash: [] },
  ghost: { color: '#94a3b8', width: 1.4, dash: [5, 4] },
  formula: { color: '#c2410c', width: 1.6, dash: [6, 4] },
  phase: { color: '#1f4fd8', width: 1.8, dash: [] },
  mark: '#c2410c',
  marker: '#94a3b8',
};

// ---------------------------------------------------------------- 狀態

const state = {
  shape: 'rectangle',
  width: 0.008,          // 秒（畫面上以毫秒表示）
  shift: 0,              // 秒
  carrierOn: false,
  carrierHz: 880,
  fmax: 2000,            // Hz
  showFormula: true,
  running: false,
  deviceRate: null,
};

// ---------------------------------------------------------------- DOM

const root = document.querySelector('.demo-layout');
const shapeSelect = document.getElementById('shape');
const carrierBox = document.getElementById('carrier-on');
const fmaxSelect = document.getElementById('fmax');
const showFormulaBox = document.getElementById('show-formula');
const soundNote = document.getElementById('sound-note');
const outWidth = document.getElementById('out-width');
const outArea = document.getElementById('out-area');
const outNull = document.getElementById('out-null');
const outBandwidth = document.getElementById('out-bandwidth');
const outProduct = document.getElementById('out-product');
const outUncertainty = document.getElementById('out-uncertainty');
const outShift = document.getElementById('out-shift');
const outAgreement = document.getElementById('out-agreement');
const verdict = document.getElementById('verdict');
const timeCanvas = document.getElementById('time-canvas');
const magnitudeCanvas = document.getElementById('magnitude-canvas');
const phaseCanvas = document.getElementById('phase-canvas');
const timeDescription = document.getElementById('time-description');
const magnitudeDescription = document.getElementById('magnitude-description');
const phaseDescription = document.getElementById('phase-description');
const widthRows = document.getElementById('width-rows');
const widthCaption = document.getElementById('width-caption');
const derivation = document.getElementById('derivation');
const repeatNote = document.getElementById('repeat-note');

// ---------------------------------------------------------------- 模型

/** 目前的訊號參數。**只有這一個地方組出它**，三張圖與聲音全部吃它。 */
function options() {
  return {
    width: state.width,
    shift: state.shift,
    carrierHz: state.carrierOn ? state.carrierHz : 0,
  };
}

/** 頻率軸上的取值點，含負頻率——實訊號的頻譜是偶的，而看得到它是偶的很重要。 */
function frequencyAxis(points) {
  const axis = new Float64Array(points);
  for (let i = 0; i < points; i += 1) {
    axis[i] = -state.fmax + (2 * state.fmax * i) / (points - 1);
  }
  return axis;
}

/**
 * 一次算完這一格畫面要的所有東西。
 *
 * ⚠️ 這裡故意**算三條頻譜**：數值積分的、閉合式的、以及「假裝沒有平移」
 * 的閉合式。第三條是為了那個「位移沒有動到幅度譜」的讀數——
 * 拿它與第二條比，兩者的幅度必須逐點相同。
 * 少了它，那句話就只能用嘴巴講。
 */
function model() {
  const opts = options();
  const count = integrationSampleCount({
    shape: state.shape, width: state.width, carrierHz: opts.carrierHz,
  });
  const axis = frequencyAxis(spectrumPointCount(count));
  const { values, dt, tStart } = pulseSamples(state.shape, opts, count);
  const numeric = fourierIntegral(values, dt, tStart, axis);
  const closed = analyticSpectrum(state.shape, opts, axis);
  const unshifted = analyticSpectrum(state.shape, { ...opts, shift: 0 }, axis);

  // ⚠️ **峰值用求值求出來，不是用「面積除以二」算出來的**，而這個差別
  // 是被測試抓到的。調變的等式 ½[X(f−f_c) + X(f+f_c)] 是精確的，
  // 但那兩份拷貝**會相加**——矩形的旁瓣以 1/f 衰減，下邊帶在
  // f = +f_c 那裡還剩下 ½X(2f_c)。T = 4 ms 配 900 Hz 的載波時，
  // 上邊帶的峰值是面積的一半**再少 2.6%**。
  //
  // 寫死 area/2 的後果有三個，而三個都很安靜：縱軸的頂端與曲線對不上、
  // 讀數印出一個比實際高 2.6% 的高度、而「數值積分與閉合式的差距」
  // 那一列因為分母不對而整列偏低。在這一格求值一次就全部避掉了。
  const centre = opts.carrierHz > 0 ? opts.carrierHz : 0;
  const peak = analyticSpectrumAt(state.shape, opts, centre).magnitude;
  const idealPeak = pulseArea(state.shape, state.width) * (opts.carrierHz > 0 ? 0.5 : 1);
  return {
    idealPeak,
    opts,
    axis,
    numeric,
    closed,
    samples: count,
    dt,
    peak,
    // 兩個「把一句話變成一個數字」的量，見 `maxAbsoluteGap()`。
    shiftGap: maxAbsoluteGap(closed.magnitude, unshifted.magnitude),
    agreement: maxAbsoluteGap(numeric.magnitude, closed.magnitude) / (peak || 1),
    bandwidth: halfPowerBandwidth(state.shape, state.width),
    firstNull: firstNullFrequency(state.shape, state.width),
    widths: rmsWidths(state.shape, state.width),
  };
}

// ---------------------------------------------------------------- 音訊

let playGain = null;
let currentNode = null;
let rebuildTimer = 0;

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
    if (!running) disposeSource();
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
    // 已經停過的節點再 stop 會丟 InvalidStateError；不是錯誤，但按規則 4
    // 仍然留一行，免得日後有別的原因掉進這裡而沒有人知道。
    console.warn('[pulse] stopping the previous source node:', err);
  }
  currentNode.disconnect();
  currentNode = null;
}

/**
 * 把目前的脈衝算成一段可迴圈播放的 buffer，接上去播。
 *
 * ⚠️ **正規化用的是脈衝本身的峰值，而峰值恆為 1**（包絡的峰值是 1，
 * 載波不會超過它），所以這裡的 0.7 是一個固定的音量係數，不是一次
 * 「每次都拉到滿」的自動增益。差別是實際的：自動增益會讓「脈衝變窄了、
 * 能量變少了」在耳朵裡消失，而畫面上的面積還在——就是 2S5 為了
 * `disableNormalization` 與 2S10 為了不用 `ConvolverNode` 打過的同一場仗。
 */
function rebuildSound() {
  if (!audio.ctx || !state.running) return;
  ensureGraph();
  const rate = audio.sampleRate;
  state.deviceRate = rate;

  const burst = pulseBurst(rate, {
    shape: state.shape,
    width: state.width,
    carrierHz: state.carrierOn ? state.carrierHz : 0,
    seconds: REPEAT_SECONDS,
  });
  const level = 0.7;
  for (let i = 0; i < burst.length; i += 1) burst[i] *= level;

  const buffer = audio.ctx.createBuffer(1, burst.length, rate);
  buffer.copyToChannel(burst, 0);

  disposeSource();
  const node = audio.ctx.createBufferSource();
  node.buffer = buffer;
  node.loop = true;
  node.connect(playGain);
  node.start();
  currentNode = node;
  shell.scheduleRender();
}

/** 連續拖滑桿時把重建合併起來——每一格都建一個新的 buffer 是浪費。 */
function scheduleSoundUpdate() {
  if (!state.running) return;
  if (rebuildTimer) clearTimeout(rebuildTimer);
  rebuildTimer = setTimeout(() => {
    rebuildTimer = 0;
    rebuildSound();
  }, 140);
}

async function toggleSound() {
  if (state.running) {
    audio.stop();
    return;
  }
  shell.clearMessage();
  const ok = await audio.start();
  if (!ok) return;                 // 失敗訊息已經由 onFailure 放上畫面了
  rebuildSound();
  shell.scheduleRender();
}

/**
 * 沒有載波時**停用播放並說出原因**。
 *
 * 這不是一個失敗，是這一頁的一項內容：一個坐在 0 Hz 的脈衝不是聲音。
 * 安靜地播一段靜音才是規則 4 禁止的那種事。
 */
function syncSoundAvailability() {
  const toggle = document.querySelector('[data-shell="toggle"]');
  if (!DemoAudio.supported) return;         // 那一條路徑已經停用過按鈕了
  const ready = state.carrierOn;
  toggle.disabled = !ready;
  soundNote.textContent = ready
    ? `Sound repeats this pulse every ${Math.round(REPEAT_SECONDS * 1000)} ms `
      + 'at the carrier frequency below. Headphones are recommended.'
    : 'Sound is off because the pulse on its own is centred at 0 Hz, which is '
      + 'not something you can hear. Switch on the carrier to move it into the '
      + 'audible range.';
  if (!ready && state.running) audio.stop();
}

// ---------------------------------------------------------------- 文字

const hz = (v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(2)} kHz` : `${v.toFixed(1)} Hz`);
const ms = (seconds) => `${(seconds * 1000).toPrecision(3)} ms`;

/**
 * 固定小數位，而且**不印出「負零」**。
 *
 * 這一頁到處都在報「恰好是零」的數字（位移造成的幅度變化、
 * 相鄰兩條曲線的差距），而 `(-1e-17).toFixed(3)` 是 `"-0.000"`——
 * 讀起來像「有一點點，而且是負的」，正好是它想否定的意思。
 * 2S10 記過同一件事，這裡是第二個實例。
 */
function fixed(v, digits = 3) {
  const text = v.toFixed(digits);
  return text === `-${(0).toFixed(digits)}` ? (0).toFixed(digits) : text;
}

/**
 * 一個「小到只是捨入」的量該怎麼講。
 *
 * ⛔ **不得寫 "exactly 0"**：位移那一條在 float64 裡是 1e−18 上下，
 * 而這一頁整頁在教「殘差是一個量」。2S10 為同一句話改過一次，
 * 理由與那次逐字相同。
 */
function residualText(value, unit) {
  if (Math.abs(value) < 1e-12) return `0${unit}, to rounding`;
  return `${value.toExponential(1)}${unit}`;
}

function shapeOf() {
  return PULSE_SHAPES[state.shape];
}

/** 一句給螢幕閱讀器的狀態播報（§8.6 第 2 點）。 */
function statusSentence(data) {
  const parts = [
    `${shapeOf().label} pulse, width ${ms(state.width)}, `
    + `half-power bandwidth ${hz(data.bandwidth)}.`,
  ];
  if (data.firstNull !== null) {
    parts.push(`The spectrum first crosses zero at ${hz(data.firstNull)}.`);
  } else {
    parts.push('This spectrum never crosses zero.');
  }
  if (state.shift !== 0) {
    parts.push(`Shifted by ${ms(state.shift)}, which leaves the magnitude alone.`);
  }
  if (state.carrierOn) parts.push(`Moved to ${hz(state.carrierHz)} by the carrier.`);
  return parts.join(' ');
}

/** Canvas 的文字替代是**算出來的**，不是靜態 alt（§8.6 第 3 點）。 */
function describeTime(data) {
  const support = 2 * pulseSupport(state.shape, state.width);
  const parts = [
    `A ${shapeOf().label.toLowerCase()} pulse of width ${ms(state.width)}, drawn `
    + `on a fixed window ${ms(2 * TIME_HALF_WINDOW)} wide, so the pulse gets `
    + 'narrower on the screen as you reduce the width.',
  ];
  if (!shapeOf().finiteSupport) {
    parts.push(`It never reaches zero; the part above the noise is about `
      + `${ms(support)} wide.`);
  }
  if (state.shift !== 0) {
    parts.push(`It is centred ${ms(state.shift)} away from the middle, and the `
      + 'dashed outline shows where it would sit with no shift.');
  }
  if (state.carrierOn) {
    parts.push(`Inside the pulse the signal oscillates at ${hz(state.carrierHz)}.`);
  }
  parts.push(`The tallest point of the spectrum is ${fixed(data.peak * 1000, 3)} `
    + 'in units of milliseconds'
    + (state.carrierOn ? '.' : ', which is the area under the pulse.'));
  return parts.join(' ');
}

function describeMagnitude(data) {
  const centre = state.carrierOn ? `two lobes centred at plus and minus ${hz(state.carrierHz)}`
    : 'a single lobe centred at zero frequency';
  const parts = [
    `The magnitude of the transform across ${hz(-state.fmax)} to ${hz(state.fmax)}: `
    + `${centre}, half-power bandwidth ${hz(data.bandwidth)}.`,
  ];
  if (data.firstNull !== null) {
    parts.push(`The first zero of each lobe is ${hz(data.firstNull)} away from its centre, `
      + 'and the sidelobes beyond it get smaller.');
  } else {
    parts.push('There are no zeros and no sidelobes: it falls away smoothly.');
  }
  parts.push('The numerical integral and the closed form differ by at most '
    + `${(data.agreement * 100).toPrecision(2)} percent of the peak.`);
  return parts.join(' ');
}

function describePhase(data) {
  if (state.shift === 0) {
    return 'The phase of the transform. With no time shift it is flat, stepping '
      + 'between 0 and 180 degrees wherever the transform changes sign.';
  }
  const slope = -360 * state.shift;
  return 'The phase of the transform, wrapped into plus or minus 180 degrees. '
    + `The time shift of ${ms(state.shift)} makes it a straight ramp of slope `
    + `${slope.toFixed(1)} degrees per hertz, which wraps round every `
    + `${hz(1 / Math.abs(state.shift))}. The magnitude above did not move at all: `
    + `it changed by ${residualText(data.shiftGap, '')}.`;
}

/**
 * 這一頁的「判決句」。**它不先講結論**（規則 5 的分寸）——它報告學生剛剛
 * 做出來的那個設定處在什麼狀態，結論留在 <details> 裡。
 */
function verdictSentence(data) {
  const bits = [
    `This ${shapeOf().label.toLowerCase()} pulse, ${ms(state.width)} wide, has a `
    + `half-power bandwidth of ${hz(data.bandwidth)}.`,
  ];
  if (data.widths.product === null) {
    bits.push('Its RMS bandwidth is not finite, because its edges are jumps and '
      + `its sidelobes only die away like ${shapeOf().tails}.`);
  } else {
    const over = data.widths.product / UNCERTAINTY_BOUND;
    bits.push(`Its RMS spread is ${fixed(data.widths.product, 4)}, which is `
      + `${over < 1.0005 ? 'exactly' : `${fixed(over, 3)} times`} the lower bound `
      + `of ${fixed(UNCERTAINTY_BOUND, 4)}.`);
  }
  if (state.shift !== 0) {
    bits.push(`Shifting it by ${ms(state.shift)} changed the magnitude by `
      + `${residualText(data.shiftGap, '')}.`);
  }
  return bits.join(' ');
}

// ---------------------------------------------------------------- 寬度階梯

/**
 * 「把脈衝變窄，頻譜會怎樣？」——這張表就是答案。
 *
 * 四欄放在一起是刻意的：前三欄各自都會變，而**最後一欄不動**。
 * 少了最後一欄，這張表只說「兩個數字都在變」，那不是一個關係。
 */
function fillWidthTable() {
  while (widthRows.firstChild) widthRows.removeChild(widthRows.firstChild);
  for (const factor of WIDTH_LADDER) {
    const width = state.width * factor;
    const nullAt = firstNullFrequency(state.shape, width);
    const bandwidth = halfPowerBandwidth(state.shape, width);
    const row = document.createElement('tr');
    if (factor === 1) row.className = 'is-current';
    const cells = [
      ms(width),
      nullAt === null ? 'none' : hz(nullAt),
      hz(bandwidth),
      // ⚠️ **有效位數，不是固定小數位。** 2S5 的第三欄踩過這個坑：
      // `toFixed(2)` 會把「每次減半」四捨五入掉，而那一欄恰好就是論點。
      // 這裡反過來——這一欄必須看起來**完全不動**，所以位數要夠多，
      // 多到讀者相信它真的是同一個數字而不是四捨五入的結果。
      (bandwidth * width).toPrecision(6),
    ];
    for (const text of cells) {
      const cell = document.createElement('td');
      cell.textContent = text;
      row.appendChild(cell);
    }
    widthRows.appendChild(row);
  }
  widthCaption.textContent =
    `${shapeOf().label} pulse: each row is twice as wide as the one above it. `
    + 'The first three columns all change. Read the last one down the page.';
}

// ---------------------------------------------------------------- 繪製

function drawTime(data) {
  const { width, height, ctx } = fitCanvas(timeCanvas, window.devicePixelRatio || 1);
  // ⛔ 固定視窗，見檔頭。
  const scale = makeScale({
    t0: -TIME_HALF_WINDOW, t1: TIME_HALF_WINDOW,
    vMin: -1.15, vMax: 1.15, width, height, pad: TIME_PAD,
  });
  const count = clamp(Math.round(width * 6), 600, 9000);

  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  // 沒有平移的那一份，虛線。它讓「東西往右移了多少」在圖上是量得出來的。
  if (state.shift !== 0) {
    const ghost = tracePulse(
      state.shape, { ...data.opts, shift: 0 },
      -TIME_HALF_WINDOW, TIME_HALF_WINDOW, count,
    );
    strokePolyline(ctx, curvePoints(scale, ghost.times, ghost.values), STYLE.ghost);
  }

  const trace = tracePulse(
    state.shape, data.opts, -TIME_HALF_WINDOW, TIME_HALF_WINDOW, count,
  );
  strokePolyline(ctx, curvePoints(scale, trace.times, trace.values), STYLE.signal);

  strokeAxisWithTicks(
    ctx, scale,
    [-0.02, -0.01, 0, 0.01, 0.02],
    (v) => `${Math.round(v * 1000)} ms`,
    STYLE,
  );
}

function drawMagnitude(data) {
  const { width, height, ctx } = fitCanvas(magnitudeCanvas, window.devicePixelRatio || 1);
  // ⛔ **橫軸固定，見檔頭——那一條沒有例外。**
  //
  // ⚠️ **縱軸則相反：它跟著目前的峰值縮放，而這是一個有代價的取捨，
  //    寫下來以免日後被當成疏漏。** 峰值就是脈衝下的面積，跨越滑桿的
  //    兩端是 40 倍；縱軸若也固定，最窄的那個脈衝的頻譜會變成貼在
  //    底線上的一條漣漪，形狀、零點、旁瓣全部看不見——而那三樣東西
  //    才是這張圖的內容。
  //
  //    代價是「脈衝變窄、頻譜也變矮」這一半在圖上看不出來。補償的方式
  //    是把它變成一個數字：讀數列有「f = 0 處的高度」，而那一列與
  //    「脈衝下的面積」是同一個值——頁面上明講了這件事。
  //    **橫軸與縱軸的處理不一樣，是因為它們承載的東西不一樣**：
  //    橫軸上那件事沒有第二個出口，縱軸上那件事有。
  const top = data.peak * 1.08;
  const scale = makeScale({
    t0: -state.fmax, t1: state.fmax, vMin: 0, vMax: top,
    width, height, pad: FREQ_PAD,
  });

  clear(ctx, width, height);

  if (state.showFormula) {
    strokePolyline(ctx, curvePoints(scale, data.axis, data.closed.magnitude), STYLE.formula);
  }
  strokePolyline(ctx, curvePoints(scale, data.axis, data.numeric.magnitude), STYLE.signal);

  // 半功率的兩個點。它們是那個「B」在圖上的位置，不標的話那一列讀數
  // 就只是一個沒有落點的數字。
  const centres = state.carrierOn ? [-state.carrierHz, state.carrierHz] : [0];
  const half = data.bandwidth / 2;
  for (const centre of centres) {
    for (const side of [-1, 1]) {
      const f = centre + side * half;
      if (Math.abs(f) > state.fmax) continue;
      markPoint(ctx, { x: scale.x(f), y: scale.y(data.peak * Math.SQRT1_2) }, {
        color: STYLE.mark,
      });
    }
  }
  if (data.firstNull !== null) {
    for (const centre of centres) {
      for (const side of [-1, 1]) {
        const f = centre + side * data.firstNull;
        if (Math.abs(f) > state.fmax) continue;
        strokeVerticalMarker(ctx, scale, f, { color: STYLE.marker });
      }
    }
  }

  const ticks = niceTicks(state.fmax, 4);
  const both = ticks.filter((v) => v > 0).map((v) => -v).reverse().concat(ticks);
  strokeAxisWithTicks(ctx, scale, both, (v) => `${Math.round(v)} Hz`, STYLE);
}

function drawPhase(data) {
  const { width, height, ctx } = fitCanvas(phaseCanvas, window.devicePixelRatio || 1);
  const scale = makeScale({
    t0: -state.fmax, t1: state.fmax, vMin: -Math.PI, vMax: Math.PI,
    width, height, pad: FREQ_PAD,
  });
  clear(ctx, width, height);
  strokeAxes(ctx, scale, STYLE);

  // 相位是繞回來的，所以要在跳點切開——否則每一次繞過 ±π 都會畫出一條
  // 幾乎垂直的假線，而學生要看的斜率就被那些線蓋掉了。
  const points = curvePoints(scale, data.axis, data.numeric.phase);
  const maxRise = Math.abs(scale.y(0) - scale.y(Math.PI));
  for (const segment of splitOnJumps(points, maxRise)) {
    strokePolyline(ctx, segment, STYLE.phase);
  }

  const ticks = niceTicks(state.fmax, 4);
  const both = ticks.filter((v) => v > 0).map((v) => -v).reverse().concat(ticks);
  strokeAxisWithTicks(ctx, scale, both, (v) => `${Math.round(v)} Hz`, STYLE);
}

function updateDerivation(data) {
  const spec = shapeOf();
  const probe = data.firstNull !== null ? data.firstNull / 2 : data.bandwidth;
  const numericAt = closestSample(data.axis, data.numeric.magnitude, probe);
  const closedAt = closestSample(data.axis, data.closed.magnitude, probe);
  derivation.textContent =
    `Right now the integral runs over ${data.samples} sample points spaced `
    + `${(data.dt * 1e6).toPrecision(3)} microseconds apart. At ${hz(probe)} the `
    + `numerical integral gives ${numericAt.toPrecision(6)} and the closed form `
    + `gives ${closedAt.toPrecision(6)}, both in units of seconds. The tails of `
    + `this shape fall away like ${spec.tails}, which is the same statement as `
    + `"the pulse ${spec.continuous ? 'has no jump in it' : 'has a jump at each edge'}".`;
}

/** 找出最接近某個頻率的那一格的值。讀數用，不影響任何繪製。 */
function closestSample(axis, values, target) {
  let best = 0;
  let bestGap = Infinity;
  for (let i = 0; i < axis.length; i += 1) {
    const gap = Math.abs(axis[i] - target);
    if (gap < bestGap) { bestGap = gap; best = i; }
  }
  return values[best];
}

// ---------------------------------------------------------------- render

function render() {
  const data = model();

  drawTime(data);
  drawMagnitude(data);
  drawPhase(data);
  fillWidthTable();
  updateDerivation(data);

  outWidth.textContent = ms(state.width);
  // ⚠️ 沒有載波時這一列**就是**脈衝下的面積，說出來是有用的：頻譜的高度
  // 就是面積，那是「變窄也變矮」的全部內容。有載波時它**不完全是**
  // 面積的一半，而那個差額本身是一句話：兩份拷貝疊在一起了。
  outArea.textContent = state.carrierOn
    ? `${(data.peak * 1000).toPrecision(4)} ms, against `
      + `${(data.idealPeak * 1000).toPrecision(4)} ms for half the area — the two `
      + 'sidebands overlap a little'
    : `${(data.peak * 1000).toPrecision(4)} ms, which is the area under the pulse`;
  outNull.textContent = data.firstNull === null
    ? 'no zero: this shape never crosses'
    : `${hz(data.firstNull)} from the centre`;
  outBandwidth.textContent = hz(data.bandwidth);
  outProduct.textContent = (data.bandwidth * state.width).toPrecision(6);
  outUncertainty.textContent = data.widths.product === null
    ? `not finite for this shape (tails fall off like ${shapeOf().tails})`
    : `${fixed(data.widths.product, 4)} against a floor of `
      + `${fixed(UNCERTAINTY_BOUND, 4)}`;
  outShift.textContent = state.shift === 0
    ? 'no shift applied'
    : residualText(data.shiftGap, '');
  outAgreement.textContent = `${(data.agreement * 100).toPrecision(2)}% of the peak`;

  repeatNote.textContent = `${Math.round(REPEAT_SECONDS * 1000)} ms`;
  verdict.textContent = verdictSentence(data);
  timeDescription.textContent = describeTime(data);
  magnitudeDescription.textContent = describeMagnitude(data);
  phaseDescription.textContent = describePhase(data);
  shell.announce(statusSentence(data));
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

bindNumberPair({
  range: document.getElementById('width'),
  number: document.getElementById('width-number'),
  onChange: (value) => {
    state.width = value / 1000;
    scheduleSoundUpdate();
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('shift'),
  number: document.getElementById('shift-number'),
  onChange: (value) => {
    state.shift = value / 1000;
    // ⚠️ 平移**不影響聲音**：延遲一段每 600 ms 重複的聲音，聽起來完全一樣。
    // 所以這裡刻意不呼叫 scheduleSoundUpdate()——重建一次 buffer 只會
    // 讓播放接縫跳一下，而學生會以為那個「喀」是位移造成的。
    shell.scheduleRender();
  },
});

bindNumberPair({
  range: document.getElementById('carrier'),
  number: document.getElementById('carrier-number'),
  onChange: (value) => {
    state.carrierHz = value;
    scheduleSoundUpdate();
    shell.scheduleRender();
  },
});

shapeSelect.addEventListener('change', () => {
  state.shape = shapeSelect.value;
  scheduleSoundUpdate();
  shell.scheduleRender();
});

carrierBox.addEventListener('change', () => {
  state.carrierOn = carrierBox.checked;
  syncSoundAvailability();
  scheduleSoundUpdate();
  shell.scheduleRender();
});

fmaxSelect.addEventListener('change', () => {
  state.fmax = Number(fmaxSelect.value);
  shell.scheduleRender();
});

showFormulaBox.addEventListener('change', () => {
  state.showFormula = showFormulaBox.checked;
  shell.scheduleRender();
});

// ---------------------------------------------------------------- 起始

state.shape = shapeSelect.value;
state.fmax = Number(fmaxSelect.value);
state.carrierOn = carrierBox.checked;
state.showFormula = showFormulaBox.checked;
state.width = Number(document.getElementById('width').value) / 1000;
state.shift = Number(document.getElementById('shift').value) / 1000;
state.carrierHz = Number(document.getElementById('carrier').value);

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。這一頁的圖全部不需要 AudioContext，所以
  // 說法與頻譜展示不同——那一頁沒有音訊就沒有內容，這一頁只少了一格。
  shell.showMessage(
    'This browser does not support the Web Audio API, so this page cannot play '
    + 'sound. Every graph below still works, and only the part about hearing a '
    + 'short pulse is lost. Try a recent version of Chrome or Firefox on a '
    + 'desktop computer.', 'warning',
  );
  document.querySelector('[data-shell="toggle"]').disabled = true;
  soundNote.textContent = 'Sound is not available in this browser.';
} else {
  syncSoundAvailability();
}

shell.setSampleRate(null);
shell.scheduleRender();
