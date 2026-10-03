"""Canonical reported season totals and a batched compatibility read projection.

Provider figures are indivisible. Reported figures come ONLY from the same
merged lines as the player page. Raw club/user cells remain evidence, not an
additive headline. The read projection also covers cells written before PC2.
"""

import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, cast, column, exists, func, literal, or_, select, type_coerce, union_all
from sqlalchemy.dialects.postgresql import JSONB
from src.models.funding import ClubProgram
from src.models.league import db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonTotal
from src.services.match_lines import match_line_input, merge_match_lines, season_totals

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


def public_report_ids(ids, eligibility_cache=None):
    """Fresh conservative public policy; memoisation belongs to this request only."""
    from src.services.public_adult import cached_public_adult_ids, request_public_adult_cache

    cache = eligibility_cache if eligibility_cache is not None else request_public_adult_cache()
    return cached_public_adult_ids(ids, cache)


def trusted_entries():
    return or_(
        and_(PlayerMatchEntry.source == "club", PlayerMatchEntry.status == "club_confirmed"),
        and_(PlayerMatchEntry.source == "self", PlayerMatchEntry.status == "self_reported"),
    )


def reported_totals(
    *, session=None, player_ids=None, season=None, identity=None, public=True, eligible_ids=None, skip_stored=False
):
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
    if skip_stored:
        table = PlayerSeasonTotal.__table__
        query = query.filter(
            ~exists(
                select(1).where(
                    table.c.player_api_id == PlayerMatchEntry.player_api_id,
                    table.c.season == PlayerMatchEntry.season,
                    table.c.level_group == "senior",
                    or_(
                        table.c.primary_source.in_(PROVIDER_SOURCES),
                        table.c.source_breakdown["matches"]["revision"].as_integer() == 2,
                    ),
                )
            )
        )
    rows = query.all()
    if public:
        eligible_ids = public_report_ids({row.player_api_id for row in rows}) if eligible_ids is None else eligible_ids
        rows = [row for row in rows if row.player_api_id in eligible_ids]
    grouped = defaultdict(list)
    for row in rows:
        entry = match_line_input(dict(row._mapping))
        entry["_scope"] = (entry["club_program_id"] or 0, entry["club_name"])
        # Pair with display labels, but persist storage labels for the JSON
        # boundary to decode once. Literal user entities must survive.
        entry["_stored_competition"] = row.competition
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
            "source_breakdown": {SOURCE_MATCHES: {**total, "revision": 2}},
            "clubs": [
                {
                    "id": -club_id,
                    "name": name,
                    **{k: season_totals(group)[k] for k in ("appearances", "minutes", "goals", "assists")},
                    "competition_tiers": list(
                        dict.fromkeys(line["_stored_competition"] for line in group if line.get("_stored_competition"))
                    ),
                }
                for (club_id, name), group in clubs.items()
            ],
            "computed_at": datetime.now(UTC),
        }
    return result


def effective_total(player_id, season, *, session=None):
    """Public batch projection shared by scalar routes; no unguarded report reads."""
    return effective_totals([player_id], season, session=session).get(player_id)


def effective_totals(player_ids, season, *, session=None, eligibility_cache=None):
    session = session or db.session
    ids = set(player_ids)
    if not ids:
        return {}
    identity = (
        select(PlayerSeasonTotal.player_api_id)
        .where(PlayerSeasonTotal.player_api_id.in_(ids))
        .union(select(PlayerMatchEntry.player_api_id).where(PlayerMatchEntry.player_api_id.in_(ids)))
        .subquery("pc2_batch_identity")
    )
    projected = scout_totals_projection(identity, season, session=session, eligibility_cache=eligibility_cache)
    rows = session.execute(
        select(projected).where(
            projected.c.player_api_id.in_(ids), projected.c.season == season, projected.c.level_group == "senior"
        )
    ).mappings()
    return {
        row["player_api_id"]: PlayerSeasonTotal(**{k: v for k, v in row.items() if k != "pc2_override"}) for row in rows
    }


def _json_relation(rows, names, table, session):
    """One JSON bind, rather than one bind per field/player (Postgres limit65535)."""
    payload = json.dumps(rows, default=lambda v: v.isoformat() if hasattr(v, "isoformat") else float(v))
    if session.get_bind().dialect.name == "postgresql":
        return (
            func.jsonb_to_recordset(cast(literal(payload), JSONB))
            .table_valued(*(column(k, table.c[k].type) for k in names))
            .render_derived(with_types=True)
            .alias("pc2_corrected")
        )
    items = func.json_each(literal(payload)).table_valued("value").alias("pc2_json")
    return select(
        *(type_coerce(func.json_extract(items.c.value, "$." + k), table.c[k].type).label(k) for k in names)
    ).subquery("pc2_corrected")


