"""Reverse the PC2 duel probes: public privacy, pairing, source and scale."""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter

import pytest
from sqlalchemy import event, text
from src.auth import issue_user_token
from src.models.follow import Follow, PlayerShadow
from src.models.funding import ClubProgram
from src.models.league import Team, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.player_suppression import PlayerSuppression
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.season_rollup import PlayerSeasonTotal
from src.models.showcase import LocalPlayer, PlayerShowcaseMedia, PlayerShowcaseProfile
from src.models.tracked_player import TrackedPlayer
from src.services import reported_match_totals as numbers
from src.services import season_rollup_service as rollup
from src.utils.sanitize import sanitize_plain_text
from test_pc2_surface_equality import SEASON, seed_personas
from test_pc2_surface_equality import app as pc2_app


@pytest.fixture
def app(monkeypatch):
    yield from pc2_app.__wrapped__(monkeypatch)


def add_reports(pid, user, club, *, opponent="Private match", status="club_confirmed"):
    db.session.add(
        PlayerMatchEntry(
            home_away="home",
            player_api_id=pid,
            season=SEASON,
            match_date=date(2025, 9, 1),
            source="club",
            status=status,
            reported_by_user_id=user,
            club_program_id=club,
            opponent=opponent,
            minutes=73,
            goals=7,
            assists=0,
            yellows=0,
            reds=0,
        )
    )
    db.session.add(
        PlayerMatchEntry(
            home_away="home",
            player_api_id=pid,
            season=SEASON,
            match_date=date(2025, 9, 2),
            source="self",
            status="self_reported",
            reported_by_user_id=user,
            opponent=opponent,
            minutes=90,
            goals=1,
            assists=0,
            yellows=0,
            reds=0,
        )
    )


def headers():
    return {"Authorization": "Bearer " + issue_user_token("pc2-scout@example.test")["token"]}


