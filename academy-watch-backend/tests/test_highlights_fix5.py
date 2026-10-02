"""RC2V4 route-review recovery probes reversed into regression assertions."""
# ruff: noqa: F811

from datetime import timedelta

import pytest
import sqlalchemy as sa
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubRosterMember, ClubSquad
from src.models.highlights import HighlightFootageReview, HighlightRenderJob, now
from src.models.league import db
from src.models.video import VideoMatch
from src.services import highlights, highlights_storage
from test_highlights import approve, headers, pick, ready, world  # noqa: F401
from test_highlights_fix3 import base, review_recording


def route_review(w):
    # Start with the actual route's complete evidence, never the old partial fixture.
    db.session.delete(w["review"])
    db.session.commit()
    assert review_recording(w).status_code == 200
    review = db.session.get(HighlightFootageReview, w["match"].id)
    assert review.source_context == review.classification_context == highlights.review_context(w["match"])
    return review


@pytest.mark.parametrize("writer", ["orm", "sql"])
@pytest.mark.parametrize("change", ["name", "kind", "age_limit", "date", "member", "match_squad", "finalized_at"])
def test_o1_change_revert_reconfirm_restores_review_not_old_consent(world, writer, change):
    if writer == "sql" and db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL source triggers")
    other = ClubSquad(program_id=world["program"].id, name="Reserves", kind="reserves")
    db.session.add(other)
    db.session.commit()
    review = route_review(world)
    row = ready(world)
    assert approve(world, row).status_code == 200
    context, reviewed_at = review.classification_context, review.reviewed_at
    changes = {
        "name": (world["squad"], ClubSquad, "club_squads", "name", "U16"),
        "kind": (world["squad"], ClubSquad, "club_squads", "kind", "reserves"),
        "age_limit": (world["squad"], ClubSquad, "club_squads", "age_limit", 23),
        "date": (
            world["match"],
            VideoMatch,
            "video_matches",
            "match_date",
            world["match"].match_date - timedelta(days=1),
        ),
        "member": (world["member"], ClubRosterMember, "club_roster_members", "squad_id", other.id),
        "match_squad": (world["match"], VideoMatch, "video_matches", "squad_id", other.id),
        "finalized_at": (
            world["match"],
            VideoMatch,
            "video_matches",
            "finalized_at",
            world["match"].finalized_at - timedelta(seconds=1),
        ),
    }
    obj, model, table, column, changed = changes[change]
    original, oid = getattr(obj, column), obj.id
    for value in (changed, original):
        if writer == "orm":
            setattr(db.session.get(model, oid), column, value)
        else:
            db.session.execute(
                sa.text(f"UPDATE c2_checks.{table} SET {column}=:value WHERE id=:id"), {"value": value, "id": oid}
            )
        db.session.commit()
        db.session.expire_all()
    assert review.source_context is None
    assert review.classification_context == context == highlights.review_context(world["match"])
    assert row.revoked_at is not None
    client = world["app"].test_client()
    before = client.get(base(world) + "/highlights", headers=headers(world["manager"])).json
    assert before["recording_block_reason"] == "review_required" and before["can_review"]
    assert pick(world).status_code == 422
    assert review_recording(world).status_code == 200
    db.session.expire_all()
    assert review.source_context == review.classification_context == context
    assert review.reviewed_at > reviewed_at
    after = client.get(base(world) + "/highlights", headers=headers(world["manager"])).json
    assert after["adult_recording"] and after["recording_block_reason"] is None
    fresh = pick(world)
    assert fresh.status_code == 201, fresh.json
    assert fresh.json["player_decision"] == "pending" and fresh.json["id"] != row.id
    assert row.revoked_at is not None
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    # Repeated confirmation of a LIVE unchanged review remains an idempotent no-op.
    timestamp = review.reviewed_at
    assert review_recording(world).status_code == 200
    assert review.reviewed_at == timestamp
    assert db.session.get(HighlightFootageReview, world["match"].id).source_context == context


@pytest.mark.parametrize("writer", ["orm", "sql"])
def test_o1_cosmetic_roundtrip_keeps_live_review(world, writer):
    if writer == "sql" and db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL source triggers")
    review = route_review(world)
    context, reviewed_at = review.source_context, review.reviewed_at
    for name in ("FIRST TEAM", "First team"):
        if writer == "orm":
            world["squad"].name = name
        else:
            db.session.execute(
                sa.text("UPDATE c2_checks.club_squads SET name=:name WHERE id=:id"),
                {"name": name, "id": world["squad"].id},
            )
        db.session.commit()
        db.session.expire_all()
    assert review.source_context == context
    assert review_recording(world).status_code == 200
    assert review.reviewed_at == reviewed_at
    assert pick(world).status_code == 201


@pytest.mark.parametrize("writer", ["route", "sql"])
@pytest.mark.parametrize("flag_on", [False, True])
def test_o2_structural_kind_change_withdraws_expired_clip_even_dark(world, monkeypatch, writer, flag_on):
    """Lead ruling retains the probe's fail-closed outcome, including invited staff."""
    if writer == "sql" and db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL source triggers")
    from src.routes.club import club_bp
    from src.services.video_retention import expire_raw_footage

    world["app"].register_blueprint(club_bp, url_prefix="/api")
    world["match"].match_date = (now() - timedelta(days=80)).date()
    world["match"].uploaded_at = now() - timedelta(days=80)
    world["match"].created_at = world["match"].uploaded_at
    world["match"].expires_at = world["match"].uploaded_at + timedelta(days=90)
    db.session.commit()
    route_review(world)
    row = ready(world)
    assert approve(world, row).status_code == 200
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")
    monkeypatch.setattr("src.services.video_storage.delete_blob", lambda path: True)
    assert expire_raw_footage(now=now() + timedelta(days=11))["expired"] == 1
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
    db.session.add(
        ClubAccessGrant(
            program_id=world["program"].id,
            user_account_id=world["stranger"].id,
            role="manager",
            all_squads=True,
            status="active",
            source="invite",
            granted_by_user_id=world["manager"].id,
        )
    )
    db.session.commit()
    path = row.output_blob_path
    assert highlights.squad_classification(world["squad"]) == "adult"
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1" if flag_on else "0")
    if writer == "route":
        changed = client.patch(
            f"/api/club/{world['program'].id}/squads/{world['squad'].id}",
            json={"kind": "reserves"},
            headers=headers(world["stranger"]),
        )
        assert changed.status_code == 200, changed.json
    else:
        db.session.execute(
            sa.text("UPDATE c2_checks.club_squads SET kind='reserves' WHERE id=:id"), {"id": world["squad"].id}
        )
        db.session.commit()
    db.session.expire_all()
    assert highlights.squad_classification(world["squad"]) == "adult"
    assert row.revoked_at is not None and row.revoke_reason == "source_changed"
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path, status="queued").count() == 1
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1")
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert review_recording(world).status_code == 404 and pick(world).status_code == 404
