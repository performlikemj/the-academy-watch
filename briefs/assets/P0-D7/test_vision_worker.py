"""Tests for the vision worker's pipeline-command construction — that the operator timeline
markers (including the 2nd-half kickoff and end/full-time) are forwarded to $VIDEO_PIPELINE_CMD
so the GPU pass can window to in-play time."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from src.models.league import db
from src.models.video import VideoAnalysisJob, VideoMatch
from src.services.video_storage import verify_expected_blob
from src.workers.vision_worker import _build_pipeline_cmd, _download_footage, process_job

TEMPLATE = "python /app/run_spike.py --device cuda"
VIDEO = Path("/tmp/match.mp4")
OUT = Path("/tmp/out")


def _cmd(**markers):
    match = SimpleNamespace(kickoff_s=None, halftime_s=None, second_half_kickoff_s=None, duration_s=None)
    for key, value in markers.items():
        setattr(match, key, value)
    return _build_pipeline_cmd(TEMPLATE, VIDEO, OUT, match)


def test_base_command_without_markers():
    assert _cmd() == [
        "python",
        "/app/run_spike.py",
        "--device",
        "cuda",
        "--video",
        str(VIDEO),
        "--out",
        str(OUT),
    ]


def test_all_markers_forwarded_including_second_half_and_end():
    joined = " ".join(_cmd(kickoff_s=900, halftime_s=3600, second_half_kickoff_s=4500, duration_s=7200))
    assert "--kickoff-s 900" in joined
    assert "--halftime-s 3600" in joined
    assert "--second-half-kickoff-s 4500" in joined  # the previously-dropped marker
    assert "--end-s 7200" in joined  # full-time from match duration


def test_partial_markers_only_forward_what_is_set():
    joined = " ".join(_cmd(kickoff_s=900, duration_s=7200))
    assert "--kickoff-s 900" in joined
    assert "--end-s 7200" in joined
    assert "--halftime-s" not in joined
    assert "--second-half-kickoff-s" not in joined


def test_zero_kickoff_is_forwarded_not_dropped():
    # 0.0 is a valid kickoff (footage begins exactly at kickoff); the builder must key on
    # "is not None", not truthiness, or a 0-second marker would silently vanish.
    assert "--kickoff-s" in _cmd(kickoff_s=0.0)


def test_download_is_pinned_to_verified_etag():
    with (
        patch("src.services.video_storage.mint_read_sas", return_value="https://blob.invalid/read"),
        patch("src.workers.vision_worker.subprocess.run") as run,
    ):
        _download_footage("matches/1/video.mp4", VIDEO, '"etag-1"')

    command = run.call_args.args[0]
    assert command[command.index("-H") + 1] == 'If-Match: "etag-1"'
    assert command[-1] == "https://blob.invalid/read"


def test_null_stored_etag_download_uses_verified_current_etag():
    current = {"ok": True, "etag": '"legacy-current"', "size_bytes": 2048}
    with patch("src.services.video_storage.verify_uploaded_blob", return_value=current) as verify:
        assert verify_expected_blob("matches/1/video.mp4", None) == current
    verify.assert_called_once_with("matches/1/video.mp4")

    with (
        patch("src.services.video_storage.mint_read_sas", return_value="https://blob.invalid/read"),
        patch("src.workers.vision_worker.subprocess.run") as run,
    ):
        _download_footage("matches/1/video.mp4", VIDEO, current["etag"])

    command = run.call_args.args[0]
    assert command[command.index("-H") + 1] == 'If-Match: "legacy-current"'
    assert command[-1] == "https://blob.invalid/read"


@pytest.mark.parametrize("verified_etag", [None, ""], ids=("none", "empty"))
def test_download_fails_closed_without_verified_etag(verified_etag):
    with (
        patch("src.services.video_storage.mint_read_sas") as mint,
        patch("src.workers.vision_worker.subprocess.run") as run,
        pytest.raises(RuntimeError, match="verified footage ETag is missing"),
    ):
        _download_footage("matches/1/video.mp4", VIDEO, verified_etag)

    mint.assert_not_called()
    run.assert_not_called()


def test_swap_after_verify_precondition_failure_marks_job_failed():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    job = SimpleNamespace(
        video_match_id=1,
        status="running",
        error=None,
        gpu_seconds=None,
        completed_at=None,
    )
    match = SimpleNamespace(
        blob_path="matches/1/video.mp4",
        blob_etag=None,
        status="processing",
    )

    def fake_get(model, _identifier):
        if model is VideoAnalysisJob:
            return job
        assert model is VideoMatch
        return match

    current = {"ok": True, "etag": '"verified-current"', "size_bytes": 2048}
    precondition_failed = subprocess.CalledProcessError(22, ["curl"])
    with app.app_context():
        with (
            patch.object(db.session, "get", side_effect=fake_get),
            patch.object(db.session, "rollback") as rollback,
            patch.object(db.session, "commit") as commit,
            patch("src.services.video_queue.heartbeat"),
            patch("src.services.video_queue.fail_running_job", return_value=True) as fail_job,
            patch("src.services.video_storage.verify_expected_blob", return_value=current),
            patch("src.services.video_storage.mint_read_sas", return_value="https://blob.invalid/read"),
            patch("src.workers.vision_worker.subprocess.run", side_effect=precondition_failed) as run,
        ):
            assert process_job(app, "job-1") is False

    command = run.call_args.args[0]
    assert command[command.index("-H") + 1] == 'If-Match: "verified-current"'
    # The failure transition is a compare-and-swap in the queue service (job still running → failed; match to failed
    # only if nothing else is live), never an unconditional ORM write from the worker.
    fail_job.assert_called_once()
    assert fail_job.call_args.args == ("job-1",)
    assert "returned non-zero exit status 22" in fail_job.call_args.kwargs["error"]
    assert job.status == "running"
    assert match.status == "processing"
    rollback.assert_called_once()
    commit.assert_not_called()


def test_non_null_etag_mismatch_fails_worker_verification():
    current = {"ok": True, "etag": '"swapped"', "size_bytes": 2048}
    with patch("src.services.video_storage.verify_uploaded_blob", return_value=current):
        result = verify_expected_blob("matches/1/video.mp4", '"stored"')

    assert result == {
        "ok": False,
        "error": "footage blob changed since upload-complete (ETag mismatch)",
    }
