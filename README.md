# 工程數學自動出題練習系統

兩個功能區：

1. **出題練習**（階段 1，已完成）——常微分方程與一階線性系統。題目、答案與逐步解答
   **全部由程式生成**（SymPy 反向構造 + 驗證閘門），不靠 LLM 計算，因此不會出現
   算錯的題目。流程是：**出題 → 自己在紙上算 → Show Answer 對答案 →
   Show Solution Steps 看過程**。
2. **互動式訊號處理展示**（階段 2S，進行中）——完全跑在瀏覽器裡的展示頁面
   （Web Audio + Canvas + 原生 JS，零 npm、零 bundler）。目前有一個：
   **取樣與混疊**。學生把取樣率拖到奈奎斯特頻率以下，直接**聽見**混疊。

兩者只共用登入、`UsageLog` 與版面（PLAN.md D21），其餘完全獨立。

規劃全文見 [PLAN.md](PLAN.md)。本 README 對應 **v0.16**。

部署：Windows 上的**測試**部署見 [`WINDOWS-SETUP.md`](WINDOWS-SETUP.md)；
**要給學生用的**正式部署（FreeBSD、校內固定 IP、**只開放校內網段**）見
[`FREEBSD-DEPLOY.md`](FREEBSD-DEPLOY.md)；
**在家用區網先預演一次**（FreeBSD 筆電 + macOS 用戶端、假網域 + 自簽憑證）見
[`FREEBSD-HOMELAB.md`](FREEBSD-HOMELAB.md)。

---

## 目前做到哪裡

**已完成**

- **兩組共用帳號**（`class` 給全班、`staff` 給老師與助教），由 `scripts/create_accounts.py`
  建立，**沒有任何自行註冊或建立第三組帳號的途徑**（D35）
- 帳號 + 密碼登入（argon2id 雜湊、session cookie），登入閘門是 middleware（D37）
- **系統不蒐集任何個人資料**：沒有學號、沒有姓名、**沒有用戶端 IP**（D35、D38）
- 下拉選單選題型與難度 → 出題 → KaTeX 排版
- **答案與逐步解答預設遮蔽**，各要點一下才展開（見下面「答案遮蔽」）
- 「Class activity」頁：全班練了哪些題型、幾題、開過哪些展示——**只有 `staff` 帳號看得到**（D39）
- 使用紀錄寫入 SQLite（彙總層級，沒有任何欄位指得到人）
- 四個題型 × 三個難度，共 12 種組合
- 每個題型都有出題端的 pytest 回歸測試
- **展示區骨架（2S0）與三個展示**：「取樣與混疊」（2S3）、「頻譜、視窗與洩漏」（2S4）、
  **「Fourier 級數的加法合成」（2S5）**，見下面「互動式展示」
- **展示區的 FFT 層（2S1）與五類數值驗證（2S2）**——vendored `fft.js` 跑在執行期，
  另有一支教學用的可讀 radix-2 通過完全相同的測試
- **六個內建範例音檔**（含 eSpeak NG 合成的語音），由 `scripts/make_demo_samples.py` 產生

**尚未實作**

- 其餘題型（待定係數、恰當方程、參數變異、Laplace、系統的重根／複數／非齊次）
- 逐步解答的整體審查與風格統一
- 相圖、離線預生成、教師後台
- 展示區的其餘部分：跨瀏覽器實測與 `/demos/selftest`（2S7）、無障礙審查一輪（2S8），
  以及第二批的三個展示（極零點 W7、摺積 W1-2、脈衝寬度 W4）。
  **沒有待決事項擋著**（PLAN.md §7 #32 已由 D31 結案）

**明確不做**

- **對話介面與 LLM 串接**（PLAN.md **D41**，v0.18）。這一項從「尚未實作」移到這裡：
  老師決定把整個階段 3 從規劃中砍掉。選單路徑已經夠用（題型 × 難度共 12 種組合），
  而接上 LLM 會需要一張 `ChatLog` 稽核表，那張表存的是**學生打進去的原文**——
  於是 v0.16 拆掉的整個個資法遵面必須整套復活，
  而**頁面上那句「不存你打的任何東西」會變成假話**。
  規格留在 PLAN.md §3（整節標為已捨棄但保留），**沒有實作可以取回，因為從未實作**。
- **自動評分／作答判定**（D12，v0.7）。實作保存在 git tag `grading-v1`。

> ⚠️ **這份清單是給維護者看的，不是給學生看的。** 系統的頁面上**不列出**
> 「目前有哪些功能、哪些待補」，也不寫上線時程（PLAN.md **D24**）——
> 涵蓋範圍由老師在課堂上口頭說明。原則不變且更嚴格：**網頁上寫的每一句都必須誠實**，
> 但不主動陳列進度，因為一份手動維護的進度表會腐化成一句假話。
> `tests/test_demos.py` 有一項盯著頁面不出現 `coming soon`／`planned` 之類的措辭。

> 本系統為**自我練習工具**：系統不判定答案、不產生成績、不呈現分數，練習紀錄只記用量。
> 紀錄與課程評量的關係**由老師在課堂上說明，系統一律不提**（PLAN.md D17）——
> 頁面、日誌都不得出現 grading／grade 字眼，`tests/test_web.py` 有兩項盯著。

> ## ⚠️ v0.16 的重大簡化：共用帳號，不再蒐集個人資料
>
> 老師決定改為**兩組共用帳號**（PLAN.md **D35–D40**）。這一版拿掉的東西比加的多：
>
> | 沒有了 | 為什麼 |
> |---|---|
> | 學號（`Student.student_no`） | 它是系統裡**唯一**一項個人資料。老師撤掉了「用量紀錄要看得出是誰」這個需求，它就沒有存在的理由。 |
> | 個資告知頁與同意流程（`/consent`） | 沒有個資，就沒有個資法第 8 條的告知義務。**不是義務被放寬，是標的沒有了。** |
> | 學生自行改密碼（`/account/password`） | 密碼是共用的——讓任何一個學生改掉它，等於把全班鎖在門外，而且不會拋任何錯誤。 |
> | 「My Progress」 | 「我練了多少」在共用帳號之下沒有答案。改為 `Class activity`，只有老師看得到（D39）。 |
> | 含明碼密碼的 CSV 對照表 | 兩組密碼用不著對照表。**系統這一側再也沒有任何含明碼的檔案。** |
> | 存取紀錄裡的用戶端 IP | D38。應用層、uvicorn、**反向代理**三層都要處理，第三層寫在 `FREEBSD-DEPLOY.md` §5.7。 |
>
> ⚠️ **舊的 `practice.db` 不能直接用**：欄位改了名字，程式會在啟動時拒絕並告訴你怎麼做。
> 見下面「從 v0.15 升級」。

### 題型清單

| 題型 | 難度 1 | 難度 2 | 難度 3 |
|---|---|---|---|
| 可分離變數 | `y' = f(x)·y` | `g(y)=y²` 或 `f(x)` 含指數 | `g(y)=1+y²`，需反正切反解 |
| 一階線性（積分因子） | `p` 為常數、`q` 為多項式 | `p` 為常數、`q` 含指數 | `p = k/x`（變係數） |
| 二階常係數齊次 | 兩相異實根 | 重根 | 共軛複數根 |
| 一階線性系統 2×2 | 三角矩陣 | 一般矩陣 | 一般矩陣 + 初始條件 |

---

## 互動式展示（`/demos`）

登入後從頁首的 **Demos** 進去。目前有三個，規劃全文見 [PLAN.md](PLAN.md) **§8**，
實作與草案的落差見 **§8.9**。

