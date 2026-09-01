"""內容開放閘門（v0.28，PLAN.md D52–D56、§4.3a）。

分成六組，順序就是「一件事可能出錯的順序」：

1. **歸類**——每個題型與展示都有週次，而且沒有多餘的、指不到東西的歸類。
2. **閘門的形狀**——列舉整張路由表，確認每一條都被分類過（這一組是這個
   功能的骨架，理由見 `app/release_gate.py`）。
3. **擋得住**——關著的內容，直接打網址拿不到。逐項打，不抽樣。
4. **看得到的那一面**——開放之後學生確實拿得到；未開放的完全不出現。
5. **管理頁**——三個按鈕的語意、staff 限定、持久化。
6. **不受影響的東西**——`/activity` 的統計、`UsageLog` 的欄位、D24 的沉默。

⚠️ **這一份刻意不用 `sign_in()`。** 那個起手式在 v0.28 之後會先把全部內容
打開（見 `tests/test_web.py::open_all_content` 的說明），而這裡要驗的正是
「沒打開的時候會怎樣」——共用同一個起手式的話，整組測試會安靜地變成
一組永遠通過的假保證。這裡一律走 `make_accounts()` + `log_in()`。
"""

from __future__ import annotations

import logging

import pytest
from sqlmodel import Session, select

from tests.test_web import (  # noqa: F401  沿用既有 fixture 與帳號流程
    CJK,
    CLASS_PASSWORD,
    STAFF_PASSWORD,
    client,
    log_in,
    make_accounts,
    open_all_content,
)

#: 展示的 slug → `content_id`。用來把「關掉這一項」對到「打這個網址」。
DEMO_URLS = {
    "demo.sampling.aliasing": "/demos/sampling/aliasing",
    "demo.spectrum.leakage": "/demos/spectrum/leakage",
    "demo.fourier.additive": "/demos/fourier/series",
    "demo.lti.convolution": "/demos/lti/convolution",
    "demo.transform.pulse": "/demos/transform/pulse",
    "demo.filter.polezero": "/demos/filter/pole-zero",
}


def sign_in_student(client):
    """建帳號 → 以學生身分登入。**不開放任何內容。**"""
    make_accounts(client)
    return log_in(client, "class", CLASS_PASSWORD)


def sign_in_teacher(client):
    make_accounts(client)
    return log_in(client, "staff", STAFF_PASSWORD)


# ============================================================================
# 1. 歸類：每一項內容都有週次，而且每一個週次都指得到東西
# ============================================================================

def test_every_registered_template_has_a_week():
    """出題註冊表裡的**每一個**題型都必須在 `curriculum.CONTENT` 裡。

    ⚠️ 這是這個功能最容易被安靜破壞的地方：新增一個題型而忘了歸類，
    它會落在「沒有人擁有的內容」——閘門看不到它、管理頁不列它，
    於是**它永遠開不起來，而且沒有任何東西會報錯**。
    """
    from app.curriculum import KIND_PRACTICE, CONTENT
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
    from app.curriculum import KIND_DEMO, CONTENT
    from app.routes.demos import DEMOS

    classified = {i.content_id for i in CONTENT if i.kind == KIND_DEMO}
    registered = {d.template_id for d in DEMOS}
    assert classified == registered


def test_every_demo_agrees_with_its_own_week_label():
    """`Demo.week`（展示自己那個給人看的字串）與歸類必須說同一件事。

    兩份真相是刻意保留的：`Demo.week` 早在每個展示落地時就寫好了，而它印在
    索引頁上；歸類是 v0.28 才有的，而它決定開關。**漂移的症狀是索引頁上
    寫「Week 5」的東西被「開放第 6 週」打開**，而兩邊各自看都很正常。
    """
    from app.curriculum import item_for, week_label
    from app.routes.demos import DEMOS

    for demo in DEMOS:
        item = item_for(demo.template_id)
        assert item is not None
        # "Weeks 1-2" vs "Weeks 1-2"；`Demo.week` 用的就是同一種寫法。
        assert week_label(item) == demo.week, (
            f"{demo.template_id}：索引頁寫 {demo.week!r}，"
            f"歸類算出來是 {week_label(item)!r}"
        )


def test_the_week_table_is_sixteen_weeks_in_order():
    from app.curriculum import WEEKS

    assert [w.number for w in WEEKS] == list(range(1, 17))
    assert all(w.topic and not CJK.search(w.topic) for w in WEEKS), (
        "週次主題會印在管理頁上，必須是英文（D5）"
    )


