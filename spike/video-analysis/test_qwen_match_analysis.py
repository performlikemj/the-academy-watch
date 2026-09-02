import errno
import hashlib
import json
import sys
import urllib.error
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
    eligible_brief_reads,
    filter_player_notes,
    finalize_analysis,
    generate_player_reads,
    generate_team_pass,
    generate_window_captions,
    gate_brief_checks,
    grounded_caption_schema,
    grounded_read_schema,
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
            "captions_action_type_coerced": 0,
            "captions_action_type_recovered": 0,
            "captions_zone_coerced": 0,
            "captions_claims_dropped": 0,
            "brief_checks_total": 0,
            "brief_checks_evidence_found": 0,
            "brief_checks_downgraded": 0,
            "notes_scope": "ours",
            "grounding": {
                "caption_windows": 0,
                "caption_grounded": 0,
                "read_observations": 0,
                "read_grounded": 0,
                "iou_threshold": 0.5,
                "containment_threshold": 0.8,
            },
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
                "read_model": "qwen3-vl:8b",
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


def test_grounded_player_prompt_bounds_observations_by_importance():
    prompt = build_player_prompt(
        ("blue", 8),
        [{"timestamp_s": 10, "observation": _good_observation()}],
        grounded_contract=True,
    )

    assert "Return at most 3 observations, most important first." in prompt
    assert '"confidence":str' in prompt
    expected_sentence = (
        "confidence must be exactly one of: "
        f"{', '.join(qwen_analysis.PLAYER_CONFIDENCE_LEVELS)} — a single word, "
        "never a list or several joined by '|'."
    )
    assert prompt.count(expected_sentence) == 1
    assert "|".join(qwen_analysis.PLAYER_CONFIDENCE_LEVELS) not in prompt


def test_grounded_player_prompt_without_brief_is_byte_identical_snapshot():
    prompt = build_player_prompt(
        ("blue", 8),
        [
            {
                "timestamp_s": 10,
                "observation": {
                    "teams": [],
                    "ball_visible": True,
                    "phase_of_play": "attack",
                    "visible_pitch_zone": "central",
                    "observation": "sample",
                    "notable_actions": [],
                },
            }
        ],
        grounded_contract=True,
    )

    assert hashlib.sha256(prompt.encode()).hexdigest() == (
        "d0351da91685738b3d18f65ef4696da228bcd9d495b793ec48a4f11cd7baf45e"
    )


def _schema_definition(schema, name):
    for value in _walk_schema(schema):
        if isinstance(value, dict) and value.get("title") == name:
            return value
    raise AssertionError(f"schema definition not found: {name}")


