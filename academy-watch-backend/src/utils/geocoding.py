"""Geocoding utilities for team locations.

Converts city names to lat/lng coordinates for journey map visualization.
Uses a static lookup for major football cities, with Nominatim fallback.
"""

import logging
import requests
from typing import Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# Static lookup for major football cities to avoid API calls
# Format: 'city_name_lower': (latitude, longitude)
CITY_COORDINATES = {
    # England
    'manchester': (53.4808, -2.2426),
    'london': (51.5074, -0.1278),
    'liverpool': (53.4084, -2.9916),
    'birmingham': (52.4862, -1.8904),
    'leeds': (53.8008, -1.5491),
    'newcastle upon tyne': (54.9783, -1.6178),
    'newcastle': (54.9783, -1.6178),
    'sheffield': (53.3811, -1.4701),
    'nottingham': (52.9548, -1.1581),
    'leicester': (52.6369, -1.1398),
    'southampton': (50.9097, -1.4044),
    'brighton': (50.8225, -0.1372),
    'bournemouth': (50.7192, -1.8808),
    'wolverhampton': (52.5870, -2.1288),
    'west bromwich': (52.5095, -1.9946),
    'stoke-on-trent': (53.0027, -2.1794),
    'sunderland': (54.9069, -1.3838),
    'middlesbrough': (54.5742, -1.2350),
    'derby': (52.9225, -1.4746),
    'ipswich': (52.0567, 1.1482),
    'norwich': (52.6309, 1.2974),
    'hull': (53.7676, -0.3274),
    'bristol': (51.4545, -2.5879),
    'cardiff': (51.4816, -3.1791),
    'swansea': (51.6214, -3.9436),
    'burnley': (53.7897, -2.2480),
    'fulham': (51.4749, -0.2214),
    'brentford': (51.4882, -0.3028),
    'watford': (51.6565, -0.3965),
    'luton': (51.8787, -0.4200),
    'reading': (51.4543, -0.9781),
    'coventry': (52.4068, -1.5197),
    'blackburn': (53.7487, -2.4890),
    'bolton': (53.5785, -2.4299),
    'wigan': (53.5448, -2.6318),
    'preston': (53.7632, -2.7031),
    'huddersfield': (53.6450, -1.7798),
    'barnsley': (53.5526, -1.4794),
    'rotherham': (53.4326, -1.3635),
    'millwall': (51.4862, -0.0509),  # South Bermondsey
    'charlton': (51.4865, 0.0363),
    'portsmouth': (50.7961, -1.0631),
    'plymouth': (50.3755, -4.1427),
    'exeter': (50.7184, -3.5339),
    'oxford': (51.7520, -1.2577),
    'wycombe': (51.6308, -0.8003),
    'peterborough': (52.5695, -0.2405),
    'crewe': (53.0986, -2.4414),

    # Spain
    'madrid': (40.4168, -3.7038),
    'barcelona': (41.3874, 2.1686),
    'sevilla': (37.3891, -5.9845),
    'seville': (37.3891, -5.9845),
    'valencia': (39.4699, -0.3763),
    'bilbao': (43.2630, -2.9350),
    'san sebastian': (43.3183, -1.9812),
    'malaga': (36.7213, -4.4214),
    'vigo': (42.2406, -8.7207),
    'villarreal': (39.9439, -0.1006),
    'pamplona': (42.8125, -1.6458),

    # Germany
    'munich': (48.1351, 11.5820),
    'münchen': (48.1351, 11.5820),
    'dortmund': (51.5136, 7.4653),
    'berlin': (52.5200, 13.4050),
    'frankfurt': (50.1109, 8.6821),
    'hamburg': (53.5511, 9.9937),
    'leipzig': (51.3397, 12.3731),
    'cologne': (50.9375, 6.9603),
    'köln': (50.9375, 6.9603),
    'gelsenkirchen': (51.5177, 7.0857),
    'leverkusen': (51.0459, 7.0192),
    'mönchengladbach': (51.1805, 6.4428),
    'wolfsburg': (52.4227, 10.7865),
    'stuttgart': (48.7758, 9.1829),
    'bremen': (53.0793, 8.8017),
    'freiburg': (47.9990, 7.8421),
    'hoffenheim': (49.2372, 8.8869),  # Sinsheim
    'mainz': (49.9929, 8.2473),
    'augsburg': (48.3705, 10.8978),
    'bochum': (51.4818, 7.2196),

    # Italy
    'milan': (45.4642, 9.1900),
    'milano': (45.4642, 9.1900),
    'rome': (41.9028, 12.4964),
    'roma': (41.9028, 12.4964),
    'turin': (45.0703, 7.6869),
    'torino': (45.0703, 7.6869),
    'naples': (40.8518, 14.2681),
    'napoli': (40.8518, 14.2681),
    'florence': (43.7696, 11.2558),
    'firenze': (43.7696, 11.2558),
    'genoa': (44.4056, 8.9463),
    'genova': (44.4056, 8.9463),
    'bologna': (44.4949, 11.3426),
    'verona': (45.4384, 10.9916),
    'bergamo': (45.6983, 9.6773),

    # France
    'paris': (48.8566, 2.3522),
    'marseille': (43.2965, 5.3698),
    'lyon': (45.7640, 4.8357),
    'monaco': (43.7384, 7.4246),
    'lille': (50.6292, 3.0573),
    'nice': (43.7102, 7.2620),
    'bordeaux': (44.8378, -0.5792),
    'toulouse': (43.6047, 1.4442),
    'nantes': (47.2184, -1.5536),
    'strasbourg': (48.5734, 7.7521),
    'montpellier': (43.6108, 3.8767),
    'rennes': (48.1173, -1.6778),
    'lens': (50.4323, 2.8269),
    'reims': (49.2583, 4.0317),

    # Netherlands
    'amsterdam': (52.3676, 4.9041),
    'rotterdam': (51.9244, 4.4777),
    'eindhoven': (51.4416, 5.4697),
    'alkmaar': (52.6324, 4.7534),
    'enschede': (52.2215, 6.8937),
    'arnhem': (51.9851, 5.8987),
    'utrecht': (52.0907, 5.1214),

    # Portugal
    'lisbon': (38.7223, -9.1393),
    'lisboa': (38.7223, -9.1393),
    'porto': (41.1579, -8.6291),
    'braga': (41.5454, -8.4265),
    'guimaraes': (41.4425, -8.2918),

    # Scotland
    'glasgow': (55.8642, -4.2518),
    'edinburgh': (55.9533, -3.1883),
    'aberdeen': (57.1497, -2.0943),
    'dundee': (56.4620, -2.9707),

    # Belgium
    'brussels': (50.8503, 4.3517),
    'bruxelles': (50.8503, 4.3517),
    'bruges': (51.2093, 3.2247),
    'brugge': (51.2093, 3.2247),
    'ghent': (51.0543, 3.7174),
    'gent': (51.0543, 3.7174),
    'antwerp': (51.2194, 4.4025),
    'antwerpen': (51.2194, 4.4025),
    'liege': (50.6326, 5.5797),

    # Turkey
    'istanbul': (41.0082, 28.9784),
    'ankara': (39.9334, 32.8597),

    # Other
    'zurich': (47.3769, 8.5417),
    'vienna': (48.2082, 16.3738),
    'wien': (48.2082, 16.3738),
    'athens': (37.9838, 23.7275),
    'moscow': (55.7558, 37.6173),
}


