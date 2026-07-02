"""Scout digest service — per-user watchlist / follow-list email digests.

Two shapes share one delta engine:

- **Watchlist (legacy) users** — each ScoutWatchlistEntry compares current stats
  (via TrackedPlayer.compute_stats()) against the entry's last_snapshot and
  renders delta chips, status-change headlines, and best-effort new-absence
  counts. This path is byte-for-byte unchanged.
- **Follow-list users** — each active FollowList resolves to a player set; a
  per-(user, player) FollowPlayerSnapshot row is the delta baseline (works for
  dynamic geo/query/academy membership) and is passed AS the "entry" to the same
  engine. Players outside the tracked universe render from their PlayerShadow.
  The email gains per-list sections; a user with no lists gets the legacy email.
"""

import json
import logging
import os
from datetime import UTC, datetime

from flask import render_template
from sqlalchemy import and_, exists, func, or_
from src.models.follow import FollowList, FollowPlayerSnapshot, PlayerShadow, PlayerShadowStats
from src.models.league import UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer

logger = logging.getLogger(__name__)

MAX_DIGEST_USERS = 200
# One run touches at most this many entries across all users — keeps a
# synchronous admin request bounded; callers page with `cursor`.
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


def _active_shadow(player_api_id: int):
    return PlayerShadow.query.filter_by(player_api_id=player_api_id, is_active=True).first()


def _shadow_stats(player_api_id: int) -> dict:
    """Latest-season totals from PlayerShadowStats (summed across teams).

    Reads the newest season present for the player rather than a wall-clock
    season, so it is immune to API-Football client season drift (a shadow
    synced against season N stays visible when the clock ticks to N+1)."""
    latest_season = (
        db.session.query(func.max(PlayerShadowStats.season))
        .filter(PlayerShadowStats.player_api_id == player_api_id)
        .scalar()
    )
    if latest_season is None:
        return {"appearances": 0, "goals": 0, "assists": 0, "minutes_played": 0}
    row = (
        db.session.query(
            func.coalesce(func.sum(PlayerShadowStats.appearances), 0),
            func.coalesce(func.sum(PlayerShadowStats.goals), 0),
            func.coalesce(func.sum(PlayerShadowStats.assists), 0),
            func.coalesce(func.sum(PlayerShadowStats.minutes), 0),
        )
        .filter(PlayerShadowStats.player_api_id == player_api_id, PlayerShadowStats.season == latest_season)
        .first()
    )
    apps, goals, assists, minutes = (int(value or 0) for value in (row or (0, 0, 0, 0)))
    return {"appearances": apps, "goals": goals, "assists": assists, "minutes_played": minutes}


# Memo key (namespaced string so it never collides with the int player_api_id
# keys _player_state stores in the same per-run cache dict).
_PULSE_CARDS_KEY = "__pulse_cards__"


def _pulse_cards_map(cache: dict) -> dict:
    """{player_api_id: {card_html, card_text, model}} for the current window.

    Reads player_card_service's shared render seam ONCE per run (memoised): the
    latest cached window, then every card in it. Returns {} when no cards exist —
    or when the pulse infra is absent (a test app that never registered the
    tables / the service) — so the digest renders EXACTLY as it did before pulse
    cards existed. A query failure rolls the session back so surrounding stat
    queries stay usable.
    """
    if _PULSE_CARDS_KEY in cache:
        return cache[_PULSE_CARDS_KEY]
    cards: dict = {}
    try:
        from src.services.player_card_service import get_cards_for_window, latest_card_window

        window = latest_card_window()
        if window is not None:
            cards = get_cards_for_window(window)
    except Exception:
        db.session.rollback()
        cards = {}
    cache[_PULSE_CARDS_KEY] = cards
    return cards


def _absence_count(api_client, player_api_id: int) -> int | None:
    """Best-effort season absence count; None when unavailable."""
    if api_client is None:
        return None
    try:
        return len(api_client.get_player_injuries(player_api_id) or [])
    except Exception as exc:
        logger.warning("Absence lookup failed for player %s: %s", player_api_id, exc)
        return None


def _load_snapshot(entry) -> dict | None:
    if not entry.last_snapshot:
        return None
    try:
        snapshot = json.loads(entry.last_snapshot)
        return snapshot if isinstance(snapshot, dict) else None
    except (TypeError, ValueError):
        return None