def test_each_item_is_owned_by_exactly_one_week():
    """`ids_for_week()` 是一個**分割**：每一項恰好被一週擁有。

    這是「整週開關」不會互相打架的前提。理由與失敗方式寫在
    `app/curriculum.py` 最後一節——多重擁有的版本會讓「關閉第 12 週」
    安靜地關掉第 10 週開的東西。
    """
    from app.curriculum import ALL_CONTENT_IDS, WEEK_NUMBERS, ids_for_week

    owned: list[str] = []
    for week in WEEK_NUMBERS:
        owned.extend(ids_for_week(week))
    assert sorted(owned) == sorted(ALL_CONTENT_IDS)
    assert len(owned) == len(set(owned))


def test_borrowed_and_owned_never_overlap():
    from app.curriculum import WEEK_NUMBERS, borrowed_ids_for_week, ids_for_week

    for week in WEEK_NUMBERS:
        assert not set(ids_for_week(week)) & set(borrowed_ids_for_week(week))


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
    """抽查三條歸類，因為「表格填錯一格」不會有任何症狀。

    挑這三條是因為它們各自代表一種容易填錯的情況：跨兩週的、與鄰週
    只差一個主題的、以及被課綱順序弄得有點怪的那一個（Laplace 在 ODE 前面）。
    """
    from app.curriculum import item_for

    assert item_for("demo.lti.convolution").weeks == (1, 2)
    assert item_for("demo.fourier.additive").weeks == (3,)
    assert item_for("demo.transform.pulse").weeks == (4,)
    assert item_for("ode.laplace.ivp").release_week == 9
    assert item_for("ode.second_order.homogeneous").release_week == 10
    assert item_for("system.linear_2x2.complex").weeks == (10, 12, 13)


# ============================================================================
# 2. 閘門的形狀：列舉整張路由表
#
# 這一組是老師指定的那一項（「需有列舉所有路由的測試守著」），也是
# `app/release_gate.py` 那段「middleware 判不了全部」的支撐。
# ============================================================================

def test_every_route_is_classified_for_release_gating(client):
    """**列舉 app 上所有已註冊的路由**，確認每一條都被明確分類過。

    三份清單各自是一個決定，所以三份都**逐字釘死在這裡**——改清單的人
    會先撞到這項測試，而測試上面那句話會叫他回去讀 `release_gate.py`。
    這與 `test_no_route_is_reachable_without_logging_in` 釘死
    `EXEMPT_PATHS` 是同一個手法。

    新增一條路由而沒有分類 → 這裡直接紅燈，而不是安靜地讓學生看到
    還沒教的內容。
    """
    from app.release_gate import (
        DEMO_PREFIX,
        SELF_GATED_PATHS,
        UNGATED_PATHS,
        UNGATED_PREFIXES,
    )
    from tests.test_web import _registered_endpoints

    assert UNGATED_PATHS == {
        "/", "/login", "/logout", "/healthz", "/demos", "/activity",
        "/admin/content",
    }, (
        "不受開放閘門管的路徑清單變了。每加一條都要先回答一個問題："
        "這條路徑吐得出某一週的內容嗎？吐得出就不能加。"
    )
    assert SELF_GATED_PATHS == {"/practice/generate"}, (
        "自己守的路徑清單變了。這份清單上的每一條都必須在自己的路由裡"
        "呼叫 release.visible_ids()，而 middleware 對它們完全沒有意見。"
    )
    assert UNGATED_PREFIXES == ("/static/",)

    checked = 0
    for path, _method in sorted(_registered_endpoints(client.fastapi_app)):
        if path.startswith(UNGATED_PREFIXES):
            continue
        assert path in UNGATED_PATHS or path in SELF_GATED_PATHS, (
            f"{path} 沒有被開放閘門分類過。請把它加進 app/release_gate.py 的"
            "三份清單之一，並回來改這項測試。"
        )
        checked += 1

    # 下限是防呆：列舉壞掉的話這項測試會變成「檢查了 0 條，全部通過」。
    assert checked >= 6, f"實際檢查到的路由太少（{checked}），列舉可能壞了"

    # 帶參數的路由只有一條，而它由 middleware 直接判定。多一條就要重想。
    parameterised = _parameterised_paths(client.fastapi_app)
    assert parameterised == {f"{DEMO_PREFIX}{{group}}/{{name}}"}, (
        f"帶參數的路由不只一條了：{sorted(parameterised)}。"
        "middleware 只認得展示那一條，其餘的請先想清楚怎麼判定。"
    )


