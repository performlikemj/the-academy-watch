"""Scout digest service — per-user watchlist email digests.

For each watchlist entry the digest compares current stats (via
TrackedPlayer.compute_stats(); watchlists are small so per-entry queries are
fine in a batch job) against the entry's last_snapshot JSON and renders delta
chips, status-change headlines, and best-effort new-absence counts.
"""

import json
import logging
import os
from datetime import UTC, datetime

from flask import render_template
from src.models.league import UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer

logger = logging.getLogger(__name__)

MAX_DIGEST_USERS = 200
# One run touches at most this many watchlist entries across all users —
# keeps a synchronous admin request bounded; callers page with `cursor`.
MAX_DIGEST_ENTRIES = 2000
# Full rendered HTML only for the first few dry-run previews; at 200 users
# the response would otherwise be a multi-megabyte JSON blob.
MAX_PREVIEW_HTML = 5
_DEFAULT_PUBLIC_BASE_URL = "https://theacademywatch.com"

_STATUS_LABELS = {
    "first_team": "Promoted to first team",
    "on_loan": "Sent on loan",
    "sold": "Sold",
    "released": "Released",
    "academy": "Back in the academy",
}


def _public_base_url() -> str:
    base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    return base or _DEFAULT_PUBLIC_BASE_URL


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _preferred_tracked_player(player_api_id: int):
    """Active academy-origin TrackedPlayer for the id.

    owning-club rows are deprecated and excluded from every scout surface —
    surfacing them only in digest emails would advertise players the site
    itself no longer shows.
    """
    return (
        TrackedPlayer.query.filter_by(player_api_id=player_api_id, is_active=True)
        .filter(TrackedPlayer.data_source != "owning-club")
        .order_by(TrackedPlayer.id)
        .first()
    )


def _absence_count(api_client, player_api_id: int) -> int | None:
    """Best-effort season absence count; None when unavailable."""
    if api_client is None:
        return None
    try:
        return len(api_client.get_player_injuries(player_api_id) or [])
    except Exception as exc:
        logger.warning("Absence lookup failed for player %s: %s", player_api_id, exc)
        return None


def _load_snapshot(entry: ScoutWatchlistEntry) -> dict | None:
    if not entry.last_snapshot:
        return None
    try:
        snapshot = json.loads(entry.last_snapshot)
        return snapshot if isinstance(snapshot, dict) else None
    except (TypeError, ValueError):
        return None


def _player_state(player_api_id: int, cache: dict, api_client=None) -> tuple:
    """(tracked_player, stats, absences) memoised per run — many users watch
    the same players, so stats and injuries are computed once per player."""
    if player_api_id in cache:
        return cache[player_api_id]
    tracked_player = _preferred_tracked_player(player_api_id)
    stats = tracked_player.compute_stats() if tracked_player else None
    absences = _absence_count(api_client, player_api_id) if tracked_player else None
    state = (tracked_player, stats, absences)
    cache[player_api_id] = state
    return state


