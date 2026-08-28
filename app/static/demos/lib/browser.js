// 瀏覽器支援偵測（PLAN.md D45）。
//
// **這一支的存在理由與 `audio.js` 完全相同：硬規則 4（不許靜默失敗）。**
// 老師決定官方只支援 Chrome 與 Firefox，理由是 macOS 上裝得到 Chrome。
// 而「不支援」若只寫在文件或首頁上，Safari 的學生會遇到的是：
// **頁面看起來完全正常、按鈕按得下去、圖畫得出來，只是聲音不對或沒有聲音**
// ——而他會以為是自己的耳機。這正是規則 4 說的「沒印出來等同沒有人知道」。
//
// ---------------------------------------------------------------------------
// ⚠️ 為什麼是**兩層**偵測，而不是只做能力偵測
// ---------------------------------------------------------------------------
//
// 老師的指示是「優先用能力偵測而非瀏覽器名稱偵測」，那個方向是對的，
// 但它單獨**擋不住 Safari**，理由要寫清楚，否則日後有人會把第二層刪掉：
//
//   * **現代 Safari 有 `AudioWorklet`、有 `createPeriodicWave`、有 `AudioParam`
//     的斜坡方法。** 能力偵測問的是「這個 API 在不在」，而 Safari 的問題是
//     「它在，但行為不一樣」——分歧在實作，不在介面。
//   * 因此**純能力偵測在 Safari 上會全部通過**，然後學生照樣聽到錯的聲音。
//
// 反過來，只做瀏覽器名稱偵測也不夠：
//
//   * UA 字串會過時、會被偽裝、會因為新瀏覽器出現而漏判。
//   * 而且它**看不到真正的失敗**：一個很舊的 Chrome 沒有 `AudioWorklet`，
//     名稱偵測會說「這是 Chrome，沒問題」，然後畫面一樣安靜地壞掉。
//     ⚠️ **非安全脈絡（http:// 加上非 localhost）也屬於這一類**——
//     `AudioWorklet` 在那裡根本取不到（D43），而瀏覽器名稱一個字都沒變。
//
// **所以兩層各自擋住對方擋不到的一半，職責分開：**
//
//   | 層 | 問的問題 | 失敗時 | 過期風險 |
//   |---|---|---|---|
//   | 1. 能力偵測 | 這個展示要用的 API 在不在？ | **error**（真的動不了） | 幾乎沒有——它問的是執行期的事實 |
//   | 2. 引擎判定 | 這是我們測過的引擎嗎？ | **warning**（可能安靜地不對） | ⚠️ 有，見下 |
//
// ---------------------------------------------------------------------------
// ⚠️ 第二層刻意寫成**白名單**（正面認出 Chromium 或 Gecko），不是黑名單
// ---------------------------------------------------------------------------
//
// 「認出 Safari 就警告」與「認不出 Chromium／Gecko 就警告」在今天結果相同，
// 但**失效的方向相反**，而這才是選擇的理由：
//
//   * 黑名單漏掉一個引擎 → **沒有訊息**，學生聽到錯的聲音卻不知道。（安靜）
//   * 白名單誤判一個其實沒問題的瀏覽器 → **多一句訊息**，學生被叫去裝 Chrome。（吵）
//
// 我們寧可吵。這與本專案在別處的取捨一致（`test_every_fetch_...` 那一項的
// 註解寫的是同一句話：誤報的代價是回來看一眼，漏報的代價是沒有人知道）。
//
// ❓ **誠實地說一次**：下面這些判準沒有一條在真的 Safari 上跑過。
// 判斷邏輯寫成純函式並由 `tests/test_dsp_js.py` 用固定的 UA 樣本做正反案例，
// 但**樣本是我抄下來的字串，不是我從一台 Mac 上讀到的**。

/** 引擎的判定結果。字串本身會寫進 `data-engine`，方便日後查頁面截圖。 */
export const Engine = {
  CHROMIUM: 'chromium',
  GECKO: 'gecko',
  OTHER: 'other',
};

/**
 * 這個功能區真的會用到的 Web Audio 能力。
 *
 * ⚠️ **只列真的在用的東西。** 列一個沒有人呼叫的 API 進來，它就會在某天
 * 某個瀏覽器上把一個其實跑得動的頁面擋掉——而那種錯誤沒有人查得出來。
 * （`IIRFilterNode` 因此不在這裡：Demo 6 還沒有寫。）
 *
 * `label` 是**給學生看的**，所以是英文而且不帶 `window.` 前綴。
 */
