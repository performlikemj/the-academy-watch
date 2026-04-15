"""
Tests for Player Journey functionality

Tests the journey models, sync service, and API endpoints.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


# Test the classification logic without database
class TestJourneyClassification:
    """Test level and entry type classification logic"""

    def test_classify_level_u18(self):
        """U18 teams should be classified correctly"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Various U18 patterns
        assert service._classify_level("Manchester United U18", "FA Youth Cup") == "U18"
        assert service._classify_level("Arsenal U18", "U18 Premier League - South") == "U18"
        assert service._classify_level("Chelsea Under 18", "Under-18 Premier League") == "U18"

    def test_classify_level_u21(self):
        """U21 teams should be classified correctly"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        assert service._classify_level("Manchester United U21", "EFL Trophy") == "U21"
        assert service._classify_level("Liverpool Under 21", "Under 21 League") == "U21"

    def test_classify_level_u23_pl2(self):
        """U23/PL2 teams should be classified correctly"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Premier League 2 is U23 level
        assert service._classify_level("Manchester Utd U23", "Premier League 2 Division One") == "U23"
        assert service._classify_level("Everton U23", "PL2") == "U23"
        assert service._classify_level("Arsenal U23", "Development League") == "U23"

    def test_classify_level_first_team(self):
        """First team entries should be classified correctly"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        assert service._classify_level("Manchester United", "Premier League") == "First Team"
        assert service._classify_level("Barcelona", "La Liga") == "First Team"
        assert service._classify_level("Bayern Munich", "Bundesliga") == "First Team"
        assert service._classify_level("Chelsea", "FA Cup") == "First Team"
        assert service._classify_level("Liverpool", "Champions League") == "First Team"

    def test_classify_level_international(self):
        """International entries should be classified correctly"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        assert service._classify_level("Argentina", "World Cup - Qualification") == "International"
        assert service._classify_level("England", "Euro 2024") == "International"
        assert service._classify_level("Brazil", "Copa America") == "International"
        assert service._classify_level("Spain", "Friendlies") == "International"

    def test_classify_level_international_youth(self):
        """International youth entries should be classified correctly"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        assert service._classify_level("Argentina U20", "U20 World Cup") == "International Youth"
        assert service._classify_level("England U21", "UEFA U21 Championship") == "International Youth"
        assert service._classify_level("Spain U19", "U19 Euro") == "International Youth"

    def test_is_international(self):
        """Test international detection"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        assert service._is_international("World Cup Qualification")
        assert service._is_international("Euro 2024")
        assert service._is_international("Copa America")
        assert not service._is_international("Premier League")
        assert not service._is_international("FA Youth Cup")


