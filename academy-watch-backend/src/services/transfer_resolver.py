"""Pure, chronological transfer-state resolution.

API-Football does not guarantee transfer-array order and overloads ``type``
with both movement labels and fee strings.  This module normalizes that input,
orders same-day chains from their causal topology, and reduces it into distinct
loan episodes plus a last-known player state.  It deliberately has no Flask or
database dependency.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Literal

from src.utils.affiliates import resolve_senior_id, senior_base_name

EventKind = Literal["loan_start", "loan_return", "permanent", "unknown"]
LoanEndReason = Literal[
    "return",
    "permanent_conversion",
    "superseded_by_permanent",
    "reloan",
    "superseded_by_loan",
    "subloan",
    "superseded_by_return",
]
LoanState = Literal["on_loan", "not_on_loan", "indeterminate", "unknown"]

_LOAN_TYPES = {"loan"}
_RETURN_TYPES = {
    "back from loan",
    "return from loan",
    "end of loan",
    "loan end",
    "loan return",
}
_NA_TYPES = {"n/a", "na"}


@dataclass(frozen=True, slots=True)
class ClubRef:
    """A provider club plus a stable best-effort organisation identity."""

    api_id: int | None
    name: str | None
    organization_key: str
    organization_api_id: int | None


@dataclass(frozen=True, slots=True)
class ResolverIssue:
    """A non-fatal validation or event-stream continuity problem."""

    code: str
    message: str
    transfer_date: date | None = None
    raw_event: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class NormalizedTransferEvent:
    """One valid provider event in a canonical, raw-preserving form."""

    transfer_date: date
    raw_type: str
    normalized_type: str
    out_club: ClubRef
    in_club: ClubRef
    fingerprint: str
    raw: Any = field(compare=False, repr=False)

    @property
    def date(self) -> date:
        """Short alias used by consumers and tests."""
        return self.transfer_date


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    events: tuple[NormalizedTransferEvent, ...]
    issues: tuple[ResolverIssue, ...]


@dataclass(frozen=True, slots=True)
class ResolvedTransferEvent:
    """A canonical effective event after topology-aware classification."""

    event: NormalizedTransferEvent
    kind: EventKind
    reason: str
    evidence: tuple[NormalizedTransferEvent, ...]
    fee: str | None = None

    @property
    def transfer_date(self) -> date:
        return self.event.transfer_date

    @property
    def date(self) -> date:
        return self.event.transfer_date

    @property
    def raw_type(self) -> str:
        return self.event.raw_type

    @property
    def out_club(self) -> ClubRef:
        return self.event.out_club

    @property
    def in_club(self) -> ClubRef:
        return self.event.in_club

    @property
    def fee_string(self) -> str | None:
        return self.fee

    @property
    def classification(self) -> str:
        """Spec-spelled classification while ``kind`` stays Python-friendly."""
        return {
            "loan_start": "loan-start",
            "loan_return": "loan-return",
            "permanent": "permanent",
            "unknown": "unknown",
        }[self.kind]


@dataclass(frozen=True, slots=True)
class LoanEpisode:
    """A half-open loan interval ``[start_date, end_date)``."""

    owner: ClubRef
    immediate_source: ClubRef
    loan_club: ClubRef
    start_date: date
    end_date: date | None
    end_reason: LoanEndReason | None
    start_event: ResolvedTransferEvent
    end_event: ResolvedTransferEvent | None

    @property
    def club(self) -> ClubRef:
        """Compatibility alias for the playing/borrower club."""
        return self.loan_club


@dataclass(frozen=True, slots=True)
class TransferResolution:
    """Resolved transfer history and last-known state at ``as_of``.

    ``legal_owner`` is ownership inferred from the stream.  It is intentionally
    separate from ``loan_owner``: player-facing journey ``current_owner`` fields
    should be populated only from a confirmed active loan, not for permanent
    players whose legal owner is simply their current club.
    """

    as_of: date
    normalized_events: tuple[NormalizedTransferEvent, ...]
    events: tuple[ResolvedTransferEvent, ...]
    loan_episodes: tuple[LoanEpisode, ...]
    legal_owner: ClubRef | None
    current_club: ClubRef | None
    current_owner: ClubRef | None
    immediate_loan_source: ClubRef | None
    active_loan: LoanEpisode | None
    on_loan: bool | None
    loan_state: LoanState
    latest_permanent_move: ResolvedTransferEvent | None
    issues: tuple[ResolverIssue, ...]
    season_start_month: int
    season_start_day: int

    @property
    def loan_owner(self) -> ClubRef | None:
        """Compatibility alias for the player-facing current owner."""
        return self.current_owner


@dataclass(slots=True)
class _CoalescedEvent:
    event: NormalizedTransferEvent
    evidence: list[NormalizedTransferEvent]


@dataclass(slots=True)
class _EpisodeBuilder:
    owner: ClubRef
    immediate_source: ClubRef
    loan_club: ClubRef
    start_date: date
    start_event: ResolvedTransferEvent
    end_date: date | None = None
    end_reason: LoanEndReason | None = None
    end_event: ResolvedTransferEvent | None = None


@dataclass(slots=True)
class _ReducerState:
    legal_owner: ClubRef | None = None
    current_club: ClubRef | None = None
    active_episode: _EpisodeBuilder | None = None


def _value(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _clean_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _club(api_id: int | None, name: str | None) -> ClubRef:
    senior_id = resolve_senior_id(api_id, name)
    base = senior_base_name(name).strip().casefold()
    organization_key = f"name:{base}" if base else f"id:{senior_id}"
    return ClubRef(
        api_id=api_id,
        name=name,
        organization_key=organization_key,
        organization_api_id=senior_id or api_id,
    )


def _context_club(value: ClubRef | Mapping[str, Any] | None, *, field_name: str) -> ClubRef | None:
    """Coerce optional caller-known state into the resolver's club identity.

    Transfer feeds sometimes begin with a topology-only ``N/A`` event.  A
    consumer that already knows the preceding owner/current club can provide
    that context without manufacturing a synthetic transfer event.
    """
    if value is None or isinstance(value, ClubRef):
        return value
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a ClubRef, mapping, or None")

    api_id = _parse_id(value.get("api_id", value.get("id")))
    name = _clean_name(value.get("name"))
    if api_id is None and name is None:
        raise ValueError(f"{field_name} must include a usable club id or name")
    return _club(api_id, name)


def _same_org(left: ClubRef | None, right: ClubRef | None) -> bool:
    if left is None or right is None:
        return False
    if (left.api_id is None and left.name is None) or (right.api_id is None and right.name is None):
        return False
    if left.api_id is not None and left.api_id == right.api_id:
        return True
    if left.organization_api_id is not None and left.organization_api_id == right.organization_api_id:
        return True
    return left.organization_key == right.organization_key


def _event_fields(event: Any) -> tuple[Any, Any, Any, Any, Any, Any]:
    """Read either an API object or a flattened event dict/model row."""
    transfer_date = _value(event, "date", None)
    if transfer_date is None:
        transfer_date = _value(event, "transfer_date", None)

    transfer_type = _value(event, "type", None)
    if transfer_type is None:
        transfer_type = _value(event, "transfer_type", None)

    teams = _value(event, "teams", None)
    if isinstance(teams, Mapping):
        outgoing = teams.get("out") or {}
        incoming = teams.get("in") or {}
        out_id = _value(outgoing, "id", None)
        out_name = _value(outgoing, "name", None)
        in_id = _value(incoming, "id", None)
        in_name = _value(incoming, "name", None)
    else:
        out_id = _value(event, "out_club_api_id", None)
        out_name = _value(event, "out_club_name", None)
        in_id = _value(event, "in_club_api_id", None)
        in_name = _value(event, "in_club_name", None)

    return transfer_date, transfer_type, out_id, out_name, in_id, in_name


def _canonical_event_key(event: NormalizedTransferEvent) -> tuple[Any, ...]:
    return (
        event.transfer_date,
        event.out_club.organization_key,
        event.in_club.organization_key,
        event.normalized_type,
        event.out_club.api_id or 0,
        event.in_club.api_id or 0,
        event.fingerprint,
    )


def _is_senior_named(club: ClubRef) -> bool:
    if not club.name:
        return False
    return club.name.strip().casefold() == senior_base_name(club.name).strip().casefold()


def _canonicalize_organizations(
    events: list[NormalizedTransferEvent],
) -> list[NormalizedTransferEvent]:
    """Resolve name-only affiliates to a senior id observed in this stream.

    ``resolve_senior_id`` covers known hardcoded ids.  This pre-scan covers the
    much larger data-driven case: if the stream includes both Everton and
    Everton U21 (or Bayern/Atalanta and their II sides), every ref keeps its raw
    provider ``api_id`` but shares the observed senior ``organization_api_id``.
    """
    clubs = [club for event in events for club in (event.out_club, event.in_club)]
    if not clubs:
        return events

    parents = list(range(len(clubs)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(clubs)):
        for right in range(left + 1, len(clubs)):
            if _same_org(clubs[left], clubs[right]):
                union(left, right)

    groups: dict[int, list[ClubRef]] = {}
    for index, club in enumerate(clubs):
        groups.setdefault(find(index), []).append(club)

    canonical: dict[tuple[int | None, str | None], tuple[int | None, str]] = {}
    for members in groups.values():
        mapped_ids = {
            member.organization_api_id
            for member in members
            if member.organization_api_id is not None and member.organization_api_id != member.api_id
        }
        senior_ids = {member.api_id for member in members if member.api_id is not None and _is_senior_named(member)}
        observed_ids = {member.organization_api_id for member in members if member.organization_api_id is not None}
        organization_id = (
            min(mapped_ids or senior_ids or observed_ids) if mapped_ids or senior_ids or observed_ids else None
        )
        named_keys = sorted(
            {member.organization_key for member in members if member.organization_key.startswith("name:")}
        )
        organization_key = named_keys[0] if named_keys else f"id:{organization_id}"
        for member in members:
            canonical[(member.api_id, member.name)] = organization_id, organization_key

    result: list[NormalizedTransferEvent] = []
    for event in events:
        out_id, out_key = canonical[(event.out_club.api_id, event.out_club.name)]
        in_id, in_key = canonical[(event.in_club.api_id, event.in_club.name)]
        result.append(
            replace(
                event,
                out_club=replace(
                    event.out_club,
                    organization_api_id=out_id,
                    organization_key=out_key,
                ),
                in_club=replace(
                    event.in_club,
                    organization_api_id=in_id,
                    organization_key=in_key,
                ),
            )
        )
    return result


def _issue_key(issue: ResolverIssue) -> tuple[str, str, date]:
    return issue.code, issue.message, issue.transfer_date or date.min


def _normalize_transfer_events(events: Iterable[Any]) -> NormalizationResult:
    normalized: list[NormalizedTransferEvent] = []
    issues: list[ResolverIssue] = []

    for raw_event in events or ():
        raw_date, raw_type, raw_out_id, raw_out_name, raw_in_id, raw_in_name = _event_fields(raw_event)
        transfer_date = _parse_date(raw_date)
        if transfer_date is None:
            issues.append(
                ResolverIssue("invalid_date", "Transfer event has a missing or invalid date", raw_event=raw_event)
            )
            continue

        if not isinstance(raw_type, str) or not raw_type.strip():
            issues.append(
                ResolverIssue(
                    "missing_type",
                    "Transfer event has a missing transfer type",
                    transfer_date=transfer_date,
                    raw_event=raw_event,
                )
            )
            continue

        transfer_type = raw_type.strip()
        normalized_type = " ".join(transfer_type.casefold().split())

        out_id = _parse_id(raw_out_id)
        out_name = _clean_name(raw_out_name)
        if out_id is None and out_name is None:
            issues.append(
                ResolverIssue(
                    "missing_out_club",
                    "Transfer event has no usable outgoing club id or name",
                    transfer_date=transfer_date,
                    raw_event=raw_event,
                )
            )
            continue
        if out_id is None:
            issues.append(
                ResolverIssue(
                    "missing_out_club_id",
                    "Transfer event uses its outgoing club name because its id is missing or invalid",
                    transfer_date=transfer_date,
                    raw_event=raw_event,
                )
            )

        in_id = _parse_id(raw_in_id)
        in_name = _clean_name(raw_in_name)
        if in_id is None and in_name is None:
            issues.append(
                ResolverIssue(
                    "missing_in_club",
                    "Transfer event has no usable incoming club id or name",
                    transfer_date=transfer_date,
                    raw_event=raw_event,
                )
            )
            # A typed permanent departure with no onward club is still
            # load-bearing evidence for academy-relative ``released`` status.
            # Retain it with an explicit unknown destination; loans, returns,
            # and topology-only N/A events cannot be resolved without one.
            if normalized_type in _LOAN_TYPES | _RETURN_TYPES | _NA_TYPES:
                continue
        if in_id is None and in_name is not None:
            issues.append(
                ResolverIssue(
                    "missing_in_club_id",
                    "Transfer event uses its incoming club name because its id is missing or invalid",
                    transfer_date=transfer_date,
                    raw_event=raw_event,
                )
            )

        digest_input = "|".join(
            (
                transfer_date.isoformat(),
                normalized_type,
                str(out_id or ""),
                out_name or "",
                str(in_id or ""),
                in_name or "",
            )
        )
        normalized.append(
            NormalizedTransferEvent(
                transfer_date=transfer_date,
                raw_type=transfer_type,
                normalized_type=normalized_type,
                out_club=_club(out_id, out_name),
                in_club=_club(in_id, in_name),
                fingerprint=hashlib.sha256(digest_input.encode()).hexdigest(),
                raw=raw_event,
            )
        )

    normalized = _canonicalize_organizations(normalized)
    normalized.sort(key=_canonical_event_key)
    issues.sort(key=_issue_key)
    return NormalizationResult(tuple(normalized), tuple(issues))


def normalize_transfer_events(events: Iterable[Any]) -> NormalizationResult:
    """Normalize and strictly date-sort raw API dictionaries or flat rows.

    Invalid events are retained as deterministic ``issues`` rather than
    raising or manufacturing transfer state.
    """
    return _normalize_transfer_events(events)


def _type_family(event: NormalizedTransferEvent) -> str:
    if event.normalized_type in _LOAN_TYPES:
        return "loan"
    if event.normalized_type in _RETURN_TYPES:
        return "return"
    if event.normalized_type in _NA_TYPES:
        return "na"
    return "permanent"


def _event_evidence_score(event: NormalizedTransferEvent) -> tuple[int, int, int, str]:
    """Prefer the richest same-date duplicate without using input order."""

    clubs = (event.out_club, event.in_club)
    ids = sum(club.api_id is not None for club in clubs)
    names = sum(club.name is not None for club in clubs)
    senior_names = sum(
        bool(club.name) and senior_base_name(club.name).casefold() == club.name.casefold() for club in clubs
    )
    return ids, names, senior_names, event.fingerprint


def _coalesce_events(events: Iterable[NormalizedTransferEvent]) -> list[_CoalescedEvent]:
    """Coalesce exact and one-day affiliate-equivalent provider duplicates."""
    groups: list[_CoalescedEvent] = []

    for event in events:
        matching: _CoalescedEvent | None = None
        for group in reversed(groups):
            representative = group.event
            day_gap = (event.transfer_date - representative.transfer_date).days
            if day_gap > 1:
                break
            if (
                day_gap >= 0
                and event.normalized_type == representative.normalized_type
                and (
                    event.fingerprint == representative.fingerprint
                    or (
                        _same_org(event.out_club, representative.out_club)
                        and _same_org(event.in_club, representative.in_club)
                    )
                )
            ):
                matching = group
                break

        if matching is None:
            groups.append(_CoalescedEvent(event=event, evidence=[event]))
        else:
            matching.evidence.append(event)
            if event.transfer_date == matching.event.transfer_date and _event_evidence_score(
                event
            ) > _event_evidence_score(matching.event):
                matching.event = event

    return groups


def _is_matching_return(event: NormalizedTransferEvent, active: _EpisodeBuilder | None) -> bool:
    return bool(active and _same_org(event.out_club, active.loan_club) and _same_org(event.in_club, active.owner))


def _is_matching_conversion(event: NormalizedTransferEvent, active: _EpisodeBuilder | None) -> bool:
    return bool(active and _same_org(event.out_club, active.owner) and _same_org(event.in_club, active.loan_club))


def _is_implied_return(event: NormalizedTransferEvent, state: _ReducerState) -> bool:
    """Resolve a return whose intervening loan start is absent from the feed."""
    if state.active_episode is not None or state.legal_owner is None:
        return False
    return bool(
        _same_org(event.in_club, state.legal_owner)
        and _same_org(state.current_club, state.legal_owner)
        and not _same_org(event.out_club, state.legal_owner)
    )


def _is_continuity_permanent(event: NormalizedTransferEvent, state: _ReducerState) -> bool:
    """Resolve concrete N/A from an established outgoing state."""
    if state.active_episode is not None:
        active = state.active_episode
        if _is_matching_conversion(event, active):
            return True
        # A definitive owner -> third-club move supersedes the open loan even
        # when the provider hides the fee/type as N/A.  The reverse
        # borrower -> owner topology was checked as a return first.
        return bool(
            _same_org(event.out_club, active.owner)
            and not _same_org(event.in_club, active.owner)
            and not _same_org(event.in_club, active.loan_club)
        )
    source = state.current_club or state.legal_owner
    return bool(source and _same_org(event.out_club, source) and not _same_org(event.in_club, source))


def _same_day_order_key(
    candidate: _CoalescedEvent,
    pending: list[_CoalescedEvent],
    state: _ReducerState,
) -> tuple[Any, ...]:
    event = candidate.event
    family = _type_family(event)

    if family in {"return", "na"} and (
        _is_matching_return(event, state.active_episode) or _is_implied_return(event, state)
    ):
        continuity_rank = 0
    elif family in {"permanent", "na"} and (
        _is_matching_conversion(event, state.active_episode)
        or (family == "na" and _is_continuity_permanent(event, state))
    ):
        continuity_rank = 1
    elif _same_org(event.out_club, state.current_club):
        continuity_rank = 2
    elif _same_org(event.out_club, state.legal_owner):
        continuity_rank = 3
    elif family == "return":
        continuity_rank = 4
    else:
        continuity_rank = 5

    # If another event arrives at this event's source, it is normally the
    # predecessor in the same-day chain.  State continuity still outranks this
    # graph hint so a return/departure cycle is resolved from the active loan.
    predecessor_count = sum(
        1 for other in pending if other is not candidate and _same_org(other.event.in_club, event.out_club)
    )
    family_rank = {"return": 0, "permanent": 1, "loan": 2, "na": 3}[family]
    return continuity_rank, predecessor_count, family_rank, _canonical_event_key(event)


def _classify(event: NormalizedTransferEvent, state: _ReducerState) -> tuple[EventKind, str]:
    family = _type_family(event)
    if family == "loan":
        return "loan_start", "explicit_loan"
    if family == "return":
        return "loan_return", "explicit_return"
    if family == "permanent":
        return "permanent", "explicit_permanent"
    if _is_matching_return(event, state.active_episode):
        return "loan_return", "topology_na_return"
    if _is_matching_conversion(event, state.active_episode):
        return "permanent", "topology_na_conversion"
    if _is_implied_return(event, state):
        return "loan_return", "topology_na_return_missing_start"
    if _is_continuity_permanent(event, state):
        return "permanent", "topology_na_permanent"
    return "unknown", "ambiguous_na"


def _close_episode(
    active: _EpisodeBuilder,
    event: ResolvedTransferEvent,
    reason: LoanEndReason,
) -> None:
    active.end_date = event.transfer_date
    active.end_reason = reason
    active.end_event = event


def _continuity_issue(
    issues: list[ResolverIssue],
    code: str,
    message: str,
    event: NormalizedTransferEvent,
) -> None:
    issues.append(
        ResolverIssue(
            code=code,
            message=message,
            transfer_date=event.transfer_date,
            raw_event=event.raw,
        )
    )


def _apply_event(
    resolved: ResolvedTransferEvent,
    state: _ReducerState,
    episodes: list[_EpisodeBuilder],
    issues: list[ResolverIssue],
) -> None:
    event = resolved.event

    if resolved.kind == "unknown":
        _continuity_issue(
            issues,
            "ambiguous_na",
            "N/A transfer could not be resolved from active loan topology",
            event,
        )
        return

    if resolved.kind == "loan_start":
        old_active = state.active_episode
        owner = event.out_club
        end_reason: LoanEndReason | None = None

        if old_active is not None:
            if _same_org(event.out_club, old_active.loan_club):
                owner = old_active.owner
                end_reason = "subloan"
            elif _same_org(event.out_club, old_active.owner) and _same_org(event.in_club, old_active.loan_club):
                end_reason = "reloan"
            elif _same_org(event.out_club, old_active.owner):
                end_reason = "superseded_by_loan"
            else:
                end_reason = "superseded_by_loan"
                _continuity_issue(
                    issues,
                    "loan_source_discontinuity",
                    "New loan source matches neither the active owner nor borrower",
                    event,
                )
            _close_episode(old_active, resolved, end_reason)
            if end_reason in {"reloan", "superseded_by_loan"}:
                _continuity_issue(
                    issues,
                    "implicit_close_before_reloan",
                    "A later loan start closed the prior episode because the provider omitted its return",
                    event,
                )
        elif state.current_club is not None and not (
            _same_org(event.out_club, state.current_club) or _same_org(event.out_club, state.legal_owner)
        ):
            _continuity_issue(
                issues,
                "loan_source_discontinuity",
                "Loan source does not match the last-known club or owner",
                event,
            )

        active = _EpisodeBuilder(
            owner=owner,
            immediate_source=event.out_club,
            loan_club=event.in_club,
            start_date=event.transfer_date,
            start_event=resolved,
        )
        episodes.append(active)
        state.active_episode = active
        state.legal_owner = owner
        state.current_club = event.in_club
        return

    if resolved.kind == "loan_return":
        active = state.active_episode
        if active is None:
            _continuity_issue(
                issues,
                "return_without_open_loan",
                "Return event has no matching open loan (the provider history may omit a re-loan)",
                event,
            )
            state.legal_owner = event.in_club
        else:
            if _is_matching_return(event, active):
                _close_episode(active, resolved, "return")
                state.legal_owner = active.owner
            else:
                _close_episode(active, resolved, "superseded_by_return")
                _continuity_issue(
                    issues,
                    "return_topology_mismatch",
                    "Return endpoints do not match the open loan",
                    event,
                )
                state.legal_owner = event.in_club
            state.active_episode = None
        state.current_club = event.in_club
        return

    active = state.active_episode
    if active is not None:
        reason: LoanEndReason
        if _is_matching_conversion(event, active):
            reason = "permanent_conversion"
        else:
            reason = "superseded_by_permanent"
        _close_episode(active, resolved, reason)
        state.active_episode = None
    elif state.current_club is not None and not (
        _same_org(event.out_club, state.current_club) or _same_org(event.out_club, state.legal_owner)
    ):
        _continuity_issue(
            issues,
            "permanent_source_discontinuity",
            "Permanent move source does not match the last-known club or owner",
            event,
        )
    state.legal_owner = event.in_club
    state.current_club = event.in_club


def _fee_for(event: NormalizedTransferEvent, kind: EventKind) -> str | None:
    if kind != "permanent" or event.normalized_type in _NA_TYPES:
        return None
    return event.raw_type


def _episode_from_builder(builder: _EpisodeBuilder) -> LoanEpisode:
    return LoanEpisode(
        owner=builder.owner,
        immediate_source=builder.immediate_source,
        loan_club=builder.loan_club,
        start_date=builder.start_date,
        end_date=builder.end_date,
        end_reason=builder.end_reason,
        start_event=builder.start_event,
        end_event=builder.end_event,
    )


def _open_loan_fresh_boundary(start: date, *, start_month: int = 7, start_day: int = 1) -> date:
    """Next end-exclusive season boundary after an unclosed loan start."""
    boundary_year = start.year + 1 if (start.month, start.day) >= (start_month, start_day) else start.year
    return date(boundary_year, start_month, start_day)


def resolve_transfer_state(
    events: Iterable[Any],
    *,
    as_of: date | str,
    initial_owner: ClubRef | Mapping[str, Any] | None = None,
    season_start_month: int = 7,
    season_start_day: int = 1,
) -> TransferResolution:
    """Resolve transfer events chronologically as of a required date.

    An unclosed loan is confirmed only within the competition season in which
    its start was observed. At the next configured boundary it becomes
    ``indeterminate``: absence of a provider return is not evidence that a loan
    continues forever. July 1 remains the compatibility default.

    ``initial_owner`` is optional caller-known state for histories that begin
    mid-stream (notably a first-event ``N/A``). The player is assumed to start
    at that owning club.
    """
    parsed_as_of = _parse_date(as_of)
    if parsed_as_of is None:
        raise ValueError("as_of must be a valid date or ISO date string")
    try:
        date(2000, season_start_month, season_start_day)
    except (TypeError, ValueError) as exc:
        raise ValueError("season start must be a valid month/day") from exc

    normalization = _normalize_transfer_events(events)
    applicable = [event for event in normalization.events if event.transfer_date <= parsed_as_of]
    coalesced = _coalesce_events(applicable)

    starting_owner = _context_club(initial_owner, field_name="initial_owner")
    state = _ReducerState(
        legal_owner=starting_owner,
        current_club=starting_owner,
    )
    episode_builders: list[_EpisodeBuilder] = []
    resolved_events: list[ResolvedTransferEvent] = []
    issues = list(normalization.issues)
    latest_permanent: ResolvedTransferEvent | None = None

    by_date: dict[date, list[_CoalescedEvent]] = {}
    for event in coalesced:
        by_date.setdefault(event.event.transfer_date, []).append(event)

    for transfer_date in sorted(by_date):
        pending = list(by_date[transfer_date])
        while pending:
            chosen = min(pending, key=lambda item: _same_day_order_key(item, pending, state))
            pending.remove(chosen)
            kind, reason = _classify(chosen.event, state)
            resolved = ResolvedTransferEvent(
                event=chosen.event,
                kind=kind,
                reason=reason,
                evidence=tuple(sorted(chosen.evidence, key=_canonical_event_key)),
                fee=_fee_for(chosen.event, kind),
            )
            resolved_events.append(resolved)
            _apply_event(resolved, state, episode_builders, issues)
            if kind == "permanent":
                latest_permanent = resolved

    episodes = tuple(_episode_from_builder(builder) for builder in episode_builders)
    active_loan = episodes[-1] if state.active_episode is not None and episodes else None

    if state.active_episode is not None and active_loan is not None:
        if parsed_as_of < _open_loan_fresh_boundary(
            active_loan.start_date,
            start_month=season_start_month,
            start_day=season_start_day,
        ):
            on_loan: bool | None = True
            loan_state: LoanState = "on_loan"
        else:
            on_loan = None
            loan_state = "indeterminate"
    elif state.legal_owner is None and state.current_club is None:
        on_loan = None
        loan_state = "unknown"
    else:
        on_loan = False
        loan_state = "not_on_loan"

    current_owner = active_loan.owner if on_loan is True and active_loan is not None else None
    issues.sort(key=_issue_key)
    return TransferResolution(
        as_of=parsed_as_of,
        normalized_events=normalization.events,
        events=tuple(resolved_events),
        loan_episodes=episodes,
        legal_owner=state.legal_owner,
        current_club=state.current_club,
        current_owner=current_owner,
        immediate_loan_source=active_loan.immediate_source if active_loan is not None else None,
        active_loan=active_loan,
        on_loan=on_loan,
        loan_state=loan_state,
        latest_permanent_move=latest_permanent,
        issues=tuple(issues),
        season_start_month=season_start_month,
        season_start_day=season_start_day,
    )


def loan_episode_overlaps_season(
    episode: LoanEpisode | Mapping[str, Any],
    season_start_year: int,
    *,
    start_month: int = 7,
    start_day: int = 1,
) -> bool:
    """Return whether two half-open intervals overlap.

    ``season_start_year`` is always the season's start year.  The default
    interval is July 1 through the following July 1; ``start_month=1`` and
    ``start_day=1`` supports calendar-year competitions.
    """
    if isinstance(episode, Mapping):
        raw_start = episode.get("start_date")
        raw_end = episode.get("end_date")
    else:
        raw_start = episode.start_date
        raw_end = episode.end_date

    loan_start = _parse_date(raw_start)
    loan_end = _parse_date(raw_end) if raw_end is not None else None
    if loan_start is None or (raw_end is not None and loan_end is None):
        return False

    try:
        season_start = date(season_start_year, start_month, start_day)
        season_end = date(season_start_year + 1, start_month, start_day)
        if raw_end is None:
            # An unclosed provider loan proves overlap only for the season in
            # which it began.  Treating it as [start, infinity) would recreate
            # the production bug for every later season.
            loan_end = _open_loan_fresh_boundary(
                loan_start,
                start_month=start_month,
                start_day=start_day,
            )
    except (TypeError, ValueError):
        return False

    return loan_start < season_end and loan_end > season_start


__all__ = [
    "ClubRef",
    "LoanEpisode",
    "NormalizationResult",
    "NormalizedTransferEvent",
    "ResolvedTransferEvent",
    "ResolverIssue",
    "TransferResolution",
    "loan_episode_overlaps_season",
    "normalize_transfer_events",
    "resolve_transfer_state",
]
