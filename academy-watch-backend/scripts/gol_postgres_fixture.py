"""Local/CI schema baseline for the disposable GOL loader regression database.

The legacy migration graph cannot replay from an empty database. Build the model
baseline, stamp fl01, then run `flask --app scripts.gol_postgres_fixture db upgrade`
so current migrations (including database constraints) are applied normally.
"""

import importlib
import os
import pkgutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa
from flask import Flask
from flask_migrate import Migrate, stamp
from src.models.league import db


def create_app():
    uri = os.environ["GOL_POSTGRES_URL"]
    parsed = sa.engine.make_url(uri)
    assert parsed.database == "aw_sbxf2" and parsed.host in {"localhost", "127.0.0.1"}
    assert parsed.drivername == "postgresql+psycopg"
    import src.models

    for module in pkgutil.iter_modules(src.models.__path__):
        importlib.import_module("src.models." + module.name)
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    Migrate(app, db)
    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        assert db.session.execute(sa.text("SELECT current_database()")).scalar() == "aw_sbxf2"
        assert not sa.inspect(db.engine).get_table_names(), "bootstrap requires an empty scratch database"
        db.create_all()
        stamp(directory="migrations", revision="fl01")
