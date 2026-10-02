# ruff: noqa: F811
"""C1F7 real PostgreSQL: every inventory action pair, both first-lock orders.

Each contender executes the real route/service. SQL hooks hold the first row
lock until the other transaction attempts a lock; final-state checks distinguish
accepted writes from retries/unavailable targets. Terminal publication changes
may legitimately close a thread and account erasure may legitimately delete it.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from itertools import combinations_with_replacement
from threading import Event, local
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
from src.models.league import Player, UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.trust import ScoutVerification
from src.services import club_player_publication as publication
from src.services.contact_locks import database_conflict
from test_club_player_publication_postgres import make_consented, pg  # noqa: F401

CONTACT = (
    "create",
    "accept",
    "decline",
    "consent",
    "link",
    "withdraw",
    "revoke",
    "message_scout",
    "message_player",
    "message_club",
    "list_club",
    "list_player",
    "list_scout",
    "outcome",
    "expiry",
    "list_requests",
)
PUBLICATION = (
    "invite",
    "redeem",
    "public_consent",
    "public_withdraw",
    "public_revoke",
    "review_approve",
    "review_reject",
    "showcase",
    "unlink",
    "erasure",
    "invitation",
    "feedback",
    "application",
    "merge",
)
# The inventory's ordinary and club-first paths share actions, but both modes
# are exercised. Each unordered pair runs twice, including same-action races.
CASES = [
    (mode, left, right, reverse)
    for mode, actions in (
        ("club", CONTACT + PUBLICATION),
        ("ordinary", CONTACT + ("merge", "application", "invitation", "feedback", "erasure")),
    )
    for left, right in combinations_with_replacement(actions, 2)
    for reverse in (False, True)
]


def setup_world(pg, monkeypatch, actions, mode):
    import src.routes.contact as routes
    from src.routes.account import account_bp
    from src.routes.feedback import feedback_bp
    from src.routes.opportunities import opportunities_bp
    from src.routes.showcase import showcase_bp
    from src.services.opportunities import register_notifications

    app, ids = pg
    for flag in (
        "CONTACT_RAIL_ENABLED",
        "OPPORTUNITIES_ENABLED",
        "APPLICATIONS_ENABLED",
        "P2_FOUNDATION_ENABLED",
        "PILOT_CLUB_RELATIONSHIPS_ENABLED",
    ):
        monkeypatch.setenv(flag, "true")
    app.config.update(RATELIMIT_ENABLED=False, ADMIN_API_KEY="c1f7-admin")
    monkeypatch.setenv("ADMIN_EMAILS", ids["email"])
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("ADMIN_API_KEY", "c1f7-admin")
    limiter.init_app(app)
    app.register_blueprint(routes.contact_bp, url_prefix="/api")
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(account_bp, url_prefix="/api")
    app.register_blueprint(feedback_bp, url_prefix="/api")
    app.register_blueprint(opportunities_bp, url_prefix="/api")
    register_notifications()
    pubid = make_consented(ids)
    row = db.session.get(Publication, pubid)
    publication.review(
        row, "matrix", {"action": "approve", "expected_version": row.version, "reason": "Synthetic concurrency fixture"}
    )
    db.session.commit()
    ids.update(publication=pubid, claim=row.claim_id)
    scouts = []
    for _ in range(2):
        suffix = uuid4().hex
        scout = UserAccount(
            email=f"c1f7-{suffix}@example.test", display_name=f"Matrix {suffix}", display_name_lower=f"matrix {suffix}"
        )
        db.session.add(scout)
        db.session.flush()
        db.session.add(
            ScoutVerification(
                user_account_id=scout.id,
                full_name="Matrix scout",
                organization="Fixture",
                role_title="Scout",
                statement="Fixture",
                status="approved",
            )
        )
        scouts.append(scout.id)
    db.session.add(Player(player_id=900_000_000 + ids["local"], name="Synthetic merge target"))
    if mode == "ordinary":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
        db.session.get(LocalPlayer, ids["local"]).provenance = "user"
        db.session.get(LocalPlayer, ids["local"]).status = "approved"
    pending = bool(set(actions) & {"accept", "decline", "withdraw", "expiry"})
    consent_pending = bool(set(actions) & {"consent", "link"})
    now = publication.now()
    request = ContactRequest(
        scout_user_id=scouts[0],
        player_api_id=-ids["local"],
        claim_id=ids["claim"],
        status="pending" if pending else "accepted",
        club_first=mode == "club",
        routing_mode="club_included",
        club_program_id=ids["program"],
        club_consent_status="pending" if consent_pending else "granted",
        message="Synthetic matrix introduction",
        responded_at=None if pending else now,
        expires_at=now - timedelta(days=1) if "expiry" in actions else now + timedelta(days=7),
    )
    db.session.add(request)
    # Seed a real relationship and an opportunity for the additional inventory paths.
    from src.models.club_invitation import ClubInvitation
    from src.models.funding import ClubProgramClaim
    from src.models.opportunities import ClubOpportunity

    invitation = ClubInvitation(
        program_id=ids["program"],
        player_api_id=-ids["local"],
        claim_id=ids["claim"],
        recipient_user_id=ids["adult"],
        created_by_user_id=ids["owner"],
        source_manager_claim_id=ClubProgramClaim.query.filter_by(program_id=ids["program"]).first().id,
        status="accepted",
        client_request_id=str(uuid4()),
        request_hash="fixture",
        expires_at=now + timedelta(days=7),
    )
    opportunity = ClubOpportunity(
        program_id=ids["program"],
        creator_user_id=ids["owner"],
        type="trial",
        title="Synthetic trial",
        description="Concurrency fixture",
        venue="Fixture ground",
        status="published",
        closes_at=now + timedelta(days=7),
        timezone="UTC",
    )
    db.session.add_all([invitation, opportunity])
    if "review_approve" in actions:
        row.moderation_status = "pending"
    if "invite" in actions:
        publication.revoke(row, club=True)
    if "redeem" in actions:
        # A retired binding and closed old thread are realistic recovery state;
        # redemption can create a fresh claim while competitors revalidate it.
        import hashlib

        token = "c1f7-fixture-token-" + uuid4().hex
        row.invite_token_hash = hashlib.sha256(token.encode()).hexdigest()
        row.invite_expires_at = now + timedelta(days=7)
        row.claimed_at = row.claim_id = row.recipient_user_id = row.consented_at = None
        row.moderation_status = "pending"
        old_claim = db.session.get(PlayerProfileClaim, ids["claim"])
        old_claim.status, old_claim.verification_method = "revoked", "club_vouch_retired"
        request.status = "withdrawn"
        ids["invite_token"] = token
    if "unlink" in actions:
        from src.models.follow import PlayerShadow

        # Legacy provider mapping: no occupied synthetic shadow namespace yet.
        PlayerShadow.query.filter_by(player_api_id=-ids["local"]).delete(synchronize_session=False)
        db.session.get(LocalPlayer, ids["local"]).api_player_id = 900_000_000 + ids["local"]
    db.session.commit()
    ids.update(
        request=request.id, scout=scouts[0], other_scout=scouts[1], invitation=invitation.id, opportunity=opportunity.id
    )
    seed_multiclub_world(ids, scouts, mode)
    tokens = {
        role: issue_user_token(db.session.get(UserAccount, id_).email)["token"]
        for role, id_ in (
            ("club", ids["owner"]),
            ("player", ids["adult"]),
            ("scout", scouts[0]),
            ("other_scout", scouts[1]),
        )
    }
    tokens["admin"] = issue_user_token(ids["email"], role="admin")["token"]
    db.session.commit()
    db.session.remove()
    return app, ids, tokens


def seed_multiclub_world(ids, scouts, mode):
    """Three adults, two clubs, feedback shared across clubs and a manager/scout.

    Background rows are valid retained history, not unavailable placeholders.
    Their IDs are included in erasure and feedback batches during the races.
    """
    from datetime import date

    from src.models.club_invitation import ClubInvitation
    from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager
    from src.models.player_feedback import PlayerFeedback

    first = db.session.get(ClubProgram, ids["program"])
    suffix = uuid4().hex
    second = ClubProgram(
        funding_league_id=first.funding_league_id,
        name=f"Other club {suffix}",
        legal_name="Fixture",
        slug=f"matrix-other-{suffix}",
        country="Test",
        region="Test",
        platform_status="approved",
    )
    db.session.add(second)
    db.session.flush()
    manager_claim = ClubProgramClaim(
        program_id=second.id, user_account_id=ids["owner"], relationship_type="club_official", status="approved"
    )
    db.session.add(manager_claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=second.id,
            user_account_id=ids["owner"],
            source_claim_id=manager_claim.id,
            status="active",
            granted_by="test",
        )
    )
    db.session.add(
        ScoutVerification(
            user_account_id=ids["owner"],
            full_name="Manager and scout",
            organization="Fixture",
            role_title="Scout",
            statement="Fixture",
            status="approved",
        )
    )
    now = publication.now()
    first_manager = ClubProgramClaim.query.filter_by(program_id=first.id, user_account_id=ids["owner"]).first()
    for kind in ("ordinary", "published"):
        user = UserAccount(
            email=f"multi-{kind}-{suffix}@example.test",
            display_name=f"Adult {kind} {suffix}",
            display_name_lower=f"adult {kind} {suffix}",
        )
        player = LocalPlayer(
            display_name=f"Adult {kind} {suffix}",
            provenance="user" if kind == "ordinary" else "club",
            origin_program_id=second.id if kind == "published" else None,
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            status="approved" if kind == "ordinary" else "pending",
        )
        db.session.add_all([user, player])
        db.session.flush()
        player.api_player_id = -player.id
        claim = PlayerProfileClaim(
            local_player_id=player.id,
            user_account_id=user.id,
            relationship_type="player",
            status="approved",
            club_program_id=second.id,
            contract_status="contracted",
            verification_method="club_vouch" if kind == "published" else "manual",
        )
        db.session.add(claim)
        db.session.flush()
        if kind == "published":
            db.session.add(
                Publication(
                    program_id=second.id,
                    local_player_id=player.id,
                    recipient_user_id=user.id,
                    recipient_email=user.email,
                    claim_id=claim.id,
                    adult_invited_at=now,
                    claimed_at=now,
                    association_confirmed_at=now,
                    association_confirmed_by=ids["owner"],
                    consent_version=publication.CONSENT_VERSION,
                    consented_at=now,
                    moderation_status="approved",
                    reviewed_at=now,
                    reviewed_by="fixture",
                    creator_user_id=ids["owner"],
                )
            )
        # The manager also sent old scout introductions; deletion must keep the
        # pilot recipients' claims distinct from the manager's owned claims.
        db.session.add(
            ContactRequest(
                scout_user_id=ids["owner"],
                player_api_id=-player.id,
                claim_id=claim.id,
                status="withdrawn",
                routing_mode="direct",
                message="Old retained introduction",
                expires_at=now - timedelta(days=30),
            )
        )
        if kind == "ordinary":
            for program, source in ((first, first_manager), (second, manager_claim)):
                invitation = ClubInvitation(
                    program_id=program.id,
                    player_api_id=-player.id,
                    claim_id=claim.id,
                    recipient_user_id=user.id,
                    created_by_user_id=ids["owner"],
                    source_manager_claim_id=source.id,
                    status="accepted",
                    client_request_id=str(uuid4()),
                    request_hash="fixture",
                    expires_at=now + timedelta(days=7),
                )
                db.session.add(invitation)
                db.session.flush()
                feedback_id = str(uuid4())
                db.session.add(
                    PlayerFeedback(
                        id=feedback_id,
                        thread_id=feedback_id,
                        revision=1,
                        invitation_id=invitation.id,
                        program_id=program.id,
                        player_api_id=-player.id,
                        claim_id=claim.id,
                        recipient_user_id=user.id,
                        author_user_id=ids["owner"],
                        client_request_id=str(uuid4()),
                        request_hash="fixture",
                        title="Retained club feedback",
                        body="Real multi-club feedback fixture",
                        published_at=now - timedelta(days=1),
                    )
                )
        ids[f"background_{kind}"] = player.id
        ids[f"background_{kind}_claim"] = claim.id
        ids[f"background_{kind}_user"] = user.id
    ids["other_program"] = second.id
    db.session.commit()


def execute(app, ids, tokens, action, marker):
    """Return real response/status and a durable accepted-write receipt."""
    import src.routes.contact as routes
    from src.services.contact import issue_club_consent_token

    base = f"/api/contact/requests/{ids['request']}"
    if action in CONTACT and action != "expiry":
        role, method, url, data = "scout", "POST", base + "/" + action, None
        if action == "create":
            role, url, data = (
                "other_scout",
                "/api/contact/requests",
                {"player_api_id": -ids["local"], "message": marker},
            )
        elif action in {"accept", "decline"}:
            role = "player"
        elif action == "consent":
            role, url, data = "club", base + "/club-consent", {"action": "grant"}
        elif action == "link":
            with app.app_context():
                url = "/api/contact/club-consent/" + issue_club_consent_token(ids["request"], "grant")
        elif action.startswith("message_"):
            role, url, data = action.split("_")[1], base + "/messages", {"body": marker}
        elif action.startswith("list_") and action != "list_requests":
            role, method, url = action.split("_")[1], "GET", base + "/messages"
        elif action == "list_requests":
            method, url = "GET", "/api/contact/requests?box=club"
            role = "club"
        elif action == "outcome":
            url, data = base + "/outcome", {"stage": "contacted", "notes": marker}
        with app.test_client() as client:
            response = client.open(url, method=method, headers={"Authorization": "Bearer " + tokens[role]}, json=data)
            return response.status_code, response.get_json()
    if action in {"showcase", "unlink", "application", "erasure", "feedback"}:
        if action == "erasure":
            method, url, data, headers = (
                "POST",
                "/api/account/delete",
                {"confirm": "DELETE"},
                {"Authorization": "Bearer " + tokens["player"]},
            )
        elif action == "feedback":
            method, url, data, headers = (
                "POST",
                f"/api/club/{ids['program']}/player-feedback",
                {
                    "invitation_id": ids["invitation"],
                    "client_request_id": str(uuid4()),
                    "title": "Synthetic matrix feedback",
                    "body": marker,
                },
                {"Authorization": "Bearer " + tokens["club"]},
            )
        elif action == "showcase":
            method, url, data, headers = (
                "PATCH",
                f"/api/local-players/{ids['local']}/showcase/profile",
                {"bio": marker},
                {"Authorization": "Bearer " + tokens["player"]},
            )
        elif action == "unlink":
            method, url, data, headers = (
                "POST",
                f"/api/admin/local-players/{ids['local']}/link-api",
                {"player_api_id": None},
                {"X-API-Key": "c1f7-admin", "Authorization": "Bearer " + tokens["admin"]},
            )
        else:
            method, url, data, headers = (
                "POST",
                f"/api/opportunities/{ids['opportunity']}/applications",
                {
                    "claim_id": ids["claim"],
                    "position": "Midfielder",
                    "contact_consent": True,
                    "client_request_id": str(uuid4()),
                },
                {"Authorization": "Bearer " + tokens["player"]},
            )
        with app.test_client() as client:
            response = client.open(url, method=method, headers=headers, json=data)
            return response.status_code, response.get_json()
    with app.app_context():
        # Actual route/service adapters, with the same transaction ownership.
        try:
            row = db.session.get(Publication, ids["publication"])
            if action == "expiry":
                routes._expire_visible_rows(ContactRequest.query.filter_by(id=ids["request"]))
            elif action == "invite":
                publication.invite(
                    ids["program"],
                    ids["local"],
                    ids["owner"],
                    {"recipient_email": ids["email"], "expected_version": row.version},
                )
            elif action == "redeem":
                publication.redeem(
                    db.session.get(UserAccount, ids["adult"]), {"token": ids["invite_token"], "self_claim": True}
                )
            elif action == "public_consent":
                if row is None:
                    return 404, {}
                publication.consent(
                    row,
                    ids["adult"],
                    {
                        "expected_version": row.version,
                        "public_profile_consent": True,
                        "consent_version": publication.CONSENT_VERSION,
                    },
                )
            elif action in {"public_withdraw", "public_revoke"}:
                if row is None:
                    return 404, {}
                publication.revoke(row, club=action == "public_revoke")
            elif action.startswith("review_"):
                if row is None:
                    return 404, {}
                publication.review(
                    row, "matrix", {"action": action.split("_")[1], "expected_version": row.version, "reason": marker}
                )
            elif action == "invitation":
                from src.models.club_invitation import ClubInvitation, resolve_invitation

                invitation = db.session.get(ClubInvitation, ids["invitation"])
                if invitation is None:
                    return 404, {}
                resolve_invitation(db.session, invitation, ids["adult"], "revoke")
            elif action == "merge":
                from src.routes.showcase import (
                    _api_subject,
                    _club_publication_identity_protected,
                    _local_subject,
                    _merge_subject_claims,
                    _rekey_contacts,
                )

                player = db.session.get(LocalPlayer, ids["local"])
                if _club_publication_identity_protected(player):
                    return 409, {}
                _merge_subject_claims(_local_subject(ids["local"]), _api_subject(900_000_000 + ids["local"]))
                _rekey_contacts(-ids["local"], 900_000_000 + ids["local"])
            db.session.commit()
            return 200, {}
        except Exception as exc:
            db.session.rollback()
            conflict = database_conflict(exc)
            if conflict:
                return conflict[1], {"error": conflict[0]}
            if isinstance(exc, publication.PublicationError) or hasattr(exc, "code") and hasattr(exc, "status"):
                return exc.status, {"error": exc.code}
            raise
        finally:
            db.session.remove()


def _run_pair(pg, monkeypatch, mode, left, right, reverse):
    app, ids, tokens = setup_world(pg, monkeypatch, (left, right), mode)
    first, second = (right, left) if reverse else (left, right)
    owns, attempted, finished = Event(), Event(), Event()
    thread = local()
    sequences = {"first": [], "second": []}
    tables = ("club_programs", "club_player_publications", "player_profile_claims", "contact_requests")
    with app.app_context():
        engine = db.engine

    def before(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and getattr(thread, "role", None) == "second":
            attempted.set()

    def after(conn, cursor, statement, parameters, context, executemany):
        role = getattr(thread, "role", None)
        if role and "FOR UPDATE" in statement:
            table = next(
                (name for name in tables if f"FROM {name} " in statement or f"FROM {name}\n" in statement), None
            )
            if table:
                sequences[role].append(table)
                if role == "first" and not owns.is_set():
                    owns.set()
                    assert attempted.wait(10), (left, right, "second did not attempt a lock")

    sa.event.listen(engine, "before_cursor_execute", before)
    sa.event.listen(engine, "after_cursor_execute", after)

    def run(role, action):
        thread.role = role
        try:
            if role == "second":
                # Some unavailable paths reject before taking locks; finished
                # releases the other contender without hiding an exception.
                assert owns.wait(10) or finished.is_set()
            return execute(app, ids, tokens, action, f"{role}-{action}")
        finally:
            if role == "first":
                finished.set()
                owns.set()
            else:
                attempted.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(run, "first", first), pool.submit(run, "second", second)
            results = {"first": a.result(30), "second": b.result(30)}
    finally:
        sa.event.remove(engine, "before_cursor_execute", before)
        sa.event.remove(engine, "after_cursor_execute", after)
    assert all(status < 500 for status, _ in results.values()), (left, right, reverse, results)
    # Every valid message/read/outcome race must perform useful work; a pair
    # of deterministic retry replies must never count as success.
    if {left, right} <= {
        "message_scout",
        "message_player",
        "message_club",
        "list_scout",
        "list_player",
        "list_club",
        "outcome",
        "list_requests",
    }:
        assert all(status in {200, 201} for status, _ in results.values()), (left, right, results)
    for sequence in sequences.values():
        # Re-locking already-held rows is harmless. First acquisitions must
        # follow the canonical order, across expiry's separate transactions too.
        distinct = list(dict.fromkeys(sequence))
        assert distinct == sorted(distinct, key=tables.index), (left, right, sequence)

    with app.app_context():
        request = db.session.get(ContactRequest, ids["request"])
        current_publication = db.session.get(Publication, ids["publication"])
        for role, action in (("first", first), ("second", second)):
            status, payload = results[role]
            if status == 201 and action.startswith("message_") and request is not None:
                message = db.session.get(ContactMessage, payload["message"]["id"])
                assert message is not None and message.body == f"{role}-{action}"
            if status == 201 and action == "outcome" and request is not None:
                assert (
                    ContactOutcome.query.filter_by(contact_request_id=ids["request"], notes=f"{role}-{action}").count()
                    == 1
                )
            if status == 201 and action == "create" and "erasure" not in (left, right):
                assert db.session.get(ContactRequest, payload["contact_request"]["id"]) is not None
        if (
            request
            and current_publication
            and (
                current_publication.withdrawn_at
                or current_publication.club_revoked_at
                or current_publication.moderation_status == "rejected"
            )
        ):
            assert request.status not in {"pending", "accepted"}
        if request:
            assert request.status in {"pending", "accepted", "declined", "withdrawn", "expired"}
        assert (
            ContactAuditEvent.query.filter_by(contact_request_id=ids["request"], event_type="message_sent").count()
            == ContactMessage.query.filter_by(contact_request_id=ids["request"]).count()
        )
        db.session.rollback()
        db.session.remove()

    return results


@pytest.mark.parametrize("mode,left,right,reverse", CASES, ids=lambda value: str(value))
def test_inventory_action_pair(pg, monkeypatch, mode, left, right, reverse):
    _run_pair(pg, monkeypatch, mode, left, right, reverse)


@pytest.mark.parametrize("sender", ["scout", "player"])
@pytest.mark.parametrize("reverse", [False, True])
def test_reviewer_revoke_vs_message_regression(pg, monkeypatch, sender, reverse):
    _run_pair(pg, monkeypatch, "club", "revoke", f"message_{sender}", reverse)


@pytest.mark.parametrize("reverse", [False, True])
def test_reviewer_second_scout_vs_player_message_regression(pg, monkeypatch, reverse):
    results = _run_pair(pg, monkeypatch, "club", "create", "message_player", reverse)
    assert [value[0] for value in results.values()] == [201, 201]


@pytest.mark.parametrize("reverse", [False, True])
def test_reviewer_inherited_ordinary_messages_regression(pg, monkeypatch, reverse):
    results = _run_pair(pg, monkeypatch, "ordinary", "message_club", "message_scout", reverse)
    assert [value[0] for value in results.values()] == [201, 201]


@pytest.mark.parametrize("reverse", [False, True])
def test_reviewer_inherited_ordinary_consent_vs_open_regression(pg, monkeypatch, reverse):
    results = _run_pair(pg, monkeypatch, "ordinary", "consent", "list_club", reverse)
    assert sorted(value[0] for value in results.values()) in ([200, 200], [200, 409])


def test_changed_binding_in_read_lock_gap_retries_without_message(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "club")
    changed = False
    with app.app_context():
        engine = db.engine

    def gap(conn, cursor, statement, parameters, context, executemany):
        nonlocal changed
        if not changed and "FROM club_programs" in statement and "FOR UPDATE" in statement:
            changed = True
            with engine.begin() as other:
                other.execute(
                    sa.text("UPDATE player_profile_claims SET club_program_id = NULL WHERE id=:id"),
                    {"id": ids["claim"]},
                )

    sa.event.listen(engine, "before_cursor_execute", gap)
    try:
        status, payload = execute(app, ids, tokens, "message_scout", "must not persist")
    finally:
        sa.event.remove(engine, "before_cursor_execute", gap)
    assert changed and status == 409 and payload["code"] == "contact_conflict"
    with app.app_context():
        assert ContactMessage.query.filter_by(contact_request_id=ids["request"]).count() == 0
        db.session.rollback()


def test_savepoint_rollback_reacquires_real_locks(pg):
    from src.services.contact_locks import lock_contact_scope

    app, ids = pg
    db.session.commit()
    nested = db.session.begin_nested()
    lock_contact_scope(db.session, program_id=ids["program"])
    nested.rollback()
    lock_contact_scope(db.session, program_id=ids["program"])
    with db.engine.connect() as contender:
        with pytest.raises(sa.exc.OperationalError) as error:
            contender.execute(
                sa.text("SELECT id FROM club_programs WHERE id=:id FOR UPDATE NOWAIT"), {"id": ids["program"]}
            )
        assert error.value.orig.sqlstate == "55P03"
    db.session.rollback()


@pytest.mark.parametrize("action", CONTACT + PUBLICATION)
def test_inventory_action_has_a_successful_control(pg, monkeypatch, action):
    # Guard against an all-pairs fixture that only exercises unavailable exits.
    # Identity merges are forbidden for club-origin consent, so their control
    # uses the ordinary identity path that exists on main.
    mode = "ordinary" if action == "merge" else "club"
    app, ids, tokens = setup_world(pg, monkeypatch, (action,), mode)
    status, payload = execute(app, ids, tokens, action, "successful-control")
    assert status in {200, 201}, (action, status, payload)
