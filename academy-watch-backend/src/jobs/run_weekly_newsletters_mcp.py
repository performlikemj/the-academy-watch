from datetime import date, datetime, timezone
from src.models.league import db, Team
from src.models.tracked_player import TrackedPlayer
from src.agents.weekly_agent import generate_weekly_newsletter_with_mcp_sync
from src.agents.errors import NoActiveLoaneesError


def teams_with_active_tracked_players() -> list[int]:
    """Return team DB IDs that have active TrackedPlayers (excluding released/sold)."""
    q = db.session.query(TrackedPlayer.team_id).filter(
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.status.notin_(['released', 'sold']),
    ).distinct()
    return [t[0] for t in q.all()]

def run_for_date(target: date, max_failures: int = 0):
    results = []
    failures = 0
    for team_db_id in teams_with_active_tracked_players():
        try:
            out = generate_weekly_newsletter_with_mcp_sync(team_db_id, target)
            results.append({"team_id": team_db_id, "status": "ok", "run": out})
        except NoActiveLoaneesError as e:
            results.append({"team_id": team_db_id, "status": "skipped", "reason": "no_active_loanees", "message": str(e)})
            continue
        except Exception as e:
            failures += 1
            results.append({"team_id": team_db_id, "status": "error", "error": str(e)})
            if max_failures == 0 or failures > max_failures:
                # Abort immediately
                raise RuntimeError(f"Aborting batch: {failures} failures so far; last={e}") from e
    return results

if __name__ == "__main__":
    today = datetime.now(timezone.utc).date()
    run_for_date(today)