class TestJourneyEntryCreation:
    """Test creation of journey entries from API data"""

    def test_create_entry_from_stat(self):
        """Test creating entry from API-Football statistics block"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        stat = {
            "team": {"id": 33, "name": "Manchester United", "logo": "https://..."},
            "league": {"id": 39, "name": "Premier League", "country": "England", "logo": "https://..."},
            "games": {"appearences": 10, "minutes": 800},
            "goals": {"total": 3, "assists": 2},
        }

        entry = service._create_entry_from_stat(journey_id=1, season=2024, stat=stat)

        assert entry is not None
        assert entry.club_api_id == 33
        assert entry.club_name == "Manchester United"
        assert entry.league_name == "Premier League"
        assert entry.appearances == 10
        assert entry.goals == 3
        assert entry.assists == 2
        assert entry.level == "First Team"
        assert not entry.is_youth

    def test_create_entry_keeps_zero_appearances(self):
        """Entries with zero appearances should be kept (squad registration)"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        stat = {
            "team": {"id": 33, "name": "Manchester United", "logo": "https://..."},
            "league": {"id": 39, "name": "Premier League", "country": "England"},
            "games": {"appearences": 0, "minutes": 0},
            "goals": {"total": 0, "assists": 0},
        }

        entry = service._create_entry_from_stat(journey_id=1, season=2024, stat=stat)

        assert entry is not None
        assert entry.appearances == 0
        assert entry.club_name == "Manchester United"

    def test_create_entry_youth_flag(self):
        """Youth entries should have is_youth=True"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        stat = {
            "team": {"id": 1234, "name": "Manchester United U18", "logo": "https://..."},
            "league": {"id": 702, "name": "U18 Premier League", "country": "England"},
            "games": {"appearences": 10, "minutes": 800},
            "goals": {"total": 5, "assists": 3},
        }

        entry = service._create_entry_from_stat(journey_id=1, season=2021, stat=stat)

        assert entry is not None
        assert entry.level == "U18"
        assert entry.is_youth


class TestIsOfficialCompetition:
    """Test official competition filtering"""

    def setup_method(self):
        from src.services.journey_sync import JourneySyncService

        self.service = JourneySyncService(api_client=Mock())

    def test_non_null_league_id_is_official(self):
        """Entries with a league_id are always official"""
        stat = {
            "league": {"id": 39, "name": "Premier League"},
            "team": {"id": 33, "name": "Manchester United"},
        }
        assert self.service._is_official_competition(stat) is True

    def test_null_league_id_senior_team_filtered(self):
        """Null league_id + senior team = preseason/friendly, filtered out"""
        stat = {
            "league": {"id": None, "name": "PL Summer Series"},
            "team": {"id": 33, "name": "Manchester United"},
        }
        assert self.service._is_official_competition(stat) is False

    def test_null_league_id_youth_team_kept(self):
        """Null league_id + youth team = kept (FA Youth Cup etc.)"""
        stat = {
            "league": {"id": None, "name": "FA Youth Cup"},
            "team": {"id": 1234, "name": "Watford U18"},
        }
        assert self.service._is_official_competition(stat) is True

    def test_null_league_id_u21_team_kept(self):
        """Null league_id + U21 team = kept"""
        stat = {
            "league": {"id": None, "name": "Some Cup"},
            "team": {"id": 5678, "name": "Liverpool U21"},
        }
        assert self.service._is_official_competition(stat) is True

    def test_null_league_id_international_kept(self):
        """Null league_id + international = kept"""
        stat = {
            "league": {"id": None, "name": "World Cup - Qualification"},
            "team": {"id": 99, "name": "England"},
        }
        assert self.service._is_official_competition(stat) is True

    def test_missing_league_id_key_filtered(self):
        """Missing league id key (no 'id' in league dict) is treated as null"""
        stat = {
            "league": {"name": "Random Friendly"},
            "team": {"id": 33, "name": "Manchester United"},
        }
        assert self.service._is_official_competition(stat) is False

    def test_championship_with_league_id_kept(self):
        """Championship (non-top league) with league_id is kept"""
        stat = {
            "league": {"id": 40, "name": "Championship"},
            "team": {"id": 62, "name": "Sheffield Wednesday"},
        }
        assert self.service._is_official_competition(stat) is True


class TestDeduplicateEntries:
    """Test deduplication of journey entries"""

    def setup_method(self):
        from src.services.journey_sync import JourneySyncService

        self.service = JourneySyncService(api_client=Mock())

    def _make_entry(self, **kwargs):
        """Create a mock entry with defaults"""
        entry = MagicMock()
        entry.season = kwargs.get("season", 2024)
        entry.appearances = kwargs.get("appearances", 13)
        entry.minutes = kwargs.get("minutes", 346)
        entry.goals = kwargs.get("goals", 0)
        entry.assists = kwargs.get("assists", 0)
        entry.is_youth = kwargs.get("is_youth", False)
        entry.sort_priority = kwargs.get("sort_priority", 100)
        entry.club_name = kwargs.get("club_name", "Manchester United")
        entry.league_name = kwargs.get("league_name", "Premier League")
        return entry

    def test_no_duplicates_passes_through(self):
        """Entries with unique fingerprints pass through unchanged"""
        e1 = self._make_entry(appearances=10, minutes=800)
        e2 = self._make_entry(appearances=5, minutes=400)
        result = self.service._deduplicate_entries([e1, e2])
        assert len(result) == 2

    def test_identical_stats_youth_preferred(self):
        """When stats are identical, youth entry is preferred"""
        senior = self._make_entry(is_youth=False, sort_priority=100, club_name="Man Utd", league_name="Premier League")
        youth = self._make_entry(
            is_youth=True, sort_priority=20, club_name="Man Utd U18", league_name="U18 Premier League"
        )
        result = self.service._deduplicate_entries([senior, youth])
        assert len(result) == 1
        assert result[0] is youth

    def test_identical_stats_no_youth_lowest_priority_wins(self):
        """When no youth entry, lowest sort_priority wins"""
        e1 = self._make_entry(sort_priority=100, club_name="Team A", league_name="League A")
        e2 = self._make_entry(sort_priority=50, club_name="Team B", league_name="League B")
        result = self.service._deduplicate_entries([e1, e2])
        assert len(result) == 1
        assert result[0] is e2

    def test_three_duplicates_one_survives(self):
        """Three entries with same fingerprint → only one survives"""
        e1 = self._make_entry(sort_priority=100, club_name="A", league_name="L1")
        e2 = self._make_entry(is_youth=True, sort_priority=20, club_name="B U18", league_name="L2")
        e3 = self._make_entry(sort_priority=90, club_name="C", league_name="L3")
        result = self.service._deduplicate_entries([e1, e2, e3])
        assert len(result) == 1
        assert result[0] is e2

    def test_different_seasons_not_deduped(self):
        """Same stats in different seasons are not duplicates"""
        e1 = self._make_entry(season=2023)
        e2 = self._make_entry(season=2024)
        result = self.service._deduplicate_entries([e1, e2])
        assert len(result) == 2

    def test_empty_entries(self):
        """Empty list returns empty"""
        assert self.service._deduplicate_entries([]) == []


class TestBuildTransferTimeline:
    """Test building loan timeline from transfer records"""

    def setup_method(self):
        from src.services.journey_sync import JourneySyncService

        self.service = JourneySyncService(api_client=Mock())

    def test_simple_loan_and_return(self):
        """Loan start followed by loan return creates a period with end date"""
        transfers = [
            {
                "type": "Loan",
                "date": "2023-08-01",
                "teams": {
                    "out": {"id": 33, "name": "Manchester United"},
                    "in": {"id": 62, "name": "Sheffield Wednesday"},
                },
            },
            {
                "type": "End of loan",
                "date": "2024-06-30",
                "teams": {
                    "out": {"id": 62, "name": "Sheffield Wednesday"},
                    "in": {"id": 33, "name": "Manchester United"},
                },
            },
        ]
        timeline = self.service._build_transfer_timeline(transfers)
        assert len(timeline) == 1
        assert timeline[0]["club_id"] == 62
        assert timeline[0]["parent_club_id"] == 33
        assert timeline[0]["start_date"] == "2023-08-01"
        assert timeline[0]["end_date"] == "2024-06-30"

    def test_open_ended_loan(self):
        """Loan without return has end_date=None"""
        transfers = [
            {
                "type": "Loan",
                "date": "2024-01-15",
                "teams": {
                    "out": {"id": 33, "name": "Manchester United"},
                    "in": {"id": 71, "name": "Norwich City"},
                },
            },
        ]
        timeline = self.service._build_transfer_timeline(transfers)
        assert len(timeline) == 1
        assert timeline[0]["end_date"] is None

    def test_non_loan_transfers_ignored(self):
        """Permanent transfers and free transfers are ignored"""
        transfers = [
            {
                "type": "Transfer",
                "date": "2020-07-01",
                "teams": {
                    "out": {"id": 100, "name": "Watford"},
                    "in": {"id": 33, "name": "Manchester United"},
                },
            },
        ]
        timeline = self.service._build_transfer_timeline(transfers)
        assert len(timeline) == 0

    def test_multiple_loans(self):
        """Multiple loan periods tracked separately"""
        transfers = [
            {
                "type": "Loan",
                "date": "2023-08-01",
                "teams": {
                    "out": {"id": 33, "name": "Man Utd"},
                    "in": {"id": 62, "name": "Sheffield Wed"},
                },
            },
            {
                "type": "End of loan",
                "date": "2024-06-30",
                "teams": {
                    "out": {"id": 62, "name": "Sheffield Wed"},
                    "in": {"id": 33, "name": "Man Utd"},
                },
            },
            {
                "type": "Loan",
                "date": "2024-08-01",
                "teams": {
                    "out": {"id": 33, "name": "Man Utd"},
                    "in": {"id": 71, "name": "Norwich"},
                },
            },
        ]
        timeline = self.service._build_transfer_timeline(transfers)
        assert len(timeline) == 2
        assert timeline[0]["club_id"] == 62
        assert timeline[0]["end_date"] == "2024-06-30"
        assert timeline[1]["club_id"] == 71
        assert timeline[1]["end_date"] is None

    def test_empty_transfers(self):
        """Empty transfers list returns empty timeline"""
        assert self.service._build_transfer_timeline([]) == []


class TestLoanOverlapsSeason:
    """Test loan/season overlap detection"""

    def setup_method(self):
        from src.services.journey_sync import JourneySyncService

        self.service = JourneySyncService(api_client=Mock())

    def test_full_season_loan(self):
        """Loan covering entire season overlaps"""
        loan = {"start_date": "2023-07-01", "end_date": "2024-06-30"}
        assert self.service._loan_overlaps_season(loan, 2023) is True

    def test_loan_starts_mid_season(self):
        """January loan overlaps that season"""
        loan = {"start_date": "2024-01-15", "end_date": "2024-06-30"}
        assert self.service._loan_overlaps_season(loan, 2023) is True

    def test_loan_before_season(self):
        """Loan ending before season starts doesn't overlap"""
        loan = {"start_date": "2022-08-01", "end_date": "2023-05-30"}
        assert self.service._loan_overlaps_season(loan, 2023) is False

    def test_loan_after_season(self):
        """Loan starting after season ends doesn't overlap"""
        loan = {"start_date": "2025-08-01", "end_date": "2026-06-30"}
        assert self.service._loan_overlaps_season(loan, 2023) is False

    def test_open_ended_loan_overlaps_future(self):
        """Open-ended loan overlaps future seasons"""
        loan = {"start_date": "2023-08-01", "end_date": None}
        assert self.service._loan_overlaps_season(loan, 2023) is True
        assert self.service._loan_overlaps_season(loan, 2024) is True

    def test_no_start_date(self):
        """Missing start date returns False"""
        loan = {"start_date": "", "end_date": "2024-06-30"}
        assert self.service._loan_overlaps_season(loan, 2023) is False

    def test_loan_ends_exactly_season_start(self):
        """Loan ending exactly at season start boundary"""
        loan = {"start_date": "2022-08-01", "end_date": "2023-07-01"}
        assert self.service._loan_overlaps_season(loan, 2023) is True


