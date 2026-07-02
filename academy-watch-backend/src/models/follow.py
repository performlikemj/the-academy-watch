"""Follow graph + shadow tracking models.

Generalizes the scout watchlist into named **lists** of heterogeneous
**follows** (kinds: ``player`` | ``academy_club`` | ``geo`` | ``query``). A
list resolves to a player set that the scout digest reports on.

Following a player *outside* the tracked universe mints a lightweight
``PlayerShadow`` (profile + per-season ``PlayerShadowStats``), giving worldwide
players a working player page without any league crawling.

``FollowPlayerSnapshot`` is the per-(user, player) digest delta baseline —
unlike the watchlist's per-entry snapshot it works for *dynamic* follow sets
(geo/query/academy lists whose membership changes between digests). Its column
names are load-bearing: a snapshot row is passed AS a digest "entry" to the
delta engine, which reads/writes ``.player_api_id`` / ``.last_snapshot`` /
``.last_digest_at`` and reads ``.note`` (see scout_digest_service).
"""

from datetime import UTC, datetime

from src.models.league import db


class FollowList(db.Model):
    __tablename__ = "follow_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="My Watchlist")
    # cadence is stored for a future scheduler; Phase 1 sends stay admin-triggered.
    cadence = db.Column(db.String(20), nullable=False, default="weekly", server_default="weekly")
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    is_default = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    # Resolved-set cap the digest applies per list (resolve endpoint paginates
    # the full set; the digest bounds the work per run).
    player_cap = db.Column(db.Integer, nullable=False, default=40, server_default="40")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Index names match migration aw20 exactly (prod DDL == test create_all).
    __table_args__ = (
        db.UniqueConstraint("user_account_id", "name", name="uq_follow_list_user_name"),
        db.Index("ix_follow_lists_user", "user_account_id"),
    )

    # ORM cascade deletes child follows even where SQLite lacks ON DELETE CASCADE
    # enforcement; the DB-level FK cascade (migration) backs it up in Postgres.
    follows = db.relationship(
        "Follow",
        backref="follow_list",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    user = db.relationship("UserAccount", backref=db.backref("follow_lists", lazy="dynamic"))


class Follow(db.Model):
    __tablename__ = "follows"

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("follow_lists.id", ondelete="CASCADE"), nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # player | academy_club | geo | query
    # Per-kind selector; see follow_resolver.validate_selector for schemas.
    selector = db.Column(db.JSON, nullable=False)
    label = db.Column(db.String(160))  # display label, server-derived where possible
    note = db.Column(db.Text)  # migrated watchlist note (player kind)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    # Exact (kind, selector) duplicates within a list are rejected in code — a
    # portable UniqueConstraint over a JSON column is not available on SQLite.
    __table_args__ = (db.Index("ix_follows_list", "list_id"),)


class PlayerShadow(db.Model):
    __tablename__ = "player_shadows"

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    player_name = db.Column(db.String(200), nullable=False)
    photo_url = db.Column(db.String(500))
    position = db.Column(db.String(50))
    nationality = db.Column(db.String(100))
    birth_date = db.Column(db.Date)
    current_club_name = db.Column(db.String(200))
    current_club_api_id = db.Column(db.Integer)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    last_profile_sync_at = db.Column(db.DateTime)
    last_stats_sync_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (db.Index("ix_player_shadows_player", "player_api_id", unique=True),)


class FollowPlayerSnapshot(db.Model):
    __tablename__ = "follow_player_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    last_snapshot = db.Column(db.Text)  # JSON string, same shape as the watchlist snapshot
    last_digest_at = db.Column(db.DateTime)
    note = db.Column(db.Text)  # copied from a player-kind follow if any
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (db.UniqueConstraint("user_account_id", "player_api_id", name="uq_follow_snapshot_user_player"),)


class PlayerShadowStats(db.Model):
    """Dedicated shadow stats store — deliberately separate from the legacy,
    unowned PlayerStatsCache so shadow syncing never collides with (or is
    mistaken for) tracked-player coverage."""

    __tablename__ = "player_shadow_stats"

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    team_api_id = db.Column(db.Integer, nullable=True)
    team_name = db.Column(db.String(200))
    season = db.Column(db.Integer, nullable=False)
    appearances = db.Column(db.Integer)
    goals = db.Column(db.Integer)
    assists = db.Column(db.Integer)
    minutes = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        db.UniqueConstraint("player_api_id", "team_api_id", "season", name="uq_shadow_stats"),
        db.Index("ix_shadow_stats_player", "player_api_id"),
    )
