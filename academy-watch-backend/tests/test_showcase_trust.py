"""Trust-tiered moderation for low-risk showcase profile edits."""

from datetime import UTC, date, datetime, timedelta

import pytest
from flask import Flask
from src.auth import _ensure_user_account, issue_user_token
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.league import db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import (
    ClubOfficialClaim,
    LocalPlayer,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
)
from src.models.showcase_moderation import ShowcaseModerationEvent, record_moderation_event
from src.services import season_rollup_service

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.delenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", raising=False)

    from src.routes.showcase import showcase_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(flask_app)
    limiter.init_app(flask_app)
    flask_app.register_blueprint(showcase_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _approved_profile_owner(email: str, *, created_at: datetime | None):
    user = _ensure_user_account(email)
    user.created_at = created_at
    claim = PlayerProfileClaim(
        player_api_id=5001,
        user_account_id=user.id,
        relationship_type="player",
        contract_status="free_agent",
        status="approved",
    )
    profile = PlayerShowcaseProfile(
        player_api_id=5001,
        bio="Original biography",
        status="approved",
        updated_by_user_id=user.id,
    )
    db.session.add_all([claim, profile])
    db.session.commit()
    token = issue_user_token(email)["token"]
    return user, profile, {"Authorization": f"Bearer {token}"}


def _old_account_time(days: int = 60) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _admin_headers():
    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _put_profile(client, headers, **payload):
    return client.put("/api/players/5001/showcase/profile", json=payload, headers=headers)


def _birth_date_years_ago(years: int) -> date:
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def _approved_local_player(email: str, *, birth_date=None, birth_year=None):
    reporter = _ensure_user_account(email)
    player = LocalPlayer(
        display_name=f"Graduate {email}",
        normalized_name=f"graduate {email}",
        birth_date=birth_date,
        birth_year=birth_year,
        status="approved",
        provenance="user",
        created_by_user_id=reporter.id,
    )
    db.session.add(player)
    db.session.flush()
    player.api_player_id = -player.id
    return reporter, player


def _reported_entry(
    *,
    player_api_id: int,
    reporter_id: int,
    source: str = "self",
    status: str | None = None,
    match_date: date = date(2025, 9, 1),
    opponent: str = "Rivals FC",
    **values,
) -> PlayerMatchEntry:
    entry = PlayerMatchEntry(
        player_api_id=player_api_id,
        season=values.pop("season", 2025),
        source=source,
        status=status or ("club_confirmed" if source == "club" else "self_reported"),
        reported_by_user_id=reporter_id,
        match_date=match_date,
        competition=values.pop("competition", "County League"),
        opponent=opponent,
        home_away=values.pop("home_away", "home"),
        minutes=values.pop("minutes", 90),
        goals=values.pop("goals", 0),
        assists=values.pop("assists", 0),
        yellows=values.pop("yellows", 0),
        reds=values.pop("reds", 0),
        **values,
    )
    db.session.add(entry)
    return entry


def test_env_unset_keeps_approved_profile_pending(app, client):
    with app.app_context():
        _, profile, headers = _approved_profile_owner("unset@example.com", created_at=_old_account_time())
        profile_id = profile.id

    response = _put_profile(client, headers, bio="Updated biography")

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "pending"
    with app.app_context():
        assert db.session.get(PlayerShowcaseProfile, profile_id).status == "pending"
        assert ShowcaseModerationEvent.query.count() == 0


def test_eligible_allow_list_edit_stays_approved_and_records_event(app, client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        user, profile, headers = _approved_profile_owner("trusted@example.com", created_at=_old_account_time())
        user_id = user.id
        profile_id = profile.id

    response = _put_profile(
        client,
        headers,
        availability="open_to_moves",
        bio="Trusted biography",
        height_cm=181,
        languages="English, Japanese",
        positions="CM, DM",
        preferred_foot="right",
    )

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "approved"
    with app.app_context():
        event = ShowcaseModerationEvent.query.one()
        assert event.user_account_id == user_id
        assert event.target_kind == "profile"
        assert event.target_id == profile_id
        assert event.action == "approved"
        assert event.actor_email == "trusted@example.com"
        assert event.event_metadata == {
            "auto": True,
            "fields": ["availability", "bio", "height_cm", "languages", "positions", "preferred_foot"],
        }


def test_frontend_shaped_bio_only_edit_ignores_unchanged_contract_attestation(app, client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, _, headers = _approved_profile_owner("full-form@example.com", created_at=_old_account_time())

    response = _put_profile(
        client,
        headers,
        agent_contact_email=None,
        agent_name=None,
        availability=None,
        bio="Updated from the full form",
        contract_status="free_agent",
        contract_until=None,
        height_cm=None,
        languages=None,
        nationality_secondary=None,
        positions="",
        preferred_foot=None,
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["profile"]["status"] == "approved"
    assert response.get_json()["profile"]["contract_attestation_review_status"] == "approved"
    with app.app_context():
        profile = PlayerShowcaseProfile.query.filter_by(player_api_id=5001).one()
        assert profile.pending_contract_status is None
        event = ShowcaseModerationEvent.query.one()
        assert event.event_metadata == {"auto": True, "fields": ["bio"]}


def test_disallowed_field_keeps_edit_pending(app, client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, _, headers = _approved_profile_owner("risky@example.com", created_at=_old_account_time())

    response = _put_profile(
        client,
        headers,
        bio="Updated biography",
        nationality_secondary="Spain",
    )

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "pending"
    with app.app_context():
        assert ShowcaseModerationEvent.query.count() == 0


@pytest.mark.parametrize("action", ["rejected", "revoked", "suppressed"])
def test_prior_adverse_action_keeps_allow_list_edit_pending(app, client, monkeypatch, action):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        user, _, headers = _approved_profile_owner("rejected@example.com", created_at=_old_account_time())
        record_moderation_event(
            user_account_id=user.id,
            target_kind="claim",
            target_id=99,
            action=action,
            actor_email="admin@example.com",
        )
        db.session.commit()

    response = _put_profile(client, headers, bio="Updated biography")

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "pending"
    with app.app_context():
        assert ShowcaseModerationEvent.query.count() == 1


def test_account_too_young_keeps_allow_list_edit_pending(app, client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, _, headers = _approved_profile_owner("young@example.com", created_at=_old_account_time(days=5))

    response = _put_profile(client, headers, bio="Updated biography")

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "pending"


def test_null_created_at_keeps_allow_list_edit_pending(app, client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, _, headers = _approved_profile_owner("null-created@example.com", created_at=None)

    response = _put_profile(client, headers, bio="Updated biography")

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "pending"


@pytest.mark.parametrize("existing_status", [None, "pending"], ids=["never-reviewed", "pending"])
def test_allow_list_edit_never_auto_approves_unapproved_profile(
    app,
    client,
    monkeypatch,
    existing_status,
):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        user = _ensure_user_account(f"{existing_status or 'new'}@example.com")
        user.created_at = _old_account_time()
        claim = PlayerProfileClaim(
            player_api_id=5001,
            user_account_id=user.id,
            relationship_type="player",
            contract_status="free_agent",
            status="approved",
        )
        db.session.add(claim)
        if existing_status is not None:
            db.session.add(
                PlayerShowcaseProfile(
                    player_api_id=5001,
                    bio="Awaiting first review",
                    status=existing_status,
                    updated_by_user_id=user.id,
                )
            )
        db.session.commit()
        headers = {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}

    response = _put_profile(client, headers, bio="Still awaiting first review")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["profile"]["status"] == "pending"
    with app.app_context():
        assert ShowcaseModerationEvent.query.count() == 0


def test_account_age_exactly_at_threshold_is_eligible(app, client, monkeypatch):
    from src.routes import showcase as showcase_routes

    fixed_now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is not None else fixed_now.replace(tzinfo=None)

    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, _, headers = _approved_profile_owner(
            "threshold@example.com",
            created_at=fixed_now - timedelta(days=30),
        )
    monkeypatch.setattr(showcase_routes, "datetime", FrozenDateTime)

    response = _put_profile(client, headers, bio="Boundary biography")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["profile"]["status"] == "approved"


def test_trust_gate_locks_approved_claim_row(app, client, monkeypatch):
    from flask_sqlalchemy.query import Query
    from sqlalchemy.dialects import postgresql

    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, _, headers = _approved_profile_owner("locked@example.com", created_at=_old_account_time())

    locked_claim_sql = []
    original_with_for_update = Query.with_for_update

    def track_with_for_update(query, *args, **kwargs):
        locked = original_with_for_update(query, *args, **kwargs)
        entities = [description.get("entity") for description in query.column_descriptions]
        if PlayerProfileClaim in entities:
            locked_claim_sql.append(str(locked.statement.compile(dialect=postgresql.dialect())))
        return locked

    monkeypatch.setattr(Query, "with_for_update", track_with_for_update)

    response = _put_profile(client, headers, bio="Serialized biography")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["profile"]["status"] == "approved"
    assert any("FOR UPDATE" in sql for sql in locked_claim_sql)


def test_reverting_staged_contract_attestation_clears_stage_and_requires_review(
    app,
    client,
    monkeypatch,
):
    monkeypatch.setenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS", "30")
    with app.app_context():
        _, profile, headers = _approved_profile_owner("revert@example.com", created_at=_old_account_time())
        claim = PlayerProfileClaim.query.filter_by(player_api_id=5001).one()
        profile.pending_contract_claim_id = claim.id
        profile.pending_contract_status = "contracted"
        profile.pending_current_club_name = "Staged United"
        profile.pending_club_program_id = None
        profile.pending_status_contradiction = True
        db.session.commit()
        profile_id = profile.id

    response = _put_profile(
        client,
        headers,
        contract_status="free_agent",
        current_club_name=None,
        club_program_id=None,
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["profile"]["status"] == "pending"
    assert response.get_json()["profile"]["contract_attestation_review_status"] == "approved"
    with app.app_context():
        profile = db.session.get(PlayerShowcaseProfile, profile_id)
        assert profile.pending_contract_claim_id is None
        assert profile.pending_contract_status is None
        assert profile.pending_current_club_name is None
        assert profile.pending_club_program_id is None
        assert profile.pending_status_contradiction is False
        assert ShowcaseModerationEvent.query.count() == 0

    approved = client.post(
        "/api/admin/showcase/profiles/5001/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert approved.status_code == 200, approved.get_json()
    assert approved.get_json()["profile"]["status"] == "approved"
    with app.app_context():
        claim = PlayerProfileClaim.query.filter_by(player_api_id=5001).one()
        assert claim.contract_status == "free_agent"
        assert claim.current_club_name is None
        assert claim.club_program_id is None


def test_profile_rejection_appends_adverse_history(app, client):
    with app.app_context():
        user, profile, _ = _approved_profile_owner("profile-rejected@example.com", created_at=_old_account_time())
        user_id = user.id
        profile_id = profile.id

    response = client.post(
        "/api/admin/showcase/profiles/5001/review",
        json={"action": "reject"},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert response.get_json()["profile"]["status"] == "pending"
    with app.app_context():
        event = ShowcaseModerationEvent.query.one()
        assert (event.user_account_id, event.target_kind, event.target_id) == (user_id, "profile", profile_id)
        assert event.action == "rejected"
        assert event.actor_email == "admin@test.com"


def test_club_claim_rejection_appends_adverse_history(app, client, monkeypatch):
    monkeypatch.setattr(
        "src.services.trust_decision_email_service.send_club_claim_decision_email",
        lambda *_args, **_kwargs: None,
    )
    with app.app_context():
        user = _ensure_user_account("club-rejected@example.com")
        claim = ClubOfficialClaim(
            user_account_id=user.id,
            team_api_id=33,
            role_title="Academy director",
            status="pending",
        )
        db.session.add(claim)
        db.session.commit()
        user_id = user.id
        claim_id = claim.id

    response = client.post(
        f"/api/admin/club-claims/{claim_id}/review",
        json={"action": "reject"},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    with app.app_context():
        event = ShowcaseModerationEvent.query.one()
        assert (event.user_account_id, event.target_kind, event.target_id) == (user_id, "club_claim", claim_id)
        assert event.action == "rejected"
        assert event.actor_email == "admin@test.com"


def test_local_player_and_media_rejections_append_adverse_history(app, client, monkeypatch):
    monkeypatch.setattr("src.routes.showcase.showcase_media_storage.is_configured", lambda: True)
    monkeypatch.setattr("src.routes.showcase.showcase_media_storage.delete_pending", lambda _path: None)
    with app.app_context():
        user = _ensure_user_account("local-rejected@example.com")
        player = LocalPlayer(
            display_name="Rejected Prospect",
            normalized_name="rejected prospect",
            birth_year=2000,
            status="pending",
            provenance="user",
            created_by_user_id=user.id,
        )
        media = PlayerShowcaseMedia(
            player_api_id=5001,
            kind="photo",
            blob_path="pending/players/5001/rejected.jpg",
            status="pending",
            uploaded_by_user_id=user.id,
        )
        db.session.add_all([player, media])
        db.session.commit()
        user_id = user.id
        player_id = player.id
        media_id = media.id

    player_response = client.post(
        f"/api/admin/local-players/{player_id}/review",
        json={"action": "reject"},
        headers=_admin_headers(),
    )
    media_response = client.post(
        f"/api/admin/showcase/media/{media_id}/review",
        json={"action": "reject"},
        headers=_admin_headers(),
    )

    assert player_response.status_code == 200, player_response.get_json()
    assert media_response.status_code == 200, media_response.get_json()
    with app.app_context():
        events = ShowcaseModerationEvent.query.order_by(ShowcaseModerationEvent.id).all()
        assert [(event.user_account_id, event.target_kind, event.target_id, event.action) for event in events] == [
            (user_id, "local_player", player_id, "rejected"),
            (user_id, "media", media_id, "rejected"),
        ]


def test_link_api_rekeys_user_match_entries_and_rebuilds_user_total(app, client):
    with app.app_context():
        reporter = _ensure_user_account("graduated-stats@example.com")
        player = LocalPlayer(
            display_name="Reported Graduate",
            normalized_name="reported graduate",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            status="approved",
            provenance="user",
            created_by_user_id=reporter.id,
        )
        db.session.add(player)
        db.session.flush()
        player_id = player.id
        old_player_api_id = -player_id
        target_player_api_id = 8_801
        player.api_player_id = old_player_api_id
        now = datetime.now(UTC)
        entry = PlayerMatchEntry(
            player_api_id=old_player_api_id,
            season=2025,
            source="self",
            status="self_reported",
            reported_by_user_id=reporter.id,
            match_date=date(2025, 9, 1),
            competition="County League",
            opponent="Rivals FC",
            home_away="home",
            minutes=90,
            goals=2,
            assists=1,
            yellows=0,
            reds=0,
        )
        db.session.add_all(
            [
                entry,
                PlayerSeasonCell(
                    player_api_id=old_player_api_id,
                    season=2025,
                    source="user",
                    club_api_id=0,
                    competition_tier="other",
                    level_group="senior",
                    appearances=1,
                    goals=2,
                    assists=1,
                    minutes=90,
                    yellows=0,
                    reds=0,
                    synced_at=now,
                ),
                PlayerSeasonTotal(
                    player_api_id=old_player_api_id,
                    season=2025,
                    level_group="senior",
                    appearances=1,
                    goals=2,
                    assists=1,
                    minutes=90,
                    yellows=0,
                    reds=0,
                    primary_source="user",
                    computed_at=now,
                ),
            ]
        )
        db.session.commit()
        entry_id = entry.id

    linked = client.post(
        f"/api/admin/local-players/{player_id}/link-api",
        json={"player_api_id": target_player_api_id},
        headers=_admin_headers(),
    )

    assert linked.status_code == 200, linked.get_json()
    graduation = linked.get_json()["graduation"]
    assert graduation["rekeyed"]["player_match_entries"] == 1
    assert graduation["rollup"] == {"cells": 1, "totals": 1}
    with app.app_context():
        assert PlayerMatchEntry.query.filter_by(player_api_id=old_player_api_id).count() == 0
        assert db.session.get(PlayerMatchEntry, entry_id).player_api_id == target_player_api_id
        assert PlayerSeasonCell.query.filter_by(player_api_id=old_player_api_id).count() == 0
        assert PlayerSeasonTotal.query.filter_by(player_api_id=old_player_api_id).count() == 0
        total = PlayerSeasonTotal.query.filter_by(
            player_api_id=target_player_api_id,
            season=2025,
            level_group="senior",
        ).one()
        assert (total.primary_source, total.appearances, total.goals, total.assists, total.minutes) == (
            "user",
            1,
            2,
            1,
            90,
        )

    repeated = client.post(
        f"/api/admin/local-players/{player_id}/link-api",
        json={"player_api_id": target_player_api_id},
        headers=_admin_headers(),
    )
    assert repeated.status_code == 200, repeated.get_json()
    assert repeated.get_json()["graduation"]["rekeyed"].get("player_match_entries", 0) == 0


def test_link_api_minor_bridge_overrides_adult_target_shadow_for_reported_cells(app, client):
    target_player_api_id = 8_802
    with app.app_context():
        birth_date = _birth_date_years_ago(17)
        reporter, player = _approved_local_player(
            "minor-graduate@example.com",
            birth_date=birth_date,
            birth_year=birth_date.year,
        )
        player_id = player.id
        old_player_api_id = -player_id
        db.session.add(
            PlayerShadow(
                player_api_id=target_player_api_id,
                player_name="Misleading adult shadow",
                birth_date=_birth_date_years_ago(30),
                is_active=True,
            )
        )
        _reported_entry(
            player_api_id=old_player_api_id,
            reporter_id=reporter.id,
            source="self",
            match_date=date(2025, 9, 1),
        )
        _reported_entry(
            player_api_id=old_player_api_id,
            reporter_id=reporter.id,
            source="club",
            match_date=date(2025, 9, 2),
        )
        db.session.commit()

    response = client.post(
        f"/api/admin/local-players/{player_id}/link-api",
        json={"player_api_id": target_player_api_id},
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["graduation"]["rollup"] == {"cells": 0, "totals": 0}
    with app.app_context():
        assert db.session.get(LocalPlayer, player_id).api_player_id == target_player_api_id
        assert PlayerMatchEntry.query.filter_by(player_api_id=target_player_api_id).count() == 2
        assert (
            PlayerSeasonCell.query.filter(
                PlayerSeasonCell.player_api_id == target_player_api_id,
                PlayerSeasonCell.source.in_({"club", "user"}),
            ).count()
            == 0
        )
        assert PlayerSeasonTotal.query.filter_by(player_api_id=target_player_api_id).count() == 0


@pytest.mark.parametrize(
    ("birth_year", "expected_cells"),
    [(2000, 1), (2009, 0)],
    ids=["adult-carried", "minor-withheld"],
)
def test_link_api_uses_conservative_year_only_local_age(
    app,
    client,
    birth_year,
    expected_cells,
):
    target_player_api_id = 8_900 + expected_cells
    with app.app_context():
        reporter, player = _approved_local_player(
            f"year-{birth_year}@example.com",
            birth_year=birth_year,
        )
        player_id = player.id
        old_player_api_id = -player_id
        _reported_entry(
            player_api_id=old_player_api_id,
            reporter_id=reporter.id,
            goals=1,
        )
        old_rollup = season_rollup_service.refresh_player(old_player_api_id, session=db.session)
        assert old_rollup == {"cells": expected_cells, "totals": expected_cells}
        db.session.commit()

    response = client.post(
        f"/api/admin/local-players/{player_id}/link-api",
        json={"player_api_id": target_player_api_id},
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["graduation"]["rollup"] == {
        "cells": expected_cells,
        "totals": expected_cells,
    }
    with app.app_context():
        assert (
            PlayerSeasonCell.query.filter_by(
                player_api_id=target_player_api_id,
                source="user",
            ).count()
            == expected_cells
        )
        assert PlayerSeasonTotal.query.filter_by(player_api_id=target_player_api_id).count() == expected_cells
        assert PlayerMatchEntry.query.filter_by(player_api_id=target_player_api_id).count() == 1


def test_link_api_rolls_back_when_refresh_silently_withholds_visible_source(
    app,
    client,
    monkeypatch,
):
    from src.routes import showcase as showcase_routes

    target_player_api_id = 8_803
    with app.app_context():
        reporter, player = _approved_local_player(
            "guarded-graduate@example.com",
            birth_year=2000,
        )
        player_id = player.id
        old_player_api_id = -player_id
        entry = _reported_entry(
            player_api_id=old_player_api_id,
            reporter_id=reporter.id,
        )
        assert season_rollup_service.refresh_player(old_player_api_id, session=db.session) == {
            "cells": 1,
            "totals": 1,
        }
        db.session.commit()
        entry_id = entry.id

    def silently_withhold(player_api_id, season=None, session=None):
        del season
        session.query(PlayerSeasonCell).filter_by(player_api_id=player_api_id).delete(synchronize_session=False)
        session.query(PlayerSeasonTotal).filter_by(player_api_id=player_api_id).delete(synchronize_session=False)
        session.flush()
        return {"cells": 0, "totals": 0}

    monkeypatch.setattr(showcase_routes.season_rollup_service, "refresh_player", silently_withhold)

    response = client.post(
        f"/api/admin/local-players/{player_id}/link-api",
        json={"player_api_id": target_player_api_id},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json() == {"error": "graduated rollup withheld previously visible sources: user"}
    with app.app_context():
        assert db.session.get(LocalPlayer, player_id).api_player_id == old_player_api_id
        assert db.session.get(PlayerMatchEntry, entry_id).player_api_id == old_player_api_id
        assert PlayerSeasonCell.query.filter_by(player_api_id=old_player_api_id, source="user").count() == 1
        assert PlayerSeasonCell.query.filter_by(player_api_id=target_player_api_id).count() == 0


def test_link_api_rekey_collision_prefers_newer_payload_preserves_dispute_and_moves_club(
    app,
    client,
):
    target_player_api_id = 8_804
    older = datetime(2025, 1, 1, tzinfo=UTC)
    newer = datetime(2025, 2, 1, tzinfo=UTC)
    earliest = datetime(2024, 12, 1, tzinfo=UTC)
    with app.app_context():
        reporter, player = _approved_local_player(
            "collision-graduate@example.com",
            birth_date=_birth_date_years_ago(25),
            birth_year=_birth_date_years_ago(25).year,
        )
        player_id = player.id
        old_player_api_id = -player_id
        source = _reported_entry(
            player_api_id=old_player_api_id,
            reporter_id=reporter.id,
            status="self_reported",
            goals=4,
            assists=2,
            minutes=75,
            note="newer source payload",
            created_at=earliest,
            updated_at=newer,
        )
        target = _reported_entry(
            player_api_id=target_player_api_id,
            reporter_id=reporter.id,
            status="disputed",
            goals=1,
            assists=0,
            minutes=20,
            note="older target payload",
            created_at=older,
            updated_at=older,
        )
        club = _reported_entry(
            player_api_id=old_player_api_id,
            reporter_id=reporter.id,
            source="club",
            match_date=date(2025, 9, 2),
            goals=2,
            minutes=60,
        )
        db.session.commit()
        source_id = source.id
        target_id = target.id
        club_id = club.id

    response = client.post(
        f"/api/admin/local-players/{player_id}/link-api",
        json={"player_api_id": target_player_api_id},
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["graduation"]["rekeyed"]["player_match_entries"] == 2
    with app.app_context():
        assert db.session.get(PlayerMatchEntry, source_id) is None
        collision = db.session.get(PlayerMatchEntry, target_id)
        assert (
            collision.player_api_id,
            collision.status,
            collision.goals,
            collision.assists,
            collision.minutes,
            collision.note,
        ) == (
            target_player_api_id,
            "disputed",
            4,
            2,
            75,
            "newer source payload",
        )
        assert collision.created_at == earliest.replace(tzinfo=None)
        assert collision.updated_at == newer.replace(tzinfo=None)
        assert db.session.get(PlayerMatchEntry, club_id).player_api_id == target_player_api_id
        assert PlayerSeasonCell.query.filter_by(player_api_id=target_player_api_id, source="user").count() == 0
        club_cell = PlayerSeasonCell.query.filter_by(player_api_id=target_player_api_id, source="club").one()
        assert (club_cell.goals, club_cell.minutes) == (2, 60)
        assert PlayerSeasonTotal.query.filter_by(player_api_id=target_player_api_id).one().primary_source == "club"