class TestApplyLoanClassification:
    """Test loan classification of journey entries"""

    def setup_method(self):
        from src.services.journey_sync import JourneySyncService

        self.service = JourneySyncService(api_client=Mock())

    def _make_entry(self, **kwargs):
        entry = MagicMock()
        entry.club_api_id = kwargs.get("club_api_id", 33)
        entry.season = kwargs.get("season", 2023)
        entry.is_international = kwargs.get("is_international", False)
        entry.entry_type = kwargs.get("entry_type", "first_team")
        return entry

    def test_entry_at_loan_club_classified(self):
        """Entry at a loan club during loan period gets entry_type='loan' and transfer_date"""
        entry = self._make_entry(club_api_id=62, season=2023, entry_type="first_team")
        loan_timeline = [
            {
                "club_id": 62,
                "parent_club_id": 33,
                "start_date": "2023-08-01",
                "end_date": "2024-06-30",
            }
        ]
        self.service._apply_loan_classification([entry], loan_timeline)
        assert entry.entry_type == "loan"
        assert entry.transfer_date == "2023-08-01"

    def test_entry_at_parent_club_not_classified(self):
        """Entry at parent club is not classified as loan"""
        entry = self._make_entry(club_api_id=33, season=2023, entry_type="first_team")
        loan_timeline = [
            {
                "club_id": 62,
                "parent_club_id": 33,
                "start_date": "2023-08-01",
                "end_date": "2024-06-30",
            }
        ]
        self.service._apply_loan_classification([entry], loan_timeline)
        assert entry.entry_type == "first_team"

    def test_international_entries_skipped(self):
        """International entries are never classified as loans"""
        entry = self._make_entry(club_api_id=62, season=2023, is_international=True, entry_type="international")
        loan_timeline = [
            {
                "club_id": 62,
                "parent_club_id": 33,
                "start_date": "2023-08-01",
                "end_date": "2024-06-30",
            }
        ]
        self.service._apply_loan_classification([entry], loan_timeline)
        assert entry.entry_type == "international"

    def test_empty_timeline_no_changes(self):
        """Empty loan timeline makes no changes"""
        entry = self._make_entry(entry_type="first_team")
        self.service._apply_loan_classification([entry], [])
        assert entry.entry_type == "first_team"

    def test_entry_outside_loan_period_not_classified(self):
        """Entry at loan club but outside loan period is not classified"""
        entry = self._make_entry(club_api_id=62, season=2022, entry_type="first_team")
        loan_timeline = [
            {
                "club_id": 62,
                "parent_club_id": 33,
                "start_date": "2023-08-01",
                "end_date": "2024-06-30",
            }
        ]
        self.service._apply_loan_classification([entry], loan_timeline)
        assert entry.entry_type == "first_team"


