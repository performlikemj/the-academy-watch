import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from qwen_match_analysis import (  # noqa: E402
    append_honest_limits,
    build_sampling_plan,
    build_sandbox_argv,
    compute_player_confidence,
    filter_player_notes,
    too_many_frame_failures,
    validate_analysis_schema,
)


def _good_analysis():
    return {
        "schema_version": "qwen-analysis-v1",
        "model": "vision-model",
        "generated_at": "2026-08-31T00:00:00+00:00",
        "sampling": {
            "interval_s": 30,
            "frames_analyzed": 2,
            "frames_failed": 0,
            "in_play_windows": [[100, 1900], [2200, 4000]],
        },
        "match_summary": "The blue-kit side attacks while the red-kit side recovers.",
        "team_analysis": [
            {
                "kit_color": "blue",
                "is_ours": True,
                "style": "Patient build-up.",
                "strengths": ["Width in possession."],
                "weaknesses": ["Space after turnovers."],
                "shape_notes": "The sampled frames suggest a compact midfield.",
            }
        ],
        "player_notes": [
            {
                "kit_color": "blue",
                "jersey_number": 8,
                "observations": ["Offers a passing option."],
                "times_seen": 3,
                "confidence": "medium",
            }
        ],
        "honest_limits": [],
    }


def test_sampling_plan_honors_markers_and_widens_for_max_calls():
    plan = build_sampling_plan(100, 1900, 2200, 4000, 4200, sample_s=30, max_calls=4)

    assert plan["in_play_windows"] == [[100, 1900], [2200, 4000]]
    assert plan["interval_s"] == 900
    assert plan["timestamps"] == [100, 1000, 2200, 3100]
    assert len(plan["timestamps"]) == 4
    assert any(timestamp >= 2200 for timestamp in plan["timestamps"])


def test_schema_validation_accepts_good_shape():
    validate_analysis_schema(_good_analysis())


def test_schema_validation_rejects_missing_key():
    analysis = _good_analysis()
    del analysis["match_summary"]
    with pytest.raises(ValueError, match="missing required keys"):
        validate_analysis_schema(analysis)


def test_schema_validation_rejects_non_int_jersey_number():
    analysis = _good_analysis()
    analysis["player_notes"][0]["jersey_number"] = "8"
    with pytest.raises(ValueError, match="jersey_number must be an integer"):
        validate_analysis_schema(analysis)


def test_confidence_is_computed_from_times_seen():
    notes = [
        {"jersey_number": 4, "times_seen": 2, "confidence": "medium"},
        {"jersey_number": 8, "times_seen": 3, "confidence": "low"},
    ]
    result = compute_player_confidence(notes)
    assert [note["confidence"] for note in result] == ["low", "medium"]


def test_player_filter_drops_numbers_never_seen_in_frames():
    notes = [{"jersey_number": 4}, {"jersey_number": 8}, {"jersey_number": 12}]
    assert filter_player_notes(notes, {4, 12}) == [
        {"jersey_number": 4},
        {"jersey_number": 12},
    ]


def test_honest_limits_are_always_appended():
    result = append_honest_limits({"honest_limits": ["Camera view was distant."]}, 45)
    joined = " ".join(result["honest_limits"])
    assert "Single-camera sampled-frame analysis" in joined
    assert "jersey number only" in joined
    assert "qualitative, not measured statistics" in joined
    assert "sampled every 45 seconds" in joined


def test_sandbox_argv_passes_static_profile_parameters():
    command = ["/opt/homebrew/bin/ffmpeg", "-i", "/jobs/input/match.mp4"]
    argv = build_sandbox_argv(
        "/repo/sandbox/ffmpeg_decode.sb",
        "/jobs/out",
        "/jobs/input",
        "/opt/homebrew",
        command,
        sandbox_exec="/usr/bin/sandbox-exec",
    )
    assert argv[:3] == ["/usr/bin/sandbox-exec", "-f", "/repo/sandbox/ffmpeg_decode.sb"]
    assert "OUT_DIR=/jobs/out" in argv
    assert "VIDEO_DIR=/jobs/input" in argv
    assert "FFMPEG_DIR=/opt/homebrew" in argv
    assert "EXECUTABLE=/opt/homebrew/bin/ffmpeg" in argv
    assert argv[-len(command) :] == command


@pytest.mark.parametrize(
    ("total", "failed", "expected"),
    [(4, 2, False), (4, 3, True), (1, 1, True), (0, 0, True)],
)
def test_more_than_half_failure_rule(total, failed, expected):
    assert too_many_frame_failures(total, failed) is expected
