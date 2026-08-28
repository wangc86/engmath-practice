# 在 FreeBSD 上部署本系統：可行性評估與安裝說明

> 對象：老師本人（校內一台固定 IP 的主機）。
> 目標：把這個系統架起來給修課學生連線使用。
>
> 本文件寫於 **v0.15**，於 **v0.16** 更新，對應「兩組共用帳號、系統不蒐集任何
> 個人資料」的版本（PLAN.md **D35–D40**）。v0.16 對這份文件的影響集中在三處：
> **新增 §5.7（反向代理的存取紀錄要把 IP 拿掉，D38——這是新增的、而且最容易
> 在部署當天被忘記的一步）**、§5.5 備份的個資義務消失、§7 建帳號那一步變簡單了。
> **v0.19 再更新**：老師決定**網站只開放校內 IP 連線，校外要先連學校 VPN**
> （PLAN.md **D42**）。這一輪的新增集中在 **§5.8**（緊接在 §5.7 後面，
> 因為「允許清單」與「不記 IP」共用同一個設定檔，而那正是它最容易一起壞掉的地方），
> 另外順手修掉 **§5.2 rc.d 草稿的兩個 bug**（服務會以 root 執行、`service status`
> 對不上）與 **§5.4 log 輪替的那個問號**（`daemon(8)` 有 `-H`）。
> §6、§7、§8 同步。
>
> Windows 上的**測試**部署見 `WINDOWS-SETUP.md`；**家裡用區網預演一次**見
> `FREEBSD-HOMELAB.md`（v0.19 新增，繁體中文，可以照著跑）；
> 這一份講的是**給學生用的**部署，三者的要求差很多（見 §6 與 `FREEBSD-HOMELAB.md` §1）。

---

## 0. 先講這份文件的可信度

**寫這份文件的環境是 Linux 沙箱，不是 FreeBSD。** 我沒有辦法在 FreeBSD 上實跑
任何一行指令。因此全文的每一項結論都標了下面三種標記之一，請照著讀：

| 標記 | 意思 |
|---|---|
| ✅ **已驗證** | 我在沙箱裡實際跑過、實際看過檔案內容。驗證的**對象**會寫清楚（例如「uvloop 的 sdist 裡有這一段程式碼」——那是關於原始碼的事實，不是關於 FreeBSD 的事實）。 |
| 📄 **依文件推論** | 來自套件的原始碼、FreeBSD 官方文件、FreshPorts、或供應商公告。推論的鏈條會寫出來，讓你可以自己判斷它斷在哪裡。 |
| ❓ **未查證** | 我查不到，或查到的東西不足以下判斷。**寧可寫「不知道」也不編一個看起來很專業的答案。** |

**這份文件裡沒有任何一件事是我在 FreeBSD 上實測過的。** §8 有一份完整的
「我無法驗證的事」清單，第一次安裝時請對著那份清單走。

---

## 1. 可行性結論

**結論：可行，而且這個系統大概是「最適合搬到 FreeBSD」的那一類 Python 專案。**
真正的風險不在系統本身，而在**相依套件怎麼裝**（§3）與 **HTTPS 怎麼生出來**（§4）。

理由分三層：

**（a）這個系統對作業系統的要求非常少。** ✅ 已驗證（對象：本專案原始碼）
我把 `app/` 與 `scripts/` 整個掃過一遍，找平台相依的東西，結果是：

| 找什麼 | 結果 |
|---|---|
| `signal`、`SIGALRM`、`setitimer` | **沒有**。v0.7（D12）捨棄作答判定時，連同 D6／D8／D10 那整套子行程逾時機制一起移除了。 |
| `multiprocessing`、`fork`、start method | **沒有**。同上。這一點很重要：`fork` vs `spawn` 的預設值差異是跨平台最典型的地雷，而這個系統一個子行程都不開。 |
| `sys.platform` 的分支 | **沒有**。程式裡沒有任何一處在問「我在哪個作業系統上」。 |
| 硬寫死的路徑 | **沒有**。全部走 `pathlib.Path(__file__).resolve().parent`（`app/config.py`、`app/main.py`、`app/routes/deps.py` 各一處）。 |
| `os.chmod` | **一處**：`app/db/session.py` 的 `os.chmod(DB_PATH, 0o600)`。已經包在 try/except 裡並留 log（規則 4）——那是為了 Windows 寫的，而在 FreeBSD 上它會**真的生效**。（v0.15 另有一處在 `scripts/create_accounts.py` 的對照表檔案上，**那個檔案隨 D35 消失了**：兩組密碼用不著對照表。） |
| 檔名大小寫 | FreeBSD 的 UFS 與 ZFS 都區分大小寫，與 Linux 相同。這條風險是 Windows 專屬的，在這裡不存在。📄 |
| 外部程式 | 執行期**零**。`scripts/make_demo_samples.py` 會呼叫 `espeak-ng`，但那是產生範例音檔的開發工具，音檔已納入版控；`tests/test_dsp_js.py` 需要 `node`（缺了會 skip 並印原因）。 |

**（b）沒有 Docker、沒有資料庫伺服器。** 資料就是一個 SQLite 檔，前端資產全部自架在
`app/static/vendor/`（KaTeX、HTMX、fft.js），不連 CDN。要搬的東西只有「一個 Python
執行環境 + 一個資料夾」。

**（c）SQLite 的 WAL 模式在 FreeBSD 上沒有問題。** 📄
`app/db/session.py` 開了 `PRAGMA journal_mode=WAL`。WAL 需要共用記憶體（`mmap`），
FreeBSD 的本機檔案系統（UFS／ZFS）都支援。
⚠️ **但 WAL 不能放在 NFS 上**——這是 SQLite 官方文件講明的限制，與 FreeBSD 無關。
如果你打算把資料庫放在校內的網路磁碟上，**不要**；放本機磁碟。

### 唯一一件真正需要決定的事

`requirements.txt` 寫的是 `uvicorn[standard]`，而 `[standard]` 會拉進
**uvloop、httptools、watchfiles** 三個需要編譯的套件。**在 FreeBSD 上建議改成
不帶 `[standard]` 的 `uvicorn`**，理由見 §3.5——這一個決定就砍掉三個編譯目標裡的
兩個 C 專案與一個 Rust 專案，而效能上你**量不出差別**（這個系統的瓶頸是
SymPy 出題的那 0.1 秒 CPU，不是事件迴圈）。

---

## 2. 相依套件全表：誰要編譯、需要什麼

✅ **已驗證（對象：套件的 sdist 內容與 build backend）。** 下表的「需要什麼」欄位
是我在沙箱裡把每個 sdist 抓下來拆開看的結果，不是從記憶裡寫的。
**但「在 FreeBSD 上會不會編過」不在驗證範圍內**——我驗的是「它需要什麼工具鏈」。

| 套件 | 純 Python？ | 需要什麼 | 備註 |
|---|---|---|---|
| `fastapi`, `starlette` | ✅ 是 | — | |
| `sqlmodel` | ✅ 是 | — | |
| `sqlalchemy` | 幾乎是 | 有可選的 C 加速，失敗會自動退回純 Python | |
| `sympy`, `mpmath` | ✅ 是 | — | 純 Python，這是本專案最重的相依但完全不需編譯 |
| `jinja2` | ✅ 是 | — | |
| `itsdangerous` | ✅ 是 | — | |
| `python-multipart` | ✅ 是 | — | |
| `click`, `h11`, `anyio`, `idna`, `typing-extensions` | ✅ 是 | — | |
| `MarkupSafe` | 否（可選） | C 編譯器；**有純 Python 後路** | |
| `greenlet` | ❌ 否 | **C++ 編譯器** | SQLAlchemy 的相依 |
| `cffi` | ❌ 否 | **C 編譯器 + libffi + pkg-config** | `setup.py` 用 `pkg-config libffi` 找標頭檔 |
| `argon2-cffi-bindings` | ❌ 否 | **C 編譯器 + cffi** | sdist **自帶 libargon2 原始碼**（`extras/libargon2/`），所以**不需要**系統的 libargon2。也可設 `ARGON2_CFFI_USE_SYSTEM=1` 改用系統的。x86 上會走 SSE2 最佳化路徑。 |
| `pydantic-core` | ❌ 否 | **Rust（build backend 是 `maturin`）** | 這是**唯一躲不掉的 Rust 相依**。pip 在沙箱裡的錯誤訊息就是 `BackendUnavailable: Cannot import 'maturin'`。 |
| `uvloop` | ❌ 否 | **C 編譯器 + make + sh**（sdist 已附 libuv 的 `configure`，**不需要 autoconf**） | 見下方「uvloop 到底支不支援 FreeBSD」 |
| `httptools` | ❌ 否 | **C 編譯器** | 自帶 llhttp 原始碼，無外部相依 |
| `watchfiles` | ❌ 否 | **Rust（`maturin`）** | **只有 `--reload` 會用到**，正式部署不需要 |
| `websockets` | 否（可選） | C 加速可選，有純 Python 後路 | 本系統不用 WebSocket |
| `pytest`, `httpx` | ✅ 是 | — | 只有跑測試才需要 |

### uvloop 到底支不支援 FreeBSD？

這是網路上講得最含糊的一件事，所以我直接去看原始碼。

✅ **已驗證（對象：`uvloop` 0.22.1 的 sdist）**：

- `setup.py` 第 7 行只拒絕 **Windows**：
  `if sys.platform in ('win32', 'cygwin', 'cli'): raise RuntimeError(...)`。
  **沒有任何一行排除 FreeBSD。**
- `setup.py` 第 212 行有一個**明確的 FreeBSD 分支**：
  `elif sys.platform.startswith(('freebsd', 'dragonfly')): self.compiler.add_library('kvm')`
  ——也就是說作者知道 FreeBSD 存在，而且為它連結了 `libkvm`。
- 它 vendor 進來的 libuv 裡有 `src/unix/freebsd.c` 與 `src/unix/kqueue.c`。
- sdist 裡**已經附了 libuv 的 `configure`**（`setup.py` 的 `sdist` 階段會先跑
  `autogen.sh`），所以編譯時只需要 `sh` + `make` + C 編譯器，**不需要
  autoconf/automake/libtool**。
- PyPI 上的 classifier 是 `Operating System :: POSIX` 與 `MacOS :: MacOS X`
  ——**POSIX 涵蓋 FreeBSD**，但作者顯然沒有列 FreeBSD 專屬的 classifier。

📄 **推論**：uvloop 在 FreeBSD 上**應該編得起來也跑得動**，而且 FreeBSD ports 裡
有 `py311-uvloop`（見 §3.2），代表有人真的在維護它。

❓ **未查證**：我沒有辦法確認 uvloop 在 FreeBSD 上是否有**執行期**的行為差異
（例如某些 libuv 功能在 kqueue 後端上的邊角）。**但這件事對我們不重要**——§3.5
的建議是根本不要裝它。

---

## 3. 兩條取得相依套件的路線

**這是最可能卡關的地方。** Linux 有 manylinux wheel，`pip install` 幾乎不會編譯任何
東西；**FreeBSD 沒有對應的 wheel 標籤**，所以 `pip install` 會退回去下載 sdist 並
**從原始碼編譯**。上面那張表就是「會編譯些什麼」的完整清單。

