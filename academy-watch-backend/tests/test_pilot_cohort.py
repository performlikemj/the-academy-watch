"""P1 checker: real route, persisted sources, narrow serialization, no writes."""

import copy
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, FundingLeague
from src.models.league import UserAccount, db
from src.models.player_fan import PlayerFan
from src.models.player_match_entry import PlayerMatchEntry
from src.models.product_event import ProductEvent
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.trust import ScoutVerification
from src.routes.events import events_bp

START = datetime(2026, 9, 5)
URL = "/api/admin/pilot-cohort/report"


def postgres_report_tables():
    """Real P1 tables and FK dependencies, without unrelated PG15-only DDL."""
    from src.models.contact import ContactOutcome, ContactRequest
    from src.models.follow import PlayerShadow
    from src.models.player_suppression import PlayerSuppression

    tables = {
        model.__table__
        for model in (
            FundingLeague,
            ClubProgram,
            ClubProgramClaim,
            ClubProgramManager,
            UserAccount,
            LocalPlayer,
            PlayerProfileClaim,
            ScoutVerification,
            PlayerMatchEntry,
            ScoutWatchlistEntry,
            PlayerFan,
            ProductEvent,
            ContactOutcome,
            ContactRequest,
            PlayerShadow,
            PlayerSuppression,
        )
    }
    pending = list(tables)
    while pending:
        for foreign_key in pending.pop().foreign_keys:
            dependency = foreign_key.column.table
            if dependency not in tables:
                tables.add(dependency)
                pending.append(dependency)
    return sorted(tables, key=lambda table: table.name)


@pytest.fixture
def app(monkeypatch, request):
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "cGlsb3QtcDEtdGVzdC1rZXktMzItYnl0ZXMtMTIzNDU=")
    monkeypatch.setenv("ADMIN_API_KEY", "pilot-test-key")
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("REVIEW_LOGIN_ACCOUNTS", raising=False)
    monkeypatch.delenv("REVIEW_LOGIN_EMAIL", raising=False)
    monkeypatch.delenv("REVIEW_LOGIN_CODE", raising=False)
    uri = postgres_url() if getattr(request, "param", None) == "postgresql" else "sqlite:///:memory:"
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="pilot-secret",
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"options": "-c timezone=UTC"}}
        if uri.startswith("postgresql")
        else {},
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
        RATELIMIT_STORAGE_URI="memory://",
    )
    db.init_app(app)
    limiter.init_app(app)
    limiter.enabled = False
    app.register_blueprint(events_bp, url_prefix="/api")
    with app.app_context():
        limiter.reset()
        tables = postgres_report_tables() if db.engine.dialect.name == "postgresql" else None
        db.metadata.create_all(db.engine, tables=tables)
        db.session.add(
            FundingLeague(
                id=1,
                name="PRIVATE_LEAGUE",
                country="Japan",
                region="Kanto",
                level="youth_regional",
                age_bands=["adult"],
                gender_program="both",
                season_calendar="calendar_year",
                data_tier="self_reported",
            )
        )
        db.session.flush()
        db.session.add(
            ClubProgram(
                id=7,
                funding_league_id=1,
                name="PRIVATE_CLUB",
                legal_name="PRIVATE_LEGAL",
                slug="pilot",
                country="Japan",
                region="Kanto",
                platform_status="approved",
            )
        )
        db.session.add_all(
            [
                UserAccount(
                    id=i,
                    email=f"private{i}@example.test",
                    display_name=f"PRIVATE_NAME_{i}",
                    display_name_lower=f"private_{i}",
                )
                for i in range(1, 7)
            ]
        )
        db.session.flush()
        db.session.add(
            ClubProgramClaim(
                id=1, program_id=7, user_account_id=1, relationship_type="club_official", status="approved"
            )
        )
        db.session.add(
            LocalPlayer(
                id=42,
                display_name="PRIVATE_PLAYER",
                normalized_name="private player",
                birth_date=date(2000, 1, 1),
                status="approved",
                api_player_id=-42,
            )
        )
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=7, user_account_id=1, source_claim_id=1, status="active", granted_by="PRIVATE_ADMIN"
            )
        )
        db.session.add(
            PlayerProfileClaim(
                id=1,
                user_account_id=2,
                local_player_id=42,
                relationship_type="player",
                status="approved",
                reviewed_at=START - timedelta(days=1),
                message="PRIVATE_BODY",
            )
        )
        db.session.add(
            ScoutVerification(
                user_account_id=3,
                full_name="PRIVATE_SCOUT",
                organization="PRIVATE_ORG",
                role_title="Scout",
                statement="PRIVATE_STATEMENT",
                status="approved",
                reviewed_at=START - timedelta(days=1),
            )
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.metadata.drop_all(db.engine, tables=tables)
        limiter.reset()


@pytest.fixture
def client(app):
    return app.test_client()


def headers(email="admin@example.test", role="admin"):
    return {"Authorization": f"Bearer {issue_user_token(email, role=role)['token']}", "X-API-Key": "pilot-test-key"}


@pytest.fixture
def register():
    return {
        "schema_version": 1,
        "cohort_id": "one-club-pilot",
        "declared_at": "2026-09-05T00:00:00Z",
        "program_id": 7,
        "window": {"start": "2026-09-05T00:00:00Z", "end": "2026-10-05T00:00:00Z"},
        "participants": [
            {
                "person_key": f"p{i}",
                "primary_role": role,
                "user_account_ids": [i],
                "player_api_ids": [-42] if i == 2 else [],
                "own_account_verified": True,
                "excluded": False,
            }
            for i, role in enumerate(("staff", "player", "scout", "supporter"), 1)
        ],
        "excluded_user_account_ids": [5],
        "observations": [],
        "continuation": {"decision": "not_discussed", "occurred_at": None, "evidence_ref": None},
    }


def action(day=0, *, actor=1, subject=-42, program=7, source="club"):
    row = PlayerMatchEntry(
        player_api_id=subject,
        season=2026,
        source=source,
        status="club_confirmed" if source == "club" else "self_reported",
        reported_by_user_id=actor,
        club_program_id=program,
        match_date=START.date() + timedelta(days=day),
        opponent=f"PRIVATE_OPPONENT_{day}",
        home_away="home",
        created_at=START.replace(tzinfo=UTC) + timedelta(days=day),
        note="PRIVATE_NOTE",
    )
    db.session.add(row)
    db.session.commit()
    return row


def observe(register, row, *, person="p1", kind="self_operated_action", record_type="player_match_entry", when=None):
    register["observations"].append(
        {
            "id": f"o{len(register['observations'])}",
            "person_key": person,
            "kind": kind,
            "occurred_at": (when or row.created_at).isoformat() + "Z",
            "record_type": record_type,
            "record_id": str(row.id),
            "evidence_ref": "private-evidence-01",
        }
    )


def report(client, register, status=200):
    response = client.post(URL, json=register, headers=headers())
    assert response.status_code == status, response.get_json()
    assert response.headers["Cache-Control"] == "private, no-store"
    return response.get_json()


def test_duplicate_accounts_cannot_inflate_people(client, register):
    register["participants"][1]["user_account_ids"].append(1)
    assert report(client, register, 400) == {"error": "duplicate_account"}


def test_exclusions_override_database_and_observations(client, register, monkeypatch):
    observe(register, action())
    assert report(client, register)["summary"]["qualifying_people"] == 1
    register["excluded_user_account_ids"].append(1)
    assert report(client, register)["summary"]["qualifying_people"] == 0
    register["excluded_user_account_ids"].remove(1)
    register["participants"][0]["excluded"] = True
    assert report(client, register)["summary"]["qualifying_people"] == 0
    register["participants"][0]["excluded"] = False
    register["participants"][0]["user_account_ids"].append(5)
    assert report(client, register)["summary"]["qualifying_people"] == 0
    register["participants"][0]["user_account_ids"].remove(5)
    monkeypatch.setattr(
        "src.services.pilot_cohort._review_account_is_configured", lambda email: email == "private1@example.test"
    )
    assert report(client, register)["summary"]["qualifying_people"] == 0


def test_registration_and_anonymous_views_do_not_qualify(client, register):
    db.session.add(ProductEvent(event_name="profile_view", props={"player_api_id": -42}, created_at=START))
    db.session.commit()
    assert report(client, register)["summary"]["qualifying_people"] == 0


@pytest.mark.parametrize("configuration", ["admin", "review_player", "review_scout", "review_legacy"])
def test_configured_admin_and_review_accounts_are_automatically_excluded(client, register, monkeypatch, configuration):
    import json

    observe(register, action())
    assert report(client, register)["summary"]["qualifying_people"] == 1
    # An additional account in the same reconciled row excludes the whole person.
    register["participants"][0]["user_account_ids"].append(6)
    if configuration == "admin":
        monkeypatch.setenv("ADMIN_EMAILS", "another@example.test, PRIVATE6@EXAMPLE.TEST ")
    elif configuration == "review_legacy":
        monkeypatch.setenv("REVIEW_LOGIN_EMAIL", " PRIVATE6@EXAMPLE.TEST ")
        monkeypatch.setenv("REVIEW_LOGIN_CODE", "PRIVATE_REVIEW_CODE")
    else:
        monkeypatch.setenv(
            "REVIEW_LOGIN_ACCOUNTS",
            json.dumps(
                {configuration.removeprefix("review_"): {"email": "PRIVATE6@EXAMPLE.TEST", "code": "PRIVATE_CODE"}}
            ),
        )
    result = report(client, register)
    assert result["summary"]["qualifying_people"] == 0
    assert "excluded" in result["participants"][0]["missing"]
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["staff_review", "cross_person_outcome"])
def test_unused_observation_kinds_are_explicitly_rejected(client, register, kind):
    observe(register, action(), kind=kind)
    assert report(client, register, 400) == {"error": "unsupported_kind"}


