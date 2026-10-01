"""B2 public list plus B1's approved-pin distance, bounded before pagination."""

import math

import sqlalchemy as sa
from sqlalchemy.orm import aliased
from src.models.funding import ClubProgramProfileRevision
from src.models.opportunities import ClubOpportunity, now
from src.services import club_directory as directory
from src.services import opportunities
from src.services.scout_attendance import adult_event


def search(data):
    allowed = {"lat", "lng", "radius_km", "page", "program_id", "type", "adult_sessions"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("invalid search")
    params = directory.parse_search(directory.search_args_from_body(data))
    page = params["page"]
    pid = data.get("program_id")
    if pid is not None:
        opportunities.integer(pid, "program_id")
    kind = data.get("type")
    if kind is not None and (not isinstance(kind, str) or kind not in {"trial", "open_session", "position"}):
        raise ValueError("invalid type")
    adults = data.get("adult_sessions", False)
    if not isinstance(adults, bool):
        raise ValueError("adult_sessions must be boolean")
    revision = aliased(ClubProgramProfileRevision)
    query = (
        opportunities.public_query(pid)
        .add_entity(revision)
        .outerjoin(revision, revision.id == directory._approved_revision_id())
    )
    if kind:
        query = query.filter(ClubOpportunity.type == kind)
    if adults:
        query = query.filter(
            ClubOpportunity.type.in_(("trial", "open_session")),
            ClubOpportunity.birth_year_max < now().year - 18,
            sa.or_(ClubOpportunity.starts_at.is_(None), ClubOpportunity.starts_at > now()),
        )
    order = [ClubOpportunity.closes_at, ClubOpportunity.id]
    lat, lng = params["latitude"], params["longitude"]
    if lat is not None:
        directory._sqlite_trig()
        distance = directory._haversine_term(revision, lat, lng)
        has_pin = sa.and_(revision.latitude.isnot(None), revision.longitude.isnot(None))
        if params["radius_km"] is not None:
            query = query.filter(
                has_pin, distance <= math.sin(params["radius_km"] / (2 * directory.EARTH_RADIUS_KM)) ** 2
            )
        order = [sa.case((has_pin, 0), else_=1), distance, *order]
    rows = query.order_by(*order).offset((page - 1) * 30).limit(31).all()
    result = []
    for row, pin in rows[:30]:
        item = opportunities.opportunity_dict(row)
        item["distance_km"] = (
            round(directory.haversine_km(lat, lng, pin.latitude, pin.longitude), 1)
            if lat is not None and pin and pin.latitude is not None and pin.longitude is not None
            else None
        )
        item["scout_attendance_available"] = adult_event(row)
        result.append(item)
    return {"opportunities": result, "page": page, "has_more": len(rows) > 30}
