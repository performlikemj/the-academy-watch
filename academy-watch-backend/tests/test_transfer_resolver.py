"""Regression tests for the pure chronological transfer resolver."""

from copy import deepcopy
from datetime import date
from random import Random
from types import SimpleNamespace

import pytest
from src.services.transfer_resolver import (
    loan_episode_overlaps_season,
    normalize_transfer_events,
    resolve_transfer_state,
)


def transfer(
    transfer_date,
    transfer_type,
    out_id,
    out_name,
    in_id,
    in_name,
):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


HALL = [
    transfer("2023-08-22", "Loan", 49, "Chelsea", 34, "Newcastle"),
    transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
]


def test_hall_is_identical_in_original_reversed_and_shuffled_order():
    shuffled = deepcopy(HALL)
    Random(284492).shuffle(shuffled)
    variants = (HALL, list(reversed(HALL)), shuffled)

    resolutions = [resolve_transfer_state(events, as_of=date(2026, 7, 16)) for events in variants]

    assert resolutions[0] == resolutions[1] == resolutions[2]
    result = resolutions[0]
    assert [event.kind for event in result.events] == ["loan_start", "permanent"]
    assert len(result.loan_episodes) == 1
    episode = result.loan_episodes[0]
    assert (episode.start_date, episode.end_date, episode.end_reason) == (
        date(2023, 8, 22),
        date(2024, 7, 1),
        "permanent_conversion",
    )
    assert result.current_club.api_id == 34
    assert result.current_owner is None
    assert result.legal_owner.api_id == 34
    assert result.on_loan is False
    assert result.loan_state == "not_on_loan"
    assert result.latest_permanent_move.date == date(2024, 7, 1)
    assert result.latest_permanent_move.fee == "€ 33M"


@pytest.mark.parametrize(
    ("permanent_type", "expected_fee"),
    [
        ("€ 5M", "€ 5M"),
        ("Transfer", "Transfer"),
        ("Free", "Free"),
        ("Free Transfer", "Free Transfer"),
        ("N/A", None),
    ],
)
def test_same_destination_permanent_variants_close_the_loan(permanent_type, expected_fee):
    result = resolve_transfer_state(
        [
            transfer("2023-01-10", "Loan", 10, "Parent", 20, "Borrower"),
            transfer("2024-01-10", permanent_type, 10, "Parent", 20, "Borrower"),
        ],
        as_of="2024-01-10",
    )

    assert [event.kind for event in result.events] == ["loan_start", "permanent"]
    assert result.events[-1].classification == "permanent"
    assert result.loan_episodes[0].end_date == date(2024, 1, 10)
    assert result.loan_episodes[0].end_reason == "permanent_conversion"
    assert result.latest_permanent_move.fee == expected_fee
    assert result.current_club.api_id == 20
    assert result.current_owner is None
    assert result.on_loan is False


def test_hall_as_of_filters_future_state_and_uses_end_exclusive_conversion_day():
    before = resolve_transfer_state(HALL, as_of="2024-06-30")
    converted = resolve_transfer_state(HALL, as_of="2024-07-01")
    before_history = resolve_transfer_state(HALL, as_of="2023-08-21")

    assert before.on_loan is True
    assert before.current_owner.api_id == 49
    assert before.current_club.api_id == 34
    assert before.latest_permanent_move is None
    assert [event.kind for event in before.events] == ["loan_start"]
    assert converted.on_loan is False
    assert converted.current_owner is None
    assert converted.latest_permanent_move.fee == "€ 33M"
    assert before_history.current_club is None
    assert before_history.current_owner is None
    assert before_history.loan_state == "unknown"


def test_knauff_july_first_fee_conversion_uses_the_real_adjudicated_shape():
    result = resolve_transfer_state(
        [
            transfer("2022-01-20", "Loan", 165, "Borussia Dortmund", 169, "Eintracht Frankfurt"),
            transfer("2023-07-01", "€ 5M", 165, "Borussia Dortmund", 169, "Eintracht Frankfurt"),
        ],
        as_of="2026-07-16",
    )

    episode = result.loan_episodes[0]
    assert episode.end_date == date(2023, 7, 1)
    assert episode.end_reason == "permanent_conversion"
    assert loan_episode_overlaps_season(episode, 2022) is True
    assert loan_episode_overlaps_season(episode, 2023) is False
    assert result.current_club.api_id == 169
    assert result.current_owner is None
    assert result.latest_permanent_move.fee == "€ 5M"


