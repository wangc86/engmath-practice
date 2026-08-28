# 在家裡的虛擬機裡預演一次 FreeBSD 部署

> 對象：老師本人。
> 場景：一台 **Ubuntu Linux 筆電**，上面跑 **QEMU + KVM + libvirt**，
> 用 **virt-manager** 當圖形介面，**虛擬機裡裝 FreeBSD** 當伺服器；
> **測試用的瀏覽器就是 Ubuntu host 自己**（Firefox／Chrome）。
> 目標：**在還沒有校內主機、還沒有網域、還沒有防火牆核准的情況下，
> 把「架站」這件事整條路徑先跑一次**，把該撞的牆在家裡撞完。
>
> ⚠️ **macOS 那一台完全不出現在這份文件裡。**
> v0.19 它是「學生的瀏覽器」，v0.20 的草稿一度把它降為「Safari 相容性驗收」，
> 而 **D45 之後連那個用途也沒有了：官方不支援 Safari**（理由與代價見 §1.6）。
> **這次預演只用兩台東西：Ubuntu host，與它裡面的一個 FreeBSD 虛擬機。**
>
> 正式部署見 [`FREEBSD-DEPLOY.md`](FREEBSD-DEPLOY.md)（本文件大量引用它的節號）。
> 規劃與決定見 [`PLAN.md`](PLAN.md)，硬規則見 [`CLAUDE.md`](CLAUDE.md)。
> 本文件初版寫於 **v0.19**（當時假設是一台實體 FreeBSD 筆電），
> **v0.20 依老師的新測試環境整份改寫**（D44），
> 並記入維持 HTTPS（D43）與不支援 Safari（D45）兩條決定。

---

## 0. 先講這份文件的可信度

**寫這份文件的環境是一個 Linux 沙箱，而且那個沙箱裡沒有任何虛擬化能力。**
全文沿用 `FREEBSD-DEPLOY.md` §0 的同一組標記：

| 標記 | 意思 |
|---|---|
| ✅ **已驗證** | 我在沙箱裡實際跑過、實際看過檔案內容。驗證的**對象**會寫清楚。 |
| 📄 **依文件推論** | 來自 libvirt／QEMU／FreeBSD／Caddy／MDN 的官方文件。推論鏈會寫出來。 |
| ❓ **未查證** | 我查不到，或查到的不足以下判斷。**寧可寫「不知道」也不編一個看起來很專業的答案。** |

✅ **已驗證（驗證的對象是沙箱本身，不是你的筆電）**：這個沙箱裡
`/dev/kvm` 不存在、`/proc/cpuinfo` 裡 `vmx`／`svm` 的出現次數是 **0**、
`qemu-system-x86_64`／`virsh`／`virt-manager` 三個指令一個都沒有。
**所以：本文件關於 QEMU、KVM、libvirt、virt-manager、FreeBSD guest 的每一句話，
沒有一句是我實跑過的。** 這與 v0.19 的處境相同，只是換了一組沒跑過的東西。

**這份文件與 `FREEBSD-DEPLOY.md` 的差別只有一個，但那個差別很重要：
這一份的每一步，你今天晚上就驗得掉。** 撞到與本文不符的地方，
請直接改這份文件——它的價值來自被實跑過。

---

## 1. 這個測試能驗證什麼、不能驗證什麼

### 1.0 ⚠️ 先講一件 v0.20 才看清楚的事：虛擬機比實體筆電**更接近**正式部署

v0.19 這份文件假設的是「一台實體筆電跑 FreeBSD」，並且把
**「硬體差異」列為一個實質落差**（風扇、電池、闔蓋、無線網卡驅動、長時間發熱）。
改成 KVM 虛擬機之後，**那個落差大幅縮小，而且方向是好的**：

| v0.19 假設的落差 | v0.20 的實際狀況 |
|---|---|
| 「這是筆電，學校那台是伺服器」 | ⚠️ **學校那台很可能也是虛擬機。** 大學的校內服務主機現在多半跑在 VMware／Proxmox／KVM 上。**你的測試環境與正式環境變成同一類東西**，而不是兩類 |
| 磁碟與網卡是真的硬體，行為與伺服器不同 | **virtio 磁碟（`vtbd0`）與 virtio 網卡（`vtnet0`）是虛擬化環境的標準介面**（§2.3）。學校那台若是 VM，看到的裝置名稱與驅動路徑**很可能一模一樣** |
| ❓ **無線網卡在 FreeBSD 上能不能用**（v0.19 §2.2 標了一個大問號，說「不通就插網路線」） | **這個問題整個消失了。** guest 看到的是 `vtnet0`，`iwlwifi`／`iwm` 的支援與否與它無關。⚠️ **這是換成虛擬機最直接的一筆收穫**——它是 v0.19 最可能一開場就卡住半個晚上的地方 |
| 闔蓋睡眠會讓 FreeBSD 那台消失 | 問題**移到 Ubuntu host 那一層**（§9.1）。仍然要處理，但你對 Ubuntu 熟得多，而且 guest 裡不再需要動 `hw.acpi.*` 那幾個 ❓ 標記的 sysctl |
| 螢幕、鍵盤、顯示卡驅動 | 不存在。virt-manager 的主控台就是 VGA 文字畫面 |
| 裝壞了要重灌 | **快照，三十秒還原**（§7）。這不只是方便——它**提高了測試品質**，見 §1.3 |

**剩下的落差改變了性質**：不再是「筆電 vs 伺服器」，而是
「**你家 NAT 後面的一個虛擬網段 vs 校園網路**」。那正是這次本來就驗不到的東西
（§1.4），所以並沒有變糟。

**那唯一實質變大的落差呢？** 換成 Linux host 之後，
**「這台機器上沒有 Safari」**曾經是這一輪唯一變糟的一格。
⚠️ **而老師在同一輪決定官方不支援 Safari（D45），於是那一格不是縮小，是消失了**
——這台 Ubuntu 筆電上有的兩個引擎，**正好就是官方支援的全部**。
理由、代價與它的實作見 **§1.6**。

**所以整體結論是**：v0.20 的測試環境**在每一個維度上都不比 v0.19 差，
而且在硬體、無線網卡與可重複性三項上明顯更好**。

### 1.1 先講比例，因為它比清單重要：能驗證的佔多數

正式部署清單（`FREEBSD-DEPLOY.md` §7）十個步驟裡，**第 1–8 步在家裡全部做得完**，
做不完的是第 9 步的一半（真憑證與校內 IP 限制）與第 10 步（備份排程，
做得完但驗不出價值）。**換句話說：卡住正式部署的通常是「這台機器怎麼把服務跑起來」，
而那一整段在家裡是可以先跑完的。**

### 1.2 ✅ 能驗證（這是這次測試的主要價值）

| # | 項目 | 為什麼在家驗得到 | 對應正式部署 |
|---|---|---|---|
| 1 | **相依套件裝得起來**（`pkg` vs `pip`，路線 A／B／C 哪一條走得通） | 這與網路環境無關，只與 FreeBSD 版本與 ports 樹有關 | `FREEBSD-DEPLOY.md` §3——**這是那份文件裡最大的未知數**，在家裡就解得掉 |
| 2 | **`pytest` 437 項在 FreeBSD + Python 3.11 上全綠** | 純本機 | §7 第 6 步、§8 #1／#2／#3 |
| 3 | **rc.d 服務腳本正確**（起得來、`status` 說得出 pid、`stop` 停得掉、**以 `engmath` 而不是 root 執行**） | 純本機 | §5.2、§8 #6、**§8 #16**（v0.19 新修的三處） |
| 4 | **重開機之後服務自動起來** | **虛擬機重開機比實體筆電還快**，而且失敗了可以還原快照重來 | §5.2 |
| 5 | **檔案權限**（DB 0600、目錄 0700、金鑰 0400、服務帳號 `nologin`） | 純本機，而且在 FreeBSD 上是**真的生效**（Windows 上形同虛設） | §5.1 |
| 6 | **newsyslog 輪替之後 log 還在寫** | 純本機，`newsyslog -F` 可以手動觸發 | §5.4、§8 #7——**v0.19 才知道要用 `daemon -H`，這是它第一次被真的跑過** |
| 7 | **反向代理設定**（Caddy 起得來、轉得到 8000、靜態檔發得出去） | 純本機 | §5.3 |
| 8 | **HTTP 自動轉 HTTPS** | 純本機 | §4、§5.3 |
| 9 | **應用程式在代理後面的行為**（`--proxy-headers`、`COOKIE_SECURE=1` 之下登入還走得通） | ⚠️ **這一項只有有 HTTPS 才驗得到**，而自簽憑證就夠——見 §1.5 | §5.2、§6 |
| 10 | **⚠️ 代理層的存取紀錄不含 IP** | 從 Ubuntu host 連幾次，`tail` 一下 log，用眼睛看 | **§5.7、PLAN §7 #40——這是整個去識別化設計裡唯一沒有測試守住的一環**，見 §8 檢查表第 20 項 |
| 11 | **`class` 與 `staff` 兩組帳號的完整流程**（含 `/activity` 對 `class` 回 403） | 純本機 | §7 的走查清單第 1–7 步 |
| 12 | **`sqlite3 .backup` 備份腳本跑得動** | 純本機 | §5.5 |
| 13 | **🆕 展示區在 Firefox 與 Chrome 上跑得對** | Ubuntu host 上兩個引擎都有 | PLAN §8.5。⚠️ **而那正好就是官方支援的全部瀏覽器**（D45，§1.6）——所以這一項在家裡就結案得掉 |
| 15 | **🆕 不支援瀏覽器的那段訊息真的出得來**（D45） | 在 host 上把它逼出來一次（§8 檢查表第 27 項） | ⚠️ **你在 Chrome 上永遠看不到它**，這正是它最可能悄悄壞掉的方式 |
| 14 | **🆕 「裝壞了重來」與「反覆重開機」變成可重複實驗** | 快照（§7） | 這一項沒有對應的正式部署步驟——它是**測試方法本身**的升級 |

### 1.3 🆕 快照為什麼不只是方便（v0.20）

v0.19 那份文件裡有幾項驗收是**一次性的**，因為在實體筆電上做錯了要重灌：

- 「重開機之後服務自動起來」——如果沒起來，你改一改再重開一次，
  **但你不知道剛剛那次失敗是不是被你這次的改動以外的東西影響**。
