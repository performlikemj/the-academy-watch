"""Canonical reported season totals and a batched compatibility read projection.

Provider figures are indivisible. Reported figures come ONLY from the same
merged lines as the player page. Source evidence is derived from current trusted rows, not stored report
cells. The read projection also covers cells written before PC2.
"""

import json
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import md5
from types import SimpleNamespace

from sqlalchemy import String, and_, case, cast, column, func, literal, or_, select, type_coerce, union_all
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from src.models.funding import ClubProgram
from src.models.league import db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
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
    *,
    session=None,
    player_ids=None,
    season=None,
    identity=None,
    public=True,
    eligible_ids=None,
    fingerprints=None,
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
    rows = query.all()
    if public:
        eligible_ids = public_report_ids({row.player_api_id for row in rows}) if eligible_ids is None else eligible_ids
        rows = [row for row in rows if row.player_api_id in eligible_ids]
    if not rows:
        return {}
    grouped = defaultdict(list)
    for row in rows:
        entry = match_line_input(dict(row._mapping))
        entry["_scope"] = (entry["club_program_id"] or 0, entry["club_name"])
        # Pair with display labels, but persist storage labels for the JSON
        # boundary to decode once. Literal user entities must survive.
        entry["_stored_competition"] = row.competition
        grouped[(entry["player_api_id"], entry["season"])].append(entry)
    fingerprints = (
        fingerprints
        if fingerprints is not None
        else report_fingerprints(session, player_ids=player_ids, season=season, identity=identity)
    )
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
            "source_breakdown": {
                SOURCE_MATCHES: {**total, "revision": 2, "evidence_digest": fingerprints.get((player_id, entry_season))}
            },
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
        row["player_api_id"]: SimpleNamespace(**{k: v for k, v in row.items() if k != "pc2_override"}) for row in rows
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


def report_fingerprints(session, *, player_ids=None, season=None, identity=None):
    """Database-owned digest of every trusted input; rebuilt reads do not merge history.

    Hash exact stored input, including pairing labels, source/status, club name
    and timestamps. Deleted, disputed or edited rows invalidate the snapshot.
    PostgreSQL returns one digest per scope, not its raw match history. SQLite
    uses the same ordered-row digest contract for the local test adapter.
    """
    values = [getattr(PlayerMatchEntry, k) for k in ENTRY_KEYS] + [ClubProgram.name]
    query = (
        select(PlayerMatchEntry.player_api_id, PlayerMatchEntry.season, *values)
        .outerjoin(ClubProgram, ClubProgram.id == PlayerMatchEntry.club_program_id)
        .where(trusted_entries())
    )
    if player_ids is not None:
        query = query.where(PlayerMatchEntry.player_api_id.in_(player_ids))
    if season is not None:
        query = query.where(PlayerMatchEntry.season == season)
    if identity is not None:
        query = query.join(identity, identity.c.player_api_id == PlayerMatchEntry.player_api_id)
    if session.get_bind().dialect.name == "postgresql":
        hashed = query.with_only_columns(
            PlayerMatchEntry.player_api_id.label("player_api_id"),
            PlayerMatchEntry.season.label("season"),
            func.md5(cast(func.jsonb_build_array(*values), String)).label("digest"),
        ).subquery()
        rows = session.execute(
            select(
                hashed.c.player_api_id,
                hashed.c.season,
                func.md5(func.string_agg(hashed.c.digest, aggregate_order_by(literal(""), hashed.c.digest))),
            ).group_by(hashed.c.player_api_id, hashed.c.season)
        )
        return {(pid, year): digest for pid, year, digest in rows}
    grouped = defaultdict(list)
    for pid, year, *row in session.execute(query):
        payload = json.dumps(row, default=lambda v: v.isoformat() if hasattr(v, "isoformat") else str(v))
        grouped[(pid, year)].append(md5(payload.encode()).hexdigest())
    return {scope: md5("".join(sorted(rows)).encode()).hexdigest() for scope, rows in grouped.items()}


def effective_source_cells(player_id, season, *, public=True, current_only=False):
    """Current report evidence and whole provider evidence via the projection."""
    return scout_totals_projection(None, season, evidence_player=player_id, public=public, current_only=current_only)


