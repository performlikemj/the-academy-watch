"""Daily C4 retention; operates even after rollout is disabled."""

from src.main import app
from src.models.league import db
from src.services.scout_attendance_account import purge_expired

if __name__ == "__main__":
    with app.app_context():
        removed = 0
        # Keep each transaction bounded while draining the daily backlog.
        while True:
            batch = purge_expired()
            db.session.commit()
            removed += batch
            if batch < 100:
                break
        print({"removed": removed})
