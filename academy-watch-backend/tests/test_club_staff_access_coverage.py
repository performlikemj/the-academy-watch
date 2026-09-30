# ruff: noqa: F401, F811
"""Grant-time, monotonic recording coverage (video_match_coverage) for club staff access. Synthetic data only.

Rules pinned here: origin is written only where a club match and its first upload grant are
created; roster writes, re-grants and completions only append to a match that has an origin;
a match without one is LEGACY (whole-club only) forever; squad-scoped byte access also needs a
completed upload.
"""

from src.models.club_access import VideoMatchCoverage
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.video import VideoMatch, VideoRosterEntry
from src.services import video_storage
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env


def _put(client, env, mid, members):
    entries = [{"club_roster_member_id": m, "jersey_number": i + 7} for i, m in enumerate(members)]
    return client.put(f"{env['base']}/matches/{mid}/roster", json={"entries": entries}, headers=_headers("a"))


def _upload(client, env, monkeypatch, mid, etag="cov-etag"):
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": etag, "size_bytes": 10}
    )
    resp = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={"kickoff_s": 0}, headers=_headers("a"))
    assert resp.status_code == 200, resp.get_json()


def _kinds(mid):
    return sorted((r.kind, r.club_roster_member_id) for r in VideoMatchCoverage.query.filter_by(video_match_id=mid))


def _make_legacy(mid):
    """A match created before p2a2 has no coverage rows at all."""
    VideoMatchCoverage.query.filter_by(video_match_id=mid).delete()
    db.session.commit()


def _status(client, env, mid, suffix="", key="coach"):
    return client.get(f"{env['base']}/matches/{mid}{suffix}", headers=_h(_email(key))).status_code


def _move(client, env, member, squad_key):
    resp = client.patch(f"{env['base']}/roster/{member}", json={"squad_id": env[squad_key]}, headers=_headers("a"))
    assert resp.status_code == 200, resp.get_json()


def test_new_upload_happy_path_for_scoped_staff(env, client, monkeypatch):
    mid = _match(client, env, "sa", uploaded=False)
    assert _kinds(mid) == [("origin", None)]  # written with the match and its first upload grant
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    assert _kinds(mid) == [("member", env["m1"]), ("origin", None)]
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    # In progress: the coach can work on the match (detail, re-grant) but gets no footage yet.
    assert _status(client, env, mid) == 200
    for suffix in ("/media-token", "/reel", "/report"):
        assert _status(client, env, mid, suffix) == 404
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"url": "https://example.invalid/upload"})
    assert client.post(f"{env['base']}/matches/{mid}/sas", headers=_h(_email("coach"))).status_code == 200
    _upload(client, env, monkeypatch, mid)
    assert _kinds(mid) == [("member", env["m1"]), ("origin", None)]
    assert _status(client, env, mid, "/media-token") == 200
    assert _status(client, env, mid, "/reel") == 200


def test_coverage_only_grows_after_origin(env, client, monkeypatch):
    mid = _match(client, env, "sa", uploaded=False)
    _move(client, env, env["m2"], "sa")
    assert _put(client, env, mid, [env["m1"], env["m2"]]).status_code == 200
    assert _put(client, env, mid, [env["m1"]]).status_code == 200  # m2 removed before upload
    _upload(client, env, monkeypatch, mid)
    assert ("member", env["m2"]) in _kinds(mid)
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    assert _status(client, env, mid, "/media-token") == 200
    _move(client, env, env["m2"], "sb")  # the removed player leaves the squad: the recording closes
    assert _status(client, env, mid, "/media-token") == 404
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).status_code == 200


def test_unidentified_row_is_permanent(env, client, monkeypatch):
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    db.session.add(VideoRosterEntry(video_match_id=mid, jersey_number=30, player_name="Unknown trialist"))
    db.session.commit()
    assert _put(client, env, mid, [env["m1"]]).status_code == 200  # snapshot before removal records it
    _upload(client, env, monkeypatch, mid, etag="other-etag")
    assert ("uncertain", None) in _kinds(mid)
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    assert _status(client, env, mid, key="viewer") == 404
    assert _status(client, env, mid, "/media-token", key="viewer") == 404


def test_legacy_match_never_gains_origin(env, client, monkeypatch):
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _make_legacy(mid)
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"url": "https://example.invalid/upload"})
    assert client.post(f"{env['base']}/matches/{mid}/sas", headers=_headers("a")).status_code == 200
    _upload(client, env, monkeypatch, mid)
    _upload(client, env, monkeypatch, mid, etag="new-etag")  # re-attestation with a new ETag
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    assert _kinds(mid) == []
    for suffix in ("", "/media-token", "/reel", "/report"):
        assert _status(client, env, mid, suffix) == 404
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).status_code == 200


def test_origin_recorded_while_flag_off(env, client, monkeypatch):
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "false")
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    assert _kinds(mid) == [("member", env["m1"]), ("origin", None)]


def test_deleted_member_keeps_recording_closed(env, client, monkeypatch):
    mid = _match(client, env, "sa", uploaded=False)
    _move(client, env, env["m2"], "sa")
    assert _put(client, env, mid, [env["m1"], env["m2"]]).status_code == 200
    _upload(client, env, monkeypatch, mid)
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    assert _status(client, env, mid, "/media-token") == 200
    assert client.delete(f"{env['base']}/roster/{env['m2']}", headers=_headers("a")).status_code in (200, 204)
    assert db.session.get(ClubRosterMember, env["m2"]) is None
    assert ("member", env["m2"]) in _kinds(mid)
    assert _status(client, env, mid, "/media-token") == 404
