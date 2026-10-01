"""The same strict adult evidence gates every scout discovery and saved read."""

import csv
import io
import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
import sqlalchemy as sa
from src.auth import issue_user_token
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot, PlayerShadow
from src.models.journey import PlayerJourney
from src.models.league import Team, UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.services.public_adult import public_adult_ids


@pytest.fixture
def desk(app, monkeypatch):
    from src.routes.scout import scout_bp

    app.register_blueprint(scout_bp, url_prefix="/api")
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    monkeypatch.delenv("SCOUT_INCLUDE_LOCAL_PLAYERS", raising=False)
    team = Team(team_id=800, name="Fixture academy", country="England", season=2025)
    user = UserAccount(
        email="adult-desk@example.test",
        display_name="Fixture Scout",
        display_name_lower="fixture scout",
        scout_digest_opt_in=True,
        scout_tier="pro",
    )
    db.session.add_all([team, user])
    db.session.flush()
    today = datetime.now(UTC).date()
    # Minor/unknown players have the best stats: filtering must precede LIMIT.
    cases = {
        1800: (18, today.replace(year=today.year - 18).isoformat()),
        1801: (20, f"{today.year - 20}-01-01"),
        1802: (22, f"{today.year - 22}-01-01"),
        1803: (23, f"{today.year - 23}-01-01"),
        1810: (40, f"{today.year - 17}-01-01"),  # stale adult snapshot cannot overrule DOB
        1811: (40, None),  # stored age alone is not trusted evidence
        1812: (None, None),
        1813: (40, "unknown"),
        1814: (40, f"{today.year - 20}-01-01"),  # conflicting shadow DOB below
        1815: (26, None),  # journey DOB establishes adulthood
    }
    fixture = Fixture(
        fixture_id_api=8000, season=2025, home_team_api_id=800, away_team_api_id=801, date_utc=datetime(2025, 9, 1)
    )
    db.session.add(fixture)
    db.session.flush()
    for pid, (age, dob) in cases.items():
        db.session.add(
            TrackedPlayer(
                player_api_id=pid,
                player_name=f"Desk player {pid}",
                team_id=team.id,
                birth_date=dob,
                age=age,
                status="on_loan",
                position="Goalkeeper",
                is_active=True,
            )
        )
        db.session.add(
            FixturePlayerStats(
                fixture_id=fixture.id,
                player_api_id=pid,
                team_api_id=800,
                position="G",
                minutes=500,
                goals=100 if pid in range(1810, 1815) else 1,
                assists=1,
                saves=3,
                rating=7,
            )
        )
    db.session.add(
        PlayerShadow(
            player_api_id=1814,
            player_name="Conflicting identity",
            birth_date=date(today.year - 17, 1, 1),
            is_active=True,
        )
    )
    db.session.add(PlayerJourney(player_api_id=1815, player_name="Journey adult", birth_date="2000-01-01"))
    follow_list = FollowList(user_account_id=user.id, name="Stored fixtures", is_active=True)
    db.session.add(follow_list)
    db.session.flush()
    for pid in cases:
        db.session.add(ScoutWatchlistEntry(user_account_id=user.id, player_api_id=pid, note=f"note {pid}"))
        db.session.add(
            Follow(
                list_id=follow_list.id,
                kind="player",
                selector={"player_api_id": pid},
                label=f"Desk player {pid}",
            )
        )
    db.session.commit()
    return SimpleNamespace(
        adults={1800, 1801, 1802, 1803, 1815},
        excluded={1810, 1811, 1812, 1813, 1814},
        ids=set(cases),
        user=user,
        team=team,
        follow_list=follow_list,
        headers={"Authorization": f"Bearer {issue_user_token(user.email)['token']}"},
    )


