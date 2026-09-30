"""Private player-page, pathway, ownership and photo authorization contracts."""

# ruff: noqa: F811
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image
from src.models.contact import ContactRequest
from src.models.funding import ClubRosterMember, ClubRosterSquadHistory
from src.models.league import db
from src.models.showcase import LocalPlayer, PlayerProfileClaim, PlayerShowcaseMedia
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoPlayerReport
from src.services import showcase_media_storage as storage
from test_club_console import (
    _add_api_member,
    _admin_headers,
    _grant_program_manager,
    _headers,
    _reel_evidence,
    _result_payload,
)
from test_club_console import client as client
from test_club_console import club_app as club_app
from test_club_home import call


def local_member(client, app, *, year=2000, name="Fictional Rowan Vale", squad=None):
    response = client.post(
        "/api/local-players",
        headers=_headers("a"),
        json={
            "display_name": name,
            "birth_year": year,
            "club_program_id": app.c2["program_a"],
            "squad_id": squad,
        },
    )
    assert response.status_code == 201, response.json
    return response.json["member"]["id"], response.json["player"]["id"]


def squad(client, app, name):
    return call(client, app, "post", "squads", {"name": name, "kind": "age_group"}).json["squad"]["id"]


def test_pathway_all_assignment_paths(club_app, client):
    first, second = squad(client, club_app, "U16"), squad(client, club_app, "U18")
    mid = call(client, club_app, "post", "roster", {"player_api_id": 7001, "squad_id": first}).json["member"]["id"]

    def rows():
        return ClubRosterSquadHistory.query.filter_by(roster_member_id=mid).order_by(ClubRosterSquadHistory.id).all()

    assert [r.squad_id for r in rows()] == [first]
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": first, "shirt_number": 8}).status_code == 200
    assert len(rows()) == 1
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": second}).status_code == 200
    assert [r.squad_id for r in rows()] == [first, second]
    assert rows()[0].ended_at == rows()[1].started_at
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": None}).status_code == 200
    assert rows()[-1].squad_id is None and rows()[-2].ended_at
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": first}).status_code == 200
    assert call(client, club_app, "delete", f"squads/{first}").status_code == 200
    assert rows()[-1].squad_id is None and rows()[-1].ended_at is None
    assert all(r.ended_at for r in rows()[:-1])
    assert [r.squad_name for r in rows()] == ["U16", "U18", None, "U16", None]
    assert [h["squad_name"] for h in call(client, club_app, "get", f"roster/{mid}/profile").json["pathway"]] == [
        "U16",
        "U18",
        "Unassigned / deleted squad",
        "U16",
        "Unassigned / deleted squad",
    ]
    assert call(client, club_app, "delete", f"roster/{mid}").status_code == 204
    assert not rows()  # required ON DELETE CASCADE: no orphan history survives removal
    local_mid, _ = local_member(client, club_app, squad=second)
    assert ClubRosterSquadHistory.query.filter_by(roster_member_id=local_mid, squad_id=second).count() == 1


def test_failed_assignment_rolls_back_history(club_app, client):
    sid = squad(client, club_app, "U18")
    call(client, club_app, "post", "roster", {"player_api_id": 7001, "squad_id": sid, "shirt_number": 8})
    mid = _add_api_member(client, club_app.c2["program_a"], 7002)
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": sid, "shirt_number": 8}).status_code == 409
    assert ClubRosterSquadHistory.query.filter_by(roster_member_id=mid).count() == 0
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": sid, "note": "x" * 501}).status_code == 422
    assert ClubRosterSquadHistory.query.filter_by(roster_member_id=mid).count() == 0


