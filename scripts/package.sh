#!/usr/bin/env bash
#
# 打包一份 self-contained 的專案快照。
#
#     scripts/package.sh                 # → dist/engmath-practice-<今天>.zip
#     scripts/package.sh 2026-09-02      # 自己指定日期
#
# 為什麼要有這支腳本（v0.23 新增）
# --------------------------------
# 在這之前，打包是一串寫在某個工作階段的 shell 歷史裡的指令：
# 「哪些檔案要進去」「根目錄放什麼」「解開之後長什麼樣」全部沒有落地。
# 那正是 `CLAUDE.md` 一再提到的那種安靜的腐化——**沒有人照著做，
# 就沒有人撞到它是錯的**，而下一個打包的人會重新猜一次。
#
# 三個決定寫在這裡，因為它們是判斷不是細節：
#
#   1. **內容物就是 `git ls-files`。** 不是 `cp -r .`，也不是一份手寫清單。
#      前者會把 `practice.db`（含密碼雜湊）、`.venv`、`__pycache__`、
#      以及 `dist/` 裡的舊 zip 一起包進去；後者會漂移。
#      走版本控制的好處是**它與 `.gitignore` 是同一份真相**：
#      新增一個不該外流的檔案時，擋住它的是同一行設定。
#   2. **根目錄放一份 `README-FIRST.md`**（來源是 `scripts/package-readme.md`，
#      納入版本控制）。解開 zip 的人第一眼要看到「先讀哪一份」，
#      而不是十四個檔名。
#   3. **檔名不再帶 `freebsd`（v0.29）。** 這包的用途變過三次：Windows 測試包
#      （v0.14）→ FreeBSD 部署包（v0.23）→ **一份 self-contained 的專案快照**
#      （v0.29，D57：沒有部署了）。檔名跟著用途走，因為它是唯一一個在下載
#      資料夾裡還看得到的線索。
#
#   ⚠️ **這包不含 `.git/`**，所以解開之後拿不到 commit 歷史，也拿不到
#      `grading-v1` 與 `hosted-v1` 兩個 tag——而那是被拆掉的功能唯一的取回
#      途徑。這件事寫在 `package-readme.md` 裡，因為收到 zip 的人不會知道
#      有那兩個 tag 存在。
#
# ⚠️ **這支腳本只負責打包，不負責驗證。** 交付之前請解壓到一個乾淨目錄、
# 重建 venv、把 `pytest` 跑完——那一步刻意不寫進這裡，因為「腳本說它通過了」
# 與「我看著它跑完」不是同一件事。

set -euo pipefail

cd "$(dirname "$0")/.."

DATE="${1:-$(date +%Y-%m-%d)}"
NAME="engmath-practice"
ZIP="dist/${NAME}-${DATE}.zip"

# 暫存目錄放在 /tmp：自動化工作階段的掛載點不允許 unlink，
# 而這裡需要一個真的可以清掉的地方（見 CLAUDE.md）。
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/$NAME"

# 只複製版本控制裡的檔案。-z 與 read -d '' 是為了處理含空白的檔名——
# 目前沒有，而「目前沒有」不是一個可以依賴的性質。
git ls-files -z | while IFS= read -r -d '' file; do
    mkdir -p "$STAGE/$NAME/$(dirname "$file")"
    cp "$file" "$STAGE/$NAME/$file"
done

cp scripts/package-readme.md "$STAGE/README-FIRST.md"

mkdir -p dist
# ⚠️ 用 python 而不是 zip(1)：FreeBSD 與 macOS 的 zip 未必裝了，
# 而這個專案本來就要求有 python。
python3 - "$STAGE" "$ZIP" <<'PY'
import os, sys, zipfile
stage, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, _, files in os.walk(stage):
        for name in sorted(files):
            path = os.path.join(root, name)
            z.write(path, os.path.relpath(path, stage))
print(f"寫入 {out}（{os.path.getsize(out)} bytes）")
PY

echo
echo "下一步（刻意不由這支腳本代跑）："
echo "  1. 解壓到一個乾淨目錄"
echo "  2. python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
echo "  3. .venv/bin/python -m pytest -q"
