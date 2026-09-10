"""Storage/import/queue safety in real Chromium with synthetic rows only."""

import json
from pathlib import Path
from urllib.parse import quote

import pytest

from ball_truth_kit import render_page
from label_rule import BASE_REVIEW_KEYS, confirmed, rule_metadata
from compare_label_exports import compare


@pytest.fixture(scope="module")
def browser():
    pw_api = pytest.importorskip("playwright.sync_api")
    with pw_api.sync_playwright() as pw:
        bins = sorted(
            (Path.home() / "Library/Caches/ms-playwright").glob(
                "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
            )
        )
        instance = pw.chromium.launch(executable_path=str(bins[-1]) if bins else None)
        yield instance
        instance.close()


@pytest.fixture
def kit(tmp_path):
    picture = "data:image/svg+xml," + quote(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="green"/></svg>'
    )
    frames = [
        {
            "clip": f"test-{i // 94}",
            "t": float(i),
            "sample_index": i % 94,
            "source_size": [1920, 1080],
            "path": picture,
        }
        for i in range(189)
    ]
    rows = [
        {
            "clip": f["clip"],
            "t": f["t"],
            "x": None,
            "y": None,
            "visible": False,
            "schema_version": 2,
            "match_ball": None,
            "review_frame": True,
            "review_confirmed": False,
            "needs_any_ball_review": True,
            "updated_at": 0,
        }
        for f in frames
    ]
    rows[0].update(
        visible=True,
        x=31,
        y=41,
        match_ball=False,
        source_accepted=True,
        accepted_source="rf_2x2",
        accepted_score=0.6,
        needs_any_ball_review=False,
        needs_confirmation=True,
    )
    rows[-1] = {
        "clip": frames[-1]["clip"],
        "t": frames[-1]["t"],
        "x": 50,
        "y": 50,
        "visible": True,
        "schema_version": 2,
        "match_ball": True,
        "updated_at": 0,
    }
    suggestions = [
        {
            "clip": f["clip"],
            "t": f["t"],
            "x": 200,
            "y": 200,
            "score": 0.9 - i * 0.001,
            "source": "rf-r5-a",
        }
        for i, f in enumerate(frames)
    ]
    queue = [
        {"clip": f["clip"], "t": f["t"], "suggestion": s}
        for f, s in zip(frames[:188], suggestions)
    ]
    key, legacy = "ball-human-v2:test", "ball-human-v1:test"
    page = render_page(
        frames,
        rows,
        queue,
        suggestions,
        [],
        key,
        legacy,
        base_keys={(f["clip"], f["t"]) for f in frames[:188]},
        review_suggestions=suggestions,
    )
    path = tmp_path / "index.html"
    path.write_text(page)
    return {"path": path, "rows": rows, "key": key, "legacy": legacy}


def settle(page):
    page.evaluate("writes")
    page.wait_for_function("initialized && imageReady")


def open_page(context, kit):
    page = context.new_page()
    page.goto(kit["path"].as_uri())
    settle(page)
    return page


def review(page):
    page.locator("#review").click()
    settle(page)
    page.locator("h1").click()


def press(page, key):
    page.keyboard.press(key)
    settle(page)


def current(page):
    return page.evaluate("labels[api.key(frames[index])]")


def upload(page, rows):
    page.locator("#import").set_input_files(
        {
            "name": "test.jsonl",
            "mimeType": "application/x-ndjson",
            "buffer": ("\n".join(json.dumps(r) for r in rows) + "\n").encode(),
        }
    )
    page.wait_for_function(
        "document.getElementById('import').value==='' && document.getElementById('import-summary').textContent.startsWith('Import:')"
    )
    settle(page)


