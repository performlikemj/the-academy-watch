"""Tests for the vision worker's pipeline-command construction — that the operator timeline
markers (including the 2nd-half kickoff and end/full-time) are forwarded to $VIDEO_PIPELINE_CMD
so the GPU pass can window to in-play time."""
from pathlib import Path
from types import SimpleNamespace

from src.workers.vision_worker import _build_pipeline_cmd

TEMPLATE = "python /app/run_spike.py --device cuda"
VIDEO = Path("/tmp/match.mp4")
OUT = Path("/tmp/out")


def _cmd(**markers):
    match = SimpleNamespace(
        kickoff_s=None, halftime_s=None, second_half_kickoff_s=None, duration_s=None
    )
    for key, value in markers.items():
        setattr(match, key, value)
    return _build_pipeline_cmd(TEMPLATE, VIDEO, OUT, match)


def test_base_command_without_markers():
    assert _cmd() == [
        "python", "/app/run_spike.py", "--device", "cuda",
        "--video", str(VIDEO), "--out", str(OUT),
    ]


def test_all_markers_forwarded_including_second_half_and_end():
    joined = " ".join(_cmd(kickoff_s=900, halftime_s=3600, second_half_kickoff_s=4500, duration_s=7200))
    assert "--kickoff-s 900" in joined
    assert "--halftime-s 3600" in joined
    assert "--second-half-kickoff-s 4500" in joined  # the previously-dropped marker
    assert "--end-s 7200" in joined                   # full-time from match duration


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
