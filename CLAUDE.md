# 給 Claude 的專案須知

工程數學自動出題練習系統。規劃見 `PLAN.md`，安裝與啟動見 `README.md`。

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
# 測試（全部 271 項、約 3 分鐘；出題引擎的 SymPy 驗證是大宗）
pytest
pytest tests/test_web.py -q          # 只跑 Web 流程，約 31 秒
pytest tests/test_grader.py -q       # 只跑判定，約 9 秒

# 判定各條路徑的比例（抽樣／符號證明／無法判定）。改 grader/equivalence.py 後要重跑
python scripts/grader_sampling_report.py 10

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

3. **不計分。** 使用紀錄（`UsageLog`）只記「誰、何時、題型、難度」，
   不得擴充為評分用途——那會使註冊頁的個資告知範圍失效。

4. **不許靜默失敗。** 這是單人維護的系統，「沒印出來」等同「沒有人知道」。
   因此：

   - 任何被 `except` 吞掉的錯誤都要留一行 log（`from .logging_setup import get_logger`）。
     `except Exception: pass` 一律視為 bug。
   - **不做無聲降級。** 尤其是判定的子行程：它是判定唯一的硬性 timeout，
     叫不起來就讓服務啟動失敗（D8、PLAN §5.6），不准退回同行程執行。
   - log 用中文（讀者是老師），但**不得寫入密碼、密碼雜湊或學生的原始作答**
     （規則 2；要看作答請查 `Attempt` 表）。判定的殘差式等同學生的作答，同樣不記。

5. **判定說「對」的時候必須是證出來的。**（D9、PLAN §5.3）
   `app/grader/equivalence.py` 的 `zero_status` 是三值的：

   - `zero` 只能來自**符號證明**（`_PIPELINE` 那串化簡）；
   - `nonzero` 來自數值抽樣**反證**（找到一個明顯不為 0 的點）；
   - 兩者都做不到就是 `unknown` → 學生看到 `unverified`（無法確認），**不准說對**。

   數值抽樣永遠不得用來主張「這個式子是 0」。誤判成「對」的代價是學生帶著錯誤的解
   離開，而且沒有任何人會知道——判定不拋錯、log 沒有一行、學生只看到綠色的 Correct。
   改動這個檔案之後請跑 `scripts/grader_sampling_report.py` 確認 `unverified` 仍是 0。

新增題型的步驟見 `README.md`「新增一個題型」。
