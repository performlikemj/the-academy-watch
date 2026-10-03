"""RC2V3 probes reversed into publication, retention and recovery regressions."""
# ruff: noqa: F811

from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubRosterMember, ClubSquad, FundingLeague
from src.models.highlights import HighlightFootageReview, HighlightRenderJob, HighlightTakedown, PlayerHighlight, now
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.video import VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services import highlights, highlights_storage
from src.workers import highlight_worker as worker
from test_highlights import approve, headers, pick, ready, world  # noqa: F401
from test_highlights_fix3 import base, review_recording


def storage(monkeypatch):
    monkeypatch.setattr(highlights_storage, "output_read_url", lambda *a, **k: "https://storage.example/clip.mp4")


def rename(w, name, writer):
    if writer == "sql":
        if db.engine.dialect.name != "postgresql":
            pytest.skip("PostgreSQL source trigger")
        db.session.execute(
            sa.text("UPDATE c2_checks.club_squads SET name=:name WHERE id=:id"), {"name": name, "id": w["squad"].id}
        )
    elif writer == "route":
        res = (
            w["app"]
            .test_client()
            .patch(
                f"/api/club/{w['program'].id}/squads/{w['squad'].id}",
                headers=headers(w["stranger"]),
                json={"name": name},
            )
        )
        assert res.status_code == 200, res.json
    else:
        w["squad"].name = name
    db.session.commit()
    db.session.expire_all()


@pytest.mark.parametrize("writer", ["orm", "route", "sql"])
@pytest.mark.parametrize("raw_expired", [False, True])
@pytest.mark.parametrize("flag_on", [False, True])
def test_o3_cosmetic_rename_preserves_clip_and_asset(world, monkeypatch, writer, raw_expired, flag_on):
    from src.routes.club import club_bp
    from src.services.video_retention import expire_raw_footage

    world["app"].register_blueprint(club_bp, url_prefix="/api")
    world["match"].match_date = (now() - timedelta(days=80)).date()
    world["match"].uploaded_at = now() - timedelta(days=80)
    world["match"].created_at = world["match"].uploaded_at
    world["match"].expires_at = world["match"].uploaded_at + timedelta(days=90)
    db.session.commit()
    assert review_recording(world).status_code == 200
    row = ready(world)
    assert approve(world, row).status_code == 200
    storage(monkeypatch)
    deleted = []
    monkeypatch.setattr("src.services.video_storage.delete_blob", lambda path: deleted.append(path) or True)
    if raw_expired:
        assert expire_raw_footage(now=now() + timedelta(days=11))["expired"] == 1
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
    path, context, fingerprint = row.output_blob_path, world["review"].source_context, row.source_fingerprint
    db.session.add(
        ClubAccessGrant(
            program_id=world["program"].id,
            user_account_id=world["stranger"].id,
            role="manager",
            all_squads=True,
            status="active",
            source="invite",
            granted_by_user_id=world["manager"].id,
        )
    )
    db.session.commit()
    assert (
        client.post(
            base(world) + "/highlight-review",
            headers=headers(world["stranger"]),
            json={"classification": "adult_only", "all_visible_people_adults": True},
        ).status_code
        == 403
    )
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1" if flag_on else "0")
    rename(world, "  FIRST   TEAM  ", writer)
    assert row.revoked_at is None
    assert row.source_fingerprint == fingerprint
    assert world["review"].source_context == context
    assert not HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).count()
    assert path not in deleted
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "1")
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302


@pytest.mark.parametrize("writer", ["orm", "sql"])
@pytest.mark.parametrize("unsafe", ["U16", "Friendlies"])
def test_o3_unsafe_rename_revert_permanently_invalidates(world, monkeypatch, writer, unsafe):
    row = ready(world)
    assert approve(world, row).status_code == 200
    storage(monkeypatch)
    rename(world, unsafe, writer)
    rename(world, "First team", writer)
    assert row.revoked_at is not None
    assert world["review"].source_context is None
    assert world["app"].test_client().get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert pick(world).status_code == 422
    assert review_recording(world).status_code == 200
    response = pick(world)
    assert response.status_code == 201 and response.json["player_decision"] == "pending"


