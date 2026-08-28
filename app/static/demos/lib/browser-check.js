// 把 `browser.js` 的判斷結果放到畫面上（PLAN.md D45）。
//
// ⚠️ **這一支刻意是一個獨立的進入點，不是從 `aliasing.js` 之流裡呼叫的。**
// 理由是它要擋的東西正好會讓那些檔案掛掉：如果某個 API 不在，展示的
// module 很可能在載入途中就拋例外而中止——**於是最需要那句訊息的時候，
// 那句訊息反而印不出來**。獨立的 `<script type="module">` 各自載入、
// 各自失敗，所以這一支跑不跑得起來與展示本身無關。
//
// 它也刻意不碰 `shell.js` 的訊息區：那一區是音訊執行期的失敗在用的
// （按了 Start 之後才會有東西），而這一句要在**還沒按任何東西之前**就在。

import { inspect, supportNotice } from './browser.js';

const target = document.getElementById('browser-notice');

if (target) {
  const notice = supportNotice(inspect(window));
  if (notice) {
    target.textContent = notice.text;
    target.dataset.kind = notice.level;
    target.dataset.reason = notice.reason;
    target.hidden = false;
  }
}
