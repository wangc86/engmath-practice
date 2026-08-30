"""相圖的四層測試（PLAN.md §2.11.4，階段 2B 的 **2B9**）。

先講清楚**做不到的事**：沒有辦法自動判斷一張圖「看起來對不對」。
能做的是把「會靜默出錯的方式」逐一堵掉——與 §1.7 對答案遮蔽、
裸露 LaTeX 的處理方式完全同一套思路。

四層，由外而內：

| 層 | 抓的是什麼 | 在這個檔案裡 |
|---|---|---|
| 1 結構良好 | SVG 解得開、有 viewBox、**每一個座標都是有限數** | ✅ |
| 2 幾何不變量 | 箭頭方向、軌跡切線、特徵方向、裁切、**$y$ 軸翻轉** | ✅ |
| 3 分類的雙路徑一致性 | 查表 vs 特徵值，加一張手算對照表 | ✅ |
| 4 人眼 | 好不好看、讀不讀得懂 | ❌ **只能是人**，見 `scripts/preview.py --portraits` |

⛔ **刻意不做像素級 golden file 比對。** 它會在任何一次無害的樣式調整
（改個顏色、挪個標籤）上變紅，而維護者很快就會養成「紅了就重新產生一次基準」
的習慣——那時它就完全不再是測試了。

---

## 為什麼第一層是四層裡最不可省的一層

SVG 路徑裡出現 `NaN`，瀏覽器的處理方式是**安靜地丟掉整條路徑**：
沒有錯誤、沒有警告、沒有主控台訊息，圖上就是少一條線。
而 NaN 在這裡很容易產生——正規化時除以 $|A\\mathbf{p}| = 0$、
特徵向量是零向量、$\\lambda$ 太大導致 $e^{\\lambda t}$ 溢位。

## 第二層的容差是量出來的，不是猜的

座標在輸出時被四捨五入到一位小數（省位元組），所以**斷言不可能是精確的**。
每一項的容差旁邊都寫了它在守什麼、以及實測的最差值是多少——
一個「調到剛好會過」的容差與一個沒有測試的函式差別不大。
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import pytest
import sympy as sp

from app.generator import generate, list_templates
from app.generator.plot import (
    CENTER,
    LIM,
    NON_ISOLATED,
    SADDLE,
    SCALE,
    SIZE,
    STABLE_DEGENERATE_NODE,
    STABLE_NODE,
    STABLE_SPIRAL,
    STABLE_STAR_NODE,
    UNSTABLE_DEGENERATE_NODE,
    UNSTABLE_NODE,
    UNSTABLE_SPIRAL,
    UNSTABLE_STAR_NODE,
    _to_screen,
    classify,
    describe,
    eigen_directions,
    invariants,
    phase_portrait_svg,
    trajectory,
)

SVG_NS = "{http://www.w3.org/2000/svg}"

#: 一組涵蓋每一種平衡點的矩陣。**每一格都手算過**，見 `HAND_CHECKED` 的註解。
SHAPES = [
    [[1, 2], [3, 2]],        # saddle
    [[-3, 1], [0, -2]],      # stable node
    [[3, -2], [1, 0]],       # unstable node
    [[3, 4], [-2, -1]],      # unstable spiral
    [[-3, -3], [6, -1]],     # stable spiral
    [[0, -1], [1, 0]],       # center
    [[3, 1], [0, 3]],        # unstable degenerate node
    [[-2, 1], [0, -2]],      # stable degenerate node
    [[2, -1], [1, 4]],       # unstable degenerate node（非三角）
]


def _svgs():
    return [(A, phase_portrait_svg(A)) for A in SHAPES]


def _group(root, class_name: str):
    for g in root.iter(f"{SVG_NS}g"):
        if g.get("class") == class_name:
            return g
    return None


def _lines(root, class_name: str) -> list[tuple[float, float, float, float]]:
    g = _group(root, class_name)
    if g is None:
        return []
    return [
        (float(e.get("x1")), float(e.get("y1")),
         float(e.get("x2")), float(e.get("y2")))
        for e in g.iter(f"{SVG_NS}line")
    ]


def _polylines(root) -> list[list[tuple[float, float]]]:
    g = _group(root, "pp-traj")
    out = []
    for e in g.iter(f"{SVG_NS}polyline"):
        pts = [tuple(float(v) for v in pair.split(","))
               for pair in e.get("points").split()]
        out.append(pts)
    return out


def _to_math(sx: float, sy: float) -> tuple[float, float]:
    """螢幕 → 數學。**刻意在測試裡自己寫一次**，不從 `plot` 匯入反函式。

    共用同一段轉換的話，一個把 $y$ 忘了翻轉的 bug 會在兩邊同時發生，
    於是所有斷言照樣通過——那正是這一組測試最想抓的東西。
    """
    return (sx - SIZE / 2) / SCALE, (SIZE / 2 - sy) / SCALE


def _alignment(u: tuple[float, float], v: tuple[float, float]) -> tuple[float, float]:
    """回傳 (正規化的外積, 正規化的內積)。"""
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-12 or nv < 1e-12:
        return 0.0, 0.0
    cross = (u[0] * v[1] - u[1] * v[0]) / (nu * nv)
    dot = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
    return cross, dot


def _velocity(A, x: float, y: float) -> tuple[float, float]:
    (a, b), (c, d) = A
    return a * x + b * y, c * x + d * y


# =========================================================================
# 第一層：結構良好
# =========================================================================

@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_the_svg_parses_and_declares_a_viewbox(A):
    root = ET.fromstring(phase_portrait_svg(A))
    assert root.tag == f"{SVG_NS}svg"
    assert root.get("viewBox") == f"0 0 {SIZE:.0f} {SIZE:.0f}"
    # 無障礙：role 與可讀的標題（2S8 那一輪會再看一次，但這兩項現在就該有）
    assert root.get("role") == "img"
    assert root.get("aria-label")
    assert root.find(f"{SVG_NS}title") is not None


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_no_coordinate_is_nan_or_infinite(A):
    r"""⛔ **這是四層裡最不可省的一項。**

    SVG 路徑裡的 `NaN` 會讓瀏覽器**安靜地丟掉整條路徑**——沒有錯誤、
    沒有警告，圖上就是少一條線。而 NaN 在這裡很容易產生：正規化時除以
    $|A\mathbf{p}| = 0$、$e^{\lambda t}$ 溢位、特徵向量是零向量。

    掃的是**整個字串**而不是解析後的某幾個屬性：新加一種元素的人
    不必記得回來更新這一項。
    """
    svg = phase_portrait_svg(A)
    assert not re.search(r"(?i)\b(nan|inf(inity)?)\b", svg), "SVG 裡出現 NaN／inf"
    root = ET.fromstring(svg)
    for element in root.iter():
        for name, value in element.attrib.items():
            if name in ("x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r"):
                assert math.isfinite(float(value)), f"{name}={value}"
            if name == "points":
                for pair in value.split():
                    for number in pair.split(","):
                        assert math.isfinite(float(number)), pair


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_every_marker_that_is_referenced_is_also_defined(A):
    """`marker-end="url(#…)"` 指到的 id 必須在同一段 SVG 裡定義。

    指錯的後果是**箭頭不見**，而一張沒有箭頭的相圖看起來完全正常
    ——穩定節點與不穩定節點就此變成同一張圖（§2.11.3 第 5 點）。
    """
    svg = phase_portrait_svg(A)
    root = ET.fromstring(svg)
    defined = {m.get("id") for m in root.iter(f"{SVG_NS}marker")}
    referenced = set(re.findall(r'marker-end="url\(#([^)]+)\)"', svg))
    assert referenced, "沒有任何一組箭頭"
    assert referenced <= defined, f"指到不存在的 marker：{referenced - defined}"


def test_two_different_matrices_get_different_marker_ids():
    """id 在 HTML 文件裡是全域的，而審圖那一頁上有二十張圖。

    兩個不同的 $A$ 若共用同一組 id，第二張圖的箭頭會去用第一張圖的定義。
    目前兩者的定義逐字相同所以看不出來，**但那是巧合不是保證**。
    """
    ids = [set(re.findall(r'<marker id="([^"]+)"', phase_portrait_svg(A)))
           for A in ([[1, 2], [3, 2]], [[-3, 1], [0, -2]])]
    assert ids[0] and ids[1]
    assert not (ids[0] & ids[1])


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_the_portrait_stays_within_its_size_budget(A):
    """單張 SVG 不得超過 40 KB（PLAN §2.11.5 第 3 點）。

    這條線擋的不是今天的輸出（實測 10–13 KB），是**日後有人把方向場格點
    從 11×11 調到 60×60「讓圖漂亮一點」**，然後每個題目卡片變成 400 KB
    而沒有人發現。
    """
    size = len(phase_portrait_svg(A).encode("utf-8"))
    assert size <= 40 * 1024, f"{classify(A)} 的 SVG 有 {size} 位元組"


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_the_svg_carries_no_script_and_no_event_handler(A):
    """範本要 `|safe` 才印得出這段字串，而 `|safe` 是 XSS 的門。

    內容全部由我們自己從一個整數矩陣組出來，所以這一項今天必然通過；
    它的價值在**日後**——哪天有人讓 asset 帶進外部字串，這裡會先變紅。
    """
    svg = phase_portrait_svg(A)
    assert "<script" not in svg.lower()
    assert not re.search(r'\son[a-z]+\s*=', svg, flags=re.IGNORECASE)
    assert "javascript:" not in svg.lower()


# =========================================================================
# 第二層：幾何不變量——拿數學斷言，不拿參考圖比對
# =========================================================================

@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_every_direction_field_arrow_points_the_same_way_as_Ap(A):
    r"""⛔ **同向，不只是平行。**

    只查平行（外積 $\approx 0$）會漏掉**箭頭反向**——而反向會讓穩定節點
    畫成不穩定節點，是這裡最嚴重也最看不出來的 bug：整張圖的形狀完全正確，
    只有流向是反的。所以內積也要為正。

    容差 0.02：座標輸出時四捨五入到一位小數，而箭頭長 9 px，
    所以方向的角度誤差上限約 $0.05\sqrt2/4.5 \approx 0.016$ 弧度。
    實測最差值 0.011。
    """
    root = ET.fromstring(phase_portrait_svg(A))
    arrows = _lines(root, "pp-field")
    assert len(arrows) >= 80, f"方向場只有 {len(arrows)} 支箭頭"
    worst = 0.0
    for x1, y1, x2, y2 in arrows:
        px, py = _to_math((x1 + x2) / 2, (y1 + y2) / 2)
        screen_direction = (x2 - x1, y2 - y1)
        math_direction = (screen_direction[0], -screen_direction[1])
        cross, dot = _alignment(math_direction, _velocity(A, px, py))
        worst = max(worst, abs(cross))
        assert abs(cross) < 0.02, f"箭頭不平行於 Ap（外積 {cross:.4f}）於 ({px:.2f},{py:.2f})"
        assert dot > 0, f"箭頭**反向**於 ({px:.2f}, {py:.2f})——這是最危險的一種錯"
    assert worst < 0.02


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_every_trajectory_segment_is_tangent_to_the_flow(A):
    r"""軌跡上相鄰兩點的連線，必須與中點處的 $A\mathbf{p}$ 近似同向。

    這一項抓的是「軌跡用錯了封閉解」——例如重根情形漏掉 $\mathbf{v}t$ 那一項。
    ⚠️ **它之所以是真的交叉驗證**，是因為軌跡由 `plot._flow()`（矩陣指數的
    封閉形式）算出來，而這裡拿的是原方程 $A\mathbf{p}$：兩條路完全不同。
    若相圖改成去拿 generator 算好的解，這一項就會退化成「同一段程式跑兩次」。

    容差 0.35，而它量的是**弦與切線的差**，不是誤差：一小段弦對曲率大的
    地方本來就不會恰好平行。這個數字是**在 167 個真的會被出出來的矩陣上
    量出來的**（`test_the_geometry_also_holds_for_matrices_the_generators_produce`
    跑的就是那一群），最差值 0.249，全部落在原點附近 $|A\mathbf{p}|$ 很小、
    弦只有 3–7 px 的那幾段——在那個尺度上曲率半徑本來就只有幾個像素。

    ⚠️ **上面那個容差因此是鬆的，而真正在守方向的是 `dot > 0` 那一行**
    （實測最差 0.968，離「反向」有整整兩個數量級）。這是刻意講出來的：
    一個看起來很嚴格但其實鬆的斷言，比一個明說自己鬆的斷言危險。
    會讓弦真的歪掉的錯（例如重根情形漏掉 $\mathbf{v}t$ 項，軌跡會退化成
    放射狀直線）在這個容差下仍然是 $O(1)$ 的偏差，而且
    `test_the_closed_form_flow_agrees_with_sympys_matrix_exponential`
    會先抓到它。
    """
    root = ET.fromstring(phase_portrait_svg(A))
    runs = _polylines(root)
    assert len(runs) >= 4, f"只有 {len(runs)} 條軌跡"
    for run in runs:
        for (sx1, sy1), (sx2, sy2) in zip(run, run[1:]):
            mx, my = _to_math((sx1 + sx2) / 2, (sy1 + sy2) / 2)
            chord = (sx2 - sx1, -(sy2 - sy1))
            if math.hypot(*chord) < 1e-9:
                continue
            cross, dot = _alignment(chord, _velocity(A, mx, my))
            assert abs(cross) < 0.35, (
                f"軌跡的弦不沿著流場（外積 {cross:.4f}）於 ({mx:.2f}, {my:.2f})"
            )
            assert dot > 0, f"軌跡的走向是**逆流**的，於 ({mx:.2f}, {my:.2f})"


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_the_arrow_on_a_trajectory_points_forward_in_time(A):
    """⛔ 沒有這支箭頭，穩定節點與不穩定節點的圖長得一模一樣。"""
    root = ET.fromstring(phase_portrait_svg(A))
    arrows = _lines(root, "pp-flow")
    assert arrows, "軌跡上一支方向箭頭都沒有"
    for x1, y1, x2, y2 in arrows:
        px, py = _to_math((x1 + x2) / 2, (y1 + y2) / 2)
        direction = (x2 - x1, -(y2 - y1))
        _cross, dot = _alignment(direction, _velocity(A, px, py))
        assert dot > 0.9, f"軌跡箭頭沒有指向 t 增加的方向（內積 {dot:.3f}）"


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_the_eigendirection_lines_really_are_eigendirections(A):
    r"""特徵方向線的方向向量必須平行於 `A.eigenvects()` 給的特徵向量。

    拿 SymPy 的精確特徵向量來比，是為了讓這一項抓得到「$x$ 與 $y$ 寫反」
    ——那個 bug 畫出來的圖仍然是一張有兩條直線的合理圖片。

    複數特徵值沒有實的不動方向，所以那幾格**必須一條線都沒有**：
    畫了才是錯的（螺旋沒有直線軌跡）。
    """
    root = ET.fromstring(phase_portrait_svg(A))
    lines = _lines(root, "pp-eig")
    M = sp.Matrix(A)
    real_vectors = [
        (float(vec[0]), float(vec[1]))
        for lam, _multiplicity, basis in M.eigenvects()
        for vec in basis
        if sp.im(lam) == 0
    ]
    if not real_vectors:
        assert not lines, "複數特徵值的圖不該有特徵方向線"
        return
    assert len(lines) == len(real_vectors), (
        f"特徵方向線有 {len(lines)} 條，特徵向量有 {len(real_vectors)} 個"
    )
    for x1, y1, x2, y2 in lines:
        direction = (x2 - x1, -(y2 - y1))
        crosses = [abs(_alignment(direction, v)[0]) for v in real_vectors]
        assert min(crosses) < 0.01, f"這條線不平行於任何一個特徵向量：{crosses}"


@pytest.mark.parametrize("A", SHAPES, ids=lambda A: classify(A).replace(" ", "_"))
def test_every_coordinate_is_inside_the_viewbox(A):
    """裁切漏做的話，超出的部分會畫到卡片的版面上（瀏覽器預設不裁切）。

    ⚠️ 只檢查得了**錨點**：`<text>` 的實際寬度由渲染器決定，量不到。
    """
    root = ET.fromstring(phase_portrait_svg(A))
    def ok(v: float) -> bool:
        return -0.01 <= v <= SIZE + 0.01
    for element in root.iter():
        if element.tag == f"{SVG_NS}marker" or element.tag.endswith("}path"):
            continue                      # marker 內部是它自己的座標系
        for name in ("x", "x1", "x2", "cx"):
            if element.get(name) is not None:
                assert ok(float(element.get(name))), f"{name}={element.get(name)}"
        for name in ("y", "y1", "y2", "cy"):
            if element.get(name) is not None:
                assert ok(float(element.get(name))), f"{name}={element.get(name)}"
        if element.get("points"):
            for pair in element.get("points").split():
                sx, sy = (float(v) for v in pair.split(","))
                assert ok(sx) and ok(sy), pair


def test_the_y_axis_is_flipped():
    r"""⛔ **數學的 $y$ 向上、SVG 的 $y$ 向下。**

    忘記翻轉的症狀是整張圖上下顛倒——而上下顛倒的螺旋**就是旋轉方向
    相反的螺旋**，它看起來完全合理，只是錯的。

    兩個方向各驗一次：座標轉換本身，以及**輸出裡真的翻了**。
    第二個用的是 $A = \begin{pmatrix}0 & -1\\ 1 & 0\end{pmatrix}$：
    在 $(1, 0)$ 處速度是 $(0, 1)$，數學上朝上，所以螢幕上的 $y$ 必須**變小**。
    """
    assert _to_screen(0, 1)[1] < _to_screen(0, 0)[1] < _to_screen(0, -1)[1]
    assert _to_screen(-1, 0)[0] < _to_screen(0, 0)[0] < _to_screen(1, 0)[0]

    A = [[0, -1], [1, 0]]
    root = ET.fromstring(phase_portrait_svg(A))
    best = None
    for x1, y1, x2, y2 in _lines(root, "pp-field"):
        px, py = _to_math((x1 + x2) / 2, (y1 + y2) / 2)
        distance = math.hypot(px - 1.0, py)
        if best is None or distance < best[0]:
            best = (distance, y2 - y1)
    assert best is not None and best[0] < 0.4, "找不到靠近 (1, 0) 的格點"
    assert best[1] < 0, "在 (1,0) 處速度朝上，螢幕座標的 y 卻沒有變小"


#: `_flow()` 的三個分支各一個代表。
FLOW_BRANCHES = [
    ([[1, 2], [3, 2]], "Δ > 0（實相異）"),
    ([[3, 1], [0, 3]], "Δ = 0（重根）"),
    ([[2, -1], [1, 4]], "Δ = 0（重根，非三角）"),
    ([[3, 4], [-2, -1]], "Δ < 0（複數）"),
    ([[0, -1], [1, 0]], "Δ < 0（純虛數）"),
]


@pytest.mark.parametrize("A,branch", FLOW_BRANCHES, ids=lambda v: str(v)[:14])
def test_the_closed_form_flow_agrees_with_sympys_matrix_exponential(A, branch):
    r"""$e^{At}$ 的三個手寫封閉形式，逐個對上 SymPy 的 `(A t).exp()`。

    這一項把 §2.11.2 那個「線性系統不需要數值積分器」的論證變成一句
    可以檢查的話，而且它是**整個第二層的地基**：軌跡上每一點都是
    $e^{At}\mathbf{x}_0$，所以 `_flow()` 對了，軌跡就不可能因為累積誤差而漂走。

    ⚠️ 三個分支都要驗，因為它們是三段**完全不同**的程式。最容易錯的是
    重根那一格（$e^{\lambda t}(I + t(A - \lambda I))$）——漏掉 $t(A-\lambda I)$
    會得到 $e^{\lambda t}I$，畫出來是一堆**直線**軌跡，而那正好是星形節點
    該有的樣子：一張正確的圖，畫的是別的矩陣。
    """
    from app.generator.plot import _flow

    t = sp.Symbol("t", real=True)
    exact = sp.Matrix(A).__mul__(t).exp()
    flow = _flow(A)
    for value in (-1.7, -0.8, -0.25, 0.0, 0.3, 0.9, 1.6):
        got = flow(value)
        want = [float(sp.re(sp.N(entry.subs(t, value)))) for entry in exact]
        for k in range(4):
            assert abs(got[k] - want[k]) < 1e-9, (
                f"{branch} 在 t={value} 的第 {k} 項：{got[k]} vs {want[k]}"
            )


def test_every_trajectory_point_lies_exactly_on_the_closed_form_orbit():
    r"""每一點都必須恰好落在 $\{e^{At}\mathbf{x}_0\}$ 這條曲線上。

    上一項驗的是 `_flow()` 本身，這一項驗的是 `trajectory()` 真的用了它
    ——「掃 $t$ 套封閉解」與「從前一點往前推一小步」的差別在這裡才看得出來，
    因為後者會**累積誤差**，而累積的誤差沒有任何視覺症狀
    （軌跡照樣是一條平滑的曲線，只是慢慢漂到隔壁那一條上）。

    ⚠️ **不用「離細掃的參考曲線多近」來判**（第一版是那樣寫的，然後容差
    卡在參考曲線自己的格點間距上——那個測試量的其實是格點密度）。
    改成把每一點換到特徵座標裡反解它的 $t$：
    $\mathbf{x}_0 = c_1\mathbf{v}_1 + c_2\mathbf{v}_2$、
    $\mathbf{p} = d_1\mathbf{v}_1 + d_2\mathbf{v}_2$，
    則兩個 $\ln(d_i/c_i)/\lambda_i$ 必須是**同一個** $t$。這是精確的，
    沒有格點，容差可以壓到 $10^{-8}$。
    """
    A = [[1, 2], [3, 2]]                                  # λ = 4, -1
    V = sp.Matrix([[2, 1], [3, -1]])                      # 兩個特徵向量作為行
    lam = (4.0, -1.0)
    x0 = (0.9, -0.4)
    c = V.solve(sp.Matrix(x0))
    assert c[0] != 0 and c[1] != 0, "起點落在特徵方向上，這一題就沒有意義了"

    points = trajectory(A, x0)
    assert len(points) > 20
    assert x0 in points, "起點自己不在軌跡上"
    for px, py in points:
        d = V.solve(sp.Matrix([px, py]))
        times = [math.log(float(d[i] / c[i])) / lam[i] for i in (0, 1)]
        assert abs(times[0] - times[1]) < 1e-8, (
            f"({px:.6f}, {py:.6f}) 不在封閉解上："
            f"兩個特徵座標給出的 t 是 {times[0]:.9f} 與 {times[1]:.9f}"
        )


@pytest.mark.parametrize(
    "template_id",
    ["system.linear_2x2.real_distinct", "system.linear_2x2.repeated",
     "system.linear_2x2.complex"],
)
def test_the_geometry_also_holds_for_matrices_the_generators_produce(template_id):
    r"""上面那幾項只看九個**手挑的**矩陣。這一項看**真的會被出出來的**那些。

    ⚠️ **這不是重複，這是上面那幾項的前提。** 一組只在手挑的漂亮矩陣上跑的
    幾何斷言，是一組不看產品的測試——而手挑的那九個是我為了涵蓋七種分類
    挑的，不是為了涵蓋最刁鑽的形狀。實測差別很大：手挑的九個上弦與切線的
    最差偏差是 0.084，真的出出來的 167 個上是 0.249（那個數字就是
    上面那個容差的來源）。

    每個題型抽 12 題，只驗最會出事的兩件：**箭頭同向**與**弦沿著流場**。
    """
    rng = __import__("random").Random(f"plot-{template_id}")
    for _ in range(12):
        problem = generate(template_id, 2, seed=rng.randrange(1, 2 ** 31 - 1))
        A = problem.params["A"]
        root = ET.fromstring(problem.assets["phase_portrait_svg"])
        for x1, y1, x2, y2 in _lines(root, "pp-field") + _lines(root, "pp-flow"):
            px, py = _to_math((x1 + x2) / 2, (y1 + y2) / 2)
            _cross, dot = _alignment((x2 - x1, -(y2 - y1)), _velocity(A, px, py))
            assert dot > 0, f"{A} 在 ({px:.2f}, {py:.2f}) 的箭頭是反向的"
        for run in _polylines(root):
            for (sx1, sy1), (sx2, sy2) in zip(run, run[1:]):
                mx, my = _to_math((sx1 + sx2) / 2, (sy1 + sy2) / 2)
                chord = (sx2 - sx1, -(sy2 - sy1))
                if math.hypot(*chord) < 1e-9:
                    continue
                cross, dot = _alignment(chord, _velocity(A, mx, my))
                assert abs(cross) < 0.35, f"{A} 的弦偏離流場 {cross:.3f}"
                assert dot > 0, f"{A} 的軌跡在 ({mx:.2f}, {my:.2f}) 逆流"


# =========================================================================
# 第三層：分類的雙路徑一致性
# =========================================================================

#: **手算的對照表**（PLAN §2.11.4 第三層要求「約 15 個矩陣，涵蓋全部七個分支
#: 加上兩個邊界」）。每一列右邊是 $(\operatorname{tr}, \det, \Delta)$，
#: 用手算填的；`test_the_hand_checked_invariants_are_right` 會再驗一次算術。
HAND_CHECKED = [
    ([[1, 2], [3, 2]], SADDLE, (3, -4, 25)),
    ([[0, 1], [1, 0]], SADDLE, (0, -1, 4)),                 # 邊界：tr = 0 但 det < 0
    ([[-3, 1], [0, -2]], STABLE_NODE, (-5, 6, 1)),
    ([[-1, 0], [0, -4]], STABLE_NODE, (-5, 4, 9)),
    ([[3, -2], [1, 0]], UNSTABLE_NODE, (3, 2, 1)),
    ([[2, 0], [0, 5]], UNSTABLE_NODE, (7, 10, 9)),
    ([[-3, -3], [6, -1]], STABLE_SPIRAL, (-4, 21, -68)),
    ([[-1, -5], [1, -1]], STABLE_SPIRAL, (-2, 6, -20)),
    ([[3, 4], [-2, -1]], UNSTABLE_SPIRAL, (2, 5, -16)),
    ([[1, 1], [-2, 1]], UNSTABLE_SPIRAL, (2, 3, -8)),
    ([[0, -1], [1, 0]], CENTER, (0, 1, -4)),                # 邊界：tr = 0，det > 0
    ([[0, -4], [1, 0]], CENTER, (0, 4, -16)),
    ([[3, 1], [0, 3]], UNSTABLE_DEGENERATE_NODE, (6, 9, 0)),   # 邊界：Δ = 0
    ([[2, -1], [1, 4]], UNSTABLE_DEGENERATE_NODE, (6, 9, 0)),
    ([[-2, 1], [0, -2]], STABLE_DEGENERATE_NODE, (-4, 4, 0)),
    ([[5, 0], [0, 5]], UNSTABLE_STAR_NODE, (10, 25, 0)),       # A = λI，不是退化節點
    ([[-1, 0], [0, -1]], STABLE_STAR_NODE, (-2, 1, 0)),
    ([[2, 1], [0, 0]], NON_ISOLATED, (2, 0, 4)),               # 邊界：det = 0
    ([[1, 2], [2, 4]], NON_ISOLATED, (5, 0, 25)),
]


@pytest.mark.parametrize("A,expected,expected_invariants", HAND_CHECKED)
def test_the_hand_checked_invariants_are_right(A, expected, expected_invariants):
    """先驗這張對照表自己的算術，再用它去驗 `classify()`。

    順序是有意義的：一張算錯的對照表會把 `classify()` 的 bug 蓋掉，
    而且是**兩邊都錯所以看起來一致**的那種蓋法。
    """
    assert invariants(A) == expected_invariants
    assert classify(A) == expected


@pytest.mark.parametrize("A,expected,_inv", HAND_CHECKED)
def test_the_eigenvalues_agree_with_the_lookup_table(A, expected, _inv):
    r"""**第二條路**：直接看 `A.eigenvals()` 的實部符號與虛部是否為零。

    這與 §2.10.4 的 Fourier 閘門、§2.4(g) 的 Laplace 交叉驗證是同一個模式。
    ⛔ 全部用整數／有理數精確運算，**不准浮點**——$\Delta$ 恰為 0 的退化節點
    是最容易被浮點誤判的一格（`0.9999999` 會被判成 $\Delta > 0$，
    於是退化節點被畫成節點，而那張圖看起來完全正常）。

    ⚠️ **一個誠實的盲點**：這條路分不出星形節點與退化節點（兩者的特徵值
    一模一樣），所以下面把它們一起當作 `degenerate-or-star`。分辨它們需要
    幾何重數，而那不是「特徵值的符號」這條路上的東西。
    """
    # ⚠️ `eigenvals()` 回的是 {λ: 重數}，重根只有**一個**鍵。
    # 忘了展開重數的話，下面那些 `real_parts[1]` 會 IndexError——
    # 而那還算好的：若寫成 `real_parts[-1]` 就會安靜地拿到同一個值。
    eigenvalues = [
        value
        for value, multiplicity in sp.Matrix(A).eigenvals().items()
        for _ in range(multiplicity)
    ]
    assert len(eigenvalues) == 2
    assert all(value.is_number for value in eigenvalues)

    real_parts = [sp.re(value) for value in eigenvalues]
    imaginary = [sp.im(value) for value in eigenvalues]
    complex_pair = any(value != 0 for value in imaginary)

    if any(value == 0 for value in eigenvalues):
        second_path = "non-isolated"
    elif complex_pair:
        alpha = real_parts[0]
        second_path = ("center" if alpha == 0
                       else "stable-rotating" if alpha < 0 else "unstable-rotating")
    elif real_parts[0] * real_parts[1] < 0:
        second_path = "saddle"
    elif len(set(eigenvalues)) == 1:
        second_path = ("stable-degenerate-or-star" if real_parts[0] < 0
                       else "unstable-degenerate-or-star")
    else:
        second_path = "stable-node" if real_parts[0] < 0 and real_parts[1] < 0 \
            else "unstable-node"

    expected_from_table = {
        SADDLE: "saddle",
        STABLE_NODE: "stable-node",
        UNSTABLE_NODE: "unstable-node",
        STABLE_SPIRAL: "stable-rotating",
        UNSTABLE_SPIRAL: "unstable-rotating",
        CENTER: "center",
        STABLE_DEGENERATE_NODE: "stable-degenerate-or-star",
        UNSTABLE_DEGENERATE_NODE: "unstable-degenerate-or-star",
        STABLE_STAR_NODE: "stable-degenerate-or-star",
        UNSTABLE_STAR_NODE: "unstable-degenerate-or-star",
        NON_ISOLATED: "non-isolated",
    }[expected]
    assert second_path == expected_from_table


def test_a_star_node_is_not_called_a_degenerate_node():
    r"""$A = \lambda I$ 與缺陷矩陣的 $(\operatorname{tr}, \det, \Delta)$ 完全相同。

    分辨它們要多看一眼矩陣本身，而上面那條「用特徵值重算」的獨立路徑
    **也分不出來**——所以這一項是那個盲點唯一的看守者。
    """
    star, defective = [[5, 0], [0, 5]], [[3, 1], [0, 3]]
    assert invariants(star)[2] == invariants(defective)[2] == 0
    assert classify(star) != classify(defective)
    assert eigen_directions(star) == [], "A = λI 每個方向都是特徵方向，不該只畫一條"
    assert len(eigen_directions(defective)) == 1, "缺陷矩陣只有一個特徵方向"


def test_the_classification_shown_in_the_steps_is_the_one_drawn_on_the_figure():
    r"""逐步解答那一句話與圖上那個標籤必須來自同一份表。

    ⚠️ 若各寫一份，就會出現「文字說鞍點、圖畫成節點」的可能，
    而那種不一致**沒有任何東西會拋錯**——兩張圖都畫得出來，兩句話都寫得出來。
    """
    for tpl in list_templates():
        if not tpl.template_id.startswith("system."):
            continue
        for difficulty in tpl.difficulties:
            problem = generate(tpl.template_id, difficulty, seed=20260830)
            svg = problem.assets.get("phase_portrait_svg")
            if svg is None:
                continue                       # 非齊次刻意沒有圖
            A = problem.params["A"]
            label = classify(A)
            assert f">{label}</text>" in svg, f"{tpl.template_id} 圖上的標籤不是 {label}"
            notes = " ".join(step.note for step in problem.steps)
            assert describe(A) in notes, (
                f"{tpl.template_id} d{difficulty} 的步驟沒有說出 {describe(A)}"
            )


# =========================================================================
# 每個系統題型都真的掛上了圖（或刻意沒掛）
# =========================================================================

def test_which_system_templates_carry_a_portrait_is_a_deliberate_list():
    r"""齊次的三個掛圖，非齊次的那一個**刻意不掛**。

    寫成一份明確的清單而不是「有就檢查」：後者在圖被整個拿掉的時候會全綠。
    非齊次不掛圖的理由是 $\mathbf{x}' = A\mathbf{x} + \mathbf{g}(t)$
    在 $\mathbf{g}$ 含 $t$ 時**根本不是自守系統**——相平面上的軌跡會互相
    穿越，「相圖」這個東西不存在。畫齊次部分的圖擺在旁邊看起來完全合理
    （它是一張正確的圖），只是它畫的不是這一題的方程。
    """
    expected = {
        "system.linear_2x2.real_distinct": True,
        "system.linear_2x2.repeated": True,
        "system.linear_2x2.complex": True,
        "system.linear_2x2.nonhomogeneous": False,
    }
    found = {t.template_id for t in list_templates()
             if t.template_id.startswith("system.")}
    assert found == set(expected), f"系統題型的清單變了：{found}"
    for template_id, should_have in expected.items():
        for difficulty in (1, 2, 3):
            problem = generate(template_id, difficulty, seed=20260830 + difficulty)
            has = "phase_portrait_svg" in problem.assets
            assert has == should_have, f"{template_id} d{difficulty} 的相圖狀態不對"
            if has:
                assert problem.assets["phase_portrait_svg"].startswith("<svg")


def test_no_problem_statement_ever_contains_an_svg():
    r"""⛔ **洩題防護的第一半（generator 這一端）。**

    一張鞍點圖等於直接告訴學生兩個特徵值異號、一張同心橢圓圖等於告訴學生
    $\operatorname{tr}A = 0$。圖只能出現在 `assets` 裡，不能溜進敘述、
    題目的 LaTeX 或任何一個步驟。

    另一半（範本這一端：圖必須在 `<details>` 內）在
    `tests/test_web.py::test_the_phase_portrait_never_escapes_the_collapsed_block`。
    """
    for tpl in list_templates():
        for difficulty in tpl.difficulties:
            problem = generate(tpl.template_id, difficulty, seed=20260830)
            blob = "\n".join(
                [problem.statement, problem.statement_latex, problem.answer_latex]
                + [s.title for s in problem.steps]
                + [s.latex for s in problem.steps]
                + [s.note for s in problem.steps]
            )
            assert "<svg" not in blob, f"{tpl.template_id} d{difficulty} 的文字裡有 SVG"
