"""Daily C1 privacy maintenance: python -m src.jobs.run_publication_retention."""

import argparse
import json

from src.utils.log_privacy import log_metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("limit must be 1–1000")
    from src.main import app
    from src.models.league import db
    from src.services.club_player_publication_account import purge_invited_emails

    with app.app_context():
        result = purge_invited_emails(limit=args.limit)
        db.session.commit()
        print(json.dumps(log_metadata(result)))


if __name__ == "__main__":
    main()
