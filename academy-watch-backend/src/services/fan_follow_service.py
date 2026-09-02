"""Transactional public-player fan follow operations."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from src.models.league import db
from src.models.player_fan import PlayerFan
from src.models.product_event import ProductEvent
from src.services.public_player_subject import resolve_public_adult_subject, user_owns_subject
from src.services.reach_metrics import fan_counts


class SubjectNotPublic(LookupError):
    """Raised when a signed player id does not resolve through the public gate."""


class CannotFollowOwnProfile(ValueError):
    """Raised when an approved player owner tries to follow their own subject."""


def follow_player(user_account, signed_id: int) -> tuple[bool, int]:
    """Idempotently follow one public adult subject and return creation/count."""

    try:
        subject = resolve_public_adult_subject(signed_id)
        if subject is None:
            raise SubjectNotPublic
        if user_owns_subject(user_account.id, subject.signed_id):
            raise CannotFollowOwnProfile

        created = True
        try:
            with db.session.begin_nested():
                db.session.add(
                    PlayerFan(
                        user_account_id=user_account.id,
                        player_api_id=subject.signed_id,
                    )
                )
                db.session.flush()
        except IntegrityError:
            created = False

        if created:
            db.session.add(
                ProductEvent(
                    event_name="fan_follow_added",
                    user_email=user_account.email,
                    props={"player_api_id": subject.signed_id},
                )
            )

        fans = fan_counts([subject.signed_id])[subject.signed_id][0]
        db.session.commit()
        return created, fans
    except Exception:
        db.session.rollback()
        raise


def unfollow_player(user_account, signed_id: int) -> bool:
    """Delete only the caller's fan row without resolving the subject."""

    try:
        fan = (
            PlayerFan.query.filter_by(
                user_account_id=user_account.id,
                player_api_id=signed_id,
            )
            .order_by(PlayerFan.id.asc())
            .first()
        )
        deleted = fan is not None
        if fan is not None:
            db.session.delete(fan)
            db.session.add(
                ProductEvent(
                    event_name="fan_follow_removed",
                    user_email=user_account.email,
                    props={"player_api_id": signed_id},
                )
            )

        db.session.commit()
        return deleted
    except Exception:
        db.session.rollback()
        raise


__all__ = [
    "CannotFollowOwnProfile",
    "SubjectNotPublic",
    "follow_player",
    "unfollow_player",
]
