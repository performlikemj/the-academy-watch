"""Real preserved pages, import sequence, and plain-HTTP check; isolated storage."""

import argparse
import json
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from common import sha256
from compare_label_exports import compare


def settle(page):
    page.evaluate("writes")
    page.wait_for_function("initialized && imageReady")


def open_page(context, url):
    page = context.new_page()
    page.goto(url)
    settle(page)
    assert not page.evaluate("readOnly"), page.evaluate(
        "({url:location.href,secure:isSecureContext,safety:document.getElementById('safety').textContent})"
    )
    return page


def press(page, key):
    page.keyboard.press(key)
    settle(page)


def snapshot(page):
    return page.evaluate(
        "({labels,deleted:state.deleted,key:storageKey,raw:localStorage.getItem(storageKey)})"
    )


def compare_pages(before, new):
    expected, actual = before["labels"], new.evaluate("labels")
    result = {
        "rows": len(expected),
        "missing": len(expected.keys() - actual.keys()),
        "extra": len(actual.keys() - expected.keys()),
        "changed": sum(
            expected[k] != actual[k] for k in expected.keys() & actual.keys()
        ),
    }
    assert result["missing"] == result["extra"] == result["changed"] == 0
    assert before["key"] == new.evaluate("storageKey")
    assert before["raw"] == new.evaluate("localStorage.getItem(storageKey)")
    assert before["deleted"] == new.evaluate("state.deleted")
    result["byte_identical_storage"] = True
    return result


def upload(page, text):
    page.locator("#import").set_input_files(
        {
            "name": "legacy.jsonl",
            "mimeType": "application/x-ndjson",
            "buffer": text.encode(),
        }
    )
    page.wait_for_function(
        "document.getElementById('import').value==='' && document.getElementById('import-summary').textContent.startsWith('Import:')"
    )
    settle(page)


def fix_path(browser, base):
    with browser.new_context(accept_downloads=True) as ctx:
        old = ctx.new_page()
        old.goto(base + "/codex-runs/ball-truth-review-build8/index.html")
        old.wait_for_function("imageReady")
        old.locator("#canvas").click(position={"x": 150, "y": 90})
        page = open_page(ctx, base + "/ball-truth-review-build14/index.html")
        page.locator("#review").click()
        settle(page)
        page.locator("h1").click()
        for _ in range(3):
            press(page, "n")
            press(page, "ArrowRight")
        before = page.evaluate("labels")
        assert page.evaluate("Object.values(labels).filter(confirmed).length") == 3
        old.locator("h1").click()
        old.keyboard.press("ArrowRight")
        old.wait_for_function("imageReady")
        old.locator("#canvas").click(position={"x": 321, "y": 123})
        key = old.evaluate("api.key(frames[index])")
        page.wait_for_function("!document.getElementById('legacy-warning').hidden")
        with old.expect_download() as d:
            old.locator("#export").click()
        exported = Path(d.value.path()).read_text()
        messages = []

        def accept(d):
            messages.append(d.message)
            d.accept()

        page.on("dialog", accept)
        upload(page, exported)
        after = page.evaluate("labels")
        changed = [k for k in before if before[k] != after[k]]
        assert changed == [key]
        assert not messages
        assert page.evaluate("Object.values(labels).filter(confirmed).length") == 3
        summary = page.locator("#import-summary").inner_text()
        assert "0 new, 1 changed, 1053 unchanged" in summary
        assert "skipped 3 rows older than what is saved here" in summary
        assert page.locator("#legacy-warning").is_visible()
        page.locator("#dismiss-legacy").click()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        fresh = open_page(ctx, base + "/ball-truth-review-build14/index.html")
        assert fresh.locator("#legacy-warning").is_hidden()
        assert fresh.evaluate("labels") == after
        old.locator("#canvas").click(position={"x": 322, "y": 124})
        page.wait_for_function("!document.getElementById('legacy-warning').hidden")
        partial_rows = exported.splitlines()[:1]
        upload(page, "\n".join(partial_rows) + "\n")
        assert page.locator("#legacy-warning").is_visible()
        return {
            "new_clicks_applied": len(changed),
            "reviews_preserved": 3,
            "dialogs": len(messages),
            "summary": summary,
            "full_export_keeps_warning_until_dismiss": True,
            "dismiss_persists_across_reload_and_new_tab": True,
            "later_build8_click_warns_again": True,
            "partial_export_keeps_warning": True,
        }


def select_frame(page, key):
    page.evaluate("key=>{index=frames.findIndex(f=>api.key(f)===key);show()}", key)
    page.wait_for_function("imageReady")


