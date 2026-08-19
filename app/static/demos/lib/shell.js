// 共用的展示外框（PLAN.md §8.2.3 的第二支基礎設施）。
//
// 每個展示都要的那幾件事，寫一次：
//   * Start/Stop 按鈕、靜音、音量（音訊安全，§8.5）
//   * 取樣率讀數（裝置決定，絕不寫死）
//   * 一個 aria-live 的狀態播報區（§8.6 第 2 點），更新有節流
//   * 一個顯示失敗訊息的區塊（規則 4：不得只寫 console）
//   * 鍵盤快捷鍵
//   * RAF 合併的重繪排程
//
// 對應的 HTML 在 `app/templates/demos/_shell.html`，元素靠 data-shell 屬性認。
//
// ⚠️ **與 §8 草案的一處落差：這裡沒有自由跑的 requestAnimationFrame 迴圈。**
// §8.2.3 寫的是「一個普通物件 + 一個 render() + 一個 RAF 迴圈」。混疊展示的
// 畫面**只在狀態改變時才需要重畫**（穩定的正弦畫出來是一張靜止的圖），
// 每秒 30 次重畫同一張圖只會讓手機發熱（§8.5 自己也要求控制重繪頻率）。
// 因此這裡提供的是 `scheduleRender()`：把同一個 frame 內的多次請求合併成一次。
// 需要連續動畫的展示（2S4 的捲動頻譜圖）再加一個真正的迴圈，
// 那時候這裡會多一個 `startLoop()`——**現在不先寫**，因為沒有呼叫者的程式碼會腐化。

const STATUS_THROTTLE_MS = 400;

export function createShell({ root, onToggle, onMuteChange, onVolumeChange }) {
  const el = (name) => root.querySelector(`[data-shell="${name}"]`);
  const toggleButton = el('toggle');
  const muteButton = el('mute');
  const volumeInput = el('volume');
  const rateReadout = el('rate');
  const messageBox = el('message');
  const statusRegion = el('status');

  let statusTimer = null;
  let pendingStatus = null;
  let lastStatusAt = 0;
  let rafId = 0;
  let renderFn = null;

  function setRunning(running) {
    toggleButton.textContent = running ? 'Stop sound' : 'Start sound';
    toggleButton.setAttribute('aria-pressed', running ? 'true' : 'false');
  }

  function setSampleRate(rate) {
    rateReadout.textContent = rate
      ? `Audio running at ${Math.round(rate)} Hz (set by your device)`
      : 'Audio not started';
  }

  /** 顯示一則訊息。kind 只影響樣式，訊息本身一律出現在畫面上。 */
  function showMessage(text, kind = 'error') {
    messageBox.textContent = text;
    messageBox.dataset.kind = kind;
    messageBox.hidden = false;
  }

  function clearMessage() {
    messageBox.textContent = '';
    messageBox.hidden = true;
  }

  /**
   * 螢幕閱讀器的狀態播報。節流是必要的——滑桿一拖就是每秒數十次，
   * 不節流的話螢幕閱讀器會被淹沒到完全不能用（§8.6 第 2 點）。
   */
  function announce(text) {
    pendingStatus = text;
    const now = Date.now();
    const wait = Math.max(0, STATUS_THROTTLE_MS - (now - lastStatusAt));
    if (statusTimer) return;
    statusTimer = setTimeout(() => {
      statusTimer = null;
      lastStatusAt = Date.now();
      if (statusRegion.textContent !== pendingStatus) {
        statusRegion.textContent = pendingStatus;
      }
    }, wait);
  }

  /** 把重繪排進下一個 frame；同一個 frame 內重複呼叫只會畫一次。 */
  function scheduleRender() {
    if (rafId || !renderFn) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      if (document.hidden) return;      // 背景分頁不該吃電池
      renderFn();
    });
  }

  function onRender(fn) {
    renderFn = fn;
  }

  toggleButton.addEventListener('click', () => onToggle());

  muteButton.addEventListener('click', () => {
    const muted = muteButton.getAttribute('aria-pressed') !== 'true';
    muteButton.setAttribute('aria-pressed', muted ? 'true' : 'false');
    muteButton.textContent = muted ? 'Unmute' : 'Mute';
    onMuteChange(muted);
  });

  volumeInput.addEventListener('input', () => {
    onVolumeChange(Number(volumeInput.value) / 100);
  });

  // 鍵盤快捷鍵：投影時老師的手不必離開鍵盤（§7 #35）。
  // 刻意不用空白鍵——它已經是「按下目前聚焦的按鈕」與「捲動頁面」了。
  document.addEventListener('keydown', (event) => {
    const tag = (event.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 's' || event.key === 'S') {
      event.preventDefault();
      onToggle();
    } else if (event.key === 'm' || event.key === 'M') {
      event.preventDefault();
      muteButton.click();
    }
  });

  // Canvas 尺寸自適應：容器變了就重畫（行動裝置轉向、視窗縮放）。
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(() => scheduleRender());
    root.querySelectorAll('canvas').forEach((canvas) => observer.observe(canvas));
  } else {
    window.addEventListener('resize', scheduleRender);
  }

  // 從背景分頁回來時補畫一次（在背景時我們刻意沒有畫）。
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) scheduleRender();
  });

  return {
    setRunning, setSampleRate, showMessage, clearMessage,
    announce, scheduleRender, onRender,
    get volume() { return Number(volumeInput.value) / 100; },
  };
}

/**
 * 綁定一組「滑桿 + 數字輸入框」，兩邊雙向同步。
 *
 * §8.6 第 1 點要求「不得有任何只能拖曳才能設定的值」——數字框同時解決了
 * 無障礙（鍵盤可輸入精確值）與行動裝置（手機上拖滑桿很難拖到準確位置）。
 * 兩個需求剛好同一個解法，所以這裡把它做成一個共用函式而不是各展示自己寫。
 */
export function bindNumberPair({ range, number, onChange }) {
  const apply = (value, source) => {
    const v = Number(value);
    if (!Number.isFinite(v)) return;
    const lo = Number(range.min);
    const hi = Number(range.max);
    const clamped = Math.min(hi, Math.max(lo, v));
    if (source !== range) range.value = String(clamped);
    if (source !== number) number.value = String(clamped);
    onChange(clamped);
  };
  range.addEventListener('input', () => apply(range.value, range));
  number.addEventListener('change', () => apply(number.value, number));
  return {
    set(value) { apply(value, null); },
  };
}
