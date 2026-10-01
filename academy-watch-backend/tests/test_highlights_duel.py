# ruff: noqa: F811
"""Reverse RC2V's first-use, transport, retention and consent probes."""

from datetime import UTC, date, timedelta
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from src.models.follow import PlayerShadow
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.league import db
from src.models.p2_foundation import NotificationOutbox
from src.services import highlights, highlights_storage
from src.services.highlights_retention import sweep_highlights
from src.workers import highlight_worker as worker
from test_highlights import approve, headers, pick, ready, world  # noqa: F401


@pytest.mark.parametrize("classification", ["adult_only", "private"])
def test_o1_first_review_without_seed(world, classification):
    db.session.delete(world["review"])
    db.session.commit()
    assert db.session.get(HighlightFootageReview, world["match"].id) is None
    response = (
        world["app"]
        .test_client()
        .post(
            f"/api/club/{world['program'].id}/matches/{world['match'].id}/highlight-review",
            headers=headers(world["manager"]),
            json={"classification": classification, "all_visible_people_adults": True},
        )
    )
    assert response.status_code == 200, response.json
    row = db.session.get(HighlightFootageReview, world["match"].id)
    assert row.classification == classification
    assert row.source_etag and row.source_snapshot and row.reviewed_at
    assert row.reviewer_user_id == world["manager"].id


def club_base(w):
    return f"/api/club/{w['program'].id}/matches/{w['match'].id}"


def grant_path(w, row, audience):
    return (
        f"/api/highlights/{row.id}/clip"
        if audience == "public"
        else f"/api/me/highlight-requests/{row.id}/preview"
        if audience == "player"
        else f"{club_base(w)}/highlights/{row.id}/preview"
    )


def grant_headers(w, audience):
    return {} if audience == "public" else headers(w["player" if audience == "player" else "manager"])


def test_x1_o2_unanswered_lives_until_raw_deadline(world, monkeypatch):
    row = ready(world)
    row.created_at = now() - timedelta(days=70)
    world["match"].expires_at = now() + timedelta(days=1)
    db.session.commit()
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/standalone.mp4")
    client = world["app"].test_client()
    assert client.get(grant_path(world, row, "player"), headers=headers(world["player"])).status_code == 302
    assert sweep_highlights()["expired"] == 0
    world["match"].expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    assert client.get(grant_path(world, row, "player"), headers=headers(world["player"])).status_code == 404
    assert sweep_highlights()["expired"] == 1


def test_x1_declined_ready_output_deleted_now(world, monkeypatch):
    row = ready(world)
    path = row.output_blob_path
    response = (
        world["app"]
        .test_client()
        .post(
            f"/api/me/highlight-requests/{row.id}/decision",
            headers=headers(world["player"]),
            json={"decision": "private", "version": row.version},
        )
    )
    assert response.status_code == 200
    deletion = HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).one()
    assert deletion.created_at <= now()
    deleted = Mock(return_value=True)
    monkeypatch.setattr("src.services.video_storage.delete_blob", deleted)
    claimed = worker.claim_next()
    assert claimed and claimed[0] == deletion.id
    assert worker.run_one(*claimed)
    deleted.assert_called_once_with(path)


def test_x1_live_attempt_cleanup_is_fenced(world):
    assert pick(world).status_code == 201
    row = PlayerHighlight.query.one()
    claim = worker.claim_next()
    attempt = db.session.get(HighlightRenderJob, claim[0])
    path = attempt.blob_path
    response = (
        world["app"]
        .test_client()
        .post(
            f"/api/me/highlight-requests/{row.id}/decision",
            headers=headers(world["player"]),
            json={"decision": "private", "version": row.version},
        )
    )
    assert response.status_code == 200
    assert not worker.finish(*claim, output_etag="late", output_size=20)
    jobs = HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).all()
    assert jobs and all(job.created_at >= now() + timedelta(minutes=19) for job in jobs)
    assert worker.claim_next() is None


@pytest.mark.parametrize(
    "label",
    [
        "U18B",
        "Under_18",
        "Under–18",
        "U  18",
        "u16a",
        "U.17",
        "Sub-17",
        "Boys 2012",
        "Under Sixteens",
        "Schoolboys",
        "Year 9",
    ],
)
def test_x2_n1_youth_labels_never_publish(world, label):
    world["squad"].name = label
    world["squad"].kind = "first_team"
    db.session.commit()
    assert highlights.squad_classification(world["squad"]) == "youth"
    response = (
        world["app"]
        .test_client()
        .post(
            club_base(world) + "/highlight-review",
            headers=headers(world["manager"]),
            json={"classification": "adult_only", "all_visible_people_adults": True, "squad_adult_attested": True},
        )
    )
    assert response.status_code == 422
    assert pick(world).status_code == 422
    assert (
        world["app"].test_client().get(f"/api/players/{world['local'].api_player_id}/highlights").json["highlights"]
        == []
    )


