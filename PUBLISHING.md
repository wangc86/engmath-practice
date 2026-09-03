# 推上 GitHub：老師要做的事

> ⛔ **這一份的每一步都必須由你自己在自己的電腦上執行。**
>
> AI 不能代為建立 repo 或推送——那需要 GitHub 的認證憑證（密碼、
> personal access token 或 SSH 金鑰），而**把憑證交給任何中間人都是錯的**，
> 不論那個中間人有多方便。這不是能力限制，是一條不該繞過的界線。
>
> 好消息是這件事只做一次。⚠️ **第 3 節的認證那一步一定會撞到
> `Password authentication is not supported`**——GitHub 從 2021 年起
> 就不收密碼了，那一節有完整的兩條路，**Linux 與 macOS 各一份指令**
> （v0.34 補上 Linux；在那之前只有 macOS，而 `pbcopy` 與
> `--apple-use-keychain` 在 Linux 上不存在）。

---

## 0. 先決定四件事

| # | 要決定的 | 建議 | 為什麼 |
|---|---|---|---|
| 1 | **repo 名稱** | `engmath-practice` | 兩份安裝說明裡的 `git clone` 指令用的就是這個名字。用別的名字就要回頭改那兩處 |
| 2 | **Public 還是 Private** | **Public** | 學生要自己 clone。Private 的話每個學生都要被加成 collaborator（一個個加，而且他們要有 GitHub 帳號）。⚠️ 見下面「Public 之前要確認的三件事」 |
| 3 | **授權條款** | 已放好 `LICENSE`（MIT） | 公開散布需要一份。⚠️ 它同時指出 `app/static/vendor/` 底下三份**不屬於**它的授權條款——那三份是 KaTeX、htmx、fft.js 的 |
| 4 | ~~`YOUR-INSTRUCTOR` 換成什麼~~ | ✅ **已填好 `wangc86`** | v0.30 老師提供，兩份安裝說明裡的 `git clone` 已經是真的網址 |

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

## 1. ~~換掉安裝說明裡的佔位符~~ — ✅ **已完成（v0.30）**

兩份安裝說明裡的 `git clone` 已經是
`https://github.com/wangc86/engmath-practice.git`，也已經提交。

確認一下（應該印出兩行，都帶 `wangc86`）：

```bash
cd ~/code/engmath-practice
grep -n 'git clone' INSTALL-*.md
```

⚠️ **如果你在第 2 步用了別的 repo 名稱**，這兩處要跟著改：

```bash
sed -i '' 's|engmath-practice.git|新名稱.git|g' INSTALL-LINUX.md INSTALL-MACOS.md   # macOS
```

## 2. 在 GitHub 上建一個空 repo

網頁上做：<https://github.com/new>

- **Repository name**：`engmath-practice`
- **Public**
- ⛔ **不要**勾 "Add a README file"、"Add .gitignore"、"Choose a license"
  ——這三個都會在遠端先建一個 commit，而你本機已經有 120 個 commit 的歷史了，
  推的時候會撞在一起（`fetch first` / `non-fast-forward`）。
  **建一個完全空的 repo**，下面才推得上去。

## 3. 接上遠端並推

```bash
cd ~/code/engmath-practice
git remote add origin https://github.com/wangc86/engmath-practice.git
git push -u origin main
git push --tags          # ⚠️ 這一行不要漏，見下
```

### ⚠️ 這一步一定會撞到：`Password authentication is not supported`

**GitHub 從 2021 年 8 月起不接受密碼**（v0.30 實際撞到了，所以這一節從
原本的兩行擴寫成可以照做的步驟）。兩條路，**推薦 SSH**——設定一次，
之後永遠不用再輸入任何東西；token 會過期，過期那天你會忘記為什麼推不上去。

> ⚠️ **v0.34：這一節原本只寫了 macOS**（`pbcopy`、`--apple-use-keychain`、
> `osxkeychain` 三個指令在 Linux 上都不存在），而老師 v0.34 那一輪是在
> **Linux 筆電**上推的，於是照著做會在第 2 步就卡住。
> 兩套指令現在各寫一份。**先看你在哪一台機器上。**

#### 路線 A：SSH 金鑰（**推薦**，Linux 與 macOS 各一份）

設定一次，之後永遠不用再輸入任何東西。
⚠️ **token（路線 B）會過期，而過期那天的錯誤訊息不會提到「你的 token 過期了」**
——它長得跟第一次設定失敗時一模一樣。

##### Linux

```bash
# 0. 先看有沒有既有的金鑰。有 id_ed25519.pub 就跳到第 3 步。
ls -la ~/.ssh

# 1. 產金鑰。三個提示一路按 Enter 即可。
#    ⚠️ 第二、三個提示問的是 passphrase，見下面那段取捨。
ssh-keygen -t ed25519 -C "cw@gapps.ntnu.edu.tw"

# 2. 只有在你「有設 passphrase」時才需要這兩行；留空的話跳過。
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# 3. 把公鑰印出來，整行複製（Linux 沒有 pbcopy）
cat ~/.ssh/id_ed25519.pub
#    有裝 xclip 的話：   xclip -selection clipboard < ~/.ssh/id_ed25519.pub
#    Wayland 桌面的話：  wl-copy < ~/.ssh/id_ed25519.pub

# 4. 貼到 https://github.com/settings/keys → New SSH key
#    Title 隨便寫（例如 zenbook-linux），Key type 選 Authentication Key

# 5. 測試
ssh -T git@github.com
#    預期：Hi wangc86! You've successfully authenticated, but GitHub does not
#          provide shell access.
#    ⚠️ 那句 "does not provide shell access" 是**成功**的訊息，不是錯誤。

# 6. ⚠️ remote 目前是 https，要換成 ssh
cd ~/code/engmath-practice
git remote set-url origin git@github.com:wangc86/engmath-practice.git
git remote -v          # 兩行都要變成 git@github.com:...

# 7. 推
git push
```