- 「相依套件走哪條路線」——路線 A 裝到一半失敗、留下半套 pkg，
  再試路線 B 就是在一個髒環境上試。**而髒環境的結論帶不到學校去。**

**有了快照，這兩項都變成可重複的實驗**：裝套件之前存一個快照，路線 A 失敗，
還原，乾淨地試路線 B。**結論的可信度因此不同**——「路線 B 在乾淨系統上一次就過」
比「路線 A 失敗後改用 B 也過了」有用得多，因為學校那台是乾淨的。

⚠️ **所以 §7 的快照不是選配。** 建議在 §7.3 那四個時間點各存一個。

### 1.4 ❌ 不能驗證（照實列出）

| # | 項目 | 為什麼家裡驗不到 | 只能在哪裡驗 |
|---|---|---|---|
| 1 | **Let's Encrypt 的真憑證** | LE 不對私有 IP 或 `home.arpa` 這類名稱簽發，而且驗證要從公網打得進來——你家的路由器後面沒有這個條件，**而虛擬機又多包了一層 NAT**（§3.1） | 學校，`FREEBSD-DEPLOY.md` §4.2／§4.3 |
| 2 | **憑證自動續期**（尤其 §4.3 的 IP 憑證是**六天一期**） | 同上。**這一項的失敗模式是「第六天才壞」**，而家裡測一個下午看不到第六天 | 學校，而且要等一週才能確認 |
| 3 | **⚠️⚠️ 校內 IP 允許清單**（D42、§5.8） | **家裡沒有校內網段。** 你可以拿 `192.168.122.0/24` 當假的「校內網段」練習語法，但**那驗不到任何真的東西**——見 §1.7 | 學校，§5.8.6 |
| 4 | **⚠️⚠️ 學校 VPN 的來源位址落在哪個網段**（PLAN §7 #41） | **完全模擬不到。** 家裡沒有學校 VPN | 學校 + 一台在校外的機器，§5.8.5 的三步 |
| 5 | **校內防火牆與資安檢查流程** | 那是人的流程，不是機器的 | 計中，§4.5 |
| 6 | **真實的多人並發**（尖峰 30 人同時在線） | 你在 host 上開十個分頁不是三十個學生。⚠️ 而且**單 worker + SymPy 每題約 0.1 秒 CPU** 這個組合的排隊行為，要在真的併發下才看得出來。⚠️ **虛擬機在這裡還多一個變數**：你給 guest 幾顆 vCPU 會直接改變結果，所以就算你做了壓力測試，數字也帶不到學校去 | 學校，開學後 |
| 7 | **長時間運行**（連續數週） | 一個下午的測試看不到。⚠️ 但**發熱／風扇／電池老化這三項與虛擬機無關了**——它們是 host 的事，而 host 是你日常在用的筆電 | 時間 |
| 8 | **host 睡眠會把 guest 一起帶走** | ⚠️ **這一項家裡「驗得到」但不代表學校沒事**——反過來說，**Ubuntu 如果沒關睡眠，你會花一小時 debug 一個其實是「host 睡著了、guest 被暫停了」的問題**。見 §9.1 |
| 9 | **真實網域的 DNS**（A 記錄、AAAA 記錄、快取、TTL） | `/etc/hosts` 不是 DNS。⚠️ **這個差別會咬人的地方是 IPv6**：`/etc/hosts` 你只填一個 IPv4，真實 DNS 可能同時有 AAAA，而 §5.8 的允許清單只填 IPv4 的話，走 IPv6 的校內學生會被自己的清單擋掉（PLAN §7 #42(b)）。⚠️ **libvirt 預設 NAT 網路是純 IPv4，所以這一項在家裡連「不小心驗到」的機會都沒有** | 學校 |
| 10 | **停電、UPS、機房網路** | — | 學校 |
| 11 | ~~**Safari 上的展示區**~~ | ⚠️ **這一列在 v0.20 的草稿裡是「唯一實質變大的落差」，而 D45 把它取消了**——不是縮小，是取消：官方不支援 Safari，所以「Safari 上對不對」不再是一個要驗的問題 | **不驗**。理由與代價見 **§1.6**；學生看到的那段訊息見 §8 檢查表第 27 項 |

### 1.5 一個關鍵的判斷：自簽憑證「夠不夠」

**夠——對這次測試的目的而言。**

原因是這次要驗的是 **HTTPS 存在時系統的行為**，不是**憑證怎麼來的**：

- `COOKIE_SECURE=1` 之下 session cookie 帶 `Secure`，**在 HTTP 上根本送不出去**
  （`FREEBSD-DEPLOY.md` §4 開頭那段），所以「登入還走不走得通」這件事
  **只有在有 TLS 的情況下才驗得到**——而瀏覽器不在乎那張憑證是誰簽的。
- HTTP→HTTPS 的轉址、代理與後端之間的 `X-Forwarded-Proto`、
  混合內容（mixed content）警告，全部與簽發者無關。
- 📄 **安全脈絡（secure context）也一樣不在乎簽發者**：`https://` 就是安全脈絡，
  自簽與否無關。所以 §1.2 第 13 項（展示區）在 `tls internal` 之下驗得到。
  ⚠️ **這一點在 v0.20 變得比 v0.19 重要得多，理由見 §1.8（D43）。**

**不夠的地方只有一件事，而且它很小**：正式部署那條 `caddy_cert_email` +
自動申請的路徑，家裡走的是 `tls internal`。兩者的差別是 Caddyfile 裡的**一行**。

### 1.6 🆕 瀏覽器相容性：**這一項不做**，而且不是漏掉（v0.20，D45）

> ⚠️ **這一節在 v0.20 的草稿裡曾經是「一項可以延後的待辦」。老師把它取消了，
> 而取消的理由值得留在這裡——半年後有人翻到這份文件，會問
> 「Safari 呢？」，而那時只有這一段答得出來。**

**決定**：**官方不支援 Safari**（PLAN **D45**）。理由是 macOS 上裝得到 Chrome，
所以「請用 Chrome 或 Firefox」對 Mac 使用者是一句**做得到**的話——
而支援 Safari 要付的代價是取得一台 Mac、在上面逐項驗收、
並且此後每一次動到展示都要再驗一次。

**於是這次預演的瀏覽器範圍就是 Ubuntu host 上的兩個引擎**：
Firefox（Gecko）與 Chrome（Blink），涵蓋 KaTeX 渲染、Canvas 的
devicePixelRatio 縮放、`AudioWorklet`、autoplay 手勢政策、
`visibilitychange` 的停止與恢復（§1.2 第 13 項）。
**那正好就是官方支援的全部範圍**——換句話說，
**這台 Ubuntu 筆電驗得到的瀏覽器，與正式部署要支援的瀏覽器，是同一組。**
⚠️ 這是 v0.20 一個沒有預期到的好消息：v0.19 那份文件把「沒有 Safari」列為
換成虛擬機之後**唯一實質變大的落差**，而 D45 直接把那個落差**取消**了，
不是縮小。

**代價要寫明，不能只寫好處**：

- 📄 Safari 的 Web Audio 實作是三個引擎裡分歧最大的，而展示重度使用
  `AudioWorklet`、`createPeriodicWave`、`AudioParam` 的斜坡——
  **所以「不支援」不是一句保守的免責聲明，它是一個真的會發生的失敗。**
- **學生中必定有人用 Mac**，而且他們的預設瀏覽器就是 Safari。
- ⚠️⚠️ **失敗模式是「聲音不對」或「沒有聲音」，不是「頁面壞掉」**——
  頁面照樣渲染、按鈕照樣按得下去，而學生以為是自己的耳機。
  **這種失敗不會有人回報。**

**因此 D45 不只是一句宣告，它有實作**（這是它與「首頁寫一句話」的差別）：
展示頁上有一段**只在偵測到不支援時才出現**的英文訊息，
做法是「能力偵測 + 引擎白名單」兩層，程式在
`app/static/demos/lib/browser.js`，測試在 `tests/test_demos.py` 與
`tests/test_dsp_js.py`。⚠️ **設計理由（為什麼能力偵測單獨不夠）寫在那支
JS 的檔頭**，這裡不重複。

> ⚠️ **這一項在檢查表裡因此不是一個空的打勾框，而是一個「確認訊息真的出得來」
> 的項目**（§8 第 27 項）。**你在 Chrome 上永遠看不到那段訊息**——
> 這正是它最可能悄悄壞掉的方式，所以那一項要求你手動把它逼出來一次。

### 1.7 ⚠️ 為什麼「拿家裡的網段假裝是校內網段」不算驗證

你當然可以在家裡的 Caddyfile 寫
`@offcampus not remote_ip 192.168.122.0/24`，然後從別的地方連進來試試看被不被擋。
**這驗到的是「Caddy 的 `remote_ip` matcher 語法我沒寫錯」，那有價值**——
它正是 `FREEBSD-DEPLOY.md` §8 #13 那一項的一半。

**但它驗不到 D42 真正的兩個風險**，而那兩個都與語法無關：

1. **校內網段清單對不對**（PLAN §7 #42）——家裡沒有那份清單。
2. **VPN 的來源位址落在哪裡**（PLAN §7 #41）——家裡沒有學校 VPN。

⚠️ **v0.20 補一個新的陷阱**：在 NAT 模式（§3.1）之下，
**從 host 連進 guest 的來源位址是 `192.168.122.1`（virbr0 那一端），
不是 host 在家用網路上的位址**。所以你在 Caddyfile 裡填的那個「假校內網段」
與你直覺想的可能不是同一個。📄 這是 NAT 的定義行為，不是 bug，
但**它會讓語法練習的結果看起來像是「擋錯人」**。
先用 §8 檢查表第 20 項那個 `grep` 確認一下真正的來源位址長什麼樣，再下結論。

所以：**語法可以在家練，清單與 VPN 不行。**
本文件 §8 的檢查表把前者列為可選項（第 21 項），並且明白標示它「不結案 §7 #41／#42」。

### 1.8 🆕 維持 HTTPS 的決定（PLAN D43）

老師這一輪重新考慮過「家用測試階段乾脆用純 HTTP，省掉憑證那一整段」，
**結論是維持 HTTPS**。理由與被否決的替代方案都記在 PLAN 的 **D43**，
這裡只寫與這份文件直接相關的那一條：

📄 **`AudioWorklet` 是 secure-context-only。** MDN 對 `AudioWorklet` 與
`Worklet.addModule()` 都標著「available only in secure contexts」，
Chrome 的開發者文件寫得更直接：Worklet API 只在安全脈絡下可用，
所以用到它的頁面必須以 HTTPS 提供——`http://localhost` 除外，那被視為安全脈絡。

