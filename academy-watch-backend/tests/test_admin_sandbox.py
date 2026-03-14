import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.models.league import db, LoanFlag, LoanedPlayer, SupplementalLoan, Team
from src.routes.api import issue_user_token
from src.utils.brave_loans import BraveLoanCollection
from src.admin.sandbox_tasks import SandboxContext, run_task as sandbox_run_task


ADMIN_KEY = 'test-admin-key'


def _auth_headers(email='admin@example.com'):
    token = issue_user_token(email, role='admin')['token']
    return {
        'Authorization': f'Bearer {token}',
        'X-API-Key': ADMIN_KEY,
    }


def _create_team(name: str, team_api_id: int, season: int = 2024):
    team = Team(
        team_id=team_api_id,
        name=name,
        country='England',
        season=season,
    )
    db.session.add(team)
    db.session.commit()
    return team


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', ADMIN_KEY)


def test_admin_sandbox_requires_auth(client):
    resp = client.get('/admin/sandbox')
    assert resp.status_code == 401
    body = resp.get_json()
    assert body['error'] == 'Admin login required'


def test_admin_sandbox_lists_tasks(client):
    resp = client.get('/admin/sandbox', headers=_auth_headers())
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'data-task-id="check-missing-loanees"' in html
    assert 'data-task-id="compare-player-stats"' in html
    assert 'data-task-id="wiki-loan-diff"' in html
    assert 'data-task-id="brave-loan-diff"' in html
    assert 'data-task-id="fetch-player-profile"' in html


def test_admin_sandbox_lists_tasks_json(client):
    _create_team('Manchester United', 33)
    resp = client.get('/admin/sandbox?format=json', headers={**_auth_headers(), 'Accept': 'application/json'})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'tasks' in payload
    task_ids = {task['task_id'] for task in payload['tasks']}
    assert 'check-missing-loanees' in task_ids
    assert 'compare-player-stats' in task_ids
    assert 'fetch-player-profile' in task_ids
    assert 'wiki-loan-diff' in task_ids
    assert 'brave-loan-diff' in task_ids
    wiki_task = next(task for task in payload['tasks'] if task['task_id'] == 'wiki-loan-diff')
    team_param = next(param for param in wiki_task['parameters'] if param['name'] == 'team_name')
    assert team_param['options']
    assert any(option['value'] == 'Manchester United' for option in team_param['options'])


