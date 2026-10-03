"""Run after a flag-changing deploy with AW_DEPLOYMENT_ID (or ACA revision) set."""

from src.main import app
from src.models.league import db
from src.services.admin_control_business import observe_deployment

if __name__ == "__main__":
    with app.app_context():
        row = observe_deployment()
        db.session.commit()
        print("deployment state recorded" if row else "disabled or deployment identity unavailable")
