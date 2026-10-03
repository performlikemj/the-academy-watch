"""Merged match lines: one line per match, totals built from exactly those lines."""

import random
from datetime import date, datetime

from src.services.match_lines import (
    merge_match_lines,
    opponent_key,
    season_totals,
    seasons_from_entries,
)


def _entry(entry_id, source="self", **overrides) -> dict:
    entry = {
        "id": entry_id,
        "season": 2025,
        "source": source,
        "status": "club_confirmed" if source == "club" else "self_reported",
        "match_date": date(2025, 9, 20),
        "opponent": "Skerraby United",
        "competition": "Wendle & District Senior League",
        "home_away": "home",
        "result_for": 3,
        "result_against": 1,
        "minutes": 90,
        "goals": 0,
        "assists": 0,
        "yellows": 0,
        "reds": 0,
        "saves": None,
        "goals_conceded": None,
        "created_at": datetime(2025, 9, 21, 9, 0),
        "updated_at": datetime(2025, 9, 21, 9, 0),
    }
    entry.update(overrides)
    return entry


def test_opponent_key_trims_collapses_spaces_and_lowercases():
    assert opponent_key("  Skerraby   UNITED ") == "skerraby united"
    assert opponent_key(None) == ""
    assert opponent_key("Skerraby Utd") != opponent_key("Skerraby United")


def test_self_and_club_reports_of_one_match_become_one_club_line():
    lines = merge_match_lines([_entry(1), _entry(2, "club", opponent="skerraby  united ")])

    assert len(lines) == 1
    line = lines[0]
    assert (line["confirmation"], line["self_report"]) == ("club_confirmed", "matches")
    assert (line["match_date"], line["minutes"], line["season"]) == ("2025-09-20", 90, 2025)
    assert line["shared_slot"] is False
    # The line never carries who reported it or an entry id.
    assert not {"id", "reported_by_user_id", "source", "status", "note"} & set(line)


def test_club_figures_win_and_a_different_self_report_is_only_flagged():
    own = _entry(1, minutes=90, goals=2, assists=1)
    club = _entry(2, "club", minutes=74, goals=1, assists=0, yellows=1)
    line = merge_match_lines([own, club])[0]

    assert (line["minutes"], line["goals"], line["assists"], line["yellows"]) == (74, 1, 0, 1)
    assert (line["confirmation"], line["self_report"]) == ("club_confirmed", "differs")
    totals = season_totals([line])
    assert (totals["matches"], totals["minutes"], totals["goals"], totals["assists"]) == (1, 74, 1, 0)
    assert (totals["club_confirmed"], totals["self_reported_only"], totals["differing"]) == (1, 0, 1)


def test_optional_figures_only_disagree_when_both_reports_state_them():
    club = _entry(2, "club", saves=4, goals_conceded=1)
    assert merge_match_lines([_entry(1), club])[0]["self_report"] == "matches"
    assert merge_match_lines([_entry(1, saves=6, goals_conceded=1), club])[0]["self_report"] == "differs"
    assert merge_match_lines([_entry(1, result_for=2), club])[0]["self_report"] == "differs"


def test_a_different_date_or_opponent_is_never_merged():
    lines = merge_match_lines(
        [
            _entry(1),
            _entry(2, "club", match_date=date(2025, 9, 21)),
            _entry(3, "club", opponent="Skerraby Utd"),
        ]
    )

    assert len(lines) == 3
    assert [line["match_date"] for line in lines] == ["2025-09-21", "2025-09-20", "2025-09-20"]
    assert sum(line["confirmation"] == "club_confirmed" for line in lines) == 2
    assert {line["self_report"] for line in lines} == {None}


def test_self_only_match_stays_self_reported():
    line = merge_match_lines([_entry(1, goals=1)])[0]

    assert (line["confirmation"], line["self_report"], line["goals"]) == ("self_reported", None, 1)


def test_club_only_match_has_no_self_report_note():
    line = merge_match_lines([_entry(1, "club")])[0]

    assert (line["confirmation"], line["self_report"]) == ("club_confirmed", None)


def test_disputed_and_unconfirmed_club_rows_are_left_out():
    lines = merge_match_lines(
        [
            _entry(1, status="disputed"),
            _entry(2, "club", status="disputed", match_date=date(2025, 9, 27)),
            _entry(3, "club", status="self_reported", match_date=date(2025, 10, 4)),
        ]
    )

    assert lines == []
    assert season_totals(lines)["matches"] == 0


