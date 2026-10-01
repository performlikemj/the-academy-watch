"""RC2V2 reversed probes: preserve bridge assets and hold overlapping footage."""
# ruff: noqa: F811

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from src.auth import issue_user_token
from src.models.follow import PlayerShadow
from src.models.funding import ClubRosterMember
from src.models.highlights import HighlightRenderJob, HighlightTakedown, PlayerHighlight, now
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.video import VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services import highlights, highlights_storage
from src.services.highlights_retention import permanent_key_missing, sweep_highlights
from test_highlights import approve, headers, pick, ready, world  # noqa: F401


@pytest.mark.parametrize("raw_expired", [False, True])
def test_bridge_retention(world, monkeypatch, raw_expired):
    pid = 765433
    if raw_expired:
        world["match"].match_date = (now() - timedelta(days=80)).date()
        world["match"].uploaded_at = now() - timedelta(days=80)
        world["match"].created_at = world["match"].uploaded_at
        world["match"].expires_at = world["match"].uploaded_at + timedelta(days=90)
    world["local"].api_player_id = pid
    world["member"].local_player_id = None
    world["member"].player_api_id = pid
    world["report"].club_local_player_id_at_finalize = None
    world["report"].club_player_api_id_at_finalize = pid
    # Leave the approved self-claim anchored to the local identity as existing ownership permits.
    db.session.add(
        PlayerShadow(player_api_id=pid, player_name="Bridge Adult", birth_date=date(2000, 1, 1), is_active=True)
    )
    db.session.commit()
    if raw_expired:
        assert review_recording(world).status_code == 200
    row = ready(world)
    assert approve(world, row).status_code == 200
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    client = world["app"].test_client()
    if raw_expired:
        from src.services.video_retention import expire_raw_footage

        monkeypatch.setattr("src.services.video_storage.delete_blob", lambda path: True)
        assert expire_raw_footage(now=now() + timedelta(days=11))["expired"] == 1
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
    assert highlights.own_claim(world["claim"], pid, world["player"].id)
    assert not permanent_key_missing(row)
    path = row.output_blob_path
    assert sweep_highlights()["expired"] == 0
    db.session.refresh(row)
    assert row.revoked_at is None
    assert not HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).count()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302


def test_takedown_overlapping_repick(world, monkeypatch):
    row = ready(world)
    assert approve(world, row).status_code == 200
    admin = world["manager"]
    admin.is_admin = True
    world["app"].config["API_KEY"] = "probe-admin-key"
    monkeypatch.setenv("ADMIN_API_KEY", "probe-admin-key")
    db.session.commit()
    auth = {
        "Authorization": "Bearer " + issue_user_token(admin.email, role="admin")["token"],
        "X-API-Key": "probe-admin-key",
    }
    client = world["app"].test_client()
    assert client.post(f"/api/admin/highlights/{row.id}/takedown", headers=auth).status_code == 200
    # Change the server-reviewed tracklet by one second: almost all held frames remain.
    world["track"].last_s = 31
    db.session.commit()
    res = pick(world, end_s=31)
    assert res.status_code == 422 and res.json["error"] == "highlight_admin_taken_down"


