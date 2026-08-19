# 工程數學自動出題練習系統

常微分方程與一階線性系統的自我練習工具。題目、答案與逐步解答**全部由程式生成**
（SymPy 反向構造 + 驗證閘門），不靠 LLM 計算，因此不會出現算錯的題目。

流程是：**出題 → 自己在紙上算 → Show Answer 對答案 → Show Solution Steps 看過程**。

規劃全文見 [PLAN.md](PLAN.md)。本 README 對應**階段 1**（v0.7）。

---

## 目前做到哪裡

**已完成**

- 學號 + 自訂密碼註冊／登入（argon2id 雜湊、session cookie）
- 下拉選單選題型與難度 → 出題 → KaTeX 排版
- **答案與逐步解答預設遮蔽**，各要點一下才展開（見下面「答案遮蔽」）
- 「My Progress」頁：自己練了哪些題型、幾題
- 使用紀錄寫入 SQLite
- 四個題型 × 三個難度，共 12 種組合
- 每個題型都有出題端的 pytest 回歸測試

**尚未實作**

- 其餘題型（待定係數、恰當方程、參數變異、Laplace、系統的重根／複數／非齊次）
- 逐步解答的整體審查與風格統一
- 相圖、離線預生成、對話介面與 LLM 串接、教師後台
- **瀏覽器端互動式訊號處理展示**（v0.11 已完成規劃，尚未實作。見 PLAN.md **§8** 與**階段 2S**）

> 本系統為**自我練習工具**：系統不判定答案、不產生成績、不呈現分數，練習紀錄只記用量。
> 紀錄與課程評量的關係**由老師在課堂上說明，系統一律不提**（PLAN.md D17）——
> 頁面、註冊頁告知、日誌都不得出現 grading／grade 字眼，`tests/test_web.py` 有兩項盯著。

### 題型清單

| 題型 | 難度 1 | 難度 2 | 難度 3 |
|---|---|---|---|
| 可分離變數 | `y' = f(x)·y` | `g(y)=y²` 或 `f(x)` 含指數 | `g(y)=1+y²`，需反正切反解 |
| 一階線性（積分因子） | `p` 為常數、`q` 為多項式 | `p` 為常數、`q` 含指數 | `p = k/x`（變係數） |
| 二階常係數齊次 | 兩相異實根 | 重根 | 共軛複數根 |
| 一階線性系統 2×2 | 三角矩陣 | 一般矩陣 | 一般矩陣 + 初始條件 |

---

## ⚠️ v0.7：自動評分（作答判定）已移除

老師改變了產品方向：**從學生自我練習的角度，「題目 + 正解 + 分段過程說明」已經足夠，
系統不需要判定學生輸入的答案對錯。**（PLAN.md D12）

**這不是因為判定做得不好。** v0.4–v0.6 的判定是可信的——說「對」的時候一律有符號證明、
逾時只殺出事的那一個 worker、答案的顯示形式一致。是它服務的那個需求本身被取消了。

**完整的判定功能保存在 git tag `grading-v1`。** 日後若要恢復，從那裡取回即可：

```bash
git show grading-v1 --stat            # 看當初有哪些檔案
git checkout grading-v1 -- app/grader tests/test_grader.py tests/test_grader_sandbox.py
git show grading-v1:app/routes/practice.py     # 作答與看解答的端點
git show grading-v1:app/db/models.py           # Attempt 資料表
```

方法論（parser 的每一條補丁、三值等價判定、fail fast 的推導、逾時隔離的三方案取捨）
留在 **PLAN.md §5.2–§5.7**，標為「已捨棄／保留供日後參考」，那就是恢復時的規格書。

### 移除了什麼

| 項目 | 處置 |
|---|---|
| `app/grader/`（5 個模組） | 移除。唯一的使用者是判定 |
| 作答輸入框、Check my answer、判定回饋 | 移除（`_answer_form.html`、`_feedback.html`） |
| `/practice/submit` 端點 | 移除 |
| `/practice/solution` 端點 | 移除——解答改用 `<details>` 收合，不再需要另外要一次（見下） |
| `Attempt` 資料表 | 移除。**沒有做 migration**，說明見下面「資料庫」 |
| "My Progress" 的正確率、作答歷史 | 移除。**用量的部分保留**——老師仍要看用量（D1） |
| 判定子行程沙箱（D6／D8／D10） | 移除。出題流程從來沒有用過它 |
| `GRADER_*` 六個環境變數、`SUBMIT_RATE_LIMIT`、`MAX_ANSWER_LENGTH` | 移除 |
| `/healthz` 的 `grader` 區塊 | 移除，現在只回 `{"status": "ok"}` |
| `scripts/grader_sampling_report.py` | 移除 |
| `tests/test_grader.py`、`tests/test_grader_sandbox.py` | 移除（共 123 項） |

### 沒有動、也不能動的東西

