"""Strict source/schedule validation for locally trained, saved candidates."""

from __future__ import annotations
import json
import math
import re
from pathlib import Path


def load_extra(specs, measurements, *, allow_synthetic=False):
    extras = {}
    expected_ids = set(measurements["outputs"]["rf_full"])
    source_hash = measurements["runs"]["rf_full"]["source_sha256"]
    for spec in specs:
        name, sep, path = spec.partition("=")
        if (
            not sep
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
            or name in measurements["outputs"]
            or name in extras
        ):
            raise ValueError("extra detections require a unique name=path")
        data = json.loads(Path(path).read_text())
        if (
            data.get("schema_version") != 1
            or data.get("frozen_set_id") != measurements["frozen_set_id"]
            or data.get("source_sha256") != source_hash
            or data.get("source_size") != [1920, 1080]
        ):
            raise ValueError("extra candidate provenance mismatch")
        if (
            type(data.get("threshold")) not in (int, float)
            or not math.isfinite(data["threshold"])
            or not 0 <= data["threshold"] <= 1
        ):
            raise ValueError("invalid saved threshold")
        if (
            type(data.get("synthetic_smoke")) is not bool
            or set(data["outputs"]) != expected_ids
        ):
            raise ValueError("all clips and explicit synthetic status required")
        if data["synthetic_smoke"] and not allow_synthetic:
            raise ValueError(
                f"synthetic extra {name!r} refused; use --allow-synthetic for badged diagnostics"
            )
        for cid, raw in data["outputs"].items():
            expected = measurements["outputs"]["rf_full"][cid]
            if (
                type(raw["wall_s"]) not in (int, float)
                or not math.isfinite(raw["wall_s"])
                or raw["wall_s"] <= 0
                or raw["duration_s"] != expected["duration_s"]
            ):
                raise ValueError("invalid extra timing")
            if [
                (r["t"], r["frame_index"], r["sample_index"]) for r in raw["frames"]
            ] != [
                (r["t"], r["frame_index"], r["sample_index"])
                for r in expected["frames"]
            ]:
                raise ValueError("extra sample schedule mismatch")
            for row in raw["frames"]:
                for d in row["detections"]:
                    if (
                        len(d["xy"]) != 2
                        or len(d["box"]) != 4
                        or any(
                            type(v) not in (int, float) or not math.isfinite(v)
                            for v in [
                                *d["xy"],
                                *d["box"],
                                d["confidence"],
                                d["size_px"],
                            ]
                        )
                    ):
                        raise ValueError("invalid extra detection numbers")
                    x, y = d["xy"]
                    a, b, c, e = d["box"]
                    if not (
                        0 <= x < 1920
                        and 0 <= y < 1080
                        and 0 <= a < c <= 1920
                        and 0 <= b < e <= 1080
                        and 0 <= d["confidence"] <= 1
                        and d["size_px"] > 0
                    ):
                        raise ValueError("invalid extra detection geometry")
                    if abs(x - (a + c) / 2) > 0.001 or abs(y - (b + e) / 2) > 0.001:
                        raise ValueError("extra centre/box mismatch")
        extras[name] = data
    return extras
