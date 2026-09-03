"""純量常微分方程的題型（PLAN.md §1.5 的 D16 目標結構；課綱 W9–W10）。

六個題型，一個檔案一個主題：

- ``ode.first_order.separable``     — 可分離變數（``separable.py``）
- ``ode.first_order.linear``        — 一階線性、積分因子（``first_order_linear.py``）
- ``ode.first_order.exact``         — 恰當方程與積分因子（``exact.py``）
- ``ode.second_order.homogeneous``  — 二階常係數齊次（``second_order_homog.py``）
- ``ode.second_order.undetermined`` — 待定係數（``undetermined.py``）
- ``ode.laplace.transform`` / ``ode.laplace.ivp`` — 拉普拉斯（``laplace.py``）

⚠️ **檔名與 ``template_id`` 沒有對齊，而那是刻意的**：
``first_order_linear.py`` 裝的是 ``ode.first_order.linear``，
``second_order_homog.py`` 裝的是 ``ode.second_order.homogeneous``，
``laplace.py`` 一個檔案裝兩個題型。D16 的整個論證就建立在
**檔案路徑與 ``template_id`` 從來沒有耦合過**這一點上；
把它們對齊會讓下一個人以為那是一條規則，然後在改檔名時順手改識別碼。

---

## v0.31：這個子目錄不再是過渡狀態

v0.24–v0.27 的四輪裡，新題型直接建在這裡，而既有的
``separable.py``／``first_order_linear.py``／``second_order_homog.py``
留在上一層的平面結構——**不是忘了搬**，是搬檔案需要 unlink，
而當時的工作環境不允許（見 ``CLAUDE.md``）。

工作項 **2a0** 在 v0.31 執行完畢：那三個檔案已經搬進來，
``system_2x2.py`` 搬成 ``../systems/real_distinct.py``（D64）。
⛔ **搬檔案沒有動任何一個 ``template_id``**，驗收是
``sorted(REGISTRY)`` 在遷移前後逐字相同（實測相同，16 個鍵）。

``base.py``、``pretty.py``、``plot.py`` **刻意留在上一層**：
它們沒有註冊任何題型，是三個子目錄共用的工具。
"""
