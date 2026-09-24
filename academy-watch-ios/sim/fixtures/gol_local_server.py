"""Run the real Flask app against local Postgres for the native GOL journey.

Only the optional --fixture-model replaces GolService's model completion layer.
Authentication, routing, SSE serialization and credit accounting remain real.
No environment file is loaded by Flask. --key-file reads only model and football API credentials.
"""

import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=53971)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--fixture-model", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    backend = root / "academy-watch-backend"
    keys = {}
    if args.key_file:
        from dotenv import dotenv_values

        values = dotenv_values(args.key_file)
        keys = {
            key: values[key]
            for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "API_FOOTBALL_KEY")
            if values.get(key)
        }
    # Prevent inherited remote databases, email delivery, integrations or allowlists.
    keep = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "LANG"}
    }
    os.environ.clear()
    os.environ.update(keep)
    os.environ.update(keys)
    os.environ.update(
        PYTHON_DOTENV_DISABLED="1",
        FLASK_ENV="development",
        FLASK_DEBUG="0",
        DB_HOST="127.0.0.1",
        DB_PORT="5432",
        DB_NAME="soccer_newsletter",
        DB_USER=getpass.getuser(),
        DB_PASSWORD="",
        DB_SSLMODE="disable",
        SECRET_KEY=secrets.token_hex(32),
        BILLING_ENABLED="1",
        GOL_FREE_ALLOWANCE="1",
        REVIEW_LOGIN_EMAIL="gol-ios-local@example.test",
        REVIEW_LOGIN_CODE="24680246802",  # Public synthetic fixture credential, local server only.
    )
    sys.path.insert(0, str(backend))
    os.chdir(backend)
    from src.main import app
    from src.models.gol_credits import GolChatExecution, GolCreditLedger
    from src.models.league import UserAccount, db

    with app.app_context():
        assert db.engine.url.host == "127.0.0.1"
        assert db.engine.url.database == "soccer_newsletter"
        user = UserAccount.query.filter_by(email="gol-ios-local@example.test").first()
        if user is None:
            user = UserAccount(
                email="gol-ios-local@example.test",
                display_name="GOL iOS Local Test",
                display_name_lower="gol ios local test",
                display_name_confirmed=True,
            )
            db.session.add(user)
            db.session.flush()
        GolChatExecution.query.filter_by(user_account_id=user.id).delete()
        GolCreditLedger.query.filter_by(user_account_id=user.id).delete()
        db.session.commit()

    if args.fixture_model:
        from src.services.gol_service import GolService

        def completion(self, messages, depth=0):
            for text in [
                "Synthetic local model fixture. ",
                "Academy progress combines ",
                "playing time, development and opportunity.",
            ]:
                time.sleep(0.6)
                yield {"event": "token", "data": {"content": text}}
            yield {"event": "done", "data": {}}

        # Constructor still runs; the synthetic key never reaches a network client.
        os.environ["OPENAI_API_KEY"] = "local-fixture-unused"
        GolService._run_completion = completion
    elif not keys.get("OPENAI_API_KEY"):
        raise SystemExit(
            "No local OpenAI key supplied. Use --key-file or explicit --fixture-model."
        )

    app.run(
        host="127.0.0.1", port=args.port, debug=False, threaded=True, use_reloader=False
    )


if __name__ == "__main__":
    main()
