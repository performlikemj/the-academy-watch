from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
from src.utils.sanitize import sanitize_comment_body, sanitize_plain_text
from sqlalchemy import func


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize naive datetimes to UTC-aware values."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

db = SQLAlchemy()



class League(db.Model):
    __tablename__ = 'leagues'
    
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(50), nullable=False)
    logo = db.Column(db.String(255))
    flag = db.Column(db.String(255))
    season = db.Column(db.Integer, nullable=False, default=2024)
    is_european_top_league = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    teams = db.relationship('Team', backref='league', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'league_id': self.league_id,
            'name': self.name,
            'country': self.country,
            'logo': self.logo,
            'flag': self.flag,
            'season': self.season,
            'is_european_top_league': self.is_european_top_league,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class LeagueLocalization(db.Model):
    __tablename__ = 'league_localizations'

    id = db.Column(db.Integer, primary_key=True)
    league_name = db.Column(db.String(100), unique=True, nullable=False)
    country = db.Column(db.String(2), nullable=False)
    search_lang = db.Column(db.String(5), nullable=False)
    ui_lang = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'league_name': self.league_name,
            'country': self.country,
            'search_lang': self.search_lang,
            'ui_lang': self.ui_lang,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Team(db.Model):
    __tablename__ = 'teams'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(10))
    country = db.Column(db.String(50), nullable=False)
    founded = db.Column(db.Integer)
    national = db.Column(db.Boolean, default=False)
    logo = db.Column(db.String(255))
    venue_name = db.Column(db.String(100))
    venue_address = db.Column(db.String(255))
    venue_city = db.Column(db.String(50))
    venue_capacity = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    newsletters_active = db.Column(db.Boolean, default=False)
    is_tracked = db.Column(db.Boolean, default=False)  # Whether we're actively tracking this team's loans
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    season = db.Column(db.Integer, nullable=False)  
    
    __table_args__ = (
        db.UniqueConstraint('team_id', 'season', name='uq_team_id_season'),
    )
      
    # Relationships
    newsletters = db.relationship('Newsletter', backref='team', lazy=True)
    subscriptions = db.relationship('UserSubscription', backref='team', lazy=True)

    def unique_active_players(self):
        """Return active tracked players for this team (parent club)."""
        return [tp for tp in self.tracked_players if tp.is_active]

    def to_dict(self):
        current_players = self.unique_active_players()
        return {
            'id': self.id,
            'team_id': self.team_id,
            'name': self.name,
            'code': self.code,
            'country': self.country,
            'founded': self.founded,
            'national': self.national,
            'logo': self.logo,
            'venue_name': self.venue_name,
            'venue_address': self.venue_address,
            'venue_city': self.venue_city,
            'venue_capacity': self.venue_capacity,
            'is_active': self.is_active,
            'newsletters_active': self.newsletters_active,
            'is_tracked': self.is_tracked,
            'season': self.season,
            'league_name': self.league.name if self.league else None,
            'current_loaned_out_count': len(current_players),
            'slug': getattr(self, '_slug', None),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class PlayerStatsCache(db.Model):
    """Cached stats for players, primarily for limited-coverage leagues
    where FixturePlayerStats doesn't exist.  Can be rebuilt at any time
    from FixturePlayerStats + lineup/event source data."""
    __tablename__ = 'player_stats_cache'

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False, index=True)
    team_api_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    stats_coverage = db.Column(db.String(20), nullable=False, default='limited')
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes_played = db.Column(db.Integer, default=0)
    saves = db.Column(db.Integer, default=0)
    yellows = db.Column(db.Integer, default=0)
    reds = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('player_api_id', 'team_api_id', 'season',
                            name='uq_player_stats_cache'),
    )

    def to_dict(self):
        return {
            'player_api_id': self.player_api_id,
            'team_api_id': self.team_api_id,
            'season': self.season,
            'stats_coverage': self.stats_coverage,
            'appearances': self.appearances or 0,
            'goals': self.goals or 0,
            'assists': self.assists or 0,
            'minutes_played': self.minutes_played or 0,
            'saves': self.saves or 0,
            'yellows': self.yellows or 0,
            'reds': self.reds or 0,
        }