def _parameterised_paths(app) -> set[str]:
    """路由表裡帶 `{}` 參數的路徑。`_registered_endpoints` 刻意跳過它們。"""
    found: set[str] = set()

    def walk(routes) -> None:
        for route in routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None) or set()
            if path and methods:
                if "{" in path:
                    found.add(path)
                continue
            inner = getattr(route, "original_router", route)
            sub = getattr(inner, "routes", None)
            if sub and not hasattr(route, "app"):
                walk(sub)

    walk(app.routes)
    return found


def test_a_path_nobody_classified_is_refused_by_default(client, caplog):
    """沒有分類過的路徑，學生拿不到——而且 log 裡有一行（規則 4）。

    這一項驗的是 middleware 的**預設值**，也就是選 middleware 而不是
    `Depends` 的全部理由。它用一條不存在的網址來驗，因為不存在的網址與
    「新加了一條路由但忘了分類」在 middleware 眼裡是同一件事。
    """
    sign_in_student(client)
    with caplog.at_level(logging.WARNING):
        r = client.get("/some/new/thing")
    assert r.status_code == 404
    assert any("沒有被分類過的路徑" in rec.message for rec in caplog.records), (
        "被擋下來卻沒有留下任何一行 log（規則 4：不許靜默失敗）"
    )