@pytest.mark.parametrize("flags", ["", "scout,season_stats,player_stats,teams"])
@pytest.mark.parametrize("frozen", ["0", "1"])
@pytest.mark.parametrize("local_flag", ["0", "1"])
def test_private_reports_never_project_on_any_public_reader(app, monkeypatch, flags, frozen, local_flag):
    ids, user, list_id = seed_personas()
    monkeypatch.setenv("SEASON_ROLLUP_READS", flags)
    monkeypatch.setenv("API_FOOTBALL_FROZEN", frozen)
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", local_flag)
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    team = Team.query.filter_by(team_id=9001).one()
    club = ClubProgram.query.one()
    blocked = {
        92001: "minor",
        92002: "unknown",
        92003: "unresolvable",
        92004: "shadow minor",
        92005: "suppressed",
        92006: "held",
        92007: "unpublished",
        92008: "conflicting DOB",
        92009: "owning-club-only",
    }
    for pid, kind in blocked.items():
        if kind not in {"unresolvable", "shadow minor"}:
            db.session.add(
                TrackedPlayer(
                    player_api_id=pid,
                    team_id=team.id,
                    player_name=kind,
                    data_source="owning-club" if kind == "owning-club-only" else "manual",
                    is_active=True,
                    birth_date="2012-01-01" if kind == "minor" else None if kind == "unknown" else "2000-01-01",
                    age=30 if kind == "unknown" else None,
                )
            )  # age snapshot is NOT adult proof
        if kind in {"shadow minor", "conflicting DOB"}:
            db.session.add(
                PlayerShadow(player_api_id=pid, player_name=kind, birth_date=date(2012, 1, 1), is_active=True)
            )
        if kind in {"held", "unpublished"}:
            local = LocalPlayer(
                display_name=kind,
                normalized_name=kind,
                status="approved",
                api_player_id=pid,
                birth_date=date(2000, 1, 1),
                provenance="club" if kind == "unpublished" else "community",
                origin_program_id=club.id if kind == "held" else None,
            )
            db.session.add(local)
        if kind == "suppressed":
            db.session.add(
                PlayerSuppression(
                    player_api_id=pid,
                    reason_code="guardian_request",
                    requester_role="guardian",
                    requester_contact="private@example.test",
                    request_statement="Withhold",
                    status="active",
                )
            )
        add_reports(pid, user, club.id)
        # Even previously canonical cells may no longer be public.
        db.session.add(
            PlayerSeasonTotal(
                computed_at=datetime.now(UTC),
                player_api_id=pid,
                season=SEASON,
                level_group="senior",
                primary_source="matches",
                appearances=2,
                minutes=163,
                goals=8,
                assists=0,
                source_breakdown={
                    "matches": {"revision": 2, "club_confirmed": 1, "self_reported_only": 1},
                    "club": {"goals": 7},
                    "user": {"goals": 1},
                },
            )
        )
        db.session.add_all(
            [
                ScoutWatchlistEntry(user_account_id=user, player_api_id=pid),
                Follow(list_id=list_id, kind="player", selector={"player_api_id": pid}),
            ]
        )
    club.emergency_hidden = True  # original personas remain unrelated to the new origin link
    db.session.commit()
    assert not (numbers.public_report_ids(blocked) & set(blocked))
    assert not numbers.effective_totals(blocked, SEASON)
    assert all(not row.get("goals") for row in numbers.saved_shadow_totals(blocked, SEASON).values())
    client = app.test_client()
    for pid, kind in blocked.items():
        assert client.get(f"/api/players/{pid}/matches?view=lines&season={SEASON}").status_code == 404
        for suffix in ("season-stats", "stats"):
            response = client.get(f"/api/players/{pid}/{suffix}?season={SEASON}")
            assert response.status_code in {200, 404}, (kind, response.json)
            # Provider data is permitted; this fixture has none, so no reported figures or labels.
            assert "Private match" not in response.get_data(as_text=True)
            payload = response.json
            if isinstance(payload, dict) and response.status_code == 200:
                assert payload.get("goals", 0) in {None, 0}, (kind, payload)
                assert (payload.get("summary") or {}).get("goals", 0) in {None, 0}, (kind, payload)
                assert not any(k in (payload.get("source_breakdown") or {}) for k in ("club", "user", "matches"))
        assert not client.get(f"/api/scout/compare?ids={pid}&season={SEASON}").json["players"]
    for path in (
        f"/api/scout/players?season={SEASON}&per_page=50",
        f"/api/scout/watchlist?season={SEASON}",
        f"/api/scout/lists/{list_id}/resolve?season={SEASON}",
        f"/api/scout/leaderboards?season={SEASON}&source=mixed",
        f"/api/scout/export.csv?season={SEASON}",
    ):
        response = client.get(path, headers=headers())
        assert response.status_code == 200, (path, response.json)
        assert not any(str(pid) in response.get_data(as_text=True) for pid in blocked), path
    from src.utils.team_season_stats import live_stats_by_player, rollup_stats_by_player

    assert not rollup_stats_by_player(list(blocked), SEASON)[0]
    assert not live_stats_by_player(TrackedPlayer.query.filter(TrackedPlayer.player_api_id.in_(blocked)).all(), SEASON)
    from src.services.scout_digest_service import _prime_number_totals

    cache = {}
    _prime_number_totals(blocked, cache)
    assert all(cache["__pc2_numbers__"][pid] is None for pid in blocked)
    # Genuine whole provider total survives the report guard, without private club data.
    provider = ids["Provider"]
    TrackedPlayer.query.filter_by(player_api_id=provider).one().birth_date = "2012-01-01"
    db.session.commit()
    total = numbers.effective_total(provider, SEASON)
    assert (total.appearances, total.minutes, total.goals, total.primary_source) == (1, 90, 2, "fixtures")


def test_disputed_rows_do_not_enter_any_report_total(app):
    ids, user, _list = seed_personas()
    pid = ids["Tobi Olawale"]
    club = ClubProgram.query.one()
    add_reports(pid, user, club.id, status="disputed")
    PlayerMatchEntry.query.filter_by(player_api_id=pid, source="self").update({"status": "disputed"})
    db.session.commit()
    assert numbers.effective_total(pid, SEASON) is None
    rollup.refresh_player(pid, SEASON)
    db.session.commit()
    assert numbers.effective_total(pid, SEASON) is None


def test_boundary_decoded_pairing_preserves_literal_entities_old_and_new(app):
    ids, user, _list = seed_personas()
    pid = ids["Tobi Olawale"]
    add_reports(pid, user, ClubProgram.query.one().id)
    rows = PlayerMatchEntry.query.filter_by(player_api_id=pid).order_by(PlayerMatchEntry.id).all()
    rows[0].opponent = sanitize_plain_text("A & B")
    rows[1].opponent = sanitize_plain_text("A &AMP; B")
    rows[1].match_date = rows[0].match_date
    rows[0].minutes = 90
    db.session.commit()
    before = [row.opponent for row in rows]
    for _stage in range(2):
        payload = app.test_client().get(f"/api/players/{pid}/matches?view=lines&season={SEASON}").json
        assert payload["seasons"][0]["totals"]["appearances"] == 2
        total = numbers.effective_total(pid, SEASON)
        assert (total.appearances, total.minutes) == (2, 180)
        rollup.refresh_player(pid, SEASON)
        db.session.commit()
    assert [row.opponent for row in rows] == before


