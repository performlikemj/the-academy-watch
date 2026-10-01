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
    import src.services.notification_outbox as outbox

    monkeypatch.setattr(outbox, "_templates", {})
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
        assert row.status == ("retry" if invalid == "unknown" else "cancelled")


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
    page = filter_public_adults(LocalPlayer.query, LocalPlayer.api_player_id, max_candidates=1)
    assert page.get_execution_options()["p2_adult_next_cursor"] == minor.api_player_id
    assert page.all() == []
    next_page = filter_public_adults(LocalPlayer.query, LocalPlayer.api_player_id, after=minor.api_player_id)
    assert [row.id for row in next_page.all()] == [adult.id]
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


@pytest.mark.parametrize("merged_side", [None, "affiliation", "program", "both"])
def test_local_only_club_program_hold(foundation_app, merged_side):
    target = LocalClub(name="Target", normalized_name="target", status="approved")
    db.session.add(target)
    db.session.flush()
    source = LocalClub(name="Source", normalized_name="source", status="merged", merged_into_local_club_id=target.id)
    sibling = LocalClub(name="Sibling", normalized_name="sibling", status="merged", merged_into_local_club_id=target.id)
    db.session.add_all([source, sibling])
    db.session.flush()
    program = _program()
    program.slug = f"console-local-club-{source.id if merged_side in {'program', 'both'} else target.id}"
    assert program.team_api_id is None and target.api_team_id is None
    local = _local(birth_date=date(1990, 1, 1))
    db.session.add(
        PlayerClubAffiliation(
            local_player_id=local.id,
            local_club_id=sibling.id if merged_side in {"affiliation", "both"} else target.id,
            status="approved",
        )
    )
    program.emergency_hidden = True
    db.session.commit()
    assert subject_publication_held(local.api_player_id)
    assert not is_public_adult(local.api_player_id)
    program.emergency_hidden = False
    db.session.commit()
    assert is_public_adult(local.api_player_id)


@pytest.mark.parametrize("size", [1, 100, 101])
def test_adult_filter_constant_query_count_and_default_pagination(foundation_app, size):
    from sqlalchemy import event

    db.session.add_all(
        [
            PlayerShadow(player_api_id=20000 + i, player_name="Fixture", is_active=True, birth_date=date(1990, 1, 1))
            for i in range(size)
        ]
    )
    db.session.commit()
    statements = []

    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        page = filter_public_adults(PlayerShadow.query, PlayerShadow.player_api_id)
        rows = page.all()
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    assert len(rows) == min(size, 100)
    assert len(statements) == 8
    assert sum("club_programs.emergency_hidden" in statement for statement in statements) == 1
    assert page.get_execution_options()["p2_adult_next_cursor"] == (20099 if size > 100 else None)
    if size > 100:
        next_page = filter_public_adults(PlayerShadow.query, PlayerShadow.player_api_id, after=20099)
        assert [row.player_api_id for row in next_page.all()] == [20100]


@pytest.mark.parametrize(
    "payload",
    [
        {"player_id": "alice"},
        {"player_id": True},
        {"player_id": None},
        {"state": "alice"},
        {"decision": "undocumented"},
    ],
)
def test_payload_rejects_untyped_ids_and_undeclared_strings(foundation_app, payload):
    _template()
    with pytest.raises(ValueError):
        _intent(_user(), payload=payload)


def test_payload_allows_int_uuid_and_declared_template_enum(foundation_app):
    register_template(
        "fixture", eligible=lambda r, u: True, render=lambda r, u: {}, payload_enums={"state": {"approved"}}
    )
    row = _intent(
        _user(),
        payload={
            "player_id": 123,
            "event_id": "12345678-1234-1234-1234-123456789abc",
            "state": "approved",
            "version": 1,
        },
    )
    assert row.payload["state"] == "approved"


