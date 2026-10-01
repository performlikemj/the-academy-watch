"""Reverse RB2's defect probes into route-level regressions; synthetic identities only."""

# ruff: noqa: F811
from datetime import date, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.models.funding import ClubProgram, ClubProgramManager, ClubSquad, FundingLeague
from src.models.league import UserAccount, db
from src.models.opportunities import ApplicationEvent, ApplicationNote, ClubOpportunity, OpportunityApplication, now
from src.models.p2_foundation import NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.services import opportunities as service
from src.services.account import _SchemaView
from src.services.opportunities_account import export_opportunities, purge_retained
from test_opportunities import _headers, apply, client, club_app, create, details, env, move  # noqa: F401


def invalidate(env, app, cause):
    who = env["people"]["adult"]
    local = db.session.get(LocalPlayer, who["local"])
    if cause == "minor":
        local.birth_date, local.birth_year = date(now().year - 15, 1, 1), now().year - 15
    elif cause == "unknown":
        local.birth_date = local.birth_year = None
    elif cause == "revoked":
        db.session.get(PlayerProfileClaim, who["claim"]).status = "revoked"
    elif cause == "suppressed":
        db.session.add(
            PlayerSuppression(
                local_player_id=local.id,
                status="active",
                reason_code="admin_other",
                requester_role="other",
                requester_contact="test@example.test",
                request_statement="Test suppression",
            )
        )
    elif cause == "held":
        local.origin_program_id = env["other"]
        db.session.get(ClubProgram, env["other"]).emergency_hidden = True
    db.session.commit()


@pytest.mark.parametrize("cause", ["minor", "unknown", "revoked", "suppressed", "held"])
@pytest.mark.parametrize("read", ["board", "detail", "postings"])
def test_ineligible_subject_is_absent_and_system_closes_releases_and_purges(client, env, cause, read):
    row = create(client, env)
    app = apply(client, env, row, current_club="Private FC").get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    app = move(client, env, app, "invited", trial_at=row["starts_at"], trial_venue="Private trial venue").get_json()[
        "application"
    ]
    assert (
        client.post(
            f"/api/club/{env['pid']}/applications/{app['id']}/notes",
            headers=_headers("a"),
            json={"body": "private child notes"},
        ).status_code
        == 201
    )
    invalidate(env, app, cause)
    # Every staff mutation including rejection is blocked before any club read has reconciled it.
    assert (
        client.post(
            f"/api/club/{env['pid']}/applications/{app['id']}/notes", headers=_headers("a"), json={"body": "more"}
        ).status_code
        == 403
    )
    assert move(client, env, app, "rejected").status_code == 403
    if read == "board":
        response = client.get(f"/api/club/{env['pid']}/opportunities/{row['id']}/applications", headers=_headers("a"))
        assert response.status_code == 200 and response.get_json()["applications"] == []
    elif read == "detail":
        response = client.get(f"/api/club/{env['pid']}/applications/{app['id']}", headers=_headers("a"))
        assert response.status_code == 404 and response.get_json() == {"error": "Not found"}
    else:
        response = client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a"))
        assert response.get_json()["opportunities"][0]["places_left"] == 1
    assert "Private FC" not in str(response.get_json()) and "private child notes" not in str(response.get_json())
    stored = db.session.get(OpportunityApplication, app["id"])
    assert stored.status == "rejected" and stored.reservation_state == "released" and stored.trial_at is None
    assert stored.retention_expires_at <= now() + timedelta(days=7)
    assert (
        ApplicationEvent.query.filter_by(application_id=app["id"], reason_code="profile_unavailable")
        .one()
        .actor_user_id
        is None
    )
    mine = client.get(f"/api/me/applications/{app['id']}", headers=env["people"]["adult"]["headers"]).get_json()[
        "application"
    ]
    assert mine["reservation_state"] == "released" and mine["trial_at"] is None
    assert purge_retained(at=now() + timedelta(days=8))["applications"] == 1
    db.session.commit()
    assert not db.session.get(OpportunityApplication, app["id"])
    assert ApplicationNote.query.count() == 0 and NotificationOutbox.query.count() == 0


def test_retention_rechecks_eligibility_while_flags_off_without_any_http_read(client, env, monkeypatch):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    invalidate(env, app, "unknown")
    monkeypatch.setenv("OPPORTUNITIES_ENABLED", "false")
    purge_retained(at=now() + timedelta(days=2))
    db.session.commit()
    stored = db.session.get(OpportunityApplication, app["id"])
    assert stored.status == "rejected" and stored.retention_expires_at <= now() + timedelta(days=9)


