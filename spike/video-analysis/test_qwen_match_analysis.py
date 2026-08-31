import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import qwen_match_analysis as qwen_analysis  # noqa: E402

from qwen_match_analysis import (  # noqa: E402
    append_honest_limits,
    build_caption_prompt,
    build_sampling_plan,
    build_sandbox_argv,
    caption_frame_timestamps,
    compute_player_confidence,
    filter_player_notes,
    finalize_analysis,
    generate_window_captions,
    parse_observation,
    parse_window_caption,
    readable_jersey_evidence,
    too_many_frame_failures,
    validate_analysis_schema,
    zone_coverage_counts,
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
            "zone_coverage": {"left": 1, "central": 1, "right": 0, "unclear": 0},
            "captions_failed": 0,
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
        "window_captions": [],
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


def test_observation_validation_rejects_empty_object():
    with pytest.raises(ValueError, match="missing required keys"):
        parse_observation("{}")


def test_observation_validation_rejects_wrong_typed_jersey_list():
    observation = _good_observation()
    observation["teams"][0]["readable_jersey_numbers"] = [8, "11"]
    with pytest.raises(ValueError, match="readable_jersey_numbers"):
        parse_observation(json.dumps(observation))


def test_observation_validation_rejects_unknown_pitch_zone():
    observation = _good_observation()
    observation["visible_pitch_zone"] = "attacking"
    with pytest.raises(ValueError, match="visible_pitch_zone is invalid"):
        parse_observation(json.dumps(observation))


def test_observation_validation_accepts_known_good_shape():
    observation = _good_observation()
    assert parse_observation(json.dumps(observation)) == observation


def test_observation_validation_rejects_team_missing_visible_players():
    observation = _good_observation()
    del observation["teams"][0]["visible_players"]
    with pytest.raises(ValueError, match="team is missing required keys"):
        parse_observation(json.dumps(observation))


def _good_observation():
    return {
        "teams": [
            {
                "kit_color": "blue",
                "visible_players": 7,
                "readable_jersey_numbers": [8, 11],
            },
            {
                "kit_color": "red",
                "visible_players": 6,
                "readable_jersey_numbers": [],
            },
        ],
        "ball_visible": True,
        "phase_of_play": "build-up",
        "visible_pitch_zone": "central",
        "observation": "The blue-kit side has possession in its own half.",
        "notable_actions": ["Blue #8 offers a short passing option."],
    }


def test_player_filter_binds_number_evidence_to_normalized_kit_color():
    observations = [
        {
            "observation": {
                **_good_observation(),
                "teams": [
                    {
                        "kit_color": "  Red ",
                        "visible_players": 1,
                        "readable_jersey_numbers": [8],
                    }
                ],
            }
        }
    ]
    notes = [
        {"kit_color": "blue", "jersey_number": 8},
        {"kit_color": "red", "jersey_number": 8},
        {"kit_color": " RED ", "jersey_number": 8},
    ]
    evidence = readable_jersey_evidence(observations)

    assert filter_player_notes(notes, evidence) == [
        {"kit_color": "red", "jersey_number": 8},
        {"kit_color": " RED ", "jersey_number": 8},
    ]


def test_finalize_overwrites_model_times_seen_from_frame_evidence():
    analysis = _good_analysis()
    analysis["player_notes"][0]["times_seen"] = 5
    observations = [
        {"timestamp_s": 30, "observation": _good_observation()},
    ]
    sampling = {
        "interval_s": 30,
        "in_play_windows": [[0, 60]],
    }

    final = finalize_analysis(
        analysis,
        observations,
        model="vision-model",
        sampling=sampling,
        frames_failed=0,
    )

    assert final["player_notes"][0]["times_seen"] == 1
    assert final["player_notes"][0]["confidence"] == "low"
    assert final["sampling"]["zone_coverage"] == {
        "left": 0,
        "central": 1,
        "right": 0,
        "unclear": 0,
    }
    assert final["sampling"]["captions_failed"] == 0
    assert final["window_captions"] == []


def test_zone_coverage_counts_only_valid_ok_observation_zones():
    observations = [
        {"observation": {**_good_observation(), "visible_pitch_zone": "left"}},
        {"observation": {**_good_observation(), "visible_pitch_zone": "left"}},
        {"observation": {**_good_observation(), "visible_pitch_zone": "right"}},
        {"observation": {**_good_observation(), "visible_pitch_zone": "invalid"}},
    ]

    assert zone_coverage_counts(observations) == {
        "left": 2,
        "central": 0,
        "right": 1,
        "unclear": 0,
    }


def test_caption_prompt_is_number_only_multi_frame_and_outcome_guarded():
    prompt = build_caption_prompt(
        {
            "roster_jersey_number": 8,
            "kit_color": "blue",
            "tracklet_id": 10,
            "start_s": 10,
            "end_s": 20,
        }
    )

    assert "wearing blue #8" in prompt
    assert "Never name any player" in prompt
    assert "never say" in prompt and "goal unless the goal is visibly scored" in prompt
    assert "player_visible=false" in prompt


def test_caption_validation_accepts_good_shape_and_rejects_bad_fields():
    good = {
        "caption": "Blue #8 carries the ball through the central camera-relative third.",
        "action_type": "carry",
        "player_visible": True,
        "visible_pitch_zone": "central",
    }
    assert parse_window_caption(json.dumps(good)) == good

    for key, value in (
        ("caption", ""),
        ("action_type", "goal"),
        ("player_visible", 1),
        ("visible_pitch_zone", "box"),
    ):
        bad = {**good, key: value}
        with pytest.raises(ValueError):
            parse_window_caption(json.dumps(bad))


def test_caption_frame_timestamps_are_evenly_spaced():
    assert caption_frame_timestamps(10, 20) == [10.0, 15.0, 20.0]
    assert caption_frame_timestamps(10, 20, max_frames=1) == [15.0]
    assert caption_frame_timestamps(20, 10) == []


def test_caption_output_copies_roster_identity_without_model_involvement(
    monkeypatch, tmp_path
):
    model_caption = {
        "caption": "Blue #8 carries the ball through the central third.",
        "action_type": "carry",
        "player_visible": True,
        "visible_pitch_zone": "central",
    }
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        qwen_analysis,
        "ollama_chat",
        lambda *args, **kwargs: json.dumps(model_caption),
    )

    captions, failed = generate_window_captions(
        [
            {
                "tracklet_id": 10,
                "roster_entry_id": 42,
                "roster_jersey_number": 8,
                "kit_color": "blue",
                "start_s": 10.0,
                "end_s": 20.0,
            }
        ],
        video_path=tmp_path / "match.mp4",
        out_dir=tmp_path / "out",
        ffmpeg_path=tmp_path / "ffmpeg",
        ffmpeg_dir=tmp_path,
        profile_path=tmp_path / "decode.sb",
        sandboxed=False,
        sandbox_exec=None,
        ollama_url="http://ollama.invalid",
        model="vision-model",
        timeout_s=30,
    )

    assert failed == 0
    assert captions == [
        {
            "tracklet_id": 10,
            "roster_entry_id": 42,
            "roster_jersey_number": 8,
            "start_s": 10,
            "end_s": 20,
            **model_caption,
        }
    ]


def test_caption_context_preserves_roster_identity(tmp_path):
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "caption_windows": [
                    {
                        "tracklet_id": 10,
                        "roster_entry_id": 42,
                        "roster_jersey_number": 8,
                        "kit_color": "blue",
                        "start_s": 10,
                        "end_s": 20,
                    }
                ]
            }
        )
    )

    assert qwen_analysis._load_context(context_path)["caption_windows"] == [
        {
            "tracklet_id": 10,
            "roster_entry_id": 42,
            "roster_jersey_number": 8,
            "kit_color": "blue",
            "start_s": 10.0,
            "end_s": 20.0,
        }
    ]


def test_honest_limits_are_always_appended():
    result = append_honest_limits({"honest_limits": ["Camera view was distant."]}, 45)
    joined = " ".join(result["honest_limits"])
    assert "Single-camera sampled-frame analysis" in joined
    assert "jersey number only" in joined
    assert "qualitative, not measured statistics" in joined
    assert "camera-relative thirds" in joined
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
