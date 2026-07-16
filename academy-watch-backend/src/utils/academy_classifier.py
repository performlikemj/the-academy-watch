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
from datetime import UTC, date, datetime
from typing import Any

from src.services.transfer_resolver import (
    ClubRef,
    ResolvedTransferEvent,
    TransferResolution,
    resolve_transfer_state,
)
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


def _club_matches_parent(
    club: ClubRef,
    parent_api_id: int,
    parent_club_name: str | None,
) -> bool:
    """Match a resolved club to an academy parent or one of its affiliates."""
    from src.utils.affiliates import is_affiliate, resolve_senior_id, senior_base_name

    parent_org_id = resolve_senior_id(parent_api_id, parent_club_name)
    parent_base = senior_base_name(parent_club_name).strip().casefold()

    return bool(
        club.api_id == parent_api_id
        or club.organization_api_id == parent_api_id
        or (parent_org_id is not None and club.organization_api_id == parent_org_id)
        or is_affiliate(club.api_id, club.name, parent_api_id, parent_club_name)
        or (parent_base and club.organization_key == f"name:{parent_base}")
    )


def _club_matches_current(
    club: ClubRef,
    club_api_id: int | None,
    club_name: str | None,
) -> bool:
    """Match current statistics to a resolver club across affiliate IDs/names."""
    if club_api_id is not None and club_api_id in {club.api_id, club.organization_api_id}:
        return True

    from src.utils.affiliates import resolve_senior_id, senior_base_name

    current_org_id = resolve_senior_id(club_api_id, club_name)
    if current_org_id is not None and current_org_id == club.organization_api_id:
        return True
    current_base = senior_base_name(club_name).strip().casefold()
    return bool(current_base and club.organization_key == f"name:{current_base}")


def _has_defensible_club_identity(club: ClubRef) -> bool:
    """Return whether a destination has a usable provider ID or real name."""
    if club.api_id is not None or club.organization_api_id is not None:
        return True
    name = (club.name or "").strip().casefold()
    return bool(name and name not in {"n/a", "na", "unknown", "unknown club", "-"})


def _status_at_parent(status: str, current_level: str | None) -> str:
    """Restore an academy-relative base status after a return or buyback."""
    if current_level is not None:
        return _base_status(current_level)
    return status if status in {"academy", "first_team"} else "first_team"


def _current_matches_parent(
    current_club_api_id: int | None,
    current_club_name: str | None,
    parent_api_id: int,
    parent_club_name: str | None,
) -> bool:
    """Match raw journey/current-stat fields to the academy organisation."""
    from src.utils.affiliates import is_affiliate

    return is_affiliate(
        current_club_api_id,
        current_club_name,
        parent_api_id,
        parent_club_name,
    )


def _has_defensible_current_club(
    current_club_api_id: int | None,
    current_club_name: str | None,
) -> bool:
    """Return whether raw current-club fields identify a real club."""
    if current_club_api_id is not None:
        return True
    name = (current_club_name or "").strip().casefold()
    return bool(name and name not in {"n/a", "na", "unknown", "unknown club", "-"})


def _resolution_is_fresh_for_stats(
    resolution: TransferResolution,
    latest_season: int | None,
    *,
    season_start_month: int = 7,
    season_start_day: int = 1,
) -> bool:
    """Whether resolved movement is at least as recent as statistics evidence."""
    if latest_season is None:
        return True
    try:
        stats_floor = date(
            int(latest_season),
            int(season_start_month),
            int(season_start_day),
        )
    except (TypeError, ValueError):
        return True
    latest_event = max(
        (event.transfer_date for event in resolution.events if event.kind != "unknown"),
        default=None,
    )
    return latest_event is not None and latest_event >= stats_floor