def _walk_schema(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_schema(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_schema(item)


@pytest.mark.parametrize(
    ("builder", "definition", "field", "expected"),
    (
        (
            grounded_caption_schema,
            "GroundedWindowCaption",
            "action_type",
            qwen_analysis.ACTION_TYPES,
        ),
        (
            grounded_caption_schema,
            "GroundedWindowCaption",
            "visible_pitch_zone",
            qwen_analysis.PITCH_ZONES,
        ),
        (
            grounded_caption_schema,
            "GroundedClaim",
            "confidence",
            qwen_analysis.CLAIM_CONFIDENCE_LEVELS,
        ),
        (
            grounded_caption_schema,
            "GroundedClaim",
            "visibility",
            qwen_analysis.CLAIM_VISIBILITY_LEVELS,
        ),
        (
            grounded_read_schema,
            "GroundedPlayerRead",
            "confidence",
            qwen_analysis.PLAYER_CONFIDENCE_LEVELS,
        ),
    ),
)
def test_grounded_schema_enums_equal_validator_constants(
    builder, definition, field, expected
):
    schema = builder()

    assert _schema_definition(schema, definition)["properties"][field]["enum"] == list(
        expected
    )


@pytest.mark.parametrize(
    ("builder", "container", "items_field", "item_definition"),
    (
        (grounded_caption_schema, "GroundedWindowCaption", "claims", "GroundedClaim"),
        (
            grounded_read_schema,
            "GroundedPlayerRead",
            "observations",
            "GroundedObservation",
        ),
    ),
)
def test_grounded_schemas_forbid_extras_bound_items_and_serialize(
    builder, container, items_field, item_definition
):
    schema = builder()
    container_schema = _schema_definition(schema, container)
    item_schema = _schema_definition(schema, item_definition)

    assert schema["additionalProperties"] is False
    assert container_schema["additionalProperties"] is False
    assert item_schema["additionalProperties"] is False
    assert container_schema["properties"][items_field]["maxItems"] == 3
    box_schema = item_schema["properties"]["box"]
    assert box_schema["minItems"] == box_schema["maxItems"] == 4
    json.dumps(schema)


@pytest.mark.parametrize("builder", (grounded_caption_schema, grounded_read_schema))
def test_grounded_schemas_inline_refs_and_require_every_object_property(builder):
    schema = builder()

    assert "$ref" not in json.dumps(schema)
    assert "$defs" not in json.dumps(schema)
    for value in _walk_schema(schema):
        if isinstance(value, dict) and value.get("type") == "object":
            assert value["required"] == list(value["properties"])


def test_grounded_schemas_raise_before_calls_when_pydantic_is_missing(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setitem(sys.modules, "pydantic", None)
    monkeypatch.setattr(
        qwen_analysis, "ollama_chat", lambda *args, **kwargs: calls.append(kwargs)
    )

    with pytest.raises(ImportError):
        generate_window_captions(
            [
                {
                    "tracklet_id": 10,
                    "roster_entry_id": 42,
                    "roster_jersey_number": 8,
                    "kit_color": "blue",
                    "start_s": 10.0,
                    "end_s": 20.0,
                    "box_track": [[10.0, 100, 100, 200, 200]],
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
            model="qwen3-vl:8b",
            timeout_s=30,
            frame_size=(1000, 1000),
        )

    with pytest.raises(ImportError):
        generate_player_reads(
            {("blue", 8)},
            [
                {
                    "timestamp_s": 10,
                    "filename": "frame_10.jpg",
                    "observation": _good_observation(),
                }
            ],
            frames_dir=tmp_path,
            ollama_url="http://ollama.invalid",
            model="qwen3-vl:8b",
            timeout_s=30,
            frame_size=(1000, 1000),
            player_tracks={"42": [[10.0, 100, 100, 200, 200]]},
            player_roster_ids={("blue", 8): 42},
        )

    assert calls == []


def test_legacy_caption_and_read_do_not_import_pydantic(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setitem(sys.modules, "pydantic", None)
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args: None)

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(
            {
                "caption": "Blue #8 carries through the central zone.",
                "action_type": "carry",
                "player_visible": True,
                "visible_pitch_zone": "central",
            }
        )

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
    assert len(captions) == 1
    assert len(calls) == 1
    assert calls[0]["response_schema"] is None

    calls.clear()

    def fake_player_chat(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(
            {
                "observations": ["Seen at t=10 in the central zone."],
                "confidence": "low",
            }
        )

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_player_chat)
    notes, limits, omitted = generate_player_reads(
        {("blue", 8)},
        [
            {
                "timestamp_s": 10,
                "filename": "frame_10.jpg",
                "observation": _good_observation(),
            }
        ],
        frames_dir=tmp_path,
        ollama_url="http://ollama.invalid",
        model="vision-model",
        timeout_s=30,
    )

    assert len(notes) == 1
    assert limits == []
    assert omitted == set()
    assert len(calls) == 1
    assert calls[0]["response_schema"] is None


def test_legacy_player_prompt_is_byte_identical_snapshot():
    prompt = build_player_prompt(
        ("blue", 8),
        [
            {
                "timestamp_s": 10,
                "observation": {
                    "phase_of_play": "attack",
                    "visible_pitch_zone": "central",
                    "observation": "Blue #8 carries forward.",
                    "notable_actions": ["carry"],
                },
            }
        ],
    )

    assert hashlib.sha256(prompt.encode()).hexdigest() == (
        "5b2b134bbd8938d400599184ecd90a2631cc977556c619b6758430994324627c"
    )


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
    assert all(call["response_schema"] is None for call in calls)


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
    assert all(call["response_schema"] is None for call in calls)
    assert notes == []
    assert omitted == {("blue", 8)}
    assert len(limits) == 1
    assert limits[0].startswith("no read produced for blue #8:")


def test_grounded_player_read_keeps_only_tracking_verified_observations(
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
    response = {
        "observations": [
            {
                "observation": "Checks into the central lane.",
                "box_t": 10,
                "box": [100, 100, 200, 200],
            },
            {
                "observation": "Runs beyond the back line.",
                "box_t": 40,
                "box": [800, 800, 900, 900],
            },
        ],
        "confidence": "medium",
    }
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise qwen_analysis.OllamaOutputTruncated("truncated")
        return json.dumps(response)

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(qwen_analysis.shutil, "copyfile", lambda *args: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    counts = {"read_observations": 0, "read_grounded": 0}

    notes, limits, omitted = generate_player_reads(
        {("blue", 8)},
        observations,
        frames_dir=tmp_path,
        ollama_url="http://ollama.invalid",
        model="qwen3-vl:8b",
        timeout_s=17,
        frame_size=(1000, 1000),
        player_tracks={
            "42": [
                [10.0, 100, 100, 200, 200],
                [40.0, 100, 100, 200, 200],
            ]
        },
        player_roster_ids={("blue", 8): 42},
        grounding_counts=counts,
    )

    assert limits == []
    assert omitted == set()
    assert counts == {"read_observations": 2, "read_grounded": 1}
    assert notes[0]["observations"] == ["Checks into the central lane."]
    assert notes[0]["evidence"] == [{"t": 10, "box": [100, 100, 200, 200], "iou": 1.0}]
    assert notes[0]["read_model"] == "qwen3-vl:8b"
    assert [call["num_predict"] for call in calls] == [
        qwen_analysis.GROUNDED_PLAYER_NUM_PREDICT,
        qwen_analysis.GROUNDED_PLAYER_NUM_PREDICT * 2,
    ]
    assert all(call["response_schema"] == grounded_read_schema() for call in calls)


def test_player_read_with_no_grounded_observation_is_failed(monkeypatch, tmp_path):
    observations = [
        {
            "timestamp_s": 10,
            "filename": "frame_10.jpg",
            "observation": _good_observation(),
        }
    ]
    response = {
        "observations": [
            {
                "observation": "The player shoots.",
                "box_t": 10,
                "box": [800, 800, 900, 900],
            }
        ],
        "confidence": "low",
    }
    monkeypatch.setattr(
        qwen_analysis, "ollama_chat", lambda *args, **kwargs: json.dumps(response)
    )
    monkeypatch.setattr(qwen_analysis.shutil, "copyfile", lambda *args: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)

    notes, limits, omitted = generate_player_reads(
        {("blue", 8)},
        observations,
        frames_dir=tmp_path,
        ollama_url="http://ollama.invalid",
        model="qwen3-vl:8b",
        timeout_s=17,
        frame_size=(1000, 1000),
        player_tracks={"42": [[10.0, 100, 100, 200, 200]]},
        player_roster_ids={("blue", 8): 42},
    )

    assert notes == []
    assert omitted == {("blue", 8)}
    assert limits == [
        "no read produced for blue #8: no observation could be verified against tracking"
    ]


def test_legacy_player_read_keeps_text_but_omits_grounding_evidence(
    monkeypatch, tmp_path
):
    observations = [
        {
            "timestamp_s": 10,
            "filename": "frame_10.jpg",
            "observation": _good_observation(),
        }
    ]
    monkeypatch.setattr(
        qwen_analysis,
        "ollama_chat",
        lambda *args, **kwargs: json.dumps(
            {
                "observations": ["Seen at t=10 in the central zone."],
                "confidence": "low",
            }
        ),
    )

    notes, limits, omitted = generate_player_reads(
        {("blue", 8)},
        observations,
        frames_dir=tmp_path,
        ollama_url="http://ollama.invalid",
        model="qwen3-vl:8b",
        timeout_s=17,
    )

    assert limits == []
    assert omitted == set()
    assert notes[0]["observations"] == ["Seen at t=10 in the central zone."]
    assert notes[0]["read_model"] == "qwen3-vl:8b"
    assert "evidence" not in notes[0]


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
    assert final["sampling"]["captions_action_type_coerced"] == 0
    assert final["sampling"]["captions_action_type_recovered"] == 0
    assert final["sampling"]["captions_zone_coerced"] == 0
    assert final["sampling"]["captions_claims_dropped"] == 0
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
    assert "at most 3 claims" not in prompt

    grounded_prompt = build_caption_prompt(
        {
            "roster_jersey_number": 8,
            "kit_color": "blue",
            "tracklet_id": 10,
            "start_s": 10,
            "end_s": 20,
        },
        grounded_contract=True,
    )
    assert "Return at most 3 claims, most important first." in grounded_prompt
    for field, noun, choices in (
        ("action_type", "word", qwen_analysis.ACTION_TYPES),
        ("visible_pitch_zone", "value", qwen_analysis.PITCH_ZONES),
        ("confidence", "word", qwen_analysis.CLAIM_CONFIDENCE_LEVELS),
        ("visibility", "word", qwen_analysis.CLAIM_VISIBILITY_LEVELS),
    ):
        assert f'"{field}":str' in grounded_prompt
        expected_sentence = (
            f"{field} must be exactly one of: {', '.join(choices)} — a single "
            f"{noun}, never a list or several joined by '|'."
        )
        assert grounded_prompt.count(expected_sentence) == 1
        assert "|".join(choices) not in grounded_prompt


def test_legacy_caption_prompt_is_byte_identical_snapshot():
    prompt = build_caption_prompt(
        {
            "roster_jersey_number": 8,
            "kit_color": "blue",
            "tracklet_id": 10,
            "start_s": 10,
            "end_s": 20,
        }
    )

    assert hashlib.sha256(prompt.encode()).hexdigest() == (
        "0f8196d66e8c34a72b4cc60af40e4965e1f16b548d209cd516ae3e975bb25bcb"
    )


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


def test_grounded_caption_coerces_unknown_action_and_keeps_window(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(
            {
                "claims": [],
                "action_type": "progressive dribble",
                "visible_pitch_zone": "central",
            }
        )

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)
    counts = {"captions_action_type_coerced": 0}

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        captions, failed = generate_window_captions(
            [
                {
                    "tracklet_id": 10,
                    "roster_entry_id": 42,
                    "roster_jersey_number": 8,
                    "kit_color": "blue",
                    "start_s": 10.0,
                    "end_s": 20.0,
                    "box_track": [[10.0, 100, 100, 200, 200]],
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
            model="qwen3-vl:8b",
            timeout_s=30,
            frame_size=(1000, 1000),
            fault_counts=counts,
        )

    assert failed == 0
    assert captions[0]["action_type"] == "unclear"
    assert counts["captions_action_type_coerced"] == 1
    assert calls[0]["response_schema"] == grounded_caption_schema()
    assert (
        "grounded caption action_type 'progressive dribble' not in vocabulary; "
        "coerced to 'unclear' (tracklet 10 at 10.0s)" in caplog.text
    )


@pytest.mark.parametrize(
    ("raw_action_type", "expected_action_type", "expected_recovered"),
    (
        ("carry|unclear", "unclear", 0),
        ("duel|xx", "duel", 1),
        ("duel|duel", "duel", 1),
        ("unclear|xx", "unclear", 0),
        ("carry|pass", "unclear", 0),
    ),
)
def test_grounded_caption_recovers_only_one_valid_pipe_token(
    raw_action_type, expected_action_type, expected_recovered, caplog
):
    counts = {
        "captions_action_type_coerced": 0,
        "captions_action_type_recovered": 0,
    }

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        parsed = parse_window_caption(
            json.dumps(
                {
                    "claims": [],
                    "action_type": raw_action_type,
                    "visible_pitch_zone": "central",
                }
            ),
            {"tracklet_id": 10, "start_s": 10.0, "end_s": 20.0},
            grounded_contract=True,
            fault_counts=counts,
        )

    assert parsed["action_type"] == expected_action_type
    assert counts["captions_action_type_coerced"] == 1
    assert counts["captions_action_type_recovered"] == expected_recovered
    assert ("single-choice recovered" in caplog.text) is bool(expected_recovered)


def test_grounded_caption_drops_only_malformed_claim(caplog):
    good_claim = {
        "claim": "Blue #8 checks toward the ball.",
        "t0": 10,
        "t1": 20,
        "box_t": 10,
        "box": [100, 100, 200, 200],
        "confidence": "high",
        "visibility": "clear",
    }
    malformed_claim = {"claim": "Blue #8 turns."}
    counts = {"captions_claims_dropped": 0}

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        parsed = parse_window_caption(
            json.dumps(
                {
                    "claims": [good_claim, malformed_claim],
                    "action_type": "off_ball",
                    "visible_pitch_zone": "central",
                }
            ),
            {"tracklet_id": 10, "start_s": 10.0, "end_s": 20.0},
            grounded_contract=True,
            fault_counts=counts,
        )

    assert parsed["claims"] == [good_claim]
    assert counts["captions_claims_dropped"] == 1
    assert "grounded claim is missing required keys" in caplog.text
    assert repr(malformed_claim) in caplog.text


def test_grounded_caption_keeps_window_when_all_claims_are_malformed(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    monkeypatch.setattr(
        qwen_analysis,
        "ollama_chat",
        lambda *args, **kwargs: json.dumps(
            {
                "claims": [{"claim": "Missing evidence."}, "not an object"],
                "action_type": "unclear",
                "visible_pitch_zone": "unclear",
            }
        ),
    )
    gated_claims = []
    original_gate = qwen_analysis._gate_model_items

    def capture_gate(items, *args):
        gated_claims.append(items)
        return original_gate(items, *args)

    monkeypatch.setattr(qwen_analysis, "_gate_model_items", capture_gate)
    counts = {"captions_claims_dropped": 0}

    captions, failed = generate_window_captions(
        [
            {
                "tracklet_id": 10,
                "roster_entry_id": 42,
                "roster_jersey_number": 8,
                "kit_color": "blue",
                "start_s": 10.0,
                "end_s": 20.0,
                "box_track": [[10.0, 100, 100, 200, 200]],
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
        model="qwen3-vl:8b",
        timeout_s=30,
        frame_size=(1000, 1000),
        fault_counts=counts,
    )

    assert failed == 0
    assert gated_claims == [[]]
    assert captions[0]["grounded"] is False
    assert counts["captions_claims_dropped"] == 2


def test_legacy_caption_still_rejects_unknown_action_type():
    caption = {
        "caption": "Blue #8 moves through midfield.",
        "action_type": "progressive dribble",
        "player_visible": True,
        "visible_pitch_zone": "central",
    }

    with pytest.raises(ValueError) as exc_info:
        parse_window_caption(json.dumps(caption))

    assert str(exc_info.value) == "window caption.action_type is invalid"


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
            "caption": None,
            "action_type": "carry",
            "player_visible": False,
            "visible_pitch_zone": "central",
            "grounded": False,
            "box_t": None,
            "box": None,
            "evidence_iou": None,
            "caption_model": "vision-model",
        }
    ]
    assert calls[0]["num_predict"] == qwen_analysis.CAPTION_NUM_PREDICT
    assert calls[0]["response_schema"] is None


def test_legacy_caption_truncation_retries_without_doubling_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        raise qwen_analysis.OllamaOutputTruncated("truncated")

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
        model="qwen3-vl:8b",
        timeout_s=30,
    )

    assert captions == []
    assert failed == 1
    assert [call["num_predict"] for call in calls] == [
        qwen_analysis.CAPTION_NUM_PREDICT,
        qwen_analysis.CAPTION_NUM_PREDICT,
    ]


def test_grounded_caption_keeps_best_supported_claim_and_withholds_rejected_one(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    model_caption = {
        "claims": [
            {
                "claim": "Blue #8 checks toward the ball.",
                "t0": 10,
                "t1": 20,
                "box_t": 10,
                "box": [100, 100, 200, 200],
                "confidence": "high",
                "visibility": "clear",
            },
            {
                "claim": "Blue #8 makes a run.",
                "t0": 10,
                "t1": 20,
                "box_t": 20,
                "box": [800, 800, 900, 900],
                "confidence": "medium",
                "visibility": "partial",
            },
        ],
        "action_type": "off_ball",
        "visible_pitch_zone": "central",
    }
    monkeypatch.setattr(
        qwen_analysis, "ollama_chat", lambda *args, **kwargs: json.dumps(model_caption)
    )
    counts = {"caption_grounded": 0}

    captions, failed = generate_window_captions(
        [
            {
                "tracklet_id": 10,
                "roster_entry_id": 42,
                "roster_jersey_number": 8,
                "kit_color": "blue",
                "start_s": 10.0,
                "end_s": 20.0,
                "box_track": [
                    [10.0, 100, 100, 200, 200],
                    [20.0, 100, 100, 200, 200],
                ],
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
        model="qwen3-vl:8b",
        timeout_s=30,
        frame_size=(1000, 1000),
        grounding_counts=counts,
    )

    assert failed == 0
    assert counts == {"caption_grounded": 1}
    assert captions[0]["caption"] == "Blue #8 checks toward the ball."
    assert captions[0]["grounded"] is True
    assert captions[0]["box"] == [100, 100, 200, 200]
    assert captions[0]["evidence_iou"] == 1.0
    assert captions[0]["caption_model"] == "qwen3-vl:8b"


def test_grounded_caption_retries_truncation_with_doubled_cap(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    response = {
        "claims": [
            {
                "claim": "Blue #8 checks toward the ball.",
                "t0": 10,
                "t1": 20,
                "box_t": 10,
                "box": [100, 100, 200, 200],
                "confidence": "high",
                "visibility": "clear",
            }
        ],
        "action_type": "off_ball",
        "visible_pitch_zone": "central",
    }
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise qwen_analysis.OllamaOutputTruncated("truncated")
        return json.dumps(response)

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        captions, failed = generate_window_captions(
            [
                {
                    "tracklet_id": 10,
                    "roster_entry_id": 42,
                    "roster_jersey_number": 8,
                    "kit_color": "blue",
                    "start_s": 10.0,
                    "end_s": 20.0,
                    "box_track": [[10.0, 100, 100, 200, 200]],
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
            model="qwen3-vl:8b",
            timeout_s=30,
            frame_size=(1000, 1000),
        )

    assert failed == 0
    assert captions[0]["caption"] == "Blue #8 checks toward the ball."
    assert [call["num_predict"] for call in calls] == [
        qwen_analysis.GROUNDED_CAPTION_NUM_PREDICT,
        qwen_analysis.GROUNDED_CAPTION_NUM_PREDICT * 2,
    ]
    assert "caption output truncated at 900 tokens; retrying with 1800" in caplog.text
    assert "tracklet 10 at 10.0s" in caplog.text


def test_grounded_caption_schema_error_retries_without_doubling_cap(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    response = {
        "claims": [
            {
                "claim": "Blue #8 checks toward the ball.",
                "t0": 10,
                "t1": 20,
                "box_t": 10,
                "box": [100, 100, 200, 200],
                "confidence": "high",
                "visibility": "clear",
            }
        ],
        "action_type": "off_ball",
        "visible_pitch_zone": "central",
    }
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ValueError("schema mismatch")
        return json.dumps(response)

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
                "box_track": [[10.0, 100, 100, 200, 200]],
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
        model="qwen3-vl:8b",
        timeout_s=30,
        frame_size=(1000, 1000),
    )

    assert failed == 0
    assert captions[0]["caption"] == "Blue #8 checks toward the ball."
    assert [call["num_predict"] for call in calls] == [
        qwen_analysis.GROUNDED_CAPTION_NUM_PREDICT,
        qwen_analysis.GROUNDED_CAPTION_NUM_PREDICT,
    ]


def test_grounded_caption_second_truncation_marks_window_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    calls = []

    def fake_ollama_chat(*args, **kwargs):
        calls.append(kwargs)
        raise qwen_analysis.OllamaOutputTruncated("truncated")

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
                "box_track": [[10.0, 100, 100, 200, 200]],
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
        model="qwen3-vl:8b",
        timeout_s=30,
        frame_size=(1000, 1000),
    )

    assert captions == []
    assert failed == 1
    assert [call["num_predict"] for call in calls] == [
        qwen_analysis.GROUNDED_CAPTION_NUM_PREDICT,
        qwen_analysis.GROUNDED_CAPTION_NUM_PREDICT * 2,
    ]


def test_tracked_caption_with_only_unsupported_claim_is_withheld(monkeypatch, tmp_path):
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    response = {
        "claims": [
            {
                "claim": "The player shoots.",
                "t0": 10,
                "t1": 20,
                "box_t": 10,
                "box": [800, 800, 900, 900],
                "confidence": "high",
                "visibility": "clear",
            }
        ],
        "action_type": "shot",
        "visible_pitch_zone": "right",
    }
    monkeypatch.setattr(
        qwen_analysis, "ollama_chat", lambda *args, **kwargs: json.dumps(response)
    )

    captions, failed = generate_window_captions(
        [
            {
                "tracklet_id": 10,
                "roster_entry_id": 42,
                "roster_jersey_number": 8,
                "start_s": 10.0,
                "end_s": 20.0,
                "box_track": [[10.0, 100, 100, 200, 200]],
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
        model="qwen3-vl:8b",
        timeout_s=30,
        frame_size=(1000, 1000),
    )

    assert failed == 0
    assert captions[0]["caption"] is None
    assert captions[0]["player_visible"] is False
    assert captions[0]["grounded"] is False


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
            "box_track": [],
        }
    ]


def test_context_preserves_frame_size_caption_tracks_and_player_tracks(tmp_path):
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "frame_size": [1920, 1080],
                "caption_windows": [
                    {
                        "tracklet_id": 10,
                        "roster_entry_id": 42,
                        "roster_jersey_number": 8,
                        "start_s": 10,
                        "end_s": 20,
                        "box_track": [[10, 100, 100, 200, 200]],
                    }
                ],
                "player_tracks": {
                    "42": [[10, 100, 100, 200, 200]],
                },
            }
        )
    )

    context = qwen_analysis._load_context(context_path)

    assert context["frame_size"] == [1920, 1080]
    assert context["caption_windows"][0]["box_track"] == [
        [10.0, 100.0, 100.0, 200.0, 200.0]
    ]
    assert context["player_tracks"]["42"] == [[10.0, 100.0, 100.0, 200.0, 200.0]]


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

    monkeypatch.delenv("QWEN_NUM_CTX", raising=False)
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
        "num_ctx": 65536,
        "num_predict": 123,
    }


def test_ollama_chat_request_body_snapshots_schema_and_legacy_formats(
    monkeypatch, tmp_path
):
    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpeg")
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
        return FakeResponse()

    monkeypatch.delenv("QWEN_NUM_CTX", raising=False)
    monkeypatch.setattr(qwen_analysis.urllib.request, "urlopen", fake_urlopen)
    schema = grounded_caption_schema()
    common = {
        "model": "qwen3-vl:8b",
        "think": False,
        "stream": False,
        "options": {
            "temperature": 0,
            "repeat_penalty": 1.15,
            "num_ctx": 65536,
            "num_predict": 900,
        },
        "messages": [{"role": "user", "content": "prompt"}],
    }

    for response_schema in (schema, None):
        qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="qwen3-vl:8b",
            timeout_s=17,
            num_predict=900,
            image_path=image_path,
            response_schema=response_schema,
        )

    bodies_without_images = []
    for body in request_bodies:
        body["messages"][0].pop("images")
        bodies_without_images.append(body)
    assert bodies_without_images == [
        {**common, "format": schema},
        {**common, "format": "json"},
    ]


def test_ollama_chat_returns_complete_json_at_length_cap(monkeypatch, caplog):
    answer = '{"claims": []}\n\n'

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "message": {"content": answer},
                    "done_reason": "length",
                }
            ).encode()

    monkeypatch.setattr(
        qwen_analysis.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse()
    )
    metadata = {}

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        result = qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="qwen3-vl:8b",
            timeout_s=17,
            num_predict=321,
            response_metadata=metadata,
        )

    assert result == answer
    assert metadata == {"done_reason": "length", "from_thinking": False}
    assert (
        "ollama hit num_predict=321 for model qwen3-vl:8b but the JSON is complete; "
        "using it"
    ) in caplog.text


def test_ollama_chat_raises_output_truncated_for_length_done_reason(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "message": {"content": '{"claims":['},
                    "done_reason": "length",
                }
            ).encode()

    monkeypatch.setattr(
        qwen_analysis.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse()
    )
    metadata = {}

    with pytest.raises(
        qwen_analysis.OllamaOutputTruncated,
        match=r"qwen3-vl:8b.*num_predict=321",
    ):
        qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="qwen3-vl:8b",
            timeout_s=17,
            num_predict=321,
            response_metadata=metadata,
        )

    assert metadata == {"done_reason": "length"}


def test_ollama_chat_uses_thinking_when_content_is_empty(monkeypatch, caplog):
    answer = '{"claims":[{"claim":"Visible movement"}]}'

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {"message": {"content": "  ", "thinking": answer}}
            ).encode()

    monkeypatch.setattr(
        qwen_analysis.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse()
    )
    monkeypatch.setattr(qwen_analysis, "_thinking_fallback_warning_emitted", False)
    metadata = {}

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        first = qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="qwen3-vl:8b",
            timeout_s=17,
            response_metadata=metadata,
        )
        second = qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="qwen3-vl:8b",
            timeout_s=17,
        )

    assert first == answer
    assert second == answer
    assert metadata == {"done_reason": None, "from_thinking": True}
    assert [record.message for record in caplog.records] == [
        "ollama returned the answer in the thinking field for model qwen3-vl:8b; using it"
    ]


def test_ollama_chat_prefers_nonempty_content_over_thinking(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "done_reason": "stop",
                    "message": {
                        "content": "content answer",
                        "thinking": "thinking answer",
                    },
                }
            ).encode()

    monkeypatch.setattr(
        qwen_analysis.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse()
    )
    metadata = {}

    result = qwen_analysis.ollama_chat(
        "prompt",
        ollama_url="http://ollama.invalid",
        model="qwen3-vl:8b",
        timeout_s=17,
        response_metadata=metadata,
    )

    assert result == "content answer"
    assert metadata == {"done_reason": "stop", "from_thinking": False}


