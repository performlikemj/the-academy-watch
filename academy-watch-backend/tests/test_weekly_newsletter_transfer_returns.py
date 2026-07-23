"""Focused regressions for resolver-backed newsletter loan returns."""

from datetime import date

import src.agents.weekly_newsletter_agent as agent
from src.models.league import Team, db
from src.models.tracked_player import TrackedPlayer
from src.services import transfer_resolver


def _transfer(transfer_date, transfer_type, out_id, out_name, in_id, in_name):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


class _BatchTransferAPI:
    def __init__(self, events_by_player, omitted_player_ids=()):
        self.events_by_player = events_by_player
        self.omitted_player_ids = set(omitted_player_ids)

    def batch_get_player_transfers(self, player_ids):
        assert set(player_ids) == set(self.events_by_player) | self.omitted_player_ids
        return {
            player_id: [
                {
                    "player": {"id": player_id},
                    "transfers": list(events),
                }
            ]
            for player_id, events in self.events_by_player.items()
        }


def _seed_parent(team_api_id, name):
    parent = Team(
        team_id=team_api_id,
        name=name,
        country="Test Country",
        season=2025,
        is_active=True,
    )
    db.session.add(parent)
    db.session.flush()
    return parent


def _seed_player(parent, player_api_id, name):
    player = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=name,
        team_id=parent.id,
        status="on_loan",
        is_active=True,
    )
    db.session.add(player)
    db.session.flush()
    return player


def _detect(
    monkeypatch,
    parent,
    events_by_player,
    week_start,
    week_end,
    *,
    omitted_player_ids=(),
):
    monkeypatch.setattr(
        agent,
        "api_client",
        _BatchTransferAPI(events_by_player, omitted_player_ids),
    )
    return agent._detect_recent_loan_returns(
        team_db_id=parent.id,
        parent_api_id=parent.team_id,
        week_start=week_start,
        week_end=week_end,
        lookback_days=0,
    )


def test_mills_topology_na_return_to_parent_affiliate_is_included(app, monkeypatch):
    parent = _seed_parent(45, "Everton")
    player = _seed_player(parent, 1001, "Stanley Mills")
    events = [
        _transfer("2023-07-27", "Loan", 45, "Everton", 1338, "Oxford United"),
        _transfer("2024-01-08", "N/A", 1338, "Oxford United", 99945, "Everton U21"),
        # Provider duplicates must collapse to one newsletter return.
        _transfer("2024-01-08", "N/A", 1338, "Oxford United", 99945, "Everton U21"),
    ]

    returns = _detect(
        monkeypatch,
        parent,
        {player.player_api_id: events},
        date(2024, 1, 8),
        date(2024, 1, 14),
    )

    assert len(returns) == 1
    assert returns[0]["player_api_id"] == player.player_api_id
    assert returns[0]["returned_from_club_api_id"] == 1338
    assert returns[0]["returned_from_club_name"] == "Oxford United"
    assert returns[0]["return_date"] == "2024-01-08"


def test_aseko_na_return_without_loan_start_uses_parent_as_initial_owner(app, monkeypatch):
    parent = _seed_parent(157, "Bayern Munich")
    player = _seed_player(parent, 1002, "Noel Aseko")
    events = [
        _transfer(
            "2025-07-01",
            "N/A",
            166,
            "Hannover 96",
            990157,
            "Bayern Munich II",
        )
    ]

    returns = _detect(
        monkeypatch,
        parent,
        {player.player_api_id: events},
        date(2025, 7, 1),
        date(2025, 7, 7),
    )

    assert len(returns) == 1
    assert returns[0]["player_api_id"] == player.player_api_id
    assert returns[0]["returned_from_club_name"] == "Hannover 96"
    assert returns[0]["return_date"] == "2025-07-01"


def test_latest_resolved_parent_return_wins_and_other_destinations_are_excluded(app, monkeypatch):
    parent = _seed_parent(49, "Chelsea")
    returned = _seed_player(parent, 1003, "Latest Return")
    wrong_destination = _seed_player(parent, 1004, "Wrong Destination")
    events_by_player = {
        returned.player_api_id: [
            _transfer("2023-12-01", "Loan", 49, "Chelsea", 300, "Hull City"),
            _transfer("2024-01-02", "Return from loan", 300, "Hull City", 49, "Chelsea"),
            _transfer("2024-01-04", "Loan", 49, "Chelsea", 301, "Crystal Palace"),
            _transfer("2024-01-10", "Back from loan", 301, "Crystal Palace", 9949, "Chelsea U21"),
            # Future events must not affect an as-of newsletter report.
            _transfer("2024-01-20", "Return from loan", 302, "Future FC", 49, "Chelsea"),
        ],
        wrong_destination.player_api_id: [
            _transfer("2023-12-01", "Loan", 49, "Chelsea", 303, "Loan FC"),
            _transfer("2024-01-09", "Return from loan", 303, "Loan FC", 42, "Arsenal"),
        ],
    }

    returns = _detect(
        monkeypatch,
        parent,
        events_by_player,
        date(2024, 1, 1),
        date(2024, 1, 12),
    )

    assert len(returns) == 1
    assert returns[0]["player_api_id"] == returned.player_api_id
    assert returns[0]["returned_from_club_name"] == "Crystal Palace"
    assert returns[0]["return_date"] == "2024-01-10"


