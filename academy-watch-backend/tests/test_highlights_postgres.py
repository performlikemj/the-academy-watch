# ruff: noqa: F811
"""Opt-in concurrency/SQL-writer checks against C2's isolated scratch schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import sqlalchemy as sa
from src.models.highlights import HighlightConsentEvent, HighlightRenderJob, PlayerHighlight, now
from src.models.league import db
from src.workers.highlight_worker import claim_next
from test_highlights import approve, headers, pick, ready, world  # noqa: F401, F811

pytestmark = pytest.mark.skipif(os.getenv("C2_POSTGRES_TESTS") != "1", reason="isolated local PostgreSQL required")


def test_sql_source_update_durably_resets_consent(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    db.session.execute(
        sa.text("UPDATE c2_checks.video_matches SET blob_etag=:etag WHERE id=:id"),
        {"etag": "bulk-new-generation", "id": world["match"].id},
    )
    db.session.commit()
    db.session.refresh(row)
    assert row.player_decision == "pending" and row.approved_source_version is None and row.source_version == 2
    assert HighlightConsentEvent.query.filter_by(highlight_id=row.id, action="source_changed").count() == 1
    assert abs((row.revoked_at - now()).total_seconds()) < 10
    cleanup = HighlightRenderJob.query.filter_by(kind="highlight_delete").one()
    assert 1190 < (cleanup.created_at - now()).total_seconds() < 1210


def test_two_pick_requests_share_one_intent_job_and_notification(world):
    app = world["app"]
    base = f"/api/club/{world['program'].id}/matches/{world['match'].id}/highlights"
    header = headers(world["manager"])
    body = dict(roster_entry_id=world["entry"].id, tracklet_id=world["track"].id, start_s=10, end_s=30)
    db.session.commit()
    barrier = Barrier(2)

    def request():
        with app.test_client() as client:
            barrier.wait()
            response = client.post(base, json=body, headers=header)
            return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(), range(2)))
    assert sorted(row[0] for row in results) == [200, 201], results
    assert results[0][1]["id"] == results[1][1]["id"]
    assert PlayerHighlight.query.count() == 1 and HighlightRenderJob.query.count() == 1


def test_two_workers_claim_once(world):
    assert pick(world).status_code == 201
    app = world["app"]
    db.session.commit()
    barrier = Barrier(2)

    def claim():
        with app.app_context():
            barrier.wait()
            return claim_next()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(), range(2)))
    assert sum(row is not None for row in claims) == 1


def test_decision_race_has_one_winner(world):
    row = ready(world)
    app = world["app"]
    path = f"/api/me/highlight-requests/{row.id}/decision"
    header = headers(world["player"])
    version = row.version
    db.session.commit()
    barrier = Barrier(2)

    def request(decision):
        with app.test_client() as client:
            barrier.wait()
            return client.post(path, json={"decision": decision, "version": version}, headers=header).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, ["approve", "private"]))
    assert sorted(results) == [200, 409]


def test_sql_source_removal_revokes_and_queues_cleanup(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    # Existing video child FKs restrict raw match deletion; maintenance removes children first.
    for table in ("video_player_reports", "video_tracklets", "video_roster_entries", "video_matches"):
        key = "id" if table == "video_matches" else "video_match_id"
        db.session.execute(sa.text(f"DELETE FROM c2_checks.{table} WHERE {key}=:id"), {"id": world["match"].id})
    db.session.commit()
    db.session.refresh(row)
    assert row.video_match_id is None and row.revoked_at and row.approved_source_version is None
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete").count() == 1


def test_f13_raw_child_then_match_writer_uses_match_before_highlight(world):
    import time
    from threading import Event

    row = ready(world)
    assert approve(world, row).status_code == 200
    match_id, track_id, hid = world["match"].id, world["track"].id, row.id
    engine = db.engine
    db.session.commit()
    started = Event()

    def writer():
        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL lock_timeout='5s'"))
            started.set()
            conn.execute(
                sa.text("UPDATE c2_checks.video_tracklets SET first_s=first_s+1 WHERE id=:id"), {"id": track_id}
            )
            conn.execute(
                sa.text("UPDATE c2_checks.video_matches SET duration_s=duration_s+1 WHERE id=:id"), {"id": match_id}
            )

    with engine.connect() as decision, ThreadPoolExecutor(max_workers=1) as pool:
        transaction = decision.begin()
        decision.execute(sa.text("SET LOCAL lock_timeout='1s'"))
        decision.execute(sa.text("SELECT id FROM c2_checks.video_matches WHERE id=:id FOR UPDATE"), {"id": match_id})
        pending = pool.submit(writer)
        assert started.wait(2)
        time.sleep(0.15)  # writer reaches its source trigger, waiting on the match lock
        # Before F13 the trigger held this row and waited for our match: deadlock.
        decision.execute(sa.text("SELECT id FROM c2_checks.player_highlights WHERE id=:id FOR UPDATE"), {"id": hid})
        transaction.commit()
        pending.result(timeout=8)
    db.session.refresh(row)
    assert row.revoked_at and row.player_decision == "pending"
    assert world["app"].test_client().get(f"/api/highlights/{hid}/clip").status_code == 404


@pytest.mark.parametrize("parent", ["local_players", "club_programs"])
def test_f14_parent_cascade_queues_standalone_asset_cleanup(world, parent):
    from uuid import uuid4

    from src.models.funding import ClubProgram
    from src.models.showcase import LocalPlayer

    original = ready(world)
    values = {column.name: getattr(original, column.name) for column in PlayerHighlight.__table__.columns}
    program = ClubProgram(
        funding_league_id=world["program"].funding_league_id,
        name="Cascade test",
        legal_name="Cascade test",
        slug="cascade-only",
        country="JP",
        region="Test",
        platform_status="approved",
    )
    local = LocalPlayer(display_name="Cascade test", status="approved")
    db.session.add_all([program, local])
    db.session.flush()
    local.api_player_id = -local.id
    hid, attempt = str(uuid4()), str(uuid4())
    path = f"highlights/{hid}/{attempt}.mp4"
    values.update(
        id=hid,
        pick_key=uuid4().hex,
        program_id=program.id,
        local_player_id=local.id,
        video_match_id=None,
        roster_entry_id=None,
        tracklet_id=None,
        claim_id=None,
        output_blob_path=path,
    )
    db.session.add(PlayerHighlight(**values))
    db.session.flush()
    db.session.add(
        HighlightRenderJob(
            highlight_id=hid, kind="highlight_cut", blob_path=path, status="succeeded", completed_at=now()
        )
    )
    db.session.commit()
    parent_id = local.id if parent == "local_players" else program.id
    db.session.execute(sa.text(f"DELETE FROM c2_checks.{parent} WHERE id=:id"), {"id": parent_id})
    db.session.commit()
    assert PlayerHighlight.query.filter_by(id=hid).count() == 0
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).count() == 1
