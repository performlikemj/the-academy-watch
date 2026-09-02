"""Signed player-match routes: ownership, privacy, validation, and transactions."""

from datetime import UTC, date, datetime, timedelta

import pytest
from flask import Flask
from src.auth import _user_serializer, issue_user_token
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.funding import ClubProgramManager, ClubRosterMember
from src.models.league import UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.showcase_moderation import ShowcaseModerationEvent, record_moderation_event
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
    db.session.add_all(
        [
            ClubProgramManager(
                program_id=77,
                user_account_id=manager.id,
                source_claim_id=777,
                status="active",
                granted_by="admin@example.com",
            ),
            ClubRosterMember(
                program_id=77,
                player_api_id=6001,
                added_by_user_id=manager.id,
            ),
        ]
    )
    db.session.commit()

    assert client.get("/api/players/6001/matches").status_code == 404
    assert client.get("/api/players/6001/matches", headers=stranger_headers).status_code == 404
    assert client.get("/api/players/6001/matches", headers=agent_headers).status_code == 404
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

    manager_grant = ClubProgramManager.query.filter_by(user_account_id=manager.id).one()
    manager_grant.status = "revoked"
    db.session.commit()
    assert client.get("/api/players/6001/matches", headers=manager_headers).status_code == 404

    _shadow(6002, birth_date=None)
    _entry(6002, guardian)
    assert client.get("/api/players/6002/matches").status_code == 404


def test_negative_minor_is_private_to_guardian_and_matching_manager(client):
    guardian, guardian_headers = _user("local-guardian@example.com")
    manager, manager_headers = _user("local-manager@example.com")
    wrong_manager, wrong_headers = _user("wrong-manager@example.com")
    local = _local_player(birth_date=date(2011, 2, 1))
    synthetic_id = -local.id
    _claim(guardian, local_player_id=local.id, relationship="guardian")
    _entry(synthetic_id, guardian)
    db.session.add_all(
        [
            ClubProgramManager(
                program_id=88,
                user_account_id=manager.id,
                source_claim_id=888,
                status="active",
                granted_by="admin@example.com",
            ),
            ClubRosterMember(
                program_id=88,
                local_player_id=local.id,
                added_by_user_id=manager.id,
            ),
            ClubProgramManager(
                program_id=89,
                user_account_id=wrong_manager.id,
                source_claim_id=889,
                status="active",
                granted_by="admin@example.com",
            ),
        ]
    )
    db.session.commit()

    assert client.get(f"/api/players/{synthetic_id}/matches").status_code == 404
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=guardian_headers).status_code == 200
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=manager_headers).status_code == 200
    assert client.get(f"/api/players/{synthetic_id}/matches", headers=wrong_headers).status_code == 404
    assert client.get("/api/players/-99999/matches").status_code == 404

    unknown_age_local = _local_player(birth_date=None)
    _entry(-unknown_age_local.id, guardian)
    assert client.get(f"/api/players/{-unknown_age_local.id}/matches").status_code == 404


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
        ({"match_date": (datetime.now(UTC).date() + timedelta(days=1)).isoformat()}, "future"),
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
