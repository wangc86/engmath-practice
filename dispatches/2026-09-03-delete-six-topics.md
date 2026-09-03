# 刪掉六個題型，以及現在的部署方式下已經沒有標的的回歸看守

**日期**：2026-09-03　**工作項**：**DEL6**（新，不在 PLAN 路線圖上）
**狀態**：進行中（本檔案在開工的第一件事就建立，見 `dispatches/README.md`）

> 同一天、同一個工作階段的第五輪派送。

---

## 提示詞（逐字）

刪 3, 5, 9, 15, 16, 17，以及現在的佈署方式下（i.e., 不用連網到別台機器、不用身份驗證、不用紀錄使用者用量、...） ，不需要的測試也都刪掉。

### 那六個編號指的是什麼

上一則回覆列了一份編號清單（16 個已實作題型 + 2 個規劃中的），老師挑的是：

| # | 題型 | `template_id` |
|---|---|---|
| 3 | 恰當方程與積分因子 | `ode.first_order.exact` |
| 5 | 待定係數法 | `ode.second_order.undetermined` |
| 9 | 線性系統 2×2 非齊次 | `system.linear_2x2.nonhomogeneous` |
| 15 | Fourier 奇偶性與係數消失 | `fourier.symmetry.parity` |
| 16 | Parseval 求級數和 | `fourier.parseval.series_sum` |
| 17 | 參數變異法（**從未實作**，工作項 2e） | — |

### 「不需要的測試」那一句的追問與老師的裁示

AI 查過之後回報：那一句底下其實是**性質相反的兩組**，並用 `AskUserQuestion` 問了。

- **A 組（回歸看守，44 項）**——檢查已經拆掉的帳號／資料庫／判分端點「沒有偷跑回來」。
  它們確實只因為那些東西曾經存在而存在。
- **B 組（性質看守，8 項）**——檢查「沒有資料庫、不連外網、檔案不外流」這些
  **現在還成立**的性質。⛔ **它們不是「不需要的測試」，它們正是讓那個部署方式成立的東西。**

**老師的選擇：只刪 A 組，保留 B 組。**

---

## 回覆（摘要；完整版見本輪最終訊息）

### 刪掉了什麼

| 刪的 | 怎麼刪 |
|---|---|
| `ode.first_order.exact` | `app/generator/ode/exact.py` 整份 |
| `ode.second_order.undetermined` | `app/generator/ode/undetermined.py` 整份 |
| `system.linear_2x2.nonhomogeneous` | `systems/linear_2x2.py` 的最後一段 |
| `fourier.symmetry.parity` | `app/generator/fourier/symmetry.py` 整份 |
| `fourier.parseval.series_sum` | `app/generator/fourier/parseval.py` 整份 |
| 工作項 2e（參數變異法） | **從未實作**，關閉規劃；§7 #14 連帶失去標的 |

**題型 16 → 11，測試 1394 → 1159（−235）。**

⛔ **課程範圍的決定，不是品質的決定**——五個當時全部綠燈。
**沒有另外打 tag**，理由記在 D67。

### −235 分成兩堆

| 哪一堆 | 幾項 |
|---|---|
| 五個題型自己的測試 | −191 |
| A 組「回歸看守」 | −44 |

**B 組「性質看守」（8 項）保留**，那是老師的裁示。

### ⛔ 整輪最容易做錯的一步

`Check.ic_derivative_values` 的唯一證明原本掛在待定係數上，而
**`ode.laplace.ivp` 的難度 2、3 仍然在用那個欄位**。
跟著刪的話，一個還在用的欄位會安靜地變成沒有人守。
那一項**改寫成用 `ode.laplace.ivp`**（自變數 $x \to t$，只取 `order == 2`
的兩個難度），實測前後行為相同。

### 兩項寫死的清單如期變紅

`test_registry_is_wired_up`（16 → 11）與
`test_which_system_templates_carry_a_portrait_is_a_deliberate_list`
（非齊次那個 `False` 消失了）。**那正是它們存在的意義。**

### 踩到的坑

**沒有。** 五個題型的模組邊界是乾淨的——刪掉之後 `fourier/core.py`
一行都不用動，`systems/linear_2x2.py` 只是砍掉最後一段。

⚠️ 兩件不算坑但值得記：量測相依地圖時第一次用了 `--merge` 卻沒先重設，
舊的 18 批（含已刪題型）還留在地圖裡；掛了鉤子的量測比裸跑慢，
Fourier 那兩批因此超過沙箱 180 秒上限，各再切成兩塊。