@lru_cache(maxsize=500)
def geocode_city(city: str, country: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """Get coordinates for a city.

    Args:
        city: City name
        country: Optional country name for disambiguation

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    if not city:
        return None

    city_lower = city.lower().strip()

    # Check static lookup first
    if city_lower in CITY_COORDINATES:
        return CITY_COORDINATES[city_lower]

    # Try with country suffix removed if present
    city_clean = city_lower.replace(',', '').split()[0] if ',' in city_lower else city_lower
    if city_clean in CITY_COORDINATES:
        return CITY_COORDINATES[city_clean]

    # Fallback to Nominatim (OpenStreetMap)
    try:
        return _nominatim_geocode(city, country)
    except Exception as e:
        logger.warning(f"Geocoding failed for {city}, {country}: {e}")
        return None


def _nominatim_geocode(city: str, country: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """Query Nominatim API for coordinates.

    Note: Nominatim has usage limits (1 request/second, no heavy usage).
    We cache results aggressively via lru_cache.
    """
    query = f"{city}, {country}" if country else city

    headers = {
        'User-Agent': 'TheAcademyWatch/1.0 (contact@theacademywatch.com)'
    }

    params = {
        'q': query,
        'format': 'json',
        'limit': 1,
    }

    try:
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params=params,
            headers=headers,
            timeout=5
        )
        response.raise_for_status()

        data = response.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            logger.info(f"Geocoded {query} -> ({lat}, {lon})")
            return (lat, lon)

    except Exception as e:
        logger.warning(f"Nominatim geocode failed for {query}: {e}")

    return None


def get_team_coordinates(venue_city: Optional[str], venue_country: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """Get coordinates for a team based on venue info.

    Args:
        venue_city: City from API-Football venue data
        venue_country: Country from API-Football

    Returns:
        Tuple of (latitude, longitude) or None
    """
    if not venue_city:
        return None

    return geocode_city(venue_city, venue_country)
