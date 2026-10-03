"""Read-only source separation and freshness for stored football facts.

Never persist frozen precedence: switching the flag off restores normal totals
immediately, without a rollup rebuild. Rollup computation time is not freshness.
"""

from datetime import UTC, datetime

from sqlalchemy import func
from src.models.follow import PlayerShadow
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import db
from src.models.weekly import Fixture, FixturePlayerStats
from src.utils.data_mode import api_football_frozen
from src.utils.sanitize import display_plain_text


def public_match_metadata(player_id, season=None):
    journey = PlayerJourney.query.filter_by(player_api_id=player_id).first()
    timestamps = []
    if journey:
        entries = db.session.query(func.max(PlayerJourneyEntry.stats_synced_at)).filter_by(journey_id=journey.id)
        if season is not None:
            entries = entries.filter(PlayerJourneyEntry.season == season)
        timestamps.extend([entries.scalar(), journey.last_synced_at])
    fixtures = (
        db.session.query(func.max(Fixture.date_utc))
        .join(FixturePlayerStats)
        .filter(FixturePlayerStats.player_api_id == player_id)
    )
    if season is not None:
        fixtures = fixtures.filter(Fixture.season == season)
    timestamps.append(fixtures.scalar())
    shadow = PlayerShadow.query.filter_by(player_api_id=player_id).first()
    if shadow:
        timestamps.append(shadow.last_stats_sync_at)
    known = [t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC) for t in timestamps if t]
    return {"source": "public_match_data", "as_of": max(known).isoformat() if known else None}


_UNREAD_TOTAL = object()


def separated_season_stats(player_id, season, legacy, *, merged_total=_UNREAD_TOTAL):
    """Use existing DB feeders/deduplication; never add public and club totals."""
    from src.services.reported_match_totals import effective_source_cells, effective_total

    unread = merged_total is _UNREAD_TOTAL
    if unread:
        merged_total = None
    if (
        unread
        and legacy.get("source") in {"none", "season-rollup", "club_verified", "self_reported"}
        and (legacy.get("provenance") or {}).get("primary_source")
        not in {"fixtures", "journey", "apss", "shadow", "cache"}
    ):
        merged_total = effective_total(player_id, season)
    merged_provenance = legacy.get("provenance") or {}
    if not api_football_frozen():
        if merged_total and legacy.get("source") != "season-rollup":
            legacy.update(
                {
                    key: getattr(merged_total, key)
                    for key in (
                        "appearances",
                        "minutes",
                        "goals",
                        "assists",
                        "yellows",
                        "reds",
                        "saves",
                        "goals_conceded",
                    )
                }
            )
            legacy["provenance"] = {**merged_provenance, "primary_source": merged_total.primary_source}
        return legacy

    from src.services.season_rollup_service import _resolve_totals

    now = datetime.now(UTC)
    cells = [
        cell for cell in effective_source_cells(player_id, season, current_only=True) if cell["level_group"] == "senior"
    ]
    stat_keys = (
        "appearances",
        "minutes",
        "goals",
        "assists",
        "yellows",
        "reds",
        "avg_rating",
        "saves",
        "goals_conceded",
    )

    def block(source, label, source_cells):
        totals = _resolve_totals(source_cells, now)
        total = totals[0] if totals else None
        return {
            "source": source,
            "label": label,
            "available": total is not None,
            "totals": {key: total.get(key) for key in stat_keys} if total else None,
            "primary_source": total["primary_source"] if total else None,
            "clubs": [
                {
                    **club,
                    "competition_tiers": list(
                        dict.fromkeys(display_plain_text(label) for label in club.get("competition_tiers", []))
                    ),
                }
                for club in total["clubs"]
            ]
            if total
            else [],
        }

    public = block("public_match_data", "Public match data", [c for c in cells if c["source"] not in {"club", "user"}])
    public.update(public_match_metadata(player_id, season))
    # Limited-coverage cache totals have no rollup feeder; retain the endpoint's
    # season-scoped stored result when there are no detailed public sources.
    if not public["available"] and (
        legacy.get("source") in {"limited-coverage", "shadow", "local-db", "api-football"}
        or (legacy.get("provenance") or {}).get("primary_source") == "cache"
    ):
        public.update(
            available=True,
            totals={key: legacy.get(key) for key in stat_keys},
            primary_source=(legacy.get("provenance") or {}).get("primary_source") or legacy["source"],
        )
    club = block("club_verified", "Club-verified", [c for c in cells if c["source"] == "club"])
    reported = block("self_reported", "Self-reported", [c for c in cells if c["source"] == "user"])
    legacy.update(
        public_match_data=public,
        club_verified=club,
        self_reported=reported,
        as_of=public["as_of"],
        source_label="public_match_data",
        api_football_frozen=api_football_frozen(),
    )
    if api_football_frozen():
        selected = public if public["available"] else club if club["available"] else reported
        if selected["available"]:
            legacy.update(selected["totals"])
            legacy["source"] = selected["source"]
            legacy["provenance"] = {**merged_provenance, "primary_source": selected["primary_source"]}
            legacy["clubs"] = [
                {
                    "team_api_id": c["id"],
                    "team_name": c["name"],
                    "team_logo": None,
                    "window_type": None,
                    "is_current": None,
                    **{key: c.get(key) for key in ("appearances", "minutes", "goals", "assists")},
                }
                for c in selected["clubs"]
            ]
            legacy["loan_team"] = legacy["clubs"][0]["team_name"] if legacy["clubs"] else None
            legacy["has_multiple_clubs"] = len(legacy["clubs"]) > 1
            legacy["loan_clubs_only"] = False
    if merged_total and not public["available"]:
        legacy.update({key: getattr(merged_total, key) for key in stat_keys})
        legacy["source"] = "season-rollup"
        legacy["provenance"] = {**merged_provenance, "primary_source": merged_total.primary_source}
    return legacy