📄 這一點有旁證：pydantic-core 的 GitHub 上有一個標題就叫
「Pre-build wheels not available for FreeBSD and Cygwin」的 issue（#773），
內容正是「FreeBSD 使用者 `pip install pydantic` 會失敗」。

### 3.1 路線 A：用 FreeBSD 的 `pkg`

FreeBSD 的 ports/pkg 裡**這個專案要的東西幾乎全都有**。
📄 我用 FreshPorts 逐一查證了下面這些 port 存在：

| port | 對應套件 |
|---|---|
| `www/py-fastapi` | fastapi |
| `www/py-uvicorn` | uvicorn |
| `databases/py-sqlmodel` | sqlmodel |
| `math/py-sympy` | sympy |
| `devel/py-pydantic-core` | pydantic-core（**Rust 那一個，已經有人幫你編好了**） |
| `security/py-argon2-cffi` + `security/py-argon2-cffi-bindings` | argon2-cffi |
| `security/py-itsdangerous` | itsdangerous |
| `www/py-python-multipart` | python-multipart |

❓ **未查證的兩件事，安裝前先用 `pkg search` 確認名稱**：

- **jinja2 的 port 路徑**（很可能是 `devel/py-Jinja2`，但我沒有查證，
  而且 FreeBSD 的 port 名稱有大小寫）——`pkg search jinja2`。
- **pydantic 的 port 名稱**。FreeBSD 為了同時保留 v1 與 v2，pydantic v2 的 port
  很可能叫 **`py311-pydantic2`** 而不是 `py311-pydantic`（我看到 ports 樹裡有
  一個 `devel/py-pydantic2` 的 commit）。本專案要的是 **v2**（`pydantic>=2.7`）。
  `pkg search pydantic` 之後挑對的那一個。**這一項裝錯會是最難查的錯誤**：
  裝到 v1 的話 FastAPI 會用完全不同的程式路徑，症狀不會是「找不到套件」。
- `www/py-httptools`、`devel/py-uvloop`、`devel/py-watchfiles`（`uvicorn[standard]`
  的三個）在 ports 裡存在——📄 它們出現在別人記錄的 FreeBSD 相依清單裡，
  但我沒有逐一查證 port 路徑。§3.5 建議不要裝它們。

📄 FreeBSD 14 與 15 的**預設 Python 是 3.11**（amd64／aarch64／armv7），
所以套件名稱前綴是 `py311-`。本專案要求 `python >= 3.10`（PLAN 附錄 B），3.11 符合。

📄 **一個很好的數據點**：`py311-sympy` 目前的版本是 **1.14.0**，
而 `requirements.txt` 鎖的是 `sympy==1.14.*`——**剛好對得上**。
這件事比看起來重要：SymPy 是本專案唯一鎖死版本的相依（`dsolve` 的輸出形式
會隨版本改變，逐步解答的字串比對會因此壞掉），如果 pkg 給的是 1.13 或 1.15，
路線 A 就直接不成立。

**代價：版本被 pkg 鎖住。**
❓ **未查證**：除了 sympy 之外，我**沒有辦法**確認 pkg 裡其他套件的實際版本
是否滿足 `requirements.txt` 的下限（`fastapi>=0.115`、`sqlmodel>=0.0.22`、
`pydantic>=2.7`、`argon2-cffi>=23.1`）。裝完之後**第一件事**就是驗：

```sh
pkg info | grep -E 'py311-(fastapi|uvicorn|sqlmodel|sympy|pydantic|argon2|jinja2|itsdangerous|multipart)'
```

然後跑一次 `pytest`（§7 第 6 步）。**測試綠燈就是版本合用的證明**——
這個專案有 343 項測試，其中 91 項在驗 SymPy 的輸出，那正是版本最敏感的地方。

### 3.2 路線 B：venv + pip 自行編譯

```sh
pkg install python311 py311-pip rust pkgconf libffi gmake
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt      # 會編譯 §2 表裡標「否」的每一個
```

**代價：編譯時間與工具鏈。**
❓ **未查證**：我沒有辦法給出 FreeBSD 上的實際編譯時間。可以確定的是
**Rust 那兩個（pydantic-core、watchfiles）是大宗**——它們在任何平台上都是分鐘級的，
而 `lang/rust` 這個相依本身在磁碟上就是 GB 級的。

**好處**：版本完全照 `requirements.txt`，與你在 Windows 上測試的那一份**一模一樣**。

### 3.3 路線 C：混合（**建議**）

用 pkg 裝**需要編譯的**，用 pip 裝**純 Python 的**：

```sh
pkg install python311 py311-pip py311-pydantic-core py311-argon2-cffi py311-sqlite3
python3.11 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -r requirements-freebsd.txt   # 見 §3.5
```

`--system-site-packages` 讓 venv 看得到 pkg 裝在
`/usr/local/lib/python3.11/site-packages` 底下的東西。這樣：

- **Rust 與 C 的部分由 FreeBSD 的 package builder 負責**，你的機器上不需要裝 Rust。
- **純 Python 的部分（含 sympy 這個版本敏感的）由 pip 精確控制版本。**

📄 **這條路線我沒有實跑過，而且它有一個已知的粗糙處**：`--system-site-packages`
的 venv 裡，pip 有時候會認為某個套件「已經裝好了」而跳過它，即使系統那一份版本
不符。遇到的時候用 `pip install --ignore-installed <套件>` 處理，或退回路線 B。

### 3.4 建議

**先試路線 A（全部用 pkg），跑 `pytest`，綠燈就收工。**

理由是這個系統的相依清單短、而且沒有一個是冷門套件；FreeBSD ports 裡全都有人維護，
而「有人維護」在一台要撐一整個學期的機器上，比「版本號完全一致」值錢——
安全性更新會跟著 `pkg upgrade` 進來，不必你自己盯 PyPI。

**測試紅燈才往下走**：紅在 SymPy 相關的項目 → 路線 C（用 pip 鎖 sympy）；
紅在別的地方 → 路線 B。

### 3.5 一份 FreeBSD 專用的 requirements（建議新增）

不論走哪條路線，**在 FreeBSD 上都建議把 `uvicorn[standard]` 換成 `uvicorn`**：

```
# requirements-freebsd.txt —— 與 requirements.txt 只差一行
fastapi>=0.115,<1.0
uvicorn>=0.30,<1.0          # ← 不帶 [standard]
sqlmodel>=0.0.22,<0.1
jinja2>=3.1,<4.0
itsdangerous>=2.2,<3.0
python-multipart>=0.0.9
argon2-cffi>=23.1,<26.0
sympy==1.14.*
pydantic>=2.7,<3.0
```

`[standard]` 帶進來的是 uvloop（C + libuv）、httptools（C）、watchfiles（Rust）。
拿掉它們：

- **watchfiles 只有 `--reload` 用得到**，正式部署本來就不該開 `--reload`（§5.3）。
- **uvloop 與 httptools 換來的是每秒幾萬個請求等級的差異**，而這個系統的規模假設是
  「60–150 人、尖峰同時在線 30 人」（PLAN §0），單一請求的成本由 SymPy 的
  約 0.1 秒 CPU 主導。**你量不出差別。**
- 換到的是：少三個編譯目標、少一個 Rust 工具鏈、少三個日後可能編不過的東西。

> ⚠️ 這一段是**建議**，不是已知的必要。如果路線 A 的 `py311-uvicorn` 自動把
> `py311-uvloop` 也裝進來了，那也沒關係——它裝得起來就代表它編得過。

---

## 4. 對學生開放的必要條件：HTTPS

**這不是加分項，是硬性前提**（PLAN.md §4.4 第 3 點）。系統會在登入表單上傳輸密碼，
而學生很可能重用密碼——沒有 HTTPS，那些密碼就是在校園網路上以明文傳輸。

還有一個更技術性的理由：`app/config.py` 的 `COOKIE_SECURE` 要設成 `1`，
session cookie 才會帶 `Secure` 屬性。而 `Secure` cookie 在 HTTP 上根本送不出去，
**所以「先用 HTTP 上線、之後再補 HTTPS」在實作上會直接壞掉登入**，不是妥協的問題。

### 4.1 先確認一件事：那個固定 IP 是不是公開可路由的

這決定了下面三條路裡走哪一條，而且**只有你查得到**：

```sh
# 在那台機器上
ifconfig | grep 'inet '
```

- 位址落在 `10.x.x.x`、`172.16–31.x.x`、`192.168.x.x` → **校內私有 IP**，
  外面連不進來，Let's Encrypt 的驗證也打不到 → 走 §4.4。
- 其他（例如 `140.122.x.x` 這類學術網段） → **公開 IP**，§4.2 與 §4.3 都可行。

### 4.2 情境一：有網域名稱（**最省事，優先爭取這個**）

跟系上或計中要一個 `something.ntnu.edu.tw` 的 A 記錄指到那台機器。有了網域，
**Caddy 會自動把 HTTPS 整件事做完**——申請、安裝、續期，你一行設定都不用寫：

```
# /usr/local/etc/caddy/Caddyfile
engmath.ntnu.edu.tw {
    reverse_proxy 127.0.0.1:8000
}
```

📄 Caddy 在 FreeBSD 的 ports 裡有（`www/caddy`），啟用方式是
`sysrc caddy_enable=YES` 加上 `sysrc caddy_cert_email=你的信箱`，然後
`service caddy start`。

**前提**：Let's Encrypt 的 HTTP-01 驗證需要從外部連得到這台機器的 **80 埠**，
TLS-ALPN-01 則需要 **443 埠**。兩個都被防火牆擋住的話，就要改用 DNS-01
（需要能寫 DNS 記錄的 API 權限，通常在計中手上）。

### 4.3 情境二：只有 IP，沒有網域

**這條路在 2025 年之前是死的，現在活了。** 📄

Let's Encrypt 在 2025-07-01 簽出第一張 IP 位址憑證，並在 **2026-01-15 宣布
6 天期憑證與 IP 位址憑證正式進入一般可用（GA）**。做法是在 ACME 用戶端選
`shortlived` 這個憑證 profile。

**三個必須知道的限制：**

1. **IP 憑證只發給 `shortlived` profile，效期約 6 天（160 小時）。**
   這代表**自動續期不是「最好有」，是「不做就會斷線」**——一週斷一次。
   Caddy 這類自己管憑證的伺服器沒問題；手動跑 certbot 的話，一定要排程。
2. **那個 IP 必須是公開可路由、而且驗證期間從外面連得到的。** 私有 IP 不可能。
3. ❓ **未查證：Caddy 對「IP 位址 + shortlived profile」的支援程度。**
   我查到 Caddy/CertMagic/ACMEz 已經支援 ACME 的 profile 機制（那是 6 天憑證的
   前提），也查到 Caddy 專案裡有一個標題就叫「Unable to issue IP address
   certificate with Let's Encrypt `shortlived` ACME profile」的 issue（#7399）。
   **我無法確認你要用的那個版本現在能不能直接做到這件事。**
   請在動手前先在 Caddy 的文件與 issue 追蹤器上確認一次。