@pytest.mark.parametrize("args", ["", "&min_age=0", "&max_age=99", "&search=Desk", "&sort=goals"])
def test_browse_filters_before_pagination_and_counts(client, desk, args):
    response = client.get(f"/api/scout/players?per_page=1{args}")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == len(desk.adults)
    ids = set()
    for page in range(1, len(desk.adults) + 1):
        body = client.get(f"/api/scout/players?per_page=1&page={page}{args}").get_json()
        ids.update(row["player_id"] for row in body["players"])
    assert ids == desk.adults


@pytest.mark.parametrize("maximum,expected", [(20, {1800, 1801}), (22, {1800, 1801, 1802})])
def test_under_age_chips_have_adult_lower_bound(client, desk, maximum, expected):
    ids = {row["player_id"] for row in client.get(f"/api/scout/players?max_age={maximum}").get_json()["players"]}
    assert ids == expected


@pytest.mark.parametrize("phase", ["all", "attack", "midfield", "defense", "gk"])
def test_every_leaderboard_excludes_ineligible_high_scorers(client, desk, phase):
    response = client.get(f"/api/scout/leaderboards?phase={phase}&limit=1&min_age=0")
    assert response.status_code == 200
    boards = response.get_json()["leaderboards"]
    assert any(boards.values())
    assert all(row["player_id"] in desk.adults for rows in boards.values() for row in rows)


@pytest.mark.parametrize("pid", [1810, 1811, 1812, 1813, 1814])
def test_compare_and_explicit_csv_ids_do_not_bypass_rule(client, desk, pid):
    ids = f"1800,{pid}"
    response = client.get(f"/api/scout/compare?ids={ids}")
    assert response.status_code == 200
    assert {p["profile"]["player_id"] for p in response.get_json()["players"]} == {1800}
    response = client.get(f"/api/scout/export.csv?ids={ids}", headers=desk.headers)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert {int(row["player_id"]) for row in rows} == {1800}


def test_filtered_csv_and_global_search(client, desk):
    response = client.get("/api/scout/export.csv?min_age=0", headers=desk.headers)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert {int(row["player_id"]) for row in rows} == desk.adults
    response = client.get("/api/players/search?q=Desk")
    assert response.status_code == 200
    assert {row["player_api_id"] for row in response.get_json()} == desk.adults


@pytest.mark.parametrize("pid", [1810, 1811, 1812, 1813, 1814])
def test_watchlist_add_refuses_even_existing_ineligible_rows(client, desk, pid):
    response = client.post("/api/scout/watchlist", json={"player_api_id": pid}, headers=desk.headers)
    assert response.status_code == 404
    assert response.get_json() == {"error": "Player not found"}
    response = client.patch(f"/api/scout/watchlist/{pid}", json={"note": "new"}, headers=desk.headers)
    assert response.status_code == 404
    db.session.query(ScoutWatchlistEntry).filter_by(player_api_id=pid).delete()
    db.session.commit()
    response = client.post("/api/scout/watchlist", json={"player_api_id": pid}, headers=desk.headers)
    assert response.status_code == 404
    assert ScoutWatchlistEntry.query.filter_by(player_api_id=pid).count() == 0


def test_watchlist_and_embedded_follows_hide_rows_without_deleting(client, desk):
    response = client.get("/api/scout/watchlist", headers=desk.headers)
    assert response.status_code == 200
    assert {entry["player_api_id"] for entry in response.get_json()["entries"]} == desk.adults
    response = client.get("/api/scout/watchlist/ids", headers=desk.headers)
    assert set(response.get_json()["player_ids"]) == desk.adults
    response = client.get("/api/scout/lists", headers=desk.headers)
    body = response.get_json()["lists"][0]
    assert body["follow_count"] == len(desk.adults)
    assert {f["selector"]["player_api_id"] for f in body["follows"]} == desk.adults
    assert ScoutWatchlistEntry.query.count() == Follow.query.count() == len(desk.ids)


