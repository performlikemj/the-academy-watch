"""Shared source-pixel coordinates and deterministic 2 fps sample schedule."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = Path.home() / "Projects/loanarmy-bench-frozen/manifest.json"
DEFAULT_SOURCE = (
    Path.home()
    / "Projects/loanarmy/spike/video-analysis/footage/youtube/afc-yorkies-full.mp4"
)
DEFAULT_REPORT = Path.home() / "Projects/loanarmy-bench-reports/ball-detect-2026-09-10"


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def probe(path):
    data = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,avg_frame_rate,nb_frames",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(data)["streams"][0]


def load_dataset(manifest_path=DEFAULT_MANIFEST, source=DEFAULT_SOURCE):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    native = source is not None and Path(source).is_file()
    if native:
        if not sha256(source).startswith(manifest["footage_sha256_prefix"]):
            raise ValueError("source video hash does not match frozen manifest")
        info = probe(source)
        if [info["width"], info["height"]] != manifest["frame_size"]:
            raise ValueError("source dimensions do not match frozen manifest")
    clips = []
    for entry in manifest["clips"]:
        truth = json.loads((manifest_path.parent / entry["truth"]).read_text())
        cid = entry["clip_id"]
        if Path(cid).name != cid or cid in {".", ".."}:
            raise ValueError("unsafe clip id")
        clips.append(
            {
                **entry,
                "truth_data": truth,
                "video": str(
                    source if native else manifest_path.parent / entry["clip"]
                ),
                "native_source": native,
                "source_size": manifest["frame_size"],
            }
        )
    return manifest, clips


def samples(clip, fps=2.0):
    """Yield actual source timestamps and three consecutive RGB frames.

    Sequentially decode the complete window; sample the nearest native frame to
    start + k/fps, half-open [start,end). Stack the two preceding native frames,
    replicating the first window frame at the left boundary. Decoder work for
    skipped frames stays inside the caller's wall timer.
    """
    import cv2

    if fps <= 0 or not math.isfinite(fps):
        raise ValueError("positive finite fps required")
    start, end = (clip["window"][k] for k in ("start_s", "end_s"))
    cap = cv2.VideoCapture(clip["video"])
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {clip['video']}")
    native_fps = cap.get(cv2.CAP_PROP_FPS)
    offset = 0 if clip["native_source"] else start
    first, last, targets = sample_indices(start, end, native_fps, fps, offset)
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    history: list[Any] = []
    target_i = 0
    try:
        for index in range(first, last):
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError(f"short decode: {clip['clip_id']} at frame {index}")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            history = (history + [rgb])[-3:]
            if target_i < len(targets) and index == targets[target_i]:
                stack = [history[0]] * (3 - len(history)) + history
                yield (
                    {
                        "t": round(offset + index / native_fps, 6),
                        "frame_index": index,
                        "sample_index": target_i,
                    },
                    stack,
                )
                target_i += 1
        if target_i != len(targets):
            raise RuntimeError("incomplete sample schedule")
    finally:
        cap.release()


def sample_indices(start, end, native_fps, fps=2.0, offset=0.0):
    first = math.ceil((start - offset) * native_fps - 1e-6)
    last = math.ceil((end - offset) * native_fps - 1e-6)
    targets = sorted(
        {
            max(first, round((start - offset + k / fps) * native_fps))
            for k in range(math.ceil((end - start) * fps - 1e-8))
        }
        - {last}
    )
    targets = [i for i in targets if i < last]
    return first, last, targets
