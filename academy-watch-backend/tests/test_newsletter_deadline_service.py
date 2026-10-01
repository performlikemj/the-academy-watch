import json
from datetime import UTC, date, datetime

import pytest
from src.models.league import Newsletter, NewsletterDigestQueue, Team, UserAccount, db
from src.services.newsletter_deadline_service import _send_single_digest
from src.utils import legacy_pages


class _DummyResponse:
    ok = True
    status_code = 200
    text = "ok"


@pytest.mark.parametrize("legacy_visible", [False, True])
def test_send_single_digest_loads_content_without_enriched_content(app, monkeypatch, legacy_visible):
    monkeypatch.setattr(legacy_pages, "LEGACY_PUBLIC_PAGES", legacy_visible)
    monkeypatch.setenv("N8N_EMAIL_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")

    team = Team(team_id=10, name="Digest Team", country="England", season=2025)
    db.session.add(team)
    db.session.commit()

    content_payload = {
        "title": "Digest Title",
        "summary": "Digest summary",
        "sections": [],
    }
    newsletter = Newsletter(
        team_id=team.id,
        title="Digest Title",
        content=json.dumps(content_payload),
        structured_content=json.dumps(content_payload),
        issue_date=date(2025, 1, 8),
        week_start_date=date(2025, 1, 6),
        week_end_date=date(2025, 1, 12),
        public_slug="digest-title-slug",
        published=True,
    )
    db.session.add(newsletter)

    user = UserAccount(
        email="digest-user@example.com",
        display_name="Digest User",
        display_name_lower="digest user",
    )
    db.session.add(user)
    db.session.flush()

    queue_entry = NewsletterDigestQueue(
        user_id=user.id,
        newsletter_id=newsletter.id,
        week_key="2025-W01",
        queued_at=datetime.now(UTC),
        sent=False,
    )
    db.session.add(queue_entry)
    db.session.commit()

    captured = []

    def fake_post(*args, **kwargs):
        captured.append(kwargs["json"])
        return _DummyResponse()

    monkeypatch.setattr("requests.post", fake_post)

    result = _send_single_digest(user.id, "2025-W01")
    assert result["success"] is True
    assert result["newsletter_count"] == 1
    assert captured[0]["meta"]["unsubscribe_url"] == "https://example.com/settings"
    assert 'href="https://example.com/settings"' in captured[0]["html"]
    assert "https://example.com/settings" in captured[0]["text"]

    for part in (captured[0]["html"], captured[0]["text"]):
        assert ("https://example.com/newsletters/digest-title-slug" in part) is legacy_visible
        assert "Digest Title" in part
        assert 'href=""' not in part
        assert 'href="None"' not in part
    assert ("Read Full Newsletter" in captured[0]["html"]) is legacy_visible
    assert ("Read more:" in captured[0]["text"]) is legacy_visible

    refreshed = NewsletterDigestQueue.query.get(queue_entry.id)
    assert refreshed.sent is True
