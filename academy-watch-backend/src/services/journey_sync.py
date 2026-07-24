"""
Journey Sync Service

Fetches and processes player career data from API-Football to build
complete journey records with academy, loan, and first team data.
"""

import logging
import re
from calendar import monthrange
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from src.api_football_client import APIFootballClient
from src.models.journey import LEVEL_PRIORITY, YOUTH_LEVELS, ClubLocation, PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, TeamProfile, db
from src.models.season_rollup import LeagueSeasonConfig
from src.models.transfer_event import PlayerTransferEvent
from src.services.season_rollup_service import refresh_player as refresh_season_rollup
from src.services.transfer_resolver import (
    ClubRef,
    LoanEpisode,
    TransferResolution,
    loan_episode_overlaps_season,
    normalize_transfer_events,
    resolve_transfer_state,
)
from src.utils.academy_classifier import (
    INTERNATIONAL_PATTERNS as _INTERNATIONAL_PATTERNS,
)
from src.utils.academy_classifier import (
    YOUTH_SUFFIXES as _YOUTH_SUFFIXES_RE,
)
from src.utils.academy_classifier import (
    is_international_competition,
    is_national_team,
    latest_parent_permanent_departure,
    resolved_current_club_is_authoritative,
    strip_youth_suffix,
)
from src.utils.affiliates import resolve_senior_id, senior_base_name
from src.utils.geocoding import get_team_coordinates
from src.utils.player_names import clean_name, is_placeholder_name, resolve_player_name

logger = logging.getLogger(__name__)


def _transfer_as_of(as_of: date | str | None = None) -> date | str:
    """Use one explicit UTC date for every resolver consumer in a sync."""
    return as_of if as_of is not None else datetime.now(UTC).date()


def _coerce_transfer_resolution(
    transfers,
    *,
    transfer_resolution: TransferResolution | None = None,
    as_of: date | str | None = None,
    season_start_month: int = 7,
    season_start_day: int = 1,
) -> TransferResolution | None:
    """Return a supplied resolution or resolve a fetched transfer payload once.

    ``None`` means transfer evidence was not fetched.  An empty list is a real,
    successfully-fetched empty history and therefore resolves to an explicit
    unknown state instead of falling back to stored journey guesses.
    """
    if transfer_resolution is not None:
        return transfer_resolution
    if isinstance(transfers, TransferResolution):
        return transfers
    if transfers is None:
        return None
    return resolve_transfer_state(
        transfers,
        as_of=_transfer_as_of(as_of),
        season_start_month=season_start_month,
        season_start_day=season_start_day,
    )


def _season_bounds(season: int, start_month: int = 7, start_day: int = 1) -> tuple[date, date]:
    """Return the half-open competition season for a provider season label."""
    start = date(int(season), int(start_month), int(start_day))
    return start, date(int(season) + 1, int(start_month), int(start_day))


def _season_grace_end(season_end: date, months: int = 3) -> date:
    """Return the inclusive end of a short post-season transfer grace window."""
    month_index = season_end.year * 12 + season_end.month - 1 + months - 1
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, monthrange(year, month)[1])


