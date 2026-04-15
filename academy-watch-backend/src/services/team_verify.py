"""Idempotent team consistency verification.

This module is the canonical "make this team's TrackedPlayer data correct"
operation. It re-runs every consistency check we know about, optionally
auto-corrects what's safely fixable, and returns a structured audit report
for anything it can't.

It exists because we've discovered several bug classes (radar showing
"Premier League Avg" for sub-PL loanees, first-team players resolving to
"League comparison unavailable", local Team.league_id drifting away from
API-Football reality) where the underlying TrackedPlayer state was stale or
inconsistent. Each individual bug got a defensive radar-side patch, but the
data hygiene fix lives in the classifier (`utils/academy_classifier.py`)
and `transfer_heal_service.refresh_and_heal()`. This module ties them
together with an audit pass so the operator can hit ONE button after
shipping a fix and know every tracked team is in a clean state.

Usage:
    from src.services.team_verify import verify_and_repair_team

    report = verify_and_repair_team(team_db_id=18, force_resync_journeys=False)
    # report['audit']['suspect_first_team_null_current_club'] should be 0
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.models.league import Team, db
from src.models.tracked_player import TrackedPlayer

logger = logging.getLogger(__name__)


def _current_season() -> int:
    """European season cycle: Aug-Jul. Mirrors get_radar_chart_data."""
    now = datetime.now(UTC)
    return now.year if now.month >= 7 else now.year - 1


def audit_team_consistency(team_db_id: int) -> dict[str, Any]:
    """Read-only audit of every active TrackedPlayer for a parent team.

    Categorises rows that fail any of the consistency checks we've
    discovered through the Forest/ManU investigations:

    - `suspect_first_team_null_current_club`: status='first_team' but
      current_club_api_id IS NULL. Should be zero post-PR #106 (the
      classifier writes the parent club for first-team status). Non-zero
      means the classifier hasn't been re-run for this team yet.
    - `suspect_loanee_null_current_club`: status in ('on_loan','sold','released')
      but current_club_api_id IS NULL. Means the classifier couldn't
      determine the destination — usually a journey-sync gap or a player
      whose transfer never made it into API-Football.
    - `suspect_db_id_unresolved`: current_club_api_id IS NOT NULL but
      current_club_db_id IS NULL. Means the destination club isn't in our
      local `teams` table — common for non-Big-5 clubs we never seeded.
    - `parent_league_drift`: the parent Team's `league_id` (local) doesn't
      match what API-Football says for that team in the current season.
      Surfaces "team got promoted/relegated and we never re-keyed it"
      and "team was first ingested via a cup competition" cases.

    Returns a dict with counts + per-row details, structured for both human
    and programmatic consumption. Read-only — no writes.
    """
    from src.services.radar_stats_service import _team_league_from_api

    team = db.session.get(Team, team_db_id)
    if not team:
        return {
            "team_db_id": team_db_id,
            "error": f"team_db_id={team_db_id} not found",
        }

    season = _current_season()

    # Parent league drift check
    parent_local_league_id: int | None = None
    parent_local_league_name: str | None = None
    if team.league_id:
        from src.models.league import League

        local_league = db.session.get(League, team.league_id)
        if local_league:
            parent_local_league_id = local_league.league_id
            parent_local_league_name = local_league.name

    parent_api_result = _team_league_from_api(team.team_id, season) if team.team_id else None
    parent_drift = (
        parent_api_result is not None
        and parent_local_league_id is not None
        and parent_api_result[0] != parent_local_league_id
    )

    rows = (
        TrackedPlayer.query.filter_by(team_id=team_db_id, is_active=True)
        .order_by(TrackedPlayer.status, TrackedPlayer.player_name)
        .all()
    )

    suspect_first_team_null_current_club: list[dict] = []
    suspect_loanee_null_current_club: list[dict] = []
    suspect_db_id_unresolved: list[dict] = []

    for tp in rows:
        row_summary = {
            "id": tp.id,
            "player_api_id": tp.player_api_id,
            "player_name": tp.player_name,
            "status": tp.status,
            "current_club_api_id": tp.current_club_api_id,
            "current_club_db_id": tp.current_club_db_id,
            "current_club_name": tp.current_club_name,
            "pinned_parent": tp.pinned_parent,
        }

        if tp.status == "first_team" and tp.current_club_api_id is None:
            suspect_first_team_null_current_club.append(row_summary)

        if tp.status in ("on_loan", "sold", "released") and tp.current_club_api_id is None:
            suspect_loanee_null_current_club.append(row_summary)

        if tp.current_club_api_id is not None and tp.current_club_db_id is None:
            suspect_db_id_unresolved.append(row_summary)

    total_active = len(rows)
    suspect_total = (
        len(suspect_first_team_null_current_club)
        + len(suspect_loanee_null_current_club)
        + len(suspect_db_id_unresolved)
    )
    ok_total = total_active - suspect_total

    return {
        "team_db_id": team.id,
        "team_api_id": team.team_id,
        "team_name": team.name,
        "season": season,
        "total_active": total_active,
        "ok": ok_total,
        "suspect_total": suspect_total,
        "parent_league": {
            "local_id": parent_local_league_id,
            "local_name": parent_local_league_name,
            "api_id": parent_api_result[0] if parent_api_result else None,
            "api_name": parent_api_result[1] if parent_api_result else None,
            "drift": parent_drift,
        },
        "suspect_first_team_null_current_club": {
            "count": len(suspect_first_team_null_current_club),
            "rows": suspect_first_team_null_current_club,
        },
        "suspect_loanee_null_current_club": {
            "count": len(suspect_loanee_null_current_club),
            "rows": suspect_loanee_null_current_club,
        },
        "suspect_db_id_unresolved": {
            "count": len(suspect_db_id_unresolved),
            "rows": suspect_db_id_unresolved,
        },
    }


def verify_and_repair_team(
    team_db_id: int,
    *,
    force_resync_journeys: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the full verify + repair pipeline for a single team.

    Steps (in order, all idempotent):
      1. Audit — pre-repair snapshot of consistency state
      2. Repair — call `transfer_heal_service.refresh_and_heal()` which
         re-derives status/current_club_* via the classifier (Part B in
         the radar plan ensures this writes both api_id and db_id and
         handles first-team players correctly)
      3. Audit — post-repair snapshot

    The pre/post audits make it easy to see what the repair pass actually
    fixed. Read-only `dry_run=True` skips step 2 and only returns the audit.

    Returns a structured report with both audit snapshots and the repair
    summary (rows updated, etc.).
    """
    team = db.session.get(Team, team_db_id)
    if not team:
        return {
            "team_db_id": team_db_id,
            "error": f"team_db_id={team_db_id} not found",
        }

    pre_audit = audit_team_consistency(team_db_id)

    repair_result: dict[str, Any] | None = None
    if not dry_run:
        from src.services.transfer_heal_service import refresh_and_heal

        try:
            repair_result = refresh_and_heal(
                team_id=team_db_id,
                resync_journeys=force_resync_journeys,
                cascade_fixtures=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("team_verify: refresh_and_heal failed for team %s", team_db_id)
            repair_result = {"error": str(exc)}

    post_audit = audit_team_consistency(team_db_id) if not dry_run else None

    return {
        "team_db_id": team.id,
        "team_api_id": team.team_id,
        "team_name": team.name,
        "dry_run": dry_run,
        "force_resync_journeys": force_resync_journeys,
        "pre_audit": pre_audit,
        "repair": repair_result,
        "post_audit": post_audit,
    }