def _rows_represented(lines) -> int:
    """A paired line stands for two rows (club + own); every other line for one."""
    return sum(2 if line["self_report"] is not None else 1 for line in lines)


def test_two_claimants_reporting_one_match_stay_two_lines_and_both_count():
    player = _entry(1, minutes=45, goals=1)
    guardian = _entry(2, minutes=45, goals=1, opponent="skerraby  united")
    lines = merge_match_lines([guardian, player])

    assert len(lines) == 2
    assert [line["key"] for line in lines] == ["2025-09-20|skerraby united|own-1", "2025-09-20|skerraby united|own-2"]
    assert {(line["confirmation"], line["self_report"], line["shared_slot"]) for line in lines} == {
        ("self_reported", None, True)
    }
    totals = season_totals(lines)
    assert (totals["matches"], totals["minutes"], totals["goals"], totals["self_reported_only"]) == (2, 90, 2, 2)


def test_a_double_header_keeps_both_club_rows():
    first = _entry(1, "club", minutes=45)
    second = _entry(2, "club", minutes=60, result_for=0, result_against=2)
    lines = merge_match_lines([second, first])

    assert [(line["key"], line["minutes"]) for line in lines] == [
        ("2025-09-20|skerraby united|club-1", 45),
        ("2025-09-20|skerraby united|club-2", 60),
    ]
    assert all(line["confirmation"] == "club_confirmed" and line["shared_slot"] for line in lines)
    totals = season_totals(lines)
    assert (totals["matches"], totals["minutes"], totals["club_confirmed"]) == (2, 105, 2)


def test_ambiguous_groups_are_never_paired_and_never_lose_a_row():
    two_own_one_club = merge_match_lines([_entry(1, minutes=45), _entry(2, minutes=50), _entry(3, "club", minutes=74)])
    one_own_two_club = merge_match_lines(
        [_entry(1, minutes=90), _entry(2, "club", minutes=45), _entry(3, "club", minutes=60)]
    )

    for lines, minutes in ((two_own_one_club, 169), (one_own_two_club, 195)):
        assert len(lines) == 3
        assert {line["self_report"] for line in lines} == {None}
        assert all(line["shared_slot"] for line in lines)
        assert len({line["key"] for line in lines}) == 3
        assert season_totals(lines)["minutes"] == minutes
    assert sum(line["confirmation"] == "club_confirmed" for line in two_own_one_club) == 1
    assert sum(line["confirmation"] == "club_confirmed" for line in one_own_two_club) == 2


def test_an_unambiguous_pair_is_not_marked_as_sharing_a_slot():
    paired, alone = merge_match_lines([_entry(1), _entry(2, "club"), _entry(3, match_date=date(2025, 9, 27))])[::-1]

    assert (paired["self_report"], paired["shared_slot"], alone["shared_slot"]) == ("matches", False, False)
    assert paired["key"] == "2025-09-20|skerraby united"


def test_property_totals_equal_the_lines_and_every_undisputed_row_is_represented():
    rng = random.Random(1131)
    opponents = ["Skerraby United", "skerraby  united ", "Skerraby Utd", "Durnsea", "Pellowick Town"]
    for _case in range(2000):
        entries = []
        for entry_id in range(1, rng.randint(0, 14) + 1):
            source = rng.choice(["self", "club"])
            entries.append(
                _entry(
                    entry_id,
                    source,
                    status=rng.choice(["disputed", None, None, None, None])
                    or ("club_confirmed" if source == "club" else "self_reported"),
                    season=2025,
                    match_date=date(2025, 9, rng.randint(1, 4)),
                    opponent=rng.choice(opponents),
                    minutes=rng.choice([0, 30, 45, 90]),
                    goals=rng.randint(0, 2),
                    assists=rng.randint(0, 2),
                    yellows=rng.randint(0, 1),
                    reds=rng.randint(0, 1),
                    saves=rng.choice([None, 0, 3]),
                    goals_conceded=rng.choice([None, 0, 2]),
                )
            )
        lines = merge_match_lines(entries)
        totals = season_totals(lines)

        assert _rows_represented(lines) == sum(entry["status"] != "disputed" for entry in entries)
        assert len({line["key"] for line in lines}) == len(lines)
        assert totals["matches"] == len(lines)
        for field in ("minutes", "goals", "assists"):
            assert totals[field] == sum(line[field] for line in lines)
        for field in ("yellows", "reds"):
            assert (totals[field] or 0) == sum(line[field] for line in lines)
        for field in ("saves", "goals_conceded"):
            assert (totals[field] or 0) == sum(line[field] or 0 for line in lines)
        assert totals["club_confirmed"] + totals["self_reported_only"] == len(lines)
        # A pair exists only where the slot holds exactly one club row and one own row.
        for line in lines:
            if line["self_report"] is not None:
                slot = [
                    entry
                    for entry in entries
                    if entry["status"] != "disputed"
                    and (entry["match_date"].isoformat(), opponent_key(entry["opponent"]))
                    == tuple(line["key"].split("|"))
                ]
                assert sorted(entry["source"] for entry in slot) == ["club", "self"]