⚠️ **最後那個例外正是陷阱所在**：

- 你在 guest 上用 `http://127.0.0.1:8000` 測，**展示區會正常運作**
  （localhost 算安全脈絡）。
- 學生用 `http://192.168.x.x` 連進來，
  **`BaseAudioContext.audioWorklet` 直接取不到**，自訂的 processor 定義不了。
- 於是**「純 HTTP 可不可行」這個問題，在本機測試時永遠得到「可以」這個錯誤答案**。

v0.19 把這一點標為「未經驗證」；**v0.20 把它升級為 📄 依文件推論**（來源見文末）。
這改變了 D43 的性質：**它不再只是一個威脅模型的取捨，而是一個功能性的硬阻塞**
——沒有 HTTPS，PLAN §8 整章（2S，已投入約 3.6 PW）的產出對非本機的使用者是壞的。

❓ **仍未查證的部分**：各瀏覽器**實際**在非安全脈絡下的行為細節
（是拋例外、回 `undefined`、還是靜默不出聲）。
**這一項不需要查證就能行動**，因為決定已經是「用 HTTPS」——寫在這裡只是為了
不要把「文件這樣說」讀成「我看過它壞掉」。

> 💡 **順帶一提，D45 的實作把這件事變成看得見的**：非安全脈絡下
> `AudioWorklet` 取不到，而能力偵測那一層會抓到它並顯示一句提到 https 的訊息
> （`app/static/demos/lib/browser.js`）。**所以「忘了開 HTTPS」不再是一個
> 安靜的失敗**——這是 D43 與 D45 互相補上的一角。

---

## 2. 建立虛擬機（Ubuntu host 這一側）

> 📄 **整節依 libvirt／QEMU／virt-manager 的官方文件與 Ubuntu 的套件命名推論。**
> ✅ 唯一驗證過的是「沙箱裡沒有這些東西」（§0）。

### 2.1 先確認這台筆電做得到

```sh
# CPU 有沒有虛擬化擴充（Intel 是 vmx、AMD 是 svm）；印 0 就是 BIOS 裡關著
grep -c -E '(vmx|svm)' /proc/cpuinfo

# 裝套件
sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients \
                 virtinst virt-manager

# 把自己加進群組（⚠️ 要登出再登入，或 newgrp，否則 virt-manager 會要 root 密碼）
sudo usermod -aG libvirt,kvm "$USER"

# 驗一下
kvm-ok                      # 需要 apt install cpu-checker
virsh --connect qemu:///system list --all
ls -l /dev/kvm
```

⚠️ **`qemu:///system` 與 `qemu:///session` 是兩個不同的世界。**
virt-manager 預設連的是 `qemu:///system`（需要 libvirt 群組），
而 `virsh` 在命令列上預設是 `qemu:///session`。
**兩邊看到的虛擬機清單不一樣**，而症狀是「virt-manager 裡明明有，`virsh list` 卻是空的」。
建議一律加 `--connect qemu:///system`，或設
`export LIBVIRT_DEFAULT_URI=qemu:///system`（寫進 `~/.bashrc`）。

### 2.2 虛擬機的規格建議

這個系統很輕量（PLAN §0 的規模假設是 60–150 人、尖峰同時在線 30 人，
單一請求由 SymPy 的約 0.1 秒 CPU 主導），但**測試環境的瓶頸不是服務本身，
是 `pytest` 那 437 項**（CLAUDE.md 寫明約 3 分鐘，出題引擎的 SymPy 驗證是大宗）。

| 項目 | 建議 | 依據 |
|---|---|---|
| **vCPU** | **2**（有餘裕給 4） | pytest 預設單行程，多給也不會更快；2 顆是為了「測試在跑的時候 ssh 還進得去」。⚠️ **不要一次給滿**——host 上還有 virt-manager、瀏覽器與你的日常工作 |
| **記憶體** | **UFS：2 GB 夠，4 GB 舒服**；**ZFS：至少 4 GB** | SymPy 匯入後常駐約數百 MB，pytest 跑起來峰值更高；ZFS 的 ARC 會吃掉一大塊，這是 FreeBSD 在小記憶體虛擬機上最常見的抱怨來源 |
| **磁碟** | **路線 A：20 GB**；**可能走路線 B：40 GB** | FreeBSD base 約數 GB、python + 相依套件約 1–2 GB、`node22` 數百 MB；⚠️ **路線 B 要拉進 Rust 工具鏈，那是 GB 級的**（`FREEBSD-DEPLOY.md` §3.2）。⚠️ **再加上快照**：含記憶體狀態的內部快照，每一個大約多吃「配置的記憶體」那麼多空間（§7.4） |
| **磁碟格式** | **qcow2**（virt-manager 的預設） | ⚠️ **只有 qcow2 支援內部快照**，raw 不支援（§7.4）。qcow2 是稀疏配置，宣告 40 GB 不等於當下就佔 40 GB |
| **磁碟匯流排** | **VirtIO**（不是 SATA／IDE） | 📄 效能差異明顯，而且它是虛擬化環境的標準介面。guest 裡會看到 `vtbd0` |
| **網卡型號** | **virtio**（不是 e1000／rtl8139） | 同上。guest 裡會看到 `vtnet0` |
| **CPU 型號** | **host-passthrough**（virt-manager 裡是「Copy host CPU configuration」） | 📄 最快、而且 guest 看得到 host 的完整指令集。⚠️ 代價是「不能遷移到不同型號的 CPU」，**這件事在這裡完全不重要** |
| **韌體** | **BIOS（SeaBIOS）或 UEFI（OVMF）都可以** | ❓ 我沒有實測 FreeBSD 在兩者下的安裝差異。**BIOS 的活動零件比較少**，除非你想順便練 UEFI，否則選預設 |
| **顯示** | 預設即可 | 這是伺服器，主控台只用來裝系統。裝完就 ssh 進去 |

### 2.3 ⚠️ virtio 在 FreeBSD 安裝階段需不需要額外動作

📄 **依文件推論：不需要。**
virtio 的驅動（`virtio`、`virtio_pci`、`vtnet`、`virtio_blk`）
**自 FreeBSD 9.2／10.0 起就編進 GENERIC 核心**，
而你要裝的是 15.x 或 14.x。所以 `bsdinstall` 應該直接看得到 `vtbd0` 這顆磁碟
與 `vtnet0` 這張網卡，不需要「先用 SATA 裝完再換 virtio」那套老流程
（那是 FreeBSD 9.0 時代的作法，網路上還查得到，**看到了不要照做**）。

❓ **我沒有實測。** 驗收方式在安裝程式的第一頁就看得到：

- 分割區那一步**列不出任何磁碟** → virtio-blk 沒認到 → 先把磁碟匯流排改成 SATA
  把系統裝起來，再依 `/boot/loader.conf` 加 `virtio_blk_load="YES"` 之類的老方法處理。
- 網路設定那一步**列不出介面** → virtio-net 沒認到 → 同理，先換 e1000。

⚠️ **如果真的走了退路，請把它寫回這一節**——那正是這份文件存在的理由。

### 2.4 建立的實際步驟（virt-manager）

1. 下載 FreeBSD 的安裝映像（`FreeBSD-*-amd64-disc1.iso`）。
   ❓ **版本選哪一個我不替你決定**：`FREEBSD-DEPLOY.md` 的參考來源記著
   15.0-RELEASE 於 2025-12-02 發布、14.3 已於 2026-06-30 EOL。
   ⚠️ **重點是「與學校那台同一個版本」**，因為 §10.1 的第一列
   （相依套件走哪條路線）**只有在版本相同時才帶得走**。
2. virt-manager → 「Create a new virtual machine」→ Local install media → 選 ISO。
   ⚠️ OS 型別偵測不到 FreeBSD 的話手動選；偵測錯了只影響預設值，不影響能不能跑。
3. 記憶體與 CPU 照 §2.2。
4. 磁碟：**qcow2**、容量照 §2.2。
5. **勾「Customize configuration before install」**——這一步不勾的話，
   下面兩項要裝完再回頭改：
   - **CPUs → Copy host CPU configuration**（host-passthrough）
   - **Disk → Advanced options → Disk bus: VirtIO**
   - **NIC → Device model: virtio**
   - **Network source: `Virtual network 'default': NAT`**（§3.1，通常已經是預設）
6. Begin Installation。

---

## 3. 網路模式：NAT，而且這是最終方案

**先講結論，再講理由：**

> **用 libvirt 預設的 NAT（`virbr0`），不做橋接、不做埠轉發。**

⚠️ **這在 v0.20 是一個決定，不是一個「先這樣試試看」**（PLAN D44）：
老師已經確定**只從 Ubuntu host 測試虛擬機裡的站台**，macOS 那台不接進來
（§1.6 之後也不需要接進來了）。**用戶端就是 host 自己**，而 NAT 正好
把這件事做到最好。

因此 §3.2 與 §3.3 的定位要看清楚：**它們是附註，不是選項。**
§3.2 說明「為什麼不必去碰橋接」，§3.3 是「萬一日後真的需要讓別台機器連入」
的備忘——**這次不做，而且不需要為了它預先設計任何東西**。

### 3.1 為什麼是 NAT

📄 libvirt 安裝時會自動建一個叫 **`default`** 的虛擬網路：
一座**不接任何實體網卡**的橋 **`virbr0`**，網段 **`192.168.122.0/24`**，
host 那一端是 **`192.168.122.1`**，內建的 dnsmasq 在
**`192.168.122.2`–`192.168.122.254`** 配發 DHCP，對外走 NAT + forwarding。

這個模式對這次測試**剛好完美**，理由有三個，而第二個是決定性的：

1. **不用設定任何東西。** 它是預設值。
2. ⚠️ **Ubuntu host 本來就連得到 guest**（`192.168.122.x`），
   而**這次的測試用戶端就是 host 自己**。
3. ⚠️⚠️ **因此完全避開了「WiFi 沒辦法做傳統橋接」這個坑**，見 §3.2。

**代價**：家用網路上的**其他**機器連不到 guest。
⚠️ **而在 v0.20 之後，這個代價是零**——唯一曾經需要連進來的那台 macOS，
它的用途（Safari 驗收）已經隨 D45 取消了（§1.6）。
**這一格從「取捨」變成了「沒有取捨」。**

### 3.2 ⚠️ 附註：為什麼不必去碰橋接

