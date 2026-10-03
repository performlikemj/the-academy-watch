"""Real SQL loaders must supply frames accepted by the analysis boundary."""

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa
from flask import Flask
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import League, Player, Team, TeamProfile, db
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.services.gol_capabilities import plain_value, validate_frame
from src.services.gol_dataframes import DataFrameCache
from src.services.gol_sandbox import execute_analysis
from src.services.gol_service import GolService


@pytest.fixture(autouse=True)
def analysis_available(monkeypatch):
    monkeypatch.setenv("GOL_PROVIDER", "openai")
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")


def test_sqlite_numeric_loader():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "loader_values",
        metadata,
        sa.Column("rating", sa.Numeric(4, 2)),
        sa.Column("day", sa.Date),
        sa.Column("label", sa.Text),
        sa.Column("details", sa.JSON),
    )
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                table.insert(),
                [
                    {"rating": Decimal("6.50"), "day": date(2026, 1, 1), "label": "Example", "details": [1, 2]},
                    {"rating": None, "day": None, "label": None, "details": None},
                ],
            )
        frame = DataFrameCache._load_query(engine, "SELECT * FROM loader_values")
        assert len(frame) == 2 and frame.rating.dtype == "float64"
        validate_frame(frame)
        assert execute_analysis("result=values", {"values": frame})["result_type"] == "table"
    finally:
        engine.dispose()


@pytest.fixture
def pg_loader():
    uri = os.getenv("GOL_POSTGRES_URL")
    if not uri:
        pytest.skip("GOL_POSTGRES_URL opt-in; exercised by PostgreSQL CI")
    parsed = sa.engine.make_url(uri)
    assert parsed.database == "aw_sbxf2" and parsed.host in {"localhost", "127.0.0.1"}
    assert parsed.drivername == "postgresql+psycopg"
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        assert db.session.execute(sa.text("SELECT current_database()")).scalar() == "aw_sbxf2"
        assert db.session.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "p2c1"
        # Also exercise a Numeric deployment variant. The current model is Float;
        # only this disposable database changes, and its original type is restored.
        rating_type = next(
            column["type"]
            for column in sa.inspect(db.engine).get_columns("fixture_player_stats")
            if column["name"] == "rating"
        )
        assert isinstance(rating_type, (sa.Float, sa.Numeric))
        original_type = str(rating_type)
        db.session.execute(sa.text("ALTER TABLE fixture_player_stats ALTER COLUMN rating TYPE NUMERIC(4,2)"))
        db.session.commit()
        models = [
            CohortMember,
            PlayerJourneyEntry,
            FixturePlayerStats,
            TrackedPlayer,
            AcademyCohort,
            PlayerJourney,
            Fixture,
            Player,
            TeamProfile,
            Team,
            League,
        ]
        try:
            for i in range(3):
                key = 90100 + i
                missing = i == 1
                text = None if missing else f"Example {i}"
                number = sa.null() if missing else i + 1
                league = League(id=key, league_id=key, name=f"Example League {i}", country="Test", season=2026)
                team = Team(
                    id=key,
                    team_id=key,
                    name=f"Example Team {i}",
                    country="Test",
                    league_id=key,
                    season=2026,
                    is_tracked=sa.null() if missing else True,
                )
                journey = PlayerJourney(
                    id=key,
                    player_api_id=key,
                    player_name=text,
                    nationality=text,
                    birth_date="2000-01-01",
                    origin_club_name=text,
                    origin_year=number,
                    current_club_name=text,
                    current_level=text,
                    first_team_debut_season=number,
                    first_team_debut_club=text,
                    total_clubs=number,
                    total_first_team_apps=number,
                    total_youth_apps=number,
                    total_loan_apps=number,
                    total_goals=number,
                    total_assists=number,
                    academy_club_ids=None if missing else [key, key + 1],
                )
                cohort = AcademyCohort(
                    id=key,
                    team_api_id=key,
                    team_name=text,
                    league_api_id=key,
                    league_name=text,
                    league_level=text,
                    season=2026,
                    total_players=3,
                    players_first_team=number,
                    players_on_loan=number,
                    players_still_academy=number,
                    players_released=number,
                    sync_status=text,
                )
                fixture = Fixture(
                    id=key,
                    fixture_id_api=key,
                    date_utc=None if missing else datetime(2026, 1, i + 1),
                    season=2026,
                    competition_name=text,
                    home_team_api_id=number,
                    away_team_api_id=number,
                    home_goals=number,
                    away_goals=number,
                )
                db.session.add_all(
                    [
                        league,
                        team,
                        journey,
                        cohort,
                        fixture,
                        TeamProfile(team_id=key, name=f"Example Team {i}", country=text, logo_url=text),
                        Player(player_id=key, name=f"Example Player {i}"),
                    ]
                )
                db.session.flush()
                db.session.add_all(
                    [
                        TrackedPlayer(
                            id=key,
                            player_api_id=key,
                            player_name=f"Example Player {i}",
                            birth_date="2000-01-01",
                            position=text,
                            nationality=text,
                            age=number,
                            team_id=key,
                            journey_id=key,
                            status="academy",
                            current_level=text,
                            current_club_name=text,
                            data_source="api-football",
                            is_active=True,
                            updated_at=sa.null() if missing else datetime(2026, 1, 1),
                        ),
                        PlayerJourneyEntry(
                            id=key,
                            journey_id=key,
                            season=2026,
                            club_api_id=key,
                            club_name=text,
                            league_name=text,
                            level=text,
                            entry_type=text,
                            is_youth=sa.null() if missing else False,
                            appearances=number,
                            goals=number,
                            assists=number,
                            minutes=number,
                        ),
                        CohortMember(
                            id=key,
                            cohort_id=key,
                            player_api_id=key,
                            player_name=text,
                            position=text,
                            nationality=text,
                            current_club_name=text,
                            current_level=text,
                            current_status=text,
                            appearances_in_cohort=number,
                            goals_in_cohort=number,
                            first_team_debut_season=number,
                            total_first_team_apps=number,
                            total_clubs=number,
                            total_loan_spells=number,
                            journey_synced=True,
                        ),
                        FixturePlayerStats(
                            id=key,
                            fixture_id=key,
                            player_api_id=key,
                            team_api_id=key,
                            rating=None if missing else Decimal("6.50") + i,
                            position=text,
                            formation=text,
                            grid=text,
                            formation_position=text,
                            **{
                                name: number
                                for name in (
                                    "minutes",
                                    "goals",
                                    "assists",
                                    "saves",
                                    "yellows",
                                    "reds",
                                    "shots_total",
                                    "shots_on",
                                    "passes_total",
                                    "passes_key",
                                    "tackles_total",
                                    "tackles_blocks",
                                    "tackles_interceptions",
                                    "duels_total",
                                    "duels_won",
                                    "dribbles_success",
                                    "fouls_drawn",
                                    "fouls_committed",
                                )
                            },
                        ),
                    ]
                )
            db.session.commit()
            yield app
        finally:
            db.session.rollback()
            for model in models:
                db.session.execute(
                    sa.delete(model).where(model.__table__.primary_key.columns.values()[0].in_(range(90100, 90103)))
                )
            db.session.execute(sa.text(f"ALTER TABLE fixture_player_stats ALTER COLUMN rating TYPE {original_type}"))
            db.session.commit()
            db.session.remove()
            db.engine.dispose()


