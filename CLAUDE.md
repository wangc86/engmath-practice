# 給 Claude 的專案須知

工程數學自動出題練習系統。規劃見 `PLAN.md`，安裝與啟動見 `README.md`。

> **v0.7：自動評分（作答判定）已捨棄**（PLAN.md D12）。`app/grader/`、`Attempt` 表、
> 作答 UI 與判定的子行程沙箱全部移除，保存在 git tag **`grading-v1`**。
> 若你在舊的對話紀錄或註解裡看到 `grader`、`Attempt`、`GRADER_*`，那些都已經不存在了。
>
> **v0.15：學生自行註冊已關閉**（PLAN.md D32–D34）。`/register`、`register.html`、
> `REGISTER_RATE_LIMIT` 全部移除，帳號改由 `scripts/create_accounts.py` 預先配發；
> 個資告知搬到 `/consent`（第一次登入必經）；學生可自行改密碼（`/account/password`）。
> **⚠️ 這三件事在 v0.16 又全部被推翻了，見下一段。**
>
> **v0.16：改為兩組共用帳號，系統不再蒐集任何個人資料**（PLAN.md D35–D40）。
> 這一輪拿掉的東西很多，**在舊對話紀錄或註解裡看到下面任何一個，都已經不存在了**：
>
> - `Student`、`student_no`、`consent_at`、`UsageLog.student_id`
>   → 換成 `Account`（`name` / `role`，永遠只有 `class` 與 `staff` 兩列）
>   與 `UsageLog.account_id`。
> - `/consent`、`consent.html`、`app/consent_gate.py`、`accept_consent()`
>   → 沒有個資就沒有告知義務。閘門改名為 `app/login_gate.py`，**形狀沒變**
>   （middleware 而不是 `Depends`，理由見該檔）。
> - `/account/password`、`password.html`、`PASSWORD_CHANGE_RATE_LIMIT`
>   → 密碼是共用的，讓一個學生改掉它等於把全班鎖在門外。
> - `/progress`、`progress.html`、`_usage.html`、"My Progress"
>   → 改為 `/activity`（全班彙總，**只有 `staff` 帳號進得去**）。
> - `create_accounts.py` 的 `batch`／`add` 子指令、含明碼的 CSV 對照表
>   → 只剩 `init`／`reset`／`list`，密碼印在終端機上一次。
> - `client_ip()`、以 IP 或帳號分組的速率限制
>   → 存取紀錄一律不含用戶端 IP（D38），速率限制是一個全站計數器。
>
> **v0.18：階段 3（對話介面 + LLM）已從規劃中砍掉**（PLAN.md D41）。
> **不要為這個系統寫任何 LLM 整合、對話入口、`app/sanitizer.py` 或 `ChatLog`**，
> 也不要把 `anthropic`／`openai` 之類的套件加進 `requirements.txt`。
> 那些東西**從來沒有被實作過**（所以沒有 tag 可以取回，也沒有殘留要清），
> 規格保留在 PLAN.md §3，整節標為已捨棄。
>
> 砍掉的理由裡有一條與這裡的硬規則直接相扣，值得記住：**對話介面需要一張
> `ChatLog` 稽核表，而它存的是學生打進去的原文**——稽核的意義就是那一欄不能雜湊、
> 不能省，所以它是個人資料。建了它，`app/templates/_about.html` 對學生說的
> 「不存你打的任何東西」就變成假話，而下面第三條與第八條硬規則會同時被違反。
>
> ⚠️ **一個順帶浮現、但很容易被無聲打破的性質**：執行期相依裡**沒有任何一個會連到
> 本機以外的東西**（前端資產自架、展示區完全跑在瀏覽器、沒有任何 API client）。
> 這不是設計目標，是 D18／D28／D35／D41 疊出來的結果——**打破它的那一行 import
> 會長得非常無害**，所以加任何新相依之前先想一下它會不會發出對外連線。
>
> **v0.19：網站只開放校內 IP 連線，校外要先連學校 VPN**（PLAN.md D42）。
> **這一輪一行程式碼都沒有動，而「沒有動」正是那條決定的內容**：過濾做在反向代理層。
> 做在應用層就要讀 `request.client`，而
> `tests/test_web.py::test_nothing_in_the_app_reads_the_client_address`
> 是第七條規則在應用層唯一的**結構性**保證——應用程式碰不到位址，
> 就「不可能」把位址寫進 log 或資料庫。**危險的不是那項測試會紅，是紅了以後
> 會有人想把它改掉**（判準與第六條選 middleware 而不是 `Depends` 相同）。
> 化解的方式是一句話：**允許清單是「判斷」，D38 管的是「儲存」，兩件事正交**；
> `_about.html` 的動詞是 *store*，那四句話一個字都不必改。
> ⚠️ **不要為這件事在 `app/` 底下加任何讀取用戶端位址的程式碼**，包含「只是為了
> 回一頁比較好看的 403」——那一頁由代理層發（`FREEBSD-DEPLOY.md` §5.8.4a）。
>
> **v0.20：三項新決定（PLAN D43–D45），而且這一版動到了程式碼。**
>
> - **D43 維持 HTTPS**（否決純 HTTP）。⚠️ **理由的重心不是機密性**：
>   📄 `AudioWorklet` 是 secure-context-only，而 **`http://localhost` 算安全脈絡**
>   ——所以「純 HTTP 行不行」**在本機測試時永遠會給出「可以」這個錯誤答案**，
>   而學生從別台機器連進來時展示區直接不能用。**不要用 `http://127.0.0.1:8000`
>   去判斷這件事。**
> - **D44 家用預演改為 Ubuntu + QEMU/KVM 虛擬機**，`FREEBSD-HOMELAB.md` 整份改寫。
>   ⚠️ 舊版假設的「實體 FreeBSD 筆電 + macOS 用戶端」**已經不存在**；
>   macOS 那台在新版裡一次都沒有出現。
> - **D45 官方不支援 Safari**（展示區只支援 Chrome 與 Firefox）。
>   ⚠️ **這一條有實作，不是一句宣告**：`app/static/demos/lib/browser.js`
>   （純函式的判斷邏輯）＋ `browser-check.js`（獨立的進入點，**刻意不從展示的
>   進入點呼叫**）＋ `app/templates/demos/_browser_notice.html`。
>   偵測分兩層——**能力偵測**（error）與**引擎白名單**（warning）。
>   ⚠️ **不要把第二層刪掉「因為能力偵測比較穩健」**：現代 Safari 三個關鍵 API
>   全都有，能力偵測在它身上會全部通過。理由寫在 `browser.js` 的檔頭，
>   而 `test_safari_with_every_api_present_still_gets_a_warning` 盯著它。
>
> **測試 437 → 471。**
>
> **v0.21：2S10 摺積與 LTI 展示落地，另加牆鐘時間紀錄（PLAN D46）。測試 471 → 612。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 三件新的事實：
>
> - 展示區多了第四頁 `/demos/lti/convolution`（`template_id = "demo.lti.convolution"`）。
>   ⚠️ 它的音訊**刻意不用 `ConvolverNode`**（那個節點的 `normalize` 預設 true，
>   會讓畫面上的 Σ|h| 與耳朵聽到的音量對不上），改為自己用頻域摺積算完塞進
>   `AudioBuffer`。理由與其餘三個取捨見 PLAN §8.9.4。
> - **影像的二維摺積判斷為不做**，理由不是工作量，是 §8.1 的准入判準
>   （「靜態圖表給不了什麼」）在影像上很弱——一張模糊前後的對照圖本身就是靜態圖表。
>   若日後要做，它應該是一個獨立的展示，不是塞進那一頁。
> - **每個實作任務現在都要記錄開始與結束時間**，見下面「⏱ 每個實作任務都要記錄
>   牆鐘時間」那一節。**這一條會影響你下一次開工的第一個動作。**
>
> **v0.22：2S11 脈衝與時頻取捨展示落地，另加下面的第九條硬規則。測試 612 → 686。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 四件新的事實：
>
> - 展示區多了第五頁 `/demos/transform/pulse`（`template_id = "demo.transform.pulse"`）。
>   ⚠️ 第二段是 `transform` 而**不是** `fourier`：W3 的級數與 W4 的變換是兩個主題
>   （週期 vs 非週期），沿用 `fourier` 會讓「一個查詢就分得開兩週的用量」失效。
>   `tests/test_demos.py` 盯著這件事。
> - ⛔ **這一頁的座標軸絕不自動縮放**，而那是它唯一一條會**安靜地把整頁內容刪掉**
>   的規則：軸跟著資料縮放的話，脈衝與頻譜都會看起來一樣寬，而兩張圖都還在動、
>   都沒有報錯、每一個數字都仍然正確。理由寫在 `app/static/demos/pulse.js` 的檔頭。
>   縱軸是相反的（跟著峰值走），判準與代價寫在 `drawMagnitude()` 旁邊。
> - **執行期跑的是數值積分不是 FFT**（課綱 W4 的 Python 指標就是這件事）。
>   ⚠️ 中點和乘的那個 `sinc(f·dt)` 不是修正係數，**它讓那個和變成一個精確的積分**；
>   拿掉它，畫面右緣的旁瓣會安靜地低 1% 左右。
> - **新增第九條硬規則（見下）。** 老師這一輪明確指定，而它是唯一一條
>   **沒有測試守得住**的規則。
>
> **v0.23：2S9 極零點與數位濾波器落地，階段 2S 的六個展示全部做完。測試 686 → 760。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 四件新的事實，而第一件是這個功能區裡最需要小心的一條：
>
> - ⛔ **這是唯一一頁有可能真的把喇叭弄壞的展示，而防護是三層、刻意重疊的**：
>   極點出圈就停止音訊並說明（`polezero.js`）、把 |H| 峰值壓回 1 且**只衰減不放大**
>   （`transform.js` 的 `safetyGain()`）、以及 worklet 裡的**逐樣本看守**
>   （`worklets/polezero-processor.js`）。**每一層單獨看都「應該夠了」，
>   而那正是三層必須同時存在的理由**——前兩層都在主執行緒上，
>   而主執行緒可能卡住、可能有 bug；音訊執行緒仍然在跑。
>   ⚠️ **不要因為「第三層從來沒有跳過」就把它拿掉。**
> - ⚠️ **只有一對極點，而那是一個技術約束不是版面選擇。** worklet 換係數時
>   對新舊兩組做線性內插，安全的根據是**二階的穩定域（Jury 三角形）是凸的**——
>   三階以上不是凸的，兩組穩定的係數之間的直線可以跑出去。
>   理由寫在 `transform.js` 的 `isStableSecondOrder()`，
>   而 `test_a_straight_line_between_two_stable_filters_stays_stable` 盯著它。
> - **展示區多了第六頁 `/demos/filter/pole-zero`（`template_id = "demo.filter.polezero"`）。**
>   ⚠️ 第二段是 `filter` 而**不是** `transform`：W4 的連續變換已經用掉了
>   `transform`，沿用會讓「一個查詢就分得開兩週的用量」失效。
>   `tests/test_demos.py` 現在斷言**每一個主題字首各只有一頁**。
> - ⚠️ **`peakGain()` 的格點數（4096）是一個安全參數，而它看起來像效能參數。**
>   它是第二層防護的分母；格點太疏會跳過很尖的共振峰，於是正規化不足、
>   輸出比預期大聲。它與極點半徑滑桿的 `step`（0.001）之間有一個隱含關係，
>   **而沒有測試把兩者綁在一起**。動任何一邊之前先讀 §8.9.6 的「仍然不穩」第 2 點。
>
> **剩下的 2S 工作只有 2S7（跨瀏覽器實測，沙箱做不到）與 2S8（無障礙一輪）。**
>
> **v0.25：階段 2B 的前半落地（2B0–2B4，Fourier 級數，課綱 W3）。測試 866 → 992。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 但它**第一次動到驗證閘門本身的形狀**，五件事：
>
> - ⛔ **`base.generate()` 不再自己算殘差，它呼叫 `problem.verify_answer()`。**
>   `check` 的型別從 `Check` 變成 `Verifier` 協定（`verify(problem) -> (bool, str)`），
>   目前三個實作：`Check`、`fourier.core.FourierCheck`、`fourier.symmetry.ParityCheck`。
>   **既有五個 generator 一行都沒有改。**
>   ⚠️ **`Problem.residual_is_zero()` 還在，但它現在只是一個薄殼**——
>   新程式碼請用 `verify_answer()`，因為對 Fourier 而言「殘差」這個詞不適用
>   （沒有方程可以代回去），繼續用那個名字會讓人以為 `check.residual_of()` 一定存在。
> - **`Problem.answer_kind` 回來了，但只有三個值**：`expression`（預設）、
>   `coefficients`、`classification`。⚠️ **PLAN §2.2.1 那張表寫的是五個**——
>   `general`／`ivp`／`vector` 併成一個，理由寫在 `base.py`（它們可以從 `Check` 推出來）。
>   ⛔ **`classification` 的 `answer_expr` 是 `None`**，所以任何碰 `answer_expr` 的
>   程式都要有一個**明示的分支**跳過它（不是 `try/except`）。
> - ~~**`Problem.assets` 仍然不存在，而那是一個判斷不是遺漏。**~~ PLAN 把它排在 2B0，
>   落地時延後到相圖那一輪（2B6）——它的三條約定有兩條要有產出者才寫得出測試，
>   先加一個空欄位等於先開一個沒有人看守的 `|safe` 出口。理由寫在 §2.2.1 的落地紀錄。
>   **⚠️ v0.26 補上了它**（連同白名單與洩題防護），見下面 v0.26 那一段。
> - ⛔ **Fourier 的閘門是四層，而且四層都要跑（D48）。** 沒有任何一層是充分的，
>   所以「這麼多層太慢了」不是一個可以自己下的結論。⚠️ **第二層（Parseval）
>   在部分參數上跳過是正常的**（實測 7/90，全部集中在半幅展開的難度 3），
>   但跳過必須記一行 log，而且比例由 `test_how_often_the_parseval_gate_is_skipped` 印出來。
> - ⚠️ **`test_latex_is_katex_safe` 原本有一項是錯的**：它禁止 `\begin{cases}`，
>   理由寫著「KaTeX 不支援」——**0.16.11 支援它**。現在 `\begin{cases}` 只對
>   非 Fourier 的題型禁止，而理由換成正確的那一個（它出現在 `ode/laplace.py` 代表
>   有人把閘門用的 `Piecewise` 拿去 `sp.latex()` 了）。另新增
>   `test_every_formula_renders_in_the_bundled_katex`，用 node 載入自架的 KaTeX
>   把每個題型的每一行真的渲染一次——**猜錯的黑名單同時做錯兩件事**：
>   擋掉可以用的東西，而且對它沒想到的東西完全沒有意見。
>
> ⚠️ 在這個沙箱裡單次指令約 180 秒上限，而 `tests/test_generators.py` 要 10 分鐘，
> 所以它**必須分批跑**。
> ⛔ **切法換過兩次**：v0.35（老師刪了五個題型，舊的九批有四批整批空掉）
> 與 **v0.39**（新增 Fourier 變換，它自己就要 100 秒）。現在是**八批**：
>
> ```bash
> pytest tests/test_generators.py -q -k "separable or first_order or second_order"
> pytest tests/test_generators.py -q -k "laplace or y_prime"
> pytest tests/test_generators.py -q -k "full_range"
> pytest tests/test_generators.py -q -k "half_range"
> pytest tests/test_generators.py -q -k "linear_2x2"
> # v0.39：Fourier 變換。⚠️ 關鍵字用 `forward` 不用 `transform`——
> # 後者會連 `ode.laplace.transform` 一起撈進來。
> pytest tests/test_generators.py -q -k "forward or textbook or inversion or plancherel or convention_lives or single_transform or parenthesised"
> # 兜底批太大，再切成三塊（第三塊只有那一項 KaTeX 渲染）：
> B="not (separable or first_order or second_order or laplace or y_prime or full_range or half_range or linear_2x2 or forward or textbook or inversion or plancherel or convention_lives or single_transform or parenthesised)"
> pytest tests/test_generators.py -q -k "$B and not katex and not the_"
> pytest tests/test_generators.py -q -k "$B and not katex and the_"
> pytest tests/test_generators.py -q -k "katex"
> ```
>
> ⚠️ **各批之間會有重疊，那是可以的**——真正保證「每一項都跑到」的是那個
> `not (…)` 兜底批，不是各批加起來剛好等於總數。
> ⚠️ **`y_prime` 一定要跟 `laplace` 同一批**：
> `test_the_gate_would_miss_a_wrong_y_prime_at_zero_without_that_field` v0.35
> 改成用 `ode.laplace.ivp` 抽樣，同一批可以共用快取。
> 理由是 `_cached_sample` 的快取**每個行程一份**：同一個題型的通用檢查
> 放在同一批就只生成一次題目，散在不同批就是重複生成。
>
> **v0.24：階段 2A 開工，2f（拉普拉斯，課綱 W9）落地。測試 760 → 866。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 五件新的事實：
>
> - **`app/generator/ode/` 出現了，而且裡面只住著新寫的 `laplace.py`。**
>   既有四個 generator 加上 `base.py`、`pretty.py` 仍在平面結構裡。
>   ⚠️ **這不是忘了搬**——D16 的那一項（工作項 2a0）需要 `git mv`，
>   而這個環境不能 unlink。混著放安全的理由只有一句：**`template_id` 與檔案路徑
>   從來沒有耦合過**（D16 明文寫過，正是「所以搬檔案很便宜」的那個論證）。
>   ⛔ 老師日後執行 2a0 時**不得順手改 `template_id`**。
> - **落地成兩個題型**：`ode.laplace.transform` 與 `ode.laplace.ivp`（D47）。
>   ⚠️ 兩者都掛在 `ode.` 底下，而 `transform` 那一個嚴格說不是 ODE——
>   刻意接受的一點不精確，見 D47。
> - ⛔ **難度 3 的答案有兩個形狀，而它們不可以各寫一遍。** 閘門看
>   `Piecewise`、學生看 $u(t-a)$，而 `Piecewise` 那個是從顯示形
>   **`.rewrite(Piecewise)` 機械產生**的。理由：$u(t-a)$ 的導數會生出
>   $\delta(t-a)w(0)$，數學上是 0 但 SymPy 化簡不掉，閘門會擋下正確答案。
>   ⚠️ 連帶一條硬性的：**`answer_expr` 不可以拿去 `sp.latex()`**
>   （`\begin{cases}` KaTeX 不支援），本模組的 LaTeX 一律走 `_tex()`。
> - ⛔ **不要為這個題型加脈衝（δ 外力）的難度。** 上面那個 `Piecewise` 技巧
>   在脈衝上**會給出錯的答案**：`Piecewise` 的微分忽略跳躍，那個 δ 會安靜消失、
>   殘差照樣是 0、**閘門會對錯的答案說通過**。理由寫在 `laplace.py` 的檔頭，
>   而 `test_laplace_ivp_answers_have_no_distributions` 盯著它。
> - **`Check` 多了一個欄位 `ic_derivative_values`**（$y'(t_0)$、$y''(t_0)$…）。
>   在這之前純量的二階初值問題只驗得了 $y(t_0)$。既有四個 generator 一行未動。
>
> **v0.26：2d（系統的重根／複數／非齊次）＋ 2B6/2B7/2B9（相圖）落地。測試 992 → 1271。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 但它是**第一次有非 LaTeX 的東西被渲染到題目卡片上**，而那件事帶進三條要記住的規則：
>
> - ⛔ **`Problem.assets` 的鍵必須在 `base.ASSET_KEYS` 白名單裡**（建構時就拋，
>   不是渲染時），而 `_solution.html` 是一個**明示的 `{% if %}`，不是迴圈**。
>   理由：渲染 SVG 一定要 `|safe`，而 `|safe` 關掉的正是 Jinja 唯一那道 XSS 防線
>   ——「範本印得出什麼」不可以取決於 generator 塞了什麼進去。
>   **加一個新鍵要同時改三個地方**（`ASSET_KEYS`、範本、`tests/test_web.py` 的洩題測試），
>   那個成本就是它的功能。
> - ⛔ **相圖只能出現在第二層 `<details>` 裡面，這是第五條硬規則的延伸。**
>   一張鞍點圖等於直接告訴學生兩個特徵值異號、一張同心橢圓圖等於告訴學生
>   $\operatorname{tr}A = 0$——**插圖會把答案洩掉，而且是靜默地洩**：頁面不會壞、
>   不會拋錯，只是這一題白出了，而改程式的人（已經知道答案）不會覺得哪裡不對。
>   ⚠️ **非齊次那個題型刻意沒有相圖**（D51）：$\mathbf{g}$ 含 $t$ 時不是自守系統，
>   軌跡會互相穿越，「相圖」這個東西不存在。**不要好心幫它補上一張。**
> - ⛔ **複數特徵值的答案不得含 $i$，也不得寫成振幅－相位形**（附錄 C.2、D11 的擴充）。
>   $C_1 e^{(\alpha+i\beta)t}\mathbf{v}$ 與 $R e^{\alpha t}\sin(\beta t + \varphi)$
>   **兩者都是正確答案、殘差都是 0、驗證閘門都會放行**——守它們的各是一項專門的測試。
>   ⚠️ 特別注意 `sp.simplify` 會自己生出後者，所以 `systems/linear_2x2.py` 的難度 3
>   刻意用 `sp.expand` 而不是 `sp.simplify`。
>
> 另外三件事：**相圖的軌跡刻意不去拿 generator 算好的解**（自己用 $e^{At}$ 的封閉形式
> 算，否則「軌跡切線平行於 $A\mathbf{p}$」的斷言會退化成「同一段程式跑兩次」）；
> **`app/generator/plot.py` 在第一層而不是 `systems/` 裡面**（它與 `pretty.py` 同類，
> 是沒有註冊題型的共用工具，2a0 不必搬它）；以及 **`test_generators.py` 現在要分七批跑**
> （依題型字首切，理由見 PLAN §1.7）。
>
> ⚠️ **一個誠實的缺口**：相圖的箭頭**在真的瀏覽器裡沒有看過**。沙箱是用 `cairosvg`
> 光柵化來看的，它把 `<marker>` 畫對了，但它不是 Chrome 也不是 Firefox。
> 這與 2S7 是同一類的缺口。

