"""Entry-time authority for club-confirmed tracked-player results."""

import re

from sqlalchemy import or_
from src.models.league import Team
from src.models.showcase import PlayerClubAffiliation
from src.models.tracked_player import TrackedPlayer


def _affiliation_season_start(value: str) -> int | None:
    """Normalize a year or consecutive-year range; reject other free text."""
    match = re.fullmatch(r"([0-9]{4})(?:[/-]([0-9]{2}|[0-9]{4}))?", value)
    if match is None:
        return None
    start = int(match[1])
    end = match[2]
    if end is not None and int(end) != ((start + 1) % 100 if len(end) == 2 else start + 1):
        return None
    return start


def club_authorized_player_ids(program, player_api_ids, *, season: int, session) -> set[int]:
    """Batch provider/accepted-affiliation authority in at most two queries.

    Team identities are provider IDs, not database primary keys. Every tracked
    academy row counts, including inactive rows. Affiliation creation stores
    sanitized free text and approval preserves it: the UI suggests ``2025/26``.
    Accept ``2025``, ``2025/26``, ``2025/2026`` and equivalent hyphen ranges;
    NULL applies to every season, while malformed/nonconsecutive ranges do not.

    Local identities retain the route's existing roster/result rules. This
    predicate is for entry time only: rebuilding historical rollups must not
    revoke an earlier result after a transfer. The caller owns the transaction.
    """
    player_api_ids = {player_id for player_id in player_api_ids if player_id is not None and player_id > 0}
    if not player_api_ids or program is None or program.team_api_id is None:
        return set()

    authorized = {
        player_id
        for (player_id,) in session.query(TrackedPlayer.player_api_id)
        .outerjoin(Team, TrackedPlayer.team_id == Team.id)
        .filter(
            TrackedPlayer.player_api_id.in_(player_api_ids),
            or_(
                TrackedPlayer.current_club_api_id == program.team_api_id,
                Team.team_id == program.team_api_id,
            ),
        )
        .all()
    }

    affiliations = (
        session.query(PlayerClubAffiliation.player_api_id, PlayerClubAffiliation.season)
        .filter(
            PlayerClubAffiliation.player_api_id.in_(player_api_ids),
            PlayerClubAffiliation.team_api_id == program.team_api_id,
            PlayerClubAffiliation.status.in_(("self_reported", "club_confirmed")),
        )
        .all()
    )
    authorized.update(
        player_id
        for player_id, affiliation_season in affiliations
        if affiliation_season is None or _affiliation_season_start(affiliation_season) == season
    )
    return authorized


def club_has_authority_over_player(program, player_api_id: int, *, season: int, session) -> bool:
    """Single-player version of the shared entry-time authority predicate."""
    return player_api_id in club_authorized_player_ids(program, {player_api_id}, season=season, session=session)