def _player_state(player_api_id: int, cache: dict, api_client=None) -> dict:
    """Memoised per run — many users watch the same players, so stats and
    injuries are computed once per player.

    Returns a dict with ``kind`` in {tracked, shadow, none}. A tracked player
    NEVER goes through the shadow branch (compute_stats stays authoritative);
    only players with no active tracked row fall back to a PlayerShadow.
    """
    if player_api_id in cache:
        return cache[player_api_id]
    tracked_player = _preferred_tracked_player(player_api_id)
    if tracked_player is not None:
        state = {
            "kind": "tracked",
            "tracked": tracked_player,
            "shadow": None,
            "stats": tracked_player.compute_stats(),
            "absences": _absence_count(api_client, player_api_id),
        }
    else:
        shadow = _active_shadow(player_api_id)
        if shadow is not None:
            state = {
                "kind": "shadow",
                "tracked": None,
                "shadow": shadow,
                "stats": _shadow_stats(player_api_id),
                "absences": None,
            }
        else:
            state = {"kind": "none", "tracked": None, "shadow": None, "stats": None, "absences": None}
    # Shared per-window AI card (looked up from a once-per-run memoised map).
    # Absent when no card exists for the current window — the digest then renders
    # the legacy delta line.
    state["pulse_card"] = _pulse_cards_map(cache).get(player_api_id)
    cache[player_api_id] = state
    return state


def _entry_update(entry, cache: dict, api_client=None) -> dict | None:
    """Card + fresh snapshot for one entry; None when the player is neither a
    tracked player nor an active shadow. ``entry`` is a ScoutWatchlistEntry
    (watchlist path) or a FollowPlayerSnapshot (list path) — both expose
    player_api_id / last_snapshot / note."""
    state = _player_state(entry.player_api_id, cache, api_client=api_client)
    if state["kind"] == "none":
        return None

    stats = state["stats"]
    previous = _load_snapshot(entry)

    if state["kind"] == "tracked":
        tracked_player = state["tracked"]
        name = tracked_player.player_name
        status = tracked_player.status
        parent_club = tracked_player.team.name if tracked_player.team else None
        current_club = tracked_player.current_club_name
        absences = state["absences"]
        new_headline = "Added to your watchlist"
    else:
        shadow = state["shadow"]
        name = shadow.player_name
        status = None
        parent_club = None
        current_club = shadow.current_club_name
        absences = None
        new_headline = "Now tracking worldwide"

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
        card_headline = new_headline
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

        # Status headlines only apply to tracked players (shadows have no status).
        previous_status = previous.get("status")
        if status and previous_status and previous_status != status:
            label = _STATUS_LABELS.get(status, f"Status changed to {status}")
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
        "status": status,
        "absences": absences if absences is not None else int((previous or {}).get("absences") or 0),
        "taken_at": datetime.now(UTC).isoformat(),
    }

    card = {
        "player_api_id": entry.player_api_id,
        "player_name": name,
        "player_url": f"{_public_base_url()}/players/{entry.player_api_id}",
        "parent_club": parent_club,
        "current_club": current_club,
        "status": status,
        "is_new": previous is None,
        "season_line": season_line,
        "chips": chips,
        "headline": card_headline,
        "note": entry.note,
    }

    # ADDITIVE: when a shared card exists for this player's current window, the
    # provenance-clean card text supersedes the raw delta line. The keys are
    # only ADDED when a card exists, so a card-less digest is byte-identical.
    pulse_card = state.get("pulse_card")
    if pulse_card:
        card["pulse_html"] = pulse_card["card_html"]
        card["pulse_text"] = pulse_card["card_text"]

    return {"entry": entry, "card": card, "snapshot": snapshot, "headlines": headlines}


