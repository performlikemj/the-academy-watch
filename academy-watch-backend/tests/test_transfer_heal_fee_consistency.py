"""Hermetic transfer-heal regressions for parent-relative sale fees."""

from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, db
from src.models.season_rollup import LeagueSeasonConfig
from src.models.tracked_player import TrackedPlayer
from src.services import transfer_heal_service


def _transfer(transfer_date, transfer_type, out_id, out_name, in_id, in_name):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


class _FakeAPI:
    def __init__(self, raw_transfers_by_player, squad_player_ids):
        self.raw_transfers_by_player = raw_transfers_by_player
        self.squad_player_ids = set(squad_player_ids)

    def batch_get_player_transfers(self, player_ids):
        assert set(player_ids) == self.squad_player_ids
        return self.raw_transfers_by_player

    def get_team_players(self, club_id):
        assert club_id > 0
        return [{"player": {"id": player_id}} for player_id in self.squad_player_ids]


def _team(team_api_id, name):
    team = Team(
        team_id=team_api_id,
        name=name,
        country="Test Country",
        season=2025,
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _tracked_player(
    player_api_id,
    parent,
    *,
    journey_club_id,
    journey_club_name,
    journey_level,
    status,
    current_club_id,
    current_club_name,
    sale_fee,
):
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"Player {player_api_id}",
        current_club_api_id=journey_club_id,
        current_club_name=journey_club_name,
        current_level=journey_level,
        academy_club_ids=[parent.team_id],
        academy_last_seasons={str(parent.team_id): 2025},
    )
    db.session.add(journey)
    db.session.flush()
    tracked = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Player {player_api_id}",
        team_id=parent.id,
        journey_id=journey.id,
        status=status,
        current_club_api_id=current_club_id,
        current_club_name=current_club_name,
        sale_fee=sale_fee,
        data_source="journey-sync",
        last_academy_season=2025,
        is_active=True,
    )
    db.session.add(tracked)
    db.session.commit()
    return tracked


def _install_api(monkeypatch, raw_transfers_by_player, *player_api_ids):
    fake = _FakeAPI(raw_transfers_by_player, player_api_ids)
    monkeypatch.setattr(transfer_heal_service, "APIFootballClient", lambda: fake)
    return fake


def test_heal_writes_the_parent_departure_fee_not_a_later_resale(app, monkeypatch):
    parent = _team(49, "Chelsea")
    _team(34, "Newcastle")
    _team(529, "Barcelona")
    tracked = _tracked_player(
        884492,
        parent,
        journey_club_id=529,
        journey_club_name="Barcelona",
        journey_level="First Team",
        status="on_loan",
        current_club_id=529,
        current_club_name="Barcelona",
        sale_fee=None,
    )
    transfers = [
        _transfer("2025-07-01", "€ 55M", 34, "Newcastle", 529, "Barcelona"),
        _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
    ]
    _install_api(
        monkeypatch,
        {884492: [{"player": {"id": 884492}, "transfers": transfers}]},
        884492,
    )

    real_resolve = transfer_heal_service.resolve_transfer_state
    real_classify = transfer_heal_service.classify_tracked_player
    built_resolutions = []
    injected_resolutions = []

    def recording_resolve(*args, **kwargs):
        resolution = real_resolve(*args, **kwargs)
        built_resolutions.append(resolution)
        return resolution

    def recording_classify(*args, **kwargs):
        injected_resolutions.append(kwargs.get("transfer_resolution"))
        return real_classify(*args, **kwargs)

    monkeypatch.setattr(transfer_heal_service, "resolve_transfer_state", recording_resolve)
    monkeypatch.setattr(transfer_heal_service, "classify_tracked_player", recording_classify)

    result = transfer_heal_service.refresh_and_heal(
        resync_journeys=False,
        cascade_fixtures=False,
    )
    db.session.refresh(tracked)

    assert result["updated"] == 1
    assert tracked.status == "sold"
    assert tracked.current_club_api_id == 529
    assert tracked.current_club_name == "Barcelona"
    assert tracked.sale_fee == "€ 33M"
    assert len(built_resolutions) == 1
    assert injected_resolutions == built_resolutions


