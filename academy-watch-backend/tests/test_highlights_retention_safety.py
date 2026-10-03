"""Production-shaped dark safety and exact-owned-blob retention invariants.

The same tests run on SQLite and the lane's isolated PostgreSQL schema/guards.
"""
# ruff: noqa: F811

import json
import random
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    HighlightTakedown,
    PlayerHighlight,
    now,
    uuid4,
)
from src.models.league import db
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services import highlights_retention as retention
from src.services import highlights_storage, video_retention, video_storage
from src.workers import highlight_worker as worker
from test_highlights import approve, ready, world  # noqa: F401

HIGHLIGHT_TABLES = (
    PlayerHighlight,
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    HighlightTakedown,
)
RAW_TABLES = (VideoMatch, VideoRosterEntry, VideoTracklet, VideoPlayerReport)


def snapshot(models):
    return {
        model.__tablename__: sorted(
            [tuple(getattr(row, col.name) for col in model.__table__.columns) for row in model.query], key=repr
        )
        for model in models
    }


@pytest.fixture
def production_today(world):
    db.session.delete(world["review"])
    match = world["match"]
    old = now() - timedelta(days=120)
    match.created_at = match.uploaded_at = old
    match.match_date = old.date()
    match.finalized_at = old + timedelta(hours=1)
    match.expires_at = old + timedelta(days=90)
    # Includes completed-but-overdue, already-expired, and abandoned raw uploads.
    for status in ("expired", "created"):
        db.session.add(
            VideoMatch(
                club_program_id=world["program"].id,
                squad_id=world["squad"].id,
                status=status,
                blob_path=f"matches/legacy-{status}/raw.mp4",
                blob_etag="old-raw-etag",
                created_at=old,
                uploaded_at=old if status == "expired" else None,
                expires_at=old + timedelta(days=90) if status == "expired" else None,
            )
        )
    db.session.commit()
    assert all(model.query.count() == 0 for model in HIGHLIGHT_TABLES)
    assert len(video_retention.due_matches()) == 2  # real raw retention would act; highlights must not
    return world


def forbid_storage(monkeypatch):
    calls = {}
    for module, names in (
        (video_storage, ("delete_blob", "_service_client", "verify_expected_blob", "mint_media_read_sas")),
        (highlights_storage, ("download_source", "upload_output", "output_read_url")),
        (worker, ("cut_file",)),
        (video_retention, ("expire_raw_footage",)),
    ):
        for name in names:
            calls[name] = Mock(side_effect=AssertionError(f"unexpected storage/raw-retention call: {name}"))
            monkeypatch.setattr(module, name, calls[name])
    return calls


@pytest.mark.parametrize("feature_on", [False, True])
@pytest.mark.parametrize("sweep_on", [False, True])
def test_production_today_zero_selection_deletion_and_storage(production_today, monkeypatch, feature_on, sweep_on):
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1" if feature_on else "0")
    monkeypatch.setenv("HIGHLIGHT_RETENTION_SWEEP_ENABLED", "1" if sweep_on else "0")
    calls = forbid_storage(monkeypatch)
    before = snapshot(RAW_TABLES + HIGHLIGHT_TABLES)
    statements = []

    def record_sql(conn, cursor, statement, params, context, many):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", record_sql)
    try:
        assert retention.sweep_highlights() == dict.fromkeys(retention.COUNT_KEYS, 0)
        assert retention.sweep_highlights(dry_run=True) == dict.fromkeys(retention.COUNT_KEYS, 0)
        assert worker.claim_next() is None
        # Both CLI modes also perform no cuts, cleanup, claims or raw retention.
        monkeypatch.setitem(sys.modules, "src.main", SimpleNamespace(app=production_today["app"]))
        for args in (["highlight_worker"], ["highlight_worker", "--dry-run"]):
            monkeypatch.setattr(sys, "argv", args)
            worker.main()
        assert snapshot(RAW_TABLES + HIGHLIGHT_TABLES) == before
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record_sql)
    assert not any(sql.lstrip().split()[0].upper() in {"DELETE", "UPDATE", "INSERT"} for sql in statements)
    for call in calls.values():
        call.assert_not_called()
    print(
        json.dumps(
            {
                "feature_on": feature_on,
                "sweep_on": sweep_on,
                "rows": {k: len(v) for k, v in before.items()},
                "selected_for_retention": 0,
                "deleted_rows": 0,
                "storage_calls": 0,
                "raw_unchanged": True,
            }
        )
    )


