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
    build_player_prompt,
    build_sampling_plan,
    build_sandbox_argv,
    build_team_prompt,
    caption_frame_timestamps,
    compute_player_confidence,
    filter_player_notes,
    finalize_analysis,
    generate_player_reads,
    generate_team_pass,
    generate_window_captions,
    parse_observation,
    parse_player_read,
    parse_window_caption,
    player_evidence_frames,
    player_image_paths,
    readable_jersey_evidence,
    recurring_jersey_evidence,
    scoped_recurring_jersey_evidence,
    too_many_frame_failures,
    too_many_player_read_failures,
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
            "notes_scope": "ours",
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


def test_recurring_jersey_evidence_requires_two_distinct_frames():
    observations = [
        {
            "observation": {
                **_good_observation(),
                "teams": [
                    {
                        "kit_color": " Blue ",
                        "visible_players": 2,
                        "readable_jersey_numbers": [8, 8, 11],
                    }
                ],
            }
        },
        {
            "observation": {
                **_good_observation(),
                "teams": [
                    {
                        "kit_color": "blue",
                        "visible_players": 1,
                        "readable_jersey_numbers": [8],
                    }
                ],
            }
        },
    ]

    assert recurring_jersey_evidence(observations) == {("blue", 8)}


@pytest.mark.parametrize(
    ("requested_scope", "context", "expected_pairs", "expected_scope"),
    [
        ("ours", {"our_kit_color": "  BLUE  "}, {("blue", 8)}, "ours"),
        (
            "all",
            {"our_kit_color": "blue"},
            {("blue", 8), ("red", 9)},
            "all",
        ),
        ("ours", {}, {("blue", 8), ("red", 9)}, "all"),
    ],
)
def test_scope_selection_normalizes_ours_and_falls_back_to_all(
    requested_scope, context, expected_pairs, expected_scope
):
    observation = {
        **_good_observation(),
        "teams": [
            {
                "kit_color": " Blue ",
                "visible_players": 1,
                "readable_jersey_numbers": [8],
            },
            {
                "kit_color": "RED",
                "visible_players": 1,
                "readable_jersey_numbers": [9],
            },
        ],
    }
    observations = [
        {"timestamp_s": timestamp, "observation": observation} for timestamp in (10, 40)
    ]

    pairs, effective_scope = scoped_recurring_jersey_evidence(
        observations, context, requested_scope
    )

    assert pairs == expected_pairs
    assert effective_scope == expected_scope


def test_player_prompt_contains_only_that_players_evidence_frames():
    observations = [
        {
            "timestamp_s": 10,
            "filename": "one.jpg",
            "observation": {
                **_good_observation(),
                "observation": "first-player-frame",
            },
        },
        {
            "timestamp_s": 40,
            "filename": "other.jpg",
            "observation": {
                **_good_observation(),
                "teams": [
                    {
                        "kit_color": "red",
                        "visible_players": 1,
                        "readable_jersey_numbers": [9],
                    }
                ],
                "observation": "other-player-only-frame",
            },
        },
    ]

    evidence = player_evidence_frames(observations, ("blue", 8))
    prompt = build_player_prompt(("blue", 8), evidence)

    assert [frame["timestamp_s"] for frame in evidence] == [10]
    assert "first-player-frame" in prompt
    assert "other-player-only-frame" not in prompt
    assert '"t":40' not in prompt
    assert "Never name or identify any player" in prompt


def test_player_images_are_limited_to_three_and_spread_across_time(tmp_path):
    evidence = [
        {"timestamp_s": timestamp, "filename": f"{index}.jpg"}
        for index, timestamp in enumerate((10, 20, 30, 40, 50))
    ]

    assert player_image_paths(evidence, tmp_path) == [
        tmp_path / "0.jpg",
        tmp_path / "2.jpg",
        tmp_path / "4.jpg",
    ]


def test_team_prompt_uses_compacted_stream_without_frame_prose_or_number_lists():
    observations = [
        {"timestamp_s": 10, "observation": _good_observation()},
        {"timestamp_s": 40, "observation": _good_observation()},
    ]

    prompt = build_team_prompt(observations, {"our_kit_color": "blue"})

    assert "The blue-kit side has possession in its own half." not in prompt
    assert "readable_jersey_numbers" not in prompt
    assert '"kits":[{"kit_color":"blue","visible_players":7}' in prompt
    assert '"phase_of_play":"build-up"' in prompt
    assert (
        "otherwise use an empty style string and empty strengths/weaknesses lists"
        in prompt
    )


def test_team_pass_retries_once_with_team_cap(monkeypatch):
    calls = []
    valid_team_pass = {
        "match_summary": "A sampled summary.",
        "team_analysis": _good_analysis()["team_analysis"],
        "honest_limits": [],
    }

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        return "{}" if len(calls) == 1 else json.dumps(valid_team_pass)

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)

    result = generate_team_pass(
        [{"timestamp_s": 10, "observation": _good_observation()}],
        {},
        ollama_url="http://ollama.invalid",
        model="vision-model",
        timeout_s=1201,
    )

    assert result == valid_team_pass
    assert len(calls) == 2
    assert all(call["timeout_s"] == 1201 for call in calls)
    assert all(call["num_predict"] == qwen_analysis.TEAM_NUM_PREDICT for call in calls)