> **v0.27：2a 待定係數與 2b 恰當方程落地，階段 2A 的題型只剩 2e。測試 1271 → 1355。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 五件新的事實，而前兩件是這一輪最需要小心的：
>
> - ⛔ **`ode.second_order.undetermined` 的難度軸是共振重數 $m$（0／1／2），
>   而驗證閘門對 $m$ 完全沒有意見。** 把 $x^m$ 多乘一次得到的 $y_p$ **仍然讓殘差為 0**
>   （多出來的那一項是齊次解，被 $C_1, C_2$ 吸收），所以「難度 3 真的是重根共振」
>   **只有 `test_the_resonance_multiplicity_is_what_the_difficulty_promises` 一項在守**。
>   ⚠️ 它失效的症狀是**學生練不到重根共振，而每一題都完全正確**。
>   右式三族（指數／多項式／三角）與「有沒有初值條件」是**兩條與難度正交的軸**，
>   不要把它們搬到難度上。**難度 3 只有指數一種而且不是漏掉**（理由寫在檔頭）。
> - ⛔ **`answer_kind` 現在有四個值**，新的那個是 `implicit`
>   （`ode.first_order.exact`，答案是關係式 $F(x,y) = C_1$，`answer_expr` 是位勢函數 $F$）。
>   **加它的理由不是型別上的潔癖**：`test_steps_are_complete` 原本「比等號右邊」的作法
>   對隱式解**會恆真**（等號右邊永遠是 $C_1$），必須改成逐字比對。
>   ⚠️ **漂亮度那一路刻意不分支**——$F$ 就是一個普通的算式。
> - **`Verifier` 協定多了第四個實作 `ode.exact.ExactCheck`，它有四層。**
>   ⛔ **第 2 層（非退化）不是型別檢查**：$F$ 退化成常數時 $F_x = F_y = 0$，
>   第 1 層的 $M F_y - N F_x$ **恆為 0**——閘門會對一個什麼都沒說的「答案」說通過。
>   ⛔ **第 4 層（難度 3 宣稱原式不恰當）守的是「題目本身是不是真的」**：
>   少了它，一個把 $a$ 抽成 0 的 bug 會生出一個已經恰當的方程，然後要學生去找一個
>   等於 1 的積分因子——**答案正確、步驟正確、只有題目是假的**。
> - ⚠️ **`sp.classify_ode()` 不能當恰當性的第二意見。** SymPy 1.14 對一個
>   $M_y \ne N_x$ 的方程照樣回報 `1st_exact`（實測）。
>   `test_sympy_classify_ode_is_not_an_oracle_for_exactness` 把這個事實釘住，
>   **它會在 SymPy 修好的那天變紅，而那時候該做的是刪掉它，不是把斷言反過來寫。**
> - **新增 `VERIFY-CHECKLIST.md`**：一份只收「自動測試守不住、只有老師做得到」
>   的實測清單。⚠️ **維護它的規則只有一條**：**已經被自動測試涵蓋的東西不准放進去**
>   ——被忽略的清單等於沒有清單。

