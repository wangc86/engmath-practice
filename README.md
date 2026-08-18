# 工程數學自動出題練習系統

常微分方程與一階線性系統的自我練習工具。題目與逐步解答**全部由程式生成**
（SymPy 反向構造 + 驗證閘門），不靠 LLM 計算，因此不會出現算錯的題目。

規劃全文見 [PLAN.md](PLAN.md)。本 README 對應**階段 1 + 階段 2 的作答判定**。

---

## 目前做到哪裡

**已完成**

- 學號 + 自訂密碼註冊／登入（argon2id 雜湊、session cookie）
- 下拉選單選題型與難度 → 出題 → KaTeX 排版
- **作答輸入 → 符號判定 → 分層級回饋**（見下面「作答判定」一節）
- 「Show solution」按鈕顯示逐步解答（解答不隨題目一起送到瀏覽器）
- 「My Progress」頁：自己的作答歷史與各題型正確率
- 使用紀錄與作答紀錄寫入 SQLite
- 四個題型 × 三個難度，共 12 種組合
- 每個題型都有出題與判定兩邊的 pytest 回歸測試

**尚未實作**

- 其餘題型（待定係數、恰當方程、參數變異、Laplace、系統的重根／複數／非齊次）
- 相圖、離線預生成、對話介面與 LLM 串接、教師後台

> 本系統為**自我練習工具，不計分**。練習與作答紀錄只用來看用量與自我檢視，不作為評分依據。

### 題型清單

| 題型 | 難度 1 | 難度 2 | 難度 3 |
|---|---|---|---|
| 可分離變數 | `y' = f(x)·y` | `g(y)=y²` 或 `f(x)` 含指數 | `g(y)=1+y²`，需反正切反解 |
| 一階線性（積分因子） | `p` 為常數、`q` 為多項式 | `p` 為常數、`q` 含指數 | `p = k/x`（變係數） |
| 二階常係數齊次 | 兩相異實根 | 重根 | 共軛複數根 |
| 一階線性系統 2×2 | 三角矩陣 | 一般矩陣 | 一般矩陣 + 初始條件 |

---

## 作答判定

判定的細節見 [PLAN.md §5](PLAN.md)，這裡是重點。

### 判的是數學性質，不是字面形式

**不會**拿學生答案去減標準答案——通解幾乎必然減不出 0，因為學生的 `C1` 可能對應不同的
基本解。判定的是三件事：

1. 把答案代回原方程，殘差為 0；
2. 任意常數的個數等於方程的階數；
3. 對這些常數的偏導線性獨立（Wronskian ≠ 0）。

因此下面這些**全部判對**：

| 學生輸入 | 為什麼對 |
|---|---|
| `C1*exp(3x) + C2*exp(-2x)` | 標準形 |
| `A e^(-2x) + B e^(3x)` | 換常數名稱、換順序 |
| `(C1+C2)e^(3x) + (C1-C2)e^(-2x)` | **重新參數化，同一個解族** |
| `e^(x^2/2 + C)` vs `C1*e^(x^2/2)` | `C` 與 `e^C` 的差異自動消失 |
| `ln(y) = x^2/2 + C1` | 隱式解會先反解出 `y` |

而 `C1*exp(3x)`（漏了一個常數）判為**部分正確**並明講漏了什麼；
`C1*exp(3x) + C2*exp(3x)`（兩項相同）判為「常數不獨立」。

### 回饋分六級

正確／漏常數／常數過多或不獨立／初始條件沒對／答錯／讀不懂。
**答錯時不爆雷**，只給下一步該檢查什麼（例如「你的兩項裡有一項是對的」）；
要看答案得自己按 Show solution，那個動作會被記錄下來。

### 學生輸入是不可信輸入

`app/grader/parse.py` 走白名單：長度上限 300、字元白名單、禁用 `__`／`lambda`、
`.` 只准出現在數字中間、次方塔（`9^9^9^9`）在進 parser 之前就擋掉、解析後再檢查
運算元個數與指數大小。**絕不 `eval`。**

判定本身跑在**獨立子行程**裡並套用 5 秒逾時（`app/grader/sandbox.py`），
逾時就把 worker 殺掉重建——`simplify` 沒有停機保證，這是唯一能保證「一定回得來」的做法。
可用 `GRADER_TIMEOUT`、`GRADER_WORKERS` 調整。

**子行程叫不起來時，服務會拒絕啟動**，不會退回同行程執行（v0.5 的 D8）。
理由與運維方式見下面的〈判定子行程池：怎麼看它正不正常〉。

---

## 安裝