def test_postgres_full_loader_frames_and_service(pg_loader, record_property):
    cache = DataFrameCache()
    queries = []

    def remember_query(_connection, _cursor, statement, _parameters, _context, _executemany):
        queries.append(statement)

    with pg_loader.app_context():
        engine = db.engine
        sa.event.listen(engine, "before_cursor_execute", remember_query)
        try:
            raw = cache._load_all(pg_loader)
        finally:
            sa.event.remove(engine, "before_cursor_execute", remember_query)
    assert set(raw) == {
        "teams",
        "tracked",
        "journeys",
        "journey_entries",
        "cohorts",
        "cohort_members",
        "fixtures",
        "team_profiles",
        "players",
        "fixture_stats",
    }
    dtypes = {name: {str(column): str(dtype) for column, dtype in frame.dtypes.items()} for name, frame in raw.items()}
    record_property("loader_dtypes", json.dumps(dtypes, sort_keys=True))
    if path := os.getenv("GOL_DTYPE_REPORT"):
        Path(path).write_text(json.dumps(dtypes, indent=2) + "\n")
    for name, frame in raw.items():
        assert len(frame) == 3, name  # Failed queries must never pass as empty frames.
        validate_frame(frame)
        assert execute_analysis(f"result={name}.head()", raw)["result_type"] == "table", name
    assert raw["fixture_stats"].rating.dtype == "float64"
    assert raw["fixture_stats"].rating.isna().sum() == 1
    assert isinstance(raw["journeys"].academy_club_ids.iloc[0], list)
    with pg_loader.app_context():
        # Prove the driver's native Numeric type separately from pandas coercion.
        rating = db.session.execute(sa.text("SELECT rating FROM fixture_player_stats WHERE id=90100")).scalar()
        assert type(rating) is Decimal and plain_value(rating) == 6.5
        stats_query = next(query for query in queries if "FROM fixture_player_stats fs" in query)
        native_stats = pd.read_sql_query(stats_query, db.engine, coerce_float=False)
        assert native_stats.rating.dtype == object
        assert type(native_stats.rating.dropna().iloc[0]) is Decimal
        validate_frame(native_stats)
        native_frames = {**raw, "fixture_stats": native_stats}
        assert execute_analysis("result=teams.head()", native_frames)["result_type"] == "table"
        assert execute_analysis("result=fixture_stats.head()", native_frames)["result_type"] == "table"
        # The actual loader selects JSON arrays, dates/timestamps, NULLs and text.
        # Cover PostgreSQL native date/array/object-JSON values through the same query loader too.
        probe = cache._load_query(
            db.engine,
            """
            SELECT CAST('2026-01-01' AS date) AS day, ARRAY[1,2] AS ids,
                   '{"values":[1,null],"label":"Example"}'::jsonb AS details
            UNION ALL SELECT NULL::date, NULL::int[], NULL::jsonb
        """,
        )
        assert len(probe) == 2
        validate_frame(probe)
        assert execute_analysis("result=probe", {**raw, "probe": probe})["result_type"] == "table"
        service = GolService.__new__(GolService)
        service.df_cache = cache
        result = service._execute_tool("run_analysis", {"code": "result=teams.head()"})
        assert result["result_type"] == "table" and result["total_rows"] == 3
        filtered = cache.get_frames(pg_loader)
        assert all(len(frame) == 3 for frame in filtered.values())
        assert service._execute_tool("run_analysis", {"code": "result=fixture_stats.rating.mean()"})["value"] == 7.5
