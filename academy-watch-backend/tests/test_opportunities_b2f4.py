"""RB2V2: production legacy zones, hold deferral and dark-directory contract."""

# ruff: noqa: F811
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from src.models.funding import ClubProgram
from src.models.league import db
from src.models.opportunities import OpportunityApplication
from src.models.p2_foundation import NotificationOutbox
from src.services import opportunities as service
from src.services.notification_outbox import MAX_ATTEMPTS, dispatch_due
from test_opportunities import _headers, apply, client, club_app, create, env, move  # noqa: F401
from test_opportunities_rb2 import invalidate


@pytest.mark.parametrize("alias,canonical", sorted(service.TIMEZONE_ALIASES.items()))
def test_all_committed_aliases_save_and_format_without_runtime_legacy_links(client, env, monkeypatch, alias, canonical):
    def production_zone(zone):
        assert zone not in service.TIMEZONE_ALIASES, "Production image need not install backward links"
        return ZoneInfo(zone)

    monkeypatch.setattr(service, "ZoneInfo", production_zone)
    row = create(client, env, timezone=alias)
    assert row["timezone"] == canonical
    assert service.canonical_timezone(alias) == canonical
    assert service.format_time(service.timestamp(row["starts_at"], "start"), alias).endswith(f"({canonical})")


def test_every_browser_device_default_formats_without_legacy_runtime_links(monkeypatch):
    data = Path(service.__file__).parents[1] / "data"
    snapshot = json.loads((data / "opportunity_timezone_browser_snapshot.json").read_text())
    for zone in snapshot:
        assert zone in service.TIMEZONES
        canonical = service.canonical_timezone(zone)
        assert canonical not in service.TIMEZONE_ALIASES
        assert service.format_time(datetime(2026, 10, 10, 17), zone).endswith(f"({canonical})")


def test_dark_counts_are_none_and_execute_zero_sql(club_app, monkeypatch):
    monkeypatch.setenv("OPPORTUNITIES_ENABLED", "false")
    queries = []

    def record(*args):
        queries.append(args[2])

    sa.event.listen(db.engine, "before_cursor_execute", record)
    try:
        assert service.open_opportunity_counts([1, 2]) is None
        assert service.open_opportunity_counts([]) is None
        assert queries == []
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record)


def invitation(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    app = move(client, env, app, "invited", trial_at=row["starts_at"], trial_venue="Ground").get_json()["application"]
    return row, app


def test_hold_confirmation_and_reserved_reason_are_neutral_then_restore(client, env):
    row, app = invitation(client, env)
    invalidate(env, app, "held")
    result = client.post(
        f"/api/me/applications/{app['id']}/trial-response",
        headers=env["people"]["adult"]["headers"],
        json={"expected_version": app["version"], "response": "accept"},
    )
    assert result.status_code == 403 and result.get_json() == {"error": "temporarily_unavailable"}
    postings = client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a")).get_json()["opportunities"]
    assert postings[0]["places_left"] == 0
    assert postings[0]["temporarily_unavailable_reservations"] == 1
    assert "Test Player adult" not in json.dumps(postings)
    assert app["id"] not in json.dumps(postings)
    assert (
        service.opportunity_dict(service.opportunity(row["id"]), private=True)["temporarily_unavailable_reservations"]
        == 1
    )
    db.session.commit()
    db.session.get(ClubProgram, env["other"]).emergency_hidden = False
    db.session.commit()
    result = client.post(
        f"/api/me/applications/{app['id']}/trial-response",
        headers=env["people"]["adult"]["headers"],
        json={"expected_version": app["version"], "response": "accept"},
    )
    assert result.status_code == 200 and result.get_json()["application"]["reservation_state"] == "confirmed"
    assert (
        client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a")).get_json()["opportunities"][0][
            "temporarily_unavailable_reservations"
        ]
        == 0
    )


@pytest.mark.parametrize("hold", ["subject", "posting"])
def test_due_emails_survive_many_hold_cycles_and_send_after_lift(client, env, hold):
    _, app = invitation(client, env)
    if hold == "subject":
        invalidate(env, app, "held")
        held_program = env["other"]
    else:
        held_program = env["pid"]
        db.session.get(ClubProgram, held_program).emergency_hidden = True
        db.session.commit()
    sender = Mock(return_value=SimpleNamespace(success=True, provider="test", message_id="test"))
    at = datetime.now(UTC) + timedelta(seconds=1)
    # Superseded intents cancel; the latest invitation to both recipients defers indefinitely.
    for cycle in range(MAX_ATTEMPTS + 2):
        summary = dispatch_due(limit=100, now=at + timedelta(minutes=6 * cycle), send=sender)
        assert summary["deferred"] == 2 and summary["sent"] == summary["failed"] == summary["errors"] == 0
        intents = NotificationOutbox.query.filter(
            NotificationOutbox.payload["version"].as_integer() == app["version"]
        ).all()
        assert len(intents) == 2 and all(i.status == "retry" and i.attempts == 0 for i in intents)
        assert all(i.lease_token is None and i.lease_expires_at is None for i in intents)
    sender.assert_not_called()
    db.session.get(ClubProgram, held_program).emergency_hidden = False
    db.session.commit()
    summary = dispatch_due(limit=100, now=at + timedelta(hours=2), send=sender)
    assert summary["sent"] == 2 and sender.call_count == 2
    assert all(i.status == "sent" and i.attempts == 1 for i in intents)


@pytest.mark.parametrize("cause", ["revoked", "minor", "suppressed", "expired", "withdrawn"])
def test_deferred_email_rechecks_permanent_ineligibility_before_lift(client, env, cause):
    _, app = invitation(client, env)
    invalidate(env, app, "held")
    sender = Mock()
    at = datetime.now(UTC) + timedelta(seconds=1)
    assert dispatch_due(now=at, send=sender)["deferred"] == 2
    if cause in {"revoked", "minor", "suppressed"}:
        invalidate(env, app, cause)
    else:
        stored = db.session.get(OpportunityApplication, app["id"])
        if cause == "expired":
            stored.retention_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        else:
            stored.status, stored.version = "withdrawn", stored.version + 1
        db.session.commit()
    summary = dispatch_due(now=at + timedelta(minutes=6), send=sender)
    assert summary["cancelled"] == 2 and summary["deferred"] == 0
    sender.assert_not_called()