def _entry_update(entry: ScoutWatchlistEntry, cache: dict, api_client=None) -> dict | None:
    """Card + fresh snapshot for one entry; None when the player is no longer tracked."""
    tracked_player, stats, absences = _player_state(entry.player_api_id, cache, api_client=api_client)
    if tracked_player is None:
        return None

    previous = _load_snapshot(entry)
    name = tracked_player.player_name

    season_line = " · ".join(
        [
            _plural(int(stats.get("appearances") or 0), "app"),
            _plural(int(stats.get("goals") or 0), "goal"),
            _plural(int(stats.get("assists") or 0), "assist"),
            f"{int(stats.get('minutes_played') or 0)} mins",
        ]
    )

    chips = []
    headlines = []
    card_headline = None

    if previous is None:
        card_headline = "Added to your watchlist"
    else:
        new_apps = int(stats.get("appearances") or 0) - int(previous.get("appearances") or 0)
        new_goals = int(stats.get("goals") or 0) - int(previous.get("goals") or 0)
        new_assists = int(stats.get("assists") or 0) - int(previous.get("assists") or 0)
        new_minutes = int(stats.get("minutes_played") or 0) - int(previous.get("minutes_played") or 0)
        if new_goals > 0:
            chips.append(f"+{_plural(new_goals, 'goal')}")
        if new_assists > 0:
            chips.append(f"+{_plural(new_assists, 'assist')}")
        if new_apps > 0:
            chips.append(f"+{_plural(new_apps, 'app')}")
        if new_minutes > 0:
            chips.append(f"+{new_minutes} mins")

        previous_status = previous.get("status")
        if previous_status and tracked_player.status and previous_status != tracked_player.status:
            label = _STATUS_LABELS.get(tracked_player.status, f"Status changed to {tracked_player.status}")
            card_headline = label
            headlines.append(f"{name}: {label}")

        previous_absences = previous.get("absences")
        if absences is not None and previous_absences is not None:
            new_absences = absences - int(previous_absences or 0)
            if new_absences > 0:
                chips.append(_plural(new_absences, "new absence"))
                headlines.append(f"{name}: {_plural(new_absences, 'new absence')}")

    snapshot = {
        "appearances": int(stats.get("appearances") or 0),
        "goals": int(stats.get("goals") or 0),
        "assists": int(stats.get("assists") or 0),
        "minutes_played": int(stats.get("minutes_played") or 0),
        "status": tracked_player.status,
        "absences": absences if absences is not None else int((previous or {}).get("absences") or 0),
        "taken_at": datetime.now(UTC).isoformat(),
    }

    card = {
        "player_api_id": entry.player_api_id,
        "player_name": name,
        "player_url": f"{_public_base_url()}/players/{entry.player_api_id}",
        "parent_club": tracked_player.team.name if tracked_player.team else None,
        "current_club": tracked_player.current_club_name,
        "status": tracked_player.status,
        "is_new": previous is None,
        "season_line": season_line,
        "chips": chips,
        "headline": card_headline,
        "note": entry.note,
    }

    return {"entry": entry, "card": card, "snapshot": snapshot, "headlines": headlines}


def _digest_text(headlines: list[str], cards: list[dict], watchlist_url: str) -> str:
    lines = ["THE ACADEMY WATCH — Scout Digest", ""]
    if headlines:
        lines.append("Headlines:")
        lines.extend(f"- {headline}" for headline in headlines)
        lines.append("")
    for card in cards:
        club_line = " -> ".join(part for part in (card["parent_club"], card["current_club"]) if part)
        lines.append(f"{card['player_name']} ({club_line or 'club unknown'}) [{card['status']}]")
        if card["headline"]:
            lines.append(f"  {card['headline']}")
        lines.append(f"  {card['season_line']}")
        if card["chips"]:
            lines.append(f"  {', '.join(card['chips'])}")
        lines.append(f"  {card['player_url']}")
        lines.append("")
    lines.append(f"Manage this digest from your watchlist: {watchlist_url}")
    return "\n".join(lines)


def _render_digest(user: UserAccount, updates: list[dict]) -> dict | None:
    if not updates:
        return None
    cards = [update["card"] for update in updates]
    headlines = [headline for update in updates for headline in update["headlines"]]
    count = len(cards)
    subject = f"Scout Digest — {_plural(count, 'player')} on your watchlist"
    watchlist_url = f"{_public_base_url()}/scout/watchlist"
    html = render_template(
        "scout_digest_email.html",
        headlines=headlines,
        players=cards,
        player_count=count,
        watchlist_url=watchlist_url,
    )
    return {
        "subject": subject,
        "html": html,
        "text": _digest_text(headlines, cards, watchlist_url),
        "players": count,
    }


def build_user_digest(user: UserAccount, entries: list[ScoutWatchlistEntry], api_client=None) -> dict | None:
    """Render one user's digest; None when there is nothing to send."""
    cache: dict = {}
    updates = [u for u in (_entry_update(entry, cache, api_client=api_client) for entry in entries) if u]
    return _render_digest(user, updates)


