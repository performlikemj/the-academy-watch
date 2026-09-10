"""Two predeclared RF fits: affine augmentation/decay, optionally TRAIN replay."""

from __future__ import annotations
import argparse
import importlib.metadata
import json
import math
import random
import time
from pathlib import Path
from ball_truth_kit import import_labels
from common import HERE, dump, sha256
from compare_ball import load_measurements
from human_loop import frame_catalog
from round5_data import dataset_class, is_hard
from train_tiny_ball_rfdetr import export_final, LICENSE, LICENSE_URL


class Plateau:
    def __init__(self):
        self.best, self.stale = math.inf, 0

    def update(self, loss):
        if not math.isfinite(loss):
            raise ValueError("nonfinite TRAIN loss")
        if loss < self.best * 0.99:
            self.best, self.stale = loss, 0
        else:
            self.stale += 1
        return self.stale >= 3


def main():
    import cv2
    import numpy as np
    import torch
    from rfdetr._namespace import _namespace_from_configs
    from rfdetr.config import RFDETRNanoConfig, TrainConfig
    from rfdetr.training import RFDETRModelModule
    from rfdetr.training.param_groups import get_param_dict
    from rfdetr.utilities.tensors import make_collate_fn

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("preserve prior fits")
    root = Path.home() / "models/tinyball"
    protocol = json.loads((HERE / "fixtures/round5_execution.json").read_text())
    cfg = protocol["protocol"]["config"]
    split = protocol["split"]
    old = json.loads((root / "mj-r4-rf-b/fit_summary.json").read_text())
    source = root / "mj-r4-rf-b/dataset"
    labels_path = Path.home() / "codex-runs/ball-human-truth.jsonl"
    labels = import_labels(labels_path, frame_catalog(load_measurements()))
    if old["split"] != split or old["labels_sha256"] != sha256(labels_path):
        raise ValueError("cached TRAIN source provenance differs")
    records = json.loads((source / "annotations.json").read_text())
    if len(records) != 3012 or any(r["clip"] not in split["train"] for r in records):
        raise ValueError("TRAIN-only cached dataset required")
    catalog = {
        (r["clip"], r["sample_index"]): r for r in frame_catalog(load_measurements())
    }
    clicks = []
    for record in records:
        stem = Path(record["file"]).stem
        _, sample, tile = stem.rsplit("-", 2)
        row = catalog[(record["clip"], int(sample))]
        label = labels[(record["clip"], row["t"])]
        i = int(tile)
        clicks.append(
            [label["x"] - (i % 2) * 960, label["y"] - (i // 2) * 540]
            if label["visible"]
            else None
        )
    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True, warn_only=True)
    a.out.mkdir(parents=True)
    data = json.loads((root / "mj-r4-rf-b/dataset.json").read_text())
    data.update(
        cache_root=str(source), annotations_sha256=sha256(source / "annotations.json")
    )
    dump(a.out / "dataset.json", data)
    initial = root / "rf-detr-nano.pth"
    mc = RFDETRNanoConfig(
        resolution=960,
        num_classes=1,
        device="mps",
        pretrain_weights=str(initial),
        model_name="RFDETRNano",
    )
    tc = TrainConfig(
        dataset_dir=str(source),
        output_dir=str(a.out),
        batch_size=8,
        grad_accum_steps=1,
        epochs=cfg["max_epochs"],
        lr=cfg["lr"],
        lr_encoder=cfg["lr_encoder"],
        lr_scheduler="step",
        lr_drop=2,
        warmup_epochs=0,
        multi_scale=False,
        expanded_scales=False,
        use_ema=False,
        early_stopping=False,
        num_workers=0,
        tensorboard=False,
        seed=42,
        accelerator="mps",
    )
    module = RFDETRModelModule(mc, tc)
    model, criterion = module.model.to("mps"), module.criterion.to("mps")
    params = [
        p
        for p in get_param_dict(_namespace_from_configs(mc, tc), model)
        if p["params"].requires_grad
    ]
    optimizer = torch.optim.AdamW(params, lr=cfg["lr"], weight_decay=tc.weight_decay)
    base_lrs = [g["lr"] for g in optimizer.param_groups]
    base = dataset_class()(source, augment=False)
    augmented = dataset_class()(source, augment=True)

    def loader(ds, shuffle=False):
        return torch.utils.data.DataLoader(
            ds,
            batch_size=8,
            shuffle=shuffle,
            num_workers=0,
            drop_last=False,
            collate_fn=make_collate_fn(block_size=32),
        )

    def loss_value(pred, targets):
        losses = criterion(pred, targets)
        return sum(
            v * criterion.weight_dict[k]
            for k, v in losses.items()
            if k in criterion.weight_dict
        )

    def audit_train(mine):
        model.eval()
        criterion.eval()
        total = count = 0
        hard = []
        with torch.no_grad():
            for batch, targets in loader(base):
                batch = batch.to("mps")
                targets = [{k: v.to("mps") for k, v in t.items()} for t in targets]
                pred = model(batch)
                value = float(loss_value(pred, targets).cpu())
                total += value * len(targets)
                count += len(targets)
                if mine:
                    boxes = (pred["pred_boxes"] * 960).cpu().tolist()
                    scores = pred["pred_logits"].sigmoid()[:, :, 0].cpu().tolist()
                    for t, bs, ss in zip(targets, boxes, scores):
                        index = int(t["image_id"].cpu()[0])
                        if is_hard(bs, ss, clicks[index]):
                            hard.append(index)
        return total / count, hard

    history = []
    refreshes = []
    checkpoints = []
    steps = views = 0
    stopper = Plateau()
    torch.mps.synchronize()
    start = time.perf_counter()
    hard = []
    if a.replay:
        # The reset COCO ball head is not a trained checkpoint: defer mining.
        refreshes.append(
            {
                "after_epoch": 0,
                "hard_tiles": len(hard),
                "negative_tiles": sum(not records[i]["boxes"] for i in hard),
            }
        )
        dump(a.out / "hard_negative_indices.json", {"0": hard})
    reason = "epoch cap"
    for epoch in range(cfg["max_epochs"]):
        augmented.indices = list(range(len(records))) + (hard if a.replay else [])
        model.train()
        criterion.train()
        total = count = 0
        for batch, targets in loader(augmented, True):
            factor = min(1.0, (steps + 1) / 100) * (0.1 ** min(epoch // 2, 2))
            for group, lr in zip(optimizer.param_groups, base_lrs):
                group["lr"] = lr * factor
            batch = batch.to("mps")
            targets = [{k: v.to("mps") for k, v in t.items()} for t in targets]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_value(model(batch, targets), targets)
            value = float(loss.detach().cpu())
            if not math.isfinite(value):
                raise RuntimeError("nonfinite TRAIN loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)
            optimizer.step()
            steps += 1
            views += len(targets)
            count += len(targets)
            total += value * len(targets)
            if steps % 20 == 0 or steps == 1:
                print(
                    f"TRAIN epoch={epoch + 1} steps={steps} views={views} loss={value:.5f} minutes={(time.perf_counter() - start) / 60:.2f}",
                    flush=True,
                )
            if time.perf_counter() - start >= cfg["max_minutes_per_fit"] * 60:
                reason = "90-minute wall budget at optimizer-step boundary"
                break
        complete = count == len(augmented)
        row = {
            "epoch": epoch + 1,
            "complete": complete,
            "views": count,
            "augmented_mean_loss": total / count,
            "replay_tiles": len(hard) if a.replay else 0,
        }
        stop = False
        if complete and not reason.startswith("90"):
            audit_loss, new_hard = audit_train(a.replay and (epoch + 1) % 2 == 0)
            row["base_train_loss"] = audit_loss
            stop = stopper.update(audit_loss)
            if a.replay and (epoch + 1) % 2 == 0:
                hard = new_hard
                refreshes.append(
                    {
                        "after_epoch": epoch + 1,
                        "hard_tiles": len(hard),
                        "negative_tiles": sum(not records[i]["boxes"] for i in hard),
                    }
                )
                path = a.out / "hard_negative_indices.json"
                saved = json.loads(path.read_text())
                saved[str(epoch + 1)] = hard
                dump(path, saved)
            if (epoch + 1) % 2 == 0:
                path = a.out / f"epoch-{epoch + 1:02d}.pt"
                export_final(model, mc, tc, path, steps)
                checkpoints.append(
                    {
                        "epoch": epoch + 1,
                        "path": str(path),
                        "sha256": sha256(path),
                        "diagnostic_only": True,
                    }
                )
        history.append(row)
        dump(a.out / "train_history.json", history)
        dump(a.out / "replay_history.json", refreshes)
        print(f"EPOCH {row}", flush=True)
        if (
            reason.startswith("90")
            or time.perf_counter() - start >= cfg["max_minutes_per_fit"] * 60
        ):
            reason = "90-minute wall budget"
            break
        if stop:
            reason = "TRAIN-loss plateau: 3 complete epochs without >1% improvement"
            break
    torch.mps.synchronize()
    elapsed = time.perf_counter() - start
    weights = a.out / "weights.pt"
    export_final(model, mc, tc, weights, steps)
    fit = {
        "model": "RFDETRNano",
        "licence": LICENSE,
        "licence_url": LICENSE_URL,
        "versions": {
            "rfdetr": importlib.metadata.version("rfdetr"),
            "torch": torch.__version__,
        },
        "split": split,
        "labels_sha256": sha256(labels_path),
        "weights_sha256": sha256(weights),
        "initial_weights_sha256": sha256(initial),
        "resolution": 960,
        "batch": 8,
        "seed": 42,
        "config": cfg,
        "replay": a.replay,
        "replay_refreshes": refreshes,
        "history": history,
        "epochs_complete": sum(r["complete"] for r in history),
        "images_seen": views,
        "optimizer_steps": steps,
        "training_s": elapsed,
        "stop_reason": reason,
        "checkpoints": checkpoints,
        "checkpoint_selection": "FINAL",
        "protocol_sha256": sha256(HERE / "fixtures/round5_execution.json"),
    }
    dump(a.out / "fit_summary.json", fit)
    dump(a.out / "metrics.json", fit)
    print(f"COMPLETE {a.out.name} {elapsed / 60:.2f} minutes {reason}", flush=True)


if __name__ == "__main__":
    main()
