"""Regression tests for the 'released' over-classification bug.

Two independent defects in src/utils/academy_classifier.py used to mark
actively-playing academy products as 'released' (relative to their parent
academy club):

HEAD 1 — upgrade_status_from_transfers() mapped a permanent parent departure
typed "N/A"/"Free" to 'released'. API-Football types undisclosed-fee sales as
"N/A" and populates teams.in for virtually every departure, so the fee string
cannot distinguish a free-agency exit from a permanent move to a new club. The
fix keys off a concrete onward destination: a real, non-parent, non-national
club ⇒ 'sold'; only the absence of one ⇒ 'released'. Canonical case: Julian
Rijkhoff (Dortmund→Jong Ajax typed "N/A", now on loan at Almere) read
'released' under Dortmund; he should be 'sold'.

HEAD 2 — _get_latest_season() returned the latest *parent-named* season
(often a stale youth entry like "<Parent> U19") instead of the player's latest
activity anywhere, tripping the Step-3 inactivity rule for players active
elsewhere. The fix returns the latest *domestic* season at ANY club.
"""

from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import db
from src.utils.academy_classifier import (
    _get_latest_season,
    classify_tracked_player,
    upgrade_status_from_transfers,
)
from src.utils.affiliates import is_affiliate, senior_base_name

DORTMUND = 165


def _t(date, in_id, in_name, out_id, out_name, ttype):
    return {
        "date": date,
        "type": ttype,
        "teams": {
            "in": {"id": in_id, "name": in_name},
            "out": {"id": out_id, "name": out_name},
        },
    }


# Rijkhoff's real flattened transfer history (verified via API-Football).
RIJKHOFF_TRANSFERS = [
    _t("2024-02-01", 425, "Jong Ajax", DORTMUND, "Borussia Dortmund", "N/A"),
    _t("2025-06-23", 419, "Almere City FC", 194, "Ajax", "Loan"),
    _t("2025-06-30", 419, "Almere City FC", 194, "Ajax", "Loan"),
]


class TestUpgradeStatusFromTransfers:
    """HEAD 1 — permanent departures resolve to sold/released by destination."""

    def test_na_departure_with_destination_is_sold(self):
        # Rijkhoff: only Dortmund departure is type "N/A" -> Jong Ajax (425).
        assert upgrade_status_from_transfers("on_loan", RIJKHOFF_TRANSFERS, DORTMUND, 419) == "sold"

    def test_free_departure_with_destination_is_sold(self):
        transfers = [_t("2022-07-01", 740, "Antwerp", DORTMUND, "Borussia Dortmund", "Free")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, 740) == "sold"

    def test_fee_departure_is_sold(self):
        transfers = [_t("2023-08-01", 50, "Man City", DORTMUND, "Borussia Dortmund", "€ 20M")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, 50) == "sold"

    def test_permanent_departure_with_no_destination_is_released(self):
        # Genuine free agent: no onward club recorded on the departure.
        transfers = [{"date": "2023-06-30", "type": "Free agent", "teams": {"in": {}, "out": {"id": DORTMUND}}}]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, None) == "released"

    def test_no_departure_destination_stays_released_even_with_current_club(self):
        # The departure's empty teams.in is the free-agency signal. The
        # journey's current club (passed as current_club_api_id) is a separate
        # signal and must NOT be folded in to manufacture a 'sold'.
        transfers = [{"date": "2023-06-30", "type": "Free agent", "teams": {"in": {}, "out": {"id": DORTMUND}}}]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, 999) == "released"

    def test_destination_equal_to_parent_is_released(self):
        # A departure whose "in" is the parent itself is not a sale away.
        transfers = [_t("2023-06-30", DORTMUND, "Borussia Dortmund", DORTMUND, "Borussia Dortmund", "N/A")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, None) == "released"

    def test_national_team_destination_is_not_sold(self):
        transfers = [_t("2023-06-30", 10, "England", DORTMUND, "Borussia Dortmund", "N/A")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, None) == "released"

    def test_genuine_loan_to_loan_destination_stays_on_loan(self):
        transfers = [_t("2025-07-01", 700, "Loan Club", DORTMUND, "Borussia Dortmund", "Loan")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, 700) == "on_loan"

    def test_loan_typed_but_current_club_not_a_loan_destination_is_left(self):
        # Loan-typed departure to 700, but the player's current club is 999 (not
        # a parent loan destination) -> loaned out then moved on -> left.
        transfers = [_t("2025-07-01", 700, "Loan Club", DORTMUND, "Borussia Dortmund", "Loan")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, 999) == "left"

    def test_no_parent_departure_with_current_club_is_left(self):
        # Berry@Man United: player is at another club (Al Kholood 10509) but has
        # NO recorded departure from the parent -> left, not on_loan.
        transfers = [_t("2026-01-25", 10509, "Al Kholood", 65, "Nottingham Forest", "Transfer")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, 10509) == "left"

    def test_no_parent_departure_without_current_club_stays_on_loan(self):
        # Conservative: with no known current club we cannot assert departure.
        transfers = [_t("2026-01-25", 10509, "Al Kholood", 65, "Nottingham Forest", "Transfer")]
        assert upgrade_status_from_transfers("on_loan", transfers, DORTMUND, None) == "on_loan"

    def test_non_on_loan_status_unchanged(self):
        assert upgrade_status_from_transfers("academy", RIJKHOFF_TRANSFERS, DORTMUND, 419) == "academy"

    def test_no_transfers_unchanged(self):
        assert upgrade_status_from_transfers("on_loan", [], DORTMUND, 419) == "on_loan"