需要 Python 3.10 以上。

```bash
git clone <這個 repo>
cd engmath-practice

python3 -m venv .venv
source .venv/bin/activate          # Windows：.venv\Scripts\activate

pip install -r requirements.txt
```

## 啟動

```bash
# 產生一把 session 金鑰（不設也能跑，但每次重啟會把所有人登出）
export SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")

uvicorn app.main:app --reload
```

開啟 <http://127.0.0.1:8000> → 第一次使用請先到「註冊」建立帳號。
資料庫 `practice.db` 會在第一次啟動時自動建立（權限自動設為 600）。

### 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `SESSION_SECRET` | 每次啟動隨機產生 | session cookie 的簽章金鑰。**正式環境必須設定。** |
| `PRACTICE_DB` | `./practice.db` | SQLite 檔案位置 |
| `COOKIE_SECURE` | `0` | 走 HTTPS 時設為 `1` |
| `GRADER_TIMEOUT` | `5` | 單次作答判定的秒數上限 |
| `GRADER_WORKERS` | `2` | 判定用的子行程數 |
| `GRADER_WARMUP` | `1` | 啟動時先暖機判定子行程並自檢（測試中會關掉） |
| `GRADER_WARMUP_TIMEOUT` | `60` | 暖機的時間上限（秒）。超過就視為這台機器有問題 |
| `APP_LOG_LEVEL` | `INFO` | `app.*` 的 log 等級。查判定細節時可設 `DEBUG` |

可複製 `.env.example` 為 `.env` 管理（`.env` 已被 `.gitignore` 排除）。

---

## 運維：判定子行程池

判定是這個系統唯一會執行「學生給的東西」的地方，所以它的健康狀況值得單獨看一節。
（**log 訊息是寫給維護者看的，用中文**；學生看得到的介面一律英文，見 D5。）

### 正常長什麼樣

啟動時應該看到這兩行，第二行是**啟動自檢通過**的證據：

```
2026-08-18 09:12:03 INFO     app.grader.sandbox: 判定子行程池已就緒（2 個 worker，單次判定上限 5.0 秒）。
INFO:     Application startup complete.
```

之後隨時可以問 `/healthz`（很便宜，只讀旗標，可以讓監控每分鐘打一次）：

```bash
curl -s localhost:8000/healthz
# {"status":"ok","grader":{"warmed_up":true,"pool_alive":true,"workers":2,"timeout_seconds":5.0}}
```

- `warmed_up: true` → 這次啟動的自檢過了。
- `pool_alive: false` 而 `warmed_up: true` → 剛剛有人逾時、整池被殺掉了，**這是正常的**，
  下一次判定會自動重建。

### 出問題長什麼樣

**（a）機器開不了子行程 → 服務直接起不來。** 這是刻意的（D8）：

```
ERROR    app.grader.sandbox: 判定用的子行程池建不起來（OSError: ...）。這台機器目前沒有辦法
         開子行程，判定會全部失敗——本系統不會退回同行程執行，因為那等於沒有 timeout，
         一個病態的作答就能把伺服器卡死。請檢查行程數／記憶體上限（ulimit -u、
         cgroup pids.max）與 /dev/shm。
ERROR    app.grader.sandbox: 判定子行程無法啟動，服務不會啟動。原因見上一行。
ERROR:    Application startup failed. Exiting.
```

先查 `ulimit -u`、systemd unit 的 `TasksMax`、容器的 `pids.max`，以及 `/dev/shm` 是否掛得起來。
真的急著先把頁面開起來（判定會全部回 internal_error）可以設 `GRADER_WARMUP=0` 跳過自檢——
但那只是把發現問題的時間點延後，不會讓判定變得能用。

**（b）有學生的作答跑太久 → 逾時，整池重建。** 偶爾出現是正常的：

```
WARNING  app.grader.sandbox: 一次判定超過 5.0 秒的時限，整池 worker 重建。...
WARNING  app.grader: 判定逾時：template=ode.second_order.homogeneous difficulty=3 seed=12345（學生看到 timeout 訊息）。
```

要看是什麼輸入造成的，查 `Attempt` 表裡 `verdict='timeout'` 的那幾筆：

```sql
SELECT created_at, template_id, difficulty, seed, submitted_raw, duration_ms
FROM attempt WHERE verdict = 'timeout' ORDER BY created_at DESC LIMIT 20;
```

若頻繁出現且都指向同一個題型，那多半是判定本身在某類輸入上化簡不動，
而不是有人在搗蛋。