@pytest.mark.parametrize("when", ["2026-10-05T00:00:00Z", "2026-11-01T12:00:00Z", "2026-09-04T12:00:00Z"])
def test_continuation_outside_window_preserves_register_and_action_counts(client, register, when):
    observe(register, action())
    before = report(client, register)
    register["continuation"] = {"decision": "agreed", "occurred_at": when, "evidence_ref": "review-01"}
    after = report(client, register)
    assert after["register_sha256"] == before["register_sha256"]
    assert after["summary"] == before["summary"]
    assert after["participants"] == before["participants"]
    assert after["continuation"] == {"decision": "agreed", "occurred_at": when, "evidence_basis": "operator"}
    register["observations"][0]["occurred_at"] = when
    assert report(client, register, 400) == {"error": "invalid_observation"}


def test_operator_observation_cannot_invent_database_action(client, register):
    row = action()
    observe(register, row)
    db.session.delete(row)
    db.session.commit()
    assert report(client, register, 422) == {"error": "cohort_reference_invalid"}


@pytest.mark.parametrize("change", ["actor", "subject", "program", "before", "end", "unobserved", "disputed"])
def test_actor_subject_program_and_window_must_all_match(client, register, change):
    row = action()
    observe(register, row)
    if change == "actor":
        row.reported_by_user_id = 5
    if change == "subject":
        row.player_api_id = -43
    if change == "program":
        row.club_program_id = None
    if change == "before":
        row.created_at = START - timedelta(seconds=1)
    if change == "end":
        row.created_at = datetime(2026, 10, 5)
    if change == "unobserved":
        register["observations"] = []
    if change == "disputed":
        row.status = "disputed"
    db.session.commit()
    assert report(client, register)["summary"]["qualifying_people"] == 0


def test_seven_day_repeat_boundary_and_primary_role_counting(client, register):
    observe(register, action())
    row = action(7)
    row.created_at -= timedelta(seconds=1)
    db.session.commit()
    observe(register, row)
    result = report(client, register)
    assert result["summary"]["qualifying_people"] == 1
    assert result["summary"]["repeat_people"] == 0
    row.created_at += timedelta(seconds=1)
    db.session.commit()
    register["observations"].pop()
    observe(register, row)
    result = report(client, register)
    assert result["summary"]["repeat_staff"] == 1
    assert result["summary"]["by_role"] == {"staff": 1, "player": 0, "scout": 0, "supporter": 0}
    assert result["summary"]["repeat_target_met"] is False
    assert result["participants"][0]["repeat_dates"] == ["2026-09-12"]


def test_missing_future_tables_are_capability_gaps(client, register):
    action(actor=2, source="self")
    result = report(client, register)
    assert result["capabilities"] == {"relationships": False, "feedback": False, "stable_results": False}
    assert "accepted_relationship" in result["participants"][1]["missing"]
    assert "relationships_not_installed" in result["warnings"]