def test_ollama_chat_omits_num_ctx_when_disabled(monkeypatch):
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
        return FakeResponse()

    monkeypatch.setenv("QWEN_NUM_CTX", "0")
    monkeypatch.setattr(qwen_analysis.urllib.request, "urlopen", fake_urlopen)

    qwen_analysis.ollama_chat(
        "prompt",
        ollama_url="http://ollama.invalid",
        model="vision-model",
        timeout_s=17,
    )

    assert "num_ctx" not in request_bodies[0]["options"]


def test_ollama_chat_retries_connection_refused_then_succeeds(monkeypatch, caplog):
    attempts = 0
    sleeps = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"message": {"content": "result"}}).encode()

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise urllib.error.URLError(
                OSError(errno.ECONNREFUSED, "Connection refused")
            )
        return FakeResponse()

    monkeypatch.setenv("QWEN_TRANSIENT_RETRY_S", "0.25")
    monkeypatch.setattr(qwen_analysis.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qwen_analysis.time, "sleep", sleeps.append)

    with caplog.at_level("WARNING", logger="qwen_match_analysis"):
        result = qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="vision-model",
            timeout_s=17,
        )

    assert result == "result"
    assert attempts == 3
    assert sleeps == [0.25, 0.25]
    assert [record.levelname for record in caplog.records] == ["WARNING", "WARNING"]


