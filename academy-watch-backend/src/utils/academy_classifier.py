"""
Academy Classifier Utility

Centralised helpers for determining a player's relationship to their
academy / parent club.  Used by:
 - JourneySyncService (journey building)
 - Seed endpoint (TrackedPlayer status derivation)
 - Any future code that needs to distinguish academy, on-loan,
   first-team, or international status.
"""

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# ── regex to strip youth suffixes from club names ──────────────────────
YOUTH_SUFFIXES = re.compile(
    r'\s+(U18|U19|U21|U23|Under[\s-]?\d+|II|B|Youth|Academy|Reserve|Development)s?$',
    re.IGNORECASE,
)

# ── regex to strip age-group suffix from national team names ───────────
_NATIONAL_TEAM_AGE_SUFFIX = re.compile(r'\s+U\d{2}$')

# ── FIFA nations (used by is_national_team) ────────────────────────────
_FIFA_NATIONS = frozenset({
    'Afghanistan', 'Albania', 'Algeria', 'American Samoa', 'Andorra',
    'Angola', 'Antigua and Barbuda', 'Argentina', 'Armenia', 'Aruba',
    'Australia', 'Austria', 'Azerbaijan', 'Bahamas', 'Bahrain',
    'Bangladesh', 'Barbados', 'Belarus', 'Belgium', 'Belize', 'Benin',
    'Bermuda', 'Bhutan', 'Bolivia', 'Bosnia and Herzegovina', 'Botswana',
    'Brazil', 'Brunei', 'Bulgaria', 'Burkina Faso', 'Burundi',
    'Cambodia', 'Cameroon', 'Canada', 'Cape Verde', 'Central African Republic',
    'Chad', 'Chile', 'China', 'Chinese Taipei', 'Colombia', 'Comoros',
    'Congo', 'Costa Rica', 'Croatia', 'Cuba', 'Curacao', 'Cyprus',
    'Czech Republic', 'Czechia', 'Denmark', 'Djibouti', 'Dominica',
    'Dominican Republic', 'DR Congo', 'East Timor', 'Ecuador', 'Egypt',
    'El Salvador', 'England', 'Equatorial Guinea', 'Eritrea', 'Estonia',
    'Eswatini', 'Ethiopia', 'Faroe Islands', 'Fiji', 'Finland', 'France',
    'Gabon', 'Gambia', 'Georgia', 'Germany', 'Ghana', 'Gibraltar',
    'Greece', 'Grenada', 'Guam', 'Guatemala', 'Guinea', 'Guinea-Bissau',
    'Guyana', 'Haiti', 'Honduras', 'Hong Kong', 'Hungary', 'Iceland',
    'India', 'Indonesia', 'Iran', 'Iraq', 'Ireland', 'Israel', 'Italy',
    'Ivory Coast', 'Jamaica', 'Japan', 'Jordan', 'Kazakhstan', 'Kenya',
    'Kosovo', 'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon',
    'Lesotho', 'Liberia', 'Libya', 'Liechtenstein', 'Lithuania',
    'Luxembourg', 'Macau', 'Madagascar', 'Malawi', 'Malaysia', 'Maldives',
    'Mali', 'Malta', 'Mauritania', 'Mauritius', 'Mexico', 'Moldova',
    'Mongolia', 'Montenegro', 'Montserrat', 'Morocco', 'Mozambique',
    'Myanmar', 'Namibia', 'Nepal', 'Netherlands', 'New Caledonia',
    'New Zealand', 'Nicaragua', 'Niger', 'Nigeria', 'North Korea',
    'North Macedonia', 'Northern Ireland', 'Norway', 'Oman', 'Pakistan',
    'Palestine', 'Panama', 'Papua New Guinea', 'Paraguay', 'Peru',
    'Philippines', 'Poland', 'Portugal', 'Puerto Rico', 'Qatar',
    'Republic of Ireland', 'Romania', 'Russia', 'Rwanda', 'Saint Kitts and Nevis',
    'Saint Lucia', 'Saint Vincent and the Grenadines', 'Samoa',
    'San Marino', 'Sao Tome and Principe', 'Saudi Arabia', 'Scotland',
    'Senegal', 'Serbia', 'Seychelles', 'Sierra Leone', 'Singapore',
    'Slovakia', 'Slovenia', 'Solomon Islands', 'Somalia', 'South Africa',
    'South Korea', 'South Sudan', 'Spain', 'Sri Lanka', 'Sudan',
    'Suriname', 'Sweden', 'Switzerland', 'Syria', 'Tahiti', 'Tajikistan',
    'Tanzania', 'Thailand', 'Togo', 'Tonga', 'Trinidad and Tobago',
    'Tunisia', 'Turkey', 'Turkmenistan', 'Turks and Caicos Islands',
    'Uganda', 'Ukraine', 'United Arab Emirates', 'United States',
    'Uruguay', 'US Virgin Islands', 'Uzbekistan', 'Vanuatu', 'Venezuela',
    'Vietnam', 'Wales', 'Yemen', 'Zambia', 'Zimbabwe',
})

