# 在 Windows PC 上部署測試

這份文件帶你在一台 Windows 電腦上，從完全沒有 Python 開始，把「工程數學自動出題
練習系統」跑起來，並在瀏覽器裡實際點過出題頁與兩個互動展示。

**讀者假設**：會用檔案總管、會開 PowerShell，但不熟悉 Python 生態。每一段都給
可以直接複製貼上的指令，並說明它在做什麼。

> ⚠️ **這是本機測試用的部署，不是正式上線。** 沒有 HTTPS、跑的是 uvicorn 的開發
> 伺服器、只監聽本機。要開放給學生之前必須另外處理，見最後一節
> 〈[這不是正式上線](#這不是正式上線)〉。

---

## 目錄

- [0. 先看這裡：整體流程](#0-先看這裡整體流程)
- [1. 要安裝什麼](#1-要安裝什麼)
- [2. 安裝 Python](#2-安裝-python)
- [3. 取得專案檔案](#3-取得專案檔案)
- [4. 建立虛擬環境並安裝套件](#4-建立虛擬環境並安裝套件)
- [5. 設定 SESSION_SECRET](#5-設定-session_secret)
- [6. 啟動與停止伺服器](#6-啟動與停止伺服器)
- [7. 第一次使用](#7-第一次使用)
- [8. 互動展示的瀏覽器需求](#8-互動展示的瀏覽器需求)
- [9. 疑難排解](#9-疑難排解)
- [10. 資料庫檔案、備份與清除](#10-資料庫檔案備份與清除)
- [11. 跑測試（選用）](#11-跑測試選用)
- [12. 這不是正式上線](#這不是正式上線)

---

## 0. 先看這裡：整體流程

全部順利的話，從零到能在瀏覽器看到題目大約 **15 分鐘**（其中安裝套件約 1–3 分鐘，
看網路速度）。流程是：

```
安裝 Python  →  解壓專案  →  建立虛擬環境  →  安裝套件
             →  設一把金鑰  →  啟動 uvicorn  →  瀏覽器開 127.0.0.1:8000
```

整段只需要一個 PowerShell 視窗。**伺服器跑起來之後那個視窗不能關**——關掉視窗
等於關掉伺服器。

---

## 1. 要安裝什麼

| 軟體 | 版本 | 一定要嗎 |
|---|---|---|
| **Python** | **3.10 以上**；建議 **3.13.x** | ✅ 必要 |
| **Node.js** | 18 以上 | ❌ **部署不需要**，只有跑 JS 測試才要 |
| 瀏覽器 | 近幾年的 Chrome／Edge／Firefox | ✅ 必要（Edge 是 Windows 內建的） |

不需要安裝的東西：**Git**（用 zip 就好）、**Visual Studio / C++ 編譯器**、
**npm**、**Docker**、**任何資料庫伺服器**。這個系統的執行期就是「一個 Python
行程 + 一個 SQLite 檔案」。

### 為什麼 Python 最低是 3.10

這個數字不是憑印象，是從專案的相依套件實際查出來的：

1. **程式碼本身**其實可以在更舊的版本上編譯。全部 `.py` 檔以 `ast` 在
   `feature_version=(3, 8)` 下都解析得過；所有用到 `X | None` 這種新式型別寫法的
   模組都寫了 `from __future__ import annotations`，所以那些寫法在執行期不會被求值。
   語法不是瓶頸。
2. **`requirements.txt` 把 `sympy` 鎖在 `1.14.*`**，而 sympy 1.14.0 的
   `Requires-Python` 是 **`>=3.9`**。這是第一道硬牆——3.8 連套件都裝不起來。
3. **真正決定 3.10 的是其餘套件的現況。** `requirements.txt` 用的是範圍
   （例如 `fastapi>=0.115,<1.0`），所以今天在一台乾淨的機器上 `pip install` 會拿到
   目前的最新版。實際查到的 `Requires-Python`：

   | 套件 | 目前會裝到的版本 | Requires-Python |
   |---|---|---|
   | fastapi | 0.141.1 | **>=3.10** |
   | starlette | 1.6.0 | **>=3.10** |
   | sqlmodel | 0.0.39 | **>=3.10** |
   | pytest | 9.1.1 | **>=3.10** |
   | pydantic | 2.13.4 | >=3.9 |
   | sympy | 1.14.0 | >=3.9 |

   在 Python 3.9 上 pip **不會報錯**，它會安靜地退回舊版（fastapi 0.128.8、
   starlette 0.49.3、sqlmodel 0.0.34、pytest 8.4.2）。那是一組**這個專案從來沒有
   測過的組合**——正是 `CLAUDE.md` 硬規則 4 所說的「無聲降級」。所以 3.9 不列為支援。

4. **建議 3.13 的理由**：開發機的 `.venv` 就是 Python 3.13.4，測試都在那上面跑過。
   3.12 也沒問題。3.14 在相依解析上查得到全部套件，但這個專案沒有在上面跑過測試，
   要用請自行跑一次 `pytest`。

### Node 只有跑 JS 測試才需要

展示頁面用的是瀏覽器原生的 ES modules，**沒有 build step、沒有 npm、沒有
`package.json`**。瀏覽器自己就是執行環境。

Node 唯一的用途是 `tests/test_dsp_js.py`——它用 node 直接 import
`app/static/demos/lib/` 的純函式來驗證 93 項數值斷言。**沒有裝 node 的話那 93 項會
自動 skip 並印出原因**，其餘 197 項照跑。單純要把系統跑起來給人看，不用裝 node。

---

## 2. 安裝 Python

### 2.1 下載

到 <https://www.python.org/downloads/windows/> 下載
**Windows installer (64-bit)**，選 3.13 系列的最新版。

> **不要用 Microsoft Store 版的 Python。** Store 版會把套件裝到一個被重新導向的
> 虛擬化路徑底下，虛擬環境與檔案權限的行為都和一般安裝不同，出問題時很難查。

### 2.2 ⚠️ 安裝精靈：一定要勾「Add python.exe to PATH」

這是整份文件裡**最常見的卡關點**，而且它的症狀會讓人往完全錯誤的方向找：

執行安裝檔後的第一個畫面，最下方有一個核取方塊：

```
[ ] Use admin privileges when installing py.exe
[ ] Add python.exe to PATH          ← 這個一定要勾
```

**勾起來**，再按 `Install Now`。

沒有勾的話，安裝其實是成功的，但 PowerShell 找不到 `python` 這個指令。Windows 的
反應特別容易誤導人——它不會說「找不到」，而是**跳出 Microsoft Store 叫你安裝
Python**，於是很多人以為剛才沒裝成功，又裝一次，然後又跳出來。

**如果已經裝好才發現沒勾**：不用移除重裝。重新執行同一個安裝檔 → 選 `Modify` →
下一頁把 `Add Python to environment variables` 勾起來 → `Install`。

### 2.3 驗證

**關掉所有已開啟的 PowerShell 視窗，重新開一個**（PATH 的變更只對新開的視窗生效，
這也是一個常見的假性失敗），然後執行：

```powershell
python --version
```

應該印出類似：

```
Python 3.13.4
```

如果印出的是 `Python 3.9.x` 或更舊，或者跳出 Microsoft Store，請回頭看 2.2。

> **`python` 還是 `py`？** Windows 版 Python 另外安裝了一個「啟動器」`py`。
> `py --version` 也可以用，而且 `py -3.13` 可以在裝了多個版本時指定其中一個。
> 本文件一律用 `python`，因為 PATH 勾了之後兩者等價，少一個要記的東西。

---

## 3. 取得專案檔案

你拿到的是一個 `engmath-practice-<日期>.zip`。

1. 如果這個 zip 是從網路下載或從郵件存下來的，Windows 會給它一個「來自其他電腦」
   的標記，有時會讓解壓出來的檔案帶著封鎖屬性。先解除封鎖比較省事：

   ```powershell
   Unblock-File -Path "$HOME\Downloads\engmath-practice-2026-08-19.zip"
   ```

2. 解壓縮。用檔案總管右鍵「解壓縮全部」也可以，或用 PowerShell：

   ```powershell
   Expand-Archive -Path "$HOME\Downloads\engmath-practice-2026-08-19.zip" -DestinationPath "$HOME\Documents"
   ```

   解壓後會得到 `C:\Users\<你的帳號>\Documents\engmath-practice\`。

3. **路徑裡不要有中文、空白以外的特殊符號，也不要放在 OneDrive 同步資料夾裡。**
   OneDrive 會在你跑伺服器的同時去同步 `practice.db`，SQLite 的鎖與同步軟體相處得
   不好。`Documents` 若已被 OneDrive 接管，改放 `C:\engmath-practice\` 最單純。

4. 進到專案資料夾（**之後每一段指令都假設你在這個資料夾裡**）：

   ```powershell
   cd "$HOME\Documents\engmath-practice"
   ```

   確認一下位置對不對：

   ```powershell
   Get-ChildItem
   ```

   應該看得到 `app`、`tests`、`scripts`、`requirements.txt`、`README.md` 這些項目。

---

## 4. 建立虛擬環境並安裝套件

「虛擬環境」是一個放在專案資料夾裡的獨立 Python 套件空間。用它的理由很單純：這個
專案要裝十幾個套件，裝進虛擬環境就只影響這個資料夾，不會污染整台電腦的 Python，
不想要了直接刪掉 `.venv` 資料夾就乾淨了。

### 4.1 建立

```powershell
python -m venv .venv
```

跑完會多出一個 `.venv` 資料夾。這一步不需要網路。

### 4.2 ⚠️ 先處理 PowerShell 的執行原則

Windows 的 PowerShell 預設**禁止執行指令碼檔案**，而啟用虛擬環境靠的正是一個
`.ps1` 指令碼。不先處理的話，下一步會看到紅字：

```
無法載入檔案 ...\.venv\Scripts\Activate.ps1，因為這個系統上已停用指令碼執行。
File ... cannot be loaded because running scripts is disabled on this system.
```

解法是把執行原則放寬，**而且只放寬給目前這個視窗**：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

- `-Scope Process` 表示「只影響現在這個 PowerShell 視窗」。視窗一關就恢復原狀，
  不會改到整台電腦的設定，也**不需要系統管理員權限**。
- `RemoteSigned` 表示「本機自己產生的指令碼可以跑，從網路下載的要有簽章」。
  `Activate.ps1` 是剛才 `python -m venv` 在本機產生的，所以放行。

> 這一行**每開一個新的 PowerShell 視窗就要重跑一次**。覺得麻煩的話有兩個替代做法：
> （a）不啟用虛擬環境，直接用完整路徑呼叫，見 [9.3](#93-執行原則怎麼樣都過不了)；
> （b）改用 `cmd.exe` 並執行 `.venv\Scripts\activate.bat`（`.bat` 不受執行原則管）。

### 4.3 啟用虛擬環境

```powershell
.\.venv\Scripts\Activate.ps1
```

注意三件事，這是 PowerShell 和 Linux／macOS 差最多的地方：

- 開頭的 `.\` **不能省**。PowerShell 為了安全，不會執行目前資料夾裡的檔案，除非你
  明白寫出 `.\`。
- 路徑用**反斜線** `\`，而且是 `Scripts` 資料夾（Linux／macOS 是 `bin`）。
- **沒有 `source` 這個指令**，直接執行檔案本身。網路上查到的
  `source .venv/bin/activate` 是給 bash 用的，在 PowerShell 上一定失敗。

成功的話，提示字元前面會多出 `(.venv)`：

```
(.venv) PS C:\Users\你的帳號\Documents\engmath-practice>
```

**看到 `(.venv)` 才算啟用成功。** 之後每次要操作這個專案，都要先 `cd` 進來再啟用一次。

想離開虛擬環境就打 `deactivate`。

### 4.4 安裝套件

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

第一行先把 pip 自己更新到最新版（舊版 pip 偶爾認不得新的 wheel 檔名格式）。
第二行大約要 1–3 分鐘。

**這一步不需要 C++ 編譯器。** 所有需要編譯的相依套件（`cffi`、
`argon2-cffi-bindings`、`pydantic-core`、`greenlet`、`httptools`、`watchfiles`、
`websockets`、`MarkupSafe`）在 PyPI 上都有現成的 64 位元 Windows wheel，
cp310 / cp312 / cp313 / cp314 均已逐一確認過。看到「Microsoft Visual C++ 14.0 is
required」就代表出了別的問題，見 [9.5](#95-pip-install-失敗)。

> **一個 Windows 上的正常現象**：`uvicorn[standard]` 在 Linux／macOS 上會裝
> `uvloop`，Windows 上不會（uvloop 不支援 Windows，套件自己用條件排除了它）。
> 這不是安裝失敗，效能差異在單機測試的規模下看不出來。

### 4.5 確認裝好了

```powershell
python -c "import fastapi, sympy, sqlmodel; print('ok', fastapi.__version__, sympy.__version__)"
```

印出 `ok 0.141.1 1.14.0`（版本號可能略有不同）就成功了。

---

## 5. 設定 SESSION_SECRET

`SESSION_SECRET` 是用來簽章登入 cookie 的金鑰。**不設也能跑**——程式會在啟動時
自動抽一把隨機的。但那樣的話**每次重啟伺服器，所有人都會被登出**，測試時反覆
重啟會很煩。

### 5.1 設定（目前這個視窗有效）

複製貼上這一行：

```powershell
$env:SESSION_SECRET = (python -c "import secrets; print(secrets.token_hex(32))")
```

它做的事是：呼叫 Python 產生 64 個十六進位字元的隨機字串，把輸出指派給環境變數
`SESSION_SECRET`。

> **PowerShell 和 bash 的差別**：設環境變數是 `$env:名稱 = "值"`，
> **不是** `export 名稱=值`。`export` 在 PowerShell 裡是完全不同的東西
> （`Export-Csv` 之類指令的別名），照 Linux 教學打會得到莫名其妙的錯誤。

檢查有沒有設好：

```powershell
$env:SESSION_SECRET
```

應該印出一長串十六進位字元。**印出空白就是沒設成功**，多半是 `python` 那一段
出錯（虛擬環境沒啟用？）。

### 5.2 想讓它固定下來（選用）

上面那一行只對目前這個視窗有效。要讓它每次開視窗都在：

```powershell
# 先產生一把、印出來看看
python -c "import secrets; print(secrets.token_hex(32))"

# 把印出來的字串填進去（連同引號）
setx SESSION_SECRET "把上面那一串貼在這裡"
```

`setx` 寫進使用者的環境變數，**但只對之後新開的視窗生效**，目前這個視窗還是要用
5.1 的寫法設一次。

> ⚠️ `setx` 會把金鑰以明文存進 Windows 登錄檔。測試機上還好，正式環境請用別的做法。

### 5.3 或者用 `.env` 檔（選用）

專案附了 `.env.example`。複製一份改名為 `.env`，把 `SESSION_SECRET=` 後面填上金鑰：

```powershell
Copy-Item .env.example .env
notepad .env
```

然後啟動時多帶一個參數（見下一節）：

```powershell
uvicorn app.main:app --env-file .env --reload
```

注意 `.env` 是 **uvicorn 讀的，不是應用程式自己讀的**，所以一定要加
`--env-file .env`，不然檔案會被完全忽略。

---

## 6. 啟動與停止伺服器

### 6.1 啟動

確認提示字元前面有 `(.venv)`，然後：

```powershell
uvicorn app.main:app --reload
```

看到這樣的輸出就是起來了：

```
INFO:     Will watch for changes in these directories: ['C:\\Users\\...\\engmath-practice']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Application startup complete.
```

`--reload` 表示改到程式碼會自動重啟，測試時很方便；不想要就拿掉。

第一次啟動會在專案資料夾裡自動建立 `practice.db`。

### 6.2 用瀏覽器打開

網址是：

**<http://127.0.0.1:8000>**

（`http://localhost:8000` 也是同一個地方。注意是 `http`，**不是 `https`**——
這個測試部署沒有憑證，打 `https://` 會連不上。）

### 6.3 停止

回到那個 PowerShell 視窗，按 **`Ctrl` + `C`**。看到提示字元回來就是停了。

**不要用關視窗的方式停**（雖然通常也沒事）。如果 `Ctrl+C` 按了沒反應，再按一次；
`--reload` 模式下偶爾要按兩下才會把子行程一起收掉。

### 6.4 其他常用參數

```powershell
# 換一個埠（8000 被占用時）
uvicorn app.main:app --port 8001

# 想看出題引擎為什麼重抽參數
$env:APP_LOG_LEVEL = "DEBUG"
uvicorn app.main:app --reload
```

> ⚠️ **不要加 `--host 0.0.0.0`。** 預設只監聽 `127.0.0.1`，也就是只有這台電腦連得到，
> 這正是測試部署該有的樣子。改成 `0.0.0.0` 會讓同一個網路上的人都連得進來，
> 而這個系統**沒有 HTTPS**，登入密碼會以明文在網路上傳輸。

---

## 7. 第一次使用

### 7.1 註冊一個帳號

1. 開 <http://127.0.0.1:8000>，會被導到登入頁。
2. 點 **Register** 進註冊頁 <http://127.0.0.1:8000/register>。
3. 填「學號」與密碼（密碼要輸入兩次）：
   - 學號：4–20 個字元，只能是**英文字母、數字、連字號**（會自動轉成大寫）。
     測試用 `TEST001` 就好。
   - 密碼：8–128 字元，不能和學號相同。
   - ⚠️ 註冊頁上寫著、這裡再說一次：**不要用學校的信箱密碼或校務系統密碼。**
     這是一個測試部署。
4. 頁面下方有一段個人資料蒐集告知，**旁邊的核取方塊必須勾起來**才送得出去。
   系統只會記錄「誰、什麼時候、開了哪個題型／展示、哪個難度、哪個 seed」這五個欄位。
5. 送出成功會**直接登入**並跳到首頁。

### 7.2 出題頁

註冊完會直接登入並進到首頁 <http://127.0.0.1:8000>，也就是出題頁。

1. 從下拉選單挑一個題型（目前有四個，都是常微分方程與線性系統）。
2. 挑難度 1～3。
3. 按 **Generate**。題目會用 KaTeX 排版顯示出來。
4. 題目卡片下面有兩層收合區塊，**預設都是收起來的**：
   - `Show Answer` → 展開看答案
   - `Show Solution Steps` → 展開看逐步解答

   這是刻意的設計（先自己算，再對答案）。

5. 偶爾會看到「Please press Generate again」——這是正常的。出題用的是拒絕抽樣：
   抽一組參數、用 SymPy 驗證答案代回去殘差是不是 0，不是就重抽；重抽到上限仍然
   失敗時就請你再按一次。**如果某個題型每次都這樣，那才是 bug**，PowerShell 視窗
   裡會有一行中文的 WARNING 說明是哪個題型、哪個難度。

6. 上方導覽列有 **My Progress** <http://127.0.0.1:8000/progress>，看自己出過幾題。

### 7.3 兩個互動展示

從導覽列進 **Demos** <http://127.0.0.1:8000/demos>，目前有兩頁：

| 展示 | 網址 | 內容 |
|---|---|---|
| **Sampling and aliasing** | <http://127.0.0.1:8000/demos/sampling/aliasing> | 把取樣率降到奈奎斯特頻率以下，**聽**純音變成什麼樣子 |
| **Spectrum, windows and leakage** | <http://127.0.0.1:8000/demos/spectrum/leakage> | 一個音不落在分析格點上時頻譜怎麼散開，加窗又能幫上什麼 |

這兩頁**都會發出聲音**。請先讀下一節。

---

## 8. 互動展示的瀏覽器需求

### 8.1 用哪個瀏覽器

展示用到 **Web Audio API**、**AudioWorklet**、**ES modules**、**Canvas**。
這些都是標準功能，但需要**不算太舊的瀏覽器**：

| 瀏覽器 | 最低 | 建議 |
|---|---|---|
| **Microsoft Edge** | 79 | 近一年內的版本 |
| **Google Chrome** | 66 | 近一年內的版本 |
| **Mozilla Firefox** | 76 | 近一年內的版本 |

Windows 內建的 Edge 只要有在更新就一定夠新。**Internet Explorer 完全不能用**
（它沒有 AudioWorklet，也不支援 ES modules）。

**只支援桌機瀏覽器**：不處理觸控、沒有為小螢幕最佳化。用手機開不會壞，但版面會亂。

> ⚠️ **老實說一句**：這兩個展示的伺服器端該驗的都驗過了（路由、資產、頁面內容、
> 純函式層 93 項數值斷言），但**音訊、canvas、autoplay 解鎖、worklet 載入這些只有
> 真的瀏覽器才跑得到的部分，開發環境沒有瀏覽器，從來沒有實際執行過**。這次
> Windows 測試部署正好就是它們的第一次驗收——遇到問題是意料之中的，不是你裝錯了。

### 8.2 ⚠️ 要先點一下頁面才會有聲音

瀏覽器有 **autoplay 政策**：頁面在使用者做出「明確的互動」之前，不准自己發出聲音。
所以：

- **一定要先按頁面上那個藍色的 `Start sound` 按鈕**，音訊才會啟動。載入頁面就等著
  聽是等不到的。（按下去之後它會變成 `Stop sound`。）
- 這不是 bug。如果 autoplay 被擋掉，頁面會用英文寫一句訊息告訴你，**不會只在
  devtools 裡默默印一行**。
- 切到別的分頁再切回來，有些瀏覽器會把音訊暫停。按一下 `Stop sound` 再
  `Start sound` 就好。

### 8.3 音量建議

**先把系統音量調到很低，再按 `Start sound`。**

理由很實際：這兩個展示放的是**純音**（正弦波）與**白雜訊**，不是音樂。同樣的
音量刻度下，純音聽起來會比音樂刺耳得多，而混疊展示的重點又剛好是把頻率一路往上
推。用耳機的話更要小心。

頁面上有自己的 `Volume` 滑桿與 `Mute` 鈕，建議：

1. 系統音量先降到平常的三分之一。
2. 頁面的 `Volume` 滑桿放在低檔。
3. 按 `Start sound`，再慢慢往上調到聽得清楚就好。

### 8.4 選自己的音訊檔（頻譜展示）

頻譜展示可以讓你選一個自己電腦上的音訊檔來分析。

**檔案完全在瀏覽器裡處理，絕對不會上傳到伺服器**，也不會寫進任何紀錄。頁面上有
寫明這件事，而且有六項測試在盯著它（前端不得出現任何送出資料的原語、伺服器端
根本沒有任何路由收得了檔案）。

格式：`.wav` 一定可以；`.mp3`／`.m4a`／`.ogg`／`.flac` 看瀏覽器支不支援。
太大、解不開、不是音訊、多聲道、太長（只取前 30 秒）都會在畫面上給一句英文說明。

不想用自己的檔案的話，下拉選單裡有六個內建範例（純正弦、雙頻、方波、鋸齒、
白雜訊、一句合成語音），跟著專案一起打包，不需要另外下載。

---

## 9. 疑難排解

### 9.1 `python` 不是內部或外部命令 / 跳出 Microsoft Store

PATH 沒設好。看 [2.2](#22-️-安裝精靈一定要勾add-pythonexe-to-path)。
最常見的兩個原因：安裝時沒勾 PATH，或者**勾了但沒有重開 PowerShell 視窗**。

臨時繞過的辦法（確認 Python 真的裝好了）：

```powershell
py --version
```

`py` 走的是另一個註冊機制，即使 PATH 沒設好通常也能用。

### 9.2 連接埠 8000 被占用

啟動時看到：

```
ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000):
          only one usage of each socket address is normally permitted
```

先找出是誰占著：

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
Get-Process -Id <上面印出來的數字>
```

（舊系統上 `Get-NetTCPConnection` 不在的話，用 `netstat -ano | findstr :8000`，
最後一欄就是 PID。）

最常見的元凶是**上一個沒關乾淨的 uvicorn**。確定是自己的就關掉：

```powershell
Stop-Process -Id <PID>
```

不想追究就直接換一個埠，記得瀏覽器網址也要跟著改：

```powershell
uvicorn app.main:app --port 8001
```

> **Windows 特有的一種情況**：裝了 Hyper-V、WSL2 或 Docker Desktop 的機器，系統會
> 預留一段動態連接埠，8000 有可能落在裡面。這時候占用它的不是任何看得到的程式。
> 用這個指令看預留範圍：
>
> ```powershell
> netsh int ipv4 show excludedportrange protocol=tcp
> ```
>
> 8000 若在某個區間裡，別跟它爭，換 8080 或 5000 之外的一個埠就好。

### 9.3 執行原則怎麼樣都過不了

如果公司或學校的群組原則鎖死了 PowerShell 執行原則，`Set-ExecutionPolicy` 會失敗，
而且你也改不了。**不用啟用虛擬環境也能跑**，直接用完整路徑呼叫裡面的執行檔：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

效果完全相同，只是提示字元前面不會出現 `(.venv)`，而且每一行都要打全路徑。

另一個辦法是改用 `cmd.exe`（不是 PowerShell），執行 `.venv\Scripts\activate.bat`
——`.bat` 檔不受執行原則管轄。

### 9.4 出現「Windows 安全性警訊」防火牆詢問

第一次啟動 uvicorn 時 Windows 可能跳出防火牆對話框，問要不要允許 Python 通過防火牆。

**按「取消」或取消所有勾選就好。** 這個測試部署只監聽 `127.0.0.1`（本機回送位址），
本機連本機的流量根本不經過防火牆，拒絕它不會影響任何功能。

反過來說：如果你**允許**了，加上前面警告過的 `--host 0.0.0.0`，就會變成同網段的
任何人都連得到一個沒有 HTTPS 的登入頁。測試部署不要這樣做。

### 9.5 `pip install` 失敗

依錯誤訊息分：

| 訊息裡有 | 多半是 | 怎麼辦 |
|---|---|---|
| `Could not find a version that satisfies the requirement sympy==1.14.*` | Python 版本太舊（3.8 以下） | 裝 3.13，見第 2 節 |
| `Microsoft Visual C++ 14.0 or greater is required` | pip 在嘗試從原始碼編譯 | 先 `python -m pip install --upgrade pip`；並確認裝的是 **64 位元**的 Python（32 位元沒有預編譯的 wheel） |
| `SSL: CERTIFICATE_VERIFY_FAILED` | 公司／學校網路做 TLS 攔檢 | 換一個網路（例如手機熱點），或請資訊人員給根憑證 |
| `Connection timed out` / 卡住不動 | 連不到 PyPI | 換網路；或試國內鏡像 `python -m pip install -r requirements.txt -i https://pypi.org/simple` |
| `Access is denied` / `Permission denied` | 防毒軟體鎖住 `.venv` | 把專案資料夾加進防毒的排除清單，或換一個資料夾 |

還是不行的話，把整段錯誤訊息留下來——最後幾行通常直接寫出了原因。

### 9.6 網頁打得開但數學公式是一堆原始碼

看到 `\frac{dy}{dx}` 這種字面文字而不是排版好的公式，代表 KaTeX 沒載入。

這個專案**沒有連任何外部 CDN**，KaTeX、HTMX、FFT 全部自己帶在
`app/static/vendor/`。所以這個症狀幾乎一定是**檔案缺了**——多半是解壓縮沒解完整
（Windows 內建的解壓縮偶爾會在路徑太長時中斷）。檢查：

```powershell
Get-ChildItem app\static\vendor\katex\fonts | Measure-Object
```

應該有 **20** 個 `.woff2` 字型檔。少了就重解一次 zip，並把專案放到更短的路徑
（例如 `C:\engmath\`）。

### 9.7 展示頁聽不到聲音

依序檢查：

1. **按了 `Start sound` 嗎？** 見 [8.2](#82-️-要先點一下頁面才會有聲音)。這是最常見的原因。
2. **頁面上有沒有一句英文錯誤訊息？** 有的話照著它說的處理——這個專案規定音訊的
   每一種失敗都要在畫面上留一句話，不會只寫在 devtools 裡。
3. **靜音鈕、音量滑桿。** 頁面自己有一組。
4. **系統音量混音器。** Windows 會為每個應用程式分開記音量：工作列音量圖示右鍵 →
   「開啟音量混音器」→ 看看瀏覽器那一條是不是被拉到 0 或靜音。
5. **輸出裝置對不對。** 接了 HDMI 螢幕或藍牙耳機時，Windows 常常把預設輸出換掉。
6. **換一個瀏覽器試。** Edge 與 Firefox 各試一次，可以區分是瀏覽器的問題還是系統的。

### 9.8 圖不會動 / 畫面卡住

1. **先看 devtools 的 Console**（按 `F12` → `Console` 分頁），紅字通常直接指出問題。
2. **`file://` 開不起來。** 一定要透過 `http://127.0.0.1:8000` 存取。直接在檔案總管
   裡按兩下 `.html` 檔會被 CORS 擋掉，ES modules 根本不會載入。
3. **`prefers-reduced-motion`。** 如果 Windows 的「設定 → 協助工具 → 視覺效果 →
   動畫效果」是關的，頻譜圖會刻意改成**按鍵推進**而不是連續捲動。這是有意的無障礙
   行為，不是壞掉。
4. **硬體加速。** 瀏覽器設定裡關掉硬體加速再試一次；老舊的顯示卡驅動有時會讓
   canvas 整個不更新。

### 9.9 資料庫檔案相關

- **`practice.db` 建不出來**：多半是專案放在需要系統管理員權限的位置
  （例如 `C:\Program Files\`）。移到 `C:\Users\<你>\Documents\` 或 `C:\engmath\`。
- **`database is locked`**：同時跑了兩個 uvicorn，或 OneDrive／備份軟體正在同步
  那個檔案。先確認只有一個伺服器在跑，並把專案移出同步資料夾。
- **⚠️ 檔案權限在 Windows 上是另一回事**：程式啟動時會呼叫 `os.chmod(db, 0o600)`
  想把權限收緊成「只有自己讀得到」。**這一行在 Windows 上幾乎沒有作用**——
  Windows 的 `os.chmod` 只認得「唯讀」這一個位元，Unix 的 rwx 權限位它一概忽略。
  而且因為呼叫本身**成功**了，程式不會印出任何警告。

  也就是說：`practice.db` 的實際存取權限完全由它所在資料夾的 Windows ACL 決定。
  放在自己的使用者資料夾底下，一般家用機大致等同「只有你和管理員讀得到」；
  多人共用的電腦上請自己確認一次。這個檔案裡有**學號明文與密碼雜湊**。

---

## 10. 資料庫檔案、備份與清除

### 10.1 檔案在哪

預設就在專案資料夾裡：

```
engmath-practice\
├── practice.db        ← 全部的資料都在這裡
├── practice.db-wal    ← WAL 日誌（SQLite 用，正常現象）
└── practice.db-shm    ← 共用記憶體索引（同上）
```

想換位置就設 `PRACTICE_DB`：

```powershell
$env:PRACTICE_DB = "C:\engmath-data\practice.db"
uvicorn app.main:app --reload
```

（那個資料夾要先自己建好。）

`-wal` 和 `-shm` 是 SQLite 的 WAL 模式產生的，**不要手動刪**，伺服器正常關閉後
內容會併回主檔。

### 10.2 裡面有什麼

兩張表，就這些：

- **`student`**：學號（明文）、密碼的 argon2id 雜湊、建立時間、最後登入時間、同意時間。
  **密碼本身絕對沒有存**（有一項測試會掃過整個 DB 檔案確認這件事）。
- **`usagelog`**：誰、什麼時候、哪個題型／展示、哪個難度、哪個 seed。
  沒有作答內容、沒有對錯、沒有滑桿位置、沒有停留時間。

### 10.3 備份

伺服器停著的時候，複製一份就是備份：

```powershell
Copy-Item practice.db "practice-backup-$(Get-Date -Format yyyyMMdd).db"
```

伺服器正在跑的時候要用 SQLite 自己的備份指令，才不會抄到寫到一半的狀態：

```powershell
python -c "import sqlite3; s=sqlite3.connect('practice.db'); d=sqlite3.connect('practice-backup.db'); s.backup(d); d.close(); s.close()"
```

> ⚠️ **備份檔和正本一樣含有學號與密碼雜湊。** 真的要留存就加密（7-Zip 設密碼、
> 或 `age`／`gpg`），不要往雲端硬碟隨手一丟。測試完就刪掉最省事。

### 10.4 全部清掉重來

這是測試部署，資料就是一個檔案，砍掉重練沒有任何副作用：

```powershell
# 先確定伺服器已經停了（Ctrl+C）
Remove-Item practice.db, practice.db-wal, practice.db-shm -ErrorAction SilentlyContinue
```

下次啟動會自動建一個新的空資料庫，帳號要重新註冊。

### 10.5 整包移除

不想留任何東西的話：停掉伺服器 → 刪掉整個 `engmath-practice` 資料夾。
套件全部裝在裡面的 `.venv`，系統其他地方沒有殘留。要連 Python 一起移除的話走
「設定 → 應用程式」。

---

## 11. 跑測試（選用）

不是部署的必要步驟，但這是確認「這包東西是完整的」最快的方法。

```powershell
pytest
```

全部 **290 項**，大約 **2 分 40 秒**（出題引擎的 SymPy 驗證佔了大部分時間）。

沒有裝 Node 的話：

```
93 skipped
```

——那 93 項是 `tests/test_dsp_js.py`，需要 node 才跑得動，會 skip 並印出原因，
其餘 197 項照常。要跑那 93 項就去 <https://nodejs.org/> 裝一個 LTS 版，
重開 PowerShell 之後再跑一次。

想跳過它們、只跑 Python 那邊：

```powershell
pytest -m "not dsp_js"
```

單獨跑某一組：

```powershell
pytest tests\test_web.py -q      # 端對端流程（56 項）
pytest tests\test_demos.py -q    # 展示區規則（50 項，約 9 秒）
```

---

## 這不是正式上線

再說一次，因為這件事很容易在「跑起來了、看起來很正常」之後被忘記。

**目前這個部署缺的東西：**

| 缺什麼 | 為什麼要緊 |
|---|---|
| **HTTPS** | 系統處理密碼。沒有 HTTPS，登入時的學號與密碼在網路上是明文。這是上線的硬性前提，不是加分項。 |
| **正式的 WSGI／ASGI 部署方式** | `uvicorn --reload` 是**開發伺服器**：會監看檔案變動、沒有 process 管理、掛了不會自己起來。 |
| **資料庫檔案權限** | 見 [9.9](#99-資料庫檔案相關)。Windows 上 `chmod 600` 形同虛設，而檔案裡有學號與密碼雜湊。 |
| **備份機制** | 現在只有「你記得手動複製」。 |
| **速率限制的正確性前提** | 目前的登入速率限制是**單一行程的記憶體計數器**。所以只能用**單一個 uvicorn 行程**部署；開多個 worker 會讓限制形同虛設。 |

**另外要記得的兩件事：**

- 學期結束後應執行去識別化（PLAN.md §4.4）。
- 註冊頁的個資告知與 `UsageLog` 實際存的欄位是**一字對應**的，而且有測試盯著。
  要多記任何東西之前，先看 PLAN.md §4.4 與 `CLAUDE.md` 硬規則 3。

**要真的開放給學生，PLAN.md §7〈仍待決定〉的「部署與維運」四項必須先有答案**
（那一節就是為這件事準備的）：

1. **部署在哪？** 校內 VM（要申請、通常要過資安檢查）／個人租的 VPS（學生資料放
   校外要先確認學校政策）／校內實驗室機器 + Cloudflare Tunnel。
2. **HTTPS 與網域怎麼取得？** 校內網域要申請，或用 Caddy／Cloudflare Tunnel
   自動取得憑證。
3. **誰在學期中負責修 bug？** 只有老師一人的話，階段 2 的範圍應該再壓縮。
4. **備份頻率與存放位置？** 建議每日 `sqlite3 .backup` + 加密後傳到另一台機器。

順帶一提：真的要上線的話，**Windows 不是建議的環境**。PLAN.md §1.3 假設的是
校內 Linux VM + systemd + Caddy（自動 HTTPS）。這台 Windows PC 的用途是**先把
東西跑起來看看、特別是在真的瀏覽器裡驗收那兩個展示**——那正是目前最欠缺的一塊。

---

## 附錄：指令速查

從零開始（第一次）：

```powershell
cd "$HOME\Documents\engmath-practice"
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:SESSION_SECRET = (python -c "import secrets; print(secrets.token_hex(32))")
uvicorn app.main:app --reload
```

之後每次（開新視窗時）：

```powershell
cd "$HOME\Documents\engmath-practice"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
$env:SESSION_SECRET = (python -c "import secrets; print(secrets.token_hex(32))")
uvicorn app.main:app --reload
```

然後開 <http://127.0.0.1:8000>，`Ctrl+C` 停止。

---

## PowerShell 與 bash 對照表

網路上大部分 Python 教學是寫給 macOS／Linux 的。這張表列出這份文件用得到的全部差異：

| 要做的事 | bash（Linux／macOS） | PowerShell（Windows） |
|---|---|---|
| 啟用虛擬環境 | `source .venv/bin/activate` | `.\.venv\Scripts\Activate.ps1` |
| 設環境變數 | `export VAR=value` | `$env:VAR = "value"` |
| 讀環境變數 | `echo $VAR` | `$env:VAR` |
| 把指令輸出存進變數 | `VAR=$(cmd)` | `$VAR = (cmd)` |
| 路徑分隔符號 | `/` | `\`（多數情況 `/` 也通） |
| 執行目前資料夾的檔案 | `./script` | `.\script`（`.\` 不能省） |
| 列出檔案 | `ls -l` | `Get-ChildItem`（別名 `ls`、`dir`） |
| 刪檔 | `rm file` | `Remove-Item file`（別名 `rm`、`del`） |
| 複製 | `cp a b` | `Copy-Item a b`（別名 `cp`） |
| 家目錄 | `~` 或 `$HOME` | `$HOME`（`~` 多數指令也認） |
| 停止前景程式 | `Ctrl+C` | `Ctrl+C`（一樣） |