### 1. Sampling and aliasing（W6，取樣定理）

多數人以為取樣不足就是「變模糊」，而實際結果是**一個乾淨但錯誤的訊號**——這是本課程
唯一一個學生直覺會系統性出錯的主題。學生拖兩支滑桿（訊號頻率 $f$、取樣率 $f_s$），
畫面上同時出現原始波形、取樣點、零階保持的階梯，以及**穿過同一組取樣點的那條低頻
正弦**；耳朵那一側可以在「原始音」與「取樣＋重建後的音」之間即時切換。
把 $f_s$ 拖到 $2f$ 以下，聽到的音高開始往下走，而訊號本身完全沒動。

### 2. Spectrum, windows and leakage（W5，DFT 與 FFT）

這一頁糾正兩個誤解，而且兩個都是實務上真的會害人的：

- **洩漏不是雜訊。** 把測試音移到 bin 中心（頁面上有一個按鈕做這件事），矩形窗之下
  只有一根線；把它移開半格，同一個純音散成一整片裙擺，而且**峰值讀數還偏低**。
  訊號一點都沒變。切到 Hann／Hamming／Blackman，裙擺塌下去、主瓣變寬——
  那個取捨就是視窗函數的全部。
- **補零不是解析度。** 選「兩個相距 12 Hz 的正弦」那個範例、$N$ 設 1024、補零開到四倍：
  曲線變得又平滑又細緻，峰仍然只有一個。把補零關掉、$N$ 改成 4096：兩個峰出來了。
  解析度只來自觀測時間 $T = N/f_s$。

音源有三種：**可調的測試音**、**六個內建範例**（純正弦、帶限方波、帶限鋸齒、白雜訊、
雙頻、以及一句合成的人聲）、以及**使用者自己電腦上的音訊檔**。

> ### ⛔ 使用者選的檔案**完全不離開這台電腦**
>
> 這是 PLAN.md **D28**，它推翻了原本「不開放上傳」的 D20——而推翻的關鍵是一個很窄的
> 區分：**個資風險來自「檔案送到伺服器」，不是來自「使用者選了一個檔案」。**
>
> 路徑只有一條：`<input type="file">` → `file.arrayBuffer()` → `decodeAudioData()`，
> 全程在瀏覽器裡。檔案不上傳、不落地、不進資料庫、不進 `UsageLog`。
> 個資告知因此**一個字都不用改**。
>
> **這個區分由六項測試強制，不是靠紀律**（`tests/test_demos.py` 第 6 組）：展示的 JS
> 不得出現 `FormData`／`XMLHttpRequest`／`sendBeacon`／`WebSocket`／`EventSource`；
> 每個 `fetch` 都必須是單純 GET 一個 `/static/` 資產；檔案選擇器不得在任何 `<form>` 裡；
> `/demos` 底下只有 GET；整個 `app/` 不得 import `UploadFile`；頁面上要寫明檔案不外流。
>
> 格式接受 `audio/*`（wav 一定可以，mp3/m4a/ogg/flac 看瀏覽器）。**五種失敗全部有畫面
> 訊息**：檔案過大、解不開、非音訊、多聲道（會混成單聲道並說出來）、過長（只取前 30 秒）。

### 3. Fourier series: building a wave out of sines（W3，Fourier 級數）

**這一頁的正當性完全落在聲音上。** 部分和逼近方波的圖，Octave 三行就畫得出來，
所以它不是這個展示存在的理由；真正給不了的是這一件事——

> 把相位隨機化，**波形變得認不出來，而音色幾乎不動**。

長條圖一格都不會動（振幅根本沒有被碰），耳朵也聽不出差別，但畫面上那條曲線
已經不是鋸齒波了。人耳量的是振幅、對相位相當不敏感；眼睛看的是總和，
而總和同時吃振幅與相位。**兩個訊號可以長得完全不像而聽起來一樣**——
這件事只有同時給眼睛和耳朵才教得出來。

另外三件事一起放在這一頁：

- **吉布斯現象，而且印出數字。** 學生看得到角落翹起來，但「翹了多少」讀不出來，
  而整個誤解（「加更多項就會收斂到完美」）就活在那個讀不出來的縫隙裡。
  頁面上有一張對照表，三欄刻意放在一起，因為誤解正是由它們的**不同步**構成的：
  過衝的高度朝著落差的 **8.95%** 去（**不是朝 0 去**）、寬度每加倍項數就減半、
  而「與目標的最大差距」在有跳點時**根本不下降**（它停在跳點那一格，永遠是落差的一半）。
  方波由上面下來（$N=3$ 時 10.02%）、鋸齒波由下面上去（$N=3$ 時甚至是負的），
  兩者收斂到同一個數字。
- **收斂速度**：方波與鋸齒是 $1/n$，三角波與半波整流是 $1/n^2$，長條圖上有一條包絡線
  畫著它。連續的波形不會過衝，這兩件事是同一件事的兩面。
- **三角形式與指數形式的對應**：$c_n = (a_n - i b_n)/2$、$|c_n| = A_n/2$、
  $c_{-n} = \overline{c_n}$，收合區裡有推導，讀數裡有當前波形的實際數字。

控制項：目標波形（方波／鋸齒／三角／半波整流）、項數 $N$（1–64）、基頻 $f_0$（55–880 Hz）、
相位方案（照級數／全部正弦相位／隨機＋重抽）、**單獨轉某一次諧波的相位**（選第幾次 + 轉幾度）、
聽部分和或聽目標、要不要畫出個別諧波。

> **音訊：一個 `OscillatorNode` + `setPeriodicWave`，不是 N 個振盪器疊加。**
> PLAN §8.8 原文寫的是後者，實作改掉了，理由很硬：**`OscillatorNode` 沒有相位參數**。
> 疊加 N 個振盪器做得出振幅正確的部分和，但每一個的起始相位由它 `start()` 的那一刻
> 決定——而這一頁有一半的內容就是控制相位。`createPeriodicWave(real, imag)` 逐次諧波
> 指定 cos 與 sin 的係數，也就是逐次諧波指定振幅**與相位**。
>
> **帶限是硬性的**：合成的每一個諧波都必須嚴格低於 $f_s/2$，超出的直接裁掉並在畫面上
> 說出來。在一個教 Fourier 級數的頁面上讓自己的合成先混疊會很難看——畫面上第 40 根
> 長條會在耳朵裡變成一個位置錯誤的音。`tests/test_dsp_js.py` 有一組盯著這件事。
>
> **換波形不會有爆音**：改 $N$、改相位、換目標都要換掉振盪器的波形，而直接
> `setPeriodicWave` 是一個階躍——就是「喀」一聲，方波與鋸齒的高諧波尤其刺耳。
> 作法是先把音量線性降到 0（12 ms），**在那段確實是 0 的 36 ms 裡換**，再升回來；
> 連續拖滑桿時這個動作最密 90 ms 一次。

### 內建範例音檔

`app/static/demos/samples/*.wav`，22.05 kHz 單聲道 16-bit，合計約 510 KB，**納入版本控制**。
由 [`scripts/make_demo_samples.py`](scripts/make_demo_samples.py) 產生（可重現）：

```bash
python scripts/make_demo_samples.py          # 產生全部
python scripts/make_demo_samples.py --list   # 只列出會產生什麼
```

語音那一個用 **eSpeak NG**（`espeak-ng -v en-us -s 150 -w`）。**找不到 espeak-ng 時
腳本會明說跳過了哪一個、為什麼**，不會安靜地少產生一個檔案——版本控制裡那份仍然有效。