def test_ollama_chat_raises_after_transient_retries_are_exhausted(monkeypatch):
    attempts = 0
    sleeps = []

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise urllib.error.URLError(
            OSError(errno.ECONNRESET, "Connection reset by peer")
        )

    monkeypatch.setattr(qwen_analysis.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qwen_analysis.time, "sleep", sleeps.append)

    with pytest.raises(urllib.error.URLError, match="Connection reset by peer"):
        qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="vision-model",
            timeout_s=17,
        )

    assert attempts == 6
    assert sleeps == [5.0, 15.0, 30.0, 60.0, 60.0]


def test_ollama_chat_does_not_retry_timeout(monkeypatch):
    attempts = 0
    sleeps = []

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise TimeoutError("timed out")

    monkeypatch.setattr(qwen_analysis.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qwen_analysis.time, "sleep", sleeps.append)

    with pytest.raises(TimeoutError, match="timed out"):
        qwen_analysis.ollama_chat(
            "prompt",
            ollama_url="http://ollama.invalid",
            model="vision-model",
            timeout_s=17,
        )

    assert attempts == 1
    assert sleeps == []


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
    assert all(call["response_schema"] is None for call in calls)
    analysis = json.loads((out_dir / "analysis.json").read_text())
    assert analysis["sampling"]["grounding"] == {
        "caption_windows": 0,
        "caption_grounded": 0,
        "read_observations": 0,
        "read_grounded": 0,
        "iou_threshold": 0.5,
        "containment_threshold": 0.8,
    }
    assert (
        "0 of 0 clip notes and 0 of 0 read observations were verified against "
        "player tracking; unverified ones were withheld." in analysis["honest_limits"]
    )


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