YOUTH = [
    "Youths",
    "Juveniles",
    "Cadets",
    "Minors",
    "Fifteens",
    "Fourteens",
    "Seventeens",
    "Sixteen",
    "U Sixteen",
    "U-Fifteen",
    "Junioren",
    "Juniores",
    "Children",
    "Teen",
    "Teenagers",
    "Boy",
    "Girl",
    "Mini",
    "Colt",
    "Infantil",
    "Varsity",
    "Development",
    "Underage",
]


@pytest.mark.parametrize("label", YOUTH)
def test_o1_youth_stems_never_attestable(world, label):
    world["squad"].name = label
    db.session.commit()
    result = review_recording(world, squad_adult_attested=True)
    assert result.status_code == 422 and result.json["error"] == "youth_recording_private"
    assert pick(world).status_code == 422


@pytest.mark.parametrize(
    "label", ["Friendlies", "Sunday League", "XVIII", "MU16", "FC 1909", "First Team 2025", "Seniors 2025/26"]
)
def test_o1_o7_ambiguous_names_require_verified_attestation(world, label):
    world["squad"].name = label
    db.session.commit()
    result = review_recording(world)
    assert result.status_code == 422 and result.json["error"] == "senior_squad_attestation_required"
    result = review_recording(world, squad_adult_attested="true")
    assert result.status_code == 422
    assert review_recording(world, squad_adult_attested=True).status_code == 200
    assert world["review"].squad_adult_attested is True
    assert pick(world).status_code == 201


@pytest.mark.parametrize(
    "label", ["First Team", "Reserves", "Seniors", "Men", "Women", "Ladies", "Vets", "A Team", "B Team"]
)
def test_o1_known_senior_allowlist(label):
    assert highlights.squad_classification(SimpleNamespace(name=label, kind="first_team", age_limit=None)) == "adult"


@pytest.mark.parametrize("match_kind", ["none", "unknown", "senior"])
def test_o2_member_youth_squad_vetoes_whole_recording(world, match_kind):
    youth = ClubSquad(program_id=world["program"].id, name="U16", kind="age_group", age_limit=16)
    db.session.add(youth)
    db.session.flush()
    world["member"].squad_id = youth.id
    if match_kind == "none":
        world["match"].squad_id = None
    elif match_kind == "unknown":
        squad = ClubSquad(program_id=world["program"].id, name="Friendlies", kind="other")
        db.session.add(squad)
        db.session.flush()
        world["match"].squad_id = squad.id
    db.session.commit()
    res = review_recording(world, squad_adult_attested=True)
    assert res.status_code == 422 and res.json["error"] == "youth_recording_private"
    listed = world["app"].test_client().get(base(world) + "/highlights", headers=headers(world["manager"])).json
    assert listed["recording_block_reason"] == "youth_recording_private"
    assert not listed["candidates"]
    assert pick(world).status_code == 422


@pytest.mark.parametrize("writer", ["orm", "sql"])
def test_o2_member_squad_context_invalidates_on_edit_and_revert(world, monkeypatch, writer):
    other = ClubSquad(program_id=world["program"].id, name="Reserves", kind="reserves")
    db.session.add(other)
    db.session.flush()
    world["member"].squad_id = other.id
    db.session.commit()
    assert review_recording(world).status_code == 200
    row = ready(world)
    assert approve(world, row).status_code == 200
    storage(monkeypatch)
    match_squad = world["squad"]
    world["squad"] = other
    rename(world, "U16", writer)
    rename(world, "Reserves", writer)
    world["squad"] = match_squad
    assert row.revoked_at and world["review"].source_context is None
    assert pick(world).status_code == 422


@pytest.mark.parametrize("suspended", ["player", "stranger"])
@pytest.mark.parametrize("binding", ["local", "signed"])
def test_x1_suspension_never_resolves_approved_ambiguity(world, monkeypatch, suspended, binding):
    row = ready(world)
    assert approve(world, row).status_code == 200
    competing = PlayerProfileClaim(
        user_account_id=world["stranger"].id,
        relationship_type="player",
        status="approved",
        **(
            {"local_player_id": world["local"].id}
            if binding == "local"
            else {"player_api_id": world["local"].api_player_id}
        ),
    )
    db.session.add(competing)
    db.session.commit()
    storage(monkeypatch)
    client = world["app"].test_client()
    for state in ("active", "suspended", "active"):
        world[suspended].account_status = state
        db.session.commit()
        assert client.get(f"/api/highlights/{row.id}/clip").status_code == 404
        assert not client.get(f"/api/programs/{world['program'].slug}/highlights").json["highlights"]
        assert pick(world).status_code == 422
        assert row.revoked_at is None
    competing.status = "rejected"
    db.session.commit()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302