@pytest.mark.parametrize("age_limit", [19, 20, 21])
def test_o11_age_upper_bound_needs_senior_attestation(world, age_limit):
    world["squad"].kind = "age_group"
    world["squad"].age_limit = age_limit
    world["squad"].name = f"U{age_limit}"
    db.session.commit()
    assert pick(world).status_code == 422
    response = (
        world["app"]
        .test_client()
        .post(
            club_base(world) + "/highlight-review",
            headers=headers(world["manager"]),
            json={"classification": "adult_only", "all_visible_people_adults": True, "squad_adult_attested": True},
        )
    )
    assert response.status_code == 200
    from src.models.p2_foundation import AdminActionEvent

    audit = (
        AdminActionEvent.query.filter_by(action="highlight_recording_review")
        .order_by(AdminActionEvent.id.desc())
        .first()
    )
    assert audit.event_metadata["squad_adult_attested"] is True
    row = ready(world)
    assert approve(world, row).status_code == 200
    assert highlights.public(row)
    # Un-attesting invalidates the recording and both publication keys.
    response = (
        world["app"]
        .test_client()
        .post(
            club_base(world) + "/highlight-review",
            headers=headers(world["manager"]),
            json={"classification": "private"},
        )
    )
    assert response.status_code == 200
    db.session.refresh(row)
    assert row.revoked_at and not highlights.public(row)


@pytest.mark.parametrize("audience", ["public", "player", "club"])
@pytest.mark.parametrize("change", ["revoke", "hold", "source", "standing", "deadline", "delay"])
def test_x3_n2_final_grant_rechecks_after_storage(world, monkeypatch, audience, change):
    row = ready(world)
    if change != "deadline" or audience == "public":
        assert approve(world, row).status_code == 200
    start = now()
    seen = []

    def storage(path, etag, *, expires_at):
        seen.append(expires_at)
        if change == "revoke":
            highlights.revoke(row, world["player"].id, "player_revoke")
        elif change == "hold":
            world["program"].emergency_hidden = True
        elif change == "source":
            world["entry"].jersey_number = 10
        elif change == "standing":
            world["player"].account_status = "suspended"
        elif change == "deadline":
            world["match"].expires_at = now() - timedelta(seconds=1)
        db.session.commit()
        if change == "delay":
            monkeypatch.setattr("src.routes.highlights.now", lambda: start + timedelta(seconds=61))
        return "https://storage.example/standalone.mp4"

    monkeypatch.setattr(highlights_storage, "output_read_url", storage)
    response = world["app"].test_client().get(grant_path(world, row, audience), headers=grant_headers(world, audience))
    # Approved standalone assets deliberately survive ordinary raw expiry.
    expected = 302 if change == "deadline" and audience == "public" else 404
    assert response.status_code == expected
    assert seen and (seen[0] - start.replace(tzinfo=UTC)).total_seconds() <= 61


def test_o3_preview_url_transport_keeps_existing_redirect(world, monkeypatch):
    row = ready(world)
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/standalone.mp4")
    client = world["app"].test_client()
    for audience in ("player", "club"):
        path = grant_path(world, row, audience)
        assert client.get(path, headers=grant_headers(world, audience)).status_code == 302
        response = client.get(path + "?transport=url", headers=grant_headers(world, audience))
        assert response.status_code == 200
        assert response.json == {"url": "https://storage.example/standalone.mp4"}
        assert response.headers["Cache-Control"] == "private, no-store, max-age=0"


def test_o4_live_consent_history_retained(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    for event in HighlightConsentEvent.query.all():
        event.created_at = now() - timedelta(days=400)
    db.session.commit()
    assert sweep_highlights()["events"] == 0
    assert HighlightConsentEvent.query.filter_by(highlight_id=row.id).count() == 2
    assert highlights.public(row)


@pytest.mark.parametrize(
    "missing", ["claim_null", "claim_revoked", "recipient_null", "recipient_changed", "relationship", "tombstone"]
)
def test_o5_permanently_missing_key_queues_cleanup(world, missing):
    row = ready(world)
    assert approve(world, row).status_code == 200
    path = row.output_blob_path
    if missing == "claim_null":
        row.claim_id = None
    elif missing == "recipient_null":
        row.recipient_user_id = None
    elif missing == "claim_revoked":
        world["claim"].status = "revoked"
    elif missing == "tombstone":
        world["player"].is_tombstone = True
    elif missing == "recipient_changed":
        world["claim"].user_account_id = world["stranger"].id
    else:
        world["claim"].relationship_type = "agent"
    db.session.commit()
    assert sweep_highlights()["expired"] == 1
    db.session.refresh(row)
    assert row.revoked_at and row.revoke_reason == "consent_key_removed"
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).count() >= 1


