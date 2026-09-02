"""課程週次歸類（PLAN.md D52，v0.29 改用途）。

這一份是 `tests/test_release.py`（v0.28，47 項）的**倖存部分**。
內容開放閘門隨 D59 移除之後，那一份裡「閘門擋不擋得住」的 39 項失去了標的；
留下來的是歸類本身的性質，而它們一項都沒有失效——**歸類的用途從
「決定開放什麼」換成「決定選單怎麼分組」，但「不得漏、不得多、不得漂移」
這三件事完全一樣**。

⚠️ 兩項改了名字：`release_week` → `primary_week`。理由寫在 `curriculum.py`
——「release」在 v0.29 之後是一個不存在的概念，而留著死掉的詞彙比留著
死掉的程式碼更糟。
"""

from __future__ import annotations

import pytest

# CJK 的定義只有一份，跟著介面語言的那組測試走。
from tests.test_web import CJK  # noqa: F401


def test_every_registered_template_has_a_week():
    """出題註冊表裡的**每一個**題型都必須在 `curriculum.CONTENT` 裡。

    ⚠️ 這是這件事最容易被安靜破壞的地方：新增一個題型而忘了歸類，
    它會落在「沒有任何一週擁有的內容」——於是它**不會出現在下拉選單上**，
    而且**沒有任何東西會報錯**。

    ⚠️ v0.29 這一項的後果變得更嚴重，不是更輕。 v0.28 的症狀是
    「那個題型開不起來」（老師在管理頁上看得到它、只是沒勾）；現在管理頁
    沒有了，症狀變成**它整個不存在**，而唯一會發現的方式是有人剛好去數
    選單上有幾個項目。
    """
    from app.curriculum import CONTENT, KIND_PRACTICE
    from app.generator import list_templates

    classified = {i.content_id for i in CONTENT if i.kind == KIND_PRACTICE}
    registered = {t.template_id for t in list_templates()}
    assert registered - classified == set(), (
        "有題型沒有被歸到任何一週，請在 app/curriculum.py 的 CONTENT 補一列"
    )
    assert classified - registered == set(), (
        "curriculum.CONTENT 有一列指向不存在的題型（改名或移除之後忘了同步）"
    )


def test_every_demo_has_a_week():
    from app.curriculum import CONTENT, KIND_DEMO
    from app.routes.demos import DEMOS

    classified = {i.content_id for i in CONTENT if i.kind == KIND_DEMO}
    registered = {d.template_id for d in DEMOS}
    assert classified == registered


def test_every_demo_agrees_with_its_own_week_label():
    """`Demo.week`（展示自己那個給人看的字串）與歸類必須說同一件事。

    兩份真相是刻意保留的：`Demo.week` 早在每個展示落地時就寫好了，而它印在
    索引頁的每一列旁邊；歸類決定那一列被放在哪個標題底下。**漂移的症狀是
    索引頁上「Week 5」那一列出現在「Week 6」的標題下面**，而兩邊各自看
    都很正常。
    """
    from app.curriculum import item_for, week_label
    from app.routes.demos import DEMOS

    for demo in DEMOS:
        item = item_for(demo.template_id)
        assert item is not None
        assert week_label(item) == demo.week, (
            f"{demo.template_id}：索引頁寫 {demo.week!r}，"
            f"歸類算出來是 {week_label(item)!r}"
        )


def test_the_week_table_is_sixteen_weeks_in_order():
    from app.curriculum import WEEKS

    assert [w.number for w in WEEKS] == list(range(1, 17))
    assert all(w.topic and not CJK.search(w.topic) for w in WEEKS), (
        "週次主題會印在下拉選單上，必須是英文（D5）"
    )


def test_each_item_is_listed_under_exactly_one_week():
    """`ids_for_week()` 是一個**分割**：每一項恰好出現在一個週次底下。

    v0.28 這一條守的是「關閉第 12 週不會安靜地關掉第 10 週開的東西」。
    閘門沒有了，理由換成一個更平淡但一樣真的：**一個下拉選單不可以把同一個
    題型列三次**——使用者會以為那是三個不同的東西，而點下去出的是同一題。
    """
    from app.curriculum import ALL_CONTENT_IDS, WEEK_NUMBERS, ids_for_week

    listed: list[str] = []
    for week in WEEK_NUMBERS:
        listed.extend(ids_for_week(week))
    assert sorted(listed) == sorted(ALL_CONTENT_IDS)
    assert len(listed) == len(set(listed))


