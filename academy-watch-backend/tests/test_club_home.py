# ruff: noqa: F811

"""Private Club Home contracts and cross-program boundaries."""

from io import BytesIO

import pytest
from PIL import Image
from src.models.funding import ClubProgram
from src.models.league import db
from src.routes.club_home import contrast
from src.services import showcase_media_storage as storage
from test_club_console import _add_api_member, _headers, client, club_app  # noqa: F401
from test_club_results import rate_limited_club_app  # noqa: F401


def call(client, club_app, method, path, data=None, key="a"):
    return getattr(client, method)(f"/api/club/{club_app.c2['program_a']}/{path}", json=data, headers=_headers(key))


def test_squad_lifecycle(club_app, client):
    template = call(client, club_app, "post", "squads/template", {}).get_json()["squads"]
    assert len(template) == 5
    assert call(client, club_app, "post", "squads/template", {}).status_code == 409
    ids = [s["id"] for s in template][::-1]
    result = call(client, club_app, "post", "squads/reorder", {"ids": ids})
    assert [s["id"] for s in result.json["squads"]] == ids
    assert call(client, club_app, "post", "squads/reorder", {"ids": [ids[0]]}).status_code == 404
    sid = ids[0]
    assert call(client, club_app, "patch", f"squads/{sid}", {"name": "Fictional Youth"}).status_code == 200
    assert call(client, club_app, "post", "squads", {"name": "fictional youth", "kind": "other"}).status_code == 409
    member = _add_api_member(client, club_app.c2["program_a"])
    assert call(client, club_app, "patch", f"roster/{member}", {"squad_id": sid, "shirt_number": 9}).status_code == 200
    assert len(call(client, club_app, "get", f"roster?squad_id={sid}").json["members"]) == 1
    assert call(client, club_app, "get", "roster?squad_id=none").json["members"] == []
    assert call(client, club_app, "delete", f"squads/{sid}").status_code == 200
    assert call(client, club_app, "get", "roster?squad_id=none").json["members"][0]["squad_id"] is None
    assert len(call(client, club_app, "get", "squads").json["squads"]) == 4


def test_staff_graph(club_app, client):
    first = call(
        client, club_app, "post", "staff", {"display_name": "Fictional Director", "title": "Sporting Director"}
    ).json["staff"]["id"]
    second = call(
        client,
        club_app,
        "post",
        "staff",
        {"display_name": "Fictional Coach", "title": "Coach", "reports_to_staff_id": first},
    ).json["staff"]["id"]
    assert call(client, club_app, "patch", f"staff/{first}", {"reports_to_staff_id": second}).status_code == 422
    assert call(client, club_app, "patch", f"staff/{first}", {"reports_to_staff_id": first}).status_code == 422
    foreign = client.post(
        f"/api/club/{club_app.c2['program_b']}/staff",
        json={"display_name": "Other Fictional Coach", "title": "Coach"},
        headers=_headers("b"),
    ).json["staff"]["id"]
    assert call(client, club_app, "patch", f"staff/{first}", {"reports_to_staff_id": foreign}).status_code == 404
    assert call(client, club_app, "patch", f"staff/{foreign}", {"title": "Director"}).status_code == 404
    assert call(client, club_app, "delete", f"staff/{foreign}").status_code == 404
    assert call(client, club_app, "patch", f"staff/{second}", {"title": "Head Coach"}).status_code == 200
    assert call(client, club_app, "delete", f"staff/{first}").status_code == 200
    assert call(client, club_app, "get", "staff").json["staff"][0]["reports_to_staff_id"] is None


