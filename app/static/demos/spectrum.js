// 展示 2：即時頻譜 + 視窗與洩漏（PLAN.md §8.2.1 第 2 列，路線圖 2S4）。
//
// **這是唯一知道 DOM、AudioContext 與使用者手勢的一層。**
// 這裡不放任何數值演算法——所有算數都在 signal.js／transform.js／draw.js，
// 因為 `tests/test_dsp_js.py` 只測得到那三層。
//
// 音訊圖：
//
//   OscillatorNode ─┐
//   AudioBufferSource ─┼─► sourceGain ─► analyser ─► master ─► destination
//   （內建範例或使用者的檔案）
//
// ⚠️ **AnalyserNode 在這裡只當一支「取時域樣本的探針」，它自己的 FFT 一格都
// 沒有用到。** 理由是 §8.3 那張表：`getFloatFrequencyData()` 內部**硬寫死
// Blackman 窗**，而這一頁有一半的教學內容就是切換視窗看旁瓣怎麼變——
// 用它等於這一格做不出來。`getFloatTimeDomainData()` 給的是未經加工的樣本，
// 那才是我們要的東西；窗、補零、FFT、正規化全部由 transform.js 自己做，
// 因此畫面上的每一個數字都在 `tests/test_dsp_js.py` 的斷言範圍內。
//
// ⛔ **使用者選的檔案完全不離開瀏覽器**（D28）。這一頁唯一的 fetch 是
// 「去伺服器拿內建的範例 wav」，方向是**下載**；檔案上傳的路徑在這裡不存在，
// 而且 `tests/test_demos.py` 有一組測試確認它不會偷偷長出來。

import { DemoAudio, AudioFailure, rampParamLinear } from './lib/audio.js';
import { createShell, bindNumberPair } from './lib/shell.js';
import { clamp, mixToMono, describeAudioBuffer } from './lib/signal.js';
import {
  spectrum, windowCoefficients, binSpacing, observationSeconds,
  nearestBinFrequency, findPeaks, interpolatePeakBin, toDecibels,
  nyquist,
} from './lib/transform.js';
import {
  makeScale, curvePoints, fitCanvas, clear, strokeAxes, strokePolyline,
  strokeAxisWithTicks, strokeVerticalMarker, fillUnderCurve, niceTicks,
  createSpectrogram, resampleMax, dbToUnit,
} from './lib/draw.js';

// ---------------------------------------------------------------- 常數

/** 內建範例的目錄。**這是這一頁唯一會被 fetch 的東西**（GET，靜態資產）。 */
const SAMPLE_PREFIX = '/static/demos/samples/';

/**
 * 使用者檔案的兩道上限。
 *
 * 大小的上限擋在**讀取之前**（`file.size` 不必讀檔就知道），長度的上限則
 * 只能在解碼之後才處理——`decodeAudioData` 沒有「只解前 N 秒」這種選項。
 * 兩者都不是靜默的：超過就在畫面上說出來（規則 4）。
 */
const MAX_FILE_BYTES = 40 * 1024 * 1024;
const MAX_SECONDS = 30;

/** dB 軸的範圍。−100 dB 已經在任何裝置的雜訊底下。 */
const DB_MIN = -100;
const DB_MAX = 0;

/** 線性軸固定 0…1，**不自動縮放**——自動縮放會讓「切視窗前後的高度」失去可比性。 */
const LINEAR_MAX = 1.0;

const PAD = { left: 44, right: 12, top: 12, bottom: 22 };
const WAVE_PAD = { left: 44, right: 12, top: 10, bottom: 10 };

// 線型與顏色並用（§8.6 第 4 點：顏色不得是唯一的訊息載體）。
const STYLE = {
  axis: '#c7ccd4',
  axisText: '#6b7280',
  wave: { color: '#1f4fd8', width: 1.5, dash: [] },
  window: { color: '#6b7280', width: 1.5, dash: [2, 4] },
  spectrumLine: { color: '#c2410c', width: 1.5, dash: [] },
  spectrumFill: { color: 'rgba(194, 65, 12, 0.18)' },
  marker: { color: '#111827', dash: [5, 4] },
};

// ---------------------------------------------------------------- 狀態

const state = {
  source: 'tone',        // 'tone' | 'sample' | 'file'
  tone: 440,             // Hz
  sample: null,          // 內建範例的檔名
  fftSize: 2048,
  windowName: 'hann',
  zeroPad: 1,
  fmax: 5000,            // 0 代表「到奈奎斯特為止」
  useDecibels: true,
  running: false,
  deviceRate: null,
  fileBuffer: null,      // 使用者檔案解碼並混成單聲道之後的 AudioBuffer
  fileName: null,
};

