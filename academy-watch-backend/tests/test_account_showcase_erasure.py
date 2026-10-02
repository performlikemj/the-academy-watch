# ruff: noqa: F811
"""Inherited O4: owned showcase rows leave with an account, even while dark."""

from datetime import date

import pytest
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerClubAffiliation, PlayerShowcaseMedia
from src.services import showcase_media_storage as storage
from src.services.account import delete_account
from test_club_console import club_app  # noqa: F401


@pytest.mark.parametrize("kind", ["media", "affiliation"])
@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_dark_community_showcase_erasure(club_app, monkeypatch, tmp_path, kind, rollback, nested):
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path))
    uid = club_app.c2["users"]["b"]
    other_uid = club_app.c2["users"]["a"]
    local = LocalPlayer(
        display_name="Erasure community adult", birth_date=date(2000, 1, 1), status="approved", provenance="user"
    )
    db.session.add(local)
    db.session.flush()
    blob = f"local-players/{local.id}/owner/photo.png"
    pending = storage.local_pending_path(blob, create_parent=True)
    pending.write_bytes(b"private uploaded bytes")
    published_blob = storage.publish(blob, b"approved photo bytes")
    approved = storage.local_public_path(published_blob)
    if kind == "media":
        item = PlayerShowcaseMedia(
            local_player_id=local.id,
            uploaded_by_user_id=uid,
            blob_path=blob,
            public_url=f"/api/media/published/{published_blob}",
            status="approved",
        )
        other = PlayerShowcaseMedia(
            local_player_id=local.id,
            uploaded_by_user_id=other_uid,
            blob_path="local-players/other/photo.png",
            status="pending_upload",
        )
    else:
        item = PlayerClubAffiliation(
            local_player_id=local.id, created_by_user_id=uid, team_api_id=7001, status="club_confirmed"
        )
        other = PlayerClubAffiliation(
            local_player_id=local.id, created_by_user_id=other_uid, team_api_id=7002, status="club_confirmed"
        )
    db.session.add_all([item, other])
    db.session.commit()
    item_id, other_id = item.id, other.id
    transaction = db.session.begin_nested() if nested else None
    event = delete_account(db.session.get(UserAccount, uid))
    assert type(item).query.filter_by(id=item_id).count() == 0
    assert pending.exists() and approved.exists(), "storage deletion must wait for the root commit"
    if rollback:
        if nested:
            transaction.rollback()
        else:
            db.session.rollback()
        assert db.session.get(UserAccount, uid) is not None
        assert db.session.get(type(item), item_id) is not None
        assert pending.exists() and approved.exists()
        # A later unrelated commit cannot execute the abandoned erasure's cleanup.
        db.session.commit()
        assert pending.exists() and approved.exists()
    else:
        if nested:
            transaction.commit()
            assert pending.exists() and approved.exists(), "a savepoint cannot finalize media erasure"
        db.session.commit()
        assert db.session.get(UserAccount, uid) is None
        assert db.session.get(type(item), item_id) is None
        assert event.counts["deleted"]["showcase_media" if kind == "media" else "showcase_affiliations"] == 1
        if kind == "media":
            assert not pending.exists() and not approved.exists()
        else:
            assert pending.exists() and approved.exists()
    assert db.session.get(type(item), other_id) is not None
