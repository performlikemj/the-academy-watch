"""Public player share-page, social card, and neutral-denial contracts."""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from PIL import Image
from src.models.follow import PlayerShadow
from src.models.league import League, Team, db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.routes import share as share_routes
from src.routes.share import share_bp
from src.services.player_share_card import (
    SHARE_CARD_FONT_PATH,
    build_share_meta,
    get_share_card_font_path,
    public_api_origin,
    public_share_origin,
)
from src.services.player_suppression import neutral_player_not_found
from src.services.public_player_subject import resolve_public_adult_subject


def _years_ago(years: int) -> date:
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, month=2, day=28)


@pytest.fixture
def share_client(app):
    app.register_blueprint(share_bp)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa_shell(path):
        del path
        return "SPA SHELL"

    return app.test_client()


@pytest.fixture
def parent_team(app) -> Team:
    league = League(league_id=98_001, name="Share League", country="England", season=2026)
    db.session.add(league)
    db.session.flush()
    team = Team(
        team_id=98_002,
        name="Share Academy",
        country="England",
        season=2026,
        league_id=league.id,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _tracked(
    parent_team: Team,
    player_api_id: int,
    *,
    name: str | None = None,
    birth_date: date | None = None,
    age: int | None = None,
    position: str | None = "Midfielder",
    club: str | None = "Share FC",
) -> TrackedPlayer:
    player = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=name or f"Player {player_api_id}",
        team_id=parent_team.id,
        birth_date=birth_date.isoformat() if birth_date else None,
        age=age,
        position=position,
        current_club_name=club,
        data_source="api-football",
        is_active=True,
    )
    db.session.add(player)
    db.session.flush()
    return player


def _local(
    name: str,
    *,
    birth_date: date | None,
    status: str = "approved",
    api_player_id: int | None = None,
    position: str | None = "Defender",
    club: str | None = "Community FC",
) -> LocalPlayer:
    player = LocalPlayer(
        display_name=name,
        normalized_name=LocalPlayer.normalize_name(name),
        birth_date=birth_date,
        birth_year=birth_date.year if birth_date else None,
        position=position,
        club_name=club,
        status=status,
    )
    db.session.add(player)
    db.session.flush()
    player.api_player_id = api_player_id if api_player_id is not None else -player.id
    db.session.flush()
    return player


def _suppress(*, player_api_id=None, local_player_id=None) -> None:
    db.session.add(
        PlayerSuppression(
            player_api_id=player_api_id,
            local_player_id=local_player_id,
            reason_code="player_request",
            requester_role="player",
            requester_contact="share-suppression@example.com",
            request_statement="Remove this profile.",
            status="active",
        )
    )
    db.session.flush()


def _neutral_body(app) -> bytes:
    with app.test_request_context("/"):
        response, status = neutral_player_not_found()
        assert status == 404
        return response.get_data()


def test_share_html_has_escaped_social_metadata_and_configured_api_origin(
    share_client,
    parent_team,
    monkeypatch,
):
    player = _tracked(
        parent_team,
        98_101,
        name="Kai <script>alert(1)</script>",
        birth_date=_years_ago(24),
        position="Central Midfielder",
        club="North & South FC",
    )
    db.session.commit()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://www.share.test/")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test/root///")
    monkeypatch.delenv("PUBLIC_SHARE_BASE_URL", raising=False)

    response = share_client.get(
        f"/p/{player.player_api_id}",
        headers={"Host": "ingress.test", "X-Forwarded-Host": "forged.example"},
    )

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "no-store"
    html = response.get_data(as_text=True)
    escaped_title = "Kai &lt;script&gt;alert(1)&lt;/script&gt; · The Academy Watch"
    assert f"<title>{escaped_title}</title>" in html
    assert f'<meta property="og:title" content="{escaped_title}">' in html
    assert '<meta property="og:description" content="Central Midfielder · North &amp; South FC">' in html
    assert '<meta property="og:type" content="profile">' in html
    assert '<meta property="og:url" content="https://api.share.test/root/p/98101">' in html
    assert '<meta property="og:image" content="https://api.share.test/root/p/98101/card.png">' in html
    assert '<meta property="og:image:width" content="1200">' in html
    assert '<meta property="og:image:height" content="630">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '<meta name="twitter:image" content="https://api.share.test/root/p/98101/card.png">' in html
    assert '<link rel="canonical" href="https://www.share.test/players/98101">' in html
    assert '<meta http-equiv="refresh" content="0; url=https://www.share.test/players/98101">' in html
    assert '<a href="https://www.share.test/players/98101">' in html
    assert "<script" not in html
    assert "forged.example" not in html
    assert "ingress.test" not in html