class TestClassifyTrackedPlayerEndToEnd:
    """Full classify pipeline (pure: config + transfers + latest_season passed)."""

    CONFIG = {"inactivity_release_years": 2, "use_squad_check": False}

    def test_rijkhoff_classifies_as_sold(self):
        status, club_id, club_name = classify_tracked_player(
            current_club_api_id=419,
            current_club_name="Almere City FC",
            current_level="First Team",
            parent_api_id=DORTMUND,
            parent_club_name="Borussia Dortmund",
            transfers=RIJKHOFF_TRANSFERS,
            latest_season=2025,
            config=self.CONFIG,
        )
        assert status == "sold"
        assert club_id == 419  # destination retained for display

    def test_player_active_elsewhere_recently_is_not_released(self):
        # academy base status, no permanent departure transfer, recent activity.
        status, _, _ = classify_tracked_player(
            current_club_api_id=None,
            current_club_name=None,
            current_level="U21",
            parent_api_id=100,
            parent_club_name="Some FC",
            transfers=[],
            latest_season=2025,
            config=self.CONFIG,
        )
        assert status == "academy"

    def test_genuinely_inactive_player_is_released(self):
        # No activity anywhere for years -> the inactivity rule still releases.
        status, _, _ = classify_tracked_player(
            current_club_api_id=None,
            current_club_name=None,
            current_level="U21",
            parent_api_id=100,
            parent_club_name="Some FC",
            transfers=[],
            latest_season=2020,
            config=self.CONFIG,
        )
        assert status == "released"


class TestGetLatestSeason:
    """HEAD 2 — latest *domestic* activity anywhere, not the stale parent season."""

    def _make_journey(self, entries):
        journey = PlayerJourney(player_api_id=999999)
        db.session.add(journey)
        db.session.flush()
        for season, club_api_id, club_name, is_intl in entries:
            db.session.add(
                PlayerJourneyEntry(
                    journey_id=journey.id,
                    season=season,
                    club_api_id=club_api_id,
                    club_name=club_name,
                    is_international=is_intl,
                    appearances=1,
                )
            )
        db.session.flush()
        return journey.id

    def test_returns_latest_domestic_anywhere_not_stale_parent_youth(self, app):
        # Parent youth season 2023 is stale; player active at Almere in 2025.
        jid = self._make_journey(
            [
                (2023, 7890, "Borussia Dortmund U19", False),
                (2025, 419, "Almere City FC", False),
            ]
        )
        assert _get_latest_season(jid, parent_api_id=DORTMUND, parent_club_name="Borussia Dortmund") == 2025

    def test_ignores_international_only_recent_entries(self, app):
        # Recent activity is only an international cap; latest club season is 2022.
        jid = self._make_journey(
            [
                (2022, 419, "Almere City FC", False),
                (2025, 10, "Netherlands U21", True),
            ]
        )
        assert _get_latest_season(jid, parent_api_id=DORTMUND, parent_club_name="Borussia Dortmund") == 2022

    def test_international_only_history_falls_back_to_latest(self, app):
        jid = self._make_journey([(2024, 10, "Netherlands U19", True)])
        assert _get_latest_season(jid, parent_api_id=DORTMUND, parent_club_name="Borussia Dortmund") == 2024


class TestAffiliateResolver:
    """Affiliate / B-team -> senior org resolution (data-driven + hardcoded)."""

    def test_senior_base_name_strips_jong_prefix(self):
        assert senior_base_name("Jong Ajax") == "Ajax"

    def test_senior_base_name_strips_u_number(self):
        assert senior_base_name("Atalanta U20") == "Atalanta"

    def test_senior_base_name_strips_castilla_and_reserve(self):
        assert senior_base_name("Real Madrid Castilla") == "Real Madrid"
        assert senior_base_name("Manchester United U18") == "Manchester United"

    def test_is_affiliate_via_name(self):
        # "Jong Ajax" normalises to "Ajax" == parent "Ajax"
        assert is_affiliate(99999, "Jong Ajax", 194, "Ajax") is True

    def test_is_affiliate_via_hardcoded_id_when_name_missing(self):
        # 425 (Jong Ajax) -> 194, even with no name loaded
        assert is_affiliate(425, None, 194, "Ajax") is True

    def test_not_affiliate_of_different_club(self):
        assert is_affiliate(15382, "Manchester United U18", 50, "Manchester City") is False


