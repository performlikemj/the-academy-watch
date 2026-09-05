"""Read-only, current-state evidence for an operator-declared pilot cohort.

Opaque labels are operator supplied, not identities verified by this service.
Only the explicitly projected evidence below may leave the report boundary.
"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import sqlalchemy as sa
from src.auth import _admin_email_list, _review_account_is_configured
from src.models.contact import ContactOutcome, ContactRequest
from src.models.funding import ClubProgram, ClubProgramManager
from src.models.league import UserAccount, db
from src.models.player_fan import PlayerFan
from src.models.player_match_entry import PlayerMatchEntry
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ScoutVerification
from src.services.club_registry import is_manager_of_approved_program
from src.services.player_subject import resolve_player_subject
from src.services.public_player_subject import resolve_public_adult_subject, user_owns_subject

MAX_BYTES = 256 * 1024
ROLES = ("staff", "player", "scout", "supporter")
KINDS = {"self_operated_action", "scout_discovery", "supporter_update_view"}
UNSUPPORTED_KINDS = {"cross_person_outcome", "staff_review"}
RECORDS = {
    "player_match_entry": PlayerMatchEntry,
    "scout_watchlist_entry": ScoutWatchlistEntry,
    "player_fan": PlayerFan,
    "contact_outcome": ContactOutcome,
}
FUTURE_RECORDS = {"player_feedback": ("player_feedback", "feedback"), "club_result": ("club_results", "stable_results")}
# Only these metadata columns are read. Authored text and video references are
# deliberately absent, including when later models become importable.
FUTURE_TABLES = {
    "club_invitations": (
        "id",
        "program_id",
        "player_api_id",
        "claim_id",
        "recipient_user_id",
        "created_by_user_id",
        "status",
        "created_at",
        "responded_at",
        "revoked_at",
    ),
    "player_feedback": (
        "id",
        "thread_id",
        "revision",
        "program_id",
        "invitation_id",
        "claim_id",
        "recipient_user_id",
        "player_api_id",
        "author_user_id",
        "published_at",
        "acknowledged_at",
        "withdrawn_at",
        "audit_expires_at",
    ),
    "club_results": (
        "id",
        "program_id",
        "version",
        "created_by_user_id",
        "created_at",
        "deleted_at",
    ),
    "player_match_entries": ("id", "club_result_id", "club_program_id", "player_api_id", "source", "status"),
}
OPAQUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)


class CohortError(ValueError):
    def __init__(self, code="invalid_register", status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def utc(value):
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def iso(value):
    return utc(value).isoformat() + "Z" if value else None


def timestamp(value, code):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value, re.ASCII
    ):
        raise CohortError(code)
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise CohortError(code) from None
    return utc(result)


def fields(value, required, code="invalid_register"):
    if not isinstance(value, dict) or set(value) != set(required.split()):
        raise CohortError(code)


def identifier(value, code="invalid_register"):
    if not isinstance(value, str) or not OPAQUE.fullmatch(value):
        raise CohortError(code)


def integer(value, *, signed=False):
    return type(value) is int and 0 < abs(value) <= 2_147_483_647 and (signed or value > 0)


def id_list(value, *, signed=False):
    if not isinstance(value, list) or len(value) > 100 or not all(integer(v, signed=signed) for v in value):
        raise CohortError()
    if len(set(value)) != len(value):
        raise CohortError()


def validate(data):
    fields(
        data,
        "schema_version cohort_id declared_at program_id window participants excluded_user_account_ids observations continuation",
    )
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or not integer(data["program_id"]):
        raise CohortError()
    identifier(data["cohort_id"])
    fields(data["window"], "start end", "invalid_window")
    start, end = (timestamp(data["window"][k], "invalid_window") for k in ("start", "end"))
    declared = timestamp(data["declared_at"], "invalid_window")
    if not start < end or end - start > timedelta(days=90) or declared > start:
        raise CohortError("invalid_window")
    people = data["participants"]
    if not isinstance(people, list) or not 1 <= len(people) <= 50:
        raise CohortError()
    accounts, subjects, keys = set(), set(), set()
    for p in people:
        fields(p, "person_key primary_role user_account_ids player_api_ids own_account_verified excluded")
        identifier(p["person_key"])
        if p["person_key"] in keys or p["primary_role"] not in ROLES:
            raise CohortError()
        keys.add(p["person_key"])
        if type(p["own_account_verified"]) is not bool or type(p["excluded"]) is not bool:
            raise CohortError()
        id_list(p["user_account_ids"])
        id_list(p["player_api_ids"], signed=True)
        if accounts.intersection(p["user_account_ids"]):
            raise CohortError("duplicate_account")
        accounts.update(p["user_account_ids"])
        subjects.update(p["player_api_ids"])
    id_list(data["excluded_user_account_ids"])
    if (
        len(accounts | set(data["excluded_user_account_ids"])) > 100
        or sum(len(p["player_api_ids"]) for p in people) > 100
    ):
        raise CohortError()
    observations = data["observations"]
    if not isinstance(observations, list) or len(observations) > 500:
        raise CohortError("invalid_observation")
    seen = set()
    for o in observations:
        fields(o, "id person_key kind occurred_at record_type record_id evidence_ref", "invalid_observation")
        for k in ("id", "person_key", "evidence_ref", "record_id"):
            identifier(o[k], "invalid_observation")
        if isinstance(o["kind"], str) and o["kind"] in UNSUPPORTED_KINDS:
            raise CohortError("unsupported_kind")
        if (
            o["id"] in seen
            or o["person_key"] not in keys
            or not isinstance(o["kind"], str)
            or o["kind"] not in KINDS
            or not isinstance(o["record_type"], str)
            or o["record_type"] not in RECORDS.keys() | FUTURE_RECORDS.keys()
        ):
            raise CohortError("invalid_observation")
        if o["record_type"] in FUTURE_RECORDS:
            try:
                if str(UUID(o["record_id"])) != o["record_id"]:
                    raise ValueError()
            except ValueError:
                raise CohortError("invalid_observation") from None
        elif not o["record_id"].isdigit() or not integer(int(o["record_id"])):
            raise CohortError("invalid_observation")
        seen.add(o["id"])
        if not start <= timestamp(o["occurred_at"], "invalid_observation") < end:
            raise CohortError("invalid_observation")
    continuation = data["continuation"]
    fields(continuation, "decision occurred_at evidence_ref")
    if continuation["decision"] not in ("not_discussed", "declined", "considering", "agreed", "paid"):
        raise CohortError()
    if continuation["decision"] == "not_discussed":
        if continuation["occurred_at"] is not None or continuation["evidence_ref"] is not None:
            raise CohortError()
    else:
        identifier(continuation["evidence_ref"])
        # Continuation is a separate operator decision, often made after the
        # observation window closes. Its timestamp does not alter the register.
        timestamp(continuation["occurred_at"], "invalid_window")
    register = {k: v for k, v in data.items() if k not in ("observations", "continuation")}
    digest = hashlib.sha256(
        json.dumps(register, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return start, end, accounts, subjects, digest


def reflected_tables():
    """Inspect on each report; incomplete installations fail closed, without DDL."""
    connection = db.session.connection()
    inspector = sa.inspect(connection)
    names = set(inspector.get_table_names())
    tables = {}
    for name, columns in FUTURE_TABLES.items():
        if name in names and set(columns) <= {c["name"] for c in inspector.get_columns(name)}:
            tables[name] = sa.Table(name, sa.MetaData(), autoload_with=connection, resolve_fks=False)
    return tables


def projection(table):
    return sa.select(*(table.c[name] for name in FUTURE_TABLES[table.name]))


def evidence(kind, record_type, record_id, occurred_at, basis="database"):
    return {
        "kind": kind,
        "record_type": record_type,
        "record_id": str(record_id),
        "occurred_at": iso(occurred_at),
        "basis": basis,
    }


def build_report(data):
    start, end, account_ids, subject_ids, digest = validate(data)
    program_id = data["program_id"]
    if db.session.get(ClubProgram, program_id) is None:
        raise CohortError("cohort_reference_invalid", 422)
    all_ids = account_ids | set(data["excluded_user_account_ids"])
    users = {u.id: u for u in UserAccount.query.filter(UserAccount.id.in_(all_ids)).all()}
    if set(users) != all_ids or any(resolve_player_subject(s) is None for s in subject_ids):
        raise CohortError("cohort_reference_invalid", 422)
    public_subjects = {s for s in subject_ids if resolve_public_adult_subject(s) is not None}
    admin_emails = {email.strip().lower() for email in _admin_email_list()}

    def excluded_account(user):
        return (
            user.is_tombstone
            or (user.email or "").strip().lower() in admin_emails
            or _review_account_is_configured(user.email)
        )

    excluded = set(data["excluded_user_account_ids"]) | {u.id for u in users.values() if excluded_account(u)}
    excluded.update(
        a
        for p in data["participants"]
        if p["excluded"] or set(p["user_account_ids"]) & excluded
        for a in p["user_account_ids"]
    )
    people = {p["person_key"]: p for p in data["participants"]}
    active_accounts = {
        a: p["person_key"]
        for p in people.values()
        if not p["excluded"] and p["own_account_verified"]
        for a in p["user_account_ids"]
        if a not in excluded
    }
    # Subjects on excluded rows cannot be reintroduced by another role's evidence.
    public_subjects -= {
        s
        for p in people.values()
        if p["excluded"] or set(p["user_account_ids"]) & excluded
        for s in p["player_api_ids"]
    }
    tables = reflected_tables()
    capabilities = {
        "relationships": "club_invitations" in tables,
        "feedback": "player_feedback" in tables and "club_invitations" in tables,
        "stable_results": "club_results" in tables and "player_match_entries" in tables,
    }
    relationships = []
    if capabilities["relationships"]:
        table = tables["club_invitations"]
        relationships = (
            db.session.execute(
                projection(table).where(
                    table.c.program_id == program_id,
                    table.c.status == "accepted",
                    table.c.recipient_user_id.in_(active_accounts),
                    table.c.player_api_id.in_(public_subjects),
                )
            )
            .mappings()
            .all()
        )
    program_managers = [
        m
        for m in ClubProgramManager.query.filter_by(program_id=program_id, status="active").all()
        if is_manager_of_approved_program(m.user_account_id, program_id)
    ]

    def relationship_time(actor, subject, *, invitation_id=None, claim_id=None):
        if not program_managers:
            return None
        accepted = []
        for invitation in relationships:
            if (
                (invitation_id is not None and invitation["id"] != invitation_id)
                or (claim_id is not None and invitation["claim_id"] != claim_id)
                or invitation["recipient_user_id"] != actor
                or invitation["player_api_id"] != subject
                or invitation["revoked_at"] is not None
            ):
                continue
            claim = db.session.get(PlayerProfileClaim, invitation["claim_id"])
            if (
                claim is None
                or claim.user_account_id != actor
                or claim.status != "approved"
                or claim.relationship_type != "player"
                or not (claim.player_api_id == subject or (subject < 0 and claim.local_player_id == -subject))
            ):
                continue
            when = invitation["responded_at"]
            if when is not None and claim.reviewed_at is not None and utc(claim.reviewed_at) <= utc(when):
                accepted.append(utc(when))
        return min(accepted) if accepted else None

    observations = {}
    observation_gaps = {key: set() for key in people}
    for o in data["observations"]:
        record_type, record_id = o["record_type"], o["record_id"]
        if record_type in FUTURE_RECORDS:
            table_name, capability = FUTURE_RECORDS[record_type]
            if not capabilities[capability]:
                observation_gaps[o["person_key"]].add(f"{capability}_unavailable")
                continue
            table = tables[table_name]
            exists = db.session.execute(sa.select(table.c.id).where(table.c.id == record_id)).first()
        else:
            exists = db.session.get(RECORDS[record_type], int(record_id))
            record_id = str(int(record_id))
        if exists is None:
            raise CohortError("cohort_reference_invalid", 422)
        observations.setdefault((o["person_key"], o["kind"], record_type, record_id), []).append(o)

    def correlated(key, kind, record_type, record_id, when):
        return any(
            utc(when).date() == timestamp(o["occurred_at"], "invalid_observation").date()
            for o in observations.get((key, kind, record_type, str(record_id)), [])
        )

    def inside(when):
        return when is not None and start <= utc(when) < end

    results = (
        PlayerMatchEntry.query.filter(
            PlayerMatchEntry.player_api_id.in_(public_subjects),
            PlayerMatchEntry.created_at < end,
        )
        .order_by(PlayerMatchEntry.created_at, PlayerMatchEntry.id)
        .all()
    )
    # P4 linkage is reflected separately from the legacy ORM model. A linked
    # line is never counted via the legacy fallback if its header is unavailable.
    result_links, stable_results = {}, {}
    if "player_match_entries" in tables:
        table = tables["player_match_entries"]
        result_links = dict(
            db.session.execute(
                sa.select(table.c.id, table.c.club_result_id).where(
                    table.c.id.in_([row.id for row in results]),
                )
            ).all()
        )
    if capabilities["stable_results"]:
        table = tables["club_results"]
        stable_results = {
            row["id"]: row
            for row in db.session.execute(
                projection(table).where(
                    table.c.program_id == program_id,
                    table.c.deleted_at.is_(None),
                    table.c.version >= 1,
                )
            ).mappings()
        }

    def live_result_line(row):
        header_id = result_links.get(row.id)
        if header_id is None:
            return True
        header = stable_results.get(header_id)
        return (
            header is not None
            and row.source == "club"
            and row.club_program_id == header["program_id"]
            and row.status == "club_confirmed"
        )

    feedback = []
    if capabilities["feedback"]:
        table = tables["player_feedback"]
        revisions = (
            db.session.execute(
                projection(table).where(
                    table.c.program_id == program_id,
                    table.c.recipient_user_id.in_(active_accounts),
                    table.c.player_api_id.in_(public_subjects),
                )
            )
            .mappings()
            .all()
        )
        closed_threads = {
            r["thread_id"] for r in revisions if r["withdrawn_at"] is not None or r["audit_expires_at"] is not None
        }
        for row in revisions:
            actor, subject = row["recipient_user_id"], row["player_api_id"]
            if (
                row["thread_id"] in closed_threads
                or row["revision"] < 1
                or row["published_at"] is None
                or subject not in people[active_accounts[actor]]["player_api_ids"]
            ):
                continue
            accepted_at = relationship_time(
                actor, subject, invitation_id=row["invitation_id"], claim_id=row["claim_id"]
            )
            if accepted_at is None or accepted_at > utc(row["published_at"]):
                continue
            author = db.session.get(UserAccount, row["author_user_id"]) if row["author_user_id"] is not None else None
            if row["author_user_id"] in excluded or (author and excluded_account(author)):
                continue
            feedback.append(row)

    def acknowledged(row):
        when = row["acknowledged_at"]
        return inside(when) and utc(when) >= utc(row["published_at"])

    outputs = []
    for key, p in people.items():
        role = p["primary_role"]
        ids = {a for a in p["user_account_ids"] if a in active_accounts}
        own_subjects = set(p["player_api_ids"]) & public_subjects
        missing, items = sorted(observation_gaps[key]), []
        if role in ("staff", "player") and not capabilities["feedback"]:
            missing.append("feedback_unavailable")
        if role == "staff" and not capabilities["stable_results"]:
            missing.append("stable_results_unavailable")
        if p["excluded"] or not ids:
            missing.append(
                "excluded" if p["excluded"] or set(p["user_account_ids"]) & excluded else "own_account_verified"
            )
        if role == "staff":
            managers = {a for a in ids if is_manager_of_approved_program(a, program_id)}
            if not managers:
                missing.append("approved_program_manager")
            for row in results:
                if row.source != "club" or row.status != "club_confirmed" or row.club_program_id != program_id:
                    continue
                header_id = result_links.get(row.id)
                if header_id is not None:
                    header = stable_results.get(header_id)
                    if (
                        not live_result_line(row)
                        or header["created_by_user_id"] not in managers
                        or not inside(header["created_at"])
                        or row.reported_by_user_id != header["created_by_user_id"]
                        or utc(row.created_at).date() != utc(header["created_at"]).date()
                    ):
                        continue
                    # Adoption preserves the original line reporter/time. A later
                    # editor or appended lineup cannot re-date the header action.
                    observed = correlated(key, "self_operated_action", "club_result", header_id, header["created_at"])
                    observed = observed or (
                        correlated(key, "self_operated_action", "player_match_entry", row.id, row.created_at)
                    )
                    if observed:
                        items.append(
                            evidence(
                                "self_operated_action",
                                "club_result",
                                header_id,
                                header["created_at"],
                                "operator_correlated",
                            )
                        )
                elif (
                    row.reported_by_user_id in managers
                    and inside(row.created_at)
                    and correlated(key, "self_operated_action", "player_match_entry", row.id, row.created_at)
                ):
                    items.append(
                        evidence(
                            "self_operated_action", "player_match_entry", row.id, row.created_at, "operator_correlated"
                        )
                    )
            for row in feedback:
                if (
                    row["author_user_id"] in managers
                    and inside(row["published_at"])
                    and correlated(key, "self_operated_action", "player_feedback", row["id"], row["published_at"])
                ):
                    items.append(
                        evidence(
                            "feedback_published",
                            "player_feedback",
                            row["id"],
                            row["published_at"],
                            "operator_correlated",
                        )
                    )
        elif role == "player":
            owners = {(a, s) for a in ids for s in own_subjects if user_owns_subject(a, s)}
            if not owners:
                missing.append("approved_player_claim")
            accepted = {pair: relationship_time(*pair) for pair in owners}
            accepted = {pair: when for pair, when in accepted.items() if when is not None}
            if not accepted:
                missing.append("accepted_relationship")
            for row in results:
                when = accepted.get((row.reported_by_user_id, row.player_api_id))
                if (
                    when is not None
                    and inside(row.created_at)
                    and when <= utc(row.created_at)
                    and row.source == "self"
                    and row.status == "self_reported"
                    and row.club_program_id in (None, program_id)
                ):
                    items.append(evidence("self_operated_action", "player_match_entry", row.id, row.created_at))
            for row in feedback:
                if row["recipient_user_id"] in ids and acknowledged(row):
                    items.append(
                        evidence("feedback_acknowledged", "player_feedback", row["id"], row["acknowledged_at"])
                    )
        elif role == "scout":
            verified = {
                v.user_account_id: v.reviewed_at
                for v in ScoutVerification.query.filter(
                    ScoutVerification.user_account_id.in_(ids), ScoutVerification.status == "approved"
                ).all()
            }
            if not verified:
                missing.append("approved_scout_verification")
            for row in ScoutWatchlistEntry.query.filter(
                ScoutWatchlistEntry.user_account_id.in_(verified),
                ScoutWatchlistEntry.player_api_id.in_(public_subjects),
            ).all():
                if (
                    inside(row.created_at)
                    and verified[row.user_account_id] is not None
                    and utc(verified[row.user_account_id]) <= utc(row.created_at)
                    and correlated(key, "scout_discovery", "scout_watchlist_entry", row.id, row.created_at)
                ):
                    items.append(
                        evidence(
                            "scout_discovery", "scout_watchlist_entry", row.id, row.created_at, "operator_correlated"
                        )
                    )
        elif role == "supporter":
            follows = PlayerFan.query.filter(
                PlayerFan.user_account_id.in_(ids), PlayerFan.player_api_id.in_(public_subjects)
            ).all()
            for row in results:
                if (
                    not live_result_line(row)
                    or row.status not in ("self_reported", "club_confirmed")
                    or row.reported_by_user_id not in active_accounts
                    or row.club_program_id not in (None, program_id)
                    or (row.source == "club" and row.club_program_id != program_id)
                ):
                    continue
                for o in observations.get((key, "supporter_update_view", "player_match_entry", str(row.id)), []):
                    when = timestamp(o["occurred_at"], "invalid_observation")
                    if utc(row.created_at) < when and any(
                        f.player_api_id == row.player_api_id and utc(f.created_at) < utc(row.created_at)
                        for f in follows
                    ):
                        items.append(
                            evidence("supporter_update_view", "player_match_entry", row.id, when, "operator_correlated")
                        )
        # One persisted action cannot be relabelled as later-week use.
        unique = {}
        for item in sorted(items, key=lambda e: (e["occurred_at"], e["record_type"], e["record_id"])):
            unique.setdefault((item["record_type"], item["record_id"]), item)
        items = list(unique.values())
        times = sorted({timestamp(e["occurred_at"], "invalid_observation") for e in items})
        repeats = (
            [t for t in times if t - times[0] >= timedelta(days=7) and t.date() != times[0].date()] if times else []
        )
        if not items:
            missing.append("qualifying_role_action")
        outputs.append(
            {
                "person_key": key,
                "primary_role": role,
                "qualified": bool(items),
                "eligible_now": bool(ids)
                and not any(
                    m in missing
                    for m in ("approved_program_manager", "approved_player_claim", "approved_scout_verification")
                ),
                "qualified_at": iso(times[0]) if times else None,
                "action_dates": sorted({t.date().isoformat() for t in times}),
                "repeat_dates": sorted({t.date().isoformat() for t in repeats}),
                "evidence": items,
                "missing": sorted(set(missing)),
            }
        )
    outcomes = []
    for row in feedback:
        author, recipient = row["author_user_id"], row["recipient_user_id"]
        if (
            acknowledged(row)
            and author in active_accounts
            and recipient in active_accounts
            and active_accounts[author] != active_accounts[recipient]
        ):
            outcomes.append(
                {
                    **evidence("cross_person_outcome", "player_feedback", row["id"], row["acknowledged_at"]),
                    "stage": "feedback_acknowledged",
                    "thread_id": row["thread_id"],
                    "revision": row["revision"],
                    "player_api_id": row["player_api_id"],
                    "person_keys": sorted([active_accounts[author], active_accounts[recipient]]),
                }
            )
    contact_outcomes = {}
    for outcome, contact, claim in (
        db.session.query(ContactOutcome, ContactRequest, PlayerProfileClaim)
        .join(ContactRequest, ContactRequest.id == ContactOutcome.contact_request_id)
        .join(PlayerProfileClaim, PlayerProfileClaim.id == ContactRequest.claim_id)
        .filter(
            ContactOutcome.occurred_at >= start,
            ContactOutcome.occurred_at < end,
            ContactRequest.player_api_id.in_(public_subjects),
        )
        .order_by(ContactOutcome.occurred_at, ContactOutcome.id)
        .all()
    ):
        a, b = contact.scout_user_id, claim.user_account_id
        if (
            a not in active_accounts
            or b not in active_accounts
            or active_accounts[a] == active_accounts[b]
            or outcome.reported_by_user_id not in (a, b)
        ):
            continue
        if (
            contact.status != "accepted"
            or claim.status != "approved"
            or claim.relationship_type != "player"
            or not (
                claim.player_api_id == contact.player_api_id
                or (contact.player_api_id < 0 and claim.local_player_id == -contact.player_api_id)
            )
            or not user_owns_subject(b, contact.player_api_id)
            or contact.player_api_id not in people[active_accounts[b]]["player_api_ids"]
        ):
            continue
        if ScoutVerification.query.filter_by(user_account_id=a, status="approved").first() is None:
            continue
        if contact.club_program_id not in (None, program_id) or (
            contact.routing_mode == "club_included" and contact.club_consent_status != "granted"
        ):
            continue
        # One outcome per genuine contact, represented by its latest qualifying
        # in-window stage. The ID breaks timestamp ties deterministically.
        contact_outcomes[contact.id] = {
            **evidence("cross_person_outcome", "contact_outcome", outcome.id, outcome.occurred_at),
            "stage": outcome.stage,
            "contact_request_id": contact.id,
            "player_api_id": contact.player_api_id,
            "person_keys": sorted([active_accounts[a], active_accounts[b]]),
        }
    outcomes.extend(contact_outcomes.values())
    by_role = {role: sum(p["qualified"] for p in outputs if p["primary_role"] == role) for role in ROLES}
    repeat_staff = sum(bool(p["repeat_dates"]) for p in outputs if p["primary_role"] == "staff")
    repeat_players = sum(bool(p["repeat_dates"]) for p in outputs if p["primary_role"] == "player")
    return {
        "schema_version": 1,
        "register_sha256": digest,
        "generated_at": iso(datetime.now(UTC).replace(tzinfo=None)),
        "capabilities": capabilities,
        "summary": {
            "qualifying_people": sum(by_role.values()),
            "by_role": by_role,
            "repeat_people": sum(bool(p["repeat_dates"]) for p in outputs),
            "repeat_staff": repeat_staff,
            "repeat_players": repeat_players,
            "repeat_target_met": repeat_staff >= 1 and repeat_players >= 3,
        },
        "participants": outputs,
        "cross_person_outcomes": sorted(outcomes, key=lambda e: (e["occurred_at"], e["record_id"])),
        "continuation": {
            "decision": data["continuation"]["decision"],
            "occurred_at": data["continuation"]["occurred_at"],
            "evidence_basis": "operator",
        },
        "warnings": [f"{cap}_not_installed" for cap, enabled in capabilities.items() if not enabled]
        + [
            "pre_declaration_and_person_account_reconciliation_operator_verified",
            "current_state_snapshot",
            "anonymous_events_cannot_measure_named_return_use",
        ],
    }
