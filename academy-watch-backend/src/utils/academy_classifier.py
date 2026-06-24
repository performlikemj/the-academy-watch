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
from typing import Any

from src.utils.academy_window import DEVELOPMENT_AGE_CUTOFF as _DEVELOPMENT_AGE_CUTOFF

# ── regex to strip youth suffixes from club names ──────────────────────
YOUTH_SUFFIXES = re.compile(
    r"\s+(U18|U19|U21|U23|Under[\s-]?\d+|II|B|Youth|Academy|Reserve|Development)s?$",
    re.IGNORECASE,
)

# ── regex to strip age-group suffix from national team names ───────────
_NATIONAL_TEAM_AGE_SUFFIX = re.compile(r"\s+U\d{2}$")

# ── FIFA nations (used by is_national_team) ────────────────────────────
_FIFA_NATIONS = frozenset(
    {
        "Afghanistan",
        "Albania",
        "Algeria",
        "American Samoa",
        "Andorra",
        "Angola",
        "Antigua and Barbuda",
        "Argentina",
        "Armenia",
        "Aruba",
        "Australia",
        "Austria",
        "Azerbaijan",
        "Bahamas",
        "Bahrain",
        "Bangladesh",
        "Barbados",
        "Belarus",
        "Belgium",
        "Belize",
        "Benin",
        "Bermuda",
        "Bhutan",
        "Bolivia",
        "Bosnia and Herzegovina",
        "Botswana",
        "Brazil",
        "Brunei",
        "Bulgaria",
        "Burkina Faso",
        "Burundi",
        "Cambodia",
        "Cameroon",
        "Canada",
        "Cape Verde",
        "Central African Republic",
        "Chad",
        "Chile",
        "China",
        "Chinese Taipei",
        "Colombia",
        "Comoros",
        "Congo",
        "Costa Rica",
        "Croatia",
        "Cuba",
        "Curacao",
        "Cyprus",
        "Czech Republic",
        "Czechia",
        "Denmark",
        "Djibouti",
        "Dominica",
        "Dominican Republic",
        "DR Congo",
        "East Timor",
        "Ecuador",
        "Egypt",
        "El Salvador",
        "England",
        "Equatorial Guinea",
        "Eritrea",
        "Estonia",
        "Eswatini",
        "Ethiopia",
        "Faroe Islands",
        "Fiji",
        "Finland",
        "France",
        "Gabon",
        "Gambia",
        "Georgia",
        "Germany",
        "Ghana",
        "Gibraltar",
        "Greece",
        "Grenada",
        "Guam",
        "Guatemala",
        "Guinea",
        "Guinea-Bissau",
        "Guyana",
        "Haiti",
        "Honduras",
        "Hong Kong",
        "Hungary",
        "Iceland",
        "India",
        "Indonesia",
        "Iran",
        "Iraq",
        "Ireland",
        "Israel",
        "Italy",
        "Ivory Coast",
        "Jamaica",
        "Japan",
        "Jordan",
        "Kazakhstan",
        "Kenya",
        "Kosovo",
        "Kuwait",
        "Kyrgyzstan",
        "Laos",
        "Latvia",
        "Lebanon",
        "Lesotho",
        "Liberia",
        "Libya",
        "Liechtenstein",
        "Lithuania",
        "Luxembourg",
        "Macau",
        "Madagascar",
        "Malawi",
        "Malaysia",
        "Maldives",
        "Mali",
        "Malta",
        "Mauritania",
        "Mauritius",
        "Mexico",
        "Moldova",
        "Mongolia",
        "Montenegro",
        "Montserrat",
        "Morocco",
        "Mozambique",
        "Myanmar",
        "Namibia",
        "Nepal",
        "Netherlands",
        "New Caledonia",
        "New Zealand",
        "Nicaragua",
        "Niger",
        "Nigeria",
        "North Korea",
        "North Macedonia",
        "Northern Ireland",
        "Norway",
        "Oman",
        "Pakistan",
        "Palestine",
        "Panama",
        "Papua New Guinea",
        "Paraguay",
        "Peru",
        "Philippines",
        "Poland",
        "Portugal",
        "Puerto Rico",
        "Qatar",
        "Republic of Ireland",
        "Romania",
        "Russia",
        "Rwanda",
        "Saint Kitts and Nevis",
        "Saint Lucia",
        "Saint Vincent and the Grenadines",
        "Samoa",
        "San Marino",
        "Sao Tome and Principe",
        "Saudi Arabia",
        "Scotland",
        "Senegal",
        "Serbia",
        "Seychelles",
        "Sierra Leone",
        "Singapore",
        "Slovakia",
        "Slovenia",
        "Solomon Islands",
        "Somalia",
        "South Africa",
        "South Korea",
        "South Sudan",
        "Spain",
        "Sri Lanka",
        "Sudan",
        "Suriname",
        "Sweden",
        "Switzerland",
        "Syria",
        "Tahiti",
        "Tajikistan",
        "Tanzania",
        "Thailand",
        "Togo",
        "Tonga",
        "Trinidad and Tobago",
        "Tunisia",
        "Turkey",
        "Turkmenistan",
        "Turks and Caicos Islands",
        "Uganda",
        "Ukraine",
        "United Arab Emirates",
        "United States",
        "Uruguay",
        "US Virgin Islands",
        "Uzbekistan",
        "Vanuatu",
        "Venezuela",
        "Vietnam",
        "Wales",
        "Yemen",
        "Zambia",
        "Zimbabwe",
    }
)