@pytest.mark.parametrize("kind", ["player", "query", "academy_club", "geo"])
def test_all_follow_resolution_kinds(client, desk, kind):
    Follow.query.delete()
    selectors = {
        "player": [{"player_api_id": pid} for pid in desk.ids],
        "query": [{"scout_args": {"min_age": 0}}],
        "academy_club": [{"team_id": desk.team.id}],
        "geo": [{"countries": ["England"], "match": "playing_in"}],
    }
    if kind == "geo":
        TrackedPlayer.query.update({TrackedPlayer.current_club_db_id: desk.team.id})
    for selector in selectors[kind]:
        db.session.add(Follow(list_id=desk.follow_list.id, kind=kind, selector=selector, label="Saved fixture"))
    db.session.commit()
    response = client.get(f"/api/scout/lists/{desk.follow_list.id}/resolve?limit=50", headers=desk.headers)
    assert response.status_code == 200
    assert {p["player_api_id"] for p in response.get_json()["players"]} == desk.adults


def test_digest_and_snapshots_skip_ineligible_and_recheck_cache(desk):
    from src.services.scout_digest_service import _entry_update, _player_state, build_user_digest

    entries = ScoutWatchlistEntry.query.all()
    digest = build_user_digest(desk.user, entries)
    assert digest and digest["players"] == len(desk.adults)
    for pid in desk.excluded:
        assert f"Desk player {pid}" not in digest["html"] + digest["text"]
        snap = FollowPlayerSnapshot(user_account_id=desk.user.id, player_api_id=pid)
        assert _entry_update(snap, {}) is None
        assert snap.last_snapshot is None
    cache = {}
    assert _player_state(1800, cache)["kind"] == "tracked"
    TrackedPlayer.query.filter_by(player_api_id=1800).update({"birth_date": "2015-01-01"})
    db.session.commit()
    # Eligibility is a run snapshot; a fresh run must recheck changed DOBs.
    assert _player_state(1800, {})["kind"] == "none"


