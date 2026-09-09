#!/usr/bin/env python3
"""Render CPU-only boxed review videos and a portable, offline human-note page."""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

try:
    from .apply_notes import load_truths, template
except ImportError:  # pragma: no cover - CLI
    from apply_notes import load_truths, template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from grounding import draw_anchor_box, interpolated_box, scale_box  # noqa: E402


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_frames",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["streams"][0]


def label_stamp(jersey: int, directory: Path):
    """Reuse the actual shared renderer for the white-on-red identity label."""
    import cv2
    from PIL import Image, ImageDraw

    path = directory / "label.png"
    canvas = Image.new("RGB", (128, 64))
    bounds = ImageDraw.Draw(canvas).textbbox((0, 0), f"#{jersey}")
    canvas.save(path)
    draw_anchor_box(path, [0, 0, 127, 63], f"#{jersey}")
    image = cv2.imread(str(path))
    x0, y0, x1, y1 = bounds
    return image[y0 : y1 + 1, x0 : x1 + 1], (x0, y0)


def draw_overlay(frame, box, stamp, offset):
    """Draw in BGR using the shared renderer's red, three-pixel box and label."""
    import cv2

    if box is None:
        cv2.rectangle(frame, (4, 4), (91, 26), (25, 25, 25), -1)
        cv2.putText(
            frame,
            "no track",
            (9, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return
    x0, y0, x1, y1 = (round(value) for value in box)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (40, 40, 255), 3)
    left, top = x0 + offset[0], y0 + offset[1]
    height, width = frame.shape[:2]
    a, b = max(0, left), max(0, top)
    c, d = min(width, left + stamp.shape[1]), min(height, top + stamp.shape[0])
    if c > a and d > b:
        frame[b:d, a:c] = stamp[b - top : d - top, a - left : c - left]


def render_clip(source: Path, truth: dict, output: Path, scale: int = 1280) -> dict:
    import cv2

    if scale < 2:
        raise ValueError("scale must be at least 2 pixels")
    info = probe_video(source)
    fps = Fraction(info["avg_frame_rate"])
    if fps <= 0:
        raise ValueError("source frame rate must be positive")
    source_size = (int(info["width"]), int(info["height"]))
    width = min(scale, source_size[0]) // 2 * 2
    height = max(2, round(source_size[1] * width / source_size[0] / 2) * 2)
    truth_size = tuple(truth.get("frame_size", source_size))
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    capture = cv2.VideoCapture(
        str(source),
        cv2.CAP_FFMPEG,
        [cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE],
    )
    if not capture.isOpened():
        raise RuntimeError(f"cannot open {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    count, gaps = 0, 0
    encoder = None
    try:
        with tempfile.TemporaryDirectory(prefix=".render-", dir=output.parent) as temp:
            directory = Path(temp)
            stamp, offset = label_stamp(int(truth["jersey_number"]), directory)
            encoded = directory / "encoded.mp4"
            # ffmpeg receives CPU-decoded/drawn BGR frames; no hardware codec is used.
            with (directory / "ffmpeg.log").open("w+") as log:
                encoder = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-f",
                        "rawvideo",
                        "-pix_fmt",
                        "bgr24",
                        "-s",
                        f"{width}x{height}",
                        "-r",
                        str(fps),
                        "-i",
                        "pipe:0",
                        "-an",
                        "-c:v",
                        "libx264",
                        "-crf",
                        "23",
                        "-preset",
                        "veryfast",
                        "-pix_fmt",
                        "yuv420p",
                        "-threads",
                        "2",
                        "-movflags",
                        "+faststart",
                        str(encoded),
                    ],
                    stdin=subprocess.PIPE,
                    stderr=log,
                )
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    timestamp = float(truth["window"]["start_s"]) + count / float(fps)
                    box = interpolated_box(truth.get("box_track", []), timestamp)
                    if box is None:
                        gaps += 1
                    else:
                        box = scale_box(box, truth_size, (width, height))
                    frame = cv2.resize(
                        frame, (width, height), interpolation=cv2.INTER_AREA
                    )
                    draw_overlay(frame, box, stamp, offset)
                    encoder.stdin.write(frame.tobytes())
                    count += 1
                encoder.stdin.close()
                if encoder.wait() != 0:
                    log.seek(0)
                    raise RuntimeError(f"ffmpeg encode failed: {log.read()}")
            expected = info.get("nb_frames")
            if count == 0 or (
                expected not in (None, "N/A") and abs(count - int(expected)) > 1
            ):
                raise RuntimeError(f"decoded {count} frames; source reports {expected}")
            encoded.replace(output)
    finally:
        capture.release()
        if encoder is not None and encoder.poll() is None:
            # This encoder was created above; never terminate unrelated processes.
            encoder.terminate()
            encoder.wait()
    return {
        "clip_id": truth["clip_id"],
        "frames": count,
        "no_track_frames": gaps,
        "width": width,
        "height": height,
        "fps": str(fps),
        "bytes": output.stat().st_size,
    }


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lane A · Player review</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f6f7f8;color:#17212b;font:16px/1.5 system-ui,sans-serif}
main{max-width:960px;margin:auto;padding:28px 20px}h1{font-size:28px;margin-bottom:8px}
article{margin:28px 0;padding:18px;background:white;border:1px solid #d4dce2;border-radius:8px}
article:focus-visible,input:focus-visible,button:focus-visible,textarea:focus-visible{outline:3px solid #087f8c;outline-offset:3px}
video{display:block;width:100%;aspect-ratio:16/9;background:#111;margin:12px 0}.caption{font-weight:600;margin:0}
.clip-id{font-size:13px;overflow-wrap:anywhere;color:#53616e}input,textarea{display:block;width:100%;font:inherit;padding:10px;border:1px solid #84919c;border-radius:4px}
label{display:block;margin:12px 0 6px}button{font:inherit;cursor:pointer;padding:10px 18px;background:#075d66;color:white;border:0;border-radius:4px}
textarea{height:330px;font:13px/1.6 ui-monospace,monospace;margin-top:12px}#status{min-height:24px}footer{padding-bottom:30px}
</style></head><body><main><h1>Watch the marked player</h1>
<p>Watch each clip and write one plain sentence about what the red-boxed player does. Leave uncertain clips blank.
“No track” means there is no tracked box for that frame.</p>
<p>Space: play/pause the focused clip. J/K: next/previous clip. Shortcuts stay out of note fields.</p>
<p id="save-status" role="status">Notes save in this browser as you type.</p>
__CARDS__
<footer><h2>Your notes</h2><button id="copy" type="button">Copy notes</button>
<p id="status" role="status" aria-live="polite"></p><label for="notes">Paste these lines into ledgers/lane-a-notes.md</label>
<textarea id="notes" readonly spellcheck="false">__LINES__</textarea></footer>
</main><script>
const rows = __DATA__;
const storageKey = __KEY__;
const cards = Array.from(document.querySelectorAll('article'));
const output = document.getElementById('notes');
const saveStatus = document.getElementById('save-status');
let saved = {};
let active = 0;
try { const value = JSON.parse(localStorage.getItem(storageKey) || '{}');
  if (value && typeof value === 'object' && !Array.isArray(value)) saved = value;
} catch (_) { saveStatus.textContent = 'Autosave unavailable. Copy your notes before closing this page.'; }
function update(persist) {
  output.value = rows.map(row => row.line + (saved[row.id] ? ' ' + saved[row.id] : '')).join('\n') + '\n';
  if (persist) { try { localStorage.setItem(storageKey, JSON.stringify(saved)); }
    catch (_) { saveStatus.textContent = 'Autosave unavailable. Copy your notes before closing this page.'; }
  }
}
cards.forEach((card, index) => {
  const input = card.querySelector('input');
  const id = rows[index].id;
  input.value = typeof saved[id] === 'string' ? saved[id].replace(/[\r\n]/g, ' ') : '';
  saved[id] = input.value;
  card.addEventListener('focusin', () => { active = index; });
  card.addEventListener('pointerdown', () => { active = index; });
  input.addEventListener('input', () => { saved[id] = input.value; update(true); });
  const video = card.querySelector('video');
  if (video) video.addEventListener('play', () => {
    document.querySelectorAll('video').forEach(other => { if (other !== video) other.pause(); });
  });
});
update(false);
document.addEventListener('keydown', event => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('input,textarea,button,[contenteditable="true"]')) return;
  if (event.key.toLowerCase() === 'j' || event.key.toLowerCase() === 'k') {
    event.preventDefault();
    const previous = cards[active].querySelector('video');
    if (previous) previous.pause();
    active = Math.max(0, Math.min(cards.length - 1, active + (event.key.toLowerCase() === 'j' ? 1 : -1)));
    cards[active].focus({preventScroll:true});
    cards[active].scrollIntoView({block:'center',behavior:'smooth'});
  } else if (event.code === 'Space') {
    const video = cards[active].querySelector('video');
    if (video) { event.preventDefault(); if (video.paused) video.play().catch(() => {}); else video.pause(); }
  }
});
document.getElementById('copy').addEventListener('click', async () => {
  const status = document.getElementById('status');
  try {
    if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Use selection');
    await navigator.clipboard.writeText(output.value);
    status.textContent = 'Copied notes.';
  } catch (_) {
    output.focus(); output.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (_) {}
    status.textContent = copied ? 'Copied notes.' : 'Notes selected. Press Command-C (Mac) or Control-C to copy.';
  }
});
</script></body></html>
"""


def write_page(truths: list[dict], out_dir: Path, frozen_set_id: str) -> None:
    lines = [line for line in template(truths).splitlines() if line.startswith("- `")]
    rows, cards = [], []
    for index, (truth, line) in enumerate(zip(truths, lines)):
        cid = truth["clip_id"]
        safe_id = html.escape(cid, quote=True)
        window = truth["window"]
        caption = (
            f"clip {index + 1}/{len(truths)} · #{truth['jersey_number']} · {truth['kit_color']} · "
            f"window {window['start_s']:.2f}–{window['end_s']:.2f} s · "
            f"{window['end_s'] - window['start_s']:.2f} s duration"
        )
        media = (
            f'<video controls preload="metadata" playsinline src="clips/{safe_id}.mp4" aria-label="{html.escape(caption, quote=True)}"></video>'
            if (out_dir / "clips" / f"{cid}.mp4").is_file()
            else "<p>Video not included in this export.</p>"
        )
        cards.append(
            f'<article tabindex="0" aria-labelledby="caption-{index}"><p class="caption" id="caption-{index}">{html.escape(caption)}</p>'
            f'<div class="clip-id">{safe_id}</div>{media}<label for="note-{index}">What does the marked player do?</label>'
            f'<input id="note-{index}" type="text" autocomplete="off" spellcheck="true"></article>'
        )
        rows.append({"id": cid, "line": line})
    document = PAGE.replace("__CARDS__", "\n".join(cards)).replace(
        "__LINES__", html.escape("\n".join(lines) + "\n")
    )
    document = document.replace(
        "__DATA__", json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    )
    document = document.replace(
        "__KEY__", json.dumps(f"lane-a-review:{frozen_set_id}").replace("<", "\\u003c")
    )
    (out_dir / "index.html").write_text(document)
    (out_dir / "README.txt").write_text(
        "Open index.html in your browser (keep the clips folder beside it).\n"
        "Watch each clip and follow the red box and #N label.\n"
        "Type one plain sentence about the marked player into each note field.\n"
        "Click Copy notes at the bottom of the page.\n"
        "Paste into ledgers/lane-a-notes.md.\n"
    )


def build_kit(
    frozen_dir: Path, out_dir: Path, clips: str = "all", scale: int = 1280
) -> dict:
    revision = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    commit = revision.stdout.strip() if revision.returncode == 0 else None
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe must be on PATH")
    manifest = json.loads((frozen_dir / "manifest.json").read_text())
    truths = [truth for _, truth in load_truths(frozen_dir / "manifest.json")]
    entries = {entry["clip_id"]: entry for entry in manifest["clips"]}
    selected = (
        set(entries)
        if clips == "all"
        else {cid.strip() for cid in clips.split(",") if cid.strip()}
    )
    if not selected or selected - entries.keys():
        raise ValueError("--clips must be all or known comma-separated clip IDs")
    if not math.isfinite(scale) or scale < 2:
        raise ValueError("--scale must be at least 2 pixels")
    out_dir = out_dir.resolve()
    frozen_dir = frozen_dir.resolve()
    if out_dir == frozen_dir or frozen_dir in out_dir.parents:
        raise ValueError("output must be outside the frozen dataset")
    for cid in entries:
        if not cid or Path(cid).name != cid or cid in {".", ".."}:
            raise ValueError("clip IDs must be safe filenames")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for truth in truths:
        cid = truth["clip_id"]
        if cid not in selected:
            continue
        source = (frozen_dir / entries[cid]["clip"]).resolve()
        print(f"render {cid}", flush=True)
        result = render_clip(source, truth, out_dir / "clips" / f"{cid}.mp4", scale)
        results.append(result)
        print(
            f"  {result['frames']} frames, {result['no_track_frames']} no-track, {result['bytes'] / 1_000_000:.2f} MB",
            flush=True,
        )
    write_page(truths, out_dir, manifest["frozen_set_id"])
    report = {
        "state": "rendered",
        "commit": commit,
        "scale": scale,
        "frozen_set_id": manifest["frozen_set_id"],
        "clips": results,
        "video_bytes": sum(row["bytes"] for row in results),
    }
    (out_dir / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--clips", default="all")
    parser.add_argument("--scale", type=int, default=1280)
    args = parser.parse_args(argv)
    report = build_kit(args.frozen_dir, args.out_dir, args.clips, args.scale)
    print(
        f"Wrote {len(report['clips'])} clips: {report['video_bytes'] / 1_000_000:.2f} MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
