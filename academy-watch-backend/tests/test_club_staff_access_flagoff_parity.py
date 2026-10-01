# ruff: noqa: F401, F811
"""Flag-OFF parity: 164 club route response/state snapshots must equal origin/main 4c1ce1e3 exactly.

Baseline captured by the RA2V reviewer with this same fixture and request sequence
(tests/fixtures/club_staff_access_flagoff_baseline.json). Timestamps, blob UUIDs and signed
tokens are normalised.
"""

import json
import os
import re
from pathlib import Path

import pytest
from src.models.funding import ClubSquad
from src.models.league import db
from src.routes.feedback import feedback_bp
from test_club_console import _add_api_member, _headers, client, club_app


def normalize(value, key=""):
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, key) for v in value]
    if isinstance(value, str):
        if re.fullmatch("\\d{4}-\\d\\d-\\d\\dT.*", value):
            return "<timestamp>"
        if key == "token":
            return "<signed-token>"
        return re.sub("(?<=/)\\b[0-9a-f]{32}(?=\\.mp4)", "<blob-uuid>", value)
    return value


def test_flagoff_route_snapshot(club_app, client, monkeypatch):
    monkeypatch.delenv("CLUB_STAFF_ACCESS_ENABLED", raising=False)
    monkeypatch.setenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "true")
    club_app.register_blueprint(feedback_bp, url_prefix="/api")
    pid = club_app.c2["program_a"]
    base = f"/api/club/{pid}"
    member = _add_api_member(client, pid)
    squad = ClubSquad(program_id=pid, name="Parity squad", kind="other")
    db.session.add(squad)
    db.session.commit()
    match = client.post(
        f"{base}/matches",
        json={"opponent_name": "Parity FC", "match_date": "2026-09-01", "squad_id": squad.id},
        headers=_headers("a"),
    )
    assert match.status_code == 201
    mid = match.get_json()["id"]
    snapshots = {"create_match": normalize(match.get_json())}
    entries = client.put(
        f"{base}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": member, "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert entries.status_code == 200
    snapshots["put_match_roster"] = normalize(entries.get_json())
    endpoints = []
    for rule in club_app.url_map.iter_rules():
        if not str(rule).startswith("/api/club/") or "GET" not in rule.methods:
            continue
        path = (
            str(rule)
            .replace("<int:program_id>", str(pid))
            .replace("<int:member_id>", str(member))
            .replace("<int:match_id>", str(mid))
            .replace("<int:row_id>", "999")
            .replace("<result_id>", "missing")
            .replace("<invitation_id>", "11111111-1111-4111-8111-111111111111")
            .replace("<revision_id>", "11111111-1111-4111-8111-111111111111")
        )
        assert "<" not in path, path
        endpoints.append(path)
    for path in sorted(set(endpoints)):
        for method in ("get", "head"):
            for who in ("anonymous", "a", "b", "pending"):
                response = getattr(client, method)(path, headers={} if who == "anonymous" else _headers(who))
                payload = response.get_json(silent=True)
                body = normalize(payload) if payload is not None else response.get_data(as_text=True)
                snapshots[f"{method.upper()} {path} {who}"] = {
                    "status": response.status_code,
                    "body": body,
                    "headers": {
                        h: response.headers.get(h)
                        for h in ("Content-Type", "Cache-Control", "Referrer-Policy", "Allow")
                    },
                }
    response = client.open(
        f"{base}/squads", method="HEAD", json={"name": "HEAD legacy create", "kind": "other"}, headers=_headers("a")
    )
    snapshots["HEAD squads with body"] = {
        "status": response.status_code,
        "count": ClubSquad.query.count(),
        "body": response.get_data(as_text=True),
    }
    response = client.open(
        f"{base}/staff", method="HEAD", json={"name": "HEAD staff", "role": "coach"}, headers=_headers("a")
    )
    snapshots["HEAD staff with body"] = {"status": response.status_code, "body": response.get_data(as_text=True)}
    baseline = json.loads((Path(__file__).parent / "fixtures" / "club_staff_access_flagoff_baseline.json").read_text())
    current = json.loads(json.dumps(snapshots, sort_keys=True))
    diff = {
        k: {"main": baseline.get(k), "branch": current.get(k)}
        for k in sorted(set(baseline) | set(current))
        if baseline.get(k) != current.get(k)
    }
    assert diff == {}, json.dumps(diff, indent=2)[:4000]
    assert len(current) == 164
