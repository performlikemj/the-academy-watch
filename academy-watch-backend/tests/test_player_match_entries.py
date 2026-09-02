"""Signed player-match routes: ownership, privacy, validation, and transactions."""

from datetime import UTC, date, datetime, timedelta

import pytest
from flask import Flask
from src.auth import _user_serializer, issue_user_token
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubRosterMember,
    FundingLeague,
)
from src.models.league import UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.showcase_moderation import ShowcaseModerationEvent, record_moderation_event
from src.routes import player_matches as player_matches_routes
from src.routes.player_matches import player_matches_bp
from src.services import season_rollup_service


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(flask_app)
    limiter.init_app(flask_app)
    flask_app.register_blueprint(player_matches_bp, url_prefix="/api")
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _user(email: str) -> tuple[UserAccount, dict]:
    stem = email.split("@", 1)[0].replace(".", "-")
    user = UserAccount(
        email=email,
        display_name=stem,
        display_name_lower=stem.lower(),
        created_at=datetime.now(UTC),
    )
    db.session.add(user)
    db.session.commit()
    token = issue_user_token(email)["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _shadow(player_api_id: int, *, birth_date: date | None = date(2000, 1, 1)) -> PlayerShadow:
    row = PlayerShadow(
        player_api_id=player_api_id,
        player_name=f"Player {player_api_id}",
        birth_date=birth_date,
        is_active=True,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _local_player(*, birth_date: date | None, status: str = "approved") -> LocalPlayer:
    row = LocalPlayer(
        display_name=f"Local {LocalPlayer.query.count() + 1}",
        birth_date=birth_date,
        birth_year=birth_date.year if birth_date else None,
        status=status,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _claim(
    user: UserAccount,
    *,
    player_api_id: int | None = None,
    local_player_id: int | None = None,
    relationship: str = "player",
    status: str = "approved",
) -> PlayerProfileClaim:
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        user_account_id=user.id,
        relationship_type=relationship,
        status=status,
    )
    db.session.add(claim)
    db.session.commit()
    return claim


def _manager_program(
    user: UserAccount,
    *,
    program_id: int,
    platform_status: str = "approved",
    emergency_hidden: bool = False,
    claim_status: str = "approved",
    manager_status: str = "active",
) -> tuple[ClubProgram, ClubProgramManager]:
    league = FundingLeague.query.filter_by(name="Match Entry Test League").first()
    if league is None:
        league = FundingLeague(
            name="Match Entry Test League",
            country="Japan",
            region="Kanto",
            level="youth_regional",
            age_bands=["U18"],
            gender_program="both",
            season_calendar="aug_may",
            data_tier="self_reported",
            registry_status="approved",
            admission_state="open",
        )
        db.session.add(league)
        db.session.flush()
    program = ClubProgram(
        id=program_id,
        funding_league_id=league.id,
        name=f"Program {program_id}",
        legal_name=f"Program {program_id} Association",
        slug=f"match-entry-program-{program_id}",
        country="Japan",
        region="Kanto",
        platform_status=platform_status,
        emergency_hidden=emergency_hidden,
    )
    db.session.add(program)
    db.session.flush()
    claim = ClubProgramClaim(
        program_id=program.id,
        user_account_id=user.id,
        relationship_type="club_official",
        status=claim_status,
    )
    db.session.add(claim)
    db.session.flush()
    manager = ClubProgramManager(
        program_id=program.id,
        user_account_id=user.id,
        source_claim_id=claim.id,
        status=manager_status,
        granted_by="match-entry-test",
    )
    db.session.add(manager)
    db.session.flush()
    return program, manager


def _payload(**overrides) -> dict:
    payload = {
        "match_date": "2025-09-01",
        "competition": "County League",
        "opponent": "Rivals FC",
        "home_away": "home",
        "result_for": 2,
        "result_against": 1,
        "minutes": 90,
        "goals": 1,
        "assists": 0,
        "yellows": 0,
        "reds": 0,
        "saves": None,
        "goals_conceded": None,
        "note": "Full match",
    }
    payload.update(overrides)
    return payload


def _entry(
    player_api_id: int,
    reporter: UserAccount,
    *,
    match_date: date = date(2025, 9, 1),
    source: str = "self",
    status: str = "self_reported",
    opponent: str = "Rivals FC",
) -> PlayerMatchEntry:
    row = PlayerMatchEntry(
        player_api_id=player_api_id,
        season=match_date.year if match_date.month >= 8 else match_date.year - 1,
        source=source,
        status=status,
        reported_by_user_id=reporter.id,
        match_date=match_date,
        competition="County League",
        opponent=opponent,
        home_away="home",
        minutes=90,
        goals=1,
        assists=0,
        yellows=0,
        reds=0,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_owner_create_is_idempotent_server_forced_and_public_list_marks_editability(client, monkeypatch):
    owner, headers = _user("owner@example.com")
    _shadow(5001)
    _claim(owner, player_api_id=5001)
    calls = []

    def _refresh(player_api_id, season=None, session=None):
        persisted = PlayerMatchEntry.query.filter_by(player_api_id=player_api_id).one()
        calls.append((player_api_id, season, session is db.session, persisted.goals))
        return {"cells": 1, "totals": 1}

    monkeypatch.setattr(season_rollup_service, "refresh_player", _refresh)
    spoofed = _payload(
        source="club",
        status="club_confirmed",
        reported_by_user_id=999,
        player_api_id=999,
        season=1900,
        club_program_id=123,
    )
    created = client.post("/api/players/5001/matches", json=spoofed, headers=headers)

    assert created.status_code == 201
    first = created.get_json()
    assert first["season_stats"] == {"cells": 1, "totals": 1}
    assert first["match"]["source"] == "self"
    assert first["match"]["status"] == "self_reported"
    assert first["match"]["season"] == 2025
    assert first["match"]["editable"] is True
    assert first["match"]["provenance"] == {
        "source_category": "self",
        "source_label": "Self-reported",
        "primary_source": "user",
    }
    entry_id = first["match"]["id"]
    stored = db.session.get(PlayerMatchEntry, entry_id)
    assert (stored.reported_by_user_id, stored.club_program_id) == (owner.id, None)

    repeated = client.post(
        "/api/players/5001/matches",
        json=_payload(goals=2, note="corrected"),
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["match"]["id"] == entry_id
    assert repeated.get_json()["match"]["goals"] == 2
    assert PlayerMatchEntry.query.filter_by(player_api_id=5001).count() == 1
    assert calls == [(5001, 2025, True, 1), (5001, 2025, True, 2)]

    public = client.get("/api/players/5001/matches")
    assert public.status_code == 200
    assert public.get_json()["matches"][0]["editable"] is False
    owner_view = client.get("/api/players/5001/matches", headers=headers)
    assert owner_view.get_json()["matches"][0]["editable"] is True


def test_concurrent_identical_post_joins_and_updates_the_winner(client, monkeypatch):
    owner, headers = _user("racing-owner@example.com")
    _shadow(5004)
    _claim(owner, player_api_id=5004)
    winner = _entry(5004, owner)
    real_find = player_matches_routes._find_self_entry
    lookups = []
    refreshes = []
    commits = []
    real_commit = db.session.commit

    def _stale_once(*args, **kwargs):
        lookups.append(args)
        if len(lookups) == 1:
            return None
        return real_find(*args, **kwargs)

    def _refresh(player_api_id, season=None, session=None):
        stored = PlayerMatchEntry.query.filter_by(player_api_id=player_api_id).one()
        refreshes.append((player_api_id, season, session is db.session, stored.id, stored.goals))
        return {"cells": 1, "totals": 1}

    def _commit():
        commits.append("commit")
        return real_commit()

    monkeypatch.setattr(player_matches_routes, "_find_self_entry", _stale_once)
    monkeypatch.setattr(season_rollup_service, "refresh_player", _refresh)
    monkeypatch.setattr(db.session, "commit", _commit)

    response = client.post("/api/players/5004/matches", json=_payload(goals=4), headers=headers)

    assert response.status_code == 200
    assert response.get_json()["match"]["id"] == winner.id
    assert response.get_json()["match"]["goals"] == 4
    assert len(lookups) == 2
    assert refreshes == [(5004, 2025, True, winner.id, 4)]
    assert commits == ["commit"]
    assert PlayerMatchEntry.query.filter_by(player_api_id=5004).count() == 1


def test_patch_unique_collision_returns_conflict_without_refresh(client, monkeypatch):
    owner, headers = _user("collision-owner@example.com")
    _shadow(5005)
    _claim(owner, player_api_id=5005)
    first = _entry(5005, owner, opponent="First Opponent")
    second = _entry(5005, owner, opponent="Second Opponent")
    monkeypatch.setattr(season_rollup_service, "refresh_player", lambda *a, **k: pytest.fail("must not refresh"))

    response = client.patch(
        f"/api/players/5005/matches/{second.id}",
        json={"opponent": first.opponent},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "A match entry already exists for that date and opponent"}
    assert db.session.get(PlayerMatchEntry, first.id).opponent == "First Opponent"
    assert db.session.get(PlayerMatchEntry, second.id).opponent == "Second Opponent"


def test_patch_crossing_august_refreshes_both_seasons_then_delete_refreshes_once(client, monkeypatch):
    owner, headers = _user("season-owner@example.com")
    _shadow(5002)
    _claim(owner, player_api_id=5002)
    entry = _entry(5002, owner, match_date=date(2025, 7, 31))
    calls = []
    commits = []
    real_commit = db.session.commit

    def _refresh(player_api_id, season=None, session=None):
        calls.append((player_api_id, season, session is db.session))
        return {"cells": season, "totals": 1}

    def _commit():
        commits.append("commit")
        return real_commit()

    monkeypatch.setattr(season_rollup_service, "refresh_player", _refresh)
    monkeypatch.setattr(db.session, "commit", _commit)

    updated = client.patch(
        f"/api/players/5002/matches/{entry.id}",
        json={"match_date": "2025-08-01", "source": "club", "status": "disputed"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["match"]["season"] == 2025
    assert updated.get_json()["match"]["source"] == "self"
    assert calls == [(5002, 2024, True), (5002, 2025, True)]
    assert commits == ["commit"]

    calls.clear()
    commits.clear()
    deleted = client.delete(f"/api/players/5002/matches/{entry.id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.get_json() == {"deleted": True, "rollup_refreshed": True, "season": 2025}
    assert calls == [(5002, 2025, True)]
    assert commits == ["commit"]
    assert db.session.get(PlayerMatchEntry, entry.id) is None


def test_non_owner_and_co_claimant_cannot_mutate_authors_entry(client, monkeypatch):
    owner, owner_headers = _user("author@example.com")
    stranger, stranger_headers = _user("stranger@example.com")
    coclaimant, coclaimant_headers = _user("co-owner@example.com")
    _shadow(5003)
    _claim(owner, player_api_id=5003)
    _claim(coclaimant, player_api_id=5003, relationship="guardian")
    entry = _entry(5003, owner)
    monkeypatch.setattr(season_rollup_service, "refresh_player", lambda *a, **k: {"cells": 0, "totals": 0})

    no_claim = client.patch(
        f"/api/players/5003/matches/{entry.id}",
        json={"goals": 2},
        headers=stranger_headers,
    )
    assert no_claim.status_code == 403
    co_claim = client.patch(
        f"/api/players/5003/matches/{entry.id}",
        json={"goals": 2},
        headers=coclaimant_headers,
    )
    assert co_claim.status_code == 404
    assert client.delete(f"/api/players/5003/matches/{entry.id}", headers=coclaimant_headers).status_code == 404
    assert db.session.get(PlayerMatchEntry, entry.id).goals == 1

    assert client.post("/api/players/999999/matches", json=_payload(), headers=owner_headers).status_code == 404
    assert client.post("/api/players/5003/matches", json=_payload()).status_code == 401


def test_minor_positive_reads_are_guardian_or_rostered_active_manager_only(client):
    guardian, guardian_headers = _user("guardian@example.com")
    agent, agent_headers = _user("agent@example.com")
    manager, manager_headers = _user("manager@example.com")
    stranger, stranger_headers = _user("minor-stranger@example.com")
    _shadow(6001, birth_date=date(2010, 1, 1))
    _claim(guardian, player_api_id=6001, relationship="guardian")
    _claim(agent, player_api_id=6001, relationship="agent")
    _entry(6001, guardian)
    _program, manager_grant = _manager_program(manager, program_id=77)
    db.session.add(
        ClubRosterMember(
            program_id=77,
            player_api_id=6001,
            added_by_user_id=manager.id,
        )
    )
    db.session.commit()

    assert client.get("/api/players/6001/matches").status_code == 404
    assert client.get("/api/players/6001/matches", headers=stranger_headers).status_code == 404
    agent_view = client.get("/api/players/6001/matches", headers=agent_headers)
    assert agent_view.status_code == 200
    assert agent_view.get_json()["matches"][0]["editable"] is False
    guardian_view = client.get("/api/players/6001/matches", headers=guardian_headers)
    assert guardian_view.status_code == 200
    assert guardian_view.get_json()["matches"][0]["editable"] is True
    stale_legacy_token = _user_serializer().dumps(
        {
            "email": guardian.email,
            "iat": int(guardian.created_at.timestamp()) - 60,
        }
    )
    assert (
        client.get(
            "/api/players/6001/matches",
            headers={"Authorization": f"Bearer {stale_legacy_token}"},
        ).status_code
        == 404
    )
    manager_view = client.get("/api/players/6001/matches", headers=manager_headers)
    assert manager_view.status_code == 200
    assert manager_view.get_json()["matches"][0]["editable"] is False

    manager_grant.status = "revoked"
    db.session.commit()
    assert client.get("/api/players/6001/matches", headers=manager_headers).status_code == 404

    _shadow(6002, birth_date=None)
    _entry(6002, guardian)
    assert client.get("/api/players/6002/matches").status_code == 404


def test_optional_and_required_bearer_resolution_share_account_binding(client):
    guardian, _ = _user("stale-binding-guardian@example.com")
    _shadow(6003, birth_date=date(2010, 1, 1))
    _claim(guardian, player_api_id=6003, relationship="guardian")
    _entry(6003, guardian)
    stale_token = _user_serializer().dumps(
        {
            "email": guardian.email,
            "user_id": guardian.id,
            "account_created_at": "2000-01-01T00:00:00+00:00",
            "iat": int(guardian.created_at.timestamp()),
        }
    )
    stale_headers = {"Authorization": f"Bearer {stale_token}"}

    optional_read = client.get("/api/players/6003/matches", headers=stale_headers)
    required_write = client.post(
        "/api/players/6003/matches",
        json=_payload(),
        headers=stale_headers,
    )

    assert (optional_read.status_code, optional_read.get_json()) == (404, {"error": "Player not found"})
    assert (required_write.status_code, required_write.get_json()) == (401, {"error": "account not found"})


@pytest.mark.parametrize("platform_status", ["pending", "suspended"])
def test_minor_manager_requires_an_approved_program(client, platform_status):
    reporter, _ = _user(f"{platform_status}-reporter@example.com")
    manager, manager_headers = _user(f"{platform_status}-manager@example.com")
    player_id = 6010 if platform_status == "pending" else 6011
    _shadow(player_id, birth_date=date(2010, 1, 1))
    _entry(player_id, reporter)
    program_id = 78 if platform_status == "pending" else 79
    _manager_program(manager, program_id=program_id, platform_status=platform_status)
    db.session.add(
        ClubRosterMember(
            program_id=program_id,
            player_api_id=player_id,
            added_by_user_id=manager.id,
        )
    )
    db.session.commit()

    response = client.get(f"/api/players/{player_id}/matches", headers=manager_headers)
    assert response.status_code == 404
    assert response.get_json() == {"error": "Player not found"}


def test_negative_minor_is_private_to_guardian_and_matching_manager(client):
    guardian, guardian_headers = _user("local-guardian@example.com")
    agent, agent_headers = _user("local-agent@example.com")
    manager, manager_headers = _user("local-manager@example.com")
    wrong_manager, wrong_headers = _user("wrong-manager@example.com")
    local = _local_player(birth_date=date(2011, 2, 1))
    synthetic_id = -local.id
    _claim(guardian, local_player_id=local.id, relationship="guardian")
    _claim(agent, local_player_id=local.id, relationship="agent")
    _entry(synthetic_id, guardian)
    _manager_program(manager, program_id=88)
    _manager_program(wrong_manager, program_id=89)
    db.session.add(
        ClubRosterMember(
            program_id=88,
            local_player_id=local.id,
            added_by_user_id=manager.id,
        )
    )
    db.session.commit()

    assert client.get(f"/api/players/{synthetic_id}/matches").status_code == 404
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=guardian_headers).status_code == 200
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=agent_headers).status_code == 200
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=manager_headers).status_code == 200
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=wrong_headers).status_code == 404
    assert client.get("/api/players/-99999/matches").status_code == 404

    unknown_age_local = _local_player(birth_date=None)
    _entry(-unknown_age_local.id, guardian)
    assert client.get(f"/api/players/{-unknown_age_local.id}/matches").status_code == 404


@pytest.mark.parametrize("subject_kind", ["positive", "negative"])
def test_stranger_minor_writes_are_neutral_like_unknown_subjects(client, subject_kind):
    owner, _ = _user(f"{subject_kind}-minor-owner@example.com")
    _stranger, stranger_headers = _user(f"{subject_kind}-minor-stranger@example.com")
    if subject_kind == "positive":
        player_id = 6020
        unknown_id = 999999
        _shadow(player_id, birth_date=date(2010, 1, 1))
        _claim(owner, player_api_id=player_id, relationship="guardian")
    else:
        local = _local_player(birth_date=date(2010, 1, 1))
        player_id = -local.id
        unknown_id = -99999
        _claim(owner, local_player_id=local.id, relationship="guardian")
    entry = _entry(player_id, owner)

    requests = (
        ("POST", f"/api/players/{player_id}/matches", f"/api/players/{unknown_id}/matches", _payload()),
        (
            "PATCH",
            f"/api/players/{player_id}/matches/{entry.id}",
            f"/api/players/{unknown_id}/matches/{entry.id}",
            {"goals": 2},
        ),
        (
            "DELETE",
            f"/api/players/{player_id}/matches/{entry.id}",
            f"/api/players/{unknown_id}/matches/{entry.id}",
            None,
        ),
    )
    for method, subject_path, unknown_path, payload in requests:
        kwargs = {"headers": stranger_headers}
        if payload is not None:
            kwargs["json"] = payload
        subject_response = client.open(subject_path, method=method, **kwargs)
        unknown_response = client.open(unknown_path, method=method, **kwargs)
        assert (
            (subject_response.status_code, subject_response.get_json())
            == (
                unknown_response.status_code,
                unknown_response.get_json(),
            )
            == (404, {"error": "Player not found"})
        )

    assert db.session.get(PlayerMatchEntry, entry.id) is not None


def test_positive_minor_boundary_is_strictly_under_eighteen(client):
    reporter, _ = _user("age-boundary-reporter@example.com")
    today = datetime.now(UTC).date()

    def _birthday(years_ago):
        try:
            return today.replace(year=today.year - years_ago)
        except ValueError:
            return date(today.year - years_ago, 2, 28)

    _shadow(6030, birth_date=_birthday(17))
    _shadow(6031, birth_date=_birthday(18))
    _entry(6030, reporter)
    _entry(6031, reporter)

    seventeen = client.get("/api/players/6030/matches")
    eighteen = client.get("/api/players/6031/matches")
    assert (seventeen.status_code, seventeen.get_json()) == (404, {"error": "Player not found"})
    assert eighteen.status_code == 200


def test_linked_local_player_cannot_reopen_the_graduated_negative_identity(client, monkeypatch):
    owner, headers = _user("graduated-owner@example.com")
    local = _local_player(birth_date=date(2000, 1, 1))
    _claim(owner, local_player_id=local.id)
    local.api_player_id = 9100
    db.session.commit()
    monkeypatch.setattr(season_rollup_service, "refresh_player", lambda *a, **k: pytest.fail("must not refresh"))

    synthetic_id = -local.id
    assert client.get(f"/api/players/{synthetic_id}/matches").status_code == 404
    assert client.post(f"/api/players/{synthetic_id}/matches", json=_payload(), headers=headers).status_code == 404
    assert PlayerMatchEntry.query.filter_by(player_api_id=synthetic_id).count() == 0


def test_persisted_synthetic_local_identity_remains_writable(client, monkeypatch):
    owner, headers = _user("synthetic-owner@example.com")
    local = _local_player(birth_date=date(2000, 1, 1))
    synthetic_id = -local.id
    local.api_player_id = synthetic_id
    db.session.commit()
    _claim(owner, local_player_id=local.id)
    monkeypatch.setattr(
        season_rollup_service,
        "refresh_player",
        lambda *a, **k: {"cells": 1, "totals": 1},
    )

    created = client.post(f"/api/players/{synthetic_id}/matches", json=_payload(), headers=headers)
    assert created.status_code == 201
    assert created.get_json()["match"]["player_api_id"] == synthetic_id


def test_adult_list_filters_and_paginates(client):
    reporter, _headers = _user("filter-reporter@example.com")
    _shadow(7001)
    _entry(7001, reporter, match_date=date(2025, 9, 1), source="self", status="self_reported")
    _entry(
        7001,
        reporter,
        match_date=date(2025, 9, 2),
        source="club",
        status="club_confirmed",
        opponent="Club Opponent",
    )
    _entry(7001, reporter, match_date=date(2024, 9, 1), opponent="Old Opponent")

    response = client.get("/api/players/7001/matches?season=2025&source=self&page=1&per_page=1")
    assert response.status_code == 200
    assert response.get_json()["total"] == 1
    assert response.get_json()["matches"][0]["source"] == "self"
    assert set(response.get_json()) == {"matches", "total", "page", "per_page"}
    assert client.get("/api/players/7001/matches?source=api").status_code == 400
    assert client.get("/api/players/7001/matches?per_page=101").status_code == 400


@pytest.mark.parametrize(
    ("change", "expected_fragment"),
    [
        ({"minutes": 131}, "minutes"),
        ({"minutes": True}, "minutes"),
        ({"goals": 21}, "goals"),
        ({"saves": -1}, "saves"),
        ({"opponent": "   "}, "opponent"),
        ({"home_away": "somewhere"}, "home_away"),
        ({"match_date": "1969-12-31"}, "1970-01-01"),
        ({"match_date": (datetime.now(UTC).date() + timedelta(days=2)).isoformat()}, "future"),
    ],
)
def test_write_validation_rejects_invalid_values(client, monkeypatch, change, expected_fragment):
    owner, headers = _user(f"validation-{expected_fragment}-{len(str(change))}@example.com")
    player_id = 8000 + owner.id
    _shadow(player_id)
    _claim(owner, player_api_id=player_id)
    monkeypatch.setattr(season_rollup_service, "refresh_player", lambda *a, **k: pytest.fail("must not refresh"))

    response = client.post(f"/api/players/{player_id}/matches", json=_payload(**change), headers=headers)
    assert response.status_code == 400
    assert expected_fragment in response.get_json()["error"]
    assert PlayerMatchEntry.query.filter_by(player_api_id=player_id).count() == 0


def test_match_date_bounds_include_epoch_and_one_day_of_utc_slack(client, monkeypatch):
    owner, headers = _user("date-bound-owner@example.com")
    _shadow(8999)
    _claim(owner, player_api_id=8999)
    monkeypatch.setattr(
        season_rollup_service,
        "refresh_player",
        lambda *a, **k: {"cells": 1, "totals": 1},
    )
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()

    epoch = client.post(
        "/api/players/8999/matches",
        json=_payload(match_date="1970-01-01", opponent="Historic Opponent"),
        headers=headers,
    )
    slack = client.post(
        "/api/players/8999/matches",
        json=_payload(match_date=tomorrow, opponent="Timezone Slack Opponent"),
        headers=headers,
    )

    assert epoch.status_code == 201
    assert epoch.get_json()["match"]["match_date"] == "1970-01-01"
    assert slack.status_code == 201
    assert slack.get_json()["match"]["match_date"] == tomorrow


def test_refresh_failure_rolls_back_match_write(client, monkeypatch):
    owner, headers = _user("rollback-owner@example.com")
    _shadow(9001)
    _claim(owner, player_api_id=9001)

    def _fail_after_flush(player_api_id, season=None, session=None):
        assert (player_api_id, season, session is db.session) == (9001, 2025, True)
        assert PlayerMatchEntry.query.filter_by(player_api_id=9001).count() == 1
        raise RuntimeError("rollup failed")

    monkeypatch.setattr(season_rollup_service, "refresh_player", _fail_after_flush)
    response = client.post("/api/players/9001/matches", json=_payload(), headers=headers)

    assert response.status_code == 500
    assert PlayerMatchEntry.query.filter_by(player_api_id=9001).count() == 0


def test_showcase_moderation_helper_appends_without_committing(app):
    user, _ = _user("moderated@example.com")
    event = record_moderation_event(
        user_account_id=user.id,
        target_kind="profile",
        target_id=44,
        action="rejected",
        actor_email="admin@example.com",
        metadata={"reason": "identity mismatch"},
        session=db.session,
    )
    db.session.flush()

    assert event.to_dict()["metadata"] == {"reason": "identity mismatch"}
    assert ShowcaseModerationEvent.query.count() == 1
    db.session.rollback()
    assert ShowcaseModerationEvent.query.count() == 0
    with pytest.raises(ValueError, match="action must be one of"):
        record_moderation_event(
            user_account_id=user.id,
            target_kind="profile",
            target_id=44,
            action="edited",
        )
