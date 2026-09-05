"""Entry-time authority for club-confirmed tracked-player results."""

from sqlalchemy import or_
from src.models.league import Team
from src.models.showcase import PlayerClubAffiliation
from src.models.tracked_player import TrackedPlayer


def club_has_authority_over_player(program, player_api_id: int, *, season: int, session) -> bool:
    """Check provider identity or an accepted player affiliation for this season.

    Team identities are provider IDs, not database primary keys. Every tracked
    academy row counts, including inactive rows. Affiliation seasons use the
    canonical season-start year string; NULL applies to every season.

    Local identities retain the route's existing roster/result rules. This
    predicate is for entry time only: rebuilding historical rollups must not
    revoke an earlier result after a transfer. The caller owns the transaction.
    """
    if player_api_id <= 0 or program is None or program.team_api_id is None:
        return False

    tracked = (
        session.query(TrackedPlayer.id)
        .outerjoin(Team, TrackedPlayer.team_id == Team.id)
        .filter(
            TrackedPlayer.player_api_id == player_api_id,
            or_(
                TrackedPlayer.current_club_api_id == program.team_api_id,
                Team.team_id == program.team_api_id,
            ),
        )
    )
    if tracked.first() is not None:
        return True

    return (
        session.query(PlayerClubAffiliation.id)
        .filter(
            PlayerClubAffiliation.player_api_id == player_api_id,
            PlayerClubAffiliation.team_api_id == program.team_api_id,
            PlayerClubAffiliation.status.in_(("self_reported", "club_confirmed")),
            or_(PlayerClubAffiliation.season.is_(None), PlayerClubAffiliation.season == str(season)),
        )
        .first()
        is not None
    )
