"""Foreground-only synthetic real-main HTTP fixture for UXM2F3 browser checks."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from flask import jsonify, request
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from src.extensions import limiter
from src.main import app
from src.models.follow import PlayerShadow
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.tracked_player import TrackedPlayer
from src.workers.vision_worker import _brief_context
from test_club_console import _active_suppression, _local, club_app
from test_club_staff_access import _email, _h, _join, env


def serve():
    compiles(JSONB, "sqlite")(lambda element, compiler, **kw: "JSON")
    monkeypatch = pytest.MonkeyPatch()
    fixture = club_app.__wrapped__(monkeypatch, request=SimpleNamespace(param=True))
    seeded = next(fixture)
    client = seeded.test_client()
    case = env.__wrapped__(seeded, client, monkeypatch)
    _join(client, case, "coach", "coach", squads=[case["sa"]])
    _join(client, case, "allcoach", "coach", squads=[case["sa"]])
    outside = db.session.get(ClubRosterMember, case["m2"])
    provider_id = outside.player_api_id
    local = _local(seeded.c2["users"]["a"], name="Localalias Privatealias", birth_year=2010)
    local.api_player_id = provider_id
    source = _local(seeded.c2["users"]["a"], name="Oldalias Oldperson", status="merged")
    source.merged_into_local_player_id = local.id
    outside.local_player_id, outside.player_api_id = source.id, None
    TrackedPlayer.query.filter_by(player_api_id=provider_id).update({"player_name": "Brannock Outsidesquad"})
    db.session.add(PlayerShadow(player_api_id=provider_id, player_name="Shadowalias Hiddenalias"))
    _active_suppression(player_api_id=provider_id)
    target = db.session.get(ClubRosterMember, case["m1"])
    target.coach_brief_body = "Check shoulders"
    db.session.commit()
    db._app_engines[app] = db.engines
    app.config.update(SECRET_KEY=seeded.config["SECRET_KEY"], TESTING=True)
    limiter.enabled = True
    limiter.reset()
    headers_by_width = {"1440": _h(_email("coach")), "390": _h(_email("allcoach"))}

    @app.get("/api/__uxm2f3-fixture")
    def metadata():
        target = db.session.get(ClubRosterMember, case["m1"])
        result = _brief_context(
            {"club_program_id": case["pid"], "our_kit_color": "blue"},
            [{"id": 101, "club_roster_member_id": target.id, "jersey_number": 9}],
            [target],
        )
        return jsonify(
            program_id=case["pid"],
            member_id=target.id,
            coach_token=headers_by_width[request.args.get("width", "1440")]["Authorization"].removeprefix("Bearer "),
            worker_lines=result["roster"].get("101", {}).get("lines", []),
        )

    try:
        app.run(host="127.0.0.1", port=int(os.getenv("UXM2F3_HTTP_PORT", "5163")), use_reloader=False)
    finally:
        limiter.reset()
        db._app_engines.pop(app, None)
        fixture.close()
        monkeypatch.undo()


if __name__ == "__main__":
    serve()
