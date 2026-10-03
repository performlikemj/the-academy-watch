"""Standalone PostgreSQL fixture seed for the off-container PC2 CLI proof.

Run only on the explicitly named, locally owned aw_pc2 scratch database. The
same fictional dataset is used by the all-surface endpoint equality test.
"""

import json
import os
import sys
from pathlib import Path

from flask import Flask
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from src.models.league import db
from src.routes.player_matches import player_matches_bp  # register read-policy models
from src.routes.players import players_bp
from src.routes.scout import scout_bp
from test_pc2_surface_equality import seed_personas

uri = os.environ["PC2_DATABASE_URL"]
url = make_url(uri)
assert url.database == "aw_pc2" and url.host in {None, "localhost", "127.0.0.1"}
app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
for bp in (player_matches_bp, players_bp, scout_bp):
    app.register_blueprint(bp, url_prefix="/api")
with app.app_context():
    db.create_all()
    ids, _user, _list = seed_personas()
    print(json.dumps({"fictional_personas": ids}, indent=2))