def old_start(ctx, base):
    old = ctx.new_page()
    old.goto(base + "/codex-runs/ball-truth-review-build8/index.html")
    old.wait_for_function("imageReady")
    old.locator("#canvas").click(position={"x": 150, "y": 90})
    page = open_page(ctx, base + "/ball-truth-review-build14/index.html")
    page.on("dialog", lambda d: d.accept())
    return old, page


def download_text(page):
    with page.expect_download() as d:
        page.locator("#export").click()
    return Path(d.value.path()).read_text()


def h1(browser, base):
    with browser.new_context(accept_downloads=True) as ctx:
        old, page = old_start(ctx, base)
        raw_base = page.evaluate("localStorage.getItem(legacyHashKey)")
        baseline = json.loads(raw_base)
        sizes = {
            "raw_utf8_bytes": len(baseline["raw"].encode()),
            "baseline_utf8_bytes": len(raw_base.encode()),
            "baseline_utf16_bytes": len(raw_base.encode("utf-16-le")),
        }
        page.locator("#review").click()
        settle(page)
        common = set(old.evaluate("frames.map(api.key)"))
        key = next(k for k in page.evaluate("reviewQueue.map(api.key)") if k in common)
        select_frame(page, key)
        page.locator("h1").click()
        press(page, "n")
        mine = page.evaluate("key=>labels[key]", key)
        select_frame(old, key)
        old.locator("#canvas").click(position={"x": 400, "y": 300})
        page.wait_for_function("!document.getElementById('legacy-warning').hidden")
        upload(page, download_text(old))
        assert page.locator("#legacy-warning").is_visible()
        assert page.evaluate("key=>labels[key]", key) == mine
        page.locator("#legacy-keys a").filter(has_text=key).click()
        settle(page)
        assert page.locator("#legacy-use, #legacy-keep, #legacy-all").count() == 0
        raw = page.evaluate("localStorage.getItem(storageKey)")
        page.locator("#dismiss-legacy").click()
        settle(page)
        assert page.evaluate("localStorage.getItem(storageKey)") == raw
        assert page.evaluate("key=>labels[key]", key) == mine
        assert page.locator("#legacy-warning").is_hidden()
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        fresh = open_page(ctx, base + "/ball-truth-review-build14/index.html")
        assert fresh.locator("#legacy-warning").is_hidden()
        old.locator("#canvas").click(position={"x": 401, "y": 301})
        page.wait_for_function("!document.getElementById('legacy-warning').hidden")
        return {
            "skipped_import_keeps_warning": True,
            "dismiss_keeps_review_unchanged": True,
            "dismissed_across_reload_and_tab": True,
            "later_edit_flags_again": True,
            "baseline_size": sizes,
        }


def old_clear_case(browser, base, which):
    with browser.new_context(accept_downloads=True) as ctx:
        old, page = old_start(ctx, base)
        key = old.evaluate("api.key(Object.values(labels).find(r=>r.visible))")
        earlier = download_text(old)
        select_frame(old, key)
        old.locator("#clear").click()
        page.wait_for_function("!document.getElementById('legacy-warning').hidden")
        text = (
            download_text(old)
            if which == "current"
            else earlier
            if which == "pre_clear"
            else download_text(page)
        )
        upload(page, text)
        assert page.locator("#legacy-warning").is_visible()
        assert page.evaluate("key=>!!labels[key]", key)
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_visible()
        page.locator("#legacy-keys a").filter(has_text=key).click()
        settle(page)
        assert "Old page: cleared" in page.locator("#legacy-values").inner_text()
        raw = page.evaluate("localStorage.getItem(storageKey)")
        page.locator("#dismiss-legacy").click()
        settle(page)
        assert page.evaluate("localStorage.getItem(storageKey)") == raw
        assert page.evaluate("key=>!!labels[key]", key)
        assert page.locator("#legacy-warning").is_hidden()
        return {
            "file": which,
            "import_and_reload_preserve_warning": True,
            "dismiss_keeps_local_label": True,
        }