> **老實說**：如果爭取一個網域名稱只要寄一封信給計中，那就寄那封信。
> 用 IP 憑證省下的是一次行政溝通，換來的是一個一週到期一次、
> 而且工具鏈支援度我查不清楚的東西。

### 4.4 情境三：私有 IP，或防火牆擋住 80／443

Let's Encrypt 在這裡幫不上忙（它必須從公網驗證你的控制權）。兩個選項：

- **跟計中要一張校內 CA 或商業 CA 的憑證。** 很多學校的計中有這個服務。
  這是最乾淨的解。
- **自簽憑證。** 技術上可行，但**學生每次都會看到瀏覽器的紅色警告頁**，
  而這個系統對學生的唯一一句安全告誡是「這不是學校官方系統，把它當成公開場合」
  （`app/templates/_about.html`，v0.16 起在登入頁上）。
  **教學生按過瀏覽器的安全警告，會直接抵銷那句話。**
  我不建議。

### 4.5 校內防火牆與資安檢查

> **v0.19（D42）**：老師已經決定**只開放校內 IP 連線**，設定與驗收見 **§5.8**。
> 這對下面這一節是好消息——「開放對外服務要報備」那一題的答案從
> 「對全世界開 443」變成「只對校內開，校外要走學校自己的 VPN」，
> 而後者在多數學校是明顯比較好過的一個答案。⚠️ **但不要因此以為不用報備**：
> 服務仍然在校園網路上，仍然有一個對外的 443 埠（§5.8.2 說明了為什麼
> 那個埠不能用 pf 關掉）。

❓ **未查證：NTNU 的實際流程我不知道。** 但下面這幾件事在多數學校都會被問到，
先準備好會省很多來回：

- **開放對外服務通常要報備。** 至少要說明：服務用途、開哪些埠、誰負責、
  出事怎麼聯絡。
- **會被問「有沒有蒐集個資」。** 這一題你的答案很好，而且**已經寫好了**：
  資料表只有兩張、欄位就那幾個，個資告知與實際儲存的欄位是**一字對應**且有測試
  盯著（PLAN.md §4.4、`tests/test_web.py::test_notice_matches_the_fields_actually_stored`）。
  把 PLAN §4.4 印出來就是現成的說明文件。
- **會被問「密碼怎麼存」。** argon2id，不存明碼，有一項測試會掃過整個 DB 檔案
  確認這件事。
- **可能會被要求做弱點掃描。** 這個系統的攻擊面很小（沒有檔案上傳、沒有
  SQL 字串拼接、沒有執行任何不可信輸入——v0.7 之後連唯一那個都拆掉了），
  但掃描器一定會抓到「HTTP 沒有轉 HTTPS」與「缺少某些安全標頭」。
  前者由 §4.2 解決，後者可以在 Caddy 加幾行 `header` 指令。

---

## 5. 長期運行

### 5.1 專用使用者與檔案權限

**不要用 root 跑，也不要用你自己的帳號跑。** 📄

```sh
pw groupadd engmath
pw useradd -n engmath -g engmath -s /usr/sbin/nologin -d /nonexistent \
   -c "Engineering Mathematics Practice service account"
```

程式與資料的位置建議：

```
/usr/local/www/engmath-practice/     程式碼（git clone 來的）  root:wheel  0755
/var/db/engmath/practice.db          資料庫                    engmath:engmath 0600
/var/log/engmath/                    log                        engmath:engmath 0750
```

**把資料庫放在程式碼資料夾外面**，用環境變數指過去：

```sh
export PRACTICE_DB=/var/db/engmath/practice.db
```

理由有兩個：（1）`practice.db` 裡有**兩組共用帳號的密碼雜湊**，它不該待在一個
「將來可能被 `git clean` 或反向代理不小心 serve 出去」的目錄裡
（⚠️ v0.15 這裡原文寫的是「學號明文與密碼雜湊」——**學號那半已隨 D35 消失**，
所以這條理由變弱了，但沒有消失：密碼雜湊仍然不該給人拿走）；
（2）升級時 `git pull` 不會碰到它。

`init_db()` 每次啟動都會嘗試 `chmod 600`，**在 FreeBSD 上這會真的生效**
（Windows 上形同虛設）。但 chmod 只管檔案本身，`/var/db/engmath/` 這個目錄的
權限要你自己設：

```sh
install -d -o engmath -g engmath -m 0700 /var/db/engmath
```

> ⚠️ **WAL 模式會產生 `practice.db-wal` 與 `practice.db-shm` 兩個附屬檔**，
> 而 `init_db()` **只 chmod 主檔**。目錄權限設成 0700 是唯一會照顧到那兩個檔的做法。

### 5.2 rc.d 服務腳本

📄 **依文件推論，我沒有在 FreeBSD 上跑過這個腳本。** 請把它當草稿而不是成品，
第一次啟動時對著 §8 的清單逐項確認。

> ⚠️ **v0.19：這份草稿裡有兩個 bug，寫 `FREEBSD-HOMELAB.md` 的 rc.d 那一節時發現的。
> 下面的版本已經改掉了，兩個都值得單獨記，因為它們的症狀都不是「壞掉」。**
>
> 1. **`engmath_user` 定義了卻沒有傳給 `daemon`** ——**服務會以 root 執行**。
>    症狀是「一切正常」：服務起得來、網頁打得開、資料庫寫得進去。
>    唯一看得出來的地方是 `ps -o user`，而沒有人會去看。修法是 `daemon -u`。
> 2. **`procname` 指向 python，但 `-P` 寫進 pidfile 的是 `daemon(8)` 自己的 pid。**
>    📄 `daemon(8)` 的 `-P` 是**監督行程**的 pidfile（`-p` 才是子行程的），
>    而 `-r`（掛掉自動重啟）之下子行程的 pid 會變，所以**要追蹤的本來就是監督行程**。
>    但 `rc.subr` 會拿 `procname` 去核對那個 pid 的執行檔——對不上的症狀是
>    **`service status` 說沒在跑、`service stop` 停不掉，而服務其實好好地跑著**。
>    修法是把 `procname` 改成 `/usr/sbin/daemon`。
>
> **家用區網那一份（`FREEBSD-HOMELAB.md` §5）有一組專門用來驗這兩件事的指令**，
> 而且那是這兩項少數在家裡就驗得完的東西。

存成 `/usr/local/etc/rc.d/engmath`，`chmod 555`：

```sh
#!/bin/sh
#
# PROVIDE: engmath
# REQUIRE: LOGIN
# KEYWORD: shutdown
#
# 在 /etc/rc.conf 裡：
#   engmath_enable="YES"
#   engmath_dir="/usr/local/www/engmath-practice"
#   engmath_db="/var/db/engmath/practice.db"
#   engmath_secret_file="/usr/local/etc/engmath/session_secret"

. /etc/rc.subr

name=engmath
rcvar=engmath_enable

load_rc_config $name

: ${engmath_enable:="NO"}
: ${engmath_user:="engmath"}
: ${engmath_dir:="/usr/local/www/engmath-practice"}
: ${engmath_db:="/var/db/engmath/practice.db"}
: ${engmath_secret_file:="/usr/local/etc/engmath/session_secret"}
: ${engmath_bind:="127.0.0.1"}
: ${engmath_port:="8000"}
: ${engmath_log:="/var/log/engmath/app.log"}

pidfile="/var/run/${name}.pid"
# ⚠️ 這裡是 daemon(8)，不是 python：`-P` 寫進 pidfile 的是**監督行程**的 pid。
#    寫成 python 的話 `service status`／`stop` 會對不上（v0.19 修）。
procname="/usr/sbin/daemon"

command="/usr/sbin/daemon"
command_args="-f -o ${engmath_log} -H -P ${pidfile} -r -u ${engmath_user} \
    ${engmath_dir}/.venv/bin/uvicorn app.main:app \
    --host ${engmath_bind} --port ${engmath_port} \
    --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1"

start_precmd="${name}_precmd"

engmath_precmd()
{
    # SESSION_SECRET 放在一個 0400 的檔案裡，不寫進 rc.conf
    # （rc.conf 是 0644，全世界讀得到）。
    if [ ! -r "${engmath_secret_file}" ]; then
        err 1 "讀不到 ${engmath_secret_file}。請先產生：
  install -d -m 0700 /usr/local/etc/engmath
  python3.11 -c 'import secrets;print(secrets.token_hex(32))' > ${engmath_secret_file}
  chmod 0400 ${engmath_secret_file}; chown ${engmath_user} ${engmath_secret_file}"
    fi

    export SESSION_SECRET="$(cat ${engmath_secret_file})"
    export PRACTICE_DB="${engmath_db}"
    export COOKIE_SECURE=1
    export APP_LOG_LEVEL="${engmath_log_level:-INFO}"

    install -d -o "${engmath_user}" -g "${engmath_user}" -m 0750 "$(dirname ${engmath_log})"
    cd "${engmath_dir}" || err 1 "進不去 ${engmath_dir}"
}

run_rc_command "$1"
```

啟用：

```sh
sysrc engmath_enable=YES
service engmath start
service engmath status
```

**這個腳本裡有八個刻意的決定**，每一個都對應這個專案的一條硬規則
（前三個是 v0.19 補上的，見上面那個警示框）：

1. **`-u ${engmath_user}`（v0.19 修）**：沒有它，服務**以 root 執行**——
   而症狀是「一切正常」。
2. **`procname="/usr/sbin/daemon"`（v0.19 修）**：`-P` 寫進 pidfile 的是**監督行程**
   的 pid，不是 python 的。寫錯的症狀是 `service status`／`stop` 對不上，
   而服務其實好好地跑著。
3. **`-H`（v0.19 新增）**：📄 `daemon(8)` 收到 SIGHUP 時會關掉並重開 `-o` 指定的
   輸出檔，這正是 newsyslog 輪替需要的（§5.4）。⚠️ 用了 `-H`，`-o` 就**必須**是絕對路徑。
4. **`--host 127.0.0.1`**：uvicorn **只監聽本機**，對外由反向代理負責（§5.3）。
5. **`--workers 1`**：⚠️ **不可以改大。** `app/security.py` 的 `RateLimiter` 是
   **單一行程的記憶體計數器**（PLAN §4.3 寫明了這個前提）。開兩個 worker，
   登入速率限制就等於放寬一倍，而且**沒有任何東西會報錯**——它會安靜地失效。
   要多行程就得先把限制換成 Redis 或 DB 計數表。
6. **`COOKIE_SECURE=1`**：正式環境必設，否則 session cookie 不帶 `Secure`。
7. **`SESSION_SECRET` 從 0400 的檔案讀，不寫進 `rc.conf`**：`rc.conf` 是 0644。
   這把金鑰換掉會讓所有人登出（可接受），但外洩會讓人可以偽造 session（不可接受）。
8. **`daemon -r`**：行程掛掉自動重啟。`-P` 寫 pidfile 讓 `service status` 有意義。

### 5.3 為什麼 uvicorn 不該直接對外

**不該。** 五個理由，由重到輕：

