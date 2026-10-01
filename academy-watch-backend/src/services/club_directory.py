"""Clubs near you: the public club directory (dark behind ``CLUB_DIRECTORY_ENABLED``).

Three rules hold this together:

* **Location and offering are moderated.** Venue, postcode, coordinates, level and
  gender programmes live on ``ClubProgramProfileRevision``. The public only ever
  reads them from the *approved* revision, so a club's edit changes nothing until
  an admin approves it through the existing profile-revision review.
* **Directory eligibility is its own predicate** (``directory_eligibility``): an
  approved, not-hidden program with an active, claim-verified manager. A club under
  a real funding league also needs that league approved; a console-local club (the
  reserved "Console (unlisted)" league) does not. It deliberately does not reuse
  ``ClubProgram.is_verified_program``, whose US branch means "payments set up".
* **A visitor's position and search words stay out of URLs.** They arrive in the
  body of ``POST /api/club-directory/search``; ``GET /api/programs`` refuses them,
  so they never reach an access log, browser history or analytics.
* **Clubs, never people.** Cards are built from an explicit allowlist and carry
  only an aggregate squad count — no roster, staff or player data of any age.
"""

from __future__ import annotations

import math
import os
import re
from html import unescape

import sqlalchemy as sa
from sqlalchemy.orm import aliased
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubProgramProfileRevision,
    ClubSquad,
    FundingLeague,
    revision_dict,
)
from src.models.league import db
from src.services.club_console_bridge import (
    CONSOLE_LEAGUE_COUNTRY,
    CONSOLE_LEAGUE_NAME,
    CONSOLE_LEAGUE_REGION,
    is_console_league,
)
from src.utils.sanitize import sanitize_plain_text

LEVELS = ("grassroots", "amateur", "semi_pro", "professional")
GENDER_PROGRAMS = ("men", "women", "boys", "girls")
DIRECTORY_FIELDS = (
    "venue_name",
    "postcode",
    "latitude",
    "longitude",
    "geocode_source",
    "club_level",
    "gender_programs",
)
VENUE_NAME_MAX = 120
POSTCODE_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9 \-]{1,10}[A-Z0-9]")
GEOCODE_SOURCE_CLUB = "club_entered"
# Club-supplied text is refused before any decoding once it is this many times its limit, and
# after this many entity-decoding passes: both bound the work one save can cost.
RAW_TEXT_FACTOR = 4
MAX_ENTITY_PASSES = 3

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 50
MAX_PAGE = 100
SEARCH_MIN = 2
SEARCH_MAX = 80
PLACE_MAX = 120
MAX_RADIUS_KM = 250.0
EARTH_RADIUS_KM = 6371.0088
# Never accepted in a URL: a visitor's position and what they typed (often a home postcode).
BODY_ONLY_PARAMS = ("q", "lat", "lng", "radius_km")
SEARCH_PARAMS = (*BODY_ONLY_PARAMS, "country", "region", "city", "level", "programme", "page", "per_page")


