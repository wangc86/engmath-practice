// 展示頁的「載入 + 畫一次」冒煙測試（PLAN.md §8.9 那個一直沒補上的缺口）。
//
//     node scripts/run_demo_smoke.mjs fourier
//
// 印出一份 JSON，由 `tests/test_demos.py` 讀進去斷言。
//
// ============================================================================
// ⚠️ **先說清楚這支腳本不是什麼，因為它最大的風險就是被當成它不是的東西。**
//
// 它**不是**一個瀏覽器，也不是 §8.4 方案 C 的 `/demos/selftest` 的替代品。
// 它不畫任何像素、沒有 AudioContext、沒有真正的版面計算，
// 所以它證明不了「在 Chrome 上看起來對」。**跨瀏覽器實測（2S7）仍然欠著。**
//
// 它擋的是一件很窄、但也很致命的事：
//
// > **module 一載入就對 null 取屬性，或者 `render()` 第一次跑就丟例外。**
//
// 那一類錯誤的症狀是「一個完全沒有反應的畫面，而伺服器回 200」——
// 學生看不到任何訊息，`tests/test_demos.py` 的路由測試也全綠。
// §8.9 兩次都把它列為「兩件必須誠實說出來的事」的第一件，而在此之前
// 擋著它的只有「JS 抓的每個 id 都在頁面上」那一項很薄的替代品。
//
// **這支腳本與那一項互補，不重疊：**
//   * 那一項問「頁面上有沒有這個 id」——靜態的、由 HTML 那一側看。
//   * 這一支問「把整個 module 跑一遍會不會爆、跑完有沒有寫出東西」。
//
// ============================================================================
// 假 DOM 的三條紀律（否則它會變成一個會說謊的瀏覽器）
//
// 1. **元素的初始值從真的範本檔讀出來**，不是憑空捏的。滑桿的 min／max／value、
//    下拉選單選中的那個 option——全部來自 `app/templates/demos/<name>.html`。
//    捏一組值出來的話，「範本寫 value=5 而 JS 期待 value=50」這種不一致
//    就會被這支腳本蓋掉。
// 2. **不存在的東西就是不存在。** `window.AudioContext` 沒有、`matchMedia`
//    沒有，因此走的是「這個瀏覽器不支援 Web Audio」那條路徑——那條路徑
//    本來就該能跑（規則 4：圖仍然要能用），順便就驗到了。
// 3. **canvas 的 2d context 記錄呼叫次數，但不驗證任何幾何。** 幾何由
//    `tests/test_dsp_js.py` 對 `draw.js` 的純函式半邊斷言（§8.4：斷言資料，
//    不斷言像素）。這裡只回報「有沒有真的下過繪圖指令」——
//    一個什麼都沒畫的 `render()` 是一個很安靜的失敗。
// ============================================================================

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');

// ---------------------------------------------------------------- 範本的解析
//
// 一個很樸素的正規表示式掃描：找出每一個帶 id 的標籤，把它的屬性抓下來。
// 它不處理巢狀、不處理 Jinja——**而那正是它夠用的原因**：展示頁的控制項
// 全部是靜態 HTML，Jinja 只出現在 `{% include %}` 與 `{% block %}` 上。
// 有一天不夠用的時候，症狀是「少認出一個元素」，也就是誤報，不是漏報。

const TAG_WITH_ID = /<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g;
const ATTRIBUTE = /(\w[\w-]*)(?:="([^"]*)")?/g;

function parseAttributes(text) {
  const attributes = {};
  let match = ATTRIBUTE.exec(text);
  while (match !== null) {
    attributes[match[1]] = match[2] === undefined ? '' : match[2];
    match = ATTRIBUTE.exec(text);
  }
  ATTRIBUTE.lastIndex = 0;
  return attributes;
}

/** `<select id="x">` 選中的 option 的 value（沒有 selected 就取第一個）。 */
function selectedOption(html, id) {
  const block = new RegExp(`<select\\b[^>]*id="${id}"[^>]*>([\\s\\S]*?)</select>`);
  const found = block.exec(html);
  if (!found) return '';
  const options = [...found[1].matchAll(/<option\b([^>]*)>/g)]
    .map((m) => parseAttributes(m[1]));
  const chosen = options.find((o) => 'selected' in o) || options[0];
  return chosen ? (chosen.value ?? '') : '';
}

