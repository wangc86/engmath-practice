# 2c 人工審題的機器初篩

**自動產生**：`python scripts/review_steps.py -n 5`。⛔ **這份不是判斷，是排序**——2c 的判斷是老師的（`VERIFY-CHECKLIST.md` §A6）。

樣本：16 個題型 × 3 個難度 × 5 題 = **240 題**。
題目本身請開 `preview.html`（`python scripts/preview.py -n 5`）對照著看。

> ⚠️ **每一項都是線索不是結論**，每一節的開頭都寫著它為什麼可能誤報。
> 五項判準的完整說明在 `scripts/review_steps.py` 的檔頭。

## 先看這幾個（線索最多的排前面）

⚠️ **排序不是評分。** 這裡排的是「機器讀得出來的線索有幾條」，不是「哪個題型比較差」——一條線索完全可能是誤報，每一節的開頭都寫著它為什麼會誤報。

- **`ode.second_order.homogeneous`**（4 條）
  - C1 步驟數離中位數 -2.1 步
  - C2 有 30/60 個步驟根本沒有 note
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C3 三個可量的向度都沒有隨難度上升
- **`ode.second_order.undetermined`**（4 條）
  - C1 步驟數離中位數 +4.0 步
  - C2 有 68/151 個步驟根本沒有 note
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C5 有 8 題步驟寫 $y$、答案寫 $y(x)$
- **`fourier.symmetry.parity`**（3 條）
  - C1 步驟數離中位數 -2.1 步
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C3 三個可量的向度都沒有隨難度上升
- **`ode.first_order.separable`**（3 條）
  - C2 有 30/75 個步驟根本沒有 note
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C5 有 15 題步驟寫 $y$、答案寫 $y(x)$
- **`ode.laplace.ivp`**（3 條）
  - C1 步驟數離中位數 +2.6 步
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C5 有 15 題步驟寫 $y$、答案寫 $y(x)$
- **`system.linear_2x2.complex`**（3 條）
  - C1 步驟數離中位數 +2.6 步
  - C1 三個難度之間的步驟數跳 2 步以上
  - C2 有 40/130 個步驟根本沒有 note
- **`system.linear_2x2.real_distinct`**（3 條）
  - C1 三個難度之間的步驟數跳 2 步以上
  - C2 有 40/105 個步驟根本沒有 note
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
- **`system.linear_2x2.repeated`**（3 條）
  - C1 步驟數離中位數 +2.6 步
  - C1 三個難度之間的步驟數跳 2 步以上
  - C2 有 50/130 個步驟根本沒有 note
- **`fourier.parseval.series_sum`**（2 條）
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C3 三個可量的向度都沒有隨難度上升
- **`fourier.series.full_range`**（2 條）
  - C1 步驟數離中位數 +2.4 步
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
- **`fourier.series.half_range`**（2 條）
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
  - C3 三個可量的向度都沒有隨難度上升
- **`ode.first_order.exact`**（2 條）
  - C1 三個難度之間的步驟數跳 2 步以上
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
- **`ode.first_order.linear`**（2 條）
  - C2 有 45/75 個步驟根本沒有 note
  - C5 有 15 題步驟寫 $y$、答案寫 $y(x)$
- **`ode.laplace.transform`**（2 條）
  - C1 三個難度之間的步驟數跳 2 步以上
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）
- **`system.linear_2x2.classification`**（2 條）
  - C1 步驟數離中位數 -2.1 步
  - C3 三個可量的向度都沒有隨難度上升
- **`system.linear_2x2.nonhomogeneous`**（2 條）
  - C2 有 45/105 個步驟根本沒有 note
  - C2 有 note 像在重述步驟（動作動詞開頭／與 title 重疊）

## C1 步驟顆粒度：每題幾步

§7 #22 想訂的規則是「一步 = 課本上會單獨寫一行的一個動作」，而目前各題型是各憑感覺切的。
⚠️ **步驟數不一樣不一定是錯的**——有些題型本來就比較長。要看的是**同一個題型在三個難度之間**跳不跳，以及有沒有哪個題型明顯離群。

