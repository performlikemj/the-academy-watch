"""Scheduled scout digests page safely and preserve an honest dry run."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.jobs import run_scout_digests as job
from src.models.follow import FollowList, FollowPlayerSnapshot
from src.models.league import UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.services import scout_digest_service


def test_run_pages_to_exhaustion_and_aggregates(monkeypatch):
    api_client = object()
    now = datetime(2026, 9, 2, 7, 0, tzinfo=UTC)
    calls = []
    pages = iter(
        [
            {
                "users_considered": 200,
                "users_processed": 2,
                "sent": 1,
                "skipped": 1,
                "errors": 0,
                "next_cursor": 41,
            },
            {
                "users_considered": 1,
                "users_processed": 1,
                "sent": 1,
                "skipped": 0,
                "errors": 0,
                "next_cursor": None,
            },
        ]
    )

    monkeypatch.setattr(job, "_utcnow", lambda: now)
    monkeypatch.setattr(job, "_get_api_client", lambda: api_client)

    def fake_send_scout_digests(**kwargs):
        calls.append(kwargs)
        return next(pages)

    monkeypatch.setattr(job, "send_scout_digests", fake_send_scout_digests)

    assert job.run() == {"users_considered": 3, "sent": 2, "skipped": 1, "errors": 0}
    assert [call["cursor"] for call in calls] == [0, 41]
    assert all(call["limit"] == job.MAX_DIGEST_USERS for call in calls)
    assert all(call["api_client"] is api_client for call in calls)
    assert all(call["dry_run"] is False for call in calls)
    assert all(call["skip_sent_since"] == now - timedelta(hours=144) for call in calls)
    assert all(call["report_job_metrics"] is True for call in calls)


def test_dry_run_is_forwarded_and_prints_one_json_line(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(job, "_get_api_client", lambda: object())

    def fake_send_scout_digests(**kwargs):
        calls.append(kwargs)
        return {"users_processed": 1, "sent": 0, "skipped": 0, "errors": 0, "next_cursor": None}

    monkeypatch.setattr(job, "send_scout_digests", fake_send_scout_digests)

    assert job.main(["--dry-run", "--min-interval-hours", "0"]) == 0
    output_lines = capsys.readouterr().out.splitlines()
    assert len(output_lines) == 1
    assert json.loads(output_lines[0]) == {"users_considered": 1, "sent": 0, "skipped": 0, "errors": 0}
    assert calls[0]["dry_run"] is True
    assert calls[0]["skip_sent_since"] is None


def test_service_failure_reports_error_and_nonzero_exit(monkeypatch, capsys):
    monkeypatch.setattr(job, "_get_api_client", lambda: object())
    monkeypatch.setattr(
        job,
        "send_scout_digests",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("page failed")),
    )

    assert job.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "users_considered": 0,
        "sent": 0,
        "skipped": 0,
        "errors": 1,
    }


def test_interval_guard_uses_watchlist_and_follow_send_markers(app):
    cutoff = datetime(2026, 9, 1, tzinfo=UTC)
    due = UserAccount(email="due@example.com", display_name="Due", display_name_lower="due")
    recent_watchlist = UserAccount(
        email="recent-watch@example.com",
        display_name="Recent Watch",
        display_name_lower="recent watch",
    )
    recent_follow = UserAccount(
        email="recent-follow@example.com",
        display_name="Recent Follow",
        display_name_lower="recent follow",
    )
    db.session.add_all((due, recent_watchlist, recent_follow))
    db.session.flush()
    db.session.add_all(
        (
            ScoutWatchlistEntry(
                user_account_id=due.id,
                player_api_id=101,
                last_digest_at=cutoff - timedelta(hours=1),
            ),
            ScoutWatchlistEntry(
                user_account_id=recent_watchlist.id,
                player_api_id=102,
                last_digest_at=cutoff + timedelta(hours=1),
            ),
            FollowList(user_account_id=recent_follow.id, name="Prospects"),
            FollowPlayerSnapshot(
                user_account_id=recent_follow.id,
                player_api_id=103,
                last_digest_at=cutoff + timedelta(hours=1),
            ),
        )
    )
    db.session.commit()

    result = scout_digest_service.send_scout_digests(
        dry_run=True,
        api_client=object(),
        skip_sent_since=cutoff,
        report_job_metrics=True,
    )

    assert result["users_considered"] == 1
    assert result["users_processed"] == 1
    assert result["skipped"] == 1
    assert result["next_cursor"] is None


def test_provider_failure_is_reported_as_a_job_error(app, monkeypatch):
    user = UserAccount(email="failure@example.com", display_name="Failure", display_name_lower="failure")
    db.session.add(user)
    db.session.flush()
    db.session.add(ScoutWatchlistEntry(user_account_id=user.id, player_api_id=201))
    db.session.commit()

    monkeypatch.setattr(
        scout_digest_service,
        "_assemble_user_updates",
        lambda *args, **kwargs: ([], [], []),
    )
    monkeypatch.setattr(
        scout_digest_service,
        "_render_digest",
        lambda *args, **kwargs: {"subject": "Digest", "players": 1, "html": "<p>Digest</p>", "text": "Digest"},
    )
    from src.services.email_service import email_service

    monkeypatch.setattr(email_service, "send_email", lambda **kwargs: SimpleNamespace(success=False))

    result = scout_digest_service.send_scout_digests(
        dry_run=False,
        api_client=object(),
        report_job_metrics=True,
    )

    assert result["users_processed"] == 1
    assert result["sent"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == 1