def directory_enabled() -> bool:
    return os.getenv("CLUB_DIRECTORY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Club-side input (moderated profile revision)
# ---------------------------------------------------------------------------


def _clean_text(value, field, limit):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if len(value) > limit * RAW_TEXT_FACTOR:
        raise ValueError(f"{field} must be at most {limit} characters")
    decoded = value
    for _ in range(MAX_ENTITY_PASSES):
        decoded = unescape(decoded)
    if unescape(decoded) != decoded:
        raise ValueError(f"{field} must be plain text")
    cleaned = " ".join(unescape(sanitize_plain_text(decoded)).split())
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return cleaned or None


def _postcode(value):
    cleaned = _clean_text(value, "postcode", 40)
    if cleaned is None:
        return None
    cleaned = cleaned.upper()
    if not POSTCODE_PATTERN.fullmatch(cleaned):
        raise ValueError("postcode must be 3 to 12 letters, digits, spaces or hyphens")
    return cleaned


def _coordinate(value, field, bound):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    # An int is compared as an int: a huge JSON integer must not be converted to a float first.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field} must be a number")
    if abs(value) > bound:
        raise ValueError(f"{field} must be between {-bound} and {bound}")
    return round(float(value), 5)


def _club_level(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value not in LEVELS:
        raise ValueError(f"club_level must be one of {list(LEVELS)}")
    return value


def _gender_programs(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("gender_programs must be a list")
    unknown = sorted(set(value) - set(GENDER_PROGRAMS))
    if unknown:
        raise ValueError(f"gender_programs must only contain {list(GENDER_PROGRAMS)}")
    return [code for code in GENDER_PROGRAMS if code in value]


def submitted_directory_values(data) -> tuple[dict | None, dict[str, str]]:
    """Parse the ``directory`` object of a club profile save.

    Returns ``(None, {})`` when the flag is off or the caller did not send the
    object: the save then leaves these fields exactly as they were.
    """
    if not directory_enabled() or not isinstance(data, dict) or "directory" not in data:
        return None, {}
    raw = data["directory"]
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None, {"directory": "directory must be an object or null"}
    values = {}
    errors = {}
    for field, parser in (
        ("venue_name", lambda value: _clean_text(value, "venue_name", VENUE_NAME_MAX)),
        ("postcode", _postcode),
        ("latitude", lambda value: _coordinate(value, "latitude", 90)),
        ("longitude", lambda value: _coordinate(value, "longitude", 180)),
        ("club_level", _club_level),
        ("gender_programs", _gender_programs),
    ):
        try:
            values[field] = parser(raw.get(field))
        except ValueError as exc:
            errors[field] = str(exc)
    if not errors:
        latitude, longitude = values["latitude"], values["longitude"]
        if (latitude is None) != (longitude is None):
            errors["latitude"] = "latitude and longitude must be supplied together"
        elif latitude == 0 and longitude == 0:
            errors["latitude"] = "latitude and longitude must point at the club's ground"
    if errors:
        return None, errors
    values["geocode_source"] = GEOCODE_SOURCE_CLUB if values["latitude"] is not None else None
    return values, {}


def carry_directory_forward(target, source) -> None:
    """A new draft starts from the approved location so an unrelated edit never erases it."""
    if source is None:
        return
    for field in DIRECTORY_FIELDS:
        setattr(target, field, getattr(source, field))


def apply_directory_values(revision, values) -> None:
    if values is None:
        return
    for field in DIRECTORY_FIELDS:
        setattr(revision, field, values[field])


def settle_directory_on_approval(revision, previous) -> None:
    """While the flag is off the reviewer cannot see these fields, so an approval never publishes them.

    The approved revision keeps the location that was already approved (or none); a
    club's unseen edit is dropped rather than promoted, and must be sent again once
    the directory (and its review card) is on.
    """
    if directory_enabled():
        return
    for field in DIRECTORY_FIELDS:
        setattr(revision, field, getattr(previous, field) if previous is not None else None)


def revision_directory(revision) -> dict:
    """The directory fields of one revision, for the club that owns it and for admin review."""
    return {
        "venue_name": revision.venue_name,
        "postcode": revision.postcode,
        "latitude": revision.latitude,
        "longitude": revision.longitude,
        "club_level": revision.club_level,
        "gender_programs": list(revision.gender_programs or []),
    }


def revision_payload(revision) -> dict | None:
    """``revision_dict`` plus the directory fields while the flag is on (unchanged while off)."""
    if revision is None:
        return None
    payload = revision_dict(revision)
    if directory_enabled():
        payload["directory"] = revision_directory(revision)
    return payload


# ---------------------------------------------------------------------------
# Public reads
# ---------------------------------------------------------------------------


def _venue(revision) -> dict | None:
    if revision is None:
        return None
    venue = {
        "name": revision.venue_name,
        "postcode": revision.postcode,
        "latitude": revision.latitude if revision.longitude is not None else None,
        "longitude": revision.longitude if revision.latitude is not None else None,
    }
    return venue if any(value is not None for value in venue.values()) else None


def squad_counts(program_ids) -> dict[int, int]:
    """Aggregate only: how many squads a club runs, never who is in them."""
    ids = sorted(set(program_ids))
    if not ids:
        return {}
    rows = db.session.execute(
        sa.select(ClubSquad.program_id, sa.func.count(ClubSquad.id))
        .where(ClubSquad.program_id.in_(ids))
        .group_by(ClubSquad.program_id)
    ).all()
    return {program_id: int(count) for program_id, count in rows}


_opportunity_counts = None  # resolved once: B2's function, or False when that lane is not deployed


def open_opportunity_counts(program_ids) -> dict[int, int] | None:
    """B2's public open-opportunity counts when that lane is present; ``None`` otherwise."""
    global _opportunity_counts
    if _opportunity_counts is None:
        try:
            from src.services.opportunities import open_opportunity_counts as counts
        except Exception:
            counts = False
        _opportunity_counts = counts
    if _opportunity_counts is False:
        return None
    try:
        result = _opportunity_counts(list(program_ids))
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    return {
        int(program_id): int(count)
        for program_id, count in result.items()
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0
    }


def is_listed(program) -> bool:
    """Whether this club is in the directory right now (the list's own predicate, for one club)."""
    return (
        db.session.query(ClubProgram.id)
        .join(FundingLeague, FundingLeague.id == ClubProgram.funding_league_id)
        .filter(ClubProgram.id == program.id, directory_eligibility())
        .first()
        is not None
    )


def public_directory_block(program, revision) -> dict | None:
    """Additive block on the public club page: approved location/offering + squad count.

    ``None`` for a club that is not listed (no verified manager any more, say): its
    page may still exist for other reasons, but it serves no directory data.
    """
    if not is_listed(program):
        return None
    return {
        "venue": _venue(revision),
        "club_level": revision.club_level if revision else None,
        "gender_programs": list(revision.gender_programs or []) if revision else [],
        "squad_count": squad_counts([program.id]).get(program.id, 0),
    }


def _iso(value):
    return value.isoformat() if value else None


def club_card(program, revision, league_name, *, squad_count=0, distance_km=None) -> dict:
    """The one public directory projection. Every key is listed here on purpose."""
    return {
        "id": program.id,
        "slug": program.slug,
        "name": program.name,
        "crest_url": program.crest_url,
        "brand": {
            "primary_color": program.brand_primary_color or "#0F3D2E",
            "accent_color": program.brand_accent_color or "#E3B23C",
        },
        "country": program.country,
        "region": program.region,
        "city": program.city,
        "league": {"name": league_name} if league_name else None,
        "verified": True,
        "verified_at": _iso(program.verified_at),
        "venue": _venue(revision),
        "club_level": revision.club_level if revision else None,
        "gender_programs": list(revision.gender_programs or []) if revision else [],
        "age_groups": list(revision.age_groups or []) if revision else [],
        "activities": list(revision.activities or []) if revision else [],
        "squad_count": squad_count,
        "distance_km": distance_km,
    }


def _console_league():
    """SQL twin of ``club_console_bridge.is_console_league``."""
    return sa.and_(
        FundingLeague.name == CONSOLE_LEAGUE_NAME,
        FundingLeague.country == CONSOLE_LEAGUE_COUNTRY,
        FundingLeague.region == CONSOLE_LEAGUE_REGION,
    )


def directory_eligibility():
    """Who may appear: approved, not hidden, active claim-verified manager.

    A club under a real funding league also needs that league approved. A
    console-local club sits on the reserved console league, which is never
    "approved" as a funding league; those are the clubs being onboarded, so the
    league check does not apply to them. The emergency hold is the
    ``emergency_hidden`` column A1's ``club_publication_hold`` helpers derive
    from, read in the same statement. Needs ``FundingLeague`` joined.
    """
    verified_manager = sa.exists(
        sa.select(ClubProgramManager.id)
        .join(
            ClubProgramClaim,
            sa.and_(
                ClubProgramClaim.id == ClubProgramManager.source_claim_id,
                ClubProgramClaim.program_id == ClubProgramManager.program_id,
                ClubProgramClaim.user_account_id == ClubProgramManager.user_account_id,
            ),
        )
        .where(
            ClubProgramManager.program_id == ClubProgram.id,
            ClubProgramManager.status == "active",
            ClubProgramClaim.status == "approved",
        )
        .correlate(ClubProgram)
    )
    return sa.and_(
        ClubProgram.platform_status == "approved",
        ClubProgram.emergency_hidden.is_(False),
        sa.or_(FundingLeague.registry_status == "approved", _console_league()),
        verified_manager,
    )


def _approved_revision_id():
    """SQL twin of ``approved_revision_for``: the pointer when valid, else the latest approved."""
    pointed = aliased(ClubProgramProfileRevision)
    latest = aliased(ClubProgramProfileRevision)
    pointer = (
        sa.select(pointed.id)
        .where(
            pointed.id == ClubProgram.approved_profile_revision_id,
            pointed.program_id == ClubProgram.id,
            pointed.status == "approved",
        )
        .correlate(ClubProgram)
        .scalar_subquery()
    )
    fallback = (
        sa.select(latest.id)
        .where(latest.program_id == ClubProgram.id, latest.status == "approved")
        .order_by(latest.created_at.desc(), latest.id.desc())
        .limit(1)
        .correlate(ClubProgram)
        .scalar_subquery()
    )
    return sa.func.coalesce(pointer, fallback)


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _text_arg(args, name, limit, *, minimum=1):
    raw = args.get(name)
    if raw is None:
        return None
    cleaned = " ".join(str(raw).split())
    if not cleaned:
        return None
    if len(cleaned) < minimum:
        raise ValueError(f"{name} must be at least {minimum} characters")
    if len(cleaned) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")
    return cleaned


def _int_arg(args, name, default, maximum):
    raw = args.get(name)
    if raw is None or raw == "":
        return default
    if not re.fullmatch(r"[0-9]{1,6}", str(raw)):
        raise ValueError(f"{name} must be a positive integer")
    value = int(raw)
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _float_arg(args, name, minimum, maximum):
    raw = args.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def _codes_arg(args, name, allowed):
    raw = args.get(name)
    if raw is None or not str(raw).strip():
        return []
    codes = [code.strip().lower() for code in str(raw).split(",") if code.strip()]
    unknown = sorted(set(codes) - set(allowed))
    if unknown:
        raise ValueError(f"{name} must only contain {list(allowed)}")
    return [code for code in allowed if code in codes]


def search_args_from_body(data) -> dict:
    """The JSON body of ``POST /api/club-directory/search`` as the flat mapping ``parse_search`` reads."""
    if not isinstance(data, dict):
        raise ValueError("the search must be a JSON object")
    args = {}
    for name in SEARCH_PARAMS:
        value = data.get(name)
        if value is None:
            continue
        if isinstance(value, list) and name in ("level", "programme"):
            if any(not isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a list of codes")
            value = ",".join(value)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"{name} must be text or a number")
        if isinstance(value, int) and abs(value) > 10**9:
            raise ValueError(f"{name} is out of range")
        args[name] = value if isinstance(value, str) else repr(value)
    return args


def refuse_url_search_terms(args) -> None:
    """``GET /api/programs`` never takes a position or search words: a URL ends up in logs and history."""
    present = [name for name in BODY_ONLY_PARAMS if args.get(name) is not None]
    if present:
        raise ValueError(
            f"{', '.join(present)} cannot be sent in the URL; send the search in the body of "
            "POST /api/club-directory/search"
        )


def parse_search(args) -> dict:
    """Validate one search (query string or body mapping). Raises ``ValueError`` with a caller-safe message."""
    latitude = _float_arg(args, "lat", -90.0, 90.0)
    longitude = _float_arg(args, "lng", -180.0, 180.0)
    if (latitude is None) != (longitude is None):
        raise ValueError("lat and lng must be supplied together")
    radius_km = _float_arg(args, "radius_km", 1.0, MAX_RADIUS_KM)
    if radius_km is not None and latitude is None:
        raise ValueError("radius_km needs lat and lng")
    return {
        "q": _text_arg(args, "q", SEARCH_MAX, minimum=SEARCH_MIN),
        "country": _text_arg(args, "country", PLACE_MAX),
        "region": _text_arg(args, "region", PLACE_MAX),
        "city": _text_arg(args, "city", PLACE_MAX),
        "levels": _codes_arg(args, "level", LEVELS),
        "programmes": _codes_arg(args, "programme", GENDER_PROGRAMS),
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km,
        "page": _int_arg(args, "page", 1, MAX_PAGE),
        "per_page": _int_arg(args, "per_page", DEFAULT_PER_PAGE, MAX_PER_PAGE),
    }


def _sqlite_trig() -> None:
    """SQLite (tests, local dev) may be built without maths functions; Postgres always has them."""
    if db.session.get_bind().dialect.name != "sqlite":
        return
    raw = db.session.connection().connection
    for name, function in (("sin", math.sin), ("cos", math.cos)):
        # NULL in, NULL out, as the built-ins do (a club with no pin has no coordinates).
        raw.create_function(name, 1, lambda value, f=function: None if value is None else f(value), deterministic=True)


def _haversine_term(revision, latitude, longitude):
    """SQL ``hav(d / R)`` from the visitor to a venue: the exact great-circle haversine term.

    It rises with distance over the whole globe, so it orders nearest-first and
    bounds a radius (``<= sin(r / 2R) ** 2``) without a square root or arcsine,
    and ``sin`` squared of half the longitude gap needs no antimeridian case.
    """
    half = math.pi / 360
    sin_lat = sa.func.sin((revision.latitude - latitude) * half)
    sin_lng = sa.func.sin((revision.longitude - longitude) * half)
    cos_lat = sa.func.cos(revision.latitude * (math.pi / 180))
    return sin_lat * sin_lat + math.cos(math.radians(latitude)) * cos_lat * sin_lng * sin_lng


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    half_lat = (phi2 - phi1) / 2
    half_lng = math.radians(lng2 - lng1) / 2
    a = math.sin(half_lat) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(half_lng) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def search(params) -> dict:
    """Run one bounded directory page. ``params`` comes from ``parse_search``."""
    revision = aliased(ClubProgramProfileRevision)
    query = (
        db.session.query(ClubProgram, revision, FundingLeague)
        .join(FundingLeague, FundingLeague.id == ClubProgram.funding_league_id)
        .outerjoin(revision, revision.id == _approved_revision_id())
        .filter(directory_eligibility())
    )
    if params["q"]:
        pattern = _like_pattern(params["q"])
        query = query.filter(
            sa.or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (
                        ClubProgram.name,
                        ClubProgram.city,
                        ClubProgram.region,
                        revision.venue_name,
                        revision.postcode,
                    )
                )
            )
        )
    for key, column in (("country", ClubProgram.country), ("region", ClubProgram.region), ("city", ClubProgram.city)):
        if params[key]:
            # Both sides are folded by the database, so one collation decides (İstanbul matches İstanbul).
            query = query.filter(sa.func.lower(column) == sa.func.lower(params[key]))
    if params["levels"]:
        query = query.filter(revision.club_level.in_(params["levels"]))
    if params["programmes"]:
        stored = sa.cast(revision.gender_programs, sa.String)
        query = query.filter(sa.or_(*(stored.like(f'%"{code}"%') for code in params["programmes"])))

    latitude, longitude = params["latitude"], params["longitude"]
    order = [sa.func.lower(ClubProgram.name), ClubProgram.id]
    if latitude is not None:
        _sqlite_trig()
        distance = _haversine_term(revision, latitude, longitude)
        if params["radius_km"] is not None:
            query = query.filter(
                revision.latitude.isnot(None),
                revision.longitude.isnot(None),
                distance <= math.sin(params["radius_km"] / (2 * EARTH_RADIUS_KM)) ** 2,
            )
        has_pin = sa.and_(revision.latitude.isnot(None), revision.longitude.isnot(None))
        # Nearest first; name then id settle ties, so pages never repeat or skip a club.
        order = [sa.case((has_pin, 0), else_=1), distance, *order]

    page, per_page = params["page"], params["per_page"]
    total = query.order_by(None).count()
    rows = query.order_by(*order).limit(per_page).offset((page - 1) * per_page).all()
    program_ids = [program.id for program, _revision, _league in rows]
    squads = squad_counts(program_ids)
    opportunities = open_opportunity_counts(program_ids)

    clubs = []
    for program, approved, league in rows:
        distance_km = None
        if latitude is not None and approved is not None and approved.latitude is not None:
            if approved.longitude is not None:
                distance_km = round(haversine_km(latitude, longitude, approved.latitude, approved.longitude), 1)
        card = club_card(
            program,
            approved,
            None if is_console_league(league) else league.name,
            squad_count=squads.get(program.id, 0),
            distance_km=distance_km,
        )
        if opportunities is not None:
            card["open_opportunities"] = opportunities.get(program.id, 0)
        clubs.append(card)
    return {
        "clubs": clubs,
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": page * per_page < total,
        "filters": {"levels": list(LEVELS), "programmes": list(GENDER_PROGRAMS)},
    }
