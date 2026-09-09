"""One-shot Python 3.12 MLX worker; stdin/stdout are exclusively JSON."""

from __future__ import annotations

import contextlib
import json
import sys
import time
from unittest.mock import patch


def load_native_video(path: str, fps: float):
    """Observe mlx-vlm's decoder reads without implementing another sampler."""
    import cv2
    from mlx_vlm.utils import load_video

    capture = cv2.VideoCapture
    indices = []
    metadata = {}

    class RecordingCapture:
        def __init__(self, *args, **kwargs):
            self.cap = capture(*args, **kwargs)
            metadata.update(
                fps=self.cap.get(cv2.CAP_PROP_FPS),
                total_num_frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            )

        def __getattr__(self, name):
            return getattr(self.cap, name)

        def read(self):
            index = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            ok, frame = self.cap.read()
            if ok:
                indices.append(index)
            return ok, frame

    with patch.object(cv2, "VideoCapture", RecordingCapture):
        video, effective_fps = load_video(path, fps=fps, max_frames=768)
    if metadata["fps"] <= 0 or len(indices) != len(video) or len(video) % 2:
        raise ValueError(
            "video decode produced invalid timing or incomplete frame pairs"
        )
    metadata["frames_indices"] = indices
    return video, effective_fps, metadata


def run(request: dict) -> dict:
    started = time.monotonic()
    import mlx.core as mx
    from mlx_vlm import generate, load
    from PIL import Image

    video, effective_fps, metadata = load_native_video(
        request["clip"], float(request["fps"])
    )
    times = [index / metadata["fps"] for index in metadata["frames_indices"]]
    model, processor = load(request["model"])
    if getattr(processor, "video_processor", None) is None:
        raise RuntimeError("model processor has no native video support")
    absolute_times = [round(request["start_s"] + t, 3) for t in times]
    prompt = request["prompt"].replace(
        "__VIDEO_TIMESTAMPS__", ", ".join(f"{t:.3f}" for t in absolute_times)
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "video"},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    formatted = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    # The installed mlx-vlm Qwen processor uses native temporal patch grids
    # without HF timestamp tokens or a second sampling pass. Exact decoder
    # timestamps are supplied in the prompt; prepared tensors let us audit sizes.
    with Image.open(request["anchor_image"]) as anchor:
        inputs = processor(
            text=[formatted],
            images=[anchor.convert("RGB")],
            videos=[video],
            return_tensors="np",
        )
    grid = inputs["video_grid_thw"][0].tolist()
    patch_size = processor.video_processor.patch_size
    sent_h, sent_w = int(grid[1] * patch_size), int(grid[2] * patch_size)
    if int(grid[0]) * processor.video_processor.temporal_patch_size != len(times):
        raise RuntimeError("processor changed the native video frame count")
    image_grid = inputs["image_grid_thw"][0].tolist()
    image_patch = processor.image_processor.patch_size
    prepared = {
        key: mx.array(value) for key, value in inputs.items() if key != "video_metadata"
    }
    prepared["mask"] = prepared.pop("attention_mask", None)
    response = generate(
        model,
        processor,
        formatted,
        **prepared,
        max_tokens=int(request["max_tokens"]),
        temperature=float(request["temperature"]),
        repetition_penalty=float(request["repetition_penalty"]),
        repetition_context_size=int(request["repetition_context_size"]),
        verbose=False,
    )
    return {
        "text": response.text,
        "prompt_tokens": response.prompt_tokens,
        "generation_tokens": response.generation_tokens,
        "wall_s": round(time.monotonic() - started, 3),
        "sampled_frame_times": times,
        "sent_w": sent_w,
        "sent_h": sent_h,
        "anchor_sent_w": int(image_grid[2] * image_patch),
        "anchor_sent_h": int(image_grid[1] * image_patch),
        "effective_fps": effective_fps,
        "model": request["model"],
    }


def main() -> int:
    try:
        request = json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr):
            result = run(request)
    except Exception as exc:
        # Do not expose package diagnostics or environment values in the protocol.
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1
    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
