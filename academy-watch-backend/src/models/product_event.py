"""Product analytics event model — first-party, privacy-light telemetry.

One row per tracked event (pageview, follow_added, ...). No cookies, no IPs,
no user-agent: identity is only ever the verified user email when a token is
present, otherwise anonymous.
"""

from sqlalchemy.dialects.postgresql import JSONB
from src.models.league import db


class ProductEvent(db.Model):
    __tablename__ = "product_events"

    # BigInteger PK: SQLite only aliases INTEGER PRIMARY KEY to rowid, so fall
    # back to Integer under the test harness while keeping BIGINT in Postgres.
    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_name = db.Column(db.String(64), nullable=False)
    user_email = db.Column(db.String(320), nullable=True)
    session_id = db.Column(db.String(64), nullable=True)
    path = db.Column(db.String(512), nullable=True)
    referrer = db.Column(db.String(512), nullable=True)
    props = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    __table_args__ = (
        # Index names must match the migration exactly (prod DDL == test create_all).
        db.Index("ix_product_events_name_created", "event_name", "created_at"),
        db.Index("ix_product_events_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_name": self.event_name,
            "user_email": self.user_email,
            "session_id": self.session_id,
            "path": self.path,
            "referrer": self.referrer,
            "props": self.props,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