> **v0.28：內容開放閘門落地（PLAN D52–D56）。測試 1355 → 1402。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 但它是**第一次有一道閘門擋在既有內容前面**，帶進五件要記住的事：
>
> - ⛔ **新增題型或展示時，要在 `app/curriculum.py` 的 `CONTENT` 補一列。**
>   忘了補的症狀是**那個題型永遠開不起來**——閘門看不到它、管理頁不列它、
>   學生的選單也不會有它，而**不會拋錯、不會壞掉任何頁面**。
>   `test_every_registered_template_has_a_week` 盯著（雙向：漏一個會紅，
>   多一列指不到東西也會紅）。
> - ⛔ **`app/curriculum.py` 是純資料、零相依，不要讓它 import 任何東西。**
>   它同時列出了出題與展示的識別碼，而那**不違反 D21**——因為它只認得字串，
>   沒有型別、沒有基底類別、沒有任何一邊要實作的介面。一旦它 import 了兩邊，
>   它就變成一個接縫，而接縫會長出東西。
> - ⚠️ **強制點是 middleware（`app/release_gate.py`），但有一個明示的例外**：
>   `POST /practice/generate` 的題型代號在表單 body 裡，而
>   `BaseHTTPMiddleware` 讀掉 `receive` 之後下游路由就拿不到 body。
>   那條路徑列在 `SELF_GATED_PATHS` 裡由 `routes/practice.py` 自己守，
>   **而那三行不可以拿掉，也不可以搬進 `generate()`**（`/activity`、
>   `scripts/preview.py`、整份 `test_generators.py` 都合法地呼叫 `generate()`，
>   那裡沒有「哪個帳號」這個概念）。
>   `test_every_route_is_classified_for_release_gating` 會列舉整張路由表並
>   **把三份分類清單逐字釘死**。
> - ⛔ **預設是全部關閉，不要「為了方便」改成全開。** 預設全開的失敗方式
>   （學生第一週看到全部 16 週的內容）**沒有任何人會發現**；預設全關的失敗方式
>   （學生看到一頁空的）看得見。它有三個落點，一個都不能省：學生端的空狀態
>   文字、啟動時的 WARNING、管理頁的「x / 20」。
> - ⛔ **未開放的內容在學生端完全不出現：不灰掉、不留標題、不寫「尚未開放」。**
>   這是 D24 的延伸而不是例外，完整的張力分析在 D56。分界線一句話：
>   **說明機制可以，列出清單不行**。
>
> ⚠️ 順帶：`app/main.py` 補上了 `openapi_url=None`。`docs_url`／`redoc_url`
> 早就關了，但 FastAPI 仍掛著 `/openapi.json`，**已登入的學生打它會拿到 200，
> 內容是整張路由表**。那是一個一直都在的洞，被上面那項列舉測試逼出來的。

> **v0.29：改為學生自行從 GitHub 下載、在自己的電腦上安裝執行（PLAN D57–D61）。**
> **測試 1305（1402 − 97）。這是本專案範圍最大的一次推翻，保存在 git tag `hosted-v1`。**
>
> ⛔ **在舊對話紀錄或註解裡看到下面任何一個，都已經不存在了**：
>
> - `Account`、`ROLE_CLASS`／`ROLE_STAFF`、argon2、`hash_password`、
>   `SESSION_SECRET`、`SessionMiddleware`、`LoginGateMiddleware`、`RateLimiter`、
>   `current_account`／`staff_account`、`NotLoggedIn`／`NotStaff`、`/login`、
>   `/logout`、`login.html`、`_about.html`、`scripts/create_accounts.py`
>   → **沒有帳號了**（D57）。本機單人使用，能執行 `uvicorn` 的人本來就讀得到
>   整個資料夾。
> - `UsageLog`、`/activity`、`activity.html`、`DEMO_ACTION`、`DEMO_SENTINEL`、
>   `app/access_log.py`、`take_over_uvicorn_access_log()`、`IP_BEARING_FIELDS`
>   → **系統不再蒐集任何東西**（D58）。⚠️ **D38 那一整套（存取紀錄不得含 IP）
>   也一起拆了**：唯一的用戶端是 `127.0.0.1`、唯一看得到那行 log 的人就是本人。
> - **整個 `app/db/`**（`models.py`、`session.py`、`init_db()`、
>   `LegacySchemaError`）、`sqlmodel`／`argon2-cffi`／`itsdangerous`
>   → **沒有資料庫了**（D58）。
> - `ReleaseState`、`app/release.py`、`app/release_gate.py`、
>   `/admin/content`、`admin_content.html`、`tests/test_release.py`、
>   `release_week`（改名 `primary_week`）
>   → **沒有開放閘門了**（D59）。⚠️ **`app/curriculum.py` 留下來了**，
>   用途從「決定開放什麼」換成「決定選單怎麼分組」。
> - `FREEBSD-DEPLOY.md`、`FREEBSD-HOMELAB.md`、`WINDOWS-SETUP.md`、
>   `.env.example`、`COOKIE_SECURE`、`PRACTICE_DB`
>   → **沒有站台就沒有部署**（D60）。
>
> **五件要記住的事：**
>
> - ⛔ **不要為了「將來也許要部署」把任何一項加回來。** 一組沒有使用者的
>   設定會讓讀程式的人以為系統支援某件事，而它不支援。真的要回頭做站台版，
>   `git checkout hosted-v1 -- <路徑>` 一行就取得回來。
> - ⛔ **應用程式現在沒有狀態，而那是一個要守住的性質。**
>   沒有資料庫、沒有 session、沒有任何會寫到磁碟上的東西——關掉它就什麼都
>   不剩，而**頁尾對使用者寫著那句話**。最可能打破它的不是「有人加了一張表」
>   （那看得見），是**有人為了一個看起來無害的小功能加了一行 `import sqlite3`**
>   （例如「把上次選的題型記起來」）。
>   `test_nothing_in_the_app_imports_a_database` 盯著。
> - ⛔ **頁尾還說「它從不把任何東西送出網路」，而那也必須是真的。**
>   `test_the_footer_promise_is_true_no_outbound_url_in_any_page` 掃每一頁的
>   `href`／`src`／`action`，只放行 XML 命名空間。**執行期相依裡沒有任何一個
>   會連到本機以外**——這條老規則現在有了一個學生看得到的承諾在背書。
> - ⛔ **新增題型或展示時，要在 `app/curriculum.py` 的 `CONTENT` 補一列。**
>   v0.28 忘了補的症狀是「開不起來」；**現在的症狀是「它整個不出現在選單上」**，
>   而且不會報錯。`test_every_registered_template_has_a_week` 盯著。
> - ⚠️ **每一輪開工的第一件事多了一項**：把提示詞原文存進 `dispatches/`，
>   **在 `turnaround.py start` 之前**。理由見那個目錄的 README——
>   前面約二十輪的原始提示詞已經拿不回來了，而這個專案花了大量力氣讓
>   「決定」不會遺失，卻沒有人想過要保存「要求」。
>
> **⚠️ 一件沒有變、而且變得更重要的事**：這個專案現在是**公開散布**的
> （GitHub + 學生自己 clone），所以 `app/static/vendor/` 底下三份 LICENSE
> 從「應該做」變成「必須做」。`test_vendor_licenses_are_kept` 盯著。

> **v0.30：2B5（Parseval）與 2B8（平衡點分類）落地（PLAN D62、D63）。測試 1305 → 1386。**
> 這一輪**沒有推翻任何東西**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 四件新的事實：
>
> - **題型數 14 → 16**：`fourier.parseval.series_sum`（W3）與
>   `system.linear_2x2.classification`（W10/W12–13）。
>   ⛔ 兩個都記得在 `app/curriculum.py` 補了一列——**那是新增題型時最容易
>   漏掉、而且漏了不會報錯的一步**。
> - ⛔ **Parseval 的閘門「一層都不准跳過」，而這與 D48 不同。**
>   `FourierCheck` 允許它的 Parseval 那一層在算不出封閉形式時跳過並記 log；
>   **這個題型不行，因為題目的內容就是那個和**——算不出來的樣本不是
>   「少驗一層」，是「這一題沒有答案」，所以要重抽。
> - ⛔ **平衡點分類的難度軸不累積**（難度 3 只出邊界情形，不含節點與螺旋）。
>   第一版寫成累積，實測難度 3 只有 5/11 的機會真的是邊界情形，
>   而難度說明上寫著 "Boundary cases"——**那句話會變成假話，
>   而每一題都完全正確**。`test_the_equilibrium_type_is_what_the_difficulty_promises`
>   盯著。
> - ⚠️ **`test_answer_is_pretty` 對 Parseval 開了一個明示的例外**
>   （$\pi^4/90$ 的分母 90 會被醜分數檢查擋下來，而那個啟發式在這裡問錯了
>   問題）。⛔ **但例外不是豁免**：`test_the_parseval_answer_is_one_of_the_named_constants`
>   接手，而它要求答案**恰好**是白名單上那四個常數之一——比原本的檢查嚴格。
>
> ⚠️ 順帶：PLAN §1.7 那張表在 v0.29 有三個分項數字是錯的（總數是對的，
> 三個錯誤恰好互相抵銷）。v0.30 逐檔 `--collect-only` 量過並更正，
> 更正本身記在該處——**安靜改掉與安靜寫錯，對讀的人是同一件事**。

