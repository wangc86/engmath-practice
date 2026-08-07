# 工程數學自動出題練習系統

常微分方程與一階線性系統的自我練習工具。題目與逐步解答**全部由程式生成**
（SymPy 反向構造 + 驗證閘門），不靠 LLM 計算，因此不會出現算錯的題目。

規劃全文見 [PLAN.md](PLAN.md)。本 README 對應**階段 1 MVP**。

---

## 目前做到哪裡

**已完成（階段 1）**

- 學號 + 自訂密碼註冊／登入（argon2id 雜湊、session cookie）
- 下拉選單選題型與難度 → 出題 → KaTeX 排版 → 可展開逐步解答
- 使用紀錄寫入 SQLite（誰、何時、題型、難度）
- 四個題型 × 三個難度，共 12 種組合
- 每個題型都有 pytest 回歸測試（殘差為 0、係數範圍、無醜分數）

**尚未實作（階段 2 之後）**

- 作答輸入與判分、對話介面、LLM 串接、相圖、教師後台

> 本系統為**自我練習工具，不計分**。練習紀錄只用來看用量，不作為評分依據。

### 題型清單

| 題型 | 難度 1 | 難度 2 | 難度 3 |
|---|---|---|---|
| 可分離變數 | `y' = f(x)·y` | `g(y)=y²` 或 `f(x)` 含指數 | `g(y)=1+y²`，需反正切反解 |
| 一階線性（積分因子） | `p` 為常數、`q` 為多項式 | `p` 為常數、`q` 含指數 | `p = k/x`（變係數） |
| 二階常係數齊次 | 兩相異實根 | 重根 | 共軛複數根 |
| 一階線性系統 2×2 | 三角矩陣 | 一般矩陣 | 一般矩陣 + 初始條件 |

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

可複製 `.env.example` 為 `.env` 管理（`.env` 已被 `.gitignore` 排除）。

---

## 測試

```bash
pytest                        # 全部，約 2 分鐘
pytest tests/test_web.py -q   # 只跑 Web 流程，約 8 秒
```

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
├── security.py                 argon2 密碼雜湊、密碼規則、速率限制
├── db/
│   ├── models.py               Student / UsageLog
│   └── session.py              SQLite 連線（WAL）
├── generator/                  ← 出題引擎，本專案的核心
│   ├── base.py                 Problem / Step、註冊表、generate()
│   ├── pretty.py               漂亮度評分與拒絕抽樣
│   ├── separable.py
│   ├── first_order_linear.py
│   ├── second_order_homog.py
│   └── system_2x2.py
├── routes/
│   ├── auth.py                 註冊／登入／登出
│   └── practice.py             出題頁與 HTMX 片段
├── templates/                  Jinja2（繁體中文）
└── static/style.css
tests/
├── test_generators.py          出題引擎回歸測試
└── test_web.py                 註冊 → 登入 → 出題端對端測試
```

---

## 新增一個題型

只要加一個檔案，UI 下拉選單與 pytest 參數化測試都會自動撿到，兩處都不用改。

1. 在 `app/generator/` 建立新檔，例如 `exact.py`：

```python
import random
import sympy as sp
from .base import Problem, Step, register
from .pretty import is_pretty

x = sp.Symbol("x", positive=True)

@register(
    "ode.first_order.exact",
    name_zh="恰當方程",
    chapter="一階常微分方程",
    difficulty_notes={1: "直接恰當", 2: "需先驗證恰當性", 3: "需找積分因子"},
)
def generate(rng: random.Random, difficulty: int) -> Problem | None:
    ...
    # 回傳 None 表示這組參數不合格，base.generate() 會自動換一組重抽
    return Problem(
        template_id="ode.first_order.exact",
        difficulty=difficulty,
        seed=0,                       # 由 base.generate() 填入
        params={...},                 # 供測試檢查係數範圍
        statement_zh="...",
        statement_latex="...",
        answer_latex="...",
        answer_expr=sol,
        steps=[Step("標題", r"latex", "中文說明"), ...],
        residual=sp.simplify(...),    # 解代回原方程的殘差，必須為 0
    )
```

2. 在 `app/generator/__init__.py` 加一行 `from . import exact`。
3. 若需要專屬的係數範圍檢查，在 `tests/test_generators.py` 加一個測試函式。

**設計約定**（詳見 PLAN.md §2.1）：

- **反向構造優先於正向求解**——先決定答案長什麼樣，再倒推題目。
  例如二階齊次是先選特徵根再算係數，線性系統是先選 `D` 與 `det = ±1` 的 `P`
  再令 `A = PDP⁻¹`。
- **SymPy 是驗證閘門，不是生成器**——`residual` 必須是「把答案代回原方程」的表達式，
  `base.generate()` 會逐題驗證它為 0，不過就換一組參數重抽。
- **逐步解答由模板自己寫**——文字敘述是固定的中文模板，中間量由 SymPy 算，
  所以不會算錯，也能對應課本的解題流程。

---

## 前端資產

KaTeX 0.16.11 與 HTMX 2.0.4 都從 jsDelivr 載入，版本號已鎖定，**不需要 build step**。

兩件值得知道的事：

- 範本沒有加 SRI `integrity` 屬性。若要加，請自行從 KaTeX 官方文件複製當版的雜湊值
  ——**填錯的雜湊會讓整頁數學靜默地不渲染**，比不加更糟。
- 若校內網路連不到 CDN，把 `katex.min.css`、`katex.min.js`、`auto-render.min.js`、
  字型目錄與 `htmx.min.js` 下載到 `app/static/vendor/`，再把 `base.html` 的路徑改成
  `/static/vendor/...` 即可。

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
