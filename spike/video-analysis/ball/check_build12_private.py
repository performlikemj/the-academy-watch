"""Real preserved pages, import sequence, and plain-HTTP check; isolated storage."""

from output_guard import guard_outputs
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
    assert not page.evaluate("readOnly")
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
        page = open_page(ctx, base + "/ball-truth-review-build12/index.html")
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
        assert page.locator("#legacy-warning").is_hidden()
        page.reload()
        settle(page)
        assert page.locator("#legacy-warning").is_hidden()
        fresh = open_page(ctx, base + "/ball-truth-review-build12/index.html")
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
            "full_export_hides_warning_across_reload_and_new_tab": True,
            "later_build8_click_warns_again": True,
            "partial_export_keeps_warning": True,
        }


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
    base = f"http://{address}:{server.server_port}"
    audit = {}
    try:
        with sync_playwright() as pw:
            bins = sorted(
                (home / "Library/Caches/ms-playwright").glob(
                    "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
                )
            )
            browser = pw.chromium.launch(
                executable_path=str(bins[-1]) if bins else None
            )
            for version in (10, 11):
                with browser.new_context() as ctx:
                    old = open_page(
                        ctx, base + f"/ball-truth-review-build{version}/index.html"
                    )
                    before = snapshot(old)
                    new = open_page(ctx, base + "/ball-truth-review-build12/index.html")
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
                    new = open_page(ctx, base + "/ball-truth-review-build12/index.html")
                    audit[f"build{version}_to_build12"] = {
                        "initial": initial,
                        "edited": compare_pages(before, new),
                    }
            with browser.new_context(accept_downloads=True) as ctx:
                page = open_page(ctx, base + "/ball-truth-review-build12/index.html")
                with page.expect_download() as d:
                    page.locator("#export").click()
                exported = Path(d.value.path())
                result = compare(
                    home / "codex-runs/ball-human-truth-v2-build12.jsonl", exported
                )
                assert result["verdict"] == "same"
                audit["zero_edit_export_vs_seed"] = result["counts"]
            audit["real_build8_import"] = fix_path(browser, base)
            with browser.new_context() as ctx:
                url = f"http://{address}:{server.server_port}/ball-truth-review-build12/index.html"
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
        audit["page_sha256"] = {
            str(v): sha256(home / f"ball-truth-review-build{v}/index.html")
            for v in (10, 11, 12)
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
        default=Path.home() / "codex-runs/ball-build12-compatibility.json",
    )
    a = p.parse_args()
    # Guard audit destinations before launching browsers or a local server.
    guard_outputs(a.out, parser=p)
    check(a.out)
