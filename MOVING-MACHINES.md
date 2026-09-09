# 換一台電腦繼續開發（Cowork）

> **給誰看**：老師本人，以及接手的 AI 工作階段。
> **不是給學生看的**——學生要的是 `INSTALL-LINUX.md` / `INSTALL-MACOS.md`，
> 那兩份只講「怎麼把這個系統跑起來」，不講開發環境。
>
> ⚠️ **這份文件的最後一節寫著哪些部分我沒有辦法實測**。先看那一節再決定要多信任前面。

---

## 0. 動手之前：確認舊機器上沒有東西還沒推上去

`git clone` 只拿得到**已經推上 GitHub 的東西**。所以在舊機器上先跑：

```bash
git status                      # 要乾淨
git log --oneline origin/main..HEAD    # 要沒有輸出
git log --oneline --all --not --remotes  # 也要沒有輸出（含其他分支與 tag）
```

> **實測（2026-09-09）**：`git reflog show origin/main` 顯示每一輪之後都有 push，
> 最後一次是 `13:25:52 +0800` 推上最後一個 commit。也就是說在寫這份文件的當下，
> 「repo 就是全部」是成立的——⚠️ **但那是那一刻的事實，不是一條性質**，
> 所以上面三個指令還是要跑。

### ⛔ 不會跟著 git 走的東西

`.gitignore` 擋掉的東西不會出現在新機器上。逐項看它們要不要緊：

| 東西 | 大小 | 要緊嗎 |
|---|---|---|
| `.venv/` | 約 129 MB | **不要緊**，一行指令重建（見下） |
| `__pycache__/`、`.pytest_cache/` | — | 不要緊 |
| `preview*.html`、`dist/` | — | 不要緊，都是產出物 |
| `.attic/` | — | 不要緊，那是「已刪除」的暫存地 |
| **`.turnaround-current.json`** | 幾百 bytes | ⚠️ **會有感覺**，見下 |

⚠️ **`.turnaround-current.json` 是「這一輪從什麼時候開始」的標記**
（`scripts/turnaround.py start` 寫的）。它不進版控，所以
⛔ **一輪工作不能在 A 機器 `start`、在 B 機器 `finish`**——
`finish` 會找不到起點。換機器前先把手上那一輪收尾，或接受那一列的時間要重填。

✅ **沒有任何秘密要搬。** v0.29（D57、D58）之後這個系統沒有資料庫、沒有 `.env`、
沒有任何環境變數要設；`requirements.txt` 裡也沒有任何會對外連線的套件。
唯一與身分有關的東西是 GitHub 的 SSH 金鑰，而**金鑰本來就是每台機器一把**（見第 2 節）。

---

## 1. 新機器上要有的四樣東西

| 東西 | 誰在用 | 沒有它會怎樣 |
|---|---|---|
| **Python ≥ 3.10** | 全部 | 跑不起來（明顯） |
| **git** | 全部 | 拿不到 repo（明顯） |
| **Node.js** | `tests/test_dsp_js.py` 與 KaTeX 那一項 | ⛔ **406 項會被跳過而不是變紅**——見下 |
| **SSH 金鑰** | `git push` | 只影響推上去，不影響開發與測試 |

### ⛔ Node.js 那一列要單獨講，因為它的失敗方式是靜默的

沒有 `node` 的時候：

* `tests/test_dsp_js.py` **整份 405 項**被 `pytest.mark.skipif` 跳過（模組層級的 `pytestmark`）；
* `test_every_formula_renders_in_the_bundled_katex` 再 1 項。

⚠️ **它們是 `skipped`，不是 `failed`。** 全套會印

```
888 passed, 406 skipped
```

而不是 `1294 passed`。**888 個綠燈看起來非常安全**，而實際上展示區的數值層
與「公式渲染得出來」這兩件事**一項都沒有被檢查**。

⛔ 這正是 `CLAUDE.md` 那句「守著不存在的東西的綠燈比沒有測試更糟」的另一種樣子，
所以第 4 節的驗收清單**要求你去看那個數字**，不是只看有沒有紅字。
（那兩處的 skip 理由字串本身寫得很清楚——「這不是通過，是沒有跑」——
但前提是有人真的去讀輸出。）

---

## 2. 步驟

```bash
# 1) 拿到 repo
git clone git@github.com:wangc86/engmath-practice.git      # 或 https://
cd engmath-practice

# 2) 建 venv 並裝相依（含測試用的 pytest / httpx）
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 3) Node.js：用系統的套件管理員裝，版本不挑
node -v          # 有輸出就好

# 4) 跑起來看一眼
uvicorn app.main:app --reload      # 然後開 http://127.0.0.1:8000
```

**SSH 金鑰**：⛔ **金鑰是每台機器一把，不要把舊機器的私鑰複製過來。**
在新機器上重新產一把、把**公鑰**貼到 GitHub 即可，
逐步指令（Linux 與 macOS 各一份）見 **`PUBLISHING.md`**。
⚠️ 那份文件也寫了 `remote: Invalid username or token` 這個錯誤怎麼查
——它多半是某個 credential helper 存著失效的舊資料，不會因為新建金鑰就消失。

### Cowork 那一側

