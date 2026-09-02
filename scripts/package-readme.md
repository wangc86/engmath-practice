# 先讀這一份

這是一份 **self-contained 的專案快照**：解開之後就是完整的 repo，
不需要網路、不需要 git，也不需要向任何人索取缺少的檔案。

---

## 如果你只是想用它

> **你需要 Python 3.10 以上，以及 Chrome 或 Firefox。**

照著 `engmath-practice/` 底下這兩份的其中一份走：

| 你的系統 | 讀哪一份 |
|---|---|
| Linux | 📄 `INSTALL-LINUX.md` |
| macOS | 📄 `INSTALL-MACOS.md`　⚠️ **不要用 Safari**，理由在那份文件的最上面 |

四個步驟，大約五分鐘：

```bash
cd engmath-practice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app
```

然後打開 <http://127.0.0.1:8000>。

**它不會在你的機器上留下任何東西**：沒有帳號、沒有資料庫、沒有設定檔，
也不會發出任何對外連線。刪掉資料夾就乾淨了。

---

## 如果你要接手開發（人或 AI）

這個專案是用「一次一段任務描述、由 AI 在獨立工作階段裡完成」的方式做出來的，
所以**所有需要被記住的東西都寫在檔案裡**。按這個順序讀：

| # | 檔案 | 為什麼 |
|---|---|---|
| 1 | `CLAUDE.md` | **九條硬規則**，以及一份「已經不存在的東西」的清單。⚠️ 那份清單防的是一件真的會發生的事：照著一個已經作廢的設計往下寫 |
| 2 | `README.md` | 現況、專案結構、怎麼新增一個題型 |
| 3 | `COLLABORATION-NOTES.md` | 這個專案是怎麼跟 AI 一起做出來的：協作模型、有效的慣例、重建的專案史 |
| 4 | `PLAN.md` 的**決定事項表** | D1–D61。不必讀六千行，但動任何東西之前先在那張表裡搜一下相關代號 |
| 5 | `dispatches/` | 每一輪派送的原始提示詞（v0.29 起才有，之前的沒有留下來） |
| 6 | `VERIFY-CHECKLIST.md` | 自動測試守不住、只有人做得到的實測項目 |

### 開工的第一件事

```bash
# 1. 把這一輪的提示詞原文存進 dispatches/（見該目錄的 README）
# 2. 才開始計時
python scripts/turnaround.py start <任務編號> --estimate <人週>
```

### 跑測試

```bash
pytest                            # 全部 1305 項，約 10–12 分鐘
pytest tests/test_web.py -q       # 只跑 Web 流程
pytest tests/test_curriculum.py -q  # 只跑週次歸類（約 3 秒）
```

⚠️ **如果你在一個單次指令有時間上限的環境裡**（例如某些 AI 沙箱），
`tests/test_generators.py` 要分批跑——切法寫在 `CLAUDE.md`。

---

## 這個 zip 裡面有什麼、沒有什麼

**內容物就是 `git ls-files`**，不是 `cp -r .`。也就是說 `.gitignore` 擋掉的
東西一個都不在裡面：沒有 `.venv/`、沒有 `__pycache__/`、沒有舊的 zip、
沒有 `.attic/`（被移除的檔案的暫存地）。

⚠️ **`.git/` 也不在裡面**，所以：

- 你**沒有** commit 歷史，也**沒有** `grading-v1` 與 `hosted-v1` 兩個 tag
  ——而那兩個 tag 是「被拆掉的功能」唯一的取回途徑
  （v0.7 的自動評分、v0.29 的站台版）。
- 需要那些的話，repo 在 <https://github.com/wangc86/engmath-practice>（`git clone` 就拿得到全部）。
- 反過來說，`COLLABORATION-NOTES.md` 裡的「專案史」那一節就是為此而寫的：
  它把 102 個 commit 訊息與決定表濃縮成一張時間軸，**看得出發生過什麼，
  只是取不回程式碼**。

---

## 一句誠實的話

這個專案的六個互動展示，**從來沒有在真正的瀏覽器裡被驗收過**——
開發環境是一個沒有瀏覽器的 Linux 沙箱。數值層有 405 項由 node 驅動的測試，
版面與聲音只有一支在假 DOM 裡跑的冒煙測試。

**所以你打開它的時候，就是一次真實的驗收。** 有任何一頁看起來不對、
聽起來不對，那很可能是真的不對——請回報。逐項的檢查清單在
`VERIFY-CHECKLIST.md` 的 A 組。