# ── international competition keywords ─────────────────────────────────
INTERNATIONAL_PATTERNS = [
    "world cup",
    "euro",
    "copa america",
    "african cup",
    "asian cup",
    "gold cup",
    "nations league",
    "friendlies",
    "qualification",
    "u20 world",
    "u17 world",
    "olympic",
    "toulon",
    "maurice revello",
    "caf",
    "concacaf",
    "conmebol",
    "afc",
    "cup of nations",
]

# ── levels that count as "international" ───────────────────────────────
INTERNATIONAL_LEVELS = {"International", "International Youth"}


# ─── public helpers ────────────────────────────────────────────────────


def strip_youth_suffix(club_name: str) -> str:
    """Strip youth-team suffix to get the parent club's base name.

    >>> strip_youth_suffix('Arsenal U21')
    'Arsenal'
    >>> strip_youth_suffix('Chelsea')
    'Chelsea'
    """
    return YOUTH_SUFFIXES.sub("", club_name).strip()


def is_international_level(level: str | None) -> bool:
    """Return True if the level represents international duty."""
    return (level or "") in INTERNATIONAL_LEVELS


def is_international_competition(league_name: str) -> bool:
    """Return True if the league/competition name looks international."""
    lower = league_name.lower()
    return any(p in lower for p in INTERNATIONAL_PATTERNS)


def is_national_team(club_name: str | None) -> bool:
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
    base = _NATIONAL_TEAM_AGE_SUFFIX.sub("", club_name).strip()
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
    current_club_api_id: int | None,
    current_club_name: str | None,
    current_level: str | None,
    parent_api_id: int,
    parent_club_name: str,
) -> tuple[str, int | None, str | None]:
    """Derive (status, current_club_api_id, current_club_name) for a player
    relative to their parent / academy club.

    Rules (in order):
    1. International duty  → not a loan (keep academy / first_team)
    2. Same club (youth-suffix stripped) → not a loan
    3. Same API ID as parent → not a loan
    4. Different club → on_loan

    Returns:
        (status, current_club_api_id, current_club_name)
        where status is one of 'academy', 'first_team', 'on_loan'
    """
    # No current club info → trust current_level. A first-team player who
    # was promoted internally (academy → first team) will have NULL
    # journey.current_club_api_id because there's no transfer event to
    # write it from, but their current_level is still 'First Team'. The
    # post-process at the end of classify_tracked_player will then
    # populate current_club_api_id/name from the parent academy club.
    if not current_club_api_id:
        return (_base_status(current_level), None, None)

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
    if is_same_club(current_club_name or "", parent_club_name):
        return (_base_status(current_level), None, None)

    # 3b. Parent's OWN reserve / youth / B side (Jong Ajax for Ajax, Atalanta
    # U20 for Atalanta, Birmingham U21 for Birmingham). Catches the cases
    # is_same_club misses — a "Jong " prefix, a U-number like U20, or an id
    # whose team name isn't loaded — so the player reads as still at the
    # parent, not as having left.
    from src.utils.affiliates import is_affiliate

    if is_affiliate(current_club_api_id, current_club_name, parent_api_id, parent_club_name):
        return (_base_status(current_level), None, None)

    # 4. Genuinely at a different club → tentatively on_loan; the transfer
    # check in classify_tracked_player Step 2 decides the real status
    # (on_loan only with a parent loan record; sold / released / left otherwise).
    return ("on_loan", current_club_api_id, current_club_name)