class TestCurrentClubTiebreaker:
    """Test that current club is determined by transfer_date when sort_priority ties"""

    def test_later_transfer_date_wins(self):
        """When two First Team entries share a season, the one with the later transfer_date wins"""
        from src.models.journey import LEVEL_PRIORITY
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Sheffield Wed: loaned Aug 2025
        shef = MagicMock()
        shef.season = 2025
        shef.club_api_id = 62
        shef.club_name = "Sheffield Wednesday"
        shef.level = "First Team"
        shef.entry_type = "loan"
        shef.is_youth = False
        shef.is_international = False
        shef.appearances = 21
        shef.goals = 1
        shef.assists = 1
        shef.sort_priority = LEVEL_PRIORITY["First Team"]
        shef.transfer_date = "2025-08-01"

        # Norwich: loaned Jan 2026
        norw = MagicMock()
        norw.season = 2025
        norw.club_api_id = 71
        norw.club_name = "Norwich"
        norw.level = "First Team"
        norw.entry_type = "loan"
        norw.is_youth = False
        norw.is_international = False
        norw.appearances = 1
        norw.goals = 0
        norw.assists = 0
        norw.sort_priority = LEVEL_PRIORITY["First Team"]
        norw.transfer_date = "2026-01-15"

        mock_journey = MagicMock()
        mock_journey.id = 1

        with patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry:
            MockEntry.query.filter_by.return_value.all.return_value = [shef, norw]
            service._update_journey_aggregates(mock_journey)

        assert mock_journey.current_club_api_id == 71
        assert mock_journey.current_club_name == "Norwich"

    def test_no_transfer_date_falls_back_gracefully(self):
        """Entries without transfer_date still work (empty string tiebreaker)"""
        from src.models.journey import LEVEL_PRIORITY
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        entry = MagicMock()
        entry.season = 2025
        entry.club_api_id = 33
        entry.club_name = "Manchester United"
        entry.level = "First Team"
        entry.entry_type = "first_team"
        entry.is_youth = False
        entry.is_international = False
        entry.appearances = 5
        entry.goals = 0
        entry.assists = 0
        entry.sort_priority = LEVEL_PRIORITY["First Team"]
        entry.transfer_date = None

        mock_journey = MagicMock()
        mock_journey.id = 1

        with patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry:
            MockEntry.query.filter_by.return_value.all.return_value = [entry]
            service._update_journey_aggregates(mock_journey)

        assert mock_journey.current_club_api_id == 33
        assert mock_journey.current_club_name == "Manchester United"


class TestDeriveCurrentLevelFromClubName:
    """Test the helper that derives current_level from a destination club name.

    Added after the O. Hammond incident where the transfer-override path in
    _update_journey_aggregates was hardcoding current_level='First Team'
    even when the destination was a youth team.
    """

    def test_u21_destination(self):
        from src.services.journey_sync import _derive_current_level_from_club_name

        assert _derive_current_level_from_club_name("Nottingham Forest U21") == "U21"

    def test_u18_destination(self):
        from src.services.journey_sync import _derive_current_level_from_club_name

        assert _derive_current_level_from_club_name("Arsenal U18") == "U18"

    def test_reserves_destination(self):
        from src.services.journey_sync import _derive_current_level_from_club_name

        assert _derive_current_level_from_club_name("Manchester City Reserves") == "Reserve"

    def test_plain_club_returns_first_team(self):
        from src.services.journey_sync import _derive_current_level_from_club_name

        assert _derive_current_level_from_club_name("Nottingham Forest") == "First Team"

    def test_none_falls_back(self):
        from src.services.journey_sync import _derive_current_level_from_club_name

        assert _derive_current_level_from_club_name(None) == "First Team"

    def test_custom_fallback(self):
        from src.services.journey_sync import _derive_current_level_from_club_name

        assert _derive_current_level_from_club_name("Arsenal", fallback="U21") == "U21"


