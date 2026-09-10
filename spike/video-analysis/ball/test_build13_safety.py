"""Build-13 RED/GREEN regressions; all labels are synthetic."""

import hashlib
import json
from pathlib import Path

import pytest

from compare_label_exports import compare
from test_kit_safety import (
    browser as browser,
    kit as kit,
    open_page,
    settle,
    review,
    press,
    current,
    upload,
)
from test_storage_ties import merge, state, KEY

HERE = Path(__file__).parent


def export(page):
    with page.expect_download() as d:
        page.locator("#export").click()
    return Path(d.value.path()).read_text()


def import_text(page, text):
    page.locator("#import").set_input_files(
        {"name": "backup.json", "mimeType": "application/json", "buffer": text.encode()}
    )
    page.wait_for_function("document.getElementById('import').value===''")
    settle(page)


def old_rows(kit):
    return [{k: r[k] for k in ("clip", "t", "visible", "x", "y")} for r in kit["rows"]]


def legacy_set(page, rows):
    page.evaluate(
        "text=>localStorage.setItem(legacyKey,text)",
        "\n".join(json.dumps(r) for r in rows) + "\n",
    )
    page.reload()
    settle(page)


def bootstrap(ctx, kit):
    p = open_page(ctx, kit)
    rows = old_rows(kit)
    p.evaluate("localStorage.clear()")
    legacy_set(p, rows)
    return p, rows


@pytest.mark.parametrize("choice", ["use", "keep"])
def test_h1_skipped_old_decision_requires_reconciliation(browser, kit, choice):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        review(page)
        press(page, "n")
        mine = current(page)
        rows[0].update(visible=True, x=333, y=222)
        legacy_set(page, rows)
        page.on("dialog", lambda d: d.accept())
        upload(page, rows)
        assert page.locator("#legacy-warning").is_visible()
        links = page.locator("#legacy-keys a")
        assert links.count() == 1
        links.first.click()
        settle(page)
        assert "Old page: ball at" in page.locator("#legacy-values").inner_text()
        assert "This page: no ball" in page.locator("#legacy-values").inner_text()
        page.locator("#legacy-" + choice).click()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        if choice == "use":
            assert current(page)["visible"] and current(page)["x"] == 333
            assert current(page)["match_ball"] is True  # committed v1 migration
        else:
            assert current(page) == mine
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        assert open_page(ctx, kit).locator("#legacy-warning").is_hidden()
        rows[0]["x"] = 334
        legacy_set(page, rows)
        assert page.locator("#legacy-warning").is_visible()


@pytest.mark.parametrize("which", ["current", "pre_clear", "own"])
def test_h2_h3_old_clear_is_never_acknowledged_by_import(browser, kit, which):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        before = list(rows)
        own = export(page)
        rows = rows[:-1]
        legacy_set(page, rows)
        page.on("dialog", lambda d: d.accept())
        if which == "own":
            import_text(page, own)
        else:
            upload(page, rows if which == "current" else before)
        assert page.locator("#legacy-warning").is_visible()
        page.locator("#legacy-keys a").first.click()
        settle(page)
        assert "Old page: cleared" in page.locator("#legacy-values").inner_text()
        page.locator("#legacy-use").click()
        settle(page)
        assert page.evaluate("!labels[api.key(frames[188])]")
        assert page.locator("#legacy-warning").is_hidden()


@pytest.mark.parametrize("kind", ["sha", "fnv"])
@pytest.mark.parametrize("changed", [False, True])
def test_hash_baseline_upgrade_or_explicit_fallback(browser, kit, kind, changed):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        raw = page.evaluate("localStorage.getItem(legacyKey)")
        oldhash = (
            hashlib.sha256(json.dumps(raw, ensure_ascii=False).encode()).hexdigest()
            if kind == "sha"
            else page.evaluate("legacyHash(localStorage.getItem(legacyKey))")
        )
        page.evaluate(
            "v=>{localStorage.removeItem(legacyHashKey);localStorage.setItem(storageKey+':legacy-sha256',v)}",
            oldhash,
        )
        if changed:
            rows[-1]["x"] += 5
        legacy_set(page, rows)
        if changed:
            assert page.locator("#legacy-warning").is_visible()
            assert (
                "can't tell which frames"
                in page.locator("#legacy-message").inner_text()
            )
            upload(page, rows)
            assert page.locator("#legacy-warning").is_visible()
            # Once history is unknown, only Dismiss acknowledges it, even if v1 reverts.
            page.evaluate("raw=>localStorage.setItem(legacyKey,raw)", raw)
            page.reload()
            settle(page)
            assert page.locator("#legacy-warning").is_visible()
            page.once("dialog", lambda d: d.accept())
            page.locator("#dismiss-legacy").click()
            settle(page)
            assert page.locator("#legacy-warning").is_hidden()
        else:
            baseline = json.loads(page.evaluate("localStorage.getItem(legacyHashKey)"))
            assert baseline["raw"] == raw and baseline["taken_at"] > 0
            assert page.locator("#legacy-warning").is_hidden()


