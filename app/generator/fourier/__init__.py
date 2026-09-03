"""Fourier 分析的題型（PLAN.md §2.10、階段 2B 的 2B1–2B5；課綱 W3）。

四個題型，共用 ``core.py`` 的一整套機器：

- ``fourier.series.full_range``   — 全幅 Fourier 級數（2B2，``series.py``）
- ``fourier.series.half_range``   — 半幅展開（正弦／餘弦級數，2B3，``half_range.py``）
- ``fourier.symmetry.parity``     — 奇偶性與係數消失（2B4，``symmetry.py``）
- ``fourier.parseval.series_sum`` — 用 Parseval 恆等式求級數和（2B5，``parseval.py``）

⚠️ **上面那句「四個」在 v0.30 之前是「三個」**，而 v0.30 加了 ``parseval.py``
卻沒有回來改這一行。v0.31 順手更正並記在這裡——**一份會漂移的自述比沒有自述
更不誠實**（D24 的同一個論證）。

⚠️ **檔名與 ``template_id`` 的第二段沒有一一對應**：``half_range.py`` 裝的是
``fourier.series.half_range``。D16 的論證正是「兩者從來沒有耦合過」，
所以這不是要修的東西——⛔ **但也不得反過來，在搬檔案時順手改識別碼。**

v0.31 的工作項 2a0 把最後三個 ODE 題型與 ``system_2x2.py`` 也搬進了子目錄，
所以 ``app/generator/`` 的平面結構過渡狀態到此結束。

---

## 這一包與 ODE 那幾個最大的不同

**沒有方程可以代回去。** ODE 的驗證閘門有一條天然的獨立路徑（把答案代回原式），
Fourier 的答案是「一組由積分定義的係數」，而那條積分**就是生成它的路徑**——
拿定義式重算一次只是把同一段程式再跑一遍。

所以這裡的閘門是自己造出來的四層，寫在 ``core.FourierCheck`` 的 docstring 裡。
**四層不是保守，是因為沒有一層是充分的。**

⛔ ``fourier.parseval.series_sum`` 的閘門**一層都不准跳過**，這與 ``FourierCheck``
不同：那個題型的內容就是那個和，算不出封閉形式的樣本不是「少驗一層」，
是「這一題沒有答案」，所以要重抽（D62）。
"""