| 題型 | d1 | d2 | d3 | 平均 | 離中位數 |
|---|---|---|---|---|---|
| `fourier.parseval.series_sum` | 5.0 | 5.0 | 5.0 | 5.0 | -1.1 |
| `fourier.series.full_range` | 7.8 | 9.0 | 8.8 | 8.5 | +2.4 ⚠️ |
| `fourier.series.half_range` | 6.8 | 6.4 | 6.0 | 6.4 | +0.3 |
| `fourier.symmetry.parity` | 4.0 | 4.0 | 4.0 | 4.0 | -2.1 ⚠️ |
| `ode.first_order.exact` | 5.0 | 5.0 | 7.4 | 5.8 | -0.3 |
| `ode.first_order.linear` | 5.0 | 5.0 | 5.0 | 5.0 | -1.1 |
| `ode.first_order.separable` | 5.0 | 5.0 | 5.0 | 5.0 | -1.1 |
| `ode.laplace.ivp` | 8.0 | 9.2 | 9.0 | 8.7 | +2.6 ⚠️ |
| `ode.laplace.transform` | 3.0 | 5.0 | 5.0 | 4.3 | -1.8 |
| `ode.second_order.homogeneous` | 4.0 | 4.0 | 4.0 | 4.0 | -2.1 ⚠️ |
| `ode.second_order.undetermined` | 9.8 | 10.2 | 10.2 | 10.1 | +4.0 ⚠️ |
| `system.linear_2x2.classification` | 4.0 | 4.0 | 4.0 | 4.0 | -2.1 ⚠️ |
| `system.linear_2x2.complex` | 8.0 | 8.0 | 10.0 | 8.7 | +2.6 ⚠️ |
| `system.linear_2x2.nonhomogeneous` | 7.0 | 7.0 | 7.0 | 7.0 | +0.9 |
| `system.linear_2x2.real_distinct` | 6.0 | 6.0 | 9.0 | 7.0 | +0.9 |
| `system.linear_2x2.repeated` | 8.0 | 8.0 | 10.0 | 8.7 | +2.6 ⚠️ |

中位數 **6.1** 步。⚠️ 標了 ⚠️ 的是離中位數 2 步以上的——**先看那幾個**。

**同一題型在三個難度之間跳 2 步以上**（切法可能不一致，也可能是難度真的不同）：
- `ode.first_order.exact`
- `ode.laplace.transform`
- `system.linear_2x2.complex`
- `system.linear_2x2.real_distinct`
- `system.linear_2x2.repeated`

## C2 `note` 是在回答「為什麼」還是在重述「做了什麼」

⚠️ **這一節是五項裡最粗的。** 它只看四件表面的事：`note` 是不是空的、是不是以動作動詞開頭、有沒有任何因果詞、以及與 `title` 的詞重疊。**一句好的 `note` 完全可能三項都中**，所以這裡列的是「先看這幾句」。

| 題型 | 步驟總數 | 空的 | 動作動詞開頭 | 沒有因果詞 | 重述 title | 很短 |
|---|---|---|---|---|---|---|
| `fourier.parseval.series_sum` | 75 | 0 | 0 | 15 | 15 | 0 |
| `fourier.series.full_range` | 128 | 0 | 0 | 15 | 30 | 0 |
| `fourier.series.half_range` | 96 | 0 | 0 | 0 | 15 | 0 |
| `fourier.symmetry.parity` | 60 | 0 | 15 | 0 | 0 | 0 |
| `ode.first_order.exact` | 87 | 17 | 0 | 15 | 20 | 0 |
| `ode.first_order.linear` | 75 | 45 | 0 | 15 | 0 | 0 |
| `ode.first_order.separable` | 75 | 30 | 15 | 37 | 0 | 0 |
| `ode.laplace.ivp` | 131 | 25 | 0 | 28 | 15 | 0 |
| `ode.laplace.transform` | 65 | 15 | 0 | 25 | 9 | 0 |
| `ode.second_order.homogeneous` | 60 | 30 | 5 | 25 | 0 | 0 |
| `ode.second_order.undetermined` | 151 | 68 | 15 | 45 | 30 | 0 |
| `system.linear_2x2.classification` | 60 | 0 | 0 | 15 | 0 | 0 |
| `system.linear_2x2.complex` | 130 | 40 | 0 | 55 | 0 | 0 |
| `system.linear_2x2.nonhomogeneous` | 105 | 45 | 0 | 15 | 15 | 0 |
| `system.linear_2x2.real_distinct` | 105 | 40 | 15 | 65 | 0 | 0 |
| `system.linear_2x2.repeated` | 130 | 50 | 0 | 30 | 0 | 0 |

### 命中兩項以上的 `note`（每個題型最多列三句，訊號多的排前面）

**`ode.first_order.separable`**

- d1　*Separate the variables*
  - note：Collect everything involving $y$ on the left and everything involving $x$ on the right.
  - 訊號：starts-with-action-verb, no-reason-marker

**`ode.second_order.undetermined`**

- d1　*Substitute and compare coefficients*
  - note：Substitute $y_p$ into the left-hand side, collect like terms, and match them against the right-hand side.
  - 訊號：starts-with-action-verb, no-reason-marker
- d1　*General solution*
  - note：The general solution is the homogeneous solution plus any one particular solution.
  - 訊號：no-reason-marker, restates-title(100%)

**`system.linear_2x2.real_distinct`**

- d1　*Find the eigenvectors*
  - note：Solve $(A - \lambda_i I)\mathbf{v} = \mathbf{0}$ for each eigenvalue. Any nonzero scalar multiple of an eigenvector is equally correct.
  - 訊號：starts-with-action-verb, no-reason-marker

## C3 難度階梯：難度 2 有沒有在任何一個可量的向度上超過難度 1

⛔ **長度不是難度。** 這一節唯一能回答的是「有沒有任何一個可量的向度隨難度上升」；答案是「沒有」時**也可能是對的**（例如難度軸是共振重數，那件事量不出來，`ode.second_order.undetermined` 就是這樣）。