def scout_totals_projection(identity, season, *, session=None, eligibility_cache=None):
    """Correct only legacy/missing report totals; canonical cells stay SQL-owned.

    Public eligibility covers both stored and newly projected reports. Provider
    figures retain legacy age rules. No raw history is loaded for rebuilt cells.
    """
    session = session or db.session
    table = PlayerSeasonTotal.__table__
    scope = and_(table.c.season == season, table.c.level_group == "senior")
    report_sources = ("club", "user", "matches")
    stored = session.execute(
        select(table.c.player_api_id, table.c.primary_source, table.c.source_breakdown)
        .join(identity, identity.c.player_api_id == table.c.player_api_id)
        .where(scope)
    ).all()
    providers = {r.player_api_id for r in stored if r.primary_source in PROVIDER_SOURCES}
    canonical = {
        r.player_api_id
        for r in stored
        if r.primary_source in report_sources and ((r.source_breakdown or {}).get("matches") or {}).get("revision") == 2
    }
    candidates = set(
        session.execute(
            select(PlayerMatchEntry.player_api_id)
            .join(identity, identity.c.player_api_id == PlayerMatchEntry.player_api_id)
            .where(PlayerMatchEntry.season == season, trusted_entries())
            .distinct()
        ).scalars()
    )
    report_ids = candidates | {r.player_api_id for r in stored if r.primary_source in report_sources}
    eligible = public_report_ids(report_ids, eligibility_cache)
    stale_ids = (candidates & eligible) - providers - canonical
    totals = (
        reported_totals(session=session, player_ids=stale_ids, season=season, eligible_ids=eligible)
        if stale_ids
        else {}
    )
    positive = {pid for pid, _ in totals if pid > 0}
    if positive:
        from src.services.season_rollup_service import provider_totals_batch

        for pid, provider in provider_totals_batch(positive, season, session=session).items():
            totals[(pid, season)] = provider
    names = list(table.c.keys())
    keep_report = and_(table.c.player_api_id.in_(eligible & canonical & candidates), scope)
    existing = select(
        *table.c, and_(table.c.player_api_id.in_(positive | (eligible & canonical)), scope).label("pc2_override")
    ).where(scope, or_(table.c.primary_source.not_in(report_sources), keep_report))
    if not totals:
        return existing.subquery("pc2_effective_totals")
    rows = [{k: -i if k == "id" else t.get(k) for k in names} for i, t in enumerate(totals.values(), 1)]
    projected = _json_relation(rows, names, table, session)
    return union_all(existing, select(*projected.c, literal(True).label("pc2_override"))).subquery(
        "pc2_effective_totals"
    )


def saved_shadow_totals(player_ids, requested_season=None, *, eligibility_cache=None):
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
    stored_seasons = {s for (s,) in stored_query.with_entities(PlayerSeasonTotal.season).distinct()}
    entry_seasons = {
        s
        for (s,) in db.session.query(PlayerMatchEntry.season)
        .filter(PlayerMatchEntry.player_api_id.in_(ids), trusted_entries())
        .distinct()
        if season is None or s == season
    }
    stored = {
        (pid, s): total
        for s in stored_seasons | entry_seasons
        for pid, total in effective_totals(ids, s, eligibility_cache=eligibility_cache).items()
    }
    grouped = defaultdict(list)
    for row in shadow_query.all():
        grouped[(row.player_api_id, row.season)].append(row)
    result = {}
    for player_id in ids:
        seasons = {s for pid, s in set(stored) | set(grouped) if pid == player_id}
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
            elif total is None:
                source, figures = None, None
        result[player_id] = {
            **({k if k != "minutes" else "minutes_played": v for k, v in figures.items()} if figures else {}),
            "season": target,
            "provenance": {
                **{
                    k: v
                    for k, v in (
                        ((total.source_breakdown or {}).get("matches") or {})
                        if total and source == total.primary_source
                        else {}
                    ).items()
                    if k in {"club_confirmed", "self_reported_only"}
                },
                "primary_source": source,
                "source_category": "api"
                if source in PROVIDER_SOURCES
                else "self"
                if source == "user"
                else "mixed"
                if source == "matches"
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