def test_a_datetime_is_read_as_its_own_written_calendar_day():
    late_kick_off = datetime(2025, 9, 20, 23, 30)
    lines = merge_match_lines([_entry(1, match_date=late_kick_off), _entry(2, "club")])

    assert len(lines) == 1
    assert lines[0]["match_date"] == "2025-09-20"
    # The next calendar day is a different match, however close the clock times are.
    assert len(merge_match_lines([_entry(1, match_date=datetime(2025, 9, 21, 0, 15)), _entry(2, "club")])) == 2


def test_competition_label_falls_back_to_the_players_when_the_club_left_it_blank():
    line = merge_match_lines([_entry(1), _entry(2, "club", competition=None)])[0]

    assert line["competition"] == "Wendle & District Senior League"


def test_totals_count_each_match_once_and_state_their_sources():
    entries = [
        _entry(1),
        _entry(2, "club"),
        _entry(3, match_date=date(2025, 9, 27), opponent="Durnsea", minutes=62, goals=1, yellows=1),
        _entry(4, "club", match_date=date(2025, 10, 4), opponent="Pellowick Town", minutes=0),
        _entry(5, match_date=date(2025, 10, 11), opponent="Thrandby", minutes=90, assists=2, reds=1),
    ]
    lines = merge_match_lines(entries)
    totals = season_totals(lines)

    assert totals == {
        "matches": 4,
        "appearances": 3,
        "full_matches": 2,
        "minutes": 242,
        "goals": 1,
        "assists": 2,
        "yellows": 1,
        "reds": 1,
        "cards_known": True,
        "saves": None,
        "goals_conceded": None,
        "keeper_matches": 0,
        "club_confirmed": 2,
        "self_reported_only": 2,
        "differing": 0,
    }
    assert totals["minutes"] == sum(line["minutes"] for line in lines)


def test_unknown_cards_are_not_clean_and_empty_is_not_clean():
    assert season_totals([])["cards_known"] is False
    unknown = season_totals([{"minutes": 90, "yellows": None, "reds": None, "confirmation": "self_reported"}])
    assert (unknown["cards_known"], unknown["yellows"], unknown["reds"]) == (False, None, None)


def test_keeper_figures_sum_only_where_stated():
    lines = merge_match_lines(
        [
            _entry(1, "club", saves=5, goals_conceded=0),
            _entry(2, "club", match_date=date(2025, 9, 27), saves=3, goals_conceded=2),
            _entry(3, match_date=date(2025, 10, 4)),
        ]
    )
    totals = season_totals(lines)

    assert (totals["saves"], totals["goals_conceded"], totals["keeper_matches"]) == (8, 2, 2)


def test_seasons_are_grouped_newest_first_with_their_own_totals():
    seasons = seasons_from_entries(
        [
            _entry(1, season=2024, match_date=date(2024, 9, 14), goals=3),
            _entry(2),
            _entry(3, "club"),
        ]
    )

    assert [season["season"] for season in seasons] == [2025, 2024]
    assert [season["totals"]["matches"] for season in seasons] == [1, 1]
    assert [season["totals"]["goals"] for season in seasons] == [0, 3]
    assert seasons[0]["lines"][0]["confirmation"] == "club_confirmed"


def test_iso_string_dates_and_date_objects_share_one_identity():
    lines = merge_match_lines([_entry(1, match_date="2025-09-20"), _entry(2, "club")])

    assert len(lines) == 1
