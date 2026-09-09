"""Hash the current truth bytes separately from the immutable frozen-set identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _hash_mapping(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def load_truth_snapshot(manifest_path: Path) -> tuple[dict[str, dict], dict[str, str]]:
    """Read all manifest truth files once; hash sorted ID→byte-digest and ID→note maps."""
    manifest = json.loads(manifest_path.read_text())
    truths, digests = {}, {}
    for entry in manifest["clips"]:
        cid = entry["clip_id"]
        if cid in truths:
            raise ValueError("duplicate clip ID in truth snapshot")
        raw = (manifest_path.parent / entry["truth"]).read_bytes()
        truths[cid] = json.loads(raw)
        digests[cid] = hashlib.sha256(raw).hexdigest()
    return truths, {
        "truth_set_sha256_after_notes": _hash_mapping(digests),
        "human_notes_sha256": _hash_mapping(
            {cid: truth.get("human_note") for cid, truth in truths.items()}
        ),
    }


def thinking_rate(results: list[dict]) -> float | None:
    """Fraction of all attempts explicitly recorded as using the thinking field."""
    return (
        round(
            sum(result.get("from_thinking") is True for result in results)
            / len(results),
            4,
        )
        if results
        else None
    )