def test_takedown_existing_overlap(world, monkeypatch):
    second = VideoTracklet(
        video_match_id=world["match"].id,
        roster_entry_id=world["entry"].id,
        kind="chain",
        team_cluster=0,
        tag_source="human",
        review_action="confirmed",
        reviewed_at=now(),
        confidence="high",
        first_s=10,
        last_s=31,
    )
    third = VideoTracklet(
        video_match_id=world["match"].id,
        roster_entry_id=world["entry"].id,
        kind="chain",
        team_cluster=0,
        tag_source="human",
        review_action="confirmed",
        reviewed_at=now(),
        confidence="high",
        first_s=70,
        last_s=80,
    )
    db.session.add_all([second, third])
    db.session.commit()
    row = ready(world)
    assert approve(world, row).status_code == 200
    siblings = []
    from src.workers.highlight_worker import claim_next, finish

    for track in (second, third):
        response = pick(world, tracklet_id=track.id, start_s=track.first_s, end_s=track.last_s, title="Other window")
        assert response.status_code == 201, response.json
        sibling = db.session.get(PlayerHighlight, response.json["id"])
        job = claim_next()
        assert finish(*job, output_etag="clip-other", output_size=20)
        assert approve(world, sibling).status_code == 200
        siblings.append(sibling)
    monkeypatch.setenv("ADMIN_API_KEY", "probe-admin-key")
    world["app"].config["API_KEY"] = "probe-admin-key"
    auth = {
        "Authorization": "Bearer " + issue_user_token(world["manager"].email, role="admin")["token"],
        "X-API-Key": "probe-admin-key",
    }
    client = world["app"].test_client()
    assert client.post(f"/api/admin/highlights/{row.id}/takedown", headers=auth).status_code == 200
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    codes = [client.get(f"/api/highlights/{item.id}/clip").status_code for item in siblings]
    print("After admin takedown 10-30, overlapping10-31 and harmless70-80 grants", codes)
    assert codes == [404, 302], "Already approved overlapping held frames remain public"


def base(w):
    return f"/api/club/{w['program'].id}/matches/{w['match'].id}"


def review_recording(w, **data):
    return (
        w["app"]
        .test_client()
        .post(
            base(w) + "/highlight-review",
            headers=headers(w["manager"]),
            json={"classification": "adult_only", "all_visible_people_adults": True, **data},
        )
    )


@pytest.mark.parametrize("roster_provider", [False, True])
def test_x1_pending_bridge_retains_both_selection_and_permanent_key(world, roster_provider):
    from src.models.follow import PlayerShadow

    world["local"].api_player_id = 765433
    if roster_provider:
        world["member"].local_player_id = None
        world["member"].player_api_id = 765433
    world["report"].club_local_player_id_at_finalize = None
    world["report"].club_player_api_id_at_finalize = 765433
    db.session.add(PlayerShadow(player_api_id=765433, player_name="Adult", birth_date=date(2000, 1, 1), is_active=True))
    db.session.commit()
    row = ready(world)
    assert row.player_decision == "pending" and row.player_api_id == 765433
    assert not permanent_key_missing(row)
    assert sweep_highlights()["expired"] == 0
    assert row.revoked_at is None
    # A real removal still selects and revokes this formerly valid bridge.
    world["local"].merged_into_local_player_id = world["local"].id
    db.session.commit()
    assert permanent_key_missing(row)
    assert sweep_highlights()["expired"] == 1
    assert row.revoke_reason == "consent_key_removed"


@pytest.mark.parametrize(
    "label",
    [
        "2012B",
        "B2012",
        "G2011",
        "2010s",
        "U2010",
        "15U",
        "14u",
        "12 & under",
        "15 and under",
        "Age 15",
        "Year9",
        "Yr 10",
        "Grade 8",
        "18s",
        "O17",
        "JO17",
        "MO15",
        "Ｕ１８",
        "Sixteens",
        "Scholars",
        "J15",
        "P16",
        "F17",
        "U٨",
        "U１２",
    ],
)
@pytest.mark.parametrize("kind", ["first_team", "reserves"])
def test_o1_youth_labels_never_publish_even_with_senior_tick(world, label, kind):
    world["squad"].name = label
    world["squad"].kind = kind
    db.session.commit()
    assert highlights.squad_classification(world["squad"]) == "youth"
    result = review_recording(world, squad_adult_attested=True)
    assert result.status_code == 422 and result.json["error"] == "youth_recording_private"
    assert pick(world).status_code == 422
    assert world["app"].test_client().get(f"/api/players/{world['local'].api_player_id}/highlights").json == {
        "highlights": []
    }