**（c）`判定 worker 在工作途中消失`**：沒有伴隨 (b) 的逾時訊息時，
最可能是被 OOM killer 殺掉的。`dmesg -T | grep -i oom` 或 `journalctl -k` 確認一下。

### 為什麼沒有「降級模式」

同行程執行沒有辦法套上可靠的 timeout：`SIGALRM` 只有主執行緒收得到，而判定跑在
FastAPI 的 threadpool 裡；看門狗執行緒則沒有辦法中斷一條卡在 SymPy 裡的執行緒。
所以「降級模式」實際上就是「沒有 timeout 的模式」。詳細推導寫在
`app/grader/sandbox.py` 的模組說明裡。

---

## 測試

```bash
pytest                          # 全部 237 項，約 2.5 分鐘
pytest tests/test_web.py -q     # 只跑 Web 流程，約 20 秒
pytest tests/test_grader.py -q  # 只跑作答判定，約 13 秒
```

| 檔案 | 項數 | 耗時 | 守的是什麼 |
|---|---|---|---|
| `test_generators.py` | 75 | 約 102 秒 | 出題引擎 |
| `test_web.py` | 55 | 約 20 秒 | 端對端流程、前端資產、介面語言、啟動自檢 |
| `test_grader.py` | 91 | 約 13 秒 | 作答判定與輸入解析 |
| `test_grader_sandbox.py` | 16 | 約 16 秒 | 判定的子行程、timeout、子行程建不起來時的 fail fast |

`tests/test_generators.py` 是整個專案最重要的測試：每個題型 × 每個難度
各隨機生成 30 題，逐題檢查

1. **把解代回原方程，殘差恰為 0**（最關鍵的一項）
2. 沒有特殊函數（`erf`、`Ei`、`LambertW`…）或未算完的積分
3. 沒有醜分數（分母 > 12）
4. 出題係數落在白名單範圍內
5. 逐步解答非空，且最後一步就是答案
6. 同一個 seed 必然生出相同的題目

升級 SymPy 版本前請跑完整回歸：

```bash
GEN_TEST_SAMPLES=200 pytest tests/test_generators.py
```

---

## 專案結構

```
app/
├── main.py                     FastAPI 進入點、SessionMiddleware
├── config.py                   設定（環境變數）
├── logging_setup.py            app.* 的 log 輸出（被 except 吞掉的錯誤都要留一行）
├── security.py                 argon2 密碼雜湊、密碼規則、速率限制
├── db/
│   ├── models.py               Student / UsageLog
│   └── session.py              SQLite 連線（WAL）
├── generator/                  ← 出題引擎，本專案的核心
│   ├── base.py                 Problem / Step / Check、註冊表、generate()
│   ├── pretty.py               漂亮度評分與拒絕抽樣
│   ├── separable.py
│   ├── first_order_linear.py
│   ├── second_order_homog.py
│   └── system_2x2.py
├── grader/                     ← 作答判定
│   ├── parse.py                學生輸入 → SymPy（白名單、複雜度上限）
│   ├── equivalence.py          是否為 0、常數是否線性獨立
│   ├── core.py                 判定流程（跑在子行程裡）
│   ├── feedback.py             判定結果 → 英文分層回饋
│   └── sandbox.py              子行程與 timeout（叫不起來就 fail fast，D8）
├── routes/
│   ├── auth.py                 註冊／登入／登出
│   └── practice.py             出題、作答、看解答、我的紀錄
├── templates/                  Jinja2（介面文字一律英文，見 PLAN.md D5）
└── static/
    ├── style.css
    └── vendor/                 自架的 KaTeX 與 HTMX（見該目錄的 README）
tests/
├── test_generators.py          出題引擎回歸測試
├── test_grader.py              判定的正反例、解析寬容度、惡意輸入
├── test_grader_sandbox.py      判定的子行程、timeout、fail fast 告警
└── test_web.py                 註冊 → 登入 → 出題 → 作答端對端測試
scripts/
├── preview.py                  批次產題目樣本供人工審題（HTML / LaTeX）
└── git-safe-commit.sh          不需 unlink 的提交路徑（見 CLAUDE.md）
```

---

## 新增一個題型

只要加一個檔案，UI 下拉選單與 pytest 參數化測試都會自動撿到，兩處都不用改。

1. 在 `app/generator/` 建立新檔，例如 `exact.py`：