@pytest.mark.parametrize("change", ["revoked_manager", "minor", "suppressed", "deleted", "unverified"])
def test_deleted_revoked_minor_and_suppressed_subjects_do_not_qualify(client, register, change):
    observe(register, action())
    if change == "revoked_manager":
        ClubProgramManager.query.one().status = "revoked"
    if change == "minor":
        db.session.get(LocalPlayer, 42).birth_date = date(2020, 1, 1)
    if change == "suppressed":
        from src.models.player_suppression import PlayerSuppression

        db.session.add(
            PlayerSuppression(
                local_player_id=42,
                reason_code="player_request",
                requester_role="player",
                requester_contact="test@example.test",
                request_statement="private",
                status="active",
            )
        )
    if change == "deleted":
        db.session.delete(db.session.get(UserAccount, 1))
    if change == "unverified":
        register["participants"][0]["own_account_verified"] = False
    db.session.commit()
    result = report(client, register, 422 if change == "deleted" else 200)
    if change != "deleted":
        assert result["summary"]["qualifying_people"] == 0


def test_report_contains_no_private_bodies_names_emails_or_tokens(client, register):
    observe(register, action())
    before = {
        table.name: db.session.execute(db.select(db.func.count()).select_from(table)).scalar()
        for table in db.metadata.sorted_tables
    }
    first = report(client, register)
    second = report(client, register)
    assert {k: v for k, v in first.items() if k != "generated_at"} == {
        k: v for k, v in second.items() if k != "generated_at"
    }
    import json

    serialized = json.dumps(first)
    for secret in ("PRIVATE_", "@example", "private-evidence", headers()["Authorization"]):
        assert secret not in serialized
    after = {
        table.name: db.session.execute(db.select(db.func.count()).select_from(table)).scalar()
        for table in db.metadata.sorted_tables
    }
    assert before == after
    assert set(first["participants"][0]["evidence"][0]) == {"kind", "record_type", "record_id", "occurred_at", "basis"}


def test_admin_auth_precedes_rate_limit(client, register, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    for _ in range(8):
        assert client.post(URL, json=register).status_code == 401
        assert client.post(URL, json=register, headers=headers(role="user")).status_code == 401
    for _ in range(6):
        report(client, register)
    limited = client.post(URL, json=register, headers=headers())
    assert limited.status_code == 429
    assert limited.get_json() == {"error": "rate_limit_exceeded"}
    assert int(limited.headers["Retry-After"]) > 0
    assert limited.headers["Cache-Control"] == "private, no-store"
    assert client.post(URL, json=register).status_code == 401
    assert client.post(URL, json=register, headers=headers("ADMIN@EXAMPLE.TEST")).status_code == 429
    assert client.post(URL, json=register, headers=headers("other-admin@example.test")).status_code == 200


def test_pilot_ui_drops_identifiers_and_unknown_properties(client):
    payload = {
        "events": [
            {
                "name": "pilot_ui",
                "path": "/PRIVATE",
                "referrer": "PRIVATE",
                "session_id": "PRIVATE",
                "props": {
                    "package": "P1",
                    "action": "report_completed",
                    "outcome": "success",
                    "person_key": "PRIVATE",
                    "email": "PRIVATE",
                },
            }
        ]
    }
    assert client.post("/api/events", json=payload, headers=headers()).get_json() == {"accepted": 1}
    row = ProductEvent.query.one()
    assert row.props == {"package": "P1", "action": "report_completed", "outcome": "success"}
    assert (row.path, row.referrer, row.session_id, row.user_email) == (None, None, None, None)
    payload["events"][0]["props"]["action"] = ["unhashable"]
    assert client.post("/api/events", json=payload).get_json() == {"accepted": 0}


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("schema_version", True, "invalid_register"),
        ("program_id", True, "invalid_register"),
        ("participants", {}, "invalid_register"),
        ("observations", [{}], "invalid_observation"),
        ("cohort_id", "https://private.test", "invalid_register"),
        ("window", {"start": "2026-10-05T00:00:00Z", "end": "2026-09-05T00:00:00Z"}, "invalid_window"),
    ],
)
def test_strict_register_validation(client, register, field, value, code):
    register[field] = value
    assert report(client, register, 400) == {"error": code}


@pytest.mark.parametrize("payload", [None, [], True, "private", {"unknown": "private"}])
def test_non_object_and_unknown_json(client, payload):
    assert client.post(URL, json=payload, headers=headers()).get_json() == {"error": "invalid_register"}


def test_bounded_body(client):
    response = client.post(URL, data=b" " * (256 * 1024 + 1), headers=headers())
    assert response.status_code == 413
    assert response.get_json() == {"error": "register_too_large"}


def test_hash_excludes_observations_and_continuation(client, register):
    original = report(client, register)["register_sha256"]
    observe(register, action())
    register["continuation"] = {
        "decision": "agreed",
        "occurred_at": "2026-09-12T00:00:00Z",
        "evidence_ref": "decision-01",
    }
    assert report(client, register)["register_sha256"] == original
    changed = copy.deepcopy(register)
    changed["participants"][0]["excluded"] = True
    assert report(client, changed)["register_sha256"] != original


def test_scout_and_supporter_require_persisted_action(client, register):
    save = ScoutWatchlistEntry(user_account_id=3, player_api_id=-42, created_at=START)
    db.session.add_all([save, PlayerFan(user_account_id=4, player_api_id=-42, created_at=START - timedelta(days=1))])
    db.session.commit()
    observe(register, save, person="p3", kind="scout_discovery", record_type="scout_watchlist_entry")
    row = action(actor=2, source="self")
    observe(register, row, person="p4", kind="supporter_update_view", when=START + timedelta(hours=2))
    result = report(client, register)
    assert result["summary"]["by_role"] == {"staff": 0, "player": 0, "scout": 1, "supporter": 1}
    observe(register, row, person="p4", kind="supporter_update_view", when=START + timedelta(days=8))
    assert report(client, register)["summary"]["repeat_people"] == 0


def invitation_table(*, incomplete=False):
    """Literal P2 schema subset; deliberately independent of adapter constants."""
    import sqlalchemy as sa

    columns = [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("program_id", sa.Integer),
        sa.Column("player_api_id", sa.Integer),
        sa.Column("claim_id", sa.Integer),
        sa.Column("recipient_user_id", sa.Integer),
        sa.Column("created_by_user_id", sa.Integer),
        sa.Column("status", sa.String(20)),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("responded_at", sa.DateTime()),
    ]
    if not incomplete:
        columns.append(sa.Column("revoked_at", sa.DateTime()))
    table = sa.Table("club_invitations", sa.MetaData(), *columns)
    table.create(db.session.connection())
    db.session.commit()
    return table