@pytest.mark.parametrize("source", ["watchlist", "list", "both"])
def test_digest_eligibility_queries_once_per_player_per_run_across_pages(app, desk, monkeypatch, source):
    from src.jobs import run_scout_digests as job
    from src.services import public_adult

    desk.user.scout_digest_opt_in = False
    users = [
        UserAccount(
            email=f"watcher-{index}@example.test",
            display_name=f"Watcher {index}",
            display_name_lower=f"watcher {index}",
            scout_digest_opt_in=True,
        )
        for index in range(8)
    ]
    db.session.add_all(users)
    db.session.flush()
    for user in users:
        if source in {"watchlist", "both"}:
            db.session.add_all(ScoutWatchlistEntry(user_account_id=user.id, player_api_id=pid) for pid in (1800, 1810))
        if source in {"list", "both"}:
            follow_list = FollowList(user_account_id=user.id, name="Run fixtures", is_active=True)
            db.session.add(follow_list)
            db.session.flush()
            db.session.add_all(
                Follow(list_id=follow_list.id, kind="player", selector={"player_api_id": pid}, label="Stored fixture")
                for pid in (1800, 1810)
            )
    db.session.commit()
    monkeypatch.setattr(job, "MAX_DIGEST_USERS", 2)
    monkeypatch.setattr(job, "_get_api_client", lambda: SimpleNamespace(get_player_injuries=lambda pid: []))

    evaluations = Counter()
    queries = []
    check = public_adult.public_adult_ids

    def count_query(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    def counted_check(ids):
        ids = list(ids)
        evaluations.update(ids)
        # Count real eligibility SQL separately from rendering/stat queries.
        sa.event.listen(db.engine, "before_cursor_execute", count_query)
        try:
            return check(ids)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", count_query)

    monkeypatch.setattr(public_adult, "public_adult_ids", counted_check)
    for run in (1, 2):
        summary = job.run(dry_run=True, min_interval_hours=0)
        assert summary["users_considered"] == summary["would_send"] == len(users)
        assert summary["errors"] == summary["skipped"] == 0
        assert evaluations == Counter({1800: run, 1810: run})
        # Six source/hold queries per check, independent of eight watchers and
        # four pages. List resolution batches both IDs in one check.
        assert len(queries) == run * (6 if source == "list" else 12)
    assert ScoutWatchlistEntry.query.filter_by(player_api_id=1810).count() >= 1
    assert FollowPlayerSnapshot.query.count() == 0  # dry runs never persist baselines


def test_prefilled_digest_state_cannot_bypass_ineligible_result(desk):
    from src.services.scout_digest_service import _player_state

    cache = {1810: {"kind": "tracked", "stats": {"goals": 100}}}
    assert _player_state(1810, cache)["kind"] == "none"
    assert _player_state(1810, cache)["kind"] == "none"
    assert _player_state(1800, cache)["kind"] == "tracked"


def test_follow_player_eligibility_is_batched_before_resolution(desk, monkeypatch):
    from src.services import public_adult
    from src.services.follow_resolver import resolve_list

    calls = []
    check = public_adult.public_adult_ids

    def counted_check(ids):
        ids = list(ids)
        calls.append(set(ids))
        return check(ids)

    monkeypatch.setattr(public_adult, "public_adult_ids", counted_check)
    for _ in range(2):
        assert {row["player_api_id"] for row in resolve_list(desk.follow_list)} == desk.adults
    assert calls == [desk.ids, desk.ids]  # fresh ordinary reads recheck once per list


def test_gol_rechecks_cached_frames_and_all_player_relations(app, desk):
    from src.services.gol_dataframes import DataFrameCache
    from src.services.gol_player_lookup import GolPlayerLookup
    from src.services.gol_service import GolService

    frames = {
        name: pd.DataFrame({"player_api_id": sorted(desk.ids)})
        for name in (
            "tracked",
            "journeys",
            "journey_entries",
            "cohort_members",
            "players",
            "fixture_stats",
        )
    }
    cache = DataFrameCache()
    cache._cache = frames
    import time

    cache._loaded_at = time.time()
    for frame in cache.get_frames(app).values():
        assert set(frame["player_api_id"]) == desk.adults
    TrackedPlayer.query.filter_by(player_api_id=1800).update({"birth_date": "2015-01-01"})
    db.session.commit()
    for frame in cache.get_frames(app).values():
        assert set(frame["player_api_id"]) == desk.adults - {1800}
    lookup = GolPlayerLookup(app)
    for pid in desk.excluded:
        assert lookup._find_existing(f"Desk player {pid}") is None
    assert lookup._find_existing("Desk player 1801")["player_name"] == "Desk player 1801"
    # Suggestions also sample the eligible universe before LIMIT.
    service = object.__new__(GolService)
    suggestions = json.dumps(service.get_suggestions())
    assert all(f"Desk player {pid}" not in suggestions for pid in desk.excluded | {1800})


@pytest.mark.parametrize("frozen", [False, True])
def test_scout_worldwide_search_uses_trusted_dob_not_reported_age(client, desk, monkeypatch, frozen):
    from src.services.player_shadow_service import search_players

    monkeypatch.setenv("API_FOOTBALL_FROZEN", "1" if frozen else "0")
    # Outside tracked universe: upstream DOB can establish a new adult, age alone cannot.
    profiles = [
        {"player": {"id": pid, "name": f"Upstream {pid}", "age": 40, "birth": {"date": dob}}}
        for pid, dob in [(9000, "2000-01-01"), (9001, "2015-01-01"), (9002, None)]
    ]
    fake = SimpleNamespace(search_player_profiles_global=lambda q: profiles)
    results = search_players("Desk" if frozen else "Upstream", api_client=fake)
    expected = desk.adults if frozen else {9000}
    assert {row["player_api_id"] for row in results} == expected
    monkeypatch.setattr("src.routes.scout._get_api_client", lambda: fake)
    response = client.get("/api/scout/player-search?q=" + ("Desk" if frozen else "Upstream"), headers=desk.headers)
    assert response.status_code == 200
    assert {row["player_api_id"] for row in response.get_json()["players"]} == expected


def test_rule_ignores_client_age_and_rejects_contradictory_sources(desk):
    assert public_adult_ids(desk.ids) == desk.adults


def test_eighteenth_birthday_and_year_only_local_evidence(client, desk, monkeypatch):
    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)
    TrackedPlayer.query.filter_by(player_api_id=1800).update(
        {"birth_date": tomorrow.replace(year=tomorrow.year - 18).isoformat()}
    )
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "1")
    eligible = set()
    for year in [None, today.year - 18, today.year - 19]:
        local = LocalPlayer(
            display_name=f"Year-only fixture {year}", birth_year=year, status="approved", provenance="community"
        )
        db.session.add(local)
        db.session.flush()
        local.api_player_id = -local.id
        db.session.add(PlayerShadow(player_api_id=-local.id, player_name=local.display_name, is_active=True))
        if year is not None and year < today.year - 18:
            eligible.add(-local.id)
    db.session.commit()
    body = client.get("/api/scout/players?per_page=100").get_json()
    assert {p["player_id"] for p in body["players"]} == desk.adults - {1800} | eligible


