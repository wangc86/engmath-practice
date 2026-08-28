# 在家用區網裡預演一次 FreeBSD 部署

> 對象：老師本人。
> 場景：家裡的 WiFi 路由器底下，一台**實體筆電**跑 FreeBSD 當伺服器，
> 一台 **macOS** 當學生的瀏覽器。
> 目標：**在還沒有校內主機、還沒有網域、還沒有防火牆核准的情況下，
> 把「架站」這件事整條路徑先跑一次**，把該撞的牆在家裡撞完。
>
> 正式部署見 [`FREEBSD-DEPLOY.md`](FREEBSD-DEPLOY.md)（本文件大量引用它的節號）。
> 規劃與決定見 [`PLAN.md`](PLAN.md)，硬規則見 [`CLAUDE.md`](CLAUDE.md)。
> 本文件寫於 **v0.19**。

---

## 0. 先講這份文件的可信度（與 `FREEBSD-DEPLOY.md` §0 相同）

**寫這份文件的環境是 Linux 沙箱，不是 FreeBSD，也不是你家的網路。**
全文沿用同一組標記：

| 標記 | 意思 |
|---|---|
| ✅ **已驗證** | 我在沙箱裡實際跑過、實際看過檔案內容。驗證的**對象**會寫清楚。 |
| 📄 **依文件推論** | 來自 FreeBSD／Caddy／Apple 的官方文件或原始碼。推論鏈會寫出來。 |
| ❓ **未查證** | 我查不到，或查到的不足以下判斷。**寧可寫「不知道」也不編一個看起來很專業的答案。** |

**這份文件裡沒有任何一件事是我在 FreeBSD 或 macOS 上實測過的。**
它與 `FREEBSD-DEPLOY.md` 的差別只有一個，但那個差別很重要：
**這一份的每一步，你今天晚上就驗得掉。** 撞到與本文不符的地方，
請直接改這份文件——它的價值來自被實跑過。

---

## 1. 這個測試能驗證什麼、不能驗證什麼

**先講比例，因為它比清單重要：能驗證的佔多數。**
正式部署清單（`FREEBSD-DEPLOY.md` §7）十個步驟裡，**第 1–8 步在家裡全部做得完**，
做不完的是第 9 步的一半（真憑證與校內 IP 限制）與第 10 步（備份排程，
做得完但驗不出價值）。**換句話說：卡住正式部署的通常是「這台機器怎麼把服務跑起來」，
而那一整段在家裡是可以先跑完的。**

### 1.1 ✅ 能驗證（而且這是這次測試的全部價值）

| # | 項目 | 為什麼在家驗得到 | 對應正式部署 |
|---|---|---|---|
| 1 | **相依套件裝得起來**（`pkg` vs `pip`，路線 A／B／C 哪一條走得通） | 這與網路環境無關，只與 FreeBSD 版本與 ports 樹有關 | `FREEBSD-DEPLOY.md` §3——**這是那份文件裡最大的未知數**，在家裡就解得掉 |
| 2 | **`pytest` 437 項在 FreeBSD + Python 3.11 上全綠** | 純本機 | §7 第 6 步、§8 #1／#2／#3 |
| 3 | **rc.d 服務腳本正確**（起得來、`status` 說得出 pid、`stop` 停得掉、**以 `engmath` 而不是 root 執行**） | 純本機 | §5.2、§8 #6、**§8 #16**（v0.19 新修的三處） |
| 4 | **重開機之後服務自動起來** | 筆電重開機比校內主機容易得多 | §5.2 |
| 5 | **檔案權限**（DB 0600、目錄 0700、金鑰 0400、服務帳號 `nologin`） | 純本機，而且在 FreeBSD 上是**真的生效**（Windows 上形同虛設） | §5.1 |
| 6 | **newsyslog 輪替之後 log 還在寫** | 純本機，`newsyslog -F` 可以手動觸發 | §5.4、§8 #7——**v0.19 才知道要用 `daemon -H`，這是它第一次被真的跑過** |
| 7 | **反向代理設定**（Caddy 起得來、轉得到 8000、靜態檔發得出去） | 純本機 | §5.3 |
| 8 | **HTTP 自動轉 HTTPS** | 純本機 | §4、§5.3 |
| 9 | **應用程式在代理後面的行為**（`--proxy-headers`、`COOKIE_SECURE=1` 之下登入還走得通） | ⚠️ **這一項只有有 HTTPS 才驗得到**，而自簽憑證就夠——見 §1.3 | §5.2、§6 |
| 10 | **⚠️ 代理層的存取紀錄不含 IP** | 從 macOS 連幾次，`tail` 一下 log，用眼睛看 | **§5.7、PLAN §7 #40——這是整個去識別化設計裡唯一沒有測試守住的一環**，見 §6 檢查表第 20 項 |
| 11 | **`class` 與 `staff` 兩組帳號的完整流程**（含 `/activity` 對 `class` 回 403） | 純本機 | §7 的走查清單第 1–7 步 |
| 12 | **`sqlite3 .backup` 備份腳本跑得動** | 純本機 | §5.5 |

### 1.2 ❌ 不能驗證（照實列出）

