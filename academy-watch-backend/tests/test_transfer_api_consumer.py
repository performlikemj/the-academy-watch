"""Focused regressions for transfer consumers in API routes and classifier."""

import src.routes.api as api_routes
from src.models.league import Team, db
from src.models.tracked_player import TrackedPlayer
from src.routes.api import _academy_seed_transfer_fallback_eligible, _run_batch_fixture_sync
from src.services.transfer_resolver import resolve_transfer_state as real_resolve_transfer_state
from src.utils.academy_classifier import classify_tracked_player


def _transfer(transfer_date, transfer_type, out_id, out_name, in_id, in_name):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


def _payload(player_id, transfers):
    return [{"player": {"id": player_id}, "transfers": transfers}]


def _parent_team(team_id=49, name="Chelsea"):
    team = Team(
        team_id=team_id,
        name=name,
        country="England",
        season=2025,
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


class _BatchAPI:
    def __init__(self, player_id, transfers, *, profile=None):
        self.player_id = player_id
        self.transfers = transfers
        self.profile = profile
        self.fixture_team_ids = []
        self.transfer_calls = 0

    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        self.transfer_calls += 1
        return _payload(player_id, self.transfers)

    def get_player_by_id(self, player_id, season):
        assert player_id == self.player_id
        assert season == 2025
        if self.profile is None:
            raise AssertionError("known current club must not trigger profile discovery")
        return self.profile

    def get_fixtures_for_team_cached(self, team_id, season, start, end):
        self.fixture_team_ids.append(team_id)
        return []


def test_batch_fee_uses_parent_departure_even_after_later_resale(app, monkeypatch):
    """A known current club must not skip or replace the academy's sale fee."""
    parent = _parent_team()
    player_id = 284492
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="L. Hall",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            sale_fee=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [
            _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2026-07-01", "€ 50M", 34, "Newcastle", 66, "Aston Villa"),
        ],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert tracked.sale_fee == "€ 33M"
    assert fake.transfer_calls == 1
    assert fake.fixture_team_ids == [66]


def test_batch_current_club_ignores_later_ambiguous_na(app, monkeypatch):
    """Parent context resolves the first N/A while unrelated N/A stays inert."""
    parent = _parent_team()
    player_id = 900002
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Topology Player",
            team_id=parent.id,
            status="sold",
            current_club_api_id=None,
            current_club_name=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [
            _transfer("2024-07-01", "N/A", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "N/A", 777, "Unrelated", 888, "Wrong Club"),
        ],
        profile={"statistics": []},
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (34, "Newcastle")
    assert fake.transfer_calls == 1
    assert fake.fixture_team_ids == [34]


def test_batch_reconciles_stale_stored_club_before_early_continue(app, monkeypatch):
    """Fresh resolver state must replace a contradictory prior backfill."""
    parent = _parent_team()
    player_id = 900004
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Stale Destination",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            sale_fee="Undisclosed",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [_transfer("2025-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (34, "Newcastle")
    assert fake.transfer_calls == 1
    assert fake.fixture_team_ids == [34]


def test_batch_indeterminate_historical_loan_preserves_newer_stored_club(app, monkeypatch):
    """An expired open loan is not proof the old borrower is current."""
    parent = _parent_team()
    player_id = 900006
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Old Open Loan",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [_transfer("2023-07-01", "Loan", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_team_ids == [66]


def test_batch_old_permanent_move_preserves_newer_unrelated_stored_club(app, monkeypatch):
    """An old sale cannot erase later statistics/backfill at a third club."""
    parent = _parent_team()
    player_id = 900010
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Later Third Club",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [_transfer("2023-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (
        66,
        "Aston Villa",
    )
    assert fake.fixture_team_ids == [66]


def test_batch_indeterminate_historical_loan_preserves_newer_profile_club(app, monkeypatch):
    """Current-season profile evidence wins over an expired open loan."""
    parent = _parent_team()
    player_id = 900007
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Profile Club",
            team_id=parent.id,
            status="sold",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [_transfer("2023-07-01", "Loan", 49, "Chelsea", 34, "Newcastle")],
        profile={
            "statistics": [
                {
                    "team": {"id": 66, "name": "Aston Villa"},
                    "games": {"appearences": 12, "position": "Defender"},
                }
            ]
        },
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_team_ids == [66]


def test_batch_commits_resolver_fee_before_profile_failure(app, monkeypatch):
    """A later profile error cannot discard an academy sale-fee repair."""
    parent = _parent_team()
    player_id = 900008
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Fee Repair",
            team_id=parent.id,
            status="sold",
            sale_fee=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _BatchAPI(
        player_id,
        [_transfer("2024-07-01", "€ 12M", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    # Expire ORM state to prove the value survived the independent commit.
    db.session.expire_all()
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert tracked.sale_fee == "€ 12M"


class _SeedTransferAPI:
    def __init__(self, player_id, *, transfers=None, transfer_error=None):
        self.player_id = player_id
        self.transfers = transfers
        self.transfer_error = transfer_error

    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        if self.transfer_error is not None:
            raise self.transfer_error
        return _payload(player_id, self.transfers or [])


def test_seed_fallback_skips_candidate_when_transfer_fetch_fails():
    player_id = 900005
    fake = _SeedTransferAPI(
        player_id,
        transfer_error=RuntimeError("provider unavailable"),
    )

    assert not _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )


def test_seed_fallback_accepts_successful_empty_transfer_history():
    player_id = 900005
    fake = _SeedTransferAPI(player_id, transfers=[])

    assert _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )


def test_seed_fallback_does_not_invent_parent_owner_for_ambiguous_na(monkeypatch):
    resolver_kwargs = []

    def _capture_resolver(events, **kwargs):
        resolver_kwargs.append(kwargs)
        return real_resolve_transfer_state(events, **kwargs)

    monkeypatch.setattr(api_routes, "resolve_transfer_state", _capture_resolver)
    player_id = 900005
    fake = _SeedTransferAPI(
        player_id,
        transfers=[
            _transfer(
                "2025-07-01",
                "N/A",
                700,
                "Other Club",
                49,
                "Chelsea",
            )
        ],
    )

    assert not _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )
    assert len(resolver_kwargs) == 1
    assert "initial_owner" not in resolver_kwargs[0]


def test_seed_fallback_rejects_external_loan_arrival_into_parent():
    """Borrowing a prospect does not make that prospect an academy product."""
    player_id = 900009
    fake = _SeedTransferAPI(
        player_id,
        transfers=[
            _transfer(
                "2025-07-01",
                "Loan",
                700,
                "Other Club",
                49,
                "Chelsea",
            )
        ],
    )

    assert not _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )


def test_classifier_matches_active_borrower_across_reverse_affiliate_id(app):
    """Stats may expose Jong Ajax while the transfer names senior Ajax."""
    status, club_id, club_name = classify_tracked_player(
        current_club_api_id=425,
        current_club_name="Jong Ajax",
        current_level="First Team",
        parent_api_id=165,
        parent_club_name="Borussia Dortmund",
        transfers=[
            _transfer(
                "2025-07-01",
                "Loan",
                165,
                "Borussia Dortmund",
                194,
                "Ajax",
            )
        ],
        latest_season=2025,
        as_of="2026-06-30",
    )

    assert (status, club_id, club_name) == ("on_loan", 425, "Jong Ajax")


def test_classifier_fetch_failure_is_not_a_successful_empty_history(app):
    """Provider failure preserves uncertainty; a real empty response means left."""

    class _FailingAPI:
        def get_player_transfers(self, player_id):
            raise RuntimeError("provider unavailable")

    class _EmptyAPI:
        def get_player_transfers(self, player_id):
            return _payload(player_id, [])

    kwargs = {
        "current_club_api_id": 700,
        "current_club_name": "Other Club",
        "current_level": "First Team",
        "parent_api_id": 165,
        "parent_club_name": "Borussia Dortmund",
        "player_api_id": 900003,
        "latest_season": 2025,
        "as_of": "2026-06-30",
    }

    failed = classify_tracked_player(api_client=_FailingAPI(), transfers=None, **kwargs)
    empty = classify_tracked_player(api_client=_EmptyAPI(), transfers=None, **kwargs)

    assert failed[0] == "on_loan"
    assert empty[0] == "left"


def test_classifier_same_parent_fetch_failure_stays_conservative(app):
    """Unknown transfer evidence must not invent a same-parent departure."""

    class _FailingAPI:
        def get_player_transfers(self, player_id):
            raise RuntimeError("provider unavailable")

    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=None,
        player_api_id=284492,
        api_client=_FailingAPI(),
        latest_season=2025,
        config={"inactivity_release_years": 2, "use_squad_check": False},
        as_of="2026-06-30",
    )

    assert result == ("first_team", 49, "Chelsea")


_CLASSIFIER_CONFIG = {"inactivity_release_years": 2, "use_squad_check": False}


def test_classifier_hall_sale_overrides_stale_same_parent_journey(app):
    """Hall-shaped parent stats must not hide the later permanent conversion."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2023-08-22", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("sold", 34, "Newcastle")


def test_classifier_release_overrides_stale_same_parent_journey(app):
    """A definitive parent-to-free-agent event clears stale parent fields."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2025-07-01", "Free agent", 49, "Chelsea", None, None),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("released", None, None)


def test_classifier_active_loan_overrides_stale_same_parent_journey(app):
    """A fresh resolved parent loan supplies the borrower even before stats move."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2026-07-10", "Loan", 49, "Chelsea", 44, "Burnley"),
        ],
        latest_season=2026,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-12-01",
    )

    assert result == ("on_loan", 44, "Burnley")


def test_classifier_name_only_parent_and_destination_can_be_sold(app):
    """Provider IDs are enrichment, not a prerequisite for a named sale."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer(
                "2024-07-01",
                "Transfer",
                None,
                "Chelsea U21",
                None,
                "Newcastle United",
            ),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("sold", None, "Newcastle United")


def test_classifier_permanent_buyback_restores_parent_status(app):
    """A later permanent move back to the parent supersedes its old sale."""
    result = classify_tracked_player(
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2023-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "Transfer", 34, "Newcastle", 49, "Chelsea"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("first_team", 49, "Chelsea")


def test_classifier_older_loan_return_does_not_override_newer_external_stats(app):
    """A return predating the latest stats season cannot erase its current club."""
    result = classify_tracked_player(
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2023-07-01", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2024-07-01", "Back from Loan", 34, "Newcastle", 49, "Chelsea"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("left", 34, "Newcastle")


def test_classifier_current_season_loan_return_restores_parent_status(app):
    """A return in the latest stats season supersedes stale borrower fields."""
    result = classify_tracked_player(
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2024-07-01", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "Back from Loan", 34, "Newcastle", 49, "Chelsea"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("first_team", 49, "Chelsea")