def recovery_salvage(browser):
    import tempfile
    from test_kit_safety import kit as synthetic_kit

    results = {}
    with tempfile.TemporaryDirectory(prefix="ball-build14-recovery-") as folder:
        kit = synthetic_kit.__wrapped__(Path(folder))
        for which in ("own_backup", "older_jsonl", "unparseable"):
            with browser.new_context(accept_downloads=True) as ctx:
                page = open_page(ctx, kit["path"].as_uri())
                older = download_text(page)
                page.evaluate("""()=>{
                  const newer=api.key(frames[187]),clear=api.key(frames[188]);
                  state.labels[newer]={...labels[newer],updated_at:100};
                  delete state.labels[clear];state.deleted[clear]=100;persist();
                  const raw=JSON.parse(localStorage.getItem(storageKey));
                  raw.labels.find(r=>r.t===0).match_ball='bad';
                  localStorage.setItem(storageKey,JSON.stringify(raw));
                }""")
                if which == "unparseable":
                    page.evaluate("localStorage.setItem(storageKey,'{broken')")
                page.reload()
                settle(page)
                assert page.evaluate("readOnly")
                expected = page.evaluate("state")
                assert len(expected["labels"]) == (0 if which == "unparseable" else 187)
                backup = download_text(page)
                messages = []
                page.on("dialog", lambda d: (messages.append(d.message), d.accept()))
                upload(page, older if which == "older_jsonl" else backup)
                assert not page.evaluate("readOnly")
                actual = page.evaluate("state")
                if which != "older_jsonl":
                    assert actual == expected
                else:
                    assert actual["deleted"] == expected["deleted"]
                    key = page.evaluate("api.key(frames[187])")
                    assert actual["labels"][key] == expected["labels"][key]
                    assert (
                        "skipped 2 rows older"
                        in page.locator("#import-summary").inner_text()
                    )
                if which == "unparseable":
                    assert (
                        "not parseable JSON" in messages[0]
                        and "nothing could be salvaged" in messages[0]
                    )
                fresh = open_page(ctx, kit["path"].as_uri())
                assert fresh.evaluate("state") == actual
                results[which] = {
                    "salvaged_labels": len(expected["labels"]),
                    "salvaged_clears": len(expected["deleted"]),
                    "recovered_labels": len(actual["labels"]),
                    "recovered_clears": len(actual["deleted"]),
                    "fresh_tab_identical": True,
                    "confirmation": messages,
                }
    return results


def first_open(browser, base):
    original = Path.home() / "codex-runs/ball-human-truth.jsonl"
    with browser.new_context(accept_downloads=True) as ctx:
        page = ctx.new_page()
        page.goto(base + "/ball-truth-review-build14/index.html")
        settle(page)
        page.evaluate(
            "raw=>{localStorage.clear();localStorage.setItem(legacyKey,raw)}",
            original.read_text(),
        )
        page.reload()
        settle(page)
        assert not page.evaluate("readOnly")
        assert page.locator("#legacy-warning").is_hidden()
        assert page.evaluate("Object.keys(labels).length") == 1057
        assert page.evaluate("reviewQueue.length") == 188
        with page.expect_download() as d:
            page.locator("#export").click()
        result = compare(original, Path(d.value.path()))
        assert result["verdict"] == "same"
        return {
            "labels": 1057,
            "queue": 188,
            "read_only": False,
            "banner": False,
            "export_compare": result["counts"],
        }


def navigation_timings(browser, base):
    original = (Path.home() / "codex-runs/ball-human-truth.jsonl").read_text()
    result = {}
    for version in (12, 13, 14):
        with browser.new_context() as ctx:
            page = open_page(
                ctx, base + f"/ball-truth-review-build{version}/index.html"
            )
            page.evaluate(
                "raw=>{localStorage.clear();localStorage.setItem(legacyKey,raw)}",
                original,
            )
            page.reload()
            settle(page)
            samples = {}
            for pending in (False, True):
                if pending:
                    page.evaluate(
                        """()=>{const rows=localStorage.getItem(legacyKey).trim().split('\\n').map(JSON.parse);const r=rows.find(r=>r.visible);r.x+=1;localStorage.setItem(legacyKey,rows.map(JSON.stringify).join('\\n')+'\\n')}"""
                    )
                    page.reload()
                    settle(page)
                    assert page.locator("#legacy-warning").is_visible()
                sample = page.evaluate("""()=>{
                  reviewMode=false;index=0;
                  const median=fn=>{const values=[];for(let i=0;i<36;i++){const t=performance.now();fn();if(i>=5)values.push(performance.now()-t)}values.sort((a,b)=>a-b);return values[Math.floor(values.length/2)]};
                  return {show_ms:median(()=>show()),arrow_ms:median(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'})))};
                }""")
                if version == 14:
                    assert sample["show_ms"] <= 2 and sample["arrow_ms"] <= 2, sample
                samples["pending" if pending else "no_pending"] = sample
            result[str(version)] = samples
    return result


class LocalOriginBrowser:
    """Keep old build 11 on its supported localhost origin, using one LAN listener."""

    def __init__(self, browser, local, lan):
        self.browser, self.local, self.lan = browser, local, lan

    def new_context(self, **kwargs):
        context = self.browser.new_context(**kwargs)

        def forward(route):
            from playwright.sync_api import Error

            try:
                response = route.fetch(
                    url=route.request.url.replace(self.local, self.lan, 1)
                )
                route.fulfill(response=response)
            except Error as error:
                # Navigation timings deliberately create superseded image loads.
                # Closing their isolated context can dispose a request in flight.
                if "disposed" not in str(error) and "closed" not in str(error):
                    raise

        context.route(self.local + "/**", forward)
        return context

    def close(self):
        self.browser.close()