| # | 項目 | 為什麼家裡驗不到 | 只能在哪裡驗 |
|---|---|---|---|
| 1 | **Let's Encrypt 的真憑證** | LE 不對私有 IP 或 `home.arpa` 這類名稱簽發，而且驗證要從公網打得進來——你家的路由器後面沒有這個條件（除非做通訊埠轉發並且有真網域，那已經不是「家用測試」了） | 學校，`FREEBSD-DEPLOY.md` §4.2／§4.3 |
| 2 | **憑證自動續期**（尤其 §4.3 的 IP 憑證是**六天一期**） | 同上。**這一項的失敗模式是「第六天才壞」**，而家裡測一個下午看不到第六天 | 學校，而且要等一週才能確認 |
| 3 | **⚠️⚠️ 校內 IP 允許清單**（D42、§5.8） | **家裡沒有校內網段**。你可以拿家裡的 `192.168.x.x` 當假的「校內網段」練習語法，但**那驗不到任何真的東西**——見下面 §1.4 | 學校，§5.8.6 |
| 4 | **⚠️⚠️ 學校 VPN 的來源位址落在哪個網段**（PLAN §7 #41） | **完全模擬不到。** 家裡沒有學校 VPN，而這一項的答案取決於 VPN 集中器怎麼配發位址 | 學校 + 一台在校外的機器，§5.8.5 的三步 |
| 5 | **校內防火牆與資安檢查流程** | 那是人的流程，不是機器的 | 計中，§4.5 |
| 6 | **真實的多人並發**（尖峰 30 人同時在線） | 你一台 Mac 開十個分頁不是三十個學生。⚠️ 而且**單 worker + SymPy 每題約 0.1 秒 CPU** 這個組合的排隊行為，要在真的併發下才看得出來 | 學校，開學後 |
| 7 | **筆電長時間運行**（連續數週、發熱、風扇、電池老化） | 一個下午的測試看不到 | 時間 |
| 8 | **筆電睡眠**（闔蓋、閒置） | ⚠️ **這一項家裡「驗得到」但不代表學校沒事**——校內主機是桌機或 VM，沒有闔蓋問題；反過來，**家裡的筆電如果沒關睡眠，你會花一小時 debug 一個其實是「筆電睡著了」的問題**。見 §7.1 |
| 9 | **真實網域的 DNS**（A 記錄、AAAA 記錄、快取、TTL） | `/etc/hosts` 不是 DNS。⚠️ **這個差別會咬人的地方是 IPv6**：`/etc/hosts` 你只填一個 IPv4，真實 DNS 可能同時有 AAAA，而 §5.8 的允許清單只填 IPv4 的話，走 IPv6 的校內學生會被自己的清單擋掉（PLAN §7 #42(b)） | 學校 |
| 10 | **停電、UPS、機房網路** | — | 學校 |

### 1.3 一個關鍵的判斷：自簽憑證「夠不夠」

**夠——對這次測試的目的而言。**

原因是這次要驗的是 **HTTPS 存在時系統的行為**，不是**憑證怎麼來的**：

- `COOKIE_SECURE=1` 之下 session cookie 帶 `Secure`，**在 HTTP 上根本送不出去**
  （`FREEBSD-DEPLOY.md` §4 開頭那段），所以「登入還走不走得通」這件事
  **只有在有 TLS 的情況下才驗得到**——而瀏覽器不在乎那張憑證是誰簽的。
- HTTP→HTTPS 的轉址、代理與後端之間的 `X-Forwarded-Proto`、
  混合內容（mixed content）警告，全部與簽發者無關。

**不夠的地方只有一件事，而且它很小**：正式部署那條 `caddy_cert_email` +
自動申請的路徑，家裡走的是 `tls internal`。兩者的差別是 Caddyfile 裡的**一行**。

### 1.4 ⚠️ 為什麼「拿家裡的網段假裝是校內網段」不算驗證

你當然可以在家裡的 Caddyfile 寫
`@offcampus not remote_ip 192.168.1.0/24`，然後拿手機開 4G 連進來試試看被不被擋。
**這驗到的是「Caddy 的 `remote_ip` matcher 語法我沒寫錯」，那有價值**——
它正是 `FREEBSD-DEPLOY.md` §8 #13 那一項的一半。

**但它驗不到 D42 真正的兩個風險**，而那兩個都與語法無關：

1. **校內網段清單對不對**（PLAN §7 #42）——家裡沒有那份清單。
2. **VPN 的來源位址落在哪裡**（PLAN §7 #41）——家裡沒有學校 VPN。

所以：**語法可以在家練，清單與 VPN 不行。**
本文件 §6 的檢查表把前者列為可選項（第 21 項），並且明白標示它「不結案 §7 #41／#42」。

---

## 2. 從零開始：FreeBSD 那一台

> 📄 **整段都是依文件推論。** FreeBSD 的安裝程式（`bsdinstall`）與 `sysrc`
> 的用法來自官方 Handbook，但我沒有在你的那台筆電上跑過任何一步。

### 2.1 裝完 FreeBSD 之後的最小設定

安裝時的建議選擇：

- **檔案系統**：ZFS 或 UFS 都可以。ZFS 多一個 §5.5 提到的快照玩法，
  但**筆電上 ZFS 比較吃記憶體**；只是要測試的話 UFS 更省事。
- **套件**：勾 `ports` 不必要（我們用 `pkg`）；`src` 不必要。
- **服務**：勾 `sshd`（等一下都從 Mac 上操作會舒服得多）、`ntpd`。
  ⚠️ **不要勾 `powerd` 以外的省電相關項目**，理由見 §7.1。
- **使用者**：建一個你自己的帳號，加進 `wheel` 群組（才能 `su`）。

裝完之後：

```sh
# 更新套件庫
pkg update && pkg upgrade -y

# 基本工具（bash 不是必要的，但你可能會想要）
pkg install -y git curl sudo

# 讓 wheel 群組可以 sudo
visudo        # 取消 %wheel ALL=(ALL:ALL) ALL 那一行的註解
```

### 2.2 取得區域網路 IP

