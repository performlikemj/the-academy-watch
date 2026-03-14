"""
Cohort Service

Discovers academy cohorts from API-Football, syncs player journeys,
and calculates "where are they now" analytics.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import or_

from src.models.league import db
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.api_football_client import APIFootballClient
from src.services.journey_sync import JourneySyncService
from src.utils.academy_classifier import classify_tracked_player, strip_youth_suffix

logger = logging.getLogger(__name__)


class CohortService:
    """Service for discovering and managing academy cohorts"""

    def __init__(self, api_client: Optional[APIFootballClient] = None):
        self.api = api_client or APIFootballClient()

    def discover_cohort(
        self,
        team_api_id: int,
        league_api_id: int,
        season: int,
        fallback_team_name: str = None,
        fallback_league_name: str = None,
        query_team_api_id: int | None = None,
        heartbeat_fn=None,
    ) -> AcademyCohort:
        """
        Discover players in a youth league/season for a team.

        Idempotent: returns existing cohort if already seeded.
        Creates AcademyCohort + CohortMember records with cohort stats.

        Args:
            team_api_id: API-Football team ID
            league_api_id: API-Football league ID
            season: Season year

        Returns:
            AcademyCohort record
        """
        query_team_id = int(query_team_api_id or team_api_id)
        logger.info(
            "Discovering cohort: parent_team=%s query_team=%s league=%s season=%s",
            team_api_id,
            query_team_id,
            league_api_id,
            season,
        )

        # Check for existing cohort (idempotent)
        existing = AcademyCohort.query.filter_by(
            team_api_id=team_api_id,
            league_api_id=league_api_id,
            season=season
        ).first()

        if existing and existing.sync_status != 'failed':
            # Allow re-seeding if cohort has no members (API may have
            # returned nothing on a previous attempt due to rate limits
            # or transient errors).
            member_count = CohortMember.query.filter_by(cohort_id=existing.id).count()
            if member_count > 0:
                logger.info(f"Cohort already exists (id={existing.id}, status={existing.sync_status})")
                return existing
            logger.info(f"Re-seeding empty cohort id={existing.id}")

        try:
            # Create or reset cohort
            if existing:
                cohort = existing
                cohort.sync_status = 'seeding'
                cohort.sync_error = None
            else:
                cohort = AcademyCohort(
                    team_api_id=team_api_id,
                    league_api_id=league_api_id,
                    season=season,
                    sync_status='seeding'
                )
                db.session.add(cohort)
                db.session.flush()

            # Fetch players from API-Football (paginated)
            page = 1
            total_pages = 1
            players_added = 0

            while page <= total_pages:
                response = self.api._make_request('players', {
                    'team': query_team_id,
                    'league': league_api_id,
                    'season': season,
                    'page': page
                })

                paging = response.get('paging', {})
                total_pages = paging.get('total', 1)

                # Set team/league info from first response
                if page == 1:
                    results = response.get('response', [])
                    if results:
                        first_player = results[0]
                        stats = first_player.get('statistics', [{}])
                        if stats:
                            stat = stats[0]
                            team_info = stat.get('team', {})
                            league_info = stat.get('league', {})
                            cohort.team_name = team_info.get('name')
                            cohort.team_logo = team_info.get('logo')
                            cohort.league_name = league_info.get('name')

                for player_data in response.get('response', []):
                    player = player_data.get('player', {})
                    stats_list = player_data.get('statistics', [])

                    player_api_id = player.get('id')
                    if not player_api_id:
                        continue

                    # Check for existing member (for re-seeding failed cohorts)
                    existing_member = CohortMember.query.filter_by(
                        cohort_id=cohort.id,
                        player_api_id=player_api_id
                    ).first()
                    if existing_member:
                        continue

                    # Extract stats from first statistics entry
                    appearances = 0
                    goals = 0
                    assists = 0
                    minutes = 0
                    position = None
                    if stats_list:
                        stat = stats_list[0]
                        games = stat.get('games', {})
                        goals_data = stat.get('goals', {})
                        appearances = games.get('appearences') or games.get('appearances') or 0
                        goals = goals_data.get('total') or 0
                        assists = goals_data.get('assists') or 0
                        minutes = games.get('minutes') or 0
                        position = games.get('position')

                    member = CohortMember(
                        cohort_id=cohort.id,
                        player_api_id=player_api_id,
                        player_name=player.get('name'),
                        player_photo=player.get('photo'),
                        nationality=player.get('nationality'),
                        birth_date=player.get('birth', {}).get('date'),
                        position=position,
                        appearances_in_cohort=appearances,
                        goals_in_cohort=goals,
                        assists_in_cohort=assists,
                        minutes_in_cohort=minutes,
                    )
                    db.session.add(member)
                    players_added += 1

                if heartbeat_fn:
                    heartbeat_fn()
                page += 1

            cohort.total_players = CohortMember.query.filter_by(cohort_id=cohort.id).count()
            if cohort.team_name:
                cohort.team_name = strip_youth_suffix(cohort.team_name)

            # Preserve parent club display naming when querying youth teams.
            if query_team_id != team_api_id and fallback_team_name:
                cohort.team_name = fallback_team_name

            # Apply fallback names if the API didn't return any data
            if not cohort.team_name and fallback_team_name:
                cohort.team_name = fallback_team_name
            if not cohort.league_name and fallback_league_name:
                cohort.league_name = fallback_league_name
            cohort.seeded_at = datetime.now(timezone.utc)
            if cohort.total_players == 0:
                cohort.sync_status = 'no_data'
                cohort.sync_error = (
                    f"No cohort players returned for query_team={query_team_id}, "
                    f"league={league_api_id}, season={season}"
                )
                db.session.commit()
                logger.warning(
                    "Empty cohort discovered id=%s parent=%s query_team=%s league=%s season=%s",
                    cohort.id,
                    team_api_id,
                    query_team_id,
                    league_api_id,
                    season,
                )
                return cohort

            cohort.sync_status = 'seeded'
            db.session.commit()

            logger.info(f"Discovered cohort id={cohort.id}: {players_added} players")
            return cohort

        except Exception as e:
            logger.error(f"Failed to discover cohort: {e}")
            db.session.rollback()

            try:
                cohort = AcademyCohort.query.filter_by(
                    team_api_id=team_api_id,
                    league_api_id=league_api_id,
                    season=season
                ).first()
                if cohort:
                    cohort.sync_status = 'failed'
                    cohort.sync_error = str(e)
                    db.session.commit()
            except Exception:
                pass

            raise

    def sync_cohort_journeys(self, cohort_id: int) -> AcademyCohort:
        """
        Sync journeys for all members in a cohort.

        Reuses JourneySyncService for each member, then updates
        the "where are they now" snapshot fields.

        Args:
            cohort_id: ID of the cohort to sync

        Returns:
            Updated AcademyCohort record
        """
        cohort = db.session.get(AcademyCohort, cohort_id)
        if not cohort:
            raise ValueError(f"Cohort {cohort_id} not found")

        logger.info(f"Syncing journeys for cohort {cohort_id} ({cohort.team_name} {cohort.season})")

        cohort.sync_status = 'syncing_journeys'
        db.session.commit()

        journey_service = JourneySyncService(self.api)
        members = CohortMember.query.filter(
            CohortMember.cohort_id == cohort_id,
            or_(CohortMember.journey_synced == False, CohortMember.journey_id.is_(None)),
        ).all()

        current_year = datetime.now().year

        for member in members:
            try:
                journey = journey_service.sync_player(member.player_api_id)

                if journey:
                    member.journey_id = journey.id
                    member.current_club_api_id = journey.current_club_api_id
                    member.current_club_name = journey.current_club_name
                    member.current_level = journey.current_level
                    member.first_team_debut_season = journey.first_team_debut_season
                    member.total_first_team_apps = journey.total_first_team_apps
                    member.total_clubs = journey.total_clubs

                    # Count loan spells
                    loan_entries = PlayerJourneyEntry.query.filter_by(
                        journey_id=journey.id,
                        entry_type='loan'
                    ).count()
                    member.total_loan_spells = loan_entries

                    # Derive current status
                    member.current_status = self._derive_status(
                        journey, current_year,
                        parent_api_id=cohort.team_api_id,
                        parent_club_name=cohort.team_name or '',
                    )

                    member.journey_synced = True
                    member.journey_sync_error = None
                else:
                    member.journey_synced = False
                    member.journey_sync_error = "Journey sync returned no data"
                db.session.commit()

            except Exception as e:
                logger.warning(f"Failed to sync journey for player {member.player_api_id}: {e}")
                member.journey_synced = False
                member.journey_sync_error = str(e)
                db.session.commit()

        # Refresh aggregates
        self.refresh_cohort_stats(cohort_id)

        total_members = CohortMember.query.filter_by(cohort_id=cohort_id).count()
        synced_members = CohortMember.query.filter_by(cohort_id=cohort_id, journey_synced=True).count()
        if total_members == 0:
            cohort.sync_status = 'no_data'
        elif synced_members == total_members:
            cohort.sync_status = 'complete'
            cohort.journeys_synced_at = datetime.now(timezone.utc)
        elif synced_members == 0:
            cohort.sync_status = 'failed'
        else:
            cohort.sync_status = 'partial'
            cohort.journeys_synced_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(f"Journey sync complete for cohort {cohort_id}")
        return cohort

    def refresh_cohort_stats(self, cohort_id: int) -> None:
        """Recalculate denormalized analytics for a cohort."""
        cohort = db.session.get(AcademyCohort, cohort_id)
        if not cohort:
            return

        members = CohortMember.query.filter_by(cohort_id=cohort_id).all()

        cohort.total_players = len(members)
        cohort.players_first_team = sum(1 for m in members if m.current_status == 'first_team')
        cohort.players_on_loan = sum(1 for m in members if m.current_status == 'on_loan')
        cohort.players_still_academy = sum(1 for m in members if m.current_status == 'academy')
        cohort.players_released = sum(1 for m in members if m.current_status in ('released', 'sold'))

        db.session.commit()
        logger.info(f"Refreshed stats for cohort {cohort_id}: {cohort.total_players} players")

    @staticmethod
    def _derive_status(
        journey: PlayerJourney,
        current_year: int,
        parent_api_id: int = 0,
        parent_club_name: str = '',
    ) -> str:
        """Derive current_status from a player's journey data.

        Uses the centralised classify_tracked_player which handles:
        - International duty and same-club youth teams
        - Transfer-based upgrade (on_loan → sold/released)
        - Inactivity-based release (config-driven)
        """
        if not journey:
            return 'unknown'

        latest_entry = PlayerJourneyEntry.query.filter_by(
            journey_id=journey.id
        ).order_by(PlayerJourneyEntry.season.desc()).first()

        status, _, _ = classify_tracked_player(
            current_club_api_id=journey.current_club_api_id,
            current_club_name=journey.current_club_name,
            current_level=journey.current_level,
            parent_api_id=parent_api_id,
            parent_club_name=parent_club_name,
            transfers=[],  # cohort context — no per-player API calls
            latest_season=latest_entry.season if latest_entry else None,
        )

        return status