def test_brief_player_prompt_numbers_expectations_and_forbids_negative_claims():
    sentinel = "SENTINEL_PRIVATE_EXPECTATION"
    prompt = build_player_prompt(
        ("blue", 8),
        [{"timestamp_s": 10, "observation": _good_observation()}],
        grounded_contract=True,
        brief={"lines": [sentinel, "Recover inside"], "hash": "a" * 64},
        system_brief={"lines": ["Press together"], "hash": "b" * 64},
    )

    assert (
        "The coach's expectations for this player, numbered: "
        f"1. {sentinel} 2. Recover inside" in prompt
    )
    assert "How the team plays: Press together" in prompt
    assert "Use evidence_found only when a supplied frame visibly supports" in prompt
    assert "otherwise use no_evidence with null box_t and box" in prompt
    assert "Never state or imply that an expectation was not met" in prompt
    assert '"expectation_checks"' in prompt


def test_team_pass_prompt_never_receives_separate_brief_text():
    sentinel = "SENTINEL_TEAM_MUST_NOT_SEE"
    analysis_context = {"our_kit_color": "blue"}
    brief_context = {
        "roster": {"42": {"lines": [sentinel], "hash": "a" * 64}},
        "system_brief": None,
    }

    prompt = build_team_prompt(
        [{"timestamp_s": 10, "observation": _good_observation()}],
        analysis_context,
    )

    assert sentinel not in prompt
    assert "brief" not in prompt.casefold()
    assert brief_context["roster"]["42"]["lines"][0] == sentinel


