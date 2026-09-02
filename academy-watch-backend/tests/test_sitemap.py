"""Public sitemap eligibility, enumeration, and cache tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from itertools import count
from threading import Barrier, Event, Lock

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
    assert sitemap_service.wait_for_build(timeout=5)
    sitemap_service.clear_sitemap_cache()
    yield
    assert sitemap_service.wait_for_build(timeout=5)
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


def _xml_with_locations(*locations: str) -> bytes:
    ET.register_namespace("", sitemap_service.SITEMAP_NAMESPACE)
    urlset = ET.Element(f"{{{sitemap_service.SITEMAP_NAMESPACE}}}urlset")
    for location in locations:
        url = ET.SubElement(urlset, f"{{{sitemap_service.SITEMAP_NAMESPACE}}}url")
        ET.SubElement(url, f"{{{sitemap_service.SITEMAP_NAMESPACE}}}loc").text = location
    return ET.tostring(urlset, encoding="utf-8", xml_declaration=True)


def _prime_cache(xml: bytes, *, built_at: float) -> None:
    sitemap_service._cache["xml"] = xml
    sitemap_service._cache["built_at"] = built_at


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


def test_sitemap_candidate_query_is_distinct_sorted_and_respects_env_cap(app, monkeypatch):
    monkeypatch.setenv("SITEMAP_MAX_PLAYER_CANDIDATES", "4")
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
            for player_api_id in range(30_000, 30_010)
        ],
    )
    local = _local("First sorted candidate", birth_date=_years_ago(25))
    db.session.commit()

    candidates = sitemap_service._player_candidate_ids()

    assert len(candidates) == 4
    assert candidates == sorted(set(candidates))
    assert candidates == [local.api_player_id, 30_000, 30_001, 30_002]


def test_sitemap_candidate_default_cap_is_500(app, monkeypatch):
    monkeypatch.delenv("SITEMAP_MAX_PLAYER_CANDIDATES", raising=False)
    team = _team()
    db.session.execute(
        sa.insert(TrackedPlayer),
        [
            {
                "player_api_id": player_api_id,
                "player_name": f"Default-capped candidate {player_api_id}",
                "team_id": team.id,
                "status": "academy",
                "data_source": "api-football",
                "data_depth": "full_stats",
                "is_active": True,
            }
            for player_api_id in range(31_000, 31_501)
        ],
    )
    db.session.commit()

    candidates = sitemap_service._player_candidate_ids()

    assert len(candidates) == 500
    assert candidates[0] == 31_000
    assert candidates[-1] == 31_499


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


def test_sitemap_build_budget_stops_after_partial_players_but_keeps_non_player_urls(app, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test")
    monkeypatch.setenv("SITEMAP_BUILD_BUDGET_SECONDS", "1")
    monkeypatch.setattr(sitemap_service, "_player_candidate_ids", lambda: [51_001, 51_002])
    clock_values = iter((100.0, 100.25, 101.1))
    gate_calls: list[int] = []

    def build_clock():
        return next(clock_values, 101.1)

    def permit_subject(player_api_id: int):
        gate_calls.append(player_api_id)
        return object()

    monkeypatch.setattr(sitemap_service.time, "monotonic", build_clock)
    monkeypatch.setattr(sitemap_service, "resolve_public_adult_subject", permit_subject)
    monkeypatch.setattr(sitemap_service, "_team_slugs", lambda: ["budget-team"])
    monkeypatch.setattr(sitemap_service, "_newsletter_slugs", lambda: ["budget-newsletter"])
    monkeypatch.setattr(sitemap_service, "_program_slugs", lambda: ["budget-program"])

    locations = _locations(sitemap_service.build_sitemap_xml())

    assert gate_calls == [51_001]
    assert locations == [
        "https://public.example.test/",
        "https://public.example.test/players/51001",
        "https://public.example.test/teams/budget-team",
        "https://public.example.test/newsletters/budget-newsletter",
        "https://public.example.test/programs/budget-program",
    ]


def test_sitemap_cache_respects_configured_ttl_serves_stale_and_clears(share_client, monkeypatch):
    monkeypatch.setenv("SITEMAP_TTL_SECONDS", "2")
    clock = [100.0]
    old_xml = _xml_with_locations("https://public.example.test/old")
    new_xml = _xml_with_locations("https://public.example.test/new")
    renders: list[bytes] = []

    def render():
        renders.append(new_xml)
        return new_xml

    monkeypatch.setattr(sitemap_service.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(sitemap_service, "build_sitemap_xml", render)
    _prime_cache(old_xml, built_at=clock[0])

    clock[0] += 1.99
    fresh = share_client.get("/sitemap.xml")
    assert fresh.status_code == 200
    assert fresh.data == old_xml
    assert renders == []

    clock[0] += 0.02
    stale = share_client.get("/sitemap.xml")
    assert stale.status_code == 200
    assert stale.data == old_xml
    assert sitemap_service.wait_for_build(timeout=5)
    assert renders == [new_xml]
    assert sitemap_service._cache["built_at"] == clock[0]

    refreshed = share_client.get("/sitemap.xml")
    assert refreshed.status_code == 200
    assert refreshed.data == new_xml
    assert sitemap_service.wait_for_build(timeout=5)
    assert renders == [new_xml]

    sitemap_service.clear_sitemap_cache()
    assert sitemap_service._cache == {"xml": None, "built_at": None}


def test_concurrent_cold_sitemap_requests_start_exactly_one_build(share_client, monkeypatch):
    app = share_client.application
    callers = 8
    barrier = Barrier(callers)
    build_started = Event()
    release_build = Event()
    calls_lock = Lock()
    build_calls = 0
    built_xml = _xml_with_locations("https://public.example.test/built")

    def slow_build():
        nonlocal build_calls
        with calls_lock:
            build_calls += 1
        build_started.set()
        if not release_build.wait(timeout=5):
            raise TimeoutError("test did not release sitemap build")
        return built_xml

    def fetch_sitemap(_index: int):
        barrier.wait(timeout=5)
        with app.test_client() as client:
            return client.get("/sitemap.xml")

    monkeypatch.setattr(sitemap_service, "build_sitemap_xml", slow_build)
    executor = ThreadPoolExecutor(max_workers=callers)
    try:
        futures = [executor.submit(fetch_sitemap, index) for index in range(callers)]
        assert build_started.wait(timeout=5)
        responses = [future.result(timeout=1) for future in futures]
        assert release_build.is_set() is False
        assert {response.status_code for response in responses} == {503}
        assert build_calls == 1
        assert sitemap_service._build_thread is not None
        assert sitemap_service._build_thread.daemon is True
    finally:
        release_build.set()
        executor.shutdown(wait=True)
        assert sitemap_service.wait_for_build(timeout=5)

    assert sitemap_service._cache["xml"] == built_xml
    assert sitemap_service._building is False


def test_fast_stale_requests_do_not_start_a_second_build_from_the_same_snapshot(share_client, monkeypatch):
    monkeypatch.setenv("SITEMAP_TTL_SECONDS", "1")
    monkeypatch.setattr(sitemap_service.time, "monotonic", lambda: 100.0)
    app = share_client.application
    old_xml = _xml_with_locations("https://public.example.test/old-generation")
    new_xml = _xml_with_locations("https://public.example.test/new-generation")
    _prime_cache(old_xml, built_at=1.0)
    initial_generation = sitemap_service._cache_generation
    real_start = sitemap_service._start_background_build
    callers_ready = Barrier(2)
    first_build_finished = Event()
    order_lock = Lock()
    observed_generations: list[int] = []
    build_calls = 0

    def fast_build():
        nonlocal build_calls
        build_calls += 1
        return new_xml

    def coordinated_start(request_app, observed_generation: int):
        with order_lock:
            call_index = len(observed_generations)
            observed_generations.append(observed_generation)
        callers_ready.wait(timeout=5)
        if call_index == 0:
            started = real_start(request_app, observed_generation)
            assert started is True
            assert sitemap_service.wait_for_build(timeout=5)
            first_build_finished.set()
            return started
        assert first_build_finished.wait(timeout=5)
        return real_start(request_app, observed_generation)

    def fetch_sitemap():
        with app.test_client() as client:
            return client.get("/sitemap.xml")

    monkeypatch.setattr(sitemap_service, "build_sitemap_xml", fast_build)
    monkeypatch.setattr(sitemap_service, "_start_background_build", coordinated_start)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [future.result(timeout=5) for future in [executor.submit(fetch_sitemap) for _ in range(2)]]

    assert sitemap_service.wait_for_build(timeout=5)
    assert [response.status_code for response in responses] == [200, 200]
    assert [response.data for response in responses] == [old_xml, old_xml]
    assert observed_generations == [initial_generation, initial_generation]
    assert build_calls == 1
    assert sitemap_service._cache["xml"] == new_xml
    assert sitemap_service._cache_generation == initial_generation + 1
    assert sitemap_service._building is False


def test_failed_stale_refresh_keeps_previous_cache_and_clears_building(share_client, monkeypatch, caplog):
    monkeypatch.setenv("SITEMAP_TTL_SECONDS", "1")
    monkeypatch.setattr(sitemap_service.time, "monotonic", lambda: 100.0)
    old_xml = _xml_with_locations("https://public.example.test/still-valid")
    _prime_cache(old_xml, built_at=1.0)

    def fail_build():
        raise RuntimeError("deliberate sitemap build failure")

    monkeypatch.setattr(sitemap_service, "build_sitemap_xml", fail_build)

    response = share_client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.data == old_xml
    assert sitemap_service.wait_for_build(timeout=5)
    assert sitemap_service._cache == {"xml": old_xml, "built_at": 1.0}
    assert sitemap_service._building is False
    assert any("sitemap" in record.getMessage().lower() for record in caplog.records)


def test_sitemap_route_returns_xml_before_spa_catch_all(share_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.test")
    real_build = sitemap_service.build_sitemap_xml
    builds: list[bytes] = []

    def counted_build():
        xml = real_build()
        builds.append(xml)
        return xml

    monkeypatch.setattr(sitemap_service, "build_sitemap_xml", counted_build)

    cold = share_client.get("/sitemap.xml")

    assert cold.status_code == 503
    assert cold.mimetype == "text/plain"
    assert cold.headers["Cache-Control"] == "no-store"
    assert cold.headers["Retry-After"] == "60"
    assert cold.get_data(as_text=True) == "Sitemap is being generated"
    assert b"<urlset" not in cold.data
    assert cold.data != b"SPA shell"
    assert sitemap_service.wait_for_build(timeout=5)
    assert len(builds) == 1

    response = share_client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.data != b"SPA shell"
    assert _locations(response.data) == ["https://public.example.test/"]


def test_api_robots_points_at_api_origin_sitemap(share_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test/root/")
    monkeypatch.delenv("PUBLIC_SHARE_BASE_URL", raising=False)

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