def test_assignments_and_map(club_app, client):
    squad = call(client, club_app, "post", "squads", {"name": "Youth", "kind": "age_group", "age_limit": 18}).json[
        "squad"
    ]
    sid = squad["id"]
    lead = call(
        client, club_app, "post", "staff", {"display_name": "Fictional Lead", "title": "Coach", "leads_squad_id": sid}
    ).json["staff"]["id"]
    first = call(client, club_app, "post", "roster", {"player_api_id": 7001, "squad_id": sid, "shirt_number": 8})
    assert first.status_code == 201
    second = call(client, club_app, "post", "roster", {"player_api_id": 7002, "squad_id": sid, "shirt_number": 8})
    assert second.status_code == 409 and second.json["error"] == "shirt_number_taken"
    mid = _add_api_member(client, club_app.c2["program_a"], 7002)
    assert call(client, club_app, "patch", f"roster/{mid}", {"squad_id": sid, "shirt_number": 8}).status_code == 409
    assert call(client, club_app, "patch", f"roster/{mid}", {"shirt_number": 100}).status_code == 422
    foreign = client.post(
        f"/api/club/{club_app.c2['program_b']}/squads", json={"name": "Other", "kind": "other"}, headers=_headers("b")
    ).json["squad"]["id"]
    for path, body in (
        (f"roster/{mid}", {"squad_id": foreign}),
        (f"staff/{lead}", {"leads_squad_id": foreign}),
        (f"squads/{foreign}", {"name": "Invalid"}),
    ):
        assert call(client, club_app, "patch", path, body).status_code == 404
    assert call(client, club_app, "get", f"roster?squad_id={foreign}").status_code == 404
    data = call(client, club_app, "get", "map").json
    assert set(data) == {"program", "staff", "squads", "unassigned_count"}
    assert data["squads"][0]["member_count"] == 1
    assert data["squads"][0]["lead_staff_id"] == lead
    assert data["unassigned_count"] == 1
    assert "members" not in data["squads"][0]
    assert "brand" in call(client, club_app, "get", "roster").json["program"]
    assert "brand" not in db.session.get(ClubProgram, club_app.c2["program_a"]).public_dict()


@pytest.mark.parametrize(
    "field,value",
    [
        ("primary_color", "red"),
        ("primary_color", "#FFF"),
        ("primary_color", "#FFFFFF"),
        ("accent_color", "#16201B"),
        ("primary_color", 123),
        ("accent_color", None),
    ],
)
def test_invalid_brand(club_app, client, field, value):
    response = call(client, club_app, "patch", "branding", {field: value})
    assert response.status_code == 422
    assert response.json["error"]


def test_contrast_and_brand(club_app, client):
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21)
    assert contrast("#123456", "#123456") == pytest.approx(1)
    assert contrast("#777777", "#FFFFFF") < 4.5
    assert contrast("#767676", "#FFFFFF") >= 4.5
    assert (
        call(client, club_app, "patch", "branding", {"primary_color": "#0f3d2e", "accent_color": "#E3B23C"}).json[
            "brand"
        ]["primary_color"]
        == "#0F3D2E"
    )


def test_banner(club_app, client, monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FLASK_ENV", "development")
    grant = call(client, club_app, "post", "branding/banner", {"content_type": "image/jpeg"}).json
    assert grant["upload"]["blob_path"].startswith(f"club-banners/{club_app.c2['program_a']}/")
    raw = BytesIO()
    exif = Image.Exif()
    exif[270] = "private metadata"
    Image.new("RGB", (120, 60), "green").save(raw, "JPEG", exif=exif)
    storage.local_pending_path(grant["upload"]["blob_path"], True).write_bytes(raw.getvalue())
    response = call(client, club_app, "post", "branding/banner/complete", {"upload_token": grant["upload_token"]})
    assert response.status_code == 200
    path = storage.local_public_path(storage._published_blob_path(grant["upload"]["blob_path"]))
    with Image.open(path) as image:
        assert not image.getexif()
        assert image.format == "JPEG"
    assert (
        call(client, club_app, "post", "branding/banner/complete", {"upload_token": grant["upload_token"]}).status_code
        == 422
    )
    assert call(client, club_app, "post", "branding/banner/complete", {"upload_token": "invalid"}).status_code == 404
    grant = call(client, club_app, "post", "branding/banner", {"content_type": "image/png"}).json
    storage.local_pending_path(grant["upload"]["blob_path"], True).write_bytes(b"not an image")
    assert (
        call(client, club_app, "post", "branding/banner/complete", {"upload_token": grant["upload_token"]}).status_code
        == 422
    )
    assert call(client, club_app, "post", "branding/banner", {"content_type": "image/gif"}).status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "squads"),
        ("post", "squads"),
        ("patch", "squads/1"),
        ("delete", "squads/1"),
        ("post", "squads/template"),
        ("post", "squads/reorder"),
        ("get", "staff"),
        ("post", "staff"),
        ("patch", "staff/1"),
        ("delete", "staff/1"),
        ("patch", "roster/1"),
        ("get", "map"),
        ("patch", "branding"),
        ("post", "branding/banner"),
        ("post", "branding/banner/complete"),
        ("get", "roster?squad_id=1"),
    ],
)
@pytest.mark.parametrize("key", ["scout", "b"])
def test_every_route_denies_foreign_and_nonmanager(club_app, client, method, path, key):
    response = call(client, club_app, method, path, {}, key)
    assert response.status_code == 403