def test_share_meta_uses_public_share_origin_for_social_urls_and_keeps_canonical(
    app,
    share_client,
    parent_team,
    monkeypatch,
):
    player = _tracked(parent_team, 98_106, birth_date=_years_ago(25))
    db.session.commit()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://www.share.test/")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test/root/")
    monkeypatch.setenv("PUBLIC_SHARE_BASE_URL", "https://theacademywatch.com")

    with app.test_request_context(
        "/",
        base_url="https://ingress.test",
        headers={"X-Forwarded-Host": "forged.example"},
    ):
        subject = resolve_public_adult_subject(player.player_api_id)
        meta = build_share_meta(subject)

    assert meta["share_url"] == "https://theacademywatch.com/p/98106"
    assert meta["image_url"] == "https://theacademywatch.com/p/98106/card.png"
    assert meta["canonical_url"] == "https://www.share.test/players/98106"

    response = share_client.get(
        f"/p/{player.player_api_id}",
        headers={"Host": "ingress.test", "X-Forwarded-Host": "forged.example"},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<meta property="og:url" content="https://theacademywatch.com/p/98106">' in html
    assert '<meta property="og:image" content="https://theacademywatch.com/p/98106/card.png">' in html
    assert '<meta name="twitter:image" content="https://theacademywatch.com/p/98106/card.png">' in html
    assert '<link rel="canonical" href="https://www.share.test/players/98106">' in html
    assert "api.share.test" not in html
    assert "forged.example" not in html
    assert "ingress.test" not in html


def test_share_meta_uses_explicit_club_precedence(app, parent_team, monkeypatch):
    player = _tracked(parent_team, 98_102, birth_date=_years_ago(26), club="Tracked Club")
    local = _local(
        "Graduated Local",
        birth_date=_years_ago(26),
        api_player_id=player.player_api_id,
        club="Local Club",
    )
    shadow = PlayerShadow(
        player_api_id=player.player_api_id,
        player_name="Shadow Name",
        birth_date=_years_ago(26),
        current_club_name="Shadow Club",
        is_active=True,
    )
    db.session.add(shadow)
    db.session.commit()
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test")

    with app.test_request_context("/"):
        subject = resolve_public_adult_subject(player.player_api_id)
        assert build_share_meta(subject)["description"] == "Midfielder · Local Club"
        local.club_name = None
        assert build_share_meta(subject)["description"] == "Midfielder · Tracked Club"
        player.current_club_name = None
        assert build_share_meta(subject)["description"] == "Midfielder · Shadow Club"


def test_share_card_is_deterministic_1200_by_630_and_uses_repo_font(
    share_client,
    parent_team,
    monkeypatch,
):
    player = _tracked(parent_team, 98_103, birth_date=_years_ago(22), position="Forward", club="Goals FC")
    db.session.commit()
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test")

    first = share_client.get(f"/p/{player.player_api_id}/card.png")
    second = share_client.get(f"/p/{player.player_api_id}/card.png")

    assert first.status_code == second.status_code == 200
    assert first.mimetype == second.mimetype == "image/png"
    assert first.headers["Cache-Control"] == second.headers["Cache-Control"] == "no-store"
    assert first.data == second.data
    with Image.open(io.BytesIO(first.data)) as image:
        assert image.format == "PNG"
        assert image.size == (1200, 630)

    expected_fonts = Path(__file__).resolve().parents[1] / "fonts"
    assert get_share_card_font_path() == SHARE_CARD_FONT_PATH
    assert SHARE_CARD_FONT_PATH is not None
    assert Path(SHARE_CARD_FONT_PATH).is_file()
    assert Path(SHARE_CARD_FONT_PATH).resolve().parent == expected_fonts.resolve()


def test_negative_local_share_uses_local_canonical_path(share_client, monkeypatch):
    local = _local("Ada Local", birth_date=_years_ago(21), position="Goalkeeper", club="Local United")
    db.session.commit()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://theacademywatch.test/")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.theacademywatch.test/")
    monkeypatch.delenv("PUBLIC_SHARE_BASE_URL", raising=False)

    response = share_client.get(f"/p/{local.api_player_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"https://theacademywatch.test/local-players/{local.id}" in html
    assert f"https://api.theacademywatch.test/p/{local.api_player_id}/card.png" in html
    assert "Goalkeeper · Local United" in html


def test_api_origin_falls_back_to_request_root_only_when_unset(
    share_client,
    parent_team,
    monkeypatch,
):
    player = _tracked(parent_team, 98_104, birth_date=_years_ago(25))
    db.session.commit()
    monkeypatch.delenv("PUBLIC_SHARE_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_API_BASE_URL", raising=False)

    response = share_client.get(
        f"/p/{player.player_api_id}",
        base_url="http://dev-api.test:5188",
        headers={"X-Forwarded-Host": "forged.example"},
    )

    html = response.get_data(as_text=True)
    assert "http://dev-api.test:5188/p/98104/card.png" in html
    assert "forged.example" not in html


@pytest.mark.parametrize(
    "configured_origin",
    ("", " \t "),
    ids=("empty", "whitespace-only"),
)
def test_api_origin_falls_back_to_request_root_when_configured_origin_is_blank(
    share_client,
    parent_team,
    monkeypatch,
    configured_origin,
):
    player = _tracked(parent_team, 98_105, birth_date=_years_ago(25))
    db.session.commit()
    monkeypatch.delenv("PUBLIC_SHARE_BASE_URL", raising=False)
    monkeypatch.setenv("PUBLIC_API_BASE_URL", configured_origin)

    response = share_client.get(
        f"/p/{player.player_api_id}",
        base_url="http://dev-api.test:5189",
        headers={"X-Forwarded-Host": "forged.example"},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "http://dev-api.test:5189/p/98105/card.png" in html
    assert "forged.example" not in html


def test_api_origin_preserves_nonblank_config_verbatim_except_trailing_slashes(app, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "  https://api.share.test/root///")

    with app.test_request_context("/", base_url="http://dev-api.test:5190"):
        assert public_api_origin() == "  https://api.share.test/root"


@pytest.mark.parametrize(
    ("configured_share_origin", "expected"),
    (
        ("", "https://api.share.test/root"),
        (" \t ", "https://api.share.test/root"),
        ("  https://theacademywatch.com/// \t", "https://theacademywatch.com"),
    ),
    ids=("empty", "whitespace-only", "trimmed"),
)
def test_public_share_origin_strips_config_and_treats_blank_as_unset(
    app,
    monkeypatch,
    configured_share_origin,
    expected,
):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test/root/")
    monkeypatch.setenv("PUBLIC_SHARE_BASE_URL", configured_share_origin)

    with app.test_request_context(
        "/",
        base_url="https://ingress.test",
        headers={"X-Forwarded-Host": "forged.example"},
    ):
        assert public_share_origin() == expected


def test_all_unsafe_and_malformed_share_paths_are_byte_identical_neutral_json(
    app,
    share_client,
    parent_team,
):
    minor = _tracked(parent_team, 98_201, birth_date=_years_ago(15))
    unknown_age = _tracked(parent_team, 98_202, birth_date=None, age=None)
    suppressed = _tracked(parent_team, 98_203, birth_date=_years_ago(25))
    _suppress(player_api_id=suppressed.player_api_id)
    pending = _local("Pending Local", birth_date=_years_ago(25), status="pending")
    suppressed_local = _local("Suppressed Local", birth_date=_years_ago(25))
    _suppress(local_player_id=suppressed_local.id)
    bridged = _tracked(parent_team, 98_204, birth_date=_years_ago(25))
    bridged_local = _local(
        "Suppressed Bridge",
        birth_date=_years_ago(25),
        api_player_id=bridged.player_api_id,
    )
    _suppress(local_player_id=bridged_local.id)
    db.session.commit()

    expected = _neutral_body(app)
    numeric_ids = (
        minor.player_api_id,
        unknown_age.player_api_id,
        suppressed.player_api_id,
        pending.api_player_id,
        suppressed_local.api_player_id,
        bridged.player_api_id,
        0,
        2_147_483_648,
        999_999_999,
    )
    for player_api_id in numeric_ids:
        html_response = share_client.get(f"/p/{player_api_id}")
        card_response = share_client.get(f"/p/{player_api_id}/card.png")
        for response in (html_response, card_response):
            assert response.status_code == 404
            assert response.mimetype == "application/json"
            assert response.headers["Cache-Control"] == "no-store"
            assert response.data == expected

    for malformed_path in ("/p", "/p/", "/p/abc", "/p/abc/card.png", "/p/card.png"):
        response = share_client.get(malformed_path)
        assert response.status_code == 404
        assert response.mimetype == "application/json"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.data == expected
        assert response.data != b"SPA SHELL"


def test_share_routes_call_the_public_adult_gate_before_rendering(
    share_client,
    parent_team,
    monkeypatch,
):
    player = _tracked(parent_team, 98_301, birth_date=_years_ago(25))
    db.session.commit()
    seen = []

    def reject(player_api_id):
        seen.append(player_api_id)
        return None

    monkeypatch.setattr(share_routes, "resolve_public_adult_subject", reject)

    page = share_client.get(f"/p/{player.player_api_id}")
    card = share_client.get(f"/p/{player.player_api_id}/card.png")

    assert page.status_code == card.status_code == 404
    assert page.data == card.data
    assert seen == [player.player_api_id, player.player_api_id]


def test_api_robots_txt_uses_configured_api_origin(share_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test/base///")
    monkeypatch.delenv("PUBLIC_SHARE_BASE_URL", raising=False)

    response = share_client.get(
        "/robots.txt",
        headers={"Host": "ingress.test", "X-Forwarded-Host": "forged.example"},
    )

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == (
        "User-agent: *\nAllow: /p/\nDisallow: /api/\nSitemap: https://api.share.test/base/sitemap.xml\n"
    )


def test_api_robots_txt_uses_configured_public_share_origin(share_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.share.test/base/")
    monkeypatch.setenv("PUBLIC_SHARE_BASE_URL", "https://theacademywatch.com")

    response = share_client.get(
        "/robots.txt",
        headers={"Host": "ingress.test", "X-Forwarded-Host": "forged.example"},
    )

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == (
        "User-agent: *\nAllow: /p/\nDisallow: /api/\nSitemap: https://theacademywatch.com/sitemap.xml\n"
    )