/** `prefers-reduced-motion` 時不自動捲動頻譜圖（§8.6 第 5 點）。 */
const reducedMotion = typeof matchMedia === 'function'
  && matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------------------------------------------------------------- DOM

const root = document.querySelector('.demo-layout');
const toneControls = document.getElementById('tone-controls');
const sampleControls = document.getElementById('sample-controls');
const fileControls = document.getElementById('file-controls');
const snapButton = document.getElementById('snap');
const snapHint = document.getElementById('snap-hint');
const sampleSelect = document.getElementById('sample');
const fileInput = document.getElementById('audio-file');
const fileStatus = document.getElementById('file-status');
const sizeSelect = document.getElementById('fft-size');
const windowSelect = document.getElementById('window');
const padSelect = document.getElementById('zero-pad');
const fmaxSelect = document.getElementById('fmax');
const dbCheckbox = document.getElementById('db-axis');
const outFs = document.getElementById('out-fs');
const outN = document.getElementById('out-n');
const outTime = document.getElementById('out-time');
const outSpacing = document.getElementById('out-spacing');
const outPeak = document.getElementById('out-peak');
const outOffset = document.getElementById('out-offset');
const verdict = document.getElementById('verdict');
const waveCanvas = document.getElementById('waveform');
const spectrumCanvas = document.getElementById('spectrum');
const spectrogramCanvas = document.getElementById('spectrogram');
const waveDescription = document.getElementById('waveform-description');
const spectrumDescription = document.getElementById('spectrum-description');
const spectrogramStep = document.getElementById('spectrogram-step');

// ---------------------------------------------------------------- 音訊

let analyser = null;
let sourceGain = null;
let currentNode = null;          // OscillatorNode 或 AudioBufferSourceNode
const sampleBuffers = new Map(); // 檔名 → AudioBuffer，解碼過一次就留著
let timeData = null;             // 重複使用的 Float32Array，避免每格配置
let latest = null;               // 最近一次的分析結果，render() 用

