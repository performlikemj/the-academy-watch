"""
Tests for academy_classifier utility — focusing on loan recall detection
and related status derivation logic.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers to build minimal fake transfer records
# ---------------------------------------------------------------------------

def _make_transfer(
    *,
    date: str,
    transfer_type: str,
    out_id: int,
    out_name: str,
    in_id: int,
    in_name: str,
) -> dict:
    return {
        "date": date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


# ---------------------------------------------------------------------------
# check_loan_return
# ---------------------------------------------------------------------------

class TestCheckLoanReturn:
    """Unit tests for the check_loan_return helper."""

    def test_no_transfers_returns_false(self):
        from src.utils.academy_classifier import check_loan_return
        assert check_loan_return([], parent_api_id=33) is False

    def test_only_loan_out_no_return_returns_false(self):
        """Player went on loan but hasn't come back yet."""
        from src.utils.academy_classifier import check_loan_return

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33,
                out_name="Manchester United",
                in_id=84,
                in_name="Northampton",
            )
        ]
        assert check_loan_return(transfers, parent_api_id=33) is False

    def test_loan_return_after_loan_start_returns_true(self):
        """Wheatley scenario: recalled from Northampton on Jan 12."""
        from src.utils.academy_classifier import check_loan_return

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33,
                out_name="Manchester United",
                in_id=84,
                in_name="Northampton",
            ),
            _make_transfer(
                date="2025-01-12",
                transfer_type="Back From Loan",
                out_id=84,
                out_name="Northampton",
                in_id=33,
                in_name="Manchester United",
            ),
        ]
        assert check_loan_return(transfers, parent_api_id=33) is True

    def test_return_before_loan_start_returns_false(self):
        """Stale return from an earlier loan should not count."""
        from src.utils.academy_classifier import check_loan_return

        transfers = [
            # Old return (from a prior season loan)
            _make_transfer(
                date="2023-06-30",
                transfer_type="Return From Loan",
                out_id=84,
                out_name="Northampton",
                in_id=33,
                in_name="Manchester United",
            ),
            # New outgoing loan (no return recorded yet)
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33,
                out_name="Manchester United",
                in_id=84,
                in_name="Northampton",
            ),
        ]
        assert check_loan_return(transfers, parent_api_id=33) is False

    def test_return_to_different_parent_returns_false(self):
        """Loan return to a club that isn't the queried parent."""
        from src.utils.academy_classifier import check_loan_return

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=42,          # Arsenal sent the player
                out_name="Arsenal",
                in_id=84,
                in_name="Northampton",
            ),
            _make_transfer(
                date="2025-01-12",
                transfer_type="Back From Loan",
                out_id=84,
                out_name="Northampton",
                in_id=42,           # Return to Arsenal
                in_name="Arsenal",
            ),
        ]
        # Querying for Man United (33) — should be False
        assert check_loan_return(transfers, parent_api_id=33) is False

    def test_various_loan_return_type_strings(self):
        """All LOAN_RETURN_TYPES strings should trigger detection."""
        from src.utils.academy_classifier import check_loan_return
        from src.api_football_client import LOAN_RETURN_TYPES

        for return_type in LOAN_RETURN_TYPES:
            transfers = [
                _make_transfer(
                    date="2024-08-01",
                    transfer_type="Loan",
                    out_id=33,
                    out_name="Manchester United",
                    in_id=84,
                    in_name="Northampton",
                ),
                _make_transfer(
                    date="2025-01-12",
                    transfer_type=return_type.title(),  # Match real API casing
                    out_id=84,
                    out_name="Northampton",
                    in_id=33,
                    in_name="Manchester United",
                ),
            ]
            assert check_loan_return(transfers, parent_api_id=33) is True, (
                f"Expected True for return_type='{return_type}'"
            )

    def test_multiple_loan_spells_picks_latest(self):
        """With multiple loan spells, only the LATEST loan out matters."""
        from src.utils.academy_classifier import check_loan_return

        # Season 1: loaned to Northampton then returned
        # Season 2: loaned to Hull — no return yet
        transfers = [
            _make_transfer(
                date="2023-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=84, in_name="Northampton",
            ),
            _make_transfer(
                date="2024-01-12",
                transfer_type="Back From Loan",
                out_id=84, out_name="Northampton",
                in_id=33, in_name="Manchester United",
            ),
            # Latest loan OUT — no return yet
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=56, in_name="Hull City",
            ),
        ]
        # No return after 2024-08-01 → still on loan
        assert check_loan_return(transfers, parent_api_id=33) is False


# ---------------------------------------------------------------------------
# classify_tracked_player — step 1.5 integration
# ---------------------------------------------------------------------------