def derive_player_status_with_reasoning(
    current_club_api_id: int | None,
    current_club_name: str | None,
    current_level: str | None,
    parent_api_id: int,
    parent_club_name: str,
) -> tuple[str, int | None, str | None, list[dict]]:
    """Like derive_player_status but also returns step-by-step reasoning.

    Returns:
        (status, current_club_api_id, current_club_name, reasoning)
        where reasoning is a list of dicts with rule/check/result/detail.
    """
    reasoning: list[dict] = []

    if not current_club_api_id:
        base = _base_status(current_level)
        reasoning.append(
            {
                "rule": "no_current_club",
                "result": "match",
                "check": "current_club_api_id is null",
                "detail": (
                    f"No current club info — falling back to current_level "
                    f'"{current_level}" → status="{base}". Will be populated '
                    f"from parent club by post-process if status is first_team."
                ),
            }
        )
        return base, None, None, reasoning
    reasoning.append(
        {
            "rule": "no_current_club",
            "result": "pass",
            "check": "current_club_api_id is not null",
            "detail": f"Current club: {current_club_name} ({current_club_api_id})",
        }
    )

    intl = is_international_level(current_level)
    reasoning.append(
        {
            "rule": "international_level",
            "result": "match" if intl else "pass",
            "check": f'current_level "{current_level}" in INTERNATIONAL_LEVELS',
            "detail": f"Level {'is' if intl else 'is not'} international",
        }
    )
    if intl:
        return _base_status(current_level), None, None, reasoning

    natl = is_national_team(current_club_name)
    reasoning.append(
        {
            "rule": "national_team",
            "result": "match" if natl else "pass",
            "check": f'is_national_team("{current_club_name}")',
            "detail": f'"{current_club_name}" {"is" if natl else "is not"} a national team',
        }
    )
    if natl:
        return _base_status(current_level), None, None, reasoning

    same_id = current_club_api_id == parent_api_id
    reasoning.append(
        {
            "rule": "same_api_id",
            "result": "match" if same_id else "pass",
            "check": f"{current_club_api_id} == {parent_api_id}",
            "detail": f"{current_club_api_id} {'==' if same_id else '!='} {parent_api_id}",
        }
    )
    if same_id:
        return _base_status(current_level), None, None, reasoning

    same_name = is_same_club(current_club_name or "", parent_club_name)
    stripped = strip_youth_suffix(current_club_name or "").lower()
    reasoning.append(
        {
            "rule": "same_club_name",
            "result": "match" if same_name else "pass",
            "check": f'strip_youth_suffix("{current_club_name}") == "{parent_club_name}"',
            "detail": f'"{stripped}" {"==" if same_name else "!="} "{parent_club_name.lower()}"',
        }
    )
    if same_name:
        return _base_status(current_level), None, None, reasoning

    from src.utils.affiliates import is_affiliate

    affiliate = is_affiliate(current_club_api_id, current_club_name, parent_api_id, parent_club_name)
    reasoning.append(
        {
            "rule": "affiliate_b_team",
            "result": "match" if affiliate else "pass",
            "check": f'is_affiliate("{current_club_name}", parent "{parent_club_name}")',
            "detail": f'"{current_club_name}" {"is" if affiliate else "is not"} the parent\'s own reserve/youth side',
        }
    )
    if affiliate:
        return _base_status(current_level), None, None, reasoning

    reasoning.append(
        {
            "rule": "different_club",
            "result": "match",
            "check": "No rules matched — different club (transfer check decides on_loan/sold/released/left)",
            "detail": f"Tentatively on_loan at {current_club_name}",
        }
    )
    return "on_loan", current_club_api_id, current_club_name, reasoning