def test_legacy_input_once_old_tab_cannot_wipe_v2(browser, kit):
    with browser.new_context() as context:
        old = context.new_page()
        old.goto(kit["path"].as_uri())
        settle(old)
        v1 = [
            {k: r[k] for k in ("clip", "t", "x", "y", "visible")} for r in kit["rows"]
        ]
        raw = "\n".join(json.dumps(r) for r in v1) + "\n"
        old.evaluate(
            "([key,legacy,text])=>{localStorage.removeItem(key);localStorage.setItem(legacy,text)}",
            [kit["key"], kit["legacy"], raw],
        )
        page = open_page(context, kit)
        assert page.evaluate("Object.keys(labels).length") == len(v1)
        expected = [{k: r[k] for k in ("clip", "t", "x", "y", "visible")} for r in v1]
        actual = page.evaluate(
            "Object.values(labels).map(({clip,t,x,y,visible})=>({clip,t,x,y,visible}))"
        )
        assert sorted(actual, key=lambda r: r["t"]) == sorted(
            expected, key=lambda r: r["t"]
        )
        review(page)
        press(page, "Enter")
        assert current(page)["review_confirmed"]
        assert old.evaluate("key=>localStorage.getItem(key)", kit["legacy"]) == raw
        # Exact old save semantics: one N action rewrites the entire v1 snapshot.
        old.evaluate(
            "([key,rows])=>{rows[1]={...rows[1],visible:false,x:null,y:null};localStorage.setItem(key,rows.map(r=>JSON.stringify(r)).join('\\n')+'\\n')}",
            [kit["legacy"], v1],
        )
        fresh = open_page(context, kit)
        assert (
            fresh.evaluate("Object.values(labels).filter(r=>r.review_confirmed).length")
            == 1
        )
        assert current(page)["updated_at"] > 0


@pytest.mark.parametrize("which", ["legacy", "v2", "legacy-clears", "invalid-v2-row"])
def test_corrupt_storage_read_only_no_save(browser, kit, which):
    with browser.new_context() as context:
        setup = open_page(context, kit)
        badkey = (
            kit["legacy"]
            if which == "legacy"
            else kit["legacy"] + ":cleared"
            if which == "legacy-clears"
            else kit["key"]
        )
        raw = (
            json.dumps({**kit["rows"][0], "match_ball": "bad"})
            if which == "invalid-v2-row"
            else "{broken"
        )
        setup.evaluate(
            "([key,badkey,raw])=>{localStorage.clear();localStorage.setItem(badkey,raw)}",
            [kit["key"], badkey, raw],
        )
        setup.close()
        page = open_page(context, kit)
        assert page.evaluate("readOnly")
        assert "Export a recovery backup" in page.locator("#safety").inner_text()
        before = page.evaluate("JSON.stringify(labels)")
        stored = page.evaluate("JSON.stringify({...localStorage})")
        review(page)
        for key in ("Enter", "Space", "n", "m", "c"):
            press(page, key)
        page.locator("#canvas").click(position={"x": 100, "y": 100})
        settle(page)
        page.evaluate('save(()=>{throw Error("must not run")})')
        assert page.evaluate("JSON.stringify(labels)") == before
        assert page.evaluate("JSON.stringify({...localStorage})") == stored
        assert page.evaluate("readOnly")
        with page.expect_download() as download:
            page.locator("#export").click()
        backup = json.loads(Path(download.value.path()).read_text())
        assert raw in backup.values()
        page.once("dialog", lambda d: d.accept())
        upload(page, kit["rows"])
        assert not page.evaluate("readOnly")
        assert page.evaluate("Object.keys(labels).length") == 189


def test_cross_tab_merge_events_newest_row_and_clear(browser, kit):
    with browser.new_context() as context:
        a = open_page(context, kit)
        b = open_page(context, kit)
        review(a)
        review(b)
        press(a, "Enter")
        b.wait_for_function("confirmed(labels[api.key(frames[0])])")
        assert "labels changed in another tab" in b.locator("#status").inner_text()
        # Simulate a suspended tab that has not consumed the storage event.
        b.evaluate(
            "state=store.fromRows(api.parse(seedRows.map(r=>JSON.stringify(r)).join('\\n'),frames));rebuildQueue()"
        )
        press(b, "ArrowRight")
        press(b, "n")
        fresh = open_page(context, kit)
        assert fresh.evaluate("Object.values(labels).filter(confirmed).length") == 2
        # Same-key later edit wins and a clear cannot be resurrected by another tab.
        press(b, "ArrowLeft")
        press(b, "m")
        a.wait_for_function("labels[api.key(frames[0])].match_ball===true")
        latest = current(b)["updated_at"]
        assert latest > 0
        a.locator("#clear").click()
        settle(a)
        b.wait_for_function("!labels[api.key(frames[0])]")
        press(b, "ArrowRight")
        press(b, "n")
        fresh.reload()
        settle(fresh)
        assert fresh.evaluate("!labels[api.key(frames[0])]")
        assert fresh.evaluate("Object.values(labels).filter(confirmed).length") == 1