def test_x1_storage_boundary_rechecks_suspended_competitor(world, monkeypatch):
    row = ready(world)
    assert approve(world, row).status_code == 200

    def changed(*args, **kwargs):
        world["stranger"].account_status = "suspended"
        db.session.add(
            PlayerProfileClaim(
                local_player_id=world["local"].id,
                user_account_id=world["stranger"].id,
                status="approved",
                relationship_type="player",
            )
        )
        db.session.commit()
        return "https://storage.example/clip.mp4"

    monkeypatch.setattr(highlights_storage, "output_read_url", changed)
    assert world["app"].test_client().get(f"/api/highlights/{row.id}/clip").status_code == 404
    assert row.revoked_at is None


@pytest.mark.parametrize("state", ["pending", "hidden", "unapproved_league"])
def test_o4_club_admission_matches_public_page(world, state):
    from src.routes.funding import funding_bp

    world["app"].register_blueprint(funding_bp, url_prefix="/api")
    if state == "pending":
        world["program"].platform_status = "pending"
    elif state == "hidden":
        world["program"].emergency_hidden = True
    else:
        db.session.get(FundingLeague, world["program"].funding_league_id).registry_status = "proposed"
    db.session.commit()
    client = world["app"].test_client()
    root = f"/api/programs/{world['program'].slug}"
    assert client.get(root).status_code == 404
    assert client.get(root + "/highlights").status_code == 404
    assert client.get("/api/programs/unknown/highlights").status_code == 404


def test_o5_held_windows_are_not_offered(world):
    db.session.add(HighlightTakedown(id=str(uuid4()), video_match_id=world["match"].id, start_s=29.5, end_s=40))
    db.session.commit()
    listed = world["app"].test_client().get(base(world) + "/highlights", headers=headers(world["manager"])).json
    assert not listed["candidates"]
    assert pick(world).status_code == 422


def test_o6_claim_checks_are_linear(world, monkeypatch):
    n = 24
    entries = []
    for i in range(n):
        user = UserAccount(email=f"cross{i}@example.test", display_name=f"Cross {i}", display_name_lower=f"cross {i}")
        local = LocalPlayer(
            display_name=f"Adult {i}",
            status="approved",
            birth_date=date(1998, 1, 1),
            birth_year=1998,
            provenance="user",
        )
        db.session.add_all([user, local])
        db.session.flush()
        local.api_player_id = -local.id
        claim = PlayerProfileClaim(
            local_player_id=local.id, user_account_id=user.id, relationship_type="player", status="approved"
        )
        member = ClubRosterMember(
            program_id=world["program"].id,
            local_player_id=local.id,
            added_by_user_id=world["manager"].id,
            squad_id=world["squad"].id,
        )
        db.session.add_all([claim, member])
        db.session.flush()
        entry = VideoRosterEntry(
            video_match_id=world["match"].id,
            player_name=f"Adult {i}",
            jersey_number=20 + i,
            club_roster_member_id=member.id,
        )
        db.session.add(entry)
        db.session.flush()
        track = VideoTracklet(
            video_match_id=world["match"].id,
            roster_entry_id=entry.id,
            kind="chain",
            team_cluster=0,
            tag_source="human",
            review_action="confirmed",
            reviewed_at=now(),
            confidence="high",
            first_s=40,
            last_s=55,
        )
        report = VideoPlayerReport(
            video_match_id=world["match"].id,
            roster_entry_id=entry.id,
            identity_confidence="human_confirmed",
            club_program_id_at_finalize=world["program"].id,
            club_roster_member_id_at_finalize=member.id,
            club_local_player_id_at_finalize=local.id,
            model_version="test",
        )
        db.session.add_all([track, report])
        entries.append((user, entry, track))
    db.session.commit()
    assert review_recording(world).status_code == 200
    for user, entry, track in entries:
        p = pick(world, roster_entry_id=entry.id, tracklet_id=track.id, start_s=40, end_s=55)
        assert p.status_code == 201, p.json
        row = db.session.get(PlayerHighlight, p.json["id"])
        assert worker.finish(*worker.claim_next(), output_etag="clip-v1", output_size=20)
        a = (
            world["app"]
            .test_client()
            .post(
                f"/api/me/highlight-requests/{row.id}/decision",
                headers=headers(user),
                json={"decision": "approve", "version": row.version},
            )
        )
        assert a.status_code == 200, a.json
    calls = []
    real = highlights.own_claim

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(highlights, "own_claim", counted)
    r = world["app"].test_client().get(f"/api/programs/{world['program'].slug}/highlights")
    assert r.status_code == 200 and len(r.json["highlights"]) == n
    assert len(calls) <= 2 * n
    print("O6 clips=", n, "loaded claims=", n + 1, "own_claim evaluations=", len(calls))