1. 在新電腦上裝 Claude 桌面版，用**同一個帳號**登入。
2. 把 `engmath-practice` 這個資料夾接上工作階段
   （⚠️ **選 repo 的根目錄**——含 `CLAUDE.md`、`PLAN.md`、`app/` 的那一層。
   選錯的症狀是 AI 找不到 `CLAUDE.md`，於是它會用一般的方式開始寫程式，
   而這個專案幾乎每一條慣例都與「一般的方式」不同）。
3. 從那台電腦開一個新的工作階段（或在既有工作階段選「連到這台電腦」）。
4. ⚠️ **刪檔權限要現場授權一次。** `scripts/git-safe-commit.sh` 會撞到
   `.git/objects/**/tmp_obj_*` 這種惰性垃圾檔，而這個環境預設不能 unlink；
   AI 會送出一次授權請求，⛔ **那個對話框出現在那台電腦上**，
   所以換機器之後第一次提交前要記得去按同意。
   （拒絕也不會壞掉，只是刪不掉的東西會被搬到 `_to_delete/`。）

---

## 3. 第一次跑測試：會是「全跑」，而且那是對的

```bash
python scripts/test_deps.py select
```

在一份剛 clone 完、工作區乾淨的 repo 上，它會回答**八個測試檔全部要跑，約 1690 秒**。

**為什麼**：相依地圖（D65、D68）記的是每一條相依被觀察到時的 `mtime`，
而 `git clone` 會把每個檔案的 mtime 設成 **checkout 的時刻**——
於是每一條都對不上，每個測試檔都被判定「地圖過期」。
⛔ **「第一次下載到新機器要跑全部」這條規則因此是從機制裡長出來的，不靠人記得。**

> ⚠️ **v0.43 之前這件事其實不成立，而且沒有任何東西會說。**
> `select` 的 CLI 會先問 git「有沒有未提交的變更」，沒有就印「沒有任何變更。」
> 然後 `return`——**在那段「地圖過期的也要跑」被執行到之前**。
> 在一份新 clone 上實測，它回答的是「沒有任何變更」。
> 失敗的方向是最壞的那一個：**它說不必跑，而畫面上什麼都沒有紅。**
> 修掉了（D77），並補上一項用合成地圖的測試把這個性質釘住。

⚠️ **沙箱的單次指令上限約 180 秒，跑不完全套**，所以要分批。
切法（跑測試十三批、量測二十七批）寫在 `CLAUDE.md` 的
「只跑相關的測試」那一節，⛔ **不要自己重新發明切法**——
那些批是被 180 秒逼出來的，而且必須互斥且窮盡。

跑完之後地圖會被更新成新機器的 mtime，往後就恢復成「只跑相關的」。

---

## 4. 驗收清單（照順序，任何一步不對就先停下來）

| # | 做什麼 | 期望 |
|---|---|---|
| 1 | `python3 -V`、`git --version`、`node -v` | 三個都有輸出，Python ≥ 3.10 |
| 2 | `. .venv/bin/activate && pytest --collect-only -q` | **1295 tests collected** |
| 3 | 分批跑完全套 | ⛔ **1295 passed**，**不是 `889 passed, 406 skipped`** |
| 4 | `uvicorn app.main:app` 後開 `/healthz` | `{"status":"ok"}` |
| 5 | 首頁的下拉選單 | 依課程週次分組，答案預設收合 |
| 6 | `git status` | 乾淨 |
| 7 | `git tag` | `grading-v1`、`hosted-v1` 兩個都在 |
| 8 | 第一輪工作 | 用 `dispatches/TEMPLATE-first-session.md` 的樣板，**不要直接開始實作** |

⚠️ 第 2、3 步的數字會隨版本改變。**現行值寫在 `PLAN.md` §1.7 與 `CLAUDE.md`**，
以那裡為準；這裡寫的是 v0.43 當下的值。

---

## 5. ⚠️ 這份文件哪些部分我沒有辦法實測

寫這份文件的 AI 工作階段跑在一個**只掛載了專案資料夾**的沙箱 VM 裡。
它看不到 `~/.ssh`、看不到 `~/.gitconfig`、也看不到 Claude 桌面版的設定。所以：

| 段落 | 狀態 |
|---|---|
| 第 3 節「新 clone 會全跑」 | ✅ **實測過**：在沙箱裡 `git clone` 一份、提交、跑 `select`，輸出逐字如上 |
| 第 1 節「沒有 node 會跳過 406 項」 | ✅ **由程式碼確認**：`test_dsp_js.py` 的模組層 `pytestmark` 405 項 + KaTeX 那 1 項 |
| 第 0 節「舊機器已經推乾淨」 | ✅ **實測過**（`git reflog show origin/main`），⚠️ 但那是當下的事實 |
| 第 2 節的 SSH 與 Cowork 步驟 | ⚠️ **規格上的把握，不是實測**——這個環境碰不到那些設定 |
| 第 4 節的 `uvicorn` / 瀏覽器那幾步 | ⚠️ 同上；沙箱裡沒有瀏覽器可以開 |

⛔ **把「沒有實測」寫出來，比讓它看起來像全部都驗過有用。**
如果第 2 節照做卡住了，那是文件的問題，不是你的問題——回來把卡住的那一步記下來。
