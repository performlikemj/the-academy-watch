"""Bench-only AGPL YOLO11n point supervision; clip holdouts and saved predictions."""

from __future__ import annotations
import argparse
import importlib.metadata
import json
import math
import shutil
import statistics
import time
from pathlib import Path
from ball_truth_kit import import_labels
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, dump, load_dataset, samples, sha256
from compare_ball import load_measurements
from detectors import merge_tiles
from human_loop import frame_catalog, review_plan, write_jsonl
from metrics import clip_class, ratio

LICENSE = "AGPL-3.0; bench-only internal tooling; https://github.com/ultralytics/ultralytics/blob/main/LICENSE"
WEIGHTS_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt"
)


def split_clips(measurements, labels, smoke=False):
    on = [c["clip_id"] for c in measurements["clips"] if clip_class(c) == "on_ball"]
    labelled = {cid for cid, _ in labels}
    if smoke:
        selected = [c for c in on if c in labelled]
        if len(selected) != 1 or labelled != set(selected):
            raise ValueError(
                "synthetic smoke requires labels for exactly one on-ball clip"
            )
        return {"train": selected, "held_out": [], "smoke_resubstitution_only": True}
    if len(on) != 6 or not set(on) <= labelled:
        raise ValueError(
            "label each of the six on-ball clips before training; split is fixed 4/2 by clip"
        )
    return {
        "train": on[:4],
        "held_out": [
            c["clip_id"]
            for c in measurements["clips"]
            if c["clip_id"] in labelled and c["clip_id"] not in on[:4]
        ],
        "smoke_resubstitution_only": False,
    }