```sh
ifconfig
```

找那張有線或無線網卡（常見名稱：有線 `em0`／`re0`／`bge0`，
無線 `wlan0`），看它的 `inet` 那一行：

```
wlan0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> ...
        inet 192.168.1.42 netmask 0xffffff00 broadcast 192.168.1.255
```

`192.168.1.42` 就是你要填進 Mac 的 `/etc/hosts` 的那個位址。

> ⚠️ **DHCP 會換位址。** 筆電重開機或路由器重啟之後可能拿到不同的 IP，
> 而症狀是「昨天好好的，今天 Mac 連不上」。兩個解法，選一個：
>
> 1. **在路由器上做 DHCP 保留**（用筆電網卡的 MAC 位址綁一個固定 IP）——推薦，
>    因為它同時模擬了正式部署「這台機器有固定 IP」這個前提。
> 2. **在 FreeBSD 上寫死靜態 IP**（`/etc/rc.conf` 的
>    `ifconfig_wlan0="inet 192.168.1.42 netmask 255.255.255.0"` + `defaultrouter=`）
>    ——⚠️ 要確定那個位址在路由器的 DHCP 配發範圍**外面**，否則會撞號。

❓ **無線網卡在 FreeBSD 上能不能用，我無法預測。** 這是 FreeBSD 在筆電上最常見的
卡關點（`iwlwifi`／`iwm` 的支援因晶片而異）。**如果無線不通，插網路線**——
這次測試不需要無線。

### 2.3 Python 與相依套件

**照 `FREEBSD-DEPLOY.md` §3.4 的建議：先試路線 A（全部用 pkg），跑 `pytest`，
綠燈就收工。**

```sh
# ── 路線 A ──────────────────────────────────────────────
pkg install -y python311 py311-pip py311-sqlite3 sqlite3
pkg search pydantic          # ⚠️ v2 的 port 可能叫 py311-pydantic2
pkg search jinja2            # ⚠️ 大小寫（很可能是 py311-Jinja2）
pkg install -y py311-fastapi py311-uvicorn py311-sqlmodel py311-sympy \
               py311-Jinja2 py311-itsdangerous py311-python-multipart \
               py311-argon2-cffi py311-pydantic2

# 驗版本：sympy 必須是 1.14.x、pydantic 必須是 2.x
pkg info | grep -E 'py311-(fastapi|uvicorn|sqlmodel|sympy|pydantic|argon2|Jinja2)'
```

**⚠️ 這一步是整個家用測試最有價值的一步**，因為 `FREEBSD-DEPLOY.md` §3 那三條路線
**沒有一條被跑過**，而它是那份文件自認最可能卡關的地方。無論結果如何，
請把實際發生的事寫回 §3——包括「路線 A 一次就過」這種好消息。

路線 A 不行的話，依 §3.4 的分流：**紅在 SymPy 相關 → 路線 C；紅在別處 → 路線 B**。
路線 B 需要 `pkg install rust pkgconf libffi gmake`，⚠️ 而 Rust 在磁碟上是 GB 級的，
筆電空間要先看一眼。

### 2.4 專用使用者、目錄、程式碼

**與正式部署完全相同**（`FREEBSD-DEPLOY.md` §5.1、§7 第 3–5 步），
刻意不簡化——路徑不一樣的話，這次測試就驗不到權限那幾項了。

```sh
pw groupadd engmath
pw useradd -n engmath -g engmath -s /usr/sbin/nologin -d /nonexistent \
   -c "Engineering Mathematics Practice"

install -d -o engmath -g engmath -m 0700 /var/db/engmath
install -d -o engmath -g engmath -m 0750 /var/log/engmath
install -d -m 0700 /usr/local/etc/engmath

cd /usr/local/www
git clone <你的 repo> engmath-practice
cd engmath-practice

python3.11 -c 'import secrets; print(secrets.token_hex(32))' \
    > /usr/local/etc/engmath/session_secret
chmod 0400 /usr/local/etc/engmath/session_secret
chown engmath /usr/local/etc/engmath/session_secret
```

### 2.5 跑測試（這一步就是「這台機器能不能用」的證明）

```sh
pkg install -y py311-pytest py311-httpx node22
cd /usr/local/www/engmath-practice
python3.11 -m pytest -q
```

**預期 437 項全過。** 沒有 node 的話展示區的 JS 測試會 skip 並印出原因
（那是刻意的，不是壞掉）。

> ⚠️ **這一步紅了就先停下來，不要往下走。** 後面每一步都假設應用程式本身是對的；
> 帶著紅燈往下架，你會分不清楚問題出在 FreeBSD、Caddy 還是程式。

### 2.6 建立兩組帳號

```sh
env PRACTICE_DB=/var/db/engmath/practice.db \
    python3.11 scripts/create_accounts.py init
chown engmath:engmath /var/db/engmath/practice.db
```

密碼**只印這一次**（資料庫裡只有 argon2id 雜湊）。抄下來。忘了也沒關係，
`reset` 隨時可以換一組。

---

## 3. 假網域：`engmath.home.arpa`

### 3.1 為什麼是 `home.arpa` 而不是 `.local`

**建議用 `engmath.home.arpa`。** 理由是 `.local` 在 macOS 上有一個特別的身分：

- 📄 **`.local` 是 RFC 6762（mDNS）保留給鏈路本地多播名稱解析用的**，
  而 macOS 的 `mDNSResponder` 會把 `.local` 的查詢**攔下來走 mDNS**。
  `/etc/hosts` 的項目通常仍然有效（hosts 檔在解析順序上更前面），
  ❓ **但「通常」不是「一定」**——這是一個你不需要去搞清楚的變數，
  而且它壞掉的時候症狀是「有時候通有時候不通」，那是最難查的一種。
