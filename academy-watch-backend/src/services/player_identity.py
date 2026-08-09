"""Shared local/API identity collision checks."""

from sqlalchemy import func, or_
from src.models.follow import PlayerShadow
from src.models.showcase import LocalPlayer


def _escape_like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def retained_shadow_identity_exists(
    *,
    display_name: str | None,
    birth_year: int | None,
    api_player_id: int | None = None,
) -> bool:
    """Match every retained shadow, including inactive/suppressed rows.

    An API id match is authoritative.  Otherwise the normalized name and birth
    year must match; missing year data is handled conservatively, mirroring the
    tracked-player alias defense.
    """

    normalized = LocalPlayer.normalize_name(display_name) if isinstance(display_name, str) else ""
    filters = []
    if isinstance(api_player_id, int) and not isinstance(api_player_id, bool):
        filters.append(PlayerShadow.player_api_id == api_player_id)
    if normalized:
        first_token = normalized.split(" ", 1)[0]
        filters.append(
            func.lower(PlayerShadow.player_name).like(
                f"%{_escape_like_literal(first_token)}%",
                escape="\\",
            )
        )
    if not filters:
        return False

    for candidate in PlayerShadow.query.filter(or_(*filters)).all():
        if api_player_id is not None and candidate.player_api_id == api_player_id:
            return True
        if not normalized or LocalPlayer.normalize_name(candidate.player_name) != normalized:
            continue
        if birth_year is None or candidate.birth_date is None or candidate.birth_date.year == birth_year:
            return True
    return False
