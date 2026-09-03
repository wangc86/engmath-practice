"""Fourier 分析的題型（PLAN.md §2.10、階段 2B；課綱 W3）。

兩個題型，共用 ``core.py`` 的一整套機器：

- ``fourier.series.full_range``   — 全幅 Fourier 級數（2B2，``series.py``）
- ``fourier.series.half_range``   — 半幅展開（正弦／餘弦級數，2B3，``half_range.py``）

⚠️ **檔名與 ``template_id`` 的第二段沒有一一對應**：``half_range.py`` 裝的是
``fourier.series.half_range``。D16 的論證正是「兩者從來沒有耦合過」，
所以這不是要修的東西——⛔ **但也不得反過來，在搬檔案時順手改識別碼。**

---

## ⛔ v0.35：老師刪掉了兩個題型

- ``fourier.symmetry.parity``（奇偶性與係數消失，``symmetry.py``）
- ``fourier.parseval.series_sum``（用 Parseval 恆等式求級數和，``parseval.py``）

**這是課程範圍的決定，不是品質的決定。** 兩個檔案整份移除，連同它們的測試。

⚠️ **`core.py` 一行都沒有動，而那是刻意的**：它是上面兩個倖存題型的地基，
而且被刪掉的兩個題型**沒有在它裡面留下任何只為自己存在的程式碼**
（``ParityCheck`` 住在 ``symmetry.py`` 自己那裡）。
⚠️ 但 ``core.py`` 的檔頭仍然提到 ``symmetry.py``，那一句已經更正。

取得回來：``git log -p -- app/generator/fourier/parseval.py``。

---

## 這一包與 ODE 那幾個最大的不同

**沒有方程可以代回去。** ODE 的驗證閘門有一條天然的獨立路徑（把答案代回原式），
Fourier 的答案是「一組由積分定義的係數」，而那條積分**就是生成它的路徑**——
拿定義式重算一次只是把同一段程式再跑一遍。

所以這裡的閘門是自己造出來的四層，寫在 ``core.FourierCheck`` 的 docstring 裡。
**四層不是保守，是因為沒有一層是充分的。**
⚠️ **第二層（Parseval）在部分參數上跳過是正常的**（實測集中在半幅展開的難度 3），
但跳過必須記一行 log。
"""
