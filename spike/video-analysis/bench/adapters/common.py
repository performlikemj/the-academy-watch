"""Shared adapter utilities; media/model primitives stay in qwen_match_analysis."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

VIDEO_ANALYSIS_DIR = Path(__file__).resolve().parents[2]
if str(VIDEO_ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(VIDEO_ANALYSIS_DIR))

import qwen_match_analysis  # noqa: E402

_REQUEST_PATCH_LOCK = threading.Lock()


def sample_timestamps(
    truth: dict, *, interval_s: float = 5.0, limit: int = 6
) -> list[tuple[float, float]]:
    """Return (clip-local, source-absolute) frame times at the requested cadence."""
    start = float(truth["window"]["start_s"])
    end = float(truth["window"]["end_s"])
    duration = end - start
    if duration <= 0 or interval_s <= 0 or limit <= 0:
        return []
    box_track = truth.get("box_track") or []
    first_box_s = float(box_track[0][0]) if box_track else start
    first_local = min(max(0.0, first_box_s - start), duration / 2)
    local_times = [max(min(0.05, duration / 2), first_local)]
    next_time = local_times[0] + interval_s
    while next_time < duration and len(local_times) < limit:
        local_times.append(next_time)
        next_time += interval_s
    return [(round(local, 3), round(start + local, 3)) for local in local_times]


def extract_sample_frames(
    clip: Path, truth: dict, output_dir: Path
) -> list[tuple[Path, float]]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must be available on PATH")
    # Use both shared argv helpers up front so adapter media handling stays tied
    # to the current spike primitives rather than growing a second command shape.
    qwen_match_analysis.ffprobe_argv(ffprobe, clip)
    frames: list[tuple[Path, float]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, (local_s, absolute_s) in enumerate(sample_timestamps(truth)):
        output = output_dir / f"frame-{index:02d}.jpg"
        qwen_match_analysis.extract_frame(
            clip,
            output,
            local_s,
            Path(ffmpeg),
            Path(ffmpeg).resolve().parent,
            VIDEO_ANALYSIS_DIR / "sandbox" / "ffmpeg_decode.sb",
            False,
            None,
        )
        frames.append((output, absolute_s))
    return frames


def ollama_chat_with_options(
    prompt: str,
    *,
    ollama_url: str,
    model: str,
    timeout_s: float,
    image_paths: list[Path],
    options: dict,
) -> str:
    """Call the shared Ollama primitive while adding adapter-only options.

    The existing helper owns image encoding, JSON mode, and response parsing but
    does not expose Ollama options. A narrow, locked Request wrapper augments the
    outgoing body without copying that network implementation.
    """
    original_request = qwen_match_analysis.urllib.request.Request

    def request_with_options(url, *args, data=None, **kwargs):
        if data is not None:
            body = json.loads(data.decode("utf-8"))
            body.setdefault("options", {}).update(options)
            data = json.dumps(body).encode("utf-8")
        return original_request(url, *args, data=data, **kwargs)

    with _REQUEST_PATCH_LOCK:
        qwen_match_analysis.urllib.request.Request = request_with_options
        try:
            return qwen_match_analysis.ollama_chat(
                prompt,
                ollama_url=ollama_url,
                model=model,
                timeout_s=timeout_s,
                image_paths=image_paths,
            )
        finally:
            qwen_match_analysis.urllib.request.Request = original_request


def interpolated_box(box_track: list[list], timestamp_s: float) -> list[float] | None:
    if not box_track:
        return None
    rows = sorted(box_track, key=lambda row: float(row[0]))
    if timestamp_s < float(rows[0][0]) or timestamp_s > float(rows[-1][0]):
        return None
    for index, row in enumerate(rows):
        row_t = float(row[0])
        if math.isclose(timestamp_s, row_t, abs_tol=1e-9):
            return [float(value) for value in row[1:5]]
        if row_t > timestamp_s:
            left = rows[index - 1]
            fraction = (timestamp_s - float(left[0])) / (row_t - float(left[0]))
            return [
                float(left[column])
                + fraction * (float(row[column]) - float(left[column]))
                for column in range(1, 5)
            ]
    return [float(value) for value in rows[-1][1:5]]


def draw_truth_box(
    frame: Path, box: list[float], frame_size: list[int], jersey_number: int
) -> None:
    """Draw a thin labelled box, preserving the extracted frame dimensions."""
    try:
        from PIL import Image, ImageDraw

        image = Image.open(frame).convert("RGB")
        source_width, source_height = frame_size
        scale_x = image.width / source_width
        scale_y = image.height / source_height
        scaled = [
            box[0] * scale_x,
            box[1] * scale_y,
            box[2] * scale_x,
            box[3] * scale_y,
        ]
        draw = ImageDraw.Draw(image)
        draw.rectangle(scaled, outline=(255, 40, 40), width=3)
        label = f"#{jersey_number}"
        label_box = draw.textbbox((scaled[0], scaled[1]), label)
        draw.rectangle(label_box, fill=(255, 40, 40))
        draw.text((scaled[0], scaled[1]), label, fill=(255, 255, 255))
        image.save(frame, quality=94)
        return
    except ImportError:
        pass

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "Pillow is unavailable and ffmpeg is not on PATH for drawbox fallback"
        )
    # ffmpeg sees the 1280px-wide extracted image, so scale source coordinates.
    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(frame),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    scale_x = int(stream["width"]) / frame_size[0]
    scale_y = int(stream["height"]) / frame_size[1]
    scaled = [box[0] * scale_x, box[1] * scale_y, box[2] * scale_x, box[3] * scale_y]
    output = frame.with_name(f"{frame.stem}-boxed.jpg")
    drawbox = (
        f"drawbox=x={scaled[0]:.3f}:y={scaled[1]:.3f}:"
        f"w={scaled[2] - scaled[0]:.3f}:h={scaled[3] - scaled[1]:.3f}:color=red:t=3,"
        f"drawtext=text='#{jersey_number}':x={scaled[0]:.3f}:y={scaled[1]:.3f}:"
        "fontcolor=white:fontsize=22:box=1:boxcolor=red"
    )
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(frame), "-vf", drawbox, str(output)],
        check=True,
    )
    output.replace(frame)


def temp_directory(prefix: str):
    return tempfile.TemporaryDirectory(prefix=prefix)
