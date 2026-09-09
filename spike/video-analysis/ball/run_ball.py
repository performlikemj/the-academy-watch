"""Sequential local inference; raw reports remain outside git."""

from __future__ import annotations
import argparse
import importlib.metadata
import platform
import sys
import time
from pathlib import Path

from common import (
    DEFAULT_MANIFEST,
    DEFAULT_REPORT,
    DEFAULT_SOURCE,
    HERE,
    dump,
    load_dataset,
    probe,
    samples,
    sha256,
)
from detectors import RFDetector, WASBDetector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        choices=["rf_full", "rf_2x2", "rf_3x3", "wasb", "wasb_2x2"],
        required=True,
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--clips", default="all")
    parser.add_argument("--device", default="mps", choices=["mps", "cpu"])
    parser.add_argument(
        "--resolution", type=int, help="RF-DETR input side override; default 576"
    )
    parser.add_argument(
        "--parity-frames",
        type=int,
        choices=[5],
        help="Five-frame tiled WASB CPU/MPS heatmap parity",
    )
    args = parser.parse_args()
    if args.resolution is not None and (
        args.resolution <= 0 or args.candidate.startswith("wasb")
    ):
        parser.error("resolution override requires a positive RF-DETR input side")
    if args.parity_frames and args.candidate != "wasb_2x2":
        parser.error("parity check is for wasb_2x2")
    manifest, clips = load_dataset(args.manifest, args.source)
    if args.clips != "all":
        clips = [c for c in clips if c["clip_id"] in args.clips.split(",")]
    if not clips:
        parser.error("no clips selected")
    from wasb_parity import plan_parity

    try:
        parity_plan = (
            plan_parity(clips, args.parity_frames) if args.parity_frames else None
        )
    except ValueError as error:
        parser.error(str(error))
    import cv2
    import torch

    if parity_plan and not torch.backends.mps.is_available():
        parser.error("MPS must be available for MPS-versus-CPU parity")
    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    started = time.perf_counter()
    model: RFDetector | WASBDetector
    if args.candidate.startswith("wasb"):
        model = WASBDetector(
            HERE / "third_party/WASB-SBDT",
            Path.home() / "models/wasb/wasb_soccer_best.pth.tar",
            args.device,
            grid=2 if args.candidate == "wasb_2x2" else 1,
        )
    else:
        grid = {"rf_full": 1, "rf_2x2": 2, "rf_3x3": 3}[args.candidate]
        info = probe(clips[0]["video"])
        model = RFDetector(
            grid, (info["width"], info["height"]), args.resolution, device=args.device
        )

    def sync():
        if model.device == "mps":
            torch.mps.synchronize()

    first = next(samples(clips[0]))[1]
    model(first, manifest["frame_size"])
    sync()
    startup = time.perf_counter() - started
    out = args.report_dir / args.candidate
    out.mkdir(parents=True, exist_ok=True)
    metadata = {
        "candidate": args.candidate,
        "device": model.device,
        "input_resolution": model.resolution,
        "sample_fps": 2.0,
        "startup_and_warmup_s": startup,
        "frozen_set_id": manifest["frozen_set_id"],
        "python": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "torch_mps_available": torch.backends.mps.is_available(),
        "versions": {
            n: importlib.metadata.version(n)
            for n in [
                "torch",
                "torchvision",
                "rfdetr",
                "supervision",
                "opencv-python-headless",
                "numpy",
                "transformers",
            ]
        },
        "clips": [c["clip_id"] for c in clips],
        "source": str(args.source),
        "source_sha256": sha256(args.source) if args.source.is_file() else None,
        "source_probe": probe(clips[0]["video"]),
    }
    if args.candidate == "wasb_2x2":
        metadata["tiling"] = (
            "2x2 non-overlapping 960x540 source tiles -> 512x288 each; per-tile peak, 40 source-px point NMS"
        )
    dump(out / "run.json", metadata)
    for clip in clips:
        sync()
        begin = time.perf_counter()
        rows = []
        for sample, stack in samples(clip):
            detections = model(stack, manifest["frame_size"])
            rows.append({**sample, "detections": detections})
        sync()
        wall = time.perf_counter() - begin
        result = {
            "clip": clip["clip_id"],
            "duration_s": clip["duration_s"],
            "wall_s": wall,
            "fps": len(rows) / wall,
            "frames": rows,
        }
        dump(out / f"{clip['clip_id']}.json", result)
        print(
            f"{args.candidate} {clip['clip_id']} {len(rows)} frames {wall:.2f}s {len(rows) / wall:.2f}fps",
            flush=True,
        )

    if args.parity_frames:
        from wasb_parity import check_parity

        metadata["parity"] = check_parity(model, clips, parity_plan)
        dump(out / "run.json", metadata)


if __name__ == "__main__":
    main()
