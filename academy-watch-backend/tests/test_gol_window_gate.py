"""Window gate on GOL on-demand player creation (gol_player_lookup)."""

import os

import pytest
from flask import Flask
from src.models.journey import PlayerJourney
from src.models.league import League, Team, db
from src.models.tracked_player import TrackedPlayer
from src.utils.academy_window import academy_window_start, current_academy_season


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def lookup(app):
    os.environ.setdefault("API_USE_STUB_DATA", "true")
    from src.services.gol_player_lookup import GolPlayerLookup

    return GolPlayerLookup(app)


def _seed_team(api_id=100, name="Feyenoord"):
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    team = Team(team_id=api_id, name=name, country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(team)
    db.session.flush()
    return team


def _journey(player_api_id, *, last_seasons=None, birth_date=None):
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"GOL Player {player_api_id}",
        academy_club_ids=[100],
        academy_last_seasons=last_seasons or {},
        birth_date=birth_date,
        current_club_api_id=999,
        current_club_name="Elsewhere FC",
        current_level="First Team",
    )
    db.session.add(journey)
    db.session.flush()
    return journey


def _player_block(name="GOL Player", birth_date=None, age=None):
    return {
        "player": {
            "id": 1,
            "name": name,
            "photo": None,
            "nationality": "England",
            "age": age,
            "position": "Attacker",
            "birth": {"date": birth_date},
        },
        "statistics": [],
    }