export const REQUIRED_CAPABILITIES = [
  {
    key: 'webAudio',
    label: 'Web Audio',
    present: (scope) => Boolean(scope.AudioContext || scope.webkitAudioContext),
  },
  {
    key: 'audioWorklet',
    label: 'AudioWorklet',
    // 兩個都要：建構子（建節點用）與 context 上那個 worklet 容器（載模組用）。
    // ⚠️ 只檢查 `AudioWorkletNode` 是不夠的——非安全脈絡下規格說的是
    // `BaseAudioContext.audioWorklet` 取不到（D43），而那正是我們要抓的情況。
    present: (scope) => typeof scope.AudioWorkletNode === 'function'
      && hasOnPrototype(scope, 'audioWorklet'),
  },
  {
    key: 'periodicWave',
    label: 'createPeriodicWave',
    present: (scope) => typeof scope.PeriodicWave === 'function'
      && hasOnPrototype(scope, 'createPeriodicWave'),
  },
  {
    key: 'analyser',
    label: 'AnalyserNode',
    present: (scope) => typeof scope.AnalyserNode === 'function',
  },
  {
    key: 'audioParamRamps',
    label: 'AudioParam ramps',
    present: (scope) => {
      const proto = scope.AudioParam && scope.AudioParam.prototype;
      if (!proto) return false;
      return AUDIO_PARAM_METHODS.every((name) => typeof proto[name] === 'function');
    },
  },
];

/** `audio.js` 真的呼叫到的那幾個。少一個就有一條路徑會拋例外。 */
const AUDIO_PARAM_METHODS = [
  'setValueAtTime',
  'linearRampToValueAtTime',
  'exponentialRampToValueAtTime',
  'setTargetAtTime',
  'cancelScheduledValues',
];

/** `AudioContext.prototype`（或 webkit 版）上有沒有某個成員。 */
function hasOnPrototype(scope, name) {
  const ctor = scope.AudioContext || scope.webkitAudioContext;
  return Boolean(ctor && ctor.prototype && name in ctor.prototype);
}

/**
 * 哪些能力不在。回傳的是 `REQUIRED_CAPABILITIES` 裡的 `key`，順序照原表。
 *
 * @param {object} scope 一個 window 樣子的物件（測試會餵假的進來）
 */
export function missingCapabilities(scope) {
  if (!scope) return REQUIRED_CAPABILITIES.map((c) => c.key);
  return REQUIRED_CAPABILITIES.filter((c) => !c.present(scope)).map((c) => c.key);
}

/** key → 給學生看的英文名字。 */
export function capabilityLabel(key) {
  const found = REQUIRED_CAPABILITIES.find((c) => c.key === key);
  return found ? found.label : key;
}

/**
 * 認引擎。**白名單**：認得出 Chromium 或 Gecko 才算支援，其餘一律 `OTHER`。
 *
 * 三個判準，刻意由「最不會過期」排到「最會過期」：
 *
 *   1. `navigator.userAgentData.brands`——⚠️ **這是 Chromium 專屬的 API**，
 *      Firefox 與 Safari 都沒有實作它，所以它出現本身就幾乎是一個結論。
 *      而且它是結構化資料，不是要用正則去剖的字串。
 *   2. `CSS.supports('-moz-appearance', ...)`——`-moz-` 前綴只有 Gecko 認得。
 *      同樣是問「你做得到什麼」而不是「你叫什麼名字」。
 *   3. UA 字串——最後的退路。⚠️ **這一條一定會過期**，它在這裡只是為了讓
 *      前兩條都失手時不要把 Chrome／Firefox 誤判成 `OTHER`。
 *
 * ⚠️ Safari 的 UA 裡有 `like Gecko)` 與 `Safari/`，所以 Gecko 那條用的是
 * `Gecko/<數字>`（Firefox 的 `Gecko/20100101`），不是裸的 `Gecko`。
 * 這個差別很細但它就是整條判準的成敗，動它之前先看測試裡那幾個樣本。
 *
 * @param {object} env `{ userAgent, userAgentData, supportsCss }`
 */
export function identifyEngine(env) {
  const source = env || {};

  const brands = source.userAgentData && Array.isArray(source.userAgentData.brands)
    ? source.userAgentData.brands
    : null;
  if (brands && brands.some((b) => b && /chromium/i.test(b.brand || ''))) {
    return Engine.CHROMIUM;
  }

  const supportsCss = typeof source.supportsCss === 'function'
    ? source.supportsCss
    : () => false;
  if (supportsCss('-moz-appearance', 'none')) return Engine.GECKO;

  const ua = typeof source.userAgent === 'string' ? source.userAgent : '';
  // Gecko 要先判：Firefox 的 UA 裡沒有 `Chrome/`，但這個順序讓意圖看得清楚。
  if (/\bGecko\/\d/.test(ua) && /\bFirefox\/\d/.test(ua)) return Engine.GECKO;
  if (/\b(?:Chrome|Chromium|CriOS|Edg|EdgA)\/\d/.test(ua)) return Engine.CHROMIUM;

  return Engine.OTHER;
}

