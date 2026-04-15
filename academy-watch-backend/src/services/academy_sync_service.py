"""Academy Fixture Sync Service.

Fetches fixtures from configured academy leagues and extracts
player appearances, goals, assists from lineups and events data.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.api_football_client import APIFootballClient
from src.models.league import AcademyAppearance, AcademyLeague, AcademyPlayerSeasonStats, db
from src.models.tracked_player import TrackedPlayer
from src.services.big6_seeding_service import RateLimiter

logger = logging.getLogger(__name__)

# Football season boundary: new season starts in August
SEASON_START_MONTH = 8


def _current_season() -> int:
    """Return the current football season year (season starts in August)."""
    today = date.today()
    if today.month >= SEASON_START_MONTH:
        return today.year
    return today.year - 1


class AcademySyncService:
    """Service for syncing academy/youth league fixtures and player appearances."""

    def __init__(
        self,
        api_client: APIFootballClient | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self.api_client = api_client or APIFootballClient()
        self.rate_limiter = rate_limiter or RateLimiter(per_minute_cap=25, per_day_cap=7000)

    def _ensure_current_season(self, leagues: list[AcademyLeague]) -> None:
        """Update league seasons to the current football season if stale."""
        current = _current_season()
        updated = []
        for league in leagues:
            if league.season != current:
                league.season = current
                updated.append(league.name)
        if updated:
            db.session.commit()
            logger.info(f"Updated season to {current} for: {', '.join(updated)}")

    def sync_league(
        self,
        league: AcademyLeague,
        date_from: date | None = None,
        date_to: date | None = None,
        season: int | None = None,
    ) -> dict[str, Any]:
        """
        Sync fixtures for a single academy league.

        Args:
            league: AcademyLeague to sync
            date_from: Start date (default: 7 days ago)
            date_to: End date (default: today)
            season: Season year (default: league.season or current year)

        Returns:
            Dict with sync results: fixtures_processed, appearances_created, errors
        """
        if not league.sync_enabled:
            logger.info(f"Sync disabled for league {league.name}")
            return {"status": "skipped", "reason": "sync_disabled"}

        # Auto-update season if stale
        self._ensure_current_season([league])

        # Default date range: last 7 days
        if date_from is None:
            date_from = date.today() - timedelta(days=7)
        if date_to is None:
            date_to = date.today()

        season = season or league.season or _current_season()

        logger.info(f"Syncing {league.name} ({league.api_league_id}) from {date_from} to {date_to}")

        results = {
            "league_id": league.id,
            "league_name": league.name,
            "fixtures_processed": 0,
            "appearances_created": 0,
            "appearances_updated": 0,
            "errors": [],
        }

        try:
            # Fetch fixtures for the league
            self.rate_limiter.wait_if_needed()
            fixtures = self._fetch_fixtures(
                league_id=league.api_league_id,
                season=season,
                date_from=date_from,
                date_to=date_to,
            )

            if not fixtures:
                logger.info(f"No fixtures found for {league.name}")
                return results

            logger.info(f"Found {len(fixtures)} fixtures for {league.name}")

            # Get tracked player IDs for matching
            tracked_player_ids = self._get_tracked_player_ids()

            for i, fixture in enumerate(fixtures):
                try:
                    fixture_results = self._process_fixture(
                        fixture=fixture,
                        league=league,
                        tracked_player_ids=tracked_player_ids,
                    )
                    results["fixtures_processed"] += 1
                    results["appearances_created"] += fixture_results.get("created", 0)
                    results["appearances_updated"] += fixture_results.get("updated", 0)

                    if (i + 1) % 10 == 0:
                        logger.info(
                            f"  {league.name}: {i + 1}/{len(fixtures)} fixtures processed "
                            f"({results['appearances_created']} created, {results['appearances_updated']} updated)"
                        )
                except Exception as e:
                    error_msg = f"Error processing fixture {fixture.get('fixture', {}).get('id')}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            # Update last synced timestamp
            league.last_synced_at = datetime.now(UTC)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            error_msg = f"Error syncing league {league.name}: {str(e)}"
            logger.exception(error_msg)
            results["errors"].append(error_msg)

        logger.info(
            f"Sync complete for {league.name}: {results['fixtures_processed']} fixtures, "
            f"{results['appearances_created']} created, {results['appearances_updated']} updated, "
            f"{len(results['errors'])} errors"
        )
        return results

    def sync_all_active_leagues(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict[str, Any]]:
        """Sync all active academy leagues."""
        leagues = AcademyLeague.query.filter_by(is_active=True, sync_enabled=True).all()

        # Auto-update seasons before syncing
        self._ensure_current_season(leagues)

        results = []

        for league in leagues:
            result = self.sync_league(league, date_from=date_from, date_to=date_to)
            results.append(result)

        return results

    def _fetch_fixtures(
        self,
        league_id: int,
        season: int,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        """Fetch fixtures from API-Football for a league and date range."""
        try:
            resp = self.api_client._make_request(
                "fixtures",
                {
                    "league": league_id,
                    "season": season,
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat(),
                    "status": "FT",  # Only completed fixtures
                },
            )
            return resp.get("response", [])
        except Exception as e:
            logger.error(f"Error fetching fixtures for league {league_id}: {e}")
            return []

    def _get_tracked_player_ids(self) -> dict[int, int]:
        """
        Get mapping of API player IDs to TrackedPlayer IDs for matching.

        Returns:
            Dict mapping player_api_id -> tracked_player.id
        """
        rows = (
            db.session.query(
                TrackedPlayer.player_api_id,
                TrackedPlayer.id,
            )
            .filter(
                TrackedPlayer.is_active,
            )
            .all()
        )
        return {row[0]: row[1] for row in rows}

    def _process_fixture(
        self,
        fixture: dict[str, Any],
        league: AcademyLeague,
        tracked_player_ids: dict[int, int],
    ) -> dict[str, int]:
        """
        Process a single fixture: fetch lineups/events and create appearances.

        Returns:
            Dict with 'created' and 'updated' counts
        """
        fixture_info = fixture.get("fixture", {})
        fixture_id = fixture_info.get("id")
        fixture_date_str = fixture_info.get("date", "")[:10]

        if not fixture_id:
            return {"created": 0, "updated": 0}

        try:
            fixture_date = date.fromisoformat(fixture_date_str)
        except ValueError:
            logger.warning(f"Invalid fixture date: {fixture_date_str}")
            return {"created": 0, "updated": 0}

        teams = fixture.get("teams", {})
        home_team = teams.get("home", {}).get("name", "Unknown")
        away_team = teams.get("away", {}).get("name", "Unknown")

        league_info = fixture.get("league", {})
        competition = league_info.get("name", league.name)

        # Fetch lineups and events (rate-limited)
        self.rate_limiter.wait_if_needed()
        lineups_data = self.api_client.get_fixture_lineups(fixture_id)
        self.rate_limiter.wait_if_needed()
        events_data = self.api_client.get_fixture_events(fixture_id)

        lineups = lineups_data.get("response", [])
        events = events_data.get("response", [])

        # Extract players from lineups
        players = self._extract_players_from_lineups(lineups)

        # Enrich with events (goals, assists, cards)
        player_events = self._extract_player_events(events)

        created = 0
        updated = 0

        for player_id, player_info in players.items():
            # Check if appearance already exists
            existing = AcademyAppearance.query.filter_by(
                player_id=player_id,
                fixture_id=fixture_id,
            ).first()

            # Get events for this player
            p_events = player_events.get(player_id, {})

            if existing:
                # Update existing appearance
                existing.goals = p_events.get("goals", 0)
                existing.assists = p_events.get("assists", 0)
                existing.yellow_cards = p_events.get("yellow_cards", 0)
                existing.red_cards = p_events.get("red_cards", 0)
                updated += 1
            else:
                # Create new appearance
                appearance = AcademyAppearance(
                    player_id=player_id,
                    player_name=player_info.get("name", f"Player {player_id}"),
                    fixture_id=fixture_id,
                    fixture_date=fixture_date,
                    home_team=home_team,
                    away_team=away_team,
                    competition=competition,
                    academy_league_id=league.id,
                    loaned_player_id=tracked_player_ids.get(player_id),
                    started=player_info.get("started", False),
                    minutes_played=player_info.get("minutes"),
                    goals=p_events.get("goals", 0),
                    assists=p_events.get("assists", 0),
                    yellow_cards=p_events.get("yellow_cards", 0),
                    red_cards=p_events.get("red_cards", 0),
                    lineup_data=player_info.get("raw"),
                    events_data=p_events.get("raw"),
                )
                db.session.add(appearance)
                created += 1

        db.session.commit()
        return {"created": created, "updated": updated}

    def _extract_players_from_lineups(
        self,
        lineups: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        """
        Extract player info from lineups data.

        Returns:
            Dict mapping player_id -> {'name', 'started', 'minutes', 'raw'}
        """
        players = {}

        for team_lineup in lineups:
            # Starting XI
            for player in team_lineup.get("startXI", []):
                p = player.get("player", {})
                player_id = p.get("id")
                if player_id:
                    players[player_id] = {
                        "name": p.get("name", ""),
                        "started": True,
                        "minutes": None,  # Not always available
                        "raw": player,
                    }

            # Substitutes who came on
            for player in team_lineup.get("substitutes", []):
                p = player.get("player", {})
                player_id = p.get("id")
                # Only include subs who actually played (would need event data)
                # For now, we'll just track that they were in the squad
                if player_id and player_id not in players:
                    players[player_id] = {
                        "name": p.get("name", ""),
                        "started": False,
                        "minutes": None,
                        "raw": player,
                    }

        return players

    def _extract_player_events(
        self,
        events: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        """
        Extract goals, assists, cards from events data.

        Returns:
            Dict mapping player_id -> {'goals', 'assists', 'yellow_cards', 'red_cards', 'raw'}
        """
        player_events: dict[int, dict[str, Any]] = {}

        for event in events:
            event_type = event.get("type", "").lower()
            event_detail = event.get("detail", "").lower()
            player = event.get("player", {})
            player_id = player.get("id")
            assist = event.get("assist", {})
            assist_id = assist.get("id") if assist else None

            if not player_id:
                continue

            if player_id not in player_events:
                player_events[player_id] = {
                    "goals": 0,
                    "assists": 0,
                    "yellow_cards": 0,
                    "red_cards": 0,
                    "raw": [],
                }

            player_events[player_id]["raw"].append(event)

            if event_type == "goal":
                # Own goals don't count
                if "own goal" not in event_detail:
                    player_events[player_id]["goals"] += 1

                # Track assist
                if assist_id:
                    if assist_id not in player_events:
                        player_events[assist_id] = {
                            "goals": 0,
                            "assists": 0,
                            "yellow_cards": 0,
                            "red_cards": 0,
                            "raw": [],
                        }
                    player_events[assist_id]["assists"] += 1
                    player_events[assist_id]["raw"].append(event)

            elif event_type == "card":
                if "yellow" in event_detail:
                    player_events[player_id]["yellow_cards"] += 1
                elif "red" in event_detail:
                    player_events[player_id]["red_cards"] += 1

        return player_events

    # ------------------------------------------------------------------
    # Player-first sync: fetch season stats from /players endpoint
    # ------------------------------------------------------------------

    # European youth leagues to seed into academy_leagues if missing
    EUROPEAN_YOUTH_LEAGUES = [
        # Italy
        (705, "Campionato Primavera 1", "Italy", "U20"),
        (706, "Campionato Primavera 2", "Italy", "U20"),
        (704, "Coppa Italia Primavera", "Italy", "U20"),
        (817, "Super Cup Primavera", "Italy", "U20"),
        # Germany
        (488, "U19 Bundesliga", "Germany", "U19"),
        (715, "DFB Junioren Pokal", "Germany", "U19"),
        # Netherlands
        (675, "U21 Divisie 1", "Netherlands", "U21"),
        (724, "U18 Divisie 1", "Netherlands", "U18"),
        (1152, "U19 Divisie 1", "Netherlands", "U19"),
        (883, "Reserve League", "Netherlands", "Reserve"),
        # Portugal
        (701, "Liga Revelação U23", "Portugal", "U23"),
        (840, "Taça Revelação U23", "Portugal", "U23"),
        (1041, "Júniores U19", "Portugal", "U19"),
    ]

    def _seed_european_leagues(self) -> None:
        """Ensure European youth leagues are in academy_leagues table."""
        existing_ids = {r[0] for r in db.session.query(AcademyLeague.api_league_id).all()}
        added = []
        for api_id, name, country, level in self.EUROPEAN_YOUTH_LEAGUES:
            if api_id not in existing_ids:
                league = AcademyLeague(
                    api_league_id=api_id,
                    name=name,
                    country=country,
                    level=level,
                    season=_current_season(),
                    is_active=True,
                    sync_enabled=True,
                )
                db.session.add(league)
                added.append(f"{name} ({country})")
        if added:
            db.session.commit()
            logger.info(f"Seeded {len(added)} European youth leagues: {', '.join(added)}")

    def sync_academy_stats_for_players(
        self,
        seasons: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Sync season-level stats for ALL tracked players across youth leagues.

        Uses /players?id=X&season=Y which returns per-league aggregated stats
        including appearances, goals, assists, minutes, rating, and extended stats.
        This works for youth leagues where /fixtures/lineups returns empty.
        """
        if seasons is None:
            current = _current_season()
            seasons = [current - 2, current - 1, current]

        # Seed European youth leagues if not yet in DB
        self._seed_european_leagues()

        # Get academy league IDs for filtering stats entries
        academy_leagues = AcademyLeague.query.filter_by(is_active=True).all()
        academy_league_ids = {league.api_league_id for league in academy_leagues}

        # Get ALL active tracked players (any status — they all have academy origins)
        rows = (
            db.session.query(
                TrackedPlayer.id,
                TrackedPlayer.player_api_id,
                TrackedPlayer.player_name,
            )
            .filter(
                TrackedPlayer.is_active,
            )
            .all()
        )

        if not rows:
            logger.info("No active tracked players to sync")
            return {"players_checked": 0, "stats_created": 0, "stats_updated": 0, "errors": []}

        logger.info(
            f"Syncing academy stats for {len(rows)} players "
            f"across seasons {seasons} ({len(academy_league_ids)} leagues)"
        )

        results = {
            "players_checked": 0,
            "stats_created": 0,
            "stats_updated": 0,
            "errors": [],
        }

        for i, (tp_id, player_api_id, player_name) in enumerate(rows):
            try:
                for season in seasons:
                    # Direct API call — the client has DB cache + _respect_ratelimit()
                    resp = self.api_client._make_request(
                        "players",
                        {
                            "id": player_api_id,
                            "season": season,
                        },
                    )
                    players_data = resp.get("response", [])
                    if not players_data:
                        continue

                    player_data = players_data[0]
                    stats_list = player_data.get("statistics", [])
                    p_info = player_data.get("player", {})
                    display_name = p_info.get("name") or player_name

                    for stat in stats_list:
                        league_info = stat.get("league", {})
                        league_id = league_info.get("id")

                        if league_id not in academy_league_ids:
                            continue

                        created, updated = self._upsert_season_stats(
                            player_api_id=player_api_id,
                            player_name=display_name,
                            tracked_player_id=tp_id,
                            stat=stat,
                            season=season,
                        )
                        results["stats_created"] += created
                        results["stats_updated"] += updated

                results["players_checked"] += 1

                if (i + 1) % 25 == 0:
                    db.session.commit()
                    logger.info(
                        f"  Progress: {i + 1}/{len(rows)} players "
                        f"({results['stats_created']} created, {results['stats_updated']} updated)"
                    )

            except Exception as e:
                db.session.rollback()
                error_msg = f"Error syncing player {player_api_id} ({player_name}): {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        db.session.commit()
        logger.info(
            f"Academy player stats sync complete: {results['players_checked']} players, "
            f"{results['stats_created']} created, {results['stats_updated']} updated, "
            f"{len(results['errors'])} errors"
        )
        return results

    def _upsert_season_stats(
        self,
        player_api_id: int,
        player_name: str,
        tracked_player_id: int,
        stat: dict[str, Any],
        season: int,
    ) -> tuple:
        """Upsert a single AcademyPlayerSeasonStats row. Returns (created, updated) counts."""
        league_info = stat.get("league", {})
        team_info = stat.get("team", {})
        games = stat.get("games", {})
        goals_data = stat.get("goals", {})
        cards = stat.get("cards", {})
        shots = stat.get("shots", {})
        passes = stat.get("passes", {})
        tackles = stat.get("tackles", {})
        duels = stat.get("duels", {})
        dribbles = stat.get("dribbles", {})
        fouls = stat.get("fouls", {})
        penalty = stat.get("penalty", {})

        league_api_id = league_info.get("id")

        existing = AcademyPlayerSeasonStats.query.filter_by(
            player_api_id=player_api_id,
            league_api_id=league_api_id,
            season=season,
        ).first()

        rating_str = games.get("rating")
        rating = float(rating_str) if rating_str else None

        fields = dict(
            player_name=player_name,
            league_name=league_info.get("name"),
            team_api_id=team_info.get("id"),
            team_name=team_info.get("name"),
            tracked_player_id=tracked_player_id,
            appearances=games.get("appearences") or games.get("appearances") or 0,
            lineups=games.get("lineups") or 0,
            minutes=games.get("minutes") or 0,
            rating=rating,
            goals=goals_data.get("total") or 0,
            assists=goals_data.get("assists") or 0,
            yellow_cards=cards.get("yellow") or 0,
            red_cards=cards.get("red") or 0,
            shots_total=shots.get("total"),
            shots_on=shots.get("on"),
            passes_total=passes.get("total"),
            passes_key=passes.get("key"),
            passes_accuracy=float(passes["accuracy"]) if passes.get("accuracy") else None,
            tackles_total=tackles.get("total"),
            interceptions=tackles.get("interceptions"),
            duels_total=duels.get("total"),
            duels_won=duels.get("won"),
            dribbles_attempts=dribbles.get("attempts"),
            dribbles_success=dribbles.get("success"),
            fouls_drawn=fouls.get("drawn"),
            fouls_committed=fouls.get("committed"),
            penalty_scored=penalty.get("scored"),
            penalty_missed=penalty.get("missed"),
            updated_at=datetime.now(UTC),
        )

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            return (0, 1)
        else:
            row = AcademyPlayerSeasonStats(
                player_api_id=player_api_id,
                league_api_id=league_api_id,
                season=season,
                **fields,
            )
            db.session.add(row)
            return (1, 0)

    # ------------------------------------------------------------------
    # Stats retrieval
    # ------------------------------------------------------------------

    def get_player_academy_stats(
        self,
        player_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        """
        Get aggregated academy stats for a player.

        Checks AcademyPlayerSeasonStats first (rich data from /players endpoint),
        falls back to AcademyAppearance (per-fixture data, usually empty for youth leagues).
        """
        # Try season stats first (the rich data source)
        season_rows = (
            AcademyPlayerSeasonStats.query.filter_by(
                player_api_id=player_id,
            )
            .order_by(AcademyPlayerSeasonStats.season.desc())
            .all()
        )

        if season_rows:
            # Only aggregate stats from leagues where the player actually appeared
            season_rows = [r for r in season_rows if (r.appearances or 0) > 0]

        if season_rows:
            total_apps = sum(r.appearances or 0 for r in season_rows)
            total_starts = sum(r.lineups or 0 for r in season_rows)
            total_goals = sum(r.goals or 0 for r in season_rows)
            total_assists = sum(r.assists or 0 for r in season_rows)
            total_minutes = sum(r.minutes or 0 for r in season_rows)
            total_yellows = sum(r.yellow_cards or 0 for r in season_rows)
            total_reds = sum(r.red_cards or 0 for r in season_rows)

            # Weighted average rating
            rated = [(r.rating, r.appearances or 0) for r in season_rows if r.rating]
            avg_rating = None
            if rated:
                total_w = sum(w for _, w in rated)
                if total_w:
                    avg_rating = round(sum(r * w for r, w in rated) / total_w, 2)

            return {
                "player_id": player_id,
                "player_name": season_rows[0].player_name,
                "appearances": total_apps,
                "starts": total_starts,
                "goals": total_goals,
                "assists": total_assists,
                "minutes": total_minutes,
                "yellow_cards": total_yellows,
                "red_cards": total_reds,
                "rating": avg_rating,
                "matches": [],  # No per-fixture data from this source
                "season_stats": [r.to_dict() for r in season_rows if (r.appearances or 0) > 0],
            }

        # Fall back to per-fixture appearances
        query = AcademyAppearance.query.filter_by(player_id=player_id)
        if date_from:
            query = query.filter(AcademyAppearance.fixture_date >= date_from)
        if date_to:
            query = query.filter(AcademyAppearance.fixture_date <= date_to)

        appearances = query.order_by(AcademyAppearance.fixture_date.desc()).all()

        if not appearances:
            return {
                "player_id": player_id,
                "appearances": 0,
                "starts": 0,
                "goals": 0,
                "assists": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "matches": [],
            }

        return {
            "player_id": player_id,
            "player_name": appearances[0].player_name,
            "appearances": len(appearances),
            "starts": sum(1 for a in appearances if a.started),
            "goals": sum(a.goals for a in appearances),
            "assists": sum(a.assists for a in appearances),
            "yellow_cards": sum(a.yellow_cards for a in appearances),
            "red_cards": sum(a.red_cards for a in appearances),
            "matches": [a.to_dict() for a in appearances[:10]],
        }


# Singleton instance
academy_sync_service = AcademySyncService()