> **v0.31：工作項 2a0 落地——`app/generator/` 的子目錄遷移做完（D64）。測試 1386 → 1386。**
> 這一輪**沒有推翻任何設計決定**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 但它推翻了一個**關於環境的事實**，而那件事比這次搬的四個檔案重要：
>
> - ⛔ **「不能刪檔」不是天生的限制，是一道可以當場請老師授權解除的權限政策。**
>   下面那一節（「執行環境限制：不能刪檔」）從 v0.3 起就寫著它，三個
>   `__init__.py` 的 docstring、`PLAN.md` §1.5、README 都照著它寫了一長串
>   「這一項只有老師在自己的電腦上做得到」。**沒有人回頭驗證過那句話**，
>   而 2a0 就這樣被擋了十幾輪。
>   ⚠️ **正確的作法是每個新工作階段開頭實測一次**（`touch .probe && rm .probe`），
>   而不是讀文件——文件記的是上一次的環境。
> - **搬了四個檔案**：`separable.py`／`first_order_linear.py`／`second_order_homog.py`
>   進 `ode/`；`system_2x2.py` → `systems/real_distinct.py`。
>   ⚠️ **不是 `systems/linear_2x2.py`**（§1.5 那道指令寫的）——那個名字 v0.26
>   已經被三個題型佔用了，照原指令跑會**直接覆蓋掉它們，而 `git mv` 不會抱怨**（D64）。
> - ⛔ **一個 `template_id` 都沒有改**，這是 2a0 唯一的驗收標準。
>   `sorted(REGISTRY)` 前後逐字相同（16 個鍵），`tests/test_generators.py` 0 行改動。
> - **`base.py`／`pretty.py`／`plot.py` 留在 `app/generator/` 這一層，那是刻意的**：
>   它們沒有註冊任何題型，不屬於任何一章。⚠️ 不要「為了整齊」把它們也塞進子目錄。
> - ⚠️ **一個沒有收乾淨的角，寫在這裡而不是假裝已經解決**：
>   `systems/linear_2x2.py` 自己算一份 `P_CANDIDATES` 而不 import，原本的理由是
>   「那個模組是 2a0 要搬的檔案」——**那個理由現在過期了**，而隔壁的 `classify.py`
>   已經是 import 的那一邊。兩份實測逐項相同。**v0.31 刻意沒有順手統一**：
>   合併會改變抽樣走的那個 list，而 2a0 的驗收是「只搬檔案」。要合併就單獨做一次，
>   並且用同一顆 seed 比對前後產生的題目。

> **v0.32：§1.7 併表、依相依性挑測試（D65）、2c 的樣本與初篩備妥。測試 1386 → 1394。**
> 這一輪**沒有推翻任何設計決定**，所以上面那些「已經不存在了」的清單一條都沒有變。
> 五件事：
>
> - ⛔ **新增了「只跑相關的測試」那一節（見下），而那一節的後半比前半重要。**
>   `python scripts/test_deps.py select` 會依這次改到的檔案印出該跑的指令
>   （改一個題型 838s → 312s，只改文件 → 0s），**但什麼時候一定要全跑
>   是一張明確的清單**，不是判斷題。
> - ⛔ **新增題型或測試檔之後要重量地圖**，否則 `select` 挑不到新東西。
>   忘了重量的症狀有三種，`tests/test_test_deps.py` 各有一項盯著——
>   ⚠️ **但「地圖是不是最新的」沒有測試守得住**，要驗那件事就得把全套再跑一遍。
> - **`2c-PRESCREEN.md` 是產生的，不是手寫的**（`scripts/review_steps.py`）。
>   ⛔ **這一輪一句題目敘述都沒有改**：2c 的判斷是老師的，而一個
>   「順手改得比較順」的敘述會讓那一輪的產出從老師的品味變成 AI 的品味，
>   **而且沒有人看得出來換過**。
> - ⚠️ **初篩把 §7 的一句老話推翻了**：#29 寫著「已知至少一處不一致
>   （`separable.py` 的 $y$ vs $y(x)$）」，掃過 240 題之後是**四處**。
>   那句話從 v0.8 起就在，而沒有人回頭數過。
> - ⚠️ **這一輪踩到的兩個坑都在新寫的工具裡，而第二個是規則 4 的無聲降級**：
>   `op_count()` 對 `MutableDenseMatrix` 走進 `except: return 0`，
>   於是四個系統題型的難度欄安靜地印出 `0→0→0`（看起來像「答案完全沒有變複雜」，
>   其實是「根本沒量到」）。**它發生在一支用來找問題的工具裡**——
>   改成量不到就回 `None`、印成 `—`。

> **v0.33：第九條硬規則多了第二半——回報要讓人不必打開 repo 就看得懂。**
> 這一輪**只改文件，沒有動任何程式碼**，測試 1394 → 1394。
>
> - 老師的回饋原文與那四條規範寫在第九條底下（見「專案的九條硬規則」那一節）。
>   ⛔ **這一條與第九條一樣沒有測試守得住**，而且它的失效方式很安靜：
>   **一份準確但看不懂的回報，看起來與一份好的回報一樣。**
> - ⚠️ **這一輪順便示範了 D65（依相依性挑測試）的其中一格**：
>   `python scripts/test_deps.py select` 對「只改了 `.md` 檔」的回答是
>   **「不必跑任何測試」**，所以這一輪沒有跑那 1394 項。

> **v0.35：老師刪掉五個題型與一個從未實作的規劃項（D67）。題型 16 → 11，測試 1394 → 1159（−235）。**
>
> ⛔ **在舊對話紀錄或註解裡看到下面任何一個，都已經不存在了**：
>
> - `ode.first_order.exact`（恰當方程與積分因子）、`app/generator/ode/exact.py`、
>   **`ExactCheck`**（本專案唯一走隱函數微分的驗證器，四層）
> - `ode.second_order.undetermined`（待定係數）、`app/generator/ode/undetermined.py`
> - `system.linear_2x2.nonhomogeneous`（系統非齊次）——它是 `systems/linear_2x2.py`
>   裡的第三段，整段移除
> - `fourier.symmetry.parity`（奇偶性）、`app/generator/fourier/symmetry.py`、
>   **`ParityCheck`**
> - `fourier.parseval.series_sum`（Parseval 求級數和）、`app/generator/fourier/parseval.py`
> - **工作項 2e（參數變異法）** ——它**從來沒有被實作過**，所以沒有東西要移除；
>   §7 #14（$g(x)$ 白名單）連帶失去標的
>
> ⛔ **這是課程範圍的決定，不是品質的決定。** 五個題型當時全部綠燈，
> 閘門也都有突變測試守著。**不要因為「它們被刪掉了」而推論那裡曾經有問題。**
> 全部取得回來：`git log -p -- <路徑>`（沒有另外打 tag，理由見 D67）。
>
> **五件要記住的事：**
>
> - ⚠️ **`answer_kind = "implicit"` 現在沒有任何題型在用**（它是為 `ode.first_order.exact`
>   的 $F(x,y)=C_1$ 加的第四個值）。**`base.py` 刻意留著它**，理由寫在那裡。
> - ⛔ **`Check.ic_derivative_values` 差一點失去唯一的證明。** 守它的那一項
>   （`test_the_gate_would_miss_a_wrong_y_prime_at_zero_without_that_field`）
>   原本用待定係數當載體，而那個欄位**`ode.laplace.ivp` 的難度 2、3 仍然在用**。
>   v0.35 把那一項**改寫成用 `ode.laplace.ivp`**，沒有跟著刪。
>   ⚠️ **這是這一輪最容易做錯的一步**：跟著刪掉會讓一個還在用的欄位變成沒有人守。
> - ⛔ **老師要求「現在的部署方式下不需要的測試也刪掉」，而那句話底下是性質相反的兩組。**
>   **A 組（回歸看守，44 項）**——檢查已拆掉的帳號／資料庫／判分端點沒有偷跑回來，
>   **已刪**。**B 組（性質看守，8 項）**——檢查「沒有資料庫、不連外網、檔案不外流」
>   這些**現在還成立**的性質，**保留**。⛔ **B 組不是「不需要的測試」，
>   它們正是讓那個部署方式成立的東西**（第八條硬規則：頁尾寫著的話必須是真的）。
>   這個分法是問過老師的，他選了「只刪 A 組」。
> - ⚠️ **CLAUDE.md 那一長串「已經不存在了」的清單，執行版本從此少了一半。**
>   A 組刪掉之後，「12 個已移除模組 import 不到、14 條已移除端點回 404」
>   這件事**只剩下文字，沒有測試**。加回任何一個舊模組不會讓任何東西變紅。
> - ⚠️ **`test_generators.py` 的分批切法換了**（舊的九批有四批整批空掉），見上面那一節。

> **v0.36：相依地圖會自己跟上了（§7 #44、D68）。測試 1159 → 1162（+3）。**
> 這一輪**沒有推翻任何設計決定**，它補的是 D65（依相依性挑測試）自己承認的
> 那個最大的縫。三件事：
>
> - ⛔ **平常改用 `python scripts/test_deps.py run`，不要直接跑 `pytest`。**
>   `run` 把量測的鉤子掛在「本來就要跑的那一次」上，跑完把相依聯集回地圖
>   ——**所以更新是免費的**。直接跑 `pytest` 不會更新地圖（不是錯，但下一次
>   會保守地多跑一輪）。
> - ⛔ **每一條相依現在都記著它被觀察到時的 mtime**，對不上就一律要跑。
>   ⚠️ **副作用是好的**：`git clone` 之後每個檔案的 mtime 都是新的，
>   所以「第一次下載到新機器要跑全部」**從機制裡長出來，不再靠人記得**。
> - ⚠️ **`-k` 窄化在有相依過期時會自動關掉。** 那不是保守，是因為窄化會
>   濾掉大部分測試，而一條只有被濾掉的測試碰得到的相依會**永遠**沒有機會
>   重新觀察——每一輪都判定過期、每一輪又都窄化掉唯一能修正它的那一項。
>
> ⚠️ **這一輪的地圖格式變了**（`deps` 從清單變成「路徑 → mtime」）。
> 舊格式讀得進來（`_load_map` 會遷移），但**遷移只是把現在的 mtime 蓋上去**
> ——它假設地圖在遷移的當下是對的，而不是讓它變正確。
> 這一輪的地圖是**整份重量出來的**，不是遷移出來的。

> **v0.40：§7 #23 結案——$a_0$ 要除 2（D73）。⛔ 一個答案的數值都沒有變。測試 1249 → 1251（+2）。**
>
> - 老師 2026-09-08 答「要除 2」，也就是
>   $f(x) \sim \frac{a_0}{2} + \sum_{n\ge1}(\cdots)$、$a_0 = \frac1L\int_{-L}^{L} f\,dx$
>   ——**與 v0.25 起的暫定值相同**，所以沒有任何一道題目的輸出改變。
> - ⛔ **真正的發現是：在這之前那個慣例其實沒有人守。**
>   唯一相關的測試 `test_the_a0_convention_lives_in_exactly_one_place`
>   問的是**耦合**（翻轉常數，五個導出量要跟著變），
>   而它對**兩種**慣例都是綠的。也就是說 v0.39 之前
>   **把 `A0_IS_HALVED` 翻成 `False` 不會有任何東西紅**，
>   而畫面上每一個數字都仍然很合理——學生只會以為自己算錯。
> - 新增 `test_the_a0_convention_is_the_one_the_teacher_chose`：
>   拿一個平均值為 $\frac32$ 的階梯函數，斷言 $a_0$ 是**手算的 3**
>   （不除 2 的慣例下會是 $\frac32$）。⛔ **右邊是手寫的常數**，
>   從 `A0_IS_HALVED` 導出來的斷言證明不了任何事——與 D72 的手抄變換對照表
>   同一個作法，也是 D71 那條通則的第二次套用。
> - ⚠️ 那項測試刻意選一個**平均值不是 0** 的 $f$：$a_0 = 0$ 在兩種慣例下完全相同，
>   拿偶函數來釘慣例等於沒有釘。**這個前提本身由突變測試釘住**，
>   免得日後有人把測試資料換成一個偶函數而整項變成永遠綠。
> - **開關留著**（`A0_IS_HALVED`），理由與 `transform.FORWARD_EXP_SIGN`（D72）相同：
>   老師答的是「哪一種課本慣例」，不是「哪一行程式」。
> - ⚠️ **一個一般化的教訓**：一項「翻轉常數，導出量會跟著動」的測試
>   讀起來很像在守慣例，**而它守的是耦合，不是選擇**。
>   凡是有「慣例常數」的地方，這兩件事都要各有一項測試。

