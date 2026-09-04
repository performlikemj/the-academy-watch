"""Film Room credits serialize per team and refunds reverse one real debit."""

from unittest.mock import patch

import pytest
from src.auth import issue_user_token
from src.models.league import Team, db
from src.models.video import VideoAnalysisJob, VideoCreditLedger, VideoMatch
from src.routes.video import video_bp

ADMIN_KEY = "video-credit-race-admin-key"


@pytest.fixture
def video_app(app, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app.register_blueprint(video_bp, url_prefix="/api")
    return app


@pytest.fixture
def video_client(video_app):
    return video_app.test_client()


def _admin_headers():
    token = issue_user_token("video-credit-race-admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _team_with_matches(count=1):
    team = Team(team_id=99001, name="Credit Race Academy", country="Japan", season=2026)
    db.session.add(team)
    db.session.flush()
    matches = [
        VideoMatch(
            team_id=team.id,
            status="uploaded",
            kickoff_s=0,
            blob_path=f"matches/credit-race-{index}.mp4",
            blob_etag=f"etag-{index}",
        )
        for index in range(count)
    ]
    db.session.add_all(matches)
    db.session.add(VideoCreditLedger(team_id=team.id, delta=1, reason="grant"))
    db.session.commit()
    return team, matches


def _process(client, match):
    verified = {"ok": True, "etag": match.blob_etag, "size_bytes": 2048}
    with (
        patch("src.routes.video.video_storage.verify_expected_blob", return_value=verified),
        patch("src.routes.video.video_queue.enqueue", return_value="fixture"),
    ):
        return client.post(f"/api/admin/video/matches/{match.id}/process", headers=_admin_headers())


def test_same_team_process_requests_lock_before_balance_and_cannot_overspend(video_client, monkeypatch):
    team, matches = _team_with_matches(count=2)
    real_balance = VideoCreditLedger.balance
    real_execute = db.session.execute
    events = []
    team_lock_held = False

    def record_execute(statement, *args, **kwargs):
        nonlocal team_lock_held
        if getattr(statement, "_for_update_arg", None) is not None and Team.__table__ in statement.get_final_froms():
            events.append("team_lock")
            team_lock_held = True
        return real_execute(statement, *args, **kwargs)

    def race_aware_balance(team_id):
        nonlocal team_lock_held
        events.append("balance")
        if not team_lock_held:
            # This is the stale read both overlapping requests could observe without the team lock.
            return 1
        team_lock_held = False
        return real_balance(team_id)

    monkeypatch.setattr(db.session, "execute", record_execute)
    monkeypatch.setattr(VideoCreditLedger, "balance", race_aware_balance)

    responses = [_process(video_client, match) for match in matches]

    assert sorted(response.status_code for response in responses) == [202, 402]
    assert events == ["team_lock", "balance", "team_lock", "balance"]
    assert real_balance(team.id) == 0
    assert VideoCreditLedger.query.filter_by(team_id=team.id, reason="debit").count() == 1
    assert VideoAnalysisJob.query.count() == 1


def test_refund_without_debit_is_rejected(video_client):
    _team, (match,) = _team_with_matches()

    response = video_client.post(f"/api/admin/video/matches/{match.id}/refund", headers=_admin_headers())

    assert response.status_code == 409
    assert response.get_json() == {"error": "no debit to refund"}
    assert VideoCreditLedger.query.filter_by(video_match_id=match.id, reason="refund").count() == 0


def test_second_refund_is_conflict_and_does_not_credit_twice(video_client):
    team, (match,) = _team_with_matches()
    db.session.add(VideoCreditLedger(team_id=team.id, delta=-1, reason="debit", video_match_id=match.id))
    db.session.commit()

    first = video_client.post(f"/api/admin/video/matches/{match.id}/refund", headers=_admin_headers())
    second = video_client.post(f"/api/admin/video/matches/{match.id}/refund", headers=_admin_headers())

    assert first.status_code == 200
    assert first.get_json() == {"balance": 1}
    assert second.status_code == 409
    assert second.get_json() == {"error": "match already refunded"}
    assert VideoCreditLedger.query.filter_by(video_match_id=match.id, reason="refund").count() == 1
    assert VideoCreditLedger.balance(team.id) == 1


def test_normal_process_then_refund_flow_is_unchanged(video_client):
    team, (match,) = _team_with_matches()

    processed = _process(video_client, match)
    refunded = video_client.post(
        f"/api/admin/video/matches/{match.id}/refund",
        json={"note": "poor footage"},
        headers=_admin_headers(),
    )

    assert processed.status_code == 202
    assert refunded.status_code == 200
    assert refunded.get_json() == {"balance": 1}
    movements = VideoCreditLedger.query.filter_by(team_id=team.id).order_by(VideoCreditLedger.id).all()
    assert [(row.delta, row.reason, row.video_match_id) for row in movements] == [
        (1, "grant", None),
        (-1, "debit", match.id),
        (1, "refund", match.id),
    ]
    assert movements[-1].note == "poor footage"
