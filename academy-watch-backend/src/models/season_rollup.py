"""Season-rollup models (sea02) — the precomputed per-player-per-season read surface.

The seasons design (ledgers/research/seasons-design-proposal.md §2/§3) makes every
hot stats surface "one indexed row" instead of a live cross-source aggregation on a
0.5 CPU box. Two grains plus a per-league calendar config:

- ``player_season_cells``   — FINE grain: one row per SOURCE-contributed cell,
                              ``(player, season, source, club, competition_tier)``.
                              Feeders DELETE+INSERT their own source's cells; the
                              source is IN the unique key so feeders never collide.
- ``player_season_totals``  — COARSE grain: the single hot-read row per
                              ``(player, season, level_group)``. Totals NEVER sum
                              across sources — the larger-minutes source wins the
                              headline whole (the double-count guard); both raw
                              ``fixtures_minutes`` / ``journey_minutes`` and a
                              ``reconcile_flag`` are always carried for provenance.
- ``league_season_config``  — "what season is NOW" per league (calendar-year vs
                              Aug-rollover), so calendar leagues (Brazil/MLS/…) label
                              and resolve their current season correctly.

D3a is SCHEMA ONLY — no service writes these tables yet (that is D3b). These classes
exist so the tables are registered in ``db.metadata`` (autogenerate parity) and are
importable by the D3b rollup service. Metadata here matches migration ``sea02``
column-for-column, name-for-name — a drift would make ``flask db migrate`` propose a
spurious drop/create (the exact failure the D2 drift fixes guarded against).
"""

from sqlalchemy.dialects.postgresql import JSONB
from src.models.league import db

# BigInteger surrogate PK that still works under the SQLite test harness (SQLite
# only aliases INTEGER PRIMARY KEY to rowid) — mirrors ProductEvent.
_BIG_PK = db.BigInteger().with_variant(db.Integer, "sqlite")


class PlayerSeasonCell(db.Model):
    """One SOURCE-contributed stat cell for a player-season (fine grain)."""

    __tablename__ = "player_season_cells"

    id = db.Column(_BIG_PK, primary_key=True, autoincrement=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)  # API-Football season start-year (2025 == 2025-26)
    source = db.Column(db.String(12), nullable=False)  # fixtures|journey|apss|shadow|cache
    club_api_id = db.Column(db.Integer, nullable=False)
    club_name = db.Column(db.String(200))
    competition_tier = db.Column(
        db.String(20), nullable=False
    )  # league|domestic_cup|league_cup|continental|other|youth
    level_group = db.Column(db.String(13), nullable=False)  # senior|youth|international

    appearances = db.Column(db.Integer)
    goals = db.Column(db.Integer)
    assists = db.Column(db.Integer)
    minutes = db.Column(db.Integer)
    yellows = db.Column(db.Integer)
    reds = db.Column(db.Integer)
    saves = db.Column(db.Integer)
    goals_conceded = db.Column(db.Integer)
    avg_rating = db.Column(db.Numeric(4, 2))  # minutes-weighted WITHIN this source only

    detail = db.Column(JSONB)  # rich fields: shots/passes/tackles/duels/dribbles
    synced_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # source is IN the grain so feeders never collide (proposal §2/§6 Q1).
        db.UniqueConstraint(
            "player_api_id",
            "season",
            "source",
            "club_api_id",
            "competition_tier",
            name="uq_psc_player_season_source_club_tier",
        ),
        # per-player-per-season read path; named to match migration sea02.
        db.Index("ix_psc_player_season", "player_api_id", "season"),
        # single-column clock index so the /status gauge's MAX(synced_at) is an
        # index lookup, not a full seq scan; named to match migration sea02.
        db.Index("ix_psc_synced_at", "synced_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "season": self.season,
            "source": self.source,
            "club": {"id": self.club_api_id, "name": self.club_name},
            "competition_tier": self.competition_tier,
            "level_group": self.level_group,
            "stats": {
                "appearances": self.appearances,
                "goals": self.goals,
                "assists": self.assists,
                "minutes": self.minutes,
                "yellows": self.yellows,
                "reds": self.reds,
                "saves": self.saves,
                "goals_conceded": self.goals_conceded,
                "avg_rating": float(self.avg_rating) if self.avg_rating is not None else None,
            },
            "detail": self.detail,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }


class PlayerSeasonTotal(db.Model):
    """The single hot-read totals row per player-season-level_group (coarse grain).

    Totals NEVER sum across sources — the larger-minutes source wins the headline
    whole (proposal §2 aggregation rule). ``fixtures_minutes`` / ``journey_minutes``
    and ``reconcile_flag`` are always present so provenance is never lost.
    """

    __tablename__ = "player_season_totals"

    id = db.Column(_BIG_PK, primary_key=True, autoincrement=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    level_group = db.Column(db.String(13), nullable=False)  # senior|youth|international

    appearances = db.Column(db.Integer)
    goals = db.Column(db.Integer)
    assists = db.Column(db.Integer)
    minutes = db.Column(db.Integer)
    yellows = db.Column(db.Integer)
    reds = db.Column(db.Integer)
    saves = db.Column(db.Integer)
    goals_conceded = db.Column(db.Integer)
    avg_rating = db.Column(db.Numeric(4, 2))  # ALWAYS fixtures-sourced, minutes-weighted

    primary_source = db.Column(db.String(12), nullable=False)  # source whose totals won the headline
    fixtures_minutes = db.Column(db.Integer)
    journey_minutes = db.Column(db.Integer)
    reconcile_flag = db.Column(db.String(20))  # NULL|cup-gap|journey-under-sync|fixtures-invisible
    source_breakdown = db.Column(JSONB)  # per-source minutes
    clubs = db.Column(JSONB)  # compact per-club render array
    computed_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("player_api_id", "season", "level_group", name="uq_pst_player_season_group"),
        # list surfaces scan by (season, level_group); development view by (player, season).
        db.Index("ix_pst_season_group", "season", "level_group"),
        db.Index("ix_pst_player", "player_api_id", "season"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "season": self.season,
            "level_group": self.level_group,
            "stats": {
                "appearances": self.appearances,
                "goals": self.goals,
                "assists": self.assists,
                "minutes": self.minutes,
                "yellows": self.yellows,
                "reds": self.reds,
                "saves": self.saves,
                "goals_conceded": self.goals_conceded,
                "avg_rating": float(self.avg_rating) if self.avg_rating is not None else None,
            },
            "provenance": {
                "primary_source": self.primary_source,
                "fixtures_minutes": self.fixtures_minutes,
                "journey_minutes": self.journey_minutes,
                "reconcile_flag": self.reconcile_flag,
                "source_breakdown": self.source_breakdown,
            },
            "clubs": self.clubs,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }


class LeagueSeasonConfig(db.Model):
    """Per-league calendar model — "what season is NOW" (proposal §2/§6 Q3).

    ``league_api_id`` is a NATURAL key (the API-Football league id), inserted
    explicitly, so it carries no sequence (``autoincrement=False``).
    """

    __tablename__ = "league_season_config"

    league_api_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    season_type = db.Column(db.String(12))  # calendar|split (Aug-rollover is the default elsewhere)
    rollover_month = db.Column(db.Integer)

    def to_dict(self):
        return {
            "league_api_id": self.league_api_id,
            "season_type": self.season_type,
            "rollover_month": self.rollover_month,
        }