@pytest.mark.parametrize("label", ["Team 7", "XI 2", "U21", "19U", "First team 999", "Ｓｅｎｉｏｒｓ ２"])
def test_o1_ambiguous_numbered_seniors_require_attestation(world, label):
    world["squad"].name = label
    db.session.commit()
    assert highlights.squad_classification(world["squad"]) == "unknown"
    assert review_recording(world).status_code == 422
    assert pick(world).status_code == 422
    assert review_recording(world, squad_adult_attested=True).status_code == 200
    assert pick(world).status_code == 201


def test_o3_verified_review_cannot_precede_real_invited_date_edit(world):
    from src.models.club_access import ClubAccessGrant
    from src.models.highlights import HighlightFootageReview
    from src.routes.club import club_bp

    world["app"].register_blueprint(club_bp, url_prefix="/api")
    db.session.delete(world["review"])
    world["match"].status = "uploaded"
    world["match"].finalized_at = None
    world["match"].match_date = now().date() - timedelta(days=60)
    db.session.add(
        ClubAccessGrant(
            program_id=world["program"].id,
            user_account_id=world["stranger"].id,
            role="manager",
            all_squads=True,
            status="active",
            source="invite",
        )
    )
    db.session.commit()
    assert review_recording(world).status_code == 422
    assert db.session.get(HighlightFootageReview, world["match"].id) is None
    client = world["app"].test_client()
    patch = client.patch(base(world), headers=headers(world["stranger"]), json={"match_date": now().date().isoformat()})
    assert patch.status_code == 200, patch.json
    world["match"].status = "finalized"
    world["match"].finalized_at = now()
    db.session.commit()
    assert pick(world).status_code == 422
    assert review_recording(world).status_code == 200
    assert pick(world).status_code == 201


@pytest.mark.parametrize("change", ["date", "squad_id", "squad_kind", "squad_name", "squad_age", "finalization"])
def test_o3_context_changes_need_review_pick_and_player_approval(world, monkeypatch, change):
    from src.models.funding import ClubSquad

    row = ready(world)
    assert approve(world, row).status_code == 200
    if change == "date":
        world["match"].match_date -= timedelta(days=1)
    elif change == "squad_id":
        other = ClubSquad(program_id=world["program"].id, name="Senior reserves", kind="reserves")
        db.session.add(other)
        db.session.flush()
        world["match"].squad_id = other.id
    elif change == "squad_kind":
        world["squad"].kind = "other"
    elif change == "squad_name":
        world["squad"].name = "Senior eleven"
    elif change == "squad_age":
        world["squad"].age_limit = 21
    else:
        world["match"].finalized_at += timedelta(seconds=1)
    db.session.commit()
    db.session.refresh(row)
    assert row.revoked_at and row.revoke_reason == "source_changed"
    assert pick(world).status_code == 422
    assert review_recording(world, squad_adult_attested=True).status_code == 200
    response = pick(world)
    assert response.status_code == 201
    fresh = db.session.get(PlayerHighlight, response.json["id"])
    assert fresh.id != row.id and fresh.player_decision == "pending"
    from src.workers.highlight_worker import claim_next, finish

    job = claim_next()
    while job and db.session.get(HighlightRenderJob, job[0]).kind == "highlight_delete":
        finish(*job)
        job = claim_next()
    assert finish(*job, output_etag="fresh", output_size=20)
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{fresh.id}/clip").status_code == 404
    assert approve(world, fresh).status_code == 200
    assert client.get(f"/api/highlights/{fresh.id}/clip").status_code == 302


def test_o3_unused_senior_tick_is_not_stored_or_transferred(world):
    assert review_recording(world, squad_adult_attested=True).status_code == 200
    db.session.refresh(world["review"])
    assert not world["review"].squad_adult_attested
    world["squad"].kind = "other"
    db.session.commit()
    assert pick(world).status_code == 422
    assert review_recording(world).status_code == 422
    assert review_recording(world, squad_adult_attested=True).status_code == 200
    assert pick(world).status_code == 201


