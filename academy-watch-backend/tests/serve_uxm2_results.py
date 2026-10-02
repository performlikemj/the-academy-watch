"""Foreground real-HTTP fixture for e2e/uxm2-results-real.spec.mjs.

Run with the backend venv from this directory, then point Vite's API proxy at
127.0.0.1:5161 and set E2E_UXM2_REAL=true for the browser test. All data is
synthetic and in-memory; stopping this server discards it. No providers.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from flask import jsonify
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from src.models.league import db
from src.models.player_match_entry import ClubResult, PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.routes.players import players_bp
from test_club_console import _add_api_member, _headers, _result_payload, club_app


def serve():
    compiles(JSONB, "sqlite")(lambda element, compiler, **kw: "JSON")
    monkeypatch = pytest.MonkeyPatch()
    fixture = club_app.__wrapped__(monkeypatch)
    app = next(fixture)
    app.register_blueprint(players_bp, url_prefix="/api")
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats,player_stats")

    @app.get("/api/__uxm2-fixture")
    def metadata():
        cells = PlayerSeasonCell.query.filter_by(player_api_id=7001, season=2025, source="club").all()
        total = PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025).first()
        return jsonify(
            program_id=pid,
            token=headers["Authorization"].removeprefix("Bearer "),
            members=[{"id": mid, "player_api_id": 7001, "display_name": "Known Academy Player", "available": True}],
            results=ClubResult.query.count(),
            entries=PlayerMatchEntry.query.count(),
            competitions=[cell.to_dict()["detail"]["competition"] for cell in cells],
            stored_competitions=sorted({entry.competition for entry in PlayerMatchEntry.query.all()}),
            total=total.to_dict()["stats"] if total else None,
        )

    client = app.test_client()
    pid = app.c2["program_a"]
    mid = _add_api_member(client, pid)
    legacy = client.post(
        f"/api/club/{pid}/results",
        headers=_headers("a"),
        json=_result_payload([mid], opponent="Old & Rovers", competition="Wendle & District"),
    )
    assert legacy.status_code == 201
    assert db.session.get(ClubResult, legacy.json["result"]["id"]).opponent == "Old &amp; Rovers"
    db.session.add(
        PlayerMatchEntry(
            player_api_id=7001,
            season=2025,
            match_date=date(2025, 8, 31),
            opponent="Earlier &amp; Rovers",
            competition="Wendle &amp; District",
            home_away="home",
            source="club",
            status="club_confirmed",
            club_program_id=pid,
            reported_by_user_id=app.c2["users"]["a"],
            minutes=90,
            goals=1,
        )
    )
    db.session.commit()
    headers = _headers("a")

    try:
        app.run(host="127.0.0.1", port=5161, use_reloader=False)
    finally:
        fixture.close()
        monkeypatch.undo()


if __name__ == "__main__":
    serve()
