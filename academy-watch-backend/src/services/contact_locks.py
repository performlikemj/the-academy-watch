"""One lock protocol for contact scopes: program → publication → claim → request.

Hints are non-locking column reads. Bulk callers must pass their entire scope
before making changes; IDs within each table are sorted. Domain permissions are
checked by callers using the refreshed rows returned here, never the hints.
"""

from dataclasses import dataclass, field

from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, load_only
from sqlalchemy.orm.scoping import scoped_session


class _ScopeChanged(Exception):
    sqlstate = "40001"


def database_conflict(exc, *, family="contact"):
    state = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(getattr(exc, "orig", None), "pgcode", None)
    if state in {"40P01", "40001"}:
        return f"{family}_conflict", 409
    if state == "55P03":
        return f"{family}_busy", 503
    return None


def _retry():
    raise OperationalError("Contact scope changed; retry", {}, _ScopeChanged())


@event.listens_for(Session, "after_transaction_end")
def _forget_locks(session, transaction):
    if transaction.parent is None:
        session.info.pop("contact_scope_locks", None)
        session.info.pop("contact_scope_rows", None)
        session.info.pop("contact_scope_results", None)


@event.listens_for(Session, "after_transaction_create")
def _remember_savepoint(session, transaction):
    if transaction.nested:
        transaction._contact_scope_rows_before = [
            dict(rows) for rows in session.info.get("contact_scope_rows", [{} for _ in range(4)])
        ]
        transaction._contact_scope_results_before = dict(session.info.get("contact_scope_results", {}))
        transaction._contact_scope_before = [
            set(ids) for ids in session.info.get("contact_scope_locks", [set() for _ in range(4)])
        ]


@event.listens_for(Session, "after_soft_rollback")
def _restore_savepoint(session, transaction):
    if transaction.nested:
        session.info["contact_scope_locks"] = transaction._contact_scope_before
        session.info["contact_scope_rows"] = transaction._contact_scope_rows_before
        session.info["contact_scope_results"] = transaction._contact_scope_results_before


@dataclass
class ContactScope:
    programs: dict = field(default_factory=dict)
    publications: dict = field(default_factory=dict)
    claims: dict = field(default_factory=dict)
    requests: dict = field(default_factory=dict)


def _ids(value):
    if value is None:
        return set()
    return set(value) if isinstance(value, (list, tuple, set, frozenset)) else {value}


