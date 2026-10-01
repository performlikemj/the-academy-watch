"""Exercise two keys, private cuts, age/scope boundaries and fenced completion."""

import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
import src.services.highlights_source  # noqa: F401
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.club_access import ClubAccessGrant, ClubAccessGrantSquad
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubRosterMember,
    ClubSquad,
    FundingLeague,
)
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.league import UserAccount, db
from src.models.p2_foundation import NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.routes.highlights import highlights_bp
from src.services import highlights, highlights_storage
from src.services.account import _SchemaView
from src.services.highlights_account import erase_highlights, export_highlights
from src.workers.highlight_worker import claim_next, finish


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    for flag in ("HIGHLIGHTS_ENABLED", "P2_FOUNDATION_ENABLED", "CLUB_STAFF_ACCESS_ENABLED"):
        monkeypatch.setenv(flag, "1")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="highlight-test",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    if os.getenv("C2_POSTGRES_TESTS") == "1":
        app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg://mjjones@localhost/aw_p2_c2"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"options": "-c search_path=c2_checks"}}
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(highlights_bp, url_prefix="/api")
    highlights.register_notifications()
    monkeypatch.setattr("src.services.club_access.scoped_recording_intact", lambda match: True)
    monkeypatch.setattr("src.routes.highlights.scoped_recording_intact", lambda match: True)
    monkeypatch.setattr("src.services.video_dev_artifacts.local_artifacts", lambda match: None)
    with app.app_context():
        db.create_all()
        manager = UserAccount(
            email="manager@example.test", display_name="Test Manager", display_name_lower="test manager"
        )
        player = UserAccount(email="player@example.test", display_name="Test Player", display_name_lower="test player")
        stranger = UserAccount(
            email="stranger@example.test", display_name="Test Stranger", display_name_lower="test stranger"
        )
        league = FundingLeague(
            name="Test League",
            country="JP",
            region="Test",
            level="recreational",
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="approved",
        )
        db.session.add_all([manager, player, stranger, league])
        db.session.flush()
        program = ClubProgram(
            funding_league_id=league.id,
            name="Test FC",
            legal_name="Test FC",
            slug="test-fc",
            country="JP",
            region="Test",
            platform_status="approved",
        )
        local = LocalPlayer(
            display_name="Test Adult",
            status="approved",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            provenance="user",
        )
        db.session.add_all([program, local])
        db.session.flush()
        local.api_player_id = -local.id
        squad = ClubSquad(program_id=program.id, name="First team", kind="first_team")
        manager_claim = ClubProgramClaim(program_id=program.id, user_account_id=manager.id, status="approved")
        claim = PlayerProfileClaim(
            local_player_id=local.id, user_account_id=player.id, relationship_type="player", status="approved"
        )
        member = ClubRosterMember(program_id=program.id, local_player_id=local.id, added_by_user_id=manager.id)
        db.session.add_all([squad, manager_claim, claim, member])
        db.session.flush()
        member.squad_id = squad.id
        db.session.add(
            ClubProgramManager(
                program_id=program.id,
                user_account_id=manager.id,
                source_claim_id=manager_claim.id,
                granted_by="test-admin",
                status="active",
            )
        )
        match = VideoMatch(
            club_program_id=program.id,
            squad_id=squad.id,
            status="finalized",
            blob_path="matches/1/private.mp4",
            blob_etag="source-v1",
            scoped_ready_etag="source-v1",
            scoped_snapshot="snapshot-v1",
            duration_s=120,
            uploaded_at=now(),
            finalized_at=now(),
        )
        db.session.add(match)
        db.session.flush()
        entry = VideoRosterEntry(
            video_match_id=match.id, player_name="Test Adult", jersey_number=9, club_roster_member_id=member.id
        )
        db.session.add(entry)
        db.session.flush()
        track = VideoTracklet(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            kind="chain",
            team_cluster=0,
            tag_source="human",
            review_action="confirmed",
            reviewed_at=now(),
            confidence="high",
            first_s=10,
            last_s=30,
        )
        report = VideoPlayerReport(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            identity_confidence="human_confirmed",
            club_program_id_at_finalize=program.id,
            club_roster_member_id_at_finalize=member.id,
            club_local_player_id_at_finalize=local.id,
            model_version="test",
        )
        review = HighlightFootageReview(
            video_match_id=match.id,
            reviewer_user_id=manager.id,
            classification="adult_only",
            source_etag="source-v1",
            source_snapshot="snapshot-v1",
        )
        db.session.add_all([track, report, review])
        db.session.commit()
        if os.getenv("C2_POSTGRES_TESTS") == "1":
            guard_sql = (
                (Path(__file__).parents[1] / "migrations/maintenance/p2c2_source_guards.sql")
                .read_text()
                .replace("public.", "c2_checks.")
            )
            db.session.execute(sa.text(guard_sql))
            db.session.commit()
        yield dict(
            app=app,
            manager=manager,
            player=player,
            stranger=stranger,
            program=program,
            local=local,
            squad=squad,
            claim=claim,
            member=member,
            match=match,
            entry=entry,
            track=track,
            report=report,
            review=review,
        )
        db.session.remove()
        db.drop_all()


