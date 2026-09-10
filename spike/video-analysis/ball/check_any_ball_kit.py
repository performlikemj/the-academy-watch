"""Build-13 browser checks in isolated storage; no model runtime or MJ edits."""

from pathlib import Path
import argparse
import json


def check(kit, screenshot=None):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browsers = sorted(
            (Path.home() / "Library/Caches/ms-playwright").glob(
                "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
            )
        )
        browser = pw.chromium.launch(
            executable_path=str(browsers[-1]) if browsers else None
        )
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((kit / "index.html").as_uri())
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        seed = page.evaluate("JSON.stringify(labels)")
        assert page.evaluate(
            "localStorage.getItem(storageKey)!==null && localStorage.getItem(legacyKey)===null"
        )
        page.locator("#review").click()
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.locator("#progress").inner_text() == "reviewed 0 / 188"
        assert page.evaluate("JSON.stringify(labels)") == seed
        assert page.evaluate(
            "localStorage.getItem(storageKey)!==null && localStorage.getItem(legacyKey)===null"
        )
        first = page.evaluate("api.key(frames[index])")
        page.locator("h1").click()
        page.keyboard.press("Enter")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        row = page.evaluate("labels[api.key(frames[index])]")
        assert row["visible"] and row["match_ball"] is False and row["source_accepted"]
        assert row["review_confirmed"] and row["schema_version"] == 2
        assert row["accepted_source"] == page.evaluate(
            "suggestionFor(frames[index]).source"
        )
        assert page.locator("#progress").inner_text() == "reviewed 1 / 188"
        page.keyboard.press("m")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("labels[api.key(frames[index])].match_ball")
        assert page.evaluate("labels[api.key(frames[index])].source_accepted")
        with page.expect_download() as download:
            page.locator("#export").click()
        exported = Path(download.value.path()).read_text()
        rows = [json.loads(line) for line in exported.splitlines()]
        accepted = next(r for r in rows if f"{r['clip']}|{r['t']:.6f}" == first)
        assert accepted["accepted_source"] == row["accepted_source"]
        assert accepted["accepted_score"] == row["accepted_score"]
        assert all(r["schema_version"] == 2 and "match_ball" in r for r in rows)
        page.locator("#canvas").click(position={"x": 100, "y": 100})
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate(
            "labels[api.key(frames[index])].match_ball===false && !labels[api.key(frames[index])].source_accepted && !('accepted_source' in labels[api.key(frames[index])])"
        )
        page.keyboard.press("n")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate(
            "labels[api.key(frames[index])].visible===false && labels[api.key(frames[index])].match_ball===null && labels[api.key(frames[index])].review_confirmed"
        )
        page.keyboard.press("m")
        assert page.evaluate("labels[api.key(frames[index])].match_ball===null")
        page.keyboard.press("ArrowRight")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("api.key(frames[index])") != first
        page.keyboard.press("ArrowLeft")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("api.key(frames[index])") == first
        page.keyboard.press("j")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        next_clip = page.evaluate("frames[index].clip")
        page.keyboard.press("k")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("frames[index].clip") != next_clip
        # Stale backups never replace newer decisions, even if a dialog is accepted.
        saved = page.evaluate("labels")
        page.on("dialog", lambda d: d.accept())
        page.locator("#import").set_input_files(
            {
                "name": "truth.jsonl",
                "mimeType": "application/x-ndjson",
                "buffer": exported.encode(),
            }
        )
        page.wait_for_function("document.getElementById('import').value===''")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        page.reload()
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("labels") == saved
        # Normal mode keeps default match=true and the old storage key.
        assert not page.evaluate("reviewMode")
        page.locator("#canvas").click(position={"x": 100, "y": 100})
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("labels[api.key(frames[index])].match_ball===true")
        page.keyboard.press("m")
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate("labels[api.key(frames[index])].match_ball===false")
        page.evaluate(
            'localStorage.removeItem(storageKey);localStorage.setItem(legacyKey,JSON.stringify({clip:frames[0].clip,t:frames[0].t,x:10,y:20,visible:true,source_accepted:true,accepted_source:"legacy",accepted_score:0.7})+"\\n")'
        )
        page.reload()
        page.evaluate("writes")
        page.wait_for_function("initialized && imageReady")
        assert page.evaluate(
            "labels[api.key(frames[0])].accepted_source==='legacy' && labels[api.key(frames[0])].schema_version===2"
        )
        assert not errors, errors
        if screenshot:
            page.locator("#review").click()
            page.wait_for_function("initialized && imageReady")
            page.evaluate("writes")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot))
        browser.close()
    print(
        "Chromium PASS: seed/no suggestion auto-save; review keys; normal defaults; v2 export/provenance/import; one-time legacy input"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--kit", type=Path, default=Path.home() / "ball-truth-review-build13"
    )
    p.add_argument("--screenshot", type=Path)
    a = p.parse_args()
    check(a.kit, a.screenshot)
