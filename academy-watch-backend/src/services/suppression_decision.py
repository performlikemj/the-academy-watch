"""One transaction-local suppression decision for existing tools and cases."""

from datetime import UTC, datetime

from src.models.follow import PlayerShadow
from src.models.league import db
from src.models.showcase import PlayerProfileClaim
from src.models.showcase_moderation import record_moderation_event


def decide_suppression(suppression, action, actor, notes, *, preserve_notes=False):
    active = action == "activate"
    became_active = active and suppression.status != "active"
    suppression.status = {"activate": "active", "lift": "lifted", "reject": "rejected"}[action]
    if not preserve_notes or not suppression.notes:
        suppression.notes = notes
    suppression.decided_at = suppression.updated_at = datetime.now(UTC)
    suppression.decided_by = actor
    if became_active:
        column = PlayerProfileClaim.local_player_id if suppression.local_player_id else PlayerProfileClaim.player_api_id
        subject = suppression.local_player_id or suppression.player_api_id
        other = PlayerProfileClaim.player_api_id if suppression.local_player_id else PlayerProfileClaim.local_player_id
        owners = (
            db.session.query(PlayerProfileClaim.user_account_id)
            .filter(column == subject, other.is_(None), PlayerProfileClaim.status == "approved")
            .distinct()
        )
        for (uid,) in owners:
            record_moderation_event(
                user_account_id=uid,
                target_kind="suppression",
                target_id=suppression.id,
                action="suppressed",
                actor_email=actor,
                session=db.session,
            )
    if suppression.player_api_id is not None and action in {"activate", "lift"}:
        PlayerShadow.query.filter_by(player_api_id=suppression.player_api_id).update(
            {PlayerShadow.is_active: not active}, synchronize_session=False
        )