1. **它沒有 TLS 終結。** uvicorn 可以吃 `--ssl-keyfile`，但那樣憑證的**續期**就變成
   你的事——而 §4.3 的 IP 憑證是六天一期。Caddy 自己管憑證，這件事就消失了。
2. **它不擋慢速攻擊。** slowloris 這類「連上來就不說話」的連線會佔住 worker，
   而我們只有一個 worker。nginx／Caddy 有連線逾時與緩衝，uvicorn 沒有。
3. **靜態檔案。** KaTeX 的字型有 20 個 woff2，加上 fft.js、htmx、範例音檔
   （約 510 KB）。這些讓反向代理來發（附快取標頭）比讓 Python 發合適得多。
4. **要重啟 app 的時候，代理還在。** 學生看到的是短暫的 502，而不是
   「連線被拒絕」。
5. **（v0.19，D42）校內 IP 的允許清單也在這一層。** 它不能做在應用層（§5.8.3），
   也不該做在 pf（§5.8.2）——代理是唯一同時做得到「擋得住」與「擋的時候
   還能回一頁說明」的地方。

> 📄 uvicorn 官方部署文件自己也是這個立場（「run behind a reverse proxy」）。

**選 Caddy 還是 nginx？** 這台機器上**選 Caddy**：自動 HTTPS 是它唯一但決定性的
優勢，而你要的正是「不必記得續期」。nginx 更快、設定更彈性，但這個系統的流量
用不到那些，而 `certbot` + cron 是一組要自己維護的東西。

### 5.4 log 輪替

FreeBSD 用 `newsyslog(8)`，不是 logrotate。📄
在 `/usr/local/etc/newsyslog.conf.d/engmath.conf`：

```
# logfilename          [owner:group]    mode count size(KB) when  flags [pidfile]
/var/log/engmath/app.log  engmath:engmath 640  7     1000     *     JC   /var/run/engmath.pid
```

`J` = bzip2 壓縮、`C` = 檔案不存在就建。**訊號欄留空 = 預設的 SIGHUP。**

> ⚠️ **v0.19 修正**：這一行原本在最後寫著 `30`（`SIGUSR1`），那是錯的。
> 📄 `daemon(8)` 的 `-H` 監聽的是 **SIGHUP**——收到就把 `-o` 的輸出檔關掉再重開，
> 而那正是為了 newsyslog 這類輪替機制設計的。`-H` 已經加進 §5.2 的腳本。
> 送 SIGUSR1 給 `daemon(8)` 的結果我沒有查證，但**它不會是「重開輸出檔」**。

⚠️ **v0.19：這個問號有答案了，但仍然沒有實測。** 原文寫著「輪替時 `daemon` 會不會
正確重開檔案，我不確定」——📄 **`daemon(8)` 有 `-H` 這個旗標，功能就是
「收到 SIGHUP 時關閉並重開 `output_file`，以便與 newsyslog 這類輪替機制搭配」**，
而 §5.2 的腳本已經加上它。**但這仍然是「依文件推論」而不是「已驗證」**——
`FREEBSD-HOMELAB.md` §6 的檢查表裡有一項就是在家裡手動 `newsyslog -F` 一次，
然後確認新的 `app.log` 有長大。**那是這件事第一次會被真的跑過。**
如果輪替之後 log 還是停了，最省事的修法仍然是改用 syslog
（`daemon -S -T engmath`），讓 syslogd 去處理輪替。

> ⚠️ **log 裡不得出現密碼或密碼雜湊**（專案硬規則 #2），也**不得出現用戶端 IP**
> （v0.16 的 D38，見 §5.7）。程式這一側已經守住了，但 log 檔的權限仍然要設 640。
> ⚠️ v0.15 這一句原文寫的是「裡面有學號與 IP」——**兩者現在都沒有了**
> （學號隨 D35 消失，IP 隨 D38 消失）。

### 5.5 備份

**不要用 `cp`。** WAL 模式下，`practice.db` 隨時可能有一段未合併的交易在
`practice.db-wal` 裡；直接複製主檔會抄到一個不一致的狀態。用 SQLite 自己的
備份指令：

```sh
pkg install sqlite3
```

`/usr/local/etc/engmath/backup.sh`（`chmod 700`，owner root）：

```sh
#!/bin/sh
set -eu
DB=/var/db/engmath/practice.db
DEST=/var/backups/engmath
STAMP=$(date +%Y%m%d-%H%M)
install -d -m 0700 "$DEST"

# .backup 是線上備份：伺服器照跑，抄出來的一定是一致的快照
/usr/local/bin/sqlite3 "$DB" ".backup '$DEST/practice-$STAMP.db'"
chmod 600 "$DEST/practice-$STAMP.db"

# 備份檔與正本一樣含兩組共用帳號的密碼雜湊 —— 加密再落地
# （v0.15 這裡寫的是「學號與密碼雜湊」；學號已隨 D35 消失，加密的理由縮小但仍成立）
# pkg install age;  age -r <你的公鑰> -o "$DEST/practice-$STAMP.db.age" "$DEST/practice-$STAMP.db"

# 只留 14 份
ls -1t "$DEST"/practice-*.db | tail -n +15 | xargs -r rm -f
```

排程（`crontab -e`，以 root）：

```cron
17 3 * * * /usr/local/etc/engmath/backup.sh
```

> ⚠️ **v0.16（D35）：備份檔不再含個資，這一段的義務消失了。**
> 原文是「備份檔含個資，保存期限也算在 §4.4 裡，學期結束去識別化時備份要一起
> 處理」——`student_no` 沒有了，§4.4 整節作廢，去識別化腳本連同 PLAN §7 #39
> 一起結案。**剩下的建議是純粹的衛生**：備份裡有兩組帳號的密碼雜湊，
> 加密仍然值得，而且它換一次密碼就作廢。

📄 **如果根檔案系統是 ZFS**，另一個更省事的做法是 `zfs snapshot` + `zfs send`。
但 ⚠️ 快照抓到的是「當下的 WAL 狀態」，還原後 SQLite 會自己做 recovery，
一致性沒問題，但那**不能取代** `.backup`——快照與正本在同一顆磁碟上，
磁碟壞了兩個一起沒。兩個都做最好。

### 5.6 監控

`/healthz` 很便宜（只證明行程活著、路由掛得起來），可以讓監控每分鐘打一次。
最土砲但有效的做法是一行 cron：

```cron
*/5 * * * * fetch -qo /dev/null http://127.0.0.1:8000/healthz || service engmath restart
```

📄 ⚠️ 這種「打不通就重啟」的腳本會掩蓋問題（規則 4 的精神：不要靜默）。
真的要用的話至少讓它同時 `logger -t engmath "healthz 失敗，已重啟"`，
這樣 `/var/log/messages` 裡會留下痕跡。

### 5.7 ⚠️ 反向代理的存取紀錄：把 IP 拿掉（v0.16，PLAN.md D38）

> **這一節是 D38 的另外一半，不是補充說明。**
>
> 老師的指定是「存取紀錄只記 IP 以外的其他欄位」。應用程式那一側已經做完了
> （不讀 `request.client`、把 uvicorn 的存取紀錄整個接管掉，五項測試盯著），
> **但 Caddy 與 nginx 的預設存取紀錄都含來源 IP，而那一層在我們的行程外面。**
>
> 失效的樣子是這樣的：一切正常運作，應用程式的 log 乾乾淨淨，
> `/var/log/caddy/engmath.log` 裡每一行都有一個學生的 IP。
> **沒有錯誤訊息，沒有測試會紅，而且你不會想到要去看。**
> 這正是規則 4 說的那種失敗，只是它發生在我們管不到的地方。

#### 兩個選項，先講建議

**建議選 (A)：整個關掉。** 這台機器上的存取紀錄能回答的問題，
應用程式的 `app.access` 已經全部回答了（方法、路徑、狀態碼、耗時）。
代理層再記一份的價值只剩「TLS 交握失敗」之類的東西，而那會出現在 error log 裡。

```caddyfile
# /usr/local/etc/caddy/Caddyfile
engmath.ntnu.edu.tw {
    reverse_proxy 127.0.0.1:8000

    # 存取紀錄整個關掉。錯誤仍然會記（errors 是另一條路徑）。
    log {
        output discard
    }
}
```

**選項 (B)：留著紀錄，但把 IP 欄位刪掉。** 如果你想保留代理層的紀錄
（例如要看有沒有人在掃網址），Caddy 有一個 `filter` 編碼器可以逐欄處理：

```caddyfile
engmath.ntnu.edu.tw {
    reverse_proxy 127.0.0.1:8000

    log {
        output file /var/log/engmath/caddy-access.log {
            roll_size 10MiB
            roll_keep 5
        }
        format filter {
            wrap console
            fields {
                request>remote_ip           delete
                request>client_ip           delete
                request>remote_port         delete
                request>headers>X-Forwarded-For delete
                request>headers>Cookie      delete
            }
        }
    }
}
```

📄 **這段語法來自 Caddy 官方文件的 `filter` 編碼器，我沒有跑過**
（沙箱裡沒有 Caddy，見 §0 與 §8 第 12 項）。三件要注意的事：

- `remote_ip` 與 `client_ip` **是兩個不同的欄位**（後者是信任代理標頭之後
  算出來的那個）。只刪一個等於沒刪。
- `request>headers>Cookie` 一併刪掉：那裡面有 session cookie。它不是 IP，
  但它比 IP 更能把兩次請求綁在一起，而 D36 說紀錄不得有指得到個人的東西。
- **`format filter` 的欄位名稱在 Caddy 版本之間變過。** 寫錯的症狀是
  「設定載入成功、log 照樣有 IP」——所以**設定完一定要用眼睛確認一次**，見下面。

#### nginx 的版本（如果你最後沒有用 Caddy）

nginx 沒有「刪一個欄位」的機制，但它的 `log_format` 本來就是自己拼的，
所以更簡單——**不要寫 `$remote_addr` 就好**：

```nginx
# 關掉：
access_log off;

# 或者自訂一個不含來源的格式：
log_format noip '$time_local "$request" $status $body_bytes_sent $request_time';
access_log /var/log/engmath/nginx-access.log noip;
```

⚠️ nginx 有兩個陷阱：**（1）`access_log off;` 要寫在對的 `server`／`location`
區塊裡**，寫在 `http` 層而某個 `location` 又自己開了一份的話，那一份還在。
**（2）error log 也有 IP**，而且它的格式**不可自訂**——只能靠調高
`error_log ... crit;` 的等級來減少行數，或整個導到 `/dev/null`。
這是選 Caddy 的另一個理由。

#### 唯一的驗收方式：用眼睛看

這一層**沒有辦法寫測試**（它不在我們的行程裡，也不在這個 repo 裡）。
所以部署完成之後，做一次這件事，然後就可以忘記它：

```sh
# 從別台機器打幾個請求
fetch -qo /dev/null https://engmath.ntnu.edu.tw/login

# 然後在伺服器上看
tail -n 20 /var/log/engmath/caddy-access.log
grep -E '[0-9]{1,3}(\.[0-9]{1,3}){3}' /var/log/engmath/caddy-access.log   # 應該沒有東西
```

`grep` 有東西就代表沒設好。**這是 PLAN §7 #40，在你做完這一步之前不算結案。**