# ── international competition keywords ─────────────────────────────────
INTERNATIONAL_PATTERNS = [
    'world cup', 'euro', 'copa america', 'african cup', 'asian cup',
    'gold cup', 'nations league', 'friendlies', 'qualification',
    'u20 world', 'u17 world', 'olympic', 'toulon', 'maurice revello',
]

# ── levels that count as "international" ───────────────────────────────
INTERNATIONAL_LEVELS = {'International', 'International Youth'}


# ─── public helpers ────────────────────────────────────────────────────

def strip_youth_suffix(club_name: str) -> str:
    """Strip youth-team suffix to get the parent club's base name.

    >>> strip_youth_suffix('Arsenal U21')
    'Arsenal'
    >>> strip_youth_suffix('Chelsea')
    'Chelsea'
    """
    return YOUTH_SUFFIXES.sub('', club_name).strip()


def is_international_level(level: Optional[str]) -> bool:
    """Return True if the level represents international duty."""
    return (level or '') in INTERNATIONAL_LEVELS


def is_international_competition(league_name: str) -> bool:
    """Return True if the league/competition name looks international."""
    lower = league_name.lower()
    return any(p in lower for p in INTERNATIONAL_PATTERNS)


def is_national_team(club_name: Optional[str]) -> bool:
    """Return True if *club_name* looks like a national team.

    Strips an optional youth age-group suffix (e.g. "U17", "U21") then
    checks the base name against a known set of FIFA nations.

    >>> is_national_team('England U17')
    True
    >>> is_national_team('Spain')
    True
    >>> is_national_team('Arsenal')
    False
    """
    if not club_name:
        return False
    base = _NATIONAL_TEAM_AGE_SUFFIX.sub('', club_name).strip()
    return base in _FIFA_NATIONS


def is_same_club(club_name: str, parent_club_name: str) -> bool:
    """Return True if *club_name* is really the same organisation as
    *parent_club_name* (e.g. "Arsenal U21" → "Arsenal").
    """
    if not club_name or not parent_club_name:
        return False
    base = strip_youth_suffix(club_name).lower()
    parent = parent_club_name.lower()
    return base == parent


def derive_player_status(
    current_club_api_id: Optional[int],
    current_club_name: Optional[str],
    current_level: Optional[str],
    parent_api_id: int,
    parent_club_name: str,
) -> Tuple[str, Optional[int], Optional[str]]:
    """Derive (status, loan_club_api_id, loan_club_name) for a player
    relative to their parent / academy club.

    Rules (in order):
    1. International duty  → not a loan (keep academy / first_team)
    2. Same club (youth-suffix stripped) → not a loan
    3. Same API ID as parent → not a loan
    4. Different club → on_loan

    Returns:
        (status, loan_club_api_id, loan_club_name)
        where status is one of 'academy', 'first_team', 'on_loan'
    """
    # No current club info → assume still at academy
    if not current_club_api_id:
        return ('academy', None, None)

    # 1. International duty is never a loan
    if is_international_level(current_level):
        return (_base_status(current_level), None, None)

    # 1b. National team club name is never a loan
    if is_national_team(current_club_name):
        return (_base_status(current_level), None, None)

    # 2. Same API ID → player at the parent club itself
    if current_club_api_id == parent_api_id:
        return (_base_status(current_level), None, None)

    # 3. Same club with youth suffix (e.g. "Arsenal U21" for Arsenal)
    if is_same_club(current_club_name or '', parent_club_name):
        return (_base_status(current_level), None, None)

    # 4. Genuinely at a different club → on loan
    return ('on_loan', current_club_api_id, current_club_name)