- 📄 **`home.arpa` 是 RFC 8375 指定給住宅／家用網路的特殊用途名稱**，
  設計上就是給「這個網路裡的名字」用的，而且**不是 mDNS**。

**還有一個與正式部署對齊的理由**：學校那邊會是
`engmath.ntnu.edu.tw`——一個普通的、走一般 DNS 解析的名字。
`home.arpa` 的行為與它比較接近，`.local` 不是。

> ❓ **我沒有在 macOS 上實測過任何一個。** 如果 `home.arpa` 在你的 Mac 上有問題，
> 退路是隨便一個你確定不存在的名字（例如 `engmath.test`——📄 `.test` 是
> RFC 2606 保留給測試用的 TLD，永遠不會被真的註冊）。
> **不要用一個真的網域**（`engmath.ntnu.edu.tw` 也不要，理由見 §3.2 的 ⚠️）。

### 3.2 macOS 端：`/etc/hosts`

```sh
# 在 Mac 上
sudo nano /etc/hosts
```

加一行（`192.168.1.42` 換成 §2.2 查到的那個）：

```
192.168.1.42    engmath.home.arpa
```

然後清 DNS 快取：

```sh
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

驗一下：

```sh
ping -c 2 engmath.home.arpa
```

> ⚠️ **不要在 `/etc/hosts` 裡把真的 `engmath.ntnu.edu.tw` 指到家裡的筆電。**
> 很誘人（測試路徑會 100% 一樣），但代價是：測完忘了刪那一行，
> 有一天你在校內連正式站台，連到的是一個不存在的 `192.168.1.42`，
> 然後開始查一個不存在的網路問題。**測試用的假名字要一眼看得出是假的。**

### 3.3 FreeBSD 端：Caddy 與 `tls internal`

```sh
pkg install -y caddy
```

`/usr/local/etc/caddy/Caddyfile`：

```caddyfile
# 家用測試版。與正式版（FREEBSD-DEPLOY.md §5.7／§5.8）的差別**只有兩處**，
# 都標在下面。

engmath.home.arpa {
    # ← 差別 1：正式版沒有這一行（憑證由 Let's Encrypt 自動處理）。
    #    tls internal = 用 Caddy 自己的本機 CA 簽一張。
    tls internal

    reverse_proxy 127.0.0.1:8000

    # 與正式版**完全相同**：存取紀錄整個關掉（§5.7，D38）。
    # ⚠️ 這一行就是 §6 檢查表第 20 項要驗的東西，不要為了除錯改掉它——
    #    真的要除錯的話，驗完第 20 項再改，改完再驗一次。
    log {
        output discard
    }
}

# ← 差別 2：正式版這裡還有校內 IP 的允許清單（§5.8）。
#    家裡沒有校內網段，所以整段不放。要練語法的話見 §6 檢查表第 21 項。
```

```sh
sysrc caddy_enable=YES
service caddy start
service caddy status
```

📄 **Caddy 會自動開一個 :80 的伺服器做 HTTP→HTTPS 轉址**，所以 §6 檢查表第 14 項
（HTTP 轉 HTTPS）不需要額外設定。

### 3.4 macOS 上要不要信任那張憑證

**這是一個判斷題，我的建議是：信任，但只放進「登入」鑰匙圈，而且測完就刪。**

先講**不建議放進系統鑰匙圈（System keychain）的理由**：

`tls internal` 用的是 **Caddy 在那台筆電上自己產生的一個根 CA**，
而**那個 CA 的私鑰就躺在筆電的檔案系統上**。把一個根 CA 加進 macOS 的系統信任區，
等於宣告「**任何持有那把私鑰的人，可以為任何網域簽一張我的 Mac 會相信的憑證**」
——不只是 `engmath.home.arpa`，是 `*.google.com`、你的銀行、什麼都可以。
那把私鑰在一台為了測試而臨時裝起來、沒有經過任何加固的筆電上。

**這個風險與「這只是家裡測試」無關**：信任是加在你的 Mac 上，而你的 Mac 之後會
帶去別的地方用。

三個選項，由好到壞：

1. **✅ 建議：加進「登入」鑰匙圈，標記信任，測完刪掉。**
   影響範圍限於你這個使用者，而且刪除是一個明確的動作。
   ⚠️ **「測完刪掉」必須真的做**，所以它是 §6 檢查表的最後一項（第 24 項）。

   ```sh
   # 1) 從 FreeBSD 那台把 Caddy 的根憑證抄出來
   #    ❓ 路徑取決於 caddy 服務的 HOME／XDG_DATA_HOME，FreeBSD port 的設定我沒有查證。
   #       先在 FreeBSD 上找：
   find / -name 'root.crt' -path '*caddy*' 2>/dev/null
   #    典型會長成 .../caddy/pki/authorities/local/root.crt

   # 2) 在 Mac 上抄過來
   scp you@192.168.1.42:/path/to/root.crt ~/Downloads/caddy-homelab-root.crt

   # 3) 加進「登入」鑰匙圈並信任（會跳密碼視窗）
   security add-trusted-cert -k ~/Library/Keychains/login.keychain-db \
       -p ssl ~/Downloads/caddy-homelab-root.crt
   ```

   ❓ **`security` 的旗標組合我沒有實測過**，而且 macOS 各版本的鑰匙圈路徑與
   權限提示不同。做不出來的話，改用「鑰匙圈存取.app」拖進「登入」→
   雙擊憑證 → 「信任」→ 「使用此憑證時」選「永遠信任」。

2. **⚠️ 可接受：什麼都不裝，每次點過瀏覽器的警告。**
   最安全，但**它會訓練出一個壞習慣**——而這個專案的 `FREEBSD-DEPLOY.md` §4.4
   正好因為同一個理由拒絕在正式站台用自簽憑證
   （「教學生按過瀏覽器的安全警告，會直接抵銷 `_about.html` 那句安全告誡」）。
   在**你自己的**測試機器上按警告不會傷到學生，但它也會讓 §6 檢查表第 13、15 項
   （登入流程）多幾次點擊。

3. **❌ 不建議：加進系統鑰匙圈（`/Library/Keychains/System.keychain`）。**
   理由如上。**不要因為它比較快就做這一個。**

> 💡 **另一條路，如果你不想碰根 CA**：用 `openssl` 自己簽一張**只給
> `engmath.home.arpa` 用的葉憑證**（帶 SAN），然後在 Mac 上只信任**那一張**。
> 葉憑證不能拿去簽別的網域，所以上面那個風險整個消失。
> 代價是 Caddyfile 要從 `tls internal` 改成 `tls /path/cert.pem /path/key.pem`
> ——**離正式部署的設定又遠了一步**，而這次測試的目的正是「路徑要一樣」。
> ❓ 兩者我都沒有實測。**如果你不打算把這台 Mac 帶出門，選 1；
> 如果會，選這一條或選 2。**

---

## 4. 啟動應用程式（先手動，再交給 rc.d）

**先手動跑一次**，確認程式本身在這台機器上活得下來。這一步花三十秒，
省下的是「rc.d 起不來的時候，不知道問題在 rc.d 還是在程式」。

```sh
cd /usr/local/www/engmath-practice
env SESSION_SECRET="$(cat /usr/local/etc/engmath/session_secret)" \
    PRACTICE_DB=/var/db/engmath/practice.db \
    COOKIE_SECURE=1 \
    python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 另開一個 shell
