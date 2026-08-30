"""一階線性系統的題型（PLAN.md §2.5、階段 2A 的 2d）。

三個題型，全部住在 `linear_2x2.py`：

- ``system.linear_2x2.repeated``       — 重根（缺陷矩陣，需要廣義特徵向量）
- ``system.linear_2x2.complex``        — 複數特徵值（答案必須是**實數形**）
- ``system.linear_2x2.nonhomogeneous`` — 非齊次（待定係數，難度 3 是共振）

⚠️ **既有的 `system.linear_2x2.real_distinct` 仍然住在上一層的
`app/generator/system_2x2.py`**，不是這裡。這不是忘了搬——搬檔案必然包含
「檔案要從舊路徑消失」，而自動化工作階段的掛載點不可 unlink（見 CLAUDE.md），
`git mv` 內部是「複製 + 刪除」，一定會失敗。工作項 **2a0** 保留給老師在自己的
電腦上執行，理由與指令見 `ode/__init__.py` 與 PLAN §1.5。

**為什麼混著放是安全的**：`template_id` 與檔案路徑從來沒有耦合過（D16）。
四個題型在註冊表裡看起來完全一樣，`/activity` 的用量紀錄也是。

---

## 這一包與 `real_distinct` 共用的東西，以及刻意不共用的東西

**共用**：反向構造的核心技巧（$A = PDP^{-1}$，$\\det P = \\pm 1$ 保證 $A$ 與
特徵向量都是小整數）、`Check`、`pretty.as_exponential()`、相圖。

**刻意不共用**：`real_distinct` 的那個檔案**一行都沒有被改成「通用」的形狀**。
把四個情形塞進一支 `generate()` 會得到一個三層 `if difficulty/case` 的函式，
而那種函式最容易出的錯是「某一格的分支從來沒有被執行到」——症狀是那一格
永遠出同一種題目，而**沒有任何測試會紅**。
"""
