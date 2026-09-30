"""Dark rollout, transactions, durable retries, adult rules and reversible holds."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.funding import ClubProgram, ClubRosterMember, FundingLeague
from src.models.league import Team, TeamProfile, UserAccount, db
from src.models.p2_foundation import AdminActionEvent, NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalClub, LocalPlayer, PlayerClubAffiliation, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.routes.admin_programs import admin_programs_bp
from src.routes.funding import funding_bp
from src.services.account import _SchemaView, build_account_export, delete_account
from src.services.admin_audit import record_admin_event
from src.services.club_publication_hold import (
    club_publication_held,
    subject_publication_held,
    subject_publication_hold_filter,
)
from src.services.email_service import EmailResult
from src.services.foundation_account import erase_foundation_rows
from src.services.notification_outbox import MAX_ATTEMPTS, dispatch_due, enqueue, register_template
from src.services.public_adult import filter_public_adults, is_public_adult
from src.services.public_player_subject import resolve_public_adult_subject


@pytest.fixture
def foundation_app(monkeypatch):
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "1")
    monkeypatch.setenv("ADMIN_API_KEY", "fixture-admin")
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="fixture",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(admin_programs_bp, url_prefix="/api")
    app.register_blueprint(funding_bp, url_prefix="/api")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _user(email="fixture@example.com"):
    user = UserAccount(email=email, display_name="Fixture", display_name_lower=email.split("@")[0])
    db.session.add(user)
    db.session.commit()
    return user


def _intent(user, **kw):
    values = dict(
        dedupe_key="event:1:recipient:1",
        recipient_user_id=user.id,
        event_type="fixture_changed",
        entity_type="fixture",
        entity_id=1,
        template="fixture",
        payload={"version": 1},
    )
    values.update(kw)
    return enqueue(**values)


def _template(eligible=lambda row, user: True):
    register_template(
        "fixture",
        eligible=eligible,
        render=lambda row, user: {
            "subject": "Fixture update",
            "html": "<p>Sign in to see your update.</p>",
            "text": "Sign in to see your update.",
        },
    )


def _program():
    league = FundingLeague(
        name="Fixture",
        country="JP",
        region="Fixture",
        level="recreational",
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(league)
    db.session.flush()
    program = ClubProgram(
        funding_league_id=league.id,
        name="Fixture",
        legal_name="Fixture",
        slug="fixture",
        country="JP",
        region="Fixture",
        platform_status="approved",
    )
    db.session.add(program)
    db.session.commit()
    return program


def _local(birth_date=None, birth_year=None, **kw):
    local = LocalPlayer(
        display_name="Fixture",
        normalized_name="fixture",
        birth_date=birth_date,
        birth_year=birth_year,
        status="approved",
        **kw,
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = -local.id
    db.session.commit()
    return local


def test_enqueue_dedupe_conflict_and_caller_rollback(foundation_app):
    user = _user()
    # An actual outer transaction write pins SQLite savepoint semantics too.
    user.display_name = "Changed"
    row = _intent(user)
    assert _intent(user).id == row.id
    assert NotificationOutbox.query.count() == 1
    with pytest.raises(ValueError, match="dedupe"):
        _intent(user, payload={"version": 2})
    db.session.rollback()
    assert NotificationOutbox.query.count() == 0
    assert user.display_name == "Fixture"


def test_retry_backoff_then_success_and_no_resend(foundation_app):
    user = _user()
    row = _intent(user)
    now = datetime.now(UTC) + timedelta(seconds=1)
    db.session.commit()
    _template()
    send = Mock(
        side_effect=[
            EmailResult(success=False, provider="fixture", error="PII must not persist"),
            EmailResult(success=True, provider="fixture", message_id="fixture-id"),
        ]
    )
    assert dispatch_due(now=now, send=send)["retry"] == 1
    assert row.attempts == 1 and row.last_error == "delivery_failed"
    assert dispatch_due(now=now + timedelta(seconds=59), send=send)["sent"] == 0
    assert dispatch_due(now=now + timedelta(seconds=60), send=send)["sent"] == 1
    assert row.attempts == 2 and row.provider_message_id == "fixture-id"
    assert dispatch_due(now=now + timedelta(days=1), send=send)["sent"] == 0
    assert send.call_count == 2


def test_retry_exhaustion_and_exception_redaction(foundation_app):
    user = _user()
    row = _intent(user)
    db.session.commit()
    _template()
    send = Mock(side_effect=RuntimeError("private@example.com sensitive provider body"))
    now = datetime.now(UTC) + timedelta(seconds=1)
    for attempt in range(MAX_ATTEMPTS):
        summary = dispatch_due(now=now + timedelta(hours=attempt), send=send)
    assert summary["failed"] == 1 and row.status == "failed" and row.attempts == MAX_ATTEMPTS
    assert row.last_error == "delivery_failed"


@pytest.mark.parametrize("invalid", ["ineligible", "tombstone", "unknown", "erased"])
def test_dispatch_revalidates_and_never_sends_ineligible(foundation_app, invalid):
    user = _user()
    row = _intent(user, template="unknown" if invalid == "unknown" else "fixture")
    db.session.commit()
    _template(eligible=lambda row, user: invalid != "ineligible")
    if invalid == "tombstone":
        user.is_tombstone = True
    elif invalid == "erased":
        erase_foundation_rows(user.id, user.email, _SchemaView())
        db.session.delete(user)
    db.session.commit()
    send = Mock()
    dispatch_due(now=datetime.now(UTC) + timedelta(seconds=1), send=send)
    send.assert_not_called()
    if invalid != "erased":
        assert row.status == "cancelled"


def test_recipient_and_entity_rechecked_on_retry(foundation_app):
    user = _user()
    row = _intent(user)
    db.session.commit()
    _template()
    now = datetime.now(UTC) + timedelta(seconds=1)
    send = Mock(return_value=EmailResult(success=False, provider="fixture"))
    dispatch_due(now=now, send=send)
    _template(eligible=lambda row, user: False)
    dispatch_due(now=now + timedelta(minutes=2), send=send)
    assert row.status == "cancelled" and send.call_count == 1


def test_dark_flag_prevents_enqueue_dispatch_and_endpoints(foundation_app, monkeypatch):
    user = _user()
    _intent(user)
    db.session.commit()
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    assert club_publication_held(program.id) and subject_publication_held(local.api_player_id)
    assert not is_public_adult(local.api_player_id)
    assert _intent(user) is None
    send = Mock()
    assert dispatch_due(send=send)["disabled"] is True
    send.assert_not_called()
    assert (
        foundation_app.test_client().post("/api/admin/programs/1/emergency-hide", headers=_admin()).status_code == 404
    )


def test_payload_rejects_personal_data(foundation_app):
    user = _user()
    for payload in ({"name": "alice"}, {"state": "child@example.com"}, {"message": {"nested": "private"}}):
        with pytest.raises(ValueError):
            _intent(user, payload=payload)


def _admin(role="admin", key="fixture-admin"):
    return {
        "Authorization": f"Bearer {issue_user_token('admin-fixture@example.com', role=role)['token']}",
        "X-API-Key": key,
    }


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "fixture-admin"}, "user", "bad_key"])
def test_emergency_negative_auth(foundation_app, headers):
    headers = _admin(role="user") if headers == "user" else _admin(key="wrong") if headers == "bad_key" else headers
    program = _program()
    response = foundation_app.test_client().post(
        f"/api/admin/programs/{program.id}/emergency-hide", headers=headers, json={"reason": "Fixture"}
    )
    assert response.status_code in {401, 403}
    assert not program.emergency_hidden and AdminActionEvent.query.count() == 0


def test_hide_lift_public_read_audit_and_independent_suppression(foundation_app):
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    suppression = PlayerSuppression(
        local_player_id=local.id,
        reason_code="admin_other",
        requester_role="other",
        requester_contact="fixture@example.com",
        request_statement="Fixture request",
        status="active",
    )
    db.session.add(suppression)
    db.session.commit()
    suppression_before = (suppression.id, suppression.status, suppression.updated_at)
    client = foundation_app.test_client()
    assert client.get("/api/programs/fixture").status_code == 200
    assert (
        client.post(
            f"/api/admin/programs/{program.id}/emergency-hide", headers=_admin(), json={"reason": ""}
        ).status_code
        == 400
    )
    assert not program.emergency_hidden and AdminActionEvent.query.count() == 0
    for action, hidden, public_status in (("hide", True, 404), ("lift", False, 200)):
        result = client.post(
            f"/api/admin/programs/{program.id}/emergency-{action}",
            headers=_admin(),
            json={"reason": "Fixture incident"},
        )
        assert result.status_code == 200 and result.json["emergency_hidden"] == hidden
        assert client.get("/api/programs/fixture").status_code == public_status
        assert club_publication_held(program.id) == hidden
        assert subject_publication_held(local.api_player_id) == hidden
        assert not is_public_adult(local.api_player_id)  # independent takedown survives lift
    assert AdminActionEvent.query.count() == 2
    assert (suppression.id, suppression.status, suppression.updated_at) == suppression_before
    first = AdminActionEvent.query.order_by(AdminActionEvent.id).first()
    assert first.event_metadata == {"before_hidden": False, "after_hidden": True}


def test_audit_transaction_append_only_and_account_erasure(foundation_app):
    user = _user()
    other = _user("other-fixture@example.com")
    _intent(user)
    record_admin_event(user, "fixture", "fixture", 1, "Fixture reason", {"before_hidden": False})
    record_admin_event(other, "fixture", "fixture", 2, "Unrelated reason")
    db.session.commit()
    export = build_account_export(user)
    assert len(export["notifications"]) == len(export["admin_actions"]) == 1
    assert "reason" not in export["admin_actions"][0]
    event = AdminActionEvent.query.filter_by(actor_email=user.email).one()
    event.reason = "Mutation"
    with pytest.raises(ValueError, match="append-only"):
        db.session.flush()
    db.session.rollback()
    deleted = delete_account(user)
    db.session.commit()
    assert deleted is not None and NotificationOutbox.query.count() == 0
    db.session.expire_all()
    event = db.session.get(AdminActionEvent, event.id)
    assert event.actor_email == "Account deleted" and event.reason == "[redacted]" and event.event_metadata == {}
    assert AdminActionEvent.query.filter_by(actor_email=other.email).one().reason == "Unrelated reason"


@pytest.mark.parametrize("years_ago,expected", [(None, False), (17, False), (18, False), (19, True), (30, True)])
def test_year_only_and_missing_dob(foundation_app, years_ago, expected):
    today = datetime.now(UTC).date()
    local = _local(birth_year=today.year - years_ago if years_ago is not None else None)
    assert is_public_adult(local.api_player_id) == expected


def test_adult_query_filter_and_stale_subject_revalidation(foundation_app):
    adult = _local(birth_date=date(1990, 1, 1))
    minor = _local(birth_date=date(datetime.now(UTC).year - 10, 1, 1))
    subject = resolve_public_adult_subject(adult.api_player_id)
    assert subject and is_public_adult(subject)
    rows = filter_public_adults(LocalPlayer.query, LocalPlayer.api_player_id).all()
    assert [row.id for row in rows] == [adult.id]
    with pytest.raises(ValueError, match="bound"):
        filter_public_adults(LocalPlayer.query, LocalPlayer.api_player_id, max_candidates=1)
    program = _program()
    program.emergency_hidden = True
    db.session.add(ClubRosterMember(program_id=program.id, local_player_id=adult.id, added_by_user_id=_user().id))
    db.session.commit()
    assert not is_public_adult(subject)
    held = LocalPlayer.query.filter(subject_publication_hold_filter(LocalPlayer.api_player_id)).all()
    assert [row.id for row in held] == [adult.id]
    assert not subject_publication_held(minor.api_player_id)
    program.emergency_hidden = False
    db.session.commit()
    assert is_public_adult(subject)


def test_positive_unknown_dob_and_alias_suppression(foundation_app):
    shadow = PlayerShadow(player_api_id=12345, player_name="Fixture", is_active=True)
    db.session.add(shadow)
    db.session.commit()
    assert not is_public_adult(12345)
    shadow.birth_date = date(1990, 1, 1)
    db.session.commit()
    assert is_public_adult(12345)
    local = _local(birth_date=date(1990, 1, 1))
    local.api_player_id = 12345
    db.session.add(
        PlayerSuppression(
            local_player_id=local.id,
            reason_code="admin_other",
            requester_role="other",
            requester_contact="fixture@example.com",
            request_statement="Fixture request",
            status="active",
        )
    )
    db.session.commit()
    assert not is_public_adult(12345)


def test_stored_api_age_without_dob_stays_private(foundation_app):
    team = Team(team_id=9876, name="Fixture", country="JP", season=2026)
    db.session.add(team)
    db.session.flush()
    db.session.add(TrackedPlayer(player_api_id=98765, player_name="Fixture", team_id=team.id, age=25))
    db.session.commit()
    assert resolve_public_adult_subject(98765) is not None  # legacy remains unchanged
    assert not is_public_adult(98765)


def test_lifting_one_program_preserves_another_program_hold(foundation_app):
    user = _user()
    first = _program()
    second = ClubProgram(
        funding_league_id=first.funding_league_id,
        name="Second Fixture",
        legal_name="Second Fixture",
        slug="fixture-two",
        country="JP",
        region="Fixture",
        platform_status="approved",
    )
    db.session.add(second)
    db.session.flush()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=first.id)
    db.session.add(ClubRosterMember(program_id=second.id, local_player_id=local.id, added_by_user_id=user.id))
    first.emergency_hidden = second.emergency_hidden = True
    db.session.commit()
    client = foundation_app.test_client()
    assert (
        client.post(
            f"/api/admin/programs/{first.id}/emergency-lift", headers=_admin(), json={"reason": "Fixture lift"}
        ).status_code
        == 200
    )
    assert not club_publication_held(first.id) and club_publication_held(second.id)
    assert not is_public_adult(local.api_player_id)


def test_audit_rollback_and_missing_program(foundation_app):
    record_admin_event("admin-fixture@example.com", "fixture", "fixture", 1, "Fixture reason")
    db.session.flush()
    db.session.rollback()
    assert AdminActionEvent.query.count() == 0
    response = foundation_app.test_client().post(
        "/api/admin/programs/999/emergency-hide", headers=_admin(), json={"reason": "Fixture"}
    )
    assert response.status_code == 404
    assert AdminActionEvent.query.count() == 0


@pytest.mark.parametrize(
    "link", ["origin_alias", "roster_api", "claim", "affiliation", "local_club", "parent", "current"]
)
def test_all_linked_club_holds_with_correlated_api_filter(foundation_app, link):
    user = _user()
    program = _program()
    db.session.add(TeamProfile(team_id=4321, name="Fixture"))
    db.session.flush()
    program.team_api_id = 4321
    program.emergency_hidden = True
    signed_id = 12345
    db.session.add_all(
        [
            PlayerShadow(player_api_id=pid, player_name=f"Fixture {pid}", is_active=True, birth_date=date(1990, 1, 1))
            for pid in (signed_id, 54321)
        ]
    )
    if link == "origin_alias":
        local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
        local.api_player_id = signed_id
    elif link == "roster_api":
        db.session.add(ClubRosterMember(program_id=program.id, player_api_id=signed_id, added_by_user_id=user.id))
    elif link == "claim":
        db.session.add(
            PlayerProfileClaim(
                player_api_id=signed_id,
                user_account_id=user.id,
                relationship_type="player",
                status="approved",
                club_program_id=program.id,
            )
        )
    elif link in {"affiliation", "local_club"}:
        affiliation = PlayerClubAffiliation(player_api_id=signed_id, status="approved")
        if link == "affiliation":
            affiliation.team_api_id = 4321
        else:
            club = LocalClub(name="Fixture", normalized_name="fixture", status="approved", api_team_id=4321)
            db.session.add(club)
            db.session.flush()
            affiliation.local_club_id = club.id
        db.session.add(affiliation)
    else:
        team = Team(team_id=4321 if link == "parent" else 9876, name="Fixture", country="JP", season=2026)
        db.session.add(team)
        db.session.flush()
        db.session.add(
            TrackedPlayer(
                player_api_id=signed_id,
                player_name="Fixture",
                team_id=team.id,
                birth_date="1990-01-01",
                current_club_api_id=4321 if link == "current" else None,
            )
        )
    db.session.commit()
    assert subject_publication_held(signed_id)
    assert not subject_publication_held(54321)
    rows = PlayerShadow.query.filter(subject_publication_hold_filter(PlayerShadow.player_api_id)).all()
    assert [row.player_api_id for row in rows] == [signed_id]
