#!/usr/bin/env python3
"""Vision worker: claims queued video jobs and runs the GPU pipeline.

Runs inside the academy-watch-vision image (GPU deps live THERE, not in this
repo — RF-DETR, BoT-SORT, supervision, the jersey reader). The contract between
this orchestrator and the CV code is a subprocess command plus an artifacts
directory, which keeps the Flask codebase importable without CUDA and matches
the chunk-and-merge architecture the ~33-min serverless-GPU eviction window
forces anyway:

  $VIDEO_PIPELINE_CMD --video <local mp4> --out <artifacts dir> \
      [--kickoff-s N] [--halftime-s N] [--second-half-kickoff-s N] [--end-s N] \
      [--context-json <path>]

The timeline markers window the run to in-play time: the pipeline processes [kickoff, end]
and skips the halftime gap [halftime, second-half-kickoff] (see game_time.in_play_plan /
run_spike.py marker mode). All are optional and degrade safely; kickoff alone just trims warm-up.

The default VIDEO_PIPELINE_KIND=cv must produce fragments.json + votes.json
(+ optional chains.json, thumbnails.json). VIDEO_PIPELINE_KIND=qwen_analysis
must produce analysis.json and receives match context via --context-json. Each
kind is persisted through its fenced completion service.

Modes:
  one-shot (VIDEO_JOB_ID set)  process exactly that job, exit — ACA Jobs path
  loop (default)               poll-claim queued CV jobs until idle-timeout

Loop mode is CV-only until jobs carry a persisted pipeline kind. Non-CV workers
must use one-shot pinning so they cannot claim an ordinary CV job.

Job state is DB-authoritative: claims are conditional UPDATEs, heartbeats let
the stale-reaper recover from evictions, and a re-delivered queue message
no-ops against an already-claimed job.
"""

import logging
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vision_worker")

IDLE_POLL_SECONDS = 30
IDLE_EXIT_AFTER_POLLS = 10  # loop mode: exit after ~5 idle minutes (KEDA rescales)
DEFAULT_QWEN_CAPTION_TOP_K = 5
MAX_QWEN_CAPTION_WINDOWS = 80


def _row_value(row, name, default=None):
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def select_caption_windows(
    match,
    roster_entries,
    tracklets,
    fragment_spans=None,
    *,
    top_k=DEFAULT_QWEN_CAPTION_TOP_K,
    total_cap=MAX_QWEN_CAPTION_WINDOWS,
) -> list[dict]:
    """Select the same ranked merged windows shown in reels for Qwen captions."""
    from src.services import video_reels

    if top_k <= 0 or total_cap <= 0:
        return []
    tracklets = list(tracklets)
    spans = video_reels.fragment_spans_from_tracklets(tracklets)
    spans.update(fragment_spans or {})
    active = [
        tracklet
        for tracklet in tracklets
        if not bool(_row_value(tracklet, "dismissed")) and _row_value(tracklet, "kind") != "tombstone"
    ]
    by_roster = {}
    for tracklet in active:
        roster_id = _row_value(tracklet, "roster_entry_id")
        if roster_id is not None:
            by_roster.setdefault(int(roster_id), []).append(tracklet)

    selected = []
    roster_entries = sorted(
        roster_entries,
        key=lambda entry: (int(_row_value(entry, "jersey_number")), int(_row_value(entry, "id"))),
    )
    our_cluster = _row_value(match, "our_team_cluster")
    for roster in roster_entries:
        bound = by_roster.get(int(_row_value(roster, "id")), [])
        raw_windows = []
        for tracklet in bound:
            raw_windows.extend(video_reels.tracklet_windows(tracklet, spans))
        chains_by_id = {int(_row_value(tracklet, "id")): tracklet for tracklet in bound}
        windows = video_reels.rank_windows(video_reels.merge_windows(raw_windows), chains_by_id)
        eligible = [window for window in windows if window["end_s"] - window["start_s"] >= 3]
        for window in sorted(eligible, key=lambda item: item["rank"])[:top_k]:
            chain = chains_by_id.get(window["tracklet_id"])
            cluster = _row_value(chain, "team_cluster")
            kit_color = None
            if cluster in (0, 1) and our_cluster in (0, 1):
                kit_color = (
                    _row_value(match, "our_kit_color")
                    if cluster == our_cluster
                    else _row_value(match, "opponent_kit_color")
                )
            selected.append(
                {
                    "tracklet_id": window["tracklet_id"],
                    "roster_entry_id": int(_row_value(roster, "id")),
                    "roster_jersey_number": int(_row_value(roster, "jersey_number")),
                    "kit_color": kit_color,
                    "start_s": window["start_s"],
                    "end_s": window["end_s"],
                    "_rank": window["rank"],
                    "_roster_id": int(_row_value(roster, "id")),
                }
            )

    selected.sort(
        key=lambda window: (
            window["_rank"],
            window["roster_jersey_number"],
            window["_roster_id"],
            window["start_s"],
            window["tracklet_id"],
        )
    )
    return [{key: value for key, value in window.items() if not key.startswith("_")} for window in selected[:total_cap]]


