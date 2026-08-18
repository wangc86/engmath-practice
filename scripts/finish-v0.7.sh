#!/usr/bin/env bash
#
# v0.7（捨棄自動評分）的收尾腳本 —— 一次做完「打 tag → 刪檔 → 跑測試 → 分批提交」。
#
# 為什麼存在
# ----------
# 這一版的改動是在一個沙箱環境裡做的，而那個環境的 Linux VM 當時起不來，
# 因此**檔案刪除、測試、git tag 與 commit 都沒有辦法在當下執行**。
# 所有的檔案編輯都已經完成並寫進工作目錄；這支腳本補上剩下的四件事。
#
# 用法
# ----
#   bash scripts/finish-v0.7.sh
#
# 它是**可重複執行**的：tag 已存在就略過、檔案已刪就略過、沒有變更的 commit
# 會自動略過。跑到一半失敗時（例如測試沒過），修好之後再跑一次即可。
#
# 跑完之後這支腳本本身就沒有用了，可以刪掉：rm scripts/finish-v0.7.sh
#
# 注意：本腳本沿用 CLAUDE.md 的「不可 unlink」限制的解法（index 放 /tmp、
# 用 write-tree + commit-tree、覆寫 ref），但**刪檔那一步本來就需要 unlink**，
# 所以請在**你自己的電腦上**執行，不要在受限的掛載裡執行。
#
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

export GIT_OPTIONAL_LOCKS=0
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=gc.auto            GIT_CONFIG_VALUE_0=0
export GIT_CONFIG_KEY_1=maintenance.auto   GIT_CONFIG_VALUE_1=false

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- 1. 先打 tag，標記「含完整判定功能」的那個 commit -----------------------
#
# 順序很重要：tag 必須指向**還沒有刪任何東西**的 commit，所以這一步一定在刪檔
# 與提交之前。用直接寫 ref 的方式（而不是 `git tag`），因為那條路徑完全不需要
# unlink，在受限的掛載裡也能成功。

say "1/4 建立 tag grading-v1"
if git rev-parse -q --verify refs/tags/grading-v1 >/dev/null; then
  echo "    tag grading-v1 已存在，指向 $(git rev-parse --short refs/tags/grading-v1)，略過"
else
  head_commit="$(git rev-parse HEAD)"
  mkdir -p .git/refs/tags
  printf '%s\n' "$head_commit" > .git/refs/tags/grading-v1
  echo "    grading-v1 -> ${head_commit:0:12}"
  echo "    驗證：git show grading-v1 --stat | head -30"
fi

# --- 2. 刪掉判定的實作 ------------------------------------------------------

say "2/4 移除判定相關的檔案"
to_remove=(
  app/grader                        # parse / equivalence / core / feedback / sandbox
  tests/test_grader.py
  tests/test_grader_sandbox.py
  scripts/grader_sampling_report.py
  app/templates/_answer_form.html   # 作答輸入框
  app/templates/_feedback.html      # 判定回饋
)
for path in "${to_remove[@]}"; do
  if [ -e "$path" ]; then
    rm -rf "$path"
    echo "    已刪除 $path"
  else
    echo "    $path 不在（可能已經刪過），略過"
  fi
done
# 殘留的 __pycache__ 會讓 `import app.grader` 在某些情況下仍然成功
find app tests -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# --- 3. 測試 ---------------------------------------------------------------

say "3/4 跑測試"
if [ -x .venv/bin/pytest ]; then
  PYTEST=.venv/bin/pytest
else
  PYTEST=pytest
fi
"$PYTEST" -q

# --- 4. 分批提交 ------------------------------------------------------------
#
# 這是 scripts/git-safe-commit.sh 的「可指定路徑」版本：同樣走不需要 unlink 的
# 路徑（index 放 /tmp、write-tree + commit-tree、覆寫 ref），但只 stage 指定的
# 路徑，這樣才分得出三個 commit。

safe_commit() {
  local msg_file="$1"; shift
  local tmpdir; tmpdir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" RETURN

  GIT_INDEX_FILE="$tmpdir/index" export GIT_INDEX_FILE
  git read-tree HEAD
  git add -A -- "$@"
  local tree; tree=$(git write-tree)

  local head; head=$(git rev-parse HEAD)
  if [ "$tree" = "$(git rev-parse "$head^{tree}")" ]; then
    echo "    沒有變更，略過：$(head -n 1 "$msg_file")"
    unset GIT_INDEX_FILE
    return 0
  fi

  local commit; commit=$(git commit-tree "$tree" -p "$head" -F "$msg_file")
  local branch; branch=$(git symbolic-ref --short HEAD)
  mkdir -p ".git/refs/heads/$(dirname "$branch")" ".git/logs/refs/heads/$(dirname "$branch")"
  printf '%s\n' "$commit" > ".git/refs/heads/$branch"

  local subject; subject=$(head -n 1 "$msg_file")
  local who; who="$(git config user.name) <$(git config user.email)>"
  local log
  for log in .git/logs/HEAD ".git/logs/refs/heads/$branch"; do
    printf '%s %s %s %s +0000\t%s: %s\n' \
      "$head" "$commit" "$who" "$(date +%s)" "commit" "$subject" >> "$log"
  done
  cp "$GIT_INDEX_FILE" .git/index
  unset GIT_INDEX_FILE
  echo "    ${commit:0:12}  $subject"
}

