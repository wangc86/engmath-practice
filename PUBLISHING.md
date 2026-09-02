# 推上 GitHub：老師要做的事

> ⛔ **這一份的每一步都必須由你自己在自己的電腦上執行。**
>
> AI 不能代為建立 repo 或推送——那需要 GitHub 的認證憑證（密碼、
> personal access token 或 SSH 金鑰），而**把憑證交給任何中間人都是錯的**，
> 不論那個中間人有多方便。這不是能力限制，是一條不該繞過的界線。
>
> 好消息是這件事只有五個指令，而且只做一次。

---

## 0. 先決定四件事

| # | 要決定的 | 建議 | 為什麼 |
|---|---|---|---|
| 1 | **repo 名稱** | `engmath-practice` | 兩份安裝說明裡的 `git clone` 指令用的就是這個名字。用別的名字就要回頭改那兩處 |
| 2 | **Public 還是 Private** | **Public** | 學生要自己 clone。Private 的話每個學生都要被加成 collaborator（一個個加，而且他們要有 GitHub 帳號）。⚠️ 見下面「Public 之前要確認的三件事」 |
| 3 | **授權條款** | 已放好 `LICENSE`（MIT） | 公開散布需要一份。⚠️ 它同時指出 `app/static/vendor/` 底下三份**不屬於**它的授權條款——那三份是 KaTeX、htmx、fft.js 的 |
| 4 | **`YOUR-INSTRUCTOR` 換成什麼** | 你的 GitHub 帳號 | `INSTALL-LINUX.md` 與 `INSTALL-MACOS.md` 各有一處佔位符 |

### ⚠️ Public 之前要確認的三件事

這個 repo 已經為公開做過準備，但**由你確認一次比較好**——下面三項各只要
一個指令：

```bash
cd ~/code/engmath-practice

# (a) 版控裡沒有資料庫、沒有 .env、沒有 .attic（.gitignore 應該已經擋掉了）
git ls-files | grep -E '\.db$|^\.env|^\.attic/' || echo "✅ 乾淨"

# (b) 歷史裡也沒有（現在的檔案乾淨不代表某個舊 commit 乾淨）
git log --all --diff-filter=A --name-only --pretty=format: \
  | sort -u | grep -E '\.db$|^\.env' || echo "✅ 歷史也乾淨"

# (c) 沒有任何明碼密碼留在歷史裡
git log --all -p | grep -iE 'password\s*=\s*["'"'"'][^"'"'"']{6,}' || echo "✅ 沒有明碼"
```

> ⚠️ **(b) 與 (c) 為什麼要單獨做**：v0.29 之前這個系統有帳號與 SQLite
> 資料庫。現在它們都不在了，但**它們在歷史裡存在過**——而 `git push` 推的
> 是整段歷史。推上去之後就收不回來了，所以這是唯一一次確認的機會。
>
> ### 這三項在 v0.30 實際跑過一次，結果如下（你仍然應該自己跑一次）
>
> | 檢查 | 結果 |
> |---|---|
> | (a) 版控裡的 `.db` / `.env` / `.attic` | ✅ 一個都沒有 |
> | (b) 歷史裡曾經加入過的 | ⚠️ **一個命中：`.env.example`** |
> | (c) 明碼密碼 | ⚠️ **16 個命中** |
>
> **兩個「命中」逐一看過，都不是問題，而看過本身是重點**：
>
> - **`.env.example` 是刻意進版控的**（`.gitignore` 裡有一行 `!.env.example`），
>   而它裡面的 `SESSION_SECRET=` **是空的**——它是一份範本，不是一份設定。
>   （它在 v0.29 隨 D60 下架了，但歷史裡還在。）
>   上面那個 `grep -E '^\.env'` 會連 `.env.example` 一起抓，那是**刻意寬鬆**：
>   一個會誤報的檢查比一個會漏報的檢查好。
> - **16 個「密碼」全部是測試的固定值**（`CLASS_PASSWORD = "practice-ode-2026"`
>   之類），住在已經被移除的 `tests/test_accounts.py` 與 `tests/test_web.py` 裡。
>   ⚠️ **系統從來沒有把任何真實密碼寫進檔案**——`create_accounts.py` 把密碼
>   印在終端機上一次就結束（那是 D35 當初的一個決定，而它在這裡兌現了）。
>
> ⛔ **如果你自己跑出來的結果與上表不同，先弄清楚多出來的是什麼再推。**

---

## 1. 換掉安裝說明裡的佔位符

```bash
cd ~/code/engmath-practice
sed -i '' 's|YOUR-INSTRUCTOR|你的GitHub帳號|g' INSTALL-LINUX.md INSTALL-MACOS.md   # macOS
# Linux 的話是：sed -i 's|YOUR-INSTRUCTOR|你的GitHub帳號|g' INSTALL-*.md
```