def _download_footage(blob_path: str, dest: Path, expected_etag: str) -> None:
    from src.services.video_storage import mint_read_sas

    if not expected_etag:
        raise RuntimeError("verified footage ETag is missing")
    url = mint_read_sas(blob_path)
    log.info("downloading footage to %s", dest)
    command = [
        "curl",
        "-fsSL",
        "--retry",
        "3",
        "-H",
        f"If-Match: {expected_etag}",
        "-o",
        str(dest),
        url,
    ]
    subprocess.run(
        command,
        check=True,
        timeout=3600,
    )


def _build_pipeline_cmd(
    cmd_template: str,
    video_path: Path,
    out_dir: Path,
    match,
    context_path: Path | None = None,
) -> list[str]:
    """Assemble the pipeline argv, forwarding the operator's timeline markers.

    Only markers that are set are appended. The pipeline (run_spike.py in-play marker mode /
    game_time.in_play_plan) bounds the run to [kickoff, end] and SKIPS the halftime gap
    [halftime, second-half-kickoff] — so warm-ups, halftime and post-match aren't analysed.
    `--end-s` comes from the match duration (full-time = end of footage). Pure/argv-only so it
    is unit-testable without CUDA.
    """
    cmd = shlex.split(cmd_template) + ["--video", str(video_path), "--out", str(out_dir)]
    for flag, value in (
        ("--kickoff-s", match.kickoff_s),
        ("--halftime-s", match.halftime_s),
        ("--second-half-kickoff-s", match.second_half_kickoff_s),
        ("--end-s", match.duration_s),
    ):
        if value is not None:
            cmd += [flag, str(value)]
    if context_path is not None:
        cmd += ["--context-json", str(context_path)]
    return cmd


def _keepalive(app, job_id: str, stop: threading.Event, fenced: threading.Event, interval_s: int = 300) -> None:
    """Heartbeat while the pipeline subprocess runs (it can outlive the reaper's window); a rejected heartbeat
    means the job was reaped/cancelled underneath us — flag it so the results are discarded."""
    from src.services.video_queue import heartbeat

    with app.app_context():
        while not stop.wait(interval_s):
            try:
                alive = heartbeat(job_id, stage="detect")
            except Exception:  # a blip must not kill the worker; the next tick retries
                log.exception("keepalive heartbeat failed")
                continue
            if not alive:
                fenced.set()
                return