def seed_invitation(table, **changes):
    values = dict(
        id="f339c308-9522-4c1f-ab1c-bcd21373bde0",
        program_id=7,
        player_api_id=-42,
        claim_id=1,
        recipient_user_id=2,
        created_by_user_id=1,
        status="accepted",
        created_at=START - timedelta(days=1),
        responded_at=START,
        revoked_at=None,
    )
    values.update(changes)
    db.session.execute(table.insert().values(**values))
    db.session.commit()


def test_future_table_adapters_use_exact_contract_columns(client, register):
    table = invitation_table(incomplete=True)
    try:
        assert report(client, register)["capabilities"]["relationships"] is False
    finally:
        table.drop(db.engine)
    table = invitation_table()
    try:
        seed_invitation(table)
        action(actor=2, source="self")
        action(day=7, actor=2, source="self")
        result = report(client, register)
        assert result["capabilities"]["relationships"] is True
        assert result["summary"]["by_role"]["player"] == 1
        assert result["summary"]["repeat_players"] == 1
        assert result["participants"][1]["evidence"][0]["basis"] == "database"
    finally:
        db.session.rollback()
        table.drop(db.engine)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "revoked"},
        {"revoked_at": START},
        {"recipient_user_id": 5},
        {"program_id": 8},
        {"player_api_id": -43},
        {"claim_id": 999},
        {"responded_at": START + timedelta(days=1)},
    ],
)
def test_relationship_prerequisites_and_action_order(client, register, changes):
    table = invitation_table()
    try:
        seed_invitation(table, **changes)
        action(actor=2, source="self")
        assert report(client, register)["summary"]["by_role"]["player"] == 0
    finally:
        db.session.rollback()
        table.drop(db.engine)


def test_contact_outcomes_require_distinct_registered_counterpart(client, register):
    from src.models.contact import ContactOutcome, ContactRequest

    contact = ContactRequest(
        id="f339c308-9522-4c1f-ab1c-bcd21373bde0",
        scout_user_id=3,
        player_api_id=-42,
        claim_id=1,
        message="PRIVATE_MESSAGE",
        status="accepted",
        created_at=START,
        expires_at=START + timedelta(days=10),
    )
    db.session.add(contact)
    db.session.flush()
    db.session.add(
        ContactOutcome(
            contact_request_id=contact.id,
            reported_by_user_id=3,
            stage="trial_scheduled",
            notes="PRIVATE_OUTCOME",
            occurred_at=START,
        )
    )
    db.session.commit()
    result = report(client, register)
    assert len(result["cross_person_outcomes"]) == 1
    assert result["cross_person_outcomes"][0]["stage"] == "trial_scheduled"
    # Earlier and later stage rows must not inflate this single contact.
    db.session.add_all(
        [
            ContactOutcome(
                contact_request_id=contact.id,
                reported_by_user_id=3,
                stage=stage,
                notes="PRIVATE_OUTCOME",
                occurred_at=START + timedelta(days=day),
            )
            for stage, day in [("signed", 2), ("contacted", 1), ("trial_scheduled", 30)]
        ]
    )
    db.session.commit()
    result = report(client, register)
    assert len(result["cross_person_outcomes"]) == 1
    assert result["cross_person_outcomes"][0]["stage"] == "signed"
    assert result["cross_person_outcomes"][0]["contact_request_id"] == contact.id
    assert report(client, register)["cross_person_outcomes"] == result["cross_person_outcomes"]
    register["participants"][2]["user_account_ids"].append(6)
    db.session.add(
        ScoutVerification(
            user_account_id=6,
            full_name="PRIVATE_SCOUT",
            organization="PRIVATE_ORG",
            role_title="Scout",
            statement="PRIVATE_STATEMENT",
            status="approved",
            reviewed_at=START - timedelta(days=1),
        )
    )
    second_contact = ContactRequest(
        id="f339c308-9522-4c1f-ab1c-bcd21373bde1",
        scout_user_id=6,
        player_api_id=-42,
        claim_id=1,
        message="PRIVATE_MESSAGE",
        status="accepted",
        created_at=START,
        expires_at=START + timedelta(days=10),
    )
    db.session.add(second_contact)
    db.session.flush()
    db.session.add(
        ContactOutcome(
            contact_request_id=second_contact.id, reported_by_user_id=6, stage="contacted", occurred_at=START
        )
    )
    db.session.commit()
    assert {row["contact_request_id"] for row in report(client, register)["cross_person_outcomes"]} == {
        contact.id,
        second_contact.id,
    }
    register["participants"][2]["excluded"] = True
    assert report(client, register)["cross_person_outcomes"] == []
    register["participants"][2]["excluded"] = False
    register["participants"][1]["user_account_ids"].append(3)
    register["participants"].pop(2)
    assert report(client, register)["cross_person_outcomes"] == []


def test_transaction_conflict_rolls_back_and_is_private(client, register, monkeypatch):
    import sqlalchemy as sa

    class SerializationFailure(Exception):
        sqlstate = "40001"

    def fail(_):
        db.session.add(ProductEvent(event_name="PRIVATE_UNCOMMITTED"))
        raise sa.exc.OperationalError("PRIVATE_SQL", {}, SerializationFailure())

    monkeypatch.setattr("src.services.pilot_cohort.build_report", fail)
    assert report(client, register, 409) == {"error": "retry_conflict"}
    assert ProductEvent.query.count() == 0


def postgres_url():
    import sqlalchemy as sa

    uri = os.getenv("PILOT_TEST_POSTGRES_URL")
    if not uri:
        pytest.skip("Set PILOT_TEST_POSTGRES_URL to a disposable local pilot_p1_test database")
    target = sa.engine.make_url(uri)
    assert target.host == "127.0.0.1" and target.database == "pilot_p1_test"
    return uri


