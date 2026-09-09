"""Real Chromium kit check in an isolated browser context, never MJ's storage."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kit", type=Path, default=Path.home() / "ball-truth-review")
    p.add_argument("--screenshot", type=Path, required=True)
    a = p.parse_args()
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
        assert page.evaluate("localStorage.length") == 0
        assert (
            page.locator("#progress").inner_text()
            == "labelled 0 / 640 target (540 on-ball + 100 off-pitch sample)"
        )
        assert page.evaluate(
            '[...new Set(frames.filter(f=>f.class==="on_ball").map(f=>f.clip))].every((c,i)=>clips.options[i].value===c)'
        )
        # Browsing does not save suggestions.
        page.keyboard.press("ArrowRight")
        page.wait_for_function("imageReady")
        assert page.evaluate("localStorage.length") == 0
        page.keyboard.press("Enter")
        page.wait_for_function("imageReady")
        assert page.evaluate("labels[api.key(frames[index])].source_accepted")
        assert page.evaluate(
            "labels[api.key(frames[index])].accepted_source===suggestionMap[api.key(frames[index])].source"
        )
        page.locator("#canvas").click(position={"x": 100, "y": 100})
        page.wait_for_function("imageReady")
        assert not page.evaluate("labels[api.key(frames[index])].source_accepted")
        assert page.evaluate('!("accepted_source" in labels[api.key(frames[index])])')
        page.keyboard.press("n")
        page.wait_for_function("imageReady")
        assert page.evaluate("labels[api.key(frames[index])].visible===false")
        page.keyboard.press("Space")
        page.wait_for_function("imageReady")
        assert page.evaluate("labels[api.key(frames[index])].source_accepted")
        with page.expect_download() as download:
            page.locator("#export").click()
        exported = Path(download.value.path()).read_text()
        assert json.loads(exported)["source_accepted"]
        # Clear then import exercises the real UI JSONL path.
        page.locator("#clear").click()
        page.wait_for_function("imageReady")
        page.locator("#import").set_input_files(
            {
                "name": "test.jsonl",
                "mimeType": "application/x-ndjson",
                "buffer": exported.encode(),
            }
        )
        page.wait_for_function("Object.keys(labels).length===1 && imageReady")
        page.locator("h1").click()  # Return keyboard focus from file input.
        page.keyboard.press("j")
        page.wait_for_function("imageReady")
        second = page.locator("#clips").input_value()
        page.keyboard.press("k")
        page.wait_for_function("imageReady")
        assert second != page.locator("#clips").input_value()
        # Legacy five-key rows survive reload under the unchanged key.
        page.evaluate(
            'localStorage.setItem(storageKey,JSON.stringify({clip:frames[0].clip,t:frames[0].t,x:10,y:20,visible:true})+"\\n")'
        )
        page.reload()
        page.wait_for_function("imageReady")
        assert page.evaluate("labels[api.key(frames[0])].x===10")
        page.locator("#target").click()
        page.wait_for_function("imageReady")
        assert page.evaluate(
            "targetKeys.has(api.key(frames[index])) && !labels[api.key(frames[index])]"
        )
        a.screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(a.screenshot))
        assert not errors, errors
        browser.close()
    print(
        "Chromium PASS: no auto-save, accept Enter/Space, click override, no-ball, arrows/J/K, legacy storage, export/import, target navigation"
    )


if __name__ == "__main__":
    main()
