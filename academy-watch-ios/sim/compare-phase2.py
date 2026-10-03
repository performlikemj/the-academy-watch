#!/usr/bin/env python3
"""Place approved IMF1 boards beside unaltered native capture pixels.

Requires Pillow. Both panels are scaled to equal width; they are not cropped or
stitched to imply a full-page native screenshot. An optional, separately labelled
scrolled viewport is appended below the initial native viewport.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BOARDS = {
    "N01": "player-home", "N02": "clubs-near-you", "N02b": "clubs-near-you-empty",
    "N03": "club-page", "N04": "trials", "N05": "trial-apply",
    "N06": "my-applications", "N06b": "my-applications-empty",
    "N09": "applicants-pipeline", "N09b": "applicants-pipeline-empty",
    "N10": "applicant-detail", "N13": "staff-access", "N14": "squad-quick-view",
    "N17": "introduction-thread",
}


def scaled(path, width):
    with Image.open(path) as source:
        result = source.convert("RGB")
        return result.resize((width, round(result.height * width / result.width)), Image.Resampling.LANCZOS)


def evidence(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    root = Path.home() / "codex-runs/aw-redesign"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, default=root / "shots/I1")
    parser.add_argument("--references", type=Path, default=root / "ios-mockups/preview/shots")
    parser.add_argument("--appearance", choices=["light", "dark"], default="light")
    parser.add_argument("--width", type=int, default=780)
    args = parser.parse_args()
    output = args.native / "compare"
    output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    manifest = []
    width, gutter, header = args.width, 24, 54
    for screen, name in BOARDS.items():
        reference = args.references / f"{screen}-{name}.png"
        dark = args.references / f"{screen}-{name}-dark.png"
        if args.appearance == "dark" and dark.exists():
            reference = dark
        native = args.native / f"{screen}-{args.appearance}.png"
        left, right = scaled(reference, width), scaled(native, width)
        scroll = args.native / "scroll" / f"{screen}-scrolled-{args.appearance}.png"
        bottom = scaled(scroll, width) if scroll.exists() else None
        right_height = right.height + (header + bottom.height if bottom else 0)
        result = Image.new("RGB", (2 * width + gutter, header + max(left.height, right_height)), "#deddd7")
        draw = ImageDraw.Draw(result)
        draw.text((12, 14), f"{screen} · IMF1 approved ({'dark' if reference == dark else 'light'})", font=font, fill="#0e1311")
        draw.text((width + gutter + 12, 14), f"Native · {args.appearance} · initial viewport", font=font, fill="#0e1311")
        result.paste(left, (0, header)); result.paste(right, (width + gutter, header))
        if bottom:
            offset = header + right.height
            draw.text((width + gutter + 12, offset + 14), "Native · scrolled viewport (separate capture)", font=font, fill="#0e1311")
            result.paste(bottom, (width + gutter, offset + header))
        filename = f"{screen}.png" if args.appearance == "light" else f"{screen}-dark.png"
        result.save(output / filename)
        row = {"board": screen, "reference": evidence(reference), "native": evidence(native), "comparison": filename}
        if bottom:
            row["scrolled"] = evidence(scroll)
        manifest.append(row)
    (output / f"manifest-{args.appearance}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(manifest)} {args.appearance} comparisons to {output}")


if __name__ == "__main__":
    main()
