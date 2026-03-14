"""Shared utilities for scheduled job runners."""

from src.models.league import db, AdminSetting
from src.models.tracked_player import TrackedPlayer


def teams_with_active_tracked_players() -> list[int]:
    """Return team DB IDs that have active TrackedPlayers (excluding released/sold)."""
    q = db.session.query(TrackedPlayer.team_id).filter(
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.status.notin_(['released', 'sold']),
    ).distinct()
    return [t[0] for t in q.all()]


def is_job_paused(setting_key: str) -> bool:
    """Check if a job is paused via AdminSetting.

    Args:
        setting_key: The AdminSetting key to check (e.g. 'runs_paused',
                     'transfer_heal_paused').

    Returns:
        True if setting exists and is truthy (1, true, yes, y).
    """
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        row = db.session.query(AdminSetting).filter_by(key=setting_key).first()
        if row and row.value_json:
            return row.value_json.strip().lower() in ('1', 'true', 'yes', 'y')
    except Exception:
        return False
    return False
