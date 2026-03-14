"""Persistent API response cache and daily usage tracking."""

import hashlib
import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.models.league import db

logger = logging.getLogger(__name__)


class APICache(db.Model):
    """DB-backed cache for API-Football responses.

    Keyed by (endpoint, params_hash) where params_hash is SHA-256 of the
    sorted JSON-encoded query params.  Each row carries an expiry timestamp
    so stale entries can be skipped on read and cleaned up periodically.
    """

    __tablename__ = "api_cache"

    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(100), nullable=False)
    params_hash = db.Column(db.String(64), nullable=False)
    response_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("endpoint", "params_hash", name="uq_api_cache_endpoint_hash"),
        db.Index("ix_api_cache_expires_at", "expires_at"),
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_params(params: dict | None) -> str:
        """Deterministic SHA-256 of sorted JSON params."""
        normalized = json.dumps(params or {}, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode()).hexdigest()

    @classmethod
    def get_cached(cls, endpoint: str, params: dict | None) -> dict | None:
        """Return cached response dict if a fresh entry exists, else None."""
        h = cls._hash_params(params)
        now = datetime.now(timezone.utc)
        row = cls.query.filter_by(endpoint=endpoint, params_hash=h).first()
        if row is None:
            return None
        # Check expiry – treat naive timestamps as UTC
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            return None
        try:
            return json.loads(row.response_json)
        except (json.JSONDecodeError, TypeError):
            return None

    @classmethod
    def set_cached(cls, endpoint: str, params: dict | None, response: dict, ttl_seconds: int) -> None:
        """Insert or update the cache row for the given endpoint+params."""
        h = cls._hash_params(params)
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        expires = now + timedelta(seconds=ttl_seconds)
        response_text = json.dumps(response)

        existing = cls.query.filter_by(endpoint=endpoint, params_hash=h).first()
        if existing:
            existing.response_json = response_text
            existing.created_at = now
            existing.expires_at = expires
        else:
            row = cls(
                endpoint=endpoint,
                params_hash=h,
                response_json=response_text,
                created_at=now,
                expires_at=expires,
            )
            db.session.add(row)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # Race condition – another worker inserted first; update instead
            existing = cls.query.filter_by(endpoint=endpoint, params_hash=h).first()
            if existing:
                existing.response_json = response_text
                existing.created_at = now
                existing.expires_at = expires
                db.session.commit()

    @classmethod
    def invalidate_cached(cls, endpoint: str, params: dict | None = None) -> int:
        """Delete cache entries for an endpoint.

        If *params* is given, delete only the exact (endpoint, params_hash) row.
        Otherwise delete ALL rows for the endpoint.
        Returns the count of deleted rows.
        """
        if params is not None:
            h = cls._hash_params(params)
            count = cls.query.filter_by(endpoint=endpoint, params_hash=h).delete()
        else:
            count = cls.query.filter_by(endpoint=endpoint).delete()
        db.session.commit()
        return count

    @classmethod
    def cleanup_expired(cls) -> int:
        """Delete all expired rows.  Returns count of deleted rows."""
        now = datetime.now(timezone.utc)
        count = cls.query.filter(cls.expires_at < now).delete()
        db.session.commit()
        return count

    @classmethod
    def stats(cls) -> dict:
        """Return aggregate stats for admin visibility."""
        from sqlalchemy import func as sa_func

        rows = (
            db.session.query(
                cls.endpoint,
                sa_func.count(cls.id).label("count"),
                sa_func.min(cls.created_at).label("oldest"),
                sa_func.max(cls.created_at).label("newest"),
            )
            .group_by(cls.endpoint)
            .all()
        )
        total = sum(r.count for r in rows)
        by_endpoint = [
            {
                "endpoint": r.endpoint,
                "count": r.count,
                "oldest": r.oldest.isoformat() if r.oldest else None,
                "newest": r.newest.isoformat() if r.newest else None,
            }
            for r in rows
        ]
        return {"total_entries": total, "by_endpoint": by_endpoint}


class APIUsageDaily(db.Model):
    """Tracks the number of live API calls made per day per endpoint."""

    __tablename__ = "api_usage_daily"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    endpoint = db.Column(db.String(100), nullable=False)
    call_count = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("date", "endpoint", name="uq_api_usage_daily_date_endpoint"),
    )

    @classmethod
    def increment(cls, endpoint: str) -> None:
        """Atomically increment today's counter for *endpoint*."""
        today = date.today()
        existing = cls.query.filter_by(date=today, endpoint=endpoint).first()
        if existing:
            existing.call_count = cls.call_count + 1
        else:
            row = cls(date=today, endpoint=endpoint, call_count=1)
            db.session.add(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # Race: another worker inserted – do raw UPDATE for atomicity
            db.session.execute(
                text(
                    "UPDATE api_usage_daily SET call_count = call_count + 1 "
                    "WHERE date = :d AND endpoint = :e"
                ),
                {"d": today, "e": endpoint},
            )
            db.session.commit()

    @classmethod
    def today_total(cls) -> int:
        """Return the total number of API calls made today across all endpoints."""
        today = date.today()
        result = db.session.query(db.func.coalesce(db.func.sum(cls.call_count), 0)).filter_by(date=today).scalar()
        return int(result)

    @classmethod
    def usage_summary(cls, days: int = 7) -> dict:
        """Return usage by endpoint for today + daily totals for the last *days* days."""
        from datetime import timedelta

        today = date.today()
        start = today - timedelta(days=days - 1)

        # Today by endpoint
        today_rows = cls.query.filter_by(date=today).all()
        today_by_endpoint = {r.endpoint: r.call_count for r in today_rows}
        today_total = sum(today_by_endpoint.values())

        # Daily totals
        daily_rows = (
            db.session.query(cls.date, db.func.sum(cls.call_count).label("total"))
            .filter(cls.date >= start)
            .group_by(cls.date)
            .order_by(cls.date)
            .all()
        )
        daily = [{"date": str(r.date), "total": int(r.total)} for r in daily_rows]

        return {
            "today": {"by_endpoint": today_by_endpoint, "total": today_total},
            "daily": daily,
        }
