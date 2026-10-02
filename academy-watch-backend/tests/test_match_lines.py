"""Merged match lines: one line per match, totals built from exactly those lines."""

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


def test_two_claimants_reporting_one_match_count_once_using_the_latest():
    older = _entry(1, goals=1, updated_at=datetime(2025, 9, 21, 9, 0))
    newer = _entry(2, goals=2, updated_at=datetime(2025, 9, 22, 9, 0))
    lines = merge_match_lines([newer, older])

    assert len(lines) == 1
    assert lines[0]["goals"] == 2
    assert season_totals(lines)["goals"] == 2


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
