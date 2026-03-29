"""Map API-Football formation + grid position to human-readable role labels.

API-Football's /fixtures/lineups endpoint returns:
  - formation: e.g. "4-3-3", "4-2-3-1", "3-5-2"
  - grid: e.g. "1:1" (row:col) where row 1 = GK, higher rows = further forward,
    columns go left-to-right across the pitch.

Substitutes always have grid=null. Some lower-league teams may have
formation=null and/or all grids=null.
"""


def grid_to_role(formation: str | None, grid: str | None) -> str | None:
    """Derive a positional role label from a formation string and grid coordinate.

    Returns None if either input is None or unparseable.

    Examples:
        grid_to_role("4-3-3", "1:1")  -> "GK"
        grid_to_role("4-3-3", "2:1")  -> "LB"
        grid_to_role("4-3-3", "2:4")  -> "RB"
        grid_to_role("4-2-3-1", "5:1") -> "ST"
    """
    if not formation or not grid:
        return None

    try:
        row_sizes = [int(x) for x in formation.split("-")]
    except (ValueError, AttributeError):
        return None

    try:
        row, col = [int(x) for x in grid.split(":")]
    except (ValueError, AttributeError):
        return None

    # Prepend GK row (always 1 player)
    row_sizes = [1] + row_sizes
    total_rows = len(row_sizes)

    if row < 1 or row > total_rows:
        return None

    row_width = row_sizes[row - 1]  # 0-indexed into row_sizes
    if col < 1 or col > row_width:
        return None

    # Row 1 is always GK
    if row == 1:
        return "GK"

    # Determine which layer this row belongs to:
    # row_sizes[0] = GK, row_sizes[1] = DEF, ..., row_sizes[-1] = FWD
    # The formation groups (excluding GK) are indexed 1..N
    group_idx = row - 1  # 1-based index into the formation groups (excl GK)
    num_groups = total_rows - 1  # number of formation groups (excl GK)

    is_def = (group_idx == 1)
    is_fwd = (group_idx == num_groups)
    # Everything between first and last group is midfield
    is_mid = not is_def and not is_fwd

    # For midfield layers, determine if this is a holding/defensive mid layer
    # or an attacking mid layer based on position relative to other mid layers
    mid_layer_index = 0  # 0 = deepest mid, higher = more attacking
    total_mid_layers = 0
    if is_mid:
        total_mid_layers = num_groups - 2  # exclude DEF and FWD groups
        mid_layer_index = group_idx - 2  # 0-based within mid layers

    return _map_role(
        row_width, col, is_def, is_mid, is_fwd,
        mid_layer_index, total_mid_layers,
    )


def _map_role(
    width: int, col: int,
    is_def: bool, is_mid: bool, is_fwd: bool,
    mid_layer_index: int, total_mid_layers: int,
) -> str:
    """Map a position within a row to a role label."""

    # --- Defence ---
    if is_def:
        return _DEF_ROLES.get(width, {}).get(col, "DEF")

    # --- Forward ---
    if is_fwd:
        return _FWD_ROLES.get(width, {}).get(col, "FWD")

    # --- Midfield ---
    # Holding / defensive mid (first mid layer when there are multiple)
    if total_mid_layers > 1 and mid_layer_index == 0:
        return _DM_ROLES.get(width, {}).get(col, "DM")

    # Attacking mid (last mid layer when there are multiple)
    if total_mid_layers > 1 and mid_layer_index == total_mid_layers - 1:
        return _AM_ROLES.get(width, {}).get(col, "AM")

    # Single mid layer or middle layer in 3+ mid layers
    return _CM_ROLES.get(width, {}).get(col, "CM")


# --- Lookup tables: {row_width: {col: role}} ---

_DEF_ROLES = {
    3: {1: "LCB", 2: "CB", 3: "RCB"},
    4: {1: "LB", 2: "LCB", 3: "RCB", 4: "RB"},
    5: {1: "LWB", 2: "LCB", 3: "CB", 4: "RCB", 5: "RWB"},
}

_CM_ROLES = {
    1: {1: "CM"},
    2: {1: "LCM", 2: "RCM"},
    3: {1: "LCM", 2: "CM", 3: "RCM"},
    4: {1: "LM", 2: "LCM", 3: "RCM", 4: "RM"},
    5: {1: "LWB", 2: "LCM", 3: "CM", 4: "RCM", 5: "RWB"},
}

_DM_ROLES = {
    1: {1: "CDM"},
    2: {1: "LCDM", 2: "RCDM"},
    3: {1: "LDM", 2: "CDM", 3: "RDM"},
}

_AM_ROLES = {
    1: {1: "CAM"},
    2: {1: "LAM", 2: "RAM"},
    3: {1: "LW", 2: "CAM", 3: "RW"},
    4: {1: "LW", 2: "LAM", 3: "RAM", 4: "RW"},
}

_FWD_ROLES = {
    1: {1: "ST"},
    2: {1: "LST", 2: "RST"},
    3: {1: "LW", 2: "ST", 3: "RW"},
}

# ---------------------------------------------------------------------------
# Position groups for radar-chart percentile comparisons.
# Maps each formation_position label to one of 8 comparison groups.
# ---------------------------------------------------------------------------

POSITION_GROUPS = {
    # Goalkeeper
    "GK": "GK",
    # Centre-backs
    "CB": "CB", "LCB": "CB", "RCB": "CB",
    # Full-backs / wing-backs
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    # Defensive midfield
    "CDM": "DM", "LCDM": "DM", "RCDM": "DM", "LDM": "DM", "RDM": "DM", "DM": "DM",
    # Central midfield
    "CM": "CM", "LCM": "CM", "RCM": "CM",
    # Attacking midfield
    "CAM": "AM", "LAM": "AM", "RAM": "AM", "AM": "AM",
    # Wingers
    "LW": "W", "RW": "W", "LM": "W", "RM": "W",
    # Strikers
    "ST": "ST", "LST": "ST", "RST": "ST", "CF": "ST", "FWD": "ST",
}

# Fallback: map broad API-Football position codes (G/D/M/F) to a group
POSITION_BROAD_TO_GROUP = {
    "G": "GK",
    "D": "CB",
    "M": "CM",
    "F": "ST",
}

POSITION_GROUP_LABELS = {
    "GK": "Goalkeeper",
    "CB": "Centre-Back",
    "FB": "Full-Back",
    "DM": "Defensive Mid",
    "CM": "Central Mid",
    "AM": "Attacking Mid",
    "W": "Winger",
    "ST": "Striker",
}