方波與鋸齒是**帶限**加法合成的，不是直接取樣理想波形：後者會在檔案裡就先混疊，
在一個專門教頻譜的頁面上放那種檔案，學生會看到一堆我們自己造成的、解釋不了的譜線。

`tests/test_demos.py` 有一組測試斷言**檔案內容與標籤相符**（方波真的只有奇次諧波、
雙頻真的相距 12 Hz、語音真的有音節起伏）——標錯了不會有任何東西壞掉，而學生會相信標籤。

### 給維護者的六件事

1. **⛔ 展示頁面內部不使用 HTMX。** 一次 `hx-swap` 會把 canvas 換掉，留下無人引用
   但仍在發聲的 `AudioWorkletNode`——症狀是「換頁之後還有聲音」。HTMX 仍用於展示
   **之間**的導覽。`tests/test_demos.py` 有一項斷言展示頁不含 `hx-*` 屬性。
2. **四段單向依賴。** `lib/signal.js` 與 `lib/transform.js` 是純函式（不知道 DOM 與
   AudioContext 存在）→ `lib/draw.js` 吃 canvas 與資料 → `aliasing.js`／`spectrum.js`
   是唯一知道 DOM 的一層。**任何數值演算法都必須落在前三層**，因為
   `tests/test_dsp_js.py` 只測得到那三層。
3. **零建置。** ES modules + 相對路徑 import，沒有 npm、沒有 bundler、沒有 `package.json`。
   **`node` 只是開發期相依**（跑 `tests/test_dsp_js.py`），部署不需要它。
   ⚠️ ES module 必須經 HTTP 提供，直接用瀏覽器開 `file://` 會被 CORS 擋掉。
4. **DOM 永遠不是真相的來源。** 狀態是一個普通物件 + 一個 `render()`；輸入事件只寫
   `state`，`render()` 只把 `state` 畫出來。檢查方式：搜尋 `.value`，它應該只出現在
   事件處理器與初始化裡。
5. **音訊的失敗都要在畫面上留一句英文訊息**（不支援 Web Audio、autoplay 被擋、
   worklet 載入失敗、麥克風被拒，以及檔案的五種），不得只寫 `console`——學生不會開
   devtools。前四種集中在 `lib/audio.js`，檔案那五種在 `spectrum.js`。
6. **兩支 FFT，一支跑、一支教，但測試完全相同。** 執行期跑的是 vendored 的
   `fft.js` 4.0.4（MIT，`app/static/vendor/fftjs/`，**與上游只差一行**，由 sha256 測試盯著）；
   `lib/transform.js` 裡另有一支可讀的 radix-2 標為教學用。
   `tests/test_dsp_js.py` 的每一項數值斷言都對兩支各跑一次——**一支說謊的教材比沒有教材更糟**。

更多細節在 [`app/static/demos/README.md`](app/static/demos/README.md)。

### 只支援桌機瀏覽器

PLAN.md **D30**：不處理觸控、不為小螢幕最佳化。**但無障礙一項都沒有放寬**——
鍵盤操作、螢幕閱讀器讀得到的數值、不只靠顏色區分、`prefers-reduced-motion`
（頻譜圖改為按鍵推進），這些與螢幕寬度無關。DPR 縮放也照做（HiDPI 桌機一樣需要）。

### ⚠️ 尚未在真實瀏覽器裡驗收

伺服器端該驗的都驗了（路由、`UsageLog`、資產取得得到、頁面內容、JS 抓的每個 id 都在
頁面上），純函式層有 93 項數值斷言——但**音訊、canvas、autoplay 解鎖、worklet 載入、
`decodeAudioData`、DPR 縮放全部沒有被真的執行過**（開發環境沒有瀏覽器）。
在桌機 Chrome／Firefox／Safari 上各開一次之前，這三個展示都應該當成「還沒驗收」。

**v0.17 補上了最粗的那一層，但它不是瀏覽器。**
`scripts/run_demo_smoke.mjs` 在 node 裡搭一個很小的假 DOM——**元素的初始值從真的
範本檔讀出來**，不是捏的——把整支 `<demo>.js` 載入、畫一次、再撥動十幾個控制項。
三個展示都跑，由 `tests/test_demos.py` 的 10 項斷言看守：

```bash
node scripts/run_demo_smoke.mjs fourier   # 手動跑一次，會印出一大包 JSON
```

它**擋得住**：module 一載入就對 null 取屬性、`render()` 丟例外、事件綁到不存在的
元素、`render()` 什麼都沒畫、讀數印出 `NaN`／`undefined`、以及「不支援 Web Audio
時畫面上要有一句話」那條在真實世界幾乎不會被觸發、因此幾乎不會被人看到寫錯的路徑。

它**擋不住**：像素、版面、`AudioContext` 的實際行為、`setPeriodicWave` 到底發出
什麼聲音、`decodeAudioData` 的瀏覽器差異、DPR 縮放、autoplay 政策。
**跨瀏覽器實測（2S7）一項都沒有被取代。**
PLAN.md §8.4 方案 C 的 `/demos/selftest` 頁就是為這件事準備的，還沒做。

### 用量紀錄

**一次展示頁面載入 = `UsageLog` 一列**，欄位一個都沒有加（PLAN.md 規則 3）：

```
template_id = "demo.sampling.aliasing"   action = "demo_open"
template_id = "demo.spectrum.leakage"     action = "demo_open"
template_id = "demo.fourier.additive"     action = "demo_open"
difficulty  = 0   seed = 0               ← sentinel，展示沒有這兩個概念
```

**不記任何參數變動、滑桿位置、停留時間**——滑桿軌跡是遠比使用次數親密的行為資料，
超出「用量紀錄」的範圍（PLAN.md §8.7）。

v0.16（D36）：`student_id` 改名為 `account_id`，欄位數不變。它只會有兩個值，
**留著只為了把老師的測試流量排除在全班統計之外**——改一頁版面會重新整理十幾次，
那十幾列會讓「這週有多少人看過混疊展示」失真，而失真的方式是「數字大了一點」，
沒有人看得出來。登入頁的誠實說明（D40）已涵蓋展示（"...which demos are opened"），
`test_the_honest_note_covers_opening_a_demo` 盯著它。

代價老實說一句：**重新整理頁面會多算一列**，所以「開啟次數」是略微高估的量。

---

## ⚠️ v0.7：自動評分（作答判定）已移除

老師改變了產品方向：**從學生自我練習的角度，「題目 + 正解 + 分段過程說明」已經足夠，
系統不需要判定學生輸入的答案對錯。**（PLAN.md D12）

**這不是因為判定做得不好。** v0.4–v0.6 的判定是可信的——說「對」的時候一律有符號證明、
逾時只殺出事的那一個 worker、答案的顯示形式一致。是它服務的那個需求本身被取消了。

**完整的判定功能保存在 git tag `grading-v1`。** 日後若要恢復，從那裡取回即可：

```bash
git show grading-v1 --stat            # 看當初有哪些檔案
git checkout grading-v1 -- app/grader tests/test_grader.py tests/test_grader_sandbox.py
git show grading-v1:app/routes/practice.py     # 作答與看解答的端點
git show grading-v1:app/db/models.py           # Attempt 資料表
```

方法論（parser 的每一條補丁、三值等價判定、fail fast 的推導、逾時隔離的三方案取捨）
留在 **PLAN.md §5.2–§5.7**，標為「已捨棄／保留供日後參考」，那就是恢復時的規格書。

### 移除了什麼