def upgrade_status_from_transfers(
    status: str,
    transfers: list,
    parent_api_id: int,
    current_club_api_id: int | None = None,
    parent_club_name: str | None = None,
) -> str:
    """Decide the real status of a player who is at a club other than the
    parent academy, from transfer evidence. Resolves the tentative 'on_loan'
    from derive_player_status into one of on_loan / sold / released / left.

    The key inversion: 'on_loan' must be EARNED by a parent loan record; it is
    no longer the fallback. Rules (relative to parent P), in order:

      • current club is a P loan destination (a P→current loan transfer) → on_loan
      • no departure from P at all, but player is elsewhere            → left
      • latest P departure is a loan but current ∉ P loan dests
        (loaned then moved on)                                         → left
      • latest P departure is permanent with a real, non-parent,
        non-national destination                                       → sold
      • latest P departure is permanent with no resolvable destination → released

    Loan destinations and departures are matched against P OR P's own
    reserve/youth/B side (e.g. Valencia and Valencia II both count as a Valencia
    loan), and ignore null destination ids and loan-RETURN types.
    """
    if status != "on_loan" or not transfers:
        return status

    from src.api_football_client import is_new_loan_transfer
    from src.utils.affiliates import is_affiliate

    def _out_is_parent(t: dict) -> bool:
        o = t.get("teams", {}).get("out", {}) or {}
        oid = o.get("id")
        return oid == parent_api_id or is_affiliate(oid, o.get("name"), parent_api_id, parent_club_name)

    # Loan destinations the PARENT (or its B-team) loaned the player to.
    # Exclude null in.id; is_new_loan_transfer already excludes loan-returns.
    loan_destinations = {
        (t.get("teams", {}).get("in", {}) or {}).get("id")
        for t in transfers
        if is_new_loan_transfer((t.get("type") or "").strip().lower()) and _out_is_parent(t)
    }
    loan_destinations.discard(None)

    # Genuine current loan FROM the parent — transfer-driven, not entry-type
    # driven (a brand-new loan has no synced fixtures yet so its journey entry
    # is not typed 'loan', but the loan transfer is already present).
    if current_club_api_id and current_club_api_id in loan_destinations:
        return "on_loan"

    # The 'left' outcomes require a KNOWN current club (the player is
    # demonstrably elsewhere). When current_club_api_id is unknown we cannot
    # assert they left, so we keep the tentative on_loan (callers that classify
    # without a current club rely on this conservative behaviour).
    departures = [t for t in transfers if _out_is_parent(t)]
    if not departures:
        # The player is at a different club but there is NO recorded departure
        # from the parent (typical of academy-to-academy youth moves). They
        # left the academy without a recorded senior transfer.
        return "left" if current_club_api_id else status

    departures.sort(key=lambda t: t.get("date", ""), reverse=True)
    dep_type = (departures[0].get("type") or "").strip().lower()

    if not dep_type or is_new_loan_transfer(dep_type):
        # Latest parent departure is a loan. We already returned on_loan above
        # if the current club is one of the parent's loan destinations, so a
        # known current club here means loaned-out-then-moved-on → left.
        return "left" if current_club_api_id else status

    # Permanent (non-loan) departure. The transfer TYPE alone cannot tell a
    # free-agency exit from a permanent move to a new club: API-Football
    # populates teams.in for virtually every departure, and an undisclosed-fee
    # sale is typed "N/A" (not a release). Decide on the departure's recorded
    # destination — a real, non-parent, non-national club ⇒ 'sold'; no recorded
    # destination ⇒ 'released' (a genuine free-agency exit; Step-3 inactivity
    # is the other path to 'released'). Read only the departure's teams.in,
    # NOT the journey's current club: an empty teams.in is the free-agency
    # signal, and folding in a stale last-club would manufacture a false 'sold'.
    dest = departures[0].get("teams", {}).get("in", {}) or {}
    dest_id = dest.get("id")
    if dest_id and dest_id != parent_api_id and not is_national_team(dest.get("name")):
        return "sold"
    return "released"


# ─── unified classification entry point ───────────────────────────────

logger = logging.getLogger(__name__)

# Module-level cache for the active classification config.
_config_cache: dict[str, Any] = {}
_CONFIG_TTL_SECONDS = 300  # 5 minutes