def test_all_pending_links_keep_and_bulk_with_quota_fallback(browser, kit):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        for row in rows[:25]:
            row.update(visible=True, x=555, y=555)
        legacy_set(page, rows)
        assert page.locator("#legacy-keys a").count() == 25
        page.locator("#legacy-keys a").first.click()
        settle(page)
        page.locator("#legacy-keep").click()
        settle(page)
        page.reload()
        settle(page)
        assert page.locator("#legacy-keys a").count() == 24
        before = page.evaluate("localStorage.getItem(storageKey)")
        page.once("dialog", lambda d: d.dismiss())
        page.locator("#legacy-all").click()
        settle(page)
        assert page.evaluate("localStorage.getItem(storageKey)") == before
        page.once("dialog", lambda d: d.accept())
        page.locator("#legacy-all").click()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
    with browser.new_context() as ctx:
        ctx.add_init_script(
            """const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k.endsWith(':legacy-baseline-v1')&&v.startsWith('{'))throw new DOMException('quota','QuotaExceededError');return original.call(this,k,v)}"""
        )
        page, rows = bootstrap(ctx, kit)
        assert not page.evaluate("readOnly")
        rows[-1]["x"] += 3
        legacy_set(page, rows)
        assert not page.evaluate("readOnly")
        assert "can't tell which frames" in page.locator("#legacy-message").inner_text()


def test_recovery_retains_memory_and_accepts_own_backup(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        old = export(page)
        page.evaluate("index=188;show()")
        settle(page)
        page.locator("#canvas").click(position={"x": 40, "y": 40})
        settle(page)
        mine = current(page)
        page.evaluate("localStorage.setItem(storageKey,'{broken')")
        press(page, "n")
        assert page.evaluate("readOnly")
        backup = export(page)
        page.on("dialog", lambda d: d.accept())
        import_text(page, old)
        assert len(page.evaluate("labels")) == 189 and current(page) == mine
        fresh = open_page(ctx, kit)
        assert fresh.evaluate("labels[api.key(frames[188])]") == mine
        # A recovery backup carries clears as well as the last valid labels.
        page.locator("#clear").click()
        settle(page)
        expected = page.evaluate("state")
        page.evaluate("localStorage.setItem(storageKey,'{broken')")
        press(page, "n")
        backup = export(page)
        import_text(page, backup)
        assert not page.evaluate("readOnly")
        assert page.evaluate("state") == expected
        assert open_page(ctx, kit).evaluate("state") == expected
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        page.on("dialog", lambda d: d.accept())
        import_text(page, backup)
        assert set(page.evaluate("labels")) == set(expected["labels"])
        assert set(page.evaluate("state.deleted")) == set(expected["deleted"])


def test_clear_wins_confirmed_tie_and_equal_row_import_is_distinct(browser, kit):
    assert merge(state("confirmed"), state("clear"))["result"]["labels"] == {}
    assert merge(state("clear"), state("confirmed"))["result"]["labels"] == {}
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        row = current(page)
        row["x"] += 3
        upload(page, [row])
        assert current(page)["x"] == row["x"]
    assert (
        merge(state("unconfirmed", x=1), state("unconfirmed", x=2))["result"]["labels"][
            KEY
        ]["x"]
        == 2
    )


def test_review_frame_and_unknown_fields_are_semantic(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    row = {
        "clip": "synthetic",
        "t": 1,
        "visible": False,
        "x": None,
        "y": None,
        "match_ball": None,
        "schema_version": 2,
    }
    a.write_text(json.dumps(row))
    for field, count in [
        ("review_frame", "review_state_changes"),
        ("new_field", "unknown_fields"),
    ]:
        b.write_text(json.dumps({**row, field: True}))
        result = compare(a, b)
        assert result["counts"][count] == 1 and result["verdict"] == "differs"


def test_suite_wording_and_lan_only_private_binding():
    source = (HERE / "test_build12_safety.py").read_text()
    assert "CI must exercise actual build-10 JS" not in source
    readme = (HERE / "README.md").read_text()
    assert "GitHub CI does not run the spike tests" in readme
    script = HERE / "check_build13_private.py"
    assert script.exists()
    assert '"0.0.0.0"' not in script.read_text()


def test_reconciliation_checks_storage_before_resolving_stale_tab_memory(browser, kit):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        page.evaluate(
            "()=>{const k=api.key(frames[0]);state.labels[k]={...labels[k],x:55,y:55};persist()}"
        )
        # A different tab saved no-ball; this tab has not consumed its event yet.
        page.evaluate(
            """()=>{const saved=store.parse(localStorage.getItem(storageKey),frames),k=api.key(frames[0]);saved.labels[k]={clip:frames[0].clip,t:frames[0].t,visible:false,x:null,y:null,match_ball:null,schema_version:2,updated_at:store.clock(saved)};localStorage.setItem(storageKey,store.serialize(saved))}"""
        )
        rows[0].update(x=55, y=55)
        page.evaluate(
            "raw=>{localStorage.setItem(legacyKey,raw);show()}",
            "\n".join(json.dumps(r) for r in rows) + "\n",
        )
        settle(page)
        assert page.locator("#legacy-warning").is_visible()
        assert page.locator("#legacy-keys a").count() == 1
