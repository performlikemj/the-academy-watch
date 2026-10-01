"""Bounded repair of recent Stripe events; run periodically while Business is enabled."""

from src.main import app
from src.services.admin_control_business import reconcile_cash

if __name__ == "__main__":
    with app.app_context():
        reconcile_cash(limit=50)
