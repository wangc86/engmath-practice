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
> FreeBSD 正式部署的評估與步驟見 `FREEBSD-DEPLOY.md`（⚠️ 那份文件在 Linux 沙箱裡
> 寫成，沒有一件事在 FreeBSD 上實測過，因此逐項標記了可信度）；
> **在家先預演一次**見 `FREEBSD-HOMELAB.md`（v0.19 新增，**v0.20 依 D44 整份改寫成
> 「Ubuntu + KVM 虛擬機」**，同樣沒有實測過——⚠️ 沙箱裡連 `/dev/kvm` 都沒有）。

---

## ⚠️ 執行環境限制：不能刪檔

本專案常在自動化工作階段中被操作。那個環境把資料夾以 FUSE 掛載進沙箱，
權限是 **可建檔、可覆寫、可改名，但不可 unlink（刪檔）**：

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
# 測試（全部 471 項、約 3 分鐘；出題引擎的 SymPy 驗證是大宗）
pytest
pytest tests/test_web.py -q          # 只跑 Web 流程

# 升級 SymPy 前的完整回歸
GEN_TEST_SAMPLES=200 pytest tests/test_generators.py

# 啟動
export SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
uvicorn app.main:app --reload
```

---

## 專案的五條硬規則

1. **數學正確性只能來自 SymPy。** 任何顯示給學生的算式都必須由 `sympy.latex()` 產生，
   不得由 LLM 生成或改寫。每個 generator 都要提供一個 `Check`，`base.generate()`
   會用它逐題驗證殘差為 0，不過就換一組參數重抽。

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

新增題型的步驟見 `README.md`「新增一個題型」。
共用帳號的用法見 `README.md`「帳號怎麼設定」，設計取捨見 `app/accounts.py` 的模組說明。
⚠️ **舊的 `practice.db` 接不上 v0.16**（欄位改名），程式會在啟動時拒絕並給出
`rm` 指令，見 `README.md`「從 v0.15 升級」。