def test_o5_reversible_hold_preserves_approved_asset(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    world["program"].emergency_hidden = True
    db.session.commit()
    assert not highlights.public(row)
    assert sweep_highlights()["expired"] == 0
    db.session.refresh(row)
    assert row.revoked_at is None
    world["program"].emergency_hidden = False
    db.session.commit()
    assert highlights.public(row)


def test_o6_admin_takedown_sticky_until_admin_lift(world, monkeypatch):
    row = ready(world)
    assert approve(world, row).status_code == 200
    hid = row.id
    admin = world["manager"]
    admin.is_admin = True
    world["app"].config["API_KEY"] = "duel-admin-key"
    monkeypatch.setenv("ADMIN_API_KEY", "duel-admin-key")
    db.session.commit()
    from src.auth import issue_user_token

    auth = {
        "Authorization": "Bearer " + issue_user_token(admin.email, role="admin")["token"],
        "X-API-Key": "duel-admin-key",
    }
    client = world["app"].test_client()
    assert client.post(f"/api/admin/highlights/{hid}/takedown", headers=auth).status_code == 200
    assert pick(world, title="Changed title").status_code == 422
    row.revoked_at = now() - timedelta(days=91)
    db.session.commit()
    assert sweep_highlights()["highlights"] == 1
    assert pick(world).status_code == 422
    assert client.post(f"/api/admin/highlights/{hid}/lift", headers=headers(world["player"])).status_code != 200
    assert client.post(f"/api/admin/highlights/{hid}/lift", headers=auth).status_code == 200
    fresh = ready(world)
    assert fresh.id != hid and fresh.player_decision == "pending"
    assert approve(world, fresh).status_code == 200


def test_o8_provider_flow_and_conflicting_dob(world, monkeypatch):
    pid = 765432
    world["member"].local_player_id = None
    world["member"].player_api_id = pid
    world["claim"].local_player_id = None
    world["claim"].player_api_id = pid
    world["report"].club_local_player_id_at_finalize = None
    world["report"].club_player_api_id_at_finalize = pid
    shadow = PlayerShadow(
        player_api_id=pid, player_name="Synthetic Provider", birth_date=date(2000, 1, 1), is_active=True
    )
    db.session.add(shadow)
    db.session.commit()
    row = ready(world)
    assert row.player_api_id == pid and approve(world, row).status_code == 200
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/standalone.mp4")
    client = world["app"].test_client()
    assert client.get(grant_path(world, row, "public")).status_code == 302
    shadow.birth_date = now().date().replace(year=now().year - 16)
    db.session.commit()
    assert client.get(grant_path(world, row, "public")).status_code == 404


def test_o12_cancelled_cut_actionable_after_flag_restore(world, monkeypatch):
    assert pick(world).status_code == 201
    row = PlayerHighlight.query.one()
    claim = worker.claim_next()
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    assert worker.finish(*claim, output_etag="not-published", output_size=20) is False
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1")
    db.session.refresh(row)
    assert row.render_status == "stale" and highlights.dto(row, private=True)["can_retry"]
    assert (
        world["app"]
        .test_client()
        .post(f"/api/me/highlight-requests/{row.id}/retry", headers=headers(world["player"]))
        .status_code
        == 202
    )
    claimed = worker.claim_next()
    assert claimed and worker.finish(*claimed, output_etag="retry", output_size=20)


def test_o13_source_change_notifies_both_and_new_pick_needs_new_approval(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    old_id = row.id
    world["member"].squad_id = None
    db.session.commit()
    db.session.refresh(row)
    assert row.revoked_at and not highlights.public(row)
    intents = NotificationOutbox.query.filter_by(template="highlight_source_changed").all()
    assert {intent.recipient_user_id for intent in intents} == {world["player"].id, world["manager"].id}
    assert all(set(intent.payload) == {"highlight_id", "version"} for intent in intents)
    fresh = ready(world)
    assert fresh.id != old_id and fresh.player_decision == "pending"
    assert not highlights.public(fresh)
    assert approve(world, fresh).status_code == 200


@pytest.mark.parametrize("audience", ["public", "player", "club"])
def test_o9_grant_sql_independent_of_roster_size(world, monkeypatch, audience):
    from src.models.video import VideoRosterEntry

    row = ready(world)
    assert approve(world, row).status_code == 200
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/standalone.mp4")
    path, auth = grant_path(world, row, audience), grant_headers(world, audience)
    counts = []
    for count in (1, 21):
        if count > 1:
            for number in range(20):
                db.session.add(
                    VideoRosterEntry(
                        video_match_id=world["match"].id,
                        club_roster_member_id=world["member"].id,
                        player_name="Synthetic adult",
                        jersey_number=20 + number,
                    )
                )
            # Adding to the source must fence consent. Fresh pick/approval below.
            db.session.commit()
            row = ready(world)
            assert approve(world, row).status_code == 200
            path = grant_path(world, row, audience)
        db.session.commit()
        db.session.expire_all()
        statements = []

        def query(*args):
            statements.append(args[2])

        sa.event.listen(db.engine, "before_cursor_execute", query)
        try:
            result = world["app"].test_client().get(path, headers=auth)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", query)
        assert result.status_code == 302
        counts.append(len(statements))
    assert counts[0] == counts[1], counts
    assert counts[0] <= 32, counts


def test_o10_schema_discovery_cached_without_disabling_dark_guards(world, monkeypatch):
    import src.services.highlights_source as source

    getattr(source, "_available_engines", {}).pop(db.engine, None)
    real = sa.inspect
    calls = []

    def inspect_connection(connection):
        if not isinstance(connection, sa.engine.Connection):
            return real(connection)

        class Inspector:
            def has_table(self, name):
                calls.append(name)
                return real(connection).has_table(name)

        return Inspector()

    row = ready(world)
    assert approve(world, row).status_code == 200
    getattr(source, "_available_engines", {}).pop(db.engine, None)
    monkeypatch.setattr(source.sa, "inspect", inspect_connection)
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    for jersey in (10, 11):
        world["entry"].jersey_number = jersey
        db.session.commit()
    assert calls == ["player_highlights"]
    db.session.refresh(row)
    assert row.revoked_at and row.revoke_reason == "source_changed"


@pytest.mark.parametrize("audience", ["public", "player", "club"])
def test_o7_real_app_effective_no_referrer(world, monkeypatch, audience):
    from src.main import app

    row = ready(world)
    if audience == "public":
        assert approve(world, row).status_code == 200
    engine = db.engine
    previous = db._app_engines[app]
    monkeypatch.setitem(db._app_engines, app, {None: engine})
    monkeypatch.setitem(app.config, "RATELIMIT_ENABLED", False)
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/standalone.mp4")
    path = grant_path(world, row, audience)
    db.session.commit()
    with app.app_context():
        auth = grant_headers(world, audience)
        response = app.test_client().get(path, headers=auth)
        assert response.status_code == 302
        assert response.headers["Referrer-Policy"] == "no-referrer"
    db._app_engines[app] = previous


def test_o6_minimal_hold_survives_erasure_and_admin_can_lift_archived_id(world, monkeypatch):
    from src.auth import issue_user_token
    from src.models.highlights import HighlightTakedown
    from src.services.account import _SchemaView
    from src.services.highlights_account import erase_highlights

    row = ready(world)
    assert approve(world, row).status_code == 200
    hid = row.id
    monkeypatch.setenv("ADMIN_API_KEY", "duel-admin-key")
    auth = {
        "Authorization": "Bearer " + issue_user_token(world["manager"].email, role="admin")["token"],
        "X-API-Key": "duel-admin-key",
    }
    client = world["app"].test_client()
    assert client.post(f"/api/admin/highlights/{hid}/takedown", headers=auth).status_code == 200
    erase_highlights(world["player"].id, _SchemaView())
    db.session.commit()
    assert PlayerHighlight.query.filter_by(id=hid).count() == 0
    hold = db.session.get(HighlightTakedown, hid)
    assert hold and hold.lifted_at is None
    assert pick(world, title="New title after erasure").status_code == 422
    assert client.post(f"/api/admin/highlights/{hid}/lift", headers=auth).status_code == 200
    fresh = ready(world)
    assert fresh.player_decision == "pending" and approve(world, fresh).status_code == 200


def test_o6_existing_duplicate_window_also_loses_both_grants(world, monkeypatch):
    from src.auth import issue_user_token

    first = ready(world)
    assert approve(world, first).status_code == 200
    response = pick(world, title="Other title for same footage")
    assert response.status_code == 201
    second = db.session.get(PlayerHighlight, response.json["id"])
    claimed = worker.claim_next()
    assert worker.finish(*claimed, output_etag="other", output_size=20)
    assert approve(world, second).status_code == 200
    monkeypatch.setenv("ADMIN_API_KEY", "duel-admin-key")
    auth = {
        "Authorization": "Bearer " + issue_user_token(world["manager"].email, role="admin")["token"],
        "X-API-Key": "duel-admin-key",
    }
    assert (
        world["app"].test_client().post(f"/api/admin/highlights/{first.id}/takedown", headers=auth).status_code == 200
    )
    db.session.refresh(first)
    db.session.refresh(second)
    assert first.revoked_at and second.revoked_at
    assert not highlights.public(first) and not highlights.public(second)