def test_new_minor_player_flow_remains_private(club_app, client):
    from src.models.showcase import LocalPlayer, PlayerProfileClaim

    squad = call(client, club_app, "post", "squads", {"name": "Youth", "kind": "age_group", "age_limit": 18}).json[
        "squad"
    ]
    data = {
        "display_name": "Fictional Home Youth",
        "birth_date": "2010-02-03",
        "position": "Goalkeeper",
        "club_program_id": club_app.c2["program_a"],
        "squad_id": squad["id"],
        "shirt_number": 1,
    }
    for key in ("scout", "b"):
        assert client.post("/api/local-players", headers=_headers(key), json=data).status_code == 403
    created = client.post("/api/local-players", headers=_headers("a"), json=data)
    assert created.status_code == 201, created.json
    local_id = created.json["player"]["id"]
    assert created.json["member"]["is_minor"] is True
    assert "–" in created.json["member"]["age_label"]
    assert created.json["member"]["display_name"] == "Fictional Home Youth"
    assert created.json["member"]["squad_id"] == squad["id"]
    assert PlayerProfileClaim.query.filter_by(local_player_id=local_id).count() == 0
    assert client.get(f"/api/local-players/{local_id}").status_code == 404
    conflict = client.post(
        "/api/local-players", headers=_headers("a"), json=data | {"display_name": "Fictional Conflict"}
    )
    assert conflict.status_code == 409
    assert LocalPlayer.query.filter_by(display_name="Fictional Conflict").count() == 0