def test_brave_loan_diff_identifies_missing_players(app, client, monkeypatch):
    sample_loans = [
        {
            'player_name': 'Ethan Example',
            'parent_club': 'Manchester United',
            'loan_team': 'Barnet',
            'season_year': 2025,
        }
    ]

    collection = BraveLoanCollection(rows=sample_loans, results=[], query='stub-query')

    monkeypatch.setattr('src.admin.sandbox_tasks.collect_loans_from_brave', lambda *args, **kwargs: collection)
    monkeypatch.setattr('src.admin.sandbox_tasks.classify_loan_row', lambda *args, **kwargs: {'valid': False})

    team = _create_team('Manchester United', 33)
    _create_team('Barnet', 123)

    resp = client.post(
        '/admin/sandbox/run/brave-loan-diff',
        headers=_auth_headers(),
        data=json.dumps({'team_name': team.name, 'season': 2025}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    missing = payload['payload']['missing']
    assert missing
    assert missing[0]['player_name'] == 'Ethan Example'


def test_brave_loan_diff_runs_for_all_teams(app, client, monkeypatch):
    rows_by_team = {
        'Manchester United': [
            {
                'player_name': 'Ethan Example',
                'parent_club': 'Manchester United',
                'loan_team': 'Barnet',
                'season_year': 2025,
            }
        ],
        'Arsenal': [
            {
                'player_name': 'Alice Arsenal',
                'parent_club': 'Arsenal',
                'loan_team': 'Plymouth Argyle',
                'season_year': 2025,
            }
        ],
    }

    def fake_collect(team_name, season_year, **_kwargs):
        rows = rows_by_team.get(team_name, [])
        return BraveLoanCollection(rows=rows, results=[{'team': team_name}], query=f'query-{team_name}')

    monkeypatch.setattr('src.admin.sandbox_tasks.collect_loans_from_brave', fake_collect)
    monkeypatch.setattr('src.admin.sandbox_tasks.classify_loan_row', lambda *args, **kwargs: {'valid': False})

    man_utd = _create_team('Manchester United', 33)
    _create_team('Arsenal', 42)
    _create_team('Barnet', 123)
    _create_team('Plymouth Argyle', 321)

    resp = client.post(
        '/admin/sandbox/run/brave-loan-diff',
        headers=_auth_headers(),
        data=json.dumps({'season': 2025, 'run_all_teams': True}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    assert payload['payload']['team'] is None
    missing = payload['payload']['missing']
    names = {row['player_name'] for row in missing}
    assert names == {'Ethan Example', 'Alice Arsenal'}
    meta = payload['meta']
    assert meta.get('run_all_teams') is True
    search_results = meta.get('search_results_by_team') or payload['payload'].get('search_results')
    assert isinstance(search_results, dict)
    assert {man_utd.name, 'Arsenal'}.issubset(set(search_results.keys()))
    assert meta.get('teams_processed') == len(search_results)


def test_fetch_player_profile_by_id(client, monkeypatch):
    sample_profile = {
        'player': {
            'id': 276,
            'name': 'Neymar',
            'firstname': 'Neymar',
            'lastname': 'da Silva Santos Júnior',
            'age': 32,
        }
    }
    stub_client = SimpleNamespace(
        get_player_profile=lambda player_id: sample_profile,
        search_player_profiles=lambda query, season=None, page=1, league_ids=None, team_ids=None: [],
    )
    monkeypatch.setattr('src.routes.api.api_client', stub_client, raising=False)

    resp = client.post(
        '/admin/sandbox/run/fetch-player-profile',
        headers=_auth_headers(),
        data=json.dumps({'player_id': 276}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    profile = payload['payload']['profile']
    assert profile['player']['id'] == 276
    assert payload['summary'].startswith('Player 276:')


def test_fetch_player_profile_search(client, monkeypatch):
    search_results = [
        {'player': {'id': 100, 'name': 'Alex Example'}, 'statistics': []},
        {'player': {'id': 101, 'name': 'Alexa Sample'}, 'statistics': []},
    ]
    stub_client = SimpleNamespace(
        get_player_profile=lambda player_id: None,
        search_player_profiles=lambda query, season=None, page=1, league_ids=None, team_ids=None: search_results,
    )
    monkeypatch.setattr('src.routes.api.api_client', stub_client, raising=False)

    resp = client.post(
        '/admin/sandbox/run/fetch-player-profile',
        headers=_auth_headers(),
        data=json.dumps({'search': 'alex'}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    results = payload['payload']['matches']
    assert len(results) == 2
    assert results[0]['player']['name'] == 'Alex Example'


def test_sandbox_duplicate_loan_scan_flags_active_dupes(client):
    team = _create_team('Manchester United', 33)
    borrower = _create_team('Nottingham Forest', 44)

    base_time = datetime(2024, 8, 1, tzinfo=timezone.utc)

    loan_a = LoanedPlayer(
        player_id=101,
        player_name='Loan Star',
        primary_team_id=team.id,
        primary_team_name=team.name,
        loan_team_id=borrower.id,
        loan_team_name=borrower.name,
        window_key='2024-25::INITIAL',
        is_active=True,
        data_source='test',
        created_at=base_time,
        updated_at=base_time,
    )
    loan_b = LoanedPlayer(
        player_id=101,
        player_name='Loan Star',
        primary_team_id=team.id,
        primary_team_name=team.name,
        loan_team_id=borrower.id,
        loan_team_name=borrower.name,
        window_key='2024-25::WINTER',
        is_active=True,
        data_source='test',
        created_at=base_time + timedelta(days=30),
        updated_at=base_time + timedelta(days=30),
    )
    db.session.add_all([loan_a, loan_b])
    db.session.commit()

    payload = {
        'team_name': team.name,
        'season': 2024,
    }

    resp = client.post(
        '/admin/sandbox/run/loan-duplicates-scan',
        headers=_auth_headers(),
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    duplicates = body['payload']['duplicates']
    assert len(duplicates) == 1
    entry = duplicates[0]
    assert entry['player_id'] == 101
    assert entry['active_count'] == 2
    assert len(entry['rows']) == 2
    assert entry['rows'][0]['window_key'] == '2024-25::WINTER'
def test_wiki_loan_diff_identifies_missing_players(app, client, monkeypatch):
    sample_loans = [
        {
            'player_name': 'Ethan Example',
            'parent_club': 'Manchester United',
            'loan_team': 'Barnet',
            'season_year': 2025,
        }
    ]

    monkeypatch.setattr('src.admin.sandbox_tasks.extract_wikipedia_loans', lambda *args, **kwargs: sample_loans)
    monkeypatch.setattr('src.admin.sandbox_tasks.fetch_wikitext', lambda title: 'stub')
    monkeypatch.setattr('src.admin.sandbox_tasks.classify_loan_row', lambda *args, **kwargs: {'valid': False})

    team = _create_team('Manchester United', 33)
    other = _create_team('Barnet', 123)

    resp = client.post(
        '/admin/sandbox/run/wiki-loan-diff',
        headers=_auth_headers(),
        data=json.dumps({'team_name': team.name, 'season': 2025, 'player_titles': ['Marcus Rashford']}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    missing = payload['payload']['missing']
    assert missing
    assert missing[0]['player_name'] == 'Ethan Example'


def test_wiki_loan_diff_apply_creates_supplemental_entry(app, client, monkeypatch):
    wiki_rows = [
        {
            'player_name': 'Sample Player',
            'parent_club': 'Manchester United',
            'loan_team': 'Barnet',
            'season_year': 2025,
            'raw_row': '2025– || → Barnet (loan)',
        }
    ]

    monkeypatch.setattr('src.admin.sandbox_tasks.extract_wikipedia_loans', lambda *args, **kwargs: wiki_rows)
    monkeypatch.setattr('src.admin.sandbox_tasks.fetch_wikitext', lambda title: 'stub')
    monkeypatch.setattr(
        'src.admin.sandbox_tasks.classify_loan_row',
        lambda *args, **kwargs: {
            'valid': True,
            'player_name': 'Sample Player',
            'parent_club': 'Manchester United',
            'loan_club': 'Barnet',
            'season_start_year': 2025,
            'reason': '',
            'confidence': 0.9,
        },
    )

    parent = _create_team('Manchester United', 33)
    loan_team = _create_team('Barnet', 123)

    resp = client.post(
        '/admin/sandbox/run/wiki-loan-diff',
        headers=_auth_headers(),
        data=json.dumps({
            'team_name': parent.name,
            'season': 2025,
            'player_titles': ['Sample Player'],
            'use_openai': True,
            'apply_changes': True,
        }),
        content_type='application/json',
    )

    assert resp.status_code == 200
    created = SupplementalLoan.query.filter_by(player_name='Sample Player', season_year=2025).first()
    assert created is not None
    assert created.loan_team_name == 'Barnet'


def test_wiki_loan_diff_uses_api_roster(app, client, monkeypatch):
    captured = {}

    def fake_collect(players, season_year, **kwargs):
        captured['players'] = players
        captured['season'] = season_year
        return [
            {
                'player_name': 'Kobbie Mainoo',
                'parent_club': 'Manchester United',
                'loan_team': 'Sunderland',
                'season_year': season_year,
                'wiki_title': 'Kobbie Mainoo',
            }
        ]

    stub_api_client = SimpleNamespace(
        get_team_players=lambda team_id, season: [
            {
                'player': {
                    'id': 999,
                    'name': 'Kobbie Mainoo',
                },
                'statistics': [],
            }
        ]
    )

    monkeypatch.setattr('src.routes.api.api_client', stub_api_client, raising=False)
    monkeypatch.setattr('src.admin.sandbox_tasks.collect_player_loans_from_wikipedia', fake_collect)
    monkeypatch.setattr('src.admin.sandbox_tasks.search_wikipedia_title', lambda *args, **kwargs: None)
    monkeypatch.setattr('src.admin.sandbox_tasks.fetch_wikitext', lambda *args, **kwargs: '')
    monkeypatch.setattr('src.admin.sandbox_tasks.extract_team_loan_candidates', lambda *args, **kwargs: [])
    monkeypatch.setattr('src.admin.sandbox_tasks.extract_wikipedia_loans', lambda *args, **kwargs: [])

    team = _create_team('Manchester United', 33)

    resp = client.post(
        '/admin/sandbox/run/wiki-loan-diff',
        headers=_auth_headers(),
        data=json.dumps({
            'team_name': team.name,
            'season': 2025,
            'use_api_roster': True,
        }),
        content_type='application/json',
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    rows = payload['payload']['wiki_rows']
    assert rows
    assert rows[0]['loan_team'] == 'Sunderland'
    assert captured.get('players'), 'Expected API roster to be passed to collector'
    assert captured['players'][0]['name'] == 'Kobbie Mainoo'
    assert captured['season'] == 2025

def test_wiki_loan_diff_auto_discovers_titles(app, client, monkeypatch):
    parent = _create_team('Manchester United', 33)

    monkeypatch.setattr('src.admin.sandbox_tasks.search_wikipedia_title', lambda query, context='': 'Sample Player' if 'Sample Player' in query else 'Manchester United F.C.')
    monkeypatch.setattr('src.admin.sandbox_tasks.fetch_wikitext', lambda title: 'stub')
    monkeypatch.setattr('src.admin.sandbox_tasks.extract_team_loan_candidates', lambda text, season_year: [{'player_name': 'Sample Player', 'loan_team': 'Barnet', 'season_year': season_year}])
    monkeypatch.setattr('src.admin.sandbox_tasks.extract_wikipedia_loans', lambda text, season_year, player_name, parent_club_hint: [{'player_name': 'Sample Player', 'loan_team': 'Barnet', 'season_year': season_year, 'parent_club': parent_club_hint}])
    monkeypatch.setattr('src.admin.sandbox_tasks.classify_loan_row', lambda *args, **kwargs: {'valid': False})

    resp = client.post(
        '/admin/sandbox/run/wiki-loan-diff',
        headers=_auth_headers(),
        data=json.dumps({'team_name': parent.name, 'season': 2025}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    missing = resp.get_json()['payload']['missing']
    assert missing
    assert missing[0]['player_name'] == 'Sample Player'


def test_delete_supplemental_loan_task_removes_row(app, client):
    with app.app_context():
        parent = _create_team('Parent FC', 101)
        loan_team = _create_team('Loan FC', 202)

        row = SupplementalLoan(
            player_name='Jordan Loan',
            parent_team_id=parent.id,
            parent_team_name=parent.name,
            loan_team_id=loan_team.id,
            loan_team_name=loan_team.name,
            season_year=2025,
        )
        db.session.add(row)
        db.session.commit()
        supp_id = row.id

    resp = client.post(
        '/admin/sandbox/run/delete-supplemental-loan',
        headers=_auth_headers(),
        data=json.dumps({'supplemental_id': supp_id, 'confirm': True}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    assert payload['payload']['deleted_id'] == supp_id

    with app.app_context():
        assert SupplementalLoan.query.get(supp_id) is None


def test_check_missing_loanees_task_detects_flags(app, client):
    parent = _create_team('Parent FC', 100)
    loan_team = _create_team('Loan FC', 200)

    existing_loan = LoanedPlayer(
        player_id=456,
        player_name='Existing Loanee',
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=loan_team.id,
        loan_team_name=loan_team.name,
        window_key='2024-25::FULL',
    )
    db.session.add(existing_loan)

    missing_flag = LoanFlag(
        player_api_id=999,
        primary_team_api_id=parent.team_id,
        reason='Should be tracked',
    )
    db.session.add(missing_flag)

    covered_flag = LoanFlag(
        player_api_id=456,
        primary_team_api_id=parent.team_id,
        reason='Already present',
    )
    db.session.add(covered_flag)
    db.session.commit()

    resp = client.post(
        '/admin/sandbox/run/check-missing-loanees',
        headers=_auth_headers(),
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    missing = payload['payload']['missing']
    assert len(missing) == 1
    assert missing[0]['player_api_id'] == 999
    assert payload['payload']['missing_count'] == 1


def test_compare_player_stats_reports_diff(app, client, monkeypatch):
    parent = _create_team('Parent FC', 101)
    loan_team = _create_team('Loan FC', 201)
    player = LoanedPlayer(
        player_id=555,
        player_name='Sample Player',
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=loan_team.id,
        loan_team_name=loan_team.name,
        goals=5,
        assists=0,
        minutes_played=450,
        window_key='2024-25::FULL',
    )
    db.session.add(player)
    db.session.commit()

    stub_client = SimpleNamespace(
        get_player_by_id=lambda player_id, season=None: {
            'player': {'id': player_id, 'name': 'Sample Player'},
            'statistics': [
                {
                    'games': {'minutes': 540},
                    'goals': {'total': 5, 'assists': 2},
                }
            ],
        }
    )
    monkeypatch.setattr('src.routes.api.api_client', stub_client, raising=False)

    resp = client.post(
        '/admin/sandbox/run/compare-player-stats',
        headers=_auth_headers(),
        data=json.dumps({'player_id': 555}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    diff = payload['payload']['diff']
    assert diff['assists']['db'] == 0
    assert diff['assists']['api'] == 2
    assert diff['assists']['delta'] == 2
    assert payload['payload']['player']['player_id'] == 555
def test_backfill_team_countries_task_updates_missing_entries(app, monkeypatch):
    with app.app_context():
        t1 = Team(team_id=8001, name='Club Uno', country='', season=2025)
        t2 = Team(team_id=8002, name='Club Dos', country='', season=2025)
        t3 = Team(team_id=8003, name='Club Tres', country='Spain', season=2025)
        db.session.add_all([t1, t2, t3])
        db.session.commit()

        class StubClient:
            def __init__(self):
                self.calls = []

            def get_team_by_id(self, team_id, season=None):
                self.calls.append(team_id)
                return {
                    'team': {
                        'id': team_id,
                        'country': 'Argentina' if team_id == 8001 else 'Uruguay',
                        'name': 'placeholder',
                    }
                }

        stub = StubClient()
        context = SandboxContext(db_session=db.session, api_client=stub)

        result = sandbox_run_task('backfill-team-countries', {}, context)

        assert result['status'] == 'ok'
        payload = result['payload']
        assert payload['updated'] == 2
        assert set(payload['team_ids']) == {t1.id, t2.id}
        assert stub.calls == [8001, 8002]

        db.session.refresh(t1)
        db.session.refresh(t2)
        db.session.refresh(t3)
        assert t1.country == 'Argentina'
        assert t2.country == 'Uruguay'
        assert t3.country == 'Spain'