def _card_text_lines(card: dict) -> list[str]:
    club_line = " -> ".join(part for part in (card["parent_club"], card["current_club"]) if part)
    lines = [f"{card['player_name']} ({club_line or 'club unknown'}) [{card['status'] or 'worldwide'}]"]
    if card["headline"]:
        lines.append(f"  {card['headline']}")
    # The shared card text supersedes the raw delta line when present; otherwise
    # the season line + chips render exactly as before (byte-identical).
    if card.get("pulse_text"):
        lines.append(f"  {card['pulse_text']}")
    else:
        lines.append(f"  {card['season_line']}")
        if card["chips"]:
            lines.append(f"  {', '.join(card['chips'])}")
    lines.append(f"  {card['player_url']}")
    lines.append("")
    return lines


def _digest_text(headlines: list[str], cards: list[dict], watchlist_url: str, groups=None) -> str:
    lines = ["THE ACADEMY WATCH — Scout Digest", ""]
    if headlines:
        lines.append("Headlines:")
        lines.extend(f"- {headline}" for headline in headlines)
        lines.append("")
    # Flat watchlist section first (byte-identical to the legacy digest when it
    # is all a user has), then any per-list grouped sections.
    for card in cards:
        lines.extend(_card_text_lines(card))
    if groups:
        for group in groups:
            lines.append(group["name"].upper())
            lines.append("")
            for card in group["cards"]:
                lines.extend(_card_text_lines(card))
    lines.append(f"Manage this digest from your watchlist: {watchlist_url}")
    return "\n".join(lines)


def _render_digest(user: UserAccount, flat_updates: list[dict], groups=None, group_updates=None) -> dict | None:
    """Render a digest as a flat watchlist section (``flat_updates``) followed by
    optional per-list grouped sections (``groups`` + their ``group_updates``).

    A user with only watchlist entries passes no groups → the template's legacy
    flat layout renders byte-identically."""
    group_updates = group_updates or []
    all_updates = list(flat_updates) + list(group_updates)
    if not all_updates:
        return None
    flat_cards = [update["card"] for update in flat_updates]
    headlines = [headline for update in all_updates for headline in update["headlines"]]
    count = len(all_updates)
    subject = f"Scout Digest — {_plural(count, 'player')} on your watchlist"
    watchlist_url = f"{_public_base_url()}/scout/watchlist"
    html = render_template(
        "scout_digest_email.html",
        headlines=headlines,
        players=flat_cards,
        groups=groups or None,
        player_count=count,
        watchlist_url=watchlist_url,
    )
    return {
        "subject": subject,
        "html": html,
        "text": _digest_text(headlines, flat_cards, watchlist_url, groups=groups),
        "players": count,
    }


def build_user_digest(user: UserAccount, entries: list[ScoutWatchlistEntry], api_client=None) -> dict | None:
    """Render one watchlist user's (flat) digest; None when nothing to send."""
    cache: dict = {}
    flat_updates = [u for u in (_entry_update(entry, cache, api_client=api_client) for entry in entries) if u]
    return _render_digest(user, flat_updates)


# --------------------------------------------------------------------------- #
# Follow-list digest assembly
# --------------------------------------------------------------------------- #


def _list_player_notes(lists) -> dict:
    """player_api_id -> note, from player-kind follows across the user's lists."""
    from src.models.follow import Follow

    notes: dict = {}
    for follow_list in lists:
        for follow in follow_list.follows.filter(Follow.kind == "player").all():
            pid = (follow.selector or {}).get("player_api_id")
            if pid and pid not in notes and follow.note:
                notes[pid] = follow.note
    return notes


def _get_or_transient_snapshot(user_id: int, player_api_id: int, note):
    """Existing FollowPlayerSnapshot, or a transient one (NOT added to the
    session) so dry runs never persist a baseline."""
    snap = FollowPlayerSnapshot.query.filter_by(user_account_id=user_id, player_api_id=player_api_id).first()
    if snap is None:
        snap = FollowPlayerSnapshot(user_account_id=user_id, player_api_id=player_api_id, note=note)
    return snap


