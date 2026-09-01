"""課程週次表，以及「哪一項內容屬於哪一週」的歸類（PLAN.md D52、§4.3a）。

這個檔案是**純資料，沒有任何相依**——它不 import `app.generator`，也不 import
`app.routes.demos`，更不碰資料庫。理由有兩個，而第二個比較重要：

1. **D21 的界線要守住。** 出題引擎與展示區「只共用登入與 `UsageLog`，
   不共用抽象」。一份把兩邊的識別碼列在一起的清單**不是**一個共用抽象——
   它沒有型別、沒有基底類別、沒有任何一邊要去實作的介面，它就是一張表。
   但如果這個檔案 import 了兩邊，它就會變成一個接縫，而接縫會長出東西。
   所以它只認得**字串**：`content_id` 是誰、長什麼樣，這裡完全不知道。
   把字串接回真正的題型與展示，是 `app/routes/release_admin.py` 的事。

2. **歸類必須可以被單獨測試。** `tests/test_release.py` 會拿這張表去對
   `REGISTRY` 與 `DEMOS`，斷言**兩邊逐項相符**——多一個沒歸類的題型會紅、
   多一個指向不存在內容的歸類也會紅。老師要求「歸類要放在程式碼裡可查、
   可測試的地方，不要散落在模板中」，這就是那個地方。

---

## 週次表的來源

課程 16 週的主題由老師提供（v0.28）。⚠️ **這比 PLAN §6 那張日期表多**：
那張表在 W8、W9、W12–W14、W16 寫的是「老師未提供」，現在全部有了。
日期（W1 = 2026/9/9，每週三）仍然由 §6 那張表負責，**這裡刻意不存日期**——
兩份日期會漂移，而這個檔案需要的只有「第幾週」。

## 歸類的判準（三條，依序套用）

1. **內容在教材上第一次成立的那一週**。不是「用得到它的最早一週」，
   也不是「它最像哪一週」——而是「上完那一週的課之後，這一題／這一頁
   就有意義了」。
2. **跨週的東西記完整的區間，但擁有它的是最早的那一週**（見下面
   `release_week` 的說明）。
3. **不猜老師沒說的事**。W8（SVD）、W11（轉移函數）、W14（可控可觀測性）、
   W15（PID）、W16（PINN／HNN）目前沒有任何內容，那就是空的——
   不硬把某個題型塞進去湊滿。空著本身是一個誠實的訊號。

### 逐項的歸類依據

**展示（6 項）**——這一組幾乎不需要判斷，因為每個展示的 `Demo.week`
欄位在它落地的那一輪就已經寫好了（§8.1 的准入判準本來就是按週次談的）。
這裡做的是把那個字串變成數字，並由 `test_every_demo_agrees_with_its_own_week_label`
確認兩邊沒有漂移。

* `demo.lti.convolution` → **W1–W2**。它是唯一橫跨兩週的：W1 講 LTI 的兩個
  假設、W2 講摺積是那兩個假設的後果，教材上是一條論證的兩半（§8.9.4）。
* `demo.fourier.additive` → **W3**（Fourier 級數）。
* `demo.transform.pulse` → **W4**（連續 Fourier 變換）。⚠️ 與上一項是**兩週**，
  不是同一個主題的第二頁：週期 vs 非週期。`template_id` 的第二段刻意不同
  就是為了這件事。
* `demo.spectrum.leakage` → **W5**（DFT 與 FFT）。
* `demo.sampling.aliasing` → **W6**（取樣定理）。
* `demo.filter.polezero` → **W7**（Z 轉換與數位濾波器）。D22 允許它順帶
  服務 W11 的頻率響應直覺，但**那不構成 W11 的歸類**——它裡面沒有受控體、
  沒有回饋、沒有設定值，一個 W11 才開得起來的學生會在那一頁找不到轉移函數。

**出題（14 項）**

* Fourier 三個（`fourier.series.full_range`、`fourier.series.half_range`、
  `fourier.symmetry.parity`）→ **W3**。三個都是級數，不是變換。
  ⚠️ 半幅展開與奇偶性看起來「比較進階」，但它們是同一週的同一套積分，
  分開到 W4 會讓學生在學變換的那一週回頭練級數。
* Laplace 兩個（`ode.laplace.transform`、`ode.laplace.ivp`）→ **W9**。
  課綱 W9 就是 Laplace（D47 落地時已經按這個週次做的）。
  ⚠️ **這裡有一個順序上的怪異，寫下來以免有人以為是筆誤**：`ode.laplace.ivp`
  要解一個二階常係數 ODE，而 ODE 本身排在 W10。課綱就是這個順序
  （Laplace 在前、ODE 在後），本檔案照課綱走，不自作主張把它挪到 W10——
  老師若覺得該挪，管理頁上一個核取方塊就改得動，而**改資料比改判斷便宜**。
* 一階與二階 ODE 五個（`ode.first_order.separable`、`.linear`、`.exact`、
  `ode.second_order.homogeneous`、`.undetermined`）→ **W10**（ODE 與系統建模）。
* 2×2 線性系統四個（`system.linear_2x2.*`）→ **W10 與 W12–W13**。
  依據：系統本身（$\mathbf{x}' = A\mathbf{x}$ 的解法、特徵值、相圖）在 W10
  的「系統建模」就成立了；而 W12（狀態空間表示）與 W13（狀態空間分析）
  用的是同一個 $A$、同一組特徵值、同一張相圖，只是換了名字叫狀態矩陣。
  **相圖因此也在這個區間裡**——它是這四個題型的附加呈現（`Problem.assets`），
  沒有獨立的開關，也不該有：一張相圖不能脫離它所屬的那一題被開放。

---

## `release_week`：跨週的東西由**最早**的那一週擁有

`weeks` 記的是「這一項在哪些週有意義」，但開放與否只由 **`weeks[0]`** 決定。
也就是說 `system.linear_2x2.*` 屬於 W10，W12 與 W13 只是「也用得到」。

⛔ **不要改成「屬於每一週」**，那個版本有一個安靜的失敗模式：老師在 W12
結束後按「關閉第 12 週」，四個系統題型會跟著被關掉——而它們在 W10 就開了、
學生正在期末複習用。頁面不會壞、不會報錯，只是那四個題型從選單上消失了，
而按下按鈕的人以為自己只關掉了狀態空間。

**現在這個版本的性質是一個分割**：每一項恰好屬於一週，所以管理頁由上往下
看一遍，每一列都只會被決定一次。代價是老師按「開放第 12 週」時系統題型
不會跟著開——所以管理頁在 W12、W13 底下**列出這些「別週擁有、本週也用得到」
的項目並註明它們歸屬哪一週**，讓那個空白是有解釋的，不是看起來壞掉。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 出題題型的內容種類。`content_id` 就是 `Template.template_id`。
KIND_PRACTICE = "practice"

#: 互動展示的內容種類。`content_id` 就是 `Demo.template_id`。
KIND_DEMO = "demo"

KINDS = (KIND_PRACTICE, KIND_DEMO)


@dataclass(frozen=True)
class Week:
    """課程的一週。

    `topic` 是**英文**（D5：介面語言為英文，不得出現中日韓字元）。
    它會出現在管理頁上，而管理頁雖然只有老師看得到，D5 沒有為它開例外——
    一個中英夾雜的介面會讓「頁面上不得出現中文」這條規則變成
    「除了某些頁面以外不得出現中文」，而那種規則守不住。
    """

    number: int
    topic: str


#: 16 週。順序就是 `number` 的順序，`WEEKS[i].number == i + 1` 由測試盯著。
WEEKS: tuple[Week, ...] = (
    Week(1, "LTI systems and signals"),
    Week(2, "Convolution and the impulse response"),
    Week(3, "Fourier series"),
    Week(4, "The continuous Fourier transform"),
    Week(5, "DFT and FFT"),
    Week(6, "The sampling theorem"),
    Week(7, "The z-transform and digital filters"),
    Week(8, "Singular value decomposition"),
    Week(9, "The Laplace transform"),
    Week(10, "Differential equations and system modelling"),
    Week(11, "Transfer functions and stability"),
    Week(12, "State-space representation"),
    Week(13, "State-space analysis"),
    Week(14, "Controllability and observability"),
    Week(15, "Feedback control and PID"),
    Week(16, "PINN and HNN"),
)

WEEK_NUMBERS: tuple[int, ...] = tuple(week.number for week in WEEKS)


@dataclass(frozen=True)
class ContentItem:
    """一項可以被單獨開放的內容。

    ⚠️ **這裡沒有標題、沒有說明、沒有難度。** 那些東西住在 `REGISTRY`
    與 `DEMOS` 裡，抄一份過來就是開一個會漂移的第二真相——而漂移的症狀是
    管理頁上的名字與學生看到的名字不一樣，兩邊都不會報錯。
    """

    content_id: str
    kind: str
    #: 這一項在哪幾週有意義，由小到大。**開放與否只看 `weeks[0]`**，
    #: 理由見模組說明最後一節。
    weeks: tuple[int, ...]

    @property
    def release_week(self) -> int:
        return self.weeks[0]

    @property
    def is_multi_week(self) -> bool:
        return len(self.weeks) > 1


#: 全部 20 項內容的歸類。**新增題型或展示時要在這裡加一列**，
#: 否則 `test_every_registered_template_has_a_week` 會紅。
#:
#: 順序：先展示（依週次），再出題（依週次）。這只影響讀這個檔案的人，
#: 管理頁自己會依週次重新分組。
CONTENT: tuple[ContentItem, ...] = (
    # --- 互動展示（PLAN.md §8）------------------------------------------
    ContentItem("demo.lti.convolution", KIND_DEMO, (1, 2)),
    ContentItem("demo.fourier.additive", KIND_DEMO, (3,)),
    ContentItem("demo.transform.pulse", KIND_DEMO, (4,)),
    ContentItem("demo.spectrum.leakage", KIND_DEMO, (5,)),
    ContentItem("demo.sampling.aliasing", KIND_DEMO, (6,)),
    ContentItem("demo.filter.polezero", KIND_DEMO, (7,)),
    # --- 出題題型（PLAN.md §2）------------------------------------------
    ContentItem("fourier.series.full_range", KIND_PRACTICE, (3,)),
    ContentItem("fourier.series.half_range", KIND_PRACTICE, (3,)),
    ContentItem("fourier.symmetry.parity", KIND_PRACTICE, (3,)),
    ContentItem("ode.laplace.transform", KIND_PRACTICE, (9,)),
    ContentItem("ode.laplace.ivp", KIND_PRACTICE, (9,)),
    ContentItem("ode.first_order.separable", KIND_PRACTICE, (10,)),
    ContentItem("ode.first_order.linear", KIND_PRACTICE, (10,)),
    ContentItem("ode.first_order.exact", KIND_PRACTICE, (10,)),
    ContentItem("ode.second_order.homogeneous", KIND_PRACTICE, (10,)),
    ContentItem("ode.second_order.undetermined", KIND_PRACTICE, (10,)),
    ContentItem("system.linear_2x2.real_distinct", KIND_PRACTICE, (10, 12, 13)),
    ContentItem("system.linear_2x2.repeated", KIND_PRACTICE, (10, 12, 13)),
    ContentItem("system.linear_2x2.complex", KIND_PRACTICE, (10, 12, 13)),
    ContentItem("system.linear_2x2.nonhomogeneous", KIND_PRACTICE, (10, 12, 13)),
)

_BY_ID: dict[str, ContentItem] = {item.content_id: item for item in CONTENT}

#: 全部內容代號。閘門與管理頁都以它為母集合。
ALL_CONTENT_IDS: frozenset[str] = frozenset(_BY_ID)


def item_for(content_id: str) -> ContentItem | None:
    """查一項內容的歸類。查不到回 `None`——呼叫端必須自己決定怎麼辦。

    ⚠️ **不要讓它在查不到的時候回一個「預設開放」的東西。** 這個函式的
    使用者是開放閘門，而閘門的預設必須是擋下來（與 §2.1 原則二、
    `Problem.verify_answer()` 的 `check is None` 同一條紀律）。
    """
    return _BY_ID.get(content_id)


def ids_for_week(week: int) -> tuple[str, ...]:
    """**由這一週擁有**的內容（`release_week == week`），依代號排序。

    這就是管理頁「Open week N」按鈕作用的範圍。
    """
    return tuple(
        sorted(
            item.content_id for item in CONTENT if item.release_week == week
        )
    )


def borrowed_ids_for_week(week: int) -> tuple[str, ...]:
    """這一週**也用得到、但不歸它管**的內容（`week in weeks` 但不是最早的那一週）。

    只用來在管理頁上解釋 W12／W13 為什麼看起來是空的。它不參與任何
    開放判定——`ids_for_week()` 與這個函式的結果永遠不交集。
    """
    return tuple(
        sorted(
            item.content_id
            for item in CONTENT
            if week in item.weeks and item.release_week != week
        )
    )


def week_label(item: ContentItem) -> str:
    """給人看的週次標籤，例如 ``"Week 3"``、``"Weeks 1-2"``、``"Weeks 10, 12-13"``。

    英文（D5）。連續的週次縮成區間，不連續的用逗號隔開。
    """
    parts: list[str] = []
    start = previous = item.weeks[0]
    for week in item.weeks[1:] + (None,):  # type: ignore[operator]
        if week is not None and week == previous + 1:
            previous = week
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        if week is not None:
            start = previous = week
    prefix = "Week" if len(item.weeks) == 1 else "Weeks"
    return f"{prefix} {', '.join(parts)}"
