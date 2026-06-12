#!/usr/bin/env python3
"""Load video-pipeline artifacts into the product DB (concierge path).

Phase A runs the GPU pipeline as chunked ACA jobs + a local merge/identity pass
(spike lineage). This script bridges that world into the product: it takes the
artifacts directory (fragments.json, votes.json, chains.json — the inverted
pipeline's outputs) and persists VideoTracklet rows for the tag-review UI.

Usage:
    cd academy-watch-backend
    python src/scripts/load_video_artifacts.py --match-id 1 --artifacts-dir /path/to/inverted
    python src/scripts/load_video_artifacts.py --match-id 1 --artifacts-dir ... --job-id <uuid>
    # --job-id completes that queued/running job; omitted = a synthetic
    # succeeded job row is created so reports carry a pipeline_version.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def load_artifacts_dir(artifacts_dir: Path) -> dict:
    out: dict = {}
    frag_path = artifacts_dir / "fragments.json"
    votes_path = artifacts_dir / "votes.json"
    if not frag_path.exists() or not votes_path.exists():
        raise SystemExit(f"{artifacts_dir} must contain fragments.json and votes.json")
    out["fragments"] = json.loads(frag_path.read_text())
    out["votes"] = json.loads(votes_path.read_text())
    chains_path = artifacts_dir / "chains.json"
    if chains_path.exists():
        out["chains"] = json.loads(chains_path.read_text())
    thumbs_path = artifacts_dir / "thumbnails.json"
    if thumbs_path.exists():
        out["thumbnails"] = json.loads(thumbs_path.read_text())
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--artifacts-dir", type=Path, required=True)
    p.add_argument("--job-id", default=None, help="existing job to complete (default: create one)")
    p.add_argument("--gpu-seconds", type=float, default=None, help="COGS telemetry from the run")
    args = p.parse_args()

    artifacts = load_artifacts_dir(args.artifacts_dir)
    log.info(
        "loaded artifacts: %d fragments, %d vote rows, %s chains",
        len(artifacts["fragments"]),
        len(artifacts["votes"].get("entities", [])),
        len(artifacts.get("chains", [])) if "chains" in artifacts else "rebuild",
    )

    from src.main import app
    from src.models.league import db
    from src.models.video import VideoAnalysisJob, VideoMatch
    from src.services.video_identity import complete_job_with_artifacts

    with app.app_context():
        match = db.session.get(VideoMatch, args.match_id)
        if match is None:
            raise SystemExit(f"video match {args.match_id} not found")
        job_id = args.job_id
        if job_id is None:
            job = VideoAnalysisJob(
                video_match_id=match.id,
                status="running",
                stage="persist",
                pipeline_version="phase-a-v1-concierge",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id
            log.info("created concierge job %s", job_id)
        result = complete_job_with_artifacts(job_id, artifacts, gpu_seconds=args.gpu_seconds)
        log.info("persisted: %s — match now '%s'", result, match.status)


if __name__ == "__main__":
    main()
