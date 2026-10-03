"""Canonical reported season totals and a batched compatibility read projection.

Provider figures are indivisible. Reported figures come ONLY from the same
merged lines as the player page. Raw club/user cells remain evidence, not an
additive headline. The read projection also covers cells written before PC2.
"""

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, cast, column, exists, literal, or_, select, union_all, values
from src.models.funding import ClubProgram
from src.models.league import db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonTotal
from src.services.match_lines import merge_match_lines, season_totals

SOURCE_MATCHES = "matches"
PROVIDER_SOURCES = ("fixtures", "journey", "apss", "shadow", "cache")
STAT_KEYS = ("appearances", "minutes", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
ENTRY_KEYS = (
    "id",
    "player_api_id",
    "season",
    "source",
    "status",
    "match_date",
    "opponent",
    "competition",
    "created_at",
    "minutes",
    "goals",
    "assists",
    "yellows",
    "reds",
    "saves",
    "goals_conceded",
    "home_away",
    "result_for",
    "result_against",
    "club_program_id",
)


def reported_totals(*, session=None, player_ids=None, season=None, identity=None):
    """One narrow source query for the whole batch; no reporter/profile data."""
    session = session or db.session
    query = session.query(*(getattr(PlayerMatchEntry, k) for k in ENTRY_KEYS), ClubProgram.name.label("club_name"))
    query = query.outerjoin(ClubProgram, ClubProgram.id == PlayerMatchEntry.club_program_id).filter(
        or_(
            and_(PlayerMatchEntry.source == "club", PlayerMatchEntry.status == "club_confirmed"),
            and_(PlayerMatchEntry.source == "self", PlayerMatchEntry.status == "self_reported"),
        )
    )
    if player_ids is not None:
        query = query.filter(PlayerMatchEntry.player_api_id.in_(player_ids))
    if season is not None:
        query = query.filter(PlayerMatchEntry.season == season)
    if identity is not None:
        query = query.join(identity, identity.c.player_api_id == PlayerMatchEntry.player_api_id)
    grouped = defaultdict(list)
    for row in query.all():
        entry = dict(row._mapping)
        entry["_scope"] = (entry["club_program_id"] or 0, entry["club_name"])
        grouped[(entry["player_api_id"], entry["season"])].append(entry)
    result = {}
    for (player_id, entry_season), entries in grouped.items():
        lines = merge_match_lines(entries)
        total = season_totals(lines)
        clubs = defaultdict(list)
        for line in lines:
            clubs[line["_scope"]].append(line)
        result[(player_id, entry_season)] = {
            "player_api_id": player_id,
            "season": entry_season,
            "level_group": "senior",
            **{k: total[k] for k in STAT_KEYS},
            "avg_rating": None,
            "primary_source": (
                SOURCE_MATCHES
                if total["club_confirmed"] and total["self_reported_only"]
                else "club"
                if total["club_confirmed"]
                else "user"
            ),
            "fixtures_minutes": 0,
            "journey_minutes": 0,
            "reconcile_flag": None,
            "source_breakdown": {SOURCE_MATCHES: total},
            "clubs": [
                {
                    "id": -club_id,
                    "name": name,
                    **{k: season_totals(group)[k] for k in ("appearances", "minutes", "goals", "assists")},
                    "competition_tiers": list(
                        dict.fromkeys(line["competition"] for line in group if line.get("competition"))
                    ),
                }
                for (club_id, name), group in clubs.items()
            ],
            "computed_at": datetime.now(UTC),
        }
    return result


def effective_total(player_id, season, stored=None, *, session=None):
    """Correct an old reported row without writes; preserve provider headlines."""
    if stored is not None and stored.primary_source in PROVIDER_SOURCES:
        return stored
    session = session or db.session
    total = reported_totals(session=session, player_ids=[player_id], season=season).get((player_id, season))
    if total and player_id > 0:
        stored_provider = (
            session.query(PlayerSeasonTotal)
            .filter(
                PlayerSeasonTotal.player_api_id == player_id,
                PlayerSeasonTotal.season == season,
                PlayerSeasonTotal.level_group == "senior",
                PlayerSeasonTotal.primary_source.in_(PROVIDER_SOURCES),
            )
            .one_or_none()
        )
        if stored_provider:
            return stored_provider
        from src.services.season_rollup_service import provider_totals_batch

        provider = provider_totals_batch([player_id], season, session=session).get(player_id)
        if provider:
            return PlayerSeasonTotal(**provider)
    if not total and player_id > 0 and stored is None:
        # A last report can be removed while the real cache figures remain.
        # Read a cache headline written by the same canonical refresh path.
        stored = (
            session.query(PlayerSeasonTotal)
            .filter_by(
                player_api_id=player_id,
                season=season,
                level_group="senior",
                primary_source="cache",
            )
            .one_or_none()
        )
    return (
        PlayerSeasonTotal(**total)
        if total
        else stored
        if stored and stored.primary_source in PROVIDER_SOURCES
        else None
    )


def scout_totals_projection(identity, season):
    """Expose corrected reported figures to SQL BEFORE filtering/ranking/LIMIT.

    This temporary VALUES relation is request-owned, restricted to discovery's
    existing identity universe. Provider rows retain their stored total. There
    is one source read regardless of page size, never a per-row refresh/write.
    """
    table = PlayerSeasonTotal.__table__
    names = [
        "id",
        "player_api_id",
        "season",
        "level_group",
        *STAT_KEYS,
        "avg_rating",
        "primary_source",
        "fixtures_minutes",
        "journey_minutes",
        "reconcile_flag",
        "computed_at",
    ]
    totals = reported_totals(identity=identity, season=season)
    if not totals:
        return (
            select(*table.c, literal(False).label("pc2_override"))
            .where(
                or_(
                    table.c.season != season,
                    table.c.level_group != "senior",
                    table.c.primary_source.not_in(("club", "user", "matches")),
                )
            )
            .subquery("pc2_stored_totals")
        )
    positive_ids = {pid for pid, _season in totals if pid > 0}
    if positive_ids:
        stored_providers = set(
            db.session.execute(
                select(table.c.player_api_id).where(
                    table.c.player_api_id.in_(positive_ids),
                    table.c.season == season,
                    table.c.level_group == "senior",
                    table.c.primary_source.in_(PROVIDER_SOURCES),
                )
            ).scalars()
        )
        if missing := positive_ids - stored_providers:
            from src.services.season_rollup_service import provider_totals_batch

            for pid, provider in provider_totals_batch(missing, season).items():
                totals[(pid, season)] = provider
    # Keep the provider protection in SQL, including for identities whose
    # current report rows were loaded above. Neither total is ever added.
    projected = (
        values(*(column(k, table.c[k].type) for k in names))
        .data(
            [
                tuple(
                    -index if k == "id" else cast(literal(None), table.c[k].type) if t[k] is None else t[k]
                    for k in names
                )
                for index, t in enumerate(totals.values(), start=1)
            ]
        )
        .cte("pc2_reported_totals")
    )
    has_provider = exists(
        select(1).where(
            table.c.player_api_id == projected.c.player_api_id,
            table.c.season == projected.c.season,
            table.c.level_group == "senior",
            table.c.primary_source.in_(PROVIDER_SOURCES),
        )
    )
    existing = select(
        *(table.c[k] for k in names),
        and_(
            table.c.player_api_id.in_([key[0] for key in totals]),
            table.c.season == season,
            table.c.level_group == "senior",
        ).label("pc2_override"),
    ).where(
        or_(
            table.c.primary_source.not_in(("club", "user", "matches")),
            table.c.season != season,
            table.c.level_group != "senior",
            table.c.primary_source.in_(PROVIDER_SOURCES),
        )
    )
    return union_all(
        existing, select(*(projected.c[k] for k in names), literal(True).label("pc2_override")).where(~has_provider)
    ).subquery("pc2_effective_totals")


def saved_shadow_totals(player_ids, requested_season=None):
    """Batched list-only stats for eligible worldwide shadows outside the desk.

    These identities retain the existing saved-list universe; this never adds
    them to discovery. Unpicked shadows retain the player page's latest season.
    """
    from src.models.follow import PlayerShadowStats

    ids = set(player_ids)
    if not ids:
        return {}
    stored_query = PlayerSeasonTotal.query.filter(
        PlayerSeasonTotal.player_api_id.in_(ids), PlayerSeasonTotal.level_group == "senior"
    )
    shadow_query = PlayerShadowStats.query.filter(PlayerShadowStats.player_api_id.in_(ids))
    if requested_season is not None:
        from src.utils.academy_window import resolve_stats_season

        season = resolve_stats_season(db.session, requested=requested_season, allow_history=True)
        stored_query = stored_query.filter(PlayerSeasonTotal.season == season)
        shadow_query = shadow_query.filter(PlayerShadowStats.season == season)
    else:
        season = None
    stored = {(row.player_api_id, row.season): row for row in stored_query.all()}
    grouped = defaultdict(list)
    for row in shadow_query.all():
        grouped[(row.player_api_id, row.season)].append(row)
    reported = reported_totals(player_ids=ids, season=season)
    result = {}
    for player_id in ids:
        seasons = {s for pid, s in set(stored) | set(grouped) | set(reported) if pid == player_id}
        target = season if season is not None else max(seasons, default=None)
        scope = (player_id, target)
        total = stored.get(scope)
        source = total.primary_source if total else None
        figures = {k: getattr(total, k) for k in STAT_KEYS} if total else None
        if source not in PROVIDER_SOURCES:
            if rows := grouped.get(scope):
                source = "shadow"
                figures = {
                    k: sum(getattr(row, k) or 0 for row in rows)
                    if k in {"appearances", "minutes", "goals", "assists"}
                    else None
                    for k in STAT_KEYS
                }
            elif scope in reported:
                source = reported[scope]["primary_source"]
                figures = {k: reported[scope][k] for k in STAT_KEYS}
            else:
                source, figures = None, None
        result[player_id] = {
            **({k if k != "minutes" else "minutes_played": v for k, v in figures.items()} if figures else {}),
            "provenance": {
                "primary_source": source,
                "source_category": "api"
                if source in PROVIDER_SOURCES
                else "self"
                if source == "user"
                else "club"
                if source
                else "api",
                "source_label": "Provider totals"
                if source in PROVIDER_SOURCES
                else "Merged match entries"
                if source
                else "No recorded totals",
            },
        }
    return result
