"""
Backfill academy_club_ids for all existing PlayerJourney records.

Usage:
    flask shell < scripts/backfill_academy_ids.py
"""

from src.models.journey import PlayerJourney
from src.models.league import db
from src.services.journey_sync import JourneySyncService
from src.utils.log_privacy import log_metadata

sync_service = JourneySyncService()

journeys = PlayerJourney.query.filter(
    (PlayerJourney.academy_club_ids.is_(None)) | (PlayerJourney.academy_club_ids is None)
).all()

print(f"Found {len(journeys)} journeys to backfill")

updated = 0
for journey in journeys:
    sync_service._compute_academy_club_ids(journey)
    if journey.academy_club_ids:
        updated += 1
        print(
            f"  {log_metadata(journey.player_name)} (#{log_metadata(journey.player_api_id)}): {log_metadata(journey.academy_club_ids)}"
        )

db.session.commit()
print(f"Done. Updated {log_metadata(updated)}/{len(journeys)} journeys with academy club IDs.")