> **v0.39：Fourier 變換落地（工作項 2B11、D72）——§7 #24 卡了十四輪之後解封。測試 1198 → 1249（+51）。**
>
> - ⛔ **老師拍板了 $2\pi$ 的慣例**：$2\pi$ 放在**前面係數**，正向用
>   $e^{-i\omega x}$。也就是
>   $F(\omega) = \int f(x)e^{-i\omega x}dx$、
>   $f(x) = \frac{1}{2\pi}\int F(\omega)e^{i\omega x}d\omega$。
>   §2.10.5 從 v0.25 起就把整個題型擋在這個問題後面，理由是
>   **做錯慣例等於整個題型重寫**——不是程式重寫，是學生的筆記對不上。
> - ⚠️ **拍板之後仍然做成一個可以翻的開關**（`transform.FORWARD_EXP_SIGN`、
>   `PREFACTOR_ON_INVERSE`），與 `core.A0_IS_HALVED` 同一個作法。
>   老師答的是「哪一種課本慣例」，不是「哪一行程式」。
> - ⛔ **最重要的一件事：三層閘門守不住慣例。** 閘門與答案用的是同一組常數，
>   翻掉常數兩邊會一起翻，三層全綠而每一題都錯。守慣例的是另外三項：
>   一份**手抄的**課本對照表（`test_the_transform_pairs_match_the_textbook_table`）、
>   一項「兩條定義式必須真的互為反變換」（`..._really_invert`）、
>   以及一項「所有導出量都要跟著常數動」。**前兩項各自再配一個突變測試**（D71）。
> - ⚠️ **這個題型求的是正向變換，所以 $2\pi$ 根本不會出現在任何一個答案裡。**
>   它只出現在逐步解答第 1 步印出來的定義式——而那是純文字，錯了不會讓任何
>   東西壞掉。這就是為什麼「把反變換真的做一次」那一項是必要的。
> - 三層閘門（`TransformCheck`）：定義式重算（高精度數值，四個探測點）、
>   面積（$F(0)=\int f$，精確符號）、對稱性（實偶⇒實偶、實奇⇒純虛奇）。
>   ⛔ **刻意不是四層**：對應級數那邊 Parseval 的是 Plancherel，
>   它符號上算得出來但單一族要 6–10 秒，所以改成每個族抽一題的獨立測試。
>   **那是取捨，不是遺漏。**
> - ⚠️ **`test_no_single_transform_gate_is_sufficient` 裡有一個我自己寫錯的版本，
>   留在 docstring 裡當註腳**：第三層抓不到「取共軛」——
>   $\overline{F(\omega)} = F(-\omega)$ 對任何實值 $f$ 都成立。
>   「這一層擋得住共軛」聽起來很合理，而它是錯的。
> - ⚠️ **三個「數學閘門看不見」的排版錯，是人眼審出來的**（程式全綠之後把幾題印出來看）：
>   被積函數是一個和卻沒有括號（$\int \frac{x}{2} + 1\,e^{-i\omega x}dx$）、
>   $\frac{2h}{c}$ 在 $h=1$ 被字串拼成 **$\frac{21}{2}$**（讀成二十一分之二）、
>   以及 $e^{--i\omega}$。⛔ **三個都通過了全部的數學閘門，也通過了兩項 KaTeX 測試**
>   ——那兩項問的是「渲染得出來嗎」，不是「渲染出來的是不是同一個式子」。
>   第一類加了一項會紅的測試（`test_every_sum_under_an_integral_sign_is_parenthesised`），
>   另外兩類靠 `_coeff_latex()` 這一個共用的函式。
>   ⚠️ **這正是 2B10（人工審查一輪）在守的東西，而我這一輪只看了幾題。**
> - ⚠️ `test_generators.py` 的分批切法又換了（跑八批、量測 21 批），
>   見「只跑相關的測試」那一節。

> **v0.38：把「那不是紀律問題，是缺一項測試」拿去證明（D71）。測試 1197 → 1198（+1）。**
>
> - ⛔ **一項「平常永遠是綠的」檢查，必須另外有一項測試證明它會紅。**
>   老師質疑上一輪那句話聽起來像「這不是問題，是一個特色」那種話術。
>   ⚠️ **那句話與話術的差別只有一個：它做了一個可以被否證的預測**
>   ——故意把那項測試弄壞，就必須看到紅燈。
> - ⚠️ **驗下來發現上一輪自己有雙重標準**：附錄 C 的正規式有突變測試
>   （`test_that_check_would_have_caught_the_old_spelling`），
>   **而 D70 的孤兒檢查沒有**。實測把 `rglob("*.py")` 改成 `glob("*.py")`
>   （只掃第一層）之後，`test_no_python_file_under_app_is_an_orphan`
>   **仍然是綠的**——測試總數不變、CI 顏色不變，沒有任何東西會抱怨。
> - 判斷邏輯抽成 `_orphans_under(root, loaded)`，新增
>   `test_the_orphan_check_actually_goes_red`：`tmp_path` 造一棵合成樹，
>   三格分別擋住「誤報」「只掃第一層」「`@register(` 提示壞掉」。
>   ⚠️ **刻意用合成的樹，不拿真的 `app/`**——v0.36 已經踩過一次，
>   **一項會自己閃爍的測試比沒有測試更糟**。
> - ⛔ **往後的通則**：凡是「正常情況下永遠綠」的守門測試
>   （孤兒檢查、符號黑名單、各種閘門），都要配一項突變測試；
>   否則它只證明了「今天沒事」，沒有證明「有事的時候它會說」。
> - ⚠️ **那句話裡該讓步的部分也要說**：忘記加那一行 `import` 確實是有人疏忽了，
>   說「不是紀律問題」若被讀成「沒有人有疏忽」就是不誠實。
>   準確的說法是**紀律是錯的那一層**——三層防護（1 人記得／2 指令印提醒／
>   3 測試）裡第一層明文是最弱的，因為它的失效是靜默的、不會給任何回饋。

> **v0.37：工作項 2c 的可執行部分 + 兩道結構性看守（D69、D70）。測試 1162 → 1197（+35）。**
>
> - ⛔ **附錄 C.1「未知函數全程保留自變數」現在有測試守著。**
>   `separable.py` 與 `first_order_linear.py` 的中間步驟原本寫 $y$、最後一步才寫
>   $y(x)$——§7 #29 從 v0.8 起就記著這件事，v0.37 修掉並加了
>   `test_the_unknown_function_keeps_its_argument_in_every_step`。
>   ⚠️ **只改了步驟的 `latex`，一句 `note` 或 `title` 都沒有動**：那是老師的品味。
> - ⚠️ **`ode.laplace.ivp` 不是違反，那是 v0.32 初篩的誤報。**
>   附錄 C.3 的「導數的變換」那一列**逐字**就是 `L\{y'\} = s\,L\{y\} - y(0)`。
>   ⛔ 上一輪的回報寫「三處都是滿的 15/15」，**那句話是錯的，實際是兩處**。
> - ⛔ **`tests/conftest.py` 現在會自動更新相依地圖**（D69）。
>   v0.36 把更新綁在 `test_deps.py run` 上，而那是一條靠人記得的規則；
>   pytest 一定會載入 conftest，所以搬進去之後**直接打 `pytest` 也會更新**。
> - ⛔ **`app/` 底下不准有沒被 import 的 `.py`**（D70，
>   `test_no_python_file_under_app_is_an_orphan`）。
>   ⚠️ **這一類與是誰在打字無關**——老師問「若都由 AI 實作，這類問題會不會消失」，
>   答案是**不會**：AI 一樣會忘記在 `app/generator/__init__.py` 加那一行 import，
>   而症狀是「1197 項全綠，但那個題型是死的」。
> - ⚠️ **這一輪踩到一個會癱瘓機器的坑**：conftest 的自動記錄在
>   `--collect-only` 的子行程裡又觸發了一次自動記錄，**無限遞迴地生出 pytest
>   子行程**（背景一度有 61 個）。兩道防護：`_collected()` 的子行程強制
>   `TEST_DEPS_AUTOUPDATE=0`，以及 conftest 對 `--collect-only` 直接跳過。

安裝與使用說明（**給學生看的，英文**）見 `INSTALL-LINUX.md` 與 `INSTALL-MACOS.md`；
推上 GitHub 的步驟見 `PUBLISHING.md`（**只有老師做得到**）；
這個專案是怎麼跟 AI 一起做出來的，見 `COLLABORATION-NOTES.md`。

---

## ⚠️ 執行環境限制：預設不能刪檔（**但每一輪都要自己實測**）

> ### ⛔ v0.31：先實測，不要讀這一節就下結論
>
> ```bash
> cd <專案根目錄> && touch .probe && rm .probe && echo "可以刪檔" || echo "不能刪檔"
> ```
>
> **這一節描述的是預設狀態，而預設狀態可以被解除。** v0.31 那一輪實測出
> `Operation not permitted`（與下面寫的一模一樣），但接著發現那不是掛載點的
> 天生限制，而是**一道權限政策**——請老師當場授權之後，`rm` 與 `git mv` 就正常了。
>
> ⚠️ **這件事的代價已經付過一次**：工作項 2a0 因為「環境做不到」被擋了十幾輪，
> 而擋住它的是一句寫在文件裡、沒有人回頭驗證過的話。
> **文件記的是上一次的環境，不是這一次的。**
>
> ⚠️ **下面的慣例一條都不要拆掉**：`git-safe-commit.sh`、`.attic/`、
> 「暫存檔寫 `/tmp`」在**任何一種環境裡都是對的**（前者產出與 `git commit` 等價，
> 後者兩條本來就是好習慣），而**預設仍然是不能刪檔**。

本專案常在自動化工作階段中被操作。那個環境把資料夾以 FUSE 掛載進沙箱，
預設權限是 **可建檔、可覆寫、可改名，但不可 unlink（刪檔）**：

```
touch foo   → OK          cp a b (覆寫)  → OK
mv a b      → OK          rm foo         → Operation not permitted
```

沙箱自己的 `/tmp` 不受限制，可以自由刪檔。

### 對 git 的影響：不要直接用 `git commit`

git 幾乎每個寫入都是「建 `.lock` → 寫入 → rename → 刪掉殘餘」。rename 過得了，
最後的刪除過不了，於是會發生：

- `git commit` **第一次成功**，但留下 `.git/HEAD.lock`
- **第二次 commit 卡死**在那個 HEAD.lock 上
- 被 SIGPIPE 中斷的 git（例如 `git status | grep x | head`）留下 `.git/index.lock`

這些鎖檔在沙箱裡刪不掉，只能請使用者到自己電腦上手動清理——如果任務是遠端派送的，
使用者當下不在電腦前，整個任務就卡住了。

**因此提交一律改用：**