def headers(user):
    return {"Authorization": "Bearer " + issue_user_token(user.email)["token"]}


def pick(world, **overrides):
    body = dict(
        roster_entry_id=world["entry"].id,
        tracklet_id=world["track"].id,
        start_s=10,
        end_s=30,
        title="Test match moment",
    )
    body.update(overrides)
    response = (
        world["app"]
        .test_client()
        .post(
            f"/api/club/{world['program'].id}/matches/{world['match'].id}/highlights",
            json=body,
            headers=headers(world["manager"]),
        )
    )
    return response


def ready(world):
    response = pick(world)
    assert response.status_code == 201, response.json
    row = db.session.get(PlayerHighlight, response.json["id"])
    claimed = claim_next()
    assert claimed
    assert finish(*claimed, output_etag="clip-v1", output_size=20)
    return row


def approve(world, row):
    return (
        world["app"]
        .test_client()
        .post(
            f"/api/me/highlight-requests/{row.id}/decision",
            json={"decision": "approve", "version": row.version},
            headers=headers(world["player"]),
        )
    )


def test_both_keys_required_and_private_standalone_preview(world, monkeypatch):
    client = world["app"].test_client()
    response = pick(world)
    assert response.status_code == 201, response.json
    row = db.session.get(PlayerHighlight, response.json["id"])
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert approve(world, row).status_code == 200
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    claimed = claim_next()
    assert finish(*claimed, output_etag="clip-v1", output_size=20)
    read = Mock(return_value=b"c" * 20)
    monkeypatch.setattr(highlights_storage, "read_output", read)
    response = client.get(f"/api/highlights/{row.id}/clip")
    assert response.status_code == 200 and response.data == b"c" * 20
    assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert "Location" not in response.headers
    assert "matches/" not in read.call_args.args[0] and read.call_args.args[0].startswith("highlights/")
    assert client.get(f"/api/players/{row.signed_id}/highlights").json["highlights"][0]["id"] == row.id
    assert client.get("/api/programs/test-fc/highlights").json["highlights"][0]["id"] == row.id
    assert "source_etag" not in response.json if response.is_json else True


def test_preview_without_player_key_does_not_grant_raw_match(world, monkeypatch):
    row = ready(world)
    client = world["app"].test_client()
    monkeypatch.setattr(highlights_storage, "read_output", lambda *args: b"clip-only")
    assert (
        client.get(f"/api/me/highlight-requests/{row.id}/preview", headers=headers(world["player"])).status_code == 200
    )
    assert (
        client.get(f"/api/me/highlight-requests/{row.id}/preview", headers=headers(world["stranger"])).status_code
        == 404
    )
    assert client.get(f"/api/me/highlight-requests/{row.id}/preview").status_code == 401
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    dto = client.get("/api/me/highlight-requests", headers=headers(world["player"])).json["highlights"][0]
    assert dto["preview_url"].endswith("/preview")
    assert not any(key in dto for key in ["blob_path", "capture_meta", "media_token", "source_snapshot"])


@pytest.mark.parametrize("action", ["player", "club"])
def test_revoke_effective_next_request(world, monkeypatch, action):
    row = ready(world)
    assert approve(world, row).status_code == 200
    client = world["app"].test_client()
    if action == "player":
        response = client.post(f"/api/me/highlight-requests/{row.id}/revoke", headers=headers(world["player"]))
    else:
        response = client.delete(
            f"/api/club/{world['program'].id}/matches/{world['match'].id}/highlights/{row.id}",
            headers=headers(world["manager"]),
        )
    assert response.status_code == 200
    read = Mock()
    monkeypatch.setattr(highlights_storage, "read_output", read)
    for method in ["get", "head"]:
        assert getattr(client, method)(f"/api/highlights/{row.id}/clip").status_code == 404
    assert client.get(f"/api/players/{row.signed_id}/highlights").json == {"highlights": []}
    assert approve(world, row).status_code == 422
    read.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        "minor",
        "unknown",
        "guardian",
        "unreviewed",
        "contaminated",
        "snapshot",
        "review",
        "youth",
        "mismatch",
        "full",
        "arbitrary",
    ],
)
def test_ineligible_picks_never_public(world, change):
    body = {}
    if change == "minor":
        world["local"].birth_date = date(2012, 1, 1)
    elif change == "unknown":
        world["local"].birth_date = None
        world["local"].birth_year = None
    elif change == "guardian":
        world["claim"].relationship_type = "guardian"
    elif change == "unreviewed":
        world["track"].reviewed_at = None
    elif change == "contaminated":
        world["track"].contaminated = True
    elif change == "snapshot":
        world["match"].scoped_snapshot = None
    elif change == "review":
        world["review"].classification = "private"
    elif change == "youth":
        world["squad"].age_limit = 18
    elif change == "mismatch":
        world["report"].club_local_player_id_at_finalize = 999
    elif change == "full":
        body = {"start_s": 0, "end_s": 120}
    elif change == "arbitrary":
        body = {"start_s": 11, "end_s": 20}
    db.session.commit()
    response = pick(world, **body)
    assert response.status_code in (404, 422), response.json
    assert PlayerHighlight.query.count() == 0


