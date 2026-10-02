# ruff: noqa: F811
"""Owned photos and affiliations remain portable with every publication flag OFF."""

from datetime import date

import pytest
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerClubAffiliation, PlayerShowcaseMedia
from src.services.account import build_account_export
from test_club_console import club_app  # noqa: F401


@pytest.mark.parametrize("local_subject", [True, False])
@pytest.mark.parametrize("status", ["pending", "approved", "rejected"])
def test_export_owned_photos_and_affiliations(club_app, monkeypatch, local_subject, status):
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    uid, other = club_app.c2["users"]["b"], club_app.c2["users"]["a"]
    local = LocalPlayer(display_name="Export fixture", birth_date=date(2000, 1, 1), status="approved")
    db.session.add(local)
    db.session.flush()
    subject = {"local_player_id": local.id} if local_subject else {"player_api_id": 7001}
    for owner in (uid, other):
        db.session.add(
            PlayerShowcaseMedia(
                **subject,
                uploaded_by_user_id=owner,
                blob_path=f"owned-photo-{owner}.png",
                public_url=f"/api/media/published/photo-{owner}.png",
                status=status,
                content_type="image/png",
                size_bytes=123,
                reviewed_by="private-reviewer@example.test",
            )
        )
        db.session.add(
            PlayerClubAffiliation(
                **subject,
                created_by_user_id=owner,
                team_api_id=7001,
                status=status,
                season=f"season-{owner}",
                reviewed_by="private-reviewer@example.test",
            )
        )
    db.session.commit()
    exported = build_account_export(db.session.get(UserAccount, uid))
    media, affiliations = exported["showcase_media"], exported["showcase_affiliations"]
    assert len(media) == len(affiliations) == 1
    assert media[0]["blob_path"] == f"owned-photo-{uid}.png"
    assert media[0]["public_url"] == f"/api/media/published/photo-{uid}.png"
    assert media[0]["status"] == affiliations[0]["status"] == status
    assert media[0]["size_bytes"] == 123
    assert affiliations[0]["season"] == f"season-{uid}"
    for row in media + affiliations:
        assert all(row[k] == v for k, v in subject.items())
        assert not {"uploaded_by_user_id", "created_by_user_id", "reviewed_by", "review_note"} & row.keys()
    assert "private-reviewer" not in str(media + affiliations)
    assert f"owned-photo-{other}" not in str(media)
    assert f"season-{other}" not in str(affiliations)