確認一下：

```bash
grep -n 'git clone' INSTALL-*.md
```

然後提交（**用專案的提交腳本，不要用 `git commit`**——理由見 `CLAUDE.md`）：

```bash
printf '安裝說明：填入實際的 GitHub 網址\n' > /tmp/msg.txt
scripts/git-safe-commit.sh /tmp/msg.txt -- INSTALL-LINUX.md INSTALL-MACOS.md
```

> ⚠️ 在**你自己的電腦上**其實可以正常用 `git commit`——不能刪檔的限制只存在
> 於 AI 的沙箱裡。但用同一支腳本比較不會記錯，而且它會提醒你 TURNAROUND。

## 2. 在 GitHub 上建一個空 repo

網頁上做：<https://github.com/new>

- **Repository name**：`engmath-practice`
- **Public**
- ⛔ **不要**勾 "Add a README file"、"Add .gitignore"、"Choose a license"
  ——這三個都會在遠端先建一個 commit，而你本機已經有 110 個 commit 的歷史了，
  推的時候會撞在一起（`fetch first` / `non-fast-forward`）。
  **建一個完全空的 repo**，下面才推得上去。

## 3. 接上遠端並推

```bash
cd ~/code/engmath-practice
git remote add origin https://github.com/你的GitHub帳號/engmath-practice.git
git push -u origin main
git push --tags          # ⚠️ 這一行不要漏，見下
```

第一次 `push` 會要你認證。GitHub 已經不接受密碼，所以是這兩種之一：

- **Personal access token**：<https://github.com/settings/tokens> 產一個
  （classic 就好，勾 `repo`），貼在它問密碼的地方。
- **SSH 金鑰**：`ssh-keygen -t ed25519` → 把 `~/.ssh/id_ed25519.pub` 貼到
  <https://github.com/settings/keys>，然後 remote 用
  `git@github.com:你的帳號/engmath-practice.git`。

> ⛔ **`git push --tags` 不要漏掉。** 這個專案有兩個 tag，而它們是被拆掉的
> 功能**唯一**的取回途徑：
>
> | tag | 裡面有什麼 |
> |---|---|
> | `grading-v1` | v0.7 拆掉的自動評分（`app/grader/`、`Attempt` 表、判定的子行程沙箱） |
> | `hosted-v1` | v0.29 拆掉的整個站台版（帳號、資料庫、用量紀錄、開放閘門、三份部署文件） |
>
> 沒有推 tag 的話，那些程式碼只存在於你這一台機器上——而 PLAN.md 裡有
> 十幾處寫著「保存在 tag `hosted-v1`」，那些句子會全部變成假的。

## 4. 確認學生真的裝得起來

```bash
cd /tmp
git clone https://github.com/你的GitHub帳號/engmath-practice.git
cd engmath-practice
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app
```

打開 <http://127.0.0.1:8000>（**Chrome 或 Firefox**）。

⚠️ **這一步就是 `VERIFY-CHECKLIST.md` 的 B7**，而它在這個專案裡一直是空的
——「照著安裝說明從零裝一次」的那個「零」，在你自己的機器上不存在
（你早就有 Python、有相依、有整個資料夾）。從 `/tmp` clone 一份是最接近
學生處境的作法，而且它會**真的去驗證 GitHub 上那一份是完整的**。

## 5. 之後每一輪

```bash
git push          # 把新的 commit 推上去
```

學生那一側是 `git pull`。⚠️ **修好一個 bug 之後要讓他們知道去更新**——
那是一個溝通問題，不是維運問題（PLAN §7「部署與維運」）。

---

## 之後在別台電腦上繼續開發

推上去之後，任何一台電腦（或任何一個 AI 工作階段）只要：

```bash
git clone https://github.com/你的GitHub帳號/engmath-practice.git
```

就拿到了**完整的專案**——包含 `CLAUDE.md`（九條硬規則與「已經不存在的
東西」清單）、`PLAN.md`（D1–D61 的完整推導）、`COLLABORATION-NOTES.md`
（協作方式與專案史）、`dispatches/`（每一輪的原始提示詞），以及兩個 tag。

**這正是 v0.29 花那麼多力氣寫文件的原因**：這個專案往後會由不同的 AI
工作階段接手，而它們之間唯一共享的東西就是 repo 裡的檔案。

⚠️ **在新機器上開工前先讀 `CLAUDE.md`**，特別是「⚠️ 執行環境限制：不能刪檔」
那一節——如果新的環境**沒有**那個限制（例如你自己的電腦），那一節的
`.attic/` 與 `git-safe-commit.sh` 就不是必要的了，但**照著做也不會錯**。