@pytest.mark.usefixtures("app")
class TestTransferOverrideStaleness:
    """Regression tests for the O. Hammond bug in _update_journey_aggregates.

    Before the fix, a stale 2024 'N/A' transfer from Cheltenham to
    'Nottingham Forest U21' was overriding 2025 Oldham entries, causing
    O. Hammond (api 325967) to be classified as first_team at Nottingham
    Forest even though his latest actual stats are at Oldham.

    Uses the `app` fixture from conftest.py so _update_journey_aggregates
    (which touches db.session via helpers like _compute_academy_club_ids)
    has a Flask application context.
    """

    def _mock_entry(
        self,
        *,
        season,
        club_api_id,
        club_name,
        level="First Team",
        entry_type="first_team",
        appearances=1,
        sort_priority=None,
        transfer_date=None,
    ):
        from src.models.journey import LEVEL_PRIORITY

        e = MagicMock()
        e.season = season
        e.club_api_id = club_api_id
        e.club_name = club_name
        e.level = level
        e.entry_type = entry_type
        e.is_youth = level != "First Team"
        e.is_international = False
        e.appearances = appearances
        e.goals = 0
        e.assists = 0
        e.minutes = 0
        e.sort_priority = sort_priority if sort_priority is not None else LEVEL_PRIORITY.get(level, 0)
        e.transfer_date = transfer_date
        return e

    def test_stale_transfer_does_not_override_fresher_entries(self):
        """The Hammond scenario: a 2024 N/A transfer back to Forest U21 must
        NOT overwrite 2025 Oldham entries."""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # 2025 Oldham first-team entries (the true latest state)
        oldham_2025 = self._mock_entry(
            season=2025,
            club_api_id=1349,
            club_name="Oldham",
            level="First Team",
            entry_type="first_team",
            appearances=16,
            transfer_date="2025-08-15",
        )
        # 2023 Forest U21 entry (earlier)
        forest_u21_2023 = self._mock_entry(
            season=2023,
            club_api_id=19746,
            club_name="Nottingham Forest U21",
            level="U21",
            entry_type="development",
            appearances=1,
            transfer_date="2024-01-02",
        )

        transfers = [
            # The exact pathological transfer Hammond has on prod
            {
                "date": "2024-01-02",
                "type": "N/A",
                "teams": {
                    "out": {"id": 1943, "name": "Cheltenham"},
                    "in": {"id": 19746, "name": "Nottingham Forest U21"},
                },
            },
            {
                "date": "2023-08-01",
                "type": "Loan",
                "teams": {"out": {"id": 65, "name": "Nottingham Forest"}, "in": {"id": 1943, "name": "Cheltenham"}},
            },
        ]

        journey = MagicMock()
        journey.id = 1
        journey.player_api_id = 325967

        with (
            patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry,
            patch.object(service, "_compute_academy_club_ids"),
        ):
            MockEntry.query.filter_by.return_value.all.return_value = [
                oldham_2025,
                forest_u21_2023,
            ]
            service._update_journey_aggregates(journey, transfers=transfers)

        # The stale 2024 transfer must NOT pull current_club back to Forest U21.
        assert journey.current_club_api_id == 1349
        assert journey.current_club_name == "Oldham"
        assert journey.current_level == "First Team"

    def test_na_typed_transfer_is_ignored(self):
        """N/A transfer types are ambiguous and must never drive overrides,
        even when they are newer than the latest entry."""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        entry = self._mock_entry(
            season=2024,
            club_api_id=1349,
            club_name="Oldham",
            transfer_date="2024-08-01",
        )
        transfers = [
            # Newer than the entry, but type=N/A — must be skipped
            {
                "date": "2025-01-15",
                "type": "N/A",
                "teams": {"out": {"id": 1349, "name": "Oldham"}, "in": {"id": 19746, "name": "Nottingham Forest U21"}},
            },
        ]

        journey = MagicMock()
        journey.id = 2
        journey.player_api_id = 2

        with (
            patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry,
            patch.object(service, "_compute_academy_club_ids"),
        ):
            MockEntry.query.filter_by.return_value.all.return_value = [entry]
            service._update_journey_aggregates(journey, transfers=transfers)

        assert journey.current_club_api_id == 1349
        assert journey.current_club_name == "Oldham"

    def test_loan_return_derives_level_from_destination(self):
        """A loan return to a youth team must set current_level from the
        destination, not hardcode 'First Team'."""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        entry = self._mock_entry(
            season=2024,
            club_api_id=1234,
            club_name="Some Loan Club",
            transfer_date="2024-08-01",
        )
        transfers = [
            {
                "date": "2025-12-30",
                "type": "Return from loan",
                "teams": {
                    "out": {"id": 1234, "name": "Some Loan Club"},
                    "in": {"id": 19746, "name": "Nottingham Forest U21"},
                },
            },
        ]

        journey = MagicMock()
        journey.id = 3
        journey.player_api_id = 3

        with (
            patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry,
            patch.object(service, "_compute_academy_club_ids"),
        ):
            MockEntry.query.filter_by.return_value.all.return_value = [entry]
            service._update_journey_aggregates(journey, transfers=transfers)

        assert journey.current_club_api_id == 19746
        assert journey.current_club_name == "Nottingham Forest U21"
        # Level must reflect that the destination is a U21 team
        assert journey.current_level == "U21"

    def test_newer_valid_transfer_still_overrides(self):
        """The existing 'stats show Real Madrid but on loan at Lyon' use case
        must keep working — a valid newer transfer still overrides stats."""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Stats show player at Real Madrid in 2025
        entry = self._mock_entry(
            season=2025,
            club_api_id=541,
            club_name="Real Madrid",
            transfer_date="2025-07-01",
        )
        # Jan 2026 loan to Lyon — newer than stats, valid loan type
        transfers = [
            {
                "date": "2026-01-15",
                "type": "Loan",
                "teams": {"out": {"id": 541, "name": "Real Madrid"}, "in": {"id": 80, "name": "Lyon"}},
            },
        ]

        journey = MagicMock()
        journey.id = 4
        journey.player_api_id = 4

        with (
            patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry,
            patch.object(service, "_compute_academy_club_ids"),
        ):
            MockEntry.query.filter_by.return_value.all.return_value = [entry]
            service._update_journey_aggregates(journey, transfers=transfers)

        assert journey.current_club_api_id == 80
        assert journey.current_club_name == "Lyon"


