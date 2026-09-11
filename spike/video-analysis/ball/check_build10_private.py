"""Use the preserved real build-8 page and private labels in an isolated browser."""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from ball_truth_kit import import_labels
from common import sha256
from compare_ball import load_measurements
from human_loop import frame_catalog


def check(out):
    from playwright.sync_api import sync_playwright

    home = Path.home()
    original = home / "codex-runs/ball-human-truth.jsonl"
    previous = home / "codex-runs/ball-truth-review-build8/index.html"
    expected = import_labels(original, frame_catalog(load_measurements()))
    expected = {f"{cid}|{t:.6f}": row for (cid, t), row in expected.items()}

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
                old.goto(base + "/codex-runs/ball-truth-review-build8/index.html")
                old.wait_for_function("imageReady")
                old.evaluate(
                    "raw=>localStorage.setItem(storageKey,raw)", original.read_text()
                )
                old.reload()
                old.wait_for_function("imageReady")
                before = old.evaluate("localStorage.getItem(storageKey)")
                new = context.new_page()
                new.goto(base + "/ball-truth-review-build10/index.html")
                new.evaluate("writes")
                new.wait_for_function("initialized && imageReady")
                actual = new.evaluate("labels")
                audit = {
                    "build8_page_sha256": sha256(previous),
                    "original_labels_sha256": sha256(original),
                    "missing": len(expected.keys() - actual.keys()),
                    "extra": len(actual.keys() - expected.keys()),
                    "changed": sum(
                        expected[k] != actual[k]
                        for k in expected.keys() & actual.keys()
                    ),
                }
                assert audit["missing"] == audit["extra"] == audit["changed"] == 0
                assert old.evaluate("localStorage.getItem(storageKey)") == before
                new.locator("#review").click()
                new.wait_for_function("imageReady")
                new.locator("h1").click()
                new.keyboard.press("Enter")
                new.evaluate("writes")
                new.wait_for_function("imageReady")
                new.evaluate(
                    "index=frames.findIndex(f=>f.clip==='m04-n21-t3011-390297-390800'&&f.sample_index===1);show()"
                )
                new.wait_for_function("imageReady")
                row = new.evaluate("labels[api.key(frames[index])]")
                new.keyboard.press("c")
                new.evaluate("writes")
                new.wait_for_function("imageReady")
                after = new.evaluate("labels[api.key(frames[index])]")
                assert all(
                    row[k] == after[k]
                    for k in (
                        "x",
                        "y",
                        "source_accepted",
                        "accepted_source",
                        "accepted_score",
                    )
                )
                assert after["review_confirmed"] and after["match_ball"] is False
                # The actual verified build-8 JS handles N and rewrites its key.
                old.locator("h1").click()
                old.keyboard.press("n")
                old.wait_for_function("imageReady")
                fresh = context.new_page()
                fresh.goto(base + "/ball-truth-review-build10/index.html")
                fresh.evaluate("writes")
                fresh.wait_for_function("initialized && imageReady")
                count = fresh.evaluate("Object.values(labels).filter(confirmed).length")
                assert count == 2
                audit.update(
                    build8_N_preserved_v2_reviews=count,
                    C_preserved_n21_s1_provenance_and_point=True,
                    legacy_key_untouched_by_build10=True,
                )
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
        default=Path.home() / "codex-runs/ball-build10-real-build8-check.json",
    )
    check(p.parse_args().out)
