# 這包是什麼，以及先讀哪一份

**工程數學自動出題練習系統**，打包給 **FreeBSD 正式部署**用。
解開之後你會得到一個 `engmath-practice/` 目錄，那就是完整的專案。

---

## 先讀這一份

> ## 📄 [`FREEBSD-DEPLOY.md`](engmath-practice/FREEBSD-DEPLOY.md)
>
> 從一台乾淨的 FreeBSD 開始，到學生可以從瀏覽器連進來為止的每一步：
> 套件安裝、虛擬環境、`rc.d` 服務、反向代理與 HTTPS、log 輪替、備份、
> **校內 IP 限制（§5.8）**、以及**代理層不得記錄用戶端 IP（§5.7）**。

⚠️ **那份文件是在 Linux 沙箱裡寫成的，沒有一件事在 FreeBSD 上實測過。**
它因此逐項標記了可信度（已驗證／依文件推論／未查證），文末還有一份
「無法驗證清單」。**照它做的時候請把它當成一份很仔細的推論，不是一份實測紀錄。**

**想先在家練一次**（不要拿學校那台當第一次）：
📄 [`FREEBSD-HOMELAB.md`](engmath-practice/FREEBSD-HOMELAB.md)——
Ubuntu + QEMU/KVM 開一台 FreeBSD 虛擬機，把整套流程走一遍。
同樣沒有實測過，但它涵蓋的正是最容易卡住的那幾步。

---

## 目錄裡有什麼

| 路徑 | 是什麼 | 部署需要嗎 |
|---|---|---|
| `app/` | 應用程式本體（FastAPI、出題引擎、展示區的前端） | **是** |
| `app/static/` | 自架的 KaTeX／HTMX／fft.js、展示區的 JS 與範例音檔 | **是**（全部自架，執行期不連外） |
| `requirements.txt` | Python 相依套件 | **是** |
| `scripts/create_accounts.py` | 建立兩組共用帳號、重設密碼 | **是**（第一次啟動前要跑） |
| `.env.example` | 環境變數範本（`SESSION_SECRET` 等） | **是**（複製成 `.env` 再改） |
| `FREEBSD-DEPLOY.md` | 正式部署步驟 | **是** |
| `FREEBSD-HOMELAB.md` | 在家用虛擬機預演一次 | 建議 |
| `README.md` | 系統做得到什麼、怎麼用、設計取捨 | 建議 |
| `tests/` + `pytest.ini` | 760 項自動測試 | 建議**部署後跑一次**（見下） |
| `scripts/` 其餘 | 出題預覽、範例音檔產生、golden vector、安全提交 | 否，維護用 |
| `PLAN.md` | 規劃書（所有決定與理由的出處） | 否，但 `README` 到處指向它 |
| `CLAUDE.md` | 給 AI 協作者的專案須知 | 否 |
| `TURNAROUND.csv` | 每個實作任務花掉的牆鐘時間 | 否 |
| `WINDOWS-SETUP.md` | 在 Windows 上跑一份**本機測試**用的實例 | 否——見下面那一段 |

### `WINDOWS-SETUP.md` 為什麼還留著

它跟 FreeBSD 部署沒有關係，但**留著的理由有三個，而第一個是硬的**：

1. **`FREEBSD-DEPLOY.md` 有三處、`README.md` 有兩處指向它。** 拿掉它，
   這包裡就會有五個指到空氣的連結——而那正是 `PLAN.md` 記過兩次的
   那種「沒有人照著做，就沒有人撞到它是錯的」的失效方式。
2. **它是唯一一份「從完全沒有 Python 開始」的逐步教學。**
   `FREEBSD-DEPLOY.md` 假設你會用 shell；那一份不假設。裡面的
   〈跑測試〉、〈資料庫檔案、備份與清除〉、〈第一次使用〉、
   〈互動展示的瀏覽器需求〉四節與作業系統無關，**在 FreeBSD 上照樣讀得懂**。
3. **它只有 30 KB。**

⚠️ **但它不是這包的用途**，所以說清楚：它描述的是一個**沒有 HTTPS、
只監聽本機、跑開發伺服器**的測試實例。**不要照它部署給學生用。**

---

## 最短路徑

```sh
# 1. 解壓、建虛擬環境、裝套件（FreeBSD 上這一步會編譯，要花幾分鐘）
cd engmath-practice
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 2. 產生 session 金鑰
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # 填進 .env

# 3. 建立兩組共用帳號（密碼只會印出來這一次）
python scripts/create_accounts.py init

# 4. 跑一次測試，確認這台機器上一切正常
pytest -q                    # 760 項；需要 node 的 429 項會在沒有 node 時 skip

# 5. 起服務（正式部署請照 FREEBSD-DEPLOY.md 用 rc.d + 反向代理）
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

⚠️ **`node` 只是開發期相依。** 部署不需要裝它；沒有它的話那 429 項測試會
**明確地 skip 並印出原因**，不會安靜地通過。

---

## 部署完成之前有兩件事還沒有結案

兩件都寫在 `FREEBSD-DEPLOY.md` 裡，但值得在這裡也講一次，因為它們是
**只有在那台機器上才驗得掉**的：

1. **反向代理不得記錄用戶端 IP**（§5.7）。應用程式與 uvicorn 兩層都處理好了，
   而且有測試盯著；**代理那一層在我們的行程外面，沒有測試，也不可能有**。
   驗收方式只有一種：部署完成後 `tail` 一下代理的 log，確認裡面沒有位址。
2. **校內網段的允許清單與 VPN 的來源網段**（§5.8）。文件裡填的是
   RFC 5737 的文件用位址當佔位符，**一個真實網段都沒有**——那份清單只有
   計中給得出來，而猜錯的方向是把全班擋在門外。

---

## 展示區還沒有在真的瀏覽器裡驗收過

伺服器端與純函式層都驗過了（760 項測試），但**音訊、canvas、autoplay 解鎖、
worklet 載入全部沒有被真的執行過**——開發環境裡沒有瀏覽器。
部署完成後請在桌機 **Chrome 與 Firefox** 上把六個展示各開一次。
（Safari 官方不支援，展示頁上會自己顯示一段說明。）

⚠️ **其中 `/demos/filter/pole-zero` 那一頁請先戴耳機、把音量調小再測。**
它是唯一一個會產生高增益共振的展示；防護做了三層，但**三層都沒有在
真的喇叭上驗過**。
