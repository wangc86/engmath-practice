r"""手寫 SVG 相圖（PLAN.md §2.11，階段 2B 的 2B6）。

## 為什麼這個檔案在 `app/generator/` 的第一層，而不是 `systems/` 裡面

它與 `pretty.py` 是同一類東西：**一個沒有註冊任何題型的共用工具**。
D16 的子目錄是按**章節**切的（`ode/`、`systems/`、`fourier/`），而
`pretty.py` 從一開始就留在第一層——理由是它不屬於任何一章。相圖同理，
而且它比 `pretty.py` 更明顯：`classify()` 只吃一個矩陣，
它不知道也不需要知道呼叫它的是哪一個題型（甚至日後非線性系統的
平衡點分類也用得到同一張表）。PLAN §6 的 2B6 那一列寫的正是
`generator/plot.py`。

⛔ **這一輪沒有搬動任何既有檔案**（工作項 2a0 仍然保留給老師，
沙箱不能 unlink，見 CLAUDE.md）。

---

## 為什麼是手寫字串而不是 matplotlib（§2.11.2）

決定性的一點：**對線性系統，這張圖是解析的。** 軌跡有封閉解，
所以畫一條軌跡不需要任何數值積分器——它是「算一個矩陣指數、掃一串 $t$」。
`streamplot` 是為「只知道向量場、不知道解」設計的，用在這裡等於
用一個數值方法去解一個我們已經有答案的問題。

換到的四件事：無新相依、輸出小十倍、樣式可用 CSS 變數、
**而且座標是我們自己算的所以可以逐點斷言**（`tests/test_plot.py`）。
誠實的代價：箭頭與裁切要自己刻，圖比 matplotlib 樸素。

### 落地時與 §2.11.2 的一處差異，而且它讓測試變強了

規劃說的是「軌跡的封閉解**逐步解答裡本來就算出來了**」，讀起來像是
本模組應該去拿 generator 算好的 $C_1 e^{\lambda_1 t}\mathbf{v}_1 + \cdots$。
**落地時沒有那樣做**：本模組只吃一個整數矩陣 $A$，自己用
**矩陣指數的封閉形式**（`_flow()`，三個分支）算 $\mathbf{x}(t) = e^{At}\mathbf{x}_0$。

兩個好處，第二個才是重點：

1. 相圖變成 $A$ 的**純函式**——四個系統題型（含日後的）共用同一段程式，
   呼叫端不必把自己的解形式交出來。
2. ⛔ **它與逐步解答是兩條獨立的路。** 若相圖照抄 generator 算好的解，
   「軌跡切線平行於 $A\mathbf{p}$」這項斷言就會退化成
   「我們把同一段程式跑了兩次」——**一個把重根情形的 $\mathbf{v}t$ 項漏掉的
   bug 會同時漏在兩邊，然後測試全綠**。現在那項斷言是真的交叉驗證。

---

## §7 #25 的決定（箭頭怎麼畫）——落地時決定，理由與代價見 PLAN

**軌跡上畫方向箭頭；特徵方向線不畫箭頭**，改用顏色（流入／流出）
加上 `λ = …` 的文字標籤來表達方向。方向場的密度定在 $11\times 11$。
完整理由寫在 PLAN §7 的已決定表，這裡只留一句最短的：
特徵方向線通過原點，而原點附近正是軌跡箭頭最密的地方；
在那裡再放同一個箭頭字形，讀者分不出「這條線是一條剛好是直線的軌跡」
還是「這是一個特殊方向」。
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

# --- 畫布幾何 -------------------------------------------------------------

#: 數學座標的範圍：$[-LIM, LIM]^2$。
LIM = 3.0
#: 畫布邊長（px，viewBox 單位）。**正方形是硬性的**——長寬比一歪，
#: 螺旋看起來就像橢圓、中心看起來就像螺旋（§2.11.3 第 1 點）。
SIZE = 320.0
#: 每一個數學單位對應幾個 px。
SCALE = SIZE / (2 * LIM)

#: 方向場的格點數（每邊）。§2.11.3 規劃 11×11，實測落在大小預算內，照做。
#: ⚠️ **這個數字有大小上的後果**：它是二次的，調到 21 會讓 SVG 直接翻四倍。
#: `test_the_portrait_stays_within_its_size_budget` 是擋這件事的那道網子。
FIELD_N = 11
#: 方向場箭頭的長度（px），固定。照真實大小畫的話邊緣的箭頭會蓋住整張圖，
#: 而中間的縮成一點。
FIELD_ARROW_PX = 9.0
#: 方向場格點往內縮多少（以 LIM 為單位）。
#:
#: ⚠️ **不縮的話最外圈的箭頭會有一半在 viewBox 外面**（箭頭以格點為中心，
#: 各往兩邊推半個長度）。瀏覽器預設不裁切 SVG 的內容，所以那半截會畫到
#: 卡片的版面上——而它很細、顏色很淡，看起來只像一條分隔線。
#: `test_every_coordinate_is_inside_the_viewbox` 盯著這件事。
FIELD_INSET = 0.06
#: $|A\mathbf{p}|$ 小於這個值的格點跳過——那裡的方向是數值噪音。
FIELD_MIN_SPEED = 1e-6

#: 代表性軌跡的條數。
N_TRAJECTORIES = 8
#: 軌跡取樣時每一小段的目標螢幕長度（px）。**這是取樣密度，不是積分步長**
#: ——每一個點都由封閉解 $e^{At}\mathbf{x}_0$ 精確算出，誤差不累積。
SEGMENT_PX = 9.0
#: 單一方向的取樣點數上限（防呆兼控制檔案大小）。
MAX_POINTS = 70
#: 座標超過畫布多少倍就停止取樣。
ESCAPE = 1.35
#: 靠平衡點多近就停止取樣（以 LIM 為單位）。
#:
#: ⚠️ **這不只是省位元組，它是可讀性的主要旋鈕。** 沒有它的時候，
#: 螺旋往內捲的那一半會在原點附近繞七八圈、節點的每一條軌跡都貼著
#: 慢特徵方向擠成一團——**圖的正中央會變成一坨墨**，而那正是學生最需要
#: 看清楚的地方。順帶把單張 SVG 從約 16 KB 壓到約 10 KB。
NEAR_EQUILIBRIUM = 0.045

#: 數值溢位的護欄：$e^{\lambda t}$ 在極端 $t$ 上會爆掉，而爆掉之後
#: 進到 SVG 的是 `inf`／`nan`，**瀏覽器會安靜地丟掉整條路徑**（§2.11.4 第一層）。
HUGE = 1e6


def _to_screen(x: float, y: float) -> tuple[float, float]:
    r"""數學座標 → 螢幕座標。

    ⚠️ **這裡的減號是整個模組最容易錯、而且錯了看起來最正常的一個字元。**
    數學的 $y$ 軸向上、SVG 的 $y$ 軸向下。忘記翻轉的症狀是整張圖上下顛倒，
    而上下顛倒的螺旋**就是旋轉方向相反的螺旋**——它看起來完全合理，
    只是錯的。`test_the_y_axis_is_flipped` 盯著這一行。
    """
    return SIZE / 2 + x * SCALE, SIZE / 2 - y * SCALE


# --- 分類（§2.5(e) 的表，改成英文並補上邊界情形）---------------------------
#
# ⛔ **全部用整數運算，不准浮點。** A 是整數矩陣，所以 tr、det、Δ 都是整數，
# 三個分支判斷因此是精確的。$\Delta = 0$ 的退化節點是最容易被浮點誤判的一格
# ——`0.9999999` 會被判成 $\Delta > 0$，於是一個退化節點被畫成節點，
# 而那張圖看起來完全正常。

#: 分類標籤（英文，D5）。**這是圖上與逐步解答共用的唯一一份**。
SADDLE = "saddle point"
STABLE_NODE = "stable node"
UNSTABLE_NODE = "unstable node"
STABLE_DEGENERATE_NODE = "stable degenerate node"
UNSTABLE_DEGENERATE_NODE = "unstable degenerate node"
#: $A = \lambda I$。**這一格與退化節點不是同一件事**，雖然兩者的 $\Delta$ 都是 0：
#: 星形節點的幾何重數是 2（每個方向都是特徵方向，軌跡是直線），
#: 退化節點的幾何重數是 1（所有軌跡都彎向同一條線）。
#: ⚠️ $(\operatorname{tr}, \det, \Delta)$ **分不出這兩格**，所以這裡多看一眼
#: 矩陣本身——而下面第三層那條「用特徵值重算一次」的獨立路徑也分不出來
#: （兩者的特徵值一模一樣），這是那條交叉驗證的一個誠實的盲點。
STABLE_STAR_NODE = "stable star node"
UNSTABLE_STAR_NODE = "unstable star node"
CENTER = "center"
STABLE_SPIRAL = "stable spiral"
UNSTABLE_SPIRAL = "unstable spiral"
NON_ISOLATED = "non-isolated equilibrium"

#: 每個標籤的穩定性一句話（放在括號裡給學生看）。
STABILITY = {
    SADDLE: "unstable",
    STABLE_NODE: "asymptotically stable",
    UNSTABLE_NODE: "unstable",
    STABLE_DEGENERATE_NODE: "asymptotically stable",
    UNSTABLE_DEGENERATE_NODE: "unstable",
    STABLE_STAR_NODE: "asymptotically stable",
    UNSTABLE_STAR_NODE: "unstable",
    CENTER: "stable but not asymptotically stable",
    STABLE_SPIRAL: "asymptotically stable",
    UNSTABLE_SPIRAL: "unstable",
    NON_ISOLATED: "not isolated",
}


def _entries(A) -> tuple[int, int, int, int]:
    """把 SymPy Matrix、巢狀 list 或 4-tuple 都收成四個整數。

    ⚠️ **`int()` 在這裡不是型別轉換，是一個斷言**：本模組全部的精確性
    都建立在「$A$ 是整數矩陣」上（反向構造用 $\\det P = \\pm1$ 保證了這件事）。
    哪天有人餵進一個有理數矩陣，這裡會拋 `TypeError` 而不是安靜地取整
    ——安靜地取整會畫出一張與題目無關、但看起來完全正常的圖。
    """
    if hasattr(A, "tolist"):
        rows = A.tolist()
    else:
        rows = list(A)
    if len(rows) == 2 and not isinstance(rows[0], (list, tuple)):
        flat = list(rows[0]) + list(rows[1])          # 已經是兩個 row
    else:
        flat = [c for row in rows for c in row]
    out = []
    for c in flat:
        value = int(c)
        if value != c:
            raise TypeError(f"相圖只接受整數矩陣，收到 {c!r}")
        out.append(value)
    if len(out) != 4:
        raise ValueError(f"相圖只畫 2×2 系統，收到 {len(out)} 個元素")
    return tuple(out)  # type: ignore[return-value]


def invariants(A) -> tuple[int, int, int]:
    r"""$(\operatorname{tr}A, \det A, \Delta = \operatorname{tr}^2 - 4\det)$，全部是整數。"""
    a, b, c, d = _entries(A)
    tr = a + d
    det = a * d - b * c
    return tr, det, tr * tr - 4 * det


def classify(A) -> str:
    r"""平衡點的分類標籤，只由 $(\operatorname{tr}A, \det A, \Delta)$ 決定。

    這是**查表的那一條路**。`tests/test_plot.py` 用一條完全不同的路
    （`A.eigenvals()` 的實部符號與虛部是否為零）重算一次並要求一致
    ——§2.11.4 第三層，與 §2.10.4 的 Fourier 閘門、§2.4(g) 的 Laplace
    交叉驗證是同一個模式。
    """
    a, b, c, d = _entries(A)
    tr, det, disc = invariants(A)
    if det == 0:
        # 有一個零特徵值 → 平衡點不是孤立的（整條直線都是平衡點）
        return NON_ISOLATED
    if det < 0:
        return SADDLE
    if disc > 0:
        return STABLE_NODE if tr < 0 else UNSTABLE_NODE
    if disc == 0:
        if b == 0 and c == 0:              # A = λI：星形節點，不是退化節點
            return STABLE_STAR_NODE if tr < 0 else UNSTABLE_STAR_NODE
        return STABLE_DEGENERATE_NODE if tr < 0 else UNSTABLE_DEGENERATE_NODE
    if tr == 0:
        return CENTER
    return STABLE_SPIRAL if tr < 0 else UNSTABLE_SPIRAL


def describe(A) -> str:
    """給逐步解答用的一句話，例如 ``"a saddle point (unstable)"``。

    冠詞在這裡處理，呼叫端只要寫 ``f"… identify the origin as {describe(A)}."``。
    """
    label = classify(A)
    article = "an" if label[0] in "aeiou" else "a"
    return f"{article} {label} ({STABILITY[label]})"


# --- 軌跡：矩陣指數的封閉形式 ---------------------------------------------

Flow = Callable[[float], tuple[float, float, float, float]]


def _flow(A) -> Flow:
    r"""回傳 $t \mapsto e^{At}$（攤平成四個 float），三個分支都是**封閉形式**。

    - $\Delta > 0$（實相異）：$e^{At} = \dfrac{e^{\lambda_1 t}(A - \lambda_2 I)
      - e^{\lambda_2 t}(A - \lambda_1 I)}{\lambda_1 - \lambda_2}$
    - $\Delta = 0$（重根）：$e^{At} = e^{\lambda t}\bigl(I + t(A - \lambda I)\bigr)$
    - $\Delta < 0$（複數）：$e^{At} = e^{\alpha t}\bigl(\cos\beta t\, I
      + \frac{\sin\beta t}{\beta}(A - \alpha I)\bigr)$

    ⚠️ 分支是用**整數**的 $\Delta$ 判的（見 `classify` 上方的說明），
    所以「重根」這一格不會被浮點誤差擠到別的分支去。
    """
    a, b, c, d = _entries(A)
    tr, _det, disc = invariants(A)

    if disc > 0:
        root = math.sqrt(disc)
        l1, l2 = (tr + root) / 2, (tr - root) / 2
        gap = l1 - l2

        def flow_distinct(t: float):
            e1, e2 = math.exp(l1 * t), math.exp(l2 * t)
            # (e1*(A - l2 I) - e2*(A - l1 I)) / (l1 - l2)
            return (
                (e1 * (a - l2) - e2 * (a - l1)) / gap,
                (e1 * b - e2 * b) / gap,
                (e1 * c - e2 * c) / gap,
                (e1 * (d - l2) - e2 * (d - l1)) / gap,
            )

        return flow_distinct

    if disc == 0:
        lam = tr / 2

        def flow_repeated(t: float):
            e = math.exp(lam * t)
            return (
                e * (1 + t * (a - lam)),
                e * (t * b),
                e * (t * c),
                e * (1 + t * (d - lam)),
            )

        return flow_repeated

    alpha = tr / 2
    beta = math.sqrt(-disc) / 2

    def flow_complex(t: float):
        e = math.exp(alpha * t)
        co, si = math.cos(beta * t), math.sin(beta * t) / beta
        return (
            e * (co + si * (a - alpha)),
            e * (si * b),
            e * (si * c),
            e * (co + si * (d - alpha)),
        )

    return flow_complex


def _apply(m: Sequence[float], x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[1] * y, m[2] * x + m[3] * y


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) and abs(v) < HUGE for v in values)


def _t_budget(A) -> float:
    r"""單一方向最多掃到 $|t|$ 多大。

    只對**有旋轉的**情形（中心與螺旋）真的起作用：中心的軌跡是閉合的，
    掃超過一個週期就是把同一條曲線再畫一遍——位元組多一倍、畫面完全一樣。
    其餘情形交給「跑出畫布」與「接近平衡點」兩個條件收尾，這裡給一個
    寬鬆的上界就好。
    """
    _tr, _det, disc = invariants(A)
    if disc < 0:
        beta = math.sqrt(-disc) / 2
        return 0.62 * (2 * math.pi / beta)
    return 1e3


def _sample_half(flow: Flow, A4, x0: tuple[float, float], sign: int,
                 t_budget: float) -> list[tuple[float, float]]:
    """從 $t = 0$ 往一個方向掃出一串點（不含起點）。

    步長由**螢幕上的速度**決定：$\\mathrm{d}t = \\ell / |A\\mathbf{x}|$，
    這樣快的地方點少、慢的地方點多，畫出來每一小段長度差不多。

    ⚠️ **這是取樣，不是數值積分。** 每一個點都由封閉解 $e^{At}\\mathbf{x}_0$
    直接算出來，只有「下一個 $t$ 取多少」是自適應的——所以誤差不累積，
    步長取得再粗也只是線段變長，不會讓軌跡漂到別條曲線上去。
    """
    a, b, c, d = A4
    target = SEGMENT_PX / SCALE
    points: list[tuple[float, float]] = []
    t = 0.0
    x, y = x0
    for _ in range(MAX_POINTS):
        speed = math.hypot(a * x + b * y, c * x + d * y)
        dt = target / speed if speed > 1e-9 else target
        dt = min(max(dt, 1e-4), 0.35)
        t += sign * dt
        if abs(t) > t_budget:
            break
        m = flow(t)
        if not _finite(*m):
            break
        x, y = _apply(m, *x0)
        if not _finite(x, y):
            break
        points.append((x, y))
        if max(abs(x), abs(y)) > LIM * ESCAPE:
            break
        if math.hypot(x, y) < LIM * NEAR_EQUILIBRIUM:
            break
    return points


def trajectory(A, x0: tuple[float, float]) -> list[tuple[float, float]]:
    r"""通過 $\mathbf{x}_0$ 的一整條軌跡，依 $t$ 由小到大排列。

    公開它（而不是藏在 `phase_portrait_svg` 裡）是為了測試：
    §2.11.4 第二層要逐段檢查「相鄰兩點的連線平行於中點處的 $A\mathbf{p}$」。
    """
    flow = _flow(A)
    A4 = _entries(A)
    budget = _t_budget(A)
    back = _sample_half(flow, A4, x0, -1, budget)
    forward = _sample_half(flow, A4, x0, +1, budget)
    return list(reversed(back)) + [x0] + forward


def _rotation_axis(A) -> float:
    r"""中心／螺旋的軌跡橢圓，**長軸**的方向角（弧度）。

    軌跡是 $P$ 把一個圓映過去的橢圓：取任一非零 $\mathbf{a}$，
    令 $\mathbf{b} = (\alpha I - A)\mathbf{a}/\beta$，則
    $A\mathbf{a} = \alpha\mathbf{a} - \beta\mathbf{b}$ 且
    $A\mathbf{b} = \beta\mathbf{a} + \alpha\mathbf{b}$（2×2 的
    Cayley–Hamilton 保證後者），所以 $P = [\mathbf{a}\;\mathbf{b}]$
    把單位圓送成軌跡橢圓。長軸就是 $PP^{\mathsf T}$ 的最大特徵向量方向，
    角度有封閉式 $\tfrac12\arctan\!\big(2m_{12},\, m_{11}-m_{22}\big)$。

    ⚠️ **為什麼不用一個寫死的角度**（第一版是 0.7 弧度）：那樣的話
    起點會不會落在長軸上完全看運氣，而**落在短軸上的後果是所有軌跡
    一出生就衝出畫布**、只剩幾段殘骸——那是一張看起來「圖畫壞了」
    但每一條斷言都通過的圖。
    """
    a, b, c, d = _entries(A)
    tr, _det, disc = invariants(A)
    alpha = tr / 2
    beta = math.sqrt(-disc) / 2
    # a = e₁，b = (αI − A)e₁ / β
    ax, ay = 1.0, 0.0
    bx, by = (alpha - a) / beta, (-c) / beta
    m11 = ax * ax + bx * bx
    m12 = ax * ay + bx * by
    m22 = ay * ay + by * by
    return 0.5 * math.atan2(2 * m12, m11 - m22)


def _seeds(A) -> list[tuple[float, float]]:
    r"""代表性軌跡的起點。

    兩種佈點，因為一種佈不好兩種圖：

    - **中心與轉得比長得快的螺旋**（$|\alpha| < \beta$）沿**軌跡橢圓的長軸**
      由內而外佈點（見 `_rotation_axis`）。它們的軌跡是同一條曲線的
      旋轉／縮放版本，在圓上佈點會得到八條互相重疊的曲線；
      而射線的方向不能寫死，理由見那支函式。
    - **其餘全部**（節點、鞍點、退化節點，**以及長得比轉得快的螺旋**）
      在小圓上均勻佈點，讓每一條代表不同的 $(C_1, C_2)$ 方向。
      角度刻意偏移半格，避免起點正好落在特徵方向上（那條軌跡會退化成
      一條直線，與特徵方向線畫在一起）。

    ⚠️ **那個 $|\alpha| < \beta$ 的界線是實測調出來的，不是理論。**
    $|\alpha| \ge \beta$ 時每轉一圈半徑要變 $e^{2\pi|\alpha|/\beta} \ge 535$ 倍，
    一條軌跡在畫布裡只走得到小半圈——於是「同一條曲線的旋轉版本」這個論證
    在視覺上失效，五條從同一條射線出發的軌跡會全部擠在同一個象限，
    另外半張圖一條軌跡都沒有。
    """
    label = classify(A)
    tr, _det, disc = invariants(A)
    fast_rotation = disc < 0 and abs(tr / 2) < math.sqrt(-disc) / 2
    if label in (CENTER, STABLE_SPIRAL, UNSTABLE_SPIRAL) and fast_rotation:
        n = 5
        angle = _rotation_axis(A)
        return [
            (LIM * (0.16 + 0.82 * k / (n - 1)) * math.cos(angle),
             LIM * (0.16 + 0.82 * k / (n - 1)) * math.sin(angle))
            for k in range(n)
        ]
    r = LIM * 0.30
    return [
        (r * math.cos(2 * math.pi * (k + 0.35) / N_TRAJECTORIES),
         r * math.sin(2 * math.pi * (k + 0.35) / N_TRAJECTORIES))
        for k in range(N_TRAJECTORIES)
    ]


def eigen_directions(A) -> list[tuple[float, tuple[float, float]]]:
    r"""實特徵值與對應的特徵方向 $[(\lambda, (v_x, v_y)), \dots]$。

    複數特徵值回傳空清單（沒有實的不動方向可畫）。重根回傳一筆
    ——**幾何重數是 1，所以只有一個方向**，而那正是退化節點看起來
    「所有軌跡都貼著同一條線離開」的原因。
    """
    a, b, c, d = _entries(A)
    tr, _det, disc = invariants(A)
    if disc < 0:
        return []
    root = math.sqrt(disc)
    lams = [(tr + root) / 2] if disc == 0 else [(tr + root) / 2, (tr - root) / 2]
    out = []
    for lam in lams:
        # (A - λI)v = 0 → v = (b, λ-a) 或 (λ-d, c)，取比較不接近零向量的那一個
        cand = [(b, lam - a), (lam - d, c)]
        vx, vy = max(cand, key=lambda v: math.hypot(*v))
        norm = math.hypot(vx, vy)
        if norm < 1e-9:                     # A = λI，整個平面都是特徵方向
            continue
        out.append((lam, (vx / norm, vy / norm)))
    return out


# --- SVG 組裝 -------------------------------------------------------------
#
# 樣式走 CSS 變數 + 十六進位 fallback，寫在 presentation attribute 上
# （不放 `<style>` 區塊——inline SVG 的 `<style>` 是全域 CSS，
# 一頁二十張圖就是二十份一模一樣的規則）。
# 變數定義在 `app/static/style.css` 的 `:root`；fallback 讓
# `scripts/preview.py` 產的獨立 HTML 與任何其他脈絡都仍然好看。
#
# ⚠️ presentation attribute 裡的 `var()` 需要瀏覽器支援。Chrome 與 Firefox
# 都支援，而 D45 已經明文只支援這兩家——這不是新的相容性風險。

_C_GRID = "var(--pp-grid, #eceff3)"
_C_AXIS = "var(--pp-axis, #b8c0c9)"
_C_FIELD = "var(--pp-field, #9aa5b1)"
_C_TRAJ = "var(--pp-traj, #2b6cb0)"
_C_IN = "var(--pp-inflow, #1f7a44)"      # λ < 0：沿這個方向流進原點
_C_OUT = "var(--pp-outflow, #b32d2e)"    # λ > 0：流出
_C_INK = "var(--pp-ink, #1f2933)"
_C_MUTED = "var(--pp-muted, #6b7280)"


def _n(v: float) -> str:
    """座標格式化。一位小數就夠（畫布 320 px），而且省下大量位元組。"""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _marker_suffix(A) -> str:
    """marker 的 id 後綴。

    ⚠️ **id 在 HTML 文件裡是全域的**，而一頁上會同時出現二十張相圖
    （`preview.py` 的審圖模式）。同一個 $A$ 產生同一個後綴是刻意的：
    重複的定義是無害的（內容逐字相同），而**不同的 $A$ 一定拿到不同的 id**,
    所以不會出現「第二張圖的箭頭指向第一張圖的定義」這種只在多圖頁面上
    才出現、單張測試永遠抓不到的問題。
    """
    a, b, c, d = _entries(A)
    return f"{a}_{b}_{c}_{d}".replace("-", "n")


def _polyline_runs(points: Iterable[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """把一條軌跡切成「連續留在畫布內」的幾段。

    裁切做在這裡而不是用 `<clipPath>`，是為了讓 §2.11.4 第二層那項
    「所有座標都落在 viewBox 內」變成一句可以直接斷言的話——
    `clipPath` 會讓超出的座標仍然留在檔案裡，那項測試就只能改成
    「有沒有寫 clipPath」，而那是在測拼字不是在測幾何。
    """
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, y in points:
        if abs(x) <= LIM and abs(y) <= LIM:
            current.append((x, y))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return [run for run in runs if len(run) >= 2]


def _arrow_at(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    """軌跡中段的一支方向箭頭（螢幕座標的起點與終點）。

    ⛔ **沒有這支箭頭，穩定節點與不穩定節點的圖長得一模一樣**
    （§2.11.3 第 5 點）——這是這張圖「畫錯了但看起來沒錯」風險最高的一項。
    """
    if len(points) < 3:
        return None
    i = len(points) // 2
    x1, y1 = _to_screen(*points[i - 1])
    x2, y2 = _to_screen(*points[i])
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    # 從中點往兩側各推 4 px，長度固定，方向就是 t 增加的方向
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    ux, uy = dx / length, dy / length
    return mx - 4 * ux, my - 4 * uy, mx + 4 * ux, my + 4 * uy


def _lambda_text(lam: float) -> str:
    """特徵值的標籤。整數就印整數（$A$ 是整數矩陣時多半如此）。"""
    if abs(lam - round(lam)) < 1e-9:
        return f"λ = {round(lam)}"
    return f"λ = {lam:.2f}"


def phase_portrait_svg(A) -> str:
    r"""$\mathbf{x}' = A\mathbf{x}$ 的相圖，一段可以直接內嵌的 SVG。

    ⛔ **這段字串一定要渲染在 `<details>` 裡面**（D13、§2.11.1）。
    一張鞍點圖等於直接告訴學生兩個特徵值異號、一張同心橢圓圖等於告訴學生
    $\operatorname{tr}A = 0$——**插圖會把答案洩掉，而且是靜默地洩**：
    頁面不會壞、不會拋錯，只是這題白出了。
    範本那一端由 `tests/test_web.py` 的洩題測試盯著。
    """
    a4 = _entries(A)
    label = classify(A)
    suffix = _marker_suffix(A)
    field_marker = f"ppf{suffix}"
    traj_marker = f"ppt{suffix}"

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(SIZE)} {_n(SIZE)}"'
        f' class="phase-portrait" role="img"'
        f' aria-label="Phase portrait of the system; the origin is {label}.">',
        f"<title>Phase portrait — {label}</title>",
        "<defs>"
        f'<marker id="{field_marker}" viewBox="0 0 6 6" refX="5" refY="3"'
        ' markerWidth="5" markerHeight="5" orient="auto">'
        f'<path d="M0 0.7 L5.4 3 L0 5.3 z" fill="{_C_FIELD}"/></marker>'
        f'<marker id="{traj_marker}" viewBox="0 0 6 6" refX="5" refY="3"'
        ' markerWidth="6" markerHeight="6" orient="auto">'
        f'<path d="M0 0.5 L5.6 3 L0 5.5 z" fill="{_C_TRAJ}"/></marker>'
        "</defs>",
    ]

    # 1. 格線與座標軸
    grid = []
    for k in range(-int(LIM), int(LIM) + 1):
        if k == 0:
            continue
        gx, _ = _to_screen(k, 0)
        _, gy = _to_screen(0, k)
        grid.append(f'<line x1="{_n(gx)}" y1="0" x2="{_n(gx)}" y2="{_n(SIZE)}"/>')
        grid.append(f'<line x1="0" y1="{_n(gy)}" x2="{_n(SIZE)}" y2="{_n(gy)}"/>')
    out.append(
        f'<g class="pp-grid" stroke="{_C_GRID}" stroke-width="1">' + "".join(grid) + "</g>"
    )
    cx, cy = _to_screen(0, 0)
    out.append(
        f'<g class="pp-axes" stroke="{_C_AXIS}" stroke-width="1">'
        f'<line x1="0" y1="{_n(cy)}" x2="{_n(SIZE)}" y2="{_n(cy)}"/>'
        f'<line x1="{_n(cx)}" y1="0" x2="{_n(cx)}" y2="{_n(SIZE)}"/></g>'
    )

    # 2. 方向場：固定長度，方向為 Ap/|Ap|
    a, b, c, d = a4
    field = []
    span = LIM * (1 - FIELD_INSET)
    for i in range(FIELD_N):
        px = -span + 2 * span * i / (FIELD_N - 1)
        for j in range(FIELD_N):
            py = -span + 2 * span * j / (FIELD_N - 1)
            ux, uy = a * px + b * py, c * px + d * py
            speed = math.hypot(ux, uy)
            if speed < FIELD_MIN_SPEED:      # 原點附近：方向是噪音，跳過
                continue
            sx, sy = _to_screen(px, py)
            # 螢幕方向：x 不變、y 反號（見 _to_screen 的說明）
            dx = FIELD_ARROW_PX * ux / speed
            dy = -FIELD_ARROW_PX * uy / speed
            field.append(
                f'<line x1="{_n(sx - dx / 2)}" y1="{_n(sy - dy / 2)}"'
                f' x2="{_n(sx + dx / 2)}" y2="{_n(sy + dy / 2)}"/>'
            )
    out.append(
        f'<g class="pp-field" stroke="{_C_FIELD}" stroke-width="1"'
        f' marker-end="url(#{field_marker})">' + "".join(field) + "</g>"
    )

    # 3. 特徵方向線（僅實特徵值）。§7 #25：**線上不放箭頭**，
    #    改用顏色（流入綠／流出紅）與 λ 的數值標籤表示方向。
    eig = []
    for lam, (vx, vy) in eigen_directions(A):
        scale = LIM / max(abs(vx), abs(vy))
        x1, y1 = _to_screen(-scale * vx, -scale * vy)
        x2, y2 = _to_screen(scale * vx, scale * vy)
        colour = _C_IN if lam < 0 else _C_OUT
        eig.append(
            f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"'
            f' stroke="{colour}" stroke-width="1.8"/>'
        )
        # 標籤放在線上約六成的位置，再沿**法線**推開 11 px。
        # 沿線方向推（原本的作法）會讓水平的特徵方向線把標籤直接壓在 x 軸
        # 與角落的座標軸標籤上——那不是美觀問題，是**兩層字疊在一起誰都看不懂**。
        tx, ty = _to_screen(0.60 * scale * vx, 0.60 * scale * vy)
        # ⚠️ 法線要在**螢幕座標**上算。用數學座標的法線再直接加到螢幕座標上
        # 是一個很安靜的錯誤：它在 45° 的線上看起來完全正常，只有水平／垂直
        # 附近才會把標籤推到線的另一邊去。
        nx, ny = -(y2 - y1), (x2 - x1)
        if ny > 0:                             # 一律往螢幕上方推，比較不會壓到軸
            nx, ny = -nx, -ny
        norm = math.hypot(nx, ny) or 1.0
        eig.append(
            f'<text x="{_n(tx + 11 * nx / norm)}" y="{_n(ty + 11 * ny / norm)}"'
            f' font-size="11" text-anchor="middle" fill="{colour}">'
            f"{_lambda_text(lam)}</text>"
        )
    if eig:
        out.append('<g class="pp-eig" fill="none">' + "".join(eig) + "</g>")

    # 4. 代表性軌跡 + 5. 軌跡上的方向箭頭
    paths, arrows = [], []
    for seed in _seeds(A):
        for run in _polyline_runs(trajectory(A, seed)):
            pts = " ".join(f"{_n(sx)},{_n(sy)}" for sx, sy in map(lambda p: _to_screen(*p), run))
            paths.append(f'<polyline points="{pts}"/>')
            arrow = _arrow_at(run)
            if arrow is not None:
                x1, y1, x2, y2 = arrow
                arrows.append(
                    f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"/>'
                )
    out.append(
        f'<g class="pp-traj" fill="none" stroke="{_C_TRAJ}" stroke-width="1.4"'
        ' stroke-linejoin="round">' + "".join(paths) + "</g>"
    )
    out.append(
        f'<g class="pp-flow" stroke="{_C_TRAJ}" stroke-width="1.4"'
        f' marker-end="url(#{traj_marker})">' + "".join(arrows) + "</g>"
    )

    # 6. 平衡點與分類標籤
    out.append(
        f'<circle class="pp-eq" cx="{_n(cx)}" cy="{_n(cy)}" r="3.4" fill="{_C_INK}"/>'
    )
    # 分類標籤放**左下角**，不是左上角：最長的標籤是 "unstable degenerate node"
    # （24 個字），在 12 px 下約 145 px 寬，而 x₂ 的軸標籤就在 x = 167 的上緣
    # ——兩層字疊在一起。左下角沒有這個鄰居。
    out.append(
        f'<text class="pp-label" x="10" y="{_n(SIZE - 9)}" font-size="12"'
        f' fill="{_C_INK}">{label}</text>'
    )
    # 座標軸標籤。下標用 `<tspan>` 而不是 Unicode 的 ₁ ₂：後者在缺字的字型上
    # 會變成空白或豆腐，而**缺字是靜默的**——圖照樣畫出來，只是軸沒有名字。
    # 也刻意不用 `text-anchor="end"`：帶 `<tspan>` 的文字寬度由渲染器量，
    # 而不同渲染器量出來的結果不一樣（實測 cairosvg 會把 x₁ 推出畫布外）。
    sub = '<tspan font-size="8" dy="3">%s</tspan>'
    out.append(
        f'<text class="pp-axis-label" x="{_n(SIZE - 22)}" y="{_n(cy + 15)}"'
        f' font-size="11" fill="{_C_MUTED}">x{sub % "1"}</text>'
    )
    out.append(
        f'<text class="pp-axis-label" x="{_n(cx + 7)}" y="15"'
        f' font-size="11" fill="{_C_MUTED}">x{sub % "2"}</text>'
    )
    out.append("</svg>")
    return "".join(out)
