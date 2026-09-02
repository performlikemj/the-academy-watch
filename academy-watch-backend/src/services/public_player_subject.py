"""Fail-closed public-adult player resolution and ownership queries."""

from __future__ import annotations

import sqlalchemy as sa
from src.models.league import db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.services.player_subject import PlayerSubject, resolve_player_subject
from src.services.player_suppression import is_local_player_suppressed
from src.services.season_rollup_service import positive_subject_is_minor

MAX_SIGNED_PLAYER_ID = 2_147_483_647


def resolve_public_adult_subject(signed_id) -> PlayerSubject | None:
    """Resolve one public player without writes or upstream API calls."""

    if (
        isinstance(signed_id, bool)
        or not isinstance(signed_id, int)
        or signed_id == 0
        or abs(signed_id) > MAX_SIGNED_PLAYER_ID
    ):
        return None

    subject = resolve_player_subject(signed_id)
    if subject is None or subject.is_suppressed:
        return None

    if signed_id < 0:
        if is_local_player_suppressed(-signed_id) or subject.is_minor:
            return None
        return subject

    bridged_local_ids = [
        row[0]
        for row in db.session.query(LocalPlayer.id)
        .filter(LocalPlayer.api_player_id == signed_id)
        .order_by(LocalPlayer.id.asc())
        .all()
    ]
    if any(is_local_player_suppressed(local_id) for local_id in bridged_local_ids):
        return None

    tracked_rows = (
        TrackedPlayer.query.filter(TrackedPlayer.player_api_id == signed_id).order_by(TrackedPlayer.id.asc()).all()
    )
    if positive_subject_is_minor(
        signed_id,
        tracked_rows,
        subject.shadow,
        session=db.session,
    ):
        return None
    return subject


def owned_public_adult_subjects(user_account_id: int) -> list[PlayerSubject]:
    """Return the caller's approved player claims that remain public adults."""

    claimed_ids = (
        db.session.query(
            PlayerProfileClaim.player_api_id,
            LocalPlayer.api_player_id.label("local_signed_id"),
        )
        .outerjoin(LocalPlayer, LocalPlayer.id == PlayerProfileClaim.local_player_id)
        .filter(
            PlayerProfileClaim.user_account_id == user_account_id,
            PlayerProfileClaim.relationship_type == "player",
            PlayerProfileClaim.status == "approved",
        )
        .all()
    )

    signed_ids = {
        player_api_id if player_api_id is not None else local_signed_id
        for player_api_id, local_signed_id in claimed_ids
        if (player_api_id is not None and player_api_id > 0) or local_signed_id is not None
    }
    subjects = [resolve_public_adult_subject(signed_id) for signed_id in signed_ids]
    return sorted((subject for subject in subjects if subject is not None), key=lambda subject: subject.signed_id)


def user_owns_subject(user_account_id: int, signed_id: int) -> bool:
    """Test approved player ownership across direct and local claim namespaces."""

    if isinstance(signed_id, bool) or not isinstance(signed_id, int) or signed_id == 0:
        return False

    return (
        db.session.query(PlayerProfileClaim.id)
        .outerjoin(LocalPlayer, LocalPlayer.id == PlayerProfileClaim.local_player_id)
        .filter(
            PlayerProfileClaim.user_account_id == user_account_id,
            PlayerProfileClaim.relationship_type == "player",
            PlayerProfileClaim.status == "approved",
            sa.or_(
                PlayerProfileClaim.player_api_id == signed_id,
                LocalPlayer.api_player_id == signed_id,
            ),
        )
        .first()
        is not None
    )


def owner_account_ids_subquery(signed_id):
    """Return a correlated select of approved player-owner account ids."""

    is_sql_expression = callable(getattr(signed_id, "__clause_element__", None))
    if not is_sql_expression and (isinstance(signed_id, bool) or not isinstance(signed_id, int) or signed_id == 0):
        return sa.select(PlayerProfileClaim.user_account_id).where(sa.false())

    return (
        sa.select(PlayerProfileClaim.user_account_id)
        .select_from(PlayerProfileClaim)
        .outerjoin(LocalPlayer, LocalPlayer.id == PlayerProfileClaim.local_player_id)
        .where(
            PlayerProfileClaim.relationship_type == "player",
            PlayerProfileClaim.status == "approved",
            sa.or_(
                PlayerProfileClaim.player_api_id == signed_id,
                LocalPlayer.api_player_id == signed_id,
            ),
        )
        .distinct()
        .correlate_except(PlayerProfileClaim, LocalPlayer)
    )


__all__ = [
    "owned_public_adult_subjects",
    "owner_account_ids_subquery",
    "resolve_public_adult_subject",
    "user_owns_subject",
]
