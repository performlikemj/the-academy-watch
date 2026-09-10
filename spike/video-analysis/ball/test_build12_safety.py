"""Build-12 regressions: synthetic rows only; RED recorded before fixes."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from compare_label_exports import compare
from label_rule import migrate_row
from test_kit_safety import (  # noqa: F401
    browser as browser,
    kit as kit,
    open_page,
    settle,
    review,
    press,
    current,
    upload,
)

HERE = Path(__file__).parent


def watch(page, accept=True):
    messages = []

    def handle(d):
        messages.append(d.message)
        d.accept() if accept else d.dismiss()

    page.on("dialog", handle)
    return messages, handle


def raw(page):
    return page.evaluate("localStorage.getItem(storageKey)")


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("age", ["older", "equal", "newer"])
def test_import_respects_clear_decision(browser, kit, confirmed, age):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        if confirmed:
            review(page)
            press(page, "Enter")
        row = current(page)
        page.locator("#clear").click()
        settle(page)
        key = page.evaluate("api.key(frames[index])")
        clear = page.evaluate("k=>state.deleted[k]", key)
        row["updated_at"] = clear + {"older": -1, "equal": 0, "newer": 1}[age]
        before = raw(page)
        messages, handle = watch(page, accept=False)
        upload(page, [row])
        assert raw(page) == before
        summary = page.locator("#import-summary").inner_text()
        assert "0 new" in summary and "restores a cleared frame" in summary
        if age == "newer":
            assert len(messages) == 1
            page.remove_listener("dialog", handle)
            watch(page)
            upload(page, [row])
            assert current(page)["updated_at"] > clear
        else:
            assert messages == []
            assert "skipped 1 rows older than what is saved here" in summary
            assert key in summary
            watch(page)
            upload(page, [row])
            assert raw(page) == before
            fresh = open_page(ctx, kit)
            assert fresh.evaluate("k=>!labels[k]", key)
            with page.expect_download() as d:
                page.locator("#export").click()
            exported = Path(d.value.path()).read_text()
            assert all(
                f"{r['clip']}|{r['t']:.6f}" != key
                for r in map(json.loads, exported.splitlines())
            )


def test_stale_rows_never_apply_in_mixed_import(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        review(page)
        mine = []
        for _ in range(3):
            press(page, "n")
            mine.append(current(page))
            press(page, "ArrowRight")
        incoming = [
            {
                **r,
                "visible": True,
                "x": 10,
                "y": 20,
                "match_ball": False,
                "updated_at": 0,
            }
            for r in mine
        ]
        incoming.append({**kit["rows"][-1], "x": 77})
        messages, _ = watch(page)
        upload(page, incoming)
        assert (
            page.evaluate(
                "ks=>ks.map(k=>labels[k])", [f"{r['clip']}|{r['t']:.6f}" for r in mine]
            )
            == mine
        )
        assert page.evaluate("labels[api.key(frames[188])].x") == 77
        assert (
            messages == []
        )  # Only stale confirmed rows; nothing eligible needs approval.
        assert (
            "skipped 3 rows older than what is saved here"
            in page.locator("#import-summary").inner_text()
        )


def test_stale_key_list_is_bounded(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        page.evaluate(
            "()=>{for(const row of Object.values(state.labels))row.updated_at=100;persist()}"
        )
        watch(page)
        upload(page, kit["rows"])
        summary = page.locator("#import-summary").inner_text()
        assert "skipped 189 rows older than what is saved here" in summary
        assert "first 20" in summary and "169 more" in summary
        assert summary.count("|") == 20


def legacy_warning(page, rows):
    text = "\n".join(json.dumps(r) for r in rows) + "\n"
    page.evaluate("text=>localStorage.setItem(legacyKey,text)", text)
    page.reload()
    settle(page)
    assert page.locator("#legacy-warning").is_visible()
    return text


def test_full_legacy_import_clears_warning_partial_does_not(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        legacy = [
            {k: r[k] for k in ("clip", "t", "visible", "x", "y")}
            for r in kit["rows"][-2:]
        ]
        legacy[-1]["x"] = 77
        legacy_warning(page, legacy)
        watch(page)
        upload(page, legacy[:1])
        assert page.locator("#legacy-warning").is_visible()
        upload(page, legacy)
        assert page.locator("#legacy-warning").is_hidden()
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        fresh = open_page(ctx, kit)
        assert fresh.locator("#legacy-warning").is_hidden()
        legacy[-1]["x"] = 88
        legacy_warning(page, legacy)


def test_dismiss_legacy_warning_requires_confirmation(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        legacy_warning(
            page,
            [
                {
                    **{
                        k: kit["rows"][-1][k]
                        for k in ("clip", "t", "visible", "x", "y")
                    },
                    "x": 60,
                }
            ],
        )
        button = page.locator("#dismiss-legacy")
        assert button.count() == 1
        before = raw(page)
        page.once("dialog", lambda d: d.dismiss())
        button.click()
        settle(page)
        assert page.locator("#legacy-warning").is_visible()
        page.once("dialog", lambda d: d.accept())
        button.click()
        settle(page)
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        assert raw(page) == before


def test_no_secure_crypto_required_and_hash_has_tag(browser, kit):
    with browser.new_context() as ctx:
        ctx.add_init_script("Object.defineProperty(crypto,'subtle',{value:undefined})")
        page = open_page(ctx, kit)
        assert not page.evaluate("readOnly")
        value = page.evaluate("localStorage.getItem(legacyHashKey)")
        assert json.loads(value)["kind"] == "ball-legacy-raw-v1"
        review(page)
        press(page, "n")
        assert current(page)["review_confirmed"]
        for obsolete in ("old-untagged-hash", "unknown:123"):
            page.evaluate("v=>localStorage.setItem(legacyHashKey,v)", obsolete)
            page.reload()
            settle(page)
            assert not page.evaluate("readOnly")
            assert page.locator("#legacy-warning").is_visible()
            page.once("dialog", lambda d: d.accept())
            page.locator("#dismiss-legacy").click()
            settle(page)
            assert (
                json.loads(page.evaluate("localStorage.getItem(legacyHashKey)"))["kind"]
                == "ball-legacy-raw-v1"
            )


def test_compare_migration_and_semantic_categories(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    v1 = {"clip": "synthetic", "t": 1, "visible": False, "x": None, "y": None}
    v2 = migrate_row(v1, {"sample_index": 0})

    def check(left, right, labels, reviews):
        a.write_text(json.dumps(left) + "\n")
        b.write_text(json.dumps(right) + "\n")
        result = compare(a, b)
        assert result["counts"]["label_changes"] == labels
        assert result["counts"]["review_state_changes"] == reviews
        run = subprocess.run(
            [sys.executable, str(HERE / "compare_label_exports.py"), str(a), str(b)],
            capture_output=True,
            text=True,
        )
        assert run.returncode == int(bool(labels or reviews))
        assert '"x":' not in run.stdout and '"y":' not in run.stdout

    check(v1, v2, 0, 0)
    check({**v2, "updated_at": 200}, v2, 0, 0)
    check(v2, {**v2, "needs_any_ball_review": False, "review_confirmed": True}, 0, 1)
    visible = {
        "clip": "synthetic",
        "t": 1,
        "visible": True,
        "x": 10,
        "y": 20,
        "match_ball": True,
        "schema_version": 2,
    }
    check(visible, {**visible, "x": 11}, 1, 0)


def test_frozen_build10_js_to_current_browser_compatibility(browser, kit):
    frozen = HERE / "fixtures/build10_js"
    assert (frozen / "truth_page.js").exists(), (
        "the test suite must exercise actual build-10 JS"
    )
    with browser.new_context() as ctx:
        old = kit["path"].with_name("build10.html")
        html = kit["path"].read_text()
        for name in ("truth_io.js", "truth_storage.js", "truth_page.js"):
            html = html.replace((HERE / name).read_text(), (frozen / name).read_text())
        old.write_text(html)
        page = open_page(ctx, {**kit, "path": old})
        review(page)
        press(page, "Enter")
        press(page, "ArrowRight")
        press(page, "n")
        press(page, "ArrowRight")
        page.locator("#clear").click()
        settle(page)
        rows, before = page.evaluate("labels"), raw(page)
        new = open_page(ctx, kit)
        assert new.evaluate("labels") == rows
        assert raw(new) == before
        assert new.evaluate("state.deleted") == page.evaluate("state.deleted")