def test_unknown_template_backoff_exhaustion(foundation_app):
    row = _intent(_user(), template="unregistered")
    db.session.commit()
    now = datetime.now(UTC) + timedelta(seconds=1)
    send = Mock()
    for attempt in range(MAX_ATTEMPTS):
        dispatch_due(now=now + timedelta(hours=attempt), send=send)
        assert row.attempts == attempt + 1
        assert row.status == ("failed" if attempt == MAX_ATTEMPTS - 1 else "retry")
        assert row.last_error == "template_unavailable"
    send.assert_not_called()


def test_expired_lease_reclaims_and_rejects_old_finalize(foundation_app):
    import src.services.notification_outbox as outbox

    row = _intent(_user())
    db.session.commit()
    _template()
    now = datetime.now(UTC) + timedelta(seconds=1)
    row_id, old_token = outbox._claim(now)
    assert dispatch_due(now=now + timedelta(seconds=outbox.LEASE_SECONDS - 1), send=Mock())["sent"] == 0
    send = Mock(return_value=EmailResult(success=True, provider="fixture"))
    assert dispatch_due(now=now + timedelta(seconds=outbox.LEASE_SECONDS), send=send)["sent"] == 1
    assert row.attempts == 2 and row.lease_token is None
    assert outbox._finalize(row_id, old_token, "retry", "delivery_failed", now) is None
    assert row.status == "sent"


def test_erase_pending_referenced_account_and_tombstoned_subject(foundation_app):
    subject, recipient = _user(), _user("recipient@example.com")
    pending = _intent(recipient, entity_type="user_account", entity_id=subject.id)
    sent = _intent(recipient, dedupe_key="sent-reference", entity_type="user_account", entity_id=subject.id)
    sent.status = "sent"
    db.session.commit()
    pending_id, sent_id = pending.id, sent.id
    assert erase_foundation_rows(subject.id, subject.email, _SchemaView())["notifications_deleted"] == 1
    db.session.commit()
    assert db.session.get(NotificationOutbox, pending_id) is None
    assert db.session.get(NotificationOutbox, sent_id) is not None
    row = _intent(recipient, dedupe_key="tombstone-reference", entity_type="user_account", entity_id=subject.id)
    subject.is_tombstone = True
    db.session.commit()
    _template()
    send = Mock()
    assert dispatch_due(now=datetime.now(UTC) + timedelta(seconds=1), send=send)["cancelled"] == 1
    assert row.status == "cancelled"
    send.assert_not_called()


def test_no_foundation_count_for_empty_erasure_flag_off(foundation_app, monkeypatch):
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    result = delete_account(_user())
    assert "foundation" not in result.counts


@pytest.mark.parametrize("namespace", ["api", "local"])
def test_existing_public_page_media_share_search_hold_and_lift(foundation_app, monkeypatch, namespace):
    from io import BytesIO
    from pathlib import Path

    import src.routes.share as share
    from flask import Response
    from src.models.showcase import PlayerShowcaseMedia
    from src.routes.api import api_bp
    from src.routes.players import players_bp
    from src.routes.share import share_bp
    from src.routes.showcase import showcase_bp
    from src.services import showcase_media_storage

    foundation_app.template_folder = str(Path(__file__).resolve().parents[1] / "src" / "templates")
    foundation_app.register_blueprint(api_bp, url_prefix="/api")
    foundation_app.register_blueprint(players_bp, url_prefix="/api")
    foundation_app.register_blueprint(showcase_bp, url_prefix="/api")
    foundation_app.register_blueprint(share_bp)
    monkeypatch.setattr(
        showcase_media_storage, "published_response", lambda path: Response(b"fixture-image", mimetype="image/jpeg")
    )
    monkeypatch.setattr(share, "render_share_card", lambda subject: BytesIO(b"fixture-card"))
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
        db.session.add(
            PlayerShadow(player_api_id=12345, player_name="Fixture", birth_date=date(1990, 1, 1), is_active=True)
        )
    signed_id = local.api_player_id
    prefix = f"players/{signed_id}" if namespace == "api" else f"local-players/{local.id}"
    blob = f"{prefix}/fixture.jpg"
    db.session.add(
        PlayerShowcaseMedia(
            player_api_id=signed_id if namespace == "api" else None,
            local_player_id=local.id if namespace == "local" else None,
            kind="photo",
            status="approved",
            blob_path=blob,
            public_url=blob,
        )
    )
    db.session.commit()
    client = foundation_app.test_client()
    paths = [f"/api/{prefix}/showcase", f"/api/media/published/{blob}", f"/p/{signed_id}", f"/p/{signed_id}/card.png"]
    paths.append(f"/api/players/{signed_id}/profile" if namespace == "api" else f"/api/local-players/{local.id}")
    for path in paths:
        assert client.get(path).status_code == 200, path
    for action, status in [("hide", 404), ("lift", 200)]:
        assert (
            client.post(
                f"/api/admin/programs/{program.id}/emergency-{action}", headers=_admin(), json={"reason": "Fixture"}
            ).status_code
            == 200
        )
        monkeypatch.delenv("P2_FOUNDATION_ENABLED")
        for path in paths:
            assert client.get(path).status_code == status, path
        from src.services.player_suppression import public_player_visible_filter

        listed = LocalPlayer.query.filter(public_player_visible_filter(LocalPlayer.api_player_id)).all()
        assert bool(listed) == (status == 200)
        assert PlayerSuppression.query.count() == 0
        monkeypatch.setenv("P2_FOUNDATION_ENABLED", "1")