**`Problem.check`（`Check` 物件）。** 它同時是**出題引擎的驗證閘門**：`base.generate()`
用它把標準答案代回原方程，殘差不是 0 就換一組參數重抽。判分曾經共用它，但那是附帶用途。
移除 `Check` 等於拆掉「進到學生眼前的題目 100% 有正確答案」這條唯一的保證——
新增題型時仍然必須提供它。

`UsageLog` 也完整保留：它記的是誰、何時、練了哪個題型，與判定無關。

### 資料庫：`Attempt` 表要不要處理

**不需要 migration。** `Attempt` 只在 v0.4–v0.6 存在，系統從未正式上線，實際的
`practice.db` 裡只有測試資料。`init_db()` 用的 `SQLModel.metadata.create_all()`
只建缺少的表、不會去動既有的表，所以：

- **全新的資料庫**：不會建出 `attempt` 表，什麼都不用做。
- **舊的資料庫**：`attempt` 表會留在檔案裡，但永遠不被讀寫。想清掉就手動下一行：

```bash
sqlite3 practice.db 'DROP TABLE IF EXISTS attempt;' && sqlite3 practice.db 'VACUUM;'
```

若日後真的累積了要保存的資料，那時再引入 Alembic；不必為了一張沒有資料的表提前付這個成本。

---

## 答案遮蔽

老師的要求：**每題的答案要先遮蔽，點選 Show Answer 後才顯示**，行為與逐步解答一致
（PLAN.md D13、§5.8）。實作是三層，每一層都要學生主動點：

```
題目（自動顯示）
  └─ ▸ Show Answer            → 最終答案
       └─ ▸ Show Solution Steps → 分段過程
```

三個設計決定：

1. **兩層用同一套 UI**（原生的 `<details>/`<summary>`），學生只要學一次這個互動。
2. **詳解巢狀在答案裡面**，不是並排的第二個按鈕——「先看答案對不對，看不懂再展開過程」
   是自然的順序；並排會讓人以為是二選一。
3. **兩層都預設收合。**

### 取捨：答案其實在 HTML 原始碼裡

選了 `<details>` 就代表**按 F12 或全選複製看得到答案**。這在 v0.4 曾被明確否決，
現在反過來，因為前提變了：

| | v0.4（有判定） | v0.7（無判定） |
|---|---|---|
| 提前看到答案的後果 | **判定失去意義**——貼上答案就得到 Correct，而那筆紀錄會進 `Attempt` | 只是自己少練到一題。沒有東西可以作弊 |
| 成本 | HTMX 端點 + 一次往返，值得 | 同樣的成本，換到的東西小得多 |

**系統不判定答案、也不把對錯寫進紀錄**（D12）是這個取捨成立的關鍵：展開答案不留痕跡、
也換不到任何東西，能作的弊只作用在自己身上。換到的是——沒有網路往返
（校內網路不穩時一樣能展開）、少一個端點與它的錯誤處理、上一頁回來時展開狀態還在。

**代價是 `view_solution` 這則用量紀錄消失了**（`<details>` 展開不發請求），
於是「一出題就直接看解答的比例」這個指標失去資料來源。判斷是可以接受的：那是對**解題過程**
的監看，與「練了多少」不同層次，本來就不在個資告知的蒐集範圍內。若老師改變主意想要這個訊號，
除了改回 HTMX 按需載入之外**還要重新看一次個資告知**————`/practice/solution` 的程式碼在 tag `grading-v1` 裡，原樣可用。

註解寫在 `app/templates/_problem.html` 的開頭，兩項測試盯著（見下面「測試」）。

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
| `APP_LOG_LEVEL` | `INFO` | `app.*` 的 log 等級。查出題為什麼重抽時可設 `DEBUG` |

可複製 `.env.example` 為 `.env` 管理（`.env` 已被 `.gitignore` 排除）。

> v0.6 的 `GRADER_TIMEOUT` / `GRADER_WORKERS` / `GRADER_QUEUE_TIMEOUT` /
> `GRADER_WARMUP` / `GRADER_WARMUP_TIMEOUT` 已隨判定移除。環境裡若還留著，
> 現在只會被忽略。

---

## 運維

判定移除之後，這個系統的運維面變得非常小：**一個 uvicorn 進程 + 一個 `.db` 檔案**。
它不再有子行程池、沒有暖機自檢、也**不再有任何地方執行不可信輸入**——
出題只吃 `(template_id, difficulty, seed)` 三個經過檢查的值，跑的是我們自己寫的 generator。

存活檢查：

```bash
curl -s localhost:8000/healthz
# {"status":"ok"}
```

### 值得看的一則 log

出題是拒絕抽樣：抽一組參數 → 用 `Check` 驗證殘差是不是 0 → 不是就重抽。重抽到上限
仍然失敗時，學生看到「Please press Generate again」，而 log 裡會有：

```
WARNING  app.routes.practice: 出題失敗：template=ode.first_order.separable difficulty=3
         （重抽多次都沒通過殘差驗證）。偶爾一次是正常的；若集中在某個題型請檢查它的參數範圍。