@pytest.mark.parametrize("app", ["postgresql"], indirect=True)
@pytest.mark.parametrize("preceding_query", [False, True])
def test_postgresql_http_report_starts_fresh_read_only_snapshot(app, client, register, monkeypatch, preceding_query):
    """Exercise real dual auth, route transaction setup, ORM and reflected gaps."""
    import sqlalchemy as sa
    from src.services import pilot_cohort

    observe(register, action(), when=START)
    auth = headers()  # Token issuance itself queries UserAccount in this session.
    assert db.session().in_transaction()
    db.session.rollback()
    hook_calls, snapshot_modes = [], []

    @app.before_request
    def prior_request_work():
        if preceding_query:
            assert db.session.get(UserAccount, 1) is not None
            assert db.session().in_transaction()
            # Reporting must neither flush nor persist unrelated pending state.
            db.session.add(ProductEvent(event_name="PRIVATE_PENDING"))
            hook_calls.append(True)

    original = pilot_cohort.build_report

    def checked_build(data):
        snapshot_modes.append(
            (
                db.session.execute(sa.text("SHOW transaction_isolation")).scalar_one(),
                db.session.execute(sa.text("SHOW transaction_read_only")).scalar_one(),
            )
        )
        return original(data)

    monkeypatch.setattr(pilot_cohort, "build_report", checked_build)
    results = []
    for _ in range(2):
        response = client.post(URL, json=register, headers=auth)
        assert response.status_code == 200, response.get_json()
        assert response.headers["Cache-Control"] == "private, no-store"
        result = response.get_json()
        assert result["summary"]["qualifying_people"] == 1
        assert result["capabilities"] == {"relationships": False, "feedback": False, "stable_results": False}
        assert "accepted_relationship" in result["participants"][1]["missing"]
        assert "relationships_not_installed" in result["warnings"]
        assert "PRIVATE" not in response.get_data(as_text=True)
        result.pop("generated_at")
        results.append(result)
        assert ProductEvent.query.count() == 0
        assert PlayerMatchEntry.query.count() == 1
        db.session.rollback()
    assert results[0] == results[1]
    assert hook_calls == ([True, True] if preceding_query else [])
    assert snapshot_modes == [("repeatable read", "on")] * 2


def test_postgresql_reflection_and_read_only_snapshot():
    """Online PG adapter check; no SQLite/offline-DDL substitution."""
    from uuid import uuid4

    import sqlalchemy as sa
    from src.services.pilot_cohort import reflected_tables

    uri = postgres_url()
    pg_app = Flask("pilot_pg")
    pg_app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(pg_app)
    schema = "pilot_" + uuid4().hex
    with pg_app.app_context():
        engine = db.engine
        with engine.begin() as conn:
            conn.execute(sa.schema.CreateSchema(schema))
        try:
            db.session.execute(sa.text(f"SET search_path TO {schema}"))
            table = invitation_table(incomplete=True)
            assert "club_invitations" not in reflected_tables()
            db.session.execute(
                sa.text("ALTER TABLE club_invitations ADD COLUMN revoked_at TIMESTAMP WITHOUT TIME ZONE")
            )
            db.session.commit()
            assert "club_invitations" in reflected_tables()
            feedback_table(omit="acknowledged_at")
            result_table(omit="deleted_at")
            assert "player_feedback" not in reflected_tables()
            assert "club_results" not in reflected_tables()
            db.session.execute(
                sa.text("ALTER TABLE player_feedback ADD COLUMN acknowledged_at TIMESTAMP WITHOUT TIME ZONE")
            )
            db.session.execute(sa.text("ALTER TABLE club_results ADD COLUMN deleted_at TIMESTAMP WITHOUT TIME ZONE"))
            entries = sa.Table(
                "player_match_entries",
                sa.MetaData(),
                sa.Column("id", sa.Integer, primary_key=True),
                sa.Column("club_result_id", sa.String(36)),
                sa.Column("club_program_id", sa.Integer),
                sa.Column("player_api_id", sa.Integer),
                sa.Column("source", sa.String(16)),
                sa.Column("status", sa.String(16)),
            )
            entries.create(db.session.connection())
            db.session.commit()
            assert set(reflected_tables()) == {
                "club_invitations",
                "player_feedback",
                "club_results",
                "player_match_entries",
            }
            db.session.rollback()
            # Exactly the transaction mode used by the HTTP endpoint.
            db.session.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            assert db.session.execute(sa.text("SHOW transaction_read_only")).scalar() == "on"
            assert db.session.execute(sa.select(sa.func.count()).select_from(table)).scalar() == 0
            with engine.begin() as writer:
                writer.execute(sa.text(f"SET search_path TO {schema}"))
                writer.execute(table.insert().values(id="snapshot-check"))
            assert db.session.execute(sa.select(sa.func.count()).select_from(table)).scalar() == 0
            with pytest.raises(sa.exc.DBAPIError) as error:
                db.session.execute(table.insert().values(id="forbidden-write"))
            assert error.value.orig.sqlstate == "25006"
            db.session.rollback()
            assert db.session.execute(sa.select(sa.func.count()).select_from(table)).scalar() == 1
        finally:
            db.session.remove()
            with engine.begin() as conn:
                conn.execute(sa.schema.DropSchema(schema, cascade=True))
            engine.dispose()


@pytest.mark.parametrize("birth_date,qualifies", [(date(2000, 1, 1), True), (date(2020, 1, 1), False), (None, False)])
def test_positive_subjects_require_conservative_adult_proof(client, register, birth_date, qualifies):
    from src.models.follow import PlayerShadow

    db.session.add(
        PlayerShadow(player_api_id=1234, player_name="PRIVATE_POSITIVE", birth_date=birth_date, is_active=True)
    )
    db.session.commit()
    register["participants"][1]["player_api_ids"] = [1234]
    observe(register, action(subject=1234))
    assert report(client, register)["summary"]["qualifying_people"] == int(qualifies)


def test_unknown_nested_fields_and_boolean_subjects(client, register):
    register["participants"][0]["name"] = "PRIVATE_NAME"
    assert report(client, register, 400) == {"error": "invalid_register"}
    del register["participants"][0]["name"]
    register["participants"][1]["player_api_ids"] = [True]
    assert report(client, register, 400) == {"error": "invalid_register"}


def test_admin_second_factor_is_required_and_errors_are_private(client, register):
    for key in (None, "wrong"):
        auth = headers()
        if key is None:
            del auth["X-API-Key"]
        else:
            auth["X-API-Key"] = key
        response = client.post(URL, json=register, headers=auth)
        assert response.status_code in (401, 403)
        assert response.headers["Cache-Control"] == "private, no-store"


def feedback_table(*, omit=None):
    """P3's literal columns, including leak sentinels outside P1's projection."""
    import sqlalchemy as sa

    columns = [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thread_id", sa.String(36)),
        sa.Column("revision", sa.Integer),
        sa.Column("program_id", sa.Integer),
        sa.Column("invitation_id", sa.String(36)),
        sa.Column("claim_id", sa.Integer),
        sa.Column("recipient_user_id", sa.Integer),
        sa.Column("player_api_id", sa.Integer),
        sa.Column("author_user_id", sa.Integer),
        sa.Column("video_match_id", sa.Integer),
        sa.Column("title", sa.String(140)),
        sa.Column("body", sa.Text),
        sa.Column("observation_refs", sa.JSON),
        sa.Column("client_request_id", sa.String(36)),
        sa.Column("request_hash", sa.String(64)),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("acknowledged_at", sa.DateTime()),
        sa.Column("withdrawn_at", sa.DateTime()),
        sa.Column("audit_expires_at", sa.DateTime()),
    ]
    table = sa.Table("player_feedback", sa.MetaData(), *(c for c in columns if c.name != omit))
    table.create(db.session.connection())
    db.session.commit()
    return table