say "4/4 提交"

cat > /tmp/engmath-msg-1.txt <<'EOF'
PLAN v0.7：捨棄自動評分，階段 2 重新定義為「補齊題型 + 提升解說品質」

老師改變產品方向：從學生自我練習的角度，「題目 + 正解 + 分段過程說明」
已經足夠，系統不需要判定學生輸入的答案對錯。這是產品範圍的收斂，
不是因為判定做得不好——D9/D10/D11 之後判定是可信的。

- 新增 D12（捨棄自動評分）與 D13（答案預設遮蔽），各自列出連鎖效果
- §5.2–§5.7 判定方法論改標為「已捨棄／保留供日後參考」而非刪除：
  那是三個版本累積的推導，也是日後恢復時的規格書
- 新增 §5.8：答案遮蔽的設計，以及「details 收合 vs HTMX 按需載入」的取捨
- §6 階段 2 重新規劃：待定係數 → 恰當方程 → 解說整體審查 → 系統其餘情況
  → 參數變異 → Laplace；相圖與離線預生成移出，理由寫在該節
- §7 判定相關的待決事項（#16–#21）整組關閉；#10 由 D13 回答
- §4.1/§4.2/§4.4 同步：Attempt 移除、表現面統計取消、個資告知縮回
- CLAUDE.md 的硬規則 5 換成「答案與逐步解答預設遮蔽」
EOF
safe_commit /tmp/engmath-msg-1.txt PLAN.md CLAUDE.md

cat > /tmp/engmath-msg-2.txt <<'EOF'
移除作答判定（D12），保存在 tag grading-v1

刪除：
- app/grader/（parse / equivalence / core / feedback / sandbox）
- Attempt 資料表、/practice/submit 與 /practice/solution 端點
- 作答輸入框與判定回饋範本、"My Progress" 的正確率
- 判定子行程的暖機與 fail-fast 自檢、/healthz 的 grader 區塊
- GRADER_* 六個設定、SUBMIT_RATE_LIMIT、MAX_ANSWER_LENGTH
- scripts/grader_sampling_report.py、tests/test_grader{,_sandbox}.py（123 項）

保留：
- Problem.check（Check 物件）—— 它同時是出題引擎的驗證閘門，
  移除它等於拆掉「進到學生眼前的題目 100% 有正確答案」這條保證
- UsageLog —— 老師仍要看用量（D1），與判定無關

Attempt 沒有做 migration：該表只在 v0.4–v0.6 存在、系統從未上線，
create_all() 不會動既有的表，舊 DB 檔裡的 attempt 留在原地但永不讀寫。
清法寫在 README。

註冊頁的個資告知同步縮回：系統不再蒐集作答內容。

UI 的重整（答案遮蔽）在下一個 commit。
EOF
safe_commit /tmp/engmath-msg-2.txt \
  app/grader tests/test_grader.py tests/test_grader_sandbox.py \
  scripts/grader_sampling_report.py \
  app/templates/_answer_form.html app/templates/_feedback.html \
  app/main.py app/config.py app/db/models.py app/routes/practice.py \
  app/templates/progress.html app/templates/register.html \
  app/generator/base.py .env.example README.md

cat > /tmp/engmath-msg-3.txt <<'EOF'
答案預設遮蔽：Show Answer → Show Solution Steps（D13）

題目卡片變成三層，每一層都要學生主動點開：

    題目（自動顯示）
      └─ Show Answer            → 最終答案
           └─ Show Solution Steps → 分段過程

兩層都是原生的 <details>，用同一套樣式與互動，學生只要學一次；
詳解巢狀在答案裡面而不是並排，因為「先看答案對不對，看不懂再展開過程」
是自然的順序，並排會讓人以為是二選一。

取捨：選了 <details> 就代表答案在 HTML 原始碼裡，按 F12 看得到。
這在 v0.4 曾被明確否決，因為當時貼上答案就能拿到 Correct；捨棄判定之後
前提變了——系統不計分，能作的弊只作用在自己身上。換到的是沒有網路往返、
少一個端點、上一頁回來時展開狀態還在。代價是 view_solution 這則用量紀錄
消失了，寫在 PLAN §5.8。

測試是互補的一對：預設沒有任何 <details> 帶 open（漏掉收合是這個實作唯一
會靜默出錯的方式），以及展開後答案與步驟真的在片段裡。
另有三項守住判定移除乾淨：端點 404、Attempt 不存在、app.grader import 不到。
EOF
safe_commit /tmp/engmath-msg-3.txt \
  app/templates/_problem.html app/templates/_solution.html \
  app/templates/practice.html app/static/style.css tests/test_web.py \
  scripts/finish-v0.7.sh

say "完成"
git --no-pager log -n 4 --oneline
echo
echo "tag: $(git rev-parse --short refs/tags/grading-v1) grading-v1"
echo
echo "接著請手動做一次端到端驗證："
echo "  export SESSION_SECRET=\$(python -c 'import secrets; print(secrets.token_hex(32))')"
echo "  uvicorn app.main:app --reload"
echo "  → 註冊 → 登入 → 出題 → Show Answer → Show Solution Steps → My Progress"