def test_same_manager_cannot_attach_other_origin(club_app, client):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    _grant_program_manager(b, club_app.c2["users"]["a"])
    mid, local_id = local_member(client, club_app)
    assert db.session.get(LocalPlayer, local_id).origin_program_id == a
    assert (
        client.post(f"/api/club/{b}/roster", json={"local_player_id": local_id}, headers=_headers("a")).status_code
        == 404
    )
    assert client.get(f"/api/club/{b}/available-local-players", headers=_headers("a")).json["players"] == []
    assert call(client, club_app, "delete", f"roster/{mid}").status_code == 204
    assert call(client, club_app, "get", "available-local-players").json["players"][0]["id"] == local_id
    assert call(client, club_app, "post", "roster", {"local_player_id": local_id}).status_code == 201
    _grant_program_manager(a, club_app.c2["users"]["b"])
    assert call(client, club_app, "get", "roster", key="b").status_code == 200


@pytest.fixture
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "")
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setattr(storage, "publish", lambda *args, **kw: pytest.fail("Private photo reached public storage"))
    return tmp_path


def upload(client, app, mid, raw=None):
    grant = call(client, app, "post", f"roster/{mid}/photo", {"content_type": "image/png"}).json
    if raw is None:
        stream = BytesIO()
        image = Image.new("RGB", (30, 30), "green")
        exif = Image.Exif()
        exif[270] = "Private metadata"
        image.save(stream, "PNG", exif=exif)
        raw = stream.getvalue()
    response = client.put(grant["upload"]["url"], data=raw, content_type="image/png")
    assert response.status_code == 201
    # Pending private photos cannot be fetched from the unauthenticated dev route.
    assert client.get(grant["upload"]["url"]).status_code == 404
    response = call(client, app, "post", f"roster/{mid}/photo/complete", {"upload_token": grant["upload_token"]})
    return response, grant


def test_photo_lifecycle_and_private_storage(club_app, client, private_storage):
    mid, _ = local_member(client, club_app, year=date.today().year - 15)
    response, grant = upload(client, club_app, mid)
    assert response.status_code == 200, response.json
    member = db.session.get(ClubRosterMember, mid)
    previous = member.photo_path
    assert previous.startswith(f"club-player-photos/{member.program_id}/{mid}/") and previous.endswith(".jpg")
    assert "/api/club/" in response.json["photo"]["url"]
    assert not (private_storage / "public").exists()
    assert call(client, club_app, "get", f"roster/{mid}/photo").headers["Cache-Control"] == "private, no-store"
    with Image.open(BytesIO(call(client, club_app, "get", f"roster/{mid}/photo").data)) as decoded:
        assert decoded.format == "JPEG" and not decoded.getexif()
    assert (
        call(
            client, club_app, "post", f"roster/{mid}/photo/complete", {"upload_token": grant["upload_token"]}
        ).status_code
        == 422
    )
    assert upload(client, club_app, mid)[0].status_code == 200
    assert not storage.local_club_photo_path(previous).exists()
    current = member.photo_path
    assert call(client, club_app, "delete", f"roster/{mid}/photo").status_code == 200
    assert not storage.local_club_photo_path(current).exists()
    assert call(client, club_app, "get", f"roster/{mid}/photo").status_code == 404
    assert call(client, club_app, "delete", f"roster/{mid}/photo").status_code == 200
    assert upload(client, club_app, mid, b"invalid")[0].status_code == 422
    assert call(client, club_app, "post", f"roster/{mid}/photo", {"content_type": "image/gif"}).status_code == 422
    assert call(client, club_app, "post", f"roster/{mid}/photo/complete", {"upload_token": "bad"}).status_code == 404


@pytest.mark.parametrize(
    "method,suffix",
    [("get", "profile"), ("get", "photo"), ("post", "photo"), ("delete", "photo"), ("post", "photo/complete")],
)
def test_player_routes_are_program_scoped(club_app, client, private_storage, method, suffix):
    mid = _add_api_member(client, club_app.c2["program_a"])
    assert call(client, club_app, method, f"roster/{mid}/{suffix}", {}, key="scout").status_code == 403
    response = getattr(client, method)(
        f"/api/club/{club_app.c2['program_b']}/roster/{mid}/{suffix}", json={}, headers=_headers("b")
    )
    assert response.status_code == 404 and response.json == {"error": "Not found"}


