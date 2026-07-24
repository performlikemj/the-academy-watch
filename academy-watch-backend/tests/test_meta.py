"""Public application metadata endpoint tests."""


def test_legal_metadata_reads_operator_configuration(client, monkeypatch):
    monkeypatch.setenv("TERMS_URL", "  https://legal.example.test/terms  ")
    monkeypatch.setenv("PRIVACY_URL", " https://legal.example.test/privacy ")
    monkeypatch.setenv("SUPPORT_EMAIL", " support@example.test ")

    response = client.get("/api/meta/legal")

    assert response.status_code == 200
    assert response.get_json() == {
        "terms_url": "https://legal.example.test/terms",
        "privacy_url": "https://legal.example.test/privacy",
        "support_email": "support@example.test",
    }


def test_legal_metadata_defaults_to_empty_strings(client, monkeypatch):
    monkeypatch.delenv("TERMS_URL", raising=False)
    monkeypatch.delenv("PRIVACY_URL", raising=False)
    monkeypatch.delenv("SUPPORT_EMAIL", raising=False)

    response = client.get("/api/meta/legal")

    assert response.status_code == 200
    assert response.get_json() == {
        "terms_url": "",
        "privacy_url": "",
        "support_email": "",
    }
