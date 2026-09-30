# ruff: noqa: F401, F811
"""Monotonic recording coverage (video_match_coverage) for club staff access. Synthetic data only."""

from datetime import UTC, datetime

from src.models.club_access import VideoMatchCoverage
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.video import VideoMatch, VideoRosterEntry
from src.services import video_storage
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env


def _put(client, env, mid, members):
    entries = [{"club_roster_member_id": m, "jersey_number": i + 7} for i, m in enumerate(members)]
    return client.put(f"{env['base']}/matches/{mid}/roster", json={"entries": entries}, headers=_headers("a"))


def _upload(client, env, monkeypatch, mid):
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "cov-etag", "size_bytes": 10}
    )
    resp = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={"kickoff_s": 0}, headers=_headers("a"))
    assert resp.status_code == 200, resp.get_json()


def _kinds(mid):
    return sorted((r.kind, r.club_roster_member_id) for r in VideoMatchCoverage.query.filter_by(video_match_id=mid))


def _sees(client, env, mid, key="coach"):
    return client.get(f"{env['base']}/matches/{mid}", headers=_h(_email(key))).status_code == 200


def _squad_a_member(client, env, player_api_id):
    """Move the fixture's second player (m2, Squad B) into Squad A."""
    assert player_api_id == 7002
    resp = client.patch(f"{env['base']}/roster/{env['m2']}", json={"squad_id": env["sa"]}, headers=_headers("a"))
    assert resp.status_code == 200, resp.get_json()
    return env["m2"]


def test_upload_records_origin_and_roster_then_only_grows(env, client, monkeypatch):
    mid = _match(client, env, "sa")
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    assert _kinds(mid) == []  # no recording yet: nothing recorded
    _upload(client, env, monkeypatch, mid)
    assert _kinds(mid) == [("member", env["m1"]), ("origin", None)]
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    assert _sees(client, env, mid)
    # A second Squad A player is added then removed: coverage keeps both.
    extra = _squad_a_member(client, env, 7002)
    assert _put(client, env, mid, [env["m1"], extra]).status_code == 200
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    assert ("member", extra) in _kinds(mid)
    assert _sees(client, env, mid)
    # That removed player later moves squads: the recording still shows them, so it closes.
    assert (
        client.patch(f"{env['base']}/roster/{extra}", json={"squad_id": env["sb"]}, headers=_headers("a")).status_code
        == 200
    )
    assert not _sees(client, env, mid)
    assert client.get(f"{env['base']}/matches/{mid}", headers=_headers("a")).status_code == 200


def test_unidentified_row_after_upload_is_permanent(env, client, monkeypatch):
    mid = _match(client, env, "sa")
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _upload(client, env, monkeypatch, mid)
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    assert _sees(client, env, mid, "viewer")
    # An admin-style name-only row, then the club roster write that records it.
    db.session.add(VideoRosterEntry(video_match_id=mid, jersey_number=30, player_name="Unknown trialist"))
    db.session.commit()
    assert _put(client, env, mid, [env["m1"]]).status_code == 200  # removes the name-only row (jersey 30)
    assert ("uncertain", None) in _kinds(mid)
    assert VideoRosterEntry.query.filter_by(video_match_id=mid, jersey_number=30).count() == 0
    assert not _sees(client, env, mid, "viewer")


def test_recording_uploaded_before_coverage_is_whole_club_only(env, client):
    mid = _match(client, env, "sa")
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    match = db.session.get(VideoMatch, mid)
    match.uploaded_at = datetime.now(UTC).replace(tzinfo=None)
    match.status = "uploaded"
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    assert _kinds(mid) == []
    assert not _sees(client, env, mid)
    assert client.get(f"{env['base']}/matches/{mid}", headers=_headers("a")).status_code == 200


def test_coverage_is_recorded_while_the_flag_is_off(env, client, monkeypatch):
    mid = _match(client, env, "sa")
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "false")
    _upload(client, env, monkeypatch, mid)
    assert _kinds(mid) == [("member", env["m1"]), ("origin", None)]


def test_deleted_member_keeps_recording_closed(env, client, monkeypatch):
    mid = _match(client, env, "sa")
    extra = _squad_a_member(client, env, 7002)
    assert _put(client, env, mid, [env["m1"], extra]).status_code == 200
    _upload(client, env, monkeypatch, mid)
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    assert _sees(client, env, mid)
    assert client.delete(f"{env['base']}/roster/{extra}", headers=_headers("a")).status_code in (200, 204)
    assert db.session.get(ClubRosterMember, extra) is None
    assert ("member", extra) in _kinds(mid)
    assert not _sees(client, env, mid)