**這一節不要求你做任何事。** 它存在的理由只有一個：
virt-manager 的網路下拉選單裡有「Bridge device」與「Macvtap device」，
而半夜看到它們的時候，人會想「橋接比較像真的網路，是不是該用那個」。
**答案是不該，而且理由不只是懶。**

（v0.19 這一節是三個並列選項的比較表；v0.20 老師定案只從 host 測試之後，
它降為附註——**但表格留著，因為它回答的正是「那我為什麼不用橋接」。**）

**如果你的 Ubuntu 走的是 WiFi**（多數筆電的情況），那麼：

- 📄 **傳統的軟體橋接（把 `wlan0` 加進 `br0`）在 WiFi 上做不到。**
  802.11 的資料框只有三個位址欄位，一個連上 AP 的 station
  **不能代表其他 MAC 位址發框**；AP 會丟掉來源位址沒有向它認證過的框。
  Linux 核心因此**直接禁止**把 managed 模式的無線介面加進橋。
  （有一個 4-address 模式可以做到，但**兩端都要支援並協商**，
  你家的路由器多半不支援——這不是一個值得花時間的方向。）
- **於是 virt-manager 會建議你用 macvtap**（「Macvtap device」或
  「Bridge device… 」以外的那個直連選項）。**它在 WiFi 上也常常不行**
  （同一個 MAC 位址問題），❓ 而且是否可行取決於驅動與 AP，我無法預測。
- ⚠️⚠️ **而且就算它可行，你也會失去這次測試最需要的東西**：
  📄 **macvtap 之下，guest 連不到自己的 host、host 也連不到 guest。**
  這不是 bug，是 macvtap 的定義行為——guest 的流量被轉發到實體介面之後
  **彈不回 host 的 IP 堆疊**，反過來也一樣。區網上的**其他**機器連得到，
  **只有 host 連不到**。

**把三件事並排就看得很清楚：**

| 模式 | host 連得到 guest？ | 區網其他機器連得到？ | WiFi 上可行？ |
|---|---|---|---|
| **NAT（`virbr0`）← 建議** | ✅ 是（`192.168.122.x`） | ❌ 否（要 §3.3） | ✅ 是（與實體介面無關） |
| **macvtap** | ❌ **否（已知限制）** | ✅ 是 | ⚠️ 常常不行 |
| **軟體橋接 `br0`** | ✅ 是 | ✅ 是 | ❌ **否（802.11 限制）** |

> **一句話**：**要「host 連得到」又要「其他機器連得到」，只有 `br0` 做得到，
> 而 `br0` 需要有線網路。** 這次測試的用戶端是 host 自己，
> **而且只有 host 自己**（D44）——所以 NAT 不是妥協，它是這三個裡唯一
> 完全符合需求的那一個。

📄 **macvtap 那個限制有官方的解法**（在 host 上另外建一個 macvtap 介面、
或給 guest 加第二張接到隔離網路的網卡），**但那是「為了修好一個你本來就不需要的模式」
而多裝的兩個零件**。不建議。

### 3.3 附註：如果日後真的要讓別台機器連進來

> ⚠️ **這一節這次不做。** 它在 v0.19 是「怎麼把 macOS 接進來」的正文；
> v0.20 之後那個需求不存在了（D44 只從 host 測試，D45 取消 Safari 驗收）。
> 留著是因為**「日後需要」是真的可能發生的**——例如某天想讓助教在自己的
> 機器上看一眼。**但不要為了這個可能性預先做任何設定。**

三條路，由簡到繁。⚠️ **三條我都沒有實測。**

**(a) SSH 通道——最簡單，不動任何防火牆** 📄

在那台 Mac 上：

```sh
# 把 Mac 的本機 443 轉到 guest 的 443（綁 <1024 的埠要 sudo）
sudo ssh -N -L 443:192.168.122.50:443 you@<ubuntu-host-的區網IP>
```

Mac 的 `/etc/hosts` 就寫 `127.0.0.1 engmath.home.arpa`。
✅ **好處**：不用碰 iptables、不用改 libvirt、關掉通道就完全復原。
SNI 送出去的仍然是 `engmath.home.arpa`，所以憑證與虛擬主機都對得上。
⚠️ **注意**：這條路**只服務那一台 Mac**，而且通道斷了就全斷，
所以它適合 §1.6 那種「開著做半小時驗收」的用途，不適合長時間掛著。

**(b) NAT + 在 Ubuntu 上做埠轉發（DNAT）** ❓ **未驗證**

概念是在 host 上把「打到 host 443」的封包 DNAT 到 `192.168.122.50:443`。
📄 兩個必要條件常被忘記：**（i）** DNAT 要同時處理
`nat/PREROUTING`（從外面進來的）；**（ii）** libvirt 預設的 `FORWARD` 規則
只放行 `RELATED,ESTABLISHED`，**新連線要另外放行**，否則規則看起來對但連不通。

```sh
# ⚠️ 未驗證，而且會與 libvirt 自己管理的規則互動。先在快照／可還原的狀態下試。
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A PREROUTING -p tcp --dport 443 \
     -j DNAT --to-destination 192.168.122.50:443
sudo iptables -I FORWARD -p tcp -d 192.168.122.50 --dport 443 \
     -m conntrack --ctstate NEW,RELATED,ESTABLISHED -j ACCEPT
```

⚠️ **這些規則重開機就沒了**（要 `iptables-persistent` 或寫成
libvirt 的 `/etc/libvirt/hooks/qemu` 鉤子）。
⚠️ **Ubuntu 上還有 ufw 與 nftables 兩層可能插手**，症狀是「規則加了但沒作用」。
⚠️ **libvirt 自己在網路啟動／停止時會重寫規則**，你的規則可能被洗掉。
**這條路的複雜度明顯高於 (a)，而它買到的東西這個階段用不到。**

**(c) 有線 + 真正的軟體橋接 `br0`** 📄

把 Ubuntu 插網路線，用 netplan 建一座 `br0` 把 `enp*s*` 放進去，
virt-manager 的網路來源選「Bridge device: br0」。
✅ guest 直接拿家用路由器配發的 `192.168.1.x`，**host 與區網所有機器都連得到**，
而且**最接近正式部署的網路拓樸**。
⚠️ 代價：要有線；改動的是 host 的日常網路設定（設錯會斷網，而你正在用它）；
筆電拔線移動時會需要再切回去。

> **取捨一句話**：臨時驗收用 (a)，長期兩用（自己測 + 別台機器連）用 (c)，
> **(b) 只在「必須無線、又必須讓別台機器連」時才值得**——而那個組合這次不存在。

### 3.4 查出 guest 拿到的 IP

三個來源，由可靠到將就 📄：

```sh
export LIBVIRT_DEFAULT_URI=qemu:///system

# (1) 從 libvirt 的 DHCP 租約查（預設來源，guest 不用裝任何東西）
virsh domifaddr freebsd-engmath
virsh domifaddr freebsd-engmath --source lease

# (2) 直接看 default 網路的租約表（guest 還沒起來也看得到歷史）
virsh net-dhcp-leases default

# (3) 從 host 的 ARP 表反推（(1)(2) 都空的時候的退路）
virsh domifaddr freebsd-engmath --source arp
ip neigh | grep 192.168.122

# (4) 最土但最可靠：在 guest 的主控台裡
ifconfig vtnet0
```

❓ **`--source agent` 需要 guest 裡跑 `qemu-guest-agent`**，
FreeBSD 的 pkg 裡有沒有、好不好用我沒有查證。**這次不需要它。**

⚠️ **DHCP 會換位址。** guest 重開機或 `default` 網路重啟之後可能拿到不同的 IP，
而症狀是「昨天好好的，今天連不上」。📄 在 libvirt 裡釘住它：

```sh
# 先查 guest 網卡的 MAC
virsh domiflist freebsd-engmath

virsh net-edit default
```

在 `<dhcp>` 區塊裡加一行（**位址要落在 `<range>` 外面或裡面都可以，
但不要與別的保留撞號**）：

```xml
<host mac='52:54:00:xx:xx:xx' name='engmath' ip='192.168.122.50'/>
```

```sh
virsh net-destroy default && virsh net-start default   # ⚠️ 會斷所有 guest 的網路
```

> 💡 **這一步值得做**，因為它同時模擬了正式部署「這台機器有固定 IP」這個前提，
> 而且讓 §5 的 `/etc/hosts` 那一行只需要寫一次。

---

## 4. FreeBSD guest：從零開始

> 📄 **整段都是依文件推論。** `bsdinstall` 與 `sysrc` 的用法來自官方 Handbook，
> 但我沒有在任何一台 FreeBSD 上跑過任何一步。

### 4.1 裝完 FreeBSD 之後的最小設定

安裝時的建議選擇：

- **檔案系統**：**UFS 比較省事**（記憶體需求低，見 §2.2）。
  ZFS 多一個 `FREEBSD-DEPLOY.md` §5.5 提到的快照玩法，
  ⚠️ 但**你已經有 hypervisor 層的快照了（§7），兩層快照是多餘的**，
  而且會讓「還原到哪一個」變複雜。**除非你想順便練 ZFS，否則選 UFS。**
- **套件**：`ports` 不必要（我們用 `pkg`）；`src` 不必要。
- **服務**：勾 `sshd`（等一下都從 host 上 ssh 操作會舒服得多）、
  **`ntpd`（⚠️ 這一項在虛擬機裡比在實體機上更重要，見 §4.4）**。
  ⚠️ **省電相關的項目一個都不用勾**——虛擬機沒有電池，`powerd` 在這裡沒有意義。
- **使用者**：建一個你自己的帳號，加進 `wheel` 群組（才能 `su`）。

裝完之後：

```sh
pkg update && pkg upgrade -y
pkg install -y git curl sudo
visudo        # 取消 %wheel ALL=(ALL:ALL) ALL 那一行的註解
```

### 4.2 確認 virtio 真的在用

```sh
# 磁碟應該是 vtbd0（不是 ada0／da0）
geom disk list
mount | head -3

# 網卡應該是 vtnet0（不是 em0／re0）
ifconfig vtnet0
```

⚠️ **看到 `ada0` 或 `em0` 就代表 §2.2 那兩個下拉選單有一個沒改到**，
效能會差一截。**現在改比裝完一堆東西之後再改容易**（關機 → virt-manager 改 → 開機）。

### 4.3 取得 IP

```sh
ifconfig vtnet0
```