```

**偶爾一次是正常的**（那正是驗證閘門在做事）。但如果它集中在某一個 (題型, 難度)，
那代表該模板的參數範圍出了問題，應該去看 `app/generator/<題型>.py`，
並用 `scripts/preview.py` 產一批樣本檢查。

（**log 訊息是寫給維護者看的，用中文**；學生看得到的介面一律英文，見 PLAN.md D5。）

---

## 測試

```bash
pytest                          # 全部，約 2.5 分鐘
pytest tests/test_web.py -q     # 只跑 Web 流程
```

| 檔案 | 守的是什麼 |
|---|---|
| `test_generators.py` | 出題引擎、答案的顯示形式一致性 |
| `test_web.py` | 端對端流程、答案遮蔽、前端資產、介面語言 |

`tests/test_generators.py` 是整個專案最重要的測試：每個題型 × 每個難度
各隨機生成 30 題，逐題檢查

1. **把解代回原方程，殘差恰為 0**（最關鍵的一項）
2. 沒有特殊函數（`erf`、`Ei`、`LambertW`…）或未算完的積分
3. 沒有醜分數（分母 > 12）
4. 出題係數落在白名單範圍內
5. 逐步解答非空，且最後一步就是答案
6. 同一個 seed 必然生出相同的題目

答案遮蔽（D13）由 `test_web.py` 的兩項互補測試守著：

- `test_answer_and_steps_are_collapsed_by_default`：**沒有任何一個 `<details>` 帶 `open` 屬性**。
  漏掉收合是這個實作唯一會靜默出錯的方式——頁面不會壞，只是答案直接出現在畫面上。
- `test_revealed_content_actually_contains_the_answer_and_the_steps`：展開後真的有東西。
  只有前一項的話，一個把答案整段刪掉的 bug 會讓測試全綠。

另有三項守住「判定真的移除乾淨了」：端點回 404、`Attempt` 模型不存在、`app.grader` import 不到。

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
│   ├── pretty.py               漂亮度評分與拒絕抽樣、顯示形式的一致性
│   ├── separable.py
│   ├── first_order_linear.py
│   ├── second_order_homog.py
│   └── system_2x2.py
├── routes/
│   ├── auth.py                 註冊／登入／登出
│   └── practice.py             出題、我的紀錄
├── templates/                  Jinja2（介面文字一律英文，見 PLAN.md D5）
└── static/
    ├── style.css
    └── vendor/                 自架的 KaTeX 與 HTMX（見該目錄的 README）
tests/
├── test_generators.py          出題引擎回歸測試
└── test_web.py                 註冊 → 登入 → 出題 → 展開答案／詳解
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
_y = sp.Function("y")(x)          # 驗證閘門用的未知函數

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
        check=Check(                  # ← 驗證閘門。**必要**，不可省略
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

`Check` 是 `base.generate()` 驗證標準答案的依據——**它不是可選的**。殘差算不出 0
就會換一組參數重抽，這是「進到學生眼前的題目 100% 有正確答案」的實作。
`var` 一定要用 generator 自己那顆符號（含 assumptions）——另外造一顆 `Symbol("x")`
會與 `Symbol("x", positive=True)` 不相等，代回去等於沒代，殘差永遠不會是 0。

> `Check` 建議維持**純資料**（不放 lambda 或 closure）。原本的理由是要 pickle 到判定的
> 子行程，那個理由已隨 D12 消失；但保持純資料讓它日後做離線預生成時可直接序列化。

2. 在 `app/generator/__init__.py` 加一行 `from . import exact`。
3. 若需要專屬的係數範圍檢查，在 `tests/test_generators.py` 加一個測試函式。

**設計約定**（詳見 PLAN.md §2.1）：

- **反向構造優先於正向求解**——先決定答案長什麼樣，再倒推題目。
  例如二階齊次是先選特徵根再算係數，線性系統是先選 `D` 與 `det = ±1` 的 `P`
  再令 `A = PDP⁻¹`。
- **SymPy 是驗證閘門，不是生成器**——`check` 描述「怎麼把一個表達式代回原方程」，
  `base.generate()` 會逐題驗證標準答案的殘差為 0，不過就換一組參數重抽。
- **逐步解答由模板自己寫**——文字敘述是固定的英文模板（介面語言為英文，
  見 PLAN.md D5），中間量由 SymPy 算，所以不會算錯，也能對應課本的解題流程。
  敘述裡的數學片段一律用 `$…$` 包起來，否則 KaTeX 不會渲染。
- **每一步的 `note` 要回答「為什麼」，不是重述「做了什麼」。** 判定移除之後，
  逐步解答是這個系統唯一的教學產出（PLAN.md §6 階段 2）。
  「Multiply both sides by $\mu$」是重述——式子本身已經說了；
  「$\mu$ 的作用是讓左邊變成一個乘積的導數，這樣才積得回去」才是解說。

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