function parseTemplate(name) {
  const html = readFileSync(
    join(root, 'app', 'templates', 'demos', `${name}.html`), 'utf8',
  );
  // 共用外框是另一個檔案，元素靠 data-shell 認，所以一起讀進來。
  const shell = readFileSync(
    join(root, 'app', 'templates', 'demos', '_shell.html'), 'utf8',
  );
  const combined = `${html}\n${shell}`;

  const byId = new Map();
  let match = TAG_WITH_ID.exec(combined);
  while (match !== null) {
    const [, tag, attributeText, id] = match;
    const attributes = parseAttributes(attributeText);
    if (tag === 'select') attributes.value = selectedOption(combined, id);
    byId.set(id, { tag, attributes });
    match = TAG_WITH_ID.exec(combined);
  }
  TAG_WITH_ID.lastIndex = 0;

  const byShell = new Map();
  for (const m of combined.matchAll(/<(\w+)\b([^>]*\bdata-shell="([a-z-]+)"[^>]*)>/g)) {
    byShell.set(m[3], { tag: m[1], attributes: parseAttributes(m[2]) });
  }

  const canvasIds = [...combined.matchAll(/<canvas\b[^>]*id="([^"]+)"/g)].map((m) => m[1]);
  return { byId, byShell, canvasIds };
}

// ---------------------------------------------------------------- 假的 canvas

function makeContext(counters) {
  const noop = (name) => (...args) => { counters[name] = (counters[name] || 0) + 1; return args; };
  return {
    setTransform: noop('setTransform'),
    clearRect: noop('clearRect'),
    save: noop('save'),
    restore: noop('restore'),
    beginPath: noop('beginPath'),
    closePath: noop('closePath'),
    moveTo: noop('moveTo'),
    lineTo: noop('lineTo'),
    stroke: noop('stroke'),
    fill: noop('fill'),
    fillRect: noop('fillRect'),
    strokeRect: noop('strokeRect'),
    arc: noop('arc'),
    fillText: noop('fillText'),
    setLineDash: noop('setLineDash'),
    drawImage: noop('drawImage'),
    strokeStyle: '', fillStyle: '', lineWidth: 1, lineJoin: '',
    font: '', textAlign: '', textBaseline: '',
  };
}

// ---------------------------------------------------------------- 假的元素

class StubElement {
  constructor(tag, attributes = {}, shared = {}) {
    this.tagName = tag.toUpperCase();
    this.attributes = { ...attributes };
    this.dataset = {};
    this.style = {};
    this.children = [];
    this.listeners = new Map();
    this.shared = shared;
    this.textContent = '';
    this.className = attributes.class || '';
    this.hidden = 'hidden' in attributes;
    this.disabled = 'disabled' in attributes;
    this.checked = 'checked' in attributes;
    this.value = attributes.value ?? '';
    this.min = attributes.min ?? '';
    this.max = attributes.max ?? '';
    if (tag === 'canvas') {
      this.width = Number(attributes.width || 300);
      this.height = Number(attributes.height || 150);
      this._context = makeContext(shared.drawCalls || {});
    }
  }

  getContext() { return this._context; }