def test_schema_validation_rejects_missing_recurring_player_pair():
    analysis = _good_analysis()

    with pytest.raises(ValueError, match=r"missing recurring evidenced pairs: red #11"):
        validate_analysis_schema(
            analysis,
            required_player_pairs={("blue", 8), ("red", 11)},
        )


def test_schema_validation_rejects_hollow_required_player_note():
    analysis = _good_analysis()
    analysis["player_notes"][0]["observations"] = []

    with pytest.raises(ValueError, match=r"hollow pairs .*blue #8"):
        validate_analysis_schema(
            analysis,
            required_player_pairs={("blue", 8)},
        )


def test_schema_validation_rejects_hollow_optional_player_note():
    analysis = _good_analysis()
    analysis["player_notes"][0]["observations"] = ["", "   "]

    with pytest.raises(ValueError, match=r"hollow pairs .*blue #8"):
        validate_analysis_schema(analysis)


def test_schema_validation_accepts_one_grounded_player_observation():
    analysis = _good_analysis()
    analysis["player_notes"][0]["observations"] = [
        "Seen at t=40 in the central zone offering a passing option."
    ]

    validate_analysis_schema(
        analysis,
        required_player_pairs={("blue", 8)},
    )


def test_player_read_validation_rejects_hollow_output():
    with pytest.raises(ValueError, match="1 to 3 non-empty observations"):
        parse_player_read(json.dumps({"observations": [], "confidence": "low"}))


def test_player_read_must_cite_a_timestamp_from_its_evidence():
    content = json.dumps(
        {
            "observations": ["Seen at t=99 in the central zone."],
            "confidence": "low",
        }
    )

    with pytest.raises(ValueError, match="must cite an evidence timestamp"):
        parse_player_read(content, [{"timestamp_s": 10}])

    grounded = json.dumps(
        {
            "observations": ["Seen at t=10.0 in the central zone."],
            "confidence": "low",
        }
    )
    assert parse_player_read(grounded, [{"timestamp_s": 10}])["observations"]


def test_hollow_player_read_retries_once_then_is_omitted_with_honest_limit(
    monkeypatch, tmp_path
):
    observations = [
        {
            "timestamp_s": timestamp,
            "filename": f"frame_{timestamp}.jpg",
            "observation": _good_observation(),
        }
        for timestamp in (10, 40)
    ]
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps({"observations": [], "confidence": "low"})

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)

    notes, limits, omitted = generate_player_reads(
        {("blue", 8)},
        observations,
        frames_dir=tmp_path,
        ollama_url="http://ollama.invalid",
        model="vision-model",
        timeout_s=17,
    )

    assert len(calls) == 2
    assert all(call["timeout_s"] == 17 for call in calls)
    assert all(
        call["num_predict"] == qwen_analysis.PLAYER_NUM_PREDICT for call in calls
    )
    assert notes == []
    assert omitted == {("blue", 8)}
    assert len(limits) == 1
    assert limits[0].startswith("no read produced for blue #8:")


def test_schema_validation_rejects_duplicate_normalized_player_pair():
    analysis = _good_analysis()
    analysis["player_notes"].append(
        {
            **analysis["player_notes"][0],
            "kit_color": " BLUE ",
        }
    )

    with pytest.raises(ValueError, match=r"duplicate normalized pair: blue #8"):
        validate_analysis_schema(
            analysis,
            required_player_pairs={("blue", 8)},
        )


def test_finalize_rejects_model_output_missing_a_recurring_pair():
    observations = [
        {"timestamp_s": 10, "observation": _good_observation()},
        {"timestamp_s": 40, "observation": _good_observation()},
    ]

    with pytest.raises(
        ValueError, match=r"missing recurring evidenced pairs: blue #11"
    ):
        finalize_analysis(
            _good_analysis(),
            observations,
            model="vision-model",
            sampling={"interval_s": 30, "in_play_windows": [[0, 60]]},
            frames_failed=0,
        )


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


def test_finalize_validates_assembly_against_scoped_required_set():
    observations = []
    for timestamp in (10, 40):
        observation = {
            **_good_observation(),
            "teams": [
                {
                    "kit_color": "blue",
                    "visible_players": 1,
                    "readable_jersey_numbers": [8],
                },
                {
                    "kit_color": "red",
                    "visible_players": 1,
                    "readable_jersey_numbers": [9],
                },
            ],
        }
        observations.append({"timestamp_s": timestamp, "observation": observation})

    final = finalize_analysis(
        _good_analysis(),
        observations,
        model="vision-model",
        sampling={"interval_s": 30, "in_play_windows": [[0, 60]]},
        frames_failed=0,
        notes_scope="ours",
        required_player_pairs={("blue", 8)},
    )

    validate_analysis_schema(final, required_player_pairs={("blue", 8)})
    assert final["sampling"]["notes_scope"] == "ours"
    assert {
        (note["kit_color"], note["jersey_number"]) for note in final["player_notes"]
    } == {("blue", 8)}


