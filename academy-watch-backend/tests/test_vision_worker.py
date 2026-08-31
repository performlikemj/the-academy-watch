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
from src.workers.vision_worker import (
    _build_pipeline_cmd,
    _download_footage,
    _local_video_path,
    main,
    process_job,
    select_caption_windows,
)

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


def test_context_path_is_forwarded_after_markers():
    context = Path("/tmp/context.json")
    command = _build_pipeline_cmd(
        TEMPLATE,
        VIDEO,
        OUT,
        SimpleNamespace(kickoff_s=0, halftime_s=None, second_half_kickoff_s=None, duration_s=7200),
        context,
    )
    assert command[-2:] == ["--context-json", str(context)]


def _caption_chain(tracklet_id, roster_id, start, end, *, confidence="high", contaminated=False, cluster=0):
    return {
        "id": tracklet_id,
        "kind": "chain",
        "roster_entry_id": roster_id,
        "first_s": start,
        "last_s": end,
        "evidence": {},
        "confidence": confidence,
        "contaminated": contaminated,
        "team_cluster": cluster,
        "dismissed": False,
    }


def test_caption_window_selection_uses_rank_top_k_duration_and_kit_mapping():
    match = SimpleNamespace(our_team_cluster=1, our_kit_color="blue", opponent_kit_color="red")
    roster = [SimpleNamespace(id=1, jersey_number=8), SimpleNamespace(id=2, jersey_number=11)]
    tracklets = [
        _caption_chain(1, 1, 0, 20, confidence="low", cluster=1),
        _caption_chain(2, 1, 30, 35, confidence="high", cluster=1),
        _caption_chain(3, 1, 40, 42.9, confidence="high", cluster=1),
        _caption_chain(4, 2, 50, 58, confidence="high", cluster=0),
        _caption_chain(5, 2, 60, 70, confidence="high", contaminated=True, cluster=0),
    ]

    assert select_caption_windows(match, roster, tracklets, top_k=2) == [
        {
            "tracklet_id": 2,
            "roster_jersey_number": 8,
            "kit_color": "blue",
            "start_s": 30.0,
            "end_s": 35.0,
        },
        {
            "tracklet_id": 4,
            "roster_jersey_number": 11,
            "kit_color": "red",
            "start_s": 50.0,
            "end_s": 58.0,
        },
        {
            "tracklet_id": 5,
            "roster_jersey_number": 11,
            "kit_color": "red",
            "start_s": 60.0,
            "end_s": 70.0,
        },
        {
            "tracklet_id": 1,
            "roster_jersey_number": 8,
            "kit_color": "blue",
            "start_s": 0.0,
            "end_s": 20.0,
        },
    ]


def test_caption_window_selection_caps_total_and_is_null_safe_for_kit():
    match = SimpleNamespace(our_team_cluster=None, our_kit_color="blue", opponent_kit_color="red")
    roster = [SimpleNamespace(id=index, jersey_number=index) for index in range(1, 82)]
    tracklets = [_caption_chain(index, index, index * 10, index * 10 + 4) for index in range(1, 82)]

    selected = select_caption_windows(match, roster, tracklets)

    assert len(selected) == 80
    assert [window["roster_jersey_number"] for window in selected[:2]] == [1, 2]
    assert selected[-1]["roster_jersey_number"] == 80
    assert all(window["kit_color"] is None for window in selected)


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
            patch("src.services.video_storage.is_configured", return_value=True),
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


def test_local_video_path_requires_existing_absolute_path(tmp_path):
    video = tmp_path / "match.mp4"
    video.write_bytes(b"test footage")
    match = SimpleNamespace(capture_meta={"local": {"video": str(video)}})
    assert _local_video_path(match) == video


def test_qwen_analysis_kind_uses_local_footage_and_analysis_completion(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    video = tmp_path / "match.mp4"
    video.write_bytes(b"test footage")
    job = SimpleNamespace(video_match_id=1)
    match = SimpleNamespace(
        id=1,
        blob_path=None,
        blob_etag=None,
        capture_meta={"local": {"video": str(video)}},
        kickoff_s=0,
        halftime_s=1800,
        second_half_kickoff_s=2100,
        duration_s=3900,
        opponent_name="Red-kit opposition",
        our_kit_color="blue",
        opponent_kit_color="red",
        competition="Academy fixture",
        our_team_cluster=0,
        roster_entries=[],
        status="queued",
    )

    def fake_get(model, _identifier):
        return job if model is VideoAnalysisJob else match

    analysis = {"schema_version": "qwen-analysis-v1", "match_summary": "Sampled match analysis."}

    def fake_pipeline(command, check):
        assert check is True
        assert command[command.index("--video") + 1] == str(video)
        context_path = Path(command[command.index("--context-json") + 1])
        context = __import__("json").loads(context_path.read_text())
        assert context == {
            "opponent_name": "Red-kit opposition",
            "our_kit_color": "blue",
            "opponent_kit_color": "red",
            "competition": "Academy fixture",
            "attack_direction_first_half": None,
            "caption_windows": [],
        }
        out_dir = Path(command[command.index("--out") + 1])
        (out_dir / "analysis.json").write_text(__import__("json").dumps(analysis))

    monkeypatch.setenv("VIDEO_PIPELINE_KIND", "qwen_analysis")
    monkeypatch.setenv("VIDEO_PIPELINE_CMD", "python qwen_match_analysis.py")
    with app.app_context():
        with (
            patch.object(db.session, "get", side_effect=fake_get),
            patch("src.services.video_storage.is_configured", return_value=False),
            patch("src.services.video_storage.verify_expected_blob") as verify,
            patch("src.services.video_dev_artifacts.local_artifacts", return_value=None),
            patch("src.workers.vision_worker._download_footage") as download,
            patch("src.services.video_queue.heartbeat", return_value=True),
            patch.object(db.session, "query") as query,
            patch("src.workers.vision_worker.subprocess.run", side_effect=fake_pipeline),
            patch("src.services.video_analysis_store.complete_job_with_analysis") as complete,
        ):
            query.return_value.filter.return_value.all.return_value = []
            assert process_job(app, "job-1") is True

    verify.assert_not_called()
    download.assert_not_called()
    complete.assert_called_once()
    assert complete.call_args.args[:2] == ("job-1", analysis)
    assert complete.call_args.kwargs["gpu_seconds"] >= 0


def test_qwen_analysis_requires_pinned_job_and_never_claims_loop_job(app, monkeypatch, caplog):
    monkeypatch.setenv("VIDEO_PIPELINE_KIND", "qwen_analysis")
    monkeypatch.delenv("VIDEO_JOB_ID", raising=False)

    with (
        patch("src.main.app", app),
        patch("src.services.video_queue.claim_next_job") as claim_next,
        pytest.raises(SystemExit) as exited,
    ):
        main()

    assert exited.value.code != 0
    claim_next.assert_not_called()
    assert "requires VIDEO_JOB_ID" in caplog.text
    assert "ordinary CV job" in caplog.text