def test_explicit_returns_are_order_independent_and_date_sorted():
    oldest_first = [
        transfer("2024-01-01", "Loan", 1, "Owner", 2, "Borrower"),
        transfer("2024-06-30", "Return from loan", 2, "Borrower", 1, "Owner"),
    ]
    newest_first = list(reversed(oldest_first))

    old = resolve_transfer_state(oldest_first, as_of="2024-07-01")
    new = resolve_transfer_state(newest_first, as_of="2024-07-01")

    assert old == new
    assert [event.date for event in old.events] == [date(2024, 1, 1), date(2024, 6, 30)]
    assert [event.kind for event in old.events] == ["loan_start", "loan_return"]
    assert old.loan_episodes[0].end_date == date(2024, 6, 30)
    assert old.current_club.api_id == 1
    assert old.current_owner is None
    assert old.on_loan is False


def test_july_first_is_end_exclusive_and_open_loans_do_not_reach_future_seasons():
    closed = {"start_date": "2023-08-22", "end_date": "2024-07-01"}
    open_old = {"start_date": "2023-08-22", "end_date": None}

    assert loan_episode_overlaps_season(closed, 2023) is True
    assert loan_episode_overlaps_season(closed, 2024) is False
    assert loan_episode_overlaps_season(open_old, 2023) is True
    assert loan_episode_overlaps_season(open_old, 2024) is False


def test_season_helper_supports_calendar_years_and_june_thirty_end():
    calendar_loan = {"start_date": "2024-02-01", "end_date": None}
    june_end = {"start_date": "2023-09-01", "end_date": "2024-06-30"}

    assert loan_episode_overlaps_season(calendar_loan, 2024, start_month=1) is True
    assert loan_episode_overlaps_season(calendar_loan, 2025, start_month=1) is False
    assert loan_episode_overlaps_season(june_end, 2023) is True
    assert loan_episode_overlaps_season({"start_date": "2024-01-01", "end_date": "invalid"}, 2024) is False


def test_midseason_conversion_still_overlaps_that_season():
    episode = {"start_date": "2024-01-10", "end_date": "2024-02-10"}
    assert loan_episode_overlaps_season(episode, 2023) is True


def test_saadi_same_day_return_precedes_free_departure_even_when_reversed():
    events = [
        transfer("2024-09-09", "Loan", 67, "Blackburn", 7001, "Ethnikos Achna"),
        transfer("2025-07-01", "Free Transfer", 67, "Blackburn", 7001, "Ethnikos Achna"),
        transfer("2025-07-01", "Back from Loan", 7001, "Ethnikos Achna", 67, "Blackburn"),
    ]

    result = resolve_transfer_state(list(reversed(events)), as_of="2026-07-16")
    same_day = [event for event in result.events if event.date == date(2025, 7, 1)]

    assert [event.kind for event in same_day] == ["loan_return", "permanent"]
    assert [(event.out_club.name, event.in_club.name) for event in same_day] == [
        ("Ethnikos Achna", "Blackburn"),
        ("Blackburn", "Ethnikos Achna"),
    ]
    assert result.loan_episodes[0].end_date == date(2025, 7, 1)
    assert result.current_club.name == "Ethnikos Achna"
    assert result.current_owner is None
    assert result.latest_permanent_move.fee == "Free Transfer"


def test_missing_reloan_return_precedes_same_day_free_departure():
    events = [
        transfer("2024-01-01", "Transfer", 1, "Previous", 10, "Parent"),
        transfer("2025-07-01", "Free Transfer", 10, "Parent", 30, "Next Club"),
        transfer("2025-07-01", "Return from loan", 20, "Missing Borrower", 10, "Parent"),
    ]

    normal = resolve_transfer_state(events, as_of="2025-07-01")
    reversed_result = resolve_transfer_state(list(reversed(events)), as_of="2025-07-01")

    assert normal == reversed_result
    same_day = [event for event in normal.events if event.date == date(2025, 7, 1)]
    assert [event.kind for event in same_day] == ["loan_return", "permanent"]
    assert [(event.out_club.name, event.in_club.name) for event in same_day] == [
        ("Missing Borrower", "Parent"),
        ("Parent", "Next Club"),
    ]
    assert normal.current_club.api_id == 30
    assert normal.legal_owner.api_id == 30
    assert normal.current_owner is None
    assert normal.on_loan is False
    assert normal.latest_permanent_move.fee == "Free Transfer"
    assert "return_without_open_loan" in {issue.code for issue in normal.issues}


