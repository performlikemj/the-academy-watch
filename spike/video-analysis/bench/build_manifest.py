#!/usr/bin/env python3
"""Build the frozen 20-clip Film Room evidence set from local match 4."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
VIDEO_ANALYSIS_DIR = BENCH_DIR.parent
REPO_ROOT = BENCH_DIR.parents[2]
BACKEND_DIR = REPO_ROOT / "academy-watch-backend"
DEFAULT_OUTPUT = BENCH_DIR / "frozen"
SELECTION_SEED = 20260901
CLIP_COUNT = 20
MIN_PLAYERS = 8
MIN_WINDOW_S = 3.0
FOOTAGE_HASH_PREFIX_LENGTH = 16

if str(VIDEO_ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(VIDEO_ANALYSIS_DIR))

from qwen_match_analysis import ffprobe_argv  # noqa: E402

log = logging.getLogger("build_evidence_manifest")


def _json_dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truth_set_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_main_root() -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = (REPO_ROOT / common).resolve()
    return common.parent if common.name == ".git" else None


def _load_environment(env_file: Path | None) -> None:
    from dotenv import load_dotenv

    candidates = [env_file] if env_file is not None else [BACKEND_DIR / ".env"]
    main_root = _git_main_root()
    if main_root is not None:
        candidates.append(main_root / "academy-watch-backend" / ".env")
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            load_dotenv(candidate, override=False)
            break
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")


def _load_match(match_id: int, env_file: Path | None):
    _load_environment(env_file)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import text

    from src.main import app
    from src.models.league import db
    from src.models.video import VideoMatch, VideoTracklet
    from src.services import video_dev_artifacts, video_reels

    context = app.app_context()
    context.push()
    try:
        db.session.execute(text("SET TRANSACTION READ ONLY"))
        match = db.session.get(VideoMatch, match_id)
        if match is None:
            raise RuntimeError(f"local video match {match_id} does not exist")
        if match.status != "finalized":
            raise RuntimeError(
                f"video match {match_id} must be finalized, got {match.status!r}"
            )
        artifacts = video_dev_artifacts.local_artifacts(match)
        if not artifacts:
            raise RuntimeError(f"video match {match_id} has no local capture artifacts")
        tracklets = list(VideoTracklet.query.filter_by(video_match_id=match_id).all())
        fragment_spans = video_dev_artifacts.fragment_spans(artifacts)
        reel = video_reels.build_reel_payload(
            match,
            list(match.roster_entries),
            tracklets,
            fragment_spans,
            crop_entity_ids=video_dev_artifacts.crop_entity_ids(artifacts),
        )
        # Detach the scalar/JSON state used by the builder before closing the
        # read-only session. Player names are deliberately never copied.
        match_data = {
            "id": match.id,
            "our_kit_color": match.our_kit_color,
            "capture_meta": match.capture_meta,
        }
        tracklet_data = {
            tracklet.id: {
                "id": tracklet.id,
                "kind": tracklet.kind,
                "roster_entry_id": tracklet.roster_entry_id,
                "review_action": tracklet.review_action,
                "tag_source": tracklet.tag_source,
                "evidence": tracklet.evidence
                if isinstance(tracklet.evidence, dict)
                else {},
                "bbox_track": video_dev_artifacts.tracklet_bbox_track(
                    tracklet, artifacts
                ),
            }
            for tracklet in tracklets
        }
        return match_data, dict(artifacts), fragment_spans, reel, tracklet_data
    finally:
        db.session.rollback()
        db.session.remove()
        context.pop()


def _probe_video(video_path: Path, ffprobe_path: str) -> tuple[float, list[int]]:
    duration_result = subprocess.run(
        ffprobe_argv(ffprobe_path, video_path),
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(duration_result.stdout.strip())
    result = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise RuntimeError(f"ffprobe found no video stream in {video_path}")
    return duration, [int(streams[0]["width"]), int(streams[0]["height"])]


def _window_vote_reads(
    tracklet: dict, fragment_spans: dict, start_s: float, end_s: float
) -> int:
    evidence = tracklet["evidence"]
    votes = evidence.get("votes") if isinstance(evidence.get("votes"), dict) else {}
    total = 0
    for raw_id in evidence.get("member_fragment_ids") or []:
        try:
            fragment_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        span = fragment_spans.get(fragment_id)
        if not span or float(span[1]) < start_s or float(span[0]) > end_s:
            continue
        fragment_votes = votes.get(str(fragment_id), votes.get(fragment_id, {}))
        if not isinstance(fragment_votes, dict):
            continue
        for count in fragment_votes.values():
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                total += count
    return total


def _clip_id(
    match_id: int, jersey_number: int, tracklet_id: int, start_s: float, end_s: float
) -> str:
    return f"m{match_id:02d}-n{jersey_number:02d}-t{tracklet_id}-{round(start_s * 100):06d}-{round(end_s * 100):06d}"


def build_candidates(
    match_id: int,
    reel: dict,
    tracklets: dict[int, dict],
    fragment_spans: dict,
    frame_size: list[int],
) -> list[dict]:
    frame_area = frame_size[0] * frame_size[1]
    rng = random.Random(SELECTION_SEED)
    candidates = []
    for player in reel.get("players") or []:
        for window in player.get("windows") or []:
            start_s = float(window["start_s"])
            end_s = float(window["end_s"])
            if end_s - start_s < MIN_WINDOW_S:
                continue
            tracklet_id = int(window["tracklet_id"])
            tracklet = tracklets.get(tracklet_id)
            if (
                tracklet is None
                or tracklet["roster_entry_id"] != player["roster_entry_id"]
            ):
                continue
            box_track = [
                row
                for row in tracklet["bbox_track"]
                if start_s - 0.02 <= float(row[0]) <= end_s + 0.02
            ]
            if not box_track:
                continue
            ratios = [
                max(0, row[3] - row[1]) * max(0, row[4] - row[2]) / frame_area
                for row in box_track
            ]
            jersey_number = int(player["jersey_number"])
            candidates.append(
                {
                    "clip_id": _clip_id(
                        match_id, jersey_number, tracklet_id, start_s, end_s
                    ),
                    "roster_entry_id": int(player["roster_entry_id"]),
                    "jersey_number": jersey_number,
                    "tracklet_id": tracklet_id,
                    "start_s": start_s,
                    "end_s": end_s,
                    "rank": int(window["rank"]),
                    "box_track": box_track,
                    "median_box_area_ratio": statistics.median(ratios),
                    "number_read_count": _window_vote_reads(
                        tracklet, fragment_spans, start_s, end_s
                    ),
                    "review_action": tracklet["review_action"],
                    "tie_breaker": rng.random(),
                }
            )
    return sorted(candidates, key=lambda row: row["clip_id"])


def _stored_set_piece_times(value: object) -> list[float]:
    times = []
    if isinstance(value, dict):
        if value.get("phase_of_play") == "set-piece":
            for key in ("timestamp_s", "time_s", "t", "start_s"):
                raw = value.get(key)
                if (
                    isinstance(raw, (int, float))
                    and not isinstance(raw, bool)
                    and math.isfinite(float(raw))
                ):
                    times.append(float(raw))
                    break
        for nested in value.values():
            times.extend(_stored_set_piece_times(nested))
    elif isinstance(value, list):
        for nested in value:
            times.extend(_stored_set_piece_times(nested))
    return times


def select_candidates(
    candidates: list[dict], capture_meta: dict
) -> tuple[list[dict], dict]:
    selected: dict[str, dict] = {}

    def add(candidate: dict, reason: str) -> None:
        existing = selected.get(candidate["clip_id"])
        if existing is None:
            existing = {**candidate, "selection_reasons": []}
            selected[candidate["clip_id"]] = existing
        if reason not in existing["selection_reasons"]:
            existing["selection_reasons"].append(reason)

    corrected = sorted(
        (candidate for candidate in candidates if candidate["tracklet_id"] == 1411),
        key=lambda row: (row["rank"], row["start_s"]),
    )
    if not corrected:
        raise RuntimeError(
            "required human-corrected chain 1411 has no eligible reel window"
        )
    add(
        corrected[0], "required human-corrected chain 1411 bound to uploader roster #12"
    )

    # The identity pipeline requires at least two agreeing reads. A window with
    # fewer than two stored number reads therefore has no trustworthy readable
    # number, even if one noisy single-frame OCR/VLM guess exists.
    unreadable = sorted(
        (candidate for candidate in candidates if candidate["number_read_count"] < 2),
        key=lambda row: (row["median_box_area_ratio"], row["rank"], row["clip_id"]),
    )
    if len(unreadable) < 2:
        raise RuntimeError(
            "fewer than two tracked windows fall below the two-read jersey evidence gate"
        )
    for candidate in unreadable[:2]:
        add(
            candidate,
            "required number-never-reliably-readable window "
            f"({candidate['number_read_count']} stored read; below the two-read identity gate)",
        )

    far_side = sorted(
        candidates, key=lambda row: (row["median_box_area_ratio"], row["clip_id"])
    )[:2]
    for candidate in far_side:
        add(
            candidate,
            f"required far-side/panning window (median player-box area {candidate['median_box_area_ratio']:.6f} of frame)",
        )

    set_piece_times = _stored_set_piece_times(capture_meta)
    set_piece_status = (
        "skipped: no timestamped phase_of_play=set-piece stored observation"
    )
    if set_piece_times:
        matches = [
            (
                abs((candidate["start_s"] + candidate["end_s"]) / 2 - timestamp),
                candidate,
            )
            for timestamp in set_piece_times
            for candidate in candidates
            if candidate["start_s"] <= timestamp <= candidate["end_s"]
        ]
        if matches:
            _distance, candidate = min(
                matches, key=lambda item: (item[0], item[1]["clip_id"])
            )
            add(candidate, "required stored phase_of_play=set-piece observation")
            set_piece_status = "included"
        else:
            set_piece_status = "skipped: stored set-piece timestamps do not overlap an eligible reel window"

    best_by_player = {}
    for candidate in sorted(
        candidates,
        key=lambda row: (row["rank"], -len(row["box_track"]), row["clip_id"]),
    ):
        best_by_player.setdefault(candidate["roster_entry_id"], candidate)
    for candidate in sorted(
        best_by_player.values(), key=lambda row: (row["tie_breaker"], row["clip_id"])
    ):
        covered = {row["roster_entry_id"] for row in selected.values()}
        if len(covered) >= MIN_PLAYERS:
            break
        if candidate["roster_entry_id"] not in covered:
            add(candidate, "seeded player-coverage selection")

    for candidate in sorted(
        candidates, key=lambda row: (row["tie_breaker"], row["clip_id"])
    ):
        if len(selected) >= CLIP_COUNT:
            break
        if candidate["clip_id"] in selected:
            continue
        add(candidate, "fixed-seed diversity fill")

    output = sorted(selected.values(), key=lambda row: row["clip_id"])
    if len(output) != CLIP_COUNT:
        raise RuntimeError(
            f"selection produced {len(output)} clips, expected {CLIP_COUNT}"
        )
    player_count = len({candidate["roster_entry_id"] for candidate in output})
    if player_count < MIN_PLAYERS:
        raise RuntimeError(
            f"selection covers {player_count} players, expected at least {MIN_PLAYERS}"
        )
    return output, {
        "chain_1411": "included",
        "far_side_panning": sum(
            any(
                reason.startswith("required far-side")
                for reason in candidate["selection_reasons"]
            )
            for candidate in output
        ),
        "number_never_readable": sum(
            any(
                reason.startswith("required number-never-reliably-readable")
                for reason in candidate["selection_reasons"]
            )
            for candidate in output
        ),
        "set_piece": set_piece_status,
    }


def _keyframe_near(video: Path, start_s: float, ffprobe_path: str) -> bool:
    interval_start = max(0.0, start_s - 1.0)
    result = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-skip_frame",
            "nokey",
            "-read_intervals",
            f"{interval_start:.3f}%+2",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "csv=p=0",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    timestamps = []
    for line in result.stdout.splitlines():
        try:
            timestamps.append(float(line.strip().rstrip(",")))
        except ValueError:
            continue
    return any(abs(timestamp - start_s) <= 0.08 for timestamp in timestamps)


def _cut_clip(
    source: Path,
    output: Path,
    start_s: float,
    end_s: float,
    frame_size: list[int],
    ffmpeg_path: str,
    ffprobe_path: str,
    *,
    force_reencode: bool = False,
) -> str:
    duration = end_s - start_s
    output.parent.mkdir(parents=True, exist_ok=True)
    mode = (
        "stream_copy"
        if not force_reencode and _keyframe_near(source, start_s, ffprobe_path)
        else "reencoded"
    )
    if mode == "stream_copy":
        command = [
            ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start_s:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(output),
        ]
    else:
        command = [
            ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start_s:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ]
    subprocess.run(command, check=True)
    actual_duration, actual_size = _probe_video(output, ffprobe_path)
    if actual_size != frame_size:
        raise RuntimeError(
            f"clip {output.name} changed resolution from {frame_size} to {actual_size}"
        )
    if abs(actual_duration - duration) > 0.35:
        if mode == "stream_copy":
            output.unlink(missing_ok=True)
            return _cut_clip(
                source,
                output,
                start_s,
                end_s,
                frame_size,
                ffmpeg_path,
                ffprobe_path,
                force_reencode=True,
            )
        raise RuntimeError(
            f"clip {output.name} duration {actual_duration:.3f}s differs from requested {duration:.3f}s"
        )
    return mode


def _soccertrack_paths(footage_path: Path, override: Path | None) -> dict[str, str]:
    directory = override or footage_path.parent.parent / "soccertrack-v2"
    paths = {
        "video": directory / "117093_calibrated_1st.mp4",
        "homography": directory / "117093_homography.npy",
        "keypoints": directory / "117093_keypoints.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise RuntimeError(f"SoccerTrack v2 slice is incomplete: {', '.join(missing)}")
    return {key: str(path.resolve()) for key, path in paths.items()}


def build_manifest(args: argparse.Namespace) -> dict:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError("ffmpeg and ffprobe must be available on PATH")

    match, artifacts, fragment_spans, reel, tracklets = _load_match(
        args.match_id, args.env_file
    )
    footage_raw = artifacts.get("footage") or artifacts.get("video")
    if not footage_raw:
        raise RuntimeError("capture_meta.local has no footage/video path")
    footage = Path(footage_raw)
    if not footage.exists():
        raise RuntimeError(f"local footage does not exist: {footage}")
    source_duration, frame_size = _probe_video(footage, ffprobe_path)
    candidates = build_candidates(
        args.match_id, reel, tracklets, fragment_spans, frame_size
    )
    selected, constraints = select_candidates(
        candidates, match.get("capture_meta") or {}
    )

    output_dir = args.output.resolve()
    clips_dir = output_dir / "clips"
    truth_dir = output_dir / "truth"
    clips_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    truth_paths = []
    manifest_clips = []
    for candidate in selected:
        clip_id = candidate["clip_id"]
        clip_path = clips_dir / f"{clip_id}.mp4"
        cut_mode = _cut_clip(
            footage,
            clip_path,
            candidate["start_s"],
            candidate["end_s"],
            frame_size,
            ffmpeg_path,
            ffprobe_path,
        )
        truth = {
            "clip_id": clip_id,
            "match_id": args.match_id,
            "roster_entry_id": candidate["roster_entry_id"],
            "jersey_number": candidate["jersey_number"],
            "kit_color": match["our_kit_color"],
            "tracklet_id": candidate["tracklet_id"],
            "window": {"start_s": candidate["start_s"], "end_s": candidate["end_s"]},
            "box_track": candidate["box_track"],
            "frame_size": frame_size,
            "human_note": None,
        }
        truth_path = truth_dir / f"{clip_id}.json"
        _json_dump(truth_path, truth)
        truth_paths.append(truth_path)
        manifest_clips.append(
            {
                "clip_id": clip_id,
                "clip": str(clip_path.relative_to(output_dir)),
                "truth": str(truth_path.relative_to(output_dir)),
                "roster_entry_id": candidate["roster_entry_id"],
                "jersey_number": candidate["jersey_number"],
                "tracklet_id": candidate["tracklet_id"],
                "window": truth["window"],
                "duration_s": round(candidate["end_s"] - candidate["start_s"], 2),
                "selection_reason": "; ".join(candidate["selection_reasons"]),
                "number_read_count": candidate["number_read_count"],
                "median_box_area_ratio": round(candidate["median_box_area_ratio"], 8),
                "cut_mode": cut_mode,
            }
        )

    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest = {
        "schema_version": "film-room-evidence-manifest-v1",
        "match_id": args.match_id,
        "selection_seed": SELECTION_SEED,
        "frozen_set_id": _truth_set_hash(truth_paths),
        "footage_sha256_prefix": _sha256(footage.resolve())[
            :FOOTAGE_HASH_PREFIX_LENGTH
        ],
        "git_commit": git_commit,
        "source_duration_s": round(source_duration, 3),
        "frame_size": frame_size,
        "clip_count": len(manifest_clips),
        "player_count": len({clip["roster_entry_id"] for clip in manifest_clips}),
        "total_clip_s": round(sum(clip["duration_s"] for clip in manifest_clips), 2),
        "constraints": constraints,
        "clips": manifest_clips,
        "external": {
            "soccertrack_v2": _soccertrack_paths(footage, args.soccertrack_dir)
        },
    }
    _json_dump(output_dir / "manifest.json", manifest)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", type=int, default=4)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--soccertrack-dir", type=Path)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    manifest = build_manifest(_parser().parse_args())
    print(f"frozen_set_id {manifest['frozen_set_id']}")
    print(
        f"clips={manifest['clip_count']} players={manifest['player_count']} seconds={manifest['total_clip_s']}"
    )
    for clip in manifest["clips"]:
        print(
            f"{clip['clip_id']} roster={clip['roster_entry_id']} #{clip['jersey_number']} "
            f"{clip['duration_s']:.2f}s — {clip['selection_reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