#### 順帶一提：`X-Forwarded-For` 仍然會被送到應用程式

Caddy 的 `reverse_proxy` 預設會加上 `X-Forwarded-For`。**這不需要處理**——
應用程式**從來不讀那個標頭**（`tests/test_web.py::test_nothing_in_the_app_reads_the_client_address`
掃整個 `app/` 盯著），所以它只是一個到了就被丟掉的字串，不會落地。
寫在這裡是因為看到它會讓人以為有問題。

### 5.8 ⚠️ 只開放校內 IP 連線（v0.19，PLAN.md D42）

> **這一節與 §5.7 是一對，所以它就放在 §5.7 後面。**
>
> §5.7 說的是「代理層**不要記**用戶端 IP」，這一節說的是「代理層**要看一眼**
> 用戶端 IP 才知道要不要放行」。**兩件事正交、可以同時成立**——一個是判斷，
> 一個是儲存——但它們**寫在同一個設定檔裡**，而那正是危險所在：
> 設允許清單的當天，你一定會想「先把 log 打開，看看到底擋掉了誰」。
> 然後就忘了關。**§5.8.6 的驗收步驟因此與 §5.7 是同一個 `grep`。**

#### 5.8.0 這條限制買到的是什麼（以及沒有買到什麼）

**沒有買到**資料的機密性——D35 之後資料庫裡只有兩組共用帳號的 argon2id 雜湊，
加上一批不指向任何人的計數，沒有值得偷的東西。

**買到的是兩件事**：

1. **班級密碼被轉傳這件擋不住的事，影響半徑縮小了。** D35 已經寫明那組密碼一定會
   流出去（LINE 群、共筆、學長姐的筆記），技術上擋不住。加上允許清單之後，
   **一組流到校外的密碼在校園網路以外沒有用**。
2. **整個網際網路的自動化掃描與密碼噴灑消失了。** 這正是本系統的速率限制最不擅長
   應付的東西——D38 之後它是**一個全站計數器**（不是每 IP、不是每帳號），
   面對分散來源的慢速嘗試幾乎沒有效果。

⚠️ **它同時有一個代價，寫在前面而不是藏在後面**：**校外的學生沒有 VPN 就用不了**。
這對住宿生（如果宿舍網路不算校內，見 PLAN §7 #42(c)）與用手機行動網路的人是實質的
不便。這是老師的決定，不是技術上的必然——寫在這裡是因為**被擋的那個學生看到的畫面
（§5.8.4）是這個決定唯一會被人記得的部分**，值得花時間寫好。

#### 5.8.1 做在哪一層：四個選項，選一個、順便開一個

| 層 | 擋得住？ | 擋的時候能說話嗎 | 誰改設定 | 判斷 |
|---|---|---|---|---|
| **校內防火牆**（計中那一層） | ✅ | ❌ 逾時 | **計中** | ❌ **不是不好，是不在你手上**。每改一次網段要開一張單，而 VPN 那一段幾乎確定要試錯（PLAN §7 #41） |
| **`pf`**（FreeBSD 內建） | ✅ | ❌ 逾時 | 你 | ⚠️ **要開，但不要拿它擋 80／443**，理由見 §5.8.2 |
| **反向代理**（Caddy／nginx） | ✅ | ✅ **回一頁說明** | 你 | ✅ **選這一層** |
| **應用層**（FastAPI） | ✅ | ✅ | 你 | ❌ **與 D38 正面衝突**，見 §5.8.3 |

**選反向代理的理由只有一句**：它是唯一同時做得到「擋得住」與「擋的時候還能好好說
一句話」的地方，而且設定檔在你自己手上，改一行 `service caddy reload` 就生效。

#### 5.8.2 ⚠️ 為什麼 `pf` 不能拿來擋 443（這一段是本節最容易出事的地方）

兩個理由，第二個是硬的：

1. **封包被丟掉的人不會看到任何東西。** `block drop` 的結果是連線逾時；
   學生看到的是瀏覽器轉圈轉到放棄，而**逾時長得跟「網站掛了」一模一樣**。
   老師會收到的訊息是「老師系統壞了」，而系統好好的。
   （改成 `block return` 會回 TCP RST，症狀從「轉圈」變成「連線被拒絕」——
   一樣沒有一個字可以解釋原因。）
2. **Let's Encrypt 的憑證會續不到，而且無解。** 📄 LE **不公布驗證來源位址**，
   而且自 2020 年起強制**多視角驗證**（同一次驗證從多個網路位置發出，
   用來防 BGP 劫持）——**所以「把 LE 的 IP 加進允許清單」這個選項不存在**。
   HTTP-01 要打得到 80 埠、TLS-ALPN-01 要打得到 443 埠，pf 擋掉哪一個，
   對應的驗證方式就死掉。而 §4.3 的 IP 憑證是**六天一期**：
   ⚠️ **這不會在部署當天壞，會在第六天壞**，而那時你已經在忙別的事了。

> ⚠️ **一個必須自己確認的細節**：📄 **Caddy 的自動 HTTPS 會在執行期另外開一個 :80
> 的伺服器**來處理 HTTP→HTTPS 轉址與 ACME HTTP-01 挑戰，**那個伺服器不是你寫的
> 站台區塊**——所以站台區塊裡的允許清單**不會**擋到 ACME 挑戰。這是好事
> （憑證照常續期），但它有一個前提：**你沒有自己寫一個 `http://` 或 `:80` 的
> 站台區塊**。寫了就會覆蓋掉自動的那一個，ACME 挑戰就落進你的允許清單裡了。
> **本節的範例刻意不寫 `:80` 區塊。** ❓ 我沒有辦法實測 Caddy 的這個行為，
> 第一次部署後請直接看憑證有沒有續到（`caddy list-certificates` 或看 error log）。

**pf 該做的是另一件事**：把 80／443 以外的東西關掉。這是與允許清單無關、
但同一天該做的事：

```pf
# /etc/pf.conf
#
# 這份設定**刻意不管 80／443 的來源**——校內限制做在 Caddy 那一層（§5.8.1），
# 理由是「被擋的人要看得到一句說明」與「Let's Encrypt 的驗證來源無法列舉」。
# pf 在這裡的職責只有一個：把不該對外開的東西關掉。

ext_if = "em0"                 # ← 換成 ifconfig 看到的那張網卡

# ⚠️ 下面全部是 RFC 5737／RFC 3849 的「文件用」位址，一個真的都沒有。
#    正確清單只有計中／網路中心給得出來（PLAN §7 #42），而且要含 IPv6。
#    **猜一個看起來很像的網段填進去，比留著這個明顯的佔位符危險得多**：
#    猜錯的方向是把全班擋在門外，而那個症狀在你自己的機器上（在校內）看不到。
table <campus> const { 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 }
table <campus6> const { 2001:db8::/32 }

set skip on lo0
scrub in all

block drop in all                       # 預設全關
pass  out all keep state                # 出去的都放行（pkg update、ACME 用得到）

# HTTP／HTTPS：**對全世界開**。校內限制在 Caddy 那一層，見 §5.8.1–§5.8.2。
pass in on $ext_if proto tcp to port { 80, 443 } keep state

# SSH：這一個**才**用 pf 限校內。它沒有「回一頁說明」的需求，
#      而且它正是「不限來源就會被整天掃」的那種服務。
pass in on $ext_if proto tcp from <campus>  to port 22 keep state
pass in on $ext_if inet6 proto tcp from <campus6> to port 22 keep state

# ICMP 留著：不留的話 ping 不到、PMTU 探測也會出問題
pass in inet  proto icmp  all icmp-type { echoreq, unreach, timex }
pass in inet6 proto icmp6 all
```

```sh
pfctl -nf /etc/pf.conf     # ⚠️ 先驗語法，再啟用。改壞了會把自己的 SSH 鎖在外面
sysrc pf_enable=YES
service pf start
pfctl -sr                  # 看實際生效的規則
pfctl -t campus -T show    # 看 table 內容
```

> ⚠️ **改 pf 之前先開第二條 SSH 連線，或到主機前面去。** 這是老話但每年都有人中：
> `pfctl -f` 是立即生效的，規則寫錯 → 你自己也進不去。
> 📄 保險做法是先 `pfctl -e` 之後用 `at now + 10 minutes` 排一個 `pfctl -d`，
> 確認自己還連得上再取消。

#### 5.8.3 ⚠️ 為什麼不做在應用層——這一段是 D42 的核心

在應用層做 IP 過濾，**一定**要讀 `request.client` 或 `X-Forwarded-For` 其中之一。
於是：

**（i）** `tests/test_web.py::test_nothing_in_the_app_reads_the_client_address`
會紅——它掃整個 `app/`，禁止 `request.client`、`scope["client"]`、
`x-forwarded-for`、`x-real-ip`、`client_ip`、`getpeername`。

**（ii）而真正的問題不是它會紅，是紅了以後你會想把它改掉。**
那項測試是 D38 在應用層唯一的**結構性**保證：**應用程式碰不到位址，它就「不可能」
把位址寫進 log 或資料庫**——這是「做不到」，不是「不要做」。為了允許清單開一個洞
之後，往後任何一行「順便記一下是誰被擋了」都不會有任何東西擋它，
而那一行看起來會非常合理。

> **判準與 D33 選 middleware 而不是 `Depends` 完全相同**：
> 一個只靠人記得的守則，等於沒有守則。

**在代理層它為什麼不破壞任何東西**：Caddy 拿 `remote_ip` 比對一次、回放行或回那一頁。
**這個判斷不需要儲存、不需要跨請求關聯、不需要 session**，而位址**一次都沒有跨過
「代理 → 應用程式」那條界線**（`X-Forwarded-For` 照樣會被送過來，但應用程式從來
不讀它，見 §5.7 末段）。

**`_about.html` 那四句話一個字都不必改。** 對學生說的原文是
*It does not **store** your name, your student ID, your IP address* ——動詞是
**store**。「不儲存」與「不看見」從來就不是同一件事：TCP 連線本來就必須知道
對方的位址，否則封包送不回去。這個系統從第一天起就「看得到」IP，
D38 管的一直是它不准落地。

⚠️ **一個誠實的附註（寫下來是因為下一個提議會從這裡開始滑）**：允許清單確實
**改變了匿名集合**——從「網際網路上的任何人」縮成「校園網路或 VPN 上的任何人」。
它不指向任何個人、不被儲存，所以硬規則 3 與 8 都沒有被碰到。
但「順便按網段記一下被擋的次數」**已經越界了**：那是儲存，不是判斷。

#### 5.8.4 設定範例（Caddy——建議用這一份）