def _metadata_name(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _club_ref_matches(ref: ClubRef | None, club_api_id: int | None, club_name: str | None) -> bool:
    """Match a journey club to a resolver club across senior/youth affiliates."""
    if ref is None or (club_api_id is None and not club_name):
        return False
    if club_api_id is not None:
        if ref.api_id == club_api_id:
            return True
        senior_id = resolve_senior_id(club_api_id, club_name)
        if ref.organization_api_id is not None and ref.organization_api_id == senior_id:
            return True
    base_name = senior_base_name(club_name).strip().casefold()
    return bool(base_name and ref.organization_key == f"name:{base_name}")


def _stats_backed_club_ids(ref: ClubRef | None, entries: list) -> set[int]:
    """Bind resolver identity to unambiguous statistics-backed club IDs.

    Exact/provider affiliate IDs win. Name-only evidence is accepted only when
    it identifies one stored club ID; two unrelated IDs with the same normalized
    name remain ambiguous.
    """
    if ref is None:
        return set()
    candidates = {
        (entry.club_api_id, entry.club_name)
        for entry in entries
        if entry.club_api_id is not None and _club_ref_matches(ref, entry.club_api_id, entry.club_name)
    }
    if not candidates:
        return set()

    direct_ids = {ref.api_id, ref.organization_api_id} - {None}
    exact_ids = {club_id for club_id, _ in candidates if club_id in direct_ids}
    if exact_ids:
        return exact_ids

    full_name = _metadata_name(ref.name)
    full_name_ids = {
        club_id for club_id, club_name in candidates if full_name and _metadata_name(club_name) == full_name
    }
    if len(full_name_ids) == 1:
        return full_name_ids
    if len(full_name_ids) > 1:
        return set()

    direct_senior_ids = {
        resolve_senior_id(club_id, ref.name)
        for club_id in direct_ids
        if resolve_senior_id(club_id, ref.name) is not None
    }
    affiliate_ids = {
        club_id for club_id, club_name in candidates if resolve_senior_id(club_id, club_name) in direct_senior_ids
    }
    if affiliate_ids:
        return affiliate_ids

    candidate_ids = {club_id for club_id, _ in candidates}
    return candidate_ids if len(candidate_ids) == 1 else set()


def _stats_backed_organization_ids(ref: ClubRef | None, entries: list) -> set[int]:
    """Return all stats IDs for one uniquely anchored club organization."""
    if ref is None:
        return set()
    candidates = {
        entry.club_api_id
        for entry in entries
        if entry.club_api_id is not None and _club_ref_matches(ref, entry.club_api_id, entry.club_name)
    }
    if not candidates:
        return set()
    direct_ids = {ref.api_id, ref.organization_api_id} - {None}
    if candidates & direct_ids:
        return candidates
    anchor_ids = _stats_backed_club_ids(ref, entries)
    return candidates if len(anchor_ids) == 1 else set()


def _raw_club_logo(event, direction: str) -> str:
    """Best-effort logo lookup without sacrificing the resolver's raw IDs."""
    raw = event.event.raw
    if not isinstance(raw, Mapping):
        raw = getattr(raw, "raw", None)
    if not isinstance(raw, Mapping):
        return ""
    teams = raw.get("teams")
    if not isinstance(teams, Mapping):
        return ""
    club = teams.get(direction)
    if not isinstance(club, Mapping):
        return ""
    logo = club.get("logo")
    return logo if isinstance(logo, str) else ""


def _stat_int(value) -> int | None:
    """Coerce an API-Football stat field to int, preserving NULL.

    Rich per-season fields are frequently null/absent; a missing field must
    stay NULL (unknown), never collapse to 0 (a real observed zero). Accepts
    numeric strings and percentage strings like "82%".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        value = value.strip().rstrip("%").strip()
        if not value:
            return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _stat_float(value) -> float | None:
    """Coerce an API-Football stat field to float, preserving NULL (e.g. rating)."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Regex to extract a specific level token from a club name.
# Ordered so longer / more specific tokens match first (U23 before U2, etc).
_CLUB_NAME_LEVEL_RE = re.compile(
    r"\b(U15|U16|U17|U18|U19|U21|U23|Reserves?|Development|Youth|Academy|II|B)\b",
    re.IGNORECASE,
)


def _derive_current_level_from_club_name(club_name: str | None, fallback: str = "First Team") -> str:
    """Infer a player's level from their destination club name.

    Used on the transfer-override path in _update_journey_aggregates so a
    return to a youth/reserve team does not get mislabelled as First Team.
    Before this helper existed the override path hardcoded 'First Team',
    which caused players whose journey was overridden to a '<Club> U21'
    destination to be classified as first_team at the parent club
    (see the O. Hammond incident).

    >>> _derive_current_level_from_club_name('Nottingham Forest U21')
    'U21'
    >>> _derive_current_level_from_club_name('Arsenal Reserves')
    'Reserve'
    >>> _derive_current_level_from_club_name('Nottingham Forest')
    'First Team'
    """
    if not club_name:
        return fallback
    match = _CLUB_NAME_LEVEL_RE.search(club_name)
    if not match:
        return fallback
    token = match.group(1).lower()
    mapping = {
        "u15": "U15",
        "u16": "U16",
        "u17": "U17",
        "u18": "U18",
        "u19": "U19",
        "u21": "U21",
        "u23": "U23",
        "reserve": "Reserve",
        "reserves": "Reserve",
        "ii": "Reserve",
        "b": "Reserve",
        "youth": "U18",
        "academy": "U18",
        "development": "U21",
    }
    return mapping.get(token, fallback)


class JourneySyncService:
    """Service for syncing player journey data from API-Football"""

    # Delegate to shared utility (kept as class attr for backward compat)
    YOUTH_SUFFIXES = _YOUTH_SUFFIXES_RE

    # Patterns to detect youth/academy levels
    LEVEL_PATTERNS = {
        "U15": ["u15", "under 15", "under-15"],
        "U16": ["u16", "under 16", "under-16"],
        "U17": ["u17", "under 17", "under-17"],
        "U18": ["u18", "under 18", "under-18", "youth cup"],
        "U19": ["u19", "under 19", "under-19", "youth league"],
        "U21": ["u21", "under 21", "under-21"],
        "U23": [
            "u23",
            "under 23",
            "under-23",
            "premier league 2",
            "pl2",
            "development squad",
            "development league",
            "efl development",
        ],
        "Reserve": ["reserve", "b team", " ii", " b ", "second team"],
    }

    # Top-flight leagues that indicate first team level
    TOP_LEAGUES = [
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "eredivisie",
        "primeira liga",
        "scottish premiership",
        "fa cup",
        "league cup",
        "efl cup",
        "carabao",
        "champions league",
        "europa league",
        "conference league",
        "copa del rey",
        "coppa italia",
        "dfb-pokal",
        "coupe de france",
        "community shield",
        "supercopa",
        "super cup",
    ]

    # Delegate to shared utility
    INTERNATIONAL_PATTERNS = _INTERNATIONAL_PATTERNS

    def __init__(self, api_client: APIFootballClient | None = None, *, database_only: bool = False):
        """Initialize with an API client unless this is an explicit DB repair."""
        if database_only and api_client is not None:
            raise ValueError("database_only cannot be combined with api_client")
        self.api = None if database_only else (api_client or APIFootballClient())

    def _competition_start_months(self, entries: list) -> dict[int, int]:
        """Load configured league boundaries once for a batch of entries."""
        from flask import has_app_context

        if not has_app_context():
            return {}
        league_ids = {
            int(entry.league_api_id) for entry in entries if getattr(entry, "league_api_id", None) is not None
        }
        if not league_ids:
            return {}
        rows = LeagueSeasonConfig.query.filter(LeagueSeasonConfig.league_api_id.in_(league_ids)).all()
        starts = {}
        for row in rows:
            if isinstance(row.rollover_month, int) and 1 <= row.rollover_month <= 12:
                starts[row.league_api_id] = row.rollover_month
            elif (row.season_type or "").strip().casefold() == "calendar":
                starts[row.league_api_id] = 1
        return starts

    @staticmethod
    def _entry_start_month(entry, start_months: Mapping[int, int] | None = None) -> int:
        explicit = getattr(entry, "season_start_month", None)
        if isinstance(explicit, int) and 1 <= explicit <= 12:
            return explicit
        league_id = getattr(entry, "league_api_id", None)
        return (start_months or {}).get(league_id, 7)

    def _resolution_start_month(self, entries: list, start_months: Mapping[int, int] | None = None) -> int:
        """Use the freshest domestic statistics competition as resolver context."""
        domestic = [entry for entry in entries if not getattr(entry, "is_international", False)]
        if not domestic:
            return 7
        latest = max(
            domestic,
            key=lambda entry: (
                getattr(entry, "season", 0) or 0,
                getattr(entry, "sort_priority", 0) or 0,
                getattr(entry, "transfer_date", None) or "",
            ),
        )
        return self._entry_start_month(latest, start_months)

    @staticmethod
    def _capture_transfer_metadata(entries: list) -> tuple[dict, dict]:
        exact = {}
        by_name = {}
        for entry in entries:
            if not (entry.entry_type == "loan" or entry.transfer_date or entry.transfer_fee):
                continue
            value = (entry.entry_type == "loan", entry.transfer_date, entry.transfer_fee)
            exact[(entry.season, entry.club_api_id, entry.league_api_id)] = value
            name_key = (
                entry.season,
                _metadata_name(entry.club_name),
                _metadata_name(getattr(entry, "league_name", None)),
            )
            if name_key[1] and name_key[2]:
                by_name[name_key] = value
        return exact, by_name

    @staticmethod
    def _restore_transfer_metadata(entry, prior_metadata: tuple[dict, dict]) -> None:
        exact, by_name = prior_metadata
        prior = exact.get((entry.season, entry.club_api_id, entry.league_api_id))
        if prior is None:
            prior = by_name.get(
                (
                    entry.season,
                    _metadata_name(entry.club_name),
                    _metadata_name(getattr(entry, "league_name", None)),
                )
            )
        if prior is None:
            return
        was_loan, entry.transfer_date, entry.transfer_fee = prior
        if was_loan:
            entry.entry_type = "loan"

    def sync_player(self, player_api_id: int, force_full: bool = False, heartbeat_fn=None) -> PlayerJourney | None:
        """
        Sync complete journey for a player.

        Args:
            player_api_id: API-Football player ID
            force_full: If True, re-sync all seasons even if already synced
            heartbeat_fn: Optional callable invoked between API stages to signal liveness

        Returns:
            PlayerJourney record or None if sync failed
        """
        logger.info(f"Starting journey sync for player {player_api_id}")

        try:
            # Get or create journey record (handle race conditions)
            journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
            if not journey:
                journey = PlayerJourney(player_api_id=player_api_id)
                db.session.add(journey)
                try:
                    db.session.flush()
                except IntegrityError:
                    db.session.rollback()
                    journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
                    if not journey:
                        raise

            # Get all seasons for this player
            seasons = self._get_player_seasons(player_api_id)
            if not seasons:
                journey.sync_error = "No seasons found for player"
                db.session.commit()
                return journey

            if heartbeat_fn:
                heartbeat_fn()

            logger.info(f"Found {len(seasons)} seasons for player {player_api_id}: {seasons}")

            # Determine which seasons to sync
            already_synced = set(journey.seasons_synced or [])
            if force_full:
                seasons_to_sync = seasons
            else:
                # Always sync current and previous season, plus any new ones
                current_year = datetime.now().year
                seasons_to_sync = [s for s in seasons if s not in already_synced or s >= current_year - 1]

            # Fetch transfer history for loan classification
            transfers = self._get_player_transfers(player_api_id)
            sync_as_of = _transfer_as_of()
            transfer_resolution = None
            prior_transfer_metadata = ({}, {})
            if transfers is None:
                prior_transfer_metadata = self._capture_transfer_metadata(
                    PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
                )

            if heartbeat_fn:
                heartbeat_fn()

            # Fetch and process each season
            all_entries = []
            player_info = None

            for season_idx, season in enumerate(sorted(seasons_to_sync)):
                try:
                    player_data = self._get_player_season_data(player_api_id, season)
                    if not player_data:
                        continue

                    # Extract player info from first successful response
                    if not player_info and "player" in player_data:
                        player_info = player_data["player"]

                    # Process statistics into entries
                    for stat in player_data.get("statistics", []):
                        if not self._is_official_competition(stat):
                            logger.debug(f"Skipping non-official competition: {stat.get('league', {}).get('name')}")
                            continue
                        entry = self._create_entry_from_stat(journey.id, season, stat, player_api_id)
                        if entry:
                            all_entries.append(entry)

                except Exception as e:
                    logger.warning(f"Failed to fetch season {season} for player {player_api_id}: {e}")
                    continue

                if heartbeat_fn and (season_idx + 1) % 3 == 0:
                    heartbeat_fn()

            if transfers is not None:
                calendar_entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all() + all_entries
                start_months = self._competition_start_months(calendar_entries)
                resolution_start_month = self._resolution_start_month(calendar_entries, start_months)
                initial_owner = self._derive_transfer_initial_owner(journey, all_entries, transfers)
                transfer_resolution = resolve_transfer_state(
                    transfers,
                    as_of=sync_as_of,
                    initial_owner=initial_owner,
                    season_start_month=resolution_start_month,
                )

            # Correct club IDs for players who transferred — API-Football
            # retroactively returns the current team for historical seasons
            self._correct_club_ids_from_transfers(
                all_entries,
                transfers,
                transfer_resolution=transfer_resolution,
                as_of=sync_as_of,
            )

            # Merge entries that share (club, league, season) after correction
            all_entries = self._merge_corrected_duplicates(all_entries)

            # Deduplicate entries with identical stat fingerprints
            all_entries = self._deduplicate_entries(all_entries)

            if transfer_resolution is not None:
                # Classify loan entries based on chronological transfer state.
                self._apply_loan_classification(all_entries, transfer_resolution)

                # A later permanent move replaces stale loan metadata from an
                # earlier episode and carries its raw fee into non-loan entries.
                self._apply_permanent_transfer_dates(
                    all_entries,
                    transfers,
                    transfer_resolution=transfer_resolution,
                    as_of=sync_as_of,
                )
            else:
                # A failed fetch is not an empty history. Preserve matching
                # durable entry metadata instead of falsely clearing known
                # loans/dates/fees while still accepting fresh statistics.
                for entry in all_entries:
                    self._restore_transfer_metadata(entry, prior_transfer_metadata)

            # Reclassify youth entries as 'development' or 'integration'
            # based on first-team history, transfer records, and age
            self._apply_development_classification(
                all_entries,
                transfers=transfers,
                birth_date=(player_info or {}).get("birth", {}).get("date"),
                transfer_resolution=transfer_resolution,
                as_of=sync_as_of,
            )

            # Update player info
            if player_info:
                incoming_name = clean_name(player_info.get("name")) or None
                # Never overwrite a real name with a placeholder
                if incoming_name and (not journey.player_name or not is_placeholder_name(incoming_name)):
                    journey.player_name = incoming_name
                journey.player_photo = player_info.get("photo")
                birth = player_info.get("birth", {})
                journey.birth_date = birth.get("date")
                journey.birth_country = birth.get("country")
                journey.nationality = player_info.get("nationality")

            # Remove old entries for synced seasons and add new ones
            if all_entries:
                synced_seasons = set(e.season for e in all_entries)
                PlayerJourneyEntry.query.filter(
                    PlayerJourneyEntry.journey_id == journey.id, PlayerJourneyEntry.season.in_(synced_seasons)
                ).delete(synchronize_session="fetch")

                for entry in all_entries:
                    entry.journey_id = journey.id
                    db.session.add(entry)

            db.session.flush()
            rollup_seasons = set(seasons_to_sync)
            if transfer_resolution is not None:
                persisted_entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
                reclassified = self._reclassify_all_history(
                    journey,
                    persisted_entries,
                    transfers,
                    transfer_resolution,
                    as_of=sync_as_of,
                )
                rollup_seasons.update(reclassified["changed_seasons"])
            else:
                # Failed transfer fetch: accept fresh statistics while preserving
                # the previously evidenced transfer classification/status.
                self._update_journey_aggregates(
                    journey,
                    transfers=None,
                    transfer_resolution=None,
                    as_of=sync_as_of,
                )

            # Auto-geocode missing club locations
            try:
                self._auto_geocode_clubs(journey)
            except Exception as e:
                logger.warning(f"_auto_geocode_clubs failed for player {player_api_id}: {e}")

            # Update sync tracking
            journey.seasons_synced = sorted(set((journey.seasons_synced or []) + seasons_to_sync))
            journey.last_synced_at = datetime.now(UTC)
            journey.sync_error = None

            # Keep derived rollup failures isolated from the API-expensive
            # journey write. The SAVEPOINT rolls back only partial rollup rows;
            # a later repair/cold-build can reconstruct them from the journey.
            try:
                db.session.flush()
                with db.session.begin_nested():
                    for _rollup_season in sorted(rollup_seasons):
                        refresh_season_rollup(
                            player_api_id,
                            season=_rollup_season,
                            session=db.session,
                        )
            except Exception as rollup_err:
                logger.warning(
                    "season-rollup refresh failed for player %s: %s",
                    player_api_id,
                    rollup_err,
                )

            db.session.commit()
            logger.info(f"Successfully synced journey for player {player_api_id}: {len(all_entries)} entries")

            return journey

        except Exception as e:
            logger.error(f"Failed to sync journey for player {player_api_id}: {e}")
            db.session.rollback()

            # Try to save error state
            try:
                journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
                if journey:
                    journey.sync_error = str(e)
                    db.session.commit()
            except Exception as save_err:
                logger.error(f"Failed to save sync_error for player {player_api_id}: {save_err}")
                db.session.rollback()

            return None

    def _get_player_seasons(self, player_api_id: int) -> list[int]:
        """Get all seasons a player has data for"""
        try:
            response = self.api._make_request("players/seasons", {"player": player_api_id})
            seasons = response.get("response", [])
            return [int(s) for s in seasons if isinstance(s, (int, str)) and str(s).isdigit()]
        except Exception as e:
            logger.error(f"Failed to get seasons for player {player_api_id}: {e}")
            return []

    def _get_player_season_data(self, player_api_id: int, season: int) -> dict | None:
        """Get player data for a specific season"""
        try:
            response = self.api._make_request("players", {"id": player_api_id, "season": season})
            data = response.get("response", [])
            return data[0] if data else None
        except Exception as e:
            logger.error(f"Failed to get player {player_api_id} season {season}: {e}")
            return None

    def _create_entry_from_stat(
        self, journey_id: int, season: int, stat: dict, player_api_id: int | None = None
    ) -> PlayerJourneyEntry | None:
        """Create a journey entry from API-Football statistics block.

        Persists the full rich per-season block the /players?id&season payload
        carries (shots, passes, tackles, duels, dribbles, fouls, cards,
        penalties, rating, position, keeper numbers) into the sea01 columns —
        the same payload the sync already fetched, previously discarded down to
        4 fields. Zero extra API calls. All rich fields are defensively coerced
        and may be NULL (the payload is frequently sparse).
        """
        team = stat.get("team", {})
        league = stat.get("league", {})
        games = stat.get("games", {}) or {}
        goals = stat.get("goals", {}) or {}
        shots = stat.get("shots", {}) or {}
        passes = stat.get("passes", {}) or {}
        tackles = stat.get("tackles", {}) or {}
        duels = stat.get("duels", {}) or {}
        dribbles = stat.get("dribbles", {}) or {}
        fouls = stat.get("fouls", {}) or {}
        cards = stat.get("cards", {}) or {}
        penalty = stat.get("penalty", {}) or {}

        team_id = team.get("id")
        league_id = league.get("id")

        if not team_id:
            return None

        appearances = games.get("appearences") or games.get("appearances") or 0

        team_name = team.get("name", "")
        league_name = league.get("name", "")

        # Classify the entry
        level = self._classify_level(team_name, league_name)
        entry_type = self._classify_entry_type(level, league_name)
        is_youth = level in YOUTH_LEVELS
        is_international = self._is_international(league_name)

        position = games.get("position")
        if position:
            position = str(position)[:10]

        entry = PlayerJourneyEntry(
            journey_id=journey_id,
            player_api_id=player_api_id,
            season=season,
            club_api_id=team_id,
            club_name=team_name,
            club_logo=team.get("logo"),
            league_api_id=league_id,
            league_name=league_name,
            league_country=league.get("country"),
            league_logo=league.get("logo"),
            level=level,
            entry_type=entry_type,
            is_youth=is_youth,
            is_international=is_international,
            appearances=appearances,
            goals=goals.get("total") or 0,
            assists=goals.get("assists") or 0,
            minutes=games.get("minutes") or 0,
            sort_priority=LEVEL_PRIORITY.get(level, 0),
            # Rich per-season fields (sea01) — durable archive of the free payload.
            rating=_stat_float(games.get("rating")),
            position=position,
            lineups=_stat_int(games.get("lineups")),
            shots_total=_stat_int(shots.get("total")),
            shots_on=_stat_int(shots.get("on")),
            passes_total=_stat_int(passes.get("total")),
            passes_key=_stat_int(passes.get("key")),
            passes_accuracy=_stat_int(passes.get("accuracy")),
            tackles_total=_stat_int(tackles.get("total")),
            tackles_blocks=_stat_int(tackles.get("blocks")),
            tackles_interceptions=_stat_int(tackles.get("interceptions")),
            duels_total=_stat_int(duels.get("total")),
            duels_won=_stat_int(duels.get("won")),
            dribbles_attempts=_stat_int(dribbles.get("attempts")),
            dribbles_success=_stat_int(dribbles.get("success")),
            fouls_drawn=_stat_int(fouls.get("drawn")),
            fouls_committed=_stat_int(fouls.get("committed")),
            cards_yellow=_stat_int(cards.get("yellow")),
            cards_red=_stat_int(cards.get("red")),
            penalty_scored=_stat_int(penalty.get("scored")),
            penalty_missed=_stat_int(penalty.get("missed")),
            penalty_saved=_stat_int(penalty.get("saved")),
            goals_conceded=_stat_int(goals.get("conceded")),
            saves=_stat_int(goals.get("saves")),
            stats_source="journey-api",
            stats_synced_at=datetime.now(UTC),
        )

        return entry

    def _classify_level(self, team_name: str, league_name: str) -> str:
        """Determine the level (U18, U21, First Team, etc.) from team/league names"""
        team_lower = team_name.lower()
        league_lower = league_name.lower()
        combined = f"{team_lower} {league_lower}"

        # Check for youth levels
        for level, patterns in self.LEVEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in combined:
                    return level

        # Check for international
        if self._is_international(league_name):
            # Check if it's youth international
            if any(x in league_lower for x in ["u17", "u18", "u19", "u20", "u21", "u23", "youth"]):
                return "International Youth"
            return "International"

        # Check for top-flight leagues (first team)
        for top_league in self.TOP_LEAGUES:
            if top_league in league_lower:
                return "First Team"

        # Default to first team for unrecognized leagues
        return "First Team"

    def _classify_entry_type(self, level: str, league_name: str) -> str:
        """Classify entry type (academy, first_team, international, etc.)"""
        if "International" in level:
            return "international"
        if level in YOUTH_LEVELS:
            return "academy"
        return "first_team"

    def _is_international(self, league_name: str) -> bool:
        """Check if league is international"""
        return is_international_competition(league_name)

    def _is_official_competition(self, stat: dict) -> bool:
        """
        Check if a stat block represents an official competition.

        Uses API-Football's league_id assignment as the allowlist:
        - Non-null league_id = API-Football recognizes it as official
        - Null league_id + youth team pattern = kept (youth cups sometimes lack IDs)
        - Null league_id + international = kept
        - Null league_id + none of the above = filtered (preseason/friendly)
        """
        league = stat.get("league", {})
        team = stat.get("team", {})
        league_id = league.get("id")

        # Non-null league_id = API-Football recognizes it as official
        if league_id is not None:
            return True

        # Null league_id: only keep if youth team or international
        team_name = (team.get("name") or "").lower()

        # Youth teams (FA Youth Cup etc. sometimes lack league IDs)
        for pattern in ["u15", "u16", "u17", "u18", "u19", "u20", "u21", "u23"]:
            if pattern in team_name:
                return True

        # International competitions
        if self._is_international(league.get("name", "")):
            return True

        return False

    def _get_player_transfers(self, player_api_id: int) -> list | None:
        """
        Get transfer records for a player.

        Calls the API client's cached get_player_transfers method.
        Returns a flat list on success (including ``[]`` for a successful empty
        history) and ``None`` on fetch failure. The distinction prevents a
        transient provider/cache error from clearing known transfer state.
        """
        try:
            data = self.api.get_player_transfers(player_api_id)
            # API returns list of player blocks, each with a 'transfers' list
            transfers = []
            for block in data:
                transfers.extend(block.get("transfers", []))
            return transfers
        except Exception as e:
            logger.warning(f"Failed to get transfers for player {player_api_id}: {e}")
            return None

    def _resolve_durable_transfer_state(
        self,
        journey: PlayerJourney,
        entries: list,
        *,
        as_of: date | str | None = None,
    ) -> TransferResolution | None:
        """Resolve locally persisted transfer evidence without provider I/O.

        ``None`` means no durable evidence exists and callers must leave stored
        status fields unchanged. ORM rows expose the resolver's flattened event
        attributes directly, so their raw types, endpoints, and dates retain the
        same chronology/topology semantics as an in-sync provider payload.
        """
        rows = (
            PlayerTransferEvent.query.filter_by(player_api_id=journey.player_api_id)
            .order_by(PlayerTransferEvent.transfer_date, PlayerTransferEvent.id)
            .all()
        )
        if not rows:
            return None

        start_months = self._competition_start_months(entries)
        resolution_start_month = self._resolution_start_month(entries, start_months)
        initial_owner = self._derive_transfer_initial_owner(journey, entries, rows)
        return resolve_transfer_state(
            rows,
            as_of=_transfer_as_of(as_of),
            initial_owner=initial_owner,
            season_start_month=resolution_start_month,
        )

    @staticmethod
    def _entry_reclassification_state(entry) -> tuple:
        return (
            entry.club_api_id,
            entry.club_name,
            entry.league_api_id,
            entry.league_name,
            entry.level,
            entry.entry_type,
            entry.is_youth,
            entry.transfer_date,
            entry.transfer_fee,
        )

    def _reclassify_all_history(
        self,
        journey: PlayerJourney,
        entries: list,
        transfers: list,
        resolution: TransferResolution,
        *,
        as_of: date | str | None = None,
    ) -> dict:
        """Reclassify every stored entry and recompute all transfer consumers."""
        before = {
            entry.id: (entry.season, self._entry_reclassification_state(entry))
            for entry in entries
            if entry.id is not None
        }

        self._correct_club_ids_from_transfers(
            entries,
            transfers,
            transfer_resolution=resolution,
            as_of=as_of,
        )
        merged_entries = self._merge_corrected_duplicates(entries)
        kept_ids = {entry.id for entry in merged_entries if entry.id is not None}
        for entry in entries:
            if entry.id is not None and entry.id not in kept_ids:
                db.session.delete(entry)
        entries = merged_entries

        self._apply_loan_classification(entries, resolution)
        self._apply_permanent_transfer_dates(
            entries,
            transfers,
            transfer_resolution=resolution,
            as_of=as_of,
        )
        self._apply_development_classification(
            entries,
            transfers=transfers,
            birth_date=journey.birth_date,
            transfer_resolution=resolution,
            as_of=as_of,
        )
        db.session.flush()

        self._update_journey_aggregates(
            journey,
            transfers=transfers,
            transfer_resolution=resolution,
            as_of=as_of,
        )

        changed_seasons = {
            season
            for entry_id, (season, state) in before.items()
            if entry_id not in kept_ids
            or next(
                (self._entry_reclassification_state(entry) != state for entry in entries if entry.id == entry_id),
                True,
            )
        }
        entry_seasons = {entry.season for entry in entries if entry.season is not None}
        return {
            "resolution": resolution,
            "changed_seasons": changed_seasons,
            "entry_seasons": entry_seasons,
        }

    def reclassify_from_durable_transfer_events(
        self,
        journey: PlayerJourney,
        *,
        as_of: date | str | None = None,
    ) -> dict | None:
        """Run the all-history reclassifier using only locally stored evidence.

        ``None`` is the conservative zero-evidence result: tre01 stores events,
        not a successful-empty coverage marker, so absence cannot distinguish an
        authoritative empty history from failure or not-yet-attempted.
        """
        rows = (
            PlayerTransferEvent.query.filter_by(player_api_id=journey.player_api_id)
            .order_by(PlayerTransferEvent.transfer_date, PlayerTransferEvent.id)
            .all()
        )
        return self.reclassify_from_transfer_events(journey, rows, as_of=as_of)

    def reclassify_from_transfer_events(
        self,
        journey: PlayerJourney,
        transfers: list,
        *,
        as_of: date | str | None = None,
    ) -> dict | None:
        """Run the all-history reclassifier for supplied non-empty evidence.

        The durable wrapper above uses persisted ORM rows. Manual-transfer dry
        runs add one transient API-shaped dictionary to those same rows so the
        preview exercises this exact resolver/classifier path without inserting
        a row or consuming a PostgreSQL sequence.
        """
        if not transfers:
            return None
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        start_months = self._competition_start_months(entries)
        initial_owner = self._derive_transfer_initial_owner(journey, entries, transfers)
        resolution = resolve_transfer_state(
            transfers,
            as_of=_transfer_as_of(as_of),
            initial_owner=initial_owner,
            season_start_month=self._resolution_start_month(entries, start_months),
        )
        return self._reclassify_all_history(
            journey,
            entries,
            transfers,
            resolution,
            as_of=as_of,
        )

    def _derive_transfer_initial_owner(self, journey, entries: list, transfers: list) -> dict | None:
        """Seed a mid-stream resolver only from corroborated academy evidence.

        A lone first-event ``N/A`` is directional only when we already know
        which endpoint is the player's owning/origin organisation. Persisted
        origin/academy attribution and pre-event youth entries are defensible
        evidence; senior statistics alone are not (they may belong to a
        borrower). Ambiguous or absent evidence deliberately returns ``None``.
        """
        normalized = normalize_transfer_events(transfers).events
        if not normalized:
            return None
        first_event = normalized[0]

        evidence: list[tuple[int | None, str | None]] = []
        origin_id = getattr(journey, "origin_club_api_id", None)
        origin_name = getattr(journey, "origin_club_name", None)
        if origin_id or origin_name:
            evidence.append((origin_id, origin_name))

        for academy_id in getattr(journey, "academy_club_ids", None) or []:
            evidence.append((academy_id, None))

        # Only youth evidence strictly predating the first event's year is
        # safe: same-season destination U21 statistics may be post-signing
        # integration rather than proof of academy ownership.
        for entry in entries:
            if (
                entry.is_youth
                and not entry.is_international
                and entry.season is not None
                and entry.season < first_event.transfer_date.year
                and entry.entry_type in ("academy", "development")
            ):
                evidence.append((entry.club_api_id, entry.club_name))

        matched: dict[str, ClubRef] = {}
        for endpoint in (first_event.out_club, first_event.in_club):
            if any(_club_ref_matches(endpoint, club_id, club_name) for club_id, club_name in evidence):
                matched[endpoint.organization_key] = endpoint

        if len(matched) != 1:
            return None
        owner = next(iter(matched.values()))
        owner_id = owner.organization_api_id or owner.api_id
        if owner_id is None:
            return None
        return {
            "id": owner_id,
            "name": senior_base_name(owner.name) or owner.name,
        }

    def _build_transfer_timeline(
        self,
        transfers: list,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ) -> list:
        """Return the legacy dict projection of chronological loan episodes.

        The public helper shape remains compatible for scripts/tests, but its
        semantics now come exclusively from ``resolve_transfer_state``: input
        order is irrelevant, conversions close episodes, and re-loans remain
        distinct.
        """
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        if resolution is None:
            return []
        return [
            {
                "club_id": episode.loan_club.api_id,
                "club_name": episode.loan_club.name,
                "parent_club_id": episode.owner.api_id,
                "start_date": episode.start_date.isoformat(),
                "end_date": episode.end_date.isoformat() if episode.end_date else None,
            }
            for episode in resolution.loan_episodes
        ]

    def _loan_overlaps_season(
        self,
        loan: LoanEpisode | Mapping,
        season: int,
        *,
        start_month: int = 7,
    ) -> bool:
        """Compatibility wrapper for the resolver's half-open season helper."""
        return loan_episode_overlaps_season(loan, season, start_month=start_month)

    def _deduplicate_entries(self, entries: list) -> list:
        """
        Remove duplicate entries based on stat fingerprint.

        Fingerprint: (season, appearances, minutes, goals, assists)

        When duplicates found:
        - Prefer youth entries (is_youth=True) over senior
        - If no youth entry, prefer lowest sort_priority
        """
        from collections import defaultdict

        groups = defaultdict(list)
        for entry in entries:
            fingerprint = (
                entry.season,
                entry.appearances,
                entry.minutes,
                entry.goals,
                entry.assists,
            )
            groups[fingerprint].append(entry)

        result = []
        for fingerprint, group in groups.items():
            if len(group) == 1:
                result.append(group[0])
                continue

            # Multiple entries with same fingerprint — pick the best one
            youth_entries = [e for e in group if e.is_youth]
            if youth_entries:
                # Prefer youth entry (stats often duplicated UP from youth to senior)
                winner = min(youth_entries, key=lambda e: e.sort_priority)
            else:
                winner = min(group, key=lambda e: e.sort_priority)

            removed = [e for e in group if e is not winner]
            for e in removed:
                logger.debug(
                    f"Dedup: removed {e.club_name}/{e.league_name} season {e.season} "
                    f"(dup of {winner.club_name}/{winner.league_name})"
                )

            result.append(winner)

        return result

    def _apply_loan_classification(self, entries: list, loan_timeline: list | TransferResolution):
        """Classify entries from distinct resolver loan episodes.

        When multiple episodes reach the same borrower, the latest episode
        overlapping the entry's season wins.  A stale legacy ``loan`` value is
        cleared when no episode overlaps, allowing a later permanent move to
        replace both its type and date.
        """
        episodes = (
            list(loan_timeline.loan_episodes)
            if isinstance(loan_timeline, TransferResolution)
            else list(loan_timeline or [])
        )
        start_months = self._competition_start_months(entries)

        for entry in entries:
            if entry.is_international:
                continue

            matching = []
            for episode in episodes:
                if isinstance(episode, LoanEpisode):
                    club_matches = _club_ref_matches(episode.loan_club, entry.club_api_id, entry.club_name)
                    start_date = episode.start_date
                else:
                    club_matches = entry.club_api_id == episode.get("club_id")
                    raw_start = episode.get("start_date")
                    try:
                        start_date = date.fromisoformat(str(raw_start))
                    except (TypeError, ValueError):
                        continue
                if club_matches and self._loan_overlaps_season(
                    episode,
                    entry.season,
                    start_month=self._entry_start_month(entry, start_months),
                ):
                    matching.append((start_date, episode))

            if not matching:
                if entry.entry_type == "loan":
                    entry.entry_type = "academy" if entry.is_youth else "first_team"
                    entry.transfer_date = None
                    entry.transfer_fee = None
                continue

            _, effective_episode = max(matching, key=lambda item: item[0])
            raw_start = (
                effective_episode.start_date
                if isinstance(effective_episode, LoanEpisode)
                else effective_episode.get("start_date")
            )
            entry.entry_type = "loan"
            entry.transfer_date = raw_start.isoformat() if isinstance(raw_start, date) else raw_start
            entry.transfer_fee = None

    def _apply_permanent_transfer_dates(
        self,
        entries: list,
        transfers: list | TransferResolution,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ):
        """Apply resolver-classified permanent dates and raw fees.

        Existing dates no longer block a later definitive move.  Entries that
        still overlap a loan episode keep their loan start unless a permanent
        conversion occurs later inside that same season. Because one entry
        represents the whole season, the later definitive state wins: the entry
        becomes non-loan from the conversion date and carries its verbatim fee.
        A conversion on the next configured season boundary remains outside
        the prior season.
        """
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        if resolution is None:
            return
        permanent_moves = [event for event in resolution.events if event.kind == "permanent"]
        if not permanent_moves:
            return
        start_months = self._competition_start_months(entries)

        for entry in entries:
            if entry.is_international:
                continue
            try:
                season_start, season_end = _season_bounds(
                    entry.season,
                    self._entry_start_month(entry, start_months),
                )
                window_end = _season_grace_end(season_end)
            except (TypeError, ValueError):
                continue
            candidates = [
                event
                for event in permanent_moves
                if event.transfer_date <= window_end
                and _club_ref_matches(event.in_club, entry.club_api_id, entry.club_name)
            ]
            if not candidates:
                continue

            if entry.entry_type == "loan":
                try:
                    loan_start = date.fromisoformat(str(entry.transfer_date))
                except (TypeError, ValueError):
                    loan_start = season_start
                in_season_conversions = [
                    event
                    for event in candidates
                    if season_start <= event.transfer_date < season_end and event.transfer_date >= loan_start
                ]
                if not in_season_conversions:
                    continue
                best_move = max(in_season_conversions, key=lambda event: event.transfer_date)
                entry.entry_type = "academy" if entry.is_youth else "first_team"
            else:
                best_move = max(candidates, key=lambda event: event.transfer_date)

            entry.transfer_date = best_move.transfer_date.isoformat()
            entry.transfer_fee = best_move.fee
            logger.debug(
                "Set permanent transfer metadata date=%s fee=%r for %s season %s",
                entry.transfer_date,
                entry.transfer_fee,
                entry.club_name,
                entry.season,
            )

    def _correct_club_ids_from_transfers(
        self,
        entries: list,
        transfers: list | TransferResolution,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ):
        """Correct club_api_id for entries where API-Football returned the
        player's current team instead of the historical team.

        After a permanent transfer, API-Football may retroactively return the
        new club's ID for historical seasons.  We use the transfer history to
        detect this and override club_api_id with the correct team.
        """
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        if resolution is None:
            return

        # Only topology-resolved permanent moves correct historical clubs. A
        # reverse-direction N/A return is excluded; a same-direction N/A
        # conversion is included by the same policy as every other consumer.
        # Provider IDs enrich identity but are not mandatory: a name-only
        # endpoint may bind to exactly one stats-backed journey club. Zero or
        # multiple matches remain ambiguous and are left untouched.
        evidence_entries = [entry for entry in entries if not entry.is_international]

        def _evidence_id(ref: ClubRef) -> int | None:
            direct_id = ref.api_id or ref.organization_api_id
            matching_ids = _stats_backed_club_ids(ref, evidence_entries)
            if direct_id in matching_ids:
                return direct_id
            if len(matching_ids) == 1:
                return next(iter(matching_ids))
            if not matching_ids and not any(
                _club_ref_matches(ref, entry.club_api_id, entry.club_name) for entry in evidence_entries
            ):
                return direct_id
            return None

        permanent_moves = []
        for event in resolution.events:
            if event.kind != "permanent":
                continue
            in_id = _evidence_id(event.in_club)
            out_id = _evidence_id(event.out_club)
            if in_id is None or out_id is None:
                continue
            permanent_moves.append(
                {
                    "date": event.transfer_date.isoformat(),
                    "in_id": in_id,
                    "in_name": event.in_club.name or "",
                    "in_logo": _raw_club_logo(event, "in"),
                    "out_id": out_id,
                    "out_name": event.out_club.name or "",
                    "out_logo": _raw_club_logo(event, "out"),
                }
            )

        if not permanent_moves:
            return
        start_months = self._competition_start_months(entries)

        # Clubs the player has independent evidence for (journey entries are
        # derived from the statistics feed). Used to reject bogus transfers:
        # API-Football occasionally returns a duplicate transfer into the real
        # destination from an unrelated lower-league club it invented — e.g.
        # "Newcastle ⟸ Ashington AFC" alongside the genuine "Newcastle ⟸
        # Nottingham Forest". Correcting a season to that phantom source
        # manufactures a club the player never played for.
        evidence_club_ids = {e.club_api_id for e in evidence_entries}

        moves_by_in: dict[int, list] = {}
        for move in permanent_moves:
            moves_by_in.setdefault(move["in_id"], []).append(move)

        def _source_move(in_id, season_end):
            """The transfer that explains being at ``in_id`` for a season that
            ended before it: the earliest permanent move INTO ``in_id`` after the
            season. When several moves share that destination (a contradictory
            feed), prefer one whose source club the player actually has evidence
            for, which discards the invented lower-league transfer."""
            candidates = [m for m in moves_by_in.get(in_id, []) if m["date"] > season_end]
            if not candidates:
                return None
            corroborated = [m for m in candidates if m["out_id"] in evidence_club_ids]
            pool = corroborated or candidates
            return min(pool, key=lambda m: m["date"])

        corrected = 0
        for entry in entries:
            if entry.is_international:
                continue

            # A conversion immediately after a season must not make the real
            # borrower statistics look retroactively misattributed (Hall /
            # Knauff). The resolved historical loan episode is authoritative.
            if any(
                _club_ref_matches(episode.loan_club, entry.club_api_id, entry.club_name)
                and self._loan_overlaps_season(
                    episode,
                    entry.season,
                    start_month=self._entry_start_month(entry, start_months),
                )
                for episode in resolution.loan_episodes
            ):
                continue

            try:
                _, season_end_exclusive = _season_bounds(
                    entry.season,
                    self._entry_start_month(entry, start_months),
                )
            except (TypeError, ValueError):
                continue
            season_end = (season_end_exclusive - timedelta(days=1)).isoformat()

            # Walk the transfer chain back until the club is no longer the
            # destination of a post-season transfer. A single hop only repairs the
            # season directly before the latest move; older seasons need the full
            # chain (e.g. Newcastle → Forest → Man Utd), otherwise they collapse
            # onto the wrong club. ``visited`` guards against cyclic feed data.
            club_id = entry.club_api_id
            final_move = None
            visited: set[int] = set()
            while club_id not in visited:
                visited.add(club_id)
                move = _source_move(club_id, season_end)
                if move is None or move["out_id"] == club_id:
                    break
                club_id = move["out_id"]
                final_move = move

            if final_move is not None and club_id != entry.club_api_id:
                logger.info(
                    f"Correcting entry: {entry.club_name} (season {entry.season}) "
                    f"→ {final_move['out_name']} (walked transfer chain back to the "
                    f"club active before season end {season_end})"
                )
                entry.club_api_id = final_move["out_id"]
                entry.club_name = final_move["out_name"]
                entry.club_logo = final_move["out_logo"]
                corrected += 1

        if corrected:
            logger.info(f"Corrected {corrected} entries with wrong club from post-transfer API data")

    def _merge_corrected_duplicates(self, entries: list) -> list:
        """Merge entries that share (club_api_id, league_api_id, season).

        After _correct_club_ids_from_transfers, a corrected entry may now
        share the same club+league+season as an existing entry. Keep the one
        with more appearances (more complete data); the whole winning entry is
        retained, so its rich per-season fields (sea01) ride along. When
        appearances tie, prefer the 'journey-api' (rich) source, then the newer
        stats_synced_at — so a duplicate never drops the richer/newer row.
        """
        from collections import defaultdict

        def _winner_key(e):
            source_rank = 1 if getattr(e, "stats_source", None) == "journey-api" else 0
            synced = getattr(e, "stats_synced_at", None)
            synced_ts = synced.timestamp() if synced else 0.0
            return (e.appearances or 0, source_rank, synced_ts)

        groups = defaultdict(list)
        for entry in entries:
            key = (entry.club_api_id, getattr(entry, "league_api_id", None), entry.season)
            groups[key].append(entry)

        result = []
        merged = 0
        for key, group in groups.items():
            if len(group) == 1:
                result.append(group[0])
                continue
            winner = max(group, key=_winner_key)
            merged += len(group) - 1
            result.append(winner)

        if merged:
            logger.info(f"Merged {merged} duplicate entries after club ID correction")

        return result

    def _apply_development_classification(
        self,
        entries: list,
        transfers=None,
        birth_date=None,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ):
        """
        Reclassify youth 'academy' entries based on the player's career context.

        Three youth categories:
        - 'academy': genuine academy product with no prior first-team
          experience anywhere (e.g. Rashford at Man Utd U19).
        - 'development': player had first-team apps at the SAME parent club
          in a prior season — senior player sent to youth for game time.
          Same-season entries (breakthrough year) stay as 'academy'.
        - 'integration': player had first-team apps at a DIFFERENT club
          before this youth entry — bought player being integrated
          (e.g. Diallo playing Man Utd U23 after Atalanta first team).

        Enhanced detection uses three signals:
        1. Journey entries (original): first-team at another club in data
        2. Transfer records: permanent transfer TO this club = not academy
        3. Age at entry: first appearance at club aged 21+ = not academy
        """
        # Build lookup: parent_base_name -> earliest first-team season
        first_team_debut_by_club = {}
        # Also track total first-team appearances per club for age/experience gate
        first_team_apps_by_club = {}
        for entry in entries:
            # A first-team spell at a borrower is not a prior permanent senior
            # career and must never disqualify the real parent academy.
            if entry.level == "First Team" and not entry.is_international and entry.entry_type != "loan":
                base_name = self._strip_youth_suffix(entry.club_name)
                existing = first_team_debut_by_club.get(base_name)
                if existing is None or entry.season < existing:
                    first_team_debut_by_club[base_name] = entry.season
                first_team_apps_by_club[base_name] = first_team_apps_by_club.get(base_name, 0) + (
                    entry.appearances or 0
                )

        # Build clubs the player was permanently transferred TO, with the
        # earliest transfer year. A permanent transfer TO a club means the
        # player is NOT an academy product of that club — academy products
        # don't need to be transferred in. The year matters for buy-backs:
        # a transfer AFTER a youth entry must not disqualify that entry
        # (academy product sold and later re-signed keeps academy status).
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        domestic_entries = [entry for entry in entries if not entry.is_international]
        permanent_transfer_destinations: list[tuple[set[int], int]] = []
        if resolution is not None:
            for event in resolution.events:
                if event.kind != "permanent":
                    continue
                year = event.transfer_date.year
                destination_ids = _stats_backed_organization_ids(event.in_club, domestic_entries)
                if destination_ids:
                    permanent_transfer_destinations.append((destination_ids, year))

        # Parse birth year for age-at-entry validation
        birth_year = None
        if birth_date:
            try:
                birth_year = int(str(birth_date)[:4])
            except (ValueError, TypeError):
                pass

        # Track earliest season per club for age-based checks
        earliest_season_at_club = {}
        for entry in entries:
            if entry.is_youth and not entry.is_international:
                base = self._strip_youth_suffix(entry.club_name)
                existing = earliest_season_at_club.get(base)
                if existing is None or entry.season < existing:
                    earliest_season_at_club[base] = entry.season

        # Pass 1: journey-entry-based classification.
        # ORDER MATTERS: the integration check must run BEFORE the same-club
        # development branch. A signed senior plays first team immediately and
        # turns out for the U21s later (rehab/fitness), so for exactly the
        # players this pass exists to catch, the development branch would fire
        # first and shield the entry from every integration check (this is how
        # Malacia's 46-minute United U21 game made United his academy origin).
        if first_team_debut_by_club:
            for entry in entries:
                if entry.entry_type != "academy" or entry.is_international:
                    continue

                parent_name = self._strip_youth_suffix(entry.club_name)
                same_club_debut = first_team_debut_by_club.get(parent_name)

                # Integration: first-team at a DIFFERENT club before or during
                # this youth season (player was bought with senior experience).
                # Gate: a young player (≤18) with few apps (≤15) at a small club
                # before joining a big academy is a normal academy transfer, not
                # an integration (e.g., Hansen-Aarøen: 7 apps at Tromso age 16,
                # then 4 years in ManU youth).
                reclassified = False
                for club_name, debut in first_team_debut_by_club.items():
                    if club_name != parent_name and debut <= entry.season:
                        if birth_year is not None:
                            age_at_other_debut = debut - birth_year
                            other_apps = first_team_apps_by_club.get(club_name, 0)
                            if age_at_other_debut <= 18 and other_apps <= 15:
                                continue
                        entry.entry_type = "integration"
                        reclassified = True
                        logger.debug(
                            f"Reclassified {entry.club_name} season {entry.season} as "
                            f"integration (first-team at {club_name} in {debut})"
                        )
                        break
                if reclassified:
                    continue

                # Development: same parent club had first-team in a prior season
                if same_club_debut is not None and entry.season > same_club_debut:
                    entry.entry_type = "development"
                    logger.debug(
                        f"Reclassified {entry.club_name} season {entry.season} as "
                        f"development (first-team debut at {parent_name} in {same_club_debut})"
                    )

        # Pass 2: transfer-based integration detection
        # If a player was permanently transferred TO a club, youth entries at
        # that club FROM THAT POINT ON are integration, not academy. Covers
        # development-typed entries too (a signing's U21 outing after a
        # same-club first-team debut). Entries that PRECEDE the transfer stay
        # untouched — an academy product sold and bought back keeps academy
        # status for their formative years.
        if permanent_transfer_destinations:
            for entry in entries:
                if entry.entry_type not in ("academy", "development") or entry.is_international:
                    continue
                matching_years = [
                    year
                    for destination_ids, year in permanent_transfer_destinations
                    if entry.club_api_id in destination_ids
                ]
                if not matching_years:
                    continue
                transfer_year = min(matching_years)
                # Teenage gate: a recorded transfer at <= 18 is an academy
                # move (youth-to-youth), not a senior signing.
                if transfer_year is not None and birth_year is not None and transfer_year - birth_year <= 18:
                    continue
                # +1 covers winter transfers landing mid-season
                if transfer_year is None or entry.season is None or transfer_year <= entry.season + 1:
                    entry.entry_type = "integration"
                    logger.debug(
                        f"Reclassified {entry.club_name} season {entry.season} as "
                        f"integration (permanent transfer destination)"
                    )

        # Pass 3: age-at-entry validation
        # If a player's FIRST appearance at a club's youth system was at age 21+,
        # they are not an academy product — they were bought as a senior player.
        # Players who joined younger and continue playing U23 at 21-22 are fine.
        if birth_year:
            for entry in entries:
                if entry.entry_type not in ("academy", "development") or entry.is_international:
                    continue
                parent_name = self._strip_youth_suffix(entry.club_name)
                first_season = earliest_season_at_club.get(parent_name)
                if first_season is not None:
                    age_at_first = first_season - birth_year
                    if age_at_first >= 21:
                        entry.entry_type = "integration"
                        logger.debug(
                            f"Reclassified {entry.club_name} season {entry.season} as "
                            f"integration (age {age_at_first} at first youth appearance, "
                            f"season {first_season})"
                        )

    def _update_journey_aggregates(
        self,
        journey: PlayerJourney,
        transfers=None,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ):
        """Update aggregate stats on the journey record"""
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()

        if not entries:
            return

        # Helper: exclude international entries (call-ups are not club moves)
        def _is_domestic(e):
            if e.is_international:
                return False
            if e.entry_type == "international":
                return False
            if "International" in (e.level or ""):
                return False
            if is_national_team(e.club_name):
                return False
            return True

        # Find origin (earliest domestic entry)
        domestic_entries = [e for e in entries if _is_domestic(e)]
        origin_entries = domestic_entries if domestic_entries else entries
        earliest = min(origin_entries, key=lambda e: (e.season, -e.sort_priority))

        if earliest.is_youth:
            # Resolve youth/reserve team to parent club
            base_name = self._strip_youth_suffix(earliest.club_name)
            resolved_id = self._resolve_parent_club_id(base_name, entries)
            if resolved_id:
                journey.origin_club_api_id = resolved_id
                journey.origin_club_name = base_name
            else:
                journey.origin_club_api_id = earliest.club_api_id
                journey.origin_club_name = base_name  # still strip suffix for display
        else:
            journey.origin_club_api_id = earliest.club_api_id
            journey.origin_club_name = earliest.club_name
        journey.origin_year = earliest.season

        # Find current club: latest season, highest priority, most recent transfer.
        if domestic_entries:
            latest_season = max(e.season for e in domestic_entries)
            latest_entries = [e for e in domestic_entries if e.season == latest_season]
            current = max(latest_entries, key=lambda e: (e.sort_priority, e.transfer_date or ""))
            journey.current_club_api_id = current.club_api_id
            journey.current_club_name = current.club_name
            journey.current_level = current.level

            # Guard: if the winning entry has 0 minutes (e.g. a League Cup squad
            # registration), check whether a sibling entry at the same club's
            # youth team has real playing time.  If so, the player's actual level
            # is the youth team, not the first-team registration.
            if (current.minutes or 0) == 0 and current.level == "First Team":
                club_stem = strip_youth_suffix(current.club_name or "")
                youth_at_same_club = [
                    e
                    for e in latest_entries
                    if e is not current
                    and e.is_youth
                    and (e.minutes or 0) > 0
                    and strip_youth_suffix(e.club_name or "") == club_stem
                ]
                if youth_at_same_club:
                    best_youth = max(youth_at_same_club, key=lambda e: e.minutes or 0)
                    journey.current_level = best_youth.level
        else:
            # Only international entries exist — use them as fallback
            latest_season = max(e.season for e in entries)
            latest_entries = [e for e in entries if e.season == latest_season]
            current = max(latest_entries, key=lambda e: (e.sort_priority, e.transfer_date or ""))
            journey.current_club_api_id = current.club_api_id
            journey.current_club_name = current.club_name
            journey.current_level = current.level

        # Find first team debut
        first_team_entries = [e for e in entries if e.level == "First Team" and not e.is_international]
        if first_team_entries:
            debut = min(first_team_entries, key=lambda e: e.season)
            journey.first_team_debut_season = debut.season
            journey.first_team_debut_club_id = debut.club_api_id
            journey.first_team_debut_club = debut.club_name
            journey.first_team_debut_competition = debut.league_name
            debut.is_first_team_debut = True

        # Calculate totals
        unique_clubs = set(e.club_api_id for e in entries if not e.is_international)
        journey.total_clubs = len(unique_clubs)

        journey.total_first_team_apps = sum(
            e.appearances for e in entries if e.level == "First Team" and not e.is_international
        )
        journey.total_youth_apps = sum(e.appearances for e in entries if e.is_youth)
        journey.total_loan_apps = sum(e.appearances for e in entries if e.entry_type == "loan")
        journey.total_goals = sum(e.goals for e in entries)
        journey.total_assists = sum(e.assists for e in entries)

        # Compute academy connections from youth entries
        compute_kwargs = {"transfers": transfers}
        if as_of is not None:
            compute_kwargs["as_of"] = as_of
        if resolution is not None:
            compute_kwargs["transfer_resolution"] = resolution
        self._compute_academy_club_ids(journey, entries, **compute_kwargs)

        # Project club + player-level current status from the same resolver
        # state. A failed fetch leaves all transfer-derived fields untouched.
        if resolution is not None:
            self.apply_resolved_current_state(journey, entries, resolution)

    def _set_current_status(
        self,
        journey: PlayerJourney,
        entries: list,
        transfers=None,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ) -> bool:
        """Set player-level loan status from the chronological current state.

        A confirmed, fresh active episode is the only state that populates
        ``current_status`` and owner. Closed or indeterminate episodes clear
        both. Without fetched or durable transfer evidence this method is a
        no-op: historical entry labels cannot prove a current loan or owner.

        Returns ``True`` when resolver evidence was applied (including a clear)
        and ``False`` when no evidence was available.
        """
        cur_id = journey.current_club_api_id
        cur_name = journey.current_club_name
        if not cur_id and not cur_name:
            journey.current_status = None
            journey.current_owner_api_id = None
            journey.current_owner_name = None
            return True

        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        if resolution is None:
            logger.info(
                "Journey %s: current status unchanged because no transfer evidence was supplied",
                getattr(journey, "id", None),
            )
            return False

        active_loan = resolution.active_loan if resolution.on_loan is True else None
        if active_loan is None or not _club_ref_matches(
            active_loan.loan_club,
            cur_id,
            cur_name,
        ):
            journey.current_status = None
            journey.current_owner_api_id = None
            journey.current_owner_name = None
            return True

        owner = resolution.current_owner
        journey.current_status = "on_loan"
        owner_id = (owner.organization_api_id or owner.api_id) if owner is not None else None
        owner_team = (
            Team.query.filter_by(team_id=owner_id, is_active=True).order_by(Team.season.desc()).first()
            if owner_id
            else None
        )
        journey.current_owner_api_id = owner_id
        journey.current_owner_name = owner_team.name if owner_team else (owner.name if owner else None)
        return True

    def apply_resolved_current_state(
        self,
        journey: PlayerJourney,
        entries: list,
        resolution: TransferResolution,
    ) -> bool:
        """Atomically project a durable resolver state onto journey current fields."""
        destination = resolution.current_club
        domestic = [entry for entry in entries if not entry.is_international and entry.season is not None]
        latest_season = None
        season_start_month = resolution.season_start_month
        if domestic:
            latest_season = max(entry.season for entry in domestic)
            latest_entries = [entry for entry in domestic if entry.season == latest_season]
            current_entry = max(
                latest_entries,
                key=lambda entry: (entry.sort_priority, entry.transfer_date or ""),
            )
            start_months = self._competition_start_months(latest_entries)
            season_start_month = self._entry_start_month(current_entry, start_months)

        if destination is not None and resolved_current_club_is_authoritative(
            resolution,
            journey.current_club_api_id,
            journey.current_club_name,
            latest_season=latest_season,
            season_start_month=season_start_month,
            season_start_day=resolution.season_start_day,
        ):
            destination_id = destination.api_id or destination.organization_api_id
            if destination_id is None:
                destination_ids = _stats_backed_club_ids(destination, domestic)
                if len(destination_ids) == 1:
                    destination_id = next(iter(destination_ids))
            journey.current_club_api_id = destination_id
            journey.current_club_name = destination.name
            if destination.name:
                journey.current_level = _derive_current_level_from_club_name(destination.name)
            else:
                journey.current_level = None

        return self._set_current_status(
            journey,
            entries,
            transfer_resolution=resolution,
        )

    def _strip_youth_suffix(self, club_name: str) -> str:
        """Strip youth team suffix to get parent club base name."""
        return strip_youth_suffix(club_name)

    def _resolve_parent_club_id(self, base_name: str, entries: list) -> int | None:
        """Resolve a youth/reserve team base name to the parent club's API ID.

        Resolution order:
        1. Senior entries in the same journey with matching club name
        2. TeamProfile exact name match
        3. Team table exact name match
        """
        # Check senior entries in the same journey
        for e in entries:
            if not e.is_youth and not e.is_international and e.club_name == base_name:
                return e.club_api_id

        # Fallback: TeamProfile exact name
        profile = TeamProfile.query.filter(TeamProfile.name == base_name).first()
        if profile:
            return profile.team_id

        # Fallback: Team table exact name
        team = Team.query.filter(Team.name == base_name).first()
        if team:
            return team.team_id

        return None

    def _retained_empty_run_attribution(self, journey, prior_academy_ids, prior_last_seasons):
        """Journey attribution to KEEP when this run resolved no academy evidence.

        An empty computation (API youth-coverage gap, or all youth entries
        filtered out) is "no evidence THIS run", not "evidence the player was
        never an academy product". Zeroing the journey's stored attribution
        outright makes the stored-attribution floor one-run-deep: a coverage
        gap spanning two nightly syncs still orphans the row on run 2, because
        ``prior_academy_ids`` (re-read from the journey) is empty by then.

        Retain exactly the SUBSET the floor would spare — clubs still inside
        the window by stored SEASON evidence, or (for a current academy kid)
        regardless of season — so the floor survives consecutive empty runs.
        Genuinely aged-out and season-less stale clubs are dropped, so they
        still deactivate as before.

        Row-local evidence counts too: the journey's per-club season map can be
        empty (legacy pre-aw18 maps, or youth entries whose seasons are NULL)
        while an ACTIVE tracked row still carries an in-window
        ``last_academy_season`` or a current-kid ``status='academy'``. Keying
        retention on the journey map alone would then drop the club here and
        strand the row (the floor and the transfer-heal requeue gate both read
        the journey map) — so an in-window row-local season / academy status is
        honoured, and the recovered season is written back into the map so the
        floor's SEASON key holds on subsequent empty runs.
        """
        from src.models.tracked_player import TrackedPlayer
        from src.utils.academy_window import academy_window_start

        window_start = academy_window_start()
        current_kid = (journey.current_level or "") in YOUTH_LEVELS

        # Collect row-local evidence keyed by the parent club's API id.
        row_season_by_club: dict[int, int] = {}
        row_academy_clubs: set[int] = set()
        if prior_academy_ids:
            for tp in TrackedPlayer.query.filter(
                TrackedPlayer.player_api_id == journey.player_api_id,
                TrackedPlayer.is_active.is_(True),
            ).all():
                club_id = tp.team.team_id if tp.team else None
                if club_id is None:
                    continue
                if tp.last_academy_season is not None:
                    prev = row_season_by_club.get(club_id)
                    if prev is None or tp.last_academy_season > prev:
                        row_season_by_club[club_id] = tp.last_academy_season
                if tp.status == "academy":
                    row_academy_clubs.add(club_id)

        retained_ids: list[int] = []
        retained_seasons: dict[str, int] = {}
        for cid in prior_academy_ids:
            season = prior_last_seasons.get(str(cid))
            row_season = row_season_by_club.get(cid)
            season_in_window = season is not None and season >= window_start
            row_season_in_window = row_season is not None and row_season >= window_start
            if not (current_kid or cid in row_academy_clubs or season_in_window or row_season_in_window):
                continue
            retained_ids.append(cid)
            # Persist the best in-window season so the floor's SEASON key holds
            # on later empty runs; prefer the journey map, fall back to the row.
            if season_in_window:
                retained_seasons[str(cid)] = season
            elif row_season_in_window:
                retained_seasons[str(cid)] = row_season
            elif season is not None:
                retained_seasons[str(cid)] = season
        return sorted(retained_ids), retained_seasons

    def _compute_academy_club_ids(
        self,
        journey: PlayerJourney,
        entries: list | None = None,
        transfers=None,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ):
        """
        Derive academy parent club IDs from youth journey entries.

        Algorithm:
        1. Collect all youth entries (is_youth=True, excluding internationals)
        2. Strip youth suffix from club name to get parent base name
        3. Resolve parent club API ID:
           - First: check non-youth entries in same journey for matching club name
           - Fallback: query TeamProfile for matching name
        4. Deduplicate and store as JSON array
        """
        if entries is None:
            entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )

        # Capture the journey's PERSISTED academy attribution BEFORE this run
        # overwrites it below. A transient run (API youth-coverage gap or a
        # tenure-gate flicker) can compute an EMPTY academy set even for an
        # established academy product; the stored-attribution floor in
        # _upsert_tracked_players uses these prior values so a transient empty
        # computation never orphans an in-window academy row (the Gore-class
        # orphan trap).
        prior_academy_ids = set(journey.academy_club_ids or [])
        prior_last_seasons = dict(journey.academy_last_seasons or {})

        youth_entries = [
            e
            for e in entries
            if e.is_youth
            and not e.is_international
            and e.entry_type in ("academy", "development")
            and not is_national_team(e.club_name)
        ]
        if not youth_entries:
            # Empty computation = "no evidence NOW", not "never an academy
            # product". Retain the stored attribution the floor would still
            # spare (in-window by SEASON, or a current kid) so the floor
            # survives consecutive empty runs instead of being zeroed after one;
            # genuinely aged-out / season-less stale clubs are dropped and their
            # rows deactivate as before.
            journey.academy_club_ids, journey.academy_last_seasons = self._retained_empty_run_attribution(
                journey, prior_academy_ids, prior_last_seasons
            )
            # Deactivate any stale tracked-player rows from prior runs
            self._upsert_tracked_players(
                journey,
                set(),
                transfers=transfers,
                transfer_resolution=resolution,
                as_of=as_of,
                prior_academy_ids=prior_academy_ids,
                prior_last_seasons=prior_last_seasons,
            )
            return

        # ── Development-only noise filter ──
        # If a player has 50+ first-team apps at a club but only 'development'
        # youth entries (no genuine 'academy' entries), those youth entries are
        # noise — e.g. an established player's one-off EFL Trophy appearance.
        # Exclude them so the club doesn't get tagged as an academy origin.
        ESTABLISHED_FT_THRESHOLD = 50
        ft_apps_by_base = {}
        for e in entries:
            if e.level == "First Team" and not e.is_international:
                base = self._strip_youth_suffix(e.club_name)
                ft_apps_by_base[base] = ft_apps_by_base.get(base, 0) + (e.appearances or 0)

        has_academy_entry = set()
        for e in youth_entries:
            if e.entry_type == "academy":
                has_academy_entry.add(self._strip_youth_suffix(e.club_name))

        youth_entries = [
            e
            for e in youth_entries
            if not (
                e.entry_type == "development"
                and self._strip_youth_suffix(e.club_name) not in has_academy_entry
                and ft_apps_by_base.get(self._strip_youth_suffix(e.club_name), 0) >= ESTABLISHED_FT_THRESHOLD
            )
        ]

        # ── Prior-senior-career filter ──
        # A 'development' entry at club C is not academy formation when the
        # player already had a first-team season at a DIFFERENT club before
        # it. That is a signing turning out for the U21s (e.g. a 46-minute
        # EFL Trophy rehab game — Malacia at Man United after five Feyenoord
        # first-team seasons), not a player developed by C's academy.
        # Loans never disqualify: an academy product loaned out young and
        # later back in the U21s keeps their parent club. Same-club debuts
        # never disqualify either (base name matches).
        first_ft_season_by_base = {}
        for e in entries:
            if (
                e.entry_type == "first_team"
                and not e.is_international
                and e.season is not None
                and not is_national_team(e.club_name)
            ):
                base = self._strip_youth_suffix(e.club_name)
                prior = first_ft_season_by_base.get(base)
                if prior is None or e.season < prior:
                    first_ft_season_by_base[base] = e.season

        def _prior_senior_elsewhere(entry):
            if entry.season is None:
                return False
            base = self._strip_youth_suffix(entry.club_name)
            return any(season < entry.season for other, season in first_ft_season_by_base.items() if other != base)

        youth_entries = [
            e
            for e in youth_entries
            if not (
                e.entry_type == "development"
                and self._strip_youth_suffix(e.club_name) not in has_academy_entry
                and _prior_senior_elsewhere(e)
            )
        ]
        if not youth_entries:
            # Empty computation = "no evidence NOW", not "never an academy
            # product". Retain the stored attribution the floor would still
            # spare (see _retained_empty_run_attribution) so the floor survives
            # consecutive empty runs instead of being zeroed after one.
            journey.academy_club_ids, journey.academy_last_seasons = self._retained_empty_run_attribution(
                journey, prior_academy_ids, prior_last_seasons
            )
            self._upsert_tracked_players(
                journey,
                set(),
                transfers=transfers,
                transfer_resolution=resolution,
                as_of=as_of,
                prior_academy_ids=prior_academy_ids,
                prior_last_seasons=prior_last_seasons,
            )
            return

        # ── Academy tenure gate ──
        # A single youth appearance (the old MIN_ACADEMY_APPEARANCES=1) tagged a
        # club as an academy origin, manufacturing phantom rows from trial /
        # cup cameos (e.g. a 1-app U18 spell at a club the player merely passed
        # through). Require real tenure: total youth apps >= 3 OR appearances
        # across >= 2 distinct youth seasons. ALWAYS exempt the player's single
        # best (rank-1) base so no one loses their sole / primary academy to
        # thin early-career API coverage. Seasons count only the already-filtered
        # youth_entries (academy/development), so an 'integration' U21 rehab game
        # can't inflate a season count.
        MIN_ACADEMY_APPEARANCES = 3
        MIN_ACADEMY_SEASONS = 2
        club_youth_apps: dict[str, int] = {}
        club_youth_seasons: dict[str, set] = {}
        for e in youth_entries:
            base = self._strip_youth_suffix(e.club_name)
            club_youth_apps[base] = club_youth_apps.get(base, 0) + (e.appearances or 0)
            if e.season is not None:
                club_youth_seasons.setdefault(base, set()).add(e.season)

        def _passes_tenure_gate(base: str) -> bool:
            return (
                club_youth_apps.get(base, 0) >= MIN_ACADEMY_APPEARANCES
                or len(club_youth_seasons.get(base, ())) >= MIN_ACADEMY_SEASONS
            )

        # Rank-1 base by (apps DESC, distinct seasons DESC) — always kept.
        ranked_bases = sorted(
            club_youth_apps.keys(),
            key=lambda b: (club_youth_apps.get(b, 0), len(club_youth_seasons.get(b, ()))),
            reverse=True,
        )
        top_base = ranked_bases[0] if ranked_bases else None

        youth_entries = [
            e
            for e in youth_entries
            if _passes_tenure_gate(self._strip_youth_suffix(e.club_name))
            or self._strip_youth_suffix(e.club_name) == top_base
        ]
        if not youth_entries:
            # Empty computation = "no evidence NOW", not "never an academy
            # product". Retain the stored attribution the floor would still
            # spare (in-window by SEASON, or a current kid) so the floor
            # survives consecutive empty runs instead of being zeroed after one;
            # genuinely aged-out / season-less stale clubs are dropped and their
            # rows deactivate as before.
            journey.academy_club_ids, journey.academy_last_seasons = self._retained_empty_run_attribution(
                journey, prior_academy_ids, prior_last_seasons
            )
            # Deactivate any stale tracked-player rows from prior runs
            self._upsert_tracked_players(
                journey,
                set(),
                transfers=transfers,
                transfer_resolution=resolution,
                as_of=as_of,
                prior_academy_ids=prior_academy_ids,
                prior_last_seasons=prior_last_seasons,
            )
            return

        # Build lookup: base_name -> api_id from non-youth, non-international entries
        senior_name_to_id = {}
        for e in entries:
            if not e.is_youth and not e.is_international:
                senior_name_to_id[e.club_name] = e.club_api_id

        # Collect league_country per base_name for country-aware fallback matching
        club_country = {}
        for e in youth_entries:
            base = self._strip_youth_suffix(e.club_name)
            if e.league_country and base not in club_country:
                club_country[base] = e.league_country

        academy_ids = set()
        last_seasons = {}  # parent api id -> most recent youth season there
        unresolved = []

        def _record(parent_id, entry):
            academy_ids.add(parent_id)
            if entry.season is not None:
                prior = last_seasons.get(parent_id)
                if prior is None or entry.season > prior:
                    last_seasons[parent_id] = entry.season

        for entry in youth_entries:
            base_name = self._strip_youth_suffix(entry.club_name)
            entry_country = club_country.get(base_name)

            # Try matching a senior entry first
            if base_name in senior_name_to_id:
                _record(senior_name_to_id[base_name], entry)
                continue

            # Fallback 1: query TeamProfile (exact name)
            profile = TeamProfile.query.filter(TeamProfile.name == base_name).first()
            if profile:
                _record(profile.team_id, entry)
                continue

            # Fallback 2: query Team table (exact name, broader coverage)
            team = Team.query.filter(Team.name == base_name).first()
            if team:
                _record(team.team_id, entry)
                continue

            # Fallback 3: TeamProfile name is a substring of base_name
            # Handles "Tottenham Hotspur" containing "Tottenham", etc.
            # Country filter prevents cross-contamination between similarly
            # named clubs in different countries.
            fb3_query = TeamProfile.query.filter(
                db.func.strpos(base_name, TeamProfile.name) > 0,
                db.func.length(TeamProfile.name) >= 5,
            )
            if entry_country:
                fb3_query = fb3_query.filter(TeamProfile.country == entry_country)
            profile = fb3_query.order_by(db.func.length(TeamProfile.name).desc()).first()
            if profile:
                _record(profile.team_id, entry)
                continue

            # Fallback 4: Team name is a substring of base_name
            fb4_query = Team.query.filter(
                db.func.strpos(base_name, Team.name) > 0,
                db.func.length(Team.name) >= 5,
            )
            if entry_country:
                fb4_query = fb4_query.filter(Team.country == entry_country)
            team = fb4_query.order_by(db.func.length(Team.name).desc()).first()
            if team:
                _record(team.team_id, entry)
                continue

            unresolved.append(base_name)

        if unresolved:
            logger.warning(
                f"Could not resolve academy parent club for player {journey.player_api_id}: {set(unresolved)}"
            )

        # ── Transfer gate: remove clubs the player was permanently transferred TO ──
        # Defense-in-depth — _apply_development_classification should have already
        # reclassified entries as 'integration', but if it missed a case this catches it.
        if resolution is not None and academy_ids:
            permanent_dest_ids = set()
            for event in resolution.events:
                if event.kind != "permanent":
                    continue
                if event.in_club.api_id:
                    permanent_dest_ids.add(event.in_club.api_id)
                if event.in_club.organization_api_id:
                    permanent_dest_ids.add(event.in_club.organization_api_id)

            removed = academy_ids & permanent_dest_ids
            if removed:
                logger.info(
                    f"Transfer gate: removing {removed} from academy_club_ids "
                    f"for player {journey.player_api_id} (permanent transfer destinations)"
                )
                academy_ids -= permanent_dest_ids

        journey.academy_club_ids = sorted(academy_ids)
        # JSON object keys are strings; keep only clubs that survived the gates
        journey.academy_last_seasons = {
            str(club_id): season for club_id, season in last_seasons.items() if club_id in academy_ids
        }

        # Auto-upsert TrackedPlayer rows for each academy connection. Errors
        # intentionally propagate to the sync/repair transaction owner.
        self._upsert_tracked_players(
            journey,
            academy_ids,
            transfers=transfers,
            transfer_resolution=resolution,
            as_of=as_of,
            last_seasons=last_seasons,
            prior_academy_ids=prior_academy_ids,
            prior_last_seasons=prior_last_seasons,
        )

    def _upsert_tracked_players(
        self,
        journey: PlayerJourney,
        academy_ids: set,
        transfers=None,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
        last_seasons=None,
        prior_academy_ids=None,
        prior_last_seasons=None,
    ):
        """Create or update TrackedPlayer rows for discovered academy connections.

        Clubs may only track players formed in their OWN academy, and only
        while the player is inside the academy tracking window (in the
        academy now, or within the past ACADEMY_WINDOW_YEARS seasons).
        The owning (buying) club never gets a row — legacy 'owning-club'
        rows are deactivated.

        ``prior_academy_ids`` / ``prior_last_seasons`` carry the journey's
        PERSISTED attribution from BEFORE this run overwrote it. They power the
        stored-attribution floor: when this run resolved no academy evidence
        for a club (transient API coverage gap / tenure-gate flicker) but the
        stored attribution still lists it inside the window, the row is spared
        rather than orphaned.
        """
        from src.models.journey import YOUTH_LEVELS
        from src.models.tracked_player import TrackedPlayer
        from src.utils.academy_classifier import _get_latest_season, classify_tracked_player
        from src.utils.academy_window import academy_window_start, is_within_academy_window

        last_seasons = last_seasons or {}
        prior_academy_ids = prior_academy_ids or set()
        prior_last_seasons = prior_last_seasons or {}
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )

        # Status (on_loan/sold/released/left) is transfer-driven, so it can only
        # be derived when transfers were actually fetched. Callers that pass
        # transfers=None (e.g. the recompute-academy attribution sweep) must NOT
        # re-derive status — without transfers every "current club != parent"
        # player would collapse to the tentative on_loan / 'left' default and
        # clobber the real status. transfers=[] (a fetched-but-empty list, as in
        # a full journey sync) is a legitimate signal and DOES update status.
        update_status = transfers is not None or resolution is not None

        # Owning club is still computed for current-club classification
        # context, but it no longer keeps TrackedPlayer rows alive.
        owning_api_id = self._determine_owning_club_id(
            journey,
            transfers,
            academy_ids,
            transfer_resolution=resolution,
            as_of=as_of,
        )

        # Window gate: an academy origin only stays tracked while the
        # player's last youth season there is inside the window. A player
        # whose CURRENT level is a youth level is in someone's academy right
        # now — pass the status override so patchy youth-league coverage
        # (stale last recorded youth season) can't age out a current kid.
        window_status = "academy" if (journey.current_level or "") in YOUTH_LEVELS else None
        keep_ids = {
            academy_api_id
            for academy_api_id in academy_ids
            if is_within_academy_window(
                last_seasons.get(academy_api_id), status=window_status, birth_date=journey.birth_date
            )
        }
        aged_out = academy_ids - keep_ids

        def _stored_attribution_floor(club_id: int, row_last_season=None, row_status=None) -> bool:
            """Should ``club_id`` be spared deactivation this run?

            True when this run produced NO fresh academy evidence for the club
            (it is not in the just-computed ``academy_ids``) yet the journey's
            PERSISTED attribution still lists it AND either the player is a
            current academy kid or its stored last youth season there is inside
            the tracking window. A transient empty computation (API youth-
            coverage gap / tenure-gate flicker) must never orphan an established
            in-window academy row — leave it for the next sync that actually has
            evidence.

            Keys on stored SEASON evidence (NOT the birth-date development-age
            fallback in ``is_within_academy_window``): a merely-stale, season-
            less ``academy_club_ids`` value must still deactivate. Otherwise
            every U21 with a birth date — the entire academy-tracker demographic
            — would have season-less stale attributions spared, silently
            defeating that guarantee and stalling one-shot recompute repairs.

            Callers pass the tracked ROW's own evidence (``row_last_season`` /
            ``row_status``) because the journey's per-club season map can lag
            the row (legacy pre-aw18 maps / NULL-season youth entries). A row
            that says ``status='academy'`` is a current kid even when the
            journey's ``current_level`` is stale (mirroring the aged-out branch);
            an in-window row-local season is real SEASON evidence, so honouring
            it does not reopen the season-less-stale hole.
            """
            if club_id in academy_ids or club_id not in prior_academy_ids:
                return False
            # Current academy kid — protected even without a stored season, so
            # patchy youth-league coverage can't age out a player who is in an
            # academy right now. The journey's current level OR the row's own
            # status can attest this.
            if window_status == "academy" or row_status == "academy":
                return True
            window_start = academy_window_start()
            prior_season = prior_last_seasons.get(str(club_id))
            if prior_season is not None and prior_season >= window_start:
                return True
            return row_last_season is not None and row_last_season >= window_start

        # Deactivate journey-sync and legacy owning-club rows whose academy
        # connection no longer holds. Skip pinned rows — manual corrections
        # must persist.
        stale_rows = TrackedPlayer.query.filter(
            TrackedPlayer.player_api_id == journey.player_api_id,
            TrackedPlayer.data_source.in_(["journey-sync", "owning-club"]),
            TrackedPlayer.is_active.is_(True),
        ).all()
        for tp in stale_rows:
            if tp.pinned_parent:
                continue
            if tp.team and tp.team.team_id not in keep_ids:
                if tp.team.team_id in aged_out and tp.status == "academy":
                    # The row itself says the player is currently in this
                    # academy — never window-deactivate current kids.
                    continue
                if _stored_attribution_floor(
                    tp.team.team_id, row_last_season=tp.last_academy_season, row_status=tp.status
                ):
                    logger.info(
                        f"Stored-attribution floor kept {tp.data_source} TrackedPlayer "
                        f"{tp.id} for player {journey.player_api_id} at {tp.team.name} "
                        f"(no fresh academy evidence this run; established in-window academy row)"
                    )
                    continue
                tp.is_active = False
                why = "outside the academy tracking window" if tp.team.team_id in aged_out else "not an academy origin"
                logger.info(
                    f"Deactivated {tp.data_source} TrackedPlayer {tp.id} for player "
                    f"{journey.player_api_id} at {tp.team.name} ({why})"
                )

        # The owning (non-academy) club must not track this player at all:
        # deactivate any remaining active rows there regardless of source.
        # Manual and pinned rows are preserved.
        if owning_api_id and owning_api_id not in academy_ids:
            owned_rows = TrackedPlayer.query.filter(
                TrackedPlayer.player_api_id == journey.player_api_id,
                TrackedPlayer.is_active.is_(True),
            ).all()
            for tp in owned_rows:
                if tp.pinned_parent or tp.data_source == "manual":
                    continue
                if tp.team and tp.team.team_id == owning_api_id:
                    if _stored_attribution_floor(
                        owning_api_id, row_last_season=tp.last_academy_season, row_status=tp.status
                    ):
                        # The "owning" club is also this player's established
                        # in-window academy origin (a homegrown player still
                        # owned by his academy club, e.g. an academy product on
                        # loan) and this run produced no fresh evidence — keep
                        # the academy row instead of nuking it as a buyer.
                        logger.info(
                            f"Stored-attribution floor kept TrackedPlayer {tp.id} for player "
                            f"{journey.player_api_id} at {tp.team.name} "
                            f"(owning club is an established in-window academy origin)"
                        )
                        continue
                    tp.is_active = False
                    logger.info(
                        f"Deactivated TrackedPlayer {tp.id} for player {journey.player_api_id} "
                        f"at owning club {tp.team.name} (owning club is not an academy origin)"
                    )

        if not keep_ids:
            return

        parent_resolutions: dict[int, TransferResolution] = {}
        resolution_as_of = resolution.as_of if resolution is not None else _transfer_as_of(as_of)
        for academy_api_id in keep_ids:
            team = Team.query.filter_by(team_id=academy_api_id, is_active=True).order_by(Team.season.desc()).first()
            if not team:
                continue

            # Academy-relative state needs that academy as its known initial
            # owner. Cache one contextualized resolution per parent so status
            # and the parent's own sale fee use identical chronology.
            parent_resolution = None
            if transfers is not None:
                parent_resolution = parent_resolutions.get(academy_api_id)
                if parent_resolution is None:
                    parent_resolution = resolve_transfer_state(
                        transfers,
                        as_of=resolution_as_of,
                        initial_owner={"id": academy_api_id, "name": team.name},
                        season_start_month=(resolution.season_start_month if resolution is not None else 7),
                        season_start_day=(resolution.season_start_day if resolution is not None else 1),
                    )
                    parent_resolutions[academy_api_id] = parent_resolution

            existing = TrackedPlayer.query.filter_by(
                player_api_id=journey.player_api_id,
                team_id=team.id,
            ).first()

            status, current_club_api_id, current_club_name = classify_tracked_player(
                current_club_api_id=journey.current_club_api_id,
                current_club_name=journey.current_club_name,
                current_level=journey.current_level,
                parent_api_id=academy_api_id,
                parent_club_name=team.name,
                transfers=transfers,
                latest_season=_get_latest_season(journey.id, parent_api_id=academy_api_id, parent_club_name=team.name),
                transfer_resolution=parent_resolution,
                as_of=resolution_as_of,
                season_start_month=(parent_resolution.season_start_month if parent_resolution is not None else 7),
                season_start_day=(parent_resolution.season_start_day if parent_resolution is not None else 1),
            )
            parent_departure = latest_parent_permanent_departure(
                parent_resolution,
                academy_api_id,
                team.name,
            )
            sale_fee = parent_departure.fee if parent_departure is not None and status == "sold" else None

            if not existing:
                tp = TrackedPlayer(
                    player_api_id=journey.player_api_id,
                    player_name=resolve_player_name(journey.player_api_id, journey.player_name),
                    photo_url=journey.player_photo,
                    nationality=journey.nationality,
                    birth_date=journey.birth_date,
                    team_id=team.id,
                    journey_id=journey.id,
                    data_source="journey-sync",
                    data_depth="full_stats",
                    status=status,
                    current_club_api_id=current_club_api_id,
                    current_club_name=current_club_name,
                    sale_fee=sale_fee,
                    last_academy_season=last_seasons.get(academy_api_id),
                )
                db.session.add(tp)
            else:
                # Always keep journey link and window evidence fresh
                existing.journey_id = journey.id
                if last_seasons.get(academy_api_id) is not None:
                    existing.last_academy_season = last_seasons[academy_api_id]
                # Skip status/loan updates for pinned players — manual corrections persist
                if existing.pinned_parent:
                    logger.debug(
                        f"Skipping status update for pinned player {journey.player_api_id} at team {team.name}"
                    )
                    continue
                # Provenance + window both hold — revive rows that earlier
                # mechanisms wrongly deactivated (e.g. transfer-heal once
                # retired academy rows in favour of owning-club duplicates).
                if existing.is_active is False and existing.data_source != "manual":
                    existing.is_active = True
                    # Provenance is now journey-verified (club is in keep_ids), so
                    # a legacy 'owning-club' label is both wrong and — critically —
                    # keeps the reactivated row INVISIBLE: Scout Desk and Teams all
                    # filter out data_source='owning-club' (invariant #3). Convert
                    # it to the canonical academy source so the row is actually
                    # surfaced instead of being healed-but-hidden (the Gore case).
                    if existing.data_source == "owning-club":
                        existing.data_source = "journey-sync"
                    logger.info(
                        f"Reactivated TrackedPlayer {existing.id} for player "
                        f"{journey.player_api_id} at {team.name} (academy origin inside tracking window)"
                    )
                # Only re-derive status when transfers were available (a real
                # journey sync). The recompute-academy attribution sweep passes
                # transfers=None and must leave the existing status untouched.
                if update_status:
                    existing.status = status
                    existing.current_club_api_id = current_club_api_id
                    existing.current_club_name = current_club_name
                    existing.sale_fee = sale_fee

    def _determine_owning_club_id(
        self,
        journey,
        transfers,
        academy_ids,
        *,
        transfer_resolution: TransferResolution | None = None,
        as_of: date | str | None = None,
    ):
        """Find the current legal owner from the chronological resolution.

        Returns team_api_id or None if the owning club is already in academy_ids
        or cannot be determined. Attribution-only repair callers have no
        transfer evidence, so they retain the established journey-entry
        fallback used solely to suppress rows at a player's buying club.
        """
        resolution = _coerce_transfer_resolution(
            transfers,
            transfer_resolution=transfer_resolution,
            as_of=as_of,
        )
        if resolution is not None:
            if resolution.legal_owner is None:
                return None
            owning_id = resolution.legal_owner.organization_api_id or resolution.legal_owner.api_id
        else:
            # This is not a status/owner projection: recompute-academy has no
            # provider evidence but still needs to avoid creating a tracker row
            # at an obvious later buying club. An authoritative empty or
            # ambiguous resolution never reaches this fallback.
            owning_id = None
            if journey.id:
                entry = (
                    PlayerJourneyEntry.query.filter_by(journey_id=journey.id)
                    .filter(PlayerJourneyEntry.is_youth.is_(False))
                    .filter(PlayerJourneyEntry.entry_type.in_(["permanent", "first_team"]))
                    .order_by(PlayerJourneyEntry.season.desc())
                    .first()
                )
                if entry and entry.club_api_id:
                    owning_id = entry.club_api_id

        # Skip if owning club is already in academy_ids (already has a tracked row)
        if owning_id and owning_id not in academy_ids:
            return owning_id
        return None

    def _auto_geocode_clubs(self, journey: PlayerJourney):
        """Create ClubLocation rows for clubs that don't have one yet.

        Uses TeamProfile city/country when available, falls back to
        league_country from entries, and geocodes via get_team_coordinates().
        """
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        if not entries:
            return

        # Collect unique club IDs (skip international entries)
        club_ids = set(e.club_api_id for e in entries if not e.is_international)
        if not club_ids:
            return

        # Find which clubs already have locations
        existing = set(
            loc.club_api_id for loc in ClubLocation.query.filter(ClubLocation.club_api_id.in_(club_ids)).all()
        )
        missing_ids = club_ids - existing
        if not missing_ids:
            return

        # Build lookup: club_id -> (name, country) from entries
        club_info = {}
        for entry in entries:
            if entry.club_api_id in missing_ids and entry.club_api_id not in club_info:
                club_info[entry.club_api_id] = {
                    "name": entry.club_name,
                    "country": entry.league_country,
                }

        added = 0
        for club_id in missing_ids:
            info = club_info.get(club_id, {})
            club_name = info.get("name", "")
            country = info.get("country")

            # Try TeamProfile for city/country
            city = None
            profile = TeamProfile.query.filter_by(team_id=club_id).first()
            if profile:
                city = profile.venue_city
                country = profile.country or country

            # Only geocode if we have an actual city name — using just a
            # country name produces wildly wrong results (e.g. "Scotland"
            # resolves to Virginia, USA).
            if not city:
                continue

            coords = get_team_coordinates(city, country)
            if not coords:
                continue

            location = ClubLocation(
                club_api_id=club_id,
                club_name=club_name,
                city=city,
                country=country,
                latitude=coords[0],
                longitude=coords[1],
                geocode_source="auto",
                geocode_confidence=0.7,
            )
            db.session.add(location)
            added += 1

        if added:
            logger.info(f"Auto-geocoded {added} club locations for player {journey.player_api_id}")


