"""
Tracked Player Model

Represents a player being tracked by a parent academy club.
One row per player per parent club — no duplication per window/season.
Replaces the old AcademyPlayer model for the Academy Watch redesign.
"""

from datetime import UTC, datetime

from src.models.league import db
from src.utils.player_names import clean_name


class TrackedPlayer(db.Model):
    __tablename__ = "tracked_players"

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False, index=True)
    player_name = db.Column(db.String(200), nullable=False)
    photo_url = db.Column(db.String(500))
    position = db.Column(db.String(50))  # Goalkeeper, Defender, Midfielder, Attacker
    nationality = db.Column(db.String(100))
    birth_date = db.Column(db.String(20))
    age = db.Column(db.Integer)

    # Parent academy club
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)

    # Current pathway status
    status = db.Column(db.String(20), nullable=False, default="academy")
    #   'academy' | 'on_loan' | 'first_team' | 'released' | 'sold' | 'left'
    #   'left' = academy product who departed this club for another club with
    #            no recorded senior transfer (distinct from 'sold' = permanent
    #            transfer with a destination, and 'released' = free agent / dropped).
    current_level = db.Column(db.String(20))
    #   'U18' | 'U21' | 'U23' | 'Reserve' | 'Senior'

    # Most recent youth season (season-start year) at the parent club —
    # evidence for the current+4-season academy tracking window.
    last_academy_season = db.Column(db.Integer)

    # Current club (loan club if on_loan, buying club if sold, new club if released)
    current_club_api_id = db.Column(db.Integer)
    current_club_name = db.Column(db.String(200))
    current_club_db_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)

    # Transfer fee when sold (raw string from API-Football, e.g. "€50M", "Free")
    sale_fee = db.Column(db.String(100))

    # Provenance
    data_source = db.Column(db.String(30), nullable=False, default="api-football")
    #   'api-football' | 'manual' | 'cohort-seed'
    data_depth = db.Column(db.String(20), nullable=False, default="full_stats")

    # Link to rich career data
    journey_id = db.Column(db.Integer, db.ForeignKey("player_journeys.id"))

    # When True, refresh-statuses will never change team_id — prevents
    # the classifier from reassigning parent club based on stale API data.
    pinned_parent = db.Column(db.Boolean, default=False, server_default="false")

    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (db.UniqueConstraint("player_api_id", "team_id", name="uq_tracked_player_team"),)

    # Relationships
    team = db.relationship("Team", backref="tracked_players", lazy=True, foreign_keys=[team_id])
    current_club = db.relationship("Team", foreign_keys=[current_club_db_id], lazy=True)
    journey = db.relationship("PlayerJourney", backref="tracked_player", lazy=True, foreign_keys=[journey_id])

    @property
    def effective_age(self):
        """Current age derived from birth_date, falling back to the stored
        age column (which is a snapshot and goes stale every season)."""
        from src.utils.academy_window import age_from_birth_date

        return age_from_birth_date(self.birth_date) or self.age

    def compute_stats(self):
        """Compute a player's CURRENT-SEASON stats.

        - full_stats: aggregate FixturePlayerStats for the current stats season
          across EVERY club the player actually appeared for.
        - events_only / profile_only: sum PlayerStatsCache across the player's
          clubs for that season (limited-coverage leagues).

        The season's clubs are derived from the stat rows themselves rather than
        keyed on ``current_club_api_id``. Two failure modes that keying created:
        a returned loanee's journey flips his current club back to the parent, so
        his whole loan season was dropped; and first-team rows commonly have a
        NULL current club, which returned zeros outright. A player who moved
        mid-season (sold/released) now reports the season total across both
        clubs, matching /players/<id>/season-stats.
        """
        from sqlalchemy import func
        from src.utils.academy_window import stats_season_with_data

        default_stats = {
            "appearances": 0,
            "goals": 0,
            "assists": 0,
            "minutes_played": 0,
            "saves": 0,
            "yellows": 0,
            "reds": 0,
            "stats_coverage": self.data_depth or "full_stats",
        }

        # Stats DISPLAY season, with the latest-season-with-fixtures fallback so a
        # not-yet-started calendar season never zeroes every player (see
        # utils/academy_window.stats_season_with_data).
        season = stats_season_with_data(db.session)

        # Limited / events-only coverage → read from PlayerStatsCache.
        if self.data_depth in ("events_only", "profile_only"):
            from src.models.league import PlayerStatsCache

            def _cache_totals(season_value):
                return (
                    db.session.query(
                        func.count(PlayerStatsCache.id).label("n"),
                        func.coalesce(func.sum(PlayerStatsCache.appearances), 0).label("appearances"),
                        func.coalesce(func.sum(PlayerStatsCache.goals), 0).label("goals"),
                        func.coalesce(func.sum(PlayerStatsCache.assists), 0).label("assists"),
                        func.coalesce(func.sum(PlayerStatsCache.minutes_played), 0).label("minutes_played"),
                        func.coalesce(func.sum(PlayerStatsCache.saves), 0).label("saves"),
                        func.coalesce(func.sum(PlayerStatsCache.yellows), 0).label("yellows"),
                        func.coalesce(func.sum(PlayerStatsCache.reds), 0).label("reds"),
                        func.max(PlayerStatsCache.stats_coverage).label("stats_coverage"),
                    )
                    .filter(
                        PlayerStatsCache.player_api_id == self.player_api_id,
                        PlayerStatsCache.season == season_value,
                    )
                    .first()
                )

            cache = _cache_totals(season)
            if not cache or not cache.n:
                # Lower-league feeds lag; fall back to the player's most recent
                # cached season so a limited player doesn't blank on rollover.
                latest = (
                    db.session.query(func.max(PlayerStatsCache.season))
                    .filter(PlayerStatsCache.player_api_id == self.player_api_id)
                    .scalar()
                )
                if latest is not None and latest != season:
                    cache = _cache_totals(latest)
            if cache and cache.n:
                return {
                    "appearances": int(cache.appearances or 0),
                    "goals": int(cache.goals or 0),
                    "assists": int(cache.assists or 0),
                    "minutes_played": int(cache.minutes_played or 0),
                    "saves": int(cache.saves or 0),
                    "yellows": int(cache.yellows or 0),
                    "reds": int(cache.reds or 0),
                    "stats_coverage": cache.stats_coverage or "limited",
                }
            return default_stats

        # Full stats → aggregate FixturePlayerStats across ALL clubs the player
        # appeared for this season (join Fixture to season-scope; the
        # fixtures.season index keeps this a single cheap grouped scan).
        from src.models.weekly import Fixture, FixturePlayerStats

        stats = (
            db.session.query(
                func.count(FixturePlayerStats.id).label("appearances"),
                func.coalesce(func.sum(FixturePlayerStats.goals), 0).label("goals"),
                func.coalesce(func.sum(FixturePlayerStats.assists), 0).label("assists"),
                func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label("minutes_played"),
                func.coalesce(func.sum(FixturePlayerStats.saves), 0).label("saves"),
                func.coalesce(func.sum(FixturePlayerStats.yellows), 0).label("yellows"),
                func.coalesce(func.sum(FixturePlayerStats.reds), 0).label("reds"),
            )
            .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
            .filter(
                FixturePlayerStats.player_api_id == self.player_api_id,
                Fixture.season == season,
            )
            .first()
        )

        if not stats:
            return default_stats

        return {
            "appearances": stats.appearances or 0,
            "goals": int(stats.goals or 0),
            "assists": int(stats.assists or 0),
            "minutes_played": int(stats.minutes_played or 0),
            "saves": int(stats.saves or 0),
            "yellows": int(stats.yellows or 0),
            "reds": int(stats.reds or 0),
            "stats_coverage": "full",
        }

    def to_dict(self):
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "player_name": clean_name(self.player_name),
            "photo_url": self.photo_url,
            "position": self.position,
            "nationality": self.nationality,
            "birth_date": self.birth_date,
            "age": self.effective_age,
            "last_academy_season": self.last_academy_season,
            "team_id": self.team_id,
            "team_name": self.team.name if self.team else None,
            "team_logo": self.team.logo if self.team else None,
            "team_api_id": self.team.team_id if self.team else None,
            "status": self.status,
            "current_level": self.current_level,
            "current_club_api_id": self.current_club_api_id,
            "current_club_name": self.current_club_name,
            "current_club_db_id": self.current_club_db_id,
            "current_club_logo": self.current_club.logo if self.current_club else None,
            "sale_fee": self.sale_fee,
            "data_source": self.data_source,
            "data_depth": self.data_depth,
            "journey_id": self.journey_id,
            "pinned_parent": self.pinned_parent,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_public_dict(self):
        """Return a public-facing dict with fields expected by the frontend.
        Stats default to 0 here — the endpoint enriches them via batch query."""
        return {
            "id": self.id,
            "player_id": self.player_api_id,
            "player_name": clean_name(self.player_name),
            "player_photo": self.photo_url,
            "position": self.position,
            "age": self.effective_age,
            "nationality": self.nationality,
            "primary_team_id": self.team_id,
            "primary_team_name": self.team.name if self.team else None,
            "primary_team_api_id": self.team.team_id if self.team else None,
            "loan_team_name": self.current_club_name,
            "loan_team_api_id": self.current_club_api_id,
            "loan_team_db_id": self.current_club_db_id,
            "loan_team_logo": self.current_club.logo if self.current_club else None,
            "is_active": self.is_active,
            "status": self.status,
            "pathway_status": self.status,
            "current_level": self.current_level,
            "data_source": self.data_source,
            "data_depth": self.data_depth,
            "appearances": 0,
            "goals": 0,
            "assists": 0,
            "minutes_played": 0,
            "saves": 0,
            "yellows": 0,
            "reds": 0,
            "sale_fee": self.sale_fee,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