def test_mixed_reports_have_distinct_filter_and_honest_provenance(app):
    ids, user, _list = seed_personas()
    pid = ids["Tobi Olawale"]
    add_reports(pid, user, ClubProgram.query.one().id)
    PlayerMatchEntry.query.filter_by(player_api_id=pid, source="club").one().goals = 0
    own = PlayerMatchEntry.query.filter_by(player_api_id=pid, source="self").one()
    own.goals = 3
    for day in range(3, 12):
        db.session.add(
            PlayerMatchEntry(
                home_away="home",
                player_api_id=pid,
                season=SEASON,
                match_date=date(2025, 9, day),
                source="self",
                status="self_reported",
                reported_by_user_id=user,
                opponent=f"Own {day}",
                minutes=90,
                goals=3,
                assists=0,
            )
        )
    db.session.commit()
    client = app.test_client()
    for _stage in range(2):
        for path in (f"/api/scout/players?season={SEASON}&source=club", f"/api/scout/leaderboards?season={SEASON}"):
            payload = client.get(path).json
            rows = payload.get("players", [p for board in payload.get("leaderboards", {}).values() for p in board])
            assert pid not in {p["player_id"] for p in rows}
        row = next(
            p
            for p in client.get(f"/api/scout/players?season={SEASON}&source=mixed").json["players"]
            if p["player_id"] == pid
        )
        assert row["goals"] == 30 and row["appearances"] == 11
        assert row["provenance"]["source_category"] == "mixed"
        assert row["provenance"]["club_confirmed"] == 1
        assert row["provenance"]["self_reported_only"] == 10
        rollup.refresh_player(pid, SEASON)
        db.session.commit()


def test_card_plain_bio_and_nonprimary_approved_photo(app):
    ids, _user, _list = seed_personas()
    local = -ids["Kofi Asante-Reid"]
    profile = PlayerShowcaseProfile.query.filter_by(local_player_id=local).one()
    profile.bio = "<b>Tom & Jerry</b>\nFast > strong &AMP; &#128512; " + "a" * 140 + " & end"
    PlayerShowcaseMedia.query.filter_by(local_player_id=local, status="approved").update({"is_primary": False})
    db.session.commit()
    row = next(
        p
        for p in app.test_client().get(f"/api/scout/players?season={SEASON}").json["players"]
        if p["player_id"] == -local
    )
    assert row["bio_line"].startswith("Tom & Jerry Fast > strong ")
    assert "&AMP; &#128512;" in row["bio_line"]  # preserve literal user entities
    assert len(row["bio_line"]) <= 160 and "&amp;" not in row["bio_line"] and "\n" not in row["bio_line"]
    assert row["approved_photo_url"].endswith("/pc2/approved.jpg")
    assert "pending.jpg" not in json.dumps(row)


def test_season_stats_select_effective_total_once_even_when_missing(app, monkeypatch):
    ids, _user, _list = seed_personas()
    calls = []
    original = numbers.effective_total

    def counted(*a, **kw):
        calls.append(a)
        return original(*a, **kw)

    monkeypatch.setattr(numbers, "effective_total", counted)
    monkeypatch.setattr("src.routes.players.effective_total", counted)
    for pid in (ids["Kofi Asante-Reid"], ids["Tobi Olawale"], ids["Provider"]):
        calls.clear()
        response = app.test_client().get(f"/api/players/{pid}/season-stats?season={SEASON}")
        assert response.status_code == 200
        assert len(calls) == 1, calls


def test_dry_run_counts_figures_and_all_losses_beyond_sample_cap(app):
    from scripts.rebuild_reported_match_totals import comparable, run, snapshot

    ids, _user, _list = seed_personas()
    for pid in (92000, 92001):
        db.session.add(
            PlayerSeasonTotal(
                computed_at=datetime.now(UTC),
                player_api_id=pid,
                season=SEASON,
                level_group="senior",
                primary_source="user",
                appearances=12,
                minutes=1080,
                goals=0,
                assists=0,
            )
        )
    db.session.commit()
    before = {pid: snapshot(db.session, pid) for pid in [*ids.values(), 92000, 92001]}
    result = run(db.session, dry_run=True, limit=100, after=-(2**31), delay=0)
    assert result["seasons_losing_totals"] == 2
    assert {loss["player_id"] for loss in result["losses"]} == {92000, 92001}
    assert len(result["samples"]) == 5 and all(s["player_id"] not in {92000, 92001} for s in result["samples"])
    assert result["seasons_figures_changed"] < result["seasons_changed"]  # metadata-only Emeka
    for pid, prior in before.items():
        assert {k: comparable(v) for k, v in snapshot(db.session, pid).items()} == {
            k: comparable(v) for k, v in prior.items()
        }
    if os.environ.get("PC2_REVIEW_REBUILD_PROOF"):
        Path(os.environ["PC2_REVIEW_REBUILD_PROOF"]).write_text(json.dumps(result, indent=2, default=str))


