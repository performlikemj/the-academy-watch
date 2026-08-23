"""The video-maintenance job reaps stale analysis jobs and expires raw footage (honest dry-run)."""

from src.jobs import run_video_maintenance as job

SWEPT = {"due": 2, "expired": 2, "failed": 0, "dry_run": False}
DRY = {"due": 2, "expired": 0, "failed": 0, "dry_run": True}


def test_run_reaps_then_expires_and_reports_both(monkeypatch):
    calls = []

    def fake_reap():
        calls.append("reap")
        return 3

    def fake_expire(now=None, *, dry_run=False):
        calls.append("expire" if not dry_run else "expire-dry")
        return DRY if dry_run else SWEPT

    monkeypatch.setattr(job.video_queue, "reap_stale_jobs", fake_reap)
    monkeypatch.setattr(job.video_retention, "expire_raw_footage", fake_expire)
    assert job.run() == {"stale_failed": 3, "retention": SWEPT, "dry_run": False}
    assert calls == ["reap", "expire"]


def test_dry_run_changes_nothing_but_reports_due_count(monkeypatch):
    def explode():
        raise AssertionError("dry run must not reap")

    def fake_expire(now=None, *, dry_run=False):
        assert dry_run is True
        return DRY

    monkeypatch.setattr(job.video_queue, "reap_stale_jobs", explode)
    monkeypatch.setattr(job.video_retention, "expire_raw_footage", fake_expire)
    assert job.run(dry_run=True) == {
        "stale_failed": 0,
        "retention": DRY,
        "dry_run": True,
    }
