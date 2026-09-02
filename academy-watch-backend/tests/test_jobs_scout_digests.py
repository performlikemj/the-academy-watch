"""Scheduled scout digests page safely and preserve an honest dry run."""

import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from src.jobs import run_scout_digests as job
from src.models.follow import FollowList, FollowPlayerSnapshot, PlayerShadow
from src.models.league import Team, UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.routes.api import LazyAPIFootballClient
from src.services import scout_digest_service


@pytest.fixture(autouse=True)
def _default_api_budget(monkeypatch):
    monkeypatch.delenv("SCOUT_DIGEST_API_BUDGET", raising=False)


def test_run_pages_to_exhaustion_and_aggregates(monkeypatch):
    api_client = SimpleNamespace(call_budget=None)
    constructed_with = []

    def client_factory(*, call_budget=None):
        call_budget.claim("status")
        api_client.call_budget = call_budget
        constructed_with.append(call_budget)
        return api_client

    lazy_client = LazyAPIFootballClient(client_factory)
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
    monkeypatch.setattr(job, "_get_api_client", lambda: lazy_client)

    def fake_send_scout_digests(**kwargs):
        calls.append(kwargs)
        return next(pages)

    monkeypatch.setattr(job, "send_scout_digests", fake_send_scout_digests)

    assert job.run() == {
        "users_considered": 3,
        "sent": 2,
        "skipped": 1,
        "errors": 0,
        "dry_run": False,
        "would_send": 2,
        "api_calls_used": 1,
        "api_budget_exhausted": False,
    }
    assert [call["cursor"] for call in calls] == [0, 41]
    assert all(call["limit"] == job.MAX_DIGEST_USERS for call in calls)
    assert all(call["api_client"] is api_client for call in calls)
    assert all(call["dry_run"] is False for call in calls)
    assert all(call["skip_sent_since"] == now - timedelta(hours=144) for call in calls)
    assert all(call["report_job_metrics"] is True for call in calls)
    assert all(call["enrichment_cache"] is calls[0]["enrichment_cache"] for call in calls)
    assert api_client.call_budget.limit == job.DEFAULT_API_BUDGET
    assert constructed_with == [api_client.call_budget]


def test_dry_run_is_forwarded_and_prints_one_json_line(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(job, "_get_api_client", lambda: SimpleNamespace(call_budget=None))

    def fake_send_scout_digests(**kwargs):
        calls.append(kwargs)
        return {"users_processed": 1, "sent": 0, "skipped": 0, "errors": 0, "next_cursor": None}

    monkeypatch.setattr(job, "send_scout_digests", fake_send_scout_digests)

    assert job.main(["--dry-run", "--min-interval-hours", "0"]) == 0
    output_lines = capsys.readouterr().out.splitlines()
    assert len(output_lines) == 1
    assert json.loads(output_lines[0]) == {
        "users_considered": 1,
        "sent": 0,
        "skipped": 0,
        "errors": 0,
        "dry_run": True,
        "would_send": 1,
        "api_calls_used": 0,
        "api_budget_exhausted": False,
    }
    assert calls[0]["dry_run"] is True
    assert calls[0]["skip_sent_since"] is None


def test_service_failure_reports_error_and_nonzero_exit(monkeypatch, capsys, caplog):
    monkeypatch.setattr(job, "_get_api_client", lambda: SimpleNamespace(call_budget=None))
    monkeypatch.setattr(
        job,
        "send_scout_digests",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("page failed")),
    )

    with caplog.at_level(logging.ERROR, logger=job.__name__):
        assert job.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "users_considered": 0,
        "sent": 0,
        "skipped": 0,
        "errors": 1,
        "dry_run": False,
        "would_send": 0,
        "api_calls_used": 0,
        "api_budget_exhausted": False,
    }
    assert "cursor=0" in caplog.text


def test_run_refuses_non_advancing_cursor_and_exits_nonzero(monkeypatch, capsys, caplog):
    calls = []
    monkeypatch.setattr(job, "_get_api_client", lambda: SimpleNamespace(call_budget=None))

    def fake_send_scout_digests(**kwargs):
        calls.append(kwargs)
        return {
            "users_considered": 7,
            "users_processed": 1,
            "sent": 0,
            "skipped": 1,
            "errors": 0,
            "next_cursor": kwargs["cursor"],
        }

    monkeypatch.setattr(job, "send_scout_digests", fake_send_scout_digests)

    with caplog.at_level(logging.WARNING, logger=job.__name__):
        summary = job.run()

    assert [call["cursor"] for call in calls] == [0]
    assert summary["errors"] == 1
    assert "cursor=0" in caplog.text
    assert "users_considered=7" in caplog.text

    monkeypatch.setattr(job, "run", lambda **kwargs: summary)
    assert job.main([]) == 1
    assert json.loads(capsys.readouterr().out)["errors"] == 1


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
            PlayerShadow(player_api_id=101, player_name="Due Prospect"),
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
    assert result["skipped"] == 0
    assert result["previews"][0]["email"] == "due@example.com"
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