def test_upload_token_is_member_and_actor_bound(club_app, client, private_storage):
    first = _add_api_member(client, club_app.c2["program_a"])
    second = _add_api_member(client, club_app.c2["program_a"], 7002)
    grant = call(client, club_app, "post", f"roster/{first}/photo", {"content_type": "image/jpeg"}).json
    assert (
        call(
            client, club_app, "post", f"roster/{second}/photo/complete", {"upload_token": grant["upload_token"]}
        ).status_code
        == 404
    )
    _grant_program_manager(club_app.c2["program_a"], club_app.c2["users"]["b"])
    assert (
        call(
            client, club_app, "post", f"roster/{first}/photo/complete", {"upload_token": grant["upload_token"]}, key="b"
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "minor,approved,claimed,club_photo,expected",
    [
        (False, True, True, True, "player"),
        (True, True, True, True, "club"),
        (False, False, True, True, "club"),
        (False, True, False, True, "club"),
        (False, False, False, False, "tracked"),
        (True, False, False, True, "club"),
    ],
)
def test_photo_precedence(club_app, client, private_storage, minor, approved, claimed, club_photo, expected):
    mid = _add_api_member(client, club_app.c2["program_a"])
    tracked = TrackedPlayer.query.filter_by(player_api_id=7001).first()
    tracked.birth_date = date(date.today().year - (15 if minor else 25), 1, 1)
    tracked.photo_url = "https://example.invalid/provider.jpg"
    if claimed:
        db.session.add(
            PlayerProfileClaim(
                player_api_id=7001,
                user_account_id=club_app.c2["users"]["scout"],
                relationship_type="player",
                status="approved",
            )
        )
    db.session.add(
        PlayerShowcaseMedia(
            player_api_id=7001,
            uploaded_by_user_id=club_app.c2["users"]["scout"],
            is_primary=True,
            status="approved" if approved else "pending_review",
            blob_path="players/7001/photo.jpg",
            public_url="approved.jpg",
        )
    )
    db.session.commit()
    if club_photo:
        assert upload(client, club_app, mid)[0].status_code == 200
    data = call(client, club_app, "get", f"roster/{mid}/profile").json
    assert data["identity"]["photo"]["source"] == expected
    assert data["identity"]["claim_status"] == ("claimed" if claimed else "unclaimed")
    assert call(client, club_app, "get", "roster").json["members"][0]["photo"] == data["identity"]["photo"]
    if minor:
        assert data["scout_interest"]["locked"] is True


def test_profile_sections_are_only_existing_data(club_app, client, monkeypatch):
    mid = _add_api_member(client, club_app.c2["program_a"])
    response = call(client, club_app, "get", f"roster/{mid}/profile")
    assert response.status_code == 200
    assert set(response.json) == {"identity"}
    assert response.json["identity"]["photo"] is None
    sid = squad(client, club_app, "U18")
    call(client, club_app, "patch", f"roster/{mid}", {"squad_id": sid, "note": "Private context"})
    call(client, club_app, "put", f"roster/{mid}/brief", {"body": "Scan before receiving"})
    result = call(client, club_app, "post", "results", _result_payload([mid], match_date=date.today().isoformat()))
    assert result.status_code == 201, result.json
    match, entry, _ = _reel_evidence(club_app.c2["program_a"], mid)
    match.status = "finalized"
    db.session.add(
        VideoPlayerReport(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=match.club_program_id,
            club_roster_member_id_at_finalize=mid,
            club_player_api_id_at_finalize=7001,
            identity_confidence="human_confirmed",
            minutes_visible=12,
            model_version="test",
        )
    )
    db.session.commit()
    data = call(client, club_app, "get", f"roster/{mid}/profile").json
    assert data["pathway"][0]["squad_name"] == "U18"
    assert data["note"] == "Private context"
    assert data["coach_brief"]["lines"] == ["Scan before receiving"]
    assert data["results"]["season"] == {"year": 2026, "apps": 1, "minutes": 90, "goals": 1, "assists": 0}
    assert data["film"][0]["reel_available"] and data["film"][0]["report_url"]
    assert data["film"][0]["minutes_visible"] == 12
    assert "starts" not in data["results"]["season"]


def test_scout_interest_uses_club_inbox_scope(club_app, client, monkeypatch):
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "1")
    mid = _add_api_member(client, club_app.c2["program_a"])
    db.session.add(
        ContactRequest(
            scout_user_id=club_app.c2["users"]["scout"],
            player_api_id=7001,
            club_program_id=club_app.c2["program_a"],
            routing_mode="club_included",
            message="Fictional test introduction",
            expires_at=datetime.now(UTC) + timedelta(days=5),
        )
    )
    db.session.commit()
    data = call(client, club_app, "get", f"roster/{mid}/profile").json
    assert len(data["scout_interest"]["requests"]) == 1
    row = ContactRequest.query.first()
    row.club_program_id = club_app.c2["program_b"]
    db.session.commit()
    assert "scout_interest" not in call(client, club_app, "get", f"roster/{mid}/profile").json