@pytest.mark.parametrize("during_storage", [False, True])
def test_o4_ambiguous_self_claim_hides_reversibly_without_asset_deletion(world, monkeypatch, during_storage):
    from src.models.showcase import PlayerProfileClaim

    row = ready(world)
    assert approve(world, row).status_code == 200
    other = PlayerProfileClaim(
        local_player_id=world["local"].id,
        user_account_id=world["stranger"].id,
        relationship_type="player",
        status="approved",
    )

    def add_claim():
        db.session.add(other)
        db.session.commit()

    def storage(*a, **k):
        if during_storage:
            add_claim()
        return "https://storage.example/clip.mp4"

    if not during_storage:
        add_claim()
    monkeypatch.setattr(highlights_storage, "output_read_url", storage)
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert pick(world, title="Another").status_code == 422
    assert sweep_highlights()["expired"] == 0
    db.session.refresh(row)
    assert row.revoked_at is None and row.player_decision == "approve" and row.output_blob_path
    assert not HighlightRenderJob.query.filter_by(kind="highlight_delete").count()
    other.status = "rejected"
    db.session.commit()
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
    # Keeping only the other owner must never transfer the first owner's consent.
    other.status = "approved"
    world["claim"].status = "rejected"
    db.session.commit()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404


def test_o5_public_loads_referenced_tracklets_only_and_picker_keeps_candidates(world, monkeypatch):
    import sqlalchemy as sa
    from flask import g

    db.session.execute(
        sa.insert(VideoTracklet),
        [
            dict(
                video_match_id=world["match"].id,
                kind="fragment",
                team_cluster=0,
                first_s=70,
                last_s=80,
                confidence="low",
                evidence={"unrelated": list(range(20))},
            )
            for _ in range(50)
        ],
    )
    db.session.commit()
    row = ready(world)
    assert approve(world, row).status_code == 200
    original = highlights.prepare_reads
    counts = []

    def observe(*a, **k):
        original(*a, **k)
        loaded = list(g.highlight_evidence["models"].get(VideoTracklet, {}).values())
        counts.append(len(loaded))
        if not k.get("candidates"):
            assert [t.id for t in loaded] == [world["track"].id]

    monkeypatch.setattr(highlights, "prepare_reads", observe)
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
    assert counts == [1, 1]
    counts.clear()
    assert client.get(f"/api/players/{row.signed_id}/highlights").json["highlights"]
    assert counts == [1]
    counts.clear()
    assert client.get(base(world) + "/highlights", headers=headers(world["manager"])).json["candidates"]
    assert counts == [51]


@pytest.mark.parametrize("sql_writer", [False, True])
@pytest.mark.parametrize("decision", ["pending", "approve", "private"])
def test_o6_source_notice_grouping_and_declined_exclusion(world, decision, sql_writer):
    import os

    import sqlalchemy as sa
    from src.models.league import UserAccount
    from src.models.p2_foundation import NotificationOutbox
    from src.services.notification_outbox import _templates

    if sql_writer and os.getenv("C2_POSTGRES_TESTS") != "1":
        pytest.skip("raw SQL guard requires PostgreSQL")
    rows = []
    for index in range(3):
        response = pick(world, title=f"Moment {index}")
        assert response.status_code == 201
        row = db.session.get(PlayerHighlight, response.json["id"])
        from src.workers.highlight_worker import claim_next, finish

        job = claim_next()
        assert finish(*job, output_etag=f"clip-{index}", output_size=20)
        if decision != "pending":
            response = (
                world["app"]
                .test_client()
                .post(
                    f"/api/me/highlight-requests/{row.id}/decision",
                    headers=headers(world["player"]),
                    json={"decision": decision, "version": row.version},
                )
            )
            assert response.status_code == 200
        rows.append(row)
    NotificationOutbox.query.delete()
    db.session.commit()
    if sql_writer:
        db.session.execute(
            sa.text("UPDATE c2_checks.video_roster_entries SET jersey_number=77 WHERE id=:id"),
            {"id": world["entry"].id},
        )
    else:
        world["entry"].jersey_number = 77
    db.session.commit()
    intents = NotificationOutbox.query.filter_by(template="highlight_source_changed").all()
    admitted = [
        x for x in intents if _templates[x.template].eligible(x, db.session.get(UserAccount, x.recipient_user_id))
    ]
    assert len(intents) == len(admitted) == (0 if decision == "private" else 2)
    if intents:
        assert {i.recipient_user_id for i in intents} == {world["manager"].id, world["player"].id}
        assert all(set(i.payload) == {"highlight_id", "version"} for i in intents)
        assert all(i.payload["highlight_id"] in {r.id for r in rows} for i in intents)
    assert all(db.session.get(PlayerHighlight, r.id).revoke_reason == "source_changed" for r in rows)


