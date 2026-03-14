"""On-demand player lookup for GOL.

Fetches player data from API-Football when a requested player is not already
present in the local Academy Watch DB. After lookup, saves:
- PlayerJourney
- PlayerJourneyEntry rows
- TrackedPlayer row (for the selected parent club)

The player cache is invalidated so GOL's DataFrames are refreshed on next access.
"""

import logging
import re
import threading
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from src.api_football_client import APIFootballClient
from src.models.journey import PlayerJourney
from src.models.league import Team, db
from src.models.tracked_player import TrackedPlayer
from src.services.journey_sync import JourneySyncService
from src.utils.academy_classifier import classify_tracked_player
from sqlalchemy import func

logger = logging.getLogger(__name__)

# In-memory daily rate limit state (reset at midnight UTC date boundary).
_RATE_LIMIT_STATE: dict[str, Any] = {
    "date": date.today().isoformat(),
    "global_count": 0,
    "sessions": {},
}
_RATE_LIMIT_LOCK = threading.Lock()


class GolPlayerLookup:
    """On-demand player lookup and persistence for GOL chats."""

    MAX_PER_SESSION = 10
    MAX_PER_DAY = 500

    def __init__(self, app):
        self.app = app
        self.api_client = APIFootballClient()

    def lookup(self, name: str, team: str | None = None, session_id: str | None = None) -> dict:
        """Search API-Football and persist player career data.

        Returns a dict shaped for the tool contract:
            {found, player_name, team, message, rate_limited}
        """
        player_name = (name or "").strip()
        if not player_name:
            return {
                "found": False,
                "player_name": "",
                "team": "",
                "message": "No player name provided.",
                "rate_limited": False,
            }

        with self.app.app_context():
            # If already present in any of the GOL tables, don't waste quotas.
            existing = self._find_existing(player_name)
            if existing:
                return {
                    "found": True,
                    "player_name": existing["player_name"],
                    "team": existing["team"],
                    "message": f"{existing['player_name']} is already in the database for {existing['team']}.",
                    "rate_limited": False,
                }

            # Apply simple in-process rate limits before calling external APIs.
            rate_limited, rate_message = self._is_rate_limited(session_id)
            if rate_limited:
                return {
                    "found": False,
                    "player_name": player_name,
                    "team": team or "",
                    "message": rate_message,
                    "rate_limited": True,
                }

            try:
                # Find matching API-Football player row.
                rows = self.api_client.search_player_profiles(player_name)
            except Exception as exc:
                err = str(exc).lower()
                if "quota" in err or "rate" in err:
                    return {
                        "found": False,
                        "player_name": player_name,
                        "team": team or "",
                        "message": f"Lookup failed for {player_name}: API quota reached. Try again later.",
                        "rate_limited": True,
                    }
                logger.exception("Player search failed for %s", player_name)
                return {
                    "found": False,
                    "player_name": player_name,
                    "team": team or "",
                    "message": f"Could not search API-Football for {player_name}.",
                    "rate_limited": False,
                }

            if not rows:
                return {
                    "found": False,
                    "player_name": player_name,
                    "team": team or "",
                    "message": f"Could not find a player matching '{player_name}' on API-Football.",
                    "rate_limited": False,
                }

            best = self._pick_best_match(rows, player_name, team)
            if not best:
                return {
                    "found": False,
                    "player_name": player_name,
                    "team": team or "",
                    "message": f"Could not find a close match for '{player_name}' on API-Football.",
                    "rate_limited": False,
                }

            player = best.get("player") or {}
            player_id = player.get("id")
            if not player_id:
                return {
                    "found": False,
                    "player_name": player_name,
                    "team": team or "",
                    "message": f"API-Football player data was missing for '{player_name}'.",
                    "rate_limited": False,
                }

            try:
                journey = self._sync_journey(player_id)
            except Exception as exc:
                logger.exception("Journey sync failed for player %s", player_id)
                return {
                    "found": False,
                    "player_name": player_name,
                    "team": team or "",
                    "message": f"Found {player.get('name', player_name)} but couldn't sync career data: {str(exc)}",
                    "rate_limited": False,
                }

            parent_team = self._resolve_parent_team(best, team)
            if not parent_team:
                return {
                    "found": False,
                    "player_name": player.get("name") or player_name,
                    "team": team or "",
                    "message": (
                        f"Found {player.get('name', player_name)} and cached their career, "
                        "but couldn't match a tracked parent club in our DB."
                    ),
                    "rate_limited": False,
                }

            # Create or update a tracked record for the selected parent team.
            try:
                tracked = self._upsert_tracked_player(player_id=player_id, player_block=best, journey=journey, team=parent_team)
            except Exception as exc:
                db.session.rollback()
                logger.exception("Failed to persist tracked player for %s", player_id)
                return {
                    "found": False,
                    "player_name": player.get("name") or player_name,
                    "team": parent_team.name,
                    "message": f"Found {player.get('name', player_name)} but couldn't save their record: {str(exc)}",
                    "rate_limited": False,
                }

            # Ensure GOL cache is refreshed next query.
            from src.services.gol_dataframes import DataFrameCache
            DataFrameCache.invalidate()

            return {
                "found": True,
                "player_name": tracked.player_name,
                "team": tracked.team.name if tracked.team else parent_team.name,
                "message": f"Added {tracked.player_name} to the database.\n"
                           f"Current club: {journey.current_club_name if journey else 'unknown'}.",
                "rate_limited": False,
            }

    def _is_rate_limited(self, session_id: str | None) -> tuple[bool, str]:
        """Check + increment in-memory rate limits."""
        key = (session_id or "anonymous").strip() or "anonymous"
        with _RATE_LIMIT_LOCK:
            today = date.today().isoformat()
            if _RATE_LIMIT_STATE["date"] != today:
                _RATE_LIMIT_STATE["date"] = today
                _RATE_LIMIT_STATE["global_count"] = 0
                _RATE_LIMIT_STATE["sessions"] = {}

            if _RATE_LIMIT_STATE["sessions"].get(key, 0) >= self.MAX_PER_SESSION:
                return True, "Per-session lookup limit reached. Try again later."

            if _RATE_LIMIT_STATE["global_count"] >= self.MAX_PER_DAY:
                return True, "Daily lookup limit reached. Try again tomorrow."

            _RATE_LIMIT_STATE["sessions"][key] = _RATE_LIMIT_STATE["sessions"].get(key, 0) + 1
            _RATE_LIMIT_STATE["global_count"] += 1
            return False, ""

    def _find_existing(self, name: str) -> dict | None:
        """Find player already in local records by name."""
        target = name.strip().lower()

        tracked = TrackedPlayer.query.filter(
            func.lower(TrackedPlayer.player_name) == target,
            TrackedPlayer.is_active == True,
        ).first()
        if not tracked:
            like = f"%{name.strip()}%"
            tracked = TrackedPlayer.query.filter(
                TrackedPlayer.player_name.ilike(like),
                TrackedPlayer.is_active == True,
            ).order_by(TrackedPlayer.player_name).first()

        if tracked:
            team = tracked.team.name if tracked.team else ""
            return {
                "player_name": tracked.player_name,
                "team": team,
                "source": "tracked",
            }

        journey = PlayerJourney.query.filter(
            func.lower(PlayerJourney.player_name) == target,
        ).first()
        if not journey:
            journey = PlayerJourney.query.filter(
                PlayerJourney.player_name.ilike(f"%{name.strip()}%")
            ).order_by(PlayerJourney.player_name).first()

        if journey:
            return {
                "player_name": journey.player_name or name,
                "team": journey.current_club_name or "",
                "source": "journey",
            }

        return None

    def _pick_best_match(self, rows: List[Dict[str, Any]], name: str, team: str | None) -> dict | None:
        """Choose the best API-Football row by fuzzy name + optional team match."""
        wanted_name = self._normalize(name)
        wanted_team = self._normalize(team or "")

        best_score = 0.0
        best_row = None

        for row in rows:
            player = row.get("player") or {}
            row_name = self._normalize(player.get("name") or "")
            if not row_name:
                continue

            score = SequenceMatcher(None, wanted_name, row_name).ratio()
            if not score:
                continue

            # optional team matching boost
            if wanted_team:
                team_score = self._team_match_score(row, wanted_team)
                score += 0.35 * team_score

            if score > best_score:
                best_score = score
                best_row = row

        # Require a reasonable match before syncing.
        if best_row is None or best_score < 0.40:
            return None

        return best_row

    def _team_match_score(self, row: dict, wanted_team: str) -> float:
        wanted_team = wanted_team.strip().lower()
        if not wanted_team:
            return 0.0

        for stat in row.get("statistics") or []:
            team_block = stat.get("team") or {}
            team_name = (team_block.get("name") or "").strip().lower()
            if wanted_team in team_name or team_name in wanted_team:
                return 1.0
            if SequenceMatcher(None, wanted_team, team_name).ratio() > 0.75:
                return 0.8

        return 0.0

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    def _sync_journey(self, player_id: int) -> PlayerJourney | None:
        """Build cached journey + entries with API-Football data."""
        syncer = JourneySyncService(self.api_client)
        return syncer.sync_player(player_id, force_full=False)

    def _resolve_parent_team(self, player_row: dict, team_hint: str | None) -> Optional[Team]:
        """Resolve the academy/parent team row for the requested player."""
        # 1) explicit team filter by name
        if team_hint:
            matched = Team.query.filter(Team.name.ilike(f"%{team_hint.strip()}%"))
            matched = matched.filter(Team.is_active == True)
            resolved = matched.order_by(Team.season.desc()).first()
            if resolved:
                return resolved

            try:
                team_api_id = int(team_hint)
                resolved = Team.query.filter_by(team_id=team_api_id, is_active=True).order_by(Team.season.desc()).first()
                if resolved:
                    return resolved
            except (TypeError, ValueError):
                pass

        # 2) use stats team from API row (best available)
        candidate_ids = []
        for stat in (player_row.get("statistics") or []):
            team_block = stat.get("team") or {}
            tid = team_block.get("id")
            if isinstance(tid, int):
                candidate_ids.append(tid)

        # Use latest matching team row.
        for team_id in dict.fromkeys(candidate_ids):
            resolved = Team.query.filter_by(team_id=team_id, is_active=True).order_by(Team.season.desc()).first()
            if resolved:
                return resolved

        # 3) fallback to most recent tracked team if all else fails
        latest_team = Team.query.filter(Team.is_active == True).order_by(Team.season.desc()).first()
        return latest_team

    def _upsert_tracked_player(self, player_id: int, player_block: dict, journey: PlayerJourney | None, team: Team) -> TrackedPlayer:
        """Create or refresh a TrackedPlayer row for this player and parent team."""
        player = player_block.get("player") or {}
        bio = player.get("birth") or {}

        # Current level and transfers for status classification.
        current_club_id = journey.current_club_api_id if journey else None
        current_club_name = journey.current_club_name if journey else None
        current_level = journey.current_level if journey else None

        status, loan_club_api_id, loan_club_name = classify_tracked_player(
            current_club_api_id=current_club_id,
            current_club_name=current_club_name,
            current_level=current_level,
            parent_api_id=team.team_id,
            parent_club_name=team.name,
            player_api_id=player_id,
            api_client=self.api_client,
        )

        age = player.get("age")
        try:
            age = int(age) if age is not None else None
        except (TypeError, ValueError):
            age = None

        position = player.get("position")
        if not position:
            # position may be in the first statistics block
            for stat in (player_block.get("statistics") or []):
                games = stat.get("games") or {}
                position = games.get("position")
                if position:
                    break

        existing = TrackedPlayer.query.filter_by(
            player_api_id=player_id,
            team_id=team.id,
        ).first()

        if existing:
            existing.player_name = player.get("name") or existing.player_name
            existing.photo_url = player.get("photo") or existing.photo_url
            existing.position = position or existing.position
            existing.nationality = player.get("nationality") or existing.nationality
            existing.birth_date = bio.get("date") or existing.birth_date
            existing.age = age if age is not None else existing.age
            existing.status = status
            existing.current_level = current_level or existing.current_level
            existing.loan_club_api_id = loan_club_api_id
            existing.loan_club_name = loan_club_name
            existing.journey_id = journey.id if journey else existing.journey_id
            existing.data_source = 'api-football'
            existing.data_depth = 'full_stats'
            db.session.add(existing)
            db.session.commit()
            return existing

        tracked = TrackedPlayer(
            player_api_id=player_id,
            player_name=player.get("name") or f"Player {player_id}",
            photo_url=player.get("photo"),
            position=position,
            nationality=player.get("nationality"),
            birth_date=bio.get("date"),
            age=age,
            team_id=team.id,
            status=status,
            current_level=current_level,
            loan_club_api_id=loan_club_api_id,
            loan_club_name=loan_club_name,
            data_source='api-football',
            data_depth='full_stats',
            journey_id=journey.id if journey else None,
            is_active=True,
        )
        db.session.add(tracked)
        db.session.commit()
        return tracked