@pytest.mark.skipif(not os.environ.get("PC2_TEST_DATABASE_URL"), reason="real PostgreSQL scale proof")
def test_postgres_four_thousand_reports_no_bind_cliff_and_rebuilt_skips_history(app, monkeypatch):
    _ids, user, _list = seed_personas()
    # Adult tracked identities are in the actual desk universe; bulk setup avoids N+1.
    team_id = Team.query.filter_by(team_id=9001).one().id
    db.session.execute(
        TrackedPlayer.__table__.insert(),
        [
            dict(
                player_api_id=100000 + i,
                team_id=team_id,
                player_name=f"Scale {i}",
                birth_date="2000-01-01",
                is_active=True,
            )
            for i in range(4000)
        ],
    )
    db.session.execute(
        PlayerMatchEntry.__table__.insert(),
        [
            dict(
                player_api_id=100000 + i,
                season=SEASON,
                match_date=date(2025, 9, 1),
                source="self",
                status="self_reported",
                reported_by_user_id=user,
                opponent="Scale",
                home_away="home",
                minutes=90,
                goals=1,
                assists=0,
            )
            for i in range(4000)
        ],
    )
    db.session.commit()
    db.session.execute(text("ANALYZE"))  # realistic planner statistics on this owned bulk fixture
    from src.routes.scout import _scout_identity_subquery

    parameters = []
    timings = []

    def record(_conn, _cursor, statement, params, _context, _many):
        parameters.append(len(params))
        _context.pc2_started = perf_counter()

    def completed(_conn, _cursor, statement, params, context, _many):
        timings.append(
            {"seconds": round(perf_counter() - context.pc2_started, 3), "sql": statement[:700], "binds": len(params)}
        )

    event.listen(db.engine, "before_cursor_execute", record)
    event.listen(db.engine, "after_cursor_execute", completed)
    proof = {}
    try:
        client = app.test_client()
        for path in (
            f"/api/scout/players?season={SEASON}&per_page=50",
            f"/api/scout/leaderboards?season={SEASON}&source=self",
        ):
            start = perf_counter()
            response = client.get(path)
            assert response.status_code == 200, response.json
            if "/players?" in path:
                assert response.json["total"] >= 4000
                assert any(p["player_id"] >= 100000 for p in response.json["players"])
            proof[path] = round(perf_counter() - start, 3)
        assert max(parameters) < 65535
        canonical = numbers.reported_totals(player_ids=range(100000, 104000), season=SEASON)
        db.session.execute(PlayerSeasonTotal.__table__.insert(), list(canonical.values()))
        for pid in _ids.values():
            rollup.refresh_player(pid, SEASON)
        db.session.commit()

        def unexpected(*a, **kw):
            raise AssertionError("rebuilt reports loaded raw history for merging")

        db.session.execute(text("ANALYZE"))
        monkeypatch.setattr(numbers, "merge_match_lines", unexpected)
        start = perf_counter()
        projection = numbers.scout_totals_projection(_scout_identity_subquery(), SEASON)
        rows = db.session.execute(projection.select().where(projection.c.player_api_id >= 100000)).all()
        assert len(rows) == 4000 and all(row.minutes == 90 for row in rows)
        proof["rebuilt_projection_seconds"] = round(perf_counter() - start, 3)
        for path in (
            f"/api/scout/players?season={SEASON}&per_page=50",
            f"/api/scout/leaderboards?season={SEASON}&source=self",
        ):
            start = perf_counter()
            response = client.get(path)
            assert response.status_code == 200, response.json
            proof["rebuilt " + path] = round(perf_counter() - start, 3)
        proof["max_bind_parameters"] = max(parameters)
        proof["slow_queries"] = sorted(timings, key=lambda item: item["seconds"], reverse=True)[:8]
        if os.environ.get("PC2_REVIEW_SCALE_PROOF"):
            Path(os.environ["PC2_REVIEW_SCALE_PROOF"]).write_text(json.dumps(proof, indent=2))
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
        event.remove(db.engine, "after_cursor_execute", completed)
