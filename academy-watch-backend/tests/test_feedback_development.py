"""Private practice lifecycle, stale writes and grounded evidence boundaries."""

from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.league import db
from src.models.player_feedback import PlayerFeedback
from test_club_console import _headers
from test_player_feedback import (  # noqa: F401
    accepted as accepted,
)
from test_player_feedback import (
    client as client,
)
from test_player_feedback import (
    club_app as club_app,
)
from test_player_feedback import (
    correct,
    create,
    detail,
    video,
)
from test_player_feedback import (
    p2_postgres_app as p2_postgres_app,
)
from test_player_feedback import (
    pilot as pilot,
)
from test_player_feedback import (
    postgres_app as postgres_app,
)

ACTION = {
    "focus": "Scan before receiving",
    "practice": "Check both shoulders before five receptions.",
    "success": "Describe the forward option before the ball arrives.",
    "review_on": "2026-09-12",
}


def publish(client, pilot, accepted):
    response = create(client, pilot, accepted, development_action=ACTION)
    assert response.status_code == 201, response.json
    return response.json["feedback"]


def progress(client, row, version=0, status="ready_for_review", note="I found the forward pass earlier.", key="scout"):
    return client.post(
        f"/api/me/player-feedback/{row['id']}/progress",
        json=dict(expected_version=version, status=status, note=note),
        headers=_headers(key),
    )


def review(client, pilot, row, version=1, status="reviewed", key="a"):
    return client.post(
        f"/api/club/{pilot['program']}/player-feedback/{row['thread_id']}/progress-review",
        json=dict(
            expected_revision=row["revision"],
            expected_version=version,
            status=status,
            note="Good progress. Repeat under pressure.",
        ),
        headers=_headers(key),
    )


def test_complete_private_development_cycle(client, pilot, accepted):
    row = publish(client, pilot, accepted)
    assert row["development_action"] == ACTION
    assert progress(client, row, status="working_on_it", note="First practice.").status_code == 200
    assert review(client, pilot, row).status_code == 409
    ready = progress(client, row, version=1)
    assert ready.status_code == 200
    assert ready.json["feedback"]["acknowledged_at"] is None
    assert review(client, pilot, row, version=2).status_code == 200
    saved = detail(client, row).json["feedback"]["development_progress"]
    assert saved["version"] == 3 and saved["status"] == "reviewed"
    assert saved["reflection"] == "I found the forward pass earlier."
    assert saved["coach_note"] == "Good progress. Repeat under pressure."
    assert [e["actor"] for e in saved["history"]] == ["player", "player", "coach"]
    db.session.expire_all()
    assert db.session.get(PlayerFeedback, row["id"]).development_progress == saved
    listed = client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("scout"))
    assert "development_progress" not in listed.json["feedback"][0]
    history = client.get(
        f"/api/club/{pilot['program']}/player-feedback?invitation_id={accepted}", headers=_headers("a")
    )
    assert "development_progress" not in history.json["feedback"][0]
    path = f"/api/club/{pilot['program']}/player-feedback/{row['id']}"
    coach_detail = client.get(path, headers=_headers("a"))
    assert coach_detail.status_code == 200
    assert coach_detail.json["feedback"]["development_progress"] == saved
    assert client.get(path, headers=_headers("b")).status_code == 403
    assert client.get(path, headers=_headers("scout")).status_code == 403
    for response in (listed, history):
        assert "I found the forward pass earlier." not in response.text
        assert "Good progress. Repeat under pressure." not in response.text
    invite = db.session.get(ClubInvitation, accepted)
    invite.status = "revoked"
    invite.revoked_at = utcnow()
    db.session.commit()
    closed_detail = client.get(path, headers=_headers("a"))
    assert closed_detail.status_code == 409
    assert "development_progress" not in closed_detail.text


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {},
        "",
        {**ACTION, "focus": ""},
        {**ACTION, "review_on": "2026-02-30"},
        {**ACTION, "review_on": True},
        {**ACTION, "extra": "no"},
        {**ACTION, "practice": "x" * 1001},
    ],
)
def test_invalid_action_rejected(client, pilot, accepted, bad):
    assert create(client, pilot, accepted, development_action=bad).status_code == 400
    assert PlayerFeedback.query.count() == 0


@pytest.mark.parametrize(
    "status,note,version",
    [
        ([], "ok", 0),
        ({}, "ok", 0),
        ("reviewed", "ok", 0),
        ("ready_for_review", "", 0),
        ("working_on_it", [], 0),
        ("working_on_it", "ok", True),
        ("working_on_it", "x" * 1001, 0),
    ],
)
def test_invalid_progress_rejected(client, pilot, accepted, status, note, version):
    row = publish(client, pilot, accepted)
    assert progress(client, row, version, status, note).status_code == 400
    assert detail(client, row).json["feedback"]["development_progress"] is None


