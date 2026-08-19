# `app/static/demos/` — 瀏覽器端展示的前端程式碼

規劃見 `PLAN.md` §8。這裡只寫「動手改的人必須先知道的四件事」。

---

## ⛔ 一、展示頁面內部**不使用 HTMX**

這是 §8.2 明文寫下的禁令，而且它會有人好意地「順手接上」，所以再寫一次。

HTMX 的模型是「伺服器回一段 HTML 片段換掉一塊 DOM」。展示頁持有兩個
**無法被序列化的東西**：canvas 的繪圖 context，與 AudioContext 的節點圖。
一次 `hx-swap` 就會把 canvas 換成一個新的空元素，舊的 `AudioWorkletNode`
變成無人引用但**仍在發聲**的孤兒。

症狀是「換頁之後還有聲音」或「圖不動了但沒有錯誤」——兩者都是硬規則 4
最討厭的那種靜默失敗。

HTMX 繼續用在展示**之間**的導覽與其他頁面（出題頁就是這樣用的）；
展示**之內**是純 JS。`tests/test_demos.py` 有一項測試斷言展示頁的 HTML
不含任何 `hx-` 屬性。

## 二、四段單向依賴，不得反向

```
lib/signal.js   ──┐
lib/transform.js ─┼──► 純函式：吃陣列吐陣列，不知道 DOM 與 AudioContext 存在
                  │
lib/draw.js ──────┘──► 吃 canvas + 資料 + 選項；不知道 UI 控制項存在

<demo>.js  ───────────► 唯一知道 DOM、AudioContext、與使用者手勢的一層
```

加上兩支基礎設施：`lib/audio.js`（音訊生命週期與四種失敗訊息）與
`lib/shell.js`（共用 UI 外框）。

**任何數值演算法都必須落在前三層**，因為 `tests/test_dsp_js.py` 只測得到那三層
（它用 node 直接 import 它們）。寫進 `<demo>.js` 的演算法等於沒有測試。

## 三、DOM 永遠不是真相的來源

狀態是一個普通物件 + 一個 `render()`。輸入事件只做一件事——寫進 `state`；
`render()` 只做一件事——把 `state` 畫到 canvas 與標籤上。

檢查方式很便宜：搜尋 `.value`，它應該**只出現在事件處理器與初始化裡**。

## 四、零建置：ES modules，不要 npm

`<script type="module" src="/static/demos/aliasing.js">`，模組之間用相對路徑
`import`。**不需要 npm、不需要 bundler、不需要 `package.json`**（D19）。

兩個要記住的性質：

* ES module 一律是 strict mode。
* **必須經 HTTP 提供**——`file://` 會被 CORS 擋掉。開發時要用 `uvicorn`，
  不能直接用瀏覽器開檔案。

Node **只是開發期**相依（`tests/test_dsp_js.py` 用它跑純函式層的斷言）。
**部署不需要裝 Node**——瀏覽器自己就是執行環境。

---

## 檔案

| 檔案 | 內容 |
|---|---|
| `lib/signal.js` | 正弦、取樣時刻、零階保持降取樣、畫面時間窗 |
| `lib/transform.js` | 奈奎斯特頻率、有號／無號混疊頻率。**還沒有 FFT**（排在 2S1，被 §7 #32 擋著） |
| `lib/draw.js` | 座標換算與路徑生成（純函式，可測）＋ 薄薄一層 canvas 指令 |
| `lib/audio.js` | `AudioContext` 生命週期、autoplay 解鎖、四種失敗的畫面訊息、參數斜坡 |
| `lib/shell.js` | Start/Stop、靜音、音量、取樣率讀數、aria-live 播報、RAF 合併重繪 |
| `worklets/sampler-processor.js` | 零階保持取樣器。**唯一的自訂 worklet**——其餘一律用原生節點 |
| `aliasing.js` | 混疊展示（2S3）。唯一知道 DOM 的一層 |
| `demos.css` | 展示專用樣式；一般頁面的樣式仍在 `app/static/style.css` |

## 新增一個展示

五個步驟。注意這裡**沒有註冊表機制**——`DEMOS` 就是一個 tuple，
刻意不做成 `app/generator/` 那套（D21：兩個功能區不共用抽象）。

1. **`app/routes/demos.py`**：在 `DEMOS` 加一個 `Demo(...)`。
   `template_id` 必須以 `demo.` 開頭（`UsageLog` 靠這個前綴把兩個功能區分開），
   而且**一旦寫進資料庫就不能再改**——它是穩定識別碼。
2. **`app/templates/demos/<名字>.html`**：`{% extends "base.html" %}`，
   `{% include "demos/_shell.html" %}` 取得共用外框，
   最後一行 `<script type="module" src="/static/demos/<名字>.js">`。
3. **`app/static/demos/<名字>.js`**：狀態物件 + `render()`。
   **數值演算法一律往 `lib/` 放**，這一層只做「讀控制項 → 寫 state → 呼叫下面三層」。
4. **`tests/test_dsp_js.py`**：新的純函式進 `scripts/run_dsp_case.mjs` 加一個 case，
   參考值**在 Python 這一側**用 SymPy 或閉合式現算。
5. **`tests/test_demos.py`**：把新頁面加進 `DEMO_PAGES`，那一整組「不說的話」
   與 HTMX 禁令的測試就自動涵蓋它了。

⚠️ 索引頁只列**現在真的點得進去**的展示（D24）。不要先把規劃中的項目加進 `DEMOS`
再標「coming soon」——有一項測試會攔住那個字。

## 介面語言

程式碼註解用繁體中文（開發文件語言），**但所有字串常值一律英文**（D5）——
它們會出現在學生的畫面上。`tests/test_demos.py` 會把註解剝掉之後掃過
整個目錄，確認沒有中日韓字元漏進字串裡。
