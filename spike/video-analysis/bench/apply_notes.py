#!/usr/bin/env python3
"""Generate a human-note form or apply filled lines to local, untracked truth."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

try:
    from .provenance import load_truth_snapshot
except ImportError:  # pragma: no cover
    from provenance import load_truth_snapshot

LINE = re.compile(
    r"^- `(?P<id>[^`]+)` \| window: (?P<start>[\d.]+)–(?P<end>[\d.]+) s \| jersey: #(?P<jersey>\d+) \| kit: (?P<kit>[^|]+) \| note:(?P<note>.*)$"
)


def template(truths: list[dict]) -> str:
    lines = [
        "# Marked-player notes (MJ, about 30 minutes)",
        "",
        "Watch each marked clip and fill `note:` with one plain sentence of what the player does. Leave uncertain clips blank. Blank lines preserve existing notes; no model writes these notes.",
        "",
    ]
    for truth in truths:
        window = truth["window"]
        lines.append(
            f"- `{truth['clip_id']}` | window: {window['start_s']:.2f}–{window['end_s']:.2f} s | jersey: #{truth['jersey_number']} | kit: {truth['kit_color']} | note:"
        )
    return "\n".join(lines) + "\n"


def load_truths(manifest_path: Path) -> list[tuple[Path, dict]]:
    manifest = json.loads(manifest_path.read_text())
    root = manifest_path.resolve().parent
    pairs = []
    for entry in manifest["clips"]:
        path = (root / entry["truth"]).resolve()
        if path.parent != root / "truth" or path.suffix != ".json":
            raise ValueError("truth must be a local truth/*.json file")
        truth = json.loads(path.read_text())
        if truth["clip_id"] != entry["clip_id"]:
            raise ValueError("truth clip ID differs from manifest")
        pairs.append((path, truth))
    return pairs


def require_local_untracked(path: Path) -> None:
    repo = subprocess.run(
        ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if repo.returncode:
        return  # External local frozen datasets are outside the Git worktree.
    root = Path(repo.stdout.strip())
    relative = str(path.relative_to(root))
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
    )
    ignored = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", "--", relative],
        capture_output=True,
    )
    if tracked.returncode == 0 or ignored.returncode != 0:
        raise ValueError("refusing to write tracked or nonignored truth")


def apply_notes(notes_path: Path, manifest_path: Path) -> int:
    truths = {
        truth["clip_id"]: (path, truth) for path, truth in load_truths(manifest_path)
    }
    updates, seen = [], set()
    for line in notes_path.read_text().splitlines():
        if not line.startswith("- `"):
            continue
        match = LINE.fullmatch(line)
        if match is None:
            raise ValueError("malformed note line")
        row = match.groupdict()
        cid = row["id"]
        if cid not in truths or cid in seen:
            raise ValueError("unknown or duplicate clip ID")
        seen.add(cid)
        path, truth = truths[cid]
        if (
            int(row["jersey"]) != truth["jersey_number"]
            or row["kit"].strip() != truth["kit_color"]
            or any(
                abs(float(row[key]) - truth["window"][f"{key}_s"]) > 0.0051
                for key in ("start", "end")
            )
        ):
            raise ValueError("note identity/window does not match frozen truth")
        note = row["note"].strip()
        if note:
            if re.search(r"[.!?]\s+\S", note):
                raise ValueError("note must be one plain sentence")
            require_local_untracked(path)
            updates.append((path, {**truth, "human_note": note}))
    if seen != set(truths):
        raise ValueError("notes must contain exactly one line per manifest clip")
    # Validate the complete form before the first write; replace each file atomically.
    for path, truth in updates:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, prefix=".notes-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(truth, indent=2, sort_keys=True) + "\n")
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return len(updates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--notes", type=Path, default=Path(__file__).with_name("notes_template.md")
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="create a blank form (refuses to overwrite)",
    )
    args = parser.parse_args(argv)
    if args.generate:
        with args.notes.open("x") as handle:
            handle.write(template([truth for _, truth in load_truths(args.manifest)]))
        print(f"Wrote {args.notes}")
    else:
        print(f"Applied {apply_notes(args.notes, args.manifest)} human notes")
        _, hashes = load_truth_snapshot(args.manifest)
        print(json.dumps(hashes, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