class TestUpdateAggregatesWithLoans:
    """Test that _update_journey_aggregates counts loan apps"""

    def test_total_loan_apps_populated(self):
        """total_loan_apps should sum appearances of loan entries"""
        from src.models.journey import LEVEL_PRIORITY
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Create mock entries
        loan_entry = MagicMock()
        loan_entry.season = 2023
        loan_entry.club_api_id = 62
        loan_entry.club_name = "Sheffield Wednesday"
        loan_entry.level = "First Team"
        loan_entry.entry_type = "loan"
        loan_entry.is_youth = False
        loan_entry.is_international = False
        loan_entry.appearances = 21
        loan_entry.goals = 0
        loan_entry.assists = 1
        loan_entry.sort_priority = LEVEL_PRIORITY["First Team"]

        first_team_entry = MagicMock()
        first_team_entry.season = 2024
        first_team_entry.club_api_id = 33
        first_team_entry.club_name = "Manchester United"
        first_team_entry.level = "First Team"
        first_team_entry.entry_type = "first_team"
        first_team_entry.is_youth = False
        first_team_entry.is_international = False
        first_team_entry.appearances = 5
        first_team_entry.goals = 0
        first_team_entry.assists = 0
        first_team_entry.sort_priority = LEVEL_PRIORITY["First Team"]

        # Mock the query to return our entries
        mock_journey = MagicMock()
        mock_journey.id = 1

        with patch("src.services.journey_sync.PlayerJourneyEntry") as MockEntry:
            MockEntry.query.filter_by.return_value.all.return_value = [loan_entry, first_team_entry]
            service._update_journey_aggregates(mock_journey)

        assert mock_journey.total_loan_apps == 21
        assert mock_journey.total_first_team_apps == 26


class TestClubLocationSeeding:
    """Test club location seeding"""

    def test_seed_data_structure(self):
        """Verify the seeded club data has correct structure"""
        from src.services.journey_sync import seed_club_locations

        # Just verify the function exists and MAJOR_CLUBS constant is accessible
        # Full seeding test requires database context
        assert callable(seed_club_locations)


class TestJourneyModelMethods:
    """Test journey model methods"""

    def test_level_priority_values(self):
        """Verify level priority values are set correctly"""
        from src.models.journey import LEVEL_PRIORITY

        # First team should have highest priority
        assert LEVEL_PRIORITY["First Team"] == 100
        assert LEVEL_PRIORITY["International"] == 90
        assert LEVEL_PRIORITY["U23"] == 50
        assert LEVEL_PRIORITY["U18"] == 20

        # Higher levels should have higher priority
        assert LEVEL_PRIORITY["First Team"] > LEVEL_PRIORITY["U23"]
        assert LEVEL_PRIORITY["U23"] > LEVEL_PRIORITY["U21"]
        assert LEVEL_PRIORITY["U21"] > LEVEL_PRIORITY["U18"]

    def test_youth_levels_set(self):
        """Verify youth levels are correctly defined"""
        from src.models.journey import YOUTH_LEVELS

        assert "U18" in YOUTH_LEVELS
        assert "U19" in YOUTH_LEVELS
        assert "U21" in YOUTH_LEVELS
        assert "U23" in YOUTH_LEVELS
        assert "Reserve" in YOUTH_LEVELS
        assert "First Team" not in YOUTH_LEVELS


# Integration tests (require database)
@pytest.mark.integration
class TestJourneyIntegration:
    """Integration tests that require database context"""

    @pytest.fixture
    def app(self):
        """Create test Flask app"""
        from src.main import app

        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()

    @pytest.mark.skip(reason="Requires database setup")
    def test_journey_api_endpoint(self, client):
        """Test journey API endpoint"""
        response = client.get("/api/players/284324/journey")

        # Should return 200 or 404
        assert response.status_code in [200, 404]

    @pytest.mark.skip(reason="Requires database setup")
    def test_journey_map_endpoint(self, client):
        """Test journey map API endpoint"""
        response = client.get("/api/players/284324/journey/map")

        assert response.status_code in [200, 404]

    @pytest.mark.skip(reason="Requires database setup")
    def test_club_locations_endpoint(self, client):
        """Test club locations API endpoint"""
        response = client.get("/api/club-locations")

        assert response.status_code == 200
        data = response.get_json()
        assert "locations" in data
        assert "count" in data


