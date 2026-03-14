from src.models.league import Team


def _latest_for_api_team_id(api_team_id: int) -> int | None:
    """
    Return the DB primary key for the newest season row that matches an API team_id.
    """
    try:
        latest = (
            Team.query.filter_by(team_id=api_team_id)
            .order_by(Team.season.desc())
            .first()
        )
        if latest:
            print(
                f"[TEAM RESOLVER] Latest by API ID {api_team_id}: DB ID {latest.id} (Season {latest.season})"
            )
            return latest.id
        print(f"[TEAM RESOLVER] No team found for API ID: {api_team_id}")
        return None
    except Exception as e:
        print(f"[TEAM RESOLVER] Error resolving by API ID {api_team_id}: {e}")
        return None


def resolve_latest_team_id(identifier: int, *, assume_api_id: bool = False) -> int | None:
    """
    Resolve a team identifier to the latest season's database row.

    - When assume_api_id=True, the identifier is treated as an API team_id.
    - Otherwise we first try DB primary key; if that fails, fall back to treating
      it as an API team_id.
    """
    try:
        if assume_api_id:
            return _latest_for_api_team_id(int(identifier))

        # Try as DB primary key first
        team = Team.query.get(identifier)
        if team:
            print(
                f"[TEAM RESOLVER] Resolving from DB ID: {identifier} (API ID: {team.team_id}, Season: {team.season})"
            )
            latest = (
                Team.query.filter_by(team_id=team.team_id)
                .order_by(Team.season.desc())
                .first()
            )
            if latest:
                print(
                    f"[TEAM RESOLVER] Found latest team: DB ID {latest.id} (Season {latest.season})"
                )
                return latest.id
            return identifier

        # If not a DB PK, assume it's an API team_id
        return _latest_for_api_team_id(int(identifier))
    except Exception as e:
        print(f"[TEAM RESOLVER] Error resolving team: {e}")
        return None