```
vtnet0: flags=8863<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> ...
        inet 192.168.122.50 netmask 0xffffff00 broadcast 192.168.122.255
```

`192.168.122.50` 就是你要填進 host `/etc/hosts` 的位址（§5.1）。
釘住它的方法見 §3.4。

### 4.4 ⚠️ 時間同步（虛擬機比實體機更需要這一節）

**為什麼要緊**：guest 的時鐘在虛擬機裡容易漂——host 睡眠、暫停／恢復、
CPU 超賣都會讓 guest 少算或多算時間。而這個系統有**兩件事直接靠時間**：

1. **TLS 憑證的生效與過期**。⚠️ 時鐘差太多的症狀是
   「憑證還沒生效」或「憑證已過期」，**而那個錯誤訊息長得完全不像時間問題**。
   正式部署那邊更嚴重：`FREEBSD-DEPLOY.md` §4.3 的 IP 憑證是**六天一期**。
2. **log 的時戳**。時戳錯了，`app.log` 與代理 log 對不起來，而**除錯時你會相信它**。

📄 作法（`/etc/rc.conf`）：

```sh
sysrc ntpd_enable=YES
sysrc ntpd_sync_on_start=YES     # ⚠️ 這一行是重點，見下面
service ntpd start

# 看一眼
date
ntpq -p          # 應該看得到幾個 peer，前面有 * 或 + 的表示同步上了
```

⚠️ **`ntpd_sync_on_start=YES` 在虛擬機上不是可選的。**
📄 `ntpd` 的設計是**連續微調而不跳時**，偏差太大時它會**印一行錯誤然後結束**
（傳統上的門檻是 1000 秒）。而 guest 從快照還原回來，
時間可能一口氣差了好幾天——**於是 ntpd 開機就死掉，而你不會注意到**，
直到某天 TLS 開始報一個看不懂的錯。這一行讓它在啟動時允許直接把時鐘拉正一次。

❓ **未查證**：FreeBSD 在 KVM 上會不會使用 kvmclock 當 timecounter
（那會讓漂移小很多）。**看得出來的方式**：

```sh
sysctl kern.timecounter.choice
sysctl kern.timecounter.hardware
```

看到 `kvmclock` 就是有；看到 `ACPI-fast`／`HPET`／`TSC-low` 就是沒有。
**兩種情況下上面那兩行 rc.conf 都要設**，所以這一項不影響行動。

> 💡 **從快照還原之後養成一個習慣**：`date` 看一眼。
> 這比事後查一個「憑證莫名其妙無效」的問題便宜太多。

### 4.5 Python 與相依套件

**照 `FREEBSD-DEPLOY.md` §3.4 的建議：先試路線 A（全部用 pkg），跑 `pytest`，
綠燈就收工。**

⚠️ **動手之前先存一個快照**（§7.3 第 2 點）——這一步失敗的話，
你要的是一個乾淨的系統重來，不是一個裝了半套的系統（§1.3）。

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

路線 A 不行的話，**先還原快照**，再依 §3.4 的分流：
**紅在 SymPy 相關 → 路線 C；紅在別處 → 路線 B**。
路線 B 需要 `pkg install rust pkgconf libffi gmake`，⚠️ 而 Rust 在磁碟上是 GB 級的
——這就是 §2.2 說「可能走路線 B 就給 40 GB」的原因。`df -h` 先看一眼。

### 4.6 專用使用者、目錄、程式碼

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

### 4.7 跑測試（這一步就是「這台機器能不能用」的證明）

```sh
pkg install -y py311-pytest py311-httpx node22
cd /usr/local/www/engmath-practice
python3.11 -m pytest -q
```

**預期 437 項全過。** 沒有 node 的話展示區的 JS 測試會 skip 並印出原因
（那是刻意的，不是壞掉）。

> ⚠️ **這一步紅了就先停下來，不要往下走。** 後面每一步都假設應用程式本身是對的；
> 帶著紅燈往下架，你會分不清楚問題出在 FreeBSD、Caddy 還是程式。

### 4.8 建立兩組帳號

```sh
env PRACTICE_DB=/var/db/engmath/practice.db \
    python3.11 scripts/create_accounts.py init
chown engmath:engmath /var/db/engmath/practice.db
```

密碼**只印這一次**（資料庫裡只有 argon2id 雜湊）。抄下來。忘了也沒關係，
`reset` 隨時可以換一組。

---

## 5. 假網域：`engmath.home.arpa`

### 5.1 為什麼是 `home.arpa` 而不是 `.local`

**建議用 `engmath.home.arpa`。**

- 📄 **`.local` 是 RFC 6762（mDNS）保留給鏈路本地多播名稱解析用的**。
  Linux 上 Avahi／systemd-resolved 會把它導向 mDNS，macOS 的 `mDNSResponder` 更是
  直接攔下來。`/etc/hosts` 通常仍然優先，❓ **但「通常」不是「一定」**——
  這是一個你不需要去搞清楚的變數，而且它壞掉的症狀是「有時候通有時候不通」，
  那是最難查的一種。
- 📄 **`home.arpa` 是 RFC 8375 指定給住宅／家用網路的特殊用途名稱**，
  設計上就是給「這個網路裡的名字」用的，而且**不是 mDNS**。

**還有一個與正式部署對齊的理由**：學校那邊會是
`engmath.ntnu.edu.tw`——一個普通的、走一般 DNS 解析的名字。
`home.arpa` 的行為與它比較接近，`.local` 不是。

> ❓ 退路是隨便一個你確定不存在的名字（例如 `engmath.test`——📄 `.test` 是
> RFC 2606 保留給測試用的 TLD，永遠不會被真的註冊）。
> **不要用一個真的網域**，理由見下面的 ⚠️。

在 **Ubuntu host** 上：

```sh
sudo nano /etc/hosts
```

加一行（位址是 §4.3／§3.4 那一個）：

```
192.168.122.50    engmath.home.arpa
```

Ubuntu 通常不需要清快取（`/etc/hosts` 由 glibc 直接讀）。
用 systemd-resolved 而且不放心的話：`sudo resolvectl flush-caches`。

驗一下：

```sh
ping -c 2 engmath.home.arpa
getent hosts engmath.home.arpa
```

> ⚠️ **不要在 `/etc/hosts` 裡把真的 `engmath.ntnu.edu.tw` 指到虛擬機。**
> 很誘人（測試路徑會 100% 一樣），但代價是：測完忘了刪那一行，
> 有一天你在校內連正式站台，連到的是一個不存在的 `192.168.122.50`，
> 然後開始查一個不存在的網路問題。**測試用的假名字要一眼看得出是假的。**

### 5.2 FreeBSD 端：Caddy 與 `tls internal`

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
    # ⚠️ 這一行就是 §8 檢查表第 20 項要驗的東西，不要為了除錯改掉它——
    #    真的要除錯的話，驗完第 20 項再改，改完再驗一次。
    log {
        output discard
    }
}

# ← 差別 2：正式版這裡還有校內 IP 的允許清單（§5.8）。
#    家裡沒有校內網段，所以整段不放。要練語法的話見 §8 檢查表第 21 項。
```

```sh
sysrc caddy_enable=YES
service caddy start
service caddy status
```

📄 **Caddy 會自動開一個 :80 的伺服器做 HTTP→HTTPS 轉址**，所以 §8 檢查表第 14 項
不需要額外設定。

### 5.3 Ubuntu host 上要不要信任那張憑證

**這是一個判斷題，我的建議是：只在瀏覽器的信任庫裡加，不要加進系統信任庫，
而且測完就刪。**

先講**不建議加進系統信任庫的理由**（與 v0.19 對 macOS 的論證一字不改，
因為它與作業系統無關）：

`tls internal` 用的是 **Caddy 在那台 guest 上自己產生的一個根 CA**，
而**那個 CA 的私鑰就躺在虛擬機的檔案系統上**。把一個根 CA 加進系統信任區，
等於宣告「**任何持有那把私鑰的人，可以為任何網域簽一張我的筆電會相信的憑證**」
——不只是 `engmath.home.arpa`，什麼都可以。而**你的 Ubuntu 筆電是你日常在用的機器，
會帶去別的地方**。

⚠️ **虛擬機在這裡讓風險看起來變小了，但只小了一點**：那把私鑰確實關在 guest 裡，
但 guest 的磁碟檔就在 host 上，而且你剛剛才在上面 `git clone` 與 `pkg install`。

三個選項，由好到壞：

1. **✅ 建議：只加進瀏覽器自己的信任庫，測完刪掉。**
   Firefox 與 Chrome 在 Linux 上**各自有自己的憑證庫**，不一定讀系統的那一份
   （❓ Chrome 版本之間行為有變化，Ubuntu 的 snap 版 Firefox 又是另一回事，
   我沒有實測）。**好處正好是這個隔離**：影響範圍限於那一個瀏覽器設定檔。

   ```sh
   # 1) 從 guest 把 Caddy 的根憑證抄出來
   #    ❓ 路徑取決於 caddy 服務的 HOME／XDG_DATA_HOME，FreeBSD port 的設定我沒有查證。
   #       先在 guest 上找：
   find / -name 'root.crt' -path '*caddy*' 2>/dev/null
   #    典型會長成 .../caddy/pki/authorities/local/root.crt

   # 2) 在 Ubuntu host 上抄過來
   scp you@192.168.122.50:/path/to/root.crt ~/caddy-homelab-root.crt
   ```

   - **Firefox**：設定 → 隱私權與安全性 → 憑證 → 檢視憑證 → 憑證機構 → 匯入
     → 勾「信任這個 CA 以識別網站」。**刪除也在同一頁。**
   - **Chrome**：設定 → 隱私權和安全性 → 安全性 → 管理憑證 → 授權單位 → 匯入。
     ❓ 較新的版本改用系統／自有的信任庫，選單位置與行為我沒有實測。
     命令列的路是 `certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n caddy-homelab -i ~/caddy-homelab-root.crt`
     （`apt install libnss3-tools`），❓ 一樣未實測。

2. **⚠️ 可接受：什麼都不裝，每次點過瀏覽器的警告。**
   最安全，但**它會訓練出一個壞習慣**——而這個專案的 `FREEBSD-DEPLOY.md` §4.4
   正好因為同一個理由拒絕在正式站台用自簽憑證
   （「教學生按過瀏覽器的安全警告，會直接抵銷 `_about.html` 那句安全告誡」）。
   在**你自己的**測試機器上按警告不會傷到學生，但它會讓 §8 檢查表第 13、15 項
   多幾次點擊。
   ⚠️ **而且它會弄髒 §1.2 第 13 項（展示區）**：一個「不受信任」的 HTTPS 頁面
   ❓ 在某些瀏覽器行為上與正常的 HTTPS 不完全一樣，
   **而那正是你想驗的東西**。要驗展示區就選 1。

3. **❌ 不建議：`sudo cp ... /usr/local/share/ca-certificates/ && sudo update-ca-certificates`。**
   理由如上。**不要因為它比較快就做這一個。**

> 💡 **另一條路，如果你不想碰根 CA**：用 `openssl` 自己簽一張**只給
> `engmath.home.arpa` 用的葉憑證**（帶 SAN），只信任**那一張**。
> 葉憑證不能拿去簽別的網域，所以上面那個風險整個消失。
> 代價是 Caddyfile 要從 `tls internal` 改成 `tls /path/cert.pem /path/key.pem`
> ——**離正式部署的設定又遠了一步**，而這次測試的目的正是「路徑要一樣」。
> ❓ 我沒有實測。

---

## 6. 啟動應用程式與 rc.d 服務

### 6.1 先手動跑一次

**這一步花三十秒**，省下的是「rc.d 起不來的時候，不知道問題在 rc.d 還是在程式」。

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
登入要從 host 走 `https://engmath.home.arpa`。