  // 版面：node 裡沒有版面，所以給一個固定的、合理的尺寸。
  // **不是量出來的**，因此這支腳本對版面問題完全沒有意見。
  getBoundingClientRect() {
    return { width: 900, height: Number(this.attributes.height || 200), top: 0, left: 0 };
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  removeEventListener() {}

  setAttribute(name, value) { this.attributes[name] = value; }

  getAttribute(name) { return this.attributes[name] ?? null; }

  appendChild(child) { this.children.push(child); return child; }

  removeChild(child) {
    this.children = this.children.filter((c) => c !== child);
    return child;
  }

  get firstChild() { return this.children[0] || null; }

  querySelector(selector) { return this.shared.lookup(selector); }

  querySelectorAll(selector) { return this.shared.lookupAll(selector); }

  /** 觸發一個事件，讓測試可以模擬使用者操作。 */
  fire(type, event = {}) {
    for (const handler of this.listeners.get(type) || []) {
      handler({ target: this, preventDefault() {}, ...event });
    }
  }
}

// ---------------------------------------------------------------- 假的 document

function buildEnvironment(name) {
  const template = parseTemplate(name);
  const drawCalls = {};
  const registry = new Map();
  const shellRegistry = new Map();
  const shared = { drawCalls };

  const make = (tag, attributes) => new StubElement(tag, attributes, shared);

  for (const [id, spec] of template.byId) {
    registry.set(id, make(spec.tag, { ...spec.attributes, id }));
  }
  for (const [role, spec] of template.byShell) {
    const element = spec.attributes.id
      ? registry.get(spec.attributes.id) || make(spec.tag, spec.attributes)
      : make(spec.tag, spec.attributes);
    shellRegistry.set(role, element);
    if (spec.attributes.id) registry.set(spec.attributes.id, element);
  }

  const layout = make('div', { class: 'layout demo-layout' });
  const canvases = template.canvasIds.map((id) => registry.get(id)).filter(Boolean);

  shared.lookup = (selector) => {
    const shellMatch = /^\[data-shell="([a-z-]+)"\]$/.exec(selector);
    if (shellMatch) return shellRegistry.get(shellMatch[1]) || null;
    if (selector === '.demo-layout' || selector === '.layout') return layout;
    const idMatch = /^#([\w-]+)$/.exec(selector);
    if (idMatch) return registry.get(idMatch[1]) || null;
    return null;
  };
  shared.lookupAll = (selector) => {
    if (selector === 'canvas') return canvases;
    const nameMatch = /^input\[name="(\w+)"\]$/.exec(selector);
    if (nameMatch) {
      // radio group：範本裡它們沒有 id，所以這裡照 name 現造一組。
      const group = shared.radios.get(nameMatch[1]) || [];
      return group;
    }
    return [];
  };

  // radio 沒有 id（它們是 name 群組），所以從範本原文另外抓一次。
  const html = readFileSync(
    join(root, 'app', 'templates', 'demos', `${name}.html`), 'utf8',
  );
  shared.radios = new Map();
  for (const m of html.matchAll(/<input\b([^>]*type="radio"[^>]*)>/g)) {
    const attributes = parseAttributes(m[1]);
    const element = make('input', attributes);
    if (!shared.radios.has(attributes.name)) shared.radios.set(attributes.name, []);
    shared.radios.get(attributes.name).push(element);
  }

  const documentStub = {
    hidden: false,
    body: layout,
    getElementById: (id) => registry.get(id) || null,
    querySelector: (selector) => shared.lookup(selector),
    querySelectorAll: (selector) => shared.lookupAll(selector),
    createElement: (tag) => make(tag, {}),
    addEventListener() {},
    removeEventListener() {},
  };

  // rAF：排進一個佇列，由 `drain()` 清掉。
  //
  // ⚠️ **第一版寫成「同步立刻執行」，而那讓這支腳本安靜地少測了一大半。**
  // `shell.js` 的 `scheduleRender()` 是
  //     `if (rafId) return; rafId = requestAnimationFrame(cb);`
  // 同步執行的話 `cb` 會在 `rafId = ...` 這個賦值**完成之前**就跑完並把
  // `rafId` 歸零，於是賦值把一個非零的 id 寫了回去——之後每一次
  // `scheduleRender()` 都直接 return，畫面再也不重畫。
  // 症狀是這支腳本只跑到第一次 render，而後面九個互動全部沒有畫面驗證，
  // 但輸出看起來完全正常（readouts 有值、沒有例外）。
  // 真的瀏覽器裡 rAF 是非同步的，所以這是**冒煙測試自己的 bug**，
  // 不是 `shell.js` 的——而它正是這一類假環境最典型的失真方式。
  const frames = { count: 0, queue: [], time: 0 };
  // 每個回呼配一個真的 id，`cancelAnimationFrame` 真的取消得掉。
  //
  // ⚠️ **第一版把 `cancelAnimationFrame` 寫成 no-op，而那讓這支腳本說了謊。**
  // `shell.js` 的 `stopLoop()` 是靠取消掉「tick 在開頭剛排好的下一格」來停的，
  // 而那正是「在迴圈的回呼裡面停掉迴圈」這個完全正常的用法
  // （2S10 的掃描走到底就停）。取消不掉的話，那一格照樣會跑，
  // 然後對已經被設成 null 的 `loopFn` 呼叫——**在真的瀏覽器裡不會發生的當機**。
  // 假環境的每一處偷懶都會變成一個假的紅燈或一個假的綠燈，這一次是前者。
  let nextFrameId = 1;
  globalThis.requestAnimationFrame = (fn) => {
    const id = nextFrameId;
    nextFrameId += 1;
    frames.queue.push({ id, fn });
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => {
    frames.queue = frames.queue.filter((entry) => entry.id !== id);
  };
  frames.drain = () => {
    // 迴圈而不是一次清空：`render()` 自己可能又排一格（`startLoop` 就是這樣），
    // 但也不能無限跑下去，所以設一個上限。
    let guard = 0;
    while (frames.queue.length > 0 && guard < 50) {
      const pending = frames.queue.splice(0, frames.queue.length);
      for (const { fn } of pending) {
        frames.count += 1;
        // ⚠️ **40 而不是 33，而這個差別被實際輸出抓到過。**
        // `shell.js` 的 `startLoop()` 節流條件是
        //     `if (now - lastFrameAt < 1000 / 30) return;`
        // 也就是 33.33 ms。時間每格只加 33 的話**每一格都會提早 return**，
        // 於是任何用 `startLoop()` 的東西（2S10 的自動掃描）在這支腳本裡
        // 一次都沒有跑過——而輸出看起來完全正常。
        // 這是本檔案開頭那句「假環境會安靜地測得比你以為的少」的第二個實例。
        frames.time += 40;
        fn(frames.time);
      }
      guard += 1;
    }
  };
  globalThis.document = documentStub;
  // ⛔ `window` 上刻意**沒有** AudioContext：走「不支援 Web Audio」那條路徑。
  globalThis.window = { devicePixelRatio: 2, addEventListener() {} };
  // `navigator` 在 node 22 上是唯讀的 getter，不能賦值——而展示區的
  // 這一頁本來也不碰它（麥克風那條路徑在 `lib/audio.js`，沒有呼叫者）。
  // 留這一行註解而不是留一段 try/catch，是因為「什麼都不做」在這裡是對的。

  return { registry, shellRegistry, drawCalls, frames, radios: shared.radios };
}

// ---------------------------------------------------------------- 互動腳本
//
// 每個展示載入之後要撥動哪些控制項。**選的是「會改變畫的東西」的那些**，
// 不是全部——這裡的目的是讓事件處理器與後續的 `render()` 真的跑過，
// 不是窮舉 UI。
//
// 三個展示都列出來，是因為 §8.9 對 2S3 與 2S4 也寫著同一句
// 「瀏覽器裡沒有實際跑過」——這支腳本補的那一小塊，對它們一樣有效。

const INTERACTIONS = {
  aliasing: [
    ['tone', { value: '4500' }, 'input'],
    ['rate', { value: '6000' }, 'input'],
    ['antialias', { checked: true }, 'change'],
    ['rate', { value: '400' }, 'input'],
  ],
  spectrum: [
    ['tone', { value: '1000' }, 'input'],
    ['fft-size', { value: '1024' }, 'change'],
    ['window', { value: 'rectangular' }, 'change'],
    ['zero-pad', { value: '4' }, 'change'],
    ['fmax', { value: '0' }, 'change'],
    ['db-axis', { checked: false }, 'change'],
    ['snap', {}, 'click'],
  ],
  fourier: [
    ['terms', { value: '31' }, 'input'],
    ['waveform', { value: 'sawtooth' }, 'change'],
    ['phase-mode', { value: 'random' }, 'change'],
    ['reshuffle', {}, 'click'],
    ['phase-harmonic', { value: '3' }, 'input'],
    ['phase-offset', { value: '90' }, 'input'],
    ['waveform', { value: 'triangle' }, 'change'],
    ['show-harmonics', { checked: false }, 'change'],
    ['f0', { value: '440' }, 'input'],
    ['waveform', { value: 'halfWave' }, 'change'],
    ['phase-mode', { value: 'series' }, 'change'],
    ['phase-clear', {}, 'click'],
    ['terms', { value: '1' }, 'input'],
    ['waveform', { value: 'square' }, 'change'],
  ],
  // 2S10。挑的是「會改變畫的東西」的那些控制項，特別是三個容易出事的地方：
  // 平移量掃到兩端（沒有重疊那條路徑）、輸入切到長度 1 的單一脈衝
  // （y 只有 h 那麼長，平移量的上界要跟著縮）、以及不翻轉那個開關。
  convolution: [
    ['shift', { value: '0' }, 'input'],
    ['response-shape', { value: 'repeat' }, 'change'],
    ['delay-taps', { value: '2' }, 'input'],
    ['length-taps', { value: '9' }, 'input'],
    ['shift', { value: '12' }, 'input'],
    ['flip', { checked: false }, 'change'],
    ['input-shape', { value: 'impulse' }, 'change'],
    ['shift', { value: '3' }, 'input'],
    ['response-shape', { value: 'average' }, 'change'],
    ['input-shape', { value: 'wiggle' }, 'change'],
    ['gain', { value: '0.95' }, 'input'],
    ['response-shape', { value: 'difference' }, 'change'],
    ['lti-system', { value: 'clip' }, 'change'],
    ['lti-system', { value: 'fade' }, 'change'],
    ['source', { value: 'pluck' }, 'change'],
    ['listen', { value: 'input' }, 'change'],
    ['delay-ms', { value: '25' }, 'input'],
    ['smooth-ms', { value: '0.2' }, 'input'],
    ['response-shape', { value: 'echo' }, 'change'],
    ['flip', { checked: true }, 'change'],
    ['sweep', {}, 'click'],
  ],
  // 2S11。挑的是「會改變畫的東西」的那些，特別是四個容易出事的地方：
  // 寬度掃到兩端（積分格點數的上下限都要碰到）、換成沒有零點的高斯
  // （`firstNull` 是 null 那條路徑）、把載波打開又關掉（播放可用性的
  // 切換，以及 |X| 從一個瓣變成兩個瓣）、以及把頻率軸換掉
  // （半功率標記會落到軸外，那是 `continue` 那一行）。
  pulse: [
    ['width', { value: '0.5' }, 'input'],
    ['shape', { value: 'gaussian' }, 'change'],
    ['width', { value: '20' }, 'input'],
    ['carrier-on', { checked: true }, 'change'],
    ['carrier', { value: '2000' }, 'input'],
    ['fmax', { value: '500' }, 'change'],
    ['shift', { value: '-4.5' }, 'input'],
    ['shape', { value: 'triangle' }, 'change'],
    ['fmax', { value: '8000' }, 'change'],
    ['shape', { value: 'cosine' }, 'change'],
    ['show-formula', { checked: false }, 'change'],
    ['carrier-on', { checked: false }, 'change'],
    ['shift', { value: '0' }, 'input'],
    ['shape', { value: 'rectangle' }, 'change'],
    ['width', { value: '8' }, 'input'],
  ],
};

// ---------------------------------------------------------------- 主流程

async function main() {
  const name = process.argv[2];
  if (!name) throw new Error('usage: node scripts/run_demo_smoke.mjs <demo name>');

  const env = buildEnvironment(name);
  const errors = [];
  const originalError = console.error;
  console.error = (...args) => { errors.push(args.map(String).join(' ')); };

  await import(`../app/static/demos/${name}.js`);
  env.frames.drain();

  // 載入之後再操作幾個控制項，讓事件處理器與後續的 render() 也走一遍。
  // 每一個都必須真的存在——`missing:` 就是範本與 JS 對不上，
  // 而測試會據此變紅，不是跳過。
  const interactions = [];
  const poke = ([id, changes, type]) => {
    const element = env.registry.get(id);
    if (!element) { interactions.push(`missing:${id}`); return; }
    Object.assign(element, changes);
    element.fire(type);
    env.frames.drain();
    interactions.push(`${type}:${id}`);
  };

  for (const step of INTERACTIONS[name] || []) poke(step);

  console.error = originalError;

  const readouts = {};
  for (const [id, element] of env.registry) {
    if (typeof element.textContent === 'string' && element.textContent !== '') {
      readouts[id] = element.textContent;
    }
  }

  const gibbs = env.registry.get('gibbs-rows');
  // 2S11 的寬度階梯。與上面那張表分開列，因為兩張表的欄位意義不同——
  // 共用一個鍵會讓「哪一張表沒有被填」這個問題答不出來。
  const widths = env.registry.get('width-rows');
  process.stdout.write(JSON.stringify({
    demo: name,
    frames: env.frames.count,
    drawCalls: env.drawCalls,
    readouts,
    consoleErrors: errors,
    interactions,
    gibbsRowCount: gibbs ? gibbs.children.length : 0,
    gibbsCells: gibbs
      ? gibbs.children.map((row) => row.children.map((cell) => cell.textContent))
      : [],
    widthRows: widths
      ? widths.children.map((row) => row.children.map((cell) => cell.textContent))
      : [],
    // 規則 4：不支援 Web Audio 時必須在畫面上留一句話，不得只寫 console。
    shellMessage: (env.shellRegistry.get('message') || {}).textContent || '',
    shellMessageHidden: (env.shellRegistry.get('message') || {}).hidden,
    toggleDisabled: (env.shellRegistry.get('toggle') || {}).disabled,
  }));
}

main();