def test_stale_and_superseded_progress_cannot_overwrite(client, pilot, accepted):
    row = publish(client, pilot, accepted)
    assert progress(client, row).status_code == 200
    assert progress(client, row).json["error"] == "development_progress_conflict"
    assert review(client, pilot, row, version=0).status_code == 409
    revised = correct(client, pilot, row, development_action=ACTION)
    assert revised.status_code == 201
    assert revised.json["feedback"]["development_progress"] is None
    assert progress(client, row, version=1).status_code == 409
    assert review(client, pilot, row).status_code == 409
    assert detail(client, row).json["feedback"]["can_update_progress"] is False


def test_wrong_actor_closed_relationship_and_withdrawal(client, pilot, accepted):
    row = publish(client, pilot, accepted)
    for key in ("a", "b", "pending"):
        assert progress(client, row, key=key).status_code == 404
    assert review(client, pilot, row, key="b").status_code == 403
    invite = db.session.get(ClubInvitation, accepted)
    invite.status = "revoked"
    invite.revoked_at = utcnow()
    db.session.commit()
    assert progress(client, row).status_code == 404
    assert review(client, pilot, row).status_code == 409


def test_history_bounded_and_new_practice_preserves_prior_review(client, pilot, accepted):
    row = publish(client, pilot, accepted)
    assert progress(client, row).status_code == 200
    assert review(client, pilot, row).status_code == 200
    for version in range(2, 23):
        response = progress(client, row, version, "working_on_it", "Practising again.")
        assert response.status_code == 200
    saved = response.json["feedback"]["development_progress"]
    assert len(saved["history"]) == 20 and saved["version"] == 23
    assert saved["coach_note"] is None


def test_suggestions_only_exact_grounded_player_evidence(client, pilot, accepted):
    match, report = video(pilot, duration_s=90)
    good = {
        "roster_entry_id": report.roster_entry_id,
        "grounded": True,
        "box_t": 22.5,
        "caption": "Scans before receiving.",
    }
    bad = [
        {**good, "grounded": False},
        {**good, "roster_entry_id": report.roster_entry_id + 1},
        {**good, "box_t": 100},
        {**good, "box_t": True},
        {**good, "caption": None},
        "bad",
    ]
    match.capture_meta = {"footage_url": "PRIVATE_SENTINEL", "qwen_analysis": {"window_captions": [good, *bad]}}
    db.session.commit()
    path = f"/api/club/{pilot['program']}/player-feedback/suggestions?invitation_id={accepted}"
    result = client.get(path, headers=_headers("a"))
    assert result.status_code == 200, result.json
    assert len(result.json["suggestions"]) == 1
    assert result.json["suggestions"][0]["text"] == good["caption"]
    assert "SENTINEL" not in result.text
    assert client.get(path, headers=_headers("b")).status_code == 403
    report.club_player_api_id_at_finalize = 7002
    db.session.commit()
    assert client.get(path, headers=_headers("a")).json["suggestions"] == []


@pytest.mark.parametrize("state", ["fresh", "partial", "pre-applied"])
def test_development_migration_repeat_and_partial_recovery(postgres_app, state):
    from flask_migrate import stamp, upgrade

    directory = str(Path(__file__).resolve().parents[1] / "migrations")
    with db.engine.begin() as connection:
        if state != "pre-applied":
            connection.execute(sa.text("ALTER TABLE player_feedback DROP COLUMN development_progress"))
        if state == "fresh":
            connection.execute(sa.text("ALTER TABLE player_feedback DROP COLUMN development_action"))
    for _ in range(2):
        stamp(directory=directory, revision="s4c1")
        upgrade(directory=directory, revision="s4d1")
    columns = {c["name"]: c for c in sa.inspect(db.session.connection()).get_columns("player_feedback")}
    assert len(columns) == 21
    for name in ("development_action", "development_progress"):
        assert columns[name]["nullable"] and isinstance(columns[name]["type"], sa.JSON)


def test_development_export_withdrawal_and_account_deletion(client, pilot, accepted):
    from src.models.league import UserAccount
    from src.services.account import build_account_export, delete_account

    row = publish(client, pilot, accepted)
    assert progress(client, row).status_code == 200
    user = db.session.get(UserAccount, pilot["user"])
    exported = build_account_export(user)
    assert (
        exported["player_feedback"]["received"][0]["development_progress"]["reflection"]
        == "I found the forward pass earlier."
    )
    withdrawn = client.post(
        f"/api/club/{pilot['program']}/player-feedback/{row['thread_id']}/withdraw",
        json={"expected_revision": 1},
        headers=_headers("a"),
    )
    assert withdrawn.status_code == 200
    assert progress(client, row, version=1).status_code == 404
    assert build_account_export(user)["player_feedback"]["received"] == []
    history = client.get(
        f"/api/club/{pilot['program']}/player-feedback?invitation_id={accepted}", headers=_headers("a")
    )
    assert "development_action" not in history.text and "forward pass" not in history.text
    delete_account(user)
    db.session.commit()
    assert PlayerFeedback.query.count() == 0


