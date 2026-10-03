"""Retirement hides subject content while preserving each contributor's own evidence."""

import sqlalchemy as sa
from src.models.club_player_publication import RetiredClubShowcase
from src.models.league import UserAccount, db
from src.services.showcase_erasure import schedule_media_cleanup

AUTHOR_COLUMNS = {
    "player_showcase_profiles": "updated_by_user_id",
    "player_showcase_media": "uploaded_by_user_id",
    "player_links": "user_id",
    "player_club_affiliations": "created_by_user_id",
    "player_match_entries": "reported_by_user_id",
}


def _by_author(content):
    groups = {}
    for table, records in content.items():
        author_column = AUTHOR_COLUMNS.get(table)
        for record in records:
            author = record.get(author_column) if author_column else None
            groups.setdefault(author, {}).setdefault(table, []).append(record)
    return groups


def archive_content(content, *, local_player_id, claim_id, claimant_id, created_at=None):
    for author, own_content in _by_author(content).items():
        # Anonymous evidence stays private and never enters a person's export.
        if author is not None and db.session.get(UserAccount, author) is None:
            schedule_media_cleanup(own_content.get("player_showcase_media", []))
            continue
        kwargs = {"created_at": created_at} if created_at is not None else {}
        db.session.add(
            RetiredClubShowcase(
                local_player_id=local_player_id,
                claim_id=claim_id if author == claimant_id else None,
                user_account_id=author,
                content=own_content,
                **kwargs,
            )
        )


def repair_archives(*, user_id=None, limit=None):
    """Split legacy mixed snapshots before export/erasure, including while dark."""
    query = RetiredClubShowcase.query
    postgres = db.session.get_bind().dialect.name == "postgresql"
    if user_id is not None:
        matches = []
        for table, column in AUTHOR_COLUMNS.items():
            # Identifiers are trusted constants; the account id is always bound.
            if postgres:
                clause = (
                    f"EXISTS (SELECT 1 FROM json_array_elements(COALESCE("
                    f"retired_club_showcases.content->'{table}', '[]'::json)) AS entry "
                    f"WHERE entry->>'{column}' = CAST(:archive_user_id AS text))"
                )
            else:
                clause = (
                    f"EXISTS (SELECT 1 FROM json_each(retired_club_showcases.content, '$.{table}') AS entry "
                    f"WHERE json_extract(entry.value, '$.{column}') = :archive_user_id)"
                )
            matches.append(sa.text(clause).bindparams(archive_user_id=user_id))
        query = query.filter(sa.or_(RetiredClubShowcase.user_account_id == user_id, *matches))
    elif limit is not None:
        # A bounded maintenance batch must advance past already-correct rows.
        mixed = []
        for table, column in AUTHOR_COLUMNS.items():
            if postgres:
                clause = (
                    f"EXISTS (SELECT 1 FROM json_array_elements(COALESCE("
                    f"retired_club_showcases.content->'{table}', '[]'::json)) AS entry "
                    f"WHERE entry->>'{column}' IS DISTINCT FROM CAST(retired_club_showcases.user_account_id AS text))"
                )
            else:
                clause = (
                    f"EXISTS (SELECT 1 FROM json_each(retired_club_showcases.content, '$.{table}') AS entry "
                    f"WHERE json_extract(entry.value, '$.{column}') IS NOT retired_club_showcases.user_account_id)"
                )
            mixed.append(sa.text(clause))
        query = query.filter(sa.or_(*mixed))
    query = query.order_by(RetiredClubShowcase.id)
    if limit is not None:
        query = query.limit(limit)
    for snapshot in query.populate_existing().with_for_update().all():
        groups = _by_author(snapshot.content)
        if set(groups) == {snapshot.user_account_id}:
            continue
        archive_content(
            snapshot.content,
            local_player_id=snapshot.local_player_id,
            claim_id=snapshot.claim_id,
            claimant_id=snapshot.user_account_id,
            created_at=snapshot.created_at,
        )
        db.session.delete(snapshot)
    db.session.flush()


def export_content(snapshot, user_id):
    """Portability never expands to another author or exposes internal actor identifiers."""
    return {
        table: [
            {
                key: value
                for key, value in record.items()
                if key not in {"user_id", "reviewed_by", "pending_contract_claim_id"} and not key.endswith("_user_id")
            }
            for record in records
            if record.get(AUTHOR_COLUMNS.get(table)) == user_id
        ]
        for table, records in snapshot.content.items()
        if table in AUTHOR_COLUMNS
    }


def delete_archives(snapshots):
    for snapshot in snapshots:
        schedule_media_cleanup(snapshot.content.get("player_showcase_media", []))
        db.session.delete(snapshot)
    db.session.flush()