@pytest.mark.parametrize(
    "zone", ["Factory", "posixrules", "localtime", "posix/Europe/London", "right/Europe/London", "Etc/GMT+1", "EST"]
)
def test_nonbrowser_nongeographic_timezones_are_bad_requests(client, env, zone):
    response = client.post(f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(timezone=zone))
    assert response.status_code == 400 and response.get_json()["error"] == "invalid_timezone"
    assert ClubOpportunity.query.count() == 0


@pytest.mark.parametrize(
    "zone,instant,expected",
    [
        ("Europe/London", "2026-10-25T00:30:00Z", "01:30 BST (Europe/London)"),
        ("Europe/London", "2026-10-25T01:30:00Z", "01:30 GMT (Europe/London)"),
        ("America/Los_Angeles", "2026-11-01T08:30:00Z", "01:30 PDT (America/Los_Angeles)"),
        ("America/Los_Angeles", "2026-11-01T09:30:00Z", "01:30 PST (America/Los_Angeles)"),
    ],
)
def test_notification_times_and_dtos_use_opportunity_zone_across_dst(client, env, zone, instant, expected):
    row = create(client, env, timezone=zone)
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    app = move(client, env, app, "invited", trial_at=instant, trial_venue="Ground").get_json()["application"]
    assert app["timezone"] == zone
    intent = (
        NotificationOutbox.query.filter_by(recipient_user_id=env["people"]["adult"]["user"])
        .filter(NotificationOutbox.payload["version"].as_integer() == app["version"])
        .one()
    )
    for user_id in (env["actor"], env["people"]["adult"]["user"]):
        rendered = service.notification_render(intent, db.session.get(UserAccount, user_id))
        assert expected in rendered["text"] and expected in rendered["html"]
    board = client.get(
        f"/api/club/{env['pid']}/opportunities/{row['id']}/applications", headers=_headers("a")
    ).get_json()["applications"]
    assert board[0]["timezone"] == zone


@pytest.mark.parametrize("field", ["closes_at", "starts_at", "ends_at"])
@pytest.mark.parametrize("operation", ["create", "edit"])
def test_advertised_dates_cannot_strand_applications_beyond_hard_cap(client, env, field, operation):
    changes = {field: service.iso(now() + timedelta(days=200))}
    if operation == "create":
        response = client.post(f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(**changes))
    else:
        row = create(client, env)
        response = client.patch(
            f"/api/club/{env['pid']}/opportunities/{row['id']}",
            headers=_headers("a"),
            json={"expected_version": 1, **changes},
        )
    assert response.status_code == 422


def test_latest_allowed_event_lives_through_trial_plus_90d_and_early_close(client, env):
    row = create(
        client,
        env,
        starts_at=service.iso(now() + timedelta(days=89)),
        ends_at=service.iso(now() + timedelta(days=89, hours=2)),
    )
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    assert (
        move(
            client, env, app, "invited", trial_at=service.iso(now() + timedelta(days=91)), trial_venue="Ground"
        ).status_code
        == 422
    )
    app = move(client, env, app, "invited", trial_at=row["starts_at"], trial_venue="Ground").get_json()["application"]
    confirmed = client.post(
        f"/api/me/applications/{app['id']}/trial-response",
        headers=env["people"]["adult"]["headers"],
        json={"expected_version": app["version"], "response": "accept"},
    )
    assert confirmed.status_code == 200
    assert (
        client.post(
            f"/api/club/{env['pid']}/opportunities/{row['id']}/close",
            headers=_headers("a"),
            json={"expected_version": 1},
        ).status_code
        == 200
    )
    stored = db.session.get(OpportunityApplication, app["id"])
    assert (
        stored.trial_at + timedelta(days=90) <= stored.retention_expires_at <= stored.submitted_at + timedelta(days=180)
    )
    assert purge_retained(at=stored.trial_at - timedelta(seconds=1))["applications"] == 0
    db.session.commit()
    assert db.session.get(OpportunityApplication, app["id"])


@pytest.mark.parametrize("field", ["closes_at", "starts_at", "ends_at", "trial_at"])
def test_overflow_timestamp_returns_400(client, env, field):
    overflow = "9999-12-31T23:59:59-23:00"
    if field == "trial_at":
        row = create(client, env)
        app = apply(client, env, row).get_json()["application"]
        app = move(client, env, app, "shortlisted").get_json()["application"]
        response = move(client, env, app, "invited", trial_at=overflow, trial_venue="Ground")
    else:
        response = client.post(
            f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(**{field: overflow})
        )
    assert response.status_code == 400