@pytest.mark.parametrize("during_storage", [False, True])
def test_x2_interval_hold_applies_to_batched_read_and_storage_recheck(world, monkeypatch, during_storage):
    from uuid import uuid4

    row = ready(world)
    assert approve(world, row).status_code == 200
    hold = HighlightTakedown(id=str(uuid4()), video_match_id=row.video_match_id, start_s=12, end_s=32)

    def hold_now():
        db.session.add(hold)
        db.session.commit()

    def storage(*a, **k):
        if during_storage:
            hold_now()
        return "https://storage.example/clip.mp4"

    if not during_storage:
        hold_now()
    monkeypatch.setattr(highlights_storage, "output_read_url", storage)
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert row.revoked_at is None  # eligibility must enforce the hold independently of revocation
    assert client.get(f"/api/players/{row.signed_id}/highlights").json == {"highlights": []}
    hold.lifted_at = now()
    db.session.commit()
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302


def second_adult(world, first_s=12, last_s=32, jersey=10):
    user = UserAccount(email="second@example.test", display_name="Second", display_name_lower="second")
    local = LocalPlayer(
        display_name="Second Adult", status="approved", birth_date=date(1999, 1, 1), birth_year=1999, provenance="user"
    )
    db.session.add_all([user, local])
    db.session.flush()
    local.api_player_id = -local.id
    claim = PlayerProfileClaim(
        local_player_id=local.id, user_account_id=user.id, relationship_type="player", status="approved"
    )
    member = ClubRosterMember(
        program_id=world["program"].id,
        local_player_id=local.id,
        added_by_user_id=world["manager"].id,
        squad_id=world["squad"].id,
    )
    db.session.add_all([claim, member])
    db.session.flush()
    entry = VideoRosterEntry(
        video_match_id=world["match"].id,
        player_name="Second Adult",
        jersey_number=jersey,
        club_roster_member_id=member.id,
    )
    db.session.add(entry)
    db.session.flush()
    track = VideoTracklet(
        video_match_id=world["match"].id,
        roster_entry_id=entry.id,
        kind="chain",
        team_cluster=0,
        tag_source="human",
        review_action="confirmed",
        reviewed_at=now(),
        confidence="high",
        first_s=first_s,
        last_s=last_s,
    )
    report = VideoPlayerReport(
        video_match_id=world["match"].id,
        roster_entry_id=entry.id,
        identity_confidence="human_confirmed",
        club_program_id_at_finalize=world["program"].id,
        club_roster_member_id_at_finalize=member.id,
        club_local_player_id_at_finalize=local.id,
        model_version="test",
    )
    db.session.add_all([track, report])
    db.session.commit()
    return SimpleNamespace(user=user, local=local, claim=claim, member=member, entry=entry, track=track)


