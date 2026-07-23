from src.utils.academy_classifier import classify_tracked_player
from src.utils.rebuild_runner import _rebuild_sale_fee, _rebuild_transfer_evidence

PARENT_ID = 100
PLAYER_ID = 400
CONFIG = {"inactivity_release_years": None, "use_squad_check": False}


def _transfer(transfer_date, transfer_type, out_id, out_name, in_id, in_name):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


class _TransferClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def get_player_transfers(self, player_api_id):
        assert player_api_id == PLAYER_ID
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def _evidence(client, cache, **overrides):
    kwargs = {
        "parent_api_id": PARENT_ID,
        "parent_club_name": "Parent FC",
        "as_of": "2026-12-01",
        "season_start_month": 7,
        "season_start_day": 1,
    }
    kwargs.update(overrides)
    return _rebuild_transfer_evidence(client, PLAYER_ID, cache, **kwargs)


def test_rebuild_fetches_once_and_shares_parent_resolution_with_classifier():
    transfers = [
        _transfer("2024-07-01", "€ 33M", PARENT_ID, "Parent FC", 200, "Buyer FC"),
        _transfer("2025-07-01", "€ 50M", 200, "Buyer FC", 300, "Later FC"),
    ]
    client = _TransferClient([{"player": {"id": PLAYER_ID}, "transfers": transfers}])
    cache = {}

    flat, resolution = _evidence(client, cache)
    second_flat, second_resolution = _evidence(client, cache)
    status, club_id, club_name = classify_tracked_player(
        current_club_api_id=PARENT_ID,
        current_club_name="Parent FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=flat,
        player_api_id=PLAYER_ID,
        transfer_resolution=resolution,
        as_of="2026-12-01",
        config=CONFIG,
    )

    assert client.calls == 1
    assert second_flat is flat
    assert second_resolution.events == resolution.events
    assert (status, club_id, club_name) == ("sold", 300, "Later FC")
    assert (
        _rebuild_sale_fee(
            None,
            status=status,
            resolution=resolution,
            parent_api_id=PARENT_ID,
            parent_club_name="Parent FC",
        )
        == "€ 33M"
    )


def test_rebuild_uses_the_journey_season_calendar_for_loan_freshness():
    loan = _transfer("2026-02-10", "Loan", PARENT_ID, "Parent FC", 200, "Loan FC")
    client = _TransferClient([{"player": {"id": PLAYER_ID}, "transfers": [loan]}])

    _, resolution = _evidence(
        client,
        {},
        season_start_month=1,
        season_start_day=1,
    )

    assert resolution.season_start_month == 1
    assert resolution.season_start_day == 1
    assert resolution.on_loan is True


def test_rebuild_failed_fetch_is_cached_and_preserves_existing_fee():
    client = _TransferClient(error=RuntimeError("provider unavailable"))
    cache = {}

    first = _evidence(client, cache)
    second = _evidence(client, cache)

    assert first == (None, None)
    assert second == (None, None)
    assert client.calls == 1
    assert (
        _rebuild_sale_fee(
            "€ 33M",
            status="first_team",
            resolution=None,
            parent_api_id=PARENT_ID,
            parent_club_name="Parent FC",
        )
        == "€ 33M"
    )


def test_rebuild_successful_empty_history_clears_stale_fee():
    client = _TransferClient([])

    transfers, resolution = _evidence(client, {})

    assert transfers == []
    assert resolution is not None
    assert (
        _rebuild_sale_fee(
            "€ 33M",
            status="first_team",
            resolution=resolution,
            parent_api_id=PARENT_ID,
            parent_club_name="Parent FC",
        )
        is None
    )