def test_banner_cap_and_foreign_upload_token(club_app, client, monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FLASK_ENV", "development")
    grant = call(client, club_app, "post", "branding/banner", {"content_type": "image/webp"}).json
    with storage.local_pending_path(grant["upload"]["blob_path"], True).open("wb") as file:
        file.truncate(storage.max_photo_bytes() + 1)
    result = call(client, club_app, "post", "branding/banner/complete", {"upload_token": grant["upload_token"]})
    assert result.status_code == 422 and "cap" in result.json["error"]
    foreign = client.post(
        f"/api/club/{club_app.c2['program_b']}/branding/banner/complete",
        json={"upload_token": grant["upload_token"]},
        headers=_headers("b"),
    )
    assert foreign.status_code == 404


def create_private(client, app, name="Fictional Private Adult", birth_date="2000-01-02", key="a"):
    return client.post(
        "/api/local-players",
        headers=_headers(key),
        json={
            "display_name": name,
            "birth_date": birth_date,
            "position": "Midfielder",
            "club_program_id": app.c2["program_a" if key == "a" else "program_b"],
        },
    )


def test_twelve_club_creations_bypass_user_rate_and_quota(rate_limited_club_app):
    club_app = rate_limited_club_app
    client = club_app.test_client()
    from src.extensions import limiter
    from src.models.showcase import LocalPlayer

    limiter.reset()
    try:
        for number in range(12):
            response = create_private(client, club_app, f"Fictional Private Academy {number}")
            assert response.status_code == 201, response.json
            row = db.session.get(LocalPlayer, response.json["player"]["id"])
            assert row.provenance == "club" and row.status == "pending"
            assert row.api_player_id == -row.id
        # Normal self-submissions still get their own five-per-hour bucket.
        for number in range(5):
            response = client.post(
                "/api/local-players",
                headers=_headers("a"),
                json={
                    "display_name": f"Fictional Self Submitted {number}",
                    "birth_date": "2000-02-03",
                },
            )
            assert response.status_code == 201, response.json
        assert (
            client.post(
                "/api/local-players",
                headers=_headers("a"),
                json={
                    "display_name": "Fictional Sixth Self",
                    "birth_date": "2000-02-03",
                },
            ).status_code
            == 429
        )
    finally:
        limiter.reset()


def test_normal_pending_quota_and_program_cap(club_app, client, monkeypatch):
    from src.models.showcase import LocalPlayer
    from src.routes import club_home

    for n in range(10):
        db.session.add(
            LocalPlayer(
                display_name=f"Fictional Pending {n}",
                status="pending",
                provenance="user",
                created_by_user_id=club_app.c2["users"]["a"],
            )
        )
    db.session.commit()
    response = client.post(
        "/api/local-players",
        headers=_headers("a"),
        json={
            "display_name": "Fictional Over Quota",
            "birth_date": "2000-02-03",
        },
    )
    assert response.status_code == 429 and "pending local player limit" in response.json["error"]
    assert create_private(client, club_app).status_code == 201
    monkeypatch.setattr(club_home, "MAX_CLUB_ROSTER_MEMBERS", 1)
    response = create_private(client, club_app, "Fictional Club Full")
    assert response.status_code == 429 and "Club roster limit" in response.json["error"]
    assert create_private(client, club_app, "Fictional Other Program", key="b").status_code == 201


@pytest.mark.parametrize("birth_date", ["2000-01-02", "2012-01-02"])
def test_club_identity_never_public_even_if_approved_with_shadow(club_app, client, monkeypatch, birth_date):
    from src.models.follow import PlayerShadow
    from src.models.showcase import LocalPlayer, without_minor_local_bridge
    from src.routes.players import players_bp
    from src.routes.scout import _scout_identity_subquery
    from src.services.player_subject import resolve_player_subject
    from src.services.sitemap_service import _player_candidate_ids
    from test_club_console import _admin_headers

    club_app.register_blueprint(players_bp, url_prefix="/api")
    created = create_private(client, club_app, birth_date=birth_date)
    assert created.status_code == 201, created.json
    local_id = created.json["player"]["id"]
    row = db.session.get(LocalPlayer, local_id)
    assert PlayerShadow.query.filter_by(player_api_id=-local_id).first() is None
    admin = _admin_headers()
    for status in ("", "?status=pending", "?status=approved"):
        response = client.get(f"/api/admin/local-players{status}", headers=admin)
        assert response.status_code == 200
        assert local_id not in [p["id"] for p in response.json["players"]]
    for action in ("approve", "reject"):
        response = client.post(f"/api/admin/local-players/{local_id}/review", headers=admin, json={"action": action})
        assert response.status_code == 409 and "Club-private" in response.json["error"]
    # Defence in depth against a future status-only moderation path or stale shadow.
    row.status = "approved"
    db.session.add(PlayerShadow(player_api_id=-local_id, player_name=row.display_name, is_active=True))
    db.session.commit()
    for path in (
        f"local-players/{local_id}",
        f"local-players/{local_id}/showcase",
        f"players/{-local_id}/profile",
        f"players/{-local_id}/followers/count",
    ):
        assert client.get(f"/api/{path}").status_code == 404
    assert resolve_player_subject(-local_id) is None
    identity = _scout_identity_subquery(include_local=True)
    assert db.session.query(identity).filter(identity.c.player_api_id == -local_id).first() is None
    assert db.session.query(PlayerShadow).filter(without_minor_local_bridge(PlayerShadow.player_api_id)).count() == 0
    assert -local_id not in list(_player_candidate_ids())


@pytest.mark.parametrize("birth_date", ["2000-01-02", "2012-01-02"])
def test_private_player_match_roster_and_results(club_app, client, birth_date):
    from src.models.season_rollup import PlayerSeasonTotal
    from test_club_console import _match, _result_payload

    created = create_private(client, club_app, birth_date=birth_date)
    assert created.status_code == 201, created.json
    member = created.json["member"]
    assert member["public_stats_allowed"] is False
    match = _match(club_app.c2["program_a"])
    response = call(
        client,
        club_app,
        "put",
        f"matches/{match.id}/roster",
        {
            "entries": [{"club_roster_member_id": member["id"], "jersey_number": 8}],
        },
    )
    assert response.status_code == 200, response.json
    result = call(client, club_app, "post", "results", _result_payload([member["id"]]))
    assert result.status_code == 201, result.json
    assert result.json["matches"][0]["player_name"] == "Fictional Private Adult"
    assert result.json["season_stats_by_player"] == {}
    assert PlayerSeasonTotal.query.filter_by(player_api_id=-member["local_player_id"]).count() == 0
    saved = call(client, club_app, "get", f"results/{result.json['result']['id']}")
    assert saved.json["matches"][0]["minutes"] == 90
    result_id = result.json["result"]["id"]
    entry_id = saved.json["matches"][0]["id"]
    correction = _result_payload([member["id"]])
    correction.pop("client_request_id")
    correction["expected_version"] = 1
    correction["entries"][0].pop("club_roster_member_id")
    correction["entries"][0].update(entry_id=entry_id, minutes=75)
    updated = call(client, club_app, "put", f"results/{result_id}", correction)
    assert updated.status_code == 200, updated.json
    assert updated.json["matches"][0]["minutes"] == 75
    assert call(client, club_app, "delete", f"results/{result_id}", {"expected_version": 2}).status_code == 200


def test_existing_player_picker_is_own_unassigned_only(club_app, client):
    from src.models.showcase import LocalPlayer

    created = create_private(client, club_app)
    member_id = created.json["member"]["id"]
    local_id = created.json["player"]["id"]
    create_private(client, club_app, "Fictional Foreign", key="b")
    db.session.add(
        LocalPlayer(display_name="Fictional Rejected", status="rejected", created_by_user_id=club_app.c2["users"]["a"])
    )
    db.session.commit()
    assert call(client, club_app, "get", "available-local-players").json == {"players": []}
    assert call(client, club_app, "delete", f"roster/{member_id}").status_code == 204
    available = call(client, club_app, "get", "available-local-players").json["players"]
    assert [p["id"] for p in available] == [local_id]
    assert call(client, club_app, "post", "roster", {"local_player_id": local_id}).status_code == 201
    for key in ("b", "scout"):
        assert call(client, club_app, "get", "available-local-players", key=key).status_code == 403


def test_banner_replacement_removes_only_same_program_public_blob(club_app, client, monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FLASK_ENV", "development")
    raw = BytesIO()
    Image.new("RGB", (120, 60), "blue").save(raw, "JPEG")
    previous = None
    for _ in range(3):
        grant = call(client, club_app, "post", "branding/banner", {"content_type": "image/jpeg"}).json
        storage.local_pending_path(grant["upload"]["blob_path"], True).write_bytes(raw.getvalue())
        response = call(client, club_app, "post", "branding/banner/complete", {"upload_token": grant["upload_token"]})
        assert response.status_code == 200
        current = storage.local_public_path(
            storage.public_blob_path_from_reference(response.json["brand"]["banner_url"])
        )
        assert current.exists()
        if previous:
            assert not previous.exists()
        previous = current
    foreign_path = f"club-banners/{club_app.c2['program_b']}/retained.jpg"
    foreign_url = storage.publish(foreign_path, raw.getvalue(), "image/jpeg")
    program = db.session.get(ClubProgram, club_app.c2["program_a"])
    program.banner_url = foreign_url
    db.session.commit()
    grant = call(client, club_app, "post", "branding/banner", {"content_type": "image/jpeg"}).json
    storage.local_pending_path(grant["upload"]["blob_path"], True).write_bytes(raw.getvalue())
    assert (
        call(client, club_app, "post", "branding/banner/complete", {"upload_token": grant["upload_token"]}).status_code
        == 200
    )
    assert storage.local_public_path(storage.public_blob_path_from_reference(foreign_url)).exists()


def test_different_managers_can_create_same_private_name_and_year(club_app, client):
    first = create_private(client, club_app, "Fictional Smith", "2010-01-02", key="b")
    second = create_private(client, club_app, "Fictional Smith", "2010-01-02", key="a")
    assert first.status_code == second.status_code == 201
    assert first.json["player"]["id"] != second.json["player"]["id"]
    assert "existing" not in second.json


@pytest.mark.parametrize("birth_date,relationship", [("2000-01-02", "player"), ("2010-01-02", "guardian")])
def test_normal_submission_ignores_private_club_duplicates(club_app, client, birth_date, relationship):
    private = create_private(client, club_app, "Fictional Smith", birth_date)
    assert private.status_code == 201
    response = client.post(
        "/api/local-players",
        headers=_headers("scout"),
        json={
            "display_name": "Fictional Smith",
            "birth_date": birth_date,
            "relationship_type": relationship,
        },
    )
    assert response.status_code == 201, response.json
    assert response.json["player"]["id"] != private.json["player"]["id"]
    assert "existing" not in response.json


def test_same_manager_private_duplicate_still_conflicts(club_app, client):
    created = create_private(client, club_app, "Fictional Smith", "2010-01-02")
    duplicate = create_private(client, club_app, "  FICTIONAL   SMITH  ", "2010-05-06")
    assert duplicate.status_code == 409
    assert duplicate.json["error"] == "A local player with this name and birth year already exists"
    assert duplicate.json["existing"]["id"] == created.json["player"]["id"]


@pytest.mark.parametrize("status", ["pending", "approved"])
def test_normal_submission_duplicate_still_conflicts(club_app, client, status):
    from src.models.showcase import LocalPlayer

    data = {"display_name": "Fictional Smith", "birth_date": "2000-01-02"}
    created = client.post("/api/local-players", headers=_headers("scout"), json=data)
    assert created.status_code == 201
    row = db.session.get(LocalPlayer, created.json["player"]["id"])
    row.status = status
    db.session.commit()
    duplicate = client.post("/api/local-players", headers=_headers("a"), json=data)
    assert duplicate.status_code == 409
    assert duplicate.json["error"] == "A local player with this name and birth year already exists"
    assert ("existing" in duplicate.json) == (status == "approved")
    # Club mode considers only this manager's identities, including for ordinary pending rows.
    club_created = create_private(client, club_app, "Fictional Smith", "2000-01-02")
    assert club_created.status_code == 201, club_created.json