```caddyfile
# /usr/local/etc/caddy/Caddyfile
#
# ⚠️ 下面的網段全部是 RFC 5737 的文件用位址，**一個真的都沒有**。
#    正確清單向計中／網路中心索取（PLAN §7 #42），要含 IPv6（RFC 3849 的 2001:db8::/32
#    是這裡的 IPv6 佔位符）。
#    ⚠️ **只填 IPv4 而主機有 AAAA 記錄的話，走 IPv6 的校內學生會被自己的清單擋掉。**

(campus_only) {
    # 用 remote_ip，**不要用 client_ip**。
    # 📄 client_ip 會在設了 trusted_proxies 時改讀 X-Forwarded-For，而那個標頭是
    #    用戶端送來的——Caddy 就是最外層，這裡沒有可信的上游代理，
    #    誤用它等於讓任何人加一個標頭就繞過允許清單。
    @offcampus not remote_ip 192.0.2.0/24 198.51.100.0/24 203.0.113.0/24 2001:db8::/32
    error @offcampus "off campus" 403
}

engmath.ntnu.edu.tw {
    import campus_only

    handle_errors 403 {
        root * /usr/local/www/engmath-blocked
        rewrite * /offcampus.html
        file_server
    }

    reverse_proxy 127.0.0.1:8000

    # §5.7：存取紀錄整個關掉。⚠️ 加了允許清單之後，這一行更容易被人
    #       「暫時」打開來看是誰被擋了。打開之後記得關。
    log {
        output discard
    }
}
```

📄 **這段語法來自 Caddy 官方文件（`error`／`handle_errors`／`remote_ip` matcher／
具名 snippet），我沒有跑過**——沙箱裡沒有 Caddy。三件要注意的事：

- **`import campus_only` 要放在站台區塊的最前面。** Caddyfile 的指令有預設排序，
  但 `error` 與 `reverse_proxy` 的相對順序在同一個區塊裡是靠 `handle`／`route`
  或預設排序決定的。❓ **我無法確認你那個版本的預設排序**，
  如果發現校外還是進得去，用 `route { ... }` 把兩者的順序寫死。
  **驗收方式見 §5.8.6，不要靠讀設定檔判斷。**
- **`handle_errors 403` 會攔截「所有」403**，包括應用程式自己回的那一個
  （`/activity` 對 `class` 帳號回 403，D39）。⚠️ **這是一個真的會發生的誤傷**：
  一個用 `class` 帳號在校內點進 `/activity` 的學生，會看到「請連 VPN」。
  修法是把攔截範圍縮到自己產生的錯誤——用 `{err.message}` 判斷，
  或乾脆改用下面那個更笨但不會誤傷的寫法。
- ⚠️ **`reverse_proxy` 預設不會把後端的 403 交給 `handle_errors`**
  （`handle_errors` 處理的是 Caddy 產生的錯誤，不是後端回應的狀態碼），
  📄 所以上面那個誤傷**可能根本不會發生**。**但「可能」不是「不會」**——
  §5.8.6 的驗收清單裡有一項專門測這個。

**更笨、但不會有上面那個疑慮的寫法**（如果驗收發現誤傷，換成這一份）：

```caddyfile
engmath.ntnu.edu.tw {
    @offcampus not remote_ip 192.0.2.0/24 198.51.100.0/24 203.0.113.0/24 2001:db8::/32

    handle @offcampus {
        root * /usr/local/www/engmath-blocked
        rewrite * /offcampus.html
        file_server {
            status 403
        }
    }

    handle {
        reverse_proxy 127.0.0.1:8000
    }

    log {
        output discard
    }
}
```

`handle` 區塊是互斥的，所以校外的請求**根本不會走到** `reverse_proxy` 那一塊，
而應用程式自己的 403 也不會被碰到。❓ `file_server { status 403 }` 的可用版本我
沒有查證；不支援的話改用 `respond @offcampus <<HTML ... HTML 403`（heredoc，
📄 Caddy 2.7 以後支援）或把整頁塞進一行 `respond` 字串。

#### 5.8.4a 被擋的那一頁（英文，D5）

存成 `/usr/local/www/engmath-blocked/offcampus.html`，`chmod 644`。
**它必須是一個完全靜態、不相依於應用程式的檔案**——被擋的人連不到應用程式，
所以它不能用 `base.html`、不能用 KaTeX、不能用任何 `/static/` 資產。

```html
<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus network required</title>
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         max-width: 34rem; margin: 4rem auto; padding: 0 1.25rem;
         line-height: 1.6; color: #1c1c1c; }
  h1   { font-size: 1.4rem; }
  ol   { padding-left: 1.2rem; }
  .note { color: #555; font-size: .9rem; margin-top: 2rem; }
</style>

<h1>This site is only reachable from the campus network</h1>

<p>
  You are seeing this page because your connection is coming from outside the
  university network. Nothing is wrong with your account or with the site.
</p>

<ol>
  <li>Connect to the university VPN.</li>
  <li>Come back to this address and reload the page.</li>
</ol>

<p>
  If you are already on campus (wired, campus Wi-Fi or eduroam) and still see
  this page, tell your instructor — the list of campus networks may need
  updating.
</p>

<p class="note">
  <!-- ⚠️ 老師要填：學校 VPN 的說明頁網址。留著這一行不填，這一頁就只說了
       「你要用 VPN」而沒說「怎麼用」——那是這一頁最容易失敗的方式。 -->
  VPN instructions: <a href="https://REPLACE-ME.ntnu.edu.tw/vpn">university VPN guide</a>
</p>
```

**三個刻意的決定**：

1. **狀態碼 403，不是 404 也不是 451。** 403 的語意正是「我認得這個請求，
   我拒絕服務它」。404 會讓人以為網址打錯，然後去試別的網址。
2. **不寫「你的 IP 是 x.x.x.x」。** 這在除錯上很方便，而且技術上完全合法
   （沒有儲存）——**但它會讓這一頁看起來像在記錄你**，而這個系統花了整個 v0.16
   在建立相反的印象。要除錯的時候，臨時開 log 比印在學生的畫面上好。
3. **不寫「本站只給修課學生」之類的話。** 不是那個意思，而且不是真的
   （校內任何人都連得進來）。

> ⚠️ **代價要寫明**：校外的人仍然完成得了 TCP 與 TLS 交握——否則沒有辦法用 HTTPS
> 回一頁給他看。**這條限制擋的是「使用這個系統」，不是「碰到這台機器」。**
> 要連碰都碰不到只能用 pf，而那就換回逾時畫面（§5.8.2）。
> **兩者只能挑一個，這裡挑的是「說得清楚」。**

#### 5.8.4b nginx 的版本（如果你最後沒有用 Caddy）

```nginx
# ⚠️ 一樣是 RFC 5737 的佔位符，一個真的都沒有。
geo $off_campus {
    default          1;
    192.0.2.0/24     0;
    198.51.100.0/24  0;
    203.0.113.0/24   0;
    2001:db8::/32    0;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name engmath.ntnu.edu.tw;

    # §5.7：不記 IP。access_log 要寫在**這個** server 區塊裡。
    access_log off;

    # ACME 的 HTTP-01 挑戰走 80 埠的另一個 server 區塊，**那裡不要加這個判斷**
    #（理由同 §5.8.2：LE 的來源位址無法列舉）。
    if ($off_campus) {
        return 403;
    }

    error_page 403 /offcampus.html;
    location = /offcampus.html {
        root /usr/local/www/engmath-blocked;
        internal;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        # ⚠️ 這裡**刻意不設** X-Real-IP／X-Forwarded-For（D38）。
        #    應用程式從來不讀它們，但少送一個就少一個將來被誤用的東西。
    }
}
```

⚠️ nginx 這一份有三個陷阱：

- **`error_page 403` 會攔截後端回的 403**，而應用程式真的會回 403
  （`/activity` 對 `class` 帳號，D39）——**這個誤傷在 nginx 上是確定會發生的**，
  除非加 `proxy_intercept_errors off;`（那是預設值，所以實際上不會；
  ❓ 但你的 nginx 如果在別處開了 `proxy_intercept_errors on`，就會）。
- 用 `allow`／`deny`（ngx_http_access_module）比 `if` 乾淨，但**它們回的 403
  一樣要靠 `error_page` 才有畫面**，而且不能用 `geo` 的變數，網段要逐條列。
  兩種寫法都可以，上面用 `geo` 是因為 IPv6 與 IPv4 可以寫在一起。
- **error log 有 IP 而且格式不可自訂**（§5.7 已經提過）。這是選 Caddy 的另一個理由。

#### 5.8.5 ⚠️ VPN 必須實測，不能用問的（PLAN §7 #41）

**學校 VPN 連進來的來源位址會不會落在允許的校內網段裡，沒有人知道。**
VPN 集中器可能配發一個獨立的網段，也可能就把用戶端放在校內網段裡；兩種設計都常見。

**猜錯的失敗模式特別壞**：如果猜「會落在裡面」而實際不會，一個校外的學生照著
§5.8.4a 那一頁的指示連上了 VPN，**還是**被擋——於是那一頁的每一句話都變成假話，
而他沒有第二個辦法可以試。

⚠️ **這一項不能靠問網路中心「VPN 的網段是多少」來取代。** 那個答案是設定值，
而我們要驗的是**封包到達這台機器時長什麼樣**；中間任何一次 NAT 都會讓兩者不同。

**實測步驟（需要一台在校外網路上的機器，手機開熱點接筆電就夠）**：

```sh
# ── 第 1 步：校外、沒有 VPN ─────────────────────────────────
#   預期：403，而且內容是 offcampus.html
curl -si https://engmath.ntnu.edu.tw/login | head -n 1
curl -s  https://engmath.ntnu.edu.tw/login | grep -c 'Campus network required'
#   ↑ 第一行應該是 HTTP/2 403，第二個指令應該印 1

# ── 第 2 步：連上學校 VPN，同一台機器再來一次 ────────────────
#   預期：200，而且看得到登入頁
curl -si https://engmath.ntnu.edu.tw/login | head -n 1
curl -s  https://engmath.ntnu.edu.tw/login | grep -c 'not an official university system'
#   ↑ 應該是 HTTP/2 200 與 1

# ── 第 3 步：斷開 VPN，確認又被擋回去 ────────────────────────
#   這一步不能省：它證明第 2 步的成功真的來自 VPN，
#   而不是來自「你剛好換到一個本來就被允許的網路」或某一層的快取。
curl -si https://engmath.ntnu.edu.tw/login | head -n 1
```

**三步都對過才算數。**

> **如果第 2 步失敗（連了 VPN 還是 403）**：那就是 VPN 配發了獨立網段。
> 在那台機器上連著 VPN 查一次自己的對外位址（例如 `ifconfig` 看 VPN 介面，
> 或問一個回顯自己 IP 的服務），把那個網段拿去問網路中心
> 「VPN 用戶端的對外網段是哪一段」，然後加進允許清單，**再從第 1 步重跑一次**。
> ⚠️ 不要只加「你那一次拿到的那一個位址」——那是一個位址，不是一個網段，
> 下一個學生會拿到別的。

#### 5.8.6 驗收：三件事，一次做完

**這三項全部只能用眼睛驗，沒有一項寫得出測試**（它們都在我們的行程外面）。

