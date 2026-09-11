"""Read-only CLI output preflight. Library writers retain their existing API."""

from pathlib import Path
import argparse
import sys

HERE = Path(__file__).resolve().parent


def guard_outputs(*outputs, inputs=(), parser=None):
    """Refuse unsafe destinations before work; check the whole batch before writes.

    Pass final filenames (not only prefixes), or a fresh output directory for
    a run that owns its descendants. Repeated writes within that new run are OK.
    Inputs include every JSONL read by the run, including suggestion files.
    """
    protected = {Path(p).resolve() for p in inputs if p is not None}
    fixtures = (HERE / "fixtures").resolve()
    labels = (Path.home() / "codex-runs").resolve()
    seen = set()
    for raw in outputs:
        if raw is None:
            continue
        path = Path(raw)
        resolved = path.resolve()
        reason = None
        if resolved.is_relative_to(fixtures):
            reason = "fixture paths are read-only"
        elif resolved in protected:
            reason = "output aliases an input"
        elif resolved.parent == labels and resolved.match("ball-human-truth*.jsonl"):
            reason = "protected label filename"
        elif path.exists() or path.is_symlink():
            reason = "output already exists"
        elif any(
            resolved.is_relative_to(p) or p.is_relative_to(resolved) for p in seen
        ):
            reason = "outputs overlap (identical, ancestor or descendant destinations)"
        elif any(not p.is_dir() and resolved.is_relative_to(p) for p in protected):
            reason = "output is nested under an input file"
        elif any(p.is_relative_to(resolved) for p in protected):
            reason = "output directory contains an input"
        # Resolution hides dangling symlinks, so inspect the supplied ancestry too.
        if reason is None and any(
            (parent.exists() or parent.is_symlink()) and not parent.is_dir()
            for destination in (path.absolute(), resolved)
            for parent in destination.parents
        ):
            reason = "output ancestor is not a directory"
        if reason:
            message = f"Refusing output {path}: {reason}; choose a new destination"
            if parser is not None:
                parser.error(message)
            raise SystemExit(message)
        seen.add(resolved)
    return tuple(seen)


def guard_frozen_entrypoint():
    """Preflight four byte-frozen historical CLIs on their common-module import.

    Their exact source hashes are evidence: do not rewrite them or their fixtures.
    This applies only to direct execution of these files, never library imports.
    The real parser still validates all options and prints help as before.
    """
    entry = Path(sys.argv[0]).resolve()
    names = {
        "train_tiny_ball.py",
        "train_tiny_ball_rfdetr.py",
        "train_round5.py",
        "run_round3.py",
    }
    if (
        entry.parent != HERE
        or entry.name not in names
        or any(a in sys.argv[1:] for a in ("--help", "-h"))
    ):
        return
    home = Path.home()
    if entry.name == "run_round3.py":
        root = home / "models/tinyball"
        guard_outputs(
            root / "round3-fit-state.json",
            *(root / f"mj-r3-{c}" for c in "ab"),
            *(home / f"codex-runs/ball-mj-r3-{c}.log" for c in "ab"),
        )
        return
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--out", type=Path)
    p.add_argument(
        "--human-jsonl", type=Path, default=home / "codex-runs/ball-human-truth.jsonl"
    )
    p.add_argument("--init", type=Path, default=home / "models/tinyball/yolo11n.pt")
    for option in ("--split-json", "--manifest", "--source"):
        p.add_argument(option, type=Path)
    args, _ = p.parse_known_args()
    if args.out is not None and (args.out.exists() or args.out.is_symlink()):
        p.error(
            "Refusing output: output already exists; pick a new fit dir name (even an empty directory is a prior destination)"
        )
    # The historical YOLO CLI explicitly downloads only this missing cache file.
    initial_download = (
        [args.init]
        if entry.name == "train_tiny_ball.py"
        and args.init == home / "models/tinyball/yolo11n.pt"
        and not args.init.exists()
        else []
    )
    guard_outputs(
        args.out,
        *initial_download,
        inputs=[
            args.human_jsonl,
            args.split_json,
            args.manifest,
            args.source,
            *([] if initial_download else [args.init]),
        ],
        parser=p,
    )