def test_brief_read_schema_is_strict_bounded_and_uses_verdict_vocabulary():
    schema = grounded_read_schema(with_brief=True)
    container = _schema_definition(schema, "GroundedBriefPlayerRead")
    check = _schema_definition(schema, "GroundedExpectationCheck")

    checks_schema = container["properties"]["expectation_checks"]
    assert checks_schema["minItems"] == 1
    assert checks_schema["maxItems"] == qwen_analysis.MAX_BRIEF_EXPECTATIONS
    assert check["properties"]["verdict"]["enum"] == list(
        qwen_analysis.BRIEF_CHECK_VERDICTS
    )
    assert check["additionalProperties"] is False
    assert schema["additionalProperties"] is False


def test_brief_read_schema_accepts_exact_checks_and_rejects_contract_violations():
    evidence = [{"timestamp_s": 10, "observation": _good_observation()}]
    valid = {
        "observations": [],
        "expectation_checks": [
            {
                "expectation_index": 1,
                "verdict": "evidence_found",
                "box_t": 10,
                "box": [100, 100, 200, 200],
            },
            {
                "expectation_index": 2,
                "verdict": "no_evidence",
                "box_t": None,
                "box": None,
            },
        ],
        "confidence": "low",
    }

    assert (
        parse_player_read(
            json.dumps(valid),
            evidence,
            grounded_contract=True,
            brief_expectation_count=2,
        )
        == valid
    )

    missing = {**valid, "expectation_checks": valid["expectation_checks"][:1]}
    with pytest.raises(ValueError, match="exactly one check per expectation"):
        parse_player_read(
            json.dumps(missing),
            evidence,
            grounded_contract=True,
            brief_expectation_count=2,
        )

    duplicate = {
        **valid,
        "expectation_checks": [
            valid["expectation_checks"][0],
            {**valid["expectation_checks"][1], "expectation_index": 1},
        ],
    }
    with pytest.raises(ValueError, match="each supplied index exactly once"):
        parse_player_read(
            json.dumps(duplicate),
            evidence,
            grounded_contract=True,
            brief_expectation_count=2,
        )

    non_null_no_evidence = {
        **valid,
        "expectation_checks": [
            valid["expectation_checks"][0],
            {
                **valid["expectation_checks"][1],
                "box_t": 10,
                "box": [100, 100, 200, 200],
            },
        ],
    }
    with pytest.raises(ValueError, match="no_evidence requires null"):
        parse_player_read(
            json.dumps(non_null_no_evidence),
            evidence,
            grounded_contract=True,
            brief_expectation_count=2,
        )