fetch -qo - http://127.0.0.1:8000/healthz     # 應該印 {"status":"ok"}
```

⚠️ **`COOKIE_SECURE=1` 之下，`http://127.0.0.1:8000` 是登不進去的**
（`Secure` cookie 在 HTTP 上送不出去）——**這是對的行為，不是壞掉**。
登入要從 Mac 走 `https://engmath.home.arpa`。

確認 `/healthz` 通了就 `Ctrl-C`，交給 rc.d。

---

## 5. rc.d 服務腳本（可測試的版本）

> **這一份與 `FREEBSD-DEPLOY.md` §5.2 是同一支腳本**，
> 已經含 v0.19 修掉的三處（`-u`、`procname`、`-H`）。
> **在家裡跑一次的意義就是把那三處從「📄 依文件推論」變成「✅ 已驗證」。**

### 5.1 腳本

存成 `/usr/local/etc/rc.d/engmath`：

```sh
#!/bin/sh
#
# PROVIDE: engmath
# REQUIRE: LOGIN
# KEYWORD: shutdown
#
# 在 /etc/rc.conf 裡：
#   engmath_enable="YES"

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
# ⚠️ 這裡是 daemon(8) 不是 python：`-P` 寫進 pidfile 的是**監督行程**的 pid。
#    寫成 python 的話 `service status`／`stop` 會對不上，而服務其實跑著。
procname="/usr/sbin/daemon"

command="/usr/sbin/daemon"
command_args="-f -o ${engmath_log} -H -P ${pidfile} -r -u ${engmath_user} \
    ${engmath_dir}/.venv/bin/uvicorn app.main:app \
    --host ${engmath_bind} --port ${engmath_port} \
    --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1"

start_precmd="${name}_precmd"

engmath_precmd()
{
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

> ⚠️ **`command_args` 裡寫的是 `${engmath_dir}/.venv/bin/uvicorn`。**
> 如果你走的是路線 A（全部用 pkg，沒有 venv），把它改成
> `/usr/local/bin/uvicorn-3.11`（❓ 確切名稱用 `pkg info -l py311-uvicorn | grep bin`
> 查）或 `/usr/local/bin/python3.11 -m uvicorn`。
> **這是家用測試很可能撞到的第一個東西**，而它在 `FREEBSD-DEPLOY.md` 裡沒有寫。

### 5.2 啟用

```sh
chmod 555 /usr/local/etc/rc.d/engmath
sysrc engmath_enable=YES
service engmath start
```

### 5.3 ⚠️ 驗那三處修正（這一節是本文件存在的理由之一）

```sh
# ── (a) service status 說得出 pid 嗎 ────────────────────────
service engmath status
#    預期：engmath is running as pid NNNN.
#    ⚠️ 說「is not running」而網頁又打得開 → procname 對不上（v0.19 修的第 2 處）

# ── (b) 它是以 engmath 執行的嗎，不是 root ──────────────────
ps -o user,pid,command -p "$(cat /var/run/engmath.pid)"
#    預期 USER 欄是 engmath、COMMAND 是 /usr/sbin/daemon ...
#    ⚠️ USER 是 root → `-u` 沒生效（v0.19 修的第 1 處）

# 連子行程一起看（uvicorn 那個）
ps -axo user,pid,ppid,command | grep -i uvicorn | grep -v grep
#    預期 USER 欄也是 engmath

# ── (c) stop 真的停得掉嗎 ───────────────────────────────────
service engmath stop
sleep 2
ps -axo user,pid,command | grep -i uvicorn | grep -v grep
#    預期：沒有東西。⚠️ 還在 → -r 的監督行程沒有被正確終止
service engmath start

