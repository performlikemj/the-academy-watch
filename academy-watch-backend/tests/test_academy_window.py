"""Tests for the academy tracking window helper (src/utils/academy_window.py)."""

from datetime import date, datetime

from src.utils.academy_window import (
    DEVELOPMENT_AGE_CUTOFF,
    academy_window_start,
    age_from_birth_date,
    current_academy_season,
    is_within_academy_window,
)


class TestCurrentAcademySeason:
    def test_before_july_belongs_to_previous_season(self):
        assert current_academy_season(date(2026, 6, 30)) == 2025

    def test_july_starts_new_season(self):
        assert current_academy_season(date(2026, 7, 1)) == 2026

    def test_december_mid_season(self):
        assert current_academy_season(date(2025, 12, 25)) == 2025


class TestWindowStart:
    def test_window_is_current_minus_four_seasons(self):
        assert academy_window_start(date(2026, 6, 13)) == 2021
        assert academy_window_start(date(2026, 8, 1)) == 2022

    def test_window_years_env_override(self, monkeypatch):
        monkeypatch.setenv("ACADEMY_WINDOW_YEARS", "2")
        assert academy_window_start(date(2026, 6, 13)) == 2023

    def test_window_years_bad_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("ACADEMY_WINDOW_YEARS", "not-a-number")
        assert academy_window_start(date(2026, 6, 13)) == 2021


class TestAgeFromBirthDate:
    def test_birthday_passed(self):
        assert age_from_birth_date("2007-07-13", today=date(2026, 6, 13)) == 18

    def test_birthday_not_yet(self):
        assert age_from_birth_date("2007-07-13", today=date(2026, 7, 12)) == 18
        assert age_from_birth_date("2007-07-13", today=date(2026, 7, 13)) == 19

    def test_garbage_and_missing(self):
        assert age_from_birth_date(None) is None
        assert age_from_birth_date("") is None
        assert age_from_birth_date("not-a-date") is None
        assert age_from_birth_date("3026-01-01", today=date(2026, 6, 13)) is None


class TestIsWithinAcademyWindow:
    TODAY = date(2026, 6, 13)  # current season 2025, window start 2021

    def test_recent_academy_season_in_window(self):
        assert is_within_academy_window(2021, today=self.TODAY) is True
        assert is_within_academy_window(2025, today=self.TODAY) is True

    def test_old_academy_season_out_of_window(self):
        assert is_within_academy_window(2020, today=self.TODAY) is False
        assert is_within_academy_window(2016, today=self.TODAY) is False

    def test_current_academy_status_always_in_window(self):
        assert is_within_academy_window(2016, status="academy", today=self.TODAY) is True
        assert is_within_academy_window(None, status="academy", today=self.TODAY) is True

    def test_no_evidence_falls_back_to_development_age(self):
        young = f"{self.TODAY.year - DEVELOPMENT_AGE_CUTOFF}-12-31"  # cutoff age, birthday pending
        old = "2001-09-26"  # 24 — a senior signing, not an academy prospect
        assert is_within_academy_window(None, birth_date=young, today=self.TODAY) is True
        assert is_within_academy_window(None, birth_date=old, today=self.TODAY) is False

    def test_no_evidence_at_all_is_out_of_window(self):
        assert is_within_academy_window(None, today=self.TODAY) is False

    def test_accepts_datetime_today(self):
        assert is_within_academy_window(2021, today=datetime(2026, 6, 13, 10, 0)) is True

    def test_season_evidence_beats_age_fallback(self):
        # A 20-year-old whose last academy season is outside the window is
        # still out: explicit evidence wins over the age heuristic.
        young = f"{self.TODAY.year - 20}-01-01"
        assert is_within_academy_window(2019, birth_date=young, today=self.TODAY) is False
