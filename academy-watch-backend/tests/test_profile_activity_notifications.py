"""Weekly profile-activity notifications stay private, gated, and resumable."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from src.jobs import run_profile_activity_notifications as job
from src.models.follow import PlayerShadow
from src.models.league import UserAccount, db
from src.models.player_fan import PlayerFan
from src.models.player_suppression import PlayerSuppression
from src.models.product_event import ProductEvent
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.user_block import UserBlock
from src.services import profile_activity_notification_service as notification_service
from src.services.email_service import EmailResult, email_service


@pytest.fixture(autouse=True)
def _profile_activity_env(monkeypatch):
    monkeypatch.delenv("PROFILE_ACTIVITY_DRY_RUN", raising=False)
    monkeypatch.delenv("PROFILE_ACTIVITY_MAX_SENDS", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")


def _account(
    email: str | None,
    *,
    name: str,
    opt_in: bool = False,
    tombstone: bool = False,
    watermark: datetime | None = None,
) -> UserAccount:
    account = UserAccount(
        email=email,
        display_name=name,
        display_name_lower=name.lower(),
        is_tombstone=tombstone,
        profile_activity_email_opt_in=opt_in,
        profile_activity_email_last_sent_at=watermark,
    )
    db.session.add(account)
    db.session.flush()
    return account


def _positive_subject(owner: UserAccount, player_api_id: int, *, name: str) -> PlayerShadow:
    subject = PlayerShadow(
        player_api_id=player_api_id,
        player_name=name,
        birth_date=date(1990, 1, 1),
        is_active=True,
    )
    db.session.add(subject)
    db.session.flush()
    db.session.add(
        PlayerProfileClaim(
            user_account_id=owner.id,
            player_api_id=player_api_id,
            relationship_type="player",
            status="approved",
        )
    )
    db.session.flush()
    return subject


def _local_subject(owner: UserAccount, *, name: str) -> LocalPlayer:
    subject = LocalPlayer(
        display_name=name,
        normalized_name=LocalPlayer.normalize_name(name),
        birth_date=date(1990, 1, 1),
        birth_year=1990,
        status="approved",
    )
    db.session.add(subject)
    db.session.flush()
    subject.api_player_id = -subject.id
    db.session.add(
        PlayerProfileClaim(
            user_account_id=owner.id,
            local_player_id=subject.id,
            relationship_type="player",
            status="approved",
        )
    )
    db.session.flush()
    return subject


def _profile_views(player_api_id: int, *created_at: datetime) -> None:
    db.session.add_all(
        ProductEvent(
            event_name="profile_view",
            user_email=None,
            session_id=None,
            path=None,
            referrer=None,
            props={"player_api_id": player_api_id},
            created_at=timestamp,
        )
        for timestamp in created_at
    )


def _successful_deliveries(monkeypatch):
    deliveries = []

    def send(**kwargs):
        deliveries.append(kwargs)
        return EmailResult(success=True, provider="test")

    monkeypatch.setattr(email_service, "send_email", send)
    return deliveries


def test_opted_out_tombstone_and_missing_email_accounts_are_not_considered(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    opted_out = _account("opted-out@example.com", name="Opted Out")
    tombstone = _account("deleted@example.com", name="Deleted", opt_in=True, tombstone=True)
    no_email = _account(None, name="No Email", opt_in=True)
    for offset, account in enumerate((opted_out, tombstone, no_email), start=1):
        subject = _positive_subject(account, 20_000 + offset, name=f"Hidden {offset}")
        _profile_views(subject.player_api_id, now - timedelta(hours=1))
    db.session.commit()

    deliveries = _successful_deliveries(monkeypatch)
    result = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert result["users_considered"] == 0
    assert result["sent"] == 0
    assert deliveries == []


def test_account_that_opts_out_after_page_selection_is_not_emailed(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owner = _account("late-opt-out@example.com", name="Late Opt Out", opt_in=True)
    subject = _positive_subject(owner, 20_050, name="Consent Player")
    _profile_views(subject.player_api_id, now - timedelta(hours=1))
    db.session.commit()
    owner_id = owner.id
    real_get = db.session.get

    def opt_out_on_reload(model, ident, *args, **kwargs):
        account = real_get(model, ident, *args, **kwargs)
        if model is UserAccount and ident == owner_id:
            account.profile_activity_email_opt_in = False
        return account

    monkeypatch.setattr(db.session, "get", opt_out_on_reload)
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert result["users_considered"] == 1
    assert result["sent"] == 0
    assert deliveries == []


def test_opted_in_account_without_public_subjects_is_skipped(app, monkeypatch):
    watermark = datetime(2026, 8, 25, 9)
    owner = _account(
        "no-subjects@example.com",
        name="No Subjects",
        opt_in=True,
        watermark=watermark,
    )
    db.session.commit()
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(
        dry_run=False,
        now=datetime(2026, 9, 2, 12),
    )

    assert result["users_considered"] == 1
    assert result["skipped_no_subjects"] == 1
    assert result["skipped_no_activity"] == 0
    assert db.session.get(UserAccount, owner.id).profile_activity_email_last_sent_at == watermark
    assert deliveries == []


def test_zero_activity_does_not_advance_the_watermark(app, monkeypatch):
    watermark = datetime(2026, 8, 25, 9)
    owner = _account(
        "quiet-owner@example.com",
        name="Quiet Owner",
        opt_in=True,
        watermark=watermark,
    )
    _positive_subject(owner, 20_101, name="Quiet Player")
    db.session.commit()
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(
        dry_run=False,
        now=datetime(2026, 9, 2, 12),
    )

    assert result["skipped_no_activity"] == 1
    assert result["sent"] == 0
    assert db.session.get(UserAccount, owner.id).profile_activity_email_last_sent_at == watermark
    assert deliveries == []


def test_watermark_is_set_only_after_successful_send_and_immediate_rerun_is_quiet(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owner = _account("activity-owner@example.com", name="Activity Owner", opt_in=True)
    follower = _account("private-follower@example.com", name="Private Follower")
    subject = _positive_subject(owner, 20_201, name="Public Player")
    db.session.add_all(
        (
            PlayerFan(
                user_account_id=follower.id,
                player_api_id=subject.player_api_id,
                created_at=now - timedelta(days=1),
            ),
            ScoutWatchlistEntry(
                user_account_id=follower.id,
                player_api_id=subject.player_api_id,
                created_at=now - timedelta(hours=20),
            ),
        )
    )
    _profile_views(
        subject.player_api_id,
        now - timedelta(hours=3),
        now - timedelta(hours=2),
    )
    db.session.commit()
    owner_id = owner.id
    owner_email = owner.email
    private_identities = (follower.email, follower.display_name)

    deliveries = []

    def assert_watermark_then_send(**kwargs):
        assert db.session.get(UserAccount, owner_id).profile_activity_email_last_sent_at is None
        deliveries.append(kwargs)
        return EmailResult(success=True, provider="test")

    monkeypatch.setattr(email_service, "send_email", assert_watermark_then_send)
    first = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert first["sent"] == 1
    assert first["errors"] == 0
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["to"] == owner_email
    assert delivery["subject"] == "Your Academy Watch activity: 1 new fans, 1 watchlist adds, 2 profile views"
    assert delivery["tags"] == ["profile-activity"]
    assert "Public Player" in delivery["html"]
    assert "https://example.com/players/20201" in delivery["html"]
    assert "Turn this off in Account → Email preferences" in delivery["html"]
    assert (
        "Public Player\n- 1 new fans\n- 1 watchlist adds\n- 2 profile views\nhttps://example.com/players/20201"
    ) in delivery["text"]
    assert "Turn this off in Account → Email preferences" in delivery["text"]
    assert "scouts" not in delivery["html"].lower()
    assert "scouts" not in delivery["text"].lower()
    for private_identity in private_identities:
        assert private_identity not in delivery["html"]
        assert private_identity not in delivery["text"]

    db.session.remove()
    assert db.session.get(UserAccount, owner_id).profile_activity_email_last_sent_at == now

    deliveries.clear()
    second = notification_service.send_profile_activity_notifications(dry_run=False, now=now + timedelta(minutes=1))
    assert second["sent"] == 0
    assert second["skipped_no_activity"] == 1
    assert db.session.get(UserAccount, owner_id).profile_activity_email_last_sent_at == now
    assert deliveries == []


def test_eight_to_thirty_day_watermark_uses_the_full_window(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owner = _account(
        "older-watermark@example.com",
        name="Older Watermark",
        opt_in=True,
        watermark=now - timedelta(days=20),
    )
    subject = _positive_subject(owner, 20_301, name="Window Player")
    _profile_views(subject.player_api_id, now - timedelta(days=15))
    db.session.commit()
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert result["sent"] == 1
    assert deliveries[0]["subject"] == "Your Academy Watch activity: 0 new fans, 0 watchlist adds, 1 profile views"


def test_activity_window_is_clamped_to_thirty_days(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owner = _account(
        "clamped-window@example.com",
        name="Clamped Window",
        opt_in=True,
        watermark=now - timedelta(days=60),
    )
    subject = _positive_subject(owner, 20_302, name="Clamped Player")
    _profile_views(
        subject.player_api_id,
        now - timedelta(days=31),
        now - timedelta(days=29),
    )
    db.session.commit()
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert result["sent"] == 1
    assert deliveries[0]["subject"] == "Your Academy Watch activity: 0 new fans, 0 watchlist adds, 1 profile views"


def test_provider_failure_keeps_watermark_and_makes_runner_exit_one(app, monkeypatch, capsys):
    now = datetime(2026, 9, 2, 12)
    watermark = now - timedelta(days=8)
    owner = _account(
        "provider-failure@example.com",
        name="Provider Failure",
        opt_in=True,
        watermark=watermark,
    )
    subject = _positive_subject(owner, 20_401, name="Failure Player")
    _profile_views(subject.player_api_id, now - timedelta(days=1))
    db.session.commit()
    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **_kwargs: EmailResult(success=False, provider="test", error="provider rejected"),
    )

    summary = job.run(dry_run=False, max_sends=10, now=now)

    assert summary["errors"] == 1
    assert summary["sent"] == 0
    assert db.session.get(UserAccount, owner.id).profile_activity_email_last_sent_at == watermark
    monkeypatch.setattr(job, "run", lambda **_kwargs: summary)
    assert job.main([]) == 1
    assert json.loads(capsys.readouterr().out)["errors"] == 1


def test_dry_run_masks_recipient_without_sending_or_mutating(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owner = _account("preview-owner@example.com", name="Preview Owner", opt_in=True)
    subject = _positive_subject(owner, 20_501, name="Preview Player")
    _profile_views(subject.player_api_id, now - timedelta(hours=1))
    db.session.commit()

    def unexpected_send(**_kwargs):
        raise AssertionError("dry-run attempted delivery")

    monkeypatch.setattr(email_service, "send_email", unexpected_send)
    result = notification_service.send_profile_activity_notifications(dry_run=True, now=now)

    assert result["sent"] == 0
    assert result["errors"] == 0
    assert result["previews"] == [
        {
            "email": "p***@example.com",
            "subject": "Your Academy Watch activity: 0 new fans, 0 watchlist adds, 1 profile views",
            "subjects": [
                {
                    "player_api_id": subject.player_api_id,
                    "display_name": "Preview Player",
                    "new_fans": 0,
                    "watchlist_adds": 0,
                    "profile_views": 1,
                    "url": f"https://example.com/players/{subject.player_api_id}",
                }
            ],
        }
    ]
    assert db.session.get(UserAccount, owner.id).profile_activity_email_last_sent_at is None


def test_cursor_paging_with_limit_one_visits_each_account_once(app, monkeypatch):
    accounts = [_account(f"page-{index}@example.com", name=f"Page {index}", opt_in=True) for index in range(3)]
    db.session.commit()
    visited = []
    real_owned_subjects = notification_service.owned_public_adult_subjects

    def tracked_owned_subjects(account_id):
        visited.append(account_id)
        return real_owned_subjects(account_id)

    monkeypatch.setattr(notification_service, "owned_public_adult_subjects", tracked_owned_subjects)
    cursor = None
    for _page_number in range(len(accounts) + 1):
        page = notification_service.send_profile_activity_notifications(
            dry_run=True,
            cursor=cursor,
            limit=1,
            now=datetime(2026, 9, 2, 12),
        )
        cursor = page["next_cursor"]
        if cursor is None:
            break
    else:
        pytest.fail("cursor paging did not terminate")

    assert visited == [account.id for account in accounts]


def test_max_sends_is_respected_across_pages(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owners = []
    for index in range(3):
        owner = _account(f"budget-{index}@example.com", name=f"Budget {index}", opt_in=True)
        subject = _positive_subject(owner, 20_600 + index, name=f"Budget Player {index}")
        _profile_views(subject.player_api_id, now - timedelta(hours=1))
        owners.append(owner)
    db.session.commit()
    deliveries = _successful_deliveries(monkeypatch)
    real_service = job.send_profile_activity_notifications
    remaining_budgets = []

    def tracked_service(**kwargs):
        remaining_budgets.append(kwargs["max_sends"])
        return real_service(**kwargs)

    monkeypatch.setattr(job, "MAX_PROFILE_ACTIVITY_USERS", 1)
    monkeypatch.setattr(job, "send_profile_activity_notifications", tracked_service)
    summary = job.run(dry_run=False, max_sends=2, now=now)

    assert summary == {
        "dry_run": False,
        "users_considered": 2,
        "sent": 2,
        "skipped_no_activity": 0,
        "skipped_no_subjects": 0,
        "errors": 0,
        "pages": 2,
        "budget_exhausted": True,
    }
    assert remaining_budgets == [2, 1]
    assert len(deliveries) == 2
    assert db.session.get(UserAccount, owners[2].id).profile_activity_email_last_sent_at is None


def test_failed_send_attempt_consumes_the_whole_run_budget(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    for index in range(2):
        owner = _account(f"failed-budget-{index}@example.com", name=f"Failed Budget {index}", opt_in=True)
        subject = _positive_subject(owner, 20_650 + index, name=f"Failed Budget Player {index}")
        _profile_views(subject.player_api_id, now - timedelta(hours=1))
    db.session.commit()
    attempts = []

    def fail_send(**kwargs):
        attempts.append(kwargs)
        return EmailResult(success=False, provider="test", error="provider rejected")

    monkeypatch.setattr(email_service, "send_email", fail_send)
    summary = job.run(dry_run=False, max_sends=1, now=now)

    assert summary["users_considered"] == 1
    assert summary["sent"] == 0
    assert summary["errors"] == 1
    assert summary["budget_exhausted"] is True
    assert len(attempts) == 1


def test_dry_run_previews_consume_budget_across_pages(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    for index in range(3):
        owner = _account(f"preview-budget-{index}@example.com", name=f"Preview Budget {index}", opt_in=True)
        subject = _positive_subject(owner, 20_680 + index, name=f"Preview Budget Player {index}")
        _profile_views(subject.player_api_id, now - timedelta(hours=1))
    db.session.commit()
    real_service = job.send_profile_activity_notifications
    remaining_budgets = []

    def tracked_service(**kwargs):
        remaining_budgets.append(kwargs["max_sends"])
        return real_service(**kwargs)

    monkeypatch.setattr(job, "MAX_PROFILE_ACTIVITY_USERS", 1)
    monkeypatch.setattr(job, "send_profile_activity_notifications", tracked_service)
    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("dry-run attempted delivery")),
    )

    summary = job.run(dry_run=True, max_sends=2, now=now)

    assert summary == {
        "dry_run": True,
        "users_considered": 2,
        "sent": 0,
        "skipped_no_activity": 0,
        "skipped_no_subjects": 0,
        "errors": 0,
        "pages": 2,
        "budget_exhausted": True,
    }
    assert remaining_budgets == [2, 1]


@pytest.mark.parametrize("unsafe_state", ["minor", "suppressed"])
def test_subject_that_became_unsafe_is_omitted_despite_historical_activity(app, monkeypatch, unsafe_state):
    now = datetime(2026, 9, 2, 12)
    watermark = now - timedelta(days=2)
    owner = _account(
        f"unsafe-{unsafe_state}@example.com",
        name=f"Unsafe {unsafe_state}",
        opt_in=True,
        watermark=watermark,
    )
    safe = _positive_subject(owner, 20_701, name="Still Public")
    unsafe = _positive_subject(owner, 20_702, name="Must Stay Hidden")
    _profile_views(unsafe.player_api_id, now - timedelta(days=1))
    db.session.commit()

    if unsafe_state == "minor":
        unsafe.birth_date = date(2012, 1, 1)
    else:
        db.session.add(
            PlayerSuppression(
                player_api_id=unsafe.player_api_id,
                reason_code="player_request",
                requester_role="player",
                requester_contact="requester@example.com",
                request_statement="Please remove this profile.",
                status="active",
            )
        )
    db.session.commit()
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert safe.player_api_id != unsafe.player_api_id
    assert result["skipped_no_activity"] == 1
    assert result["sent"] == 0
    assert db.session.get(UserAccount, owner.id).profile_activity_email_last_sent_at == watermark
    assert deliveries == []


def test_two_public_subjects_share_one_email_and_use_canonical_paths(app, monkeypatch):
    now = datetime(2026, 9, 2, 12)
    owner = _account("two-subjects@example.com", name="Two Subjects", opt_in=True)
    positive = _positive_subject(owner, 20_801, name="API Player")
    local = _local_subject(owner, name="Local <Star>")
    _profile_views(
        positive.player_api_id,
        now - timedelta(hours=2),
    )
    _profile_views(
        local.api_player_id,
        now - timedelta(hours=1),
        now - timedelta(minutes=30),
    )
    db.session.commit()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://theacademywatch.test/")
    deliveries = _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(dry_run=False, now=now)

    assert result["sent"] == 1
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["subject"] == "Your Academy Watch activity: 0 new fans, 0 watchlist adds, 3 profile views"
    assert f"https://theacademywatch.test/players/{positive.player_api_id}" in delivery["html"]
    assert f"https://theacademywatch.test/local-players/{local.id}" in delivery["html"]
    assert "Local &lt;Star&gt;" in delivery["html"]
    assert "Local <Star>" not in delivery["html"]
    local_start = delivery["html"].index("Local &lt;Star&gt;")
    positive_start = delivery["html"].index("API Player")
    local_html = delivery["html"][local_start:positive_start]
    positive_html = delivery["html"][positive_start:]
    assert re.search(r"Profile views</td>\s*<td[^>]*>1</td>", positive_html)
    assert re.search(r"Profile views</td>\s*<td[^>]*>2</td>", local_html)
    assert (
        f"API Player\n- 0 new fans\n- 0 watchlist adds\n- 1 profile views\n"
        f"https://theacademywatch.test/players/{positive.player_api_id}"
    ) in delivery["text"]
    assert (
        f"Local <Star>\n- 0 new fans\n- 0 watchlist adds\n- 2 profile views\n"
        f"https://theacademywatch.test/local-players/{local.id}"
    ) in delivery["text"]


def test_blocked_accounts_and_owner_rows_do_not_count_as_fans_or_watchlists(app):
    now = datetime(2026, 9, 2, 12)
    owner = _account("exclusion-owner@example.com", name="Exclusion Owner", opt_in=True)
    blocked = _account("blocked-actor@example.com", name="Blocked Actor")
    visible = _account("visible-actor@example.com", name="Visible Actor")
    subject = _positive_subject(owner, 20_901, name="Excluded Counts")
    db.session.add(UserBlock(blocker_user_id=owner.id, blocked_user_id=blocked.id))
    db.session.add_all(
        (
            PlayerFan(
                user_account_id=blocked.id, player_api_id=subject.player_api_id, created_at=now - timedelta(days=1)
            ),
            PlayerFan(
                user_account_id=owner.id, player_api_id=subject.player_api_id, created_at=now - timedelta(days=1)
            ),
            PlayerFan(
                user_account_id=visible.id,
                player_api_id=subject.player_api_id,
                created_at=now - timedelta(days=1),
            ),
            ScoutWatchlistEntry(
                user_account_id=blocked.id,
                player_api_id=subject.player_api_id,
                created_at=now - timedelta(days=1),
            ),
            ScoutWatchlistEntry(
                user_account_id=owner.id,
                player_api_id=subject.player_api_id,
                created_at=now - timedelta(days=1),
            ),
            ScoutWatchlistEntry(
                user_account_id=visible.id,
                player_api_id=subject.player_api_id,
                created_at=now - timedelta(days=1),
            ),
        )
    )
    _profile_views(subject.player_api_id, now - timedelta(hours=1))
    db.session.commit()

    result = notification_service.send_profile_activity_notifications(dry_run=True, now=now)

    counts = result["previews"][0]["subjects"][0]
    assert counts["new_fans"] == 1
    assert counts["watchlist_adds"] == 1
    assert counts["profile_views"] == 1


def test_reloaded_naive_watermark_accepts_aware_now_and_stores_naive_utc(app, monkeypatch):
    watermark = datetime(2026, 8, 20, 0)
    aware_now = datetime(2026, 9, 2, 9, tzinfo=timezone(timedelta(hours=9)))
    owner = _account(
        "aware-now@example.com",
        name="Aware Now",
        opt_in=True,
        watermark=watermark,
    )
    subject = _positive_subject(owner, 21_001, name="Timezone Player")
    _profile_views(subject.player_api_id, datetime(2026, 8, 25, 0))
    db.session.commit()
    owner_id = owner.id
    db.session.expire_all()
    assert db.session.get(UserAccount, owner_id).profile_activity_email_last_sent_at.tzinfo is None
    _successful_deliveries(monkeypatch)

    result = notification_service.send_profile_activity_notifications(dry_run=False, now=aware_now)

    assert result["sent"] == 1
    stored = db.session.get(UserAccount, owner_id).profile_activity_email_last_sent_at
    assert stored == datetime(2026, 9, 2, 0)
    assert stored.tzinfo is None


def test_runner_rejects_a_non_advancing_cursor(monkeypatch, caplog):
    monkeypatch.setattr(
        job,
        "send_profile_activity_notifications",
        lambda **_kwargs: {
            "users_considered": 1,
            "sent": 0,
            "skipped_no_activity": 1,
            "skipped_no_subjects": 0,
            "errors": 0,
            "previews": [],
            "budget_exhausted": False,
            "next_cursor": 0,
        },
    )

    summary = job.run(max_sends=1)

    assert summary["errors"] == 1
    assert summary["pages"] == 1
    assert "non-advancing cursor" in caplog.text


def _empty_job_summary(dry_run: bool) -> dict:
    return {
        "dry_run": dry_run,
        "users_considered": 0,
        "sent": 0,
        "skipped_no_activity": 0,
        "skipped_no_subjects": 0,
        "errors": 0,
        "pages": 0,
        "budget_exhausted": False,
    }


def test_runner_main_forwards_live_default_cli_dry_run_and_max_sends(monkeypatch, capsys):
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return _empty_job_summary(kwargs["dry_run"])

    monkeypatch.setattr(job, "run", fake_run)
    monkeypatch.setenv("PROFILE_ACTIVITY_MAX_SENDS", "17")

    assert job.main([]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False
    assert calls[-1] == {"dry_run": False, "max_sends": 17}

    assert job.main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert calls[-1] == {"dry_run": True, "max_sends": 17}


@pytest.mark.parametrize("env_value", ["1", "true", "yes", "on", " TRUE "])
def test_runner_dry_run_environment_values_are_honored(monkeypatch, capsys, env_value):
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return _empty_job_summary(kwargs["dry_run"])

    monkeypatch.setattr(job, "run", fake_run)
    monkeypatch.setenv("PROFILE_ACTIVITY_DRY_RUN", env_value)

    assert job.main([]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert calls == [{"dry_run": True, "max_sends": job.DEFAULT_MAX_SENDS}]


@pytest.mark.parametrize(
    "command",
    (
        ("-m", "src.jobs.run_profile_activity_notifications"),
        ("src/jobs/run_profile_activity_notifications.py",),
    ),
)
def test_runner_smoke_supports_module_and_direct_script_execution(command):
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(backend_dir),
            "PROFILE_ACTIVITY_DRY_RUN": "1",
            "PROFILE_ACTIVITY_MAX_SENDS": "0",
            "SKIP_API_HANDSHAKE": "1",
            "API_USE_STUB_DATA": "true",
        }
    )

    completed = subprocess.run(
        (sys.executable, *command),
        cwd=backend_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "dry_run": True,
        "users_considered": 0,
        "sent": 0,
        "skipped_no_activity": 0,
        "skipped_no_subjects": 0,
        "errors": 0,
        "pages": 0,
        "budget_exhausted": True,
    }