def _get_active_classification_config() -> dict[str, Any]:
    """Load classification rules from the active RebuildConfig.

    Returns a dict with keys:
        use_transfers_for_status (bool, default True) — retained for
            backward compatibility only; the loan→sold/released upgrade now
            always runs regardless of this flag (see classify_tracked_player
            Step 2). It no longer suppresses sold-detection.
        inactivity_release_years (int | None, default None)

    Uses a module-level cache with 5-minute TTL to avoid a DB query on
    every call.
    """
    now = time.monotonic()
    if _config_cache and (now - _config_cache.get("_ts", 0)) < _CONFIG_TTL_SECONDS:
        return _config_cache

    defaults: dict[str, Any] = {
        "use_transfers_for_status": True,
        "inactivity_release_years": 2,
        "use_squad_check": True,
    }

    try:
        from src.models.league import RebuildConfig

        active = RebuildConfig.query.filter_by(is_active=True).first()
        if active and active.config_json:
            raw = json.loads(active.config_json)
            defaults["use_transfers_for_status"] = raw.get(
                "use_transfers_for_status",
                True,
            )
            inactivity = raw.get("inactivity_release_years") or raw.get("inactivity_threshold_years")
            if inactivity is not None:
                defaults["inactivity_release_years"] = int(inactivity)
            if "use_squad_check" in raw:
                defaults["use_squad_check"] = bool(raw["use_squad_check"])
    except Exception:
        pass  # Fall through to safe defaults

    defaults["_ts"] = now
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
    for block in raw_transfer_response or []:
        if isinstance(block, dict):
            flat.extend(block.get("transfers", []))
    return flat


def _get_latest_season(
    journey_id: int,
    *,
    parent_api_id: int | None = None,
    parent_club_name: str | None = None,
) -> int | None:
    """Get the player's most recent season of CLUB activity, for the
    inactivity-release check.

    "Latest activity" must mean "played for any club recently", NOT "last
    seen at the parent club". A player sold or loaned away keeps appearing
    for other clubs, while their newest *parent-named* entry is often a
    stale youth season (e.g. "<Parent> U19"). Returning that stale season
    wrongly trips the Step-3 inactivity rule → 'released' even though the
    player is actively playing elsewhere. So return the latest *domestic*
    season at ANY club. International caps are not club activity and are
    excluded (a recent youth-international appearance must not keep an
    otherwise-inactive player active).

    *parent_api_id* / *parent_club_name* are accepted for signature
    compatibility with callers but no longer bias the result toward the
    parent.
    """
    from src.models.journey import PlayerJourneyEntry

    entries = PlayerJourneyEntry.query.filter_by(journey_id=journey_id).order_by(PlayerJourneyEntry.season.desc()).all()
    if not entries:
        return None

    domestic = [e for e in entries if not e.is_international]
    if domestic:
        return domestic[0].season
    # Only international entries exist — fall back to the latest of those.
    return entries[0].season