def test_other_minor_in_match_prevents_adult_public_pick(world):
    other = LocalPlayer(display_name="Test Minor", birth_date=date(2015, 1, 1), birth_year=2015, status="approved")
    db.session.add(other)
    db.session.flush()
    other.api_player_id = -other.id
    member = ClubRosterMember(
        program_id=world["program"].id, local_player_id=other.id, added_by_user_id=world["manager"].id
    )
    db.session.add(member)
    db.session.flush()
    db.session.add(
        VideoRosterEntry(
            video_match_id=world["match"].id,
            club_roster_member_id=member.id,
            player_name="Test Minor",
            jersey_number=10,
        )
    )
    db.session.commit()
    assert pick(world).status_code == 422


@pytest.mark.parametrize(
    "source_field,value",
    [
        ("blob_etag", "source-v2"),
        ("blob_path", "matches/replacement.mp4"),
        ("scoped_snapshot", "snapshot-v2"),
        ("duration_s", 121),
    ],
)
def test_source_change_resets_consent_atomically_even_when_flag_off(world, monkeypatch, source_field, value):
    row = ready(world)
    assert approve(world, row).status_code == 200
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    setattr(world["match"], source_field, value)
    db.session.commit()
    db.session.refresh(row)
    assert row.player_decision == "pending" and row.approved_source_version is None
    assert row.source_version == 2 and row.revoke_reason == "source_changed"
    assert HighlightConsentEvent.query.filter_by(highlight_id=row.id, action="source_changed").count() == 1
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1")
    assert world["app"].test_client().get(f"/api/highlights/{row.id}/clip").status_code == 404


def test_identity_reassignment_resets_and_fences_pending_worker(world):
    assert pick(world).status_code == 201
    row = PlayerHighlight.query.one()
    claimed = claim_next()
    world["track"].review_action = "dismissed"
    db.session.commit()
    assert not finish(*claimed, output_etag="late", output_size=20)
    db.session.refresh(row)
    assert row.output_blob_path is None and row.revoked_at


def test_lease_fences_stale_completion_and_duplicate_workers(world):
    assert pick(world).status_code == 201
    first = claim_next()
    assert claim_next() is None
    job = HighlightRenderJob.query.one()
    job.lease_expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    second = claim_next()
    assert second[1] != first[1]
    assert not finish(*first, output_etag="stale", output_size=20)
    assert finish(*second, output_etag="live", output_size=20)
    assert PlayerHighlight.query.one().output_etag == "live"


@pytest.mark.parametrize("reason", ["hold", "suppression", "claim", "suspended", "unlisted"])
def test_live_public_checks(world, reason):
    row = ready(world)
    assert approve(world, row).status_code == 200
    if reason == "hold":
        world["program"].emergency_hidden = True
    elif reason == "suppression":
        db.session.add(
            PlayerSuppression(
                local_player_id=world["local"].id,
                status="active",
                reason_code="player_request",
                requester_role="player",
                requester_contact="test@example.test",
                request_statement="Test privacy request",
            )
        )
    elif reason == "claim":
        world["claim"].status = "revoked"
    elif reason == "suspended":
        world["player"].account_status = "suspended"
    elif reason == "unlisted":
        ClubProgramManager.query.one().status = "revoked"
    db.session.commit()
    assert world["app"].test_client().get(f"/api/highlights/{row.id}/clip").status_code == 404


