"""User- and club-entered per-match player statistics."""

from datetime import UTC, datetime

from src.models.league import db


class PlayerMatchEntry(db.Model):
    """One reported player line for one match.

    ``player_api_id`` is a signed logical identity: positive values are
    API-Football identities and negative values are approved local players.
    It deliberately is not a foreign key.
    """

    __tablename__ = "player_match_entries"
    __table_args__ = (
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


__all__ = ["PlayerMatchEntry"]
