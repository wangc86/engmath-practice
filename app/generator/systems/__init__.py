"""一階線性系統的題型（PLAN.md §2.5、§2.11；課綱 W10、W12–13）。

四個題型，三個檔案：

- ``system.linear_2x2.real_distinct``   — 實相異特徵值（``real_distinct.py``）
- ``system.linear_2x2.repeated``        — 重根（缺陷矩陣，需要廣義特徵向量）
- ``system.linear_2x2.complex``         — 複數特徵值（答案必須是**實數形**）
  以上兩個住在 ``linear_2x2.py``
- ``system.linear_2x2.classification``  — 判斷平衡點的類型（``classify.py``）

> ⛔ **v0.35：``system.linear_2x2.nonhomogeneous``（非齊次，待定係數）已由老師刪除**，
> 連同純量的 ``ode.second_order.undetermined``。**這是課程範圍的決定，不是品質的決定。**
> ⚠️ 它帶走了這個檔案裡唯一一段「反向構造為什麼選待定係數而不選參數變異」的論證
> （先挑 $\mathbf{x}_p$ 再令 $\mathbf{g} = \mathbf{x}_p' - A\mathbf{x}_p$，
> 於是不需要任何拒絕抽樣、也不需要積分）——那段論證保存在
> ``git log -p -- app/generator/systems/linear_2x2.py``。

---

## v0.31：``real_distinct.py`` 就是原本的 ``system_2x2.py``

工作項 **2a0**（D16）在 v0.31 執行完畢。原本擋著它的是「工作環境不能 unlink」，
而 ``git mv`` 內部是「複製 + 刪除」。

⚠️ **檔名選 ``real_distinct.py`` 而不是 PLAN §1.5 原本寫的 ``linear_2x2.py``**：
那個名字在 v0.26 已經被上面三個題型用掉了，照原指令搬會把它蓋掉（D64）。
⛔ **搬檔案沒有動任何一個 ``template_id``**——五個鍵在註冊表裡與遷移前逐字相同。

---

## 這一包內部共用的東西，以及刻意不共用的東西

**共用**：反向構造的核心技巧（$A = PDP^{-1}$，$\\det P = \\pm 1$ 保證 $A$ 與
特徵向量都是小整數）、``Check``、``pretty.as_exponential()``、相圖。

**刻意不共用**：``real_distinct.py`` **一行都沒有被改成「通用」的形狀**。
把四個情形塞進一支 ``generate()`` 會得到一個三層 ``if difficulty/case`` 的函式，
而那種函式最容易出的錯是「某一格的分支從來沒有被執行到」——症狀是那一格
永遠出同一種題目，而**沒有任何測試會紅**。

⚠️ ``P_CANDIDATES`` 那份候選清單現在有兩種寫法並存：``classify.py`` 是
``from .real_distinct import``，``linear_2x2.py`` 自己算一份一樣的。
理由（以及為什麼 v0.31 沒有順手統一它）寫在 ``linear_2x2.py`` 那一行旁邊。
"""