def check(out):
    from playwright.sync_api import sync_playwright

    home = Path.home()
    # Bind only the LAN address; do not expose this server on the tailnet.
    address = subprocess.check_output(
        ["ipconfig", "getifaddr", "en0"], text=True
    ).strip()
    assert address and not address.startswith("127.")

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if not self.path.startswith(
                (
                    "/ball-truth-review/",
                    "/ball-truth-review-build10/",
                    "/ball-truth-review-build11/",
                    "/ball-truth-review-build12/",
                    "/ball-truth-review-build13/",
                    "/ball-truth-review-build14/",
                    "/codex-runs/ball-truth-review-build8/",
                )
            ):
                self.send_error(404)
                return
            if self.path.startswith(
                "/codex-runs/ball-truth-review-build8/"
            ) and self.path.endswith(".jpg"):
                self.path = self.path.replace(
                    "/codex-runs/ball-truth-review-build8/", "/ball-truth-review/", 1
                )
            super().do_GET()

    server = ThreadingHTTPServer((address, 0), partial(Handler, directory=str(home)))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    lan = f"http://{address}:{server.server_port}"
    base = f"http://localhost:{server.server_port}"
    audit = {}
    try:
        with sync_playwright() as pw:
            bins = sorted(
                (home / "Library/Caches/ms-playwright").glob(
                    "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
                )
            )
            browser = LocalOriginBrowser(
                pw.chromium.launch(
                    executable_path=str(bins[-1]) if bins else None,
                ),
                base,
                lan,
            )
            for version in (10, 11, 12, 13):
                with browser.new_context() as ctx:
                    old = open_page(
                        ctx, base + f"/ball-truth-review-build{version}/index.html"
                    )
                    before = snapshot(old)
                    new = open_page(ctx, base + "/ball-truth-review-build14/index.html")
                    initial = compare_pages(before, new)
                    new.close()
                    old.locator("#review").click()
                    settle(old)
                    old.locator("h1").click()
                    for key in (
                        "Enter",
                        "ArrowRight",
                        "n",
                        "ArrowRight",
                        "c",
                        "ArrowRight",
                    ):
                        press(old, key)
                    old.locator("#clear").click()
                    settle(old)
                    before = snapshot(old)
                    new = open_page(ctx, base + "/ball-truth-review-build14/index.html")
                    audit[f"build{version}_to_build14"] = {
                        "initial": initial,
                        "edited": compare_pages(before, new),
                    }
            with browser.new_context(accept_downloads=True) as ctx:
                page = open_page(ctx, base + "/ball-truth-review-build14/index.html")
                with page.expect_download() as d:
                    page.locator("#export").click()
                exported = Path(d.value.path())
                result = compare(
                    home / "codex-runs/ball-human-truth-v2-build14.jsonl", exported
                )
                assert result["verdict"] == "same"
                audit["zero_edit_export_vs_seed"] = result["counts"]
            audit["real_build8_import"] = fix_path(browser, base)
            audit["H1"] = h1(browser, base)
            for name, which in [
                ("H2a", "current"),
                ("H2b", "pre_clear"),
                ("H3", "own"),
            ]:
                audit[name] = old_clear_case(browser, base, which)
            audit["recovery_salvage"] = recovery_salvage(browser)
            audit["real_first_open"] = first_open(browser, base)
            audit["navigation_medians"] = navigation_timings(browser, base)
            browser.close()
            # Protected build 11 needs a secure context; only compatibility used
            # the localhost forwarding route. Verify plain HTTP in a separate browser.
            browser = pw.chromium.launch(
                executable_path=str(bins[-1]) if bins else None
            )
            with browser.new_context() as ctx:
                url = f"http://{address}:{server.server_port}/ball-truth-review-build14/index.html"
                page = open_page(ctx, url)
                flags = page.evaluate(
                    "({secure:isSecureContext,subtle:!!crypto.subtle,readOnly})"
                )
                assert flags == {"secure": False, "subtle": False, "readOnly": False}
                page.locator("h1").click()
                press(page, "n")
                assert page.evaluate("labels[api.key(frames[index])].updated_at>0")
                audit["non_loopback_http"] = {
                    "address": address,
                    **flags,
                    "edit_saved": True,
                }
            browser.close()
        audit["compatibility_origin"] = (
            "localhost, forwarded to the LAN-only listener; protected build 11 requires a secure origin"
        )
        audit["page_sha256"] = {
            str(v): sha256(home / f"ball-truth-review-build{v}/index.html")
            for v in (10, 11, 12, 13, 14)
        }
        out.write_text(json.dumps(audit, indent=2) + "\n")
        print(json.dumps(audit, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=Path.home() / "codex-runs/ball-build14-compatibility.json",
    )
    check(p.parse_args().out)
