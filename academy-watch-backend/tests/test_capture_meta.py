"""Capture preflight validation and non-destructive merge contracts."""

import pytest
from src.services.capture_meta import merge_preflight


def test_merge_preflight_preserves_existing_metadata_and_ignores_unnamed_input():
    existing = {
        "qwen_analysis": {"match_summary": "Keep this"},
        "local": {"video": "/fixtures/match.mp4"},
    }

    assert merge_preflight(
        existing,
        {
            "camera_view": "wide_fixed",
            "camera_motion": "fixed",
            "pitch_lines_visible": "all",
            "attack_direction_first_half": "right",
            "qwen_analysis": {"match_summary": "Do not copy"},
        },
    ) == {
        **existing,
        "camera_view": "wide_fixed",
        "camera_motion": "fixed",
        "pitch_lines_visible": "all",
        "attack_direction_first_half": "right",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("camera_view", "touchline"),
        ("camera_motion", "tripod"),
        ("pitch_lines_visible", "most"),
        ("attack_direction_first_half", "upfield"),
        ("camera_view", []),
        ("camera_motion", {}),
        ("pitch_lines_visible", True),
    ],
)
def test_merge_preflight_rejects_values_outside_the_contract(field, value):
    with pytest.raises(ValueError, match=field):
        merge_preflight({"local": {"video": "kept"}}, {field: value})