@pytest.mark.parametrize("field", ["position", "current_club"])
def test_nul_application_text_is_rejected_before_db_write(client, env, field):
    row = create(client, env)
    assert apply(client, env, row, **{field: "Mid\x00field"}).status_code == 400
    assert OpportunityApplication.query.count() == NotificationOutbox.query.count() == 0


def test_export_redacts_staff_actor_and_reason_codes_but_keeps_authored_notes(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    move(client, env, app, "rejected")
    client.post(
        f"/api/club/{env['pid']}/applications/{app['id']}/notes", headers=_headers("a"), json={"body": "Private review"}
    )
    exported = export_opportunities(db.session.get(UserAccount, env["people"]["adult"]["user"]), _SchemaView())[
        "recruiting"
    ]
    for event in exported["application_events"]:
        assert "reason_code" not in event
        assert "actor_user_id" not in event or event["actor_user_id"] == env["people"]["adult"]["user"]
    assert exported["authored_application_notes"] == [] and "Private review" not in str(exported)
    manager = export_opportunities(db.session.get(UserAccount, env["actor"]), _SchemaView())["recruiting"]
    assert manager["authored_application_notes"][0]["body"] == "Private review"


@pytest.mark.parametrize("closed", ["manual", "deadline"])
def test_replay_after_close_or_deadline_returns_original_without_new_intents(client, env, closed):
    row = create(client, env)
    key = str(uuid4())
    app = apply(client, env, row, client_request_id=key).get_json()["application"]
    if closed == "manual":
        assert (
            client.post(
                f"/api/club/{env['pid']}/opportunities/{row['id']}/close",
                headers=_headers("a"),
                json={"expected_version": 1},
            ).status_code
            == 200
        )
    else:
        db.session.get(ClubOpportunity, row["id"]).closes_at = now() - timedelta(seconds=1)
        db.session.commit()
    count = NotificationOutbox.query.count()
    replay = apply(client, env, row, client_request_id=key)
    assert replay.status_code == 200 and replay.get_json()["application"]["id"] == app["id"]
    assert NotificationOutbox.query.count() == count
    assert apply(client, env, row, client_request_id=key, position="changed").status_code == 409
    assert apply(client, env, row, "adult2").status_code == 404


def test_cancellation_with_applications_off_never_enqueues(client, env, monkeypatch):
    row = create(client, env)
    apply(client, env, row)
    count = NotificationOutbox.query.count()
    monkeypatch.setenv("APPLICATIONS_ENABLED", "false")
    assert (
        client.post(
            f"/api/club/{env['pid']}/opportunities/{row['id']}/close",
            headers=_headers("a"),
            json={"expected_version": 1, "status": "cancelled"},
        ).status_code
        == 200
    )
    assert NotificationOutbox.query.count() == count
    assert OpportunityApplication.query.one().reservation_state == "released"


def test_reclosing_never_resets_version_or_deletion_clock(client, env):
    row = create(client, env)
    assert (
        client.post(
            f"/api/club/{env['pid']}/opportunities/{row['id']}/close",
            headers=_headers("a"),
            json={"expected_version": 1},
        ).status_code
        == 200
    )
    stored = db.session.get(ClubOpportunity, row["id"])
    clock = stored.closed_at
    response = client.post(
        f"/api/club/{env['pid']}/opportunities/{row['id']}/close", headers=_headers("a"), json={"expected_version": 2}
    )
    assert response.status_code == 422
    assert db.session.get(ClubOpportunity, row["id"]).closed_at == clock and stored.version == 2
    assert purge_retained(at=clock + timedelta(days=91))["opportunities"] == 1


@pytest.mark.parametrize(
    "field,value", [("title", "changed"), ("description", "changed"), ("instructions", "changed"), ("capacity", 2)]
)
def test_all_advertised_terms_freeze_after_first_application(client, env, field, value):
    row = create(client, env)
    apply(client, env, row)
    assert (
        client.patch(
            f"/api/club/{env['pid']}/opportunities/{row['id']}",
            headers=_headers("a"),
            json={"expected_version": 1, field: value},
        ).status_code
        == 409
    )


def test_squad_deletion_cannot_change_retained_advertised_terms(client, env):
    squad = ClubSquad(program_id=env["pid"], name="Advertised squad", kind="other")
    db.session.add(squad)
    db.session.commit()
    row = create(client, env, squad_id=squad.id)
    apply(client, env, row)
    assert client.delete(f"/api/club/{env['pid']}/squads/{squad.id}", headers=_headers("a")).status_code == 409
    assert db.session.get(ClubOpportunity, row["id"]).squad_id == squad.id


def test_pipeline_paginated_query_count_is_constant_and_history_is_detail_only(client, env):
    row = create(client, env)
    first = apply(client, env, row).get_json()["application"]

    def read():
        statements = []

        def record(*args):
            statements.append(args[2])

        sa.event.listen(db.engine, "before_cursor_execute", record)
        try:
            response = client.get(
                f"/api/club/{env['pid']}/opportunities/{row['id']}/applications", headers=_headers("a")
            )
            return response, sum(sql.startswith("SELECT") for sql in statements)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", record)

    single, one_count = read()
    assert "notes" not in single.get_json()["applications"][0]
    for i in range(31):
        user = UserAccount(
            email=f"batch-{i}@example.test", display_name=f"Test batch {i}", display_name_lower=f"test batch {i}"
        )
        local = LocalPlayer(
            display_name="Test batch",
            status="approved",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            provenance="user",
        )
        db.session.add_all([user, local])
        db.session.flush()
        local.api_player_id = -local.id
        claim = PlayerProfileClaim(
            local_player_id=local.id, user_account_id=user.id, relationship_type="player", status="approved"
        )
        db.session.add(claim)
        db.session.flush()
        service.submit(
            row["id"],
            user.id,
            dict(claim_id=claim.id, position="Midfielder", contact_consent=True, client_request_id=str(uuid4())),
        )
    db.session.commit()
    many, many_count = read()
    assert len(many.get_json()["applications"]) == 30 and many.get_json()["has_more"] is True
    assert many_count <= one_count + 1 and many_count < 25
    assert (
        len(
            client.get(
                f"/api/club/{env['pid']}/opportunities/{row['id']}/applications?page=2", headers=_headers("a")
            ).get_json()["applications"]
        )
        == 2
    )
    detail = client.get(f"/api/club/{env['pid']}/applications/{first['id']}", headers=_headers("a")).get_json()[
        "application"
    ]
    assert "notes" in detail and "events" in detail


def test_features_is_404_when_dark_and_public_counts_never_reveal_reservations(client, env, monkeypatch):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    before = client.get(f"/api/opportunities/{row['id']}").get_json()
    move(client, env, app, "invited", trial_at=row["starts_at"], trial_venue="Ground")
    assert client.get(f"/api/opportunities/{row['id']}").get_json() == before
    assert "places_left" not in str(client.get("/api/opportunities").get_json())
    monkeypatch.setenv("OPPORTUNITIES_ENABLED", "false")
    monkeypatch.setenv("APPLICATIONS_ENABLED", "false")
    assert client.get("/api/opportunities/features").status_code == 404


def test_public_listing_matches_amended_directory_standing_including_console_league(client, env):
    row = create(client, env)
    program = db.session.get(ClubProgram, env["pid"])
    league = db.session.get(FundingLeague, program.funding_league_id)
    league.registry_status = "proposed"
    db.session.commit()
    assert client.get(f"/api/opportunities/{row['id']}").status_code == 404
    assert service.open_opportunity_counts([env["pid"]]) == {}
    league.name, league.country, league.region = "Console (unlisted)", "Global", "Unlisted"
    db.session.commit()
    assert client.get(f"/api/opportunities/{row['id']}").status_code == 200
    assert service.open_opportunity_counts([env["pid"]]) == {env["pid"]: 1}
    ClubProgramManager.query.filter_by(program_id=env["pid"]).update({"status": "revoked"})
    db.session.commit()
    assert client.get("/api/opportunities").get_json()["opportunities"] == []
    assert client.get(f"/api/opportunities/{row['id']}").status_code == 404


@pytest.mark.parametrize("club_app", [True], indirect=True)
@pytest.mark.parametrize("route", ["features", "claims", "mine", "my_detail", "board", "detail"])
def test_read_rails_are_rate_limited(client, env, route, club_app, monkeypatch):
    from src.extensions import limiter

    club_app.config["RATELIMIT_ENABLED"] = True
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.init_app(club_app)
    limiter.reset()
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    if route == "features":
        path, headers = "/api/opportunities/features", {}
    elif route == "claims":
        path, headers = "/api/me/application-claims", env["people"]["adult"]["headers"]
    elif route == "mine":
        path, headers = "/api/me/applications", env["people"]["adult"]["headers"]
    elif route == "my_detail":
        path, headers = f"/api/me/applications/{app['id']}", env["people"]["adult"]["headers"]
    elif route == "board":
        path, headers = f"/api/club/{env['pid']}/opportunities/{row['id']}/applications", _headers("a")
    else:
        path, headers = f"/api/club/{env['pid']}/applications/{app['id']}", _headers("a")
    statuses = [client.get(path, headers=headers).status_code for _ in range(61)]
    assert statuses[:60] == [200] * 60 and statuses[60] == 429
