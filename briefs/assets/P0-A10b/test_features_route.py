"""GET /api/features — the public flags the client gates its entry points on."""


def test_features_reports_contact_rail_on(client, monkeypatch):
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "1")
    res = client.get("/api/features")
    assert res.status_code == 200
    assert res.get_json() == {"contact_rail": True}


def test_features_reports_contact_rail_off_by_default(client, monkeypatch):
    monkeypatch.delenv("CONTACT_RAIL_ENABLED", raising=False)
    res = client.get("/api/features")
    assert res.status_code == 200
    assert res.get_json() == {"contact_rail": False}
