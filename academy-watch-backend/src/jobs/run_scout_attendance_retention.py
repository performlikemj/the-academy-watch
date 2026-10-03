"""Daily C4 retention; operates even after rollout is disabled."""

from src.main import app
from src.models.league import db
from src.services.scout_attendance import expire_pending, revoke_ineligible
from src.services.scout_attendance_account import purge_expired
from src.utils.log_privacy import log_metadata

if __name__ == "__main__":
    with app.app_context():
        for sweep in (expire_pending, revoke_ineligible):
            while True:
                changed = sweep()
                db.session.commit()
                if changed < 100:
                    break
        removed = 0
        # Keep each transaction bounded while draining the daily backlog.
        while True:
            batch = purge_expired()
            db.session.commit()
            removed += batch
            if batch < 100:
                break
        print(log_metadata({"removed": removed}))