def test_gate_brief_checks_keeps_all_and_counts_downgrade():
    counts = {
        "brief_checks_total": 0,
        "brief_checks_evidence_found": 0,
        "brief_checks_downgraded": 0,
    }
    checks = [
        {
            "expectation_index": 1,
            "verdict": "evidence_found",
            "box_t": 10,
            "box": [100, 100, 200, 200],
        },
        {
            "expectation_index": 2,
            "verdict": "evidence_found",
            "box_t": 10,
            "box": [800, 800, 900, 900],
        },
        {
            "expectation_index": 3,
            "verdict": "no_evidence",
            "box_t": None,
            "box": None,
        },
    ]

    gated = gate_brief_checks(
        checks,
        "a" * 64,
        [[10, 100, 100, 200, 200]],
        (1000, 1000),
        counts,
    )

    assert [check["verdict"] for check in gated] == [
        "evidence_found",
        "no_evidence",
        "no_evidence",
    ]
    assert gated[0]["iou"] == 1.0
    assert set(gated[1]) == {"expectation_index", "brief_hash", "verdict"}
    assert counts == {
        "brief_checks_total": 3,
        "brief_checks_evidence_found": 1,
        "brief_checks_downgraded": 1,
    }


def test_analysis_accepts_zero_observations_when_brief_checks_are_non_empty():
    analysis = _good_analysis()
    analysis["player_notes"][0].update(
        {
            "observations": [],
            "brief_checks": [
                {
                    "expectation_index": 1,
                    "brief_hash": "a" * 64,
                    "verdict": "no_evidence",
                }
            ],
            "system_brief_hash": "b" * 64,
        }
    )
    analysis["sampling"].update(
        {
            "brief_checks_total": 1,
            "brief_checks_evidence_found": 0,
            "brief_checks_downgraded": 0,
        }
    )

    validate_analysis_schema(analysis, required_player_pairs={("blue", 8)})


def test_analysis_rejects_missing_brief_check_counter():
    analysis = _good_analysis()
    del analysis["sampling"]["brief_checks_downgraded"]

    with pytest.raises(
        ValueError,
        match="sampling.brief_checks_downgraded must be a non-negative integer",
    ):
        validate_analysis_schema(analysis)


def test_brief_eligibility_is_independent_of_recurrence_and_reports_ineligible():
    observations = [
        {
            "timestamp_s": 10,
            "filename": "frame_10.jpg",
            "observation": _good_observation(),
        }
    ]
    context = {
        "roster": {
            "42": {"lines": ["Hold width"], "hash": "a" * 64},
            "43": {"lines": ["Recover inside"], "hash": "b" * 64},
        },
        "system_brief": {"lines": ["Press together"], "hash": "c" * 64},
    }
    caption_windows = [
        {
            "roster_entry_id": 42,
            "roster_jersey_number": 8,
            "kit_color": "blue",
        },
        {
            "roster_entry_id": 43,
            "roster_jersey_number": 11,
            "kit_color": "blue",
        },
    ]

    eligible, limits = eligible_brief_reads(
        context,
        observations,
        caption_windows,
        {"42": [[10, 100, 100, 200, 200]], "43": []},
        (1000, 1000),
    )

    assert recurring_jersey_evidence(observations) == set()
    assert set(eligible) == {("blue", 8)}
    assert eligible[("blue", 8)]["system_brief"]["hash"] == "c" * 64
    assert limits == ["brief for #11 could not be checked: no verified frames"]