def test_filtering_by_kind_splits_the_same_partition():
    """`ids_for_week(w, kind)` 的兩半合起來要等於 `ids_for_week(w)`。

    出題頁與展示索引各用一半，而**「有一項兩邊都沒撿到」是安靜的**：
    它只是從畫面上消失，不會報錯。
    """
    from app.curriculum import (
        KIND_DEMO,
        KIND_PRACTICE,
        WEEK_NUMBERS,
        ids_for_week,
    )

    for week in WEEK_NUMBERS:
        both = set(ids_for_week(week, KIND_PRACTICE)) | set(
            ids_for_week(week, KIND_DEMO)
        )
        assert both == set(ids_for_week(week))


def test_weeks_with_content_hides_only_genuinely_empty_weeks():
    """空的週次不出現在畫面上，而**那不是 D24 說的「隱藏未完成的東西」**。

    差別在於那些週次底下沒有任何一項內容存在——一個標題底下什麼都沒有的
    分組對使用者只有一個意思：「這個系統壞了」。
    """
    from app.curriculum import WEEKS, ids_for_week, weeks_with_content

    shown = {w.number for w in weeks_with_content()}
    for week in WEEKS:
        assert (week.number in shown) == bool(ids_for_week(week.number))
    # 目前五週沒有內容（W8、W11、W14、W15、W16），其中兩週是 D22 明確不做的。
    assert shown == {1, 3, 4, 5, 6, 7, 9, 10}


@pytest.mark.parametrize(
    "weeks, expected",
    [
        ((3,), "Week 3"),
        ((1, 2), "Weeks 1-2"),
        ((10, 12, 13), "Weeks 10, 12-13"),
    ],
)
def test_week_label_reads_the_way_a_person_would_write_it(weeks, expected):
    from app.curriculum import KIND_PRACTICE, ContentItem, week_label

    assert week_label(ContentItem("x", KIND_PRACTICE, weeks)) == expected


def test_the_syllabus_weeks_match_what_the_content_claims():
    """抽查幾條歸類，因為「表格填錯一格」不會有任何症狀。

    挑這幾條是因為它們各自代表一種容易填錯的情況：跨兩週的、與鄰週只差
    一個主題的、以及被課綱順序弄得有點怪的那一個（Laplace 在 ODE 前面）。
    """
    from app.curriculum import item_for

    assert item_for("demo.lti.convolution").weeks == (1, 2)
    assert item_for("demo.fourier.additive").weeks == (3,)
    assert item_for("demo.transform.pulse").weeks == (4,)
    assert item_for("ode.laplace.ivp").primary_week == 9
    assert item_for("ode.second_order.homogeneous").primary_week == 10
    assert item_for("system.linear_2x2.complex").weeks == (10, 12, 13)


def test_curriculum_imports_neither_functional_area():
    """⛔ `curriculum.py` 是純資料、零相依（D21 的界線）。

    它同時列出了出題與展示的識別碼，而那**不違反 D21**——因為它只認得
    字串，沒有型別、沒有基底類別、沒有任何一邊要實作的介面。一旦它 import
    了兩邊，它就變成一個接縫，而接縫會長出東西。

    這一項用讀原始碼的方式驗，不是用 `sys.modules`：後者會因為「別人先
    import 過了」而偽陽性。
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "app" / "curriculum.py"
    ).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    )
    for banned in ("generator", "routes", "fastapi", "sympy"):
        assert banned not in code, f"curriculum.py import 了 {banned}"


def test_the_content_table_has_no_duplicate_ids():
    from app.curriculum import ALL_CONTENT_IDS, CONTENT

    assert len(CONTENT) == len(ALL_CONTENT_IDS) == 20


def test_weeks_inside_one_item_are_sorted_and_unique():
    """`primary_week` 取 `weeks[0]`，所以順序是語意的一部分。

    沒有這一項的話，一個寫成 `(12, 10, 13)` 的歸類會安靜地把那個題型
    列到第 12 週底下——而它看起來只是欄位順序不同而已。
    """
    from app.curriculum import CONTENT

    for item in CONTENT:
        assert list(item.weeks) == sorted(set(item.weeks)), item.content_id
        assert item.primary_week == min(item.weeks)
