from datetime import date, datetime, timezone
from src.models.league import db
from src.agents.weekly_newsletter_agent import generate_team_weekly_newsletter
from src.agents.errors import NoActiveLoaneesError
from src.main import app
from src.utils.job_utils import teams_with_active_tracked_players, is_job_paused


def run_for_date(target_date: date):
    # Ensure we start from a clean transaction (in case a prior request aborted)
    try:
        db.session.rollback()
    except Exception:
        pass

    if is_job_paused('runs_paused'):
        return [{"error": "runs_paused", "team_id": None}]

    # Defensive rollback before running the query
    try:
        db.session.rollback()
    except Exception:
        pass
    team_ids = teams_with_active_tracked_players()
    results = []
    for team_db_id in team_ids:
        if is_job_paused('runs_paused'):
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
