"""National youth sides take precedence over club youth age labels."""

from unittest.mock import Mock

import pytest
from src.services.journey_sync import JourneySyncService


@pytest.mark.parametrize(
    "team,competition,expected",
    [
        ("England U21", "UEFA U21 Championship", "International Youth"),
        ("Spain U19", "U19 Euro", "International Youth"),
        ("Argentina U20", "U20 World Cup", "International Youth"),
        ("England U21", "Friendlies", "International Youth"),
        ("England", "World Cup", "International"),
        ("Manchester United U21", "EFL Trophy", "U21"),
        ("Arsenal U18", "FA Youth Cup", "U18"),
        ("Liverpool", "Champions League", "First Team"),
        ("Arsenal U21", "Friendlies Clubs", "U21"),
        ("Brazil", "Friendlies", "International"),
        ("Manchester Utd U23", "Premier League 2 Division One", "U23"),
    ],
)
def test_international_youth_precedence_preserves_club_classification(team, competition, expected):
    service = JourneySyncService(api_client=Mock())
    assert service._classify_level(team, competition) == expected
