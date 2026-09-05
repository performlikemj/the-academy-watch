"""P3 private feedback, lifecycle, migration and real concurrency attacks."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.funding import ClubProgramManager, ClubRosterMember
from src.models.league import UserAccount, db
from src.models.player_feedback import PlayerFeedback
from src.models.showcase import PlayerProfileClaim
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.routes.feedback import feedback_bp
from src.services.account import build_account_export, delete_account
from test_club_console import _admin_headers, _grant_program_manager, _headers
from test_club_console import club_app as club_app
from test_club_invitations import decide, invitation
from test_club_invitations import pilot as pilot
from test_club_invitations import postgres_app as p2_postgres_app  # noqa: F401


@pytest.fixture
def client(club_app):
    from src.extensions import limiter

    club_app.config["RATELIMIT_ENABLED"] = True
    limiter.init_app(club_app)
    limiter.enabled = False
    limiter.reset()
    club_app.register_blueprint(feedback_bp, url_prefix="/api")
    db.session.execute(sa.text("PRAGMA foreign_keys=ON"))
    assert db.session.execute(sa.text("PRAGMA foreign_keys")).scalar() == 1
    return club_app.test_client()


@pytest.fixture
def accepted(client, pilot):
    row_id = invitation(client, pilot)
    assert decide(client, row_id).status_code == 200
    return row_id


def payload(accepted, **changes):
    return {
        "invitation_id": accepted,
        "client_request_id": str(uuid4()),
        "title": "Receiving under pressure",
        "body": "Coach-authored feedback.",
        **changes,
    }


def create(client, pilot, accepted, **changes):
    return client.post(
        f"/api/club/{pilot['program']}/player-feedback", json=payload(accepted, **changes), headers=_headers("a")
    )


def published(client, pilot, accepted):
    response = create(client, pilot, accepted)
    assert response.status_code == 201, response.json
    return response.json["feedback"]


def detail(client, row, key="scout"):
    return client.get(f"/api/me/player-feedback/{row['id']}", headers=_headers(key))


def ack(client, row, key="scout"):
    return client.post(f"/api/me/player-feedback/{row['id']}/acknowledge", json={}, headers=_headers(key))


def correct(client, pilot, row, **changes):
    data = payload(None, expected_revision=row["revision"], **changes)
    data.pop("invitation_id")
    return client.post(
        f"/api/club/{pilot['program']}/player-feedback/{row['thread_id']}/revisions", json=data, headers=_headers("a")
    )


def test_exact_claimant_only_even_with_second_approved_claim(client, pilot, accepted, club_app):
    row = published(client, pilot, accepted)
    db.session.add(
        PlayerProfileClaim(
            player_api_id=7001,
            user_account_id=club_app.c2["users"]["b"],
            relationship_type="player",
            status="approved",
            reviewed_at=utcnow(),
        )
    )
    db.session.commit()
    assert detail(client, row).status_code == 200
    for key in ("a", "b", "pending"):
        assert detail(client, row, key).json == {"error": "feedback_not_found"}
        assert ack(client, row, key).status_code == 404
    assert client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("b")).json["feedback"] == []


def test_publish_does_not_project_private_analysis_sentinels(client, pilot, accepted):
    member = ClubRosterMember.query.one()
    member.coach_brief_body = "PRIVATE_ANALYSIS_SENTINEL"
    member.note = "PRIVATE_NOTE_SENTINEL"
    db.session.commit()
    row = published(client, pilot, accepted)
    response = detail(client, row)
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "SENTINEL" not in response.text
    assert set(response.json["feedback"]) == {
        "id",
        "thread_id",
        "revision",
        "program",
        "player_api_id",
        "title",
        "body",
        "observation_refs",
        "author",
        "published_at",
        "acknowledged_at",
        "can_acknowledge",
    }
    listed = client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("scout"))
    assert "body" not in listed.json["feedback"][0]
    assert "SENTINEL" not in listed.text


def video(pilot, **changes):
    match = VideoMatch(club_program_id=pilot["program"], status="finalized", finalized_at=utcnow(), **changes)
    db.session.add(match)
    db.session.flush()
    entry = VideoRosterEntry(video_match_id=match.id, player_name="PRIVATE_NAME_SENTINEL", jersey_number=9)
    db.session.add(entry)
    db.session.flush()
    report = VideoPlayerReport(
        video_match_id=match.id,
        roster_entry_id=entry.id,
        club_program_id_at_finalize=pilot["program"],
        club_player_api_id_at_finalize=7001,
        model_version="PRIVATE_ANALYSIS_SENTINEL",
    )
    db.session.add(report)
    db.session.commit()
    return match, report


def test_video_reference_requires_same_program_and_subject(client, pilot, accepted, club_app):
    match, report = video(pilot)
    assert create(client, pilot, accepted, video_match_id=match.id).status_code == 201
    for change in ("program", "subject", "status"):
        with db.session.begin_nested():
            if change == "program":
                match.club_program_id = club_app.c2["program_b"]
            elif change == "subject":
                report.club_player_api_id_at_finalize = 7002
            else:
                match.status = "review"
            db.session.flush()
            response = create(client, pilot, accepted, video_match_id=match.id)
            assert response.json == {"error": "feedback_reference_unavailable"}
        db.session.refresh(match)
        db.session.refresh(report)


def test_publish_replay_and_changed_payload_conflict(client, pilot, accepted):
    request_id = str(uuid4())
    first = create(client, pilot, accepted, client_request_id=request_id)
    assert first.status_code == 201
    assert create(client, pilot, accepted, client_request_id=request_id).json == first.json
    response = create(client, pilot, accepted, client_request_id=request_id, body="Changed")
    assert response.status_code == 409 and response.json == {"error": "client_request_id_reused"}
    assert PlayerFeedback.query.count() == 1


def test_revisions_are_immutable_and_acknowledgments_are_revision_scoped(client, pilot, accepted):
    first = published(client, pilot, accepted)
    acknowledged = ack(client, first).json["feedback"]["acknowledged_at"]
    assert acknowledged.endswith("Z") and ack(client, first).json["feedback"]["acknowledged_at"] == acknowledged
    request_id = str(uuid4())
    second = correct(client, pilot, first, body="Correction", client_request_id=request_id)
    assert second.status_code == 201, second.json
    assert correct(client, pilot, first, body="Correction", client_request_id=request_id).json == second.json
    second = second.json["feedback"]
    assert second["revision"] == 2 and second["acknowledged_at"] is None
    assert detail(client, first).json["feedback"]["body"] == first["body"]
    assert ack(client, first).json["feedback"]["acknowledged_at"] == acknowledged
    assert ack(client, second).json["feedback"]["acknowledged_at"] is not None
    listed = client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("scout")).json
    assert [r["id"] for r in listed["feedback"]] == [second["id"]]


def test_stale_revision_and_concurrent_revision_predicate(client, pilot, accepted):
    first = published(client, pilot, accepted)
    assert correct(client, pilot, first).status_code == 201
    expected = {"error": "feedback_revision_conflict", "current_revision": 2}
    assert correct(client, pilot, first).json == expected
    assert ack(client, first).json == expected
    assert PlayerFeedback.query.count() == 2


@pytest.mark.parametrize("reason", ["withdrawal", "claim", "relationship", "suppression", "minor", "program"])
def test_withdrawal_claim_revocation_suppression_and_minor_denial(client, pilot, accepted, reason):
    from src.models.funding import ClubProgram
    from src.models.player_suppression import PlayerSuppression
    from src.models.tracked_player import TrackedPlayer

    row = published(client, pilot, accepted)
    if reason == "withdrawal":
        response = client.post(
            f"/api/club/{pilot['program']}/player-feedback/{row['thread_id']}/withdraw",
            json={"expected_revision": 1},
            headers=_headers("a"),
        )
        assert response.status_code == 200
        assert correct(client, pilot, row).json == {"error": "feedback_withdrawn"}
    elif reason == "claim":
        pilot["claim"].status = "revoked"
    elif reason == "relationship":
        db.session.get(ClubInvitation, accepted).status = "revoked"
    elif reason == "suppression":
        db.session.add(
            PlayerSuppression(
                player_api_id=7001,
                status="active",
                reason_code="player_request",
                requester_role="player",
                requester_contact="synthetic@example.com",
                request_statement="Synthetic suppression",
            )
        )
    elif reason == "minor":
        TrackedPlayer.query.filter_by(player_api_id=7001).one().birth_date = "2020-01-01"
    else:
        db.session.get(ClubProgram, pilot["program"]).emergency_hidden = True
    db.session.commit()
    assert detail(client, row).json == {"error": "feedback_not_found"}
    assert ack(client, row).status_code == 404
    assert (
        "Coach-authored" not in client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("scout")).text
    )
    assert db.session.get(PlayerFeedback, row["id"]).audit_expires_at is not None
    exported = build_account_export(db.session.get(UserAccount, pilot["user"]))
    assert exported["player_feedback"]["received"] == []


def test_revoked_author_cannot_read_through_export(client, pilot, accepted, club_app):
    row = published(client, pilot, accepted)
    _grant_program_manager(pilot["program"], club_app.c2["users"]["b"])
    author = db.session.get(UserAccount, club_app.c2["users"]["a"])
    ClubProgramManager.query.filter_by(user_account_id=author.id).one().status = "revoked"
    db.session.commit()
    exported = build_account_export(author)["player_feedback"]["authored"]
    assert exported == [{"id": row["id"], "revision": 1, "published_at": row["published_at"]}]
    assert detail(client, row).status_code == 200
    assert correct(client, pilot, row).json == {"error": "Club manager access denied"}


def test_author_deletion_preserves_recipient_feedback_without_identity(client, pilot, accepted, club_app):
    row = published(client, pilot, accepted)
    _grant_program_manager(pilot["program"], club_app.c2["users"]["b"])
    member = ClubRosterMember.query.one()
    author_id = club_app.c2["users"]["a"]
    member.added_by_user_id = author_id
    member.note = "PRIVATE_NOTE_SENTINEL"
    member.coach_brief_body = "PRIVATE_BRIEF_SENTINEL"
    member.brief_updated_by_user_id = author_id
    match, _ = video(pilot)
    match.processing_requested_by_user_id = author_id
    db.session.commit()
    delete_account(db.session.get(UserAccount, author_id))
    db.session.commit()
    db.session.expire_all()
    response = detail(client, row)
    assert response.status_code == 200, response.json
    assert response.json["feedback"]["author"] == {"display_name": "Former club staff"}
    assert member.note is None and member.coach_brief_body is None
    assert member.added_by_user_id != author_id
    assert match.processing_requested_by_user_id is None
    assert db.session.get(ClubInvitation, accepted).created_by_user_id is None


def test_recipient_deletion_removes_feedback_and_relationships(client, pilot, accepted):
    published(client, pilot, accepted)
    delete_account(db.session.get(UserAccount, pilot["user"]))
    db.session.commit()
    assert PlayerFeedback.query.count() == ClubInvitation.query.count() == ClubRosterMember.query.count() == 0
    assert db.session.get(UserAccount, pilot["user"]) is None
    db.session.expire_all()
    assert pilot["local"].created_by_user_id is None


def test_purge_dry_run_and_retention_boundary(client, pilot, accepted):
    row = published(client, pilot, accepted)
    db.session.get(ClubInvitation, accepted).status = "revoked"
    db.session.commit()
    path = "/api/admin/player-feedback/purge"
    assert client.post(path, json={"dry_run": True}, headers=_admin_headers()).json["closed"] == 1
    stored = db.session.get(PlayerFeedback, row["id"])
    assert stored.audit_expires_at is None
    assert client.post(path, json={"dry_run": False}, headers=_admin_headers()).json["closed"] == 1
    boundary = stored.audit_expires_at
    with patch("src.routes.feedback.utcnow", return_value=boundary - timedelta(microseconds=1)):
        assert client.post(path, json={"dry_run": False}, headers=_admin_headers()).json["deleted"] == 0
    with patch("src.routes.feedback.utcnow", return_value=boundary):
        assert client.post(path, json={"dry_run": True}, headers=_admin_headers()).json["expired"] == 1
        assert client.post(path, json={"dry_run": False}, headers=_admin_headers()).json["deleted"] == 1
    assert PlayerFeedback.query.count() == 0


def test_account_failure_rolls_back_every_pilot_change(client, pilot, accepted):
    row = published(client, pilot, accepted)
    user_id = pilot["user"]
    with patch("src.services.account._repoint_anonymized_user_foreign_keys", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError, match="injected"):
            delete_account(db.session.get(UserAccount, user_id))
    db.session.rollback()
    assert detail(client, row).status_code == 200
    assert ClubInvitation.query.count() == ClubRosterMember.query.count() == 1
    assert pilot["local"].created_by_user_id == user_id
    assert db.session.get(UserAccount, user_id) is not None
    assert UserAccount.query.filter_by(is_tombstone=True).count() == 0


@pytest.mark.parametrize(
    "change",
    [
        {"body": True},
        {"body": "x" * 4001},
        {"title": "x" * 141},
        {"recipient_user_id": 2},
        {"video_match_id": True},
        {"observation_refs": [{"label": "test", "timestamp_s": float("nan")}]},
        {"observation_refs": [{"label": "test", "timestamp_s": -1}]},
        {"observation_refs": [{"label": "test", "timestamp_s": True}]},
        {"observation_refs": [{"label": "test", "timestamp_s": None, "secret": "private"}]},
    ],
)
def test_invalid_inputs_never_echo_private_text(client, pilot, accepted, change):
    response = create(client, pilot, accepted, **change)
    assert response.status_code == 400 and response.json == {"error": "invalid_request"}
    assert response.headers["Cache-Control"] == "private, no-store"
    assert PlayerFeedback.query.count() == 0


@pytest.fixture
def postgres_app(p2_postgres_app):  # noqa: F811
    p2_postgres_app.register_blueprint(feedback_bp, url_prefix="/api")
    return p2_postgres_app


@pytest.mark.parametrize("state", ["fresh", "pre-applied", "partial"])
def test_postgres_migrated_schema_and_repeat_partial_recovery(postgres_app, state):
    from pathlib import Path

    from flask_migrate import stamp, upgrade

    directory = str(Path(__file__).resolve().parents[1] / "migrations")
    with db.engine.begin() as connection:
        if state != "pre-applied":
            connection.execute(sa.text("DROP TABLE player_feedback"))
        if state == "partial":
            connection.execute(
                sa.text("CREATE TABLE player_feedback (id varchar(36) NOT NULL, thread_id varchar(36) NOT NULL)")
            )
    for _ in range(2):
        stamp(directory=directory, revision="s4a1")
        upgrade(directory=directory, revision="s4b1")
    inspector = sa.inspect(db.session.connection())
    assert len(inspector.get_columns("player_feedback")) == 19
    assert len(inspector.get_foreign_keys("player_feedback")) == 6
    assert len(inspector.get_check_constraints("player_feedback")) == 2
    assert len(inspector.get_unique_constraints("player_feedback")) == 2
    assert inspector.get_pk_constraint("player_feedback")["constrained_columns"] == ["id"]
    indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("player_feedback")}
    assert indexes["ix_player_feedback_recipient"] == ["recipient_user_id", "published_at", "id"]
    assert indexes["ix_player_feedback_invitation"] == ["invitation_id", "thread_id", "revision"]
    columns = {c["name"]: c for c in inspector.get_columns("player_feedback")}
    assert "[]" in columns["observation_refs"]["default"]
    assert not columns["published_at"]["type"].timezone
    assert (
        db.session.scalar(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid = 'player_feedback'::regclass"))
        is True
    )
    assert db.session.scalar(sa.text("SELECT count(*) FROM pg_policies WHERE tablename = 'player_feedback'")) == 0
    assert db.session.scalar(sa.text("SELECT version_num FROM alembic_version")) == "s4b1"


def test_postgres_concurrent_revision_replay_and_acknowledgment(postgres_app, pilot):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    with postgres_app.test_client() as http:
        accepted = invitation(http, pilot)
        assert decide(http, accepted).status_code == 200
        first = published(http, pilot, accepted)

    def concurrent(operation):
        barrier = Barrier(2)

        def run(_):
            with postgres_app.app_context(), postgres_app.test_client() as http:
                barrier.wait(timeout=10)
                response = operation(http)
                return response.status_code, response.json

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    results = concurrent(lambda http: correct(http, pilot, first))
    assert sorted(r[0] for r in results) == [201, 409], results
    second = next(r[1]["feedback"] for r in results if r[0] == 201)
    results = concurrent(lambda http: ack(http, second))
    assert [r[0] for r in results] == [200, 200]
    assert results[0][1] == results[1][1]
    request_id = str(uuid4())
    results = concurrent(lambda http: correct(http, pilot, second, client_request_id=request_id))
    assert sorted(r[0] for r in results) == [200, 201], results
    assert results[0][1] == results[1][1]


def test_p1_report_ingests_real_revision_acknowledgment(client, pilot, accepted, club_app):
    from src.services.pilot_cohort import build_report

    row = published(client, pilot, accepted)
    assert ack(client, row).status_code == 200
    start = utcnow() - timedelta(days=1)
    end = utcnow() + timedelta(days=2)
    report = build_report(
        {
            "schema_version": 1,
            "cohort_id": "p3-integration",
            "declared_at": start.isoformat() + "Z",
            "program_id": pilot["program"],
            "window": {"start": start.isoformat() + "Z", "end": end.isoformat() + "Z"},
            "participants": [
                {
                    "person_key": "staff",
                    "primary_role": "staff",
                    "user_account_ids": [club_app.c2["users"]["a"]],
                    "player_api_ids": [],
                    "own_account_verified": True,
                    "excluded": False,
                },
                {
                    "person_key": "player",
                    "primary_role": "player",
                    "user_account_ids": [pilot["user"]],
                    "player_api_ids": [7001],
                    "own_account_verified": True,
                    "excluded": False,
                },
            ],
            "excluded_user_account_ids": [],
            "observations": [
                {
                    "id": "authored",
                    "person_key": "staff",
                    "kind": "self_operated_action",
                    "occurred_at": row["published_at"],
                    "record_type": "player_feedback",
                    "record_id": row["id"],
                    "evidence_ref": "synthetic-check",
                }
            ],
            "continuation": {"decision": "not_discussed", "occurred_at": None, "evidence_ref": None},
        }
    )
    assert report["capabilities"]["feedback"] is True
    assert report["summary"]["by_role"]["player"] == 1
    import json

    serialized = json.dumps(report)
    assert "feedback_acknowledged" in serialized
    assert row["body"] not in serialized and row["title"] not in serialized


@pytest.mark.parametrize("data", [None, [], True, "PRIVATE_TEXT"])
def test_non_object_bodies_and_unknown_ack_fields(client, pilot, accepted, data):
    assert client.post(f"/api/club/{pilot['program']}/player-feedback", json=data, headers=_headers("a")).json == {
        "error": "invalid_request"
    }
    row = published(client, pilot, accepted)
    for body in [data, {"acknowledged_at": "PRIVATE_TEXT"}]:
        response = client.post(f"/api/me/player-feedback/{row['id']}/acknowledge", json=body, headers=_headers("scout"))
        assert response.status_code == 400 and response.json == {"error": "invalid_request"}


def test_limit_rejection_and_auth_order(client, pilot, accepted, club_app):
    from src.extensions import limiter

    row = published(client, pilot, accepted)
    limiter.enabled = True
    limiter.reset()
    try:
        for _ in range(30):
            assert ack(client, row).status_code == 200
        response = ack(client, row)
        assert response.status_code == 429 and response.json == {"error": "rate_limit_exceeded"}
        assert int(response.headers["Retry-After"]) > 0
        assert response.headers["Cache-Control"] == "private, no-store"
        assert ack(client, row, "b").status_code == 404
        assert client.get(f"/api/me/player-feedback/{row['id']}").json == {"error": "missing auth token"}
    finally:
        limiter.enabled = False
        limiter.reset()


@pytest.mark.parametrize("state", ["40001", "40P01", "other"])
def test_transaction_failures_rollback_without_private_errors(client, pilot, accepted, state):
    from sqlalchemy.exc import OperationalError

    error = Exception("PRIVATE_TEXT")
    error.sqlstate = state
    with patch("src.routes.feedback.publish", side_effect=OperationalError("PRIVATE_SQL", {}, error)):
        response = create(client, pilot, accepted)
    assert response.status_code == (409 if state != "other" else 500)
    assert response.json == {"error": "retry_conflict" if state != "other" else "feedback_operation_failed"}
    assert PlayerFeedback.query.count() == 0


def test_pagination_ties_wrong_program_and_closed_cursor(client, pilot, accepted, club_app):
    now = utcnow()
    with patch("src.models.player_feedback.utcnow", return_value=now):
        for _ in range(3):
            published(client, pilot, accepted)
    path = "/api/me/player-feedback?player_api_id=7001&limit=1"
    found, before = [], None
    for _ in range(3):
        response = client.get(path + (f"&before={before}" if before else ""), headers=_headers("scout"))
        assert response.status_code == 200
        found.extend(r["id"] for r in response.json["feedback"])
        before = response.json["next_before"]
    assert len(set(found)) == 3 and before is None
    response = client.get(
        f"/api/club/{club_app.c2['program_b']}/player-feedback?invitation_id={accepted}", headers=_headers("b")
    )
    assert response.status_code == 404


def test_postgres_migrated_account_lifecycle_and_rollback(postgres_app, pilot):
    from pathlib import Path

    from flask_migrate import stamp, upgrade

    directory = str(Path(__file__).resolve().parents[1] / "migrations")
    with db.engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE player_feedback"))
    stamp(directory=directory, revision="s4a1")
    upgrade(directory=directory, revision="s4b1")
    with postgres_app.test_client() as http:
        accepted = invitation(http, pilot, -pilot["local"].id)
        assert decide(http, accepted).status_code == 200
        row = published(http, pilot, accepted)
        assert ack(http, row).status_code == 200
        user_id = pilot["user"]
        with patch("src.services.account._repoint_anonymized_user_foreign_keys", side_effect=RuntimeError("injected")):
            with pytest.raises(RuntimeError, match="injected"):
                delete_account(db.session.get(UserAccount, user_id))
        db.session.rollback()
        assert detail(http, row).status_code == 200
        assert ClubInvitation.query.count() == ClubRosterMember.query.count() == 1
        delete_account(db.session.get(UserAccount, user_id))
        db.session.commit()
        assert PlayerFeedback.query.count() == ClubInvitation.query.count() == ClubRosterMember.query.count() == 0


def test_purge_batches_are_bounded_and_resumable(client, pilot, accepted):
    from uuid import uuid4

    first = published(client, pilot, accepted)
    source = db.session.get(PlayerFeedback, first["id"])
    for revision in range(2, 502):
        db.session.add(
            PlayerFeedback(
                thread_id=source.thread_id,
                revision=revision,
                program_id=source.program_id,
                invitation_id=source.invitation_id,
                claim_id=source.claim_id,
                recipient_user_id=source.recipient_user_id,
                player_api_id=source.player_api_id,
                title="Synthetic",
                body="Private",
                client_request_id=str(uuid4()),
                request_hash="0" * 64,
            )
        )
    db.session.commit()
    response = client.post("/api/admin/player-feedback/purge", json={"dry_run": True}, headers=_admin_headers())
    assert response.json["scanned"] == 500 and response.json["next_before"] is not None
    response = client.post(
        "/api/admin/player-feedback/purge",
        json={"dry_run": True, "before": response.json["next_before"]},
        headers=_admin_headers(),
    )
    assert response.json["scanned"] == 1 and response.json["next_before"] is None
    assert "Private" not in response.text