def test_mills_reverse_na_to_owner_affiliate_is_a_return():
    result = resolve_transfer_state(
        [
            transfer("2023-07-27", "Loan", 45, "Everton", 1338, "Oxford United"),
            transfer("2024-01-08", "N/A", 1338, "Oxford United", 99945, "Everton U21"),
        ],
        as_of="2026-07-16",
    )

    assert [event.kind for event in result.events] == ["loan_start", "loan_return"]
    assert result.events[-1].reason == "topology_na_return"
    assert result.current_club.organization_key == result.loan_episodes[0].owner.organization_key
    assert result.current_owner is None
    assert result.latest_permanent_move is None
    assert result.on_loan is False


@pytest.mark.parametrize(
    ("owner", "borrower", "start", "conversion"),
    [
        ((505, "Inter"), (9991, "Pro Patria"), "2023-07-20", "2024-07-03"),
        ((157, "Bayern Munich"), (785, "Karlsruhe SC"), "2023-07-01", "2024-07-01"),
    ],
)
def test_same_direction_na_is_a_permanent_conversion(owner, borrower, start, conversion):
    result = resolve_transfer_state(
        [
            transfer(start, "Loan", *owner, *borrower),
            transfer(conversion, "N/A", *owner, *borrower),
        ],
        as_of="2025-01-01",
    )

    assert result.events[-1].kind == "permanent"
    assert result.events[-1].reason == "topology_na_conversion"
    assert result.loan_episodes[0].end_date == date.fromisoformat(conversion)
    assert result.current_club.api_id == borrower[0]
    assert result.current_owner is None


def test_herold_near_date_duplicate_is_coalesced_before_latest_permanent():
    events = [
        transfer("2023-07-01", "Loan", 157, "Bayern Munich", 785, "Karlsruhe SC"),
        transfer("2024-07-01", "N/A", 157, "Bayern Munich", 785, "Karlsruhe SC"),
        transfer("2026-06-30", "Transfer", 785, "Karlsruhe SC", 163, "Borussia Monchengladbach"),
        transfer("2026-06-29", "Transfer", 785, "Karlsruhe SC", 163, "Borussia Monchengladbach"),
    ]

    result = resolve_transfer_state(events, as_of="2026-07-16")

    assert len(result.normalized_events) == 4
    assert len(result.events) == 3
    assert len(result.events[-1].evidence) == 2
    assert result.events[-1].date == date(2026, 6, 29)
    assert result.current_club.api_id == 163
    assert result.latest_permanent_move == result.events[-1]


def test_asllani_shaped_same_day_return_then_new_loan_and_later_return():
    events = [
        transfer("2026-06-29", "Return from loan", 549, "Besiktas", 505, "Inter"),
        transfer("2025-07-01", "Loan", 505, "Inter", 549, "Besiktas"),
        transfer("2025-07-01", "Return from loan", 503, "Torino", 505, "Inter"),
        transfer("2025-01-10", "Loan", 505, "Inter", 503, "Torino"),
    ]

    result = resolve_transfer_state(events, as_of="2026-07-16")
    same_day = [event for event in result.events if event.date == date(2025, 7, 1)]

    assert [event.kind for event in same_day] == ["loan_return", "loan_start"]
    assert len(result.loan_episodes) == 2
    assert result.loan_episodes[0].end_date == date(2025, 7, 1)
    assert result.loan_episodes[1].start_date == date(2025, 7, 1)
    assert result.loan_episodes[1].end_date == date(2026, 6, 29)
    assert result.current_club.api_id == 505
    assert result.current_owner is None
    assert result.on_loan is False


def test_zuccon_reloan_is_a_new_episode_and_affiliate_duplicate_is_coalesced():
    events = [
        transfer("2024-08-23", "Loan", 499, "Atalanta", 1720, "Juve Stabia"),
        transfer("2025-08-31", "Loan", 499, "Atalanta", 1720, "Juve Stabia"),
        transfer("2025-09-01", "Loan", 990499, "Atalanta II", 1720, "Juve Stabia"),
    ]

    result = resolve_transfer_state(list(reversed(events)), as_of="2026-07-16")

    assert len(result.normalized_events) == 3
    assert len(result.events) == 2
    assert len(result.loan_episodes) == 2
    first, second = result.loan_episodes
    assert (first.start_date, first.end_date) == (date(2024, 8, 23), date(2025, 8, 31))
    assert second.start_date == date(2025, 8, 31)
    assert second.end_date is None
    assert first.owner.organization_api_id == second.owner.organization_api_id == 499
    assert len(second.start_event.evidence) == 2
    assert result.loan_state == "indeterminate"
    assert result.on_loan is None
    assert result.current_owner is None
    assert result.legal_owner.organization_api_id == 499
    assert "implicit_close_before_reloan" in {issue.code for issue in result.issues}