```bash
printf '標題行\n\n內文說明。\n' > /tmp/msg.txt
scripts/git-safe-commit.sh /tmp/msg.txt
```

這支腳本走完全不需要 unlink 的路徑，可重複執行，產出與正常 `git commit` 等價。
沒有變更時會自動略過，不產生空 commit。細節見腳本開頭的註解。

### 其他要注意的習慣

- **唯讀 git 指令加 `GIT_OPTIONAL_LOCKS=0`**（`git status`、`git diff`…），
  避免它們去建 index 鎖：`export GIT_OPTIONAL_LOCKS=0`
- **不要把 git 的輸出接到 `head`**（`git log | head`）。`head` 提早關閉管線會讓 git
  收到 SIGPIPE 而來不及清鎖。改用 `git --no-pager log -n 3`。
- **暫存檔一律寫到 `/tmp`**，不要寫進專案資料夾——寫進來就刪不掉了。
- **「刪掉一個檔案」實際上只能做到「把它改名搬走」。** 慣例是搬到 `.attic/`
  （已在 `.gitignore` 裡），這樣從版本控制的角度它真的消失了，而老師在自己的
  電腦上一行 `rm -rf .attic` 就能清乾淨。**`.attic/` 裡的東西不得被任何程式碼
  引用**——引用得到就是還沒刪乾淨。
- `.git/objects/**/tmp_obj_*` 會隨每次提交累積約 5 個惰性垃圾檔，這無法避免也無害；
  可請使用者偶爾執行 `find .git/objects -name 'tmp_obj_*' -delete`。

---

## ⏱ 每個實作任務都要記錄牆鐘時間（TURNAROUND.csv）

老師要知道的是：**PLAN §6 估的 17.8 人週，實際請 AI 執行總共要花多久牆鐘時間。**
人週是一個估計，牆鐘時間不是——後者只能一列一列量出來。

**因此每個實作任務的開頭與結尾各多一個步驟，沒有例外：**

```bash
# 開工的第一件事（在讀 PLAN 之前就做，不要等到動手才做）
python scripts/turnaround.py start 2S10 --title "摺積與 LTI 展示" --estimate 0.5

# 收尾、提交之前
python scripts/turnaround.py finish 2S10 --commits 6 \
    --tests-before 471 --tests-after 553 --files 4 \
    --note "中途老師追加了 TURNAROUND 這件事本身"

python scripts/turnaround.py report      # 給老師看的那一份
```

- **開始時間拿不到精確值時不要假裝精確。** `finish --start <ISO>` 會把那一列
  標成 `estimated`，而且**強制要求 `--note` 說明依據**（例如「沙箱 session
  目錄的建立時間」）。混在一起的話，整份統計的可信度等於最差的那一列，
  而且沒有人看得出是哪一列。
- **`start` 要在工作階段的最前面跑**，不是動手寫程式的時候才跑。讀 PLAN、
  想架構那段時間一樣是牆鐘時間，而它常常佔掉三分之一。
- 格式選 CSV 而不是 Markdown 表格，理由與其餘的設計取捨都寫在
  `scripts/turnaround.py` 的檔頭。**刻意不另外維護一份 `.md`**：兩份會漂移。

**這條慣例有三層防護，一層比一層被動**（完整說明見那支腳本的檔頭）：

1. 這一段文字——靠人記得，所以最弱。
2. `scripts/git-safe-commit.sh` 沒看到 `.turnaround-current.json` 就印一行提醒。
   那支腳本是本專案**唯一**的提交途徑，所以一定會經過。**它刻意不擋提交**：
   為了一筆記帳而讓提交失敗，會讓人去找繞過的方法，而繞過一次就會繞過每一次。
3. `tests/test_turnaround.py` 的
   `test_the_last_row_knows_how_many_tests_there_are`——最後一列的
   `tests_after` 必須等於 `pytest` 實際收集到的項數。**這是唯一不依賴任何人
   記得的一層**：動了測試卻沒更新紀錄就會變紅。

⚠️ **一個誠實的空白**：第 3 層守得住「紀錄有沒有跟上」，守不住「有沒有開一列」——
一個完全沒有動到測試的任務（例如純文件的那幾輪）不會觸發它。
這個縫隙補不起來，寫在這裡而不是假裝已經解決。

---

## 常用指令

```bash
# ⛔ 先問「這次要跑哪些」，不要每次都全跑（D65，理由見下一節）
python scripts/test_deps.py select        # 依目前未提交的變更，印出該跑的指令

# 測試（全部 1251 項、約 15 分鐘；出題引擎的 SymPy 驗證是大宗）
pytest
pytest tests/test_web.py -q          # 只跑 Web 流程
pytest tests/test_curriculum.py -q   # 只跑週次歸類（21 項，約 3 秒）
pytest tests/test_plot.py -q         # 只跑相圖的四層測試（約 15 秒）

# 相圖的人工審查（§2.11.4 第四層——自動測試守不住「這張圖讀不讀得懂」）
python scripts/preview.py --portraits && open preview-portraits.html

# 升級 SymPy 前的完整回歸
GEN_TEST_SAMPLES=200 pytest tests/test_generators.py

# 啟動（v0.29 起沒有任何環境變數要設）
uvicorn app.main:app --reload
```

---

## ⛔ 只跑相關的測試（D65）——但**先讀完什麼時候不可以**

全套 **1251 項、約 15 分鐘**，而一輪工作常常只動一兩個檔案。
`scripts/test_deps.py` 有一份**實跑量出來的**相依地圖
（`tests/data/test_deps.json`：每個測試檔在執行時 import 了哪些模組、
`open()` 了哪些檔案、`subprocess` 傳了哪些路徑），可以據此只跑碰得到這次改動的那些：

```bash
python scripts/test_deps.py run                    # 一次挑好幾個檔案時用這個
python scripts/test_deps.py select                 # 只想看要跑什麼、先不跑
python scripts/test_deps.py select --base HEAD~3   # 依與某個 commit 的差異
python scripts/test_deps.py select -- app/generator/ode/separable.py
```

✅ **v0.37 起直接跑 `pytest` 也會更新地圖**（D69）：鉤子搬進了
`tests/conftest.py`，而 **pytest 一定會載入 conftest**，所以不管用什麼方式
發動都會經過它。`run` 仍然有用（它幫你挑要跑哪些），但**「忘記用 run」
不再是一個會讓地圖過期的錯誤**。

⚠️ **只有兩種情況會真的寫回地圖**：整個檔案跑完且沒有 `-k`，
或 `-k` 恰好等於地圖裡既有的某一批。其餘情況（一次跑好幾個檔案、
只跑某幾項、任意的 `-k`）**印一行說明然後不寫**。
⛔ 那不是保守，是**寫下去會壞掉**：一次跑多個檔案時沒有辦法知道哪一條相依
屬於哪一個檔案，而「都算進去」會讓每個檔案都相依於全世界，於是 `select`
從此永遠回答「全跑」——**那等於把整套機制關掉，而且看起來還在運作**。

⚠️ **沙箱單次指令約 180 秒跑不完全套**，所以 `run` 有 `--only <測試檔>`：
一次跑一個檔案，分幾次呼叫做完。

### ⛔ 什麼時候一定要全跑（這一段比上面重要）

1. **第一次把專案下載到一台新機器。** 地圖記的是「哪個檔案影響哪個測試」，
   它對「這台機器的 Python 是 3.11、SymPy 是 1.15」完全沒有意見。
2. **`requirements.txt`、`pytest.ini`、`tests/conftest.py` 動過**
   （`select` 自己會這樣回答，但值得記得為什麼：**它們改變的是測試怎麼跑，
   而不是被測的是什麼**）。
3. **`select` 說「地圖不認得這些原始碼路徑」**——多半是新檔案，而
   **一個新寫的 generator 忘了註冊時，沒有任何測試會碰到它**，
   那正是它出錯的方式。
4. **要打 tag、要 push 到 GitHub、或要交給學生之前。**
5. **升級 SymPy 之前**（那是既有的規矩：`GEN_TEST_SAMPLES=200 pytest tests/test_generators.py`）。

### v0.36：地圖現在會自己跟上（§7 #44、D68）

在這之前地圖是**某一刻**量出來的，而「它是不是最新的」**沒有任何東西在看**。
量完之後只要有人建立了一條新的相依關係卻沒有重量，就會出現
**「改到了某個檔案，但覆蓋它的那項測試沒有被挑到跑」**——而畫面上是一排綠燈。

兩件事把那個縫補起來：

1. **`run` 讓「跑測試」與「更新地圖」變成同一件事**（見上面）。
   量測用的鉤子本來就掛得上任何一次 pytest，所以增量更新是**免費**的。
2. **每一條相依都記著它被觀察到時的 mtime。** 只要對不上，那個測試檔
   **一律要跑**（跑完就順便重新記一次）。

⛔ **只重量 `select` 挑到的那些就夠，而這是可以證明的**：對任何沒有被挑到的
測試 $T$，它的相依集要改變就得有某個它已經碰得到的檔案被改過——而那個檔案
就在 $\text{deps}(T)$ 裡，於是 $T$ 會被挑到，矛盾。

⚠️ **一個很好的副作用**：`git clone` 會把每個檔案的 mtime 設成 checkout 的時刻，
所以**在一台新機器上第一次跑，每一條相依都對不上 → 全部要跑**。
「第一次下載到新機器要跑全部」這條規則因此**從機制裡長出來，不再靠人記得**。

⛔ **窄化在有相依過期時會自動關掉**，而理由是一個跑不完的迴圈：
窄化會濾掉大部分測試，若某條過期的相依只有被濾掉的那些測試碰得到
（例如自架的 KaTeX），它就永遠不會被重新觀察，於是每一輪都判定過期、
每一輪又都窄化掉唯一能修正它的那一項。`tests/test_test_deps.py` 有一項盯著。

### ⚠️ 這件事守不住的三個縫，不要假裝沒有

- **只問「檔案在不在」的相依量不到。** `test_web.py` 用 `.exists()` 檢查
  KaTeX 的 20 個 woff2 與三份 LICENSE，那些讀取在量測時看不見——
  所以它們落進「地圖不認得」那一格，結果是**全跑**。誤差方向是多跑。
- **node 自己開的檔案看不見。** `.mjs` 的相依是用「整個 `app/static/demos/`
  加上 `vendor/fftjs/`」概括的（用整棵樹而不是一份清單，是因為清單會在有人
  加一支新 JS 時安靜過期）。
- ~~**地圖會過期，而過期是安靜的。**~~ ✅ **v0.36 補起來了**（見上一節）：
  每一條相依都記著 mtime，對不上就一律要跑。**這一條從「守不住的縫」
  變成「有機制在守」。**
  ⚠️ **剩下的殘餘誤差**：mtime 變了但內容沒變（例如 `touch`、或某些
  `git` 操作）會誤判成過期。**那個誤差的方向是多跑**，所以留著。
  另外三種過期方式仍然各有一項測試守著（`tests/test_test_deps.py`）：
  漏量一個測試檔、地圖裡的路徑指不到東西、分批量測漏掉一批。

### 什麼時候要重新量測

**新增或刪掉一個測試檔**、**動了測試檔的 import**、或
**`tests/test_test_deps.py` 變紅**的時候：

```bash
python scripts/test_deps.py measure tests/test_web.py          # 一個檔案
# test_generators.py 一次跑不完（沙箱單次上限 180 秒），照 template 分 18 批：
python scripts/test_deps.py measure tests/test_generators.py --k "<template_id>" --merge
# ...16 個 template_id，加上兩個互斥的兜底批：
#   --k "not (<全部 16 個>) and the_"
#   --k "not (<全部 16 個>) and not the_"
```