def test_o3_sql_classification_and_context_agree_with_runtime(world):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL classifier parity")
    for label in YOUTH + [
        "Ｕ１８",
        "U٨",
        "U१२",
        "First Team",
        "  FIRST  TEAM ",
        "1st XI",
        "2nd XI",
        "U21",
        "FC 1909",
        "Seniors 2025/26",
        "Friendlies",
        "MU16",
        "18s",
        "12 & under",
        "Age 15",
        "2012B",
        "B2012",
        "U2010",
    ]:
        for kind, limit in [
            ("first_team", None),
            ("reserves", None),
            ("other", None),
            ("age_group", 21),
            ("first_team", 16),
        ]:
            got = db.session.execute(
                sa.text("SELECT c2_checks.p2c2_squad_classification(:label,:kind,:lim)"),
                dict(label=label, kind=kind, lim=limit),
            ).scalar()
            assert got == highlights.squad_classification(SimpleNamespace(name=label, kind=kind, age_limit=limit)), (
                label,
                kind,
                limit,
                got,
            )
    got = db.session.execute(sa.text("SELECT c2_checks.p2c2_context_hash(:id)"), {"id": world["match"].id}).scalar()
    assert got == highlights.review_context(world["match"])


@pytest.mark.parametrize("valid", [False, True])
@pytest.mark.parametrize("label", ["First team", "Ｆｉｒｓｔ　ｔｅａｍ"])
def test_o3_checked_legacy_context_transition_preserves_only_valid_consent(world, monkeypatch, valid, label):
    from pathlib import Path

    if db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL preapply compatibility")
    world["squad"].name = label
    db.session.commit()
    assert review_recording(world).status_code == 200
    row = ready(world)
    assert approve(world, row).status_code == 200
    squad, match = world["squad"], world["match"]
    legacy = highlights.digest(
        [match.match_date, match.squad_id, match.finalized_at, [squad.name, squad.kind, squad.age_limit]]
    )
    db.session.connection().exec_driver_sql("DROP TRIGGER p2c2_source_guard ON c2_checks.highlight_footage_reviews")
    db.session.connection().execute(
        sa.update(HighlightFootageReview)
        .where(HighlightFootageReview.video_match_id == match.id)
        .values(source_context=legacy if valid else None, classification_context=None)
    )
    db.session.expire_all()
    fingerprint = highlights.source_fingerprint(match, world["entry"], world["track"])
    db.session.connection().execute(
        sa.update(PlayerHighlight).where(PlayerHighlight.id == row.id).values(source_fingerprint=fingerprint)
    )
    db.session.commit()
    sql = (
        (Path(__file__).parents[1] / "migrations/maintenance/p2c2_source_guards.sql")
        .read_text()
        .replace("public.", "c2_checks.")
    )
    for _ in range(2):
        db.session.execute(sa.text(sql))
        db.session.commit()
    db.session.expire_all()
    assert (world["review"].classification_context == highlights.review_context(match)) is valid
    storage(monkeypatch)
    if valid:
        rename(world, "First Team", "orm")
        assert row.revoked_at is None and row.source_fingerprint == fingerprint
    assert world["app"].test_client().get(f"/api/highlights/{row.id}/clip").status_code == (302 if valid else 404)
