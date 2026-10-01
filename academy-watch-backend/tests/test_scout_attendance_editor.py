# ruff: noqa: F811
"""RC4V2-O1: the actual full editor payload must permit unrelated corrections."""

import json
import os

import pytest
from src.models.league import db
from src.models.opportunities import ClubOpportunity, now
from test_club_console import _headers, client, club_app  # noqa: F401
from test_opportunities import create, env  # noqa: F401
from test_scout_attendance import answer, ask, c4  # noqa: F401


def editor_payload(post, **changes):
    data = {
        key: post.get(key)
        for key in (
            "status",
            "type",
            "gender_program",
            "squad_id",
            "title",
            "description",
            "instructions",
            "position_requirements",
            "venue",
            "address",
            "timezone",
            "birth_year_min",
            "birth_year_max",
            "capacity",
            "starts_at",
            "ends_at",
            "closes_at",
        )
    }
    data.update(expected_version=post["version"], **changes)
    return data


@pytest.mark.parametrize("state", ["none", "pending", "accepted", "declined"])
@pytest.mark.parametrize("flag_off", [False, True])
def test_full_editor_payload_saves_unrelated_change(client, c4, monkeypatch, state, flag_off):
    post = create(client, c4, timezone="Europe/London", birth_year_max=now().year - 10)
    if state != "none":
        row = ask(client, c4, post).get_json()["attendance"]
        if state != "pending":
            assert answer(client, c4, row, decision=state).status_code == 200
    if flag_off:
        monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    listing = client.get(f"/api/club/{c4['pid']}/opportunities", headers=_headers("a")).get_json()
    item = next(p for p in listing["opportunities"] if p["id"] == post["id"])
    assert "live_attendance" not in client.get(f"/api/opportunities/{post['id']}").get_json()["opportunity"]
    # An equivalent ISO UTC suffix and legacy zone must compare equal.
    data = editor_payload(item, description="Corrected TEST ONLY description", timezone="Europe/Belfast")
    data["starts_at"] = item["starts_at"].replace("+00:00", "Z")
    data["ends_at"] = item["ends_at"].replace("+00:00", "Z")
    response = client.patch(f"/api/club/{c4['pid']}/opportunities/{post['id']}", headers=_headers("a"), json=data)
    assert response.status_code == 200, response.get_json()
    updated = response.get_json()["opportunity"]
    assert updated["description"] == data["description"] and updated["timezone"] == "Europe/London"
    assert item["live_attendance"] is (state in {"pending", "accepted"})
    assert updated["live_attendance"] is (state in {"pending", "accepted"})
    changed = client.patch(
        f"/api/club/{c4['pid']}/opportunities/{post['id']}",
        headers=_headers("a"),
        json=editor_payload(updated, venue="Changed ground"),
    )
    assert changed.status_code == (409 if state in {"pending", "accepted"} else 200), changed.get_json()
    if state in {"pending", "accepted"}:
        assert changed.get_json()["error"] == "advertised_terms_locked"
        assert db.session.get(ClubOpportunity, post["id"]).venue == post["venue"]


@pytest.mark.parametrize("state", ["pending", "accepted"])
def test_browser_editor_payload_against_real_flask(client, c4, state):
    """Playwright supplies the bytes captured from the shipped editor, with no API mock logic."""
    raw = os.getenv("C4_BROWSER_EDITOR_PAYLOAD")
    if not raw:
        pytest.skip("browser captured payload opt-in")
    data = json.loads(raw)
    post = create(client, c4, **{key: value for key, value in data.items() if key != "expected_version"})
    row = ask(client, c4, post).get_json()["attendance"]
    if state == "accepted":
        assert answer(client, c4, row).status_code == 200
    response = client.patch(f"/api/club/{c4['pid']}/opportunities/{post['id']}", headers=_headers("a"), json=data)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["opportunity"]["description"] == data["description"]
    changed = {**data, "expected_version": 2, "venue": "Changed ground"}
    response = client.patch(f"/api/club/{c4['pid']}/opportunities/{post['id']}", headers=_headers("a"), json=changed)
    assert response.status_code == 409 and response.get_json()["error"] == "advertised_terms_locked"
