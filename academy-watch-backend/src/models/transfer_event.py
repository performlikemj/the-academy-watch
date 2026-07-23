"""Durable raw transfer-event evidence (tre01)."""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import JSONB
from src.models.league import db

# PostgreSQL should use BIGINT for the append-heavy evidence table, while the
# SQLite test harness needs INTEGER PRIMARY KEY to receive rowid autoincrement.
_BIG_PK = db.BigInteger().with_variant(db.Integer, "sqlite")


class PlayerTransferEvent(db.Model):
    """One observed API-Football transfer object at its provider natural key."""

    __tablename__ = "player_transfer_events"

    id = db.Column(_BIG_PK, primary_key=True, autoincrement=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    transfer_date = db.Column(db.Date, nullable=False)
    transfer_type = db.Column(db.String, nullable=True)
    out_club_api_id = db.Column(db.Integer, nullable=True)
    out_club_name = db.Column(db.String, nullable=True)
    in_club_api_id = db.Column(db.Integer, nullable=True)
    in_club_name = db.Column(db.String, nullable=True)
    first_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    raw = db.Column(JSONB, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "player_api_id",
            "transfer_date",
            "out_club_api_id",
            "in_club_api_id",
            "transfer_type",
            name="uq_player_transfer_events_natural_key",
            postgresql_nulls_not_distinct=True,
        ),
        db.Index("ix_player_transfer_events_player_api_id", "player_api_id"),
    )