def tile_bounds(size=(1920, 1080)):
    w, h = size
    return [
        (x * w // 2, y * h // 2, (x + 1) * w // 2, (y + 1) * h // 2)
        for y in range(2)
        for x in range(2)
    ]


def box_recipe(measurements, labels, train_clips):
    sizes: list[float] = []
    for cid in train_clips:
        for r in measurements["outputs"]["rf_2x2"][cid]["frames"]:
            label = labels.get((cid, r["t"]))
            if label and label["visible"]:
                sizes.extend(
                    d["size_px"] * 640 / 960
                    for d in r["detections"]
                    if d["size_px"] is not None
                    and math.dist(d["xy"], [label["x"], label["y"]]) <= 20
                )
    median = statistics.median(sizes) if sizes else None
    model_side = max(12.0, 2 * median) if median is not None else 12.0
    return {
        "median_detected_size_at_640_px": median,
        "box_side_at_640_px": model_side,
        "box_side_source_px": model_side * 960 / 640,
        "size_samples": len(sizes),
        "definition": "Train-clip-only RF 2x2 saved 0.1 boxes within 20 source px of a click; size_px is shorter box side, mapped by 640/960. Side=max(12,2*median) in model pixels. No matched size: 12 model px fallback. Unverified detector sizes, not ball-size truth.",
    }


def tile_labels(label, bounds, side, rf_boxes=(), pseudo=False):
    """Single click determines its only positive tile; other tiles stay negative."""
    x0, y0, x1, y1 = bounds
    if not label["visible"] or not (x0 <= label["x"] < x1 and y0 <= label["y"] < y1):
        return []
    x, y = label["x"], label["y"]
    boxes = [
        {
            "box": [x - side / 2, y - side / 2, x + side / 2, y + side / 2],
            "confidence": 1.0,
        }
    ]
    if pseudo:
        boxes += [
            d
            for d in rf_boxes
            if d["confidence"] >= 0.1 and math.dist(d["xy"], [x, y]) <= 20
        ]
    result = []
    for d in merge_tiles(boxes):
        a, b, c, e = d["box"]
        a, b, c, e = max(a, x0), max(b, y0), min(c, x1), min(e, y1)
        if c > a and e > b:
            result.append(
                [
                    ((a + c) / 2 - x0) / (x1 - x0),
                    ((b + e) / 2 - y0) / (y1 - y0),
                    (c - a) / (x1 - x0),
                    (e - b) / (y1 - y0),
                ]
            )
    return result


def prepare_dataset(
    measurements,
    clips,
    labels,
    out,
    split,
    pseudo=False,
    train_only=False,
    scale_targets=False,
):
    import cv2

    from scale_targets import fit_scale, target_side

    if scale_targets and not train_only:
        raise ValueError("scale-aware fitting requires train-only datasets")
    recipe = (
        fit_scale(measurements, labels, split["train"])
        if scale_targets
        else box_recipe(measurements, labels, split["train"])
    )
    counts = {"train": 0, "val": 0, "positive_tiles": 0, "negative_tiles": 0}
    for c in clips:
        cid = c["clip_id"]
        role = (
            "train"
            if cid in split["train"]
            else "val"
            if cid in split["held_out"]
            else None
        )
        if role is None or (train_only and role == "val"):
            continue
        image_dir, label_dir = out / "images" / role, out / "labels" / role
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        saved = {
            r["t"]: r["detections"]
            for r in measurements["outputs"]["rf_2x2"][cid]["frames"]
        }
        for sample, stack in samples(c):
            label = labels.get((cid, sample["t"]))
            if label is None:
                continue  # Unlabelled is never negative.
            for i, bounds in enumerate(tile_bounds(c["source_size"])):
                x0, y0, x1, y1 = bounds
                name = f"{cid}-{sample['sample_index']:05d}-{i}"
                boxes = tile_labels(
                    label,
                    bounds,
                    target_side(label, saved[sample["t"]], recipe)
                    if scale_targets and label["visible"]
                    else 0
                    if scale_targets
                    else recipe["box_side_source_px"],
                    saved[sample["t"]],
                    pseudo and role == "train",
                )
                if not cv2.imwrite(
                    str(image_dir / f"{name}.jpg"),
                    cv2.cvtColor(stack[-1][y0:y1, x0:x1], cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 98],
                ):
                    raise RuntimeError("dataset image write failed")
                (label_dir / f"{name}.txt").write_text(
                    "".join(
                        "0 " + " ".join(f"{v:.8f}" for v in box) + "\n" for box in boxes
                    )
                )
                counts[role] += 1
                counts["positive_tiles" if boxes else "negative_tiles"] += 1
    if not counts["train"] or (
        not train_only and not split["smoke_resubstitution_only"] and not counts["val"]
    ):
        raise ValueError("empty training/held-out dataset")
    # Smoke does NOT split frames: trainer health check reuses the one training
    # clip; no held-out scores exist or are presented as evaluation evidence.
    val = (
        "images/train"
        if train_only or split["smoke_resubstitution_only"]
        else "images/val"
    )
    (out / "dataset.yaml").write_text(
        f"path: {json.dumps(str(out))}\ntrain: images/train\nval: {val}\nnames:\n  0: match_ball\n"
    )
    return {
        "split": split,
        "counts": counts,
        "box_recipe": recipe,
        "pseudo": pseudo,
        "tiling": "Four non-overlapping 960x540 native crops; YOLO imgsz=640, aspect-preserving letterbox to 640x640 (640x360 content). Point belongs to exactly one tile, including seam points. Clip point boxes at tile edges.",
        "negative_policy": "Only human-labelled frames; three non-click tiles or all four explicitly invisible tiles. Split determines training membership; held-out labels never supply training tiles. Pseudo boxes train-only and opt-in.",
    }


def predict_all(model, clips, out, tag, device, frozen_set_id, synthetic, imgsz=640):
    import cv2
    import torch

    outputs, suggestions = {}, []

    def sync():
        if device == "mps":
            torch.mps.synchronize()

    # Explicit warmup outside decode/inference timer.
    import numpy as np

    model.predict(
        [np.zeros((540, 960, 3), dtype=np.uint8)] * 4,
        imgsz=imgsz,
        device=device,
        conf=0.1,
        verbose=False,
    )
    sync()
    for c in clips:
        sync()
        start = time.perf_counter()
        rows = []
        for sample, stack in samples(c):
            bounds = tile_bounds(c["source_size"])
            tiles = [
                cv2.cvtColor(stack[-1][b:d, a:e], cv2.COLOR_RGB2BGR)
                for a, b, e, d in bounds
            ]
            predictions = model.predict(
                tiles, imgsz=imgsz, device=device, conf=0.1, iou=0.5, verbose=False
            )
            ds = []
            for prediction, (x0, y0, _, _) in zip(predictions, bounds):
                for box, score in zip(
                    prediction.boxes.xyxy.cpu().tolist(),
                    prediction.boxes.conf.cpu().tolist(),
                ):
                    a, b, e, d = box
                    box = [a + x0, b + y0, e + x0, d + y0]
                    ds.append(
                        {
                            "box": box,
                            "xy": [(a + e) / 2 + x0, (b + d) / 2 + y0],
                            "confidence": score,
                            "size_px": min(e - a, d - b),
                        }
                    )
            ds = merge_tiles(ds)
            rows.append({**sample, "detections": ds})
            if ds:
                best = max(ds, key=lambda d: d["confidence"])
                suggestions.append(
                    {
                        "clip": c["clip_id"],
                        "t": sample["t"],
                        "x": best["xy"][0],
                        "y": best["xy"][1],
                        "score": best["confidence"],
                        "source": f"model:{tag}",
                    }
                )
        sync()
        wall = time.perf_counter() - start
        outputs[c["clip_id"]] = {
            "clip": c["clip_id"],
            "duration_s": c["duration_s"],
            "wall_s": wall,
            "frames": rows,
        }
        print(f"predict {c['clip_id']}: {len(rows)} frames {wall:.2f}s", flush=True)
    payload = {
        "schema_version": 1,
        "frozen_set_id": frozen_set_id,
        "source_sha256": sha256(clips[0]["video"]),
        "candidate": tag,
        "synthetic_smoke": synthetic,
        "threshold": 0.1,
        "source_size": [1920, 1080],
        "outputs": outputs,
    }
    dump(out / "detections.json", payload)
    write_jsonl(out / "suggestions.jsonl", suggestions)
    return outputs, len(suggestions)


def evaluate(outputs, labels, held_out, off_sample):
    def count(keys):
        visible = hits = predicted = labelled = no_ball = no_ball_predictions = 0
        rows = {(cid, r["t"]): r for cid, raw in outputs.items() for r in raw["frames"]}
        for key in keys:
            label = labels.get(key)
            if label is None:
                continue
            labelled += 1
            ds = rows[key]["detections"]
            predicted += len(ds)
            if label["visible"]:
                visible += 1
                hits += any(
                    math.dist(d["xy"], [label["x"], label["y"]]) <= 20 for d in ds
                )
            else:
                no_ball += 1
                no_ball_predictions += len(ds)
        return {
            "no_ball_frames": no_ball,
            "no_ball_predictions": no_ball_predictions,
            "no_ball_false_per_frame": ratio(no_ball_predictions, no_ball),
            "labelled_frames": labelled,
            "visible_frames": visible,
            "matched": hits,
            "predictions": predicted,
            "recall": ratio(hits, visible),
            "precision": ratio(hits, predicted),
            "false_per_frame": ratio(predicted - hits, labelled),
        }

    held_keys = [(cid, r["t"]) for cid in held_out for r in outputs[cid]["frames"]]
    return {
        "matching_radius_source_px": 20,
        "threshold": 0.1,
        "held_out": count(held_keys),
        "off_pitch_sample": count([(f["clip"], f["t"]) for f in off_sample]),
        "fps_including_decode": sum(len(r["frames"]) for r in outputs.values())
        / sum(r["wall_s"] for r in outputs.values()),
        "definition": "One match ball per visible label; at most one matching prediction. All duplicates/other predictions unmatched; unlabelled frames excluded. Held-out clips never used for fitting or point-box sizing.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--human-jsonl", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument(
        "--init", type=Path, default=Path.home() / "models/tinyball/yolo11n.pt"
    )
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Tile model input; variant may increase to 960",
    )
    p.add_argument("--split-json", type=Path)
    p.add_argument("--allow-prior-tuning", action="store_true")
    p.add_argument("--train-loss-only", action="store_true")
    p.add_argument("--scale-targets", action="store_true")
    p.add_argument("--train-minutes", type=float, default=15)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument(
        "--defer-evaluation",
        action="store_true",
        help="Fit only; inspect TRAIN loss before a separate all-frame saved pass",
    )
    p.add_argument("--device", choices=["mps", "cpu"], default="mps")
    p.add_argument("--pseudo", action="store_true")
    p.add_argument(
        "--synthetic-smoke",
        action="store_true",
        help="ONE synthetic on-ball clip; no held-out metrics, never human truth",
    )
    a = p.parse_args()
    if (
        not math.isfinite(a.train_minutes)
        or a.train_minutes <= 0
        or a.batch < 1
        or a.patience < 1
    ):
        p.error("positive finite training budget, batch and patience required")
    if a.defer_evaluation and not a.train_loss_only:
        p.error("deferred evaluation requires train-loss-only selection")
    if a.imgsz < 32 or a.imgsz % 32:
        p.error("imgsz must be a positive multiple of 32")
    if a.epochs < 1 or (a.synthetic_smoke and a.epochs != 2):
        p.error("positive epochs required; synthetic smoke uses exactly two epochs")
    if a.out.exists() and any(a.out.iterdir()):
        p.error("output directory must be new or empty; preserve prior runs")
    m = load_measurements()
    labels = import_labels(a.human_jsonl, frame_catalog(m))
    split = split_clips(m, labels, a.synthetic_smoke)
    if a.split_json:
        from round2_protocol import validate_split

        proposed = json.loads(a.split_json.read_text())
        split = proposed.get("split", proposed)
        prior = json.loads(
            (Path(__file__).parent / "fixtures/human_execution.json").read_text()
        )["split"]
        validate_split(split, m, labels, prior, allow_prior_tuning=a.allow_prior_tuning)
        if not a.train_loss_only:
            p.error("round-2 custom split requires --train-loss-only")
        init_dataset = a.init.parent / "dataset.json"
        if init_dataset.exists():
            fitted = json.loads(init_dataset.read_text())["split"]["train"]
            if set(fitted) & set(split["held_out"]):
                p.error("initial weights already fitted on held-out clips")
    if not any(
        r["visible"] and cid in split["train"] for (cid, _), r in labels.items()
    ):
        p.error("training needs at least one visible click")
    manifest, clips = load_dataset(a.manifest, a.source)
    if manifest["frozen_set_id"] != m["frozen_set_id"] or any(
        not c["native_source"] or c["source_size"] != [1920, 1080] for c in clips
    ):
        p.error("training requires matching native 1920x1080 source")
    a.out = a.out.expanduser().resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    import cv2
    import torch

    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    if a.device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS requested but unavailable")
    start = time.perf_counter()
    dataset = prepare_dataset(
        m,
        clips,
        labels,
        a.out / "dataset",
        split,
        a.pseudo,
        a.train_loss_only,
        a.scale_targets,
    )
    dataset["model_input_px"] = a.imgsz
    dataset["tiling"] = (
        dataset["tiling"]
        .replace(
            "640x640 (640x360 content)",
            f"{a.imgsz}x{a.imgsz} ({a.imgsz}x{a.imgsz * 540 / 960:g} content)",
        )
        .replace("imgsz=640", f"imgsz={a.imgsz}")
    )
    dataset["synthetic_smoke"] = a.synthetic_smoke
    dataset["labels_sha256"] = sha256(a.human_jsonl)
    dataset["source_accepted_labels"] = sum(
        r.get("source_accepted", False) for r in labels.values()
    )
    dump(a.out / "dataset.json", dataset)
    if not a.init.exists():
        if a.init != Path.home() / "models/tinyball/yolo11n.pt":
            raise FileNotFoundError(a.init)
        import urllib.request

        a.init.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(WEIGHTS_URL, a.init)
    from ultralytics import YOLO, settings

    settings.update(
        {
            "sync": False,
            "wandb": False,
            "mlflow": False,
            "comet": False,
            "tensorboard": False,
            "clearml": False,
        }
    )
    model = YOLO(str(a.init))
    train_start = time.perf_counter()
    trainer_options: dict[str, object] = {}
    if a.train_loss_only:
        from train_loss_trainer import trainer_class

        trainer_options.update(
            trainer=trainer_class(),
            optimizer="AdamW",
            lr0=0.002,
            momentum=0.9,
            warmup_bias_lr=0.0,
        )
    model.train(
        **trainer_options,
        data=str(a.out / "dataset/dataset.yaml"),
        epochs=a.epochs,
        imgsz=a.imgsz,
        device=a.device,
        batch=a.batch,
        workers=0,
        seed=42,
        deterministic=True,
        amp=False,
        cache=False,
        project=str(a.out),
        name="fit",
        exist_ok=False,
        plots=False,
        mosaic=0.0,
        mixup=0.0,
        copy_paste=0.0,
        fliplr=0.5,
        scale=0.2,
        translate=0.05,
        val=a.train_loss_only,
        patience=a.patience,
        time=None if a.synthetic_smoke else a.train_minutes / 60,
    )
    if a.device == "mps":
        torch.mps.synchronize()
    train_s = time.perf_counter() - train_start
    weights = a.out / "weights.pt"
    # Normal runs use the final epoch, never select a checkpoint using held-out
    # labels. Ultralytics may perform its final validation, but cannot choose
    # these weights. Smoke retains its explicitly resubstitution-only checkpoint.
    checkpoint = "best.pt" if a.synthetic_smoke or a.train_loss_only else "last.pt"
    shutil.copy2(a.out / "fit/weights" / checkpoint, weights)
    if a.train_loss_only:
        import csv

        history = list(csv.DictReader((a.out / "fit/results.csv").open()))
        losses = [float(r["train/selection_loss"]) for r in history]
        fit_record = {
            "status": "fit complete; evaluation deferred"
            if a.defer_evaluation
            else "fit complete",
            "split": split,
            "device": a.device,
            "model_input_px": a.imgsz,
            "training_s": train_s,
            "fit_budget_minutes": a.train_minutes,
            "epochs_requested": a.epochs,
            "epochs_recorded": len(history),
            "best_train_loss": min(losses),
            "best_epoch": losses.index(min(losses)) + 1,
            "last_train_loss": losses[-1],
            "train_loss_history": losses,
            "selection": "Minimum mean augmented training-batch box+cls+dfl loss; early stopping sees only reciprocal training loss fitness. No held-out validation or inference during fitting.",
            "initial_weights": str(a.init),
            "initial_weights_sha256": sha256(a.init),
            "weights_sha256": sha256(weights),
            "labels_sha256": sha256(a.human_jsonl),
            "source_sha256": sha256(a.source),
            "batch": a.batch,
            "patience": a.patience,
            "versions": {
                n: importlib.metadata.version(n)
                for n in (
                    "ultralytics",
                    "torch",
                    "torchvision",
                    "numpy",
                    "opencv-python",
                )
            },
        }
        dump(a.out / "fit_summary.json", fit_record)
        if a.defer_evaluation:
            print(
                f"FIT COMPLETE {a.out}: {train_s / 60:.2f} min, TRAIN loss {min(losses):.6f}; NO held-out evaluation",
                flush=True,
            )
            return
    # Exactly one prediction pass on all 1,105 frames; held-out evaluation reuses it.
    outputs, n_suggestions = predict_all(
        YOLO(str(weights)),
        clips,
        a.out,
        a.out.name,
        a.device,
        m["frozen_set_id"],
        a.synthetic_smoke,
        a.imgsz,
    )
    saved_path = a.out / "detections.json"
    saved = json.loads(saved_path.read_text())
    saved["training_split"] = split
    saved["training_labels_sha256"] = sha256(a.human_jsonl)
    saved["weights_sha256"] = sha256(weights)
    dump(saved_path, saved)
    metrics = evaluate(
        outputs, labels, split["held_out"], review_plan(frame_catalog(m))["off_pitch"]
    )
    metrics.update(
        {
            "status": "SYNTHETIC SMOKE ONLY — NOT BALL RESULTS"
            if a.synthetic_smoke
            else "human click training; held-out sample evaluation",
            "synthetic_smoke": a.synthetic_smoke,
            "split": split,
            "model": "YOLO11n",
            "licence": LICENSE,
            "device": a.device,
            "training_s": train_s,
            "total_s": time.perf_counter() - start,
            "epochs_requested": a.epochs,
            "model_input_px": a.imgsz,
            "versions": {
                n: importlib.metadata.version(n)
                for n in (
                    "ultralytics",
                    "torch",
                    "torchvision",
                    "numpy",
                    "opencv-python",
                )
            },
            "initial_weights": str(a.init),
            "initial_weights_sha256": sha256(a.init),
            "pretrained_url": WEIGHTS_URL,
            "weights_sha256": sha256(weights),
            "suggestions": n_suggestions,
            "frames_scanned": sum(len(r["frames"]) for r in outputs.values()),
        }
    )
    dump(a.out / "metrics.json", metrics)
    print(
        f"Completed {a.out}; synthetic={a.synthetic_smoke}; training {train_s / 60:.2f} min; {n_suggestions} unconfirmed suggestions",
        flush=True,
    )


if __name__ == "__main__":
    main()
