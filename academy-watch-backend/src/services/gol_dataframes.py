"""
GOL DataFrame Cache

Loads database tables into pandas DataFrames with a 5-minute TTL cache.
Used by the GOL Assistant's code-interpreter tool for analytics queries.
"""

import logging
import threading
import time

import pandas as pd

logger = logging.getLogger(__name__)

TTL_SECONDS = 300  # 5 minutes


class DataFrameCache:
    _instance = None
    """Thread-safe in-process cache for GOL DataFrames."""

    def __init__(self):
        self._cache: dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()
        self._loaded_at: float = 0
        DataFrameCache._instance = self

    def get_frames(self, app) -> dict[str, pd.DataFrame]:
        """Return cached DataFrames, refreshing if TTL expired. Returns copies."""
        now = time.time()
        if now - self._loaded_at < TTL_SECONDS and self._cache:
            return {k: v.copy() for k, v in self._cache.items()}

        with self._lock:
            # Double-check after acquiring lock
            if now - self._loaded_at < TTL_SECONDS and self._cache:
                return {k: v.copy() for k, v in self._cache.items()}
            self._cache = self._load_all(app)
            self._loaded_at = time.time()
            logger.info("GOL DataFrame cache refreshed (%d frames)", len(self._cache))
            return {k: v.copy() for k, v in self._cache.items()}

    def _load_all(self, app) -> dict[str, pd.DataFrame]:
        """Load all DataFrames from the database."""
        from src.models.league import db

        with app.app_context():
            engine = db.engine
            frames = {}

            frames['loan_players'] = self._load_query(engine, """
                SELECT
                    tp.player_api_id, tp.player_name, tp.age,
                    tp.position, tp.nationality,
                    tp.team_id AS parent_team_id,
                    t.name AS parent_club,
                    tp.loan_club_name,
                    tp.current_level, tp.is_active
                FROM tracked_players tp
                LEFT JOIN teams t ON tp.team_id = t.id
                WHERE tp.status = 'on_loan' AND tp.is_active = true
            """)

            frames['teams'] = self._load_query(engine, """
                SELECT
                    t.id, t.team_id, t.name, t.country,
                    l.name AS league_name,
                    t.is_tracked, t.season
                FROM teams t
                LEFT JOIN leagues l ON t.league_id = l.id
                WHERE t.season = (SELECT MAX(season) FROM teams)
            """)

            frames['tracked'] = self._load_query(engine, """
                SELECT
                    tp.player_api_id, tp.player_name, tp.position,
                    tp.nationality, tp.age, tp.team_id,
                    tp.status, tp.current_level,
                    tp.loan_club_name, tp.data_source, tp.is_active
                FROM tracked_players tp
                WHERE tp.is_active = true
            """)

            frames['journeys'] = self._load_query(engine, """
                SELECT
                    player_api_id, player_name, nationality, birth_date,
                    origin_club_name, origin_year,
                    current_club_name, current_level,
                    first_team_debut_season, first_team_debut_club,
                    total_clubs, total_first_team_apps, total_youth_apps,
                    total_loan_apps, total_goals, total_assists,
                    academy_club_ids
                FROM player_journeys
            """)

            frames['journey_entries'] = self._load_query(engine, """
                SELECT
                    je.journey_id,
                    pj.player_api_id,
                    je.season, je.club_api_id, je.club_name,
                    je.league_name, je.level, je.entry_type,
                    je.is_youth, je.appearances, je.goals,
                    je.assists, je.minutes
                FROM player_journey_entries je
                JOIN player_journeys pj ON je.journey_id = pj.id
            """)

            frames['cohorts'] = self._load_query(engine, """
                SELECT
                    c.id, c.team_api_id,
                    COALESCE(c.team_name, t.name) AS team_name,
                    COALESCE(c.league_name, t_league.name) AS league_name,
                    c.league_level,
                    c.season, c.total_players, c.players_first_team,
                    c.players_on_loan, c.players_still_academy, c.players_released,
                    c.sync_status
                FROM academy_cohorts c
                LEFT JOIN teams t ON c.team_api_id = t.team_id
                    AND t.season = (SELECT MAX(season) FROM teams)
                LEFT JOIN leagues t_league ON t.league_id = t_league.id
                WHERE c.total_players > 0
            """)

            frames['cohort_members'] = self._load_query(engine, """
                SELECT
                    cohort_id, player_api_id, player_name, position,
                    nationality, current_club_name, current_level,
                    current_status, appearances_in_cohort, goals_in_cohort,
                    first_team_debut_season, total_first_team_apps,
                    total_clubs, total_loan_spells, journey_synced
                FROM cohort_members
                WHERE journey_synced = true
            """)

            frames['fixtures'] = self._load_query(engine, """
                SELECT
                    id, fixture_id_api, date_utc, season,
                    competition_name,
                    home_team_api_id, away_team_api_id,
                    home_goals, away_goals
                FROM fixtures
            """)

            frames['fixture_stats'] = self._load_query(engine, """
                SELECT
                    fs.fixture_id, fs.player_api_id, fs.team_api_id,
                    f.season, f.date_utc,
                    fs.minutes, fs.position, fs.rating,
                    fs.goals, fs.assists, fs.saves, fs.yellows, fs.reds,
                    fs.shots_total, fs.shots_on,
                    fs.passes_total, fs.passes_key,
                    fs.tackles_total, fs.tackles_blocks, fs.tackles_interceptions,
                    fs.duels_total, fs.duels_won,
                    fs.dribbles_success, fs.fouls_drawn, fs.fouls_committed
                FROM fixture_player_stats fs
                JOIN fixtures f ON fs.fixture_id = f.id
            """)

            return frames

    @classmethod
    def invalidate(cls):
        """Clear cached DataFrames so next access reloads from DB."""
        if cls._instance:
            cls._instance._cache = {}
            cls._instance._loaded_at = 0

    @staticmethod
    def _load_query(engine, sql: str) -> pd.DataFrame:
        """Execute a SQL query and return a DataFrame. Returns empty on error."""
        try:
            return pd.read_sql_query(sql, engine)
        except Exception as e:
            logger.error("Failed to load DataFrame: %s — %s", sql[:60], e)
            return pd.DataFrame()