def test_heal_clears_a_stale_sale_fee_when_status_becomes_non_sold(app, monkeypatch):
    parent = _team(49, "Chelsea")
    _team(34, "Newcastle")
    tracked = _tracked_player(
        884493,
        parent,
        journey_club_id=49,
        journey_club_name="Chelsea",
        journey_level="First Team",
        status="sold",
        current_club_id=34,
        current_club_name="Newcastle",
        sale_fee="€ 33M",
    )
    _install_api(monkeypatch, {884493: []}, 884493)

    result = transfer_heal_service.refresh_and_heal(
        resync_journeys=False,
        cascade_fixtures=False,
    )
    db.session.refresh(tracked)

    assert result["updated"] == 1
    assert tracked.status == "first_team"
    assert tracked.current_club_api_id == 49
    assert tracked.current_club_name == "Chelsea"
    assert tracked.sale_fee is None


def test_heal_missing_transfer_prefetch_leaves_transfer_fields_untouched(app, monkeypatch):
    parent = _team(49, "Chelsea")
    _team(34, "Newcastle")
    tracked = _tracked_player(
        884494,
        parent,
        journey_club_id=49,
        journey_club_name="Chelsea",
        journey_level="First Team",
        status="sold",
        current_club_id=34,
        current_club_name="Newcastle",
        sale_fee="€ 33M",
    )
    _install_api(monkeypatch, {}, 884494)

    def unexpected_resolution(*args, **kwargs):
        raise AssertionError("missing transfer prefetch must skip resolution")

    monkeypatch.setattr(
        transfer_heal_service,
        "resolve_transfer_state",
        unexpected_resolution,
    )

    result = transfer_heal_service.refresh_and_heal(
        resync_journeys=False,
        cascade_fixtures=False,
    )
    db.session.refresh(tracked)

    assert result["updated"] == 0
    assert result["skipped_by_failed_prefetch"] == 1
    assert tracked.status == "sold"
    assert tracked.current_club_api_id == 34
    assert tracked.current_club_name == "Newcastle"
    assert tracked.sale_fee == "€ 33M"


def test_heal_uses_calendar_year_boundary_for_active_loan(app, monkeypatch):
    parent = _team(49, "Chelsea")
    _team(44, "Burnley")
    tracked = _tracked_player(
        884496,
        parent,
        journey_club_id=44,
        journey_club_name="Burnley",
        journey_level="First Team",
        status="left",
        current_club_id=44,
        current_club_name="Burnley",
        sale_fee=None,
    )
    db.session.add(
        LeagueSeasonConfig(
            league_api_id=999,
            season_type="calendar",
            rollover_month=1,
        )
    )
    db.session.add(
        PlayerJourneyEntry(
            journey_id=tracked.journey_id,
            player_api_id=884496,
            season=2026,
            club_api_id=44,
            club_name="Burnley",
            league_api_id=999,
            league_name="Calendar League",
            level="First Team",
            entry_type="first_team",
            is_youth=False,
            is_international=False,
            appearances=2,
            minutes=180,
            sort_priority=100,
        )
    )
    db.session.commit()
    transfers = [_transfer("2026-02-01", "Loan", 49, "Chelsea", 44, "Burnley")]
    _install_api(
        monkeypatch,
        {884496: [{"player": {"id": 884496}, "transfers": transfers}]},
        884496,
    )

    result = transfer_heal_service.refresh_and_heal(
        resync_journeys=False,
        cascade_fixtures=False,
    )
    db.session.refresh(tracked)

    assert result["updated"] == 1
    assert tracked.status == "on_loan"
    assert tracked.current_club_api_id == 44
    assert tracked.current_club_name == "Burnley"
