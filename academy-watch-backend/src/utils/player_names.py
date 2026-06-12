"""Player name resolution utilities.

Placeholder names ("Player 12345") must never persist when a real name is
available locally. ``resolve_player_name`` returns the first real candidate,
then falls back to local sources in priority order:

    CohortMember -> AcademyPlayerSeasonStats -> Player -> PlayerJourney

Models are imported lazily inside the lookup so this module stays free of
circular imports.
"""

import re

PLACEHOLDER_NAME_RE = re.compile(r"^Player \d+$")


def is_placeholder_name(name) -> bool:
    """True when the name is empty/None or matches the 'Player NNNN' placeholder."""
    if name is None:
        return True
    text = str(name).strip()
    if not text:
        return True
    return bool(PLACEHOLDER_NAME_RE.match(text))


def _iter_local_profiles(player_api_id):
    """Yield (name, photo, nationality) tuples from local sources in priority order."""
    from src.models.cohort import CohortMember
    from src.models.journey import PlayerJourney
    from src.models.league import AcademyPlayerSeasonStats, Player

    members = CohortMember.query.filter(
        CohortMember.player_api_id == player_api_id,
        CohortMember.player_name.isnot(None),
    ).all()
    for member in members:
        yield member.player_name, member.player_photo, member.nationality

    stats_rows = AcademyPlayerSeasonStats.query.filter(
        AcademyPlayerSeasonStats.player_api_id == player_api_id,
        AcademyPlayerSeasonStats.player_name.isnot(None),
    ).all()
    for row in stats_rows:
        yield row.player_name, None, None

    player = Player.query.filter(Player.player_id == player_api_id).first()
    if player and player.name:
        yield player.name, player.photo_url, player.nationality

    journey = PlayerJourney.query.filter(PlayerJourney.player_api_id == player_api_id).first()
    if journey and journey.player_name:
        yield journey.player_name, journey.player_photo, journey.nationality


def resolve_player_name(player_api_id, *candidates) -> str:
    """Return the first non-placeholder name for a player.

    Explicit candidates are checked first (in order), then local sources
    (CohortMember, AcademyPlayerSeasonStats, Player, PlayerJourney).
    Returns ``f"Player {player_api_id}"`` only as a last resort.
    """
    for candidate in candidates:
        if not is_placeholder_name(candidate):
            return str(candidate).strip()
    for name, _photo, _nationality in _iter_local_profiles(player_api_id):
        if not is_placeholder_name(name):
            return str(name).strip()
    return f"Player {player_api_id}"


def resolve_player_profile(player_api_id) -> dict:
    """Resolve ``{"name", "photo", "nationality"}`` from local sources.

    Only rows carrying a real (non-placeholder) name contribute. Fields stay
    ``None`` when no source has them.
    """
    name = photo = nationality = None
    for src_name, src_photo, src_nationality in _iter_local_profiles(player_api_id):
        if is_placeholder_name(src_name):
            continue
        if name is None:
            name = str(src_name).strip()
        if photo is None and src_photo:
            photo = src_photo
        if nationality is None and src_nationality:
            nationality = src_nationality
        if name and photo and nationality:
            break
    return {"name": name, "photo": photo, "nationality": nationality}