⛔ **那些批必須互斥且窮盡，相加恰好等於該檔案的項數**——那是分批量測唯一的
覆蓋證明，`test_each_batched_measurement_covered_every_test_in_its_file` 盯著它。
⚠️ v0.39 之後是 **21 批，相加恰好 460**：12 個 `template_id` 各一批，
其中 `fourier.series.full_range`、`half_range` 各切成**三塊**、
`fourier.transform.forward` 切成兩塊（所以是 19 批），加上兜底的四塊
（`and katex`／`and not katex and not the_`／`and not katex and the_ and gate`／
`and not katex and the_ and not gate`）。⚠️ 完整的 21 個 `-k` 字串在
`tests/data/test_deps.json` 裡就是那 21 個鍵，**那份才是權威**，這裡只寫形狀。

> ⚠️ **v0.39 為什麼把兩個級數題型從兩塊切成三塊**：`full_range and not the_`
> 那 24 項在這台機器上掛了鉤子之後**超過 180 秒**，整個指令被砍掉而且
> 什麼都沒寫回去（量測是跑完才寫的）。切法是
> `and (answer or steps or latex)` / `and not (answer or steps or latex)`。
> ⚠️ 代價要說清楚：`_cached_sample` 的快取每個行程一份，**切成兩塊等於把
> 那個難度的題目重新生成一次**——切批是為了不被砍掉，不是為了比較快。
⚠️ **量測時的批比跑測試時的批更細**，因為量測掛了鉤子、更慢。

⚠️ `--bootstrap` 只有在新增一個「會檢查地圖本身」的測試檔時用得到
（那是一個真的自我指涉），用完一定要再跑一次不帶它的。

---

## ⛔ 一項「永遠是綠的」測試，要另外有一項測試證明它會紅（D71）

守門用的測試——孤兒檢查、符號黑名單、各種閘門——在正常的 repo 上**永遠是綠的**。
那正是它們該有的樣子，但也表示：

> ⚠️ **一項永遠綠的檢查，和一項寫錯了因而永遠不會紅的檢查，從外面看完全一樣。**
> 測試總數不會少一項，CI 不會有任何顏色改變，沒有任何東西會抱怨。

這不是假想。v0.38 實測：把孤兒檢查裡的 `rglob("*.py")` 改成 `glob("*.py")`
（只掃第一層），`test_no_python_file_under_app_is_an_orphan` **照樣是綠的**。

所以慣例是：**加一項守門測試時，同時加一項突變測試**——故意做出那個它應該
抓到的錯，斷言它真的紅。現有的兩個例子：

- `test_that_check_would_have_caught_the_old_spelling`（附錄 C 的符號正規式）
- `test_the_orphan_check_actually_goes_red`（D70 的孤兒檢查）

⚠️ **突變測試要用合成的素材，不要拿真的那一份。** v0.36 踩過：拿真實的相依地圖
去驗「窄化應該被拒絕」，環境的變動會讓它時紅時綠——**一項會自己閃爍的測試比
沒有測試更糟，它會訓練人去忽略紅燈。** 作法是 `tmp_path` 造一棵樹、或在測試裡
手寫一份最小的資料。

---

### ⚠️ 同一件事的第二種樣子：「耦合」與「選擇」是兩項測試（D73）

專案裡有兩個**慣例常數**：`fourier/core.py` 的 `A0_IS_HALVED`（$a_0$ 除不除 2）
與 `fourier/transform.py` 的 `FORWARD_EXP_SIGN`、`PREFACTOR_ON_INVERSE`。
每一個都需要**兩項**測試，而它們很容易被誤認成同一項：

| 問的是 | 長什麼樣 | 少了它會怎樣 |
|---|---|---|
| **耦合**：導出量有沒有跟著常數動 | 翻轉常數，斷言每一個導出量都變了 | 某個導出量偷偷寫死了自己的一份副本，翻轉之後**只有一半跟著改** |
| **選擇**：現在選的是哪一個 | 斷言一個**手寫的常數**（手算的 $a_0$、手抄的變換對照表） | ⛔ **翻掉常數不會有任何東西紅**，而畫面上每個數字都仍然合理 |

⚠️ **只有「耦合」那一項的時候，它讀起來非常像在守慣例。**
`A0_IS_HALVED` 從 v0.25 到 v0.39 就是這個狀態——四輪、十幾個版本，
而那段期間把它翻成 `False` 全套測試照樣全綠。

⛔ **「選擇」那一項的右邊必須是人寫下來的常數。** 從同一個慣例常數導出來的斷言
（例如「$a_0$ 等於 `constant_term(a0) * 2`」）會跟著一起翻，於是它對兩種慣例都是綠的
——那正好又變回「耦合」那一項。

---

## 專案的九條硬規則

> ## ⚠️ v0.29：九條裡有四條失去了標的，但**沒有一條被放寬**
>
> 下面的條文一字未改（保留原文供對照），但系統改為本機執行之後，
> 其中四條守的東西已經不存在了。**先讀這張表，再讀條文**：
>
> | # | 狀態 | v0.29 之後 |
> |---|---|---|
> | 1 數學正確性只能來自 SymPy | ✅ **仍然有效，而且是現在最重要的一條** | 出題引擎是這個專案剩下的全部價值 |
> | 2 密碼絕不以明碼形式存在 | ⛔ 失去標的 | 沒有密碼了（D57） |
> | 3 使用紀錄不得長出指得到人的欄位 | 🔶 **前半失去標的，後半仍然有效** | 沒有紀錄了（D58）；但**「系統對評分保持沉默」（D17）那一半完全不變**——頁面、log、註解都不得出現 `grading`／`grade`，正反皆然，`tests/test_demos.py` 有兩項盯著 |
> | 4 不許靜默失敗 | ✅ **仍然有效，而且讀者換了** | 以前 log 的讀者是老師一個人；現在是**每一個跑這個系統的學生**，而他就在終端機前面 |
> | 5 答案與逐步解答預設遮蔽 | ✅ **仍然有效** | D13 與相圖的洩題防護一個字沒動 |
> | 6 登入閘門不得被繞過 | ⛔ 失去標的 | 沒有閘門了（D57）。⚠️ **但它的論證還在用**——「middleware 的預設是擋下來，`Depends` 沒有預設」那段推導在 D55 被引用過一次 |
> | 7 存取紀錄不得含 IP | ⛔ 失去標的 | 唯一的用戶端是 `127.0.0.1`（D58） |
> | 8 頁面上寫著系統不知道你是誰，所以那必須是真的 | 🔶 **換了主詞，而且變強了** | `_about.html` 沒有了；那句承諾搬到 `base.html` 的頁尾，內容換成「這支程式跑在你自己的電腦上、不記錄你做什麼、從不把任何東西送出網路」。**守它的方式也換了**——不是檢查那句話還在，是 `test_the_footer_promise_is_true_no_outbound_url_in_any_page` 檢查**那句話是真的** |
> | 9 回報必須是真的 | ✅ **仍然有效，而且更難繞過了** | `dispatches/` 讓「當初說的」與「後來發生的」對得起來 |
>
> ⛔ **失去標的的四條不要刪掉。** 它們與 §4、階段 4、D42–D44 是同一個處理：
> 一張看不出「這裡本來有東西」的文件，會讓後人以為從來沒有考慮過。
> 而若日後真的要回頭做站台版，它們**原樣重新生效**。


1. **數學正確性只能來自 SymPy。** 任何顯示給學生的算式都必須由 `sympy.latex()` 產生，
   不得由 LLM 生成或改寫。每個 generator 都要提供一個**驗證器**，`base.generate()`
   會用它逐題驗證，不過就換一組參數重抽。
   > **v0.25（2B0）改的是那個驗證器的型別，不是這條規則。** 以前只有 `Check`
   > 一種（代回方程算殘差）；現在是 `Verifier` 協定，`Check` 是它最常見的實作。
   > ⛔ **`check=None` 一律視為不通過**——這條規則守的是失敗的方向，
   > 若被當成通過，症狀會是「新題型的每一題都完美無瑕」。

2. **密碼絕不以明碼形式存在。** 只用 argon2id 雜湊；不寫入資料庫、日誌、錯誤訊息或
   範本上下文。`tests/test_web.py` 有一項測試會掃整個 DB 檔案確認這件事。

3. **使用紀錄不得長出任何指得到特定個人的欄位，而且系統對「評分」保持沉默。**
   （D17、**D36**）
   `UsageLog` 只記「哪一組帳號、何時、題型、難度、seed」。
   ⚠️ **v0.16 換掉了這條規則的地基**：舊理由是「多存一個欄位就超出個資告知的範圍」，
   而告知沒有了（D37）。新理由更根本——加一個 session id、user agent、IP 或
   細到可當指紋的時間精度進來，**「系統不知道你是誰」就變成假話，而那句話寫在
   學生看得到的頁面上**（`app/templates/_about.html`）。新版本比舊版本強：
   舊規則只要回頭改一行告知文字就能繞過。
   `tests/test_web.py::test_usage_log_cannot_identify_a_person` 盯著。
   同時：**頁面、日誌、程式碼註解都不得出現 `grading`／`grade`
   或「（不）作為評分依據」這類字眼**，正反皆然。紀錄與課程評量的關係由老師在課堂上
   口頭宣布，系統不表態；`tests/test_web.py` 有兩項斷言頁面不含這些字眼。

   **`account_id` 為什麼還留著**（只有兩個值，看起來沒用）：把老師的測試流量
   排除在全班統計之外。改一頁版面會重新整理十幾次，那十幾列會讓「這週學生練了
   幾題」失真，而失真的方式是「數字大了一點」，沒有人看得出來。

4. **不許靜默失敗。** 這是單人維護的系統，「沒印出來」等同「沒有人知道」。
   因此：

   - 任何被 `except` 吞掉的錯誤都要留一行 log（`from .logging_setup import get_logger`）。
     `except Exception: pass` 一律視為 bug。
   - **不做無聲降級。** 這條規則原本是為判定的子行程寫的（D8），但它是全專案適用的：
     寧可讓啟動失敗、讓一個請求回錯誤，也不要安靜地換一條比較弱的路徑跑下去。
   - log 用中文（讀者是老師），但**不得寫入密碼或密碼雜湊**（規則 2），
    也**不得寫入用戶端 IP 或任何可識別欄位**（D38，見下面第七條）。

5. **答案與逐步解答預設遮蔽。**（D13、PLAN §5.8）
   題目卡片是三層：題目自動顯示 → `Show Answer` → `Show Solution Steps`，
   兩層都是 `<details>` 且**都不帶 `open`**。

   漏掉收合是這件事唯一會靜默出錯的方式：頁面不會壞、不會拋錯，只是答案直接
   出現在畫面上，而改程式的人（已經知道答案）不會覺得哪裡不對。
   `tests/test_web.py` 有一對互補的測試盯著（預設收合 / 展開後有東西），
   動 `app/templates/_problem.html` 或 `_solution.html` 之後一定要跑。

> **已捨棄的規則（v0.7）**：舊的規則 5「判定說『對』的時候必須是證出來的」（D9）
> 隨作答判定一起移除。它與 `app/grader/equivalence.py` 一同保存在 tag `grading-v1`；
> 方法論留在 PLAN §5.3。**注意規則 1 沒有變**——`Check` 現在的唯一使用者是出題端的
> 驗證閘門，那正是它最重要的角色，絕對不能因為「判分沒了」就把它拿掉。

