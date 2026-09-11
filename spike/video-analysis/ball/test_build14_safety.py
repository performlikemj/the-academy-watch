"""Build-14 regression tests, using synthetic data only."""

import gzip
import inspect
import json
import sys

import pytest

import ball_truth_kit
import review_round5
from test_kit_safety import browser as browser, kit as kit, open_page, settle, upload
from test_build13_safety import bootstrap, legacy_set, export, import_text


@pytest.mark.parametrize("backup", [True, False])
def test_corrupt_open_salvages_rows_and_clears(browser, kit, backup):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        older = export(page)
        page.evaluate(
            """()=>{const k=api.key(frames[188]);state.labels[k]={...labels[k],x:77,updated_at:100};delete state.labels[api.key(frames[1])];state.deleted[api.key(frames[1])]=100;persist();const v=JSON.parse(localStorage.getItem(storageKey));v.labels.find(r=>r.t===0).match_ball='bad';localStorage.setItem(storageKey,JSON.stringify(v));}"""
        )
        page.reload()
        settle(page)
        assert page.evaluate("readOnly")
        assert page.evaluate("Object.keys(labels).length") == 187
        assert page.locator("#safety").inner_text().find("test-0|0.000000") >= 0
        expected = page.evaluate("state")
        recovery = export(page)
        assert len(json.loads(recovery)["validated_labels"]) == 187
        page.once("dialog", lambda d: d.accept())
        import_text(page, recovery if backup else older)
        assert not page.evaluate("readOnly")
        assert page.evaluate("labels[api.key(frames[188])].x") == 77
        assert page.evaluate("state.deleted[api.key(frames[1])]") == 100
        assert page.evaluate("!labels[api.key(frames[1])]")
        if backup:
            assert page.evaluate("state") == expected
        assert open_page(ctx, kit).evaluate("state") == page.evaluate("state")


