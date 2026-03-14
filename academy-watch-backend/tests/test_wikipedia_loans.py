import pytest

from src.utils.wikipedia_loans import (
    collect_player_loans_from_wikipedia,
    extract_wikipedia_loans,
)


SENIOR_CAREER_TABLE = """
{| class="wikitable"
! Years !! Team !! Apps (Gls)
|-
|2015– || Manchester United || 287 (87)
|-
|2025– || → Aston Villa (loan) || 10 (2)
|-
|2025– || → Barcelona (loan) || 6 (0)
|-
|2024 || → Nottingham Forest (loan) || 5 (0)
|}
"""


def test_extract_wikipedia_loans_for_season_filters_current_year():
    loans = extract_wikipedia_loans(SENIOR_CAREER_TABLE, season_year=2025)
    names = {(row['loan_team'], row['season_year']) for row in loans}
    assert ('Aston Villa', 2025) in names
    assert ('Barcelona', 2025) in names
    assert all(row['season_year'] == 2025 for row in loans)


def test_extract_wikipedia_loans_deduplicates_and_maps_parent():
    loans = extract_wikipedia_loans(SENIOR_CAREER_TABLE, season_year=2025)
    assert loans
    for row in loans:
        assert row['parent_club'] == 'Manchester United'
        assert row['player_name'] == 'Unknown Player'


PLAYER_WIKITEXTS = {
    'Kobbie Mainoo': """
{| class="wikitable"
! Years !! Team !! Apps (Gls)
|-
|2023– || Manchester United || 35 (3)
|-
|2025– || → Sunderland (loan) || 5 (0)
|}
""",
    'Hannibal Mejbri': """
Kobbie Mainoo is an English professional footballer.

2024 – → Sevilla (loan)
2025 – → Everton (loan)
""",
}


def test_collect_player_loans_from_wikipedia(monkeypatch):
    def fake_search(query: str, *, context: str = '') -> str | None:
        return query if query in PLAYER_WIKITEXTS else None

    def fake_fetch(title: str) -> str:
        return PLAYER_WIKITEXTS.get(title, '')

    monkeypatch.setattr(
        'src.utils.wikipedia_loans.search_wikipedia_title',
        fake_search,
    )
    monkeypatch.setattr(
        'src.utils.wikipedia_loans.fetch_wikitext',
        fake_fetch,
    )

    players = [
        {'name': 'Kobbie Mainoo', 'parent_club': 'Manchester United'},
        {'name': 'Hannibal Mejbri', 'parent_club': 'Manchester United'},
    ]

    loans = collect_player_loans_from_wikipedia(players, season_year=2025)

    assert any(
        row['player_name'] == 'Kobbie Mainoo'
        and row['loan_team'] == 'Sunderland'
        and row['parent_club'] == 'Manchester United'
    for row in loans
    )
    assert any(
        row['player_name'] == 'Hannibal Mejbri'
        and row['loan_team'] == 'Everton'
        and row['parent_club'] == 'Manchester United'
    for row in loans
    )
