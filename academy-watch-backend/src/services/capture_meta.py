"""Validated, non-destructive updates for match capture metadata."""

PREFLIGHT_VALUES = {
    "camera_view": {"panoramic", "wide_fixed", "broadcast"},
    "camera_motion": {"fixed", "panning", "handheld"},
    "pitch_lines_visible": {"all", "partial", "none"},
    "attack_direction_first_half": {"left", "right"},
}


def merge_preflight(capture_meta, data: dict) -> dict | None:
    """Merge only validated preflight keys into the existing metadata object."""
    if capture_meta is not None and not isinstance(capture_meta, dict):
        raise ValueError("capture_meta must be an object or null")
    if not isinstance(data, dict):
        raise ValueError("capture_meta must be an object or null")

    merged = dict(capture_meta) if capture_meta else {}
    changed = False
    for key, allowed in PREFLIGHT_VALUES.items():
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str) or value not in allowed:
            if key == "attack_direction_first_half":
                raise ValueError("attack_direction_first_half must be left or right")
            choices = ", ".join(sorted(allowed))
            raise ValueError(f"{key} must be one of: {choices}")
        merged[key] = value
        changed = True
    return merged if merged or changed else None