| 項目 | 處置 |
|---|---|
| `app/grader/`（5 個模組） | 移除。唯一的使用者是判定 |
| 作答輸入框、Check my answer、判定回饋 | 移除（`_answer_form.html`、`_feedback.html`） |
| `/practice/submit` 端點 | 移除 |
| `/practice/solution` 端點 | 移除——解答改用 `<details>` 收合，不再需要另外要一次（見下） |
| `Attempt` 資料表 | 移除。**沒有做 migration**，說明見下面「資料庫」 |
| "My Progress" 的正確率、作答歷史 | 移除。**用量的部分保留**——老師仍要看用量（D1） |
| 判定子行程沙箱（D6／D8／D10） | 移除。出題流程從來沒有用過它 |
| `GRADER_*` 六個環境變數、`SUBMIT_RATE_LIMIT`、`MAX_ANSWER_LENGTH` | 移除 |
| `/healthz` 的 `grader` 區塊 | 移除，現在只回 `{"status": "ok"}` |
| `scripts/grader_sampling_report.py` | 移除 |
| `tests/test_grader.py`、`tests/test_grader_sandbox.py` | 移除（共 123 項） |

### 沒有動、也不能動的東西

**`Problem.check`（`Check` 物件）。** 它同時是**出題引擎的驗證閘門**：`base.generate()`
用它把標準答案代回原方程，殘差不是 0 就換一組參數重抽。判分曾經共用它，但那是附帶用途。
移除 `Check` 等於拆掉「進到學生眼前的題目 100% 有正確答案」這條唯一的保證——
新增題型時仍然必須提供它。

`UsageLog` 也完整保留：它記的是誰、何時、練了哪個題型，與判定無關。

### 資料庫：`Attempt` 表要不要處理

**不需要 migration。** `Attempt` 只在 v0.4–v0.6 存在，系統從未正式上線，實際的
`practice.db` 裡只有測試資料。`init_db()` 用的 `SQLModel.metadata.create_all()`
只建缺少的表、不會去動既有的表，所以：

- **全新的資料庫**：不會建出 `attempt` 表，什麼都不用做。
- **舊的資料庫**：`attempt` 表會留在檔案裡，但永遠不被讀寫。想清掉就手動下一行：

```bash
sqlite3 practice.db 'DROP TABLE IF EXISTS attempt;' && sqlite3 practice.db 'VACUUM;'
```

若日後真的累積了要保存的資料，那時再引入 Alembic；不必為了一張沒有資料的表提前付這個成本。

---

## 答案遮蔽

老師的要求：**每題的答案要先遮蔽，點選 Show Answer 後才顯示**，行為與逐步解答一致
（PLAN.md D13、§5.8）。實作是三層，每一層都要學生主動點：

```
題目（自動顯示）
  └─ ▸ Show Answer            → 最終答案
       └─ ▸ Show Solution Steps → 分段過程
```

三個設計決定：

1. **兩層用同一套 UI**（原生的 `<details>/`<summary>`），學生只要學一次這個互動。
2. **詳解巢狀在答案裡面**，不是並排的第二個按鈕——「先看答案對不對，看不懂再展開過程」
   是自然的順序；並排會讓人以為是二選一。
3. **兩層都預設收合。**

### 取捨：答案其實在 HTML 原始碼裡

選了 `<details>` 就代表**按 F12 或全選複製看得到答案**。這在 v0.4 曾被明確否決，
現在反過來，因為前提變了：

| | v0.4（有判定） | v0.7（無判定） |
|---|---|---|
| 提前看到答案的後果 | **判定失去意義**——貼上答案就得到 Correct，而那筆紀錄會進 `Attempt` | 只是自己少練到一題。沒有東西可以作弊 |
| 成本 | HTMX 端點 + 一次往返，值得 | 同樣的成本，換到的東西小得多 |

**系統不判定答案、也不把對錯寫進紀錄**（D12）是這個取捨成立的關鍵：展開答案不留痕跡、
也換不到任何東西，能作的弊只作用在自己身上。換到的是——沒有網路往返
（校內網路不穩時一樣能展開）、少一個端點與它的錯誤處理、上一頁回來時展開狀態還在。

**代價是 `view_solution` 這則用量紀錄消失了**（`<details>` 展開不發請求），
於是「一出題就直接看解答的比例」這個指標失去資料來源。判斷是可以接受的：那是對**解題過程**
的監看，與「練了多少」不同層次，本來就不在個資告知的蒐集範圍內。若老師改變主意想要這個訊號，
除了改回 HTMX 按需載入之外**還要重新看一次個資告知**————`/practice/solution` 的程式碼在 tag `grading-v1` 裡，原樣可用。

註解寫在 `app/templates/_problem.html` 的開頭，兩項測試盯著（見下面「測試」）。

---

## 安裝

需要 Python 3.10 以上。

```bash
git clone <這個 repo>
cd engmath-practice

python3 -m venv .venv
source .venv/bin/activate          # Windows：.venv\Scripts\activate

pip install -r requirements.txt
```

> **在 Windows 上從零開始安裝**（PowerShell 指令、`Add python.exe to PATH`、
> 執行原則、展示頁的瀏覽器與音訊需求、疑難排解）請看
> [`WINDOWS-SETUP.md`](WINDOWS-SETUP.md)。

## 啟動

```bash
# 產生一把 session 金鑰（不設也能跑，但每次重啟會把所有人登出）
export SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")

uvicorn app.main:app --reload
```

資料庫 `practice.db` 會在第一次啟動時自動建立（權限自動設為 600）。

**沒有註冊頁**（v0.15 起），所以第一次啟動之後要先把兩組帳號建起來：

```bash
python scripts/create_accounts.py init
```

它會印出 `class` 與 `staff` 兩組密碼——**只印這一次**，資料庫裡只有雜湊。
用 `class` 那一組開 <http://127.0.0.1:8000> 登入即可開始出題；
`staff` 那一組多一個 `Class activity` 頁。完整說明見下面「帳號怎麼設定」。

### 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `SESSION_SECRET` | 每次啟動隨機產生 | session cookie 的簽章金鑰。**正式環境必須設定。** |
| `PRACTICE_DB` | `./practice.db` | SQLite 檔案位置 |
| `COOKIE_SECURE` | `0` | 走 HTTPS 時設為 `1` |
| `APP_LOG_LEVEL` | `INFO` | `app.*` 與 `app.access` 的 log 等級。查出題為什麼重抽時可設 `DEBUG` |
| `CLASS_ACCOUNT_NAME` | `class` | 全班共用帳號的登入名稱（v0.16，D35） |
| `STAFF_ACCOUNT_NAME` | `staff` | 老師／助教帳號的登入名稱 |

可複製 `.env.example` 為 `.env` 管理（`.env` 已被 `.gitignore` 排除）。

> v0.6 的 `GRADER_TIMEOUT` / `GRADER_WORKERS` / `GRADER_QUEUE_TIMEOUT` /
> `GRADER_WARMUP` / `GRADER_WARMUP_TIMEOUT` 已隨判定移除。環境裡若還留著，
> 現在只會被忽略。
>
> v0.15：`REGISTER_RATE_LIMIT` 隨自行註冊一起移除（沒有對外的帳號建立端點
> 可以被灌），新增 `PASSWORD_CHANGE_RATE_LIMIT`。兩者都在 `app/config.py`，
> 不走環境變數。
>
> v0.16：`PASSWORD_CHANGE_RATE_LIMIT` 隨 `/account/password` 一起移除。
> `LOGIN_RATE_LIMIT` 從「每 IP 10 次／分 + 每學號 10 次／分」改成
> **一個全站共用的計數器**（120 次／分）。每 IP 不能留是因為系統不碰 IP（D38），
> 而且一整班在校園 NAT 後面共用一個對外 IP，10 次／分是全班的額度；
> 每帳號不能留是因為只有兩個帳號，一個人連打錯十次就鎖住全班。
> ⚠️ 代價：一個人狂打會讓所有人在那一分鐘內看到「Too many login attempts」。
> 視窗 60 秒、會自己恢復。

---

## 帳號怎麼設定（v0.16，PLAN.md D35）

**系統只有兩組帳號，而且沒有辦法長出第三組。**

| 角色 | 給誰 | 特別的地方 |
|---|---|---|
| `class` | 全班共用，發給所有修課學生 | 就是一般的使用者 |
| `staff` | 老師與助教測試用 | 多一個 `Class activity` 頁；**它的用量不計入全班統計** |

```bash
export PRACTICE_DB=./practice.db     # 要與 uvicorn 用的是同一個