def result_table(*, omit=None):
    import sqlalchemy as sa

    columns = [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("program_id", sa.Integer),
        sa.Column("client_request_id", sa.String(36)),
        sa.Column("create_request_hash", sa.String(64)),
        sa.Column("version", sa.Integer),
        sa.Column("match_date", sa.Date),
        sa.Column("season", sa.Integer),
        sa.Column("opponent", sa.String(120)),
        sa.Column("opponent_key", sa.String(120)),
        sa.Column("competition", sa.String(120)),
        sa.Column("home_away", sa.String(8)),
        sa.Column("result_for", sa.Integer),
        sa.Column("result_against", sa.Integer),
        sa.Column("video_match_id", sa.Integer),
        sa.Column("created_by_user_id", sa.Integer),
        sa.Column("updated_by_user_id", sa.Integer),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("deleted_at", sa.DateTime()),
    ]
    table = sa.Table("club_results", sa.MetaData(), *(c for c in columns if c.name != omit))
    table.create(db.session.connection())
    db.session.commit()
    return table


@pytest.fixture
def future_schema(app):
    import sqlalchemy as sa

    invitation = invitation_table()
    feedback = feedback_table()
    result = result_table()
    db.session.execute(sa.text("ALTER TABLE player_match_entries ADD COLUMN club_result_id VARCHAR(36)"))
    db.session.commit()
    seed_invitation(invitation)
    yield {"invitation": invitation, "feedback": feedback, "result": result}
    db.session.rollback()
    for table in (feedback, result, invitation):
        table.drop(db.engine)


def seed_feedback(tables, *, day=0, revision=1, **changes):
    from uuid import uuid4

    values = dict(
        id=str(uuid4()),
        thread_id="00000000-0000-4000-8000-000000000003",
        revision=revision,
        program_id=7,
        invitation_id="f339c308-9522-4c1f-ab1c-bcd21373bde0",
        claim_id=1,
        recipient_user_id=2,
        player_api_id=-42,
        author_user_id=1,
        video_match_id=99,
        title="PRIVATE_TITLE",
        body="PRIVATE_FEEDBACK_BODY",
        observation_refs=[{"label": "PRIVATE_REF", "timestamp_s": 9}],
        client_request_id=str(uuid4()),
        request_hash="PRIVATE_HASH",
        published_at=START + timedelta(days=day),
        acknowledged_at=START + timedelta(days=day, hours=1),
        withdrawn_at=None,
        audit_expires_at=None,
    )
    values.update(changes)
    db.session.execute(tables["feedback"].insert().values(**values))
    db.session.commit()
    return values


def observe_ref(register, row, *, person="p1", kind="self_operated_action", record_type="player_feedback", when=None):
    register["observations"].append(
        dict(
            id=f"o{len(register['observations'])}",
            person_key=person,
            kind=kind,
            occurred_at=(when or row["published_at"]).isoformat() + "Z",
            record_type=record_type,
            record_id=row["id"],
            evidence_ref="review-01",
        )
    )


def seed_result(tables, line, **changes):
    from uuid import uuid4

    import sqlalchemy as sa

    values = dict(
        id=str(uuid4()),
        program_id=7,
        client_request_id=str(uuid4()),
        create_request_hash="PRIVATE_HASH",
        version=1,
        match_date=line.match_date,
        season=2026,
        opponent="PRIVATE_OPPONENT",
        opponent_key="private",
        competition="PRIVATE_COMPETITION",
        home_away="home",
        result_for=2,
        result_against=1,
        video_match_id=99,
        created_by_user_id=1,
        updated_by_user_id=1,
        created_at=line.created_at,
        updated_at=line.created_at,
        deleted_at=None,
    )
    values.update(changes)
    db.session.execute(tables["result"].insert().values(**values))
    db.session.execute(
        sa.text("UPDATE player_match_entries SET club_result_id=:result WHERE id=:entry"),
        {"result": values["id"], "entry": line.id},
    )
    db.session.commit()
    return values


def test_future_observations_with_absent_tables_are_explicit_gaps(client, register):
    row = {"id": "00000000-0000-4000-8000-000000000001", "published_at": START}
    observe_ref(register, row)
    observe_ref(register, row, record_type="club_result")
    result = report(client, register)
    assert not any(result["capabilities"].values())
    assert {"feedback_unavailable", "stable_results_unavailable"} <= set(result["participants"][0]["missing"])
    assert "accepted_relationship" in result["participants"][1]["missing"]
    assert result["summary"]["qualifying_people"] == 0
    assert result["cross_person_outcomes"] == []


@pytest.mark.parametrize(
    "table_name,column",
    [
        ("feedback", "id"),
        ("feedback", "thread_id"),
        ("feedback", "revision"),
        ("feedback", "program_id"),
        ("feedback", "invitation_id"),
        ("feedback", "claim_id"),
        ("feedback", "recipient_user_id"),
        ("feedback", "player_api_id"),
        ("feedback", "author_user_id"),
        ("feedback", "published_at"),
        ("feedback", "acknowledged_at"),
        ("feedback", "withdrawn_at"),
        ("feedback", "audit_expires_at"),
        ("result", "id"),
        ("result", "program_id"),
        ("result", "version"),
        ("result", "created_by_user_id"),
        ("result", "created_at"),
        ("result", "deleted_at"),
    ],
)
def test_each_future_required_column_is_guarded(client, register, table_name, column):
    import sqlalchemy as sa

    invitation = invitation_table()
    factory = feedback_table if table_name == "feedback" else result_table
    table = factory(omit=column)
    if table_name == "result":
        db.session.execute(sa.text("ALTER TABLE player_match_entries ADD COLUMN club_result_id VARCHAR(36)"))
        db.session.commit()
    try:
        record_type, capability = (
            ("player_feedback", "feedback") if table_name == "feedback" else ("club_result", "stable_results")
        )
        observe_ref(
            register, {"id": "00000000-0000-4000-8000-000000000001", "published_at": START}, record_type=record_type
        )
        result = report(client, register)
        assert result["capabilities"][capability] is False
        assert f"{capability}_unavailable" in result["participants"][0]["missing"]
    finally:
        db.session.rollback()
        table.drop(db.engine)
        invitation.drop(db.engine)