```sh
# ── (1) 校內進得去 ────────────────────────────────────────
#   在校內的機器上
fetch -qo - https://engmath.ntnu.edu.tw/login | grep -c 'not an official university system'

# ── (2) 校外被擋，而且看到的是那一頁不是裸的 403 ──────────
#   在校外的機器上（見 §5.8.5 第 1 步）

# ── (3) ⚠️ 應用程式自己的 403 沒有被誤傷 ───────────────────
#   在校內，用 **class** 帳號登入之後，直接開 /activity。
#   預期：看到「這一頁只給 staff 帳號」（D39），
#   **不是**「Campus network required」。
#   ⚠️ 這一項是 §5.8.4 那兩個 handle_errors 疑慮的唯一驗收方式。

# ── (4) §5.7 沒有被這一輪改動弄壞 ─────────────────────────
#   從別台機器打幾個請求，然後在伺服器上：
grep -rE '[0-9]{1,3}(\.[0-9]{1,3}){3}' /var/log/engmath/ /var/log/caddy/ 2>/dev/null
#   ↑ 應該沒有東西。有東西就是某一份 log 被打開了忘記關。
```

> **(4) 為什麼要重做一次**：因為這一輪你剛剛編輯過 Caddyfile。
> §5.7 的 `log { output discard }` 與這一節的允許清單在同一個檔案裡，
> 而「改 A 的時候順手把 B 註解掉來除錯」是本節最可能的失效方式。
> **PLAN §7 #40 與 #41 兩項在這四步全部做完之前都不算結案。**

---

## 6. 與 Windows 測試部署的差異

`WINDOWS-SETUP.md` 那一份是**測試部署**：只給你自己看、只監聽 127.0.0.1、
沒有 HTTPS、手動啟動。這一份是**要給學生用的**。差異清單：

| 項目 | Windows 測試（`WINDOWS-SETUP.md`） | FreeBSD 正式 |
|---|---|---|
| 監聽位址 | `127.0.0.1`（明文寫著不要改成 `0.0.0.0`） | `127.0.0.1`，**由反向代理對外** |
| HTTPS | 沒有 | **硬性前提**（§4） |
| `COOKIE_SECURE` | `0` | **`1`** |
| 啟動方式 | 手動 `uvicorn --reload` | rc.d + `daemon -r`，開機自動起（§5.2） |
| `--reload` | 開著（改程式即時生效） | **關掉**（它是開發伺服器功能，而且會拉進 watchfiles 這個 Rust 相依） |
| `SESSION_SECRET` | 環境變數，重開就換一把 | 0400 的檔案，**固定不變**（換掉＝全體登出） |
| 資料庫位置 | 專案資料夾內 | `/var/db/engmath/`，程式碼資料夾**外面** |
| 檔案權限 | `chmod 600` 形同虛設 | **真的生效**，另加目錄 0700 |
| 執行身分 | 你自己的帳號 | 專用的 `engmath` 使用者、`nologin` |
| 備份 | 「你記得手動複製」 | `sqlite3 .backup` + cron（§5.5） |
| log | PowerShell 視窗 | `/var/log/engmath/` + newsyslog |
| 相依安裝 | `pip install`，全部有 wheel | 見 §3——**這是最大的差異** |
| 帳號 | `python scripts/create_accounts.py init`，用印出來的密碼登入 | 同一支指令，但**密碼要念給全班聽**（或貼進 Moodle 公告）；`staff` 那一組自己留著 |
| 存取紀錄 | uvicorn 的視窗，`app.access` 一行一個請求 | 同上，**外加反向代理那一層要關掉或濾掉 IP**（§5.7，D38）——這是兩者之間唯一一個「不做就會安靜出錯」的差異 |
| 誰連得進來 | 只有你自己（`127.0.0.1`） | **只有校內網段 + 學校 VPN**（§5.8，D42）。校外看到的是一頁英文說明，不是逾時 |
| 封包過濾 | 沒有 | `pf`：預設全關、SSH 限校內、**80／443 對全世界開**（§5.8.2——擋了它 Let's Encrypt 就續不到憑證） |
| 執行身分 之外的 rc.d 細節 | 不適用 | `daemon -u`（否則跑 root）、`procname` 要是 `/usr/sbin/daemon`（否則 `service status` 對不上）、`-H` 配 newsyslog（§5.2、§5.4，v0.19 修） |

---

## 7. 從零開始的安裝步驟

📄 **整段都是依文件推論，沒有一步是我實跑過的。** 每一步都值得停下來看一眼輸出。

```sh
# ── 1. 基本套件 ──────────────────────────────────────────────
pkg update
pkg install -y git python311 py311-pip py311-sqlite3 sqlite3 caddy

# ── 2. 相依套件（路線 A：全部用 pkg，見 §3.4）────────────────
#   ⚠️ 先確認名稱，尤其 pydantic（v2 的 port 可能叫 py311-pydantic2）
pkg search pydantic
pkg search jinja2
pkg install -y py311-fastapi py311-uvicorn py311-sqlmodel py311-sympy \
               py311-Jinja2 py311-itsdangerous py311-python-multipart \
               py311-argon2-cffi py311-pydantic2
# 驗一下版本（尤其 sympy 必須是 1.14.x、pydantic 必須是 2.x）
pkg info | grep -E 'py311-(fastapi|uvicorn|sqlmodel|sympy|pydantic|argon2|Jinja2)'

# ── 3. 專用使用者與目錄 ──────────────────────────────────────
pw groupadd engmath
pw useradd -n engmath -g engmath -s /usr/sbin/nologin -d /nonexistent \
   -c "Engineering Mathematics Practice"
install -d -o engmath -g engmath -m 0700 /var/db/engmath
install -d -o engmath -g engmath -m 0750 /var/log/engmath
install -d -m 0700 /usr/local/etc/engmath

# ── 4. 程式碼 ────────────────────────────────────────────────
cd /usr/local/www
git clone <你的 repo> engmath-practice
cd engmath-practice

# ── 5. session 金鑰（一次性，不要再換）─────────────────────────
python3.11 -c 'import secrets; print(secrets.token_hex(32))' \
    > /usr/local/etc/engmath/session_secret
chmod 0400 /usr/local/etc/engmath/session_secret
chown engmath /usr/local/etc/engmath/session_secret

# ── 6. 先跑測試（這一步就是「版本合用」的證明）────────────────
pkg install -y py311-pytest py311-httpx node22
python3.11 -m pytest -q
#   預期 343 項全過（沒有 node 的話 93 項會 skip 並印出原因）

# ── 7. 建立兩組共用帳號（v0.16，D35）──────────────────────────
#   沒有名單、沒有對照表檔案：密碼印在終端機上一次而已
env PRACTICE_DB=/var/db/engmath/practice.db \
    python3.11 scripts/create_accounts.py init
chown engmath:engmath /var/db/engmath/practice.db
#   ⚠️ 密碼只印這一次（資料庫裡只有 argon2id 雜湊）。抄下來，
#      然後清掉這個 shell 的捲動紀錄。忘了也沒關係：reset 隨時可以換一組。

# ── 8. rc.d 服務 ─────────────────────────────────────────────
#   把 §5.2 的腳本存成 /usr/local/etc/rc.d/engmath
chmod 555 /usr/local/etc/rc.d/engmath
sysrc engmath_enable=YES
service engmath start
fetch -qo - http://127.0.0.1:8000/healthz    # 應該印出 {"status":"ok"}

# ── 9. 反向代理與 HTTPS（§4）＋ 關掉代理層的 IP 紀錄（§5.7，D38）
#      ＋ 只開放校內 IP（§5.8，D42）──────────────────────────
#   ⚠️ 動手之前先向計中／網路中心要到校內網段清單（含 IPv6！），PLAN §7 #42。
#   /usr/local/etc/caddy/Caddyfile：整份範例見 §5.8.4，重點三行是
#       @offcampus not remote_ip <校內網段…>   # ← 用 remote_ip 不是 client_ip
#       error @offcampus "off campus" 403
#       log { output discard }                 # ← §5.7，這一行不要漏掉
install -d -m 0755 /usr/local/www/engmath-blocked
#   把 §5.8.4a 的 offcampus.html 放進去（⚠️ 裡面有一行 VPN 說明網址要填）
sysrc caddy_enable=YES
sysrc caddy_cert_email=你的信箱@ntnu.edu.tw
service caddy start

# ── 9b. 封包過濾（§5.8.2）────────────────────────────────────
#   ⚠️ pf **不要**擋 80／443：擋了 Let's Encrypt 就驗不到，
#      而 IP 憑證是六天一期——它不會在部署當天壞，會在第六天壞。
pfctl -nf /etc/pf.conf      # 先驗語法。⚠️ 改 pf 前先開第二條 SSH
sysrc pf_enable=YES
service pf start

# ── 10. 備份排程（§5.5）───────────────────────────────────────
#   放好 /usr/local/etc/engmath/backup.sh，chmod 700，然後
crontab -e     # 加上：17 3 * * * /usr/local/etc/engmath/backup.sh
```

**第一次開放給學生之前，用一個測試帳號把整條路徑走一次**：

1. 用瀏覽器連 `https://<你的網址>` → 應該看到登入頁，**網址列是鎖頭不是警告**，
   而且表單下面有那段誠實說明（「not an official university system」、
   「shared by the whole class」）。
2. 用 `class` 的密碼登入 → **直接進到出題頁**（沒有告知頁了，D37）。
3. 出一題 → 按 Show Answer → 按 Show Solution Steps。
4. 打開兩個展示各一次（`/demos`）。
5. 直接在網址列打 `https://<你的網址>/activity` → 應該是 **403**，
   訊息說這一頁只給 staff 帳號（D39）。
6. 登出，改用 `staff` 的密碼登入 → 頁首多一個 **Class activity** → 點進去，
   確認剛剛那幾題**有**出現、而你用 staff 做的事**沒有**混進去
   （頁面底下會寫「N record(s) came from the staff account」）。
7. 直接在網址列打 `/register`、`/consent`、`/account/password` → 三個都應該是 **404**。
8. ⚠️ **最後一步，也是最容易忘記的一步**：`tail` 一下反向代理的存取紀錄，
   確認裡面**沒有任何 IP**（§5.7）。應用程式那一側有測試盯著，代理這一層沒有。
9. **（v0.19，D42）用 `class` 帳號在校內開 `/activity`** → 應該看到「只給 staff」
   （第 5 步已經做過一次），**而不是**「Campus network required」。
   這一項驗的是 `handle_errors` 有沒有誤傷應用程式自己的 403（§5.8.6 第 3 項）。
10. **（v0.19，D42）從校外走一次 §5.8.5 的三步 VPN 實測**：沒 VPN → 那一頁；
    連上 VPN → 進得去；斷開 VPN → 又是那一頁。**三步都對過才算數**（PLAN §7 #41）。
    ⚠️ 這一步需要一台在校外網路上的機器（手機開熱點接筆電就夠），
    **所以它排在最後，但它不是可選的**——沒做過就等於不知道 VPN 那條路通不通，
    而那正是 §5.8.4a 那一頁對學生的唯一承諾。

---

## 8. 我無法驗證的事（第一次安裝時請對著這份清單走）

這一節存在的理由與 PLAN §8.9 相同：**寫下來的落差才是落差，沒寫下來的是謊。**

