"""Prove real build-10 storage survives build 11 in isolated Chromium storage."""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from common import sha256


def check(out):
    from playwright.sync_api import sync_playwright

    home = Path.home()

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith(
                "/codex-runs/ball-truth-review-build8/"
            ) and self.path.endswith(".jpg"):
                self.path = self.path.replace(
                    "/codex-runs/ball-truth-review-build8/", "/ball-truth-review/", 1
                )
            super().do_GET()

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(home))
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
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
            with browser.new_context() as context:
                old = context.new_page()
                old.goto(base + "/ball-truth-review-build10/index.html")
                old.wait_for_function("initialized && imageReady")
                old.locator("#review").click()
                old.wait_for_function("imageReady")
                old.locator("h1").click()
                for key in ("Enter", "ArrowRight", "n"):
                    old.keyboard.press(key)
                    old.evaluate("writes")
                    old.wait_for_function("imageReady")
                old.evaluate(
                    "index=frames.findIndex(f=>f.clip==='m04-n21-t3011-390297-390800'&&f.sample_index===1);show()"
                )
                old.wait_for_function("imageReady")
                old.keyboard.press("c")
                old.evaluate("writes")
                old.wait_for_function("imageReady")
                old.keyboard.press("ArrowRight")
                old.wait_for_function("imageReady")
                old.locator("#clear").click()
                old.evaluate("writes")
                old.wait_for_function("imageReady")
                expected = old.evaluate("labels")
                raw = old.evaluate("localStorage.getItem(storageKey)")
                assert len(json.loads(raw)["deleted"]) == 1
                assert (
                    old.evaluate("Object.values(labels).filter(confirmed).length") == 3
                )
                new = context.new_page()
                new.goto(base + "/ball-truth-review-build11/index.html")
                new.wait_for_function("initialized && imageReady")
                actual = new.evaluate("labels")
                audit = {
                    "build10_page_sha256": sha256(
                        home / "ball-truth-review-build10/index.html"
                    ),
                    "build11_page_sha256": sha256(
                        home / "ball-truth-review-build11/index.html"
                    ),
                    "rows_compared": len(expected),
                    "missing": len(expected.keys() - actual.keys()),
                    "extra": len(actual.keys() - expected.keys()),
                    "changed": sum(
                        expected[k] != actual[k]
                        for k in expected.keys() & actual.keys()
                    ),
                    "confirmed_decisions": 3,
                    "clear_records": 1,
                }
                assert audit["missing"] == audit["extra"] == audit["changed"] == 0
                assert new.evaluate("storageKey") == old.evaluate("storageKey")
                assert new.evaluate("localStorage.getItem(storageKey)") == raw
                assert new.evaluate("state.deleted") == old.evaluate("state.deleted")
                audit["same_key_and_byte_identical_v2_storage"] = True
                # Use the preserved build-8 JS itself to produce a later v1 edit.
                legacy = context.new_page()
                legacy.goto(base + "/codex-runs/ball-truth-review-build8/index.html")
                legacy.wait_for_function("imageReady")
                legacy.locator("h1").click()
                legacy.keyboard.press("n")
                legacy.wait_for_function("imageReady")
                new.reload()
                new.wait_for_function("initialized && imageReady")
                assert new.locator("#legacy-warning").inner_text() == (
                    "The old click page was used after this page started. "
                    "Export from it and import here to include those labels."
                )
                assert new.evaluate("localStorage.getItem(storageKey)") == raw
                audit["actual_build8_edit_warns_on_reopen_without_merging"] = True
            browser.close()
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
        default=Path.home() / "codex-runs/ball-build11-build10-compatibility.json",
    )
    check(p.parse_args().out)