def test_pierobon_former_borrowers_never_become_owners():
    events = [
        transfer("2022-08-01", "Loan", 504, "Verona", 1739, "Mantova"),
        transfer("2023-08-01", "Loan", 504, "Verona", 1735, "Triestina"),
        transfer("2024-01-31", "Loan", 504, "Verona", 1720, "Juve Stabia"),
        transfer("2024-07-07", "N/A", 504, "Verona", 1720, "Juve Stabia"),
    ]

    result = resolve_transfer_state(events, as_of="2026-07-16")

    assert len(result.loan_episodes) == 3
    assert {episode.owner.api_id for episode in result.loan_episodes} == {504}
    assert result.current_club.api_id == 1720
    assert result.current_owner is None
    assert result.legal_owner.api_id == 1720
    assert result.latest_permanent_move.reason == "topology_na_conversion"


def test_aseko_affiliate_return_after_missing_reloan_clears_current_loan_and_flags_conflict():
    events = [
        transfer("2025-02-03", "Loan", 990157, "Bayern Munich II", 166, "Hannover 96"),
        transfer("2025-07-01", "N/A", 166, "Hannover 96", 990157, "Bayern Munich II"),
        transfer("2026-06-29", "Return from loan", 166, "Hannover 96", 157, "Bayern Munich"),
    ]

    result = resolve_transfer_state(events, as_of="2026-07-16")

    assert [event.kind for event in result.events] == ["loan_start", "loan_return", "loan_return"]
    assert result.events[1].reason == "topology_na_return"
    assert len(result.loan_episodes) == 1
    assert result.loan_episodes[0].end_date == date(2025, 7, 1)
    assert result.current_club.organization_api_id == 157
    assert result.current_owner is None
    assert result.on_loan is False
    assert "return_without_open_loan" in {issue.code for issue in result.issues}


def test_concrete_na_without_active_episode_uses_state_continuity_not_the_string():
    permanent = resolve_transfer_state(
        [
            transfer("2024-01-01", "Transfer", 1, "A", 2, "B"),
            transfer("2025-01-01", "N/A", 2, "B", 3, "C"),
        ],
        as_of="2025-01-01",
    )
    missing_start_return = resolve_transfer_state(
        [
            transfer("2024-01-01", "Transfer", 1, "A", 2, "B"),
            transfer("2025-01-01", "N/A", 3, "C", 2, "B"),
        ],
        as_of="2025-01-01",
    )
    no_topology = resolve_transfer_state(
        [transfer("2025-01-01", "N/A", 1, "A", 2, "B")],
        as_of="2025-01-01",
    )

    assert permanent.events[-1].kind == "permanent"
    assert permanent.events[-1].reason == "topology_na_permanent"
    assert missing_start_return.events[-1].kind == "loan_return"
    assert missing_start_return.events[-1].reason == "topology_na_return_missing_start"
    assert "return_without_open_loan" in {issue.code for issue in missing_start_return.issues}
    assert no_topology.events[-1].kind == "unknown"
    assert "ambiguous_na" in {issue.code for issue in no_topology.issues}


def test_first_na_uses_explicit_initial_owner_context():
    event = transfer("2025-06-30", "N/A", 33, "Parent", 200, "Destination")

    without_context = resolve_transfer_state([event], as_of="2026-07-16")
    with_context = resolve_transfer_state(
        [event],
        as_of="2026-07-16",
        initial_owner={"id": 33, "name": "Parent"},
    )

    assert without_context.events[0].kind == "unknown"
    assert with_context.events[0].kind == "permanent"
    assert with_context.events[0].reason == "topology_na_permanent"
    assert with_context.current_club.api_id == 200
    assert with_context.legal_owner.api_id == 200
    assert with_context.on_loan is False


def test_permanent_departure_without_destination_remains_resolvable_evidence():
    event = transfer("2025-06-30", "Free agent", 33, "Parent", None, None)

    result = resolve_transfer_state(
        [event],
        as_of="2026-07-16",
        initial_owner={"id": 33, "name": "Parent"},
    )

    assert result.events[0].kind == "permanent"
    assert result.latest_permanent_move is result.events[0]
    assert result.current_club.api_id is None
    assert result.current_club.name is None
    assert result.on_loan is False
    assert "missing_in_club" in {issue.code for issue in result.issues}