def classify_tracked_player(
    current_club_api_id: int | None,
    current_club_name: str | None,
    current_level: str | None,
    parent_api_id: int,
    parent_club_name: str,
    *,
    transfers: list | None = None,
    player_api_id: int | None = None,
    api_client: Any = None,
    config: dict[str, Any] | None = None,
    with_reasoning: bool = False,
    latest_season: int | None = None,
    squad_members_by_club: dict[int, set[int]] | None = None,
) -> tuple[str, int | None, str | None] | tuple[str, int | None, str | None, list[dict]]:
    """Single source of truth for player status classification.

    Applies these rules in order:
    1. Base status derivation (academy / first_team / on_loan)
    2. Transfer-based upgrade (on_loan → sold / released)
       — always runs when transfer data is available (core correctness;
         a permanent departure must never read as a loan)
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
            When ``None`` the function will attempt to fetch via
            *api_client* (if *player_api_id* is also supplied).
        player_api_id: Required when transfers must be fetched on demand.
        api_client: ``APIFootballClient`` instance for on-demand fetch.
        config: Classification config dict.  When ``None`` the active
            ``RebuildConfig`` is loaded (with caching).
        with_reasoning: Return step-by-step reasoning list.
        latest_season: The player's latest season year — used for the
            inactivity check.

    Returns:
        ``(status, current_club_api_id, current_club_name)`` or
        ``(status, current_club_api_id, current_club_name, reasoning)``
        when *with_reasoning* is True.
    """
    if config is None:
        config = _get_active_classification_config()

    # ── Step 1: base status derivation ────────────────────────────────
    if with_reasoning:
        status, loan_id, loan_name, reasoning = derive_player_status_with_reasoning(
            current_club_api_id,
            current_club_name,
            current_level,
            parent_api_id,
            parent_club_name,
        )
    else:
        status, loan_id, loan_name = derive_player_status(
            current_club_api_id,
            current_club_name,
            current_level,
            parent_api_id,
            parent_club_name,
        )
        reasoning: list[dict] = []

    # ── Step 2: transfer-based upgrade ────────────────────────────────
    # The loan→sold/released upgrade is core correctness, not a tunable: a
    # permanent departure (sale or free transfer) must never read as a loan.
    # This step therefore always runs when transfer data is available and is
    # NOT gated by config['use_transfers_for_status']. That flag used to
    # suppress this entire step; with the active config storing it False,
    # sold-detection silently died platform-wide — every permanently
    # transferred player (e.g. Garnacho sold to Chelsea) was stuck at
    # on_loan. The upgrade itself is conservative (only promotes when the
    # latest parent departure is non-loan), so genuine loans stay on_loan.
    if status == "on_loan":
        effective_transfers = transfers
        if effective_transfers is None and player_api_id and api_client:
            try:
                raw = api_client.get_player_transfers(player_api_id)
                effective_transfers = flatten_transfers(raw)
            except Exception as exc:
                logger.warning("Transfer fetch failed for player %s: %s", player_api_id, exc)
                effective_transfers = []

        if effective_transfers:
            upgraded = upgrade_status_from_transfers(
                status,
                effective_transfers,
                parent_api_id,
                current_club_api_id=current_club_api_id,
                parent_club_name=parent_club_name,
            )
            if upgraded != status:
                if with_reasoning:
                    reasoning.append(
                        {
                            "rule": "transfer_upgrade",
                            "result": "match",
                            "check": f'upgrade_status_from_transfers("{status}")',
                            "detail": f"Upgraded from {status} to {upgraded}",
                        }
                    )
                status = upgraded
                # Keep current_club info — loan_id/loan_name are reused as
                # current_club_api_id/current_club_name in the return value.
                # For sold/released/left players, this is their destination/current club.
        elif effective_transfers is not None:
            # We have transfer data (an empty list) and the player is at a
            # different club, but there is NO transfer record at all → they
            # left the academy without a recorded senior transfer. Only treat
            # an explicit empty list this way; None means transfers were not
            # fetched, so keep the conservative on_loan default for callers
            # that classify without transfer data.
            status = "left"
            if with_reasoning:
                reasoning.append(
                    {
                        "rule": "no_transfers_left",
                        "result": "match",
                        "check": "at a different club with no transfer records",
                        "detail": "Left the academy (no recorded departure) → left",
                    }
                )

    # ── Step 2.5: squad cross-reference ────────────────────────────────
    # Skip squad check if transfers confirm a loan — transfer data is more
    # authoritative than squad lists (which aren't updated mid-season for loans).
    has_confirmed_loan = False
    _check_transfers = transfers or []
    if status == "on_loan" and loan_id:
        from src.api_football_client import is_new_loan_transfer as _is_loan

        has_confirmed_loan = any(
            _is_loan((t.get("type") or "").strip().lower()) and t.get("teams", {}).get("in", {}).get("id") == loan_id
            for t in _check_transfers
        )

    if (
        status == "on_loan"
        and not has_confirmed_loan
        and config.get("use_squad_check")
        and squad_members_by_club is not None
        and player_api_id
    ):
        loan_squad = squad_members_by_club.get(loan_id)
        parent_squad = squad_members_by_club.get(parent_api_id)
        in_loan_squad = loan_squad is not None and player_api_id in loan_squad
        in_parent_squad = parent_squad is not None and player_api_id in parent_squad
        if not in_loan_squad:
            if in_parent_squad:
                old_status = status
                status = _base_status(current_level)
                if with_reasoning:
                    reasoning.append(
                        {
                            "rule": "squad_cross_reference",
                            "result": "match",
                            "check": (
                                f"player {player_api_id} not in loan club "
                                f"{loan_id} squad, found in parent {parent_api_id}"
                            ),
                            "detail": (f"Returned to parent club — {old_status} → {status}"),
                        }
                    )
                loan_id = None
                loan_name = None
            else:
                if with_reasoning:
                    reasoning.append(
                        {
                            "rule": "squad_cross_reference",
                            "result": "match",
                            "check": (
                                f"player {player_api_id} not in loan club {loan_id} or parent {parent_api_id} squad"
                            ),
                            "detail": "Absent from both squads — released",
                        }
                    )
                status = "released"
                loan_id = None
                loan_name = None

    # ── Step 3: inactivity-based release ──────────────────────────────
    inactivity_years = config.get("inactivity_release_years")
    if inactivity_years and latest_season is not None and status in ("academy", "on_loan", "left"):
        current_year = datetime.now().year
        if latest_season < current_year - inactivity_years:
            if with_reasoning:
                reasoning.append(
                    {
                        "rule": "inactivity_release",
                        "result": "match",
                        "check": (f"latest_season {latest_season} < {current_year} - {inactivity_years}"),
                        "detail": (f"No data for {current_year - latest_season} seasons — marking as released"),
                    }
                )
            status = "released"
            loan_id = None
            loan_name = None

    # ── Step 4: first-team current-club default ───────────────────────
    # If the classifier resolved status='first_team' but left
    # current_club_api_id/name unset (no transfer event ever wrote them —
    # the player was promoted academy → first team internally), default to
    # the parent academy club. The parent IS the player's current club for
    # first-team status by definition. Keeping these fields NULL is what
    # breaks downstream consumers (radar comparison league, journey
    # "current club" badge, team-loans-out filters) — see PR #104 for the
    # radar-side defensive fix.
    if status == "first_team" and not loan_id:
        loan_id = parent_api_id
        loan_name = parent_club_name
        if with_reasoning:
            reasoning.append(
                {
                    "rule": "first_team_parent_default",
                    "result": "match",
                    "check": "status='first_team' and current_club_api_id is None",
                    "detail": (f"Defaulted current_club to parent academy club {parent_api_id} ({parent_club_name})"),
                }
            )

    if with_reasoning:
        return (status, loan_id, loan_name, reasoning)
    return (status, loan_id, loan_name)


