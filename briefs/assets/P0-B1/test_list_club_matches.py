

def test_list_club_matches_is_program_scoped_and_newest_first(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    first = _match(a, status="uploaded")
    second = _match(a, status="finalized")
    other = _match(b, status="uploaded")

    response = client.get(f"/api/club/{a}/matches", headers=_headers("a"))
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["total"] == 2
    assert [row["id"] for row in body["matches"]] == [second.id, first.id]
    assert body["matches"][0]["status"] == "finalized"
    assert body["matches"][0]["processing_request_status"] is None
    assert "job" in body["matches"][0]
    assert "roster" not in body["matches"][0]
    assert other.id not in [row["id"] for row in body["matches"]]

    response_b = client.get(f"/api/club/{b}/matches", headers=_headers("b"))
    assert response_b.status_code == 200
    assert [row["id"] for row in response_b.get_json()["matches"]] == [other.id]

    assert client.get(f"/api/club/{a}/matches").status_code == 401
