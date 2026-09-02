"""課程週次表，以及「哪一項內容屬於哪一週」（PLAN.md D52，v0.29 改用途）。

這個檔案是**純資料，沒有任何相依**——它不 import `app.generator`，也不 import
`app.routes.demos`。理由是 D21 的界線：出題引擎與展示區「只共用登入與
`UsageLog`，不共用抽象」（那兩樣在 v0.29 都沒有了，但界線本身沒有變）。
一份把兩邊的識別碼列在一起的清單**不是**一個共用抽象——它沒有型別、
沒有基底類別、沒有任何一邊要去實作的介面，它就是一張表。但如果這個檔案
import 了兩邊，它就變成一個接縫，而接縫會長出東西。所以它只認得**字串**；
把字串接回真正的題型與展示，是路由的事。

---

## ⚠️ v0.29：它的用途換了，而且降級了

v0.28 這張表是**開放閘門的依據**：老師在 `/admin/content` 上逐週開放內容，
未開放的東西學生連網址都打不進去。系統改為學生自行在自己的電腦上安裝
執行之後（D57），**那個用途整個消失了**——學生擁有自己那一份安裝，
任何閘門都是他自己可以改掉的一行程式碼，而假裝它擋得住只是自欺。

留下來的用途只有一個，但它站得住：**導覽**。學生找東西的動機是
「這週上課提到的那個」（這件事 §7 #34 早就寫過），所以出題頁的下拉選單
與展示索引都依週次分組，而不是依章節。

因此這一版拿掉的東西：

- `release_week` 改名為 **`primary_week`**。「release」在 v0.29 之後是一個
  不存在的概念，而**留著死掉的詞彙比留著死掉的程式碼更糟**——它會讓下一個
  人以為系統還有開放這件事，然後去找那個找不到的開關。
- `borrowed_ids_for_week()` 移除。它唯一的使用者是管理頁上那段
  「這一週也用得到、但由第 10 週開放」的說明，而管理頁沒有了。
- `ids_for_week()` 保留但語意收窄成「這一週要列出哪些東西」。

保存版本（含閘門那一套）在 tag `hosted-v1`。

---

## 週次表的來源

課程 16 週的主題由老師提供（v0.28）。日期（W1 = 2026/9/9，每週三）在
PLAN §6 那張表裡，**這裡刻意不存日期**——兩份日期會漂移，而這個檔案
需要的只有「第幾週」。

## 歸類的判準（三條，依序套用）

1. **內容在教材上第一次成立的那一週**。不是「用得到它的最早一週」，
   也不是「它最像哪一週」——而是「上完那一週的課之後，這一題／這一頁
   就有意義了」。
2. **跨週的東西記完整的區間，但列在最早的那一週底下**（見下面
   `primary_week`）。
3. **不猜老師沒說的事**。W8（SVD）、W11（轉移函數）、W14（可控可觀測性）、
   W15（PID）、W16（PINN／HNN）目前沒有任何內容，那就是空的——
   不硬把某個題型塞進去湊滿。空著本身是一個誠實的訊號。

### 逐項的歸類依據

**展示（6 項）**——這一組幾乎不需要判斷，因為每個展示的 `Demo.week`
欄位在它落地的那一輪就已經寫好了（§8.1 的准入判準本來就是按週次談的）。
這裡做的是把那個字串變成數字，並由 `test_curriculum.py` 的一項測試確認
兩邊沒有漂移。

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
  沒有回饋、沒有設定值。

**出題（14 項）**

* Fourier 四個 → **W3**。四個都是級數，不是變換。
  ⚠️ Parseval（v0.30 新增的 2B5）也在 W3：它用的是同一組係數，
  只是把它們平方之後加起來——沒有任何一步需要 W4 的變換。
  ⚠️ 半幅展開與奇偶性看起來「比較進階」，但它們是同一週的同一套積分。
* Laplace 兩個 → **W9**（課綱 W9 就是 Laplace）。
  ⚠️ **這裡有一個順序上的怪異，寫下來以免有人以為是筆誤**：`ode.laplace.ivp`
  要解一個二階常係數 ODE，而 ODE 本身排在 W10。課綱就是這個順序，
  本檔案照課綱走。
* 一階與二階 ODE 五個 → **W10**（ODE 與系統建模）。
* 2×2 線性系統五個 → **W10 與 W12–W13**。系統本身（$\\mathbf{x}' = A\\mathbf{x}$
  的解法、特徵值、相圖）在 W10 的「系統建模」就成立了；W12（狀態空間表示）
  與 W13（狀態空間分析）用的是同一個 $A$、同一組特徵值、同一張相圖，
  只是換了名字叫狀態矩陣。

---

## `primary_week`：跨週的東西列在**最早**的那一週底下

`weeks` 記的是「這一項在哪些週有意義」，但它在畫面上只出現一次，位置由
**`weeks[0]`** 決定。

v0.28 這個規則的理由是「多重擁有會讓關閉第 12 週安靜地關掉第 10 週開的
東西」。閘門沒有了，理由換成一個更平淡但一樣真的：**一個下拉選單不可以
把同一個題型列三次**。學生會以為那是三個不同的東西，而點下去出的是同一題。
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
    v0.29 起它直接出現在學生的下拉選單上（`Week 3 — Fourier series`），
    所以那條規則對它比以前更直接。
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

_WEEK_BY_NUMBER: dict[int, Week] = {week.number: week for week in WEEKS}


@dataclass(frozen=True)
class ContentItem:
    """一項內容（一個題型或一個展示）在課程上的位置。

    ⚠️ **這裡沒有標題、沒有說明、沒有難度。** 那些東西住在 `REGISTRY`
    與 `DEMOS` 裡，抄一份過來就是開一個會漂移的第二真相——而漂移的症狀是
    選單上的名字與內容頁上的名字不一樣，兩邊都不會報錯。
    """

    content_id: str
    kind: str
    #: 這一項在哪幾週有意義，由小到大。**畫面上的位置只看 `weeks[0]`**。
    weeks: tuple[int, ...]

    @property
    def primary_week(self) -> int:
        return self.weeks[0]

    @property
    def is_multi_week(self) -> bool:
        return len(self.weeks) > 1


#: 全部 20 項內容的歸類。**新增題型或展示時要在這裡加一列**，
#: 否則 `test_curriculum.py::test_every_registered_template_has_a_week` 會紅。
#:
#: 順序：先展示（依週次），再出題（依週次）。這只影響讀這個檔案的人，
#: 畫面上會自己依週次重新分組。
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
    ContentItem("fourier.parseval.series_sum", KIND_PRACTICE, (3,)),
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
    ContentItem("system.linear_2x2.classification", KIND_PRACTICE, (10, 12, 13)),
)

_BY_ID: dict[str, ContentItem] = {item.content_id: item for item in CONTENT}

#: 全部內容代號。
ALL_CONTENT_IDS: frozenset[str] = frozenset(_BY_ID)


def item_for(content_id: str) -> ContentItem | None:
    """查一項內容的歸類。查不到回 `None`——呼叫端必須自己決定怎麼辦。"""
    return _BY_ID.get(content_id)


def week_for(number: int) -> Week | None:
    return _WEEK_BY_NUMBER.get(number)


def ids_for_week(week: int, kind: str | None = None) -> tuple[str, ...]:
    """列在這一週底下的內容代號（`primary_week == week`），依代號排序。

    `kind` 給的話只回那一種（`KIND_PRACTICE` / `KIND_DEMO`）——出題頁與
    展示索引各要一半，而讓呼叫端自己過濾會讓那個 `if` 出現在兩個範本裡。
    """
    return tuple(
        sorted(
            item.content_id
            for item in CONTENT
            if item.primary_week == week and (kind is None or item.kind == kind)
        )
    )


def weeks_with_content(kind: str | None = None) -> tuple[Week, ...]:
    """有東西可列的那些週，依週次排序。

    ⚠️ **空的週次不回傳，而那不是「隱藏未完成的東西」（D24）。**
    差別在於這裡沒有任何一項內容存在——一個標題底下什麼都沒有的分組
    對學生只有一個意思：「這個系統壞了」。D24 禁止的是**陳列還沒做的東西**，
    不是禁止把空分組收起來。
    """
    return tuple(week for week in WEEKS if ids_for_week(week.number, kind))


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