def derive_player_status_with_reasoning(
    current_club_api_id: Optional[int],
    current_club_name: Optional[str],
    current_level: Optional[str],
    parent_api_id: int,
    parent_club_name: str,
) -> Tuple[str, Optional[int], Optional[str], List[Dict]]:
    """Like derive_player_status but also returns step-by-step reasoning.

    Returns:
        (status, loan_club_api_id, loan_club_name, reasoning)
        where reasoning is a list of dicts with rule/check/result/detail.
    """
    reasoning: List[Dict] = []

    if not current_club_api_id:
        reasoning.append({
            'rule': 'no_current_club', 'result': 'match',
            'check': 'current_club_api_id is null',
            'detail': 'No current club info — defaulting to academy',
        })
        return 'academy', None, None, reasoning
    reasoning.append({
        'rule': 'no_current_club', 'result': 'pass',
        'check': 'current_club_api_id is not null',
        'detail': f'Current club: {current_club_name} ({current_club_api_id})',
    })

    intl = is_international_level(current_level)
    reasoning.append({
        'rule': 'international_level', 'result': 'match' if intl else 'pass',
        'check': f'current_level "{current_level}" in INTERNATIONAL_LEVELS',
        'detail': f'Level {"is" if intl else "is not"} international',
    })
    if intl:
        return _base_status(current_level), None, None, reasoning

    natl = is_national_team(current_club_name)
    reasoning.append({
        'rule': 'national_team', 'result': 'match' if natl else 'pass',
        'check': f'is_national_team("{current_club_name}")',
        'detail': f'"{current_club_name}" {"is" if natl else "is not"} a national team',
    })
    if natl:
        return _base_status(current_level), None, None, reasoning

    same_id = (current_club_api_id == parent_api_id)
    reasoning.append({
        'rule': 'same_api_id', 'result': 'match' if same_id else 'pass',
        'check': f'{current_club_api_id} == {parent_api_id}',
        'detail': f'{current_club_api_id} {"==" if same_id else "!="} {parent_api_id}',
    })
    if same_id:
        return _base_status(current_level), None, None, reasoning

    same_name = is_same_club(current_club_name or '', parent_club_name)
    stripped = strip_youth_suffix(current_club_name or '').lower()
    reasoning.append({
        'rule': 'same_club_name', 'result': 'match' if same_name else 'pass',
        'check': f'strip_youth_suffix("{current_club_name}") == "{parent_club_name}"',
        'detail': f'"{stripped}" {"==" if same_name else "!="} "{parent_club_name.lower()}"',
    })
    if same_name:
        return _base_status(current_level), None, None, reasoning

    reasoning.append({
        'rule': 'different_club', 'result': 'match',
        'check': 'No rules matched — different club',
        'detail': f'Classified as on_loan at {current_club_name}',
    })
    return 'on_loan', current_club_api_id, current_club_name, reasoning


def upgrade_status_from_transfers(
    status: str,
    transfers: list,
    parent_api_id: int,
) -> str:
    """Upgrade 'on_loan' → 'sold'/'released' when latest departure was permanent."""
    if status != 'on_loan' or not transfers:
        return status

    from src.api_football_client import is_new_loan_transfer

    departures = [
        t for t in transfers
        if (t.get('teams', {}).get('out', {}).get('id') == parent_api_id)
    ]
    if not departures:
        return status

    departures.sort(key=lambda t: t.get('date', ''), reverse=True)
    dep_type = (departures[0].get('type') or '').strip().lower()

    if not dep_type or is_new_loan_transfer(dep_type):
        return status  # still a loan

    # Permanent departure: free agent → 'released', else → 'sold'
    if dep_type in ('free agent', 'free', 'n/a'):
        return 'released'
    return 'sold'


# ─── unified classification entry point ───────────────────────────────

logger = logging.getLogger(__name__)

# Module-level cache for the active classification config.
_config_cache: Dict[str, Any] = {}
_CONFIG_TTL_SECONDS = 300  # 5 minutes


