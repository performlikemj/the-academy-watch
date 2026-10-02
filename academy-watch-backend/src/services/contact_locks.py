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
    state = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(
        getattr(exc, "orig", None), "pgcode", None
    )
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
    after locking a request. Repeated calls reuse held locks; extending a scope
    backwards fails with a retryable conflict instead of risking a deadlock.
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

    def hints(index):
        model = models[index]
        return {
            row[0]: tuple(row)
            for row in session.query(*(getattr(model, key) for key in fields[index]))
            .filter(model.id.in_(wanted[index]))
            .all()
        } if wanted[index] else {}

    with session.no_autoflush:
        # A request may pin an older claim; include both its club and the claim's
        # current club. An explicitly supplied publication is resolved first.
        pubs = hints(1)
        if pubs:
            local_ids = {r[2] for r in pubs.values()}
            wanted[3].update(
                r[0] for r in session.query(ContactRequest.id)
                .filter(ContactRequest.player_api_id.in_([-i for i in local_ids])).all()
            )
        requests = hints(3)
        wanted[0].update(r[1] for r in requests.values() if r[1] is not None)
        wanted[2].update(r[2] for r in requests.values() if r[2] is not None)
        club_locals = {-r[4] for r in requests.values() if r[3] and r[4] < 0}
        if club_locals:
            wanted[1].update(
                r[0] for r in session.query(ClubPlayerPublication.id)
                .filter(ClubPlayerPublication.local_player_id.in_(club_locals)).all()
            )
            pubs = hints(1)
        wanted[0].update(r[1] for r in pubs.values())
        wanted[2].update(r[3] for r in pubs.values() if r[3] is not None)
        claims = hints(2)
        wanted[0].update(r[1] for r in claims.values() if r[1] is not None)
        snapshots = (hints(0), pubs, claims, requests)
        # Resolve missing IDs too: deletion is a normal unavailable target, but
        # a changed binding is contention and must retry the whole transaction.
        held = session.info.setdefault("contact_scope_locks", [set() for _ in models])
        result = ContactScope()
        for index, (model, output) in enumerate(zip(models, vars(result).values(), strict=True)):
            new = wanted[index] - held[index]
            if new and any(held[later] for later in range(index + 1, len(models))):
                _retry()
            if new:
                query = session.query(model)
                if index == 0:
                    query = query.options(load_only(model.id, model.platform_status, model.emergency_hidden))
                rows = query.filter(model.id.in_(new)).order_by(model.id).populate_existing().with_for_update().all()
                held[index].update(r.id for r in rows)
            # Already-held rows can have legitimate pending changes; do not
            # populate_existing again and overwrite those changes.
            if wanted[index]:
                query = session.query(model).filter(model.id.in_(wanted[index]))
                if index == 0:
                    query = query.options(load_only(model.id, model.platform_status, model.emergency_hidden))
                output.update((row.id, row) for row in query.all())
        for index, snapshot in enumerate(snapshots):
            output = tuple(vars(result).values())[index]
            for id_, before in snapshot.items():
                row = output.get(id_)
                if row is None or tuple(getattr(row, key) for key in fields[index]) != before:
                    _retry()
        return result
