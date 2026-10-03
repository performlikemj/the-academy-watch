"""Bounded CPU worker: python -m src.workers.highlight_worker --limit 5.

Own durable job kind/lease; does not join CV queues or mutate the match lifecycle.
No network or ffmpeg work under database locks. Restart after interruption is safe.
"""

import argparse
import json
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from src.models.highlights import HighlightRenderJob, PlayerHighlight, now, uuid4
from src.models.league import db
from src.models.video import VideoMatch
from src.services import highlights, highlights_storage, video_storage
from src.services.highlights_retention import log_disabled, retention_enabled
from src.utils.log_privacy import log_metadata

MAX_ATTEMPTS = 3
LEASE_SECONDS = 900  # greater than bounded download + cut + upload


def cut_file(source, destination, start_s, end_s):
    if not 0 <= start_s < end_s or end_s - start_s > highlights.MAX_CLIP_SECONDS:
        raise ValueError("invalid_range")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "format=format_name,duration",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    fmt = json.loads(probe.stdout)["format"]
    if (
        "mp4" not in fmt.get("format_name", "").split(",")
        or float(fmt["duration"]) <= end_s - start_s
        or float(fmt["duration"]) < end_s
    ):
        raise ValueError("unsupported_source")
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-ss",
            str(start_s),
            "-i",
            str(source),
            "-t",
            str(end_s - start_s),
            "-map",
            "0:v:0",
            "-an",
            "-map_metadata",
            "-1",
            "-vf",
            "scale=w=min(1280\\,iw):h=-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-threads",
            "1",
            "-b:v",
            "1500k",
            "-maxrate",
            "2000k",
            "-bufsize",
            "4000k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-fs",
            str(highlights_storage.MAX_OUTPUT_BYTES),
            "-f",
            "mp4",
            "-y",
            str(destination),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=300,
        check=True,
    )
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(destination)],
        capture_output=True,
        timeout=30,
        check=True,
    )
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if not 0 < duration <= end_s - start_s + 0.15:
        raise ValueError("invalid_output_duration")