class TeamProfile(db.Model):
    __tablename__ = 'team_profiles'

    team_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    code = db.Column(db.String(20))
    country = db.Column(db.String(80))
    founded = db.Column(db.Integer)
    is_national = db.Column(db.Boolean)
    logo_url = db.Column(db.String(255))
    venue_id = db.Column(db.Integer)
    venue_name = db.Column(db.String(160))
    venue_address = db.Column(db.String(255))
    venue_city = db.Column(db.String(120))
    venue_capacity = db.Column(db.Integer)
    venue_surface = db.Column(db.String(80))
    venue_image = db.Column(db.String(255))
    slug = db.Column(db.String(200), unique=True, index=True, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'team_id': self.team_id,
            'name': self.name,
            'code': self.code,
            'country': self.country,
            'founded': self.founded,
            'is_national': self.is_national,
            'logo_url': self.logo_url,
            'venue_id': self.venue_id,
            'venue_name': self.venue_name,
            'venue_address': self.venue_address,
            'venue_city': self.venue_city,
            'venue_capacity': self.venue_capacity,
            'venue_surface': self.venue_surface,
            'venue_image': self.venue_image,
            'slug': self.slug,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Player(db.Model):
    __tablename__ = 'players'

    player_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    firstname = db.Column(db.String(160))
    lastname = db.Column(db.String(160))
    nationality = db.Column(db.String(80))
    age = db.Column(db.Integer)
    height = db.Column(db.String(32))
    weight = db.Column(db.String(32))
    position = db.Column(db.String(80))
    photo_url = db.Column(db.String(255))
    sofascore_id = db.Column(db.Integer, unique=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'player_id': self.player_id,
            'name': self.name,
            'firstname': self.firstname,
            'lastname': self.lastname,
            'nationality': self.nationality,
            'age': self.age,
            'height': self.height,
            'weight': self.weight,
            'position': self.position,
            'photo_url': self.photo_url,
            'sofascore_id': self.sofascore_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class Newsletter(db.Model):
    __tablename__ = 'newsletters'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    newsletter_type = db.Column(db.String(20), nullable=False, default='weekly')
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    structured_content = db.Column(db.Text)  # JSON string
    public_slug = db.Column(db.String(200), unique=True, index=True, nullable=False)
    week_start_date = db.Column(db.Date)
    week_end_date = db.Column(db.Date)
    issue_date = db.Column(db.Date)  # The target date for this newsletter issue
    published = db.Column(db.Boolean, default=False)
    published_date = db.Column(db.DateTime)
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_date = db.Column(db.DateTime)
    subscriber_count = db.Column(db.Integer, default=0)
    generated_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint(
            'team_id',
            'newsletter_type',
            'week_start_date',
            'week_end_date',
            name='uq_newsletter_week_window',
        ),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'newsletter_type': self.newsletter_type,
            'title': self.title,
            'content': self.content,
            'structured_content': self.structured_content,
            'public_slug': self.public_slug,
            'week_start_date': self.week_start_date.isoformat() if self.week_start_date else None,
            'week_end_date': self.week_end_date.isoformat() if self.week_end_date else None,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'published': self.published,
            'published_date': self.published_date.isoformat() if self.published_date else None,
            'email_sent': self.email_sent,
            'email_sent_date': self.email_sent_date.isoformat() if self.email_sent_date else None,
            'subscriber_count': self.subscriber_count,
            'generated_date': self.generated_date.isoformat() if self.generated_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'commentaries': [c.to_dict() for c in self.commentaries] if self.commentaries else []
        }

class UserSubscription(db.Model):
    __tablename__ = 'user_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    preferred_frequency = db.Column(db.String(20), default='weekly')
    active = db.Column(db.Boolean, default=True)
    unsubscribe_token = db.Column(db.String(100), unique=True)
    last_email_sent = db.Column(db.DateTime)
    bounce_count = db.Column(db.Integer, default=0)
    email_bounced = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'team_id': self.team_id,
            'team': self.team.to_dict() if self.team else None,
            'preferred_frequency': self.preferred_frequency,
            'active': self.active,
            'unsubscribe_token': self.unsubscribe_token,
            'last_email_sent': self.last_email_sent.isoformat() if self.last_email_sent else None,
            'bounce_count': self.bounce_count,
            'email_bounced': self.email_bounced,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class EmailToken(db.Model):
    __tablename__ = 'email_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(50), nullable=False)  # 'verify', 'manage', 'unsubscribe'
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    metadata_json = db.Column(db.Text)  # optional JSON payload
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)
        expires = _as_utc(self.expires_at)
        used = _as_utc(self.used_at)
        return (used is None) and (expires is None or expires > now)

    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'email': self.email,
            'purpose': self.purpose,
            'expires_at': (_as_utc(self.expires_at).isoformat() if self.expires_at else None),
            'used_at': (_as_utc(self.used_at).isoformat() if self.used_at else None),
            'metadata_json': self.metadata_json,
            'created_at': (_as_utc(self.created_at).isoformat() if self.created_at else None),
        }

# Guest-submitted player flags for corrections
class PlayerFlag(db.Model):
    __tablename__ = 'loan_flags'  # DB table name unchanged

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    primary_team_api_id = db.Column(db.Integer, nullable=False)
    loan_team_api_id = db.Column(db.Integer, nullable=True)
    season = db.Column(db.Integer, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(255))
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(512))
    status = db.Column(db.String(20), default='pending')  # pending|resolved
    admin_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)


class TeamTrackingRequest(db.Model):
    """User requests to track a team's loan players.
    
    When users see a team isn't being tracked, they can submit a request
    which admin can approve or reject.
    """
    __tablename__ = 'team_tracking_requests'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    team_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255))
    reason = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(512))
    status = db.Column(db.String(20), default='pending')  # pending|approved|rejected
    admin_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)

    team = db.relationship('Team', backref='tracking_requests', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'team_api_id': self.team_api_id,
            'team_name': self.team_name,
            'team_logo': self.team.logo if self.team else None,
            'team_league': self.team.league.name if self.team and self.team.league else None,
            'email': self.email,
            'reason': self.reason,
            'status': self.status,
            'admin_note': self.admin_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }


class AdminSetting(db.Model):
    __tablename__ = 'admin_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value_json = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value_json,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class UserAccount(db.Model):
    __tablename__ = 'user_accounts'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    display_name = db.Column(db.String(80), nullable=False)
    display_name_lower = db.Column(db.String(80), unique=True, nullable=False)
    display_name_confirmed = db.Column(db.Boolean, default=False)
    can_author_commentary = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime)
    last_display_name_change_at = db.Column(db.DateTime)

    # Journalist fields
    is_journalist = db.Column(db.Boolean, default=False, nullable=False)
    bio = db.Column(db.Text)
    profile_image_url = db.Column(db.Text)
    attribution_url = db.Column(db.String(500))
    attribution_name = db.Column(db.String(120))

    # Email preferences
    email_delivery_preference = db.Column(db.String(20), default='individual', nullable=False)  # 'individual' | 'digest'

    # Editor role - can manage external writers
    is_editor = db.Column(db.Boolean, default=False, nullable=False)

    # Curator role - can add tweets/attributions to newsletters for approved teams
    is_curator = db.Column(db.Boolean, default=False, nullable=False)

    # Placeholder account fields - for external writers managed by editors
    managed_by_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    claimed_at = db.Column(db.DateTime, nullable=True)  # null = unclaimed placeholder
    claim_token = db.Column(db.String(100), unique=True, nullable=True, index=True)
    claim_token_expires_at = db.Column(db.DateTime, nullable=True)

    # Self-referential relationship for editor -> managed writers
    managed_by = db.relationship(
        'UserAccount',
        remote_side='UserAccount.id',
        backref=db.backref('managed_writers', lazy='dynamic'),
        foreign_keys=[managed_by_user_id]
    )

    comments = db.relationship('NewsletterComment', back_populates='user', lazy=True)
    commentaries = db.relationship('NewsletterCommentary', back_populates='author', lazy=True)
    
    # Relationships for subscriptions
    journalist_subscriptions = db.relationship('JournalistSubscription', 
                                             foreign_keys='JournalistSubscription.journalist_user_id',
                                             backref='journalist', lazy=True)
    subscribed_to = db.relationship('JournalistSubscription',
                                  foreign_keys='JournalistSubscription.subscriber_user_id',
                                  backref='subscriber', lazy=True)

    def is_placeholder(self) -> bool:
        """Return True if this is an unclaimed placeholder account (created by an editor)."""
        return self.managed_by_user_id is not None and self.claimed_at is None

    def is_claimed(self) -> bool:
        """Return True if this placeholder account has been claimed by the writer."""
        return self.managed_by_user_id is not None and self.claimed_at is not None

    def to_dict(self):
        return {
            'id': self.id,
            'email': sanitize_plain_text(self.email) if self.email else None,
            'display_name': sanitize_plain_text(self.display_name) if self.display_name else None,
            'display_name_confirmed': bool(self.display_name_confirmed),
            'can_author_commentary': bool(self.can_author_commentary),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_display_name_change_at': self.last_display_name_change_at.isoformat() if self.last_display_name_change_at else None,
            'is_journalist': self.is_journalist,
            'bio': sanitize_plain_text(self.bio) if self.bio else None,
            'profile_image_url': self.profile_image_url,
            'attribution_url': self.attribution_url,
            'attribution_name': self.attribution_name,
            'email_delivery_preference': self.email_delivery_preference or 'individual',
            'is_editor': self.is_editor,
            'is_curator': self.is_curator,
            'is_placeholder': self.is_placeholder(),
            'is_claimed': self.is_claimed(),
            'managed_by_user_id': self.managed_by_user_id,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None,
        }


