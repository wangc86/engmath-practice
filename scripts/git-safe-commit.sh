#!/usr/bin/env bash
#
# 在「不允許刪檔（unlink）的掛載」中安全地提交。
#
# 為什麼需要這支腳本
# ------------------
# 本專案常在自動化工作階段中被操作，該環境把資料夾以 FUSE 掛載進沙箱，
# 權限是「可建檔、可覆寫、可改名，但不可 unlink」。
#
# git 幾乎每個寫入都是「建 .lock → 寫 → rename → 刪掉殘餘」。rename 過得了，
# 最後的刪除過不了，於是：
#
#   * `git commit` 第一次會成功，但會留下 .git/HEAD.lock
#   * 第二次 commit 就卡死在那個 HEAD.lock 上
#   * 被 SIGPIPE 中斷的 git（例如 `git status | head`）會留下 .git/index.lock
#
# 本腳本改走完全不需要 unlink 的路徑：
#
#   1. index 放到 /tmp（鎖檔就不會落在 .git/ 裡）
#   2. 用 write-tree + commit-tree 產生 commit 物件（不碰任何 ref 鎖）
#   3. 用「覆寫」而非 rename 更新 refs/heads/<branch> 與 reflog
#
# 產出的 repo 與正常 `git commit` 完全等價（git log / reflog / fsck 皆正常）。
# 在一般環境下執行也完全沒問題，行為等同 `git add -A && git commit -F <訊息檔>`。
#
# 用法
# ----
#   printf '標題\n\n內文說明。\n' > /tmp/msg.txt
#   scripts/git-safe-commit.sh /tmp/msg.txt                    # 全部變更
#   scripts/git-safe-commit.sh /tmp/msg.txt -- app/ tests/x.py  # 只提交指定路徑
#
# 沒有任何變更時會印出「沒有變更，略過」並以 0 結束，不會產生空 commit。
#
# 為什麼要支援「只提交指定路徑」（v0.14 新增）
# --------------------------------------------
# 一輪工作動到十幾個檔案時，把它們塞進同一個 commit 會讓日後的 `git log -p`
# 與 `git bisect` 都失去意義。原本的做法是 `git add -A`（等同 `commit -a`），
# 沒有辦法分次提交——而在這個掛載上**不能用 `git add` 之後再 `git commit`**
# 的正常流程（那條路徑會留下刪不掉的鎖檔，見上面）。
#
# 所以把路徑限定加在這裡：`--` 之後的參數原樣傳給 `git add -A`。
# 其餘機制完全不變，仍然不需要任何 unlink。
#
# ⚠️ 分次提交時**每一個 commit 都應該自己站得住**（測試綠、import 得到），
# 否則就只是把一團變更切成幾塊，並沒有換到可讀性。
#
set -euo pipefail

msg_file="${1:-}"
if [ -z "$msg_file" ] || [ ! -f "$msg_file" ]; then
  echo "用法: $0 <commit 訊息檔> [-- <路徑>...]" >&2
  exit 2
fi
shift
if [ "${1:-}" = "--" ]; then
  shift
fi
# 沒給路徑就是全部（原本的行為）。
paths=("$@")

cd "$(git rev-parse --show-toplevel)"

# 0. 關掉自動維護，否則 git 會建 .git/objects/maintenance.lock 又刪不掉
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=gc.auto            GIT_CONFIG_VALUE_0=0
export GIT_CONFIG_KEY_1=maintenance.auto   GIT_CONFIG_VALUE_1=false

# 順手清掉前人留下的殘鎖。在一般環境會成功；在不可刪檔的掛載會失敗，
# 但本腳本不需要這些鎖，失敗也無所謂，所以忽略錯誤。
rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock 2>/dev/null || true

# 1. index 移出 .git/。注意必須是「尚不存在」的路徑——
#    空檔會被 git 以 "index file smaller than expected" 拒絕，
#    所以用 mktemp -d 建目錄，而不是 mktemp 建檔。
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
GIT_INDEX_FILE="$tmpdir/index"
export GIT_INDEX_FILE

# 2. 讓唯讀指令（status/diff）不要去搶 index 鎖
export GIT_OPTIONAL_LOCKS=0

git read-tree HEAD 2>/dev/null || true   # 尚無 commit 時會失敗，正常
if [ ${#paths[@]} -eq 0 ]; then
  git add -A
else
  git add -A -- "${paths[@]}"
fi
tree=$(git write-tree)

if head=$(git rev-parse -q --verify HEAD); then
  if [ "$tree" = "$(git rev-parse "$head^{tree}")" ]; then
    echo "沒有變更，略過"
    exit 0
  fi
  commit=$(git commit-tree "$tree" -p "$head" -F "$msg_file")
  verb="commit"
else
  head=0000000000000000000000000000000000000000
  commit=$(git commit-tree "$tree" -F "$msg_file")
  verb="commit (initial)"
fi

# 3. 覆寫 ref。loose ref 永遠優先於 packed-refs，所以這樣一定生效。
branch=$(git symbolic-ref --short HEAD)
mkdir -p ".git/refs/heads/$(dirname "$branch")" ".git/logs/refs/heads/$(dirname "$branch")"
printf '%s\n' "$commit" > ".git/refs/heads/$branch"

# 4. 補上 reflog，讓 git reflog / git log -g 正常運作
subject=$(head -n 1 "$msg_file")
who="$(git config user.name) <$(git config user.email)>"
for log in .git/logs/HEAD ".git/logs/refs/heads/$branch"; do
  printf '%s %s %s %s +0000\t%s: %s\n' \
    "$head" "$commit" "$who" "$(date +%s)" "$verb" "$subject" >> "$log"
done

# 5. 同步 .git/index，讓之後的 git status 顯示正確
cp "$GIT_INDEX_FILE" .git/index

echo "$commit"

# 6. 牆鐘時間紀錄的提醒（TURNAROUND.csv）。
#
# **這裡是本專案唯一一個「每次提交一定會經過」的地方**，所以那條慣例
# 掛在這裡而不是只寫在 CLAUDE.md 裡——一條只寫在文件裡的慣例等於沒有慣例。
#
# ⛔ **刻意只提醒、不擋提交。** 為了一筆記帳而讓提交失敗，代價遠大於
# 漏掉一列：提交失敗會讓人去找繞過的方法，而繞過一次就會繞過每一次。
# 真正不依賴人記得的那一層在 `tests/test_turnaround.py`（最後一列的
# tests_after 必須等於實際收集到的測試項數）。
if [ ! -s .turnaround-current.json ] || ! grep -q '"task"' .turnaround-current.json 2>/dev/null; then
  echo "提醒：這一輪還沒有記錄開始時間。開工時請跑" >&2
  echo "      python scripts/turnaround.py start <任務編號> --estimate <人週>" >&2
  echo "      收尾時 python scripts/turnaround.py finish ...（見該腳本檔頭）" >&2
fi
