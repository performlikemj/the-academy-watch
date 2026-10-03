"""One mixed-source contract across every Scout/iOS number endpoint."""

import csv
import io
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event, literal, select
from src.auth import issue_user_token
from src.models.follow import Follow, FollowList, PlayerShadow, PlayerShadowStats
from src.models.funding import ClubProgram, FundingLeague
from src.models.league import PlayerStatsCache, Team, UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import LocalPlayer, PlayerClubAffiliation, PlayerShowcaseMedia, PlayerShowcaseProfile
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.services import season_rollup_service as rollup

SEASON = 2025


def seed_personas():
    """Fictional staging-modelled adults, plus all mixed/ambiguous shapes."""
    user = UserAccount(email="pc2-scout@example.test", display_name="Corinne", display_name_lower="corinne")
    db.session.add(user)
    db.session.flush()
    league = FundingLeague(
        name="Wendleshire",
        country="England",
        region="Europe",
        level="recreational",
        gender_program="both",
        season_calendar="aug_may",
        data_tier="self_reported",
    )
    db.session.add(league)
    db.session.flush()
    club = ClubProgram(
        name="Quillmere Athletic",
        funding_league_id=league.id,
        country="England",
        region="Wendleshire",
        legal_name="Quillmere Athletic",
        slug="pc2-quillmere",
    )
    db.session.add(club)
    db.session.flush()
    follow_list = FollowList(user_account_id=user.id, name="PC2 proof")
    db.session.add(follow_list)
    db.session.flush()
    ids = {}
    for name, position in [
        ("Kofi Asante-Reid", "Defender"),
        ("Reuben Castellane", "Midfielder"),
        ("Emeka Nwosu-Clarke", "Defender"),
        ("Ellis Brannock", "Goalkeeper"),
        ("Tobi Olawale", "Defender"),
        ("Mixed fixture", "Midfielder"),
    ]:
        local = LocalPlayer(
            display_name=name,
            normalized_name=name.lower(),
            status="approved",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            position=position,
        )
        db.session.add(local)
        db.session.flush()
        local.api_player_id = -local.id
        ids[name] = -local.id
        db.session.add_all(
            [
                PlayerShadow(
                    player_api_id=-local.id,
                    player_name=name,
                    position=position,
                    birth_date=date(2000, 1, 1),
                    is_active=True,
                    current_club_name=club.name,
                ),
                ScoutWatchlistEntry(user_account_id=user.id, player_api_id=-local.id),
                Follow(list_id=follow_list.id, kind="player", selector={"player_api_id": -local.id}),
            ]
        )

    def entry(name, day, minutes=90, source="self", **kw):
        row = PlayerMatchEntry(
            player_api_id=ids[name],
            season=SEASON,
            match_date=date(SEASON, 9, day),
            source=source,
            status="club_confirmed" if source == "club" else "self_reported",
            reported_by_user_id=user.id,
            club_program_id=club.id if source == "club" else None,
            opponent=f"Opponent {day}",
            competition="Wendle Senior League",
            home_away="home",
            minutes=minutes,
            goals=0,
            assists=0,
            yellows=0,
            reds=0,
        )
        for key, value in kw.items():
            setattr(row, key, value)
        db.session.add(row)

    for name in ("Kofi Asante-Reid", "Mixed fixture"):
        entry(name, 1, source="club")
        entry(name, 1)
        entry(name, 2, source="club", minutes=74, yellows=1)
        entry(name, 2)
        entry(name, 3, assists=1)
    entry("Mixed fixture", 4, source="club", minutes=45)
    entry("Mixed fixture", 4, source="club", minutes=60, opponent="opponent 4")
    entry("Mixed fixture", 5, status="disputed", goals=20)
    for day in range(1, 23):
        minutes = 0 if day in (21, 22) else 90 if day <= 14 else 60 if day <= 19 else 50
        entry(
            "Reuben Castellane",
            day,
            minutes=minutes,
            source="club" if day <= 15 else "self",
            goals=int(day in (2, 12)),
            assists=int(day in (3, 5, 9, 16, 20)),
            yellows=int(day in (3, 8, 12, 19)),
        )
        if day <= 9:
            entry(
                "Reuben Castellane",
                day,
                minutes=minutes,
                goals=int(day in (2, 12)),
                assists=int(day in (3, 5, 9, 16, 20)),
                yellows=int(day in (3, 8, 12, 19)),
            )
    entry("Emeka Nwosu-Clarke", 1, minutes=45)
    entry("Emeka Nwosu-Clarke", 1, minutes=45, opponent="opponent 1")
    entry("Emeka Nwosu-Clarke", 2)
    for day in range(1, 7):
        entry(
            "Ellis Brannock",
            day,
            source="club" if day <= 5 else "self",
            saves={1: 6, 2: 4, 3: 3, 4: 5, 6: 4}.get(day),
            goals_conceded={1: 2, 2: 1, 3: 0, 4: 1, 6: 0}.get(day),
        )
    kofi_local = -ids["Kofi Asante-Reid"]
    db.session.add_all(
        [
            PlayerShowcaseProfile(
                local_player_id=kofi_local,
                status="approved",
                bio="<b>Right-back</b>\n" + "Football " * 40,
                agent_contact_email="PRIVATE@example.test",
            ),
            PlayerShowcaseMedia(
                local_player_id=kofi_local,
                blob_path="pc2/approved.jpg",
                public_url="pc2/approved.jpg",
                status="approved",
                is_primary=True,
            ),
            PlayerShowcaseMedia(
                local_player_id=kofi_local,
                blob_path="pc2/pending.jpg",
                public_url="pc2/pending.jpg",
                status="pending",
                is_primary=True,
            ),
            PlayerClubAffiliation(local_player_id=kofi_local, status="club_confirmed"),
        ]
    )
    parent = Team(team_id=9001, name="Provider academy", country="England", season=SEASON)
    db.session.add(parent)
    db.session.flush()
    ids["Provider"] = 91001
    db.session.add(
        TrackedPlayer(
            player_api_id=91001,
            team_id=parent.id,
            player_name="Provider",
            birth_date="2000-01-01",
            position="Midfielder",
            is_active=True,
            status="first_team",
        )
    )
    fx = Fixture(
        fixture_id_api=99001,
        season=SEASON,
        date_utc=datetime(SEASON, 9, 1, tzinfo=UTC),
        home_team_api_id=9001,
        away_team_api_id=9002,
        competition_name="Senior League",
    )
    db.session.add(fx)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fx.id,
            player_api_id=91001,
            team_api_id=9001,
            minutes=90,
            goals=2,
            assists=1,
            yellows=0,
            reds=0,
            position="M",
        )
    )
    entry("Provider", 2, minutes=120, goals=20)
    db.session.add_all(
        [
            ScoutWatchlistEntry(user_account_id=user.id, player_api_id=91001),
            Follow(list_id=follow_list.id, kind="player", selector={"player_api_id": 91001}),
        ]
    )
    db.session.flush()
    # Intentionally old whole-source cells: reconstruct pre-PC2 totals.
    for player_id in ids.values():
        now = datetime.now(UTC)
        cells = [c for feeder in rollup._FEEDERS for c in feeder(player_id, SEASON, db.session, now)]
        for cell in cells:
            db.session.add(PlayerSeasonCell(**{k: v for k, v in cell.items() if not k.startswith("_")}))
        for total in rollup._resolve_totals(cells, now):
            db.session.add(PlayerSeasonTotal(**total))
    db.session.commit()
    return ids, user.id, follow_list.id


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "1")
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "1")
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout,season_stats,player_stats,teams")
    from src.routes.api import api_bp
    from src.routes.player_matches import player_matches_bp
    from src.routes.players import players_bp
    from src.routes.scout import scout_bp
    from src.routes.teams import teams_bp

    uri = os.environ.get("PC2_TEST_DATABASE_URL", "sqlite:///:memory:")
    if uri != "sqlite:///:memory:":
        from sqlalchemy.engine import make_url

        url = make_url(uri)
        assert url.database == "aw_pc2" and url.host in {None, "localhost", "127.0.0.1"}
    application = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / "src/templates"))
    application.config.update(
        TESTING=True,
        SECRET_KEY="pc2-test",
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(application)
    from src.extensions import limiter

    limiter.init_app(application)
    if limiter._storage is not None:
        limiter.reset()
    for bp in (player_matches_bp, players_bp, scout_bp, api_bp, teams_bp):
        application.register_blueprint(bp, url_prefix="/api")
    with application.app_context():
        if uri != "sqlite:///:memory:":
            db.drop_all()  # exclusively owned aw_pc2; remove standalone proof seed
        db.create_all()
        yield application
        if limiter._storage is not None:
            limiter.reset()
        db.session.remove()
        db.drop_all()


def _numbers(payload):
    return tuple(
        payload.get(k)
        for k in ("appearances", "minutes_played", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
    )


def surfaces(client, headers, list_id):
    def get(path):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.get_data(as_text=True))
        return response.get_json()

    desk = get(f"/api/scout/players?season={SEASON}&per_page=50")
    watch = get(f"/api/scout/watchlist?season={SEASON}")
    saved = get(f"/api/scout/lists/{list_id}/resolve?season={SEASON}&limit=50")
    boards = get(f"/api/scout/leaderboards?season={SEASON}&limit=50")
    self_boards = get(f"/api/scout/leaderboards?season={SEASON}&source=self&limit=25")
    mixed_boards = get(f"/api/scout/leaderboards?season={SEASON}&source=mixed&limit=25")
    boards["leaderboards"].update({"mixed_" + k: v for k, v in mixed_boards["leaderboards"].items()})
    boards["leaderboards"].update({"self_" + k: v for k, v in self_boards["leaderboards"].items()})
    export = client.get(f"/api/scout/export.csv?season={SEASON}", headers=headers)
    assert export.status_code == 200
    return {
        "desk/cards/iOS desk": {p["player_id"]: _numbers(p) for p in desk["players"]},
        "watchlist/iOS watchlist": {p["player_api_id"]: _numbers(p["player"]) for p in watch["entries"]},
        "saved lists/iOS lists": {p["player_api_id"]: _numbers(p) for p in saved["players"]},
        "leaderboards/iOS boards": {
            p["player_id"]: _numbers(p) for board in boards["leaderboards"].values() for p in board
        },
        "CSV": {
            int(p["player_id"]): tuple(
                int(p[k]) if p[k] else None
                for k in ("appearances", "minutes", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
            )
            for p in csv.DictReader(io.StringIO(export.get_data(as_text=True)))
        },
    }, desk["players"]


@pytest.mark.parametrize("provider_kind", ["fixtures", "cache"])
@pytest.mark.parametrize("provider_rollup", [True, False])
@pytest.mark.parametrize("flags", ["", "scout,season_stats,player_stats,teams"])
@pytest.mark.parametrize("frozen", ["0", "1"])
def test_one_mixed_fixture_equal_on_every_surface_before_and_after_rebuild(
    app, monkeypatch, flags, frozen, provider_rollup, provider_kind
):
    ids, _user_id, list_id = seed_personas()
    # Positive-ID roster member with the same mixed shape as the community Kofi.
    mirror = 93001
    team = Team.query.filter_by(team_id=9001).one()
    db.session.add(
        TrackedPlayer(
            player_api_id=mirror,
            team_id=team.id,
            player_name="Tracked Kofi",
            birth_date="2000-01-01",
            is_active=True,
            data_source="manual",
        )
    )
    for row in PlayerMatchEntry.query.filter_by(player_api_id=ids["Kofi Asante-Reid"]).all():
        values = {
            c.name: getattr(row, c.name)
            for c in PlayerMatchEntry.__table__.columns
            if c.name not in {"id", "player_api_id"}
        }
        db.session.add(PlayerMatchEntry(**values, player_api_id=mirror))
    db.session.flush()
    now = datetime.now(UTC)
    cells = [c for feeder in rollup._FEEDERS for c in feeder(mirror, SEASON, db.session, now)]
    db.session.add_all([PlayerSeasonTotal(**t) for t in rollup._resolve_totals(cells, now)])
    db.session.add_all(
        [
            ScoutWatchlistEntry(user_account_id=_user_id, player_api_id=mirror),
            Follow(list_id=list_id, kind="player", selector={"player_api_id": mirror}),
        ]
    )
    ids["Tracked Kofi"] = mirror
    db.session.commit()
    monkeypatch.setattr("src.utils.academy_classifier.is_academy_product", lambda *a, **k: True)
    if provider_kind == "cache":
        provider = ids["Provider"]
        FixturePlayerStats.query.filter_by(player_api_id=provider).delete()
        PlayerSeasonTotal.query.filter_by(player_api_id=provider).delete()
        PlayerSeasonCell.query.filter_by(player_api_id=provider).delete()
        TrackedPlayer.query.filter_by(player_api_id=provider).one().data_depth = "events_only"
        db.session.add(
            PlayerStatsCache(
                player_api_id=provider,
                team_api_id=9001,
                season=SEASON,
                appearances=4,
                minutes_played=360,
                goals=3,
                assists=2,
                yellows=1,
            )
        )
        db.session.flush()
        rollup.refresh_player(provider, SEASON)
        db.session.commit()
    if not provider_rollup:
        PlayerSeasonTotal.query.filter_by(player_api_id=ids["Provider"]).delete()
        db.session.commit()
    headers = {"Authorization": "Bearer " + issue_user_token("pc2-scout@example.test")["token"]}
    client = app.test_client()
    monkeypatch.setenv("SEASON_ROLLUP_READS", flags)
    monkeypatch.setenv("API_FOOTBALL_FROZEN", frozen)
    expected = {}
    for name, player_id in ids.items():
        if name == "Provider":
            expected[player_id] = (
                (1, 90, 2, 1, 0, 0, None, None) if provider_kind == "fixtures" else (4, 360, 3, 2, 1, 0, 0, None)
            )
        else:
            result = client.get(f"/api/players/{player_id}/matches?view=lines&season={SEASON}")
            assert result.status_code == 200
            seasons = result.get_json()["seasons"]
            t = seasons[0]["totals"] if seasons else {"appearances": 0, "minutes": 0, "goals": 0, "assists": 0}
            expected[player_id] = tuple(
                t.get(k)
                for k in ("appearances", "minutes", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
            )
    assert expected[ids["Mixed fixture"]] == (5, 359, 0, 1, 1, 0, None, None)
    assert expected[ids["Kofi Asante-Reid"]] == (3, 254, 0, 1, 1, 0, None, None)
    assert expected[ids["Reuben Castellane"]] == (20, 1610, 2, 5, 4, 0, None, None)
    proof = {}
    for stage in ("old cells", "rebuilt"):
        got, rows = surfaces(client, headers, list_id)
        for surface, numbers in got.items():
            for player_id in ids.values():
                if surface.startswith("leaderboards") and player_id == ids["Tobi Olawale"]:
                    continue  # no-stat rows are not ranking candidates
                if player_id == ids["Tobi Olawale"]:
                    assert all(value in {None, 0} for value in numbers[player_id])
                    continue
                assert numbers.get(player_id) == expected[player_id], (
                    stage,
                    surface,
                    player_id,
                    numbers.get(player_id),
                    expected[player_id],
                )
        for path in (
            f"/api/teams/{team.id}/loans",
            f"/api/teams/{team.id}/players",
            f"/api/teams/{team.id}/loans?season={SEASON}",
            f"/api/teams/{team.id}/loans/season/{SEASON}",
            f"/api/teams/{team.id}/players?season={SEASON}",
        ):
            response = client.get(path)
            assert response.status_code == 200, (path, response.json)
            payload = response.json
            roster = payload if isinstance(payload, list) else payload.get("loans", payload.get("players", []))
            numbers = {p["player_id"]: _numbers(p) for p in roster}
            assert numbers[mirror] == expected[mirror], (stage, path, numbers)
            assert numbers[ids["Provider"]] == expected[ids["Provider"]], (stage, path, numbers)
            got[path] = numbers
        from src.services import scout_digest_service as digest

        user = db.session.get(UserAccount, _user_id)
        entries = ScoutWatchlistEntry.query.filter_by(user_account_id=_user_id).all()
        cache = {}
        digest._prime_number_totals(list(ids.values()), cache)
        watch_updates = [digest._entry_update(e, cache) for e in entries]
        groups, list_updates = digest._build_list_updates(user, [db.session.get(FollowList, list_id)], {})
        for label, updates, rendered in (
            ("watchlist digest", watch_updates, digest._render_digest(user, watch_updates)),
            ("saved-list digest", list_updates, digest._render_digest(user, [], groups, list_updates)),
        ):
            for update in updates:
                pid = update["entry"].player_api_id
                if pid == ids["Tobi Olawale"]:
                    continue
                snap = update["snapshot"]
                assert (snap["appearances"], snap["minutes_played"], snap["goals"], snap["assists"]) == expected[pid][
                    :4
                ]
                assert snap["season"] == SEASON
                assert snap["provenance"]["primary_source"]
                assert update["card"]["season_line"] in rendered["html"]
                assert update["card"]["season_line"] in rendered["text"]
            got[label] = {
                u["entry"].player_api_id: (
                    u["snapshot"]["appearances"],
                    u["snapshot"]["minutes_played"],
                    u["snapshot"]["goals"],
                    u["snapshot"]["assists"],
                )
                for u in updates
            }
        compare_rows = []
        player_ids = list(ids.values())
        for offset in range(0, len(player_ids), 4):
            joined = ",".join(map(str, player_ids[offset : offset + 4]))
            response = client.get(f"/api/scout/compare?ids={joined}&season={SEASON}")
            assert response.status_code == 200, response.json
            compare_rows.extend(response.json["players"])
        for player in compare_rows:
            player_id = player["profile"]["player_id"]
            if player_id == ids["Tobi Olawale"]:
                assert all(value in {None, 0} for value in _numbers(player["totals"]))
            else:
                assert _numbers(player["totals"]) == expected[player_id]
        for name, player_id in ids.items():
            if name == "Tobi Olawale":
                continue
            season = client.get(f"/api/players/{player_id}/season-stats?season={SEASON}").get_json()
            assert (
                tuple(
                    season.get(k)
                    for k in (
                        "appearances",
                        "minutes",
                        "goals",
                        "assists",
                        "yellows",
                        "reds",
                        "saves",
                        "goals_conceded",
                    )
                )
                == expected[player_id]
            ), (name, season)
        if "player_stats" in flags:
            summaries = {}
            for name, pid in ids.items():
                response = client.get(f"/api/players/{pid}/stats?season={SEASON}")
                assert response.status_code == 200, response.json
                summary = response.json["summary"]
                summaries[pid] = tuple(
                    summary.get(k)
                    for k in (
                        "appearances",
                        "minutes",
                        "goals",
                        "assists",
                        "yellows",
                        "reds",
                        "saves",
                        "goals_conceded",
                    )
                )
                if name != "Tobi Olawale":
                    assert summaries[pid] == expected[pid], (stage, name, "player-stats", response.json)
            got["player-stats/iOS summary"] = summaries
        kofi = next(p for p in rows if p["player_id"] == ids["Kofi Asante-Reid"])
        assert kofi["provenance"]["primary_source"] == "matches"
        provider = next(p for p in rows if p["player_id"] == ids["Provider"])
        assert provider["provenance"]["primary_source"] == provider_kind
        assert kofi["club_confirmed"] is True
        assert kofi["approved_photo_url"].endswith("/pc2/approved.jpg")
        assert len(kofi["bio_line"]) <= 160 and "<" not in kofi["bio_line"] and "\n" not in kofi["bio_line"]
        assert "PRIVATE" not in json.dumps(rows) and "pending.jpg" not in json.dumps(rows)
        proof[stage] = {
            surface: {name: list(numbers.get(player_id, ())) for name, player_id in ids.items()}
            for surface, numbers in got.items()
        }
        proof[stage]["compare/iOS compare"] = {
            p["profile"]["player_name"]: list(_numbers(p["totals"])) for p in compare_rows
        }
        for player_id in ids.values():
            rollup.refresh_player(player_id, SEASON)
        db.session.commit()
    if os.environ.get("PC2_PROOF_PATH") and provider_kind == "fixtures" and provider_rollup and flags and frozen == "1":
        Path(os.environ["PC2_PROOF_PATH"]).write_text(json.dumps(proof, indent=2))


def test_50_row_query_budget_is_constant(app, monkeypatch):
    from src.routes import scout

    ids, _user, _list = seed_personas()
    for index in range(44):
        local = LocalPlayer(
            display_name=f"Adult {index}",
            normalized_name=f"adult {index}",
            status="approved",
            birth_date=date(2000, 1, 1),
        )
        db.session.add(local)
        db.session.flush()
        local.api_player_id = -local.id
        db.session.add(
            PlayerShadow(
                player_api_id=-local.id, player_name=local.display_name, birth_date=date(2000, 1, 1), is_active=True
            )
        )
    db.session.commit()
    counts = {}
    statements = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        with monkeypatch.context() as baseline:
            baseline.setattr(
                scout,
                "scout_totals_projection",
                lambda identity, season: select(
                    *PlayerSeasonTotal.__table__.c, literal(False).label("pc2_override")
                ).subquery("baseline_totals"),
            )
            baseline.setattr(scout, "attach_card_fields", lambda players: None)
            statements.clear()
            response = app.test_client().get(f"/api/scout/players?per_page=50&season={SEASON}")
            assert response.status_code == 200
            counts["before50"] = len(statements)
        for size in (1, 50):
            statements.clear()
            response = app.test_client().get(f"/api/scout/players?per_page={size}&season={SEASON}")
            assert response.status_code == 200
            assert len(response.get_json()["players"]) == size
            counts[f"after{size}"] = len(statements)
        assert counts["after50"] == counts["after1"]
        assert counts["after50"] <= counts["before50"] + 11
        print("PC2 query counts", counts)
        if os.environ.get("PC2_QUERY_PROOF_PATH"):
            Path(os.environ["PC2_QUERY_PROOF_PATH"]).write_text(json.dumps(counts, indent=2))
    finally:
        event.remove(db.engine, "before_cursor_execute", record)


def test_rebuild_dry_run_resume_idempotence_and_rollback(app, tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts/rebuild_reported_match_totals.py"
    spec = importlib.util.spec_from_file_location("pc2_rebuild", path)
    rebuild = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rebuild)
    ids, _user, _list = seed_personas()
    PlayerSeasonTotal.query.filter_by(player_api_id=ids["Kofi Asante-Reid"]).one().avg_rating = 7.25
    db.session.commit()
    before = {player_id: rebuild.snapshot(db.session, player_id) for player_id in ids.values()}
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        dry = rebuild.run(db.session, dry_run=True, limit=100, after=-(2**31), delay=0)
        assert dry["players_scanned"] == 6
        assert dry["players_changed"] == 5
        assert dry["seasons_changed"] == 5
        assert all(statement.lstrip().upper().startswith(("SELECT", "WITH")) for statement in statements)
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    checkpoint, undo = tmp_path / "cursor.json", tmp_path / "undo.jsonl"
    first = rebuild.run(db.session, dry_run=False, limit=2, after=-(2**31), delay=0, checkpoint=checkpoint, undo=undo)
    assert first["players_scanned"] == 2
    remaining = rebuild.run(
        db.session,
        dry_run=False,
        limit=100,
        after=json.loads(checkpoint.read_text())["after"],
        delay=0,
        checkpoint=checkpoint,
        undo=undo,
    )
    assert remaining["players_scanned"] == 4
    repeated = rebuild.run(db.session, dry_run=True, limit=100, after=-(2**31), delay=0)
    assert repeated["players_changed"] == 0
    assert rebuild.restore(db.session, undo) == 5
    for player_id in ids.values():
        after = rebuild.snapshot(db.session, player_id)
        for table in before[player_id]:
            assert rebuild.comparable(after[table]) == rebuild.comparable(before[player_id][table])


@pytest.mark.parametrize("flags", ["", "scout,season_stats"])
def test_old_reported_cells_without_source_lines_do_not_reappear(app, monkeypatch, flags):
    ids, _user, list_id = seed_personas()
    player_id = ids["Kofi Asante-Reid"]
    PlayerMatchEntry.query.filter_by(player_api_id=player_id).delete()
    db.session.commit()  # deliberately retain old cells, as a pre-rebuild orphan
    monkeypatch.setenv("SEASON_ROLLUP_READS", flags)
    headers = {"Authorization": "Bearer " + issue_user_token("pc2-scout@example.test")["token"]}
    got, _rows = surfaces(app.test_client(), headers, list_id)
    for surface, values in got.items():
        if surface.startswith("leaderboards"):
            assert player_id not in values
        else:
            assert all(value in {None, 0} for value in values[player_id]), (surface, values[player_id])
    season = app.test_client().get(f"/api/players/{player_id}/season-stats?season={SEASON}").get_json()
    assert (season["appearances"], season["minutes"], season["goals"]) == (0, 0, 0)
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player_id).one().minutes == 164  # reads do not write


@pytest.mark.parametrize("frozen", ["0", "1"])
def test_saved_worldwide_shadow_uses_own_latest_season_without_joining_desk(app, monkeypatch, frozen):
    monkeypatch.setenv("API_FOOTBALL_FROZEN", frozen)
    _ids, user_id, list_id = seed_personas()
    player_id = 91002
    db.session.add(
        PlayerShadow(
            player_api_id=player_id, player_name="Worldwide adult", birth_date=date(2000, 1, 1), is_active=True
        )
    )
    db.session.add_all(
        [
            PlayerShadowStats(
                player_api_id=player_id, team_api_id=9002, season=2024, appearances=2, minutes=180, goals=1, assists=0
            ),
            PlayerShadowStats(
                player_api_id=player_id, team_api_id=9002, season=2025, appearances=9, minutes=900, goals=3, assists=1
            ),
            Follow(list_id=list_id, kind="player", selector={"player_api_id": player_id}),
        ]
    )
    db.session.commit()
    headers = {"Authorization": "Bearer " + issue_user_token("pc2-scout@example.test")["token"]}
    client = app.test_client()
    for pick, expected in (("", (9, 900, 3, 1)), ("&season=2024", (2, 180, 1, 0))):
        response = client.get(f"/api/scout/lists/{list_id}/resolve?limit=50{pick}", headers=headers)
        assert response.status_code == 200, response.json
        player = next(p for p in response.json["players"] if p["player_api_id"] == player_id)
        assert _numbers(player)[:4] == expected
        assert player["provenance"]["primary_source"] == "shadow"
        stats = client.get(f"/api/players/{player_id}/season-stats?season={2024 if pick else 2025}")
        assert stats.status_code == 200, stats.json
        assert tuple(
            stats.json[k]
            for k in ("appearances", "minutes", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
        ) == _numbers(player)
    desk = client.get(f"/api/scout/players?season={SEASON}&per_page=50")
    assert player_id not in {row["player_id"] for row in desk.json["players"]}


def test_removing_last_report_preserves_provider_cache(app):
    ids, _user, _list = seed_personas()
    player_id = ids["Provider"]
    FixturePlayerStats.query.filter_by(player_api_id=player_id).delete()
    db.session.add(
        PlayerStatsCache(
            player_api_id=player_id,
            team_api_id=9001,
            season=SEASON,
            appearances=4,
            minutes_played=360,
            goals=3,
            assists=2,
        )
    )
    rollup.refresh_player(player_id, SEASON)
    db.session.commit()
    PlayerMatchEntry.query.filter_by(player_api_id=player_id).delete()
    rollup.refresh_player(player_id, SEASON)
    db.session.commit()
    total = PlayerSeasonTotal.query.filter_by(player_api_id=player_id).one()
    assert (total.primary_source, total.appearances, total.minutes, total.goals) == ("cache", 4, 360, 3)
