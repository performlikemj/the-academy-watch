"""User- and club-entered per-match player statistics."""

from datetime import UTC, datetime
from uuid import uuid4

# Register P2's invitation target before isolated test/local create_all calls
# traverse ClubRosterMember's accepted-invitation foreign key.
import src.models.club_invitation  # noqa: F401
import src.models.video  # noqa: F401
from src.models.league import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class ClubResult(db.Model):
    """Club-owned fixture identity; create identity survives corrections and deletion."""

    __tablename__ = "club_results"
    __table_args__ = (
        db.UniqueConstraint("program_id", "client_request_id", name="uq_club_results_request"),
        db.UniqueConstraint("id", "program_id", name="uq_club_results_program"),
        db.CheckConstraint("version > 0", name="ck_club_results_version"),
        db.CheckConstraint("home_away IN ('home','away','neutral')", name="ck_club_results_home_away"),
        db.CheckConstraint(
            "result_for BETWEEN 0 AND 20 AND result_against BETWEEN 0 AND 20", name="ck_club_results_counts"
        ),
        db.Index(
            "uq_club_results_active",
            "program_id",
            "match_date",
            "opponent_key",
            unique=True,
            sqlite_where=db.text("deleted_at IS NULL"),
            postgresql_where=db.text("deleted_at IS NULL"),
        ),
        db.Index("ix_club_results_history", "program_id", "season", "match_date", "id"),
    )
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=False)
    client_request_id = db.Column(db.String(36), nullable=False)
    create_request_hash = db.Column(db.String(64), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    match_date = db.Column(db.Date, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    opponent = db.Column(db.String(120), nullable=False)
    opponent_key = db.Column(db.String(120), nullable=False)
    competition = db.Column(db.String(120))
    home_away = db.Column(db.String(8), nullable=False)
    result_for = db.Column(db.Integer, nullable=False)
    result_against = db.Column(db.Integer, nullable=False)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="SET NULL"), index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(), nullable=False, default=_utcnow)
    deleted_at = db.Column(db.DateTime())

    def manager_dict(self):
        return {
            "id": self.id,
            "program_id": self.program_id,
            "version": self.version,
            "season": self.season,
            "match_date": self.match_date.isoformat(),
            "opponent": self.opponent,
            "competition": self.competition,
            "home_away": self.home_away,
            "result_for": self.result_for,
            "result_against": self.result_against,
            "video_match_id": self.video_match_id,
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class PlayerMatchEntry(db.Model):
    """One reported player line for one match.

    ``player_api_id`` is a signed logical identity: positive values are
    API-Football identities and negative values are approved local players.
    It deliberately is not a foreign key.
    """

    __tablename__ = "player_match_entries"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["club_result_id", "club_program_id"],
            ["club_results.id", "club_results.program_id"],
            name="fk_player_match_entries_result_program",
        ),
        db.UniqueConstraint("club_result_id", "player_api_id", name="uq_player_match_entries_result_player"),
        db.CheckConstraint(
            "club_result_id IS NULL OR (source = 'club' AND club_program_id IS NOT NULL)",
            name="ck_player_match_entries_result_source",
        ),
        db.CheckConstraint("source IN ('self','club')", name="ck_player_match_entries_source"),
        db.CheckConstraint(
            "status IN ('self_reported','club_confirmed','disputed')",
            name="ck_player_match_entries_status",
        ),
        db.CheckConstraint(
            "home_away IN ('home','away','neutral')",
            name="ck_player_match_entries_home_away",
        ),
        db.CheckConstraint("minutes BETWEEN 0 AND 130", name="ck_player_match_entries_minutes"),
        db.CheckConstraint(
            "goals BETWEEN 0 AND 20 AND assists BETWEEN 0 AND 20 "
            "AND yellows BETWEEN 0 AND 20 AND reds BETWEEN 0 AND 20",
            name="ck_player_match_entries_counts",
        ),
        db.CheckConstraint(
            "(result_for IS NULL OR result_for BETWEEN 0 AND 20) "
            "AND (result_against IS NULL OR result_against BETWEEN 0 AND 20) "
            "AND (saves IS NULL OR saves BETWEEN 0 AND 20) "
            "AND (goals_conceded IS NULL OR goals_conceded BETWEEN 0 AND 20)",
            name="ck_player_match_entries_optional_counts",
        ),
        db.UniqueConstraint(
            "player_api_id",
            "match_date",
            "opponent",
            "source",
            "reported_by_user_id",
            name="uq_player_match_entries_identity",
        ),
        db.Index("ix_player_match_entries_player_season", "player_api_id", "season"),
        db.Index("ix_player_match_entries_club_program", "club_program_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    club_result_id = db.Column(db.String(36), index=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    reported_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    club_program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=True)
    match_date = db.Column(db.Date, nullable=False)
    competition = db.Column(db.String(120))
    opponent = db.Column(db.String(120), nullable=False)
    home_away = db.Column(db.String(8), nullable=False)
    result_for = db.Column(db.Integer)
    result_against = db.Column(db.Integer)
    minutes = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    goals = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    assists = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    yellows = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    reds = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    saves = db.Column(db.Integer)
    goals_conceded = db.Column(db.Integer)
    note = db.Column(db.String(500))
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=db.func.now(),
    )

    reporter = db.relationship("UserAccount", foreign_keys=[reported_by_user_id])
    club_program = db.relationship("ClubProgram", foreign_keys=[club_program_id])

    def to_dict(self, *, editable: bool = False) -> dict:
        source_label = "Club-confirmed" if self.source == "club" else "Self-reported"
        primary_source = "club" if self.source == "club" else "user"
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "season": self.season,
            "match_date": self.match_date.isoformat() if self.match_date else None,
            "competition": self.competition,
            "opponent": self.opponent,
            "home_away": self.home_away,
            "result_for": self.result_for,
            "result_against": self.result_against,
            "minutes": self.minutes,
            "goals": self.goals,
            "assists": self.assists,
            "yellows": self.yellows,
            "reds": self.reds,
            "saves": self.saves,
            "goals_conceded": self.goals_conceded,
            "note": self.note,
            "source": self.source,
            "status": self.status,
            "editable": bool(editable),
            "provenance": {
                "source_category": self.source,
                "source_label": source_label,
                "primary_source": primary_source,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


__all__ = ["ClubResult", "PlayerMatchEntry"]