| # | 事項 | 為什麼我驗不了 | 怎麼確認 |
|---|---|---|---|
| 1 | **這個系統在 FreeBSD 上真的跑得起來** | 沙箱是 Linux | 走完 §7 第 6 步，`pytest` 343 項全綠 |
| 2 | **Python 3.11 跑得起來**（FreeBSD 的預設） | 沙箱只有 3.10，而且我沒有在 3.11 上跑過這個專案 | 同上。專案宣告的下限是 3.10（PLAN 附錄 B），3.11 應該沒問題，但「應該」不是「跑過」 |
| 3 | **pkg 裡各套件的實際版本**是否滿足 `requirements.txt` | 我沒有 FreeBSD 機器可以 `pkg info`。唯一查到的具體版本是 `py311-sympy 1.14.0`（剛好符合鎖定的 `1.14.*`） | `pkg info \| grep py311-` 然後跑測試 |
| 4 | **uvloop／httptools 在 FreeBSD 上編得過、跑得對** | 我只驗了 sdist 的內容（有 FreeBSD 分支、vendor 了 libuv 的 `freebsd.c`／`kqueue.c`） | §3.5 的建議是不要裝它們，這樣這一項就不重要了 |
| 5 | **pip 自行編譯的時間與失敗率**（路線 B） | 沒有 FreeBSD 機器 | 只有在路線 A 失敗時才需要面對 |
| 6 | **§5.2 的 rc.d 腳本正確無誤** | 沒跑過。`daemon(8)` 的旗標組合、`start_precmd` 裡 export 的環境變數會不會傳到 `daemon` 底下的子行程，都是我沒驗證的 | `service engmath start` 之後 `fetch http://127.0.0.1:8000/healthz`；`service engmath status` 要看得到 pid |
| 7 | **newsyslog 輪替之後 log 會不會繼續寫**（§5.4） | 沒跑過。`daemon -o` 開的檔案在被 rename 之後不會自動重開 | 手動 `newsyslog -F` 一次，然後打幾個請求看新的 `app.log` 有沒有長大。停了就改走 syslog |
| 8 | **Caddy 能不能對「IP 位址 + shortlived profile」自動申請憑證**（§4.3） | Let's Encrypt 這一項是 2026-01 才 GA 的，而我查到 Caddy 專案裡有一個相關的未結 issue（#7399） | 動手前先查一次 Caddy 的文件與 issue；或直接爭取一個網域名稱，繞過整個問題 |
| 9 | **那個固定 IP 是不是公開可路由的** | 只有你查得到 | `ifconfig`，見 §4.1 |
| 10 | **NTNU 的防火牆開通與資安檢查流程** | 我不知道，也不打算猜 | 問計中 |
| 11 | **`--system-site-packages` 混合路線（路線 C）** | 沒跑過，而且它有已知的粗糙處（pip 會誤判「已安裝」） | 只有在路線 A 與 B 都不順時才需要 |
| 12 | **⚠️ Caddy 的存取紀錄真的濾掉了 IP**（§5.7，v0.16 的 D38） | 沒有 Caddy 可以跑。`format filter` 與 `delete` 的語法來自 Caddy 官方文件，但**版本之間會變**，而寫錯的症狀是「設定載入成功、log 照樣有 IP」——不會有任何錯誤訊息 | **這是這份清單裡最容易被忘記的一項**，因為它不影響任何功能。部署完成後打幾個請求，然後 `tail /var/log/caddy/engmath.log`，用眼睛確認裡面沒有位址。應用層那五項測試全綠也證明不了這一項——那一層在我們的行程外面 |
| 13 | **⚠️ Caddy 的允許清單真的擋得住**（§5.8.4，D42） | 沒有 Caddy 可以跑。`error` + `handle_errors` + `remote_ip` 的語法來自官方文件；⚠️ 而 `import`／`error`／`reverse_proxy` 在同一個站台區塊裡的**預設排序**我無法確認，寫錯的症狀是「設定載入成功、校外照樣進得去」 | **只能從校外實測**（§5.8.5 第 1 步）。不要靠讀設定檔判斷。發現進得去就改用 §5.8.4 那份 `handle` 互斥的寫法 |
| 14 | **⚠️ 允許清單有沒有誤傷應用程式自己的 403**（`/activity` 對 `class` 帳號，D39） | 沒有 Caddy。📄 文件說 `handle_errors` 處理的是 Caddy 產生的錯誤而非後端回應的狀態碼，所以**推論是不會誤傷**——但「推論不會」不是「驗過不會」 | 校內用 `class` 帳號開 `/activity`，看到的必須是「只給 staff」而不是「Campus network required」（§5.8.6 第 3 項） |
| 15 | **⚠️⚠️ 學校 VPN 的來源位址會不會落在允許的網段裡**（§5.8.5，PLAN §7 #41） | 我不知道，而且**不打算猜**。VPN 集中器可能配發獨立網段，也可能不會，兩種設計都常見 | **這一項是本清單裡唯一一個「猜錯會讓一頁對學生的說明變成假話」的**：學生照著指示連了 VPN 還是被擋。實測三步見 §5.8.5，需要一台在校外的機器 |
| 16 | **§5.2 rc.d 腳本的 `-u`／`procname`／`-H` 三處修正**（v0.19） | 三處都是 📄 依 `daemon(8)` 的文件推的，一樣沒有在 FreeBSD 上跑過。⚠️ **v0.19 之前那兩處是錯的而且症狀都不是「壞掉」**（以 root 執行／`service status` 對不上），所以「沒人抱怨」證明不了新版是對的 | `service engmath start` 之後：`ps -o user,command -p $(cat /var/run/engmath.pid)` → user 要是 `engmath`、command 要是 `daemon`；`service engmath status` → 要說得出 pid；`service engmath stop` → 要真的停。**這三項在家裡就驗得完**，見 `FREEBSD-HOMELAB.md` §5.3 |

---

## 9. 順帶一提：這台機器也可以拿來當作業系統課的教材

老師提到明年要開作業系統課、想研究 FreeBSD。這個部署恰好會用到幾樣
**在課堂上很難用投影片講清楚、但架一次就懂**的東西：

- **`rc.d` 與 `rc.subr`**：一個真正的 init 腳本長什麼樣、`PROVIDE`／`REQUIRE`／
  `KEYWORD` 怎麼決定啟動順序。這比拿 systemd 的 unit 檔當例子更接近
  「作業系統怎麼把使用者空間拉起來」這件事。
- **`kqueue`**：`uvloop` 之所以在 Linux 上用 epoll、在 FreeBSD 上用 kqueue，
  差別就在 §2 引的那幾行 `setup.py`。可以拿它當「同一個抽象、兩種核心介面」
  的實例。
- **ZFS 快照 vs 應用層一致性備份**：§5.5 那段「快照抓到的是 WAL 的當下狀態」
  正是「檔案系統的原子性不等於應用程式的原子性」的一個具體案例。
- **權限與最小權限原則**：`nologin` 的服務帳號、0600 的資料庫、0400 的金鑰檔、
  0644 的 `rc.conf`（所以金鑰不能寫在裡面）——四個檔案就講完一整節課。

⚠️ 但**不要把這台機器同時當教材與正式服務**。
（v0.15 這裡的理由是「學生的學號與密碼雜湊在上面」——**學號那半已隨 D35 消失**，
所以理由變弱了：剩下的是兩組共用帳號的密碼雜湊與 session 金鑰。仍然值得分開，
但如果只能有一台，這已經不是一個會出人命的問題。）
要拿來上課就另外開一台，或至少開一個 jail。
（順帶一提，**jail 本身也是這個系統很適合的部署方式**——📄 但我沒有查證
jail 裡的 SQLite WAL 與檔案權限有沒有額外的注意事項，所以本文件沒有寫。）

---

## 參考來源

- Let's Encrypt, [Announcing Six Day and IP Address Certificate Options in 2025](https://letsencrypt.org/2025/01/16/6-day-and-ip-certs)
- Let's Encrypt, [We've Issued Our First IP Address Certificate](https://letsencrypt.org/2025/07/01/issuing-our-first-ip-address-certificate)
- Let's Encrypt, [6-day and IP Address Certificates are Generally Available](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
- Caddy issue #7399, [Unable to issue IP address certificate with Let's Encrypt `shortlived` ACME profile](https://github.com/caddyserver/caddy/issues/7399)
- FreeBSD, [Release Information](https://www.freebsd.org/releases/)（15.0-RELEASE 於 2025-12-02 發布；14.3 已於 2026-06-30 EOL）
- FreshPorts: [www/py-fastapi](https://www.freshports.org/www/py-fastapi/)、[www/py-uvicorn](https://www.freshports.org/www/py-uvicorn)、[databases/py-sqlmodel](https://www.freshports.org/databases/py-sqlmodel)、[math/py-sympy](https://www.freshports.org/math/py-sympy)、[devel/py-pydantic-core](https://www.freshports.org/devel/py-pydantic-core/)、[security/py-argon2-cffi-bindings](https://www.freshports.org/security/py-argon2-cffi-bindings/)、[security/py-itsdangerous](https://www.freshports.org/security/py-itsdangerous)、[www/py-python-multipart](https://www.freshports.org/www/py-python-multipart)
- [py311-sympy 1.14.0 — FreeBSD math Package](https://freebsdsoftware.org/math/py311-sympy/)
- pydantic-core issue #773, [Pre-build wheels not available for FreeBSD and Cygwin](https://github.com/pydantic/pydantic-core/issues/773)
- uvloop 0.22.1 與 httptools 0.8.0 的 sdist（✅ 在沙箱裡實際下載並檢視）

**v0.19（D42）新增：**

- Let's Encrypt 社群與說明：**驗證來源位址不公布、且會隨時改變**；2020 年起強制
  **多視角驗證（Multi-Perspective Validation）**，驗證請求可能來自任何位址
  ——因此「把 LE 加進防火牆允許清單」不成立（§5.8.2）
- Caddy 文件：[Request matchers](https://caddyserver.com/docs/caddyfile/matchers)
  （`remote_ip` 是直連對端，`client_ip` 在設了 `trusted_proxies` 時改讀
  `X-Forwarded-For`——本節刻意用前者）、
  [`error`](https://caddyserver.com/docs/caddyfile/directives/error)、
  [`handle_errors`](https://caddyserver.com/docs/caddyfile/directives/handle_errors)、
  [Automatic HTTPS](https://caddyserver.com/docs/automatic-https)
  （自動 HTTPS 會在執行期另外開一個 :80 伺服器處理轉址與 ACME 挑戰，
  **那不是你寫的站台區塊**——§5.8.2 的 ⚠️ 就是根據這一段）
- FreeBSD `daemon(8)`：`-P` 是監督行程的 pidfile（`-p` 才是子行程）、`-u` 換執行
  身分、`-r` 掛掉重啟、**`-H` 收到 SIGHUP 時重開 `-o` 的輸出檔（為 newsyslog 而設）**
  ——§5.2 與 §5.4 的三處修正都出自這裡
- RFC 5737（IPv4 文件用位址 `192.0.2.0/24`、`198.51.100.0/24`、`203.0.113.0/24`）
  與 RFC 3849（IPv6 `2001:db8::/32`）——§5.8 所有網段佔位符的來源。
  **用它們而不是「一個看起來很像的網段」是刻意的**：它們永遠不會意外地是對的