@pytest.mark.parametrize("namespace", ["api", "local"])
@pytest.mark.parametrize("mutation", ["profile", "photo", "reel"])
def test_owner_can_edit_remove_during_hold_but_public_reads_remain_hidden(
    foundation_app, monkeypatch, namespace, mutation
):
    from src.models.league import PlayerLink
    from src.models.showcase import PlayerShowcaseMedia, PlayerShowcaseProfile
    from src.routes.showcase import showcase_bp
    from src.services import showcase_media_storage

    foundation_app.register_blueprint(showcase_bp, url_prefix="/api")
    program = _program()
    owner, stranger = _user(), _user("stranger@example.com")
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
        db.session.add(
            PlayerShadow(player_api_id=12345, player_name="Fixture", birth_date=date(1990, 1, 1), is_active=True)
        )
    identity = {"player_api_id": local.api_player_id} if namespace == "api" else {"local_player_id": local.id}
    db.session.add(
        PlayerProfileClaim(**identity, user_account_id=owner.id, relationship_type="player", status="approved")
    )
    profile = PlayerShowcaseProfile(**identity, bio="Before", status="approved")
    db.session.add(profile)
    prefix = f"players/{local.api_player_id}" if namespace == "api" else f"local-players/{local.id}"
    blob = f"{prefix}/fixture.jpg"
    photo = PlayerShowcaseMedia(**identity, kind="photo", status="approved", blob_path=blob, public_url=blob)
    reel_identity = {"player_id": local.api_player_id} if namespace == "api" else identity
    reel = PlayerLink(
        **reel_identity, user_id=owner.id, url="https://youtu.be/fixture123", link_type="highlight", status="approved"
    )
    db.session.add_all([photo, reel])
    program.emergency_hidden = True
    db.session.commit()
    photo_id, reel_id = photo.id, reel.id
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    monkeypatch.setattr(showcase_media_storage, "is_configured", lambda: True)
    delete_pending, delete_published = Mock(), Mock()
    monkeypatch.setattr(showcase_media_storage, "delete_pending", delete_pending)
    monkeypatch.setattr(showcase_media_storage, "delete_published", delete_published)
    client = foundation_app.test_client()
    headers = {"Authorization": f"Bearer {issue_user_token(owner.email)['token']}"}
    stranger_headers = {"Authorization": f"Bearer {issue_user_token(stranger.email)['token']}"}
    public_path = f"/api/{prefix}/showcase"
    for method in (client.get, client.head):
        assert method(public_path).status_code == 404
        assert method(public_path, headers=headers).status_code == 404
    assert client.get(f"/api/media/published/{blob}").status_code == 404
    if mutation == "profile":
        endpoint = f"/api/{prefix}/showcase/profile"
        assert client.patch(endpoint, headers=stranger_headers, json={"bio": "Unauthorized"}).status_code == 403
        response = client.patch(endpoint, headers=headers, json={"bio": "Incident edit"})
        assert response.status_code == 200, response.json
        assert db.session.get(PlayerShowcaseProfile, profile.id).bio == "Incident edit"
    else:
        endpoint = f"/api/{prefix}/showcase/{'photos' if mutation == 'photo' else 'reel'}/{photo_id if mutation == 'photo' else reel_id}"
        assert client.delete(endpoint, headers=stranger_headers).status_code == 403
        response = client.delete(endpoint, headers=headers)
        assert response.status_code == 200, response.json
        assert (
            db.session.get(
                PlayerShowcaseMedia if mutation == "photo" else PlayerLink, photo_id if mutation == "photo" else reel_id
            )
            is None
        )
        if mutation == "photo":
            delete_pending.assert_called_once_with(blob)
            delete_published.assert_called_once_with(blob)
    assert client.get(public_path).status_code == 404
    assert subject_publication_held(local.api_player_id)
    assert PlayerSuppression.query.count() == 0