def test_briefed_read_persists_hashes_and_checks_but_never_brief_text(
    monkeypatch, tmp_path
):
    sentinel = "SENTINEL_BRIEF_MUST_NOT_PERSIST"
    system_sentinel = "SENTINEL_SYSTEM_MUST_NOT_PERSIST"
    response = {
        "observations": [
            {
                "observation": sentinel,
                "box_t": 10,
                "box": [100, 100, 200, 200],
            }
        ],
        "expectation_checks": [
            {
                "expectation_index": 1,
                "verdict": "no_evidence",
                "box_t": None,
                "box": None,
            }
        ],
        "confidence": "low",
    }
    calls = []

    def fake_ollama_chat(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return json.dumps(response)

    monkeypatch.setattr(qwen_analysis, "ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(qwen_analysis.shutil, "copyfile", lambda *args: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
    brief_counts = {
        "brief_checks_total": 0,
        "brief_checks_evidence_found": 0,
        "brief_checks_downgraded": 0,
    }

    notes, limits, omitted = generate_player_reads(
        set(),
        [
            {
                "timestamp_s": 10,
                "filename": "frame_10.jpg",
                "observation": _good_observation(),
            }
        ],
        frames_dir=tmp_path,
        ollama_url="http://ollama.invalid",
        model="qwen3-vl:8b",
        timeout_s=17,
        frame_size=(1000, 1000),
        player_tracks={"42": [[10, 100, 100, 200, 200]]},
        player_roster_ids={("blue", 8): 42},
        player_briefs={
            ("blue", 8): {
                "brief": {"lines": [sentinel], "hash": "a" * 64},
                "system_brief": {
                    "lines": [system_sentinel],
                    "hash": "b" * 64,
                },
            }
        },
        brief_counts=brief_counts,
    )

    assert limits == []
    assert omitted == set()
    assert notes[0]["observations"] == []
    assert notes[0]["brief_checks"] == [
        {
            "expectation_index": 1,
            "brief_hash": "a" * 64,
            "verdict": "no_evidence",
        }
    ]
    assert notes[0]["system_brief_hash"] == "b" * 64
    persisted = json.dumps(notes)
    assert sentinel not in persisted
    assert system_sentinel not in persisted
    assert sentinel in calls[0][0]
    assert calls[0][1]["response_schema"] == grounded_read_schema(with_brief=True)
    assert calls[0][1]["num_predict"] == qwen_analysis.GROUNDED_PLAYER_NUM_PREDICT


def test_grounded_player_cap_fits_eight_checks_plus_three_observations():
    response = {
        "observations": [
            {
                "observation": "A concise grounded observation " * 5,
                "box_t": 10,
                "box": [100, 100, 200, 200],
            }
            for _ in range(3)
        ],
        "expectation_checks": [
            {
                "expectation_index": index,
                "verdict": "evidence_found",
                "box_t": 10,
                "box": [100, 100, 200, 200],
            }
            for index in range(1, 9)
        ],
        "confidence": "medium",
    }

    assert len(json.dumps(response)) < qwen_analysis.GROUNDED_PLAYER_NUM_PREDICT * 3


def test_run_keeps_brief_out_of_team_prompt_and_persisted_analysis(
    monkeypatch, tmp_path
):
    sentinel = "SENTINEL_PRIVATE_RUN_BRIEF"
    system_sentinel = "SENTINEL_PRIVATE_RUN_SYSTEM"
    video_path = tmp_path / "match.mp4"
    video_path.write_bytes(b"video")
    out_dir = tmp_path / "out"
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "our_kit_color": "blue",
                "frame_size": [1000, 1000],
                "caption_windows": [
                    {
                        "tracklet_id": 7,
                        "roster_entry_id": 42,
                        "roster_jersey_number": 8,
                        "kit_color": "blue",
                        "start_s": 0,
                        "end_s": 3,
                        "box_track": [[0, 100, 100, 200, 200]],
                    }
                ],
                "player_tracks": {"42": [[0, 100, 100, 200, 200]]},
            }
        )
    )
    brief_path = tmp_path / "brief.json"
    brief_path.write_text(
        json.dumps(
            {
                "roster": {
                    "42": {"lines": [sentinel], "hash": "a" * 64},
                },
                "system_brief": {
                    "lines": [system_sentinel],
                    "hash": "b" * 64,
                },
            }
        )
    )
    prompts = {"player": [], "team": []}

    def fake_ollama_chat(prompt, **kwargs):
        if "image_path" in kwargs:
            return json.dumps(_good_observation())
        if "image_paths" in kwargs:
            prompts["player"].append(prompt)
            return json.dumps(
                {
                    "observations": [],
                    "expectation_checks": [
                        {
                            "expectation_index": 1,
                            "verdict": "no_evidence",
                            "box_t": None,
                            "box": None,
                        }
                    ],
                    "confidence": "low",
                }
            )
        prompts["team"].append(prompt)
        return json.dumps(
            {
                "match_summary": "A compact sampled match summary.",
                "team_analysis": _good_analysis()["team_analysis"],
                "honest_limits": [],
            }
        )

    monkeypatch.setenv("VIDEO_DECODE_SANDBOX", "0")
    monkeypatch.setenv("QWEN_CAPTIONS", "0")
    monkeypatch.setattr(
        qwen_analysis.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    monkeypatch.setattr(qwen_analysis, "extract_frame", lambda *args: None)
    monkeypatch.setattr(qwen_analysis.shutil, "copyfile", lambda *args: None)
    monkeypatch.setattr(qwen_analysis, "_draw_first_anchor", lambda *args: None)
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
                "1",
                "--context-json",
                str(context_path),
                "--brief-json",
                str(brief_path),
            ]
        )
        == 0
    )

    assert sentinel in prompts["player"][0]
    assert system_sentinel in prompts["player"][0]
    assert sentinel not in prompts["team"][0]
    assert system_sentinel not in prompts["team"][0]
    analysis = json.loads((out_dir / "analysis.json").read_text())
    serialized = json.dumps(analysis)
    assert sentinel not in serialized
    assert system_sentinel not in serialized
    assert analysis["sampling"]["brief_checks_total"] == 1
    assert analysis["sampling"]["brief_checks_evidence_found"] == 0
    assert analysis["sampling"]["brief_checks_downgraded"] == 0
    assert analysis["player_notes"][0]["brief_checks"][0]["brief_hash"] == "a" * 64
    assert analysis["player_notes"][0]["system_brief_hash"] == "b" * 64
    assert qwen_analysis.COACHS_BRIEF_HONEST_LIMIT in analysis["honest_limits"]