> ⚠️ **順帶一個 §1.8 的提醒**：`http://127.0.0.1:8000` 上**展示區會正常運作**
> （localhost 算安全脈絡），所以**不要用這個網址去判斷「純 HTTP 行不行」**。
> 那個問題的答案在 §1.8，而本機測試永遠會給你錯的那一個。

確認 `/healthz` 通了就 `Ctrl-C`，交給 rc.d。

### 6.2 rc.d 腳本

> **這一份與 `FREEBSD-DEPLOY.md` §5.2 是同一支腳本**，
> 已經含 v0.19 修掉的三處（`-u`、`procname`、`-H`）。
> **在家裡跑一次的意義就是把那三處從「📄 依文件推論」變成「✅ 已驗證」。**

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

```sh
chmod 555 /usr/local/etc/rc.d/engmath
sysrc engmath_enable=YES
service engmath start
```

### 6.3 ⚠️ 驗那三處修正（這一節是本文件存在的理由之一）

```sh
# ── (a) service status 說得出 pid 嗎 ────────────────────────
service engmath status
#    預期：engmath is running as pid NNNN.
#    ⚠️ 說「is not running」而網頁又打得開 → procname 對不上（v0.19 修的第 2 處）

# ── (b) 它是以 engmath 執行的嗎，不是 root ──────────────────
ps -o user,pid,command -p "$(cat /var/run/engmath.pid)"
#    預期 USER 欄是 engmath、COMMAND 是 /usr/sbin/daemon ...
#    ⚠️ USER 是 root → `-u` 沒生效（v0.19 修的第 1 處）

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

### 6.4 重開機測試

```sh
shutdown -r now
```

⚠️ **重開的是 guest，不是 host。** virt-manager 的視窗會看著它重新開機。

開回來之後（從 host `ssh` 進去就好）：

```sh
service engmath status
fetch -qo - http://127.0.0.1:8000/healthz
service caddy status
date                       # ⚠️ 順便看一眼時鐘（§4.4）
```

> ⚠️ **這一項一定要真的重開機，不能用 `service engmath restart` 代替。**
> 兩者驗的是不同的事：`restart` 驗腳本，重開機驗 `rc.conf` 的 `_enable`、
> `REQUIRE: LOGIN` 的啟動順序、以及開機時 `/var/run` 是空的這件事。
> **開機順序的問題只有在真的開機時才會出現。**
>
> 💡 **虛擬機在這裡有一個實體機沒有的好處**：這一項可以**重複做**。
> 有了快照（§7），「改一行 → 還原 → 重開機 → 看結果」是一個三分鐘的循環，
> 而不是一次只能賭一把。

---

## 7. 🆕 快照：虛擬機相對實體機最大的優勢

### 7.1 為什麼這一節是必讀的

見 §1.3：快照把幾項**一次性的賭注**變成**可重複的實驗**，
而「可重複」直接決定了結論帶不帶得到學校去。

最適合快照的三種情境，剛好是這次測試的三個重點：

1. **「重開機之後 rc.d 服務會不會自動起來」**——`sysrc` 改一行、還原、再開機一次。
2. **「相依套件裝壞了」**——路線 A 失敗，**還原成乾淨系統**再試路線 B（§4.5）。
3. **「pf 把自己鎖在外面」**——還原就好（§9.2）。⚠️ 而且虛擬機這裡還多一層保險：
   virt-manager 的主控台**不經過網路**，鎖住了照樣進得去。

### 7.2 ⚠️ 前提：磁碟必須是 qcow2

📄 **內部快照（連記憶體狀態一起存在磁碟檔裡的那種）只有 qcow2 支援，raw 不支援。**
§2.2 建議 qcow2 就是為了這一節。已經建成 raw 的話：

```sh
# guest 要先關機
qemu-img convert -f raw -O qcow2 disk.img disk.qcow2
# 然後 virsh edit <domain>，把 <driver type='raw'/> 改成 'qcow2'、source 換掉
```

❓ 未實測。**建之前選對比較省事。**

### 7.3 建議在這四個時間點各存一個

| 快照名 | 時間點 | 為什麼 |
|---|---|---|
| `01-clean-install` | FreeBSD 裝完、`pkg upgrade` 完、sshd 與 ntpd 設好，**還沒裝任何相依套件** | ⚠️ **這一個最重要**：路線 A／B／C 的比較必須從同一個乾淨起點出發（§1.3） |
| `02-deps-ok` | `pytest` 437 項全綠之後 | 後面 Caddy／rc.d 搞砸了不用重裝 python |
| `03-service-ok` | rc.d + Caddy 都通、`https://engmath.home.arpa` 看得到登入頁 | 這是「已知良好」的基準線，§8 檢查表從這裡開始跑 |
| `04-before-pf` | 動 pf 或 §8 第 21 項的允許清單之前 | 那兩件事是唯二會把自己鎖在外面的 |

### 7.4 兩種作法

**virt-manager（圖形介面）**：

左側選中虛擬機 → 工具列最右邊的「Show virtual machine snapshots」（相機圖示）
→ `+` 新增，給名字與說明 → 要還原時選中它按「Run selected snapshot」。

⚠️ **guest 在執行中建的快照會連記憶體一起存**（還原後回到「當時那一秒」）；
**關機狀態建的只有磁碟**（還原後是關機狀態）。
📄 兩種都有用，但**§7.3 那四個建議在關機狀態下建**——乾淨、小、而且沒有
「還原之後時鐘停在三小時前」那個問題（§4.4）。

**`virsh`（命令列）**：

```sh
export LIBVIRT_DEFAULT_URI=qemu:///system

# 建（--disk-only 只存磁碟；不加就會連記憶體一起，guest 執行中時）
virsh snapshot-create-as freebsd-engmath 01-clean-install \
      "FreeBSD 裝完、pkg upgrade 完、還沒裝相依套件"

# 列
virsh snapshot-list freebsd-engmath

# 還原
virsh snapshot-revert freebsd-engmath 01-clean-install

# 刪（⚠️ 快照會佔空間，測完記得清）
virsh snapshot-delete freebsd-engmath 04-before-pf
```

⚠️ **空間**：含記憶體的快照，每一個大約多吃「配置給 guest 的記憶體」那麼多。
給了 4 GB 記憶體又存了四個含記憶體的快照，就是 16 GB。
**這是 §2.2 建議磁碟給大一點的另一個原因。**

⚠️ **還原之後第一件事是 `date`**（§4.4）。

---

## 8. 驗收檢查表

逐項打勾。**第 20 項是這整份文件最重要的一項**（它是 PLAN §7 #40 唯一的驗收方式）。

### 虛擬機與網路

- [ ] **1.** `grep -c -E '(vmx|svm)' /proc/cpuinfo` 不是 0，`ls -l /dev/kvm` 看得到，
      `kvm-ok` 說 OK
- [ ] **2.** 虛擬機建好，**磁碟 virtio（guest 裡是 `vtbd0`）、網卡 virtio（`vtnet0`）、
      CPU host-passthrough、磁碟格式 qcow2**（§2.2、§4.2）
- [ ] **3.** 網路來源是 **`Virtual network 'default': NAT`**，
      `virsh domifaddr` 查得到 `192.168.122.x`，host `ping` 得到（§3.1、§3.4）
- [ ] **4.** 在 libvirt 的 `default` 網路裡做了 DHCP 保留（重開機之後 IP 不變，§3.4）

### 機器與相依

- [ ] **5.** 存了 `01-clean-install` 快照（§7.3）⚠️ **在裝相依套件之前**
- [ ] **6.** 相依套件裝好（記下走的是路線 A／B／C，**以及撞到什麼**）
- [ ] **7.** `pkg info | grep py311-` 確認 **sympy 是 1.14.x、pydantic 是 2.x**
- [ ] **8.** `python3.11 -m pytest -q` → **437 項全過**（node 缺的話 JS 那批 skip）
- [ ] **9.** `sysrc ntpd_enable ntpd_sync_on_start` 兩個都是 YES，`ntpq -p` 有同步（§4.4）

### 權限與帳號

- [ ] **10.** `engmath` 使用者存在且是 `nologin`：`pw usershow engmath`
- [ ] **11.** `ls -ld /var/db/engmath` → `drwx------  engmath engmath`（0700）
- [ ] **12.** `ls -l /var/db/engmath/practice.db*` → **三個檔**（含 `-wal`、`-shm`）
      都在 0700 的目錄裡，主檔 0600
- [ ] **13.** `ls -l /usr/local/etc/engmath/session_secret` → `-r--------` `engmath`（0400）
- [ ] **14.** `create_accounts.py init` 印出兩組密碼，且 **`grep` 整個 DB 檔案找不到明碼**
      （`strings /var/db/engmath/practice.db | grep <那組密碼>` → 沒有東西）

### 服務

- [ ] **15.** §6.3 的 (a)–(e) 五項全過（**特別是 (b)：不是 root**）
- [ ] **16.** §6.4 **guest 重開機**之後 `engmath` 與 `caddy` 都自動起來了，
      而且 `date` 是對的

