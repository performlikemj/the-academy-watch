# ruff: noqa: F811
"""C1F9: real-route erasure gaps before and after the account FK lock."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date
from threading import local
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.auth import issue_user_token
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
from src.models.league import UserAccount, db
from src.models.player_feedback import PlayerFeedback
from src.models.showcase import LocalPlayer, PlayerProfileClaim, PlayerShowcaseProfile
from test_club_player_publication_postgres import pg  # noqa: F401
from test_contact_lock_matrix_postgres import setup_world


@pytest.mark.parametrize("flow", ["merge", "feedback_purge"])
def test_batch_revalidates_contacts_added_before_prefix_lock(pg, monkeypatch, flow):
    app, ids, tokens = setup_world(pg, monkeypatch, (), "ordinary")
    with app.app_context():
        if flow == "feedback_purge":
            # A UUID cursor isolates this page from matrix fixtures retained on
            # the same database, without changing the production purge query.
            db.session.add(
                PlayerFeedback(
                    id="ffffffff-ffff-4fff-8fff-ffffffffffff",
                    thread_id=str(uuid4()),
                    revision=1,
                    program_id=ids["program"],
                    invitation_id=ids["invitation"],
                    claim_id=ids["claim"],
                    recipient_user_id=ids["adult"],
                    player_api_id=-ids["local"],
                    author_user_id=ids["owner"],
                    request_hash="gap",
                    title="Gap feedback",
                    body="Synthetic",
                    client_request_id=str(uuid4()),
                    published_at=utcnow(),
                )
            )
            db.session.commit()
        engine = db.engine
        db.session.remove()
    role = local()
    created = []
    fired = False

    def create_contact():
        with app.test_client() as client:
            response = client.post(
                "/api/contact/requests",
                headers={"Authorization": "Bearer " + tokens["other_scout"]},
                json={"player_api_id": -ids["local"], "message": "Batch gap"},
            )
            assert response.status_code == 201, response.json
            created.append(response.json["contact_request"]["id"])

    def gap(conn, cursor, statement, parameters, context, executemany):
        nonlocal fired
        if (
            getattr(role, "active", False)
            and not fired
            and "FROM club_programs" in statement
            and "FOR UPDATE" in statement
        ):
            fired = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(create_contact).result(20)

    sa.event.listen(engine, "before_cursor_execute", gap)
    try:
        role.active = True
        with app.test_client() as client:
            headers = {"X-API-Key": "c1f7-admin", "Authorization": "Bearer " + tokens["admin"]}
            if flow == "merge":
                response = client.post(
                    f"/api/admin/local-players/{ids['local']}/link-api",
                    headers=headers,
                    json={"player_api_id": 900000000 + ids["local"]},
                )
            else:
                response = client.post(
                    "/api/admin/player-feedback/purge",
                    headers=headers,
                    json={"dry_run": False, "before": "ffffffff-ffff-4fff-8fff-fffffffffffe"},
                )
    finally:
        role.active = False
        sa.event.remove(engine, "before_cursor_execute", gap)
    assert fired and created
    assert response.status_code == 409, response.json
    with app.app_context():
        assert db.session.get(ContactRequest, created[0]).player_api_id == -ids["local"]
        assert db.session.get(PlayerProfileClaim, ids["claim"]).local_player_id == ids["local"]
        assert db.session.get(LocalPlayer, ids["local"]).api_player_id == -ids["local"]
        if flow == "feedback_purge":
            row = db.session.get(PlayerFeedback, "ffffffff-ffff-4fff-8fff-ffffffffffff")
            assert row is not None and row.audit_expires_at is None
            db.session.delete(row)
            db.session.commit()


@pytest.mark.parametrize("c1", [False, True])
@pytest.mark.parametrize("kind", ["claim", "contact", "invitation"])
def test_erasure_refreshes_scope_after_gap(pg, monkeypatch, c1, kind):
    app, ids, tokens = setup_world(pg, monkeypatch, (), "ordinary")
    from src.routes.club import club_bp

    app.register_blueprint(club_bp, url_prefix="/api")
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", str(c1).lower())
    monkeypatch.setenv("SHOWCASE_ENABLED", "true")
    monkeypatch.setenv("PLAYER_SHOWCASE_ENABLED", "true")
    role = "other_scout" if kind == "contact" else "club"
    uid = ids["other_scout"] if kind == "contact" else ids["owner"]
    with app.app_context():
        if kind == "invitation":
            suffix = uuid4().hex
            player = UserAccount(email=f"gap-{suffix}@example.test", display_name=suffix, display_name_lower=suffix)
            subject = LocalPlayer(
                display_name="Gap adult",
                provenance="user",
                status="approved",
                birth_date=date(2000, 1, 1),
                birth_year=2000,
            )
            db.session.add_all([player, subject])
            db.session.flush()
            subject.api_player_id = -subject.id
            db.session.add(
                PlayerProfileClaim(
                    local_player_id=subject.id, user_account_id=player.id, relationship_type="player", status="approved"
                )
            )
            db.session.commit()
            signed_id = -subject.id
        engine = db.engine
        db.session.remove()
    deletion_thread = local()
    created = []

    def create_in_window():
        with app.test_client() as client:
            headers = {"Authorization": "Bearer " + tokens[role]}
            if kind == "claim":
                response = client.post(
                    "/api/players/987654321/claim",
                    headers=headers,
                    json={"relationship_type": "agent", "message": "Gap claim"},
                )
                key = "claim"
            elif kind == "contact":
                response = client.post(
                    "/api/contact/requests",
                    headers=headers,
                    json={"player_api_id": -ids["local"], "message": "Gap introduction"},
                )
                key = "contact_request"
            else:
                response = client.post(
                    f"/api/club/{ids['program']}/invitations",
                    headers=headers,
                    json={"player_api_id": signed_id, "client_request_id": str(uuid4())},
                )
                key = "invitation"
            assert response.status_code == 201, response.json
            created.append(response.json[key]["id"])

    fired = False

    def gap(conn, cursor, statement, parameters, context, executemany):
        nonlocal fired
        # Invitation creation itself needs P/C, so let it commit immediately
        # before erasure's first P lock, after the full selection was read.
        table = "club_programs" if kind == "invitation" else "user_accounts"
        if (
            getattr(deletion_thread, "active", False)
            and not fired
            and f"FROM {table}" in statement
            and "FOR UPDATE" in statement
        ):
            fired = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(create_in_window).result(20)

    sa.event.listen(engine, "before_cursor_execute", gap)
    try:
        deletion_thread.active = True
        with app.test_client() as client:
            response = client.post(
                "/api/account/delete", headers={"Authorization": "Bearer " + tokens[role]}, json={"confirm": "DELETE"}
            )
    finally:
        deletion_thread.active = False
        sa.event.remove(engine, "before_cursor_execute", gap)
    assert fired and created
    assert response.status_code == 200, response.json
    with app.app_context():
        assert db.session.get(UserAccount, uid) is None
        assert PlayerProfileClaim.query.filter_by(user_account_id=uid).count() == 0
        assert PlayerShowcaseProfile.query.filter_by(updated_by_user_id=uid).count() == 0
        assert ContactRequest.query.filter_by(scout_user_id=uid).count() == 0
        assert ContactMessage.query.filter_by(sender_user_id=uid).count() == 0
        assert ContactOutcome.query.filter_by(reported_by_user_id=uid).count() == 0
        assert ContactAuditEvent.query.filter_by(actor_user_id=uid).count() == 0
        if kind == "claim":
            assert db.session.get(PlayerProfileClaim, created[0]) is None
        if kind == "invitation":
            assert db.session.get(ClubInvitation, created[0]) is None


@pytest.mark.parametrize("c1", [False, True])
def test_claim_after_account_lock_matches_main(pg, monkeypatch, c1):
    app, ids, tokens = setup_world(pg, monkeypatch, (), "ordinary")
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", str(c1).lower())
    monkeypatch.setenv("SHOWCASE_ENABLED", "true")
    monkeypatch.setenv("PLAYER_SHOWCASE_ENABLED", "true")
    with app.app_context():
        suffix = uuid4().hex
        user = UserAccount(email=f"after-{suffix}@example.test", display_name=suffix, display_name_lower=suffix)
        db.session.add(user)
        db.session.commit()
        uid, token = user.id, issue_user_token(user.email)["token"]
        engine = db.engine
        db.session.remove()
    headers = {"Authorization": "Bearer " + token}
    role = local()
    future = None

    def submit_claim():
        with app.test_client() as client:
            return client.post(
                "/api/players/987654321/claim",
                headers=headers,
                json={"relationship_type": "agent", "message": "After lock"},
            )

    with ThreadPoolExecutor(max_workers=1) as pool:

        def after(conn, cursor, statement, parameters, context, executemany):
            nonlocal future
            if (
                getattr(role, "deleting", False)
                and future is None
                and "FROM user_accounts" in statement
                and "FOR UPDATE" in statement
            ):
                future = pool.submit(submit_claim)
                with pytest.raises(TimeoutError):
                    future.result(0.5)

        sa.event.listen(engine, "after_cursor_execute", after)
        try:
            role.deleting = True
            with app.test_client() as client:
                response = client.post("/api/account/delete", headers=headers, json={"confirm": "DELETE"})
        finally:
            role.deleting = False
            sa.event.remove(engine, "after_cursor_execute", after)
        assert response.status_code == 200, response.json
        # N-1 is inherited: the blocked claim's insert fails after deletion.
        assert future is not None and future.result(20).status_code == 500
    with app.app_context():
        assert db.session.get(UserAccount, uid) is None
        assert PlayerProfileClaim.query.filter_by(user_account_id=uid).count() == 0


def test_erasure_scope_retry_is_bounded_and_preserves_account(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, (), "ordinary")
    monkeypatch.setenv("SHOWCASE_ENABLED", "true")
    monkeypatch.setenv("PLAYER_SHOWCASE_ENABLED", "true")
    with app.app_context():
        suffix = uuid4().hex
        user = UserAccount(email=f"bounded-{suffix}@example.test", display_name=suffix, display_name_lower=suffix)
        db.session.add(user)
        db.session.commit()
        uid, token = user.id, issue_user_token(user.email)["token"]
        engine = db.engine
        db.session.remove()
    headers = {"Authorization": "Bearer " + token}
    role = local()
    created = []

    def submit_claim():
        with app.test_client() as client:
            response = client.post(
                f"/api/players/{987650000 + len(created)}/claim",
                headers=headers,
                json={"relationship_type": "agent", "message": "Repeated real scope change"},
            )
            assert response.status_code == 201, response.json
            created.append(response.json["claim"]["id"])

    def gap(conn, cursor, statement, parameters, context, executemany):
        if (
            getattr(role, "deleting", False)
            and "FROM user_accounts" in statement
            and "ORDER BY user_accounts.id" in statement
            and "FOR UPDATE" in statement
        ):
            assert len(created) < 5, "erasure retry limit exceeded"
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(submit_claim).result(20)

    sa.event.listen(engine, "before_cursor_execute", gap)
    try:
        role.deleting = True
        with app.test_client() as client:
            response = client.post("/api/account/delete", headers=headers, json={"confirm": "DELETE"})
    finally:
        role.deleting = False
        sa.event.remove(engine, "before_cursor_execute", gap)
    assert len(created) == 5
    assert response.status_code == 409, response.json
    with app.app_context():
        assert db.session.get(UserAccount, uid) is not None
        assert PlayerProfileClaim.query.filter_by(user_account_id=uid).count() == 5
        with engine.begin() as connection:
            # Savepoint exhaustion releases both the account and claim locks.
            connection.execute(sa.text("SELECT id FROM user_accounts WHERE id=:id FOR UPDATE NOWAIT"), {"id": uid})
            assert (
                len(
                    connection.execute(
                        sa.text("SELECT id FROM player_profile_claims WHERE user_account_id=:id FOR UPDATE NOWAIT"),
                        {"id": uid},
                    ).all()
                )
                == 5
            )
