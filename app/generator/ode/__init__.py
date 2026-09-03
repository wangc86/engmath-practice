"""純量常微分方程的題型（PLAN.md §1.5 的 D16 目標結構；課綱 W9–W10）。

四個題型：

- ``ode.first_order.separable``     — 可分離變數（``separable.py``）
- ``ode.first_order.linear``        — 一階線性、積分因子（``first_order_linear.py``）
- ``ode.second_order.homogeneous``  — 二階常係數齊次（``second_order_homog.py``）
- ``ode.laplace.transform`` / ``ode.laplace.ivp`` — 拉普拉斯（``laplace.py``）

⚠️ **檔名與 ``template_id`` 沒有對齊，而那是刻意的**：
``first_order_linear.py`` 裝的是 ``ode.first_order.linear``，
``second_order_homog.py`` 裝的是 ``ode.second_order.homogeneous``，
``laplace.py`` 一個檔案裝兩個題型。D16 的整個論證就建立在
**檔案路徑與 ``template_id`` 從來沒有耦合過**這一點上；
把它們對齊會讓下一個人以為那是一條規則，然後在改檔名時順手改識別碼。

---

## ⛔ v0.35：老師刪掉了兩個題型，而**它們不是「做壞了」**

- ``ode.first_order.exact``（恰當方程與積分因子，``exact.py``）
- ``ode.second_order.undetermined``（待定係數，``undetermined.py``）

兩個檔案整份移除，連同它們的測試。**這是課程範圍的決定，不是品質的決定**
——兩者當時都全綠、閘門也都有突變測試守著。

⚠️ **它們帶走的兩樣東西值得記住，因為下次要用會找不到**：

1. ``ExactCheck``——本專案唯一一個走**隱函數微分**（而不是代回方程）的驗證器，
   四層，其中第 2 層擋的是「$F$ 退化成常數時 $M F_y - N F_x$ 恆為 0，
   閘門會對一個什麼都沒說的答案說通過」。
2. ``answer_kind = "implicit"``——為了 $F(x,y) = C_1$ 這種答案而加的第四個值。
   **它現在沒有任何題型在用**，但 ``base.py`` 保留著它，理由寫在那裡。

兩者都取得回來：``git log -p -- app/generator/ode/exact.py``。

---

## 這個子目錄不再是過渡狀態（v0.31）

v0.24–v0.27 的四輪裡，新題型直接建在這裡，而既有的三個留在上一層的平面結構
——不是忘了搬，是搬檔案需要 unlink，而當時的工作環境不允許（見 ``CLAUDE.md``）。
工作項 **2a0** 在 v0.31 執行完畢。

``base.py``、``pretty.py``、``plot.py`` **刻意留在上一層**：
它們沒有註冊任何題型，是各子目錄共用的工具。
"""