| 題型 | 敘述長度 d1→d2→d3 | 步驟數 | 答案的運算元 | 有沒有單調上升 |
|---|---|---|---|---|
| `fourier.parseval.series_sum` | 155→87.8→144.6 | 5→5→5 | 2→2→2 | **都沒有** ⚠️ |
| `fourier.series.full_range` | 38.6→76.6→106 | 7.8→9→8.8 | 8.4→17.4→20.6 | 敘述、運算元 |
| `fourier.series.half_range` | 31.8→31.4→64 | 6.8→6.4→6 | 8→7.4→17.6 | **都沒有** ⚠️ |
| `fourier.symmetry.parity` | 35→79.2→73.8 | 4→4→4 | —→—→— | **都沒有** ⚠️ |
| `ode.first_order.exact` | 66.6→83.4→70.6 | 5→5→7.4 | 6.2→8.6→6.8 | 步驟 |
| `ode.first_order.linear` | 14.2→19.2→25.4 | 5→5→5 | 4.2→6→3.8 | 敘述 |
| `ode.first_order.separable` | 22.4→26.6→50 | 5→5→5 | 3.4→4.2→4 | 敘述 |
| `ode.laplace.ivp` | 35→56.6→69.2 | 8→9.2→9 | 5.6→10→19 | 敘述、運算元 |
| `ode.laplace.transform` | 38→47.2→78 | 3→5→5 | 7→6.6→10.2 | 敘述、步驟 |
| `ode.second_order.homogeneous` | 18→17.4→18.6 | 4→4→4 | 6.4→4.4→8.6 | **都沒有** ⚠️ |
| `ode.second_order.undetermined` | 40.6→52.4→45 | 9.8→10.2→10.2 | 12.4→11.4→10.8 | 步驟 |
| `system.linear_2x2.classification` | 79→78.8→77.8 | 4→4→4 | —→—→— | **都沒有** ⚠️ |
| `system.linear_2x2.complex` | 77→77.2→143.6 | 8→8→10 | 13.2→21.8→13.8 | 敘述、步驟 |
| `system.linear_2x2.nonhomogeneous` | 125.2→142.6→138 | 7→7→7 | 16.2→21.2→24.2 | 運算元 |
| `system.linear_2x2.real_distinct` | 75.8→77.2→143.4 | 6→6→9 | 10→13.8→12 | 敘述、步驟 |
| `system.linear_2x2.repeated` | 76.6→76.4→143.6 | 8→8→10 | 12.4→16.2→8 | 步驟 |

## C4 英文用語（§7 #11：這件事要對著課本拍板）

⚠️ 不同題型用不同動詞**可能是對的**，這一節只是把分佈攤開。

**敘述開頭的第一個字**：`Find` × 127、`Solve` × 38、`Use` × 30、`Decide` × 15、`Classify` × 15、`Verify` × 10、`The` × 5

**幾組競爭說法各出現幾次**（兩邊都 > 0 的那幾組要拍板）：

- `general solution` × 227　vs　`complete solution` × 0
- `initial condition` × 38　vs　`initial value` × 110 ⚠️ **兩種都在用**
- `particular solution` × 83　vs　`particular integral` × 0
- `characteristic equation` × 60　vs　`auxiliary equation` × 0

## C5 附錄 C：同一題裡 $y$ 與 $y(x)$ 混用（§7 #29 已知 `separable.py` 有一處）

| 題型 | 步驟寫裸露的 $y$ 的題數 | 答案寫 $y(x)$ 的題數 | 同一題兩者都有 |
|---|---|---|---|
| `fourier.parseval.series_sum` | 0 | 0 | 0 |
| `fourier.series.full_range` | 0 | 0 | 0 |
| `fourier.series.half_range` | 0 | 0 | 0 |
| `fourier.symmetry.parity` | 0 | 0 | 0 |
| `ode.first_order.exact` | 10 | 0 | 0 |
| `ode.first_order.linear` | 15 | 15 | 15 ⚠️ |
| `ode.first_order.separable` | 15 | 15 | 15 ⚠️ |
| `ode.laplace.ivp` | 15 | 15 | 15 ⚠️ |
| `ode.laplace.transform` | 0 | 0 | 0 |
| `ode.second_order.homogeneous` | 0 | 15 | 0 |
| `ode.second_order.undetermined` | 8 | 15 | 8 ⚠️ |
| `system.linear_2x2.classification` | 0 | 0 | 0 |
| `system.linear_2x2.complex` | 0 | 0 | 0 |
| `system.linear_2x2.nonhomogeneous` | 0 | 0 | 0 |
| `system.linear_2x2.real_distinct` | 0 | 0 | 0 |
| `system.linear_2x2.repeated` | 0 | 0 | 0 |

---

## 這份初篩**沒有**回答的事

- **「這題出得好不好」**——§A6 的三件事裡，「敘述像不像上課的講法」與「難度階梯合不合理」最後都要人看。
- **數學對不對**——那是 1394 項自動測試在守的，不在這裡。
- **`note` 說的理由對不對**——C2 只看它像不像理由，不看它是不是真的。