```python
import random
import sympy as sp
from .base import Check, Problem, Step, register
from .pretty import is_pretty

x = sp.Symbol("x", positive=True)
_y = sp.Function("y")(x)          # 判定用的未知函數

@register(
    "ode.first_order.exact",
    name="Exact Equations",
    chapter="First-Order ODEs",
    difficulty_notes={1: "Already exact", 2: "Verify exactness first",
                      3: "An integrating factor is needed"},
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    ...
    # 回傳 None 表示這組參數不合格，base.generate() 會自動換一組重抽
    return Problem(
        template_id="ode.first_order.exact",
        difficulty=difficulty,
        seed=0,                       # 由 base.generate() 填入
        params={...},                 # 供測試檢查係數範圍
        statement="...",
        statement_latex="...",
        answer_latex="...",
        answer_expr=sol,
        steps=[Step("Title", r"latex", "Note in English; wrap math in $…$"), ...],
        check=Check(                  # 驗證閘門與作答判定共用這一個物件
            var=x,
            kind="scalar",            # 或 "system"
            n_constants=1,            # 通解需要幾個任意常數（初值問題填 0）
            order=1,                  # 方程的階數
            unknown=_y,
            residual_expr=sp.Derivative(_y, x) - ...,   # L[y] - g，含 _y
            linear=True,              # L 對 y 是否線性
        ),
    )
```

`Check` 必須是**純資料**（不能放 lambda 或 closure）：判定要送進子行程才套得上 timeout，
而 closure 不能 pickle。`var` 一定要用 generator 自己那顆符號（含 assumptions）——
另外造一顆 `Symbol("x")` 會與 `Symbol("x", positive=True)` 不相等，代回去等於沒代，
所有正確答案都會被判錯。

2. 在 `app/generator/__init__.py` 加一行 `from . import exact`。
3. 若需要專屬的係數範圍檢查，在 `tests/test_generators.py` 加一個測試函式。
4. 把新題型加進 `tests/test_grader.py` 的 `REFERENCE_CASES`，讓它自動獲得
   「標準答案判對、加 1 判錯」的判定回歸測試。

**設計約定**（詳見 PLAN.md §2.1）：

- **反向構造優先於正向求解**——先決定答案長什麼樣，再倒推題目。
  例如二階齊次是先選特徵根再算係數，線性系統是先選 `D` 與 `det = ±1` 的 `P`
  再令 `A = PDP⁻¹`。
- **SymPy 是驗證閘門，不是生成器**——`check` 描述「怎麼把一個表達式代回原方程」，
  `base.generate()` 會逐題驗證標準答案的殘差為 0，不過就換一組參數重抽。
  同一個 `check` 之後也被拿去驗證學生的答案，因此出題與判分不可能對同一題有不同標準。
- **逐步解答由模板自己寫**——文字敘述是固定的英文模板（介面語言為英文，
  見 PLAN.md D5），中間量由 SymPy 算，所以不會算錯，也能對應課本的解題流程。
  敘述裡的數學片段一律用 `$…$` 包起來，否則 KaTeX 不會渲染。

---

## 前端資產

KaTeX 0.16.11 與 HTMX 2.0.4 **全部自架**於 `app/static/vendor/`（約 656 KB，已納入版本控制）。
沒有 build step、沒有 npm 相依、不連外部 CDN——clone 完就能離線啟動，
校內網路連不到外網時數學一樣正常渲染。

細節與升級步驟見 [`app/static/vendor/README.md`](app/static/vendor/README.md)。

三個測試會守住這件事（`tests/test_web.py`）：

- `test_referenced_static_assets_all_exist`：`base.html` 引用的每個 `/static/` 路徑都取得到
- `test_no_external_cdn_dependency`：頁面不得再出現 jsDelivr／unpkg／cdnjs
- `test_katex_fonts_referenced_by_css_are_present`：CSS 列到的 woff2 字型檔都在

題目的 LaTeX 是經 Jinja2 autoescape 後才輸出的（HTML 原始碼裡會看到 `&#39;`、`&amp;`），
瀏覽器解析時會還原成 `'` 與 `&`，KaTeX 讀到的是正確的內容。
**請不要為了「讓原始碼好看」而加上 `|safe`**，那會打開 XSS 的門。

---

## 部署注意事項

- **必須走 HTTPS**：系統處理密碼，沒有 HTTPS 不得上線。建議用 Caddy 自動申請憑證。
- `practice.db` 內含學號明文與密碼雜湊，權限須為 600，放在非 web root 目錄。
- 備份請加密（`age` 或 `gpg`），並設定保存期限。
- 學期結束後執行去識別化（詳見 PLAN.md §4.4）。
- 目前的速率限制是單進程記憶體計數器，因此請以**單一 uvicorn 進程**部署；
  要多進程時需改用 Redis 或資料庫計數表。