def test_postgres_simultaneous_progress_and_review_only_one_winner(postgres_app, pilot):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from test_club_invitations import decide, invitation

    with postgres_app.test_client() as http:
        accepted = invitation(http, pilot)
        assert decide(http, accepted).status_code == 200
        row = publish(http, pilot, accepted)

    def concurrent(operation):
        barrier = Barrier(2)

        def run(_):
            with postgres_app.app_context(), postgres_app.test_client() as http:
                barrier.wait(timeout=10)
                return operation(http).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    assert sorted(concurrent(lambda http: progress(http, row))) == [200, 409]
    assert sorted(concurrent(lambda http: review(http, pilot, row))) == [200, 409]
    db.session.expire_all()
    saved = db.session.get(PlayerFeedback, row["id"]).development_progress
    assert saved["version"] == 2 and len(saved["history"]) == 2


@pytest.mark.parametrize("correction", [False, True])
@pytest.mark.parametrize("first_null", [False, True])
def test_null_and_omitted_action_replay_identically(client, pilot, accepted, correction, first_null):
    original = publish(client, pilot, accepted) if correction else None
    send = (
        (lambda **kw: correct(client, pilot, original, **kw))
        if correction
        else (lambda **kw: create(client, pilot, accepted, **kw))
    )
    request_id = str(uuid4())
    first = send(client_request_id=request_id, **({"development_action": None} if first_null else {}))
    assert first.status_code == 201
    replay = send(client_request_id=request_id, **({} if first_null else {"development_action": None}))
    assert replay.status_code == 200
    assert replay.json["feedback"]["id"] == first.json["feedback"]["id"]
    changed = send(client_request_id=request_id, development_action=ACTION)
    assert changed.status_code == 409
    assert changed.json["error"] == "client_request_id_reused"


@pytest.mark.parametrize("correction", [False, True])
@pytest.mark.parametrize(
    "body",
    [
        "Scans before receiving.",
        "  SCANS  before\nreceiving.  ",
        "Ｓcans before receiving.",
        "<p>Scans before receiving.</p>",
        "Scans&nbsp;before receiving.",
    ],
)
def test_raw_observation_cannot_be_published(client, pilot, accepted, correction, body):
    match, report = video(pilot, duration_s=90)
    # The referenced observation is beyond the suggestion picker limit.
    captions = [
        dict(roster_entry_id=report.roster_entry_id, grounded=True, box_t=i, caption=f"Other observation {i}.")
        for i in range(13)
    ]
    captions.append(
        dict(roster_entry_id=report.roster_entry_id, grounded=True, box_t=22.5, caption="Scans before receiving.")
    )
    captions.insert(0, {"roster_entry_id": [], "caption": "Malformed caption"})
    match.capture_meta = {"qwen_analysis": {"window_captions": captions}}
    db.session.commit()
    refs = [
        {"label": "Another observation", "timestamp_s": 0},
        {"label": "Edited reference label", "timestamp_s": 22.5},
    ]
    changes = dict(body=body, video_match_id=match.id, observation_refs=refs)
    original = publish(client, pilot, accepted) if correction else None
    response = correct(client, pilot, original, **changes) if correction else create(client, pilot, accepted, **changes)
    assert response.status_code == 400, response.json
    assert response.json["error"] == "body_matches_observation"
    assert PlayerFeedback.query.count() == int(correction)
    changes["body"] = "Try checking both shoulders before your next five receptions."
    response = correct(client, pilot, original, **changes) if correction else create(client, pilot, accepted, **changes)
    assert response.status_code == 201


def test_observation_label_reference_without_timestamp(client, pilot, accepted):
    match, report = video(pilot, duration_s=90)
    match.capture_meta = {
        "qwen_analysis": {
            "window_captions": [
                dict(
                    roster_entry_id=report.roster_entry_id, grounded=True, box_t=22.5, caption="Scans before receiving."
                ),
            ]
        }
    }
    db.session.commit()
    changes = dict(
        body="Scans before receiving.",
        video_match_id=match.id,
        observation_refs=[{"label": " SCANS before receiving. ", "timestamp_s": None}],
    )
    response = create(client, pilot, accepted, **changes)
    assert response.status_code == 400
    assert response.json["error"] == "body_matches_observation"
    # Unreferenced evidence does not prohibit separately authored feedback.
    changes["observation_refs"] = [{"label": "A different observation", "timestamp_s": 10}]
    assert create(client, pilot, accepted, **changes).status_code == 201


@pytest.mark.parametrize("body", ["", " \n\t ", "<p></p>"])
def test_empty_feedback_body_rejected_with_action(client, pilot, accepted, body):
    response = create(client, pilot, accepted, body=body, development_action=ACTION)
    assert response.status_code == 400
    assert PlayerFeedback.query.count() == 0