def _build_list_updates(user: UserAccount, lists, cache: dict, api_client=None, seen=None):
    """Resolve a user's lists into (groups, updates).

    A player is shown once — the first list to resolve it wins, and any player
    already in ``seen`` (e.g. the watchlist section — watchlist wins) is
    skipped. Each resolved player gets a get-or-transient FollowPlayerSnapshot
    that carries the delta baseline and is the "entry" handed to the shared
    delta engine.
    """
    from src.services.follow_resolver import resolve_list

    note_map = _list_player_notes(lists)
    groups = []
    updates = []
    seen = set(seen) if seen else set()
    for follow_list in lists:
        resolved = resolve_list(follow_list, limit=follow_list.player_cap)
        cards = []
        for item in resolved:
            pid = item["player_api_id"]
            if pid in seen:
                continue
            seen.add(pid)
            snap = _get_or_transient_snapshot(user.id, pid, note_map.get(pid))
            update = _entry_update(snap, cache, api_client=api_client)
            if update is None:
                continue
            cards.append(update["card"])
            updates.append(update)
        if cards:
            groups.append({"name": follow_list.name, "cards": cards})
    return groups, updates


def _assemble_user_updates(user: UserAccount, watchlist_entries, routed_lists, cache: dict, api_client=None):
    """(flat_updates, groups, group_updates) for one user — ADDITIVE.

    The flat section comes from the watchlist (legacy ordering/snapshots/caps);
    the grouped sections come from ``routed_lists`` and exclude any player
    already on the watchlist (watchlist wins) so a player is never shown twice.
    """
    flat_updates = [u for u in (_entry_update(e, cache, api_client=api_client) for e in watchlist_entries) if u]
    seen = {entry.player_api_id for entry in watchlist_entries}
    groups, group_updates = _build_list_updates(user, routed_lists, cache, api_client=api_client, seen=seen)
    return flat_updates, groups, group_updates


def send_scout_digests(dry_run: bool = True, limit: int = 50, api_client=None, cursor: int = 0) -> dict:
    """Build (and optionally send) digests for eligible users.

    Eligibility (opt-in true, email present, AND has watchlist entries OR an
    active follow list) is filtered in SQL so ineligible users never consume
    slots. `cursor` is the last fully-processed user_account_id; the result's
    `next_cursor` is non-null while more users remain.

    A user with active follow lists gets the generalized per-list digest; a
    user with only a watchlist gets the legacy digest (byte-identical). dry_run
    renders previews without sending and without mutating snapshots. Real runs
    persist each entry's last_snapshot/last_digest_at after a successful send.
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

    has_watchlist = exists().where(ScoutWatchlistEntry.user_account_id == UserAccount.id)
    has_list = exists().where(and_(FollowList.user_account_id == UserAccount.id, FollowList.is_active.is_(True)))
    user_ids = [
        row[0]
        for row in db.session.query(UserAccount.id)
        .filter(
            UserAccount.id > cursor,
            UserAccount.email.isnot(None),
            UserAccount.scout_digest_opt_in.is_(True),
            or_(has_watchlist, has_list),
        )
        .order_by(UserAccount.id)
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

        # Additive routing: the watchlist is always the flat section; active
        # NON-DEFAULT lists append grouped sections. The default list is the
        # watchlist's mirror twin and never routes — EXCEPT as a fallback when
        # the watchlist is empty (a user who cleared their watchlist but whose
        # mirror follows remain still gets that content).
        watchlist_entries = (
            ScoutWatchlistEntry.query.filter_by(user_account_id=user_id)
            .order_by(ScoutWatchlistEntry.created_at.desc(), ScoutWatchlistEntry.id.desc())
            .all()
        )
        active_lists = FollowList.query.filter_by(user_account_id=user_id, is_active=True).order_by(FollowList.id).all()
        routed_lists = [fl for fl in active_lists if not fl.is_default]
        if not watchlist_entries:
            routed_lists += [fl for fl in active_lists if fl.is_default]

        flat_updates, groups, group_updates = _assemble_user_updates(
            user, watchlist_entries, routed_lists, player_cache, api_client=api_client
        )
        total_updates = len(flat_updates) + len(group_updates)
        if total_updates > entry_budget:
            exhausted_budget = True
            break
        entry_budget -= total_updates
        updates = list(flat_updates) + list(group_updates)
        digest = _render_digest(user, flat_updates, groups=groups, group_updates=group_updates)

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
            entry = update["entry"]
            # List-path FollowPlayerSnapshot rows may be transient (first digest);
            # persist them only now, on a real, successful send.
            if entry not in db.session:
                db.session.add(entry)
            entry.last_snapshot = json.dumps(update["snapshot"])
            entry.last_digest_at = now
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