# 學期初：把兩組帳號建起來，印出密碼（已存在的會跳過）
python scripts/create_accounts.py init

# 密碼流出去了，或學期結束要換
python scripts/create_accounts.py reset class

# 想自己指定一組好念的
python scripts/create_accounts.py reset class --password "fourier-series-2026"

# 看目前有哪些帳號（沒有密碼——資料庫只存雜湊，撈不回來）
python scripts/create_accounts.py list
```

### 密碼長什麼樣、為什麼

自動產生的格式是 **`字-字-字-兩位數字`**，例如 `cedar-otter-flint-47`。

- 字典恰好 **256** 個相異的字（4–6 個小寫字母），數字只用 **2–9**，
  所以熵是 log2(256³ × 8²) = **恰好 30 bits**。
- **整個密碼裡不存在任何一對長得像的字元**（`l/1/I`、`O/0` 全部排除）。
  這個需求在 v0.16 **變強了**：密碼現在是**老師在課堂上念出來、三十個人同時
  打進去**的一個字串——念錯一次，三十個人一起打錯。
- 30 bits 在「線上猜測 + 速率限制」的威脅模型下綽綽有餘：登入端點全站
  120 次／分鐘，猜完 2³⁰ 的一半要約 **8,500 年**（離線那一側由 argon2id 擋）。

完整的取捨寫在 `app/accounts.py` 的模組說明裡。

### 三件必須知道的事

1. **重跑 `init` 是安全的。** 已存在的帳號會被跳過，密碼不變。這比 v0.15 更要緊：
   覆寫一個逐人配發的帳號只鎖住一個人，**覆寫共用帳號是全班同時進不來**，
   而且是在你只想確認帳號建好了沒的時候。要換密碼請明確用 `reset`。
2. **密碼只印在終端機上，不寫檔。** v0.15 那份 `ACCOUNTS-PLAINTEXT-DELETE-ME-*.csv`
   沒有了——兩組密碼用不著一份對照表。這是 v0.16 一個很實際的安全性改善：
   **系統這一側再也沒有任何含明碼的檔案。**
   ⚠️ 但終端機的捲動紀錄仍然有它，公用電腦上記得清掉。
3. **密碼會被轉傳，這件事擋不住。** 一組全班共用的密碼遲早會出現在 LINE 群組、
   共筆、學長姐的筆記裡。緩解不是技術性的：換密碼只要一行，而且系統裡本來就
   沒有值得偷的東西——沒有個人資料、沒有成績、沒有作答內容。

### 學生看得到什麼

登入頁上有一段**誠實說明**（D40）。它不是縮水版的個資告知（沒有勾選、沒有
保存期限那些制式段落——沒有個資，那些欄位是空的），它只糾正兩個使用者會有的
錯誤預設：

- 「登入了，所以系統知道我是誰」——不對，帳號是全班共用的。
- 「這是學校的系統」——不對，而且密碼由老師配發，這個誤會比 v0.15 更容易發生。

內容四句：全班共用同一個帳號所以系統無從得知你是誰、只彙總「哪些題型被練、
哪些展示被開」、不存姓名／學號／IP／你打的任何東西、沒有作答框也不判對錯。
頁尾有一句話的版本。`tests/test_web.py` 有四項盯著這幾句話還在。

---

## 存取紀錄不含 IP（v0.16，PLAN.md D38）

老師的指定是「只記錄 IP 以外的其他欄位」。存取紀錄長這樣：

```
2026-08-26 19:31:33 INFO     app.access: GET /demos/spectrum/leakage -> 200 in 12.4ms
```

方法、路徑、狀態碼、耗時都在，**沒有來源位址**。實作有三處，
**第三處在這個 repo 外面，也是最容易被忘記的**：

1. **應用層**——不讀 `request.client`、不讀 `X-Forwarded-For`／`X-Real-IP`。
   速率限制的 key 從 IP 改成一個固定字串。
2. **uvicorn**——它的預設存取格式是 `'%(client_addr)s - "%(request_line)s" ...'`。
   ⚠️ **不處理的話，應用層一個 IP 都不碰，而終端機上照樣一行一個 IP。**
   `app/logging_setup.py` 在 lifespan 裡把 `uvicorn.access` 的 handler 整個拔掉
   （不是換 formatter——格式是設定，設定會被 `--log-config` 覆寫），
   改由 `app/access_log.py` 的中介層產生紀錄。接管時會印一行 log 說明。
3. **反向代理**——Caddy／nginx 的存取紀錄預設含來源 IP，而那一層在我們的行程
   外面。設定寫在 [`FREEBSD-DEPLOY.md`](FREEBSD-DEPLOY.md) §5.7。
   **第一次部署完成後請 `tail` 一下代理的 log 確認**，這是唯一的驗收方式。

看守：`tests/test_web.py` 有五項（格式字串黑名單、整個 `app/` 不得讀用戶端位址、
黑名單檔案自己、`uvicorn.access` 拔乾淨、實際請求的紀錄裡沒有形如 IP 的字串）。
**五項全綠也證明不了第 3 項**——那不在這個行程裡。

---

## 從 v0.15 升級：舊的 `practice.db` 要刪掉

`Student` 改名為 `Account`、`UsageLog.student_id` 改名為 `account_id`，而
`SQLModel.metadata.create_all()` **只建缺少的表、不會去改既有的表**。
所以一個 v0.15 的資料庫接上 v0.16 會「看起來正常」，直到第一次有人出題——
那時才噴 `no such column: account_id`。

那是一個半夜出現在某個學生螢幕上的 500，所以程式選擇**在啟動時就拒絕**
（規則 4：寧可讓啟動失敗）：

```
LegacySchemaError: 資料庫 ./practice.db 是 v0.15 以前的格式：有一張舊的 `student` 表…
請把它刪掉讓程式重建：
    rm ./practice.db ./practice.db-wal ./practice.db-shm