def test_the_gate_does_not_get_in_front_of_the_login_gate(client):
    """未登入的人要被導去登入頁，不是被告知「這裡沒有東西」。

    掛載順序的實際後果。`test_middleware_order` 守的是順序本身，
    這一項守的是那個順序**帶來的行為**——兩者都要，因為有人可能
    在「修好」順序的同時把那項斷言也改掉。
    """
    make_accounts(client)
    for path in ("/demos/sampling/aliasing", "/admin/content", "/nope"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, f"{path} 未登入時沒有導向登入頁"
        assert r.headers["location"] == "/login"


# ============================================================================
# 3. 擋得住：關著的內容，直接打網址拿不到
# ============================================================================

@pytest.mark.parametrize("content_id, url", sorted(DEMO_URLS.items()))
def test_no_closed_demo_can_be_opened_by_url(client, content_id, url):
    """展示逐項打一次。**不抽樣**——抽樣會讓漏掉的那一頁有六分之五的機會通過。"""
    sign_in_student(client)
    assert client.get(url).status_code == 404


def test_no_closed_topic_can_be_generated_by_url(client):
    """出題端點逐個題型打一次。

    ⛔ 這是 `/practice/generate` 那條「自己守」的路徑唯一的看守點——
    middleware 對它沒有意見（內容代號在 body 裡），所以如果
    `routes/practice.py` 那三行被拿掉，**只有這一項會紅**。
    """
    from app.generator import list_templates

    sign_in_student(client)
    for tpl in list_templates():
        r = client.post(
            "/practice/generate",
            data={"template_id": tpl.template_id, "difficulty": 1},
        )
        assert r.status_code == 400, f"{tpl.template_id} 沒開放卻出得了題"
        assert "$$" not in r.text, f"{tpl.template_id} 的題目內容外洩了"


def test_opening_one_demo_does_not_open_its_neighbour(client):
    """開一項就只開那一項。

    看起來是廢話，但它守的是一個具體的寫錯方式：用前綴或主題去比對
    （`demo.fourier.*`）而不是用完整代號。那種寫法在只有一個 Fourier
    展示的時候完全正確，會在第二個出現時安靜地失效。
    """
    from app.release import set_released

    sign_in_student(client)
    set_released({"demo.fourier.additive"})
    assert client.get(DEMO_URLS["demo.fourier.additive"]).status_code == 200
    for content_id, url in DEMO_URLS.items():
        if content_id != "demo.fourier.additive":
            assert client.get(url).status_code == 404, f"{content_id} 也被打開了"


def test_closing_something_takes_effect_without_a_restart(client):
    """老師關掉之後，下一個請求就拿不到了（`released_ids()` 不快取）。"""
    from app.release import set_released

    sign_in_student(client)
    set_released({"demo.sampling.aliasing"})
    assert client.get(DEMO_URLS["demo.sampling.aliasing"]).status_code == 200
    set_released(set())
    assert client.get(DEMO_URLS["demo.sampling.aliasing"]).status_code == 404


def test_an_unknown_demo_address_is_still_a_404(client):
    """打錯網址與「這一頁沒開放」對學生是同一句話（D24 的分寸）。"""
    open_all_content(client)
    sign_in_student(client)
    assert client.get("/demos/sampling/nope").status_code == 404


# ============================================================================
# 4. 看得到的那一面
# ============================================================================

def test_an_opened_topic_shows_up_and_generates(client):
    from app.release import set_released

    sign_in_student(client)
    set_released({"fourier.series.full_range"})

    html = client.get("/").text
    assert "fourier.series.full_range" in html
    assert "ode.first_order.separable" not in html, "沒開放的題型出現在選單上"

    r = client.post(
        "/practice/generate",
        data={"template_id": "fourier.series.full_range", "difficulty": 1},
    )
    assert r.status_code == 200
    assert "Show Answer" in r.text


def test_a_closed_topic_leaves_no_trace_on_the_page(client):
    """未開放的內容**完全不出現**——不灰掉、不留名字（D56）。

    連名稱都不能留：`Linear System 2x2 (Complex Eigenvalues)` 這一行
    本身就告訴學生課程後面會教什麼、系統打算做什麼，而那正是 D24 說
    「系統少說話」的東西。
    """
    from app.generator import list_templates
    from app.release import set_released
    from markupsafe import escape

    sign_in_student(client)
    set_released({"fourier.series.full_range"})
    html = client.get("/").text

    for tpl in list_templates():
        if tpl.template_id == "fourier.series.full_range":
            continue
        assert tpl.template_id not in html, f"{tpl.template_id} 的代號還在頁面上"
        assert str(escape(tpl.name)) not in html, f"{tpl.name} 的名稱還在頁面上"


def test_a_student_with_nothing_open_is_told_so_in_words(client):
    """空狀態必須說得出「還沒開放」，不能只是一頁空白（D54 的第一個落點）。

    ⚠️ 這一項與下面那項 D24 的沉默測試是一對，而且它們**看起來互相矛盾**：
    一個要求說話，一個禁止列出待補項目。分界線是「有沒有列出東西」——
    說明機制可以，列出清單不行。
    """
    sign_in_student(client)
    html = client.get("/").text
    assert "Nothing is open yet" in html
    assert "opens each week's material" in html
    assert "<select" not in html, "沒有東西可選的時候不該還有一個空的下拉選單"


def test_a_student_with_no_demo_open_is_told_so_in_words(client):
    sign_in_student(client)
    html = client.get("/demos").text
    assert "no demo has been opened so far" in html
    assert 'href="/demos/' not in html


def test_the_demo_index_only_lists_what_is_open(client):
    from app.release import set_released

    sign_in_student(client)
    set_released({"demo.sampling.aliasing"})
    html = client.get("/demos").text
    assert "Sampling and aliasing" in html
    assert "Poles, zeros and digital filters" not in html
    assert "Fourier series" not in html


def test_staff_see_everything_regardless(client):
    """老師要能在按下「開放」之前先自己點進去看一眼。

    這不是特權，是這個功能能用的前提——若老師也被擋著，唯一的檢查方式
    會變成「先開放給全班、自己看完再關掉」，也就是每週對學生閃一次
    還沒準備好的內容。
    """
    from app.generator import list_templates

    sign_in_teacher(client)
    html = client.get("/").text
    for tpl in list_templates():
        assert tpl.template_id in html
    for url in DEMO_URLS.values():
        assert client.get(url).status_code == 200
    r = client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
    )
    assert r.status_code == 200


# ============================================================================
# 5. 管理頁
# ============================================================================

def test_the_admin_page_is_staff_only(client):
    sign_in_student(client)
    assert client.get("/admin/content").status_code in (403, 404)
    assert client.post(
        "/admin/content", data={"action": "save"}
    ).status_code in (403, 404)


def test_the_admin_link_is_only_in_the_staff_header(client):
    sign_in_student(client)
    assert 'href="/admin/content"' not in client.get("/").text
    client.post("/logout")
    log_in(client, "staff", STAFF_PASSWORD)
    assert 'href="/admin/content"' in client.get("/").text


def test_the_admin_page_lists_every_week_and_every_item(client):
    from app.curriculum import ALL_CONTENT_IDS

    sign_in_teacher(client)
    html = client.get("/admin/content").text
    for week in range(1, 17):
        assert f"Week {week} —" in html, f"管理頁少了第 {week} 週"
    for content_id in ALL_CONTENT_IDS:
        assert content_id in html, f"管理頁少了 {content_id}"