@pytest.mark.parametrize("version", [1, 2])
def test_import_counts_and_confirmation_downgrade_guard(browser, kit, version):
    with browser.new_context() as context:
        page = open_page(context, kit)
        review(page)
        press(page, "Enter")
        protected = current(page)
        legacy = {k: protected[k] for k in ("clip", "t", "x", "y", "visible")}
        if version == 2:
            legacy.update(
                schema_version=2,
                match_ball=False,
                review_frame=True,
                review_confirmed=False,
            )
        dialogs = []

        def reject(d):
            dialogs.append(d.message)
            d.dismiss()

        page.once("dialog", reject)
        upload(page, [legacy])
        assert current(page) == protected
        summary = page.locator("#import-summary").inner_text()
        assert "skipped 1 rows older than what is saved here" in summary
        assert not dialogs
        upload(page, [legacy])
        assert current(page) == protected
        upload(page, [current(page)])
        assert (
            "0 new, 0 changed, 1 unchanged"
            in page.locator("#import-summary").inner_text()
        )


def test_dynamic_queue_and_confirm_as_is(browser, kit):
    with browser.new_context() as context:
        page = open_page(context, kit)
        review(page)
        before = current(page)
        press(page, "c")
        after = current(page)
        for field in ("x", "y", "source_accepted", "accepted_source", "accepted_score"):
            assert after[field] == before[field]
        assert (
            after["match_ball"] is False
            and after["review_confirmed"]
            and not after["needs_confirmation"]
        )
        assert after["updated_at"] > before["updated_at"]
        # A confirmation on a non-queue row does not count towards the 188.
        extra = {**kit["rows"][-1], "review_frame": True, "review_confirmed": True}
        upload(page, [extra])
        assert page.locator("#progress").inner_text() == "reviewed 1 / 188"
        extra.update(
            review_confirmed=False,
            needs_any_ball_review=True,
            updated_at=page.evaluate("store.clock(state)"),
        )
        page.once("dialog", lambda d: d.accept())
        upload(page, [extra])
        assert page.locator("#progress").inner_text() == "reviewed 1 / 189"
        assert page.evaluate("reviewKeys.has(api.key(frames[188]))")
        assert (
            page.evaluate("reviewSuggestionMap[api.key(frames[188])].source")
            == "rf-r5-a"
        )


def test_provisional_cannot_be_bypassed():
    assert len(BASE_REVIEW_KEYS) == 188
    outside = ("not-a-queue-clip", 1.0)
    labels = {
        key: {"review_confirmed": True, "review_frame": True}
        for key in BASE_REVIEW_KEYS
    }
    missing = next(iter(BASE_REVIEW_KEYS))
    del labels[missing]
    labels[outside] = {"review_confirmed": True, "review_frame": True}
    meta = rule_metadata(labels, "any_ball")
    assert meta["provisional"] == "PROVISIONAL: 187 of 188 review frames confirmed"
    labels[missing] = {"review_confirmed": True}
    labels[outside] = {"needs_confirmation": True}
    meta = rule_metadata(labels, "any_ball")
    assert meta["provisional"] == "PROVISIONAL: 188 of 189 review frames confirmed"
    assert meta["pending_rows"] == 1
    labels[outside] = {"review_confirmed": True}
    assert rule_metadata(labels, "any_ball")["provisional"] is None
    assert confirmed(labels[outside])