def test_x2_other_subject_overlap_blocked_and_only_admin_can_lift(world, monkeypatch):
    other = second_adult(world, 12, 32)
    row = ready(world)
    assert approve(world, row).status_code == 200
    monkeypatch.setenv("ADMIN_API_KEY", "c2-test-key")
    auth = {
        "Authorization": "Bearer " + issue_user_token(world["manager"].email, role="admin")["token"],
        "X-API-Key": "c2-test-key",
    }
    client = world["app"].test_client()
    assert client.post(f"/api/admin/highlights/{row.id}/takedown", headers=auth).status_code == 200
    overlap = dict(roster_entry_id=other.entry.id, tracklet_id=other.track.id, start_s=12, end_s=32)
    result = pick(world, **overlap)
    assert result.status_code == 422 and result.json["error"] == "highlight_admin_taken_down"
    assert (
        client.post(
            f"/api/admin/highlights/{row.id}/lift", headers={**headers(world["stranger"]), "X-API-Key": "c2-test-key"}
        ).status_code
        == 401
    )
    assert client.post(f"/api/admin/highlights/{row.id}/lift", headers=auth).status_code == 200
    result = pick(world, **overlap)
    assert result.status_code == 201 and result.json["player_decision"] == "pending"


@pytest.mark.parametrize("field", ["match_date", "squad_id", "finalized_at", "squad_name"])
def test_o3_raw_sql_context_roundtrip_cannot_reuse_review(world, field):
    import os

    import sqlalchemy as sa

    if os.getenv("C2_POSTGRES_TESTS") != "1":
        pytest.skip("raw SQL context guards require PostgreSQL")
    row = ready(world)
    assert approve(world, row).status_code == 200
    if field == "squad_name":
        table, original = "club_squads", world["squad"].name
        column, changed, target = "name", "Another senior name", world["squad"].id
    else:
        table, column, target = "video_matches", field, world["match"].id
        original = getattr(world["match"], field)
        changed = {
            "match_date": now().date() - timedelta(days=1),
            "squad_id": None,
            "finalized_at": now() + timedelta(seconds=1),
        }[field]
    for value in (changed, original):
        db.session.execute(
            sa.text(f"UPDATE c2_checks.{table} SET {column}=:value WHERE id=:id"), {"value": value, "id": target}
        )
        db.session.commit()
        db.session.expire_all()
        assert pick(world).status_code == 422
    db.session.refresh(row)
    assert row.revoked_at and row.revoke_reason == "source_changed"
    assert review_recording(world).status_code == 200
    assert pick(world).status_code == 201


def test_o4_real_admin_claim_approval_hides_existing_clip_without_consent_transfer(world, monkeypatch):
    from src.routes.showcase import showcase_bp

    world["app"].register_blueprint(showcase_bp, url_prefix="/api")
    monkeypatch.setenv("ADMIN_API_KEY", "c2-claim-test-key")
    monkeypatch.setattr(
        "src.services.trust_decision_email_service.send_player_claim_decision_email", lambda *a, **k: True
    )
    world["manager"].is_admin = True
    db.session.commit()
    row = ready(world)
    assert approve(world, row).status_code == 200
    other = PlayerProfileClaim(
        local_player_id=world["local"].id,
        user_account_id=world["stranger"].id,
        relationship_type="player",
        status="pending",
    )
    db.session.add(other)
    db.session.commit()
    auth = {
        "Authorization": "Bearer " + issue_user_token(world["manager"].email, role="admin")["token"],
        "X-API-Key": "c2-claim-test-key",
    }
    client = world["app"].test_client()
    result = client.post(f"/api/admin/showcase/claims/{other.id}/review", headers=auth, json={"action": "approve"})
    assert result.status_code == 200, result.json
    assert highlights.claim_for_subject(row.signed_id) is None
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert sweep_highlights()["expired"] == 0
    assert row.claim_id == world["claim"].id and row.recipient_user_id == world["player"].id
    other.status = "rejected"
    db.session.commit()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