const audio = new DemoAudio({
  onFailure: (kind, message) => {
    shell.showMessage(message, kind === AudioFailure.MICROPHONE ? 'warning' : 'error');
    shell.setRunning(false);
    state.running = false;
    shell.stopLoop();
    shell.scheduleRender();
  },
  onStateChange: (running, reason) => {
    state.running = running;
    shell.setRunning(running);
    shell.setSampleRate(running ? audio.sampleRate : null);
    if (running && !reducedMotion) shell.startLoop(frame);
    if (!running) shell.stopLoop();
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
  if (analyser) return;
  const ctx = audio.ctx;
  sourceGain = ctx.createGain();
  sourceGain.gain.value = 1;
  analyser = ctx.createAnalyser();
  analyser.fftSize = state.fftSize;
  // 平滑會把相鄰幾格做指數平均，讓數字無法與解析解比對（§8.3 那張表的第三列）。
  // 這一頁的每一個讀數都要能被斷言，所以關掉它。
  analyser.smoothingTimeConstant = 0;
  sourceGain.connect(analyser).connect(audio.master);
}

/** 拆掉目前的音源。**一定要 disconnect**，否則就是 §8.2 說的孤兒節點。 */
function disposeSource() {
  if (!currentNode) return;
  try {
    currentNode.stop();
  } catch (err) {
    // 已經停過的節點再 stop 會丟 InvalidStateError；這不是錯誤，
    // 但按規則 4 仍然留一行，免得日後有別的原因掉進這裡而沒有人知道。
    console.warn('[spectrum] stopping the previous source node:', err);
  }
  currentNode.disconnect();
  currentNode = null;
}

async function loadSample(name) {
  if (sampleBuffers.has(name)) return sampleBuffers.get(name);
  // ⛔ 這是這一頁唯一的 fetch：GET 一個靜態資產。沒有 method、沒有 body。
  const response = await fetch(SAMPLE_PREFIX + name);
  if (!response.ok) {
    throw new Error(`sample ${name} responded with ${response.status}`);
  }
  const decoded = await audio.ctx.decodeAudioData(await response.arrayBuffer());
  sampleBuffers.set(name, decoded);
  return decoded;
}

function playBuffer(buffer) {
  const node = audio.ctx.createBufferSource();
  node.buffer = buffer;
  node.loop = true;
  node.connect(sourceGain);
  node.start();
  currentNode = node;
}

/** 依 state.source 重建音源。失敗一律有畫面訊息。 */
async function applySource() {
  if (!audio.ctx || !state.running) return;
  ensureGraph();
  disposeSource();

  if (state.source === 'tone') {
    const osc = audio.ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = state.tone;
    osc.connect(sourceGain);
    osc.start();
    currentNode = osc;
    return;
  }

  if (state.source === 'sample') {
    try {
      playBuffer(await loadSample(state.sample));
    } catch (err) {
      console.error('[spectrum] loading a built-in example failed:', err);
      shell.showMessage(
        'That built-in example could not be loaded or decoded. Reload the page; '
        + 'if it keeps happening, tell your instructor which browser you are '
        + 'using.', 'error',
      );
    }
    return;
  }

  // 'file'
  if (!state.fileBuffer) {
    shell.showMessage(
      'Choose an audio file below and it will start playing. Nothing is sent '
      + 'anywhere — the file is read on this computer.', 'notice',
    );
    return;
  }
  playBuffer(state.fileBuffer);
}

async function toggleSound() {
  if (state.running) {
    audio.stop();
    disposeSource();
    return;
  }
  shell.clearMessage();
  const ok = await audio.start();
  if (!ok) return;                    // 失敗訊息已經由 onFailure 放上畫面了
  state.deviceRate = audio.sampleRate;
  ensureGraph();
  await applySource();
  shell.scheduleRender();
}

// ---------------------------------------------------------------- 使用者的檔案
//
// **這一段是 D28 的全部。** 三個階段各有各的失敗，每一個都有畫面訊息：
//   1. 選檔之前   —— 檔案過大（讀都不讀）
//   2. 解碼       —— 格式不支援、檔案損毀、根本不是音訊
//   3. 解碼之後   —— 多聲道、太長、取樣率被瀏覽器改掉
// 沒有一條路徑會把資料送出去，也沒有一條路徑會安靜地什麼都不做。

function setFileStatus(text, kind = 'notice') {
  fileStatus.textContent = text;
  fileStatus.dataset.kind = kind;
}

async function handleFileChosen(file) {
  if (!file) {
    setFileStatus('No file chosen.');
    return;
  }
  const megabytes = file.size / (1024 * 1024);
  if (file.size > MAX_FILE_BYTES) {
    setFileStatus(
      `That file is ${megabytes.toFixed(0)} MB, and this page reads files up to `
      + `${MAX_FILE_BYTES / (1024 * 1024)} MB. Nothing was read. A shorter clip `
      + 'shows exactly the same things.', 'error',
    );
    return;
  }

  // AudioContext 必須在使用者手勢裡建立，而選檔就是一個手勢——所以
  // start() 要在任何 await 之前呼叫，不能等讀完檔案再開。
  const ok = await audio.start();
  if (!ok) return;
  ensureGraph();
  state.deviceRate = audio.sampleRate;

  setFileStatus(`Reading ${file.name} on this computer…`);
  let decoded;
  try {
    const bytes = await file.arrayBuffer();
    decoded = await audio.ctx.decodeAudioData(bytes);
  } catch (err) {
    console.error('[spectrum] decodeAudioData failed:', err);
    setFileStatus(
      `The browser could not decode ${file.name}. Either it is not an audio `
      + 'file, or it is in a format this browser cannot read — support for MP3, '
      + 'M4A, OGG and FLAC varies between browsers. A .wav file always works. '
      + 'The file was not sent anywhere.', 'error',
    );
    return;
  }

  const channels = [];
  for (let c = 0; c < decoded.numberOfChannels; c += 1) {
    channels.push(decoded.getChannelData(c));
  }
  const maxFrames = Math.round(MAX_SECONDS * decoded.sampleRate);
  const mono = mixToMono(channels, maxFrames);
  if (mono.length === 0) {
    setFileStatus(
      `${file.name} decoded to an empty signal, so there is nothing to analyse.`,
      'error',
    );
    return;
  }

  const buffer = audio.ctx.createBuffer(1, mono.length, decoded.sampleRate);
  buffer.copyToChannel(mono, 0);
  state.fileBuffer = buffer;
  state.fileName = file.name;

  setFileStatus(`${file.name} — ${describeAudioBuffer({
    sampleRate: decoded.sampleRate,
    channels: decoded.numberOfChannels,
    seconds: decoded.duration,
    keptSeconds: mono.length / decoded.sampleRate,
  })}`, 'ok');

  selectSource('file');
  await applySource();
  shell.scheduleRender();
}

// ---------------------------------------------------------------- 分析

function ensureTimeBuffer(n) {
  if (!timeData || timeData.length !== n) timeData = new Float32Array(n);
  return timeData;
}

/**
 * 一格：取時域樣本 → 算頻譜 → 畫。
 *
 * 這裡刻意只做「把資料交給下面三層」——這一層不算任何東西，
 * 所以 `latest` 裡的每一個數字都來自 transform.js，也就是都在測試的範圍內。
 */
function frame() {
  if (!analyser || !state.running) return;
  const n = state.fftSize;
  if (analyser.fftSize !== n) analyser.fftSize = n;
  const samples = ensureTimeBuffer(n);
  analyser.getFloatTimeDomainData(samples);

  const fs = state.deviceRate || audio.sampleRate;
  const padded = n * state.zeroPad;
  const result = spectrum(samples, { window: state.windowName, fs, padTo: padded });
  const peaks = findPeaks(result.amplitudes, 3).map((peak) => {
    const exact = interpolatePeakBin(result.amplitudes, peak.bin);
    return { ...peak, hz: (exact * fs) / padded };
  });
  latest = { samples, fs, result, peaks, n, padded };
  render();
}

// ---------------------------------------------------------------- 文字

const hz = (v) => (v >= 1000 ? `${(v / 1000).toFixed(2)} kHz` : `${v.toFixed(1)} Hz`);

function upperFrequency(fs) {
  return state.fmax === 0 ? nyquist(fs) : Math.min(state.fmax, nyquist(fs));
}

/** 一句給螢幕閱讀器的狀態播報（§8.6 第 2 點）。 */
function statusSentence() {
  if (!latest) return 'Press Start sound to begin.';
  const spacing = binSpacing(latest.n, latest.fs);
  const peak = latest.peaks[0];
  return `Window ${state.windowName}. Analysis length ${latest.n} samples, `
    + `bins ${spacing.toFixed(1)} hertz apart. `
    + (peak ? `Strongest peak at ${hz(peak.hz)}.` : 'No clear peak.');
}

/** Canvas 的文字替代是**算出來的**，不是靜態 alt（§8.6 第 3 點）。 */
function describeSpectrum() {
  if (!latest || latest.peaks.length === 0) {
    return 'No peaks stand out in the spectrum yet.';
  }
  const listed = latest.peaks
    .map((peak, index) => `${index === 0 ? 'Largest' : 'then a'} peak at `
      + `${hz(peak.hz)} at ${toDecibels(peak.value, DB_MIN).toFixed(0)} decibels`)
    .join(', ');
  return `${listed}.`;
}

function describeWaveform() {
  if (!latest) return 'No samples analysed yet.';
  const seconds = observationSeconds(latest.n, latest.fs);
  let peak = 0;
  for (let i = 0; i < latest.samples.length; i += 1) {
    const value = Math.abs(latest.samples[i]);
    if (value > peak) peak = value;
  }
  return `${latest.n} samples covering ${(seconds * 1000).toFixed(1)} milliseconds, `
    + `peaking at ${peak.toFixed(2)}, multiplied by a ${state.windowName} window.`;
}

/**
 * 這一頁的「判決句」。**它不先講結論**（規則 5 的分寸）——它只報告
 * 學生剛剛做出來的那個設定處在什麼狀態，結論留在 <details> 裡。
 */
function verdictSentence() {
  if (!latest) return 'Press Start sound to begin.';
  const spacing = binSpacing(latest.n, latest.fs);
  if (state.source !== 'tone') {
    return `Each bin covers ${spacing.toFixed(1)} Hz. Two frequencies closer `
      + 'together than that fall into the same bin.';
  }
  const centre = nearestBinFrequency(state.tone, latest.fs, latest.n);
  const offset = Math.abs(state.tone - centre);
  const fraction = offset / spacing;
  if (fraction < 0.02) {
    return `The tone sits on a bin centre (${hz(centre)}), so the whole tone `
      + 'fits into a whole number of cycles of the analysis window.';
  }
  return `The tone is ${offset.toFixed(1)} Hz from the nearest bin centre `
    + `(${hz(centre)}), which is ${fraction.toFixed(2)} of a bin.`;
}

// ---------------------------------------------------------------- 繪製

function drawWaveform() {
  const { width, height, ctx } = fitCanvas(waveCanvas, window.devicePixelRatio || 1);
  clear(ctx, width, height);
  if (!latest) return;
  const scale = makeScale({
    t0: 0, t1: latest.n - 1, vMin: -1.1, vMax: 1.1, width, height, pad: WAVE_PAD,
  });
  strokeAxes(ctx, scale, STYLE);

  // 視窗的包絡先畫（在底下），波形後畫。
  const coefficients = windowCoefficients(state.windowName, latest.n);
  const indices = new Float64Array(latest.n);
  for (let i = 0; i < latest.n; i += 1) indices[i] = i;
  strokePolyline(ctx, curvePoints(scale, indices, coefficients), STYLE.window);
  strokePolyline(ctx, curvePoints(scale, indices, latest.samples), STYLE.wave);
}

function drawSpectrum() {
  const { width, height, ctx } = fitCanvas(spectrumCanvas, window.devicePixelRatio || 1);
  clear(ctx, width, height);
  if (!latest) return;

  const top = upperFrequency(latest.fs);
  const vMin = state.useDecibels ? DB_MIN : 0;
  const vMax = state.useDecibels ? DB_MAX : LINEAR_MAX;
  const scale = makeScale({
    t0: 0, t1: top, vMin, vMax, width, height, pad: PAD,
  });

  const { frequencies, amplitudes } = latest.result;
  const xs = [];
  const ys = [];
  for (let k = 0; k < frequencies.length; k += 1) {
    if (frequencies[k] > top) break;
    xs.push(frequencies[k]);
    ys.push(state.useDecibels ? toDecibels(amplitudes[k], DB_MIN) : amplitudes[k]);
  }
  const points = curvePoints(scale, xs, ys);
  fillUnderCurve(ctx, points, scale.y(vMin), STYLE.spectrumFill);
  strokePolyline(ctx, points, STYLE.spectrumLine);

  if (state.source === 'tone' && state.tone <= top) {
    strokeVerticalMarker(ctx, scale, state.tone, STYLE.marker);
  }
  strokeAxisWithTicks(
    ctx, scale, niceTicks(top),
    (v) => (v >= 1000 ? `${v / 1000}k` : String(v)), STYLE,
  );
}

const spectrogram = createSpectrogram(spectrogramCanvas);

function pushSpectrogramColumn() {
  if (!latest) return;
  const ratio = window.devicePixelRatio || 1;
  const rect = spectrogramCanvas.getBoundingClientRect();
  spectrogram.resize(
    Math.max(1, Math.round(rect.width * ratio)),
    Math.max(1, Math.round(rect.height * ratio)),
  );
  const top = upperFrequency(latest.fs);
  const { frequencies, amplitudes } = latest.result;
  let cut = amplitudes.length;
  for (let k = 0; k < frequencies.length; k += 1) {
    if (frequencies[k] > top) { cut = k; break; }
  }
  const rows = Math.max(1, Math.round(rect.height * ratio));
  const visible = amplitudes.slice(0, cut);
  const reduced = resampleMax(visible, rows);
  const units = new Float64Array(rows);
  for (let i = 0; i < rows; i += 1) {
    units[i] = dbToUnit(toDecibels(reduced[i], DB_MIN), DB_MIN, DB_MAX);
  }
  spectrogram.push(units);
}

function render() {
  drawWaveform();
  drawSpectrum();
  if (!reducedMotion) pushSpectrogramColumn();

  if (latest) {
    outFs.textContent = `${Math.round(latest.fs)} Hz`;
    outN.textContent = state.zeroPad === 1
      ? `${latest.n}`
      : `${latest.n} samples, zero-padded to ${latest.padded}`;
    outTime.textContent = `${(observationSeconds(latest.n, latest.fs) * 1000).toFixed(1)} ms`;
    outSpacing.textContent = `${binSpacing(latest.n, latest.fs).toFixed(1)} Hz`;
    const peak = latest.peaks[0];
    outPeak.textContent = peak
      ? `${hz(peak.hz)} at ${toDecibels(peak.value, DB_MIN).toFixed(1)} dB`
      : 'none';
    if (state.source === 'tone' && peak) {
      const centre = nearestBinFrequency(state.tone, latest.fs, latest.n);
      outOffset.textContent = `${Math.abs(state.tone - centre).toFixed(1)} Hz`;
    } else {
      outOffset.textContent = '—';
    }
    waveDescription.textContent = describeWaveform();
    spectrumDescription.textContent = describeSpectrum();
  }
  verdict.textContent = verdictSentence();
  updateSnapHint();
  shell.announce(statusSentence());
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

function selectSource(kind) {
  state.source = kind;
  for (const radio of document.querySelectorAll('input[name="source"]')) {
    radio.checked = radio.value === kind;
  }
  toneControls.hidden = kind !== 'tone';
  sampleControls.hidden = kind !== 'sample';
  fileControls.hidden = kind !== 'file';
}

for (const radio of document.querySelectorAll('input[name="source"]')) {
  radio.addEventListener('change', async () => {
    if (!radio.checked) return;
    selectSource(radio.value);
    shell.clearMessage();
    await applySource();
    shell.scheduleRender();
  });
}

const tonePair = bindNumberPair({
  range: document.getElementById('tone'),
  number: document.getElementById('tone-number'),
  onChange: (value) => {
    state.tone = value;
    if (currentNode && currentNode.frequency) {
      rampParamLinear(currentNode.frequency, value, audio.ctx);
    }
    shell.scheduleRender();
  },
});

/**
 * 「把音調挪到最近的 bin 中心」。
 *
 * 這個按鈕是這一頁最重要的一個控制項：**洩漏這件事只有在「同一個音、
 * 只差半格」的對照下才看得出來**，而用滑桿手動對準一格是辦不到的
 * （步進 1 Hz，而格距通常是 23 Hz 之類的非整數）。
 */
function updateSnapHint() {
  if (!latest) {
    snapHint.textContent = 'Start the sound to see where the bin centres are.';
    return;
  }
  const centre = nearestBinFrequency(state.tone, latest.fs, latest.n);
  snapHint.textContent = `Bin centres near here are ${
    binSpacing(latest.n, latest.fs).toFixed(1)} Hz apart; the closest is ${
    hz(centre)}.`;
}

snapButton.addEventListener('click', () => {
  if (!latest) return;
  tonePair.set(Math.round(nearestBinFrequency(state.tone, latest.fs, latest.n)));
});

sampleSelect.addEventListener('change', async () => {
  state.sample = sampleSelect.value;
  selectSource('sample');
  await applySource();
});

fileInput.addEventListener('change', (event) => {
  const files = event.target.files;
  handleFileChosen(files && files.length > 0 ? files[0] : null);
});

sizeSelect.addEventListener('change', () => {
  state.fftSize = Number(sizeSelect.value);
  shell.scheduleRender();
});

windowSelect.addEventListener('change', () => {
  state.windowName = windowSelect.value;
  shell.scheduleRender();
});

padSelect.addEventListener('change', () => {
  state.zeroPad = Number(padSelect.value);
  shell.scheduleRender();
});

fmaxSelect.addEventListener('change', () => {
  state.fmax = Number(fmaxSelect.value);
  spectrogram.clear();
  shell.scheduleRender();
});

dbCheckbox.addEventListener('change', () => {
  state.useDecibels = dbCheckbox.checked;
  spectrogram.clear();
  shell.scheduleRender();
});

// reduced-motion：不自動捲動，改為按鍵推進（§8.6 第 5 點）。
if (reducedMotion) {
  spectrogramStep.hidden = false;
  spectrogramStep.addEventListener('click', () => {
    frame();
    pushSpectrogramColumn();
  });
}

// ---------------------------------------------------------------- 起始

state.sample = sampleSelect.value;
state.fftSize = Number(sizeSelect.value);
state.windowName = windowSelect.value;
state.zeroPad = Number(padSelect.value);
state.fmax = Number(fmaxSelect.value);
state.useDecibels = dbCheckbox.checked;
state.tone = clamp(Number(document.getElementById('tone').value), 50, 5000);
selectSource('tone');

if (!DemoAudio.supported) {
  // 規則 4：不得靜默無反應。這一頁**沒有音訊就完全沒有內容**（不像混疊展示
  // 還有圖可以看），所以這裡把話說滿，而不是說「圖仍然能用」。
  shell.showMessage(
    'This browser does not support the Web Audio API, so this page cannot '
    + 'analyse sound at all. Try a recent version of Chrome, Firefox, Edge or '
    + 'Safari on a desktop computer.', 'error',
  );
  document.querySelector('[data-shell="toggle"]').disabled = true;
  fileInput.disabled = true;
}

if (reducedMotion) {
  shell.showMessage(
    'Your system asks for reduced motion, so the spectrogram does not scroll on '
    + 'its own. Use the button under it to add one column at a time.', 'notice',
  );
}

shell.setSampleRate(null);
shell.scheduleRender();