def test_same_week_reloan_suppresses_earlier_return(app, monkeypatch):
    parent = _seed_parent(49, "Chelsea")
    player = _seed_player(parent, 1007, "Returned Then Re-loaned")
    events = [
        _transfer("2024-01-01", "Loan", 49, "Chelsea", 300, "Hull City"),
        _transfer("2024-01-08", "Back from loan", 300, "Hull City", 49, "Chelsea"),
        _transfer("2024-01-10", "Loan", 49, "Chelsea", 301, "Crystal Palace"),
    ]

    returns = _detect(
        monkeypatch,
        parent,
        {player.player_api_id: events},
        date(2024, 1, 8),
        date(2024, 1, 14),
    )

    assert returns == []


def test_parent_internal_move_does_not_suppress_return(app, monkeypatch):
    parent = _seed_parent(49, "Chelsea")
    player = _seed_player(parent, 1008, "Returned To U21")
    events = [
        _transfer("2024-01-01", "Loan", 49, "Chelsea", 300, "Hull City"),
        _transfer("2024-01-08", "Back from loan", 300, "Hull City", 49, "Chelsea"),
        _transfer("2024-01-10", "Transfer", 49, "Chelsea", 9949, "Chelsea U21"),
    ]

    returns = _detect(
        monkeypatch,
        parent,
        {player.player_api_id: events},
        date(2024, 1, 8),
        date(2024, 1, 14),
    )

    assert len(returns) == 1
    assert returns[0]["player_api_id"] == player.player_api_id
    assert returns[0]["returned_from_club_name"] == "Hull City"
    assert returns[0]["return_date"] == "2024-01-08"


def test_parent_internal_loan_does_not_suppress_return(app, monkeypatch):
    parent = _seed_parent(49, "Chelsea")
    player = _seed_player(parent, 1009, "Returned Then Internal Loan")
    events = [
        _transfer("2024-01-01", "Loan", 49, "Chelsea", 300, "Hull City"),
        _transfer("2024-01-08", "Back from loan", 300, "Hull City", 49, "Chelsea"),
        _transfer("2024-01-10", "Loan", 49, "Chelsea", 9949, "Chelsea U21"),
    ]

    returns = _detect(
        monkeypatch,
        parent,
        {player.player_api_id: events},
        date(2024, 1, 8),
        date(2024, 1, 14),
    )

    assert len(returns) == 1
    assert returns[0]["player_api_id"] == player.player_api_id
    assert returns[0]["returned_from_club_name"] == "Hull City"


def test_batch_failure_omission_is_not_resolved_as_empty_history(app, monkeypatch, caplog):
    parent = _seed_parent(49, "Chelsea")
    covered = _seed_player(parent, 1005, "Covered Return")
    omitted = _seed_player(parent, 1006, "Failed Lookup")
    events_by_player = {
        covered.player_api_id: [
            _transfer("2024-01-01", "Loan", 49, "Chelsea", 300, "Hull City"),
            _transfer("2024-01-08", "Back from loan", 300, "Hull City", 49, "Chelsea"),
        ]
    }

    real_resolver = transfer_resolver.resolve_transfer_state
    resolved_histories = []

    def _capture_resolver(events, **kwargs):
        resolved_histories.append(list(events))
        return real_resolver(events, **kwargs)

    monkeypatch.setattr(transfer_resolver, "resolve_transfer_state", _capture_resolver)
    returns = _detect(
        monkeypatch,
        parent,
        events_by_player,
        date(2024, 1, 8),
        date(2024, 1, 14),
        omitted_player_ids={omitted.player_api_id},
    )

    assert [item["player_api_id"] for item in returns] == [covered.player_api_id]
    assert len(resolved_histories) == 1
    assert resolved_histories[0]
    assert str(omitted.player_api_id) in caplog.text
    assert "omitted" in caplog.text
