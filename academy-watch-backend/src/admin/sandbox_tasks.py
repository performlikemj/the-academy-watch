"""Utility tasks exposed through the admin sandbox UI."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unicodedata import combining as _ud_combining
from unicodedata import normalize as _ud_normalize

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.mcp.brave import BraveApiError
from src.models.league import League, Player, PlayerFlag, Team
from src.models.tracked_player import TrackedPlayer
from src.services.wikipedia_classifier import classify_loan_row
from src.utils.brave_players import BravePlayerCollection, collect_players_from_brave
from src.utils.wikipedia_players import (
    collect_player_loans_from_wikipedia,
    extract_team_loan_candidates,
    extract_wikipedia_players,
    fetch_wikitext,
    search_wikipedia_title,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxContext:
    """Execution context available to sandbox tasks."""

    db_session: Session
    api_client: Any | None = None


class SandboxTaskError(RuntimeError):
    """Base error for sandbox task execution."""


class TaskNotFoundError(SandboxTaskError):
    """Raised when attempting to execute an unknown task id."""


class TaskValidationError(SandboxTaskError):
    """Raised when task input parameters are invalid."""


class TaskExecutionError(SandboxTaskError):
    """Raised when a task fails during execution."""


@dataclass(slots=True)
class SandboxTaskResult:
    """Normalized response payload returned by sandbox tasks."""

    status: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "payload": self.payload,
            "meta": self.meta,
        }


@dataclass(slots=True)
class SandboxTask:
    """Metadata and execution hook for a sandbox task."""

    task_id: str
    label: str
    description: str
    parameters: list[dict[str, Any]]
    runner: Callable[[MutableMapping[str, Any], SandboxContext], SandboxTaskResult]


_TASKS: dict[str, SandboxTask] = {}


def register_task(task: SandboxTask) -> None:
    """Register a sandbox task, replacing any existing definition for the id."""

    _TASKS[task.task_id] = task


def list_tasks() -> Iterable[SandboxTask]:
    """Return tasks in registration order."""

    return _TASKS.values()


def run_task(task_id: str, payload: MutableMapping[str, Any], context: SandboxContext) -> dict[str, Any]:
    """Execute the task identified by *task_id* and return the serialized result."""

    task = _TASKS.get(task_id)
    if not task:
        raise TaskNotFoundError(f"Unknown sandbox task '{task_id}'")

    try:
        result = task.runner(payload or {}, context)
    except TaskValidationError:
        raise
    except SandboxTaskError:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        raise TaskExecutionError(str(exc)) from exc

    if not isinstance(result, SandboxTaskResult):
        raise TaskExecutionError(f"Task '{task_id}' returned unsupported response type: {type(result)!r}")

    response = result.to_dict()
    response["task_id"] = task_id
    return response


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _param_truthy(mapping: MutableMapping[str, Any], key: str, *, default: bool = False) -> bool:
    if key not in mapping:
        return default
    value = mapping.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _strip_diacritics(text: str) -> str:
    try:
        return "".join(c for c in _ud_normalize("NFKD", text) if not _ud_combining(c))
    except Exception:
        return text


def _normalize_player_name_key(name: str) -> str:
    """Create a stable key: initial+last, lowercase, ASCII, alnum only."""
    if not name:
        return ""
    parts = str(name).split()
    if not parts:
        return ""
    if len(parts) == 1:
        disp = parts[0]
    else:
        disp = f"{parts[0][0]}. {parts[-1]}"
    ascii_disp = _strip_diacritics(disp)
    key = "".join(ch for ch in ascii_disp.lower() if ch.isalnum())
    return key


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i]
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cb = b[j - 1]
            cost = 0 if ca == cb else 1
            cur.append(
                min(
                    cur[-1] + 1,
                    prev[j] + 1,
                    prev[j - 1] + cost,
                )
            )
        prev = cur
    return prev[-1]


def _fuzzy_equal(a: str, b: str, *, max_distance: int = 1) -> bool:
    a2 = _normalize_player_name_key(a)
    b2 = _normalize_player_name_key(b)
    if not a2 or not b2:
        return False
    if a2 == b2:
        return True
    d = _levenshtein_distance(a2, b2)
    return d <= max_distance


def _task_list_missing_sofascore_ids(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    include_with_id = bool(params.get("include_with_id"))
    include_inactive = bool(params.get("include_inactive"))

    query = context.db_session.query(
        TrackedPlayer.player_api_id,
        TrackedPlayer.player_name,
        TrackedPlayer.team_id,
        TrackedPlayer.current_club_name,
        TrackedPlayer.is_active,
    )

    if not include_inactive:
        query = query.filter(TrackedPlayer.is_active.is_(True))

    rows = query.order_by(TrackedPlayer.player_name.asc()).all()

    player_ids = {row.player_api_id for row in rows if row.player_api_id}
    players: list[Player] = []
    if player_ids:
        players = context.db_session.query(Player).filter(Player.player_id.in_(player_ids)).all()

    sofascore_map = {p.player_id: p for p in players if getattr(p, "sofascore_id", None)}

    # Pre-fetch team names for display
    team_ids = {row.team_id for row in rows if row.team_id}
    team_name_map: dict[int, str] = {}
    if team_ids:
        team_rows = context.db_session.query(Team.id, Team.name).filter(Team.id.in_(team_ids)).all()
        team_name_map = {t.id: t.name for t in team_rows}

    deduped: dict[int, dict[str, Any]] = {}
    for row in rows:
        pid = row.player_api_id
        if not pid or pid in deduped:
            continue
        player_rec = sofascore_map.get(pid)
        sofascore_id = getattr(player_rec, "sofascore_id", None)
        entry = {
            "player_id": pid,
            "player_name": row.player_name,
            "primary_team": team_name_map.get(row.team_id, ""),
            "loan_team": row.current_club_name,
            "is_active": bool(row.is_active),
            "sofascore_id": sofascore_id,
            "has_sofascore_id": bool(sofascore_id),
        }
        deduped[pid] = entry

    players_list = list(deduped.values())
    if not include_with_id:
        players_list = [p for p in players_list if not p["has_sofascore_id"]]

    summary = (
        (
            f"Found {len(players_list)} players missing Sofascore ids"
            if not include_with_id
            else f"Found {len(players_list)} tracked players"
        )
        if players_list
        else "No tracked players found"
    )

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "players": players_list,
        },
        meta={"include_with_id": include_with_id},
    )


def _task_update_sofascore_id(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    player_id = _safe_int(params.get("player_id"))
    sofascore_id = params.get("sofascore_id")
    player_name = params.get("player_name")

    if not player_id:
        raise TaskValidationError("player_id (API-Football) is required")

    if sofascore_id in (None, ""):
        normalized_sofa = None
    else:
        normalized_sofa = _safe_int(sofascore_id)
        if not normalized_sofa:
            raise TaskValidationError("sofascore_id must be a positive integer")

    session = context.db_session
    created = False
    now = datetime.now(UTC)

    logger.info("[sofa] update requested player_id=%s sofascore_id=%s", player_id, sofascore_id)

    if normalized_sofa:
        existing = (
            session.query(Player).filter(Player.sofascore_id == normalized_sofa, Player.player_id != player_id).first()
        )
        if existing:
            raise TaskValidationError(
                f"Sofascore id {normalized_sofa} already assigned to player #{existing.player_id}"
            )

    record = session.query(Player).filter_by(player_id=player_id).one_or_none()
    if record is None:
        record = Player(player_id=player_id)
        record.created_at = now
        session.add(record)
        created = True

    if player_name:
        record.name = str(player_name).strip()[:160] or record.name or f"Player {player_id}"
    elif not record.name:
        record.name = f"Player {player_id}"

    record.sofascore_id = normalized_sofa
    record.updated_at = now

    session.commit()
    logger.info("[sofa] saved player_id=%s sofascore_id=%s created=%s", player_id, normalized_sofa, created)

    summary = (
        f"Assigned Sofascore id {normalized_sofa} to player #{player_id}"
        if normalized_sofa
        else f"Cleared Sofascore id for player #{player_id}"
    )

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "player_id": player_id,
            "sofascore_id": normalized_sofa,
            "created_player_row": created,
        },
    )


def _resolve_team_from_params(params: MutableMapping[str, Any]) -> Team:
    team_name_param = params.get("team_name")
    team_db_id = params.get("team_db_id")
    api_team_id = params.get("api_team_id")

    team: Team | None = None
    if team_name_param:
        team = Team.query.filter(func.lower(Team.name) == str(team_name_param).lower()).order_by(Team.id.desc()).first()
    if not team and team_db_id:
        try:
            team = Team.query.get(int(team_db_id))
        except Exception:
            team = None
    if not team and api_team_id:
        try:
            team = Team.query.filter_by(team_id=int(api_team_id)).first()
        except Exception:
            team = None
    if not team:
        raise TaskValidationError("Unable to resolve team by provided identifiers")
    return team


def _diff_loan_rows(
    *,
    context: SandboxContext,
    team: Team | None,
    season_year: int,
    rows: list[dict[str, Any]],
    use_openai: bool = False,
    apply_changes: bool = False,
    run_all_teams: bool = False,
    data_source: str = "wikipedia",
) -> tuple[list[dict[str, Any]], int]:
    logger.info(
        "[sandbox-diff] start team=%s season=%s rows=%s apply_changes=%s use_openai=%s source=%s",
        getattr(team, "name", None),
        season_year,
        len(rows or []),
        apply_changes,
        use_openai,
        data_source,
    )
    if not rows:
        return [], 0

    query = context.db_session.query(TrackedPlayer)
    if not run_all_teams and team is not None:
        query = query.filter(TrackedPlayer.team_id == team.id)

    existing_loans = query.all()
    existing_keys = {(row.player_name.lower(), (row.current_club_name or "").lower()) for row in existing_loans}
    # Build a normalized index for fuzzy lookups scoped to team
    existing_norm: dict[str, set[str]] = {}
    for row in existing_loans:
        try:
            key = (row.current_club_name or "").lower()
            existing_norm.setdefault(key, set()).add(_normalize_player_name_key(row.player_name))
        except Exception:
            continue

    missing: list[dict[str, Any]] = []
    created_count = 0
    parent_hint = team.name if team else None

    for row in rows:
        player_name = (row.get("player_name") or "").strip()
        loan_team_name = (row.get("loan_team") or "").strip()
        if not player_name or not loan_team_name:
            continue

        season_value = _safe_int(row.get("season_year")) or season_year
        parent_club = (row.get("parent_club") or parent_hint or "").strip()
        key = (player_name.lower(), loan_team_name.lower())
        present = key in existing_keys
        if present:
            logger.debug(
                "[sandbox-diff] already present player=%s loan_team=%s season=%s",
                player_name,
                loan_team_name,
                season_value,
            )

        payload_row: dict[str, Any] = {
            "player_name": player_name,
            "loan_team": loan_team_name,
            "season_year": season_value,
            "parent_club": parent_club,
            "present_in_db": present,
        }
        if "wiki_title" in row:
            payload_row["wiki_title"] = row["wiki_title"]
        if "source" in row:
            payload_row["source"] = row["source"]

        classification = None
        if (use_openai or apply_changes) and not present:
            try:
                default_parent = parent_club or parent_hint or (team.name if team else "")
                # Build a meaningful snippet for classification when not provided (e.g., Brave rows)
                raw_text = (row.get("raw_row") or "").strip()
                if not raw_text:
                    evidence = (row.get("evidence") or "").strip()
                    if evidence:
                        raw_text = evidence
                if not raw_text:
                    title = (row.get("source_title") or "").strip()
                    snip = (row.get("source_snippet") or "").strip()
                    combined = f"{title}. {snip}".strip()
                    if combined != ".":
                        raw_text = combined
                if not raw_text:
                    raw_text = f"{player_name} on loan to {loan_team_name} during season {season_value}."
                classification = classify_loan_row(
                    raw_text,
                    default_player=player_name,
                    default_parent=default_parent,
                    season_year=season_value,
                )
            except Exception as exc:
                classification = {
                    "valid": False,
                    "reason": str(exc),
                }
            payload_row["classification"] = classification
            try:
                logger.info(
                    "[sandbox-diff] classified valid=%s conf=%s player=%s parent=%s loan=%s season=%s reason=%s",
                    bool(classification.get("valid")),
                    classification.get("confidence"),
                    classification.get("player_name") or player_name,
                    classification.get("parent_club") or parent_club or parent_hint,
                    classification.get("loan_club") or loan_team_name,
                    classification.get("season_start_year") or season_value,
                    (classification.get("reason") or "")[:160],
                )
            except Exception:
                pass

            if apply_changes and classification.get("valid") and team is not None:
                current_club_name = classification.get("loan_club") or loan_team_name
                resolved_player = classification.get("player_name") or player_name
                logger.info(
                    "[sandbox-diff] applying change create TrackedPlayer for player=%s parent=%s loan=%s source=%s",
                    resolved_player,
                    team.name,
                    current_club_name,
                    data_source,
                )

                loan_team = (
                    context.db_session.query(Team).filter(func.lower(Team.name) == current_club_name.lower()).first()
                )
                # Canonicalize loan club name when we can resolve a Team row
                if loan_team:
                    current_club_name = loan_team.name

                # Check if a TrackedPlayer already exists for this player+team
                existing_tp = (
                    context.db_session.query(TrackedPlayer)
                    .filter(
                        TrackedPlayer.team_id == team.id,
                        func.lower(TrackedPlayer.player_name) == resolved_player.lower(),
                        func.lower(TrackedPlayer.current_club_name) == current_club_name.lower(),
                    )
                    .first()
                )
                if not existing_tp:
                    # Try to resolve API-Football player id from existing tracked players for this parent team
                    resolved_api_player_id = None
                    try:
                        tp_match = (
                            context.db_session.query(TrackedPlayer)
                            .filter(TrackedPlayer.team_id == team.id)
                            .filter(func.lower(TrackedPlayer.player_name) == resolved_player.lower())
                            .order_by(TrackedPlayer.updated_at.desc())
                            .first()
                        )
                        if tp_match and tp_match.player_api_id:
                            resolved_api_player_id = int(tp_match.player_api_id)
                    except Exception:
                        resolved_api_player_id = None

                    if resolved_api_player_id:
                        new_tp = TrackedPlayer(
                            player_name=resolved_player,
                            player_api_id=resolved_api_player_id,
                            team_id=team.id,
                            status="on_loan",
                            current_club_db_id=loan_team.id if loan_team else None,
                            current_club_name=current_club_name,
                            data_source=data_source,
                        )
                        context.db_session.add(new_tp)
                        created_count += 1
                        logger.info(
                            "[sandbox-diff] created TrackedPlayer player=%s team_id=%s loan_team=%s",
                            resolved_player,
                            team.id,
                            current_club_name,
                        )
                    else:
                        logger.info(
                            "[sandbox-diff] skipping create for player=%s: no api_player_id resolved",
                            resolved_player,
                        )
                else:
                    logger.info(
                        "[sandbox-diff] TrackedPlayer already exists for player=%s loan_team=%s; skipping",
                        resolved_player,
                        current_club_name,
                    )

        if not present:
            missing.append(payload_row)
            if not apply_changes:
                logger.info(
                    "[sandbox-diff] missing candidate (no write) player=%s loan_team=%s season=%s",
                    player_name,
                    loan_team_name,
                    season_value,
                )
        # Soft duplicate gate: if name is fuzzy-equal to an existing row for same team
        try:
            pool = existing_norm.get(loan_team_name.lower()) or set()
            cand_key = _normalize_player_name_key(player_name)
            fuzzy_dup = any(_levenshtein_distance(cand_key, ex) <= 1 for ex in pool)
            if fuzzy_dup:
                payload_row["possible_duplicate"] = True
                logger.info(
                    "[sandbox-diff] possible duplicate by fuzzy match player=%s loan_team=%s",
                    player_name,
                    loan_team_name,
                )
        except Exception:
            pass

    if apply_changes and created_count:
        context.db_session.commit()
    logger.info(
        "[sandbox-diff] complete created=%s missing=%s",
        created_count,
        len(missing),
    )

    return missing, created_count


def _task_check_missing_loanees(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    include_resolved = bool(params.get("include_resolved"))

    query = context.db_session.query(PlayerFlag)
    if not include_resolved:
        query = query.filter(PlayerFlag.status != "resolved")

    flags: list[PlayerFlag] = query.order_by(PlayerFlag.created_at.desc()).all()

    missing: list[dict[str, Any]] = []
    for flag in flags:
        exists = (
            context.db_session.query(TrackedPlayer).filter(TrackedPlayer.player_api_id == flag.player_api_id).first()
        )
        if exists:
            continue
        missing.append(
            {
                "player_api_id": flag.player_api_id,
                "primary_team_api_id": flag.primary_team_api_id,
                "loan_team_api_id": flag.loan_team_api_id,
                "season": flag.season,
                "reason": flag.reason,
                "status": flag.status,
                "flagged_at": flag.created_at.isoformat() if flag.created_at else None,
            }
        )

    summary = f"Potential missing loanees: {len(missing)}" if missing else "No missing loanees detected"

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "missing": missing,
            "missing_count": len(missing),
            "include_resolved": include_resolved,
        },
    )


def _task_compare_player_stats(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    player_id = params.get("player_id")
    if not player_id:
        raise TaskValidationError("Parameter 'player_id' is required")

    try:
        player_id_int = int(player_id)
    except (TypeError, ValueError) as exc:
        raise TaskValidationError("Parameter 'player_id' must be an integer") from exc

    season_param = params.get("season")
    season_value: int | None = None
    if season_param not in (None, ""):
        try:
            season_value = int(season_param)
        except (TypeError, ValueError) as exc:
            raise TaskValidationError("Parameter 'season' must be a valid year") from exc

    loan = context.db_session.query(TrackedPlayer).filter(TrackedPlayer.player_api_id == player_id_int).first()
    if not loan:
        raise TaskValidationError(f"Player {player_id_int} has no tracked record in the database")

    if context.api_client is None:
        raise TaskExecutionError("API client is not configured for sandbox tasks")

    api_response = context.api_client.get_player_by_id(player_id_int, season=season_value)
    statistics = api_response.get("statistics") or []

    totals = {
        "goals": 0,
        "assists": 0,
        "minutes": 0,
        "appearances": 0,
    }

    for entry in statistics:
        goals_block = entry.get("goals") or {}
        games_block = entry.get("games") or {}
        totals["goals"] += _safe_int(goals_block.get("total"))
        totals["assists"] += _safe_int(goals_block.get("assists"))
        totals["minutes"] += _safe_int(games_block.get("minutes"))
        appearances = games_block.get("appearances") if "appearances" in games_block else games_block.get("appearences")
        totals["appearances"] += _safe_int(appearances)

    local_stats = loan.compute_stats()

    diff = {
        "goals": {
            "db": _safe_int(local_stats.get("goals")),
            "api": totals["goals"],
        },
        "assists": {
            "db": _safe_int(local_stats.get("assists")),
            "api": totals["assists"],
        },
        "minutes": {
            "db": _safe_int(local_stats.get("minutes_played")),
            "api": totals["minutes"],
        },
        "appearances": {
            "db": _safe_int(local_stats.get("appearances")),
            "api": totals["appearances"],
        },
    }

    for key, values in diff.items():
        values["delta"] = values["api"] - values["db"]

    # Resolve parent team name via relationship
    parent_team_name = loan.team.name if loan.team else ""

    deltas = [f"{key} Δ{values['delta']:+d}" for key, values in diff.items() if values["delta"]]
    if deltas:
        summary_delta = ", ".join(deltas)
        summary = f"Player {loan.player_name}: {summary_delta}"
    else:
        summary = f"Player {loan.player_name}: totals match local data"

    payload = {
        "player": {
            "player_id": loan.player_api_id,
            "player_name": loan.player_name,
            "primary_team": parent_team_name,
            "loan_team": loan.current_club_name,
            "season_requested": season_value,
        },
        "diff": diff,
        "api_statistics": statistics,
    }

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload=payload,
        meta={"season_used": season_value},
    )


def _task_fetch_player_profile(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    player_id_param = params.get("player_id")
    search_query = str(params.get("search") or "").strip()
    season_param = params.get("season")
    page_param = params.get("page")

    if not player_id_param and not search_query:
        raise TaskValidationError("Provide either 'player_id' or 'search'")

    if context.api_client is None:
        raise TaskExecutionError("API client is not configured for sandbox tasks")

    if player_id_param:
        try:
            player_id_int = int(player_id_param)
        except (TypeError, ValueError) as exc:
            raise TaskValidationError("Parameter 'player_id' must be an integer") from exc

        profile = context.api_client.get_player_profile(player_id_int) or {}
        player_name = ((profile.get("player") or {}).get("name")) if isinstance(profile, dict) else None
        summary = (
            f"Player {player_id_int}: profile for {player_name}"
            if player_name
            else f"Player {player_id_int}: profile not found"
        )
        return SandboxTaskResult(
            status="ok",
            summary=summary,
            payload={
                "player_id": player_id_int,
                "profile": profile,
            },
            meta={"mode": "profile"},
        )

    season_value: int | None = None
    if season_param not in (None, ""):
        try:
            season_value = int(season_param)
        except (TypeError, ValueError) as exc:
            raise TaskValidationError("Parameter 'season' must be a valid year") from exc

    page_value = 1
    if page_param not in (None, ""):
        try:
            page_value = max(1, int(page_param))
        except (TypeError, ValueError) as exc:
            raise TaskValidationError("Parameter 'page' must be an integer") from exc

    league_ids: list[int] = [
        row.league_id
        for row in context.db_session.query(League.league_id).filter(League.league_id.isnot(None)).distinct()
    ]

    results = context.api_client.search_player_profiles(
        search_query,
        season=season_value,
        page=page_value,
        league_ids=league_ids,
    )

    summary = f"Found {len(results)} matches for '{search_query}'" if results else f"No matches for '{search_query}'"
    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "query": search_query,
            "season": season_value,
            "page": page_value,
            "matches": results,
        },
        meta={"mode": "search"},
    )


register_task(
    SandboxTask(
        task_id="list-missing-sofascore-ids",
        label="List Missing Sofascore IDs",
        description="Show loaned players without a Sofascore embed id.",
        parameters=[
            {
                "name": "include_with_id",
                "type": "checkbox",
                "label": "Include players that already have an id",
            },
            {
                "name": "include_inactive",
                "type": "checkbox",
                "label": "Include inactive loans",
            },
        ],
        runner=_task_list_missing_sofascore_ids,
    )
)

register_task(
    SandboxTask(
        task_id="update-player-sofascore-id",
        label="Set Player Sofascore ID",
        description="Assign or clear a Sofascore player id for a loaned player.",
        parameters=[
            {
                "name": "player_id",
                "type": "number",
                "label": "Player API-Football ID",
                "placeholder": "e.g. 777",
                "required": True,
            },
            {
                "name": "sofascore_id",
                "type": "number",
                "label": "Sofascore ID",
                "placeholder": "e.g. 1101989",
                "required": False,
                "help": "Leave empty to clear the current Sofascore id.",
            },
            {
                "name": "player_name",
                "type": "text",
                "label": "Player name (optional)",
                "placeholder": "Used when creating the player record",
                "required": False,
            },
        ],
        runner=_task_update_sofascore_id,
    )
)


def _task_backfill_team_countries(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    if context.api_client is None:
        raise TaskExecutionError("API client is not configured for this sandbox context")

    limit = _safe_int(params.get("limit"))
    if limit <= 0:
        limit = 100

    session = context.db_session
    missing_query = (
        session.query(Team)
        .filter(or_(Team.country.is_(None), Team.country == ""))
        .order_by(Team.updated_at.asc().nullsfirst(), Team.id.asc())
    )
    teams = missing_query.limit(limit).all()

    if not teams:
        return SandboxTaskResult(
            status="ok",
            summary="No teams found with missing countries",
            payload={"updated": 0, "team_ids": []},
        )

    updated: list[int] = []
    skipped: list[int] = []
    failed: list[dict[str, Any]] = []

    for team in teams:
        try:
            payload = context.api_client.get_team_by_id(team.team_id)
        except Exception as exc:  # pragma: no cover
            failed.append({"team_id": team.team_id, "reason": str(exc)})
            continue

        country = None
        try:
            country = (payload or {}).get("team", {}).get("country")
        except Exception:
            country = None

        if not country:
            skipped.append(team.team_id)
            continue

        team.country = str(country).strip()
        updated.append(team.id)

    session.commit()

    summary = f"Updated {len(updated)} team(s) with country info"
    if skipped:
        summary += f"; skipped {len(skipped)} with no country returned"
    if failed:
        summary += f"; {len(failed)} API error(s)"

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "updated": len(updated),
            "team_ids": updated,
            "skipped": skipped,
            "errors": failed,
        },
        meta={"limit": limit, "requested": len(teams)},
    )


register_task(
    SandboxTask(
        task_id="backfill-team-countries",
        label="Backfill Team Countries",
        description="Fetch missing team countries from API-Football and update the local database.",
        parameters=[
            {
                "name": "limit",
                "type": "number",
                "label": "Max teams to update",
                "placeholder": "Defaults to 100",
                "required": False,
            }
        ],
        runner=_task_backfill_team_countries,
    )
)


register_task(
    SandboxTask(
        task_id="check-missing-loanees",
        label="Check Missing Loanees",
        description="List flagged players who are not represented in the current loan table.",
        parameters=[
            {
                "name": "include_resolved",
                "type": "checkbox",
                "label": "Include resolved flags",
                "help": "Tick to include flags already marked as resolved.",
            }
        ],
        runner=_task_check_missing_loanees,
    )
)

register_task(
    SandboxTask(
        task_id="compare-player-stats",
        label="Compare Player Stats",
        description="Fetch live API data for a player and compare with stored loan stats.",
        parameters=[
            {
                "name": "player_id",
                "type": "number",
                "label": "Player API ID",
                "placeholder": "e.g. 505",
                "required": True,
            },
            {
                "name": "season",
                "type": "number",
                "label": "Season (start year)",
                "placeholder": "Optional, defaults to API fallback",
                "required": False,
            },
        ],
        runner=_task_compare_player_stats,
    )
)

register_task(
    SandboxTask(
        task_id="fetch-player-profile",
        label="Fetch Player Profile",
        description="Load an individual player profile or search by name via API-Football.",
        parameters=[
            {
                "name": "player_id",
                "type": "number",
                "label": "Player ID",
                "placeholder": "e.g. 276",
                "required": False,
                "help": "Takes priority when both ID and search are provided.",
            },
            {
                "name": "search",
                "type": "text",
                "label": "Search query",
                "placeholder": "e.g. Neymar",
                "required": False,
                "help": "Search by player name when ID is unknown.",
            },
            {
                "name": "season",
                "type": "number",
                "label": "Season (optional)",
                "placeholder": "Start year, e.g. 2025",
                "required": False,
            },
            {
                "name": "page",
                "type": "number",
                "label": "Page",
                "placeholder": "Defaults to 1",
                "required": False,
            },
        ],
        runner=_task_fetch_player_profile,
    )
)


def _task_wiki_loan_diff(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    logger.info(
        "[wiki-loans] wiki-loan-diff start: season=%s team_name=%s team_db_id=%s api_team_id=%s use_api_roster=%s",
        params.get("season"),
        params.get("team_name"),
        params.get("team_db_id"),
        params.get("api_team_id"),
        bool(params.get("use_api_roster")),
    )
    season_param = params.get("season")
    try:
        season_year = int(season_param)
    except (TypeError, ValueError):
        raise TaskValidationError("Parameter 'season' is required and must be an integer")

    team_name_param = params.get("team_name")
    team_db_id = params.get("team_db_id")
    api_team_id = params.get("api_team_id")
    run_all_teams = bool(params.get("run_all_teams"))

    team: Team | None = None
    if not run_all_teams:
        if team_name_param:
            team = (
                Team.query.filter(func.lower(Team.name) == str(team_name_param).lower())
                .order_by(Team.id.desc())
                .first()
            )
        if not team and team_db_id:
            team = Team.query.get(int(team_db_id))
        if not team and api_team_id:
            team = Team.query.filter_by(team_id=int(api_team_id)).first()
        if not team:
            raise TaskValidationError("Unable to resolve team by provided identifiers")

    candidates_param = params.get("candidates")
    if isinstance(candidates_param, str):
        candidate_names = [name.strip() for name in candidates_param.split(",") if name.strip()]
    elif isinstance(candidates_param, list):
        candidate_names = [str(name).strip() for name in candidates_param if str(name).strip()]
    else:
        candidate_names = []

    titles_param = params.get("player_titles")
    if isinstance(titles_param, str):
        player_titles = [title.strip() for title in titles_param.split(",") if title.strip()]
    elif isinstance(titles_param, list):
        player_titles = [str(title).strip() for title in titles_param if str(title).strip()]
    else:
        player_titles = []

    use_api_roster = bool(params.get("use_api_roster"))

    auto_candidates: list[dict[str, Any]] = []
    team_title = params.get("team_title")

    if not player_titles and not run_all_teams:
        try:
            if not team_title:
                team_title = search_wikipedia_title(team.name, context="football club")
            if team_title:
                team_wikitext = fetch_wikitext(team_title)
                auto_candidates = extract_team_loan_candidates(team_wikitext, season_year)
                if not candidate_names:
                    candidate_names = [row["player_name"] for row in auto_candidates]
                player_titles = []
                for row in auto_candidates:
                    title = search_wikipedia_title(row["player_name"], context="footballer")
                    if title:
                        player_titles.append(title)
        except Exception:
            auto_candidates = []

    use_openai = bool(params.get("use_openai"))
    apply_changes = bool(params.get("apply_changes"))

    wiki_rows: list[dict[str, Any]] = []
    api_roster_count = 0

    if use_api_roster and not run_all_teams:
        if not context.api_client:
            logger.warning("[wiki-loans] API roster requested but api_client is missing")
        else:
            logger.info(
                "[wiki-loans] fetching API roster team_id=%s season=%s", getattr(team, "team_id", None), season_year
            )
            try:
                api_response = context.api_client.get_team_players(team.team_id, season_year)
            except Exception as exc:  # pragma: no cover - upstream errors handled via admin UI
                logger.exception(
                    "[wiki-loans] failed to fetch API roster for team_id=%s season=%s: %s",
                    team.team_id,
                    season_year,
                    exc,
                )
                api_response = []
            logger.info("[wiki-loans] API roster response items=%s", len(api_response or []))

            player_payloads: list[dict[str, Any]] = []
            for entry in api_response or []:
                player_info = (entry or {}).get("player") or {}
                name = player_info.get("name") or " ".join(
                    part
                    for part in (
                        player_info.get("firstname"),
                        player_info.get("lastname"),
                    )
                    if part
                )
                if not name:
                    continue
                player_payloads.append(
                    {
                        "name": name,
                        "parent_club": team.name,
                        "team_name": team.name,
                    }
                )

            api_roster_count = len(player_payloads)
            logger.info(
                "[wiki-loans] mapped roster players=%s for team=%s season=%s", api_roster_count, team.name, season_year
            )
            if player_payloads:
                before_rows = len(wiki_rows)
                wiki_rows.extend(
                    collect_player_loans_from_wikipedia(
                        player_payloads,
                        season_year,
                        search_context=f"footballer {team.name}",
                    )
                )
                logger.info(
                    "[wiki-loans] wiki rows added from roster scan=%s total=%s",
                    len(wiki_rows) - before_rows,
                    len(wiki_rows),
                )

    for title in player_titles if not run_all_teams else []:
        if not title:
            continue
        try:
            wikitext = fetch_wikitext(title)
        except Exception:
            continue
        before = len(wiki_rows)
        wiki_rows.extend(
            extract_wikipedia_players(
                wikitext,
                season_year,
                player_name=title,
                parent_club_hint=team.name,
            )
        )
        for row in wiki_rows[before:]:
            row["wiki_title"] = title

    if auto_candidates and not wiki_rows and not run_all_teams:
        for row in auto_candidates:
            row_copy = dict(row)
            row_copy["parent_club"] = team.name
            row_copy["wiki_title"] = team_title
            wiki_rows.append(row_copy)

    missing, created_count = _diff_loan_rows(
        context=context,
        team=None if run_all_teams else team,
        season_year=season_year,
        rows=wiki_rows,
        use_openai=use_openai,
        apply_changes=apply_changes,
        run_all_teams=run_all_teams,
        data_source="wikipedia",
    )

    summary = (
        f"Found {len(missing)} missing loans for {team.name if not run_all_teams else 'all teams'}"
        if missing
        else f"No missing loans detected for {team.name if not run_all_teams else 'all teams'}"
    )

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "team": team.name if not run_all_teams else None,
            "season": season_year,
            "missing": missing,
            "wiki_rows": wiki_rows,
        },
        meta={
            "candidate_count": len(wiki_rows),
            "created_tracked": created_count,
            "openai_used": bool(use_openai or apply_changes),
            "api_roster_count": api_roster_count,
            "use_api_roster": use_api_roster,
            "run_all_teams": run_all_teams,
        },
    )


register_task(
    SandboxTask(
        task_id="wiki-loan-diff",
        label="Wikipedia Loan Diff",
        description="Compare Wikipedia loan listings with the current database.",
        parameters=[
            {
                "name": "season",
                "type": "number",
                "label": "Season start year",
                "placeholder": "e.g. 2025",
                "required": True,
            },
            {
                "name": "team_name",
                "type": "select",
                "label": "Team",
                "placeholder": "Select a club",
                "required": False,
                "help": "Pick a team to auto-fill identifiers from the database.",
            },
            {
                "name": "run_all_teams",
                "type": "checkbox",
                "label": "Run for all teams",
                "help": "Process all teams in the database (respects rate limits).",
                "required": False,
            },
            {
                "name": "team_db_id",
                "type": "hidden",
                "label": "Team DB ID",
                "placeholder": "",
                "required": False,
            },
            {
                "name": "api_team_id",
                "type": "hidden",
                "label": "API-Football Team ID",
                "placeholder": "",
                "required": False,
            },
            {
                "name": "player_titles",
                "type": "text",
                "label": "Wikipedia page titles",
                "placeholder": "Comma-separated list of player pages",
                "required": False,
            },
            {
                "name": "candidates",
                "type": "text",
                "label": "Candidate player names",
                "placeholder": "Optional list to help locate pages",
                "required": False,
            },
            {
                "name": "use_api_roster",
                "type": "checkbox",
                "label": "Use API roster",
                "help": "Fetch the team roster from API-Football and scan player pages automatically.",
                "required": False,
            },
            {
                "name": "use_openai",
                "type": "checkbox",
                "label": "Classify with GPT-5-mini",
                "help": "Use OpenAI Responses API to structure Wikipedia rows.",
                "required": False,
            },
            {
                "name": "apply_changes",
                "type": "checkbox",
                "label": "Create tracked players",
                "help": "Insert missing loans as tracked player rows (uses OpenAI classifier).",
                "required": False,
            },
        ],
        runner=_task_wiki_loan_diff,
    )
)


def _task_brave_loan_diff(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    logger.info(
        "[brave-loans] brave-loan-diff start season=%s team=%s limit=%s strict_range=%s run_all=%s",
        params.get("season"),
        params.get("team_name") or params.get("team_db_id") or params.get("api_team_id"),
        params.get("result_limit"),
        params.get("strict_range"),
        params.get("run_all_teams"),
    )

    season_param = params.get("season")
    try:
        season_year = int(season_param)
    except (TypeError, ValueError):
        raise TaskValidationError("Parameter 'season' is required and must be an integer")

    run_all_teams = bool(params.get("run_all_teams"))

    team: Team | None = None
    teams_to_process: list[Team] = []
    if run_all_teams:
        session = context.db_session
        if session is None:
            raise TaskExecutionError("Database session is not available")
        raw_teams = session.query(Team).order_by(Team.name.asc()).all()
        dedup: dict[str, Team] = {}
        for candidate in raw_teams:
            name_key = (candidate.name or "").strip().lower()
            if name_key:
                dedup[name_key] = candidate
        teams_to_process = [team_obj for _, team_obj in sorted(dedup.items(), key=lambda item: item[0])]
        if not teams_to_process:
            raise TaskValidationError("No teams available to process for Brave search diff")
    else:
        team = _resolve_team_from_params(params)
        teams_to_process = [team]

    use_openai = bool(params.get("use_openai"))
    apply_changes = bool(params.get("apply_changes"))
    query_override = params.get("search_query")
    result_limit = _safe_int(params.get("result_limit")) or 8
    strict_range = bool(params.get("strict_range"))

    aggregated_rows: list[dict[str, Any]] = []
    collection_lookup: dict[str, BravePlayerCollection] = {}
    errors: list[dict[str, str]] = []

    for team_obj in teams_to_process:
        team_name = team_obj.name if team_obj else None
        if not team_name:
            errors.append({"team": None, "error": "Missing team name"})
            continue

        try:
            collection = collect_players_from_brave(
                team_name=team_name,
                season_year=season_year,
                query=query_override,
                result_limit=result_limit,
                strict_range=strict_range,
            )
        except BraveApiError as exc:
            logger.exception("[brave-loans] collection failed for team=%s season=%s", team_name, season_year)
            errors.append({"team": team_name, "error": str(exc)})
            continue

        rows = list(collection.rows or [])
        for row in rows:
            row.setdefault("parent_club", team_name)
            row.setdefault("team_name", team_name)
        aggregated_rows.extend(rows)
        collection_lookup[team_name] = collection

    brave_rows = aggregated_rows
    missing, created_count = _diff_loan_rows(
        context=context,
        team=None if run_all_teams else team,
        season_year=season_year,
        rows=brave_rows,
        use_openai=use_openai,
        apply_changes=apply_changes,
        run_all_teams=run_all_teams,
        data_source="brave-search",
    )

    summary = (
        f"Found {len(missing)} missing loans via Brave Search for {team.name if not run_all_teams else 'all teams'}"
        if missing
        else f"No missing loans detected via Brave Search for {team.name if not run_all_teams else 'all teams'}"
    )

    teams_processed = len(collection_lookup)

    if not run_all_teams and team and team.name not in collection_lookup:
        # When single-team mode short-circuits due to error, reflect the exception upstream.
        first_error = errors[0] if errors else {"error": "Unknown Brave search error"}
        raise TaskExecutionError(first_error.get("error") or "Unable to collect Brave loans")

    search_results_by_team = {team_name: collection_lookup[team_name].results for team_name in collection_lookup}

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={
            "team": team.name if not run_all_teams else None,
            "season": season_year,
            "missing": missing,
            "brave_rows": brave_rows,
            "search_results": search_results_by_team
            if run_all_teams
            else next(iter(collection_lookup.values())).results
            if collection_lookup
            else [],
        },
        meta={
            "candidate_count": len(brave_rows),
            "created_tracked": created_count,
            "openai_used": bool(use_openai or apply_changes),
            "query": query_override
            if run_all_teams
            else (next(iter(collection_lookup.values())).query if collection_lookup else None),
            "result_limit": result_limit,
            "strict_range": strict_range,
            "run_all_teams": run_all_teams,
            "teams_processed": teams_processed,
            "errors": errors if errors else None,
            "search_results_by_team": search_results_by_team if run_all_teams else None,
        },
    )


register_task(
    SandboxTask(
        task_id="brave-loan-diff",
        label="Brave Search Loan Diff",
        description="Use Brave Search to locate loan listings and compare them with the database.",
        parameters=[
            {
                "name": "season",
                "type": "number",
                "label": "Season start year",
                "placeholder": "e.g. 2025",
                "required": True,
            },
            {
                "name": "team_name",
                "type": "select",
                "label": "Team",
                "placeholder": "Select a club",
                "required": False,
                "help": "Pick a team to auto-fill identifiers from the database.",
            },
            {
                "name": "run_all_teams",
                "type": "checkbox",
                "label": "Run for all teams",
                "help": "Process every team in the database (may take several minutes).",
                "required": False,
            },
            {
                "name": "team_db_id",
                "type": "hidden",
                "label": "Team DB ID",
                "placeholder": "",
                "required": False,
            },
            {
                "name": "api_team_id",
                "type": "hidden",
                "label": "API-Football Team ID",
                "placeholder": "",
                "required": False,
            },
            {
                "name": "search_query",
                "type": "text",
                "label": "Override search query",
                "placeholder": "Optional custom Brave query",
                "required": False,
            },
            {
                "name": "result_limit",
                "type": "number",
                "label": "Result limit",
                "placeholder": "Defaults to 8 (max 20)",
                "required": False,
            },
            {
                "name": "strict_range",
                "type": "checkbox",
                "label": "Enforce date range",
                "help": "Discard results outside the since/until window.",
                "required": False,
            },
            {
                "name": "use_openai",
                "type": "checkbox",
                "label": "Classify with GPT-5-mini",
                "required": False,
            },
            {
                "name": "apply_changes",
                "type": "checkbox",
                "label": "Create tracked player entries",
                "help": "Adds tracked player rows for validated results.",
                "required": False,
            },
        ],
        runner=_task_brave_loan_diff,
    )
)


def _task_scan_duplicate_loans(
    params: MutableMapping[str, Any],
    context: SandboxContext,
) -> SandboxTaskResult:
    season_param = params.get("season")
    season_year: int | None = None
    if season_param not in (None, ""):
        try:
            season_year = int(season_param)
        except (TypeError, ValueError) as exc:
            raise TaskValidationError("Season must be an integer year") from exc

    active_only = _param_truthy(params, "active_only", default=True)
    min_count = max(2, _safe_int(params.get("min_count")) or 2)
    limit = max(0, _safe_int(params.get("limit")) or 100)

    try:
        team = _resolve_team_from_params(params)
    except TaskValidationError:
        team = None

    session = context.db_session
    query = session.query(TrackedPlayer)
    if team:
        query = query.filter(TrackedPlayer.team_id == team.id)
    if active_only:
        query = query.filter(TrackedPlayer.is_active.is_(True))
    # season filtering is not applicable for TrackedPlayer (no window_key)
    season_slug = None

    rows = query.order_by(
        TrackedPlayer.team_id.asc(),
        TrackedPlayer.player_api_id.asc(),
        TrackedPlayer.updated_at.desc(),
    ).all()

    grouped: dict[tuple[int, int], list[TrackedPlayer]] = defaultdict(list)
    for row in rows:
        grouped[(row.team_id, row.player_api_id)].append(row)

    def _sort_key(item: TrackedPlayer):
        ts = item.updated_at or item.created_at or datetime(1970, 1, 1, tzinfo=UTC)
        return ts, item.id or 0

    duplicates: list[dict[str, Any]] = []
    for (team_id, player_id), loan_rows in grouped.items():
        if len(loan_rows) < min_count:
            continue
        ordered = sorted(loan_rows, key=_sort_key, reverse=True)
        primary = ordered[0]
        parent_team_name = primary.team.name if primary.team else ""
        entry = {
            "primary_team_id": team_id,
            "primary_team_name": parent_team_name,
            "player_id": player_id,
            "player_name": primary.player_name,
            "count": len(ordered),
            "active_count": sum(1 for item in ordered if item.is_active),
            "rows": [
                {
                    "id": item.id,
                    "loan_team_id": item.current_club_db_id,
                    "loan_team_name": item.current_club_name,
                    "is_active": bool(item.is_active),
                    "status": item.status,
                    "data_source": item.data_source,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in ordered
            ],
        }
        duplicates.append(entry)

    duplicates.sort(key=lambda entry: (entry["active_count"], entry["count"], entry["player_id"]), reverse=True)
    if limit and len(duplicates) > limit:
        duplicates = duplicates[:limit]

    filters = {
        "team_id": getattr(team, "id", None),
        "team_name": getattr(team, "name", None),
        "season": season_year,
        "active_only": active_only,
        "min_count": min_count,
        "limit": limit,
    }

    summary = (
        f"Found {len(duplicates)} player(s) with duplicate loan rows" if duplicates else "No duplicate loans detected"
    )

    return SandboxTaskResult(
        status="ok",
        summary=summary,
        payload={"duplicates": duplicates},
        meta={
            "filters": filters,
            "total_rows_scanned": len(rows),
            "duplicate_players": len(duplicates),
        },
    )


register_task(
    SandboxTask(
        task_id="loan-duplicates-scan",
        label="Scan Duplicate Loans",
        description="Identify players who have multiple loan rows for the same parent club.",
        parameters=[
            {
                "name": "team_name",
                "type": "select",
                "label": "Team",
                "placeholder": "Optional club filter",
                "required": False,
                "help": "Leave blank to scan all teams.",
            },
            {
                "name": "team_db_id",
                "type": "hidden",
                "label": "Team DB ID",
                "placeholder": "",
                "required": False,
            },
            {
                "name": "api_team_id",
                "type": "hidden",
                "label": "API-Football Team ID",
                "placeholder": "",
                "required": False,
            },
            {
                "name": "season",
                "type": "number",
                "label": "Season start year",
                "placeholder": "e.g. 2024",
                "required": False,
            },
            {
                "name": "active_only",
                "type": "checkbox",
                "label": "Active loans only",
                "help": "Limit scan to rows where is_active is true (default).",
                "required": False,
            },
            {
                "name": "min_count",
                "type": "number",
                "label": "Minimum rows per player",
                "placeholder": "Defaults to 2",
                "required": False,
            },
            {
                "name": "limit",
                "type": "number",
                "label": "Result limit",
                "placeholder": "Defaults to 100",
                "required": False,
            },
        ],
        runner=_task_scan_duplicate_loans,
    )
)