# ─── internal ──────────────────────────────────────────────────────────


def _base_status(current_level: str | None) -> str:
    """Pick 'first_team' or 'academy' based on the player's current level."""
    if current_level == "First Team":
        return "first_team"
    return "academy"


# _DEVELOPMENT_AGE_CUTOFF (U21 — UEFA development squad rules) is imported
# at the top of this module from academy_window, the single source of truth.


def is_academy_product(
    player_api_id: int,
    team_api_id: int,
    *,
    journey: Any = None,
    data_source: str | None = None,
    birth_date: str | None = None,
) -> bool:
    """Single source of truth: should this player appear in a team's development view?

    Used by Teams page, newsletter pipeline, and GOL bot to filter out
    senior signings (owning-club rows) from academy/development views.

    Rules:
    1. academy_club_ids contains team_api_id → True (confirmed academy product)
    2. academy_club_ids exists but doesn't contain team_api_id → False (different academy)
    3. No/empty academy_club_ids + data_source='owning-club' + age ≤ 21 → True
       (bought-to-develop player, e.g. young signing loaned out immediately)
    4. No/empty academy_club_ids + data_source='owning-club' + age > 21 → False
       (senior signing)
    5. No/empty academy_club_ids + other source → True (benefit of doubt — discovered
       through academy pipelines like journey-sync or cohort-seed)
    """
    if journey is None:
        from src.models.journey import PlayerJourney

        journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()

    if journey and journey.academy_club_ids:
        return team_api_id in (journey.academy_club_ids or [])

    # No academy data — decide by data source
    if data_source == "owning-club":
        return _is_development_age(birth_date, journey)

    return True


def _is_development_age(
    birth_date: str | None,
    journey: Any = None,
) -> bool:
    """Return True if the player is young enough to be a development signing."""
    bd = birth_date or (journey.birth_date if journey else None)
    if not bd:
        return False  # no DOB → can't confirm, exclude
    try:
        born = datetime.strptime(bd, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    age = (datetime.now() - born).days / 365.25
    return age <= _DEVELOPMENT_AGE_CUTOFF