def resolved_current_club_is_authoritative(
    resolution: TransferResolution,
    current_club_api_id: int | None,
    current_club_name: str | None,
    *,
    latest_season: int | None = None,
    season_start_month: int = 7,
    season_start_day: int = 1,
) -> bool:
    """Apply one precedence policy to resolver-versus-statistics club state.

    Indeterminate loans never overwrite newer club evidence. A determinate
    movement may fill missing/matching state, replace its own stale permanent
    source (the Hall case), or override statistics no newer than the movement.
    Newer statistics at an unrelated external club win over an older stream.
    """
    if resolution.loan_state == "indeterminate":
        return False

    latest_event = max(
        (event for event in resolution.events if event.kind != "unknown"),
        key=lambda event: event.transfer_date,
        default=None,
    )
    if latest_event is None:
        return False

    current_is_unspecified = not _has_defensible_current_club(
        current_club_api_id,
        current_club_name,
    )
    if current_is_unspecified:
        return True

    destination = resolution.current_club
    if destination is not None and _club_matches_current(
        destination,
        current_club_api_id,
        current_club_name,
    ):
        return True

    if latest_event.kind == "permanent" and _club_matches_current(
        latest_event.out_club,
        current_club_api_id,
        current_club_name,
    ):
        return True

    return _resolution_is_fresh_for_stats(
        resolution,
        latest_season,
        season_start_month=season_start_month,
        season_start_day=season_start_day,
    )


def latest_parent_permanent_departure(
    resolution: TransferResolution | None,
    parent_api_id: int,
    parent_club_name: str | None,
) -> ResolvedTransferEvent | None:
    """Return the latest permanent exit from this academy parent.

    ``TransferResolution.latest_permanent_move`` is player-global and may be a
    later resale by another club. ``TrackedPlayer.sale_fee`` belongs to its
    academy-parent row, so fee consumers must select the parent-relative move.
    """
    if resolution is None:
        return None
    return next(
        (
            event
            for event in reversed(resolution.events)
            if event.kind == "permanent"
            and _club_matches_parent(event.out_club, parent_api_id, parent_club_name)
            and not _club_matches_parent(event.in_club, parent_api_id, parent_club_name)
        ),
        None,
    )


def _resolution_confirms_parent_loan(
    resolution: TransferResolution | None,
    parent_api_id: int,
    parent_club_name: str | None,
    current_club_api_id: int | None,
    current_club_name: str | None,
) -> bool:
    """Return whether the resolver proves a parent-origin loan active now."""
    if resolution is None or resolution.on_loan is not True or resolution.active_loan is None:
        return False

    episode = resolution.active_loan
    current_is_unspecified = current_club_api_id is None and not current_club_name
    return (
        _club_matches_parent(episode.owner, parent_api_id, parent_club_name)
        and not _club_matches_parent(episode.loan_club, parent_api_id, parent_club_name)
        and (
            current_is_unspecified
            or _club_matches_current(
                episode.loan_club,
                current_club_api_id,
                current_club_name,
            )
        )
    )