def test_p4_header_without_child_link_column_is_a_capability_gap(client, register):
    table = result_table()
    try:
        observe_ref(
            register, {"id": "00000000-0000-4000-8000-000000000001", "published_at": START}, record_type="club_result"
        )
        assert report(client, register)["capabilities"]["stable_results"] is False
    finally:
        db.session.rollback()
        table.drop(db.engine)


def test_feedback_revisions_acknowledgments_and_repeat_counts(client, register, future_schema):
    first = seed_feedback(future_schema)
    second = seed_feedback(future_schema, day=7, revision=2)
    observe_ref(register, first)
    observe_ref(register, second)
    observe_ref(register, second)  # Duplicate HTTP/operator reporting cannot mint another revision outcome.
    result = report(client, register)
    assert all(result["capabilities"].values())
    assert result["summary"]["by_role"] == {"staff": 1, "player": 1, "scout": 0, "supporter": 0}
    assert result["summary"]["repeat_staff"] == result["summary"]["repeat_players"] == 1
    assert [p["action_dates"] for p in result["participants"][:2]] == [["2026-09-05", "2026-09-12"]] * 2
    assert {e["record_id"] for e in result["cross_person_outcomes"]} == {first["id"], second["id"]}
    assert len(result["cross_person_outcomes"]) == 2
    import json

    assert "PRIVATE_" not in json.dumps(result)
    assert "video_match_id" not in json.dumps(result)
    assert "recipient_user_id" not in json.dumps(result)
    assert "claim_id" not in json.dumps(result)
    assert all(
        set(e) == {"kind", "record_type", "record_id", "occurred_at", "basis"}
        for p in result["participants"]
        for e in p["evidence"]
    )
    repeated = report(client, register)
    assert {k: v for k, v in result.items() if k != "generated_at"} == {
        k: v for k, v in repeated.items() if k != "generated_at"
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"claim_id": 999},
        {"recipient_user_id": 3},
        {"player_api_id": -43},
        {"program_id": 8},
        {"invitation_id": "00000000-0000-4000-8000-000000000099"},
        {"withdrawn_at": START},
        {"audit_expires_at": START + timedelta(days=30)},
        {"author_user_id": 5},
        {"published_at": START - timedelta(hours=1)},
    ],
)
def test_feedback_pinned_identity_and_closed_access_never_qualify(client, register, future_schema, changes):
    row = seed_feedback(future_schema, **changes)
    observe_ref(register, row, when=START)
    result = report(client, register)
    assert result["summary"]["qualifying_people"] == 0
    assert result["cross_person_outcomes"] == []


def test_unregistered_admin_feedback_author_cannot_qualify_player(client, register, future_schema, monkeypatch):
    seed_feedback(future_schema, author_user_id=6)
    assert report(client, register)["summary"]["by_role"]["player"] == 1
    monkeypatch.setenv("ADMIN_EMAILS", "PRIVATE6@EXAMPLE.TEST")
    result = report(client, register)
    assert result["summary"]["by_role"]["player"] == 0
    assert result["cross_person_outcomes"] == []


def test_new_claim_cannot_inherit_old_feedback(client, register, future_schema):
    row = seed_feedback(future_schema)
    observe_ref(register, row)
    db.session.get(PlayerProfileClaim, 1).status = "revoked"
    db.session.add(
        PlayerProfileClaim(
            id=2,
            user_account_id=3,
            local_player_id=42,
            relationship_type="player",
            status="approved",
            reviewed_at=START,
        )
    )
    db.session.execute(future_schema["invitation"].update().values(claim_id=2, recipient_user_id=3))
    db.session.commit()
    assert report(client, register)["summary"]["qualifying_people"] == 0


def test_old_revision_ack_survives_new_unacknowledged_revision(client, register, future_schema):
    first = seed_feedback(future_schema)
    seed_feedback(future_schema, day=7, revision=2, acknowledged_at=None)
    result = report(client, register)
    player = result["participants"][1]
    assert [e["record_id"] for e in player["evidence"]] == [first["id"]]
    assert not player["repeat_dates"]
    assert len(result["cross_person_outcomes"]) == 1


def test_withdrawn_thread_closes_all_revision_counts(client, register, future_schema):
    first = seed_feedback(future_schema)
    second = seed_feedback(future_schema, day=7, revision=2, withdrawn_at=START + timedelta(days=8))
    observe_ref(register, first)
    observe_ref(register, second)
    assert report(client, register)["summary"]["qualifying_people"] == 0


def test_feedback_author_erasure_and_grant_revocation(client, register, future_schema):
    row = seed_feedback(future_schema)
    observe_ref(register, row)
    # Another strict manager preserves the relationship after the author's loss of grant.
    db.session.add(
        ClubProgramClaim(id=2, program_id=7, user_account_id=6, relationship_type="club_official", status="approved")
    )
    db.session.flush()
    db.session.add(
        ClubProgramManager(program_id=7, user_account_id=6, source_claim_id=2, status="active", granted_by="fixture")
    )
    ClubProgramManager.query.filter_by(user_account_id=1).one().status = "revoked"
    db.session.commit()
    result = report(client, register)
    assert result["summary"]["by_role"]["staff"] == 0
    assert result["summary"]["by_role"]["player"] == 1
    db.session.execute(future_schema["feedback"].update().values(author_user_id=None))
    db.session.commit()
    result = report(client, register)
    assert result["summary"]["by_role"]["player"] == 1
    assert not result["cross_person_outcomes"]


def test_stable_result_identity_prevents_correction_or_lineup_repeat(client, register, future_schema):
    import sqlalchemy as sa

    first = action()
    header = seed_result(future_schema, first, version=2, updated_at=START + timedelta(days=8))
    second = action(day=8)
    db.session.execute(
        sa.text("UPDATE player_match_entries SET club_result_id=:result WHERE id=:entry"),
        {"result": header["id"], "entry": second.id},
    )
    db.session.commit()
    observe(register, first)
    observe(register, second)
    observe_ref(register, header, record_type="club_result", when=START)
    observe_ref(register, header, record_type="club_result", when=START + timedelta(days=8))
    result = report(client, register)
    assert result["capabilities"]["stable_results"] is True
    staff = result["participants"][0]
    assert len(staff["evidence"]) == 1
    assert staff["evidence"][0]["record_type"] == "club_result"
    assert staff["evidence"][0]["record_id"] == header["id"]
    assert staff["action_dates"] == ["2026-09-05"]
    assert staff["repeat_dates"] == []


