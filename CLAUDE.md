# 給 Claude 的專案須知

工程數學自動出題練習系統。規劃見 `PLAN.md`，安裝與啟動見 `README.md`。

> **v0.7：自動評分（作答判定）已捨棄**（PLAN.md D12）。`app/grader/`、`Attempt` 表、
> 作答 UI 與判定的子行程沙箱全部移除，保存在 git tag **`grading-v1`**。
> 若你在舊的對話紀錄或註解裡看到 `grader`、`Attempt`、`GRADER_*`，那些都已經不存在了。
>
> **v0.15：學生自行註冊已關閉**（PLAN.md D32–D34）。`/register`、`register.html`、
> `REGISTER_RATE_LIMIT` 全部移除，帳號改由 `scripts/create_accounts.py` 預先配發；
> 個資告知搬到 `/consent`（第一次登入必經，由 `app/consent_gate.py` 的 middleware
> 強制，繞不過去）；學生可自行改密碼（`/account/password`）。
> 舊紀錄裡的 `REGISTER_FORM`、`register_limiter`、`/register` 都已經不存在了。
>
> FreeBSD 正式部署的評估與步驟見 `FREEBSD-DEPLOY.md`（⚠️ 那份文件在 Linux 沙箱裡
> 寫成，沒有一件事在 FreeBSD 上實測過，因此逐項標記了可信度）。

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
- `.git/objects/**/tmp_obj_*` 會隨每次提交累積約 5 個惰性垃圾檔，這無法避免也無害；
  可請使用者偶爾執行 `find .git/objects -name 'tmp_obj_*' -delete`。

---

## 常用指令

```bash
# 測試（全部 332 項、約 2 分 50 秒；出題引擎的 SymPy 驗證是大宗）
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

3. **使用紀錄的欄位不得擴充，而且系統對「評分」保持沉默。**（D17）
   `UsageLog` 只記「誰、何時、題型、難度、seed」——多存一個欄位就超出個資告知
   的範圍（告知頁是 `/consent`，v0.15 前是註冊頁）。同時：**頁面、告知文字、日誌、
   程式碼註解都不得出現 `grading`／`grade`
   或「（不）作為評分依據」這類字眼**，正反皆然。紀錄與課程評量的關係由老師在課堂上
   口頭宣布，系統不表態；`tests/test_web.py` 有兩項斷言頁面不含這些字眼。
   要改告知文字（`app/templates/consent.html`）之前，先看 PLAN.md §4.4 與 §7 #30。

4. **不許靜默失敗。** 這是單人維護的系統，「沒印出來」等同「沒有人知道」。
   因此：

   - 任何被 `except` 吞掉的錯誤都要留一行 log（`from .logging_setup import get_logger`）。
     `except Exception: pass` 一律視為 bug。
   - **不做無聲降級。** 這條規則原本是為判定的子行程寫的（D8），但它是全專案適用的：
     寧可讓啟動失敗、讓一個請求回錯誤，也不要安靜地換一條比較弱的路徑跑下去。
   - log 用中文（讀者是老師），但**不得寫入密碼或密碼雜湊**（規則 2）。

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

> **v0.15 新增的第六條（其實是規則 4 的一個特例，但值得單獨寫）：
> 個資告知的閘門不得被繞過。**（D33、PLAN §4.4）
> 未同意個資告知的人不得使用任何功能。這件事由 `app/consent_gate.py` 的
> **middleware** 強制，不是各路由自己的 `Depends`——因為漏掉一個 `Depends`
> **不會拋錯、不會讓任何測試變紅，只會安靜地開一個洞**。
> 豁免清單只有四條（`/login`、`/logout`、`/consent`、`/healthz`），
> 加任何一條之前先想清楚那條路徑碰不碰得到學生資料。
> `tests/test_web.py::test_no_route_is_reachable_before_consent` 會列舉 app 上
> 所有已註冊的路由逐一嘗試，並且斷言豁免清單就是那四條。

新增題型的步驟見 `README.md`「新增一個題型」。
帳號配發的用法見 `README.md`「帳號怎麼配發」，設計取捨見 `app/accounts.py` 的模組說明。