def _run_pipeline(video_path: Path, out_dir: Path, match, context_path: Path | None = None) -> None:
    cmd_template = os.getenv("VIDEO_PIPELINE_CMD")
    if not cmd_template:
        raise RuntimeError("VIDEO_PIPELINE_CMD is not set (vision image misconfigured)")
    cmd = _build_pipeline_cmd(cmd_template, video_path, out_dir, match, context_path)
    log.info("running pipeline: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _local_video_path(match) -> Path:
    """Resolve the explicit dev-only local video mapping, failing closed."""
    capture_meta = match.capture_meta if isinstance(match.capture_meta, dict) else {}
    local = capture_meta.get("local")
    value = local.get("video") if isinstance(local, dict) else None
    if not isinstance(value, str) or not value:
        raise RuntimeError("local footage is missing: capture_meta.local.video must be an absolute file path")
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError("local footage is invalid: capture_meta.local.video must be an absolute file path")
    if not path.is_file():
        raise RuntimeError(f"local footage does not exist: {path}")
    return path


def process_job(app, job_id: str) -> bool:
    """Run one claimed job to completion. Returns True on success."""
    import json

    from src.models.league import db
    from src.models.video import VideoAnalysisJob, VideoMatch, VideoTracklet
    from src.services import video_storage
    from src.services.video_analysis_store import complete_job_with_analysis
    from src.services.video_identity import complete_job_with_artifacts
    from src.services.video_queue import JobFenced, fail_running_job, heartbeat

    job = db.session.get(VideoAnalysisJob, job_id)
    match = db.session.get(VideoMatch, job.video_match_id)
    pipeline_kind = os.getenv("VIDEO_PIPELINE_KIND", "cv")
    t0 = time.monotonic()
    try:
        # Pin the download to the ETag returned by this verification. For legacy
        # matches without a stored ETag, this is the just-observed current ETag.
        if not heartbeat(job_id, stage="decode", progress=0):
            raise JobFenced("job is no longer running (reaped before decode)")
        storage_configured = video_storage.is_configured()
        verified_etag = None
        if storage_configured:
            check = video_storage.verify_expected_blob(match.blob_path, match.blob_etag)
            if not check["ok"]:
                raise RuntimeError(f"footage blob failed verification: {check.get('error')}")
            verified_etag = check.get("etag")
            if not verified_etag:
                raise RuntimeError("footage blob verification returned no ETag")

        with tempfile.TemporaryDirectory(prefix="vision-job-") as tmp:
            tmp_path = Path(tmp)
            if storage_configured:
                video_path = tmp_path / "match.mp4"
                _download_footage(match.blob_path, video_path, verified_etag)
            else:
                video_path = _local_video_path(match)

            if not heartbeat(job_id, stage="detect", progress=5):
                raise JobFenced("job is no longer running (reaped before detect)")
            out_dir = tmp_path / "artifacts"
            out_dir.mkdir()
            context_path = None
            if pipeline_kind == "qwen_analysis":
                from src.services import video_dev_artifacts

                context_path = tmp_path / "context.json"
                spans = {}
                artifacts = video_dev_artifacts.local_artifacts(match)
                if artifacts:
                    try:
                        spans = video_dev_artifacts.fragment_spans(artifacts)
                    except (KeyError, OSError, TypeError, ValueError):
                        log.warning(
                            "video match %s captions could not read fragment spans; using stored chain spans",
                            match.id,
                        )
                tracklets = list(
                    db.session.query(VideoTracklet)
                    .filter(VideoTracklet.video_match_id == match.id, VideoTracklet.kind != "tombstone")
                    .all()
                )
                top_k = int(os.getenv("QWEN_CAPTION_TOP_K", str(DEFAULT_QWEN_CAPTION_TOP_K)))
                capture_meta = match.capture_meta if isinstance(match.capture_meta, dict) else {}
                context_path.write_text(
                    json.dumps(
                        {
                            "opponent_name": match.opponent_name,
                            "our_kit_color": match.our_kit_color,
                            "opponent_kit_color": match.opponent_kit_color,
                            "competition": match.competition,
                            "attack_direction_first_half": capture_meta.get("attack_direction_first_half"),
                            "caption_windows": select_caption_windows(
                                match,
                                list(match.roster_entries),
                                tracklets,
                                spans,
                                top_k=top_k,
                            ),
                        }
                    )
                )
            stop, fenced = threading.Event(), threading.Event()
            keeper = threading.Thread(target=_keepalive, args=(app, job_id, stop, fenced), daemon=True)
            keeper.start()
            try:
                _run_pipeline(video_path, out_dir, match, context_path)
            finally:
                stop.set()
                keeper.join(timeout=30)
            if fenced.is_set():
                raise JobFenced("job was reaped while the pipeline was running")

            if not heartbeat(job_id, stage="persist", progress=90):
                raise JobFenced("job is no longer running (reaped before persist)")
            gpu_seconds = round(time.monotonic() - t0, 1)
            if pipeline_kind == "qwen_analysis":
                analysis = json.loads((out_dir / "analysis.json").read_text())
                if not isinstance(analysis, dict):
                    raise RuntimeError("analysis.json must contain a JSON object")
                complete_job_with_analysis(job_id, analysis, gpu_seconds=gpu_seconds)
            else:
                artifacts = {
                    "fragments": json.loads((out_dir / "fragments.json").read_text()),
                    "votes": json.loads((out_dir / "votes.json").read_text()),
                }
                for opt in ("chains", "thumbnails"):
                    p = out_dir / f"{opt}.json"
                    if p.exists():
                        artifacts[opt] = json.loads(p.read_text())
                complete_job_with_artifacts(job_id, artifacts, gpu_seconds=gpu_seconds)
        log.info("job %s succeeded", job_id)
        return True
    except JobFenced as e:
        # Another actor (reaper + requeue, or a cancel) owns this job/match now. Write nothing.
        log.warning("job %s fenced: %s — results discarded", job_id, e)
        db.session.rollback()
        return False
    except Exception as e:
        log.exception("job %s failed", job_id)
        db.session.rollback()
        # Compare-and-swap in the queue service: only a job that is STILL running flips (a reaper/requeue may own it
        # by now), and its match moves to failed only if no other job is live for it.
        if not fail_running_job(job_id, error=str(e), gpu_seconds=round(time.monotonic() - t0, 1)):
            log.warning("job %s was no longer running; someone else owns it — nothing overwritten", job_id)
        return False


def main() -> None:
    pipeline_kind = os.getenv("VIDEO_PIPELINE_KIND", "cv")
    pinned = os.getenv("VIDEO_JOB_ID")
    if pipeline_kind != "cv" and not pinned:
        log.error(
            "VIDEO_PIPELINE_KIND=%s requires VIDEO_JOB_ID: loop mode could claim an ordinary CV job; exiting",
            pipeline_kind,
        )
        raise SystemExit(2)

    from src.main import app

    worker_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or socket.gethostname()
    with app.app_context():
        from src.services.video_queue import claim_job, claim_next_job

        if pinned:
            if not claim_job(pinned, worker_id):
                log.info("job %s already claimed elsewhere — exiting (duplicate delivery)", pinned)
                return
            ok = process_job(app, pinned)
            sys.exit(0 if ok else 1)

        idle = 0
        while idle < IDLE_EXIT_AFTER_POLLS:
            job = claim_next_job(worker_id)
            if job is None:
                idle += 1
                time.sleep(IDLE_POLL_SECONDS)
                continue
            idle = 0
            process_job(app, job.id)
        log.info("idle for %ds — exiting", IDLE_POLL_SECONDS * IDLE_EXIT_AFTER_POLLS)


if __name__ == "__main__":
    main()