def test_admin_club_identities_auth_filter_and_existing_takedown(club_app, client):
    mid, lid = local_member(client, club_app, year=date.today().year - 15)
    url = "/api/admin/club-identities"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=_headers("a")).status_code in (401, 403)
    data = client.get(url, headers=_admin_headers()).json
    assert data["total"] == 1 and data["players"][0]["is_minor"]
    assert data["players"][0]["memberships"][0]["member_id"] == mid
    assert client.get(f"{url}?program_id={club_app.c2['program_b']}", headers=_admin_headers()).json["players"] == []
    assert client.get(f"{url}?program_id={club_app.c2['program_a']}", headers=_admin_headers()).json["total"] == 1
    assert client.get(f"{url}?program_id=oops", headers=_admin_headers()).status_code == 400
    assert (
        client.post(
            f"/api/local-players/{lid}/takedown-request",
            json={
                "requester_role": "club",
                "contact_email": "review@example.test",
                "statement": "Fictional safeguarding test",
            },
        ).status_code
        == 202
    )
    queue = client.get("/api/admin/suppressions", headers=_admin_headers()).json["suppressions"]
    assert (
        client.post(
            f"/api/admin/suppressions/{queue[0]['id']}/activate",
            headers=_admin_headers(),
            json={"notes": "Fictional review"},
        ).status_code
        == 200
    )
    assert call(client, club_app, "get", f"roster/{mid}/profile").status_code == 404
    assert client.get(url, headers=_admin_headers()).json["players"][0]["suppressed"]


def test_azure_private_container_never_public(monkeypatch):
    monkeypatch.setattr(storage, "is_azure_configured", lambda: True)
    monkeypatch.setattr(storage, "is_configured", lambda: True)
    service = MagicMock()
    container = service.get_container_client.return_value
    container.get_container_properties.return_value = {"public_access": None}
    monkeypatch.setattr(storage, "_service_client", lambda: service)
    path = storage.store_club_photo("club-player-photos/1/2/abc.png", b"jpeg")
    assert path == "club-player-photos/1/2/abc.jpg"
    service.get_container_client.assert_called_once_with("club-player-photos-private")
    container.create_container.assert_called_once_with(public_access=None)
    container.get_blob_client.assert_called_once_with(path)
    container.get_container_properties.return_value = {"public_access": "blob"}
    with pytest.raises(storage.StorageNotConfiguredError):
        storage.store_club_photo(path, b"jpeg")
    monkeypatch.setenv("CLUB_PLAYER_PHOTOS_CONTAINER", storage._public_container())
    with pytest.raises(storage.StorageNotConfiguredError):
        storage.store_club_photo(path, b"jpeg")


