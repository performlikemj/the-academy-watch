"""Check round-two labels/suggestions in an isolated browser, never MJ's profile."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from ball_truth_kit import import_labels
from human_loop import frame_catalog
from compare_ball import load_measurements


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kit", type=Path, default=Path.home() / "ball-truth-review")
    p.add_argument("--human-jsonl", type=Path, required=True)
    p.add_argument("--screenshot", type=Path, required=True)
    a = p.parse_args()
    labels = import_labels(a.human_jsonl, frame_catalog(load_measurements()))
    with sync_playwright() as playwright:
        browsers = sorted(
            (Path.home() / "Library/Caches/ms-playwright").glob(
                "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
            )
        )
        browser = playwright.chromium.launch(
            executable_path=str(browsers[-1]) if browsers else None
        )
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((a.kit / "index.html").as_uri())
        page.wait_for_function("imageReady")
        assert page.evaluate("Object.keys(labels).length") == len(labels)
        assert "1057 / 1105 (48 remaining)" in page.locator("#progress").inner_text()
        assert (
            page.evaluate("localStorage.length") == 0
        )  # Viewing never saves anything.
        imported = page.evaluate("Object.values(labels)")
        assert {(r["clip"], r["t"]): r for r in imported} == labels
        page.locator("#unlabelled").click()
        page.wait_for_function("imageReady")
        assert page.evaluate("!labels[api.key(frames[index])]")
        page.screenshot(path=str(a.screenshot), full_page=True)
        # Simulate a newer browser label and verify that the seed does not replace it.
        page.locator("#none").click()
        key = page.evaluate("api.key(frames[index])")
        assert page.evaluate("Object.keys(labels).length") == len(labels) + 1
        page.reload()
        page.wait_for_function("imageReady")
        assert page.evaluate("(k)=>labels[k].visible", key) is False
        assert page.evaluate("Object.keys(labels).length") == len(labels) + 1
        # Clearing an original seeded label must survive reload, too.
        original = page.evaluate("api.key(frames[index])")
        assert page.evaluate("(k)=>!!labels[k]", original)
        page.locator("#clear").click()
        page.reload()
        page.wait_for_function("imageReady")
        assert page.evaluate("(k)=>!!labels[k]", original) is False
        assert not errors, errors
        browser.close()
    print(
        f"PASS: {len(labels)} exact seeded labels, no auto-save, all-frame navigation and newer browser labels preserved"
    )


if __name__ == "__main__":
    main()
