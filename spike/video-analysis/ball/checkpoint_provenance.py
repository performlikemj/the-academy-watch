"""Bind saved passes to independent fit declarations, never their own envelopes."""

from __future__ import annotations

import json
from pathlib import Path

from common import sha256


FIT_DIRECTORIES = {
    "yolo-r2-b": "mj-r2-b",
    "rf-b": "mj-r4-rf-b",
    "rf-r5-a": "mj-r5-rf-a",
    "rf-r5-b": "mj-r5-rf-b",
}
FINAL_PASSES = {
    "yolo-r2-b": "r5-yolo-low",
    "rf-b": "r5-rfb-low",
    "rf-r5-a": "r5-rf-a-final-low",
    "rf-r5-b": "r5-rf-b-final-low",
}


def require_hash(expected, actual, context):
    if expected != actual:
        raise ValueError(
            f"{context}: checkpoint hash mismatch; declared={expected}; actual={actual}"
        )


def checkpoint_declaration(fit, epoch=None):
    if epoch is None:
        return fit["weights_sha256"]
    entries = [c for c in fit.get("checkpoints", []) if c["epoch"] == epoch]
    if len(entries) != 1:
        raise ValueError(f"expected one declared checkpoint for epoch-{epoch}")
    return entries[0]["sha256"]


def validate_model(weights, epoch=None):
    """FINAL by default; diagnostics require an explicitly declared epoch.

    Never infer the expected identity from whichever weights file was selected.
    """
    weights = Path(weights)
    fit = json.loads((weights.parent / "fit_summary.json").read_text())
    expected = checkpoint_declaration(fit, epoch)
    require_hash(expected, sha256(weights), str(weights))
    return fit, expected


def validate_saved_passes(paths, root=None):
    """Validate finals and 'candidate / epoch-N' passes before any scoring.

    The candidate registry selects the fit summary independently of the supplied
    detections path and envelope. Scoring needs declarations, not installed models.
    """
    root = Path(root) if root is not None else Path.home() / "models/tinyball"
    for name, path in paths.items():
        candidate, separator, diagnostic = name.partition(" / epoch-")
        if candidate not in FIT_DIRECTORIES:
            raise ValueError(f"no registered fit summary for {name}")
        epoch = int(diagnostic) if separator else None
        fit = json.loads(
            (root / FIT_DIRECTORIES[candidate] / "fit_summary.json").read_text()
        )
        payload = json.loads(Path(path).read_text())
        require_hash(
            checkpoint_declaration(fit, epoch), payload["weights_sha256"], name
        )


def declared_passes(root):
    """Enumerate all finals and every declared diagnostic, failing if missing."""
    paths = {k: root / v / "detections.json" for k, v in FINAL_PASSES.items()}
    for candidate, directory in FIT_DIRECTORIES.items():
        fit = json.loads((root / directory / "fit_summary.json").read_text())
        for checkpoint in fit.get("checkpoints", []):
            epoch = checkpoint["epoch"]
            if candidate not in {"rf-r5-a", "rf-r5-b"}:
                raise ValueError(f"no diagnostic pass convention for {candidate}")
            paths[f"{candidate} / epoch-{epoch}"] = (
                root / f"r5-rf-{candidate[-1]}-epoch-{epoch:02d}-low/detections.json"
            )
    return paths


def audit_saved_passes(root):
    """Recompute on-disk hashes; retain only provenance, never model/detection data."""
    rows = []
    for name, path in declared_passes(root).items():
        candidate, separator, diagnostic = name.partition(" / epoch-")
        directory = root / FIT_DIRECTORIES[candidate]
        fit = json.loads((directory / "fit_summary.json").read_text())
        epoch = int(diagnostic) if separator else None
        weights = directory / "weights.pt"
        if epoch is not None:
            entry = next(c for c in fit["checkpoints"] if c["epoch"] == epoch)
            weights = Path(entry["path"])
            if not weights.is_absolute():
                weights = directory / weights
        expected = checkpoint_declaration(fit, epoch)
        recorded = json.loads(path.read_text())["weights_sha256"]
        actual = sha256(weights)
        rows.append(
            {
                "pass_id": name,
                "weights_path": str(weights),
                "declared_sha256": expected,
                "recorded_sha256": recorded,
                "on_disk_sha256": actual,
                "status": "MATCH" if expected == recorded == actual else "MISMATCH",
            }
        )
    return rows
