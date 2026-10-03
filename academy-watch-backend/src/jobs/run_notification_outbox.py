"""Dispatch durable Phase 2 email intents: python -m src.jobs.run_notification_outbox."""

import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Also support the packaged direct-script entrypoint.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

with redirect_stdout(sys.stderr):
    from src.main import app

from src.services.notification_outbox import dispatch_due
from src.utils.log_privacy import log_metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)
    with app.app_context():
        summary = dispatch_due(limit=args.limit)
    print(json.dumps(log_metadata(summary), sort_keys=True))
    return 1 if summary["failed"] or summary["retry"] or summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