def lock_contact_scope(session, *, program_id=None, publication_id=None, claim_id=None, request_id=None):
    """Resolve, lock in P/U/C/R order, and reject any changed identity binding.

    Scalars and collections are accepted for erasure/merges. Publications also
    discover their existing threads, so retirement cannot acquire another claim
    after locking a request. Repeated calls reuse held rows without SQL. Bulk callers supply the entire
    batch before locking. Unavoidable dynamic extensions use NOWAIT when their
    rank/id precedes a held row: only actual contention can produce a busy reply.
    """
    if isinstance(session, scoped_session):
        session = session()
    from src.models.club_player_publication import ClubPlayerPublication
    from src.models.contact import ContactRequest
    from src.models.funding import ClubProgram
    from src.models.showcase import PlayerProfileClaim

    models = (ClubProgram, ClubPlayerPublication, PlayerProfileClaim, ContactRequest)
    fields = (
        ("id",),
        ("id", "program_id", "local_player_id", "claim_id"),
        ("id", "club_program_id", "local_player_id", "player_api_id"),
        ("id", "club_program_id", "claim_id", "club_first", "player_api_id", "routing_mode"),
    )
    wanted = [_ids(v) for v in (program_id, publication_id, claim_id, request_id)]

    held = session.info.setdefault("contact_scope_locks", [set() for _ in models])
    retained = session.info.setdefault("contact_scope_rows", [{} for _ in models])
    results = session.info.setdefault("contact_scope_results", {})
    key = tuple(frozenset(ids) for ids in wanted)
    if key in results:
        return results[key]
    # Program-only prefixes have no identity edges and need a single SELECT.
    if not any(wanted[1:]):
        new = wanted[0] - held[0]
        if new:
            with session.no_autoflush:
                rows = (
                    session.query(ClubProgram)
                    .options(load_only(ClubProgram.id, ClubProgram.platform_status, ClubProgram.emergency_hidden))
                    .filter(ClubProgram.id.in_(new))
                    .order_by(ClubProgram.id)
                    .populate_existing()
                    .with_for_update(nowait=any(held[1:]) or bool(held[0] and min(new) < max(held[0])))
                    .all()
                )
            held[0].update(r.id for r in rows)
            retained[0].update((r.id, r) for r in rows)
        result = ContactScope(programs={i: retained[0][i] for i in wanted[0] if i in retained[0]})
        results[key] = result
        return result
    snapshots_cache = [{} for _ in models]
    inspected = [set() for _ in models]

    def hints(index):
        model = models[index]
        missing = wanted[index] - inspected[index] - held[index]
        if missing:
            snapshots_cache[index].update(
                (row[0], tuple(row))
                for row in session.query(*(getattr(model, key) for key in fields[index]))
                .filter(model.id.in_(missing))
                .all()
            )
            inspected[index].update(missing)
        for id_ in wanted[index] & held[index]:
            row = retained[index].get(id_)
            if row is not None:
                snapshots_cache[index][id_] = tuple(getattr(row, key) for key in fields[index])
        return snapshots_cache[index]

    with session.no_autoflush:
        # Resolve the transitive batch before any lock. A publication can close
        # older claims' threads; a request can pin a different club from its claim.
        while True:
            before = [set(ids) for ids in wanted]
            requests = hints(3)
            wanted[0].update(r[1] for r in requests.values() if r[1] is not None)
            wanted[2].update(r[2] for r in requests.values() if r[2] is not None)
            club_locals = {-r[4] for r in requests.values() if r[3] and r[4] < 0}
            claims = hints(2)
            from src.models.showcase import LocalPlayer
            from src.services.club_player_publication import enabled

            if enabled() and wanted[2] - held[2]:
                local_ids = {r[2] for id_, r in claims.items() if r[2] is not None and id_ not in held[2]}
                if local_ids:
                    club_locals.update(
                        r[0]
                        for r in session.query(LocalPlayer.id)
                        .filter(LocalPlayer.id.in_(local_ids), LocalPlayer.provenance == "club")
                        .all()
                    )
            if club_locals:
                wanted[1].update(r.id for r in retained[1].values() if r.local_player_id in club_locals)
                known_locals = {r.local_player_id for r in retained[1].values()}
                club_locals -= known_locals
                wanted[1].update(
                    r[0]
                    for r in session.query(ClubPlayerPublication.id)
                    .filter(ClubPlayerPublication.local_player_id.in_(club_locals))
                    .all()
                )
            pubs = hints(1)
            if pubs:
                local_ids = {r[2] for r in pubs.values()}
                wanted[3].update(r.id for r in retained[3].values() if r.player_api_id in {-i for i in local_ids})
                local_ids = {r[2] for id_, r in pubs.items() if id_ not in held[1]}
                wanted[3].update(
                    r[0]
                    for r in session.query(ContactRequest.id)
                    .filter(ContactRequest.player_api_id.in_([-i for i in local_ids]))
                    .all()
                )
            wanted[0].update(r[1] for r in pubs.values())
            wanted[2].update(r[3] for r in pubs.values() if r[3] is not None)
            wanted[0].update(r[1] for r in claims.values() if r[1] is not None)
            if wanted == before:
                break
        snapshots = (hints(0), pubs, claims, requests)
        # Resolve missing IDs too: deletion is a normal unavailable target, but
        # a changed binding is contention and must retry the whole transaction.
        result = ContactScope()
        for index, (model, output) in enumerate(zip(models, vars(result).values(), strict=True)):
            new = wanted[index] - held[index]
            earlier = any(held[later] for later in range(index + 1, len(models))) or bool(
                new and held[index] and min(new) < max(held[index])
            )
            if new:
                query = session.query(model)
                if index == 0:
                    query = query.options(load_only(model.id, model.platform_status, model.emergency_hidden))
                rows = (
                    query.filter(model.id.in_(new))
                    .order_by(model.id)
                    .populate_existing()
                    .with_for_update(nowait=earlier)
                    .all()
                )
                held[index].update(r.id for r in rows)
                retained[index].update((r.id, r) for r in rows)
            # Already-held rows can have legitimate pending changes; do not
            # populate_existing again and overwrite those changes.
            output.update((i, retained[index][i]) for i in wanted[index] if i in retained[index])
        for index, snapshot in enumerate(snapshots):
            output = tuple(vars(result).values())[index]
            for id_, before in snapshot.items():
                row = output.get(id_)
                if row is None or tuple(getattr(row, key) for key in fields[index]) != before:
                    _retry()
        results[key] = result
        return result