def test_unowned_footage_never_enters_any_highlight_delete_path(production_today, monkeypatch):
    calls = forbid_storage(monkeypatch)
    before = snapshot(RAW_TABLES + HIGHLIGHT_TABLES)
    for match in VideoMatch.query.all():
        worker.queue_cleanup(match.blob_path, delayed=False)
        worker.cleanup_output(match.blob_path)
        assert not worker.delete_output(match.blob_path)
    assert worker.claim_next() is None
    assert not worker.run_one(uuid4(), uuid4())
    assert snapshot(RAW_TABLES + HIGHLIGHT_TABLES) == before
    for call in calls.values():
        call.assert_not_called()


@pytest.mark.parametrize("switch", [None, "0", "false", "off", "no", "garbage"])
def test_kill_switch_blocks_sweep_and_all_worker_deletes(world, monkeypatch, capsys, switch):
    row = ready(world)
    path = row.output_blob_path
    row.revoked_at = now() - timedelta(days=100)
    job = HighlightRenderJob(kind="highlight_delete", blob_path=path, created_at=now() - timedelta(days=100))
    db.session.add(job)
    db.session.commit()
    claimed = worker.claim_next()
    assert claimed and claimed[0] == job.id
    if switch is None:
        monkeypatch.delenv("HIGHLIGHT_RETENTION_SWEEP_ENABLED")
    else:
        monkeypatch.setenv("HIGHLIGHT_RETENTION_SWEEP_ENABLED", switch)
    calls = forbid_storage(monkeypatch)
    before = snapshot(HIGHLIGHT_TABLES + RAW_TABLES)
    assert retention.sweep_highlights() == dict.fromkeys(retention.COUNT_KEYS, 0)
    assert "disabled" in capsys.readouterr().out
    assert not worker.run_one(*claimed)  # switch withdrawn after a lease was claimed
    worker.cleanup_output(path)  # failed/stale cut's immediate cleanup
    assert not worker.delete_output(path)
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    assert worker.claim_next() is None
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["highlight_worker"])
    worker.main()
    assert len(capsys.readouterr().out.splitlines()) == 1
    assert snapshot(HIGHLIGHT_TABLES + RAW_TABLES) == before
    for call in calls.values():
        call.assert_not_called()


@pytest.mark.parametrize("sweep_on", [False, True])
def test_dry_run_reports_rows_and_exact_paths_without_writes(world, monkeypatch, capsys, sweep_on):
    row = ready(world)
    path = row.output_blob_path
    row.revoked_at = now() - timedelta(days=100)
    job = HighlightRenderJob(kind="highlight_delete", blob_path=path)
    db.session.add(job)
    db.session.commit()
    before = snapshot(HIGHLIGHT_TABLES + RAW_TABLES)
    calls = forbid_storage(monkeypatch)
    monkeypatch.setenv("HIGHLIGHT_RETENTION_SWEEP_ENABLED", "1" if sweep_on else "0")
    monkeypatch.setitem(sys.modules, "src.main", SimpleNamespace(app=world["app"]))
    monkeypatch.setattr(sys, "argv", ["highlight_worker", "--dry-run"])
    statements = []

    def record_sql(conn, cursor, statement, params, context, many):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", record_sql)
    try:
        worker.main()
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record_sql)
    assert not any(sql.lstrip().split()[0].upper() in {"DELETE", "UPDATE", "INSERT"} for sql in statements)
    assert not any("FOR UPDATE" in sql.upper() for sql in statements)
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0]["would"]["delete_rows"]["player_highlights"] == [row.id]
    assert output[0]["would"]["queue_cleanup"] == [path]
    assert output[1]["would_delete_blobs"] == [path]
    assert snapshot(HIGHLIGHT_TABLES + RAW_TABLES) == before
    for call in calls.values():
        call.assert_not_called()


@pytest.mark.parametrize("value", ["1", "true", "yes", "ON", " on "])
def test_kill_switch_requires_explicit_enable(monkeypatch, value):
    monkeypatch.setenv("HIGHLIGHT_RETENTION_SWEEP_ENABLED", value)
    assert retention.retention_enabled()