```

**刻意不提供自動遷移**：舊檔裡的 `student_no` 正是這一版要拿掉的東西，
一個「幫你搬過來」的腳本會把那批學號從一個要刪掉的檔案搬進一個要長期使用的
檔案。系統從未正式上線，資料庫裡只有測試資料。

刪掉之後重跑 `python scripts/create_accounts.py init` 即可。

---

## 運維

判定移除之後，這個系統的運維面變得非常小：**一個 uvicorn 進程 + 一個 `.db` 檔案**。
它不再有子行程池、沒有暖機自檢、也**不再有任何地方執行不可信輸入**——
出題只吃 `(template_id, difficulty, seed)` 三個經過檢查的值，跑的是我們自己寫的 generator。

存活檢查：

```bash
curl -s localhost:8000/healthz
# {"status":"ok"}
```

### 值得看的一則 log

出題是拒絕抽樣：抽一組參數 → 用 `Check` 驗證殘差是不是 0 → 不是就重抽。重抽到上限
仍然失敗時，學生看到「Please press Generate again」，而 log 裡會有：

```
WARNING  app.routes.practice: 出題失敗：template=ode.first_order.separable difficulty=3
         （重抽多次都沒通過殘差驗證）。偶爾一次是正常的；若集中在某個題型請檢查它的參數範圍。
```

**偶爾一次是正常的**（那正是驗證閘門在做事）。但如果它集中在某一個 (題型, 難度)，
那代表該模板的參數範圍出了問題，應該去看 `app/generator/<題型>.py`，
並用 `scripts/preview.py` 產一批樣本檢查。

（**log 訊息是寫給維護者看的，用中文**；學生看得到的介面一律英文，見 PLAN.md D5。）

---

## 測試

```bash
pytest                          # 全部 437 項，約 4 分鐘
pytest tests/test_web.py -q     # 只跑 Web 流程
pytest tests/test_demos.py -q   # 只跑展示區的規則與冒煙測試（約 18 秒）
pytest -m "not dsp_js"          # 排除需要 node 的那 175 項

python scripts/dsp_reference.py --check   # 只驗證 golden 檔的自我一致性
python scripts/dsp_reference.py           # 重新產生它（改了那支腳本才需要）
```

| 檔案 | 項數 | 守的是什麼 |
|---|---|---|
| `test_generators.py` | 91 | 出題引擎、答案的顯示形式一致性 |
| `test_web.py` | 75 | 端對端流程、答案遮蔽、**`/register` 是否移除乾淨（D32）**、**個資告知閘門（D33）**、**改密碼（D34）**、前端資產、介面語言 |
| `test_accounts.py` | 23 | **帳號配發（D32）**：初始密碼的格式與熵、重跑不覆寫、`reset` 的行為、CLI 與對照表的權限與警告 |
| `test_demos.py` | 73 | 展示區的**規則**：登入、`UsageLog` sentinel、誠實說明、HTMX 禁令、三組「不說的話」、**範例音檔的內容**、**D28 的六項「檔案不外流」看守**、vendored FFT 的完整性、**以及冒煙測試（見下）** |
| `test_dsp_js.py` | 165 | 展示區的**數字**：pytest 驅動 node 跑純函式層，參考值在 Python 這一側用 SymPy 或樸素 DFT 現算。**每一項對兩支 FFT 各跑一次** |

### 展示區的數值驗證（PLAN.md §8.4 的五類）

出題端的承諾是「每一題都由 `Check` 驗過殘差為 0」，展示端做不到逐幀驗證（SymPy 不在
瀏覽器的迴圈裡）。能做到的是**演算法本身經一條與它獨立的路徑驗證過**：

1. **樸素 DFT 交叉比對**（最強，不可裁減）——照定義的二重迴圈寫在 **Python 這一側**，
   $N = 8 \dots 1024$、隨機複數輸入、相對誤差 $\le 10^{-10}$。兩條路徑連語言都不同。
2. **解析解對照**（不可裁減）——$\delta[n]$ 全平、常數只有 DC、落在 bin 中心的正弦
   讀回自己的振幅、長度 $L$ 的矩形是 Dirichlet 核且零點落在 $k = mN/L$。
3. **Parseval**——能量守恆。便宜，但抓不到相位錯誤。
4. **往返誤差**——⚠️ **不得單獨當閘門**。有一項測試把這句話做成反例：一支 twiddle
   正負號**一致地**寫反的 DFT，往返完美，頻譜卻是共軛的（也就是錯的）。
5. **SymPy golden vector**——`scripts/dsp_reference.py` 產 `tests/data/dsp_golden.json`
   （視窗係數、加窗正弦的整條幅度譜、Dirichlet 核），並對它自己跑一輪自我一致性檢查。

另有三項測的不是程式而是**教學內容**：四種視窗的洩漏排序、off-bin 時峰值讀數會偏低、
以及「補零不會把兩個相距半格的頻率分開，而觀測時間加倍會」。

`tests/test_generators.py` 是整個專案最重要的測試：每個題型 × 每個難度
各隨機生成 30 題，逐題檢查

1. **把解代回原方程，殘差恰為 0**（最關鍵的一項）
2. 沒有特殊函數（`erf`、`Ei`、`LambertW`…）或未算完的積分
3. 沒有醜分數（分母 > 12）
4. 出題係數落在白名單範圍內
5. 逐步解答非空，且最後一步就是答案
6. 同一個 seed 必然生出相同的題目

答案遮蔽（D13）由 `test_web.py` 的兩項互補測試守著：

- `test_answer_and_steps_are_collapsed_by_default`：**沒有任何一個 `<details>` 帶 `open` 屬性**。
  漏掉收合是這個實作唯一會靜默出錯的方式——頁面不會壞，只是答案直接出現在畫面上。
- `test_revealed_content_actually_contains_the_answer_and_the_steps`：展開後真的有東西。
  只有前一項的話，一個把答案整段刪掉的 bug 會讓測試全綠。

另有三項守住「判定真的移除乾淨了」：端點回 404、`Attempt` 模型不存在、`app.grader` import 不到。

升級 SymPy 版本前請跑完整回歸：

```bash
GEN_TEST_SAMPLES=200 pytest tests/test_generators.py
```

---

## 專案結構

```
app/
├── main.py                     FastAPI 進入點、三層中介層（順序有意義）
├── config.py                   設定（環境變數）
├── logging_setup.py            app.* 的 log 輸出 + 接管 uvicorn 的存取紀錄（D38）
├── access_log.py               存取紀錄：方法／路徑／狀態碼／耗時，不記來源（D38）
├── security.py                 argon2 密碼雜湊、密碼規則、速率限制
├── db/
│   ├── models.py               Account / UsageLog（D35、D36）
│   └── session.py              SQLite 連線（WAL）
├── generator/                  ← 出題引擎，本專案的核心
│   ├── base.py                 Problem / Step / Check、註冊表、generate()
│   ├── pretty.py               漂亮度評分與拒絕抽樣、顯示形式的一致性
│   ├── separable.py
│   ├── first_order_linear.py
│   ├── second_order_homog.py
│   └── system_2x2.py
├── accounts.py                 兩組共用帳號的建立與密碼重設（D35）
├── login_gate.py               登入閘門 middleware（D37；由 consent_gate.py 改名）
├── routes/
│   ├── auth.py                 登入／登出（註冊、告知、改密碼都已移除）
│   ├── practice.py             出題、/activity（全班活動，僅 staff）
│   └── demos.py                ← 展示區的路由（純資料的清單 + 一列 UsageLog）
├── templates/                  Jinja2（介面文字一律英文，見 PLAN.md D5）
│   ├── _about.html             誠實說明（D40；登入頁 include，由 consent.html 改名）
│   ├── activity.html           全班活動（D39；由 progress.html 改名）
│   └── demos/                  index.html、_shell.html（共用外框）、aliasing.html、spectrum.html、fourier.html
└── static/
    ├── style.css
    ├── demos/                  ← 展示區的前端（見該目錄的 README）
    │   ├── demos.css
    │   ├── lib/                signal / transform / draw / audio / shell
    │   ├── worklets/           sampler-processor.js（唯一的自訂 worklet）
    │   ├── samples/            內建範例音檔（make_demo_samples.py 產生）
    │   ├── aliasing.js         展示 1 的控制器
    │   ├── spectrum.js         展示 2 的控制器（含本機檔案的純瀏覽器端處理）
    │   └── fourier.js          展示 3 的控制器（PeriodicWave 合成、相位控制）
    └── vendor/                 自架的 KaTeX、HTMX、fft.js（見該目錄的 README）