def test_photo_caps_preserve_previous_photo(club_app, client, private_storage, monkeypatch):
    from src.services import photo_processing

    mid = _add_api_member(client, club_app.c2["program_a"])
    assert upload(client, club_app, mid)[0].status_code == 200
    previous = db.session.get(ClubRosterMember, mid).photo_path
    monkeypatch.setattr(photo_processing, "MAX_SOURCE_PIXELS", 100)
    assert upload(client, club_app, mid)[0].status_code == 422
    assert db.session.get(ClubRosterMember, mid).photo_path == previous
    assert storage.local_club_photo_path(previous).exists()


def test_ch02_chain_and_preapply_are_exact():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "ch02", root / "academy-watch-backend/migrations/versions/ch02_club_player_pages.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "ch02" and module.down_revision == "ch01"
    preapply = (root / "ledgers/tooling/club-home/ch02_preapply.sql").read_text()
    assert preapply.split("BEGIN;\n", 1)[1].removesuffix("COMMIT;\n").strip() == module.UPGRADE_SQL.strip()


def test_profile_does_not_attribute_rebound_report(club_app, client):
    first = _add_api_member(client, club_app.c2["program_a"])
    second = _add_api_member(client, club_app.c2["program_a"], 7002)
    match, entry, _ = _reel_evidence(club_app.c2["program_a"], first)
    match.status = "finalized"
    db.session.add(
        VideoPlayerReport(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=match.club_program_id,
            club_roster_member_id_at_finalize=first,
            club_player_api_id_at_finalize=7001,
            identity_confidence="human_confirmed",
            minutes_visible=12,
            model_version="test",
        )
    )
    entry.club_roster_member_id = second
    db.session.commit()
    film = call(client, club_app, "get", f"roster/{second}/profile").json["film"][0]
    assert film["report_url"] is None and film["minutes_visible"] is None


def test_photo_expired_grant_and_byte_cap(club_app, client, private_storage, monkeypatch):
    import time
    from unittest.mock import patch

    mid = _add_api_member(client, club_app.c2["program_a"])
    with patch("itsdangerous.timed.time.time", return_value=time.time() - 4000):
        grant = call(client, club_app, "post", f"roster/{mid}/photo", {"content_type": "image/png"}).json
    assert (
        call(
            client, club_app, "post", f"roster/{mid}/photo/complete", {"upload_token": grant["upload_token"]}
        ).status_code
        == 404
    )
    grant = call(client, club_app, "post", f"roster/{mid}/photo", {"content_type": "image/png"}).json
    storage.local_pending_path(grant["upload"]["blob_path"], True).write_bytes(b"x" * 20)
    monkeypatch.setattr(storage, "max_photo_bytes", lambda: 10)
    assert (
        call(
            client, club_app, "post", f"roster/{mid}/photo/complete", {"upload_token": grant["upload_token"]}
        ).status_code
        == 422
    )
    assert db.session.get(ClubRosterMember, mid).photo_path is None