def test_run_caps_provider_calls_across_three_pages_and_sends_after_exhaustion(app, monkeypatch):
    team = Team(team_id=9901, name="Budget Academy", country="England", season=2026)
    db.session.add(team)
    db.session.flush()

    users = []
    player_ids = []
    baseline = json.dumps(
        {
            "appearances": 0,
            "goals": 0,
            "assists": 0,
            "minutes_played": 0,
            "status": "academy",
            "absences": 7,
        }
    )
    for index in range(5):
        user = UserAccount(
            email=f"budget-{index}@example.com",
            display_name=f"Budget {index}",
            display_name_lower=f"budget {index}",
        )
        player_api_id = 8000 + index
        users.append(user)
        player_ids.append(player_api_id)
        db.session.add_all(
            (
                user,
                TrackedPlayer(
                    player_api_id=player_api_id,
                    player_name=f"Prospect {index}",
                    team_id=team.id,
                    status="academy",
                    is_active=True,
                ),
            )
        )
        db.session.flush()
        db.session.add(
            ScoutWatchlistEntry(
                user_account_id=user.id,
                player_api_id=player_api_id,
                last_snapshot=baseline,
            )
        )
    db.session.commit()

    class BudgetedInjuryClient:
        def __init__(self):
            self.call_budget = None
            self.provider_calls = []

        def get_player_injuries(self, player_api_id):
            self.call_budget.claim("injuries")
            self.provider_calls.append(player_api_id)
            return [{"player": {"id": player_api_id}}]

    api_client = BudgetedInjuryClient()
    lazy_client = SimpleNamespace(_resolve=lambda: api_client)
    page_calls = []
    real_send_scout_digests = job.send_scout_digests

    def tracked_send_scout_digests(**kwargs):
        page_calls.append(kwargs)
        return real_send_scout_digests(**kwargs)

    deliveries = []
    from src.services.email_service import email_service

    monkeypatch.setenv("SCOUT_DIGEST_API_BUDGET", "2")
    monkeypatch.setattr(job, "MAX_DIGEST_USERS", 2)
    monkeypatch.setattr(job, "_get_api_client", lambda: lazy_client)
    monkeypatch.setattr(job, "send_scout_digests", tracked_send_scout_digests)
    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **kwargs: deliveries.append(kwargs) or SimpleNamespace(success=True),
    )

    result = job.run(min_interval_hours=0)

    assert result == {
        "users_considered": 5,
        "sent": 5,
        "skipped": 0,
        "errors": 0,
        "dry_run": False,
        "would_send": 5,
        "api_calls_used": 2,
        "api_budget_exhausted": True,
    }
    assert len(page_calls) == 3
    assert [call["cursor"] for call in page_calls] == [0, users[1].id, users[3].id]
    assert all(call["api_client"] is api_client for call in page_calls)
    assert all(call["enrichment_cache"] is page_calls[0]["enrichment_cache"] for call in page_calls)
    assert api_client.provider_calls == player_ids[:2]
    assert len(deliveries) == 5

    entries = ScoutWatchlistEntry.query.order_by(ScoutWatchlistEntry.id).all()
    assert [json.loads(entry.last_snapshot)["absences"] for entry in entries[:2]] == [1, 1]
    assert [json.loads(entry.last_snapshot)["absences"] for entry in entries[2:]] == [7, 7, 7]


def test_service_reuses_enrichment_cache_for_a_player_shared_across_pages(app):
    team = Team(team_id=9902, name="Cache Academy", country="England", season=2026)
    player = TrackedPlayer(
        player_api_id=9001,
        player_name="Shared Prospect",
        team=team,
        status="academy",
        is_active=True,
    )
    users = [
        UserAccount(
            email=f"cache-{index}@example.com",
            display_name=f"Cache {index}",
            display_name_lower=f"cache {index}",
        )
        for index in range(2)
    ]
    db.session.add_all((team, player, *users))
    db.session.flush()
    db.session.add_all(
        ScoutWatchlistEntry(user_account_id=user.id, player_api_id=player.player_api_id) for user in users
    )
    db.session.commit()

    provider_calls = []
    api_client = SimpleNamespace(
        call_budget=None,
        get_player_injuries=lambda player_api_id: provider_calls.append(player_api_id) or [],
    )
    enrichment_cache = {}

    first_page = scout_digest_service.send_scout_digests(
        dry_run=True,
        limit=1,
        api_client=api_client,
        enrichment_cache=enrichment_cache,
    )
    second_page = scout_digest_service.send_scout_digests(
        dry_run=True,
        limit=1,
        api_client=api_client,
        cursor=first_page["next_cursor"],
        enrichment_cache=enrichment_cache,
    )

    assert [first_page["previews"][0]["email"], second_page["previews"][0]["email"]] == [
        "cache-0@example.com",
        "cache-1@example.com",
    ]
    assert provider_calls == [player.player_api_id]