def scout_totals_projection(
    identity,
    season,
    *,
    session=None,
    eligibility_cache=None,
    evidence_player=None,
    public=True,
    evidence_sources=None,
    current_only=False,
    private_eligible_ids=None,
):
    """The sole effective report projection, including evidence and absence.

    Canonical snapshots remain SQL-owned only while their current input digest
    matches. Every positive reporting scope checks current provider facts in one
    batch, including backed canonical scopes. No rebuilt match merging or writes.
    """
    session = session or db.session
    if evidence_player is not None:
        from src.services.season_rollup_service import _FEEDERS

        # Do not even load report evidence until conservative public policy
        # authorizes it. Private callers still use the writers' subject guard.
        ids = {evidence_player} if isinstance(evidence_player, int) else set(evidence_player)
        permitted = not public or bool(public_report_ids(ids, eligibility_cache))
        feeders = _FEEDERS if permitted else _FEEDERS[:4]
        if evidence_sources is not None:
            feeders = [
                f
                for source, f in zip(("fixtures", "journey", "apss", "shadow", "club", "user"), _FEEDERS)
                if source in evidence_sources and (permitted or source not in {"club", "user"})
            ]
        now = datetime.now(UTC)
        if private_eligible_ids is not None:
            assert not public and evidence_sources == {"club"}
            from src.services.season_rollup_service import _club_cells

            cells = _club_cells(ids, season, session, now, eligible_ids=private_eligible_ids)
        else:
            cells = [cell for feeder in feeders for cell in feeder(evidence_player, season, session, now)]
        if not current_only and evidence_sources is None:
            stored = (
                session.query(PlayerSeasonCell)
                .filter(
                    PlayerSeasonCell.player_api_id.in_(ids),
                    PlayerSeasonCell.season == season,
                    PlayerSeasonCell.source.in_(PROVIDER_SOURCES),
                )
                .all()
            )
            # Provider evidence retains its established whole-source cells;
            # reports always derive from current authorized match rows.
            sources = {c.source for c in stored}
            cells = [c for c in cells if c["source"] not in sources]
            cells.extend({k: getattr(c, k) for k in PlayerSeasonCell.__table__.c.keys()} for c in stored)
        return cells
    table = PlayerSeasonTotal.__table__
    scope = and_(table.c.season == season, table.c.level_group == "senior")
    report_sources = ("club", "user", "matches")
    stored = session.execute(
        select(table.c.player_api_id, table.c.primary_source, table.c.source_breakdown)
        .join(identity, identity.c.player_api_id == table.c.player_api_id)
        .where(scope)
    ).all()
    providers = {r.player_api_id for r in stored if r.primary_source in PROVIDER_SOURCES}
    fingerprints = report_fingerprints(session, identity=identity, season=season)
    candidates = {pid for pid, year in fingerprints}
    canonical = {
        r.player_api_id
        for r in stored
        if r.primary_source in report_sources
        and ((r.source_breakdown or {}).get("matches") or {}).get("revision") == 2
        and ((r.source_breakdown or {}).get("matches") or {}).get("evidence_digest")
        == fingerprints.get((r.player_api_id, season))
        and r.player_api_id in candidates
    }
    report_ids = candidates | {r.player_api_id for r in stored if r.primary_source in report_sources}
    eligible = public_report_ids(report_ids, eligibility_cache)
    stale_ids = (candidates & eligible) - providers - canonical
    totals = (
        reported_totals(
            session=session, player_ids=stale_ids, season=season, eligible_ids=eligible, fingerprints=fingerprints
        )
        if stale_ids
        else {}
    )
    # Absence is a projected result too: an orphan/disputed report must not
    # conceal real provider facts merely because no provider rollup exists yet.
    # Scope compatibility work to selected stored reporting identities; feeders
    # load each provider source once for the whole set, never per player.
    kept_reports = eligible & canonical & candidates
    withheld_reports = {r.player_api_id for r in stored if r.primary_source in report_sources} - kept_reports
    positive = {pid for pid in ({pid for pid, _ in totals} | withheld_reports | kept_reports) - providers if pid > 0}
    if positive:
        from src.services.season_rollup_service import provider_totals_batch

        for pid, provider in provider_totals_batch(positive, season, session=session).items():
            totals[(pid, season)] = provider
    kept_reports -= {pid for pid, year in totals}
    names = list(table.c.keys())
    keep_report = and_(table.c.player_api_id.in_(kept_reports), scope)
    # Never let per-source report subtotals hitch a ride on a provider row.
    # Canonical reports expose only their validated merged evidence; source
    # panels are separately derived from current trusted rows above.
    if session.get_bind().dialect.name == "postgresql":
        clean_breakdown = table.c.source_breakdown.op("-")("club").op("-")("user")
        clean_breakdown = case(
            (table.c.primary_source.in_(report_sources), clean_breakdown), else_=clean_breakdown.op("-")("matches")
        )
    else:
        clean_breakdown = case(
            (
                table.c.primary_source.in_(report_sources),
                func.json_remove(table.c.source_breakdown, "$.club", "$.user"),
            ),
            else_=func.json_remove(table.c.source_breakdown, "$.club", "$.user", "$.matches"),
        )
    clean_breakdown = type_coerce(clean_breakdown, table.c.source_breakdown.type).label("source_breakdown")
    existing = select(
        *(clean_breakdown if c.name == "source_breakdown" else c for c in table.c),
        and_(table.c.player_api_id.in_(positive | (eligible & canonical)), scope).label("pc2_override"),
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


def rollup_metadata_relations():
    """Narrow storage metadata, without any numeric or source-evidence cells.

    Admin freshness/storage counters and calendar discovery are not football
    projections. No raw ORM model/record escapes the boundary.
    """
    return tuple(
        select(*(getattr(model, k).label(k) for k in fields)).subquery()
        for model, fields in (
            (PlayerSeasonTotal, ("id", "player_api_id", "season", "level_group", "computed_at")),
            (PlayerSeasonCell, ("id", "player_api_id", "season", "level_group", "source", "synced_at")),
        )
    )


def rollup_storage_table_names():
    return (PlayerSeasonCell.__tablename__, PlayerSeasonTotal.__tablename__)


def _delete_scope(session, model, player_api_id: int, season: int | None):
    q = session.query(model).filter(model.player_api_id == player_api_id)
    if season is not None:
        q = q.filter(model.season == season)
    q.delete(synchronize_session=False)


def clear_rollup_scope(session, player_id, season):
    for model in (PlayerSeasonCell, PlayerSeasonTotal):
        _delete_scope(session, model, player_id, season)


def insert_rollup_rows(session, cells, totals):
    """Writer-only persistence. No stored facts are returned to response code."""
    for model, rows in ((PlayerSeasonCell, cells), (PlayerSeasonTotal, totals)):
        names = set(model.__table__.c.keys()) - {"id"}
        session.add_all([model(**{k: row[k] for k in names}) for row in rows])


def stored_report_sources(player_id, *, lock=False):
    """Merge safety membership only; never a returned football source label."""
    queries = (
        db.session.query(PlayerSeasonCell.source).filter_by(player_api_id=player_id),
        db.session.query(PlayerSeasonTotal.primary_source).filter_by(player_api_id=player_id),
    )
    return {
        source
        for query in queries
        for (source,) in (query.with_for_update() if lock else query)
        if source in {"club", "user"}
    }


def current_club_evidence_totals(player_ids, seasons, *, authorized_ids):
    """Authenticated club-result adapter: same current projection, batch selection.

    The caller already scopes entries to its readable results; conservative
    subject guards inside the feeders keep minor private facts withheld.
    """
    from src.services.season_rollup_service import _resolve_totals

    if not player_ids:
        return {}
    cells = scout_totals_projection(
        None,
        None,
        evidence_player=set(player_ids),
        evidence_sources={"club"},
        public=False,
        private_eligible_ids=authorized_ids,
    )
    grouped = defaultdict(list)
    for cell in cells:
        if cell["season"] in seasons:
            grouped[cell["player_api_id"]].append(cell)
    return {
        (pid, total["season"], total["level_group"]): SimpleNamespace(**total)
        for pid, rows in grouped.items()
        for total in _resolve_totals(rows, datetime.now(UTC))
    }


def rekey_rollup_rows(old_player_api_id: int, player_api_id: int, conflict) -> dict:
    """Re-key derived rows collision-safely before rebuilding them from source.

    Shadow plus user/club match-entry sources are re-keyed before refresh. Fail
    closed if API-derived rows somehow exist for a synthetic local identity.
    """
    source_cells = PlayerSeasonCell.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    source_totals = PlayerSeasonTotal.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    # API fixture/journey/APSS rows should never exist for a synthetic local id;
    # fail closed if malformed historical data says otherwise instead of
    # refreshing those totals into zeros.
    rebuildable_sources = {"club", "shadow", "user", "matches"}
    observed_sources = {row.source for row in source_cells} | {row.primary_source for row in source_totals}
    unsupported_sources = sorted(source for source in observed_sources if source not in rebuildable_sources)
    if unsupported_sources:
        raise conflict(f"rollup sources require graduation integration: {', '.join(unsupported_sources)}")

    target_cells = PlayerSeasonCell.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    target_cells_by_key = {(row.season, row.source, row.club_api_id, row.competition_tier): row for row in target_cells}
    cells_to_move = []
    for source in source_cells:
        key = (source.season, source.source, source.club_api_id, source.competition_tier)
        if key in target_cells_by_key:
            db.session.delete(source)
        else:
            target_cells_by_key[key] = source
            cells_to_move.append(source)

    target_totals_by_key = {
        (row.season, row.level_group): row
        for row in PlayerSeasonTotal.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    totals_to_move = []
    for source in source_totals:
        key = (source.season, source.level_group)
        if key in target_totals_by_key:
            db.session.delete(source)
        else:
            target_totals_by_key[key] = source
            totals_to_move.append(source)

    db.session.flush()
    for source in cells_to_move:
        source.player_api_id = player_api_id
    for source in totals_to_move:
        source.player_api_id = player_api_id
    db.session.flush()
    return {"season_cells": len(source_cells), "season_totals": len(source_totals)}