def _get_active_classification_config() -> Dict[str, Any]:
    """Load classification rules from the active RebuildConfig.

    Returns a dict with keys:
        use_transfers_for_status (bool, default True)
        inactivity_release_years (int | None, default None)

    Uses a module-level cache with 5-minute TTL to avoid a DB query on
    every call.
    """
    now = time.monotonic()
    if _config_cache and (now - _config_cache.get('_ts', 0)) < _CONFIG_TTL_SECONDS:
        return _config_cache

    defaults: Dict[str, Any] = {
        'use_transfers_for_status': True,
        'inactivity_release_years': 2,
        'use_squad_check': True,
    }

    try:
        from src.models.league import RebuildConfig
        active = RebuildConfig.query.filter_by(is_active=True).first()
        if active and active.config_json:
            raw = json.loads(active.config_json)
            defaults['use_transfers_for_status'] = raw.get(
                'use_transfers_for_status', True,
            )
            inactivity = raw.get('inactivity_release_years') or raw.get('inactivity_threshold_years')
            if inactivity is not None:
                defaults['inactivity_release_years'] = int(inactivity)
            if 'use_squad_check' in raw:
                defaults['use_squad_check'] = bool(raw['use_squad_check'])
    except Exception:
        pass  # Fall through to safe defaults

    defaults['_ts'] = now
    _config_cache.clear()
    _config_cache.update(defaults)
    return _config_cache


def flatten_transfers(raw_transfer_response: list) -> list:
    """Flatten API-Football nested transfer response to a flat list.

    API-Football returns ``[{player: {}, transfers: [...]}, ...]``.
    This helper extracts and concatenates every inner ``transfers`` list
    into a single flat list so callers don't need to do it themselves.
    """
    flat: list = []
    for block in (raw_transfer_response or []):
        if isinstance(block, dict):
            flat.extend(block.get('transfers', []))
    return flat


def _get_latest_season(
    journey_id: int,
    *,
    parent_api_id: int | None = None,
    parent_club_name: str | None = None,
) -> Optional[int]:
    """Get the most recent season from a player's journey entries.

    When *parent_api_id* (and optionally *parent_club_name*) are provided,
    entries at the parent club are preferred.  If no parent-club entries
    exist (common because API-Football records loan *destinations*, not
    the parent club itself), we fall back to the latest season at any club.
    Active loans will have recent entries that pass the inactivity
    threshold; truly inactive players will have old entries that trigger
    release.
    """
    from src.models.journey import PlayerJourneyEntry
    query = PlayerJourneyEntry.query.filter_by(journey_id=journey_id)

    if parent_api_id is not None:
        entries = query.order_by(PlayerJourneyEntry.season.desc()).all()
        for entry in entries:
            if entry.club_api_id == parent_api_id:
                return entry.season
            if parent_club_name and is_same_club(entry.club_name or '', parent_club_name):
                return entry.season
        # No entries at parent club — fall back to latest season at any club.
        # Active loans have recent entries (2025) that pass the threshold.
        # Truly inactive players have old entries that trigger release.
        if entries:
            return entries[0].season
        return None

    entry = query.order_by(PlayerJourneyEntry.season.desc()).first()
    return entry.season if entry else None