# ── (d) 掛掉會自動重啟嗎（-r）──────────────────────────────
UVPID=$(pgrep -f 'uvicorn app.main:app' | head -1)
kill -9 "$UVPID"
sleep 3
pgrep -f 'uvicorn app.main:app'      # 預期：印出一個**新的** pid
#    ⚠️ 沒有新的 pid → -r 沒有生效

# ── (e) 本機通不通 ──────────────────────────────────────────
fetch -qo - http://127.0.0.1:8000/healthz     # {"status":"ok"}
```

### 5.4 重開機測試

```sh
shutdown -r now
```

開回來之後（不要登入桌面，直接從 Mac ssh 進去就好）：

```sh
service engmath status
fetch -qo - http://127.0.0.1:8000/healthz
service caddy status
```

> ⚠️ **這一項一定要真的重開機，不能用 `service engmath restart` 代替。**
> 兩者驗的是不同的事：`restart` 驗腳本，重開機驗 `rc.conf` 的 `_enable`、
> `REQUIRE: LOGIN` 的啟動順序、以及開機時 `/var/run` 是空的這件事。
> **開機順序的問題只有在真的開機時才會出現。**

---

## 6. 驗收檢查表

逐項打勾。**第 20 項是這整份文件最重要的一項**（它是 PLAN §7 #40 唯一的驗收方式）。

### 機器與相依

- [ ] **1.** FreeBSD 裝好，`ifconfig` 看得到區網 IP，Mac `ping` 得到
- [ ] **2.** 路由器上做了 DHCP 保留，或設了靜態 IP（重開機之後 IP 不變）
- [ ] **3.** 相依套件裝好（記下走的是路線 A／B／C，**以及撞到什麼**）
- [ ] **4.** `pkg info | grep py311-` 確認 **sympy 是 1.14.x、pydantic 是 2.x**
- [ ] **5.** `python3.11 -m pytest -q` → **437 項全過**（node 缺的話 JS 那批 skip）

### 權限與帳號

- [ ] **6.** `engmath` 使用者存在且是 `nologin`：`pw usershow engmath`
- [ ] **7.** `ls -ld /var/db/engmath` → `drwx------  engmath engmath`（0700）
- [ ] **8.** `ls -l /var/db/engmath/practice.db*` → **三個檔**（含 `-wal`、`-shm`）
      都在 0700 的目錄裡，主檔 0600
- [ ] **9.** `ls -l /usr/local/etc/engmath/session_secret` → `-r--------` `engmath`（0400）
- [ ] **10.** `create_accounts.py init` 印出兩組密碼，且 **`grep` 整個 DB 檔案找不到明碼**
      （`strings /var/db/engmath/practice.db | grep <那組密碼>` → 沒有東西）

### 服務

- [ ] **11.** §5.3 的 (a)–(e) 五項全過（**特別是 (b)：不是 root**）
- [ ] **12.** §5.4 重開機之後 `engmath` 與 `caddy` 都自動起來了

### 網路與 HTTPS

- [ ] **13.** Mac 上 `https://engmath.home.arpa` 看得到**登入頁**
- [ ] **14.** `curl -sI http://engmath.home.arpa | head -1` → **301／308 轉到 https**
- [ ] **15.** 用 `class` 密碼登入 → **進得到出題頁**
      （⚠️ 這一項證明 `COOKIE_SECURE=1` + 代理 + TLS 三者串得起來）
- [ ] **16.** 出一題 → `Show Answer` → `Show Solution Steps`，**兩層預設都是收合的**
- [ ] **17.** 開一個展示（`/demos`），**KaTeX 與 Canvas 都正常**
      （這一項順便驗自架的靜態資產經過代理發得出去）
- [ ] **18.** `class` 帳號開 `/activity` → **403，訊息說只給 staff**
- [ ] **19.** 登出，用 `staff` 密碼登入 → 頁首多一個 **Class activity**，點得進去

### ⚠️ 去識別化（第 20 項是重點）

- [ ] **20.** **代理層的 log 不含 IP。** 步驟：

  ```sh
  # (1) 在 Mac 上連幾次，製造一些流量
  for i in 1 2 3 4 5; do curl -sk -o /dev/null https://engmath.home.arpa/login; done

  # (2) 在 FreeBSD 上，先確認 Mac 的 IP 是什麼（等一下要找的就是它）
  arp -a | grep -i <你的 Mac 的 MAC 或主機名>
  #     或直接在 Mac 上：ipconfig getifaddr en0

  # (3) 掃所有可能的 log 落點，找任何形如 IP 的字串
  grep -rE '[0-9]{1,3}(\.[0-9]{1,3}){3}' \
       /var/log/engmath/ /var/log/caddy/ /var/log/messages 2>/dev/null

  # (4) 特別針對 Mac 的那個位址再找一次（上一步可能被 127.0.0.1 洗掉）
  grep -r '192.168.1.99' /var/log/ 2>/dev/null      # ← 換成你 Mac 的 IP
  ```

  **預期：(4) 沒有任何東西。** (3) 可能會有 `127.0.0.1`
  （那是 Caddy 連到 uvicorn 的位址，不是學生的），看到要能解釋得出來。

  > ⚠️ **這一項是整個去識別化設計裡唯一沒有測試守住的一環**
  > （應用層與 uvicorn 那兩層有五項測試，代理層在我們的行程外面）。
  > **在家裡做這一次，比在學校部署當天第一次做，安全得多**——
  > 因為家裡沒有真的學生的 IP 會被寫下來。
  > 對應 `FREEBSD-DEPLOY.md` §5.7 與 **PLAN §7 #40**。
  > ⚠️ **但它不結案 #40**：學校那台的設定檔會多一段允許清單（§5.8），
  > 而那正是最可能讓人「暫時把 log 打開」的原因。**學校那邊要再做一次。**

