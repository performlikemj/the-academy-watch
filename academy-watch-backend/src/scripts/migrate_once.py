import os
import sys
from pathlib import Path

import dotenv
from flask import Flask
from flask_migrate import Migrate, upgrade
from sqlalchemy.engine.url import make_url
from sqlalchemy.engine.url import URL

# Ensure project root is on sys.path so 'src.*' imports resolve when run as a file
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse app DB models (after path fix)
from src.models.league import db

# Ensure local development pulls in .env settings the same way the app does
dotenv.load_dotenv(dotenv.find_dotenv())


def _env_value(key: str) -> str | None:
    raw = os.getenv(key)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _build_db_uri_from_components() -> str:
    port_raw = _env_value("DB_PORT") or ""
    port_value = None
    if port_raw:
        try:
            port_value = int(port_raw)
        except ValueError:
            port_value = None
    url = URL.create(
        drivername="postgresql+psycopg",
        username=_env_value("DB_USER"),
        password=_env_value("DB_PASSWORD"),
        host=_env_value("DB_HOST"),
        port=port_value,
        database=_env_value("DB_NAME"),
        query={"sslmode": _env_value("DB_SSLMODE") or "require"},
    )
    return url.render_as_string(hide_password=False)


def main() -> None:
    app = Flask(__name__)
    raw = _env_value("SQLALCHEMY_DATABASE_URI")
    if raw:
        candidate = raw.strip().strip('"').strip("'")
        try:
            make_url(candidate)
            dsn = candidate
        except Exception:
            dsn = _build_db_uri_from_components()
    else:
        dsn = _build_db_uri_from_components()
    app.config["SQLALCHEMY_DATABASE_URI"] = dsn
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    # Ensure Flask-Migrate is initialized so Alembic env.py can access current_app.extensions['migrate']
    migrations_dir = PROJECT_ROOT / "migrations"
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Expected migrations directory at {migrations_dir}")

    Migrate(app, db, directory=str(migrations_dir))
    with app.app_context():
        upgrade(directory=str(migrations_dir))
    print("DONE")


if __name__ == "__main__":
    main()