def test_roster_photo_queries_are_constant_and_brief_needs_none(club_app, client):
    from sqlalchemy import event

    statements = []

    def count_photo_reads(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and any(
            f"FROM {table}" in statement for table in ("player_profile_claims", "player_showcase_media")
        ):
            statements.append(statement)

    def add_members(start, stop):
        for i in range(start, stop):
            player = LocalPlayer(
                display_name=f"Fictional Batch {i}",
                birth_year=2000,
                created_by_user_id=club_app.c2["users"]["a"],
                provenance="user",
                status="approved",
            )
            db.session.add(player)
            db.session.flush()
            player.api_player_id = -player.id
            db.session.add(
                ClubRosterMember(
                    program_id=club_app.c2["program_a"],
                    local_player_id=player.id,
                    added_by_user_id=club_app.c2["users"]["a"],
                )
            )
            owner = club_app.c2["users"]["scout"]
            db.session.add(
                PlayerProfileClaim(
                    local_player_id=player.id, user_account_id=owner, relationship_type="player", status="approved"
                )
            )
            db.session.add(
                PlayerShowcaseMedia(
                    local_player_id=player.id,
                    uploaded_by_user_id=owner,
                    status="approved",
                    is_primary=True,
                    blob_path=f"batch/{i}.jpg",
                    public_url=f"batch/{i}.jpg",
                )
            )
        db.session.commit()
        db.session.remove()  # cold session; do not hide queries in the identity map

    engine = db.engine
    event.listen(engine, "before_cursor_execute", count_photo_reads)
    try:
        counts = []
        for start, stop in ((0, 3), (3, 30)):
            add_members(start, stop)
            statements.clear()
            response = call(client, club_app, "get", "roster")
            assert response.status_code == 200
            assert len(response.json["members"]) == stop
            assert all(m["photo"]["source"] == "player" for m in response.json["members"])
            counts.append(len(statements))
        assert counts == [2, 2]
        statements.clear()
        # Calling validation directly isolates it from the brief response serializer.
        from src.models.funding import ClubProgram
        from src.routes.club import _brief_name_tokens

        assert _brief_name_tokens(db.session.get(ClubProgram, club_app.c2["program_a"]))
        assert statements == []
    finally:
        event.remove(engine, "before_cursor_execute", count_photo_reads)


def test_batch_photos_keep_owners_scoped_to_each_subject(club_app, client, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test")
    from types import SimpleNamespace

    from src.services.club_player_profile import prefetch_member_photos

    mid, lid = local_member(client, club_app)
    owner, other = club_app.c2["users"]["a"], club_app.c2["users"]["b"]
    db.session.add_all(
        [
            PlayerProfileClaim(
                local_player_id=lid, user_account_id=owner, relationship_type="player", status="approved"
            ),
            PlayerProfileClaim(player_api_id=lid, user_account_id=other, relationship_type="player", status="approved"),
            PlayerShowcaseMedia(
                local_player_id=lid,
                uploaded_by_user_id=other,
                status="approved",
                is_primary=True,
                blob_path="wrong.jpg",
                public_url="wrong.jpg",
            ),
            PlayerShowcaseMedia(
                player_api_id=lid,
                uploaded_by_user_id=other,
                status="approved",
                is_primary=True,
                blob_path="right.jpg",
                public_url="right.jpg",
            ),
        ]
    )
    db.session.commit()
    photos = prefetch_member_photos(
        [
            db.session.get(ClubRosterMember, mid),
            SimpleNamespace(local_player_id=None, player_api_id=lid),
        ]
    )
    assert photos == {("tracked", lid): "https://api.example.test/api/media/published/right.jpg"}


@pytest.mark.parametrize("status,consent", [("pending", "pending"), ("accepted", "pending")])
def test_profile_expires_visible_introductions(club_app, client, monkeypatch, status, consent):
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "1")
    mid = _add_api_member(client, club_app.c2["program_a"])
    visible = ContactRequest(
        scout_user_id=club_app.c2["users"]["scout"],
        player_api_id=7001,
        club_program_id=club_app.c2["program_a"],
        routing_mode="club_included",
        message="Fictional expired introduction",
        status=status,
        club_consent_status=consent,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    hidden = ContactRequest(
        scout_user_id=club_app.c2["users"]["b"],
        player_api_id=7001,
        club_program_id=club_app.c2["program_b"],
        routing_mode="club_included",
        message="Fictional other club introduction",
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.session.add_all([visible, hidden])
    db.session.commit()
    data = call(client, club_app, "get", f"roster/{mid}/profile").json
    assert data["scout_interest"]["requests"][0]["status"] == "expired"
    db.session.refresh(visible)
    db.session.refresh(hidden)
    assert visible.status == "expired"
    assert hidden.status == "pending"