> **第六條：登入閘門不得被繞過。**（v0.15 的 D33 立下，v0.16 的 D37 換掉主詞）
> ⚠️ **這一條在 v0.18 之前寫的是「個資告知的閘門」，那已經與上面 v0.16 那段
> 自相矛盾**（`consent_gate.py` 與 `/consent` 都不存在了）；本版改寫成現況。
> **論證一個字都沒變**——D33 選 middleware 而不是 `Depends` 的理由與「擋什麼」無關。
>
> 未登入的人不得使用任何功能。這件事由 `app/login_gate.py` 的
> **middleware** 強制，不是各路由自己的 `Depends`——因為漏掉一個 `Depends`
> **不會拋錯、不會讓任何測試變紅，只會安靜地開一個洞**。
> 豁免清單只有三條（`/login`、`/logout`、`/healthz`；`/consent` 隨 D37 移除），
> 加任何一條之前先想清楚那條路徑碰不碰得到什麼。
> `tests/test_web.py::test_no_route_is_reachable_without_logging_in` 會列舉 app 上
> 所有已註冊的路由逐一嘗試，並且斷言豁免清單就是那幾條。
> ⚠️ **以測試裡的清單為準**，不是以這裡為準——這一段在 v0.16 就漏改了一次。

> **v0.16 新增的第七條：存取紀錄不得含用戶端 IP，而且這件事有三層。**（D38）
> 老師的指定是「只記錄 IP 以外的其他欄位」。方法、路徑、狀態碼、耗時都留著。
>
> 危險的是**只做第一層就以為做完了**：
>
> 1. **應用層**——不讀 `request.client`、不讀 `X-Forwarded-For`／`X-Real-IP`。
>    ✅ 有測試掃整個 `app/`。
> 2. **uvicorn**——它的預設存取格式含 `client_addr`。
>    ⚠️ **不處理的話，應用層一個 IP 都不碰，而終端機上照樣一行一個 IP。**
>    `logging_setup.take_over_uvicorn_access_log()` 把它的 handler 整個拔掉
>    （不是換 formatter——格式是設定，設定會被覆寫）。✅ 有測試。
> 3. **反向代理**——Caddy／nginx 預設也記 IP，而那一層在我們的行程外面。
>    ❌ **沒有測試，也不可能有。** 設定寫在 `FREEBSD-DEPLOY.md` §5.7，
>    驗收方式只有一種：部署完成後 `tail` 一下代理的 log。
>    這是 PLAN §7 #40，**在那之前不算結案**。
>
> 動到 `logging_setup.py`、`access_log.py` 或速率限制的 key 之前，
> 先看 `tests/test_web.py` 的「IP 不落地」那五項。

> **v0.16 新增的第八條：頁面上寫著系統不知道你是誰，所以那必須是真的。**（D35、D40）
> `app/templates/_about.html` 對學生說了四件事：全班共用同一個帳號、只彙總全班
> 用量、不存姓名／學號／IP／你打的任何東西、不判對錯。**這四句話是承諾，不是文案。**
> 任何一次改動如果讓其中一句不再成立，正確的做法是回頭改程式，不是改那句話——
> 而如果真的要改那句話，先想清楚為什麼一個學生應該相信下一個版本。

> **v0.22 新增的第九條：回報必須是真的，包括那些讓回報變得無聊的部分。**
> （老師這一輪明確指定）
>
> **⛔ 絕對不要為了讓回報有趣、或因為老師對實作細節有興趣，而故意製造一個
> bug 再把它修好。** 這條規則往外展開成六件具體的事：
>
> 1. **回報中的「踩到的坑」必須是真實發生過的錯誤。** 不得為了敘事效果而
>    製造一個、把小事誇大成一個、或把**動手之前就已經知道**的問題寫成
>    「實作到一半才發現」。時序也是事實的一部分：一個早就知道的取捨寫成
>    意外發現，句子裡每一個字都是真的，而整段是假的。
> 2. **不得為了展示除錯能力而繞遠路。** 開工時就看得出來的簡單正確作法，
>    就直接用。**「先寫一個比較笨的版本，好讓後面有東西可以改進」是被禁止的**，
>    即使那個笨版本從來沒有被提交。
> 3. **不得寫出明知有問題的程式碼再修正它。** 這一條與第 2 條的差別是刻意的：
>    第 2 條管路線，這一條管**已經知道是錯的**那一行。寫下去的當下就已經
>    違反了，不因為後來修好而抵銷。
> 4. **某一輪沒有踩到任何坑，回報就據實寫「沒有」。** 那是好消息，不是
>    回報不夠精彩。一份「這一輪很順，沒有意外」的回報**資訊量並不低**——
>    它告訴老師這一塊的地基是穩的，而那正是他要判斷的事情之一。
> 5. **數字不得注水。** 測試項數、檔案數、commit 數、工作量、TURNAROUND 的
>    牆鐘時間，一律照實。**不得為了讓項數變好看而把本來該寫成一項
>    （或用 `parametrize`）的測試拆成好幾項**；反過來，也不得為了讓
>    「新增測試數」看起來克制而把該分開的斷言硬塞成一項。
>    判準始終是「這樣切對讀測試的人比較好」，不是「這樣切數字比較好看」。
>    ⚠️ 同一條適用於 TURNAROUND：`start` 晚跑一點會讓耗時看起來比較短，
>    而**沒有人查得出來**——那正是它必須靠紀律的原因。
> 6. **不確定的事要說成不確定。** 「沙箱裡沒跑過」「只有規格上的把握」
>    「這個數字是估的」——這些話在 §8.9 的每一輪落地紀錄裡都出現過，
>    它們是這份文件最有價值的部分之一，不是免責聲明。
>
> **為什麼這件事值得升格成硬規則，而不是一句提醒：**
>
> 老師不看每一行程式碼，他**依賴這些回報做判斷**——要不要繼續投入、
> 哪一塊的風險高、下一輪先做什麼、什麼東西不能相信。回報因此不是工作的
> 附屬品，它是這個專案唯一的一條觀測管道。
>
> 而**這個系統最大的風險一直都是「安靜的錯誤」**：規則 4 講的靜默失敗、
> 規則 5 講的忘記收合、2S5 那個「形狀對、尺度錯三倍」的鋸齒波、
> 2S10 那個「一次都沒有跑過卻看起來完全正常」的冒煙測試——它們的共同點
> 是**不會有人發現**。發現它們的唯一辦法，是有人如實把「哪裡差點沒被發現」
> 說出來。一份被修飾過的回報會讓老師對真實的風險失去感覺，
> 而失去的方式恰好與那些 bug 相同：**沒有任何東西看起來不對**。
>
> 還有一個更難修復的後果：**編出來的坑會讓真的坑失去訊號價值。** 老師讀
> 「這一輪踩到三個坑」時要能推論出「這一塊比預期脆弱」。如果坑的數量
> 有一部分來自敘事需要，那個推論就斷了，而**斷掉之後沒有辦法只修一半**——
> 他必須把過去所有回報的那一欄一起打折。
>
> ⚠️ **這一條與規則 4 是同一件事在兩個層面上**，而且順序是有方向的：
> 規則 4 要求**程式**不得對老師隱瞞，第九條要求**回報**不得對老師隱瞞。
> 規則 4 的所有機制（log、測試、TURNAROUND.csv）最後都要經過一份回報
> 才到得了老師手上——**回報若不可信，那些機制就只是裝飾**。
>
> **自我檢查的一句話**：如果老師看得到這一段的產生過程，他會不會覺得
> 被推銷了什麼？會的話就重寫，而重寫的方向永遠是「講得更平淡、更準確」，
> 不是「講得更少」。
>
> ⚠️ **這一條沒有測試守得住，而這裡不假裝有。** 前八條都有測試或至少有
> 結構性的保證，第九條沒有——一份修飾過的回報不會讓任何東西變紅。
> 它只能靠寫的人自己遵守，所以它寫得比其他幾條長：**唯一的執行機制
> 就是把理由講到讓人不想繞過。**

> ## 第九條的第二半：**回報要讓人不必打開 repo 就看得懂**（v0.33，老師這一輪指定）
>
> 上面那一整條管的是**準確**。這一段管**可讀**，而兩者的失效方式是同一種。
>
> ### 老師實際遇到的那一句
>
> v0.32 的回報裡有一句：「**C2 是五項判準裡最粗的一項**」。
> 老師的回饋原文是：「這短句的意思我較難理解，一方面是我不記得 C2 是什麼，
> 一方面是我不知道所謂的五項判準是哪五項。」
>
> **那句話對讀的人的資訊量是零**，而它被放在「還不夠穩的地方」——
> 整份回報裡最需要被讀懂的那一段。
>
> ### 四條，寫回報的時候逐條對一遍
>
> 1. **每個代號在**那一則訊息裡**第一次出現時就用一句話說它是什麼。**
>    「D65（依相依性挑測試）」、「2a0（把 `app/generator/` 拆成子目錄）」、
>    「C2（五項初篩判準的第二項：`note` 是在講為什麼還是在重述步驟）」。
>    ⛔ **不可以假設老師記得上一輪、上個月、或這份文件裡講過什麼。**
>    每一輪都可能是他隔了兩週回來讀的第一則。
> 2. **「還不夠穩的地方」的每一條寫成三段**：
>    **（a）現象是什麼 →（b）它會怎麼咬到人，給一個具體到可以想像的情境
>    →（c）補起來要多少成本、不補的代價是什麼。**
>    ⛔ 只寫「這裡有個縫」就結束是不合格的——那讓老師沒有辦法決定要不要補。
> 3. **引用檔案時，把結論搬進訊息裡，檔名只當出處。**
>    寫「四組競爭說法裡只有 `initial condition`（38 次）與 `initial value`
>    （110 次）兩種都在用（細節見 `2c-PRESCREEN.md`）」，
>    不要寫「用語不一致的情形見 §C4」。
> 4. **數字一律附單位與對照基準。**
>    「312 秒（全套是 838 秒）」，不要寫「312 秒」。
>
> ### 為什麼這值得寫成規則，而不是一句提醒
>
> 第九條的論證是：**回報是老師唯一的觀測管道**——他不看每一行程式碼，
> 靠回報判斷要不要繼續投入、哪一塊風險高、下一輪先做什麼。
>
> 那條論證有一個沒有寫出來的前提：**回報被讀懂了。**
>
> 一份要打開三個檔案才解得開的回報，實際上**不會被解開**——讀的人會跳過
> 那一段。於是那段話的資訊量歸零，**而它看起來仍然像一段有內容的回報**。
> ⛔ **準確但看不懂的回報，與不準確的回報，對老師的判斷造成的損害是同一種**：
> 他以為他知道風險在哪裡，其實他不知道，而且沒有任何東西看起來不對——
> 與規則 4 的靜默失敗、規則 5 的忘記收合是同一個家族。
>
> 還有一個具體的理由：**老師不一定坐在那台電腦前面。** 他可能在手機上讀，
> 手邊沒有 repo。一份要配著檔案讀的回報，在那個情境下等於沒有寄出。
>
> ⚠️ **這一段與第九條一樣沒有測試守得住**，理由也一樣：
> 一份難讀的回報不會讓任何東西變紅。唯一的執行機制仍然是把理由講清楚。
> **自我檢查的一句話**：把這則回報交給一個沒有這個 repo 的人，
> 他讀得出「哪裡有風險、我該做什麼決定」嗎？讀不出就重寫。

新增題型的步驟見 `README.md`「新增一個題型」。
共用帳號的用法見 `README.md`「帳號怎麼設定」，設計取捨見 `app/accounts.py` 的模組說明。
⚠️ **舊的 `practice.db` 接不上 v0.16**（欄位改名），程式會在啟動時拒絕並給出
`rm` 指令，見 `README.md`「從 v0.15 升級」。