tests/
├── test_generators.py          出題引擎回歸測試
├── test_web.py                 登入 → 出題 → 展開答案／詳解、IP 不落地、staff 限定
├── test_accounts.py            共用帳號：密碼格式與熵、重跑不覆寫、CLI
├── test_demos.py               展示區的規則（登入、UsageLog、誠實說明、HTMX 禁令、D28…）
├── test_dsp_js.py              展示區的數字（pytest 驅動 node，對照 SymPy）
└── data/dsp_golden.json        SymPy 產的 golden vector（納入版本控制）
scripts/
├── create_accounts.py          共用帳號 CLI：init／reset／list（D35）
├── preview.py                  批次產題目樣本供人工審題（HTML / LaTeX）
├── run_dsp_case.mjs            test_dsp_js.py 用來驅動 node 的執行器
├── run_demo_smoke.mjs          在 node 的假 DOM 裡把展示的 JS 跑一遍（見「尚未驗收」）
├── dsp_reference.py            SymPy → tests/data/dsp_golden.json（§8.4 第 5 類）
├── make_demo_samples.py        產生內建範例音檔（含 eSpeak NG 語音）
└── git-safe-commit.sh          不需 unlink 的提交路徑（見 CLAUDE.md）
```

---

## 新增一個題型

只要加一個檔案，UI 下拉選單與 pytest 參數化測試都會自動撿到，兩處都不用改。

1. 在 `app/generator/` 建立新檔，例如 `exact.py`：

```python
import random
import sympy as sp
from .base import Check, Problem, Step, register
from .pretty import is_pretty

x = sp.Symbol("x", positive=True)
_y = sp.Function("y")(x)          # 驗證閘門用的未知函數

