// 「這一頁在開始之前就死掉了」——把它說出來（硬規則 4）。
//
// ⛔ **這一支是在 v0.45 之後、老師回報「convolution 那個網頁壞了，沒有聲音
// 沒有波形按鈕也無反應」之後補上的。** 當時發生的事情是：展示的進入點模組
// 在**求值階段**就丟了例外，於是——
//
//   * `render()` 從來沒有被呼叫過 → 三張圖是空白的；
//   * 檔尾那一段 `addEventListener` 從來沒有跑到 → 按鈕全部沒有反應；
//   * `audio` 沒有被建立 → 沒有聲音；
//   * **而畫面上一個字都沒有。**
//
// ⚠️ 三個症狀看起來像三個問題，其實是同一個。**最糟的部分不是它壞了，
// 是它壞得沒有聲音**：老師只能說「壞了」，而沒有任何東西指出從哪裡開始查。
//
// ---
//
// ## 為什麼這是一個**獨立的**進入點，而不是寫在展示模組裡
//
// 與 D45(6) 完全同一個論證：**它要報的失敗，正好會讓那個檔案掛掉。**
// 寫在 `convolution.js` 裡的錯誤處理，在 `convolution.js` 求值失敗時
// 一行都不會執行——也就是最需要那句訊息的時候，那句訊息印不出來。
//
// ⚠️ **載入順序是這一支能不能動的全部關鍵**：`<script type="module">` 是
// 延後執行的，而多支 module 之間**依文件順序求值**。所以
// `_crash_notice.html` 必須出現在展示自己那支 `<script>` 的**前面**，
// 監聽器才會在展示求值之前就掛上去。有一項測試盯著這個順序
// （`test_the_crash_notice_is_wired_before_the_demo_module`）——⛔ 順序錯了
// 不會有任何症狀，直到真的有人壞掉的那一天，而那天它剛好不會說話。

/** 畫面上那個預設隱藏的段落。 */
const NOTICE_ID = 'demo-crash-notice';

/**
 * ⚠️ 這段話要對**學生**有用，不是對開發者有用。
 *
 * 排第一的是「硬重新整理」，因為到目前為止唯一真的發生過的成因就是它：
 * 瀏覽器手上是這一頁其中一個檔案的**舊版本**，而舊的 JS 配上新的 HTML
 * 會在啟動時就丟例外。⛔ 不寫「請開 devtools」——學生不會開，而且那句話
 * 等於把責任丟回去給看不懂的人。
 *
 * ⛔ 原始的錯誤訊息**要印出來**（而且不翻譯、不美化）：它是老師或助教唯一
 * 拿得到的線索，而學生有辦法把螢幕上的一行字念出來或拍下來。
 */
function sentence(detail) {
  return 'This page stopped working before it could start, so the buttons and '
    + 'the graphs on it will not do anything. First try a hard reload '
    + '(Ctrl+Shift+R, or Cmd+Shift+R on a Mac) — the usual cause is that the '
    + 'browser kept an old copy of one of this page’s files. If it still '
    + 'happens after a hard reload, tell your instructor and include this '
    + `line: ${detail}`;
}

function show(detail) {
  const notice = document.getElementById(NOTICE_ID);
  // ⚠️ 連這個段落都不在的話就只剩 console——但那是「範本也被改壞了」的情況，
  // 而規則 4 要求的是**盡力說出來**，不是「說不出來就假裝沒事」。
  if (!notice) {
    console.error('[demo] the page crashed and there is nowhere to say so:', detail);
    return;
  }
  // ⛔ 只報**第一個**。一個死掉的模組往往會連帶丟出好幾個
  //（例如之後每一次 rAF 都再丟一次），而把它們疊上去只會把第一句
  // ——也就是真正的成因——擠到看不見的地方。
  if (!notice.hidden) return;
  notice.textContent = sentence(detail);
  notice.hidden = false;
}

window.addEventListener('error', (event) => {
  // ⚠️ `error` 事件同時會被「某個 <img> 載不到」這種事觸發，而那不是這裡要管的
  // ——只有真的有例外物件（或訊息）的那一種才算。
  const detail = event.error
    ? `${event.error.name}: ${event.error.message}`
    : event.message;
  if (detail) show(detail);
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason;
  show(reason && reason.message ? `${reason.name}: ${reason.message}` : String(reason));
});
