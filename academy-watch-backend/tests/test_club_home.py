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