def test_finalize_allows_only_explicitly_omitted_failed_scoped_pair():
    observations = []
    for timestamp in (10, 40):
        observation = {
            **_good_observation(),
            "teams": [
                {
                    "kit_color": "blue",
                    "visible_players": 2,
                    "readable_jersey_numbers": [8, 11],
                }
            ],
        }
        observations.append({"timestamp_s": timestamp, "observation": observation})
    analysis = _good_analysis()
    analysis["honest_limits"] = ["no read produced for blue #11: player read timed out"]

    final = finalize_analysis(
        analysis,
        observations,
        model="vision-model",
        sampling={"interval_s": 30, "in_play_windows": [[0, 60]]},
        frames_failed=0,
        notes_scope="ours",
        required_player_pairs={("blue", 8), ("blue", 11)},
        omitted_player_pairs={("blue", 11)},
    )

    assert "no read produced for blue #11" in " ".join(final["honest_limits"])


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
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(model_caption)

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)

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
    assert calls[0]["num_predict"] == qwen_analysis.CAPTION_NUM_PREDICT


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


def test_ollama_chat_passes_num_predict_and_repeat_penalty(monkeypatch):
    request_bodies = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"message": {"content": "{}"}}).encode()

    def fake_urlopen(request, timeout):
        request_bodies.append(json.loads(request.data))
        assert timeout == 17
        return FakeResponse()

    monkeypatch.setattr(qwen_analysis.urllib.request, "urlopen", fake_urlopen)

    qwen_analysis.ollama_chat(
        "prompt",
        ollama_url="http://ollama.invalid",
        model="vision-model",
        timeout_s=17,
        num_predict=123,
    )

    assert request_bodies[0]["options"] == {
        "temperature": 0,
        "repeat_penalty": 1.15,
        "num_predict": 123,
    }


def test_run_passes_frame_and_team_caps_with_separate_timeouts(monkeypatch, tmp_path):
    video_path = tmp_path / "match.mp4"
    video_path.write_bytes(b"video")
    out_dir = tmp_path / "out"
    calls = []

    monkeypatch.setenv("VIDEO_DECODE_SANDBOX", "0")
    monkeypatch.setenv("QWEN_CAPTIONS", "0")
    monkeypatch.setenv("QWEN_ANALYSIS_TIMEOUT_S", "17")
    monkeypatch.setenv("QWEN_AGGREGATION_TIMEOUT_S", "1201")
    monkeypatch.setattr(
        qwen_analysis.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args: None)

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        if "image_path" in kwargs:
            return json.dumps(_good_observation())
        return json.dumps(
            {
                "match_summary": "A compact sampled match summary.",
                "team_analysis": _good_analysis()["team_analysis"],
                "honest_limits": [],
            }
        )

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)

    assert (
        qwen_analysis.run(
            [
                "--video",
                str(video_path),
                "--out",
                str(out_dir),
                "--kickoff-s",
                "0",
                "--end-s",
                "30",
            ]
        )
        == 0
    )
    assert [call["timeout_s"] for call in calls] == [17.0, 1201.0]
    assert [call["num_predict"] for call in calls] == [
        qwen_analysis.FRAME_NUM_PREDICT,
        qwen_analysis.TEAM_NUM_PREDICT,
    ]


def test_run_fails_when_more_than_half_of_required_player_reads_fail(
    monkeypatch, tmp_path
):
    video_path = tmp_path / "match.mp4"
    video_path.write_bytes(b"video")
    out_dir = tmp_path / "out"

    observation = {
        **_good_observation(),
        "teams": [
            {
                "kit_color": "blue",
                "visible_players": 1,
                "readable_jersey_numbers": [8],
            }
        ],
    }
    monkeypatch.setenv("VIDEO_DECODE_SANDBOX", "0")
    monkeypatch.setenv("QWEN_CAPTIONS", "0")
    monkeypatch.setattr(
        qwen_analysis.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args: None)

    def fake_ollama_chat(prompt, **kwargs):
        if "image_path" in kwargs:
            return json.dumps(observation)
        return json.dumps({"observations": [], "confidence": "low"})

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)

    with pytest.raises(RuntimeError, match=r"1 of 1 required player reads failed"):
        qwen_analysis.run(
            [
                "--video",
                str(video_path),
                "--out",
                str(out_dir),
                "--kickoff-s",
                "0",
                "--end-s",
                "60",
            ]
        )


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


@pytest.mark.parametrize(
    ("total", "failed", "expected"),
    [(4, 2, False), (4, 3, True), (1, 1, True), (0, 0, False)],
)
def test_more_than_half_player_read_failure_rule(total, failed, expected):
    assert too_many_player_read_failures(total, failed) is expected
