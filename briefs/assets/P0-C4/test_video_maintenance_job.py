"""The video-maintenance job reaps stale analysis jobs (and reports honestly in dry-run)."""

from src.jobs import run_video_maintenance as job


def test_run_reaps_stale_jobs_and_reports_count(monkeypatch):
    calls = []

    def fake_reap():
        calls.append("reap")
        return 3

    monkeypatch.setattr(job.video_queue, "reap_stale_jobs", fake_reap)
    assert job.run() == {"stale_failed": 3, "dry_run": False}
    assert calls == ["reap"]


def test_dry_run_changes_nothing(monkeypatch):
    def explode():
        raise AssertionError("dry run must not reap")

    monkeypatch.setattr(job.video_queue, "reap_stale_jobs", explode)
    assert job.run(dry_run=True) == {"stale_failed": 0, "dry_run": True}
