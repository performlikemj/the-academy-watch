"""Weekly, opt-in aggregate profile-activity email notifications."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from flask import render_template
from src.models.league import UserAccount, db
from src.services.public_player_subject import owned_public_adult_subjects
from src.services.reach_metrics import fan_counts, profile_view_counts_since, watchlist_counts
from src.services.user_blocks import blocked_user_ids

logger = logging.getLogger(__name__)

MAX_PROFILE_ACTIVITY_USERS = 200
DEFAULT_MAX_SENDS = 500
_DEFAULT_PUBLIC_BASE_URL = "https://theacademywatch.com"


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _run_now(now: datetime | None) -> datetime:
    return _naive_utc(now or datetime.now(UTC))


def _page_limit(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = MAX_PROFILE_ACTIVITY_USERS
    return min(max(parsed, 1), MAX_PROFILE_ACTIVITY_USERS)


def _cursor(value) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return max(parsed, 0)


def _send_budget(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_SENDS
    return max(parsed, 0)


def _public_base_url() -> str:
    base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    return base or _DEFAULT_PUBLIC_BASE_URL


def _subject_url(subject) -> str:
    if subject.is_local:
        return f"{_public_base_url()}/local-players/{subject.local_player_id}"
    return f"{_public_base_url()}/players/{subject.signed_id}"


def _plain_text(subjects: list[dict], *, new_fans: int, watchlist_adds: int, profile_views: int) -> str:
    lines = [
        "THE ACADEMY WATCH",
        "",
        "Your weekly profile activity",
        "",
        f"{new_fans} new fans, {watchlist_adds} watchlist adds, {profile_views} profile views",
        "",
    ]
    for subject in subjects:
        lines.extend(
            (
                subject["display_name"],
                f"- {subject['new_fans']} new fans",
                f"- {subject['watchlist_adds']} watchlist adds",
                f"- {subject['profile_views']} profile views",
                subject["url"],
                "",
            )
        )
    lines.append("Turn this off in Account → Email preferences")
    return "\n".join(lines)


def _activity_for_subjects(subjects, *, since: datetime, now: datetime, exclude_user_ids) -> list[dict]:
    signed_ids = [subject.signed_id for subject in subjects]
    fans = fan_counts(signed_ids, since=since, exclude_user_ids=exclude_user_ids)
    watchlists = watchlist_counts(signed_ids, since=since, exclude_user_ids=exclude_user_ids)
    views = profile_view_counts_since(signed_ids, since=since, now=now)
    return [
        {
            "player_api_id": subject.signed_id,
            "display_name": subject.display_name or "Player profile",
            "new_fans": fans.get(subject.signed_id, (0, 0))[1],
            "watchlist_adds": watchlists.get(subject.signed_id, (0, 0))[1],
            "profile_views": views.get(subject.signed_id, 0),
            "url": _subject_url(subject),
        }
        for subject in subjects
    ]


def send_profile_activity_notifications(
    *,
    dry_run: bool,
    cursor: int | None = None,
    limit: int = MAX_PROFILE_ACTIVITY_USERS,
    max_sends: int = DEFAULT_MAX_SENDS,
    now=None,
) -> dict:
    """Process one id-cursor page of opted-in profile owners.

    ``max_sends`` is the caller's remaining whole-run allowance. A send
    attempt consumes one unit, as does one preview in dry-run mode. The
    account watermark advances only after the email provider reports success.
    """

    from src.services.email_service import email_service

    page_limit = _page_limit(limit)
    cursor_value = _cursor(cursor)
    remaining = _send_budget(max_sends)
    result = {
        "users_considered": 0,
        "sent": 0,
        "skipped_no_activity": 0,
        "skipped_no_subjects": 0,
        "errors": 0,
        "previews": [],
        "next_cursor": None,
        "budget_exhausted": False,
    }
    if remaining == 0:
        result["next_cursor"] = cursor_value
        result["budget_exhausted"] = True
        return result

    run_now = _run_now(now)
    candidate_ids = [
        row[0]
        for row in db.session.query(UserAccount.id)
        .filter(
            UserAccount.id > cursor_value,
            UserAccount.profile_activity_email_opt_in.is_(True),
            UserAccount.is_tombstone.is_(False),
            UserAccount.email.isnot(None),
            UserAccount.email != "",
        )
        .order_by(UserAccount.id.asc())
        .limit(page_limit + 1)
        .all()
    ]
    has_more = len(candidate_ids) > page_limit
    account_ids = candidate_ids[:page_limit]
    last_processed = cursor_value

    for account_id in account_ids:
        result["users_considered"] += 1
        account = db.session.get(UserAccount, account_id)
        if account is None or not account.email or not account.profile_activity_email_opt_in or account.is_tombstone:
            # Consent or account state changed after the cursor page was read.
            last_processed = account_id
            continue

        subjects = owned_public_adult_subjects(account_id)
        if not subjects:
            result["skipped_no_subjects"] += 1
            last_processed = account_id
            continue

        fallback_since = run_now - timedelta(days=7)
        watermark = account.profile_activity_email_last_sent_at
        since = _naive_utc(watermark) if watermark is not None else fallback_since
        since = max(since, run_now - timedelta(days=30))
        hidden_user_ids = blocked_user_ids(blocker_user_id=account_id)
        activity = _activity_for_subjects(
            subjects,
            since=since,
            now=run_now,
            exclude_user_ids=hidden_user_ids,
        )

        total_fans = sum(subject["new_fans"] for subject in activity)
        total_watchlists = sum(subject["watchlist_adds"] for subject in activity)
        total_views = sum(subject["profile_views"] for subject in activity)
        if total_fans == 0 and total_watchlists == 0 and total_views == 0:
            result["skipped_no_activity"] += 1
            last_processed = account_id
            continue

        email_subject = (
            f"Your Academy Watch activity: {total_fans} new fans, "
            f"{total_watchlists} watchlist adds, {total_views} profile views"
        )
        html = render_template(
            "profile_activity_email.html",
            subjects=activity,
            new_fans=total_fans,
            watchlist_adds=total_watchlists,
            profile_views=total_views,
        )
        text = _plain_text(
            activity,
            new_fans=total_fans,
            watchlist_adds=total_watchlists,
            profile_views=total_views,
        )

        remaining -= 1
        if dry_run:
            result["previews"].append(
                {
                    "email": email_service._mask_email(account.email),
                    "subject": email_subject,
                    "subjects": activity,
                }
            )
        else:
            try:
                delivery = email_service.send_email(
                    to=account.email,
                    subject=email_subject,
                    html=html,
                    text=text,
                    tags=["profile-activity"],
                )
            except Exception:
                db.session.rollback()
                logger.exception("Profile activity email failed for account %s", account_id)
                result["errors"] += 1
            else:
                if not getattr(delivery, "success", False):
                    result["errors"] += 1
                else:
                    account.profile_activity_email_last_sent_at = run_now
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        logger.exception("Profile activity watermark commit failed for account %s", account_id)
                        result["errors"] += 1
                    else:
                        result["sent"] += 1

        last_processed = account_id
        if remaining == 0:
            result["budget_exhausted"] = True
            result["next_cursor"] = last_processed
            break
    else:
        result["next_cursor"] = last_processed if has_more else None

    return result


__all__ = ["MAX_PROFILE_ACTIVITY_USERS", "send_profile_activity_notifications"]
