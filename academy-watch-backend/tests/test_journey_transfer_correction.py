"""Regression tests for JourneySyncService._correct_club_ids_from_transfers.

API-Football retroactively returns a player's CURRENT club for historical
seasons after a permanent transfer. The correction walks the transfer history to
restore the real club. Two failure modes this guards against:

1. Multi-hop history. A single-hop correction only fixes the season directly
   before the latest move; older seasons collapse onto the wrong club
   (e.g. a 2022 Man Utd season becoming Nottingham Forest).
2. Contradictory feed data. API-Football sometimes returns a duplicate transfer
   into the real destination from an invented lower-league club
   ("Newcastle ⟸ Ashington AFC" alongside "Newcastle ⟸ Nottingham Forest").
   Correcting to that phantom source manufactures a club the player never
   played for — the visible "Ashington AFC" bug on A. Elanga's journey.
"""

from src.services.journey_sync import JourneySyncService


class _Entry:
    def __init__(self, season, club_api_id, club_name, *, is_international=False, appearances=1):
        self.season = season
        self.club_api_id = club_api_id
        self.club_name = club_name
        self.club_logo = ""
        self.is_international = is_international
        self.appearances = appearances


def _transfer(date, in_id, in_name, out_id, out_name):
    return {
        "date": date,
        "type": "Transfer",
        "teams": {
            "in": {"id": in_id, "name": in_name, "logo": ""},
            "out": {"id": out_id, "name": out_name, "logo": ""},
        },
    }


def _svc():
    # Bypass __init__ (which builds an API client / handshake); the method under
    # test only uses its arguments and the module logger.
    return JourneySyncService.__new__(JourneySyncService)


def test_elanga_chain_walk_and_phantom_rejection():
    """The exact A. Elanga scenario: Man Utd → Forest → Newcastle, with a bogus
    duplicate 'Newcastle ⟸ Ashington AFC' transfer in the feed."""
    # Order the invented transfer FIRST so a naive "first matching move" picks
    # the phantom — the worst case the corroboration guard must reject.
    transfers = [
        _transfer("2025-07-11", 34, "Newcastle", 8686, "Ashington AFC"),  # invented
        _transfer("2025-07-11", 34, "Newcastle", 65, "Nottingham Forest"),
        _transfer("2023-07-25", 65, "Nottingham Forest", 33, "Manchester United"),
    ]
    # API mis-attributed 2022-2024 to the current club (Newcastle), plus the real
    # entries the player actually has (the evidence that discards Ashington).
    misattributed = [
        _Entry(2022, 34, "Newcastle"),
        _Entry(2023, 34, "Newcastle"),
        _Entry(2024, 34, "Newcastle"),
    ]
    real = [
        _Entry(2022, 33, "Manchester United"),
        _Entry(2023, 65, "Nottingham Forest"),
        _Entry(2025, 34, "Newcastle"),  # genuine current club — must stay
    ]
    entries = misattributed + real

    _svc()._correct_club_ids_from_transfers(entries, transfers)

    # Phantom never appears.
    assert all(e.club_api_id != 8686 for e in entries)
    assert all("Ashington" not in (e.club_name or "") for e in entries)
    # Multi-hop chain restores the right club per season.
    assert misattributed[0].club_api_id == 33, "2022 should walk back to Man Utd"
    assert misattributed[1].club_api_id == 65, "2023 should be Nottingham Forest"
    assert misattributed[2].club_api_id == 65, "2024 should be Nottingham Forest"
    # The genuine current-club season is untouched.
    assert real[2].club_api_id == 34


def test_single_hop_correction_still_applies():
    """The common case — one permanent transfer — keeps working."""
    transfers = [_transfer("2024-07-01", 50, "New Club", 40, "Old Club")]
    entries = [_Entry(2023, 50, "New Club")]  # mis-attributed to the new club

    _svc()._correct_club_ids_from_transfers(entries, transfers)

    assert entries[0].club_api_id == 40
    assert entries[0].club_name == "Old Club"


def test_international_entries_are_never_rewritten():
    transfers = [_transfer("2025-07-11", 34, "Newcastle", 65, "Nottingham Forest")]
    natl = _Entry(2022, 34, "Sweden", is_international=True)

    _svc()._correct_club_ids_from_transfers([natl], transfers)

    assert natl.club_api_id == 34 and natl.club_name == "Sweden"