def test_compare_exports_values_not_bytes(tmp_path):
    a = tmp_path / "old.jsonl"
    b = tmp_path / "new.jsonl"
    before = [
        {"clip": "test", "t": 1, "visible": True, "x": 1, "y": 2},
        {"clip": "test", "t": 2, "visible": False, "x": None, "y": None},
    ]
    a.write_text("\n".join(json.dumps(r) for r in before))
    b.write_text(
        "\n".join(
            json.dumps(dict(reversed(list(r.items()))), separators=(",", ":"))
            for r in reversed(before)
        )
    )
    assert compare(a, b)["unchanged"] == 2 and compare(a, b)["changed"] == []
    b.write_text(
        "\n".join(json.dumps(r) for r in [{**before[0], "x": 2}, {**before[1], "t": 3}])
    )
    result = compare(a, b)
    assert result["added"] == ["test|3.000000"] and result["removed"] == [
        "test|2.000000"
    ]
    assert result["changed"] == [{"key": "test|1.000000", "fields": ["x"]}]


def test_versioned_build_shared_frames_and_no_overwrite(tmp_path, monkeypatch):
    import ball_truth_kit
    import compare_ball
    import human_loop
    from common import DEFAULT_SOURCE

    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "frame.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    frames = [
        {
            "clip": "synthetic",
            "t": 1.0,
            "sample_index": 0,
            "source_size": [100, 100],
            "path": "frame.svg",
        }
    ]
    (shared / "frames.json").write_text(json.dumps(frames))
    (shared / "build.json").write_text(
        json.dumps(
            {"frozen_set_id": "test", "source": str(DEFAULT_SOURCE), "build_version": 8}
        )
    )
    before = {f.name: f.read_bytes() for f in shared.iterdir()}
    monkeypatch.setattr(
        compare_ball, "load_measurements", lambda: {"frozen_set_id": "test"}
    )
    monkeypatch.setattr(human_loop, "frame_catalog", lambda _: frames)
    monkeypatch.setattr(
        human_loop, "review_plan", lambda _: {"on_ball": [], "off_pitch": []}
    )
    out = tmp_path / "test-build12"
    ball_truth_kit.build(None, DEFAULT_SOURCE, out, frames_dir=shared)
    meta = json.loads((out / "build.json").read_text())
    assert meta["build_version"] == 12 and meta["shared_frames"] == "../shared"
    assert '"path": "../shared/frame.svg"' in (out / "index.html").read_text()
    assert meta["storage_key"].startswith("ball-human-v2:")
    assert meta["legacy_input_key"].startswith("ball-human-v1:")
    assert {f.name: f.read_bytes() for f in shared.iterdir()} == before
    assert {f.name for f in out.iterdir()} == {"index.html", "build.json"}
    with pytest.raises(ValueError, match="overwrite"):
        ball_truth_kit.build(None, DEFAULT_SOURCE, out, frames_dir=shared)
    with pytest.raises(ValueError, match="VERSIONED"):
        ball_truth_kit.build(None, DEFAULT_SOURCE, shared, frames_dir=shared)


@pytest.mark.parametrize(
    "change", ["coordinates", "visibility", "identity", "provenance"]
)
@pytest.mark.parametrize("age", ["stale", "equal", "newer"])
def test_same_confirmed_import_requires_approval_and_cancel_keeps_storage(
    browser, kit, change, age
):
    with browser.new_context() as context:
        page = open_page(context, kit)
        review(page)
        press(page, "Enter")
        original = current(page)
        incoming = {
            **original,
            "updated_at": original["updated_at"]
            + {"stale": -1, "equal": 0, "newer": 1}[age],
        }
        if change == "coordinates":
            incoming["x"] += 5
        elif change == "identity":
            incoming["match_ball"] = not original["match_ball"]
        elif change == "provenance":
            incoming["accepted_source"] = "different-source"
        else:
            incoming.update(
                visible=False, x=None, y=None, match_ball=None, source_accepted=False
            )
            incoming.pop("accepted_source")
            incoming.pop("accepted_score")
        before = page.evaluate("localStorage.getItem(storageKey)")
        messages = []

        def reject(dialog):
            messages.append(dialog.message)
            dialog.dismiss()

        page.once("dialog", reject)
        upload(page, [incoming])
        assert current(page) == original
        assert page.evaluate("localStorage.getItem(storageKey)") == before
        if age == "stale":
            assert messages == []
            assert (
                "skipped 1 rows older than what is saved here"
                in page.locator("#import-summary").inner_text()
            )
            upload(page, [incoming])
            assert (
                current(page) == original
                and page.evaluate("localStorage.getItem(storageKey)") == before
            )
        else:
            assert "would replace 1 confirmed decisions" in messages[0]
            assert "skipped 0 rows" in page.locator("#import-summary").inner_text()
            page.once("dialog", lambda d: d.accept())
            upload(page, [incoming])
            after = current(page)
            assert {k: v for k, v in after.items() if k != "updated_at"} == {
                k: v for k, v in incoming.items() if k != "updated_at"
            }
            assert after["updated_at"] > original["updated_at"]


