"""Public sitemap eligibility, enumeration, and cache tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from itertools import count

import pytest
import sqlalchemy as sa
from src.models.funding import ClubProgram, FundingLeague
from src.models.league import Newsletter, Team, TeamProfile, db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.routes.share import share_bp
from src.services import sitemap_service

_SYNTHETIC_ID = object()
_TEAM_API_IDS = count(700_000)
_SITEMAP_NS = {"sm": sitemap_service.SITEMAP_NAMESPACE}


@pytest.fixture(autouse=True)
def reset_sitemap_cache():
    sitemap_service.clear_sitemap_cache()
    yield
    sitemap_service.clear_sitemap_cache()


@pytest.fixture
def share_client(app):
    app.register_blueprint(share_bp)

    @app.route("/<path:path>")
    def spa_shell(path):
        del path
        return "SPA shell"

    return app.test_client()


def _years_ago(years: int) -> date:
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, month=2, day=28)


def _team(*, api_id: int | None = None, season: int = 2026, active: bool = True) -> Team:
    api_id = api_id if api_id is not None else next(_TEAM_API_IDS)
    team = Team(
        team_id=api_id,
        name=f"Sitemap Team {api_id}",
        country="England",
        season=season,
        is_active=active,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _tracked(
    player_api_id: int,
    *,
    birth_date: date | None,
    age: int | None = None,
    data_source: str = "api-football",
    active: bool = True,
) -> TrackedPlayer:
    team = _team()
    player = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Sitemap Player {player_api_id}",
        team_id=team.id,
        birth_date=birth_date.isoformat() if birth_date else None,
        age=age,
        status="academy",
        data_source=data_source,
        is_active=active,
    )
    db.session.add(player)
    db.session.flush()
    return player


def _local(
    name: str,
    *,
    birth_date: date | None,
    status: str = "approved",
    api_player_id=_SYNTHETIC_ID,
    merged_into_local_player_id: int | None = None,
) -> LocalPlayer:
    player = LocalPlayer(
        display_name=name,
        normalized_name=LocalPlayer.normalize_name(name),
        birth_date=birth_date,
        birth_year=birth_date.year if birth_date else None,
        status=status,
        merged_into_local_player_id=merged_into_local_player_id,
    )
    db.session.add(player)
    db.session.flush()
    player.api_player_id = -player.id if api_player_id is _SYNTHETIC_ID else api_player_id
    db.session.flush()
    return player


def _suppress(*, player_api_id: int | None = None, local_player_id: int | None = None) -> None:
    suffix = player_api_id if player_api_id is not None else f"local-{local_player_id}"
    db.session.add(
        PlayerSuppression(
            player_api_id=player_api_id,
            local_player_id=local_player_id,
            reason_code="player_request",
            requester_role="player",
            requester_contact=f"sitemap-{suffix}@example.com",
            request_statement="Please remove this profile.",
            status="active",
        )
    )
    db.session.flush()


def _locations(xml: bytes) -> list[str]:
    root = ET.fromstring(xml)
    assert root.tag == f"{{{sitemap_service.SITEMAP_NAMESPACE}}}urlset"
    return [node.text for node in root.findall("sm:url/sm:loc", _SITEMAP_NS) if node.text]


def test_sitemap_includes_only_gate_approved_player_subjects(app, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test/")
    adult = _years_ago(24)
    minor = _years_ago(15)

    _tracked(10_001, birth_date=adult)
    _tracked(10_001, birth_date=adult)  # Same logical player under another parent club.
    _tracked(10_002, birth_date=minor)
    _tracked(10_003, birth_date=None)
    _tracked(10_004, birth_date=adult)
    _tracked(10_004, birth_date=minor)
    _tracked(10_005, birth_date=adult)
    _suppress(player_api_id=10_005)
    _tracked(10_006, birth_date=adult)
    suppressed_bridge = _local("Suppressed bridge", birth_date=adult, api_player_id=10_006)
    _suppress(local_player_id=suppressed_bridge.id)
    _tracked(10_007, birth_date=adult, data_source="owning-club")
    _tracked(10_008, birth_date=adult, active=False)

    adult_local = _local("Adult local", birth_date=adult)
    _local("Minor local", birth_date=minor)
    _local("Unknown-age local", birth_date=None)
    _local("Pending local", birth_date=adult, status="pending")
    merge_target = _local("Pending merge target", birth_date=adult, status="pending")
    _local("Merged local", birth_date=adult, merged_into_local_player_id=merge_target.id)
    mismatched = _local("Mismatched synthetic id", birth_date=adult)
    mismatched.api_player_id = -(mismatched.id + 50_000)
    suppressed_local = _local("Suppressed local", birth_date=adult)
    _suppress(local_player_id=suppressed_local.id)
    db.session.commit()

    locations = _locations(sitemap_service.build_sitemap_xml())

    assert locations.count("https://public.example.test/players/10001") == 1
    assert f"https://public.example.test/local-players/{adult_local.id}" in locations
    assert set(locations) == {
        "https://public.example.test/",
        "https://public.example.test/players/10001",
        f"https://public.example.test/local-players/{adult_local.id}",
    }


def test_sitemap_player_emission_calls_public_adult_gate(app, monkeypatch):
    """Mutation guard: removing the per-emission public-adult gate fails this test."""

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test")
    _tracked(20_001, birth_date=_years_ago(25))
    db.session.commit()
    calls: list[int] = []

    def deny_subject(player_api_id: int):
        calls.append(player_api_id)
        return None

    monkeypatch.setattr(sitemap_service, "resolve_public_adult_subject", deny_subject)

    locations = _locations(sitemap_service.build_sitemap_xml())

    assert calls == [20_001]
    assert "https://public.example.test/players/20001" not in locations


def test_sitemap_candidate_query_is_distinct_sorted_and_capped_across_namespaces(app):
    team = _team()
    db.session.execute(
        sa.insert(TrackedPlayer),
        [
            {
                "player_api_id": player_api_id,
                "player_name": f"Candidate {player_api_id}",
                "team_id": team.id,
                "status": "academy",
                "data_source": "api-football",
                "data_depth": "full_stats",
                "is_active": True,
            }
            for player_api_id in range(30_000, 32_001)
        ],
    )
    local = _local("First sorted candidate", birth_date=_years_ago(25))
    db.session.commit()

    candidates = sitemap_service._player_candidate_ids()

    assert len(candidates) == 2_000
    assert candidates == sorted(set(candidates))
    assert candidates[0] == local.api_player_id
    assert candidates[-1] == 31_998


def test_sitemap_includes_public_teams_newsletters_and_programs(app, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test")
    current_team = _team(api_id=40_001)
    db.session.add(TeamProfile(team_id=current_team.team_id, name="Current Team", slug="current-team"))
    inactive_team = _team(api_id=40_002, active=False)
    db.session.add(TeamProfile(team_id=inactive_team.team_id, name="Historic Team", slug="historic-team"))
    db.session.add(TeamProfile(team_id=40_003, name="Missing Team", slug="missing-team"))
    db.session.add(TeamProfile(team_id=40_004, name="Blank Slug", slug="   "))

    db.session.add_all(
        [
            Newsletter(
                team_id=current_team.id,
                title="Published issue",
                content="Published content",
                public_slug="published-issue",
                published=True,
            ),
            Newsletter(
                team_id=current_team.id,
                title="Draft issue",
                content="Draft content",
                public_slug="draft-issue",
                published=False,
            ),
        ]
    )

    approved_league = _funding_league("Approved league", registry_status="approved")
    proposed_league = _funding_league("Proposed league", registry_status="proposed")
    db.session.flush()
    db.session.add_all(
        [
            _program("public-program", approved_league),
            _program("emergency-hidden", approved_league, emergency_hidden=True),
            _program("pending-program", approved_league, platform_status="pending"),
            _program("unapproved-league", proposed_league),
        ]
    )
    db.session.commit()

    xml = sitemap_service.build_sitemap_xml()
    locations = _locations(xml)

    assert xml.startswith(b"<?xml")
    assert set(locations) == {
        "https://public.example.test/",
        "https://public.example.test/teams/current-team",
        "https://public.example.test/teams/historic-team",
        "https://public.example.test/newsletters/published-issue",
        "https://public.example.test/programs/public-program",
    }


def _funding_league(name: str, *, registry_status: str) -> FundingLeague:
    league = FundingLeague(
        name=name,
        country="United States",
        region=name,
        level="youth_regional",
        age_bands=["U18"],
        gender_program="both",
        season_calendar="fall_spring",
        data_tier="self_reported",
        registry_status=registry_status,
        admission_state="open",
    )
    db.session.add(league)
    return league


def _program(
    slug: str,
    league: FundingLeague,
    *,
    platform_status: str = "approved",
    emergency_hidden: bool = False,
) -> ClubProgram:
    return ClubProgram(
        funding_league_id=league.id,
        name=slug.replace("-", " ").title(),
        legal_name=f"{slug} legal",
        slug=slug,
        country="United States",
        region="Test Region",
        provenance_tier="self_reported",
        platform_status=platform_status,
        emergency_hidden=emergency_hidden,
    )


def test_sitemap_total_url_cap_short_circuits_later_collections(app, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test")
    monkeypatch.setattr(sitemap_service, "_player_candidate_ids", lambda: [])
    monkeypatch.setattr(sitemap_service, "_team_slugs", lambda: (f"team-{index}" for index in range(6_000)))

    def should_not_query():
        raise AssertionError("collections after the URL cap must not be queried")

    monkeypatch.setattr(sitemap_service, "_newsletter_slugs", should_not_query)
    monkeypatch.setattr(sitemap_service, "_program_slugs", should_not_query)

    locations = _locations(sitemap_service.build_sitemap_xml())

    assert len(locations) == 5_000
    assert locations[0] == "https://public.example.test/"
    assert locations[-1] == "https://public.example.test/teams/team-4998"


def test_sitemap_cache_respects_one_hour_ttl_and_clear(app, monkeypatch):
    clock = [100.0]
    renders: list[bytes] = []

    def render():
        payload = f"render-{len(renders) + 1}".encode()
        renders.append(payload)
        return payload

    monkeypatch.setattr(sitemap_service.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(sitemap_service, "_render_sitemap_xml", render)

    first = sitemap_service.build_sitemap_xml()
    clock[0] += sitemap_service.SITEMAP_CACHE_TTL_SECONDS - 1
    assert sitemap_service.build_sitemap_xml() is first
    assert renders == [b"render-1"]

    clock[0] += 1
    second = sitemap_service.build_sitemap_xml()
    assert second == b"render-2"
    assert renders == [b"render-1", b"render-2"]

    sitemap_service.clear_sitemap_cache()
    assert sitemap_service.build_sitemap_xml() == b"render-3"
    assert renders == [b"render-1", b"render-2", b"render-3"]


def test_sitemap_route_returns_xml_before_spa_catch_all(share_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test")

    response = share_client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.data != b"SPA shell"
    assert _locations(response.data) == ["https://public.example.test/"]


def test_api_robots_points_at_api_origin_sitemap(share_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test/root/")

    response = share_client.get("/robots.txt", headers={"X-Forwarded-Host": "forged.invalid"})

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == (
        "User-agent: *\nAllow: /p/\nDisallow: /api/\nSitemap: https://api.example.test/root/sitemap.xml\n"
    )


def test_main_registers_share_routes_ahead_of_spa_catch_all():
    from src.main import app as production_app

    adapter = production_app.url_map.bind("api.example.test")

    assert adapter.match("/sitemap.xml")[0] == "share.sitemap_xml"
    assert adapter.match("/p/abc")[0] == "share.invalid_player_share_path"
    assert adapter.match("/p/")[0] == "share.empty_player_share_path"
