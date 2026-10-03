"""Small approved-only card enrichment, batched for already eligible Scout rows."""

import bleach
from sqlalchemy import or_
from src.models.league import db
from src.models.showcase import LocalPlayer, PlayerClubAffiliation, PlayerShowcaseMedia, PlayerShowcaseProfile
from src.services import showcase_media_storage
from src.utils.sanitize import display_plain_text

BIO_LIMIT = 160


def attach_card_fields(players):
    if not players:
        return
    ids = {p["player_id"] for p in players}
    locals_by_id = {
        row.id: row.api_player_id or -row.id
        for row in db.session.query(LocalPlayer.id, LocalPlayer.api_player_id).filter(
            or_(LocalPlayer.api_player_id.in_(ids), LocalPlayer.id.in_([-i for i in ids if i < 0])),
            LocalPlayer.status == "approved",
            LocalPlayer.merged_into_local_player_id.is_(None),
        )
    }

    def scope(model):
        return or_(model.player_api_id.in_(ids), model.local_player_id.in_(locals_by_id))

    def signed(row):
        return locals_by_id.get(row.local_player_id) if row.local_player_id is not None else row.player_api_id

    bios = {}
    for row in db.session.query(
        PlayerShowcaseProfile.player_api_id, PlayerShowcaseProfile.local_player_id, PlayerShowcaseProfile.bio
    ).filter(scope(PlayerShowcaseProfile), PlayerShowcaseProfile.status == "approved"):
        text = " ".join(bleach.clean(display_plain_text(row.bio) or "", tags=[], strip=True).split())
        bios[signed(row)] = text if len(text) <= BIO_LIMIT else text[: BIO_LIMIT - 1].rstrip() + "…"
    photos = {}
    for row in (
        db.session.query(
            PlayerShowcaseMedia.player_api_id, PlayerShowcaseMedia.local_player_id, PlayerShowcaseMedia.public_url
        )
        .filter(
            scope(PlayerShowcaseMedia),
            PlayerShowcaseMedia.status == "approved",
            PlayerShowcaseMedia.kind == "photo",
            PlayerShowcaseMedia.is_primary.is_(True),
        )
        .order_by(PlayerShowcaseMedia.sort_order, PlayerShowcaseMedia.id)
    ):
        player_id = signed(row)
        if player_id not in photos:
            photos[player_id] = showcase_media_storage.published_url(row.public_url)
    confirmed = {
        signed(row)
        for row in db.session.query(PlayerClubAffiliation.player_api_id, PlayerClubAffiliation.local_player_id).filter(
            scope(PlayerClubAffiliation), PlayerClubAffiliation.status == "club_confirmed"
        )
    }
    for player in players:
        player.update(
            approved_photo_url=photos.get(player["player_id"]),
            bio_line=bios.get(player["player_id"]) or None,
            club_confirmed=player["player_id"] in confirmed,
        )