def classify_tracked_player(
    current_club_api_id: Optional[int],
    current_club_name: Optional[str],
    current_level: Optional[str],
    parent_api_id: int,
    parent_club_name: str,
    *,
    transfers: Optional[list] = None,
    player_api_id: Optional[int] = None,
    api_client: Any = None,
    config: Optional[Dict[str, Any]] = None,
    with_reasoning: bool = False,
    latest_season: Optional[int] = None,
    squad_members_by_club: Optional[Dict[int, Set[int]]] = None,
) -> Union[
    Tuple[str, Optional[int], Optional[str]],
    Tuple[str, Optional[int], Optional[str], List[Dict]],
]:
    """Single source of truth for player status classification.

    Applies these rules in order:
    1. Base status derivation (academy / first_team / on_loan)
    2. Transfer-based upgrade (on_loan → sold / released)
       — controlled by ``config['use_transfers_for_status']``
    2.5. Squad cross-reference (on_loan players only)
       — if player absent from loan club squad, check parent squad;
         returned to parent → academy/first_team, absent from both → released
       — controlled by ``config['use_squad_check']``
    3. Inactivity-based release (no data for N seasons)
       — controlled by ``config['inactivity_release_years']``

    Args:
        current_club_api_id: Player's current club from journey data.
        current_club_name: Player's current club name.
        current_level: Player's current level (First Team, U21 …).
        parent_api_id: Parent / academy club API-Football ID.
        parent_club_name: Parent / academy club name.
        transfers: Pre-fetched *flat* transfer list (already flattened).
            When ``None`` and ``use_transfers_for_status`` is True the
            function will attempt to fetch via *api_client*.
        player_api_id: Required when transfers must be fetched on demand.
        api_client: ``APIFootballClient`` instance for on-demand fetch.
        config: Classification config dict.  When ``None`` the active
            ``RebuildConfig`` is loaded (with caching).
        with_reasoning: Return step-by-step reasoning list.
        latest_season: The player's latest season year — used for the
            inactivity check.

    Returns:
        ``(status, loan_club_api_id, loan_club_name)`` or
        ``(status, loan_club_api_id, loan_club_name, reasoning)``
        when *with_reasoning* is True.
    """
    if config is None:
        config = _get_active_classification_config()

    # ── Step 1: base status derivation ────────────────────────────────
    if with_reasoning:
        status, loan_id, loan_name, reasoning = derive_player_status_with_reasoning(
            current_club_api_id, current_club_name, current_level,
            parent_api_id, parent_club_name,
        )
    else:
        status, loan_id, loan_name = derive_player_status(
            current_club_api_id, current_club_name, current_level,
            parent_api_id, parent_club_name,
        )
        reasoning: List[Dict] = []

    # ── Step 2: transfer-based upgrade ────────────────────────────────
    if status == 'on_loan' and config.get('use_transfers_for_status', True):
        effective_transfers = transfers
        if effective_transfers is None and player_api_id and api_client:
            try:
                raw = api_client.get_player_transfers(player_api_id)
                effective_transfers = flatten_transfers(raw)
            except Exception as exc:
                logger.warning('Transfer fetch failed for player %s: %s', player_api_id, exc)
                effective_transfers = []

        if effective_transfers:
            upgraded = upgrade_status_from_transfers(
                status, effective_transfers, parent_api_id,
            )
            if upgraded != status:
                if with_reasoning:
                    reasoning.append({
                        'rule': 'transfer_upgrade',
                        'result': 'match',
                        'check': f'upgrade_status_from_transfers("{status}")',
                        'detail': f'Upgraded from {status} to {upgraded}',
                    })
                status = upgraded
                loan_id = None
                loan_name = None

    # ── Step 2.5: squad cross-reference ────────────────────────────────
    if (status == 'on_loan' and config.get('use_squad_check')
            and squad_members_by_club is not None and player_api_id):
        loan_squad = squad_members_by_club.get(loan_id)
        parent_squad = squad_members_by_club.get(parent_api_id)
        in_loan_squad = loan_squad is not None and player_api_id in loan_squad
        in_parent_squad = parent_squad is not None and player_api_id in parent_squad
        if not in_loan_squad:
            if in_parent_squad:
                old_status = status
                status = _base_status(current_level)
                if with_reasoning:
                    reasoning.append({
                        'rule': 'squad_cross_reference',
                        'result': 'match',
                        'check': (
                            f'player {player_api_id} not in loan club '
                            f'{loan_id} squad, found in parent {parent_api_id}'
                        ),
                        'detail': (
                            f'Returned to parent club — '
                            f'{old_status} → {status}'
                        ),
                    })
                loan_id = None
                loan_name = None
            else:
                if with_reasoning:
                    reasoning.append({
                        'rule': 'squad_cross_reference',
                        'result': 'match',
                        'check': (
                            f'player {player_api_id} not in loan club '
                            f'{loan_id} or parent {parent_api_id} squad'
                        ),
                        'detail': 'Absent from both squads — released',
                    })
                status = 'released'
                loan_id = None
                loan_name = None

    # ── Step 3: inactivity-based release ──────────────────────────────
    inactivity_years = config.get('inactivity_release_years')
    if inactivity_years and latest_season is not None and status in ('academy', 'on_loan'):
        current_year = datetime.now().year
        if latest_season < current_year - inactivity_years:
            if with_reasoning:
                reasoning.append({
                    'rule': 'inactivity_release',
                    'result': 'match',
                    'check': (
                        f'latest_season {latest_season} < '
                        f'{current_year} - {inactivity_years}'
                    ),
                    'detail': (
                        f'No data for {current_year - latest_season} seasons — '
                        f'marking as released'
                    ),
                })
            status = 'released'
            loan_id = None
            loan_name = None

    if with_reasoning:
        return (status, loan_id, loan_name, reasoning)
    return (status, loan_id, loan_name)


# ─── internal ──────────────────────────────────────────────────────────

def _base_status(current_level: Optional[str]) -> str:
    """Pick 'first_team' or 'academy' based on the player's current level."""
    if current_level == 'First Team':
        return 'first_team'
    return 'academy'