def test_saving_the_form_sets_exactly_what_was_ticked(client):
    """存檔是**覆寫**，不是增量——沒有勾的就是關的。"""
    from app.release import released_ids

    sign_in_teacher(client)
    client.post(
        "/admin/content",
        data={"action": "save", "open": ["demo.fourier.additive",
                                         "fourier.series.full_range"]},
    )
    assert released_ids() == {"demo.fourier.additive", "fourier.series.full_range"}

    client.post("/admin/content", data={"action": "save",
                                        "open": ["demo.fourier.additive"]})
    assert released_ids() == {"demo.fourier.additive"}


def test_open_week_opens_the_whole_week_in_one_click(client):
    """老師每週的那一下。第 3 週有三個 Fourier 題型加一個展示。"""
    from app.curriculum import ids_for_week
    from app.release import released_ids

    sign_in_teacher(client)
    client.post("/admin/content", data={"action": "open-week:3"})
    assert released_ids() == set(ids_for_week(3))
    assert len(ids_for_week(3)) == 4


def test_open_week_keeps_what_was_already_ticked_on_the_screen(client):
    """⛔ 整週按鈕以**畫面上的勾選**為基礎，不是以資料庫為基礎。

    反過來寫的話，「先手動改三個核取方塊、再按開放整週」會讓那三個改動
    無聲消失——頁面重新載入之後看起來完全正常，只是他剛剛做的事沒發生。
    """
    from app.release import released_ids

    sign_in_teacher(client)
    client.post(
        "/admin/content",
        data={"action": "open-week:3", "open": ["demo.sampling.aliasing"]},
    )
    assert "demo.sampling.aliasing" in released_ids()
    assert "demo.fourier.additive" in released_ids()


def test_close_week_removes_only_that_week(client):
    from app.curriculum import ids_for_week
    from app.release import released_ids, set_released

    sign_in_teacher(client)
    set_released(set(ids_for_week(3)) | set(ids_for_week(6)))
    client.post(
        "/admin/content",
        data={
            "action": "close-week:3",
            "open": sorted(set(ids_for_week(3)) | set(ids_for_week(6))),
        },
    )
    assert released_ids() == set(ids_for_week(6))


def test_closing_a_later_week_does_not_close_what_an_earlier_week_opened(client):
    """W12／W13 的按鈕不得動到 W10 開的系統題型（`curriculum.py` 末段那條）。

    失敗的樣子：老師上完狀態空間，按「關閉第 12 週」，四個系統題型
    從學生的選單上消失——而它們在第 10 週就開了、學生正在期末複習用。
    """
    from app.curriculum import ids_for_week
    from app.release import released_ids

    sign_in_teacher(client)
    client.post("/admin/content", data={"action": "open-week:10"})
    opened = released_ids()
    assert "system.linear_2x2.complex" in opened

    client.post(
        "/admin/content",
        data={"action": "close-week:12", "open": sorted(opened)},
    )
    assert released_ids() == opened
    assert ids_for_week(12) == ()


def test_an_unknown_content_id_in_the_form_is_ignored_and_logged(client, caplog):
    """表單被改過。丟掉它，但**說出來**（規則 4）。"""
    from app.release import released_ids

    sign_in_teacher(client)
    with caplog.at_level(logging.WARNING):
        client.post(
            "/admin/content",
            data={"action": "save", "open": ["ode.first_order.separable",
                                             "made.up.thing"]},
        )
    assert released_ids() == {"ode.first_order.separable"}
    assert any("不認得的內容代號" in rec.message for rec in caplog.records)


def test_the_setting_survives_a_restart(client):
    """持久化：換一個 app 實例（等同重啟）之後開放狀態還在。

    這是選資料表而不是行程內狀態的理由，所以它要有測試——「重啟後
    全部關回去」不會拋錯，只會讓老師每週一早發現學生看不到東西。
    """
    from fastapi.testclient import TestClient

    from app.release import released_ids

    sign_in_teacher(client)
    client.post("/admin/content", data={"action": "open-week:6"})

    import importlib

    from app import main as main_module

    importlib.reload(main_module)
    with TestClient(main_module.app) as fresh:
        fresh.session_module = client.session_module   # 同一個 DB 檔
        make_accounts(fresh)
        log_in(fresh, "class", CLASS_PASSWORD)
        assert fresh.get(DEMO_URLS["demo.sampling.aliasing"]).status_code == 200
    assert released_ids() == {"demo.sampling.aliasing"}


