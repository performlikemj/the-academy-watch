# ruff: noqa: F811
"""Provider hot paths preserve origin/main query counts even with club bridges."""

import time
from datetime import date

import pytest
from sqlalchemy import event
from src.models.follow import PlayerShadow
from src.models.journey import PlayerJourney
from src.models.league import db
from src.models.showcase import LocalPlayer
from test_club_console import _admin_headers, club_app  # noqa: F401


@pytest.fixture
def parity(club_app, monkeypatch):
    from src.routes.journey import journey_bp
    from src.routes.players import players_bp
    from src.routes.share import share_bp
    from src.services import sitemap_service

    monkeypatch.setenv("API_FOOTBALL_FROZEN", "true")
    monkeypatch.setenv("LEGACY_PUBLIC_PAGES", "true")
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    club_app.register_blueprint(journey_bp, url_prefix="/api")
    club_app.register_blueprint(players_bp, url_prefix="/api")
    club_app.register_blueprint(share_bp)
    db.session.add(
        PlayerShadow(
            player_api_id=7001, player_name="Provider parity fixture", birth_date=date(2000, 1, 1), is_active=True
        )
    )
    db.session.add(PlayerJourney(player_api_id=7001, player_name="Provider parity fixture", birth_date="2000-01-01"))
    db.session.commit()
    xml = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://theacademywatch.com/players/7001</loc></url></urlset>'
    monkeypatch.setattr(sitemap_service, "_cache", {"xml": xml, "built_at": time.monotonic()})
    return club_app.test_client()


def measured(client, path):
    db.session.expire_all()
    statements = []

    def count(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", count)
    try:
        response = client.get(path)
    finally:
        event.remove(db.engine, "before_cursor_execute", count)
    return response, statements


@pytest.mark.parametrize("on", [False, True])
@pytest.mark.parametrize(
    "path", ["/api/players/7001/journey", "/api/players/7001/profile", "/api/players/7001/season-stats", "/sitemap.xml"]
)
def test_provider_bridge_status_and_query_counts_match_main(parity, monkeypatch, path, on):
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", str(on).lower())
    before, baseline = measured(parity, path)
    assert before.status_code == 200, before.json
    local = LocalPlayer(
        display_name="Private club roster alias",
        provenance="club",
        origin_program_id=1,
        api_player_id=7001,
        birth_date=date(2000, 1, 1),
        status="approved",
    )
    db.session.add(local)
    db.session.commit()
    after, statements = measured(parity, path)
    assert after.status_code == 200, after.json
    assert before.data == after.data
    assert len(statements) == len(baseline)
    print(f"QUERY_PARITY {path} flag={on}: {len(statements)}")
    # Pinned against an actual origin/main checkout by the C1F1 gate.
    counts = {
        "/api/players/7001/journey": 9,
        "/api/players/7001/profile": 11,
        "/api/players/7001/season-stats": 24,  # PC2 reuses the selected total; C1 adds none
        "/sitemap.xml": 1,
    }
    assert len(statements) == counts[path]


def test_admin_unlinks_legacy_club_bridge_without_transferring_provider_data(parity, monkeypatch):
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "true")
    local = LocalPlayer(
        display_name="Private club alias",
        provenance="club",
        origin_program_id=1,
        api_player_id=7001,
        birth_date=date(2000, 1, 1),
        status="approved",
    )
    db.session.add(local)
    db.session.commit()
    id_ = local.id
    listed = parity.get("/api/admin/local-players", headers=_admin_headers())
    assert id_ in [r["id"] for r in listed.json["players"]]
    response = parity.post(
        f"/api/admin/local-players/{id_}/link-api", headers=_admin_headers(), json={"player_api_id": None}
    )
    assert response.status_code == 200, response.json
    assert local.api_player_id == -id_ and local.status == "pending"
    assert PlayerShadow.query.filter_by(player_api_id=7001).one().is_active
    assert PlayerJourney.query.filter_by(player_api_id=7001).count() == 1
    assert parity.get("/api/players/7001/profile").status_code == 200
    assert parity.get(f"/api/local-players/{id_}").status_code == 404


def test_cached_enabled_sitemap_is_discarded_on_flag_withdrawal(parity, monkeypatch):
    from src.services import sitemap_service

    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    sitemap_service._cache["publication_enabled"] = True
    monkeypatch.setattr(sitemap_service, "_start_background_build", lambda *args: False)
    response, statements = measured(parity, "/sitemap.xml")
    assert response.status_code == 503
    assert b"7001" not in response.data
    assert not statements


@pytest.mark.parametrize("on,ids", [(False, [-23, 7001]), (True, [7001])])
def test_cache_policy_performs_no_sql_while_dark_or_for_provider_ids(parity, monkeypatch, on, ids):
    from src.services.club_player_publication import hidden_club_subject_ids

    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", str(on).lower())
    statements = []

    def count(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", count)
    try:
        assert hidden_club_subject_ids(ids) == set()
    finally:
        event.remove(db.engine, "before_cursor_execute", count)
    assert statements == []


def test_flag_withdrawal_during_sitemap_cache_publish_never_serves_club_urls(parity, monkeypatch):
    from threading import Event

    from src.services import sitemap_service

    published, finish = Event(), Event()

    class PausedCache(dict):
        def update(self, *args, **kwargs):
            super().update(*args, **kwargs)
            published.set()
            assert finish.wait(timeout=5)

    xml = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://theacademywatch.com/local-players/23</loc></url></urlset>'
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "true")
    monkeypatch.setattr(sitemap_service, "_cache", PausedCache(xml=None, built_at=None))
    monkeypatch.setattr(sitemap_service, "build_sitemap_xml", lambda: xml)
    assert sitemap_service._start_background_build(parity.application, sitemap_service._cache_generation)
    try:
        assert published.wait(timeout=5)
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
        response, statements = measured(parity, "/sitemap.xml")
        assert response.status_code == 503
        assert b"local-players/23" not in response.data
        assert not statements
    finally:
        finish.set()
        assert sitemap_service.wait_for_build(timeout=5)