class NewsletterComment(db.Model):
    __tablename__ = 'newsletter_comments'

    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    author_email = db.Column(db.String(255), nullable=False)
    author_name = db.Column(db.String(120))
    author_name_legacy = db.Column(db.String(120))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_deleted = db.Column(db.Boolean, default=False)

    user = db.relationship('UserAccount', back_populates='comments')

    def to_dict(self):
        display_name = None
        display_name_confirmed = None
        if self.user and self.user.display_name:
            current_name = sanitize_plain_text(self.user.display_name)
            display_name_confirmed = bool(self.user.display_name_confirmed)
            legacy_raw = self.author_name_legacy or self.author_name
            legacy = sanitize_plain_text(legacy_raw) if legacy_raw else None
            if legacy and legacy != current_name:
                display_name = f"{legacy} (now: {current_name})"
            else:
                display_name = current_name
        elif self.author_name:
            display_name = sanitize_plain_text(self.author_name)
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'author_email': sanitize_plain_text(self.author_email) if self.author_email else None,
            'author_name': sanitize_plain_text(self.author_name) if self.author_name else None,
            'author_name_legacy': sanitize_plain_text(self.author_name_legacy) if self.author_name_legacy else None,
            'author_display_name': display_name,
            'author_display_name_confirmed': display_name_confirmed,
            'user_id': self.user_id,
            'body': sanitize_comment_body(self.body) if not self.is_deleted else '',
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NewsletterPlayerYoutubeLink(db.Model):
    """YouTube highlights links for players in newsletters.

    Uses player_id for both tracked (positive IDs) and manual (negative IDs) players.
    Manual players are identified by:
    - player_id < 0 (negative IDs from migration or Players & Loans Manager)
    - Corresponding TrackedPlayer.can_fetch_stats = False
    """
    __tablename__ = 'newsletter_player_youtube_links'

    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=False)
    player_id = db.Column(db.Integer, nullable=False)  # Player ID: positive for tracked, negative for manual players
    player_name = db.Column(db.String(120), nullable=False)  # For display/reference
    youtube_link = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    newsletter = db.relationship('Newsletter', backref='youtube_links', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'youtube_link': self.youtube_link,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NewsletterCommentary(db.Model):
    """Commentary added by authorized authors to newsletters.
    
    Supports three types of commentary:
    - 'player': Commentary attached to a specific player's performance
    - 'intro': Opening commentary for the newsletter
    - 'summary': Closing commentary/wrap-up for the newsletter
    
    All content is sanitized on save to prevent XSS attacks.
    """
    __tablename__ = 'newsletter_commentary'
    
    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=True)  # Now nullable
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)  # For week-based creation
    player_id = db.Column(db.Integer, nullable=True)  # Nullable for intro/summary commentary
    commentary_type = db.Column(db.String(20), nullable=False)  # 'player', 'intro', 'summary'
    content = db.Column(db.Text, nullable=False)  # Sanitized HTML content
    author_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False)
    author_name = db.Column(db.String(120), nullable=False)  # Cached display name
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor_profiles.id', ondelete='SET NULL'), nullable=True)
    contributor_name = db.Column(db.String(120), nullable=True)  # Cached contributor display name
    position = db.Column(db.Integer, default=0, nullable=False)  # For ordering multiple commentaries
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # New fields for journalist articles
    title = db.Column(db.String(200))
    is_premium = db.Column(db.Boolean, default=True, nullable=False)
    
    # Structured blocks for modular content builder (stores array of block objects)
    # Each block has: id, type (text|chart|divider), content, is_premium, position, chart_config
    structured_blocks = db.Column(db.JSON, nullable=True)
    

    
    # Week-based association fields (for pre-newsletter creation)
    week_start_date = db.Column(db.Date, nullable=True)
    week_end_date = db.Column(db.Date, nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    newsletter = db.relationship('Newsletter', backref='commentaries', lazy=True)
    author = db.relationship('UserAccount', back_populates='commentaries', lazy=True)
    contributor = db.relationship('ContributorProfile', lazy=True)
    team = db.relationship('Team', lazy=True)
    applause = db.relationship('CommentaryApplause', backref='commentary', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        from src.utils.sanitize import sanitize_plain_text
        
        # Content is already sanitized on write, no need to re-sanitize on read
        # (Re-sanitizing caused errors with large content like base64 chart images)
        
        # Get author profile image if author relationship exists
        author_profile_image = None
        if self.author:
            author_profile_image = self.author.profile_image_url

        # Get contributor info if contributor relationship exists
        contributor_photo_url = None
        contributor_attribution_url = None
        contributor_attribution_name = None
        if self.contributor:
            contributor_photo_url = self.contributor.photo_url
            contributor_attribution_url = self.contributor.attribution_url
            contributor_attribution_name = self.contributor.attribution_name

        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else (self.newsletter.team.name if self.newsletter and self.newsletter.team else None),
            'player_id': self.player_id,
            'commentary_type': self.commentary_type,
            'content': self.content or '',
            'structured_blocks': self.structured_blocks,
            'author_id': self.author_id,
            'author_name': sanitize_plain_text(self.author_name) if self.author_name else None,
            'author_profile_image': author_profile_image,
            'contributor_id': self.contributor_id,
            'contributor_name': sanitize_plain_text(self.contributor_name) if self.contributor_name else None,
            'contributor_photo_url': contributor_photo_url,
            'contributor_attribution_url': contributor_attribution_url,
            'contributor_attribution_name': contributor_attribution_name,
            'position': self.position,
            'is_active': self.is_active,
            'title': sanitize_plain_text(self.title) if self.title else None,
            'is_premium': self.is_premium,
            'week_start_date': self.week_start_date.isoformat() if self.week_start_date else None,
            'week_end_date': self.week_end_date.isoformat() if self.week_end_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'applause_count': self.applause.count(),
        }
    
    def validate_commentary_type(self):
        """Validate that commentary_type is one of the allowed values."""
        allowed_types = ['player', 'intro', 'summary']
        if self.commentary_type not in allowed_types:
            raise ValueError(f'commentary_type must be one of {allowed_types}, got: {self.commentary_type}')
    
    def validate_player_commentary(self):
        """Validate that player_id is present if commentary_type is 'player'."""
        if self.commentary_type == 'player' and not self.player_id:
            raise ValueError("Player ID is required for player commentary")


class CommentaryApplause(db.Model):
    """Tracks applause/likes for newsletter commentaries."""
    __tablename__ = 'commentary_applause'

    id = db.Column(db.Integer, primary_key=True)
    commentary_id = db.Column(db.Integer, db.ForeignKey('newsletter_commentary.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    session_id = db.Column(db.String(100), nullable=True)  # For anonymous tracking
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'commentary_id': self.commentary_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @staticmethod
    def sanitize_and_create(newsletter_id, author_id, author_name, commentary_type, content, player_id=None, position=0):
        """Factory method that sanitizes content before creating a commentary."""
        from src.utils.sanitize import sanitize_commentary_html
        
        # Sanitize content
        sanitized_content = sanitize_commentary_html(content)
        
        # Create instance
        commentary = NewsletterCommentary(
            newsletter_id=newsletter_id,
            author_id=author_id,
            author_name=author_name,
            commentary_type=commentary_type,
            content=sanitized_content,
            player_id=player_id,
            position=position,
        )
        
        # Validate
        commentary.validate_commentary_type()
        commentary.validate_player_commentary()
        
        return commentary


class JournalistSubscription(db.Model):
    __tablename__ = 'journalist_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    subscriber_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('subscriber_user_id', 'journalist_user_id', name='uq_journalist_subscription'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'subscriber_user_id': self.subscriber_user_id,
            'journalist_user_id': self.journalist_user_id,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class JournalistTeamAssignment(db.Model):
    __tablename__ = 'journalist_team_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    assigned_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)

    # Relationships
    journalist = db.relationship('UserAccount', foreign_keys=[user_id], backref=db.backref('assigned_teams', lazy=True))
    team = db.relationship('Team', backref=db.backref('assigned_journalists', lazy=True))
    assigner = db.relationship('UserAccount', foreign_keys=[assigned_by])

    __table_args__ = (
        db.UniqueConstraint('user_id', 'team_id', name='uq_journalist_team_assignment'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'assigned_by': self.assigned_by
        }


class JournalistLoanTeamAssignment(db.Model):
    """Assignment of a journalist to cover players at a specific loan destination.
    
    This enables a writer who watches a specific club (e.g., Falkirk) to write
    about ANY player loaned TO that club, regardless of parent club.
    
    Supports both DB-tracked teams (loan_team_id set) and custom teams
    (loan_team_name only, loan_team_id NULL).
    """
    __tablename__ = 'journalist_loan_team_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    loan_team_name = db.Column(db.String(100), nullable=False)  # Always stored for display
    loan_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)  # Nullable for custom teams
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    assigned_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)

    # Relationships
    journalist = db.relationship('UserAccount', foreign_keys=[user_id], 
                                  backref=db.backref('loan_team_assignments', lazy=True))
    loan_team = db.relationship('Team', backref=db.backref('loan_team_journalists', lazy=True))
    assigner = db.relationship('UserAccount', foreign_keys=[assigned_by])

    __table_args__ = (
        # Unique per user + team name (handles both DB and custom teams)
        db.UniqueConstraint('user_id', 'loan_team_name', name='uq_journalist_loan_team_assignment'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'loan_team_id': self.loan_team_id,
            'loan_team_name': self.loan_team_name,
            'loan_team_logo': self.loan_team.logo if self.loan_team else None,
            'is_custom_team': self.loan_team_id is None,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'assigned_by': self.assigned_by
        }


class WriterCoverageRequest(db.Model):
    """Request from a writer to cover a specific team (parent club or loan destination).
    
    Writers submit requests which admins can approve or deny. On approval,
    the appropriate assignment record is created (JournalistTeamAssignment 
    for parent clubs, JournalistLoanTeamAssignment for loan destinations).
    """
    __tablename__ = 'writer_coverage_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    coverage_type = db.Column(db.String(20), nullable=False)  # 'parent_club' | 'loan_team'
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)  # FK if team in DB
    team_name = db.Column(db.String(100), nullable=False)  # Always stored (for custom teams too)
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending' | 'approved' | 'denied'
    request_message = db.Column(db.Text, nullable=True)  # Why they want coverage
    denial_reason = db.Column(db.Text, nullable=True)  # Admin's reason for denial
    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)

    # Relationships
    writer = db.relationship('UserAccount', foreign_keys=[user_id],
                              backref=db.backref('coverage_requests', lazy=True))
    team = db.relationship('Team', lazy=True)
    reviewer = db.relationship('UserAccount', foreign_keys=[reviewed_by])

    __table_args__ = (
        db.Index('ix_coverage_requests_status', 'status'),
        db.Index('ix_coverage_requests_user', 'user_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'writer_name': self.writer.display_name if self.writer else None,
            'writer_email': self.writer.email if self.writer else None,
            'coverage_type': self.coverage_type,
            'team_id': self.team_id,
            'team_name': self.team_name,
            'team_logo': self.team.logo if self.team else None,
            'is_custom_team': self.team_id is None,
            'status': self.status,
            'request_message': self.request_message,
            'denial_reason': self.denial_reason,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewed_by': self.reviewed_by
        }


# =============================================================================
# DEPRECATED: Stripe models below are kept for data preservation only.
# The Academy Watch refactor removed Stripe payment integration.
# Do not use these models in new code. Tables may be dropped in future migration.
# =============================================================================

class StripeConnectedAccount(db.Model):
    """DEPRECATED: Stores journalist Stripe Connect account info"""
    __tablename__ = 'stripe_connected_accounts'

    id = db.Column(db.Integer, primary_key=True)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False, unique=True)
    stripe_account_id = db.Column(db.String(255), unique=True, nullable=False)
    onboarding_complete = db.Column(db.Boolean, default=False, nullable=False)
    payouts_enabled = db.Column(db.Boolean, default=False, nullable=False)
    charges_enabled = db.Column(db.Boolean, default=False, nullable=False)
    details_submitted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    journalist = db.relationship('UserAccount', foreign_keys=[journalist_user_id], backref=db.backref('stripe_account', uselist=False))

    def to_dict(self):
        return {
            'id': self.id,
            'journalist_user_id': self.journalist_user_id,
            'stripe_account_id': self.stripe_account_id,
            'onboarding_complete': self.onboarding_complete,
            'payouts_enabled': self.payouts_enabled,
            'charges_enabled': self.charges_enabled,
            'details_submitted': self.details_submitted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StripeSubscriptionPlan(db.Model):
    """DEPRECATED: Journalist-defined subscription pricing"""
    __tablename__ = 'stripe_subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    stripe_product_id = db.Column(db.String(255), nullable=False)
    stripe_price_id = db.Column(db.String(255), nullable=False, unique=True)
    price_amount = db.Column(db.Integer, nullable=False)  # in cents
    currency = db.Column(db.String(3), default='usd', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    journalist = db.relationship('UserAccount', foreign_keys=[journalist_user_id], backref=db.backref('subscription_plans', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'journalist_user_id': self.journalist_user_id,
            'stripe_product_id': self.stripe_product_id,
            'stripe_price_id': self.stripe_price_id,
            'price_amount': self.price_amount,
            'price_display': f"${self.price_amount / 100:.2f}",
            'currency': self.currency,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StripeSubscription(db.Model):
    """DEPRECATED: Tracks active Stripe subscriptions"""
    __tablename__ = 'stripe_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    subscriber_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    stripe_customer_id = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # active, canceled, past_due, etc.
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('subscriber_user_id', 'journalist_user_id', name='uq_stripe_subscription'),
    )

    # Relationships
    subscriber = db.relationship('UserAccount', foreign_keys=[subscriber_user_id], backref=db.backref('stripe_subscriptions', lazy=True))
    journalist = db.relationship('UserAccount', foreign_keys=[journalist_user_id], backref=db.backref('stripe_subscribers', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'subscriber_user_id': self.subscriber_user_id,
            'journalist_user_id': self.journalist_user_id,
            'stripe_subscription_id': self.stripe_subscription_id,
            'stripe_customer_id': self.stripe_customer_id,
            'status': self.status,
            'current_period_start': self.current_period_start.isoformat() if self.current_period_start else None,
            'current_period_end': self.current_period_end.isoformat() if self.current_period_end else None,
            'cancel_at_period_end': self.cancel_at_period_end,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StripePlatformRevenue(db.Model):
    """DEPRECATED: Tracks platform fees for admin dashboard"""
    __tablename__ = 'stripe_platform_revenue'

    id = db.Column(db.Integer, primary_key=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    total_revenue_cents = db.Column(db.Integer, default=0, nullable=False)  # Total subscriptions processed
    platform_fee_cents = db.Column(db.Integer, default=0, nullable=False)  # 10% collected
    subscription_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'total_revenue_cents': self.total_revenue_cents,
            'total_revenue_display': f"${self.total_revenue_cents / 100:.2f}",
            'platform_fee_cents': self.platform_fee_cents,
            'platform_fee_display': f"${self.platform_fee_cents / 100:.2f}",
            'subscription_count': self.subscription_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class NewsletterDigestQueue(db.Model):
    """Queue for newsletters to be sent as part of a weekly digest email"""
    __tablename__ = 'newsletter_digest_queue'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id'), nullable=False)
    week_key = db.Column(db.String(20), nullable=False)  # e.g., '2025-W48' for grouping
    queued_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent = db.Column(db.Boolean, default=False, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'newsletter_id', name='uq_digest_queue_user_newsletter'),
        db.Index('ix_digest_queue_week_sent', 'week_key', 'sent'),
    )

    # Relationships
    user = db.relationship('UserAccount', backref=db.backref('digest_queue', lazy=True))
    newsletter = db.relationship('Newsletter', backref=db.backref('digest_queue_entries', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'newsletter_id': self.newsletter_id,
            'week_key': self.week_key,
            'queued_at': self.queued_at.isoformat() if self.queued_at else None,
            'sent': self.sent,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }


class BackgroundJob(db.Model):
    """Stores background job state in the database for multi-worker environments.
    
    This replaces in-memory job storage to ensure all gunicorn workers can access
    the same job state. Jobs are persisted and can be queried across workers.
    """
    __tablename__ = 'background_jobs'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    job_type = db.Column(db.String(50), nullable=False)  # seed_top5, fix_miscategorized, etc.
    status = db.Column(db.String(20), nullable=False, default='running')  # running, completed, failed
    progress = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    current_player = db.Column(db.String(200))
    results_json = db.Column(db.Text)  # JSON serialized results
    error = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_background_jobs_status', 'status'),
        db.Index('ix_background_jobs_created', 'created_at'),
    )

    def to_dict(self):
        import json
        results = None
        if self.results_json:
            try:
                results = json.loads(self.results_json)
            except (json.JSONDecodeError, TypeError):
                results = None
        
        return {
            'id': self.id,
            'type': self.job_type,
            'status': self.status,
            'progress': self.progress,
            'total': self.total,
            'current_player': self.current_player,
            'results': results,
            'error': self.error,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class TeamSubreddit(db.Model):
    """Maps teams to their subreddit(s) for Reddit posting.
    
    Each team can have multiple subreddits configured with different
    posting formats (full or compact markdown).
    """
    __tablename__ = 'team_subreddits'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    subreddit_name = db.Column(db.String(50), nullable=False)  # e.g., "reddevils" without r/
    post_format = db.Column(db.String(20), nullable=False, default='full')  # 'full' or 'compact'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    team = db.relationship('Team', backref=db.backref('subreddits', lazy=True))
    posts = db.relationship('RedditPost', backref='team_subreddit', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('team_id', 'subreddit_name', name='uq_team_subreddit'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'subreddit_name': self.subreddit_name,
            'subreddit_url': f'https://reddit.com/r/{self.subreddit_name}',
            'post_format': self.post_format,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class RedditPost(db.Model):
    """Tracks posts made to Reddit for history and preventing duplicates.
    
    Each newsletter can be posted to multiple subreddits, and this table
    tracks the status and URL of each post.
    """
    __tablename__ = 'reddit_posts'

    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=False)
    team_subreddit_id = db.Column(db.Integer, db.ForeignKey('team_subreddits.id', ondelete='CASCADE'), nullable=False)
    reddit_post_id = db.Column(db.String(20))  # Reddit's post ID (e.g., "abc123")
    reddit_post_url = db.Column(db.String(255))  # Full URL to the post
    post_title = db.Column(db.String(300), nullable=False)  # Title used for the post
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending', 'success', 'failed', 'deleted'
    error_message = db.Column(db.Text)  # Error details if posting failed
    posted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    newsletter = db.relationship('Newsletter', backref=db.backref('reddit_posts', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('newsletter_id', 'team_subreddit_id', name='uq_newsletter_subreddit_post'),
        db.Index('ix_reddit_posts_status', 'status'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'team_subreddit_id': self.team_subreddit_id,
            'subreddit_name': self.team_subreddit.subreddit_name if self.team_subreddit else None,
            'reddit_post_id': self.reddit_post_id,
            'reddit_post_url': self.reddit_post_url,
            'post_title': self.post_title,
            'status': self.status,
            'error_message': self.error_message,
            'posted_at': self.posted_at.isoformat() if self.posted_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class TeamAlias(db.Model):
    __tablename__ = 'team_aliases'

    id = db.Column(db.Integer, primary_key=True)
    canonical_name = db.Column(db.String(100), nullable=False)
    alias = db.Column(db.String(100), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    team = db.relationship('Team', backref='aliases', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'canonical_name': self.canonical_name,
            'alias': self.alias,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ManualPlayerSubmission(db.Model):
    __tablename__ = 'manual_player_submissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    team_name = db.Column(db.String(100), nullable=False)
    league_name = db.Column(db.String(100), nullable=True)
    position = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, approved, rejected
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)

    # Relationships
    user = db.relationship('UserAccount', foreign_keys=[user_id], backref=db.backref('manual_submissions', lazy=True))
    reviewer = db.relationship('UserAccount', foreign_keys=[reviewed_by])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.display_name if self.user else None,
            'player_name': self.player_name,
            'team_name': self.team_name,
            'league_name': self.league_name,
            'position': self.position,
            'notes': self.notes,
            'status': self.status,
            'admin_notes': self.admin_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewed_by': self.reviewed_by
        }


class AcademyLeague(db.Model):
    """Configuration for academy/youth leagues to track.

    Stores which youth leagues (U18, U21, U23, Reserves) should be synced
    from API-Football for tracking academy player appearances.
    """
    __tablename__ = 'academy_leagues'

    id = db.Column(db.Integer, primary_key=True)
    api_league_id = db.Column(db.Integer, nullable=False, unique=True)  # API-Football league ID
    name = db.Column(db.String(200), nullable=False)
    country = db.Column(db.String(100), nullable=True)
    level = db.Column(db.String(20), nullable=False)  # 'U18' | 'U21' | 'U23' | 'Reserve'
    season = db.Column(db.Integer, nullable=True)  # Current season year
    is_active = db.Column(db.Boolean, default=True)

    # Optional: Link to parent club team for filtering
    parent_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    # Sync tracking
    last_synced_at = db.Column(db.DateTime, nullable=True)
    sync_enabled = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    parent_team = db.relationship('Team', backref=db.backref('academy_leagues', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'api_league_id': self.api_league_id,
            'name': self.name,
            'country': self.country,
            'level': self.level,
            'season': self.season,
            'is_active': self.is_active,
            'parent_team_id': self.parent_team_id,
            'parent_team_name': self.parent_team.name if self.parent_team else None,
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
            'sync_enabled': self.sync_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AcademyAppearance(db.Model):
    """Tracks a player's appearance in an academy/youth match.

    Since youth leagues often have limited stats coverage, this model
    focuses on what's reliably available: appearance, minutes, goals, assists.
    """
    __tablename__ = 'academy_appearances'

    id = db.Column(db.Integer, primary_key=True)

    # Player reference
    player_id = db.Column(db.Integer, nullable=False)  # API-Football player ID
    player_name = db.Column(db.String(100), nullable=False)  # Cached for display

    # Match reference
    fixture_id = db.Column(db.Integer, nullable=False)  # API-Football fixture ID
    fixture_date = db.Column(db.Date, nullable=False)
    home_team = db.Column(db.String(100), nullable=True)
    away_team = db.Column(db.String(100), nullable=True)
    competition = db.Column(db.String(100), nullable=True)

    # League reference
    academy_league_id = db.Column(db.Integer, db.ForeignKey('academy_leagues.id'), nullable=True)

    # Appearance data (what we can reliably get from lineups/events)
    started = db.Column(db.Boolean, default=False)  # In starting XI
    minutes_played = db.Column(db.Integer, nullable=True)  # If available
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    yellow_cards = db.Column(db.Integer, default=0)
    red_cards = db.Column(db.Integer, default=0)

    # Raw data for debugging
    lineup_data = db.Column(db.JSON, nullable=True)
    events_data = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    academy_league = db.relationship('AcademyLeague', backref=db.backref('appearances', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('player_id', 'fixture_id', name='uq_academy_appearance_player_fixture'),
        db.Index('ix_academy_appearances_player', 'player_id'),
        db.Index('ix_academy_appearances_fixture_date', 'fixture_date'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'fixture_id': self.fixture_id,
            'fixture_date': self.fixture_date.isoformat() if self.fixture_date else None,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'competition': self.competition,
            'academy_league_id': self.academy_league_id,
            'started': self.started,
            'minutes_played': self.minutes_played,
            'goals': self.goals,
            'assists': self.assists,
            'yellow_cards': self.yellow_cards,
            'red_cards': self.red_cards,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CommunityTake(db.Model):
    """Community-sourced commentary about players.

    Takes can come from multiple sources:
    - 'reddit': Scraped from subreddits
    - 'twitter': Scraped from Twitter/X
    - 'submission': User-submitted via QuickTakeSubmission
    - 'editor': Written by the editor directly

    Takes go through a curation workflow where they are approved/rejected
    before being included in newsletters.
    """
    __tablename__ = 'community_takes'

    id = db.Column(db.Integer, primary_key=True)

    # Source information
    source_type = db.Column(db.String(20), nullable=False)  # 'reddit' | 'twitter' | 'submission' | 'editor'
    source_url = db.Column(db.String(500), nullable=True)  # Original URL if from external source
    source_author = db.Column(db.String(100), nullable=False)  # Reddit username, Twitter handle, or display name
    source_platform = db.Column(db.String(50), nullable=True)  # 'r/reddevils', '@handle', etc.

    # Content
    content = db.Column(db.Text, nullable=False)  # The actual take (1-3 sentences)

    # Association - can be linked to player, team, and/or newsletter
    player_id = db.Column(db.Integer, nullable=True)  # API-Football player ID
    player_name = db.Column(db.String(100), nullable=True)  # Cached for display
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id'), nullable=True)

    # Curation workflow
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending' | 'approved' | 'rejected'
    curated_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    curated_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)

    # Metadata from source
    scraped_at = db.Column(db.DateTime, nullable=True)  # When we scraped it (if external)
    original_posted_at = db.Column(db.DateTime, nullable=True)  # When it was originally posted
    upvotes = db.Column(db.Integer, default=0)  # From Reddit/Twitter engagement

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    team = db.relationship('Team', backref=db.backref('community_takes', lazy=True))
    newsletter = db.relationship('Newsletter', backref=db.backref('community_takes', lazy=True))
    curator = db.relationship('UserAccount', foreign_keys=[curated_by])

    __table_args__ = (
        db.Index('ix_community_takes_status', 'status'),
        db.Index('ix_community_takes_player', 'player_id'),
        db.Index('ix_community_takes_team', 'team_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'source_type': self.source_type,
            'source_url': self.source_url,
            'source_author': self.source_author,
            'source_platform': self.source_platform,
            'content': self.content,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'newsletter_id': self.newsletter_id,
            'status': self.status,
            'curated_by': self.curated_by,
            'curated_at': self.curated_at.isoformat() if self.curated_at else None,
            'rejection_reason': self.rejection_reason,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None,
            'original_posted_at': self.original_posted_at.isoformat() if self.original_posted_at else None,
            'upvotes': self.upvotes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class QuickTakeSubmission(db.Model):
    """User-submitted quick takes pending moderation.

    This is the intake table for community submissions. When approved,
    a CommunityTake record is created and linked via community_take_id.

    Supports anonymous submissions (submitter_name/email optional) with
    IP hashing for spam prevention.
    """
    __tablename__ = 'quick_take_submissions'

    id = db.Column(db.Integer, primary_key=True)

    # Submitter info (can be anonymous)
    submitter_name = db.Column(db.String(100), nullable=True)
    submitter_email = db.Column(db.String(255), nullable=True)

    # Content
    player_id = db.Column(db.Integer, nullable=True)  # API-Football player ID
    player_name = db.Column(db.String(100), nullable=False)  # Always required for display
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)  # Max ~280 chars enforced at API level

    # Moderation workflow
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending' | 'approved' | 'rejected'
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)

    # Link to approved CommunityTake (set when approved)
    community_take_id = db.Column(db.Integer, db.ForeignKey('community_takes.id'), nullable=True)

    # Spam prevention
    ip_hash = db.Column(db.String(64), nullable=True)  # SHA-256 hash of IP
    user_agent = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    team = db.relationship('Team', backref=db.backref('quick_take_submissions', lazy=True))
    reviewer = db.relationship('UserAccount', foreign_keys=[reviewed_by])
    community_take = db.relationship('CommunityTake', backref=db.backref('submission', uselist=False))

    __table_args__ = (
        db.Index('ix_quick_take_submissions_status', 'status'),
        db.Index('ix_quick_take_submissions_ip', 'ip_hash'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'submitter_name': self.submitter_name,
            'submitter_email': self.submitter_email,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'content': self.content,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'rejection_reason': self.rejection_reason,
            'community_take_id': self.community_take_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ContributorProfile(db.Model):
    """Profile for external contributors (scouts, guest analysts) who can be credited on commentaries.

    Allows journalists to create profiles for contributors who don't want to register
    as full users but still need attribution on content.
    """
    __tablename__ = 'contributor_profiles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    photo_url = db.Column(db.Text, nullable=True)
    attribution_url = db.Column(db.String(500), nullable=True)
    attribution_name = db.Column(db.String(120), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    created_by = db.relationship('UserAccount', foreign_keys=[created_by_id],
                                  backref=db.backref('contributor_profiles', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'bio': self.bio,
            'photo_url': self.photo_url,
            'attribution_url': self.attribution_url,
            'attribution_name': self.attribution_name,
            'created_by_id': self.created_by_id,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class RebuildConfig(db.Model):
    """Named rebuild configuration preset with all pipeline parameters."""
    __tablename__ = 'rebuild_configs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    config_json = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    logs = db.relationship('RebuildConfigLog', backref='config',
                           lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self, include_config=True):
        import json
        d = {
            'id': self.id,
            'name': self.name,
            'is_active': self.is_active,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_config:
            try:
                d['config'] = json.loads(self.config_json)
            except (json.JSONDecodeError, TypeError):
                d['config'] = {}
        return d


class PlayerComment(db.Model):
    """User comments on player pages."""
    __tablename__ = 'player_comments'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, nullable=False)  # API-Football player ID
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    author_email = db.Column(db.String(255), nullable=False)
    author_name = db.Column(db.String(120))
    body = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('UserAccount', backref='player_comments')

    def to_dict(self):
        display_name = None
        if self.user and self.user.display_name:
            display_name = sanitize_plain_text(self.user.display_name)
        return {
            'id': self.id,
            'player_id': self.player_id,
            'author_name': sanitize_plain_text(self.author_name) if self.author_name else None,
            'author_display_name': display_name,
            'body': self.body,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PlayerLink(db.Model):
    """User-submitted links on player pages (articles, highlights, etc.)."""
    __tablename__ = 'player_links'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, nullable=False)  # API-Football player ID
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    link_type = db.Column(db.String(30), default='article')  # article | highlight | social | stats | other
    status = db.Column(db.String(20), default='pending')      # pending | approved | rejected
    upvotes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('UserAccount', backref='player_links')

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'url': self.url,
            'title': self.title,
            'link_type': self.link_type,
            'status': self.status,
            'upvotes': self.upvotes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class RebuildConfigLog(db.Model):
    """Audit log entry for rebuild configuration changes."""
    __tablename__ = 'rebuild_config_logs'

    id = db.Column(db.Integer, primary_key=True)
    config_id = db.Column(db.Integer, db.ForeignKey('rebuild_configs.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    diff_json = db.Column(db.Text)
    snapshot_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        import json
        d = {
            'id': self.id,
            'config_id': self.config_id,
            'action': self.action,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        try:
            d['diff'] = json.loads(self.diff_json) if self.diff_json else None
        except (json.JSONDecodeError, TypeError):
            d['diff'] = None
        try:
            d['snapshot'] = json.loads(self.snapshot_json) if self.snapshot_json else None
        except (json.JSONDecodeError, TypeError):
            d['snapshot'] = None
        return d