def test_the_startup_check_says_when_nothing_is_open(client, caplog):
    """D54 的第二個落點：老師不會用學生帳號登入，log 是唯一的途徑。"""
    from app.release import set_released, warn_if_nothing_is_open

    set_released(set())
    with caplog.at_level(logging.WARNING):
        warn_if_nothing_is_open()
    assert any(
        "沒有任何內容對學生開放" in rec.message for rec in caplog.records
    )


# ============================================================================
# 6. 不受影響的東西
# ============================================================================

def test_closing_a_topic_does_not_change_the_activity_numbers(client):
    """`/activity` 統計全部歷史用量，與開放狀態正交（老師這一輪指定）。

    把已關閉的週次從統計裡拿掉，會讓期末的總數比期中還小——一個沒有人
    解釋得清楚的數字，而且它會被讀成「學生變少了」。
    """
    from app.release import set_released

    make_accounts(client)
    set_released({"ode.first_order.separable"})
    log_in(client, "class", CLASS_PASSWORD)
    client.post(
        "/practice/generate",
        data={"template_id": "ode.first_order.separable", "difficulty": 1},
    )
    client.post("/logout")

    set_released(set())                       # 老師關掉了那一週
    log_in(client, "staff", STAFF_PASSWORD)
    html = client.get("/activity").text
    assert "Separable Equations" in html, "關掉題型之後統計就看不到它了"
    assert ">1<" in html or "1</th>" in html


def test_the_release_table_has_no_column_that_points_at_a_person(client):
    """新增的表不得引入任何個人資料（規則 3 的延伸，D53）。

    ⚠️ 看起來最自然的一欄是「是誰改的」。系統裡只有一個 staff 帳號，
    所以那一欄答不出任何問題；而它會讓規則 3 的邊界變成「除了那張表以外」。
    """
    from app.db.models import ReleaseState

    columns = set(ReleaseState.model_fields)
    assert columns == {"id", "content_id", "is_open", "updated_at"}
    banned = ("account", "student", "session", "ip", "address", "agent", "user")
    for column in columns:
        assert not any(word in column.lower() for word in banned), column


def test_the_release_table_stores_nothing_that_looks_like_a_person(client):
    """真的翻一次資料庫檔案，比對欄位名稱的作法多一層（同 D36 那項的手法）。"""
    from app.db.models import ReleaseState

    sign_in_teacher(client)
    client.post("/admin/content", data={"action": "open-week:3"})
    with Session(client.session_module.engine) as s:
        rows = s.exec(select(ReleaseState)).all()
    assert rows
    for row in rows:
        assert row.content_id.startswith(("ode.", "system.", "fourier.", "demo."))


@pytest.mark.parametrize("path", ["/", "/demos", "/admin/content"])
def test_no_page_advertises_what_has_not_been_opened(client, path):
    """D24 的沉默，在這個功能上特別容易破。

    這個功能天生想說「第 12 週的內容還沒開放」——那正好是 D24 禁止的那句話。
    ⚠️ 管理頁也在清單裡：它只有老師看得到，但那不是開例外的理由，
    而**它是最容易寫出時程承諾的一頁**（它手上就有一張完整的週次表）。
    """
    from tests.test_demos import PROGRESS_WORDS

    sign_in_teacher(client)
    text = client.get(path).text.lower()
    for word in PROGRESS_WORDS:
        assert word not in text, f"{path} 出現了進度／時程措辭：{word}"


def test_the_student_facing_note_names_no_content_and_no_date(client):
    """學生端那一句話：可以說明機制，不可以列出東西、不可以寫日期。

    這是 D24 與「不要讓學生以為系統壞了」之間那條線的落點，所以它
    有一項專門的測試——一句多寫了「Fourier series will open in week 3」
    的說明不會讓任何東西壞掉。
    """
    import re

    from app.release import set_released

    sign_in_student(client)
    set_released({"fourier.series.full_range"})
    html = client.get("/").text
    assert "opens each week's material" in html
    # 不得出現「第 N 週」這種對未來的指涉。
    assert not re.search(r"[Ww]eek \d", html), "學生端出現了具體的週次"
    assert not re.search(r"20\d\d[-/]\d", html), "學生端出現了日期"