class TestClassifyTrackedPlayerLoanReturn:
    """Verify classify_tracked_player respects loan return detection."""

    def _make_config(self) -> dict:
        return {
            "use_transfers_for_status": True,
            "inactivity_release_years": None,
            "use_squad_check": False,
        }

    def test_on_loan_without_return_stays_on_loan(self):
        """Player on loan with no return transfer → status = on_loan."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=56, in_name="Hull City",
            ),
        ]
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=56,
            current_club_name="Hull City",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=self._make_config(),
        )
        assert status == "on_loan"
        assert loan_id == 56
        assert loan_name == "Hull City"

    def test_recalled_player_status_overridden(self):
        """Wheatley scenario: loan return clears on_loan → academy/first_team."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=84, in_name="Northampton",
            ),
            _make_transfer(
                date="2025-01-12",
                transfer_type="Back From Loan",
                out_id=84, out_name="Northampton",
                in_id=33, in_name="Manchester United",
            ),
        ]
        # Journey data is stale — still shows Northampton as current club
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=84,           # stale: still shows Northampton
            current_club_name="Northampton",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=self._make_config(),
        )
        assert status != "on_loan", "Recalled player should not be on_loan"
        assert loan_id is None
        assert loan_name is None

    def test_recalled_player_reasoning_recorded(self):
        """with_reasoning=True should include the loan_return_check step."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=84, in_name="Northampton",
            ),
            _make_transfer(
                date="2025-01-12",
                transfer_type="Back From Loan",
                out_id=84, out_name="Northampton",
                in_id=33, in_name="Manchester United",
            ),
        ]
        status, loan_id, loan_name, reasoning = classify_tracked_player(
            current_club_api_id=84,
            current_club_name="Northampton",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=self._make_config(),
            with_reasoning=True,
        )
        rule_names = [r.get("rule") for r in reasoning]
        assert "loan_return_check" in rule_names, (
            f"Expected 'loan_return_check' in reasoning steps: {rule_names}"
        )
        assert status != "on_loan"

    def test_permanent_departure_still_detected(self):
        """upgrade_status_from_transfers (step 2) still fires for sold players."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Transfer",  # Permanent
                out_id=33, out_name="Manchester United",
                in_id=56, in_name="Hull City",
            ),
        ]
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=56,
            current_club_name="Hull City",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=self._make_config(),
        )
        # Permanent transfer → 'sold' (not 'on_loan')
        assert status == "sold"
        assert loan_id is None

    def test_collyer_still_on_loan_at_hull(self):
        """Collyer (no return transfer) should remain on_loan at Hull City."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=56, in_name="Hull City",
            ),
        ]
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=56,
            current_club_name="Hull City",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=self._make_config(),
        )
        assert status == "on_loan"
        assert loan_id == 56

    def test_first_team_player_at_parent_unchanged(self):
        """Mainoo at Man United (first team, no loan) → first_team, no change."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = []  # No outgoing transfers
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=33,
            current_club_name="Manchester United",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=self._make_config(),
        )
        assert status == "first_team"
        assert loan_id is None

    def test_cross_club_arsenal_loan_recall(self):
        """Arsenal academy player recalled from loan — should clear on_loan."""
        from src.utils.academy_classifier import classify_tracked_player

        # Hypothetical: Arsenal (42) player loaned to Brentford (55), recalled
        transfers = [
            _make_transfer(
                date="2024-08-15",
                transfer_type="Loan",
                out_id=42, out_name="Arsenal",
                in_id=55, in_name="Brentford",
            ),
            _make_transfer(
                date="2025-01-20",
                transfer_type="Return From Loan",
                out_id=55, out_name="Brentford",
                in_id=42, in_name="Arsenal",
            ),
        ]
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=55,           # stale entry still shows Brentford
            current_club_name="Brentford",
            current_level="First Team",
            parent_api_id=42,
            parent_club_name="Arsenal",
            transfers=transfers,
            config=self._make_config(),
        )
        assert status != "on_loan"
        assert loan_id is None

    def test_cross_club_chelsea_loan_no_recall(self):
        """Chelsea (49) player still on loan with no return → on_loan stays."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-07-01",
                transfer_type="Loan",
                out_id=49, out_name="Chelsea",
                in_id=57, in_name="Ipswich",
            ),
        ]
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=57,
            current_club_name="Ipswich",
            current_level="First Team",
            parent_api_id=49,
            parent_club_name="Chelsea",
            transfers=transfers,
            config=self._make_config(),
        )
        assert status == "on_loan"
        assert loan_id == 57

    def test_use_transfers_for_status_false_skips_check(self):
        """When use_transfers_for_status=False, step 1.5 is not applied."""
        from src.utils.academy_classifier import classify_tracked_player

        transfers = [
            _make_transfer(
                date="2024-08-01",
                transfer_type="Loan",
                out_id=33, out_name="Manchester United",
                in_id=84, in_name="Northampton",
            ),
            _make_transfer(
                date="2025-01-12",
                transfer_type="Back From Loan",
                out_id=84, out_name="Northampton",
                in_id=33, in_name="Manchester United",
            ),
        ]
        config = {
            "use_transfers_for_status": False,
            "inactivity_release_years": None,
            "use_squad_check": False,
        }
        status, loan_id, loan_name = classify_tracked_player(
            current_club_api_id=84,
            current_club_name="Northampton",
            current_level="First Team",
            parent_api_id=33,
            parent_club_name="Manchester United",
            transfers=transfers,
            config=config,
        )
        # Transfer checks disabled → stale on_loan persists
        assert status == "on_loan"


# ---------------------------------------------------------------------------
# _get_transfer_current_club_override — pure function tests
# ---------------------------------------------------------------------------

class TestGetTransferCurrentClubOverride:
    """Tests for the pure helper that detects transfer overrides."""

    def test_override_when_most_recent_transfer_differs(self):
        """Recall from Northampton: most-recent transfer → Man United → override."""
        from src.services.journey_sync import JourneySyncService

        transfers = [
            {
                "date": "2024-08-01",
                "type": "Loan",
                "teams": {
                    "out": {"id": 33, "name": "Manchester United"},
                    "in": {"id": 84, "name": "Northampton"},
                },
            },
            {
                "date": "2025-01-12",
                "type": "Back From Loan",
                "teams": {
                    "out": {"id": 84, "name": "Northampton"},
                    "in": {"id": 33, "name": "Manchester United"},
                },
            },
        ]
        # Journey still shows Northampton (84), but most recent transfer → 33
        result = JourneySyncService._get_transfer_current_club_override(84, transfers)
        assert result is not None
        assert result[0] == 33
        assert result[1] == "Manchester United"

    def test_no_override_when_transfer_matches_current(self):
        """Most-recent transfer destination matches current club → None."""
        from src.services.journey_sync import JourneySyncService

        transfers = [
            {
                "date": "2024-08-01",
                "type": "Loan",
                "teams": {
                    "out": {"id": 33, "name": "Manchester United"},
                    "in": {"id": 56, "name": "Hull City"},
                },
            },
        ]
        # Current club IS Hull City (56)
        result = JourneySyncService._get_transfer_current_club_override(56, transfers)
        assert result is None

    def test_no_override_when_transfers_is_none(self):
        """None transfers → None override."""
        from src.services.journey_sync import JourneySyncService

        result = JourneySyncService._get_transfer_current_club_override(84, None)
        assert result is None

    def test_no_override_when_transfers_is_empty(self):
        """Empty transfers list → None override."""
        from src.services.journey_sync import JourneySyncService

        result = JourneySyncService._get_transfer_current_club_override(84, [])
        assert result is None

    def test_no_override_when_transfers_have_no_date(self):
        """Transfers without dates are ignored."""
        from src.services.journey_sync import JourneySyncService

        transfers = [
            {
                "date": None,
                "type": "Loan",
                "teams": {
                    "out": {"id": 33, "name": "Manchester United"},
                    "in": {"id": 56, "name": "Hull City"},
                },
            },
        ]
        result = JourneySyncService._get_transfer_current_club_override(84, transfers)
        assert result is None

    def test_picks_most_recent_when_multiple_transfers(self):
        """Multiple transfers: latest date wins."""
        from src.services.journey_sync import JourneySyncService

        transfers = [
            # Older transfer to Hull
            {
                "date": "2023-07-01",
                "type": "Loan",
                "teams": {
                    "out": {"id": 33, "name": "Manchester United"},
                    "in": {"id": 56, "name": "Hull City"},
                },
            },
            # More recent transfer to Chelsea
            {
                "date": "2024-01-15",
                "type": "Transfer",
                "teams": {
                    "out": {"id": 56, "name": "Hull City"},
                    "in": {"id": 49, "name": "Chelsea"},
                },
            },
        ]
        # Current club still shows Hull (56) — most recent transfer → Chelsea (49)
        result = JourneySyncService._get_transfer_current_club_override(56, transfers)
        assert result is not None
        assert result[0] == 49
        assert result[1] == "Chelsea"

    def test_arsenal_player_transfer_override(self):
        """Arsenal player recalled: transfer override returns Arsenal ID (42)."""
        from src.services.journey_sync import JourneySyncService

        transfers = [
            {
                "date": "2024-08-15",
                "type": "Loan",
                "teams": {
                    "out": {"id": 42, "name": "Arsenal"},
                    "in": {"id": 55, "name": "Brentford"},
                },
            },
            {
                "date": "2025-01-20",
                "type": "Return From Loan",
                "teams": {
                    "out": {"id": 55, "name": "Brentford"},
                    "in": {"id": 42, "name": "Arsenal"},
                },
            },
        ]
        # Journey still shows Brentford (55)
        result = JourneySyncService._get_transfer_current_club_override(55, transfers)
        assert result is not None
        assert result[0] == 42
        assert result[1] == "Arsenal"