class TestUpgradeStatusFromTransfers:
    """Test the upgrade_status_from_transfers shared utility"""

    def test_non_loan_status_unchanged(self):
        """Non-loan statuses pass through unchanged"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        assert upgrade_status_from_transfers("academy", [], 33) == "academy"
        assert upgrade_status_from_transfers("first_team", [], 33) == "first_team"
        assert upgrade_status_from_transfers("sold", [], 33) == "sold"

    def test_on_loan_no_transfers_unchanged(self):
        """on_loan with no transfers stays on_loan"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        assert upgrade_status_from_transfers("on_loan", [], 33) == "on_loan"

    def test_on_loan_with_loan_transfer_stays_loan(self):
        """on_loan with a loan departure stays on_loan"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "Loan",
                "date": "2024-08-01",
                "teams": {"out": {"id": 33}, "in": {"id": 62}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "on_loan"

    def test_permanent_transfer_becomes_sold(self):
        """Permanent transfer departure upgrades to sold"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "Transfer",
                "date": "2025-01-15",
                "teams": {"out": {"id": 33}, "in": {"id": 100}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "sold"

    def test_free_agent_becomes_released(self):
        """Free agent departure upgrades to released"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "Free Agent",
                "date": "2026-01-14",
                "teams": {"out": {"id": 33}, "in": {"id": 200}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "released"

    def test_free_lowercase_becomes_released(self):
        """'free' departure type also upgrades to released"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "free",
                "date": "2026-01-14",
                "teams": {"out": {"id": 33}, "in": {"id": 200}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "released"

    def test_na_becomes_released(self):
        """N/A departure type upgrades to released"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "N/A",
                "date": "2025-06-30",
                "teams": {"out": {"id": 33}, "in": {"id": 200}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "released"

    def test_latest_departure_wins(self):
        """When multiple departures exist, the latest one determines status"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "Loan",
                "date": "2023-08-01",
                "teams": {"out": {"id": 33}, "in": {"id": 62}},
            },
            {
                "type": "Free Agent",
                "date": "2026-01-14",
                "teams": {"out": {"id": 33}, "in": {"id": 200}},
            },
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "released"

    def test_no_departures_from_parent_unchanged(self):
        """Transfers from other clubs don't affect status"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "Transfer",
                "date": "2025-01-15",
                "teams": {"out": {"id": 99}, "in": {"id": 33}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "on_loan"

    def test_empty_type_unchanged(self):
        """Empty departure type doesn't change status"""
        from src.utils.academy_classifier import upgrade_status_from_transfers

        transfers = [
            {
                "type": "",
                "date": "2025-01-15",
                "teams": {"out": {"id": 33}, "in": {"id": 100}},
            }
        ]
        assert upgrade_status_from_transfers("on_loan", transfers, 33) == "on_loan"


class TestComputeAcademyClubIdsExcludesIntegration:
    """Test that _compute_academy_club_ids excludes integration entries"""

    def _make_entry(self, **kwargs):
        entry = MagicMock()
        entry.is_youth = kwargs.get("is_youth", True)
        entry.is_international = kwargs.get("is_international", False)
        entry.entry_type = kwargs.get("entry_type", "academy")
        entry.club_name = kwargs.get("club_name", "Arsenal U21")
        entry.club_api_id = kwargs.get("club_api_id", 1234)
        return entry

    def test_academy_entries_included(self):
        """Academy entries are included in academy ID computation"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        academy_entry = self._make_entry(
            is_youth=True,
            entry_type="academy",
            club_name="Arsenal U21",
            club_api_id=1234,
        )
        senior_entry = self._make_entry(
            is_youth=False,
            entry_type="first_team",
            club_name="Arsenal",
            club_api_id=42,
        )

        mock_journey = MagicMock()
        mock_journey.id = 1
        mock_journey.player_api_id = 999

        with patch("src.services.journey_sync.PlayerJourneyEntry"):
            with patch("src.services.journey_sync.TeamProfile") as MockTP:
                MockTP.query.filter.return_value.first.return_value = None
                with patch("src.services.journey_sync.Team") as MockTeam:
                    MockTeam.query.filter.return_value.first.return_value = None
                    with patch.object(service, "_upsert_tracked_players"):
                        service._compute_academy_club_ids(mock_journey, entries=[academy_entry, senior_entry])

        # Arsenal (42) should be in academy_club_ids via senior_name_to_id lookup
        assert 42 in mock_journey.academy_club_ids

    def test_integration_entries_excluded(self):
        """Integration entries should NOT be counted for academy ID computation"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Heaven scenario: integration entry at Man Utd U21
        integration_entry = self._make_entry(
            is_youth=True,
            entry_type="integration",
            club_name="Manchester United U21",
            club_api_id=5678,
        )
        senior_entry = self._make_entry(
            is_youth=False,
            entry_type="first_team",
            club_name="Manchester United",
            club_api_id=33,
        )

        mock_journey = MagicMock()
        mock_journey.id = 1
        mock_journey.player_api_id = 999

        with patch("src.services.journey_sync.PlayerJourneyEntry"):
            with patch.object(service, "_upsert_tracked_players"):
                service._compute_academy_club_ids(mock_journey, entries=[integration_entry, senior_entry])

        # Man Utd (33) should NOT be in academy_club_ids because the youth
        # entry is entry_type='integration', not 'academy' or 'development'
        assert mock_journey.academy_club_ids == []

    def test_development_entries_included(self):
        """Development entries (genuine academy + first team at same club) ARE included"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        dev_entry = self._make_entry(
            is_youth=True,
            entry_type="development",
            club_name="Manchester United U19",
            club_api_id=9999,
        )
        senior_entry = self._make_entry(
            is_youth=False,
            entry_type="first_team",
            club_name="Manchester United",
            club_api_id=33,
        )

        mock_journey = MagicMock()
        mock_journey.id = 1
        mock_journey.player_api_id = 999

        with patch("src.services.journey_sync.PlayerJourneyEntry"):
            with patch("src.services.journey_sync.TeamProfile") as MockTP:
                MockTP.query.filter.return_value.first.return_value = None
                with patch("src.services.journey_sync.Team") as MockTeam:
                    MockTeam.query.filter.return_value.first.return_value = None
                    with patch.object(service, "_upsert_tracked_players"):
                        service._compute_academy_club_ids(mock_journey, entries=[dev_entry, senior_entry])

        # Man Utd (33) should be included because development entries are genuine academy
        assert 33 in mock_journey.academy_club_ids


class TestUpsertTrackedPlayersDeactivatesStaleRows:
    """Test that _upsert_tracked_players deactivates rows when academy connection is removed"""

    def test_stale_row_deactivated_when_academy_id_removed(self):
        """TrackedPlayer row is deactivated when its team is no longer in academy_ids"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Existing active TrackedPlayer for Man Utd (team_id=33)
        stale_tp = MagicMock()
        stale_tp.is_active = True
        stale_tp.data_source = "journey-sync"
        stale_tp.team = MagicMock()
        stale_tp.team.team_id = 33  # API-Football ID

        mock_journey = MagicMock()
        mock_journey.player_api_id = 999

        with (
            patch("src.models.tracked_player.TrackedPlayer") as MockTP,
            patch("src.utils.academy_classifier.derive_player_status"),
        ):
            MockTP.query.filter_by.return_value.all.return_value = [stale_tp]
            # academy_ids is empty → Man Utd row should be deactivated
            service._upsert_tracked_players(mock_journey, academy_ids=set())

        assert stale_tp.is_active is False

    def test_valid_row_not_deactivated(self):
        """TrackedPlayer row is kept active when its team is still in academy_ids"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        valid_tp = MagicMock()
        valid_tp.is_active = True
        valid_tp.data_source = "journey-sync"
        valid_tp.team = MagicMock()
        valid_tp.team.team_id = 42  # Arsenal API-Football ID

        mock_journey = MagicMock()
        mock_journey.player_api_id = 999

        with (
            patch("src.models.tracked_player.TrackedPlayer") as MockTP,
            patch("src.utils.academy_classifier.derive_player_status", return_value=("academy", None, None)),
            patch("src.utils.academy_classifier.upgrade_status_from_transfers", return_value="academy"),
            patch("src.services.journey_sync.Team") as MockTeam,
        ):
            MockTP.query.filter_by.return_value.all.return_value = [valid_tp]
            # Arsenal still in academy_ids
            mock_team_row = MagicMock()
            mock_team_row.id = 1
            mock_team_row.name = "Arsenal"
            MockTeam.query.filter_by.return_value.order_by.return_value.first.return_value = mock_team_row
            MockTP.query.filter_by.return_value.first.return_value = MagicMock()  # existing row

            service._upsert_tracked_players(mock_journey, academy_ids={42})

        assert valid_tp.is_active is True

    def test_non_journey_sync_rows_untouched(self):
        """Rows with data_source != 'journey-sync' are not affected"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # This row was created by api-football seed, not journey-sync
        seed_tp = MagicMock()
        seed_tp.is_active = True
        seed_tp.data_source = "api-football"
        seed_tp.team = MagicMock()
        seed_tp.team.team_id = 33

        mock_journey = MagicMock()
        mock_journey.player_api_id = 999

        with (
            patch("src.models.tracked_player.TrackedPlayer") as MockTP,
            patch("src.utils.academy_classifier.derive_player_status"),
        ):
            # filter_by uses data_source='journey-sync', so seed row won't appear
            MockTP.query.filter_by.return_value.all.return_value = []
            service._upsert_tracked_players(mock_journey, academy_ids=set())

        # Seed row's is_active should never have been touched
        assert seed_tp.is_active is True

    def test_shrinking_academy_ids_deactivates_removed_only(self):
        """When academy_ids shrinks, only removed teams get deactivated"""
        from src.services.journey_sync import JourneySyncService

        service = JourneySyncService(api_client=Mock())

        # Two existing rows: Arsenal (42) and Man Utd (33)
        arsenal_tp = MagicMock()
        arsenal_tp.is_active = True
        arsenal_tp.data_source = "journey-sync"
        arsenal_tp.team = MagicMock()
        arsenal_tp.team.team_id = 42

        manutd_tp = MagicMock()
        manutd_tp.is_active = True
        manutd_tp.data_source = "journey-sync"
        manutd_tp.team = MagicMock()
        manutd_tp.team.team_id = 33

        mock_journey = MagicMock()
        mock_journey.player_api_id = 999

        with (
            patch("src.models.tracked_player.TrackedPlayer") as MockTP,
            patch("src.utils.academy_classifier.derive_player_status", return_value=("academy", None, None)),
            patch("src.utils.academy_classifier.upgrade_status_from_transfers", return_value="academy"),
            patch("src.services.journey_sync.Team") as MockTeam,
        ):
            MockTP.query.filter_by.return_value.all.return_value = [arsenal_tp, manutd_tp]
            # Only Arsenal remains in academy_ids
            mock_team_row = MagicMock()
            mock_team_row.id = 1
            mock_team_row.name = "Arsenal"
            MockTeam.query.filter_by.return_value.order_by.return_value.first.return_value = mock_team_row
            MockTP.query.filter_by.return_value.first.return_value = MagicMock()

            service._upsert_tracked_players(mock_journey, academy_ids={42})

        assert arsenal_tp.is_active is True
        assert manutd_tp.is_active is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
