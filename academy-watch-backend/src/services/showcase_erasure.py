"""Remove owned showcase rows; storage cleanup runs only after a root commit."""

import logging

from sqlalchemy import event
from sqlalchemy.orm import Session
from src.models.league import db
from src.models.showcase import PlayerClubAffiliation, PlayerShowcaseMedia
from src.services import showcase_media_storage as storage

logger = logging.getLogger(__name__)
_CLEANUP = "showcase_erasure_cleanup"


def schedule_media_cleanup(records):
    """Session-owned references are discarded on rollback, never persisted in audit."""
    session = db.session()
    transaction = session.get_nested_transaction() or session.get_transaction()
    pending = session.info.setdefault(_CLEANUP, {}).setdefault(transaction, set())
    for record in records:
        if record.get("blob_path"):
            pending.add(("pending", record["blob_path"]))
        if record.get("public_url"):
            pending.add(("published", record["public_url"]))


@event.listens_for(Session, "after_commit")
def _clean_committed_media(session):
    transaction = session.get_nested_transaction() or session.get_transaction()
    queues = session.info.get(_CLEANUP, {})
    references = queues.pop(transaction, set())
    if transaction is not None and transaction.parent is not None:
        queues.setdefault(transaction.parent, set()).update(references)
        return
    session.info.pop(_CLEANUP, None)
    for kind, reference in references:
        try:
            (storage.delete_pending if kind == "pending" else storage.delete_published)(reference)
        except Exception:
            # A committed account erasure cannot be rolled back by storage.
            # Paths/URLs and storage exceptions can contain credentials.
            logger.warning("Showcase account-erasure storage cleanup failed (%s)", kind)


@event.listens_for(Session, "after_rollback")
def _discard_rolled_back_cleanup(session):
    transaction = session.get_nested_transaction()
    if transaction is not None:
        session.info.get(_CLEANUP, {}).pop(transaction, None)
    else:
        session.info.pop(_CLEANUP, None)


def erase_owned_showcase(user_id):
    photos = PlayerShowcaseMedia.query.filter_by(uploaded_by_user_id=user_id).with_for_update().all()
    schedule_media_cleanup([{"blob_path": r.blob_path, "public_url": r.public_url} for r in photos])
    for photo in photos:
        db.session.delete(photo)
    affiliations = PlayerClubAffiliation.query.filter_by(created_by_user_id=user_id).delete(synchronize_session=False)
    db.session.flush()
    return {"showcase_media": len(photos), "showcase_affiliations": affiliations}