def test_equal_timestamps_preserve_confirmation_and_show_conflict(browser, kit):
    with browser.new_context() as context:
        page = open_page(context, kit)
        review(page)
        press(page, "Enter")
        saved = current(page)
        # Same-millisecond pending edit in this tab must lose to confirmed storage.
        page.evaluate("""()=> {
            const key=api.key(frames[index]);
            state.labels[key]={...labels[key],review_confirmed:false,needs_any_ball_review:true};
            refreshStored();persist();show();
        }""")
        settle(page)
        assert current(page) == saved
        # Competing confirmed coordinates at the same timestamp keep stored values.
        page.evaluate("""()=> {
            const key=api.key(frames[index]);
            state.labels[key]={...labels[key],x:labels[key].x+10};
            refreshStored();persist();show();
        }""")
        settle(page)
        assert current(page) == saved
        assert "Merge conflicts: 1" in page.locator("#conflicts").inner_text()
        assert "already in storage" in page.locator("#conflicts").inner_text()
        fresh = open_page(context, kit)
        assert fresh.evaluate("labels[api.key(frames[0])]") == saved


def test_legacy_hash_warns_on_later_open_without_merging(browser, kit):
    with browser.new_context() as context:
        page = open_page(context, kit)
        before = page.evaluate("localStorage.getItem(storageKey)")
        baseline = page.evaluate("localStorage.getItem(legacyHashKey)")
        assert baseline.startswith("fnv1a64-v1:")
        legacy = {
            "clip": kit["rows"][0]["clip"],
            "t": 0,
            "x": 5,
            "y": 5,
            "visible": True,
        }
        page.evaluate(
            "([key,row])=>localStorage.setItem(key,JSON.stringify(row)+'\\n')",
            [kit["legacy"], legacy],
        )
        page.reload()
        settle(page)
        assert (
            page.locator("#legacy-message").inner_text()
            == "The old click page was used after this page started. Export from it and import here to include those labels."
        )
        assert page.evaluate("localStorage.getItem(storageKey)") == before
        assert page.evaluate("localStorage.getItem(legacyHashKey)") == baseline


def test_existing_build10_envelope_ignores_changed_seed_and_schema_stays_same(
    browser, kit
):
    with browser.new_context() as context:
        first = open_page(context, kit)
        review(first)
        press(first, "c")
        press(first, "ArrowRight")
        first.locator("#clear").click()
        settle(first)
        rows = first.evaluate("labels")
        raw = first.evaluate("localStorage.getItem(storageKey)")
        # Build 10 has this exact envelope format and no legacy-hash metadata.
        first.evaluate("localStorage.removeItem(legacyHashKey)")
        # Replace the fresh embedded seed entirely; it must not affect saved rows.
        content = kit["path"].read_text()
        start = content.index("seedRows=") + len("seedRows=")
        end = content.index(", storageKey=", start)
        kit["path"].write_text(content[:start] + "[]" + content[end:])
        second = open_page(context, kit)
        actual = second.evaluate("labels")
        assert len(rows.keys() - actual.keys()) == 0
        assert len(actual.keys() - rows.keys()) == 0
        assert sum(rows[k] != actual[k] for k in rows.keys() & actual.keys()) == 0
        assert second.evaluate("localStorage.getItem(storageKey)") == raw
        assert set(json.loads(raw)) == {"kind", "labels", "deleted"}
        assert "embedded seed is ignored" in second.locator("#seed-help").inner_text()
        assert "both steps are mandatory" in second.locator("#seed-help").inner_text()
