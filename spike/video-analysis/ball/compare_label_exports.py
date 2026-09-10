"""Compare migrated label/review values by clip|t; never print coordinates."""

import argparse
import json
import math
from pathlib import Path

from common import sha256
from label_rule import migrate_row, N21


def rows(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("clip"), str)
            or type(row.get("t")) not in (int, float)
            or not math.isfinite(row["t"])
        ):
            raise ValueError("clip and finite timestamp required")
        key = f"{row['clip']}|{row['t']:.6f}"
        if key in result:
            raise ValueError(f"duplicate label key: {key}")
        result[key] = row
    return result


def same_value(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    return a == b


LABEL_FIELDS = (
    "visible",
    "x",
    "y",
    "match_ball",
    "source_accepted",
    "accepted_source",
    "accepted_score",
)
REVIEW_FIELDS = (
    "review_frame",
    "needs_any_ball_review",
    "needs_confirmation",
    "review_confirmed",
)


def canonical(row, catalog):
    migrated = migrate_row(row, catalog.get((row["clip"], round(row["t"], 6)), {}))
    migrated.setdefault("source_accepted", False)
    for field in REVIEW_FIELDS:
        migrated.setdefault(field, False)
    return migrated


def compare(old, new):
    before, after = rows(old), rows(new)
    # Use the committed catalog for the six n21 migration exceptions.
    catalog = {}
    if any(r["clip"] == N21 for r in (*before.values(), *after.values())):
        from compare_ball import load_measurements
        from human_loop import frame_catalog

        catalog = {
            (f["clip"], round(f["t"], 6)): f for f in frame_catalog(load_measurements())
        }
    shared = before.keys() & after.keys()
    added, removed = (
        sorted(after.keys() - before.keys()),
        sorted(before.keys() - after.keys()),
    )
    label_changes, review_changes, metadata_only, changed, unknown_changes = (
        [],
        [],
        [],
        [],
        [],
    )
    for key in sorted(shared):
        a, b = canonical(before[key], catalog), canonical(after[key], catalog)
        labels = [f for f in LABEL_FIELDS if not same_value(a.get(f), b.get(f))]
        reviews = [f for f in REVIEW_FIELDS if not same_value(a.get(f), b.get(f))]
        known = set(LABEL_FIELDS + REVIEW_FIELDS) | {
            "clip",
            "t",
            "schema_version",
            "updated_at",
        }
        unknown = [
            f
            for f in before[key].keys() | after[key].keys()
            if f not in known
            and (
                (f in before[key]) != (f in after[key])
                or not same_value(before[key].get(f), after[key].get(f))
            )
        ]
        if unknown:
            unknown_changes.append({"key": key, "fields": sorted(unknown)})
        if labels:
            label_changes.append(key)
        if reviews:
            review_changes.append(key)
        if labels or reviews or unknown:
            changed.append({"key": key, "fields": sorted(labels + reviews + unknown)})
        elif not same_value(before[key], after[key]):
            metadata_only.append(key)
    counts = {
        "label_changes": len(label_changes) + len(added) + len(removed),
        "review_state_changes": len(review_changes),
        "metadata_only": len(metadata_only),
        "unknown_fields": len(unknown_changes),
    }
    return {
        "old_sha256": sha256(old),
        "new_sha256": sha256(new),
        "counts": counts,
        "verdict": "differs"
        if counts["label_changes"]
        or counts["review_state_changes"]
        or counts["unknown_fields"]
        else "same",
        "added": added,
        "removed": removed,
        "changed": changed,
        "label_changes": label_changes,
        "review_state_changes": review_changes,
        "metadata_only": metadata_only,
        "unknown_fields": unknown_changes,
        "unchanged": len(shared) - len(changed),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("old", type=Path)
    p.add_argument("new", type=Path)
    a = p.parse_args()
    result = compare(a.old, a.new)
    print(json.dumps(result, indent=2))
    return int(result["verdict"] == "differs")


if __name__ == "__main__":
    raise SystemExit(main())