class TestClassifyEvidenceBasedModel:
    """End-to-end: on_loan is earned; departure-without-record -> 'left'."""

    CONFIG = {"inactivity_release_years": 2, "use_squad_check": False}

    def _classify(self, current_id, current_name, level, parent_id, parent_name, transfers, latest_season):
        return classify_tracked_player(
            current_club_api_id=current_id,
            current_club_name=current_name,
            current_level=level,
            parent_api_id=parent_id,
            parent_club_name=parent_name,
            transfers=transfers,
            latest_season=latest_season,
            config=self.CONFIG,
        )

    def test_berry_under_man_united_is_left(self):
        # No Man United departure transfer; player is at Al Kholood -> left.
        transfers = [
            _t("2024-04-20", 19746, "Nottingham Forest U21", 17426, "Nottingham Forest U18", "N/A"),
            _t("2026-01-25", 10509, "Al Kholood", 65, "Nottingham Forest", "Transfer"),
        ]
        status, _, _ = self._classify(10509, "Al Kholood", "First Team", 33, "Manchester United", transfers, 2026)
        assert status == "left"

    def test_berry_under_forest_is_sold(self):
        # Forest -> Al Kholood is a recorded permanent transfer with destination.
        transfers = [_t("2026-01-25", 10509, "Al Kholood", 65, "Nottingham Forest", "Transfer")]
        status, _, _ = self._classify(10509, "Al Kholood", "First Team", 65, "Nottingham Forest", transfers, 2026)
        assert status == "sold"

    def test_player_at_parent_b_team_is_not_left(self):
        # Jong Ajax (425) is Ajax's own reserve -> still in the org, not left.
        status, _, _ = self._classify(425, "Jong Ajax", "First Team", 194, "Ajax", [], 2025)
        assert status == "first_team"

    def test_genuine_current_loan_stays_on_loan(self):
        # Parent loaned the player to 430 and that IS the current club.
        transfers = [_t("2026-01-13", 430, "Bourg", 111, "Le Havre", "Loan")]
        status, _, _ = self._classify(430, "Bourg", "First Team", 111, "Le Havre", transfers, 2026)
        assert status == "on_loan"

    def test_transfers_none_does_not_become_left(self):
        # REGRESSION: the recompute-academy sweep classifies with transfers=None
        # (not fetched). It must NOT collapse a different-club player to 'left'
        # — it stays the tentative on_loan; the caller (recompute) then leaves
        # the real stored status untouched via its update_status guard. This is
        # the guard that prevents recompute from clobbering on_loan/sold to left.
        status, _, _ = classify_tracked_player(
            current_club_api_id=999,
            current_club_name="Some Club",
            current_level="First Team",
            parent_api_id=100,
            parent_club_name="Parent FC",
            transfers=None,
            latest_season=2026,
            config=self.CONFIG,
        )
        assert status == "on_loan"

    def test_transfers_empty_list_means_departed_left(self):
        # A genuine sync that fetched transfers and found NONE -> departed.
        status, _, _ = self._classify(999, "Some Club", "First Team", 100, "Parent FC", [], 2026)
        assert status == "left"


class TestJourneyCurrentStatus:
    """PlayerJourney.current_status is the player's ACTUAL current situation
    (on_loan + owner), computed from stored entries — independent of academy."""

    def _journey(self, current_club_api_id, entries):
        from src.models.journey import PlayerJourney, PlayerJourneyEntry

        j = PlayerJourney(player_api_id=424242, current_club_api_id=current_club_api_id)
        db.session.add(j)
        db.session.flush()
        objs = []
        for season, club_api_id, club_name, entry_type, is_intl in entries:
            e = PlayerJourneyEntry(
                journey_id=j.id,
                season=season,
                club_api_id=club_api_id,
                club_name=club_name,
                entry_type=entry_type,
                is_international=is_intl,
                appearances=1,
            )
            db.session.add(e)
            objs.append(e)
        db.session.flush()
        return j, objs

    def _svc(self):
        from src.services.journey_sync import JourneySyncService

        return JourneySyncService()

    def test_on_loan_sets_status_and_owner(self, app):
        # Rijkhoff-shaped: current club Almere (419) is a loan; owner = Ajax (194).
        j, entries = self._journey(
            419,
            [
                (2025, 419, "Almere City FC", "loan", False),
                (2024, 194, "Ajax", "first_team", False),
            ],
        )
        self._svc()._set_current_status(j, entries)
        assert j.current_status == "on_loan"
        assert j.current_owner_api_id == 194
        assert j.current_owner_name == "Ajax"

    def test_owner_resolves_b_team_to_senior(self, app):
        # Owner recorded as Jong Ajax (425) resolves to Ajax (194).
        j, entries = self._journey(
            419,
            [
                (2025, 419, "Almere City FC", "loan", False),
                (2024, 425, "Jong Ajax", "first_team", False),
            ],
        )
        self._svc()._set_current_status(j, entries)
        assert j.current_status == "on_loan"
        assert j.current_owner_api_id == 194  # Jong Ajax -> Ajax via affiliate map

    def test_not_on_loan_leaves_status_null(self, app):
        # Current club entry is first_team (not a loan) -> defer to academy status.
        j, entries = self._journey(
            10509,
            [(2026, 10509, "Al Kholood", "first_team", False)],
        )
        self._svc()._set_current_status(j, entries)
        assert j.current_status is None
        assert j.current_owner_api_id is None
