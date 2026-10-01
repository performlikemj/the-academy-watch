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
        # Four source/hold queries per check, independent of eight watchers and
        # four pages. List resolution batches both IDs in one check.
        assert len(queries) == run * (4 if source == "list" else 8)
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


def _seed_hidden_capacity(desk, source, count):
    Follow.query.delete()
    ScoutWatchlistEntry.query.delete()
    hidden_ids = set(range(20000, 20000 + count))
    for pid in hidden_ids:
        db.session.add(
            TrackedPlayer(
                player_api_id=pid,
                player_name=f"Hidden fixture {pid}",
                team_id=desk.team.id,
                birth_date="2015-01-01" if pid % 2 else None,
                age=40,
                is_active=True,
            )
        )
        if source == "list":
            db.session.add(
                Follow(list_id=desk.follow_list.id, kind="player", selector={"player_api_id": pid}, label="Saved")
            )
        else:
            db.session.add(ScoutWatchlistEntry(user_account_id=desk.user.id, player_api_id=pid, note="Retained note"))
    db.session.commit()
    return hidden_ids


@pytest.mark.parametrize("source,hidden_count", [("list", 1), ("list", 50), ("watchlist", 1), ("watchlist", 200)])
def test_hidden_capacity_allows_add_with_bounded_eligibility_sql(client, desk, monkeypatch, source, hidden_count):
    from src.routes import scout

    hidden_ids = _seed_hidden_capacity(desk, source, hidden_count)
    batches = []
    queries = []
    check = scout.public_adult_ids

    def count_query(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    def counted_check(ids):
        ids = set(ids)
        batches.append(ids)
        sa.event.listen(db.engine, "before_cursor_execute", count_query)
        try:
            return check(ids)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", count_query)

    monkeypatch.setattr(scout, "public_adult_ids", counted_check)
    path = f"/api/scout/lists/{desk.follow_list.id}/follows" if source == "list" else "/api/scout/watchlist"
    payload = {"kind": "player", "selector": {"player_api_id": 1800}} if source == "list" else {"player_api_id": 1800}
    response = client.post(path, json=payload, headers=desk.headers)
    assert response.status_code == 201, response.get_json()
    assert batches == [hidden_ids]  # one capacity evaluation, independent of row count
    assert len(queries) == 4  # narrow evidence and holds, independent of saved-row count

    if source == "list":
        body = client.get("/api/scout/lists", headers=desk.headers).get_json()["lists"][0]
        assert body["follow_count"] == len(body["follows"]) == 1
        assert body["follows"][0]["selector"]["player_api_id"] == 1800
        body = client.patch(
            f"/api/scout/lists/{desk.follow_list.id}", json={"is_active": False}, headers=desk.headers
        ).get_json()["list"]
        assert body["follow_count"] == len(body["follows"]) == 1
        assert desk.follow_list.follows.count() == hidden_count + 1
    else:
        body = client.get("/api/scout/watchlist", headers=desk.headers).get_json()
        assert [entry["player_api_id"] for entry in body["entries"]] == [1800]
        assert client.get("/api/scout/watchlist/ids", headers=desk.headers).get_json()["player_ids"] == [1800]
        assert ScoutWatchlistEntry.query.count() == hidden_count + 1

    # Fresh requests must see changed evidence. Reactivation may exceed the cap:
    # every saved row and note reappears, and only further additions are blocked.
    TrackedPlayer.query.filter(TrackedPlayer.player_api_id.in_(hidden_ids)).update({"birth_date": "2000-01-01"})
    db.session.commit()
    if source == "list":
        body = client.get("/api/scout/lists", headers=desk.headers).get_json()["lists"][0]
        assert body["follow_count"] == len(body["follows"]) == hidden_count + 1
        assert {f["selector"]["player_api_id"] for f in body["follows"]} == hidden_ids | {1800}
        payload["selector"]["player_api_id"] = 1801
    else:
        entries = client.get("/api/scout/watchlist", headers=desk.headers).get_json()["entries"]
        assert {entry["player_api_id"] for entry in entries} == hidden_ids | {1800}
        assert all(entry["note"] == "Retained note" for entry in entries if entry["player_api_id"] in hidden_ids)
        assert set(
            client.get("/api/scout/watchlist/ids", headers=desk.headers).get_json()["player_ids"]
        ) == hidden_ids | {1800}
        payload["player_api_id"] = 1801
    response = client.post(path, json=payload, headers=desk.headers)
    assert response.status_code == (409 if hidden_count > 1 else 201), response.get_json()
    if source == "watchlist" and hidden_count == 200:
        # An existing entry remains idempotent even above the visible cap.
        response = client.post(path, json={"player_api_id": 1800}, headers=desk.headers)
        assert response.status_code == 200
        assert ScoutWatchlistEntry.query.count() == 201


def test_nonplayer_follows_consume_visible_capacity(client, desk):
    hidden_ids = _seed_hidden_capacity(desk, "list", 50)
    db.session.add_all(
        Follow(
            list_id=desk.follow_list.id,
            kind="geo",
            selector={"countries": [f"Fixture country {index}"], "match": "playing_in"},
            label="Saved geography",
        )
        for index in range(49)
    )
    db.session.commit()
    path = f"/api/scout/lists/{desk.follow_list.id}/follows"
    response = client.post(path, json={"kind": "player", "selector": {"player_api_id": 1800}}, headers=desk.headers)
    assert response.status_code == 201
    body = client.get("/api/scout/lists", headers=desk.headers).get_json()["lists"][0]
    assert body["follow_count"] == len(body["follows"]) == 50
    response = client.post(
        path, json={"kind": "query", "selector": {"scout_args": {"position": "Attacker"}}}, headers=desk.headers
    )
    assert response.status_code == 409
    assert desk.follow_list.follows.count() == len(hidden_ids) + 50


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


@pytest.mark.parametrize(
    "change",
    [
        "minor",
        "unknown",
        "add_adult",
        "delete_tracked",
        "delete_shadow",
        "delete_local",
        "local_shadow_minor",
        "delete_journey",
        "journey_minor",
    ],
)
def test_paid_gol_replay_rechecks_adult_eligibility_before_returning_stored_answer(
    app, client, desk, monkeypatch, change
):
    from src.models.gol_credits import GolCreditLedger
    from src.routes.gol import gol_bp
    from src.services.gol_service import GolService

    app.register_blueprint(gol_bp, url_prefix="/api")
    monkeypatch.setenv("BILLING_ENABLED", "1")
    monkeypatch.setenv("GOL_FREE_ALLOWANCE", "10")
    pid = 1800
    model = TrackedPlayer
    if change == "delete_shadow":
        pid = 9900
        model = PlayerShadow
        db.session.add(PlayerShadow(player_api_id=pid, player_name="Stored adult", birth_date=date(2000, 1, 1)))
    elif change in {"delete_journey", "journey_minor"}:
        model = PlayerJourney
        pid = 9900
        db.session.add(PlayerJourney(player_api_id=pid, player_name="Stored adult", birth_date="2000-01-01"))
    elif change in {"delete_local", "local_shadow_minor"}:
        model = LocalPlayer
        local = LocalPlayer(
            display_name="Stored adult", status="approved", provenance="community", birth_date=date(2000, 1, 1)
        )
        db.session.add(local)
        db.session.flush()
        local.api_player_id = pid = -local.id
        if change == "local_shadow_minor":
            db.session.add(PlayerShadow(player_api_id=pid, player_name="Stored adult", birth_date=date(2000, 1, 1)))
    db.session.commit()
    from src.services.public_adult import gol_public_adult_ids

    assert gol_public_adult_ids([pid]) == {pid}
    # A model-free initial answer containing a currently eligible adult.
    monkeypatch.setattr(GolService, "__init__", lambda self, **kwargs: None)
    monkeypatch.setattr(
        GolService,
        "chat",
        lambda *args: iter(
            [
                # Prose-only answers have no reliable referenced-ID inventory.
                {"event": "token", "data": {"content": "Stored adult"}},
                {"event": "done", "data": {}},
            ]
        ),
    )
    payload = {"message": "List a player", "client_msg_id": "n3_replay_adult"}
    response = client.post("/api/gol/chat", json=payload, headers=desk.headers)
    assert response.status_code == 200
    assert "Stored adult" in response.get_data(as_text=True)
    replay = client.post("/api/gol/chat", json=payload, headers=desk.headers)
    assert replay.status_code == 200
    assert "Stored adult" in replay.get_data(as_text=True)
    if change.startswith("delete_"):
        column = model.api_player_id if model is LocalPlayer else model.player_api_id
        model.query.filter(column == pid).delete()
    elif change == "add_adult":
        db.session.add(
            TrackedPlayer(
                player_api_id=9900, player_name="Unrelated adult", team_id=desk.team.id, birth_date="2000-01-01"
            )
        )
    elif change == "local_shadow_minor":
        PlayerShadow.query.filter_by(player_api_id=pid).update({"birth_date": date(2015, 1, 1)})
    elif change == "journey_minor":
        PlayerJourney.query.filter_by(player_api_id=pid).update({"birth_date": "2015-01-01"})
    else:
        TrackedPlayer.query.filter_by(player_api_id=pid).update(
            {"birth_date": "2015-01-01" if change == "minor" else None}
        )
    db.session.commit()
    if change != "add_adult":
        assert gol_public_adult_ids([pid]) == set()
    replay = client.post("/api/gol/chat", json=payload, headers=desk.headers)
    assert replay.status_code == 409
    assert replay.get_json() == {"error": "client_msg_id_reused"}
    assert "Stored adult" not in replay.get_data(as_text=True)
    assert GolCreditLedger.query.filter_by(client_msg_id="n3_replay_adult", kind="debit").count() == 1


@pytest.mark.parametrize("additional,expected_queries", [(0, 8), (490, 8), (491, 8), (3490, 8)])
def test_gol_policy_revision_queries_are_batched(app, desk, additional, expected_queries):
    from src.services.public_adult import scout_adult_policy_revision

    db.session.add_all(
        TrackedPlayer(
            player_api_id=10000 + index, player_name="Batch adult", team_id=desk.team.id, birth_date="2000-01-01"
        )
        for index in range(additional)
    )
    db.session.commit()
    statements = []

    def count_query(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        revision = scout_adult_policy_revision()
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", count_query)
    assert len(revision) == 64
    assert len(statements) == expected_queries
    print(f"GOL policy revision: {10 + additional} known IDs, {len(statements)} SQL queries")


@pytest.mark.parametrize("include_local", [False, True])
def test_negative_shadow_dob_conflict_across_all_reads(app, client, desk, monkeypatch, include_local):
    from src.services.gol_dataframes import DataFrameCache
    from src.services.scout_digest_service import _player_state

    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "1" if include_local else "0")
    local = LocalPlayer(
        display_name="Conflicting local", status="approved", provenance="community", birth_date=date(2000, 1, 1)
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = pid = -local.id
    shadow = PlayerShadow(player_api_id=pid, player_name=local.display_name, birth_date=date(2000, 1, 1))
    db.session.add_all(
        [
            shadow,
            ScoutWatchlistEntry(user_account_id=desk.user.id, player_api_id=pid),
            Follow(
                list_id=desk.follow_list.id, kind="player", selector={"player_api_id": pid}, label=local.display_name
            ),
        ]
    )
    db.session.commit()
    assert public_adult_ids([pid]) == {pid}
    frames = {name: pd.DataFrame({"player_api_id": [pid]}) for name in ("players", "journey_entries", "fixture_stats")}
    assert _player_state(pid, {})["kind"] != "none"
    shadow.birth_date = date(2015, 1, 1)
    db.session.commit()
    assert public_adult_ids([pid]) == set()
    assert pid not in {row["player_id"] for row in client.get("/api/scout/players?per_page=100").get_json()["players"]}
    assert pid not in client.get("/api/scout/watchlist/ids", headers=desk.headers).get_json()["player_ids"]
    assert pid not in {
        row["player_api_id"] for row in client.get("/api/scout/watchlist", headers=desk.headers).get_json()["entries"]
    }
    body = client.get("/api/scout/lists", headers=desk.headers).get_json()["lists"][0]
    assert pid not in {row["selector"]["player_api_id"] for row in body["follows"]}
    assert _player_state(pid, {})["kind"] == "none"
    assert all(frame.empty for frame in DataFrameCache._adult_frames(app, frames).values())
    assert Follow.query.filter_by(kind="player").count() == len(desk.ids) + 1


@pytest.mark.parametrize("case", ["adult", "minor", "unknown", "invalid", "held", "suppressed", "bridge", "conflict"])
def test_gol_journey_only_identity_keeps_shared_vetoes(app, client, desk, monkeypatch, case):
    from src.models.funding import ClubProgram, ClubRosterMember, FundingLeague
    from src.models.player_suppression import PlayerSuppression
    from src.services.gol_dataframes import DataFrameCache
    from src.services.gol_player_lookup import GolPlayerLookup
    from src.services.public_adult import gol_public_adult_ids

    pid = 9900
    dob = {"minor": "2015-01-01", "unknown": None, "invalid": "unknown"}.get(case, "2000-01-01")
    db.session.add(PlayerJourney(player_api_id=pid, player_name="Journey-only fixture", birth_date=dob))
    if case == "held":
        league = FundingLeague(
            name="Hold fixture",
            country="JP",
            region="Fixture",
            level="recreational",
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="approved",
            admission_state="open",
        )
        db.session.add(league)
        db.session.flush()
        program = ClubProgram(
            funding_league_id=league.id,
            name="Hold fixture",
            legal_name="Hold fixture",
            slug="hold-fixture",
            country="JP",
            region="Fixture",
            platform_status="approved",
            emergency_hidden=True,
        )
        db.session.add(program)
        db.session.flush()
        db.session.add(ClubRosterMember(program_id=program.id, player_api_id=pid, added_by_user_id=desk.user.id))
    elif case == "suppressed":
        monkeypatch.delenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", raising=False)
        db.session.add(
            PlayerSuppression(
                player_api_id=pid,
                reason_code="player_request",
                requester_role="player",
                requester_contact="fixture@example.test",
                request_statement="Fixture",
                status="active",
            )
        )
    elif case == "bridge":
        db.session.add(
            LocalPlayer(
                display_name="Club bridge",
                api_player_id=pid,
                provenance="club",
                status="approved",
                birth_date=date(2000, 1, 1),
            )
        )
    elif case == "conflict":
        db.session.add(PlayerShadow(player_api_id=pid, player_name="Conflicting shadow", birth_date=date(2015, 1, 1)))
    db.session.commit()
    expected = {pid} if case == "adult" else set()
    assert gol_public_adult_ids([pid]) == expected
    assert public_adult_ids([pid]) == set()  # Phase 2/scout universe is unchanged.
    assert pid not in {row["player_id"] for row in client.get("/api/scout/players?per_page=100").get_json()["players"]}
    frames = {name: pd.DataFrame({"player_api_id": [pid]}) for name in ("journeys", "journey_entries", "fixture_stats")}
    assert all(set(frame["player_api_id"]) == expected for frame in DataFrameCache._adult_frames(app, frames).values())
    result = GolPlayerLookup(app)._find_existing("Journey-only fixture")
    assert (result is not None) == bool(expected)
    if result:
        assert result["source"] == "journey"


@pytest.fixture
def scale_desk(desk):
    db.session.add_all(
        TrackedPlayer(
            player_api_id=10000 + index,
            player_name="Scale adult",
            team_id=desk.team.id,
            birth_date="2000-01-01",
            nationality="England",
            position="Goalkeeper",
            is_active=True,
        )
        for index in range(3490)
    )
    db.session.commit()
    return desk


@pytest.mark.parametrize("endpoint,budget", [("players", 12), ("leaderboards", 25)])
def test_scout_scale_query_budget_and_request_freshness(client, scale_desk, endpoint, budget):
    statements = []

    def counted(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", counted)
    try:
        response = client.get(f"/api/scout/{endpoint}?limit=25")
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", counted)
    assert response.status_code == 200, response.get_json()
    assert len(statements) <= budget
    print(f"Scale {endpoint}: {len(statements)} SQL")
    # A new request must recheck a DOB correction.
    TrackedPlayer.query.filter_by(player_api_id=1800).update({"birth_date": "2015-01-01"})
    db.session.commit()
    body = client.get(f"/api/scout/{endpoint}?limit=25").get_json()
    rows = (
        body["players"] if endpoint == "players" else [row for board in body["leaderboards"].values() for row in board]
    )
    assert 1800 not in {row["player_id"] for row in rows}


@pytest.mark.parametrize(
    "kind,empty", [(kind, empty) for kind in ("query", "geo", "academy_club") for empty in (False, True)]
)
def test_dynamic_follow_scale_cache_and_query_budget(scale_desk, monkeypatch, kind, empty):
    from src.services import public_adult
    from src.services.follow_resolver import resolve_list
    from src.services.scout_digest_service import _player_state

    Follow.query.delete()
    selector = {
        "query": {"scout_args": {"nationality": "Absent" if empty else "England"}},
        "geo": {"countries": ["Absent" if empty else "England"], "match": "nationality"},
        "academy_club": {"team_id": 99999 if empty else scale_desk.team.id},
    }[kind]
    db.session.add_all(
        Follow(list_id=scale_desk.follow_list.id, kind=kind, selector=selector, label="Scale") for _ in range(5)
    )
    db.session.commit()
    calls, statements = [], []
    check = public_adult.public_adult_ids

    def checked(ids):
        ids = set(ids)
        calls.append(ids)
        return check(ids)

    def counted(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    monkeypatch.setattr(public_adult, "public_adult_ids", checked)
    cache = {}
    sa.event.listen(db.engine, "before_cursor_execute", counted)
    try:
        result = resolve_list(scale_desk.follow_list, eligibility_cache=cache)
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", counted)
    assert len(statements) <= 30
    assert len(calls) == (0 if empty else 1)
    assert bool(result) != empty
    print(f"Scale five {kind} follows empty={empty}: {len(statements)} SQL")
    resolve_list(scale_desk.follow_list, eligibility_cache=cache)
    if not empty:
        _player_state(result[0]["player_api_id"], cache)
    assert len(calls) == (0 if empty else 1)  # later lists/player states share the run cache
    resolve_list(scale_desk.follow_list, eligibility_cache={})
    assert len(calls) == (0 if empty else 2)  # the next run evaluates again


def test_mixed_dynamic_follows_share_eligibility_across_kinds_and_lists(scale_desk, monkeypatch):
    from src.services import public_adult
    from src.services.follow_resolver import resolve_list

    Follow.query.delete()
    db.session.add_all(
        Follow(list_id=scale_desk.follow_list.id, kind=kind, selector=selector, label="Mixed scale")
        for kind, selector in (
            ("query", {"scout_args": {"nationality": "England"}}),
            ("geo", {"countries": ["England"], "match": "nationality"}),
            ("academy_club", {"team_id": scale_desk.team.id}),
        )
    )
    db.session.commit()
    evaluations = Counter()
    check = public_adult.public_adult_ids

    def checked(ids):
        ids = set(ids)
        evaluations.update(ids)
        return check(ids)

    monkeypatch.setattr(public_adult, "public_adult_ids", checked)
    cache = {}
    resolve_list(scale_desk.follow_list, eligibility_cache=cache)
    assert evaluations == Counter(dict.fromkeys(scale_desk.ids | set(range(10000, 13490)), 1))
    resolve_list(scale_desk.follow_list, eligibility_cache=cache)
    assert all(count == 1 for count in evaluations.values())
    resolve_list(scale_desk.follow_list, eligibility_cache={})
    assert all(count == 2 for count in evaluations.values())
