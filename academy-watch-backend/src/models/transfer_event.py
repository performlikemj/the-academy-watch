"""Durable transfer evidence and its append-only admin audit trail."""

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


class TransferAdminEvent(db.Model):
    """One append-only audit event for a manual transfer operation."""

    __tablename__ = "transfer_admin_events"
    __table_args__ = (
        db.Index("ix_transfer_admin_events_transfer_event", "transfer_event_id"),
        db.Index("ix_transfer_admin_events_player_created", "player_api_id", "created_at"),
    )

    id = db.Column(_BIG_PK, primary_key=True, autoincrement=True)
    transfer_event_id = db.Column(
        _BIG_PK,
        db.ForeignKey("player_transfer_events.id"),
        nullable=False,
    )
    player_api_id = db.Column(db.Integer, nullable=False)
    actor_email = db.Column(db.String(254), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    source_note = db.Column(db.Text, nullable=False)
    event_metadata = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