def test_unparseable_recovery_requires_explicit_loss_notice(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        page.evaluate("localStorage.setItem(storageKey,'{broken')")
        page.reload()
        settle(page)
        raw = page.evaluate("localStorage.getItem(storageKey)")
        backup = export(page)
        messages = []
        page.once("dialog", lambda d: (messages.append(d.message), d.dismiss()))
        import_text(page, backup)
        assert "not parseable JSON" in messages[0]
        assert "nothing could be salvaged" in messages[0]
        assert page.evaluate("localStorage.getItem(storageKey)") == raw
        assert page.evaluate("readOnly")


def test_legacy_notice_dismiss_only_and_cross_tab(browser, kit):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        rows[0].update(x=333, y=222)
        legacy_set(page, rows)
        upload(page, rows)
        assert page.locator("#legacy-warning").is_visible()
        assert "this page matches" in page.locator("#legacy-keys").inner_text()
        assert page.locator("#legacy-use, #legacy-keep, #legacy-all").count() == 0
        page.evaluate("index=0;show()")
        settle(page)
        page.locator("#none").click()
        settle(page)
        assert "this page differs" in page.locator("#legacy-keys").inner_text()
        peer = open_page(ctx, kit)
        raw = page.evaluate("localStorage.getItem(storageKey)")
        messages = []
        page.once("dialog", lambda d: (messages.append(d.message), d.dismiss()))
        page.locator("#dismiss-legacy").click()
        settle(page)
        assert "1 old-page changes, 1 don't match this page" in messages[0]
        assert page.locator("#legacy-warning").is_visible()
        page.once("dialog", lambda d: d.accept())
        page.locator("#dismiss-legacy").click()
        settle(page)
        peer.wait_for_function("document.getElementById('legacy-warning').hidden")
        assert page.evaluate("localStorage.getItem(storageKey)") == raw
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        rows[0]["x"] += 1
        legacy_set(page, rows)
        assert page.locator("#legacy-warning").is_visible()


def test_navigation_never_parses_storage_and_save_parses_once(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        page.evaluate(
            "window.parses=0;window.checks=0;const origParse=store.parse;store.parse=(...a)=>{parses++;return origParse(...a)};const origCheck=legacy.check;legacy.check=(...a)=>{checks++;return origCheck(...a)}"
        )
        assert page.evaluate(
            "()=>{parses=checks=0;show();move(1);move(-1);return [parses,checks]}"
        ) == [0, 0]
        settle(page)
        page.evaluate("parses=checks=0")
        page.locator("#none").click()
        settle(page)
        assert page.evaluate("[parses,checks]") == [1, 0]


@pytest.mark.parametrize("explicit", [True, False])
def test_freeze_rejects_other_labels_before_capture(tmp_path, monkeypatch, explicit):
    fixture = tmp_path / "fixtures/round5_scored_output.json.gz"
    fixture.parent.mkdir()
    original = gzip.compress(json.dumps({"labels_sha256": "a" * 64}).encode())
    fixture.write_bytes(original)
    labels = tmp_path / "codex-runs/ball-human-truth.jsonl"
    labels.parent.mkdir()
    labels.write_text("custom labels\n")
    monkeypatch.setattr(review_round5, "HERE", tmp_path)
    monkeypatch.setattr(review_round5.Path, "home", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(
        review_round5,
        "capture",
        lambda *a, **kw: calls.append(kw) or {"provisional": None, "models": {}},
    )
    args = ["review_round5", "--freeze", "--out", str(tmp_path / "result.json")]
    if explicit:
        args += ["--human-jsonl", str(labels)]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as error:
        review_round5.main()
    assert error.value.code == 2
    assert not calls
    assert fixture.read_bytes() == original


def test_builder_does_not_offer_unsupported_manifest():
    # load_measurements takes a gzip measurement artifact, not a manifest.
    assert "manifest" not in inspect.signature(ball_truth_kit.build).parameters
    source = inspect.getsource(ball_truth_kit)
    assert 'add_argument("--manifest"' not in source


def test_preserves_build13_metadata_and_ghost_never_writes(browser, kit):
    with browser.new_context() as ctx:
        page, rows = bootstrap(ctx, kit)
        baseline = page.evaluate("localStorage.getItem(legacyHashKey)")
        data = json.loads(baseline)
        key = page.evaluate("api.key(frames[0])")
        # A build-13 Keep record must survive, but must not suppress this notice.
        rows[0].update(x=555, y=444)
        data["kept"] = {key: {k: rows[0][k] for k in ("visible", "x", "y")}}
        prior = json.dumps(data)
        page.evaluate(
            "raw=>{localStorage.setItem(storageKey+':legacy-baseline-v1',raw);localStorage.removeItem(legacyHashKey)}",
            prior,
        )
        legacy_set(page, rows)
        assert page.locator("#legacy-warning").is_visible()
        before = page.evaluate("localStorage.getItem(storageKey)")
        page.evaluate(
            "window.ghosts=[];const originalArc=ctx.arc.bind(ctx);ctx.arc=(...a)=>{if(ctx.getLineDash().length)ghosts.push(a);originalArc(...a)};index=0;show()"
        )
        settle(page)
        assert page.evaluate("ghosts.some(a=>a[0]===555&&a[1]===444)")
        assert page.evaluate("localStorage.getItem(storageKey)") == before
        page.once("dialog", lambda d: d.accept())
        page.locator("#dismiss-legacy").click()
        settle(page)
        assert (
            page.evaluate("localStorage.getItem(storageKey+':legacy-baseline-v1')")
            == prior
        )
        # Own edits after dismissal cannot reopen or blame the old page.
        page.locator("#none").click()
        settle(page)
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()


def test_salvage_rejects_bad_clear_and_duplicates_independently(browser, kit):
    with browser.new_context() as ctx:
        page = open_page(ctx, kit)
        actual = page.evaluate(
            """()=>{const v=JSON.parse(localStorage.getItem(storageKey));v.labels.push(v.labels[0]);v.deleted[api.key(frames[188])]=42;v.deleted[api.key(frames[187])]='bad';v.deleted['unknown|0.000000']=123;return store.salvage(JSON.stringify(v),frames)}"""
        )
        assert len(actual["state"]["labels"]) == 187
        assert len(actual["state"]["deleted"]) == 1
        assert len(actual["unreadable"]) == 3
        assert any(r["reason"] == "Duplicate label key" for r in actual["unreadable"])


@pytest.mark.parametrize("drift", [False, True])
def test_freeze_accepts_only_actual_historical_identity(tmp_path, monkeypatch, drift):
    labels = tmp_path / "original.jsonl"
    labels.write_text("synthetic\n")
    identity = review_round5.sha256(labels)
    fixture = tmp_path / "fixtures/round5_scored_output.json.gz"
    fixture.parent.mkdir()
    original = gzip.compress(
        json.dumps({"labels_sha256": identity, "models": {}}).encode()
    )
    fixture.write_bytes(original)
    monkeypatch.setattr(review_round5, "HERE", tmp_path)
    monkeypatch.setattr(review_round5, "FINAL_PASSES", {})

    def capture(*args, **kwargs):
        assert kwargs["label_path"] == labels
        if drift:
            labels.write_text("changed mid-capture\n")
        return {"labels_sha256": identity, "provisional": None, "models": {}}

    monkeypatch.setattr(review_round5, "capture", capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "review",
            "--freeze",
            "--human-jsonl",
            str(labels),
            "--out",
            str(tmp_path / "out.json"),
        ],
    )
    if drift:
        with pytest.raises(SystemExit) as error:
            review_round5.main()
        assert error.value.code == 2
        assert fixture.read_bytes() == original
    else:
        review_round5.main()
        assert fixture.read_bytes() == original
        assert (
            json.loads(gzip.decompress((tmp_path / "out.json").read_bytes()))[
                "labels_sha256"
            ]
            == identity
        )


def test_manifest_cli_refuses_before_build(tmp_path):
    import subprocess

    manifest = tmp_path / "other-manifest.json"
    manifest.write_text('{"clips": []}')
    result = subprocess.run(
        [
            sys.executable,
            ball_truth_kit.__file__,
            "--manifest",
            str(manifest),
            "--out",
            str(tmp_path / "test-build14"),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --manifest" in result.stderr
    assert not (tmp_path / "test-build14").exists()
