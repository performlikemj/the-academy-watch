"""Transfer-window data coverage.

Regression guard for the nightly transfer heal: the WINDOWS table must stay
ahead of the calendar so the currently-open window always has data. A missing
season does not raise — api_football_client._in_window catches the KeyError and
silently returns False ("out of window"), so a gap degrades loan detection with
no error. These tests pin that the seasons around today resolve, and that the
summer 2026 window (season 2026-27), which is open on 2026-07-07, is covered.
"""

from datetime import date

from src.api_football_client import APIFootballClient
from src.data.transfer_windows import WINDOWS, get_supported_seasons, get_supported_window_keys


def test_current_and_headroom_seasons_present():
    seasons = get_supported_seasons()
    # The season whose summer window is open right now (today is 2026-07-07)
    # plus one season of headroom so a mid-window gap never recurs.
    assert "2026-27" in seasons
    assert "2027-28" in seasons


def test_new_season_window_bounds_follow_convention():
    # SUMMER: Jun 1 – Sep 1 of the season-start year; WINTER: Dec 1 – Feb 1.
    assert WINDOWS["2026-27"]["SUMMER"] == ("2026-06-01", "2026-09-01")
    assert WINDOWS["2026-27"]["WINTER"] == ("2026-12-01", "2027-02-01")
    assert WINDOWS["2027-28"]["SUMMER"] == ("2027-06-01", "2027-09-01")
    assert WINDOWS["2027-28"]["WINTER"] == ("2027-12-01", "2028-02-01")


def test_supported_window_keys_include_new_seasons():
    keys = get_supported_window_keys()
    for key in (
        "2026-27::SUMMER",
        "2026-27::WINTER",
        "2026-27::FULL",
        "2027-28::SUMMER",
        "2027-28::FULL",
    ):
        assert key in keys


def test_parse_window_key_resolves_new_season():
    client = APIFootballClient()
    assert client._parse_window_key("2026-27::SUMMER") == (date(2026, 6, 1), date(2026, 9, 1))
    # FULL spans the summer open through the winter close of the same season.
    assert client._parse_window_key("2026-27::FULL") == (date(2026, 6, 1), date(2027, 2, 1))


def test_today_maps_into_open_summer_window():
    """2026-07-07 (today) is inside the summer 2026-27 window and, critically,
    outside every 2025-26 window — the gap the heal hit before this fix."""
    client = APIFootballClient()
    assert client._in_window("2026-07-07", "2026-27::SUMMER") is True
    assert client._in_window("2026-07-07", "2026-27::FULL") is True
    # The pre-fix data (through 2025-26 only) could never place this date in a
    # window: all 2025-26 windows closed by Feb 2026.
    assert client._in_window("2026-07-07", "2025-26::SUMMER") is False
    assert client._in_window("2026-07-07", "2025-26::FULL") is False


def test_unknown_future_season_still_degrades_silently_not_crash():
    """Behaviour contract: a season still absent from the table resolves to
    False rather than raising, so callers never crash on a gap."""
    client = APIFootballClient()
    assert client._in_window("2030-07-01", "2030-31::SUMMER") is False