def upgrade_status_from_transfers(
    status: str,
    transfers: list | None,
    parent_api_id: int,
    current_club_api_id: int | None = None,
    parent_club_name: str | None = None,
    *,
    current_club_name: str | None = None,
    current_level: str | None = None,
    transfer_resolution: TransferResolution | None = None,
    as_of: date | str | None = None,
    latest_season: int | None = None,
    season_start_month: int = 7,
    season_start_day: int = 1,
) -> str:
    """Reconcile academy-relative status against resolved transfer evidence.

    The incoming status may be stale journey evidence (including academy,
    first_team, left, or sold), so definitive transfer state is not gated on
    the caller first deriving ``on_loan``.

    The key inversion: 'on_loan' must be EARNED by a parent loan record; it is
    no longer the fallback. Rules (relative to parent P), in order:

      • an active resolved P→external loan episode covers now         → on_loan
      • a later return or permanent buyback ends at P           → academy/first_team
      • no departure from P at all, but player is elsewhere           → left
      • latest P departure is a loan but current ∉ P loan dests
        (loaned then moved on)                                         → left
      • latest P departure is permanent with a real, non-parent,
        non-national destination                                       → sold
      • latest P departure is permanent with no resolvable destination → released

    Loan episodes and departures are matched against P OR P's own
    reserve/youth/B side (e.g. Valencia and Valencia II both count as a Valencia
    loan). The injected resolution, when supplied, must have been built with
    this same parent as its initial owner.
    """
    # ``None`` means transfer evidence was unavailable (for example a provider
    # failure), while ``[]`` is a successful fetch proving an empty history.
    # Only the former may preserve the caller's conservative status unchanged.
    if transfers is None and transfer_resolution is None:
        return status

    resolution = transfer_resolution or resolve_transfer_state(
        transfers or [],
        as_of=as_of or datetime.now(UTC).date(),
        initial_owner={"id": parent_api_id, "name": parent_club_name},
        season_start_month=season_start_month,
        season_start_day=season_start_day,
    )

    # Genuine current loan FROM the parent — transfer-driven, not entry-type
    # driven (a brand-new loan has no synced fixtures yet so its journey entry
    # is not typed 'loan', but the loan transfer is already present). Historical
    # or indeterminate episodes deliberately do not confirm a current loan.
    active_parent_loan = _resolution_confirms_parent_loan(
        resolution,
        parent_api_id,
        parent_club_name,
        None,
        None,
    )
    if active_parent_loan and resolution.active_loan is not None:
        current_is_unspecified = not _has_defensible_current_club(
            current_club_api_id,
            current_club_name,
        )
        current_is_parent = _current_matches_parent(
            current_club_api_id,
            current_club_name,
            parent_api_id,
            parent_club_name,
        )
        current_is_borrower = _club_matches_current(
            resolution.active_loan.loan_club,
            current_club_api_id,
            current_club_name,
        )
        transfer_is_fresh = latest_season is not None and _resolution_is_fresh_for_stats(
            resolution,
            latest_season,
            season_start_month=season_start_month,
            season_start_day=season_start_day,
        )
        if current_is_unspecified or current_is_parent or current_is_borrower or transfer_is_fresh:
            return "on_loan"

    effective_events = [event for event in resolution.events if event.kind != "unknown"]
    if not effective_events and (resolution.normalized_events or resolution.issues):
        # A non-empty history whose every event is ambiguous or invalid is not
        # equivalent to a successful empty history. The resolver deliberately
        # emitted unknown/issues instead of manufacturing state, so preserve
        # the caller's conservative status until definitive evidence arrives.
        return status

    departures = [
        event
        for event in effective_events
        if event.kind in {"loan_start", "permanent"}
        and _club_matches_parent(event.out_club, parent_api_id, parent_club_name)
        and not _club_matches_parent(event.in_club, parent_api_id, parent_club_name)
    ]

    # A resolved return or buyback into the parent is newer and more precise
    # than a stale external journey club. Re-establish the parent's academy /
    # first-team status before interpreting historical departures.
    if (
        departures
        and effective_events
        and resolution.current_club is not None
        and _club_matches_parent(resolution.current_club, parent_api_id, parent_club_name)
    ):
        current_is_external = _has_defensible_current_club(
            current_club_api_id, current_club_name
        ) and not _current_matches_parent(
            current_club_api_id,
            current_club_name,
            parent_api_id,
            parent_club_name,
        )
        if not current_is_external or _resolution_is_fresh_for_stats(
            resolution,
            latest_season,
            season_start_month=season_start_month,
            season_start_day=season_start_day,
        ):
            return _status_at_parent(status, current_level)
        # Newer external statistics after an older return/buyback are evidence
        # of another departure missing from the transfer feed.
        return "left"

    if not departures:
        # The player is at a different club but there is NO recorded departure
        # from the parent (typical of academy-to-academy youth moves). They
        # left the academy without a recorded senior transfer.
        current_is_external = (
            _has_defensible_current_club(current_club_api_id, current_club_name)
            and not _current_matches_parent(
                current_club_api_id,
                current_club_name,
                parent_api_id,
                parent_club_name,
            )
            and not is_national_team(current_club_name)
        )
        if current_is_external:
            return "left"
        # Successful definitive/empty evidence found no departure from the
        # parent. Do not let a stale tentative ``on_loan`` survive it.
        return _status_at_parent(status, current_level)

    latest_departure = departures[-1]
    if latest_departure.kind == "loan_start":
        # A fresh parent loan returned above. An unclosed loan becomes
        # indeterminate at the next season boundary; a current external club
        # then means the player moved on, while a current parent club is newer
        # evidence that they returned despite the omitted provider event.
        if _current_matches_parent(
            current_club_api_id,
            current_club_name,
            parent_api_id,
            parent_club_name,
        ):
            return _status_at_parent(status, current_level)
        if _has_defensible_current_club(current_club_api_id, current_club_name):
            return "left"
        # The resolver deliberately expires an unclosed loan at the next
        # season boundary. With no newer raw club evidence, the historical
        # departure still proves the player left the parent, but not that the
        # loan remains active now.
        return "left"

    # Permanent (non-loan) departure. The transfer TYPE alone cannot tell a
    # free-agency exit from a permanent move to a new club: API-Football
    # populates teams.in for virtually every departure, and an undisclosed-fee
    # sale is typed "N/A" (not a release). Decide on the departure's recorded
    # destination — a real, non-parent, non-national club ⇒ 'sold'; no recorded
    # destination ⇒ 'released' (a genuine free-agency exit; Step-3 inactivity
    # is the other path to 'released'). Read only the departure's teams.in,
    # NOT the journey's current club: an empty teams.in is the free-agency
    # signal, and folding in a stale last-club would manufacture a false 'sold'.
    dest = latest_departure.in_club
    if (
        _has_defensible_club_identity(dest)
        and not _club_matches_parent(dest, parent_api_id, parent_club_name)
        and not is_national_team(dest.name)
    ):
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
    transfer_resolution: TransferResolution | None = None,
    as_of: date | str | None = None,
    season_start_month: int = 7,
    season_start_day: int = 1,
) -> tuple[str, int | None, str | None] | tuple[str, int | None, str | None, list[dict]]:
    """Single source of truth for player status classification.

    Applies these rules in order:
    1. Base status derivation (academy / first_team / on_loan)
    2. Transfer-based reconciliation (on_loan / sold / released / left /
       returned-to-parent)
       — always runs when transfer data is available (core correctness;
         stale journey status must not override definitive transfer state)
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
        season_start_month: First month of the competition season used to
            compare transfer chronology with latest-season statistics.
        season_start_day: First day of that competition season.
        transfer_resolution: Optional parent-contextualized resolver result to
            reuse. When omitted, this function resolves *transfers* with the
            academy parent as the initial owner.
        as_of: Effective date for transfer resolution. Defaults to today.

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

    # ── Step 2: transfer-based reconciliation ─────────────────────────
    # Transfer reconciliation is core correctness, not a tunable: a permanent
    # departure must override stale same-parent journey data just as a resolved
    # return/buyback must override a stale external club.
    # This step therefore always runs when transfer data is available and is
    # NOT gated by config['use_transfers_for_status']. That flag used to
    # suppress this entire step; with the active config storing it False,
    # sold-detection silently died platform-wide — every permanently
    # transferred player (e.g. Garnacho sold to Chelsea) was stuck at
    # on_loan. The reconciliation itself requires definitive resolver
    # evidence, so unknown/failing evidence stays conservative.
    effective_transfers = transfers
    effective_resolution = transfer_resolution
    if effective_transfers is None and effective_resolution is None and player_api_id and api_client:
        try:
            raw = api_client.get_player_transfers(player_api_id)
            effective_transfers = flatten_transfers(raw)
        except Exception as exc:
            logger.warning("Transfer fetch failed for player %s: %s", player_api_id, exc)
            # Keep fetch failure distinct from a successful empty history.
            # Unknown evidence must not downgrade the conservative status.
            effective_transfers = None

    if effective_transfers is not None or effective_resolution is not None:
        if effective_resolution is None:
            effective_resolution = resolve_transfer_state(
                effective_transfers,
                as_of=as_of or datetime.now(UTC).date(),
                initial_owner={"id": parent_api_id, "name": parent_club_name},
                season_start_month=season_start_month,
                season_start_day=season_start_day,
            )
        previous_status = status
        status = upgrade_status_from_transfers(
            status,
            effective_transfers or [],
            parent_api_id,
            current_club_api_id=current_club_api_id,
            parent_club_name=parent_club_name,
            current_club_name=current_club_name,
            current_level=current_level,
            transfer_resolution=effective_resolution,
            as_of=as_of,
            latest_season=latest_season,
            season_start_month=season_start_month,
            season_start_day=season_start_day,
        )
        if status != previous_status and with_reasoning:
            reasoning.append(
                {
                    "rule": "transfer_reconciliation",
                    "result": "match",
                    "check": f'upgrade_status_from_transfers("{previous_status}")',
                    "detail": f"Reconciled from {previous_status} to {status}",
                }
            )

        effective_events = [event for event in effective_resolution.events if event.kind != "unknown"]
        if status == "on_loan" and _resolution_confirms_parent_loan(
            effective_resolution,
            parent_api_id,
            parent_club_name,
            None,
            None,
        ):
            episode = effective_resolution.active_loan
            if episode is not None and not _club_matches_current(
                episode.loan_club,
                loan_id,
                loan_name,
            ):
                loan_id = episode.loan_club.api_id or episode.loan_club.organization_api_id
                loan_name = episode.loan_club.name
        elif status in {"sold", "left"} and effective_events:
            resolved_current = effective_resolution.current_club
            if (
                resolved_current is not None
                and _has_defensible_club_identity(resolved_current)
                and not _club_matches_parent(resolved_current, parent_api_id, parent_club_name)
                and not is_national_team(resolved_current.name)
            ):
                raw_matches_resolved = _club_matches_current(
                    resolved_current,
                    current_club_api_id,
                    current_club_name,
                )
                if resolved_current_club_is_authoritative(
                    effective_resolution,
                    current_club_api_id,
                    current_club_name,
                    latest_season=latest_season,
                    season_start_month=season_start_month,
                    season_start_day=season_start_day,
                ):
                    loan_id = resolved_current.api_id or resolved_current.organization_api_id
                    loan_name = resolved_current.name or (current_club_name if raw_matches_resolved else None)
        elif status == "released" or (
            status in {"academy", "first_team"}
            and effective_events
            and effective_resolution.current_club is not None
            and _club_matches_parent(
                effective_resolution.current_club,
                parent_api_id,
                parent_club_name,
            )
        ):
            loan_id = None
            loan_name = None
    # ── Step 2.5: squad cross-reference ────────────────────────────────
    # Skip squad check if transfers confirm a loan — transfer data is more
    # authoritative than squad lists (which aren't updated mid-season for loans).
    has_confirmed_loan = False
    if status == "on_loan":
        has_confirmed_loan = _resolution_confirms_parent_loan(
            effective_resolution,
            parent_api_id,
            parent_club_name,
            loan_id,
            loan_name,
        )

    if (
        status == "on_loan"
        and not has_confirmed_loan
        and config.get("use_squad_check")
        and squad_members_by_club is not None
        and player_api_id
    ):
        loan_squad_fetched = loan_id in squad_members_by_club
        parent_squad_fetched = parent_api_id in squad_members_by_club
        loan_squad = squad_members_by_club.get(loan_id)
        parent_squad = squad_members_by_club.get(parent_api_id)
        in_loan_squad = loan_squad_fetched and player_api_id in loan_squad
        in_parent_squad = parent_squad_fetched and player_api_id in parent_squad
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
            elif loan_squad_fetched and parent_squad_fetched:
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
            elif with_reasoning:
                missing_clubs = []
                if not loan_squad_fetched:
                    missing_clubs.append(str(loan_id))
                if not parent_squad_fetched:
                    missing_clubs.append(str(parent_api_id))
                reasoning.append(
                    {
                        "rule": "squad_cross_reference",
                        "result": "unknown",
                        "check": f"squad not fetched for club(s) {', '.join(missing_clubs)}",
                        "detail": "Incomplete squad coverage — preserving current status",
                    }
                )

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