@register(
    "ode.first_order.exact",
    name="Exact Equations",
    chapter="First-Order ODEs",
    difficulty_notes={1: "Already exact", 2: "Verify exactness first",
                      3: "An integrating factor is needed"},
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    ...
    # 回傳 None 表示這組參數不合格，base.generate() 會自動換一組重抽
    return Problem(
        template_id="ode.first_order.exact",
        difficulty=difficulty,
        seed=0,                       # 由 base.generate() 填入
        params={...},                 # 供測試檢查係數範圍
        statement="...",
        statement_latex="...",
        answer_latex="...",
        answer_expr=sol,
        steps=[Step("Title", r"latex", "Note in English; wrap math in $…$"), ...],
        check=Check(                  # ← 驗證閘門。**必要**，不可省略
            var=x,
            kind="scalar",            # 或 "system"
            n_constants=1,            # 通解需要幾個任意常數（初值問題填 0）
            order=1,                  # 方程的階數
            unknown=_y,
            residual_expr=sp.Derivative(_y, x) - ...,   # L[y] - g，含 _y
            linear=True,              # L 對 y 是否線性
        ),
    )
```

`Check` 是 `base.generate()` 驗證標準答案的依據——**它不是可選的**。殘差算不出 0
就會換一組參數重抽，這是「進到學生眼前的題目 100% 有正確答案」的實作。
`var` 一定要用 generator 自己那顆符號（含 assumptions）——另外造一顆 `Symbol("x")`
會與 `Symbol("x", positive=True)` 不相等，代回去等於沒代，殘差永遠不會是 0。

> `Check` 建議維持**純資料**（不放 lambda 或 closure）。原本的理由是要 pickle 到判定的
> 子行程，那個理由已隨 D12 消失；但保持純資料讓它日後做離線預生成時可直接序列化。

2. 在 `app/generator/__init__.py` 加一行 `from . import exact`。
3. 若需要專屬的係數範圍檢查，在 `tests/test_generators.py` 加一個測試函式。

**設計約定**（詳見 PLAN.md §2.1）：

- **反向構造優先於正向求解**——先決定答案長什麼樣，再倒推題目。
  例如二階齊次是先選特徵根再算係數，線性系統是先選 `D` 與 `det = ±1` 的 `P`
  再令 `A = PDP⁻¹`。
- **SymPy 是驗證閘門，不是生成器**——`check` 描述「怎麼把一個表達式代回原方程」，
  `base.generate()` 會逐題驗證標準答案的殘差為 0，不過就換一組參數重抽。
- **逐步解答由模板自己寫**——文字敘述是固定的英文模板（介面語言為英文，
  見 PLAN.md D5），中間量由 SymPy 算，所以不會算錯，也能對應課本的解題流程。
  敘述裡的數學片段一律用 `$…$` 包起來，否則 KaTeX 不會渲染。
- **每一步的 `note` 要回答「為什麼」，不是重述「做了什麼」。** 判定移除之後，
  逐步解答是這個系統唯一的教學產出（PLAN.md §6 階段 2）。
  「Multiply both sides by $\mu$」是重述——式子本身已經說了；
  「$\mu$ 的作用是讓左邊變成一個乘積的導數，這樣才積得回去」才是解說。

> **新增一個展示**（不是題型）走的是另一條路：見
> [`app/static/demos/README.md`](app/static/demos/README.md) 的「新增一個展示」。
> 兩者刻意沒有共用抽象（PLAN.md D21）——出題的資料流是
> 「seed → SymPy → LaTeX → 一次性 HTML」，展示的是
> 「手勢 → 狀態物件 → `Float32Array` → 每秒數十次的 canvas 與音訊」，
> 除了「都是一個網頁」以外沒有共同結構。

---

## 前端資產

KaTeX 0.16.11、HTMX 2.0.4 與 fft.js 4.0.4 **全部自架**於 `app/static/vendor/`
（約 670 KB，已納入版本控制）。沒有 build step、沒有 npm 相依、不連外部 CDN——
clone 完就能離線啟動，校內網路連不到外網時數學一樣正常渲染。

展示區的 JS（`app/static/demos/`）**是我們自己寫的**，同樣沒有 build step：
瀏覽器原生的 ES modules，相對路徑 import。唯一的第三方是那支 FFT。

⚠️ **`vendor/fftjs/` 與另外兩個不同：它被改過一行。** 上游是 CommonJS，
而瀏覽器裡沒有 `module` 這個識別字，所以原封不動地 vendor 進來根本載入不了。
因此只改了 `module.exports = FFT;` → `export default FFT;` 這一行，其餘 500 行逐字保留；
改動與上游 sha256 記在該檔標頭，並由一項測試對「標頭之後的內容」做 sha256 比對。
選型比較（為什麼不是 ooura／fft-js／kissfft-js）見 PLAN.md §8.3 與 D31。

細節與升級步驟見 [`app/static/vendor/README.md`](app/static/vendor/README.md)。

三個測試會守住這件事（`tests/test_web.py`）：

- `test_referenced_static_assets_all_exist`：`base.html` 引用的每個 `/static/` 路徑都取得到
- `test_no_external_cdn_dependency`：頁面不得再出現 jsDelivr／unpkg／cdnjs
- `test_katex_fonts_referenced_by_css_are_present`：CSS 列到的 woff2 字型檔都在

題目的 LaTeX 是經 Jinja2 autoescape 後才輸出的（HTML 原始碼裡會看到 `&#39;`、`&amp;`），
瀏覽器解析時會還原成 `'` 與 `&`，KaTeX 讀到的是正確的內容。
**請不要為了「讓原始碼好看」而加上 `|safe`**，那會打開 XSS 的門。

---

## 部署注意事項

> ⚠️ **這一節在 v0.18 依 D35–D40 改寫過。** 它原本停在 v0.15，寫著三件已經不存在的事：
> 「`practice.db` 內含學號明文」、「學期結束後執行去識別化」、
> 「老師手上那份對照表含明碼」。**共用帳號之後，那三件事一件都不成立了。**
> 原文與逐項對照放在本節末，因為一份說得比實際嚴格的部署清單有一個實際的害處：
> 照著做的人會去找一個不存在的檔案、跑一支不存在的腳本，然後開始懷疑清單其他各項。

- **必須走 HTTPS**：系統處理密碼，沒有 HTTPS 不得上線。建議用 Caddy 自動申請憑證。
- `practice.db` **不含任何個人資料**（沒有學號、沒有姓名、沒有 IP，D35／D38）。
  裡面是**兩組共用帳號的 argon2id 密碼雜湊**，加上一批不指向任何人的用量計數。
  權限**仍然**須為 600、放在非 web root 目錄——密碼雜湊值得保護，
  而且離線暴力破解不受登入速率限制，這一點與有沒有個資無關。
- 備份請加密（`age` 或 `gpg`）。⚠️ **理由已經縮小，但沒有消失**：以前是
  「裡面有全班的學號」，現在是「裡面有兩組共用帳號的密碼雜湊」——
  而後者**換一次密碼就作廢**（`create_accounts.py reset`，一行）。
  保存期限因此不再是法遵要求，只是磁碟管理。
- ⛔ **不需要「學期結束去識別化」——沒有東西可以去識別化**（D35，PLAN.md §7 #39）。
  ⚠️ 這一項是**被取消，不是做完了**：若日後有任何功能重新蒐集一項個資，
  它要連同 PLAN.md §4.4 一起復活。（**v0.18（D41）補一句**：最可能觸發它的
  階段 3 對話介面已經砍掉了，目前看不到任何一條會讓它回來的途徑。）
- ⛔ **沒有「學號 ↔ 初始密碼」對照表可以發、也可以刪**——兩組密碼用不著對照表，
  `create_accounts.py` 把密碼**印在終端機上一次**（D35）。
  **系統這一側再也沒有任何含明碼的檔案。**
  ⚠️ 剩下的風險換了形狀：那一組班級密碼**一定會被轉傳**（LINE 群、共筆、學長姐的筆記），
  技術上擋不住。緩解是「換密碼只要一行」，而且系統裡沒有值得偷的東西。
  ⚠️ **終端機的捲動紀錄現在是明碼唯一的落點**，CLI 自己會提醒。
- 目前的速率限制是單進程記憶體計數器，因此請以**單一 uvicorn 進程**部署
  （`--workers 1`）；要多進程時需改用 Redis 或資料庫計數表。
  ⚠️ 開多個 worker **不會報錯**，只會讓速率限制安靜地失效。

> **FreeBSD 上的完整部署步驟**（rc.d 服務腳本、檔案權限、newsyslog 輪替、
> `sqlite3 .backup` 排程、HTTPS 的三種情境）見
> [`FREEBSD-DEPLOY.md`](FREEBSD-DEPLOY.md)。⚠️ 那份文件是在 Linux 沙箱裡寫的，
> **沒有一件事在 FreeBSD 上實測過**，因此逐項標記了「已驗證／依文件推論／未查證」。

> **先在家裡預演一次**（FreeBSD 筆電 + 家用 WiFi + macOS 當用戶端、
> 假網域 `engmath.home.arpa` + 自簽憑證）見
> [`FREEBSD-HOMELAB.md`](FREEBSD-HOMELAB.md)（v0.19 新增）。
> 它的用途是把「這台機器怎麼把服務跑起來」那一整段先跑完：
> 相依套件、rc.d 開機自動啟動、檔案權限、log 輪替、反向代理、HTTP→HTTPS，
> **以及代理層 log 不含 IP 的實測**。
> ⚠️ **驗不到的是**：Let's Encrypt 真憑證（私有 IP 簽不出來）、
> **校內 IP 限制與 VPN**（家裡完全模擬不到）、真實多人並發、校內防火牆流程。

- **（v0.19，D42）只開放校內 IP 連線，校外要先連學校 VPN。**
  過濾做在**反向代理層**，不做在應用層——應用層那條路要讀 `request.client`，
  而 `test_nothing_in_the_app_reads_the_client_address` 正是 D38 在應用層唯一的
  結構性保證（碰不到位址就「不可能」寫下位址）。
  **允許清單是「判斷」，D38 管的是「儲存」，兩件事正交**，
  所以 `_about.html` 那四句話一個字都不必改（它的動詞是 *store*）。
  校外的人看到的是一頁英文說明（403），不是裸的 403 也不是連線逾時。
  設定與驗收見 [`FREEBSD-DEPLOY.md`](FREEBSD-DEPLOY.md) §5.8。
  ⚠️ **校內網段清單要向網路中心索取（含 IPv6），VPN 那一段必須實測**
  ——PLAN.md §7 #41、#42，**在那之前 D42 不算結案**。

> ⚠️ **反向代理那一層的存取紀錄要親自確認一次。** 應用層與 uvicorn 不寫 IP 這件事
> 有五項測試盯著（見上面「存取紀錄不含 IP」），但 Caddy／nginx 在我們的行程外面，
> **預設會記來源 IP**。設定寫在 `FREEBSD-DEPLOY.md` §5.7；驗收方式只有一種：
> 第一次部署完成後 `tail` 一下代理的存取紀錄。PLAN.md §7 #40，**在那之前不算結案**。

<details>
<summary>這一節在 v0.15 的原文（三處已失效，保留供對照）</summary>

```
- `practice.db` 內含學號明文與密碼雜湊，權限須為 600，放在非 web root 目錄。
- 學期結束後執行去識別化（詳見 PLAN.md §4.4）。備份檔要一起處理，它最容易被漏掉。
- 老師手上那份「學號 ↔ 初始密碼」對照表含明碼，發完就刪（PLAN.md D32）。
```

| 原文寫的 | 為什麼不成立了 |
|---|---|
| `practice.db` 內含學號明文 | `student_no` 整欄消失（**D35**）。它是系統裡唯一一項個人資料，而老師撤掉了「用量紀錄要看得出是誰」這個需求，它就沒有存在的理由。**⚠️ 舊的 `practice.db` 接不上 v0.16 的程式**，啟動時會被拒絕並附上 `rm` 指令——見上面「從 v0.15 升級」。 |
| 學期結束後執行去識別化 | 沒有東西需要去識別化（**D35**，PLAN.md §7 #39）。那支腳本從來沒有被寫出來，而它現在也不會被寫出來。 |
| 對照表含明碼，發完就刪 | 一人一組密碼才需要對照表；兩組共用帳號不需要（**D35**）。CLI 改成把密碼印在終端機上一次。這是 v0.16 一個沒有預期到的安全性改善——**系統這一側再也沒有任何含明碼的檔案**。 |

**為什麼會停在 v0.15 兩個版本沒有人發現**：這三行寫的是**部署當天**才會做的事，
而系統還沒有正式部署過。**沒有人照著它做，就沒有人撞到它是錯的。**
同一類問題在 PLAN.md §6 階段 4（教師後台）也有三行，v0.18 一併修正。

</details>
