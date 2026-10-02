"""Stored display names for authenticated admin DTOs only; no provider reads.

Lookups are constrained to the current page, use narrow columns and batches,
and may include held/private identities because the caller is an administrator.
Never use this helper to enrich public, user or export serializers.
"""

import sqlalchemy as sa
from src.models.follow import PlayerShadow
from src.models.funding import ClubProgram
from src.models.journey import PlayerJourney
from src.models.league import Player, UserAccount, db
from src.models.showcase import LocalPlayer, PlayerShowcaseMedia
from src.models.tracked_player import TrackedPlayer
from src.utils.player_names import clean_name, is_placeholder_name


def _batches(ids):
    ids = sorted(set(ids))
    for start in range(0, len(ids), 500):
        yield ids[start : start + 500]


def player_names(ids):
    """Signed player ids (negative=local), including positive local bridges."""
    ids = {int(pid) for pid in ids if pid}
    result = {}
    for batch in _batches(pid for pid in ids if pid < 0):
        for pid, name in db.session.query(LocalPlayer.id, LocalPlayer.display_name).filter(
            LocalPlayer.id.in_([-pid for pid in batch])
        ):
            if name:
                result[-pid] = name
    for batch in _batches(pid for pid in ids if pid > 0):
        sources = (
            (TrackedPlayer.player_api_id, TrackedPlayer.player_name),
            (PlayerShadow.player_api_id, PlayerShadow.player_name),
            (Player.player_id, Player.name),
            (PlayerJourney.player_api_id, PlayerJourney.player_name),
            (LocalPlayer.api_player_id, LocalPlayer.display_name),
        )
        candidates = sa.union_all(
            *[
                sa.select(key.label("pid"), name.label("name"), sa.literal(priority).label("priority"))
                .where(key.in_(batch))
                .distinct()
                for priority, (key, name) in enumerate(sources)
            ]
        ).subquery()
        for pid, name, _ in db.session.execute(
            sa.select(candidates).order_by(candidates.c.priority, candidates.c.name)
        ):
            if pid not in result and not is_placeholder_name(name):
                result[pid] = clean_name(name)
    return result


def subject_id(row):
    return -row.local_player_id if row.local_player_id else row.player_api_id


def account_names(ids):
    result = {}
    for batch in _batches(pid for pid in ids if pid):
        for pid, name in db.session.query(UserAccount.id, UserAccount.display_name).filter(
            UserAccount.id.in_(batch), UserAccount.is_tombstone.is_(False)
        ):
            if name:
                result[pid] = name
    return result


def program_names(ids):
    result = {}
    for batch in _batches(pid for pid in ids if pid):
        result.update(db.session.query(ClubProgram.id, ClubProgram.name).filter(ClubProgram.id.in_(batch)))
    return result


def target_names(targets):
    """Map typed report/case targets to a name; no evidence or messages read."""
    targets = set(targets)
    player_ids, program_ids, media_ids = {}, {}, {}
    for kind, tid in targets:
        try:
            pid = -int(tid[6:]) if str(tid).startswith("local:") else int(tid)
        except (ValueError, TypeError):
            continue
        if not 0 < abs(pid) <= 2147483647:
            continue
        if kind == "player_profile":
            player_ids[(kind, tid)] = pid
        elif kind == "club_program" and pid > 0:
            program_ids[(kind, tid)] = pid
        elif kind == "showcase_content" and pid > 0:
            media_ids[(kind, tid)] = pid
    media_subjects = {}
    for batch in _batches(media_ids.values()):
        for mid, api_id, local_id in db.session.query(
            PlayerShowcaseMedia.id, PlayerShowcaseMedia.player_api_id, PlayerShowcaseMedia.local_player_id
        ).filter(PlayerShowcaseMedia.id.in_(batch)):
            media_subjects[mid] = -local_id if local_id else api_id
    names = player_names([*player_ids.values(), *media_subjects.values()])
    clubs = program_names(program_ids.values())
    result = {target: names.get(pid) for target, pid in player_ids.items()}
    result.update({target: clubs.get(pid) for target, pid in program_ids.items()})
    result.update({target: names.get(media_subjects.get(mid)) for target, mid in media_ids.items()})
    return result