def send_scout_digests(dry_run: bool = True, limit: int = 50, api_client=None, cursor: int = 0) -> dict:
    """Build (and optionally send) digests for eligible watchlist users.

    Eligibility (opt-in true, email present) is filtered in SQL so ineligible
    users never consume slots. `cursor` is the last fully-processed
    user_account_id; the result's `next_cursor` is non-null while more users
    remain, so repeated calls walk the whole population instead of re-picking
    the same first page forever.

    dry_run renders previews without sending and without mutating snapshots.
    Real runs persist each entry's last_snapshot/last_digest_at after a
    successful send.
    """
    from src.services.email_service import email_service  # lazy so tests can monkeypatch send_email

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    limit = min(max(limit, 1), MAX_DIGEST_USERS)
    try:
        cursor = max(int(cursor), 0)
    except (TypeError, ValueError):
        cursor = 0

    user_ids = [
        row[0]
        for row in db.session.query(ScoutWatchlistEntry.user_account_id)
        .join(UserAccount, UserAccount.id == ScoutWatchlistEntry.user_account_id)
        .filter(
            ScoutWatchlistEntry.user_account_id > cursor,
            UserAccount.email.isnot(None),
            UserAccount.scout_digest_opt_in.is_(True),
        )
        .distinct()
        .order_by(ScoutWatchlistEntry.user_account_id)
        .limit(limit)
        .all()
    ]

    from_name = os.getenv("EMAIL_FROM_NAME", "The Academy Watch")
    from_email = os.getenv("EMAIL_FROM_ADDRESS", "mail@theacademywatch.com")

    sent = 0
    skipped = 0
    previews = []
    now = datetime.now(UTC)
    player_cache: dict = {}
    entry_budget = MAX_DIGEST_ENTRIES
    last_processed = cursor
    exhausted_budget = False

    for user_id in user_ids:
        user = db.session.get(UserAccount, user_id)
        if user is None or not user.email or not user.scout_digest_opt_in:
            # Eligibility changed between the id query and now.
            skipped += 1
            last_processed = user_id
            continue

        entries = (
            ScoutWatchlistEntry.query.filter_by(user_account_id=user_id)
            .order_by(ScoutWatchlistEntry.created_at.desc(), ScoutWatchlistEntry.id.desc())
            .all()
        )
        if len(entries) > entry_budget:
            exhausted_budget = True
            break
        entry_budget -= len(entries)

        updates = [u for u in (_entry_update(entry, player_cache, api_client=api_client) for entry in entries) if u]
        digest = _render_digest(user, updates)
        if digest is None:
            skipped += 1
            last_processed = user_id
            continue

        preview = {"email": user.email, "subject": digest["subject"], "players": digest["players"]}
        if dry_run:
            if len(previews) < MAX_PREVIEW_HTML:
                preview["html"] = digest["html"]
            previews.append(preview)
            last_processed = user_id
            continue

        try:
            result = email_service.send_email(
                to=user.email,
                subject=digest["subject"],
                html=digest["html"],
                text=digest["text"],
                from_name=from_name,
                from_email=from_email,
                tags=["scout-digest"],
            )
        except Exception:
            logger.exception("Scout digest send failed for user %s", user_id)
            skipped += 1
            last_processed = user_id
            continue
        if result is not None and getattr(result, "success", True) is False:
            skipped += 1
            last_processed = user_id
            continue

        for update in updates:
            update["entry"].last_snapshot = json.dumps(update["snapshot"])
            update["entry"].last_digest_at = now
        db.session.commit()
        sent += 1
        previews.append(preview)
        last_processed = user_id

    more_remaining = exhausted_budget or len(user_ids) == limit
    return {
        "sent": sent,
        "skipped": skipped,
        "users_considered": len(user_ids),
        "previews": previews,
        "next_cursor": last_processed if more_remaining else None,
    }