def seed_club_locations():
    """Seed initial club locations for major clubs"""

    MAJOR_CLUBS = [
        # Premier League
        {
            "api_id": 33,
            "name": "Manchester United",
            "city": "Manchester",
            "country": "England",
            "code": "GB",
            "lat": 53.4631,
            "lng": -2.2913,
        },
        {
            "api_id": 40,
            "name": "Liverpool",
            "city": "Liverpool",
            "country": "England",
            "code": "GB",
            "lat": 53.4308,
            "lng": -2.9608,
        },
        {
            "api_id": 42,
            "name": "Arsenal",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.5549,
            "lng": -0.1084,
        },
        {
            "api_id": 49,
            "name": "Chelsea",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.4817,
            "lng": -0.1910,
        },
        {
            "api_id": 50,
            "name": "Manchester City",
            "city": "Manchester",
            "country": "England",
            "code": "GB",
            "lat": 53.4831,
            "lng": -2.2004,
        },
        {
            "api_id": 47,
            "name": "Tottenham",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.6042,
            "lng": -0.0662,
        },
        {
            "api_id": 34,
            "name": "Newcastle",
            "city": "Newcastle",
            "country": "England",
            "code": "GB",
            "lat": 54.9756,
            "lng": -1.6217,
        },
        {
            "api_id": 66,
            "name": "Aston Villa",
            "city": "Birmingham",
            "country": "England",
            "code": "GB",
            "lat": 52.5092,
            "lng": -1.8847,
        },
        {
            "api_id": 48,
            "name": "West Ham",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.5386,
            "lng": -0.0166,
        },
        {
            "api_id": 35,
            "name": "Brighton",
            "city": "Brighton",
            "country": "England",
            "code": "GB",
            "lat": 50.8619,
            "lng": -0.0839,
        },
        {
            "api_id": 45,
            "name": "Everton",
            "city": "Liverpool",
            "country": "England",
            "code": "GB",
            "lat": 53.4387,
            "lng": -2.9664,
        },
        {
            "api_id": 36,
            "name": "Fulham",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.4750,
            "lng": -0.2217,
        },
        {
            "api_id": 52,
            "name": "Crystal Palace",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.3983,
            "lng": -0.0855,
        },
        {
            "api_id": 55,
            "name": "Brentford",
            "city": "London",
            "country": "England",
            "code": "GB",
            "lat": 51.4907,
            "lng": -0.2886,
        },
        {
            "api_id": 39,
            "name": "Wolves",
            "city": "Wolverhampton",
            "country": "England",
            "code": "GB",
            "lat": 52.5903,
            "lng": -2.1306,
        },
        {
            "api_id": 65,
            "name": "Nottingham Forest",
            "city": "Nottingham",
            "country": "England",
            "code": "GB",
            "lat": 52.9399,
            "lng": -1.1328,
        },
        {
            "api_id": 51,
            "name": "Bournemouth",
            "city": "Bournemouth",
            "country": "England",
            "code": "GB",
            "lat": 50.7352,
            "lng": -1.8383,
        },
        {
            "api_id": 46,
            "name": "Leicester",
            "city": "Leicester",
            "country": "England",
            "code": "GB",
            "lat": 52.6204,
            "lng": -1.1421,
        },
        {
            "api_id": 41,
            "name": "Southampton",
            "city": "Southampton",
            "country": "England",
            "code": "GB",
            "lat": 50.9058,
            "lng": -1.3910,
        },
        {
            "api_id": 57,
            "name": "Ipswich",
            "city": "Ipswich",
            "country": "England",
            "code": "GB",
            "lat": 52.0547,
            "lng": 1.1447,
        },
        # La Liga
        {
            "api_id": 541,
            "name": "Real Madrid",
            "city": "Madrid",
            "country": "Spain",
            "code": "ES",
            "lat": 40.4531,
            "lng": -3.6883,
        },
        {
            "api_id": 529,
            "name": "Barcelona",
            "city": "Barcelona",
            "country": "Spain",
            "code": "ES",
            "lat": 41.3809,
            "lng": 2.1228,
        },
        {
            "api_id": 530,
            "name": "Atletico Madrid",
            "city": "Madrid",
            "country": "Spain",
            "code": "ES",
            "lat": 40.4362,
            "lng": -3.5995,
        },
        {
            "api_id": 536,
            "name": "Sevilla",
            "city": "Sevilla",
            "country": "Spain",
            "code": "ES",
            "lat": 37.3840,
            "lng": -5.9705,
        },
        {
            "api_id": 532,
            "name": "Valencia",
            "city": "Valencia",
            "country": "Spain",
            "code": "ES",
            "lat": 39.4747,
            "lng": -0.3583,
        },
        {
            "api_id": 533,
            "name": "Villarreal",
            "city": "Villarreal",
            "country": "Spain",
            "code": "ES",
            "lat": 39.9441,
            "lng": -0.1036,
        },
        {
            "api_id": 548,
            "name": "Real Sociedad",
            "city": "San Sebastian",
            "country": "Spain",
            "code": "ES",
            "lat": 43.3013,
            "lng": -1.9737,
        },
        {
            "api_id": 531,
            "name": "Athletic Bilbao",
            "city": "Bilbao",
            "country": "Spain",
            "code": "ES",
            "lat": 43.2641,
            "lng": -2.9494,
        },
        {
            "api_id": 543,
            "name": "Real Betis",
            "city": "Sevilla",
            "country": "Spain",
            "code": "ES",
            "lat": 37.3567,
            "lng": -5.9817,
        },
        # Serie A
        {
            "api_id": 489,
            "name": "AC Milan",
            "city": "Milan",
            "country": "Italy",
            "code": "IT",
            "lat": 45.4781,
            "lng": 9.1240,
        },
        {
            "api_id": 505,
            "name": "Inter",
            "city": "Milan",
            "country": "Italy",
            "code": "IT",
            "lat": 45.4781,
            "lng": 9.1240,
        },
        {
            "api_id": 496,
            "name": "Juventus",
            "city": "Turin",
            "country": "Italy",
            "code": "IT",
            "lat": 45.1096,
            "lng": 7.6413,
        },
        {
            "api_id": 492,
            "name": "Napoli",
            "city": "Naples",
            "country": "Italy",
            "code": "IT",
            "lat": 40.8280,
            "lng": 14.1930,
        },
        {
            "api_id": 487,
            "name": "Roma",
            "city": "Rome",
            "country": "Italy",
            "code": "IT",
            "lat": 41.9341,
            "lng": 12.4547,
        },
        {
            "api_id": 488,
            "name": "Lazio",
            "city": "Rome",
            "country": "Italy",
            "code": "IT",
            "lat": 41.9341,
            "lng": 12.4547,
        },
        {
            "api_id": 499,
            "name": "Atalanta",
            "city": "Bergamo",
            "country": "Italy",
            "code": "IT",
            "lat": 45.7089,
            "lng": 9.6808,
        },
        {
            "api_id": 502,
            "name": "Fiorentina",
            "city": "Florence",
            "country": "Italy",
            "code": "IT",
            "lat": 43.7810,
            "lng": 11.2822,
        },
        # Bundesliga
        {
            "api_id": 157,
            "name": "Bayern Munich",
            "city": "Munich",
            "country": "Germany",
            "code": "DE",
            "lat": 48.2188,
            "lng": 11.6247,
        },
        {
            "api_id": 165,
            "name": "Borussia Dortmund",
            "city": "Dortmund",
            "country": "Germany",
            "code": "DE",
            "lat": 51.4926,
            "lng": 7.4519,
        },
        {
            "api_id": 173,
            "name": "RB Leipzig",
            "city": "Leipzig",
            "country": "Germany",
            "code": "DE",
            "lat": 51.3459,
            "lng": 12.3483,
        },
        {
            "api_id": 168,
            "name": "Bayer Leverkusen",
            "city": "Leverkusen",
            "country": "Germany",
            "code": "DE",
            "lat": 51.0383,
            "lng": 7.0022,
        },
        {
            "api_id": 169,
            "name": "Eintracht Frankfurt",
            "city": "Frankfurt",
            "country": "Germany",
            "code": "DE",
            "lat": 50.0686,
            "lng": 8.6455,
        },
        {
            "api_id": 172,
            "name": "VfB Stuttgart",
            "city": "Stuttgart",
            "country": "Germany",
            "code": "DE",
            "lat": 48.7922,
            "lng": 9.2320,
        },
        # Ligue 1
        {
            "api_id": 85,
            "name": "Paris Saint Germain",
            "city": "Paris",
            "country": "France",
            "code": "FR",
            "lat": 48.8414,
            "lng": 2.2530,
        },
        {
            "api_id": 91,
            "name": "Monaco",
            "city": "Monaco",
            "country": "Monaco",
            "code": "MC",
            "lat": 43.7277,
            "lng": 7.4156,
        },
        {
            "api_id": 81,
            "name": "Marseille",
            "city": "Marseille",
            "country": "France",
            "code": "FR",
            "lat": 43.2696,
            "lng": 5.3958,
        },
        {
            "api_id": 80,
            "name": "Lyon",
            "city": "Lyon",
            "country": "France",
            "code": "FR",
            "lat": 45.7652,
            "lng": 4.9822,
        },
        {
            "api_id": 82,
            "name": "Lille",
            "city": "Lille",
            "country": "France",
            "code": "FR",
            "lat": 50.6119,
            "lng": 3.1305,
        },
        # Other notable clubs
        {
            "api_id": 211,
            "name": "Benfica",
            "city": "Lisbon",
            "country": "Portugal",
            "code": "PT",
            "lat": 38.7528,
            "lng": -9.1847,
        },
        {
            "api_id": 212,
            "name": "Porto",
            "city": "Porto",
            "country": "Portugal",
            "code": "PT",
            "lat": 41.1618,
            "lng": -8.5836,
        },
        {
            "api_id": 194,
            "name": "Ajax",
            "city": "Amsterdam",
            "country": "Netherlands",
            "code": "NL",
            "lat": 52.3142,
            "lng": 4.9419,
        },
        {
            "api_id": 197,
            "name": "PSV",
            "city": "Eindhoven",
            "country": "Netherlands",
            "code": "NL",
            "lat": 51.4417,
            "lng": 5.4675,
        },
        {
            "api_id": 233,
            "name": "Sporting CP",
            "city": "Lisbon",
            "country": "Portugal",
            "code": "PT",
            "lat": 38.7614,
            "lng": -9.1608,
        },
    ]

    added = 0
    for club in MAJOR_CLUBS:
        existing = ClubLocation.query.filter_by(club_api_id=club["api_id"]).first()
        if not existing:
            location = ClubLocation(
                club_api_id=club["api_id"],
                club_name=club["name"],
                city=club["city"],
                country=club["country"],
                country_code=club["code"],
                latitude=club["lat"],
                longitude=club["lng"],
                geocode_source="manual",
                geocode_confidence=1.0,
            )
            db.session.add(location)
            added += 1

    db.session.commit()
    logger.info(f"Seeded {added} club locations")
    return added
