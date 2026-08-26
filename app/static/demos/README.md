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
| `lib/signal.js` | 正弦、取樣時刻、零階保持降取樣、畫面時間窗；**Fourier 級數的目標波形、部分和、吉布斯過衝與最大差距、`PeriodicWave` 的兩張表** |
| `lib/transform.js` | 奈奎斯特與混疊頻率；**FFT（vendored + 教學用 radix-2）**、視窗函數、幅度／dB、頻率軸標定、補零、峰值；**Fourier 級數的係數（$a_n$／$b_n$／$c_n$）、相位方案、帶限裁切** |
| `lib/draw.js` | 座標換算與路徑生成（純函式，可測）、viridis 色階、刻度、頻譜圖、**係數長條圖** ＋ 薄薄一層 canvas 指令 |
| `lib/audio.js` | `AudioContext` 生命週期、autoplay 解鎖、四種失敗的畫面訊息、參數斜坡 |
| `lib/shell.js` | Start/Stop、靜音、音量、取樣率讀數、aria-live 播報、RAF 合併重繪、30 fps 連續迴圈 |
| `worklets/sampler-processor.js` | 零階保持取樣器。**唯一的自訂 worklet**——其餘一律用原生節點 |
| `aliasing.js` | 混疊展示（2S3）。唯一知道 DOM 的一層 |
| `spectrum.js` | 頻譜／視窗／洩漏展示（2S4）。同上；另含**使用者檔案的純瀏覽器端處理**（D28） |
| `fourier.js` | Fourier 級數的加法合成展示（2S5）。同上；音訊是**一個 `OscillatorNode` + `setPeriodicWave`**，不是 N 個振盪器疊加（`OscillatorNode` 沒有相位參數，而這一頁一半的內容就是控制相位） |
| `samples/*.wav` | 內建範例音檔（D29）。由 `scripts/make_demo_samples.py` 產生，**不要手改** |
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
5. **`tests/test_demos.py`**：把新頁面加進 `DEMO_PAGES` 與 `DEMO_ENTRY_POINTS`，
   在 `REVEALS` 裡寫明它有幾個 `<details>`，那一整組「不說的話」與 HTMX 禁令的
   測試就自動涵蓋它了。
6. **`scripts/run_demo_smoke.mjs`**：在 `INTERACTIONS` 裡加一組「載入之後要撥動
   哪些控制項」，並把名字加進 `tests/test_demos.py` 第 8 組的 parametrize。
   這一步不能省——它是目前唯一會**真的執行**那支 JS 的東西。

### ⚠️ 兩個地方特別容易漏

* **數值演算法一律往 `lib/` 放。** 寫進 `<demo>.js` 的算法等於沒有測試。
  但反過來也要注意：**格式化住在 `<demo>.js`，而格式化也會說謊**——
  2S5 的對照表就曾經用 `toFixed(2)` 把「每次減半」四捨五入掉。
  抓到它的是冒煙測試，不是任何一項數值測試。
* **一個展示有幾個 `<details>` 是寫死在測試裡的。** 多長出一個沒有人審過的
  收合區會讓測試變紅——這是刻意的（規則 5）。

⚠️ 索引頁只列**現在真的點得進去**的展示（D24）。不要先把規劃中的項目加進 `DEMOS`
再標「coming soon」——有一項測試會攔住那個字。

## ⛔ 五、使用者選的檔案**絕對不離開瀏覽器**（D28）

頻譜展示可以讓學生選一個自己電腦上的音訊檔。D20 原本禁止上傳，D28 推翻它，
**而推翻的前提是一句很具體的話**：檔案完全在瀏覽器端處理。

> 個資風險來自「檔案送到伺服器」，不是來自「使用者選了一個檔案」。

路徑只有一條，而且沒有分支：

```
<input type="file">  →  file.arrayBuffer()  →  ctx.decodeAudioData()  →  AudioBuffer
```

沒有 `fetch` 帶 body、沒有 `FormData`、沒有 `XMLHttpRequest`、沒有 `WebSocket`、
沒有 `sendBeacon`，檔案選擇器也**不在任何 `<form>` 裡**。伺服器端沒有任何
路由能收檔案（`/demos` 底下只有 GET，整個 `app/` 不 import `UploadFile`）。

這一段由 `tests/test_demos.py` 的第 6 組看守，共六項，前端後端各三項。
**要加任何送資料出去的東西，都會先讓那一組變紅**——這是刻意的。

## 六、只支援桌機瀏覽器（D30）

不處理觸控、不為小螢幕最佳化、`demos.css` 裡沒有行動裝置的斷點。

**但無障礙的要求一個都沒有放寬**：鍵盤操作、螢幕閱讀器讀得到的數值、
不只靠顏色區分、`prefers-reduced-motion`——這些與螢幕寬度無關。
DPR 縮放也照做（HiDPI 桌機螢幕一樣需要它）。

## 介面語言

程式碼註解用繁體中文（開發文件語言），**但所有字串常值一律英文**（D5）——
它們會出現在學生的畫面上。`tests/test_demos.py` 會把註解剝掉之後掃過
整個目錄，確認沒有中日韓字元漏進字串裡。
