"""Build-15 key-press feedback regressions in real Chromium; synthetic labels only."""

import pytest

from test_kit_safety import (
    browser as browser,
    kit as kit,
    open_page,
    settle,
    review,
    press,
    current,
)

ACTIONS = {"Enter": "accept", "n": "none", "m": "match", "c": "confirm"}
IDLE = {"place": 0, "accept": 0, "none": 0, "match": 0, "confirm": 0}


def badge(page):
    return page.locator("#badge").inner_text()


def lit(page, button):
    page.wait_for_function(
        f"document.getElementById('{button}').classList.contains('active')"
    )


def unlit(page, button):
    page.wait_for_function(
        f"!document.getElementById('{button}').classList.contains('active')"
    )


def act(page, key):
    # Press without settling first so the highlight window itself is observed.
    page.keyboard.press(key)
    lit(page, ACTIONS[key])
    settle(page)
    unlit(page, ACTIONS[key])


def stored_row(page, key):
    return page.evaluate(
        "key=>JSON.parse(localStorage.getItem(storageKey)).labels.find(r=>api.key(r)===key)",
        key,
    )


def select(page, key):
    page.evaluate("key=>{index=frames.findIndex(f=>api.key(f)===key);show()}", key)
    settle(page)


def without_time(row):
    return {k: v for k, v in row.items() if k != "updated_at"}


def test_every_key_lights_its_button_and_badge_reads_the_saved_label(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        review(page)
        key = page.evaluate("api.key(frames[index])")
        assert badge(page) == "Ball (not match)"
        assert page.evaluate("flashes") == IDLE
        act(page, "Enter")
        assert badge(page) == "Ball (not match) · Confirmed"
        row = current(page)
        assert row["visible"] and row["match_ball"] is False and row["source_accepted"]
        act(page, "m")
        assert badge(page) == "Match ball · Confirmed"
        assert current(page)["match_ball"] is True
        act(page, "c")
        assert badge(page) == "Ball (not match) · Confirmed"
        assert (
            current(page)["match_ball"] is False and current(page)["review_confirmed"]
        )
        act(page, "n")
        assert badge(page) == "No ball · Confirmed"
        assert current(page)["visible"] is False
        assert stored_row(page, key)["visible"] is False
        page.locator("#canvas").click(position={"x": 120, "y": 80})
        lit(page, "place")
        settle(page)
        unlit(page, "place")
        assert badge(page) == "Ball (not match) · Confirmed"
        assert page.evaluate("badge.dataset.state") == "ball-confirmed"
        placed = stored_row(page, key)
        assert placed["visible"] and placed["match_ball"] is False
        assert current(page) == placed
        assert page.evaluate("flashes") == {**IDLE, **{k: 1 for k in IDLE}}


def test_no_ball_persists_across_navigation_reload_and_tabs(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        review(page)
        key = page.evaluate("api.key(frames[index])")
        act(page, "n")
        stored = stored_row(page, key)
        assert stored["visible"] is False and stored["review_confirmed"] is True
        assert badge(page) == "No ball · Confirmed"
        press(page, "ArrowRight")
        assert page.evaluate("api.key(frames[index])") != key
        assert badge(page) == "No ball"  # pending queue row: not confirmed
        assert page.evaluate("badge.dataset.state") == "none"
        press(page, "ArrowLeft")
        assert badge(page) == "No ball · Confirmed"
        page.reload()
        settle(page)
        assert not page.evaluate("reviewMode")
        select(page, key)
        assert badge(page) == "No ball · Confirmed"
        assert page.evaluate("flashes") == IDLE
        fresh = open_page(ctx, kit)
        select(fresh, key)
        assert badge(fresh) == "No ball · Confirmed"
        assert stored_row(fresh, key) == stored
        fresh.locator("#clear").click()
        settle(fresh)
        assert badge(fresh) == "Unlabelled"
        assert fresh.evaluate("badge.dataset.state") == "unlabelled"
        last = fresh.evaluate("api.key(frames[188])")
        select(fresh, last)
        assert badge(fresh) == "Match ball"
        assert fresh.evaluate("badge.dataset.state") == "match"


@pytest.mark.parametrize("key", ["Enter", "n", "m", "c"])
def test_button_click_is_the_key(browser, kit, key):
    button = ACTIONS[key]
    with browser.new_context() as by_key, browser.new_context() as by_click:
        a = open_page(by_key, kit)
        b = open_page(by_click, kit)
        review(a)
        review(b)
        assert a.evaluate("api.key(frames[index])") == b.evaluate(
            "api.key(frames[index])"
        )
        act(a, key)
        b.locator("#" + button).click()
        lit(b, button)
        settle(b)
        unlit(b, button)
        assert without_time(current(a)) == without_time(current(b))
        assert current(b)["updated_at"] > 0
        assert badge(a) == badge(b)
        assert a.evaluate("flashes") == b.evaluate("flashes") == {**IDLE, button: 1}


def test_feedback_only_follows_a_real_save_and_never_writes(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        review(page)
        act(page, "n")
        raw = page.evaluate("localStorage.getItem(storageKey)")
        # M on a no-ball frame is disabled: the key does nothing and nothing lights.
        assert page.locator("#match").is_disabled()
        press(page, "m")
        assert page.evaluate("flashes") == {**IDLE, "none": 1}
        page.locator("#place").click()
        settle(page)
        assert page.evaluate("flashes.place") == 0
        page.evaluate("for(let i=0;i<50;i++)show();flash('accept')")
        settle(page)
        assert page.evaluate("localStorage.getItem(storageKey)") == raw
        assert badge(page) == "No ball · Confirmed"
        # Read-only page: keys and clicks light nothing; badge shows what was salvaged.
        page.evaluate("localStorage.setItem(storageKey,'{broken')")
        page.reload()
        settle(page)
        assert page.evaluate("readOnly")
        for key in ("Enter", "n", "m", "c"):
            page.keyboard.press(key)
        page.evaluate("window.scrollTo(0,0)")  # the sticky nav must not cover the click
        page.locator("#canvas").click(position={"x": 100, "y": 100})
        settle(page)
        assert page.evaluate("flashes") == IDLE
        assert badge(page) == "Unlabelled"
        assert page.locator("#place").is_disabled()
        assert page.evaluate("localStorage.getItem(storageKey)") == "{broken"


def test_page_names_build_15_and_accept_button_names_its_default(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        assert page.title() == "Ball truth review — build 15"
        assert "13, 14 or 15" in page.locator("#seed-help").inner_text()
        assert page.locator("#accept").inner_text().endswith("match ball")
        assert page.locator("#keys button").count() == 5
        review(page)
        assert page.locator("#accept").inner_text().endswith("ball (not match)")
