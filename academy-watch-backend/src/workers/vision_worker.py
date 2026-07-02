#!/usr/bin/env python3
"""Vision worker: claims queued video jobs and runs the GPU pipeline.

Runs inside the academy-watch-vision image (GPU deps live THERE, not in this
repo — RF-DETR, BoT-SORT, supervision, the jersey reader). The contract between
this orchestrator and the CV code is a subprocess command plus an artifacts
directory, which keeps the Flask codebase importable without CUDA and matches
the chunk-and-merge architecture the ~33-min serverless-GPU eviction window
forces anyway:

  $VIDEO_PIPELINE_CMD --video <local mp4> --out <artifacts dir> \
      [--kickoff-s N] [--halftime-s N] [--second-half-kickoff-s N] [--end-s N]

The timeline markers window the run to in-play time: the pipeline processes [kickoff, end]
and skips the halftime gap [halftime, second-half-kickoff] (see game_time.in_play_plan /
run_spike.py marker mode). All are optional and degrade safely; kickoff alone just trims warm-up.

must produce fragments.json + votes.json (+ optional chains.json,
thumbnails.json) in <artifacts dir> — the schema validated in the Phase 0 spike
(invert_identity.py outputs). The worker then persists via
video_identity.complete_job_with_artifacts().

Modes:
  one-shot (VIDEO_JOB_ID set)  process exactly that job, exit — ACA Jobs path
  loop (default)               poll-claim queued jobs until idle-timeout

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
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vision_worker")

IDLE_POLL_SECONDS = 30
IDLE_EXIT_AFTER_POLLS = 10  # loop mode: exit after ~5 idle minutes (KEDA rescales)


def _download_footage(blob_path: str, dest: Path) -> None:
    from src.services.video_storage import mint_read_sas

    url = mint_read_sas(blob_path)
    log.info("downloading footage to %s", dest)
    subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "-o", str(dest), url],
        check=True,
        timeout=3600,
    )


def _build_pipeline_cmd(cmd_template: str, video_path: Path, out_dir: Path, match) -> list[str]:
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
    return cmd


def _run_pipeline(video_path: Path, out_dir: Path, match) -> None:
    cmd_template = os.getenv("VIDEO_PIPELINE_CMD")
    if not cmd_template:
        raise RuntimeError("VIDEO_PIPELINE_CMD is not set (vision image misconfigured)")
    cmd = _build_pipeline_cmd(cmd_template, video_path, out_dir, match)
    log.info("running pipeline: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def process_job(app, job_id: str) -> bool:
    """Run one claimed job to completion. Returns True on success."""
    import json

    from src.models.league import db
    from src.models.video import VideoAnalysisJob, VideoMatch
    from src.services.video_identity import complete_job_with_artifacts
    from src.services.video_queue import heartbeat
    from src.services.video_storage import verify_uploaded_blob

    job = db.session.get(VideoAnalysisJob, job_id)
    match = db.session.get(VideoMatch, job.video_match_id)
    t0 = time.monotonic()
    try:
        # content-swap TOCTOU check: blob must still match the upload-complete ETag
        heartbeat(job_id, stage="decode", progress=0)
        check = verify_uploaded_blob(match.blob_path)
        if not check["ok"]:
            raise RuntimeError(f"footage blob failed verification: {check.get('error')}")
        if match.blob_etag and check.get("etag") != match.blob_etag:
            raise RuntimeError("footage blob changed since upload-complete (ETag mismatch)")

        with tempfile.TemporaryDirectory(prefix="vision-job-") as tmp:
            tmp_path = Path(tmp)
            video_path = tmp_path / "match.mp4"
            _download_footage(match.blob_path, video_path)

            heartbeat(job_id, stage="detect", progress=5)
            out_dir = tmp_path / "artifacts"
            out_dir.mkdir()
            _run_pipeline(video_path, out_dir, match)

            heartbeat(job_id, stage="persist", progress=90)
            artifacts = {
                "fragments": json.loads((out_dir / "fragments.json").read_text()),
                "votes": json.loads((out_dir / "votes.json").read_text()),
            }
            for opt in ("chains", "thumbnails"):
                p = out_dir / f"{opt}.json"
                if p.exists():
                    artifacts[opt] = json.loads(p.read_text())
            complete_job_with_artifacts(job_id, artifacts, gpu_seconds=round(time.monotonic() - t0, 1))
        log.info("job %s succeeded", job_id)
        return True
    except Exception as e:
        log.exception("job %s failed", job_id)
        db.session.rollback()
        job = db.session.get(VideoAnalysisJob, job_id)
        job.status = "failed"
        job.error = str(e)[:2000]
        job.gpu_seconds = round(time.monotonic() - t0, 1)
        job.completed_at = datetime.now(UTC)
        match = db.session.get(VideoMatch, job.video_match_id)
        match.status = "failed"
        db.session.commit()
        return False


def main() -> None:
    from src.main import app

    worker_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or socket.gethostname()
    with app.app_context():
        from src.services.video_queue import claim_job, claim_next_job

        pinned = os.getenv("VIDEO_JOB_ID")
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