def test_dark_routes_and_idor(world, monkeypatch):
    client = world["app"].test_client()
    assert pick(world).status_code == 201
    row = PlayerHighlight.query.one()
    assert (
        client.post(
            f"/api/me/highlight-requests/{row.id}/decision",
            json={"decision": "approve", "version": 1},
            headers=headers(world["stranger"]),
        ).status_code
        == 404
    )
    paths = [
        "/api/highlights/features",
        "/api/me/highlight-requests",
        f"/api/highlights/{row.id}/clip",
        f"/api/players/{row.signed_id}/highlights",
        "/api/programs/test-fc/highlights",
        f"/api/club/{world['program'].id}/matches/{world['match'].id}/highlights",
    ]
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    for path in paths:
        assert client.get(path, headers=headers(world["player"])).status_code == 404
    assert claim_next() is None


def test_duplicate_pick_and_decision_version(world):
    assert pick(world).status_code == 201
    assert pick(world).status_code == 200
    assert (
        PlayerHighlight.query.count() == 1
        and HighlightRenderJob.query.count() == 1
        and NotificationOutbox.query.count() == 1
    )
    row = PlayerHighlight.query.one()
    assert approve(world, row).status_code == 200
    response = (
        world["app"]
        .test_client()
        .post(
            f"/api/me/highlight-requests/{row.id}/decision",
            json={"decision": "private", "version": 1},
            headers=headers(world["player"]),
        )
    )
    assert response.status_code == 409


def test_export_erase_outputs_and_history_even_dark(world, monkeypatch):
    row = ready(world)
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    schema = _SchemaView()
    assert export_highlights(world["player"], schema)["highlights"][0]["id"] == row.id
    result = erase_highlights(world["player"].id, schema)
    db.session.commit()
    assert result == {"highlights_deleted": 1}
    assert PlayerHighlight.query.count() == 0 and HighlightConsentEvent.query.count() == 0
    cleanup = HighlightRenderJob.query.filter_by(kind="highlight_delete").one()
    assert cleanup.blob_path.startswith("highlights/") and cleanup.highlight_id is None


def test_range_endpoint_never_redirects_or_reads_other_assets(world, monkeypatch):
    row = ready(world)
    assert approve(world, row).status_code == 200
    read = Mock(return_value=b"clip")
    monkeypatch.setattr(highlights_storage, "read_output", read)
    client = world["app"].test_client()
    path = f"/api/highlights/{row.id}/clip"
    response = client.get(path, headers={"Range": "bytes=2-5"})
    assert response.status_code == 206 and response.headers["Content-Range"] == "bytes 2-5/20"
    assert read.call_args.args[2:] == (2, 4)
    assert client.get(path, headers={"Range": "bytes=0-5,7-8"}).status_code == 416
    row.output_blob_path = world["match"].blob_path
    db.session.commit()
    read.reset_mock()
    assert client.get(path).status_code == 404
    read.assert_not_called()


def test_scoped_staff_need_a2_footage_provenance(world):
    analyst = world["stranger"]
    squad = world["squad"]
    grant = ClubAccessGrant(
        program_id=world["program"].id, user_account_id=analyst.id, role="analyst", status="active", all_squads=False
    )
    db.session.add(grant)
    db.session.flush()
    db.session.add(ClubAccessGrantSquad(grant_id=grant.id, squad_id=squad.id))
    db.session.commit()
    client = world["app"].test_client()
    path = f"/api/club/{world['program'].id}/matches/{world['match'].id}/highlights"
    # No grant-time origin exists in this legacy fixture: even an in-squad analyst is denied footage-derived reads.
    assert client.get(path, headers=headers(analyst)).status_code == 404


def test_worker_upload_finishes_after_revoke_cannot_publish(world, monkeypatch):
    from src.workers import highlight_worker as worker

    assert pick(world).status_code == 201
    row = PlayerHighlight.query.one()
    claim = worker.claim_next()
    monkeypatch.setattr(highlights_storage, "download_source", lambda *args: None)
    monkeypatch.setattr(worker, "cut_file", lambda *args: None)

    def upload(path, file):
        highlights.revoke(row, world["player"].id, "player_revoke")
        db.session.commit()
        return "late-output", 10

    monkeypatch.setattr(highlights_storage, "upload_output", upload)
    removed = []
    monkeypatch.setattr(worker.video_storage, "delete_blob", lambda path: removed.append(path) or True)
    assert not worker.run_one(*claim)
    db.session.refresh(row)
    assert row.output_blob_path is None and removed
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete").count() == 1


def test_cleanup_runs_with_flag_off_and_retries_failure(world, monkeypatch):
    from src.workers import highlight_worker as worker

    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    job = HighlightRenderJob(kind="highlight_delete", blob_path="highlights/test/attempt.mp4")
    db.session.add(job)
    db.session.commit()
    claim = worker.claim_next()
    monkeypatch.setattr(worker.video_storage, "delete_blob", lambda path: False)
    assert not worker.run_one(*claim)
    db.session.refresh(job)
    assert job.status == "queued" and job.created_at > now()
    assert worker.claim_next() is None