@pytest.mark.parametrize(
    "changes",
    [{"deleted_at": START}, {"program_id": 8}, {"created_by_user_id": 5}, {"created_by_user_id": None}, {"version": 0}],
)
def test_stable_result_deleted_foreign_excluded_headers_do_not_qualify(client, register, future_schema, changes):
    line = action()
    header = seed_result(future_schema, line, **changes)
    observe(register, line)
    observe_ref(register, header, record_type="club_result", when=START)
    assert report(client, register)["summary"]["qualifying_people"] == 0


def test_linked_line_with_partial_header_cannot_fall_back_to_legacy(client, register):
    import sqlalchemy as sa

    table = result_table(omit="deleted_at")
    try:
        db.session.execute(sa.text("ALTER TABLE player_match_entries ADD COLUMN club_result_id VARCHAR(36)"))
        db.session.commit()
        line = action()
        db.session.execute(
            sa.text("UPDATE player_match_entries SET club_result_id=:result"),
            {"result": "00000000-0000-4000-8000-000000000001"},
        )
        db.session.commit()
        observe(register, line)
        result = report(client, register)
        assert result["summary"]["qualifying_people"] == 0
        assert result["capabilities"]["stable_results"] is False
    finally:
        db.session.rollback()
        table.drop(db.engine)


def test_installed_future_schema_unknown_references_still_rejected(client, register, future_schema):
    observe_ref(register, {"id": "00000000-0000-4000-8000-000000000001", "published_at": START})
    assert report(client, register, 422) == {"error": "cohort_reference_invalid"}


@pytest.mark.parametrize(
    "package,action", [("P2", "invite_accepted"), ("P3", "feedback_acknowledged"), ("P4", "result_corrected")]
)
def test_other_pilot_package_telemetry_is_allowlisted_and_anonymous(client, package, action):
    response = client.post(
        "/api/events",
        json={
            "events": [
                {
                    "name": "pilot_ui",
                    "path": "PRIVATE_PATH",
                    "props": {"package": package, "action": action, "outcome": "success", "body": "PRIVATE_BODY"},
                }
            ]
        },
        headers=headers(),
    )
    assert response.status_code == 202 and response.get_json()["accepted"] == 1
    row = ProductEvent.query.one()
    assert row.props == {"package": package, "action": action, "outcome": "success"}
    assert row.path is row.user_email is row.referrer is row.session_id is None


def test_repeat_target_requires_one_staff_and_three_distinct_players(client, register, future_schema):
    from uuid import uuid4

    for actor, subject in [(3, -43), (4, -44)]:
        participant = register["participants"][actor - 1]
        participant["primary_role"] = "player"
        participant["player_api_ids"] = [subject]
        db.session.add(
            LocalPlayer(
                id=-subject,
                display_name=f"PRIVATE_{actor}",
                normalized_name=f"private_{actor}",
                birth_date=date(2000, 1, 1),
                status="approved",
                api_player_id=subject,
            )
        )
        db.session.flush()
        db.session.add(
            PlayerProfileClaim(
                id=actor,
                user_account_id=actor,
                local_player_id=-subject,
                relationship_type="player",
                status="approved",
                reviewed_at=START - timedelta(days=1),
            )
        )
        db.session.commit()
        seed_invitation(
            future_schema["invitation"], id=str(uuid4()), recipient_user_id=actor, player_api_id=subject, claim_id=actor
        )
    for invitation in db.session.execute(future_schema["invitation"].select()).mappings():
        thread = str(uuid4())
        for day, revision in [(0, 1), (7, 2)]:
            row = seed_feedback(
                future_schema,
                day=day,
                revision=revision,
                thread_id=thread,
                invitation_id=invitation["id"],
                claim_id=invitation["claim_id"],
                recipient_user_id=invitation["recipient_user_id"],
                player_api_id=invitation["player_api_id"],
            )
            observe_ref(register, row)
    result = report(client, register)
    assert result["summary"]["qualifying_people"] == 4
    assert result["summary"]["repeat_people"] == 4
    assert result["summary"]["repeat_target_met"] is True
    assert result["summary"]["repeat_staff"] == 1 and result["summary"]["repeat_players"] == 3
    assert len(result["cross_person_outcomes"]) == 6


@pytest.mark.parametrize("change", ["claim", "invitation", "minor", "suppressed", "program", "excluded"])
def test_feedback_current_prerequisites_reduce_snapshot_counts(client, register, future_schema, change):
    row = seed_feedback(future_schema)
    observe_ref(register, row)
    assert report(client, register)["summary"]["qualifying_people"] == 2
    if change == "claim":
        db.session.get(PlayerProfileClaim, 1).status = "revoked"
    elif change == "invitation":
        db.session.execute(future_schema["invitation"].update().values(status="revoked", revoked_at=START))
    elif change == "minor":
        db.session.get(LocalPlayer, 42).birth_date = date(2020, 1, 1)
    elif change == "suppressed":
        from src.models.player_suppression import PlayerSuppression

        db.session.add(
            PlayerSuppression(
                local_player_id=42,
                reason_code="player_request",
                requester_role="player",
                requester_contact="private@example.test",
                request_statement="PRIVATE",
                status="active",
            )
        )
    elif change == "program":
        db.session.get(ClubProgram, 7).emergency_hidden = True
    else:
        register["participants"][1]["excluded"] = True
    db.session.commit()
    result = report(client, register)
    assert result["summary"]["qualifying_people"] == 0
    assert result["cross_person_outcomes"] == []


@pytest.mark.parametrize("actor,day", [(5, 0), (1, 8)])
def test_stable_header_cannot_adopt_excluded_or_later_subject_action(client, register, future_schema, actor, day):
    line = action(day=day, actor=actor)
    header = seed_result(future_schema, line, created_by_user_id=1, created_at=START)
    observe_ref(register, header, record_type="club_result", when=START)
    assert report(client, register)["summary"]["qualifying_people"] == 0


@pytest.mark.parametrize("source,program", [("club", 7), ("club", 8), ("self", 7), ("self", 8)])
def test_supporter_update_must_match_registered_program(client, register, source, program):
    db.session.add(PlayerFan(user_account_id=4, player_api_id=-42, created_at=START - timedelta(days=1)))
    db.session.commit()
    row = action(actor=1 if source == "club" else 2, source=source, program=program)
    observe(register, row, person="p4", kind="supporter_update_view", when=START + timedelta(hours=1))
    assert report(client, register)["summary"]["by_role"]["supporter"] == int(program == 7)
