"""Apache-2.0 RF-DETR Nano: training-only stopping and final-checkpoint export."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import random
import time
from pathlib import Path

from ball_truth_kit import import_labels
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, HERE, dump, load_dataset, sha256
from compare_ball import load_measurements
from human_loop import frame_catalog
from rfdetr_data import dataset_class, prepare
from round2_protocol import validate_split

LICENSE = "Apache-2.0"
LICENSE_URL = "https://github.com/roboflow/rf-detr/blob/develop/LICENSE"


class TrainStop:
    """Only complete TRAIN epoch losses affect patience; time may end a partial epoch."""

    def __init__(self, patience):
        self.patience, self.stale, self.best = patience, 0, math.inf

    def epoch(self, loss):
        if not math.isfinite(loss):
            raise ValueError("non-finite TRAIN loss")
        if loss < self.best - 0.001:
            self.best, self.stale = loss, 0
        else:
            self.stale += 1
        return self.stale >= self.patience


def export_final(model, config, train_config, path, steps):
    import torch
    from rfdetr._namespace import _namespace_from_configs

    args = vars(_namespace_from_configs(config, train_config))
    args.update(class_names=["match_ball"], model_name="RFDETRNano")
    torch.save(
        {
            "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "args": args,
            "model_name": "RFDETRNano",
            "class_names": ["match_ball"],
            "final_optimizer_step": steps,
            "licence": LICENSE,
            "checkpoint_selection": "final parameters; no validation, no EMA, no best-checkpoint restore",
        },
        path,
    )


def train(a):
    import cv2
    import numpy as np
    import torch
    from rfdetr._namespace import _namespace_from_configs
    from rfdetr.config import RFDETRNanoConfig, TrainConfig
    from rfdetr.training import RFDETRModelModule
    from rfdetr.training.param_groups import get_param_dict
    from rfdetr.utilities.tensors import make_collate_fn

    if a.out.exists() and any(a.out.iterdir()):
        raise ValueError("output must be new/empty; preserve all prior fits")
    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS is required for this experiment")
    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    m = load_measurements()
    labels = import_labels(a.human_jsonl, frame_catalog(m))
    split = json.loads((HERE / "fixtures/round2_execution.json").read_text())["split"]
    prior = json.loads((HERE / "fixtures/human_execution.json").read_text())["split"]
    validate_split(split, m, labels, prior, allow_prior_tuning=True)
    manifest, clips = load_dataset(a.manifest, a.source)
    if manifest["frozen_set_id"] != m["frozen_set_id"] or any(
        not c["native_source"] or c["source_size"] != [1920, 1080] for c in clips
    ):
        raise ValueError("matching native 1920x1080 source required")
    if a.init:
        previous = json.loads((a.init.parent / "fit_summary.json").read_text())
        if (
            previous["split"] != split
            or previous["labels_sha256"] != sha256(a.human_jsonl)
            or previous["weights_sha256"] != sha256(a.init)
        ):
            raise ValueError("continuation provenance/split mismatch")
    a.out.mkdir(parents=True, exist_ok=True)
    data = prepare(m, clips, labels, a.out / "dataset", split, a.floor, a.pseudo)
    data.update(
        labels_sha256=sha256(a.human_jsonl),
        source_sha256=sha256(a.source),
        model_input_px=a.resolution,
    )
    dump(a.out / "dataset.json", data)
    initial = str(a.init) if a.init else str(a.out.parent / "rf-detr-nano.pth")
    mc = RFDETRNanoConfig(
        resolution=a.resolution,
        num_classes=1,
        device="mps",
        pretrain_weights=initial,
        model_name="RFDETRNano",
    )
    tc = TrainConfig(
        dataset_dir=str(a.out / "dataset"),
        output_dir=str(a.out),
        batch_size=a.batch,
        grad_accum_steps=1,
        epochs=a.epochs,
        lr=a.lr,
        lr_encoder=a.lr * 1.5,
        lr_scheduler="step",
        lr_drop=100,
        warmup_epochs=0,
        multi_scale=False,
        expanded_scales=False,
        use_ema=False,
        early_stopping=False,
        num_workers=0,
        tensorboard=False,
        seed=a.seed,
        accelerator="mps",
    )
    # RF-DETR model/criterion and official layer-wise AdamW parameter groups.
    # A small explicit loop avoids PTL's validation callbacks and checkpoint selection.
    module = RFDETRModelModule(mc, tc)
    model, criterion = module.model.to("mps"), module.criterion.to("mps")
    params = [
        p
        for p in get_param_dict(_namespace_from_configs(mc, tc), model)
        if p["params"].requires_grad
    ]
    optimizer = torch.optim.AdamW(params, lr=a.lr, weight_decay=tc.weight_decay)
    dataset = dataset_class()(a.out / "dataset", a.resolution)
    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=a.batch,
        shuffle=True,
        num_workers=0,
        drop_last=False,
        collate_fn=make_collate_fn(block_size=32),
    )
    initial_hash = sha256(initial)
    base_lrs = [g["lr"] for g in optimizer.param_groups]
    stopper, history, steps, images_seen = TrainStop(a.patience), [], 0, 0
    torch.mps.synchronize()
    start = time.perf_counter()
    reason = "epoch limit"
    for epoch in range(a.epochs):
        model.train()
        criterion.train()
        total, count = 0.0, 0
        complete = True
        for batch, targets in loader:
            # 100-step linear warmup, constant thereafter until epoch100 x0.1.
            factor = min(1.0, (steps + 1) / 100) * (1.0 if epoch < 100 else 0.1)
            for group, base in zip(optimizer.param_groups, base_lrs):
                group["lr"] = base * factor
            batch = batch.to("mps")
            targets = [
                {k: v.to("mps") for k, v in target.items()} for target in targets
            ]
            optimizer.zero_grad(set_to_none=True)
            losses = criterion(model(batch, targets), targets)
            loss = sum(
                v * criterion.weight_dict[k]
                for k, v in losses.items()
                if k in criterion.weight_dict
            )
            value = float(loss.detach().cpu())
            if not math.isfinite(value):
                raise RuntimeError("nonfinite TRAIN loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)
            optimizer.step()
            steps += 1
            count += len(targets)
            images_seen += len(targets)
            total += value * len(targets)
            torch.mps.synchronize()
            elapsed = time.perf_counter() - start
            if steps % 20 == 0 or steps == 1:
                print(
                    f"TRAIN epoch={epoch + 1} steps={steps} images={images_seen} loss={value:.5f} minutes={elapsed / 60:.2f}",
                    flush=True,
                )
            if elapsed >= a.train_minutes * 60:
                complete = count == len(dataset)
                reason = "time budget at optimizer-step boundary"
                break
        history.append(
            {
                "epoch": epoch + 1,
                "mean_train_loss": total / count,
                "images": count,
                "complete": complete,
            }
        )
        dump(a.out / "train_history.json", history)
        print(f"EPOCH {history[-1]}", flush=True)
        if reason.startswith("time"):
            break
        if stopper.epoch(total / count):
            reason = "TRAIN-loss patience"
            break
    torch.mps.synchronize()
    training_s = time.perf_counter() - start
    weights = a.out / "weights.pt"
    export_final(model, mc, tc, weights, steps)
    fit = {
        "model": "RFDETRNano",
        "licence": LICENSE,
        "licence_url": LICENSE_URL,
        "device": "mps",
        "resolution": a.resolution,
        "batch": a.batch,
        "gradient_accumulation": 1,
        "epochs_requested": a.epochs,
        "epochs_complete": sum(r["complete"] for r in history),
        "history": history,
        "optimizer_steps": steps,
        "images_seen": images_seen,
        "training_s": training_s,
        "budget_minutes": a.train_minutes,
        "stop_reason": reason,
        "patience": a.patience,
        "seed": a.seed,
        "lr": a.lr,
        "lr_encoder": a.lr * 1.5,
        "lr_schedule": "100 optimizer-step linear warmup, constant base LR thereafter; x0.1 at epoch100. AdamW wd=0.0001, official encoder layer decay0.8/component decay0.7; gradient norm clip0.1; FP32; no accumulation, EMA or validation.",
        "augmentation": "Horizontal flip p=0.5 only; fixed resolution. All 3012 TRAIN tiles once per full epoch, including negatives; last partial batch retained.",
        "floor_px": a.floor,
        "split": split,
        "labels_sha256": sha256(a.human_jsonl),
        "source_sha256": sha256(a.source),
        "initial_weights": initial,
        "initial_weights_sha256": initial_hash,
        "weights_sha256": sha256(weights),
        "checkpoint_selection": "FINAL optimizer step, never minimum train/validation checkpoint",
        "model_config": mc.model_dump(),
        "train_config": tc.model_dump(),
        "versions": {
            p: importlib.metadata.version(p)
            for p in ("rfdetr", "torch", "torchvision", "numpy", "pytorch-lightning")
        },
    }
    dump(a.out / "fit_summary.json", fit)
    dump(a.out / "metrics.json", {"status": "fit complete; evaluation deferred", **fit})
    print(
        f"FIT COMPLETE {a.out}: {training_s / 60:.2f}min, {steps} final steps",
        flush=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--human-jsonl", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--init", type=Path)
    p.add_argument("--resolution", type=int, default=640)
    p.add_argument("--floor", type=float, default=18.680435180664062)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--train-minutes", type=float, default=29)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pseudo", action="store_true")
    a = p.parse_args()
    if (
        a.resolution < 32
        or a.resolution % 32
        or min(a.batch, a.epochs, a.patience) < 1
        or not 0 < a.train_minutes <= 29
        or not 6 <= a.floor <= 48
        or not 0 < a.lr < 1
    ):
        p.error(
            "invalid resolution/floor/positive training options; budget <=29min leaves export margin"
        )
    train(a)


if __name__ == "__main__":
    main()
