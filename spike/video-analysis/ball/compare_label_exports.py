"""Compare raw JSONL row values by clip|t, without editing or migrating either file."""

import argparse
import json
import math
from pathlib import Path

from common import sha256


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


def compare(old, new):
    before, after = rows(old), rows(new)
    shared = before.keys() & after.keys()
    return {
        "old_sha256": sha256(old),
        "new_sha256": sha256(new),
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": [
            {
                "key": key,
                "fields": sorted(
                    k
                    for k in before[key].keys() | after[key].keys()
                    if (k in before[key]) != (k in after[key])
                    or not same_value(before[key].get(k), after[key].get(k))
                ),
            }
            for key in sorted(shared)
            if not same_value(before[key], after[key])
        ],
        "unchanged": sum(same_value(before[key], after[key]) for key in shared),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("old", type=Path)
    p.add_argument("new", type=Path)
    a = p.parse_args()
    result = compare(a.old, a.new)
    print(
        json.dumps(
            {
                "counts": {k: len(result[k]) for k in ("added", "removed", "changed")},
                **result,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
