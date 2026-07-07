"""
Transfer window data for loan detection system.

This module contains hard-coded transfer window boundaries for European football leagues
from seasons 2022-23 through 2027-28. These dates are based on league-specific deadlines
and stored as ISO date strings for precise date filtering.

Each season maps to two windows on the standard European convention: SUMMER runs
Jun 1 – Sep 1 of the season-start year, WINTER runs Dec 1 – Feb 1. Keep future
seasons ahead of the calendar so the nightly transfer heal always has window data
for the window that is currently open (a missing season silently resolves every
lookup to "out of window" — see api_football_client._in_window).

Window Keys Format: "<YYYY-YY>::<SUMMER|WINTER|FULL>"
- SUMMER: Summer transfer window
- WINTER: Winter/January transfer window
- FULL: Union of both summer and winter windows for the season
"""

# Transfer window boundaries - dates are league deadline times as naive dates
WINDOWS = {
    "2022-23": {"SUMMER": ("2022-06-01", "2022-09-01"), "WINTER": ("2022-12-01", "2023-02-01")},
    "2023-24": {"SUMMER": ("2023-06-01", "2023-09-01"), "WINTER": ("2023-12-01", "2024-02-01")},
    "2024-25": {"SUMMER": ("2024-06-01", "2024-09-01"), "WINTER": ("2024-12-01", "2025-02-01")},
    "2025-26": {
        # Premier League has two-stage open but single close - collapsed to main run
        "SUMMER": ("2025-06-01", "2025-09-01"),
        "WINTER": ("2025-12-01", "2026-02-01"),
    },
    "2026-27": {"SUMMER": ("2026-06-01", "2026-09-01"), "WINTER": ("2026-12-01", "2027-02-01")},
    "2027-28": {"SUMMER": ("2027-06-01", "2027-09-01"), "WINTER": ("2027-12-01", "2028-02-01")},
}


def get_supported_seasons():
    """Return list of supported season slugs."""
    return list(WINDOWS.keys())


def get_supported_window_keys():
    """Return list of all supported window keys."""
    window_keys = []
    for season in WINDOWS.keys():
        window_keys.extend([f"{season}::SUMMER", f"{season}::WINTER", f"{season}::FULL"])
    return window_keys