def test_dry_run_models_expiry_without_revoking_live_rows(world, capsys):
    old = now() - timedelta(days=100)
    world["review"].reviewed_at = old
    db.session.commit()
    row = ready(world)
    path = row.output_blob_path
    world["match"].expires_at = old
    job = HighlightRenderJob.query.filter_by(kind="highlight_cut").one()
    job.created_at = job.completed_at = old
    db.session.commit()
    before = snapshot(HIGHLIGHT_TABLES + RAW_TABLES)
    proposal = retention.sweep_highlights(dry_run=True)
    plan = json.loads(capsys.readouterr().out)["would"]
    assert plan["revoke"] == [row.id]
    assert plan["delete_rows"]["highlight_footage_reviews"] == [world["match"].id]
    assert plan["delete_rows"]["highlight_render_jobs"] == [job.id]
    assert plan["queue_cleanup"] == [path]
    assert snapshot(HIGHLIGHT_TABLES + RAW_TABLES) == before
    assert retention.sweep_highlights() == proposal


@pytest.mark.parametrize("seed", range(8))
def test_deleted_blob_set_is_subset_of_recorded_highlight_attempts(world, monkeypatch, seed):
    rng = random.Random(seed)
    original = ready(world)
    assert approve(world, original).status_code == 200
    # Mix retained approved, revoked, private, orphan attempts, successful/failed
    # cuts, plus malicious raw/prefix/derived paths in otherwise valid job rows.
    old = now() - timedelta(days=100)
    for index in range(rng.randint(4, 10)):
        values = {col.name: getattr(original, col.name) for col in PlayerHighlight.__table__.columns}
        hid = uuid4()
        path = f"highlights/{hid}/{uuid4()}.mp4"
        revoked = bool(rng.getrandbits(1))
        values.update(id=hid, pick_key=uuid4(), output_blob_path=path, revoked_at=old if revoked else None)
        clone = PlayerHighlight(**values)
        db.session.add(clone)
        db.session.flush()
        db.session.add(
            HighlightRenderJob(
                highlight_id=hid,
                kind="highlight_cut",
                blob_path=path,
                status=rng.choice(["failed", "succeeded", "cancelled"]),
                created_at=old,
                completed_at=old,
            )
        )
    invalid_paths = {
        world["match"].blob_path,
        "highlights/",
        f"matches/{world['match'].id}/clip.mp4",
        f"highlights/{original.id}/",
        f"highlights/{original.id}/../raw.mp4",
    }
    # An exact-shaped raw alias must still fail the raw-footage veto.
    raw_alias = f"highlights/{uuid4()}/{uuid4()}.mp4"
    db.session.add(VideoMatch(status="created", blob_path=raw_alias, created_at=old))
    invalid_paths.add(raw_alias)
    for path in invalid_paths:
        db.session.add(HighlightRenderJob(kind="highlight_delete", blob_path=path, created_at=old))
        db.session.add(HighlightRenderJob(kind="highlight_cut", blob_path=path, status="failed", created_at=old))
    db.session.commit()
    raw_before = snapshot(RAW_TABLES)
    recorded = {row.output_blob_path for row in PlayerHighlight.query if row.output_blob_path}
    recorded |= {job.blob_path for job in HighlightRenderJob.query if job.blob_path}
    allowed = {path for path in recorded if highlights_storage.is_output_path(path)} - invalid_paths
    removed = []

    def delete(path):
        removed.append(path)
        assert path in allowed and path in recorded
        return True

    monkeypatch.setattr(video_storage, "delete_blob", delete)
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    retention.sweep_highlights()
    # Advance only the highlight cleanup fence, never raw retention.
    for job in HighlightRenderJob.query.filter_by(kind="highlight_delete", status="queued"):
        job.created_at = old
    db.session.commit()
    while claimed := worker.claim_next():
        worker.run_one(*claimed)
    assert set(removed) <= allowed <= recorded
    assert original.output_blob_path not in removed
    assert set(removed).isdisjoint(invalid_paths)
    assert snapshot(RAW_TABLES) == raw_before
    assert removed  # exercise real deletion, rather than proving an empty-set tautology
