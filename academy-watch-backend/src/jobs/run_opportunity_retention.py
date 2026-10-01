"""python -m src.jobs.run_opportunity_retention --limit 100; works while dark."""

import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("limit must be 1–1000")
    from src.main import app
    from src.models.league import db
    from src.services.opportunities_account import purge_retained

    with app.app_context():
        result = purge_retained(limit=args.limit)
        db.session.commit()
        print(json.dumps(result))


if __name__ == "__main__":
    main()