> **passphrase 要不要設？** 這是一個真的取捨，不是形式問題。
>
> - **留空**：`git push` 完全不問任何東西，最省事。代價是**任何拿得到
>   `~/.ssh/id_ed25519` 這個檔案的人就等於拿到你的 GitHub 寫入權**。
>   個人筆電、而且開了全碟加密的話，多數人接受這個代價。
> - **設一個**：每次開機後第一次用要輸入一次。GNOME 桌面通常會用鑰匙圈
>   幫你記住（跳出一個對話框問「要不要記住」，按了就好）。
>
> ⛔ **無論哪一種，只貼 `.pub` 那一個檔案。** `~/.ssh/id_ed25519`
> （沒有 `.pub`）是私鑰，**任何情況下都不要複製、不要貼給任何人、
> 不要貼給任何 AI，包括我。**

##### macOS

```bash
ssh-keygen -t ed25519 -C "cw@gapps.ntnu.edu.tw"
eval "$(ssh-agent -s)"
ssh-add --apple-use-keychain ~/.ssh/id_ed25519    # ⚠️ 這個旗標 Linux 沒有
pbcopy < ~/.ssh/id_ed25519.pub                    # ⚠️ pbcopy Linux 也沒有
# 之後同 Linux 的第 4–7 步
```

##### ⚠️ 第 5 步卡住沒反應（不是被拒絕，是逾時）

通常是校園或公司網路擋了 22 埠。把這三行加進 `~/.ssh/config`
（檔案不存在就自己建）改走 443，再試一次第 5 步：

```
Host github.com
  Hostname ssh.github.com
  Port 443
```

#### ⚠️ 換成 SSH 之後還是失敗？先清掉舊的 HTTPS 憑證

錯誤訊息裡出現 **`Invalid username or token`** 而不是單純的
`Password authentication is not supported`，代表 git **有送出東西**
——多半是某個 credential helper 存著一組舊的、已經失效的帳密。
⚠️ **那組東西不會因為你新建了 token 或金鑰就消失**，它會繼續被送出去。

換成 SSH（路線 A 第 6 步）之後那組憑證就用不到了，所以這一段多半不必做。
真的要清：

```bash
git config --global --get credential.helper     # 先看是誰在存

# 存成純文字檔的（helper = store）
grep -n github ~/.git-credentials               # 找到那一行，用編輯器刪掉

# 只存在記憶體的（helper = cache）
git credential-cache exit

# GNOME 鑰匙圈（helper = libsecret / gnome-keyring）
# 開「密碼與金鑰」（Seahorse），搜尋 github.com，刪掉那一筆
```

#### 路線 B：Personal access token

**只在 SSH 兩條路都走不通時用**（例如網路把 22 與 443 都擋了）。

1. <https://github.com/settings/tokens> → **Tokens (classic)** →
   Generate new token。
2. Note 隨便寫，**Expiration 選一個你記得住的**，Scopes 只勾 **`repo`**。
3. `git push` 問 Username 時打 `wangc86`，問 Password 時**貼那個 token**
   （不是你的 GitHub 密碼）。
4. 讓它被記住：
   - **macOS**：`git config --global credential.helper osxkeychain`（通常預設就開了）
   - **Linux**：`git config --global credential.helper store`
     ⚠️ **這個 helper 把 token 以純文字存進 `~/.git-credentials`**，
     它不是「加密後存起來」。這是路線 B 在 Linux 上比 macOS 差的地方，
     也是這裡推薦 SSH 的另一個理由。
     不想留純文字的話用 `git config --global credential.helper 'cache --timeout=86400'`
     ——只存在記憶體、一天後失效，代價是每天要重貼一次。

⚠️ **token 到期那天**，`git push` 會再一次說認證失敗，而錯誤訊息**不會**提到
「你的 token 過期了」——它跟你第一次設定失敗時看到的一模一樣。到時候回來看這一節。

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
>
> ✅ **v0.34 查過：兩個 tag 已經在 GitHub 上了**（`git ls-remote --tags origin`
> 兩個都回得出來），所以現在再跑一次 `git push --tags` 是 no-op，不會有事，
> 也不必特地跑。這一段留著是給**下一次**建 repo 或換遠端的人看的。

## 4. 確認學生真的裝得起來

```bash
cd /tmp
git clone https://github.com/wangc86/engmath-practice.git
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
git clone https://github.com/wangc86/engmath-practice.git
```

就拿到了**完整的專案**——包含 `CLAUDE.md`（九條硬規則與「已經不存在的
東西」清單）、`PLAN.md`（D1–D61 的完整推導）、`COLLABORATION-NOTES.md`
（協作方式與專案史）、`dispatches/`（每一輪的原始提示詞），以及兩個 tag。

**這正是 v0.29 花那麼多力氣寫文件的原因**：這個專案往後會由不同的 AI
工作階段接手，而它們之間唯一共享的東西就是 repo 裡的檔案。

⚠️ **在新機器上開工前先讀 `CLAUDE.md`**，特別是「⚠️ 執行環境限制：不能刪檔」
那一節——如果新的環境**沒有**那個限制（例如你自己的電腦），那一節的
`.attic/` 與 `git-safe-commit.sh` 就不是必要的了，但**照著做也不會錯**。
