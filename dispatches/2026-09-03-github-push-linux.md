# 在 Linux 上把專案 push 回 GitHub（`PUBLISHING.md` 的認證那一節只寫了 macOS）

**日期**：2026-09-03　**工作項**：**PUB-LINUX**（新，不在 PLAN 路線圖上）
**狀態**：進行中（本檔案在開工的第一件事就建立，見 `dispatches/README.md`）

> 同一天、同一個工作階段的第四輪派送。

---

## 提示詞（逐字）

關於自動增量更新地圖的部份，先暫時不動，但請在每輪工作結束的回報的最後一段提醒我。我打算刪除微分方程的一些題型，決定後會告訴您，您刪掉那些題型後，接著刪掉相關的測試，然後再做自動增量更新地圖的部份（這樣就不需要重跑我會刪掉的東西）。現在，請先教我如何在 linux 能夠把這個專案 push 回 github 我的 repo 。我之前 linux 關於 github 的設定可能沒設好，我也忘記怎麼設定了。剛剛打 git push 出現如下訊息："remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/wangc86/engmath-practice.git/'"
請協助我、教我能成功 push。

---

## 回覆（摘要；完整版見本輪最終訊息）

### 診斷：文件有寫，但寫的是 macOS

`PUBLISHING.md` §3 早就有「一定會撞到 `Password authentication is not
supported`」那一節，兩條路（SSH／token）都寫了。**問題是那三個關鍵指令
在 Linux 上都不存在**：`pbcopy`、`ssh-add --apple-use-keychain`、
`git config credential.helper osxkeychain`。照著做會在第 2 步卡住。

⚠️ **一份「寫過了但在這台機器上跑不動」的文件，比沒寫更容易讓人卡住**
——讀的人會以為是自己做錯了。

### 另一條線索：`Invalid username or token`

老師貼的錯誤訊息是 `remote: Invalid username or token.`，**而不只是**
`Password authentication is not supported`。差別有意義：前者代表
**git 確實送出了某組帳密**，多半是某個 credential helper 存著一組
已經失效的舊資料。⚠️ **那組東西不會因為新建了 token 就消失。**
換成 SSH 之後它就用不到了，所以那一節寫成「多半不必做，但真的要清的話這樣清」。

### 做了什麼

`PUBLISHING.md` 的認證那一節改寫：SSH 路線 **Linux 與 macOS 各一份指令**，
另補三件原本沒有的東西——passphrase 要不要設的取捨（兩行，讓老師自己決定）、
怎麼清掉失效的舊憑證、以及 Linux 的 `credential.helper store` 是**純文字**
存 token（macOS 的鑰匙圈不是），那是更推薦 SSH 的另一個理由。

另外查證並記下：**兩個 tag（`grading-v1`、`hosted-v1`）已經在 GitHub 上了**，
所以 `git push --tags` 現在是 no-op。

### 老師的排程決定（記在 PLAN §7 #44）

自動增量更新相依地圖那一項**先不做**，順序改成
**（1）刪掉部分微分方程題型 →（2）刪掉相關測試 →（3）才做那一項**，
理由是現在做等於先花一小時去量一批馬上要被刪掉的東西。
⛔ **老師要求每一輪回報的最後一段都要提醒這一項**，
而那件事沒有測試守得住，所以寫進 §7 #44 讓下一個接手的人讀得到。

### 踩到的坑

沒有。這一輪只改文件。⚠️ 但有一件不算坑、值得記的事：
**我沒有辦法從這裡驗證那些指令在老師的機器上真的可行**——
`device_bash` 跑的是一個掛載了資料夾的沙箱 VM，不是老師的登入環境，
`~/.ssh` 與 `~/.gitconfig` 都看不到。那些步驟是規格上的把握，不是實測過的。
