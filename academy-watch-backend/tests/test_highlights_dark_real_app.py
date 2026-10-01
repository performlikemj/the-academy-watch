"""RC2 F7: compare the real app's unrouted paths, all methods and default headers."""

import pytest
import sqlalchemy as sa


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
def test_f7_real_app_dark_routes_are_unrouted(monkeypatch, method):
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    monkeypatch.setenv("ADMIN_PROGRAMS_ENABLED", "0")
    monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", "0")
    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "0")
    monkeypatch.setenv("ADMIN_BUSINESS_ENABLED", "0")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    from src.main import app
    from src.models.league import db

    monkeypatch.setitem(app.config, "RATELIMIT_ENABLED", False)
    client = app.test_client()
    hid = "00000000-0000-4000-8000-000000000001"
    paths = [
        "/api/highlights/features",
        "/api/me/highlight-requests",
        f"/api/highlights/{hid}/clip",
        f"/api/me/highlight-requests/{hid}/decision",
        f"/api/me/highlight-requests/{hid}/revoke",
        f"/api/me/highlight-requests/{hid}/retry",
        f"/api/me/highlight-requests/{hid}/preview",
        "/api/players/-7/highlights",
        "/api/programs/test-fc/highlights",
        "/api/club/1/matches/1/highlights",
        "/api/club/1/matches/1/highlight-review",
        f"/api/club/1/matches/1/highlights/{hid}",
        f"/api/club/1/matches/1/highlights/{hid}/preview",
        f"/api/admin/highlights/{hid}/takedown",
    ]
    with app.app_context():
        statements = []

        def queried(*args):
            statements.append(args[2])

        sa.event.listen(db.engine, "before_cursor_execute", queried)
        try:
            baseline = client.open("/api/rc2-unrouted-sibling", method=method)
            for path in paths:
                result = client.open(path, method=method)
                assert result.status_code == baseline.status_code, (method, path)
                assert result.data == baseline.data, (method, path)
                for header in ("Content-Type", "Cache-Control", "X-Content-Type-Options", "Allow"):
                    assert result.headers.get(header) == baseline.headers.get(header), (method, path, header)
            assert statements == []
            # C2's rematch must not restore disabled B3 rules.
            b3 = client.open("/api/admin/control/programs", method=method)
            assert b3.status_code == baseline.status_code and b3.data == baseline.data
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", queried)
