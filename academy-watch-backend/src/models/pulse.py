"""Player pulse + shared AI card cache models.

Two composite-key tables that split editorial digest generation into a cheap
deterministic layer and a shared LLM layer:

- ``PlayerPulse`` — deterministic per-player-per-window newsworthiness score with
  full signal provenance in ``delta_json``. Computed ONCE per (player, window)
  regardless of how many users follow the player (see player_pulse_service).
- ``PlayerCardCache`` — the ONE place LLM output lives: a 2-3 sentence card per
  player per window, generated once and reused across every user's digest (see
  player_card_service).

Both are keyed on ``(player_api_id, window_end)`` — no surrogate id — mirroring
the data-model in ledgers/research/talent-platform/panel-grouping.md.
"""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import JSONB
from src.models.league import db


class PlayerPulse(db.Model):
    __tablename__ = "player_pulse"

    player_api_id = db.Column(db.Integer, nullable=False)
    window_end = db.Column(db.Date, nullable=False)
    # REAL in Postgres; deterministic weighted sum of the signals in delta_json.
    score = db.Column(db.Float, nullable=False)
    # Every contributing signal with its raw value + weight + points (provenance)
    # plus the player context block the card prompt is allowed to read.
    delta_json = db.Column(JSONB, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (db.PrimaryKeyConstraint("player_api_id", "window_end", name="pk_player_pulse"),)

    def to_dict(self):
        return {
            "player_api_id": self.player_api_id,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "score": self.score,
            "delta_json": self.delta_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PlayerCardCache(db.Model):
    __tablename__ = "player_card_cache"

    player_api_id = db.Column(db.Integer, nullable=False)
    window_end = db.Column(db.Date, nullable=False)
    # Outlook-safe HTML fragment (plain <p>/<strong> only) for the email template.
    card_html = db.Column(db.Text, nullable=False)
    card_text = db.Column(db.Text, nullable=False)  # plaintext equivalent
    model = db.Column(db.String(40))  # resolved LLM model string
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (db.PrimaryKeyConstraint("player_api_id", "window_end", name="pk_player_card_cache"),)

    def to_dict(self):
        return {
            "player_api_id": self.player_api_id,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "card_html": self.card_html,
            "card_text": self.card_text,
            "model": self.model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