@pytest.mark.parametrize("namespace", ["api", "local"])
def test_actual_suppression_still_blocks_existing_owner_profile_write(foundation_app, namespace):
    from src.routes.showcase import showcase_bp

    foundation_app.register_blueprint(showcase_bp, url_prefix="/api")
    program = _program()
    owner = _user()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
    identity = {"player_api_id": local.api_player_id} if namespace == "api" else {"local_player_id": local.id}
    db.session.add(
        PlayerProfileClaim(**identity, user_account_id=owner.id, relationship_type="player", status="approved")
    )
    db.session.add(
        PlayerSuppression(
            **identity,
            reason_code="admin_other",
            requester_role="other",
            requester_contact="fixture@example.com",
            request_statement="Fixture",
            status="active",
        )
    )
    program.emergency_hidden = True
    db.session.commit()
    prefix = f"players/{local.api_player_id}" if namespace == "api" else f"local-players/{local.id}"
    response = foundation_app.test_client().patch(
        f"/api/{prefix}/showcase/profile",
        json={"bio": "Must remain blocked"},
        headers={"Authorization": f"Bearer {issue_user_token(owner.email)['token']}"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("cursor_sweep", [False, True])
def test_shadow_refresh_includes_held_rows_without_cursor_skip_and_discovery_hides_them(
    foundation_app, monkeypatch, cursor_sweep
):
    import src.services.player_shadow_service as shadows
    from src.models.follow import PlayerShadowStats
    from src.services.player_suppression import public_player_visible_filter, without_active_suppression

    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    monkeypatch.setattr(shadows, "_current_season_start_year", lambda client: 2026)
    program = _program()
    anchor = PlayerShadow(player_api_id=6000, player_name="Anchor", is_active=False)
    held = PlayerShadow(player_api_id=7001, player_name="Fixture Held", birth_date=date(1990, 1, 1), is_active=True)
    visible = PlayerShadow(
        player_api_id=7002, player_name="Fixture Visible", birth_date=date(1990, 1, 1), is_active=True
    )
    suppressed = PlayerShadow(player_api_id=7003, player_name="Fixture Suppressed", is_active=True)
    db.session.add_all([anchor, held, visible, suppressed])
    db.session.flush()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    local.api_player_id = held.player_api_id
    db.session.add(
        PlayerSuppression(
            player_api_id=suppressed.player_api_id,
            reason_code="admin_other",
            requester_role="other",
            requester_contact="fixture@example.com",
            request_statement="Fixture",
            status="active",
        )
    )
    program.emergency_hidden = True
    db.session.commit()
    assert {
        row.player_api_id
        for row in PlayerShadow.query.filter(without_active_suppression(PlayerShadow.player_api_id)).all()
    } == {6000, 7001, 7002}
    assert 7001 not in {
        row.player_api_id
        for row in PlayerShadow.query.filter(public_player_visible_filter(PlayerShadow.player_api_id)).all()
    }
    client = Mock()
    client._make_request.return_value = {
        "response": [
            {
                "statistics": [
                    {
                        "team": {"id": 42, "name": "Fixture"},
                        "games": {"appearences": 2, "minutes": 180},
                        "goals": {"total": 1, "assists": 2},
                    }
                ]
            }
        ]
    }
    client.get_player_profile.return_value = {"player": {"name": "Fixture Refreshed"}}
    client.search_player_profiles_global.return_value = [
        {"player": {"id": pid, "name": "Fixture"}} for pid in (7001, 7002, 7003)
    ]
    assert [row["player_api_id"] for row in shadows.search_players("Fixture", api_client=client)] == [7002]
    first = shadows.refresh_shadows(limit=1, cursor=anchor.id if cursor_sweep else None, api_client=client)
    assert first["considered"] == first["stats_upserted"] == first["profiles_refreshed"] == 1
    assert first["failed"] == 0 and held.last_stats_sync_at is not None
    assert held.player_name == "Fixture Refreshed"
    assert PlayerShadowStats.query.filter_by(player_api_id=7001).one().minutes == 180
    if cursor_sweep:
        assert first["next_cursor"] == held.id
    second = shadows.refresh_shadows(limit=1, cursor=first["next_cursor"] if cursor_sweep else None, api_client=client)
    assert second["considered"] == 1 and visible.last_stats_sync_at is not None
    assert PlayerShadowStats.query.filter_by(player_api_id=7002).one().goals == 1
    if cursor_sweep:
        assert second["next_cursor"] == visible.id
        assert shadows.refresh_shadows(limit=1, cursor=second["next_cursor"], api_client=client)["considered"] == 0
    assert suppressed.last_stats_sync_at is None
    assert {call.args[1]["id"] for call in client._make_request.call_args_list} == {7001, 7002}
    assert subject_publication_held(7001)  # updating stats never lifts the public incident hold


@pytest.fixture
def public_player_reads(foundation_app, monkeypatch):
    from src.routes.academy import academy_bp
    from src.routes.api import api_bp
    from src.routes.journey import journey_bp
    from src.routes.player_matches import player_matches_bp
    from src.routes.players import players_bp
    from src.routes.showcase import showcase_bp

    for blueprint in (players_bp, showcase_bp, academy_bp, journey_bp, player_matches_bp, api_bp):
        foundation_app.register_blueprint(blueprint, url_prefix="/api")
    # Use only database-backed/stub data; no upstream fetches during this audit.
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "1")
    return foundation_app.test_client()


_PUBLIC_READ_CASES = [
    (namespace, suffix)
    for namespace in ("api", "local")
    for suffix in (
        "stats",
        "profile",
        "season-stats",
        "availability",
        "journey",
        "journey/map",
        "showcase",
        "followers/count",
        "matches",
    )
] + [("api", suffix) for suffix in ("academy-stats", "comments", "links", "commentaries")]


@pytest.mark.parametrize("namespace,suffix", _PUBLIC_READ_CASES)
def test_every_public_player_id_read_hold_and_lift(foundation_app, public_player_reads, monkeypatch, namespace, suffix):
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
        db.session.add(
            PlayerShadow(player_api_id=12345, player_name="Fixture", birth_date=date(1990, 1, 1), is_active=True)
        )
    db.session.commit()
    if namespace == "api":
        team = Team(team_id=9001, name="Fixture club", country="JP", season=2025)
        db.session.add(team)
        db.session.flush()
        db.session.add(
            TrackedPlayer(
                player_api_id=local.api_player_id,
                player_name="Fixture",
                team_id=team.id,
                birth_date="1990-01-01",
                status="academy",
                data_source="api-football",
                is_active=True,
            )
        )
        db.session.commit()
    path = f"/api/players/{local.api_player_id}/{suffix}"
    before = public_player_reads.get(path)
    assert before.status_code == 200, (path, before.json)
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    for method in (public_player_reads.get, public_player_reads.head):
        held = method(path)
        assert held.status_code == 404, (path, held.json)
    assert public_player_reads.get(path).json == {"error": "Player not found"}
    program.emergency_hidden = False
    db.session.commit()
    restored = public_player_reads.get(path)
    assert restored.status_code == before.status_code, (path, restored.json)
    assert PlayerSuppression.query.count() == 0


@pytest.mark.parametrize("namespace", ["api", "local"])
def test_reported_match_hold_preserves_owner_crud(foundation_app, public_player_reads, monkeypatch, namespace):
    from src.models.player_match_entry import PlayerMatchEntry

    owner = _user()
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
        db.session.add(
            PlayerShadow(player_api_id=12345, player_name="Fixture", birth_date=date(1990, 1, 1), is_active=True)
        )
    identity = {"player_api_id": local.api_player_id} if namespace == "api" else {"local_player_id": local.id}
    db.session.add(
        PlayerProfileClaim(**identity, user_account_id=owner.id, relationship_type="player", status="approved")
    )
    club_entry = PlayerMatchEntry(
        player_api_id=local.api_player_id,
        season=2025,
        source="club",
        status="club_confirmed",
        reported_by_user_id=owner.id,
        club_program_id=program.id,
        match_date=date(2025, 9, 1),
        opponent="Club fixture",
        home_away="home",
        minutes=90,
        note="Club report",
    )
    db.session.add(club_entry)
    db.session.commit()
    path = f"/api/players/{local.api_player_id}/matches"
    headers = {"Authorization": f"Bearer {issue_user_token(owner.email)['token']}"}
    payload = {"match_date": "2025-09-02", "opponent": "Self fixture", "home_away": "away", "note": "Self report"}
    created = public_player_reads.post(path, headers=headers, json=payload)
    assert created.status_code == 201, created.json
    entry_id = created.json["match"]["id"]
    visible = public_player_reads.get(path)
    assert visible.status_code == 200 and visible.json["total"] == 2
    assert {entry["source"] for entry in visible.json["matches"]} == {"self", "club"}
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    for auth in ({}, headers):
        assert public_player_reads.get(path, headers=auth).json == {"error": "Player not found"}
        assert public_player_reads.get(path, headers=auth).status_code == 404
    updated = public_player_reads.patch(f"{path}/{entry_id}", headers=headers, json={"note": "Incident edit"})
    assert updated.status_code == 200, updated.json
    assert db.session.get(PlayerMatchEntry, entry_id).note == "Incident edit"
    created_during = public_player_reads.post(path, headers=headers, json={**payload, "match_date": "2025-09-03"})
    assert created_during.status_code == 201, created_during.json
    assert public_player_reads.delete(f"{path}/{entry_id}", headers=headers).status_code == 200
    program.emergency_hidden = False
    db.session.commit()
    assert public_player_reads.get(path).json["total"] == 2
    assert PlayerSuppression.query.count() == 0


@pytest.mark.parametrize("namespace", ["api", "local"])
@pytest.mark.parametrize("suffix,surface", [("stats", "player_stats"), ("season-stats", "season_stats")])
def test_rollup_public_reads_remain_held(foundation_app, public_player_reads, monkeypatch, namespace, suffix, surface):
    from src.models.season_rollup import PlayerSeasonTotal

    monkeypatch.setenv("SEASON_ROLLUP_READS", surface)
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
        db.session.add(
            PlayerShadow(player_api_id=12345, player_name="Fixture", birth_date=date(1990, 1, 1), is_active=True)
        )
    db.session.add(
        PlayerSeasonTotal(
            player_api_id=local.api_player_id,
            season=2025,
            level_group="senior",
            primary_source="fixtures",
            computed_at=datetime.now(UTC),
            appearances=1,
            minutes=90,
            goals=1,
            clubs=[],
        )
    )
    db.session.commit()
    path = f"/api/players/{local.api_player_id}/{suffix}?season=2025"
    visible = public_player_reads.get(path)
    assert visible.status_code == 200, visible.json
    if suffix == "stats":
        assert visible.json["provenance"]["primary_source"] == "fixtures", visible.json
        assert visible.json["summary"]["minutes"] == 90
    else:
        assert visible.json["source"] == "season-rollup", visible.json
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    assert public_player_reads.get(path).status_code == 404
    program.emergency_hidden = False
    db.session.commit()
    restored = public_player_reads.get(path)
    assert restored.status_code == 200
    assert restored.json == visible.json


def test_tracked_loan_journey_hold_and_lift(foundation_app, public_player_reads, monkeypatch):
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    local.api_player_id = 12345
    team = Team(team_id=9001, name="Fixture club", country="JP", season=2025)
    db.session.add(team)
    db.session.flush()
    tracked = TrackedPlayer(
        player_api_id=12345,
        player_name="Fixture",
        team_id=team.id,
        birth_date="1990-01-01",
        status="academy",
        data_source="api-football",
        is_active=True,
    )
    db.session.add(tracked)
    db.session.commit()
    path = f"/api/loans/{tracked.id}/journey"
    assert public_player_reads.get(path).status_code == 200
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    assert public_player_reads.get(path).status_code == 404
    assert public_player_reads.head(path).status_code == 404
    program.emergency_hidden = False
    db.session.commit()
    assert public_player_reads.get(path).status_code == 200


@pytest.mark.parametrize("namespace", ["api", "local"])
@pytest.mark.parametrize("stale", [False, True])
def test_sitemap_cached_and_new_player_urls_hold_and_lift(foundation_app, monkeypatch, namespace, stale):
    import time
    import xml.etree.ElementTree as ET

    from src.routes.share import share_bp
    from src.services import sitemap_service

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://theacademywatch.com")
    foundation_app.register_blueprint(share_bp)
    program = _program()
    local = _local(birth_date=date(1990, 1, 1), origin_program_id=program.id)
    if namespace == "api":
        local.api_player_id = 12345
        team = Team(team_id=9001, name="Fixture club", country="JP", season=2025)
        db.session.add(team)
        db.session.flush()
        db.session.add(
            TrackedPlayer(
                player_api_id=12345,
                player_name="Fixture",
                team_id=team.id,
                birth_date="1990-01-01",
                status="academy",
                data_source="api-football",
                is_active=True,
            )
        )
    db.session.commit()
    sitemap_service.clear_sitemap_cache()
    xml = sitemap_service.build_sitemap_xml()
    prefix = f"players/{local.api_player_id}" if namespace == "api" else f"local-players/{local.id}"
    origin = "https://theacademywatch.com"
    player_url, program_url = f"{origin}/{prefix}", f"{origin}/programs/fixture"

    def locations(body):
        return {node.text for node in ET.fromstring(body).iter(f"{{{sitemap_service.SITEMAP_NAMESPACE}}}loc")}

    assert {player_url, program_url} <= locations(xml)
    # Cache predates the incident. Avoid racing a background fixture DB connection.
    monkeypatch.setattr(sitemap_service, "_start_background_build", Mock(return_value=False))
    monkeypatch.setattr(sitemap_service, "_cache", {"xml": xml, "built_at": time.monotonic() - (7200 if stale else 0)})
    client = foundation_app.test_client()
    assert client.get("/sitemap.xml").data == xml
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.delenv("P2_FOUNDATION_ENABLED")
    for body in (sitemap_service.build_sitemap_xml(), client.get("/sitemap.xml").data):
        assert player_url not in locations(body)
        assert program_url not in locations(body)
    assert sitemap_service._cache["xml"] == xml  # lifting can restore the original response copy
    assert client.head("/sitemap.xml").status_code == 200
    program.emergency_hidden = False
    db.session.commit()
    assert client.get("/sitemap.xml").data == xml
    assert {player_url, program_url} <= locations(sitemap_service.build_sitemap_xml())