### 網路與 HTTPS（用戶端是 Ubuntu host 的瀏覽器）

- [ ] **17.** host 上 `https://engmath.home.arpa` 看得到**登入頁**
- [ ] **18.** `curl -sI http://engmath.home.arpa | head -1` → **301／308 轉到 https**
- [ ] **19.** 用 `class` 密碼登入 → **進得到出題頁**
      （⚠️ 這一項證明 `COOKIE_SECURE=1` + 代理 + TLS 三者串得起來）
- [ ] **20.** 出一題 → `Show Answer` → `Show Solution Steps`，**兩層預設都是收合的**
- [ ] **21.** 開一個展示（`/demos`），**KaTeX 與 Canvas 都正常、按 `Start sound` 聽得到聲音**
      （這一項順便驗自架的靜態資產經過代理發得出去）
      ⚠️ **兩個瀏覽器都開一次**（Firefox 與 Chrome）——那是官方支援的全部，
      所以「兩個都對」在這裡等於結案（D45，§1.6）
- [ ] **22.** `class` 帳號開 `/activity` → **403，訊息說只給 staff**
- [ ] **23.** 登出，用 `staff` 密碼登入 → 頁首多一個 **Class activity**，點得進去

### ⚠️ 去識別化（這一項是重點）

- [ ] **24.** **代理層的 log 不含 IP。** 步驟：

  ```sh
  # (1) 在 Ubuntu host 上連幾次，製造一些流量
  for i in 1 2 3 4 5; do curl -sk -o /dev/null https://engmath.home.arpa/login; done

  # (2) ⚠️ 先想清楚「要找的位址」是哪一個。
  #     NAT 模式之下，guest 看到的來源是 virbr0 那一端，也就是 192.168.122.1
  #     ——**不是** host 在家用網路上的 192.168.1.x（§1.7 的那個陷阱）。

  # (3) 在 guest 上掃所有可能的 log 落點，找任何形如 IP 的字串
  grep -rE '[0-9]{1,3}(\.[0-9]{1,3}){3}' \
       /var/log/engmath/ /var/log/caddy/ /var/log/messages 2>/dev/null

  # (4) 特別針對 192.168.122.1 再找一次（上一步可能被 127.0.0.1 洗掉）
  grep -r '192.168.122.1' /var/log/ 2>/dev/null
  ```

  **預期：(4) 沒有任何東西。** (3) 可能會有 `127.0.0.1`
  （那是 Caddy 連到 uvicorn 的位址，不是使用者的），看到要能解釋得出來。

  > ⚠️ **這一項是整個去識別化設計裡唯一沒有測試守住的一環**
  > （應用層與 uvicorn 那兩層有五項測試，代理層在我們的行程外面）。
  > **在家裡做這一次，比在學校部署當天第一次做，安全得多**——
  > 因為家裡沒有真的學生的 IP 會被寫下來。
  > 對應 `FREEBSD-DEPLOY.md` §5.7 與 **PLAN §7 #40**。
  > ⚠️ **但它不結案 #40**：學校那台的設定檔會多一段允許清單（§5.8），
  > 而那正是最可能讓人「暫時把 log 打開」的原因。**學校那邊要再做一次。**

### 長期運行的東西

- [ ] **25.** **newsyslog 輪替**：

  ```sh
  # 放好 /usr/local/etc/newsyslog.conf.d/engmath.conf（見 FREEBSD-DEPLOY.md §5.4）
  newsyslog -Nv          # 先 dry-run，看它打算做什麼
  newsyslog -F           # 強制輪替一次
  ls -l /var/log/engmath/
  #    預期：app.log 變成 app.log.0.bz2，並且有一個新的空 app.log

  for i in 1 2 3; do curl -sk -o /dev/null https://engmath.home.arpa/login; done
  ls -l /var/log/engmath/app.log
  ```

  ⚠️ **新的 `app.log` 大小是 0 就代表 `daemon -H` 沒有生效**
  （或者訊號欄寫錯了）。這正是 `FREEBSD-DEPLOY.md` §8 #7 那一項，
  **而這是它第一次被真的跑過**。修不好的話改走 syslog（`daemon -S -T engmath`）。

- [ ] **26.** **備份腳本**：放好 `FREEBSD-DEPLOY.md` §5.5 的 `backup.sh`，
      手動跑一次，確認 `/var/backups/engmath/` 有一個 0600 的檔，
      而且 `sqlite3 <備份檔> '.tables'` 讀得出 `account` 與 `usagelog`

### 🆕 瀏覽器支援（D45）

> ⚠️ **這一格在 v0.20 的草稿裡是「在 Safari 上驗收」。D45 之後不是那樣了：
> Safari 不支援，所以要驗的不是「它在 Safari 上對不對」，
> 而是「不支援的人有沒有真的被告知」。**

- [ ] **27.** ⚠️ **把那段「請用 Chrome 或 Firefox」的訊息逼出來看一次。**
      **你在 Chrome 與 Firefox 上永遠看不到它**——這正是它最可能悄悄壞掉的方式
      （改壞了，測試以外沒有任何東西會提醒你）。逼出來的方式，任選一個：

      1. **開發者工具 → Console**，貼上
         `document.getElementById('browser-notice').hidden = false;`
         `document.getElementById('browser-notice').textContent = 'x';`
         ——只驗**版面**（它在頁面上顯眼嗎？被捲軸推到看不到的地方了嗎？）。
      2. ⚠️ **更有價值的一種**：`http://` 開一次
         （在 guest 上把 Caddy 暫時指到 8000，或直接
         `http://192.168.122.50:8000` 從 host 連——**不是 localhost**）。
         **這會真的觸發能力偵測那一層**：非安全脈絡下 `AudioWorklet` 取不到
         （§1.8），訊息應該出現而且提到 https。
         **驗完把 Caddy 改回來，並重跑第 24 項。**

- [ ] **28.** 訊息出現時，確認它**沒有**遮住或推走 `Start sound` 按鈕，
      而且 Firefox 與 Chrome 上**確實一個字都沒有出現**
      （出現了就是白名單把自己人擋掉了——那是這個設計唯一的誤報方向）。

### 可選：語法練習（不結案任何一項）

- [ ] **29.** 在 Caddyfile 加上
      `@offcampus not remote_ip 192.168.122.0/24` + `error @offcampus "off campus" 403`
      與 `handle_errors 403 { ... }`，放一份 §5.8.4a 的 `offcampus.html`。
      ⚠️ **先讀 §1.7 的那個 NAT 陷阱**——你會發現「怎麼試都不被擋」，
      因為來源永遠是 `192.168.122.1`。要真的看到被擋的那一頁，
      把允許清單寫成一個**不含** `192.168.122.1` 的網段就好。
      **只驗到語法**；**驗不到**校內網段是否正確（PLAN §7 #42）與 VPN（#41）。
      ⚠️ **做完一定要把它從 Caddyfile 拿掉再驗一次第 24 項**——
      改設定檔正是第 24 項最可能被弄壞的方式。

### 收尾

- [ ] **30.** ⚠️ **把 §5.3 加進瀏覽器信任庫的那張根憑證刪掉。**
      ⚠️ **這一項最容易忘，而忘了的代價是你的筆電長期信任一台測試虛擬機上的 CA。**
- [ ] **31.** 把 host `/etc/hosts` 那一行刪掉（或註解）
- [ ] **32.** 清掉不再需要的快照（`virsh snapshot-list` → `snapshot-delete`），
      它們會佔掉「記憶體大小 × 快照數」的空間（§7.4）
- [ ] **33.** **把這次撞到的每一件事寫回 `FREEBSD-DEPLOY.md`**，
      並把對應的 📄／❓ 改成 ✅——見 §10.3

---

## 9. 實用提醒

### 9.1 ⚠️ 關掉 Ubuntu host 的睡眠（不做的話，你會 debug 一個假問題）

**這是家用測試最常見的鬼打牆**，而換成虛擬機之後它只是**換了一層**，沒有消失：
一切都設好了，你去吃個飯回來，瀏覽器連不上；ssh 也不通；`ping` 不回。
你開始查 FreeBSD、查 Caddy、查 rc.d——**而 host 只是睡著了，
把 guest 一起帶著暫停了**。

📄 在 Ubuntu 上：

```sh
# 圖形介面：設定 → 電源 → 自動暫停：關閉；螢幕熄滅可以留著
#（⚠️ 螢幕熄滅不等於睡眠，不要因為螢幕黑了就以為它睡了）

# 徹底一點（測試期間）：
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
# 還原：sudo systemctl unmask ...

# 闔蓋不睡：/etc/systemd/logind.conf
#   HandleLidSwitch=ignore
#   HandleLidSwitchExternalPower=ignore
sudo systemctl restart systemd-logind
```

❓ **`libvirt-guests` 這個服務會在 host 關機／睡眠時對 guest 做什麼
（暫停？存檔？直接關？），我沒有查證。** 它的設定在
`/etc/default/libvirt-guests`。**驗收方式很簡單**：闔蓋、等五分鐘、打開，
從 host `ping` 一下 guest，並在 guest 裡 `date` 看時鐘有沒有跳（§4.4）。

### 9.2 防火牆（pf，在 guest 裡）

家用測試**可以完全不開 pf**（你在兩層 NAT 後面）。
但如果你想順便練 `FREEBSD-DEPLOY.md` §5.8.2 的那份 `pf.conf`：

```sh
pfctl -nf /etc/pf.conf     # ⚠️ 一定先驗語法
```

⚠️ **動 pf 之前先存一個快照**（§7.3 的 `04-before-pf`）。
把自己鎖在外面的代價，在實體筆電上是「走過去掀開蓋子」，
**在虛擬機上是「還原快照」或「開 virt-manager 的主控台」——後者不經過網路，
所以你根本鎖不住自己**。這是虛擬機比實體機更適合練 pf 的地方。

### 9.3 Ubuntu host 上怎麼確認「連得到」

由淺到深，撞牆時照順序往下：