### 可選：語法練習（不結案任何一項）

- [ ] **21.** 在 Caddyfile 加上
      `@offcampus not remote_ip 192.168.1.0/24` + `error @offcampus "off campus" 403`
      與 `handle_errors 403 { ... }`，放一份 §5.8.4a 的 `offcampus.html`，
      然後**用手機開 4G**（不要連家裡 WiFi）連進來看看——
      ⚠️ 這需要路由器做通訊埠轉發，而且**只驗到語法**。
      **驗不到**校內網段是否正確（PLAN §7 #42）與 VPN（#41），
      那兩項只有在學校做得到。
      ⚠️ **做完這一項一定要把它從 Caddyfile 拿掉再驗一次第 20 項**——
      改設定檔正是第 20 項最可能被弄壞的方式。

### 長期運行的東西

- [ ] **22.** **newsyslog 輪替**：

  ```sh
  # 放好 /usr/local/etc/newsyslog.conf.d/engmath.conf（見 FREEBSD-DEPLOY.md §5.4）
  newsyslog -Nv          # 先 dry-run，看它打算做什麼
  newsyslog -F           # 強制輪替一次
  ls -l /var/log/engmath/
  #    預期：app.log 變成 app.log.0.bz2，並且有一個新的空 app.log

  # 然後再打幾個請求，確認新的 app.log 有長大
  for i in 1 2 3; do curl -sk -o /dev/null https://engmath.home.arpa/login; done
  ls -l /var/log/engmath/app.log
  ```

  ⚠️ **新的 `app.log` 大小是 0 就代表 `daemon -H` 沒有生效**
  （或者訊號欄寫錯了）。這正是 `FREEBSD-DEPLOY.md` §8 #7 那一項，
  **而這是它第一次被真的跑過**。修不好的話改走 syslog（`daemon -S -T engmath`）。

- [ ] **23.** **備份腳本**：放好 `FREEBSD-DEPLOY.md` §5.5 的 `backup.sh`，
      手動跑一次，確認 `/var/backups/engmath/` 有一個 0600 的檔，
      而且 `sqlite3 <備份檔> '.tables'` 讀得出 `account` 與 `usagelog`

### 收尾

- [ ] **24.** ⚠️ **把 §3.4 加進「登入」鑰匙圈的那張根憑證刪掉**
      （鑰匙圈存取.app → 登入 → 憑證 → 找到 Caddy Local Authority → 刪除）。
      ⚠️ **這一項最容易忘，而忘了的代價是你的 Mac 長期信任一台測試筆電上的 CA。**
- [ ] **25.** 把 `/etc/hosts` 那一行刪掉（或註解），
      `sudo killall -HUP mDNSResponder`
- [ ] **26.** **把這次撞到的每一件事寫回 `FREEBSD-DEPLOY.md`**，
      並把對應的 📄／❓ 改成 ✅——見 §8

---

## 7. 實用提醒

### 7.1 ⚠️ 關掉筆電的睡眠（不做的話，你會 debug 一個假問題）

**這是家用筆電測試最常見的鬼打牆**：一切都設好了，你去吃個飯回來，
Mac 上連不上；ssh 也不通；`ping` 不回。你開始查網路、查 Caddy、查 rc.d——
**而筆電只是闔蓋睡著了**。

📄 FreeBSD 上關掉「闔蓋即睡眠」：

```sh
# 立即生效
sysctl hw.acpi.lid_switch_state=NONE

# 開機時生效：/etc/sysctl.conf 加一行
echo 'hw.acpi.lid_switch_state=NONE' >> /etc/sysctl.conf
```

📄 順便把電源／睡眠按鈕也一起處理，並確認沒有自動待機：

```sh
sysctl hw.acpi.sleep_button_state=NONE      # 睡眠鍵不觸發
sysctl hw.acpi.standby_state=NONE
sysctl -a | grep -E 'hw.acpi.(lid|sleep|standby|power)_'   # 看目前狀態
```

❓ **這幾個 sysctl 的可用值與預設值我沒有實測**，而且它們依 ACPI 實作而異
（`NONE`／`S1`／`S3`）。**驗收方式很簡單：闔蓋、等五分鐘、從 Mac ping 一下。**

> 💡 **順帶一提**：`powerd` 可以留著（它只調整 CPU 頻率，不會睡眠），
> 但如果你想排除變因，測試期間 `service powerd stop` 也無妨。
> ⚠️ 螢幕保護／黑屏是無害的——**黑屏不等於睡眠**，不要因為螢幕黑了就以為它睡了。

### 7.2 防火牆

家用測試**可以完全不開 pf**（路由器已經把你隔在 NAT 後面了）。
但如果你想順便練 `FREEBSD-DEPLOY.md` §5.8.2 的那份 `pf.conf`：

```sh
pfctl -nf /etc/pf.conf     # ⚠️ 一定先驗語法
```

⚠️ **改 pf 之前先確定你有實體鍵盤可以用**（這正是家用測試比校內主機安全的地方：
把自己鎖在外面的代價只是走過去掀開筆電）。這也是**先在家練 pf 的好理由**。

### 7.3 macOS 端怎麼確認「連得到」

由淺到深，撞牆時照順序往下：

