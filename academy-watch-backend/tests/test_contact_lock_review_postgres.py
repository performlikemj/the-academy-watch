# ruff: noqa: F811
"""RC1XV3-X independent regression probes, retained as first-attempt controls."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.models.club_invitation import ClubInvitation
from src.models.contact import ContactMessage, ContactRequest
from src.models.funding import ClubProgramClaim
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from test_club_player_publication_postgres import pg  # noqa: F401
from test_contact_lock_matrix_postgres import _run_pair, execute, setup_world


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("mode", ["ordinary", "club"])
def test_repeat_accept_vs_player_outcome(pg, monkeypatch, reverse, mode):
    # Outcome actor is the PLAYER, unlike the builder's scout-only adapter.
    import test_contact_lock_matrix_postgres as matrix

    original = matrix.execute

    def run(app, ids, tokens, action, marker):
        if action == "outcome":
            with app.test_client() as client:
                r = client.post(
                    f"/api/contact/requests/{ids['request']}/outcome",
                    headers={"Authorization": "Bearer " + tokens["player"]},
                    json={"stage": "contacted", "notes": marker},
                )
                return r.status_code, r.json
        return original(app, ids, tokens, action, marker)

    monkeypatch.setattr(matrix, "execute", run)
    # The fixture starts accepted to force repeat accept, matching X-N1.
    original_setup = matrix.setup_world

    def setup(*a, **k):
        app, ids, tokens = original_setup(*a, **k)
        with app.app_context():
            db.session.get(ContactRequest, ids["request"]).status = "accepted"
            db.session.commit()
        return app, ids, tokens

    monkeypatch.setattr(matrix, "setup_world", setup)
    results = _run_pair(pg, monkeypatch, mode, "accept", "outcome", reverse)
    assert sorted(s for s, p in results.values()) == [201, 409], results


@pytest.mark.parametrize("gap_state", ["withdrawn", "revoked", "retired"])
def test_status_changed_in_hint_lock_gap(pg, monkeypatch, gap_state):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "club")
    changed = False
    with app.app_context():
        engine = db.engine

    def gap(conn, cursor, statement, parameters, context, executemany):
        nonlocal changed
        if not changed and "FROM club_programs" in statement and "FOR UPDATE" in statement:
            changed = True
            with engine.begin() as other:
                if gap_state == "withdrawn":
                    other.execute(
                        sa.text("UPDATE contact_requests SET status='withdrawn' WHERE id=:id"), {"id": ids["request"]}
                    )
                elif gap_state == "revoked":
                    other.execute(
                        sa.text("UPDATE club_player_publications SET club_revoked_at=NOW() WHERE id=:id"),
                        {"id": ids["publication"]},
                    )
                else:
                    other.execute(
                        sa.text(
                            "UPDATE player_profile_claims SET status='revoked',verification_method='club_vouch_retired' WHERE id=:id"
                        ),
                        {"id": ids["claim"]},
                    )

    sa.event.listen(engine, "before_cursor_execute", gap)
    try:
        status, body = execute(app, ids, tokens, "message_scout", "must-not-persist")
    finally:
        sa.event.remove(engine, "before_cursor_execute", gap)
    print("GAP", gap_state, status, body)
    assert changed and 400 <= status < 500
    with app.app_context():
        assert ContactMessage.query.filter_by(contact_request_id=ids["request"]).count() == 0


def test_manager_erasure_with_other_invitation_claim(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "ordinary")
    from src.services.club_player_publication import now

    with app.app_context():
        # Eraser participated in this accepted contact, so root scope owns R.
        db.session.get(ContactRequest, ids["request"]).club_consent_by_user_id = ids["owner"]
        from src.models.club_player_publication import ClubPlayerPublication

        ClubPlayerPublication.query.filter_by(id=ids["publication"]).delete(synchronize_session=False)
        suffix = uuid4().hex
        user = UserAccount(
            email=f"erasure-{suffix}@example.test", display_name="Other adult", display_name_lower=f"other-{suffix}"
        )
        local = LocalPlayer(
            display_name="Other community adult",
            provenance="user",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            status="approved",
        )
        db.session.add_all([user, local])
        db.session.flush()
        local.api_player_id = -local.id
        claim = PlayerProfileClaim(
            local_player_id=local.id,
            user_account_id=user.id,
            relationship_type="player",
            status="approved",
            club_program_id=ids["program"],
        )
        db.session.add(claim)
        db.session.flush()
        db.session.add(
            ClubInvitation(
                program_id=ids["program"],
                player_api_id=-local.id,
                claim_id=claim.id,
                recipient_user_id=user.id,
                created_by_user_id=ids["owner"],
                source_manager_claim_id=ClubProgramClaim.query.filter_by(program_id=ids["program"]).first().id,
                status="accepted",
                client_request_id=str(uuid4()),
                request_hash="fixture",
                expires_at=now() + timedelta(days=7),
            )
        )
        db.session.commit()
    with app.test_client() as client:
        response = client.post(
            "/api/account/delete", headers={"Authorization": "Bearer " + tokens["club"]}, json={"confirm": "DELETE"}
        )
    print("MANAGER ERASURE", response.status_code, response.json)
    with app.app_context():
        print("ERASER STILL STORED", db.session.get(UserAccount, ids["owner"]) is not None)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(UserAccount, ids["owner"]) is None


def test_relationship_revoke_preserves_unrelated_contact(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "club")
    from src.models.club_invitation import resolve_invitation
    from src.services.club_player_publication import now

    with app.app_context():
        # A retained, unrelated direct request is deliberately outside invitation's predicate.
        other = ContactRequest(
            scout_user_id=ids["other_scout"],
            player_api_id=-ids["local"],
            claim_id=ids["claim"],
            status="accepted",
            routing_mode="direct",
            club_consent_status=None,
            message="Unrelated retained ordinary request",
            expires_at=now() + timedelta(days=7),
        )
        db.session.add(other)
        db.session.commit()
        otherid = other.id
        invitation = db.session.get(ClubInvitation, ids["invitation"])
        resolve_invitation(db.session, invitation, ids["adult"], "revoke")
        db.session.commit()
        row = db.session.get(ContactRequest, otherid)
        print("UNRELATED CONTACT", row.status, row.club_consent_status)
        assert row.status == "accepted" and row.club_consent_status is None


def test_dark_contact_list_sql_work(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "ordinary")
    queries = []
    with app.app_context():
        engine = db.engine

    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        with app.test_client() as client:
            response = client.get(
                "/api/contact/requests?box=club", headers={"Authorization": "Bearer " + tokens["club"]}
            )
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.json
    assert len(queries) <= 31, len(queries)
    print("DARK CLUB LIST", len(queries), "SQL", len([q for q in queries if "FOR UPDATE" in q]), "LOCK QUERIES")
    for q in queries:
        if "club_programs" in q:
            print("PROGRAM SQL", q.replace("\n", " "))


def test_club_feedback_list_multiple_publications(pg, monkeypatch):
    from src.models.funding import ClubRosterMember
    from src.services import club_player_publication as publication

    app, ids, tokens = setup_world(pg, monkeypatch, ("feedback",), "club")
    status, payload = execute(app, ids, tokens, "feedback", "first valid feedback")
    assert status == 201, (status, payload)
    with app.app_context():
        suffix = uuid4().hex
        adult = UserAccount(
            email=f"feedback-{suffix}@example.test",
            display_name="Second club adult",
            display_name_lower=f"second-{suffix}",
        )
        local = LocalPlayer(
            display_name=f"Second published club adult {suffix}",
            provenance="club",
            origin_program_id=ids["program"],
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            status="pending",
        )
        db.session.add_all([adult, local])
        db.session.flush()
        local.api_player_id = -local.id
        db.session.add(
            ClubRosterMember(program_id=ids["program"], local_player_id=local.id, added_by_user_id=ids["owner"])
        )
        db.session.commit()
        row, token = publication.invite(ids["program"], local.id, ids["owner"], {"recipient_email": adult.email})
        db.session.commit()
        row = publication.redeem(adult, {"token": token, "self_claim": True})
        publication.consent(
            row,
            adult.id,
            {
                "expected_version": row.version,
                "public_profile_consent": True,
                "consent_version": publication.CONSENT_VERSION,
            },
        )
        db.session.commit()
        publication.review(
            row, "reviewer", {"action": "approve", "expected_version": row.version, "reason": "Synthetic second adult"}
        )
        db.session.commit()
        invitation = ClubInvitation(
            program_id=ids["program"],
            player_api_id=-local.id,
            claim_id=row.claim_id,
            recipient_user_id=adult.id,
            created_by_user_id=ids["owner"],
            source_manager_claim_id=ClubProgramClaim.query.filter_by(program_id=ids["program"]).first().id,
            status="accepted",
            client_request_id=str(uuid4()),
            request_hash="fixture",
            expires_at=publication.now() + timedelta(days=7),
        )
        request = ContactRequest(
            scout_user_id=ids["scout"],
            player_api_id=-local.id,
            claim_id=row.claim_id,
            status="accepted",
            club_first=True,
            routing_mode="club_included",
            club_program_id=ids["program"],
            club_consent_status="granted",
            message="Second accepted introduction",
            expires_at=publication.now() + timedelta(days=7),
        )
        db.session.add_all([invitation, request])
        db.session.commit()
        ids2 = {
            **ids,
            "local": local.id,
            "adult": adult.id,
            "publication": row.id,
            "claim": row.claim_id,
            "invitation": invitation.id,
            "request": request.id,
        }
    status, payload = execute(app, ids2, tokens, "feedback", "second valid feedback")
    assert status == 201, (status, payload)
    with app.test_client() as client:
        response = client.get(
            f"/api/club/{ids['program']}/player-feedback", headers={"Authorization": "Bearer " + tokens["club"]}
        )
    print("MULTI PUBLICATION FEEDBACK", response.status_code, response.json)
    assert response.status_code == 200 and len(response.json["feedback"]) >= 2


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("mode", ["ordinary", "club"])
def test_new_relationship_revoke_vs_player_outcome(pg, monkeypatch, reverse, mode):
    import test_contact_lock_matrix_postgres as matrix

    original = matrix.execute

    def run(app, ids, tokens, action, marker):
        if action == "outcome":
            with app.test_client() as client:
                r = client.post(
                    f"/api/contact/requests/{ids['request']}/outcome",
                    headers={"Authorization": "Bearer " + tokens["player"]},
                    json={"stage": "contacted", "notes": marker},
                )
                return r.status_code, r.json
        return original(app, ids, tokens, action, marker)

    monkeypatch.setattr(matrix, "execute", run)
    _run_pair(pg, monkeypatch, mode, "invitation", "outcome", reverse)


def test_dark_player_feedback_list_multiple_clubs(pg, monkeypatch):
    from src.models.funding import ClubProgram, ClubProgramManager
    from src.services.club_player_publication import now

    app, ids, tokens = setup_world(pg, monkeypatch, ("feedback",), "ordinary")
    with app.app_context():
        suffix = uuid4().hex
        first = db.session.get(ClubProgram, ids["program"])
        program = ClubProgram(
            funding_league_id=first.funding_league_id,
            name=f"Other legacy club {suffix}",
            legal_name="Fixture",
            slug=f"other-legacy-{suffix}",
            country="Test",
            region="Test",
            platform_status="approved",
        )
        db.session.add(program)
        db.session.flush()
        mclaim = ClubProgramClaim(
            program_id=program.id, user_account_id=ids["owner"], relationship_type="club_official", status="approved"
        )
        db.session.add(mclaim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=program.id,
                user_account_id=ids["owner"],
                source_claim_id=mclaim.id,
                status="active",
                granted_by="test",
            )
        )
        invitation = ClubInvitation(
            program_id=program.id,
            player_api_id=-ids["local"],
            claim_id=ids["claim"],
            recipient_user_id=ids["adult"],
            created_by_user_id=ids["owner"],
            source_manager_claim_id=mclaim.id,
            status="accepted",
            client_request_id=str(uuid4()),
            request_hash="fixture",
            expires_at=now() + timedelta(days=7),
        )
        db.session.add(invitation)
        db.session.commit()
        ids2 = {**ids, "program": program.id, "invitation": invitation.id}
    # Latest club A row sorts first; only A is in the claim's current binding.
    status, payload = execute(app, ids2, tokens, "feedback", "older feedback from club B")
    assert status == 201, (status, payload)
    status, payload = execute(app, ids, tokens, "feedback", "newer feedback from club A")
    assert status == 201, (status, payload)
    with app.test_client() as client:
        response = client.get(
            f"/api/me/player-feedback?player_api_id={-ids['local']}",
            headers={"Authorization": "Bearer " + tokens["player"]},
        )
    print("DARK MULTI CLUB PLAYER FEEDBACK", response.status_code, response.json)
    assert response.status_code == 200 and len(response.json["feedback"]) >= 2


@pytest.mark.parametrize("reverse", [False, True])
def test_review_two_step_scope_succeeds_without_contention(pg, monkeypatch, reverse):
    # RC1XV3-O C1-ON probe, both orders: dynamic callers never fabricate 409.
    from src.models.club_invitation import lock_context

    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "club")
    with app.app_context():
        claims = [ids["claim"], ids["background_ordinary_claim"]]
        if reverse:
            claims.reverse()
        for claim in claims:
            assert lock_context(db.session, claim_id=claim, program_id=ids["program"], account_ids=[])[0] is not None
        db.session.rollback()


def test_feedback_batch_pagination_and_real_purge(pg, monkeypatch):
    from src.models.player_feedback import PlayerFeedback
    from src.services.club_player_publication import now

    app, ids, tokens = setup_world(pg, monkeypatch, ("feedback",), "ordinary")
    status, payload = execute(app, ids, tokens, "feedback", "newest feedback")
    assert status == 201
    with app.app_context():
        engine = db.engine
        expected = {row.id for row in PlayerFeedback.query.filter_by(program_id=ids["program"]).all()}
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        with app.test_client() as client:
            first = client.get(
                f"/api/club/{ids['program']}/player-feedback?limit=1",
                headers={"Authorization": "Bearer " + tokens["club"]},
            )
            assert first.status_code == 200 and first.json["next_before"]
            second = client.get(
                f"/api/club/{ids['program']}/player-feedback?limit=1&before={first.json['next_before']}",
                headers={"Authorization": "Bearer " + tokens["club"]},
            )
            assert second.status_code == 200
            assert {row["id"] for row in first.json["feedback"] + second.json["feedback"]} == expected
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)
    assert not [
        sql
        for sql in statements
        if "FOR UPDATE" in sql or sql.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT"))
    ]
    with app.app_context():
        # All synthetic feedback predates the audit deadline; purge must really
        # delete across claims/programs instead of passing only dry-run probes.
        feedback = PlayerFeedback.query.filter(
            PlayerFeedback.program_id.in_([ids["program"], ids["other_program"]])
        ).all()
        all_ids = {row.id for row in feedback}
        # Isolate this global sweep from retained rows of prior scratch schedules.
        PlayerFeedback.query.filter(~PlayerFeedback.id.in_(all_ids)).delete(synchronize_session=False)
        for row in feedback:
            row.withdrawn_at = now() - timedelta(days=40)
            row.audit_expires_at = now() - timedelta(days=10)
        db.session.commit()
    with app.test_client() as client:
        response = client.post(
            "/api/admin/player-feedback/purge",
            json={"dry_run": False},
            headers={"X-API-Key": "c1f7-admin", "Authorization": "Bearer " + tokens["admin"]},
        )
    assert response.status_code == 200 and response.json["deleted"] >= len(all_ids), response.json
    with app.app_context():
        assert PlayerFeedback.query.filter(PlayerFeedback.id.in_(all_ids)).count() == 0


def test_repeated_helper_uses_held_rows_without_sql(pg, monkeypatch):
    from src.services.contact_locks import lock_contact_scope

    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "club")
    with app.app_context():
        first = lock_contact_scope(db.session, request_id=ids["request"])
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sa.event.listen(db.engine, "before_cursor_execute", record)
        try:
            second = lock_contact_scope(db.session, request_id=ids["request"])
            program = lock_contact_scope(db.session, program_id=ids["program"])
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", record)
        assert first is second and program.programs[ids["program"]] is first.programs[ids["program"]]
        assert statements == []
        db.session.rollback()


def test_club_origin_owner_can_stage_second_club_attestation(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "club")
    from src.models.club_invitation import create_invitation, resolve_invitation

    with app.app_context():
        invitation, created = create_invitation(
            db.session,
            ids["other_program"],
            ids["owner"],
            {"player_api_id": -ids["local"], "client_request_id": str(uuid4())},
        )
        assert created
        db.session.commit()
        resolve_invitation(db.session, invitation, ids["adult"], "accept")
        db.session.commit()
    with app.test_client() as client:
        response = client.put(
            f"/api/local-players/{ids['local']}/showcase/profile",
            headers={"Authorization": "Bearer " + tokens["player"]},
            json={"contract_status": "contracted", "club_program_id": ids["other_program"]},
        )
    assert response.status_code == 200, response.json


def test_source_owned_invitation_claim_in_erasure_batch(pg, monkeypatch):
    app, ids, tokens = setup_world(pg, monkeypatch, ("message_scout",), "ordinary")
    with app.app_context():
        invitation = ClubInvitation.query.filter_by(
            claim_id=ids["background_ordinary_claim"], program_id=ids["program"]
        ).one()
        invitation.created_by_user_id = ids["other_scout"]
        # Ownership is now solely source_manager_claim_id, the omitted branch
        # in the original prelocking selection. Keep an older request R too.
        db.session.get(ContactRequest, ids["request"]).club_consent_by_user_id = ids["owner"]
        db.session.commit()
    with app.test_client() as client:
        response = client.post(
            "/api/account/delete", headers={"Authorization": "Bearer " + tokens["club"]}, json={"confirm": "DELETE"}
        )
    assert response.status_code == 200, response.json
    with app.app_context():
        assert db.session.get(UserAccount, ids["owner"]) is None
        assert db.session.get(PlayerProfileClaim, ids["background_ordinary_claim"]) is not None
        assert db.session.get(UserAccount, ids["background_ordinary_user"]) is not None