```sh
# 1) 網路層通不通
ping -c 3 192.168.122.50

# 2) 名字解析對不對（應該印出你填的那個 IP）
getent hosts engmath.home.arpa

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

> 💡 **5 通而 6 不通 = 憑證信任沒設好**（§5.3），不是伺服器的問題。
> 這個區分能省下很多時間。
> ⚠️ **注意 `curl` 讀的是系統信任庫，Firefox／Chrome 讀的是自己的**
> ——§5.3 建議只加進瀏覽器，所以**第 6 步「不通」是預期的**，
> 而瀏覽器上仍然是綠色的鎖頭。兩者不一致不是 bug。

### 9.4 其他零碎

- **磁碟**：guest 裡 `df -h`，host 上 `du -sh /var/lib/libvirt/images/`。
  路線 B 會拉進 Rust（GB 級），快照會吃記憶體大小 × 快照數（§7.4）。
- **從 host 操作 guest**：`ssh you@192.168.122.50`。
  比在 virt-manager 的主控台裡打字舒服得多，而且輸出可以複製貼上。
  ⚠️ 主控台留著當**鎖不住自己的後路**（§9.2）。
- ⚠️ **不要在 guest 裡直接編輯 repo 的檔案然後忘記**——
  那些改動不會回到你的 host 上，而下一次 `git pull` 會衝突。
  要改就在 host 上改、commit、在 guest 裡 `git pull`。
- **guest 的複製貼上**：virt-manager 的主控台預設沒有共用剪貼簿
  （❓ 要 spice-vdagent，FreeBSD 上可不可用我沒有查證）。
  **ssh 進去就沒有這個問題**，這是上一點的另一個理由。

---

## 10. 測完之後：哪些結論帶得走、哪些不行

### 10.1 ✅ 直接帶到學校的正式部署

| 這次驗到的 | 為什麼帶得走 |
|---|---|
| **相依套件走哪條路線、撞到什麼** | 與網路環境無關，只與 FreeBSD 版本有關。⚠️ **前提是學校那台的 FreeBSD 版本與 ports 樹相同**——版本不同就要重驗第 6–8 項 |
| **437 項測試在 FreeBSD + Python 3.11 上的結果** | 同上 |
| **rc.d 腳本**（含 `-u`／`procname`／`-H` 三處） | 純本機行為。**這是家用測試最大的一筆收穫**：它把 `FREEBSD-DEPLOY.md` §8 #6 與 #16 從「沒跑過」變成「跑過」 |
| **開機自動啟動** | 純本機 |
| **檔案權限與 `nologin` 服務帳號** | 純本機 |
| **newsyslog 輪替 + `daemon -H`** | 純本機。§8 #7 就此結案 |
| **Caddy 的反向代理設定、HTTP→HTTPS** | 設定檔可以整份帶過去，**只改兩行**（`tls internal` 拿掉、加上允許清單） |
| **應用程式在代理後面的行為**（`COOKIE_SECURE=1` 的登入流程） | 與憑證誰簽的無關 |
| **`log { output discard }` 的寫法有效** | 語法層面帶得走 |
| **🆕 virtio 磁碟與網卡在 FreeBSD 上的行為** | ⚠️ **這一項是 v0.20 才有的**，而且**只在學校那台也是虛擬機時才帶得走**——但那個機率不低（§1.0） |
| **🆕 `ntpd_sync_on_start` 的設定** | 純本機，而且**學校那台如果也是 VM，這一項同樣要緊**（§4.4） |
| **🆕 展示區在 Firefox 與 Chrome 上的行為** | 瀏覽器與伺服器無關，而 **Chrome 與 Firefox 就是官方支援的全部**（D45）——所以這一項在家裡就結案得掉，不必等正式部署 |
| **🆕 不支援瀏覽器的那段訊息**（D45） | 純前端。⚠️ 但**帶得走的只有「它顯示得出來」**——「Safari 上會不會顯示」帶不走，因為家裡沒有 Safari，而那件事**沒有人會去驗**（見 §10.2 最後一列） |

### 10.2 ⚠️ 必須在學校（或另外）重新驗證

| 項目 | 為什麼不能帶 | 在哪一節 |
|---|---|---|
| **代理層 log 不含 IP** | 語法帶得走，但**學校那台的 Caddyfile 會多一段允許清單**，而那正是最可能讓人「暫時把 log 打開」的原因。⚠️ **PLAN §7 #40 不因為家裡驗過就結案** | `FREEBSD-DEPLOY.md` §5.7、§5.8.6 (4) |
| **憑證**（Let's Encrypt、自動續期、六天一期的 IP 憑證） | 家裡是自簽。**這一項的失敗模式是「第六天才壞」** | §4.2–§4.4 |
| **校內 IP 允許清單擋得住** | 家裡沒有校內網段。⚠️ **而且 NAT 讓「來源位址」與你的直覺不同**（§1.7） | §5.8.6 (1)(2) |
| **允許清單有沒有誤傷應用程式的 403** | 家裡沒放允許清單（除非做了第 29 項，而那是不同的網段） | §5.8.6 (3) |
| **⚠️⚠️ VPN 的來源位址**（PLAN §7 #41） | **完全模擬不到**，而且猜錯會讓被擋頁面對學生說謊 | §5.8.5 的三步 |
| **DNS**（A／AAAA 記錄、IPv6） | `/etc/hosts` 不是 DNS。⚠️ **libvirt 預設 NAT 是純 IPv4**，所以 IPv6 這一項在家裡連不小心驗到的機會都沒有 | PLAN §7 #42(b) |
| **多人並發** | host 上開十個分頁不是三十個學生，⚠️ 而且**你給 guest 幾顆 vCPU 會直接改變數字** | 開學後 |
| **校內防火牆報備** | 人的流程 | §4.5 |
| **長期穩定度** | 時間 | — |
| **⚠️ Safari 上那段訊息真的會顯示嗎**（D45 唯一沒有人會驗的一角） | Linux 上沒有 Safari，而 D45 之後**也沒有人打算去弄一台 Mac 來驗**。⚠️ **所以這是一個誠實的空白，不是一個待辦**：`browser.js` 的引擎判準在真的 Safari 上一次都沒有跑過，測試用的 UA 是抄下來的字串。**失效方向是「Safari 被誤判成支援」→ 沒有訊息 → 學生靜默地聽到錯的聲音**——與 D45 想擋的失敗一模一樣 | 只有一台 Mac 驗得掉。**在那之前，這一格就是空的**；如果哪天有學生反映「Mac 上沒有聲音而且沒看到任何訊息」，**先看這一格** |

### 10.3 ⚠️ 最後一件事：把結果寫回去

`FREEBSD-DEPLOY.md` 全文逐項標著 ✅／📄／❓，而**那些標記的價值取決於它們是最新的**。
這次測試會把其中好幾項從 📄 變成 ✅（或者更有價值地：變成「試過，不對，實際是這樣」）。

**建議的做法**：測試當下開一個檔案隨手記，測完一次改進去，
並在 §10 的表格裡把對應列刪掉或改寫。

> ⚠️ **不要只在心裡記得。** 這份文件與 `FREEBSD-DEPLOY.md` 的讀者是**半年後的你**
> ——那時你會記得「好像測過」，但不會記得「那個 uvicorn 的路徑到底要寫哪一個」。
> **PLAN v0.18 剛好抓到兩處停在 v0.15 的失效敘述，原因一模一樣：
> 沒有人照著它做，就沒有人撞到它是錯的。**
> ⚠️ **而 v0.20 這一版本身就是第三個例子**：v0.19 整份文件假設「一台實體 FreeBSD 筆電」，
> 那個假設**在被實際執行之前就已經過時了**。**沒有被執行的文件會悄悄地與現實脫節。**

---

## 參考來源（v0.20 新增）

⚠️ **以下全部是文件，不是實測。**

- libvirt wiki, [Virtual Networking](https://wiki.libvirt.org/VirtualNetworking.html) 與
  [NAT forwarding](https://wiki.libvirt.org/Networking.html)
  ——預設網路 `default`／`virbr0`／`192.168.122.0/24`／dnsmasq DHCP（§3.1）
- libvirt wiki, [Guest can reach outside network, but can't reach host (macvtap)](https://wiki.libvirt.org/TroubleshootMacvtapHostFail.html)
  與 Red Hat 虛擬化文件的同一條目
  ——**macvtap 之下 host 與 guest 不能互通是定義行為，不是 bug**（§3.2）
- Linux 無線子系統（`cfg80211`）**禁止把 managed 模式的無線介面加進橋**、
  以及 802.11 資料框只有三個位址欄位這件事
  ——「WiFi 上做不了傳統橋接」的根據（§3.2）
- libvirt／KVM 的埠轉發作法（`/etc/libvirt/hooks/qemu` 鉤子、
  `nat/PREROUTING` DNAT + `FORWARD` 要放行 `NEW`）——§3.3 (b)，❓ 未實測
- QEMU／libvirt 快照：**內部快照需要 qcow2，raw 不支援**；
  `virsh snapshot-create-as`／`snapshot-revert`／`snapshot-delete`（§7）
- FreeBSD：**virtio 驅動自 9.2／10.0 起編進 GENERIC**（§2.3）；
  Handbook 的 NTP 一章與 `ntpd_sync_on_start`
  （**ntpd 偏差過大會印錯誤然後結束**，§4.4）
- MDN, [`AudioWorklet`](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)、
  [`Worklet.addModule()`](https://developer.mozilla.org/en-US/docs/Web/API/Worklet/addModule)
  與 Chrome for Developers, [Audio Worklet is now available by default](https://developer.chrome.com/blog/audio-worklet)
  ——**Worklet API 是 secure-context-only，`http://localhost` 除外**。
  ⚠️ **這是 §1.8（PLAN D43）最關鍵的一條，而它在 v0.19 被標為「未經驗證」**
- ✅ **沙箱自身**：`/dev/kvm` 不存在、`grep -c -E '(vmx|svm)' /proc/cpuinfo` 印 0、
  `qemu-system-x86_64`／`virsh`／`virt-manager` 都不存在（§0）

**D45（不支援 Safari）那一段的可信度，單獨說一次：**

- ✅ **已驗證**：`app/static/demos/lib/browser.js` 的判斷邏輯**在 node 裡跑過**，
  正反案例共 15 項（`tests/test_dsp_js.py` 第 9 組），包含
  「Safari 的 UA 裡有 `like Gecko` 卻不得被判成 Firefox」這一項。
- ❓ **未查證，而且沒有人打算去查**：**那些 UA 字串是抄下來的，不是從一台
  真的 Mac 上讀到的**，而 `navigator.userAgentData`／`CSS.supports('-moz-appearance')`
  這兩條判準在真的 Safari／Firefox 上一次都沒有跑過。
  ⚠️ **失效方向見 §10.2 最後一列**——它是這一版唯一一個「我知道它沒被驗過、
  而且短期內不會被驗」的地方，所以它在兩個地方各寫了一次。