```sh
# 1) 網路層通不通
ping -c 3 192.168.1.42

# 2) 名字解析對不對（應該印出你填的那個 IP）
dscacheutil -q host -a name engmath.home.arpa
#    或
ping -c 1 engmath.home.arpa

# 3) 埠開著嗎
nc -vz engmath.home.arpa 443
nc -vz engmath.home.arpa 80

# 4) TLS 交握與憑證長什麼樣
openssl s_client -connect engmath.home.arpa:443 -servername engmath.home.arpa </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

# 5) HTTP 層（-k 是「忽略憑證問題」，用來把 TLS 的變因排除掉）
curl -skI https://engmath.home.arpa/ | head -3

# 6) 不加 -k：這一步才是在驗「憑證信任」有沒有設好
curl -sI https://engmath.home.arpa/ | head -3
```

> 💡 **5 通而 6 不通 = 憑證信任沒設好**（§3.4），不是伺服器的問題。
> 這個區分能省下很多時間。

### 7.4 其他零碎

- **時間**：`ntpd` 要開。⚠️ 時鐘差太多會讓 TLS 憑證「還沒生效」或「已過期」，
  而錯誤訊息長得完全不像時間問題。`date` 看一眼。
- **磁碟**：`df -h`。路線 B 會拉進 Rust（GB 級）。
- **從 Mac 操作 FreeBSD**：`ssh you@192.168.1.42`。比在筆電小鍵盤上打字舒服得多，
  而且輸出可以複製貼上。
- ⚠️ **不要在 FreeBSD 那台上直接編輯 repo 裡的檔案然後忘記**——
  那些改動不會回到你的 Mac 上，而下一次 `git pull` 會衝突。
  要改就在 Mac 上改、commit、在 FreeBSD 上 `git pull`。

---

## 8. 測完之後：哪些結論帶得走、哪些不行

### 8.1 ✅ 直接帶到學校的正式部署

| 這次驗到的 | 為什麼帶得走 |
|---|---|
| **相依套件走哪條路線、撞到什麼** | 與網路環境無關，只與 FreeBSD 版本有關。⚠️ **前提是學校那台的 FreeBSD 版本與 ports 樹相同**——版本不同就要重驗第 3–5 項 |
| **437 項測試在 FreeBSD + Python 3.11 上的結果** | 同上 |
| **rc.d 腳本**（含 `-u`／`procname`／`-H` 三處） | 純本機行為。**這是家用測試最大的一筆收穫**：它把 `FREEBSD-DEPLOY.md` §8 #6 與 #16 從「沒跑過」變成「跑過」 |
| **開機自動啟動** | 純本機 |
| **檔案權限與 `nologin` 服務帳號** | 純本機 |
| **newsyslog 輪替 + `daemon -H`** | 純本機。§8 #7 就此結案 |
| **Caddy 的反向代理設定、HTTP→HTTPS** | 設定檔可以整份帶過去，**只改兩行**（`tls internal` 拿掉、加上允許清單） |
| **應用程式在代理後面的行為**（`COOKIE_SECURE=1` 的登入流程） | 與憑證誰簽的無關 |
| **`log { output discard }` 的寫法有效** | 語法層面帶得走 |

### 8.2 ⚠️ 必須在學校重新驗證

| 項目 | 為什麼不能帶 | 在哪一節 |
|---|---|---|
| **代理層 log 不含 IP** | 語法帶得走，但**學校那台的 Caddyfile 會多一段允許清單**，而那正是最可能讓人「暫時把 log 打開」的原因。⚠️ **PLAN §7 #40 不因為家裡驗過就結案** | `FREEBSD-DEPLOY.md` §5.7、§5.8.6 (4) |
| **憑證**（Let's Encrypt、自動續期、六天一期的 IP 憑證） | 家裡是自簽。**這一項的失敗模式是「第六天才壞」** | §4.2–§4.4 |
| **校內 IP 允許清單擋得住** | 家裡沒有校內網段 | §5.8.6 (1)(2) |
| **允許清單有沒有誤傷應用程式的 403** | 家裡沒放允許清單（除非做了第 21 項，而那是不同的網段） | §5.8.6 (3) |
| **⚠️⚠️ VPN 的來源位址**（PLAN §7 #41） | **完全模擬不到**，而且猜錯會讓被擋頁面對學生說謊 | §5.8.5 的三步 |
| **DNS**（A／AAAA 記錄、IPv6） | `/etc/hosts` 不是 DNS。⚠️ **IPv6 是這裡的地雷**：允許清單只填 IPv4 而主機有 AAAA 的話，走 IPv6 的校內學生會被自己的清單擋掉 | PLAN §7 #42(b) |
| **多人並發** | 一台 Mac 不是三十個學生 | 開學後 |
| **校內防火牆報備** | 人的流程 | §4.5 |
| **長期穩定度** | 時間 | — |

### 8.3 ⚠️ 最後一件事：把結果寫回去

`FREEBSD-DEPLOY.md` 全文逐項標著 ✅／📄／❓，而**那些標記的價值取決於它們是最新的**。
這次測試會把其中好幾項從 📄 變成 ✅（或者更有價值地：變成「試過，不對，實際是這樣」）。

**建議的做法**：測試當下開一個檔案隨手記，測完一次改進去，
並在 §8 的表格裡把對應列刪掉或改寫。

> ⚠️ **不要只在心裡記得。** 這份文件與 `FREEBSD-DEPLOY.md` 的讀者是**半年後的你**
> ——那時你會記得「好像測過」，但不會記得「那個 uvicorn 的路徑到底要寫哪一個」。
> **PLAN v0.18 剛好抓到兩處停在 v0.15 的失效敘述，原因一模一樣：
> 沒有人照著它做，就沒有人撞到它是錯的。** 這次是有人照著做了，
> 那就趁還記得的時候寫下來。