def test_exact_duplicate_release_without_destination_is_coalesced_without_false_name_fallback():
    event = transfer("2025-06-30", "Free agent", 33, "Parent", None, None)

    result = resolve_transfer_state(
        [deepcopy(event), deepcopy(event)],
        as_of="2026-07-16",
        initial_owner={"id": 33, "name": "Parent"},
    )

    assert len(result.normalized_events) == 2
    assert len(result.events) == 1
    assert len(result.events[0].evidence) == 2
    assert result.events[0].kind == "permanent"
    assert "missing_in_club" in {issue.code for issue in result.issues}
    assert "missing_in_club_id" not in {issue.code for issue in result.issues}


def test_owner_to_third_club_na_supersedes_an_open_loan():
    result = resolve_transfer_state(
        [
            transfer("2024-08-01", "Loan", 1, "Owner", 2, "Borrower"),
            transfer("2025-01-10", "N/A", 1, "Owner", 3, "Buyer"),
        ],
        as_of="2025-01-10",
    )

    assert [event.kind for event in result.events] == ["loan_start", "permanent"]
    assert result.events[-1].reason == "topology_na_permanent"
    assert result.loan_episodes[0].end_date == date(2025, 1, 10)
    assert result.loan_episodes[0].end_reason == "superseded_by_permanent"
    assert result.current_club.api_id == 3
    assert result.legal_owner.api_id == 3
    assert result.current_owner is None
    assert result.on_loan is False


def test_open_loan_becomes_indeterminate_at_evidence_boundary():
    events = [transfer("2024-08-23", "Loan", 1, "Owner", 2, "Borrower")]

    fresh = resolve_transfer_state(events, as_of="2025-06-30")
    stale = resolve_transfer_state(events, as_of="2025-07-01")

    assert fresh.on_loan is True
    assert fresh.current_owner.api_id == 1
    assert stale.on_loan is None
    assert stale.loan_state == "indeterminate"
    assert stale.current_owner is None
    assert stale.legal_owner.api_id == 1


def test_invalid_fields_are_deterministic_and_name_only_teams_still_resolve():
    events = [
        transfer("2024-01-01junk", "Loan", 1, "Owner", 2, "Borrower"),
        transfer("2024-01-02", None, 1, "Owner", 2, "Borrower"),
        transfer("2024-01-03", "Loan", None, None, 2, "Borrower"),
        transfer("2024-01-04", "Loan", 1, "Owner", None, "Borrower"),
        transfer("2024-06-30", "Return from loan", None, "Borrower", 1, "Owner"),
    ]

    normal = resolve_transfer_state(events, as_of="2024-07-01")
    reversed_result = resolve_transfer_state(list(reversed(events)), as_of="2024-07-01")

    assert normal == reversed_result
    assert [event.kind for event in normal.events] == ["loan_start", "loan_return"]
    assert normal.current_club.api_id == 1
    assert normal.on_loan is False
    codes = {issue.code for issue in normal.issues}
    assert {"invalid_date", "missing_type", "missing_out_club", "missing_in_club_id", "missing_out_club_id"} <= codes


def test_flat_row_objects_are_accepted_without_database_imports():
    row = SimpleNamespace(
        transfer_date=date(2024, 1, 1),
        transfer_type="Transfer",
        out_club_api_id=1,
        out_club_name="A",
        in_club_api_id=2,
        in_club_name="B",
    )

    result = resolve_transfer_state([row], as_of="2024-01-01")

    assert result.events[0].kind == "permanent"
    assert result.current_club.api_id == 2
    assert result.current_owner is None


def test_exact_duplicate_is_one_effective_event_but_keeps_raw_evidence():
    event = transfer("2024-01-01", "Transfer", 1, "A", 2, "B")
    result = resolve_transfer_state([deepcopy(event), deepcopy(event)], as_of="2024-01-01")

    assert len(result.normalized_events) == 2
    assert len(result.events) == 1
    assert len(result.events[0].evidence) == 2


def test_normalizer_handles_empty_history_and_reports_unknown_state():
    normalization = normalize_transfer_events([])
    resolution = resolve_transfer_state([], as_of="2026-07-16")

    assert normalization.events == ()
    assert normalization.issues == ()
    assert resolution.current_club is None
    assert resolution.current_owner is None
    assert resolution.legal_owner is None
    assert resolution.loan_state == "unknown"
    assert resolution.on_loan is None


def test_as_of_is_required_and_must_be_a_strict_iso_date():
    with pytest.raises(TypeError):
        resolve_transfer_state(HALL)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="as_of"):
        resolve_transfer_state(HALL, as_of="2024-07-01T00:00:00")