def test_upstream_conflicting_dobs_and_gol_lookup_do_not_ingest_minors(app, desk, monkeypatch):
    from src.services.gol_player_lookup import GolPlayerLookup
    from src.services.public_adult import public_adult_profile_ids

    profiles = [
        {"player": {"id": 9900, "name": "Upstream fixture", "birth": {"date": dob}}}
        for dob in ["2015-01-01", "2000-01-01"]
    ]
    assert public_adult_profile_ids(profiles) == set()
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    lookup = GolPlayerLookup(app)
    lookup.api_client = SimpleNamespace(search_player_profiles=lambda name: profiles)
    monkeypatch.setattr(lookup, "_sync_journey", lambda pid: pytest.fail("ineligible player must not be synced"))
    assert lookup.lookup("Upstream fixture")["found"] is False
    assert TrackedPlayer.query.filter_by(player_api_id=9900).count() == 0


def test_gol_cannot_call_unverified_web_discovery(monkeypatch):
    from src.services.gol_service import GolService, active_tool_schemas

    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    assert {tool["function"]["name"] for tool in active_tool_schemas()} == {"run_analysis", "lookup_player"}
    service = object.__new__(GolService)
    assert service._execute_tool("search_web", {"query": "best U18 players"})["result_type"] == "error"


def test_paid_gol_replay_rechecks_adult_eligibility_before_returning_stored_answer(app, client, desk, monkeypatch):
    from src.models.gol_credits import GolCreditLedger
    from src.routes.gol import gol_bp
    from src.services.gol_service import GolService

    app.register_blueprint(gol_bp, url_prefix="/api")
    monkeypatch.setenv("BILLING_ENABLED", "1")
    monkeypatch.setenv("GOL_FREE_ALLOWANCE", "10")
    # A model-free initial answer containing a currently eligible adult.
    monkeypatch.setattr(GolService, "__init__", lambda self, **kwargs: None)
    monkeypatch.setattr(
        GolService,
        "chat",
        lambda *args: iter(
            [
                {"event": "token", "data": {"content": "Desk player 1800"}},
                {"event": "done", "data": {}},
            ]
        ),
    )
    payload = {"message": "List a player", "client_msg_id": "n3_replay_adult"}
    response = client.post("/api/gol/chat", json=payload, headers=desk.headers)
    assert response.status_code == 200
    assert "Desk player 1800" in response.get_data(as_text=True)
    replay = client.post("/api/gol/chat", json=payload, headers=desk.headers)
    assert replay.status_code == 200
    assert "Desk player 1800" in replay.get_data(as_text=True)
    TrackedPlayer.query.filter_by(player_api_id=1800).update({"birth_date": "2015-01-01"})
    db.session.commit()
    replay = client.post("/api/gol/chat", json=payload, headers=desk.headers)
    assert replay.status_code == 409
    assert "Desk player 1800" not in replay.get_data(as_text=True)
    assert GolCreditLedger.query.filter_by(client_msg_id="n3_replay_adult", kind="debit").count() == 1
