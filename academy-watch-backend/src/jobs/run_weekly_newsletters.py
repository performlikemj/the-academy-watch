import os
from datetime import date, datetime, timezone
from src.models.league import db, Team, AdminSetting
from src.models.tracked_player import TrackedPlayer
from src.agents.weekly_newsletter_agent import generate_team_weekly_newsletter
from src.agents.errors import NoActiveLoaneesError
from src.main import app


def teams_with_active_tracked_players() -> list[int]:
    """Return team DB IDs that have active TrackedPlayers (excluding released/sold)."""
    q = db.session.query(TrackedPlayer.team_id).filter(
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.status.notin_(['released', 'sold']),
    ).distinct()
    return [t[0] for t in q.all()]

def run_for_date(target_date: date):
    # Ensure we start from a clean transaction (in case a prior request aborted)
    try:
        db.session.rollback()
    except Exception:
        pass
    def _runs_paused() -> bool:
        try:
            # Defensive rollback before metadata reads
            try:
                db.session.rollback()
            except Exception:
                pass
            row = db.session.query(AdminSetting).filter_by(key='runs_paused').first()
            if row and row.value_json:
                return row.value_json.strip().lower() in ('1','true','yes','y')
        except Exception:
            return False
        return False

    if _runs_paused():
        return [{"error": "runs_paused", "team_id": None}]

    # Defensive rollback before running the query
    try:
        db.session.rollback()
    except Exception:
        pass
    team_ids = teams_with_active_tracked_players()
    results = []
    for team_db_id in team_ids:
        if _runs_paused():
            results.append({"team_id": team_db_id, "error": "stopped_by_admin"})
            break
        try:
            # Clean transaction before generating; previous iterations may have errored
            try:
                db.session.rollback()
            except Exception:
                pass
            out = generate_team_weekly_newsletter(team_db_id, target_date)
            results.append({"team_id": team_db_id, "newsletter_id": out["id"]})
        except NoActiveLoaneesError as e:
            results.append({"team_id": team_db_id, "skipped": "no_active_loanees", "message": str(e)})
            continue
        except Exception as e:
            # Roll back the failed transaction so subsequent iterations can proceed
            try:
                db.session.rollback()
            except Exception:
                pass
            results.append({"team_id": team_db_id, "error": str(e)})
    return results

if __name__ == "__main__":
    # Ensure Flask application context is active for DB/session access
    today = datetime.now(timezone.utc).date()
    with app.app_context():
        run_for_date(today)