def claim_next():
    kinds = []
    if retention_enabled():
        kinds.append("highlight_delete")
    if highlights.enabled():
        kinds.append("highlight_cut")
    if not kinds:
        log_disabled()
        return None
    # Bounded scan: exhausted leases must not hide the next healthy job.
    for _ in range(20):
        candidate = (
            HighlightRenderJob.query.outerjoin(PlayerHighlight, PlayerHighlight.id == HighlightRenderJob.highlight_id)
            .filter(
                HighlightRenderJob.kind.in_(kinds),
                HighlightRenderJob.created_at <= now(),
                (HighlightRenderJob.status == "queued")
                | ((HighlightRenderJob.status == "running") & (HighlightRenderJob.lease_expires_at < now())),
            )
            .order_by(
                HighlightRenderJob.kind.desc(),
                PlayerHighlight.video_match_id,
                HighlightRenderJob.created_at,
                HighlightRenderJob.id,
            )
            .first()
        )
        if candidate is None:
            db.session.commit()
            return None
        row = db.session.get(PlayerHighlight, candidate.highlight_id) if candidate.highlight_id else None
        if row and row.video_match_id:
            VideoMatch.query.filter_by(id=row.video_match_id).with_for_update().first()
        if row:
            row = PlayerHighlight.query.filter_by(id=row.id).populate_existing().with_for_update().first()
        job = (
            HighlightRenderJob.query.filter_by(id=candidate.id)
            .populate_existing()
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job or not (job.status == "queued" or (job.status == "running" and job.lease_expires_at < now())):
            db.session.commit()
            continue
        if job.attempt >= MAX_ATTEMPTS:
            if job.kind == "highlight_cut" and job.blob_path:
                queue_cleanup(job.blob_path)
            job.status, job.error_code, job.completed_at = "failed", "attempt_limit", now()
            job.lease_token = None
            if row and row.render_status != "ready":
                row.render_status = "failed"
            db.session.commit()
            continue
        if job.kind == "highlight_cut" and job.blob_path:
            queue_cleanup(job.blob_path)
        job.status = "running"
        job.attempt += 1
        job.lease_token = uuid4()
        job.lease_expires_at = now() + timedelta(seconds=LEASE_SECONDS)
        if job.kind == "highlight_cut":
            job.blob_path = f"highlights/{job.highlight_id}/{job.lease_token}.mp4"
        db.session.commit()
        return job.id, job.lease_token
    return None


def finish(job_id, lease, *, output_etag=None, output_size=None, error=None):
    # Read ids without locks, then use the common match -> highlight -> job lock order.
    job = db.session.get(HighlightRenderJob, job_id)
    row = db.session.get(PlayerHighlight, job.highlight_id) if job and job.highlight_id else None
    if row and row.video_match_id:
        VideoMatch.query.filter_by(id=row.video_match_id).with_for_update().first()
    if row:
        row = PlayerHighlight.query.filter_by(id=row.id).populate_existing().with_for_update().first()
    job = HighlightRenderJob.query.filter_by(id=job_id).populate_existing().with_for_update().first()
    if not job or job.status != "running" or job.lease_token != lease or job.lease_expires_at < now():
        db.session.rollback()
        return False
    if job.kind == "highlight_delete":
        job.status = "queued" if error and job.attempt < MAX_ATTEMPTS else "failed" if error else "succeeded"
        if job.status == "queued":
            job.created_at = now() + timedelta(minutes=job.attempt)

    elif (
        not row
        or row.player_decision == "private"
        or row.source_version != job.source_version
        or not highlights.eligible(row)
    ):
        job.status = "cancelled"
        if row and not row.revoked_at and row.render_status != "ready":
            row.render_status = "stale"
        if job.blob_path:
            queue_cleanup(job.blob_path)
    elif error:
        job.status = "failed"
        row.render_status = "failed"
    else:
        job.status = "succeeded"
        row.output_blob_path = job.blob_path
        row.output_etag = output_etag
        row.output_bytes = output_size
        row.render_source_version = job.source_version
        row.render_status = "ready"
    job.error_code = error
    job.completed_at = now()
    job.lease_token = None
    db.session.commit()
    return job.status == "succeeded"


def queue_cleanup(path, *, delayed=True):
    # Reclaimed/cancelled attempts can finish uploading late; wait beyond their lease.
    if highlights_storage.is_output_path(path):
        db.session.add(
            HighlightRenderJob(
                kind="highlight_delete",
                blob_path=path,
                created_at=now() + timedelta(minutes=20) if delayed else now(),
            )
        )


def owned_output(path):
    """Only an exact recorded attempt blob; never raw footage or a prefix capability."""
    if not highlights_storage.is_output_path(path):
        return False
    recorded = (
        PlayerHighlight.query.filter_by(output_blob_path=path).first()
        or HighlightRenderJob.query.filter_by(blob_path=path).first()
    )
    return bool(recorded and not VideoMatch.query.filter_by(blob_path=path).first())


def delete_output(path):
    if not retention_enabled():
        log_disabled()
        return False
    allowed = owned_output(path)
    db.session.commit()  # ownership reads end before storage I/O
    if not retention_enabled():
        log_disabled()
        return False
    return bool(allowed and video_storage.delete_blob(path))


def cleanup_output(path):
    if not retention_enabled():
        log_disabled()
        return
    if not owned_output(path):
        return
    try:
        removed = delete_output(path)
    except Exception:
        removed = False
    if not removed:
        db.session.rollback()
        queue_cleanup(path)
        db.session.commit()


class SourceBatch:
    """One frozen match download per grouped batch, disk capped at one source."""

    def __init__(self, directory):
        self.source = Path(directory) / "source.mp4"
        self.key = None
        self.failed_key = None

    def get(self, blob, snapshot, etag):
        key = (blob, snapshot, etag)
        if key == self.failed_key:
            raise ValueError("source_batch_download_failed")
        if key != self.key:
            self.key = None
            self.source.unlink(missing_ok=True)
            try:
                highlights_storage.download_source(blob, snapshot, etag, self.source)
            except Exception:
                self.failed_key = key
                raise
            self.key = key
        return self.source


def run_one(job_id, lease, *, source_batch=None):
    job = db.session.get(HighlightRenderJob, job_id)
    if job is None:
        return False
    output_path = job.blob_path
    if job.kind == "highlight_delete":
        if not retention_enabled():
            log_disabled()
            return False
        db.session.commit()
        try:
            ok = delete_output(output_path)
        except Exception:
            ok = False
        finish(job_id, lease, error=None if ok else "storage_delete_failed")
        return ok
    row = db.session.get(PlayerHighlight, job.highlight_id) if job.highlight_id else None
    if (
        not row
        or row.player_decision == "private"
        or job.source_version != row.source_version
        or not highlights.eligible(row)
    ):
        finish(job_id, lease, error="ineligible")
        return False
    match = db.session.get(VideoMatch, row.video_match_id)
    args = (match.blob_path, row.source_snapshot, row.source_etag, row.start_s, row.end_s)
    db.session.commit()  # all eligibility queries/locks end before I/O
    try:
        with tempfile.TemporaryDirectory(prefix="aw-highlight-") as folder:
            source, output = Path(folder) / "source.mp4", Path(folder) / "clip.mp4"
            if source_batch is None:
                highlights_storage.download_source(*args[:3], source)
            else:
                source = source_batch.get(*args[:3])
            cut_file(source, output, *args[3:])
            etag, size = highlights_storage.upload_output(output_path, output)
        ok = finish(job_id, lease, output_etag=etag, output_size=size)
        if not ok:
            cleanup_output(output_path)
        return ok
    except Exception:
        # Exceptions can contain credentials/storage URLs. Persist a machine code only.
        db.session.rollback()
        finish(job_id, lease, error="cut_failed")
        cleanup_output(output_path)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="print proposed retention/deletes; change nothing")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("limit must be 1..20")
    if not args.dry_run and not retention_enabled() and not highlights.enabled():
        log_disabled()
        return
    from src.main import app

    with app.app_context():
        completed = 0
        from src.services.highlights_retention import sweep_highlights

        retention = sweep_highlights(limit=100, dry_run=args.dry_run)
        if args.dry_run:
            jobs = (
                HighlightRenderJob.query.filter(
                    HighlightRenderJob.kind == "highlight_delete",
                    HighlightRenderJob.created_at <= now(),
                    (HighlightRenderJob.status == "queued")
                    | ((HighlightRenderJob.status == "running") & (HighlightRenderJob.lease_expires_at < now())),
                )
                .order_by(HighlightRenderJob.created_at, HighlightRenderJob.id)
                .limit(args.limit)
            )
            print(
                json.dumps(
                    log_metadata(
                        {
                            "dry_run": True,
                            "would_delete_blobs": [job.blob_path for job in jobs if owned_output(job.blob_path)],
                        }
                    )
                )
            )
            return
        with tempfile.TemporaryDirectory(prefix="aw-highlight-batch-") as directory:
            batch = SourceBatch(directory)
            for _ in range(args.limit):
                claimed = claim_next()
                if claimed is None:
                    break
                completed += int(run_one(*claimed, source_batch=batch))
        print(
            json.dumps(log_metadata({"enabled": highlights.enabled(), "completed": completed, "retention": retention}))
        )


if __name__ == "__main__":
    main()