/** 引擎支援與否。白名單：只有這兩個。 */
export function isSupportedEngine(engine) {
  return engine === Engine.CHROMIUM || engine === Engine.GECKO;
}

// ---------------------------------------------------------------------------
// 訊息
//
// ⚠️ **措辭有三條硬性限制，改字之前先讀完：**
//
//   1. **英文**（D5）。
//   2. **不得出現任何「未來會支援」的字眼**——沒有 "yet"、"coming soon"、
//      "will be added"、"planned"。D45 是一條決定，不是一個待辦事項；
//      寫成待辦就是給了一個沒有人打算兌現的承諾。
//      `tests/test_demos.py` 的 `test_pages_do_not_advertise_what_is_missing`
//      已經盯著那幾個詞，這裡再多守一個 "yet"。
//   3. ⚠️ **不得變成變相的功能清單**（D24 的張力）。D24 禁的是「陳列現在
//      有哪些功能、哪些待補」，而這裡說的是**執行這一頁需要什麼**——
//      那是一個前提條件，不是進度表。分界線很實際：這段話**不提任何展示的
//      名字、不提任何題型、不提任何數量**，只提瀏覽器。
// ---------------------------------------------------------------------------

/** 引擎不在白名單上。**這是 Safari 會看到的那一句。** */
export const UNSUPPORTED_ENGINE_MESSAGE =
  'These demo pages are built for Chrome and Firefox. In other browsers, '
  + 'including Safari, the page looks the same but the sound can be wrong or '
  + 'silent. Open this page in Chrome or Firefox.';

/** 能力真的缺了。`{missing}` 會被換成缺的那幾個名字。 */
export const MISSING_CAPABILITY_TEMPLATE =
  'This browser cannot run the audio on these pages: {missing} is not '
  + 'available. Open this page in Chrome or Firefox.';

/**
 * ⚠️ 這一句是 D43 在畫面上的樣子。
 *
 * `AudioWorklet` 只在安全脈絡（https，或 localhost）下取得到，而症狀
 * 與「瀏覽器太舊」一模一樣。分不出來的話，老師會去查瀏覽器版本，
 * 而問題其實在網址列上。
 */
export const INSECURE_CONTEXT_HINT =
  ' This also needs a secure connection: check that the address starts '
  + 'with https.';

/**
 * 算出該顯示什麼。沒有問題時回 `null`。
 *
 * 兩層同時有話要說時，**能力那一層優先**：它是「真的動不了」，
 * 而引擎那一層是「可能安靜地不對」。同時印兩段話會讓人只讀第一段。
 *
 * @param {object} input `{ missing, engine, secureContext }`
 * @returns {null | {level: string, text: string, reason: string}}
 */
export function supportNotice(input) {
  const { missing = [], engine = Engine.OTHER, secureContext = true } = input || {};

  if (missing.length > 0) {
    const names = missing.map(capabilityLabel);
    const listed = names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
    let text = MISSING_CAPABILITY_TEMPLATE.replace('{missing}', listed);
    if (!secureContext) text += INSECURE_CONTEXT_HINT;
    return { level: 'error', text, reason: 'capability' };
  }

  if (!isSupportedEngine(engine)) {
    return { level: 'warning', text: UNSUPPORTED_ENGINE_MESSAGE, reason: 'engine' };
  }

  return null;
}

/**
 * 從一個真的 window 上把 `supportNotice()` 要的東西讀出來。
 *
 * 分成這一支的理由：上面全部是純函式（測得到），而讀 `navigator` 這件事
 * 測不到。界線劃在這裡，測試就涵蓋得到所有的判斷邏輯。
 */
export function inspect(scope) {
  const nav = (scope && scope.navigator) || {};
  const css = scope && scope.CSS;
  return {
    missing: missingCapabilities(scope || {}),
    engine: identifyEngine({
      userAgent: nav.userAgent,
      userAgentData: nav.userAgentData,
      supportsCss: (property, value) => Boolean(
        css && typeof css.supports === 'function' && css.supports(property, value),
      ),
    }),
    secureContext: scope ? scope.isSecureContext !== false : true,
  };
}