class TestGolWindowGate:
    def test_out_of_window_player_not_created(self, app, lookup, monkeypatch):
        team = _seed_team()
        old = academy_window_start() - 1
        journey = _journey(500, last_seasons={"100": old}, birth_date="2001-09-26")
        db.session.commit()
        monkeypatch.setattr(
            "src.services.gol_player_lookup.classify_tracked_player",
            lambda **kwargs: ("first_team", 999, "Elsewhere FC"),
        )

        tracked = lookup._upsert_tracked_player(
            player_id=500, player_block=_player_block(birth_date="2001-09-26", age=24), journey=journey, team=team
        )

        assert tracked is None
        assert TrackedPlayer.query.filter_by(player_api_id=500).first() is None

    def test_in_window_player_created_with_evidence(self, app, lookup, monkeypatch):
        team = _seed_team()
        recent = current_academy_season() - 1
        journey = _journey(501, last_seasons={"100": recent}, birth_date="2006-01-01")
        db.session.commit()
        monkeypatch.setattr(
            "src.services.gol_player_lookup.classify_tracked_player",
            lambda **kwargs: ("first_team", 100, "Feyenoord"),
        )

        tracked = lookup._upsert_tracked_player(
            player_id=501, player_block=_player_block(birth_date="2006-01-01", age=20), journey=journey, team=team
        )

        assert tracked is not None
        assert tracked.is_active is True
        assert tracked.last_academy_season == recent

    def test_existing_row_refreshed_not_gated(self, app, lookup):
        team = _seed_team()
        old = academy_window_start() - 1
        journey = _journey(502, last_seasons={"100": old})
        existing = TrackedPlayer(
            player_api_id=502,
            player_name="GOL Player 502",
            team_id=team.id,
            status="sold",
            data_source="api-football",
            is_active=False,
        )
        db.session.add(existing)
        db.session.commit()

        tracked = lookup._upsert_tracked_player(
            player_id=502, player_block=_player_block(birth_date="2001-01-01", age=25), journey=journey, team=team
        )

        # Existing rows are refreshed (liveness governed by repair endpoints),
        # never force-created or force-deleted by GOL.
        assert tracked is not None
        assert tracked.id == existing.id
        assert tracked.is_active is False
        assert tracked.last_academy_season == old

    def test_existing_transfer_state_survives_fetch_failure(self, app, lookup):
        team = _seed_team()
        destination = Team(
            team_id=777,
            name="Buying Club",
            country="England",
            season=2025,
            league_id=team.league_id,
            is_active=True,
        )
        db.session.add(destination)
        db.session.flush()
        recent = current_academy_season() - 1
        journey = _journey(503, last_seasons={"100": recent})
        journey.current_club_api_id = team.team_id
        journey.current_club_name = team.name
        existing = TrackedPlayer(
            player_api_id=503,
            player_name="Known Sale",
            team_id=team.id,
            status="sold",
            current_club_api_id=777,
            current_club_name="Buying Club",
            current_club_db_id=destination.id,
            sale_fee="€ 20M",
            data_source="api-football",
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

        class _FailedTransfers:
            def get_player_transfers(self, player_id):
                raise RuntimeError("provider unavailable")

        lookup.api_client = _FailedTransfers()
        tracked = lookup._upsert_tracked_player(
            player_id=503,
            player_block=_player_block(birth_date="2005-01-01", age=21),
            journey=journey,
            team=team,
        )

        assert tracked.status == "sold"
        assert (tracked.current_club_api_id, tracked.current_club_name) == (777, "Buying Club")
        assert tracked.current_club_db_id == destination.id
        assert tracked.sale_fee == "€ 20M"

    def test_successful_sale_updates_club_fk_and_parent_fee(self, app, lookup):
        team = _seed_team()
        stale_destination = Team(
            team_id=200,
            name="Old Buying Club Row",
            country="England",
            season=2024,
            league_id=team.league_id,
            is_active=False,
        )
        destination = Team(
            team_id=200,
            name="Buying Club",
            country="England",
            season=2025,
            league_id=team.league_id,
            is_active=True,
        )
        db.session.add_all([stale_destination, destination])
        recent = current_academy_season() - 1
        journey = _journey(504, last_seasons={"100": recent})
        journey.current_club_api_id = team.team_id
        journey.current_club_name = team.name
        existing = TrackedPlayer(
            player_api_id=504,
            player_name="Fresh Sale",
            team_id=team.id,
            status="first_team",
            current_club_api_id=team.team_id,
            current_club_name=team.name,
            current_club_db_id=team.id,
            data_source="api-football",
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

        class _SuccessfulTransfers:
            def get_player_transfers(self, player_id):
                return [
                    {
                        "player": {"id": player_id},
                        "transfers": [
                            {
                                "date": "2025-07-01",
                                "type": "€ 12M",
                                "teams": {
                                    "out": {"id": 100, "name": "Feyenoord"},
                                    "in": {"id": 200, "name": "Buying Club"},
                                },
                            }
                        ],
                    }
                ]

        lookup.api_client = _SuccessfulTransfers()
        tracked = lookup._upsert_tracked_player(
            player_id=504,
            player_block=_player_block(birth_date="2005-01-01", age=21),
            journey=journey,
            team=team,
        )

        assert tracked.status == "sold"
        assert (tracked.current_club_api_id, tracked.current_club_name) == (200, "Buying Club")
        assert tracked.current_club_db_id == destination.id
        assert tracked.sale_fee == "€ 12M"

    def test_successful_empty_history_clears_stale_sale_fee(self, app, lookup):
        team = _seed_team()
        recent = current_academy_season() - 1
        journey = _journey(505, last_seasons={"100": recent})
        journey.current_club_api_id = team.team_id
        journey.current_club_name = team.name
        existing = TrackedPlayer(
            player_api_id=505,
            player_name="Returned Player",
            team_id=team.id,
            status="sold",
            current_club_api_id=777,
            current_club_name="Old Buyer",
            sale_fee="€ 20M",
            data_source="api-football",
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

        class _EmptyTransfers:
            def get_player_transfers(self, player_id):
                return []

        lookup.api_client = _EmptyTransfers()
        tracked = lookup._upsert_tracked_player(
            player_id=505,
            player_block=_player_block(birth_date="2005-01-01", age=21),
            journey=journey,
            team=team,
        )

        assert tracked.status == "first_team"
        assert (tracked.current_club_api_id, tracked.current_club_name) == (100, "Feyenoord")
        assert tracked.current_club_db_id == team.id
        assert tracked.sale_fee is None

    def test_ambiguous_nonempty_history_preserves_existing_transfer_state(self, app, lookup):
        team = _seed_team()
        destination = Team(
            team_id=777,
            name="Known Buyer",
            country="England",
            season=2025,
            league_id=team.league_id,
            is_active=True,
        )
        db.session.add(destination)
        db.session.flush()
        recent = current_academy_season() - 1
        journey = _journey(506, last_seasons={"100": recent})
        journey.current_club_api_id = team.team_id
        journey.current_club_name = team.name
        existing = TrackedPlayer(
            player_api_id=506,
            player_name="Ambiguous Player",
            team_id=team.id,
            status="sold",
            current_club_api_id=777,
            current_club_name="Known Buyer",
            current_club_db_id=destination.id,
            sale_fee="€ 20M",
            data_source="api-football",
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

        class _AmbiguousTransfers:
            def get_player_transfers(self, player_id):
                return [
                    {
                        "player": {"id": player_id},
                        "transfers": [
                            {
                                "date": "2025-07-01",
                                "type": "N/A",
                                "teams": {
                                    "out": {"id": 888, "name": "Unrelated"},
                                    "in": {"id": 999, "name": "Other"},
                                },
                            }
                        ],
                    }
                ]

        lookup.api_client = _AmbiguousTransfers()
        tracked = lookup._upsert_tracked_player(
            player_id=506,
            player_block=_player_block(birth_date="2005-01-01", age=21),
            journey=journey,
            team=team,
        )

        assert tracked.status == "sold"
        assert (tracked.current_club_api_id, tracked.current_club_name) == (777, "Known Buyer")
        assert tracked.current_club_db_id == destination.id
        assert tracked.sale_fee == "€ 20M"


def test_lookup_message_uses_persisted_tracked_club(app, lookup, monkeypatch):
    team = _seed_team()
    journey = _journey(507, last_seasons={"100": current_academy_season() - 1})
    journey.current_club_name = "Stale Journey Club"
    tracked = TrackedPlayer(
        player_api_id=507,
        player_name="Message Player",
        team_id=team.id,
        status="sold",
        current_club_api_id=200,
        current_club_name="Persisted Buyer",
        data_source="api-football",
        is_active=True,
    )
    db.session.add(tracked)
    db.session.commit()
    player_row = {"player": {"id": 507, "name": "Message Player"}, "statistics": []}

    monkeypatch.setattr(lookup, "_find_existing", lambda name: None)
    monkeypatch.setattr(lookup, "_is_rate_limited", lambda session_id: (False, ""))
    monkeypatch.setattr(lookup.api_client, "search_player_profiles", lambda name: [player_row])
    monkeypatch.setattr(lookup, "_pick_best_match", lambda rows, name, team_hint: player_row)
    monkeypatch.setattr(lookup, "_sync_journey", lambda player_id: journey)
    monkeypatch.setattr(lookup, "_resolve_parent_team", lambda row, team_hint: team)
    monkeypatch.setattr(lookup, "_upsert_tracked_player", lambda **kwargs: tracked)

    result = lookup.lookup("Message Player")

    assert result["found"] is True
    assert "Current club: Persisted Buyer." in result["message"]
    assert "Stale Journey Club" not in result["message"]


def test_lookup_message_uses_journey_club_for_parent_status(app, lookup, monkeypatch):
    team = _seed_team()
    journey = _journey(508, last_seasons={"100": current_academy_season() - 1})
    journey.current_club_name = "Feyenoord U21"
    tracked = TrackedPlayer(
        player_api_id=508,
        player_name="Academy Player",
        team_id=team.id,
        status="academy",
        current_club_api_id=None,
        current_club_name=None,
        data_source="api-football",
        is_active=True,
    )
    db.session.add(tracked)
    db.session.commit()
    player_row = {"player": {"id": 508, "name": "Academy Player"}, "statistics": []}

    monkeypatch.setattr(lookup, "_find_existing", lambda name: None)
    monkeypatch.setattr(lookup, "_is_rate_limited", lambda session_id: (False, ""))
    monkeypatch.setattr(lookup.api_client, "search_player_profiles", lambda name: [player_row])
    monkeypatch.setattr(lookup, "_pick_best_match", lambda rows, name, team_hint: player_row)
    monkeypatch.setattr(lookup, "_sync_journey", lambda player_id: journey)
    monkeypatch.setattr(lookup, "_resolve_parent_team", lambda row, team_hint: team)
    monkeypatch.setattr(lookup, "_upsert_tracked_player", lambda **kwargs: tracked)

    result = lookup.lookup("Academy Player")

    assert result["found"] is True
    assert "Current club: Feyenoord U21." in result["message"]
