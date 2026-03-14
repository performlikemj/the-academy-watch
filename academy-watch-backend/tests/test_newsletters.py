import base64
import json
import os
from copy import deepcopy
from datetime import date, timedelta
import uuid

from flask import render_template

from src.models.league import db, Team, Newsletter, NewsletterComment, UserSubscription, Player, SupplementalLoan
from src.routes.api import _deliver_newsletter_via_webhook, issue_user_token, render_newsletter
from src.agents import weekly_agent, weekly_newsletter_agent as weekly_nl_agent
from src.agents.weekly_newsletter_agent import (
    _apply_stat_driven_summaries,
    _build_player_report_item,
    _enforce_loanee_metadata,
    compose_team_weekly_newsletter,
)
from src.api_football_client import APIFootballClient


class _DummyResponse:
    status_code = 200
    text = 'ok'


def _test_slug(prefix: str = 'newsletter') -> str:
    return f"{prefix}-{uuid.uuid4().hex}"

def _stub_render_variants(parsed, team_name):
    return {'web_html': '', 'email_html': '', 'text': ''}


def test_auto_send_uses_prior_season_subscriptions(app, monkeypatch):
    monkeypatch.setenv('N8N_EMAIL_WEBHOOK_URL', 'https://example.com/webhook')
    monkeypatch.setenv('EMAIL_FROM_NAME', 'The Academy Watch Test')
    monkeypatch.setenv('EMAIL_FROM_ADDRESS', 'newsletter@example.com')

    prev_team = Team(team_id=123, name='Club FC', country='England', season=2023)
    curr_team = Team(team_id=123, name='Club FC', country='England', season=2024)
    db.session.add_all([prev_team, curr_team])
    db.session.commit()

    subscription = UserSubscription(
        email='fan@example.com',
        team_id=prev_team.id,
        active=True,
        unsubscribe_token='tok-prev-season',
    )
    db.session.add(subscription)
    db.session.commit()

    newsletter = Newsletter(
        team_id=curr_team.id,
        title='Club FC Weekly',
        content=json.dumps({'title': 'Club FC Weekly'}),
        structured_content=json.dumps({
            'title': 'Club FC Weekly',
            'summary': 'Summary placeholder',
            'sections': [],
        }),
        issue_date=date(2024, 9, 20),
        week_start_date=date(2024, 9, 13),
        week_end_date=date(2024, 9, 19),
        published=True,
        public_slug=_test_slug('club-fc'),
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)

    sent_payloads: list[dict] = []

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        sent_payloads.append({'url': url, 'json': json})
        return _DummyResponse()

    monkeypatch.setattr('requests.post', fake_post)

    with app.test_request_context('/'):
        result = _deliver_newsletter_via_webhook(newsletter)

    assert result['status'] == 'ok'
    assert result['recipient_count'] == 1
    assert sent_payloads and sent_payloads[0]['json']['email'] == 'fan@example.com'


def test_deliver_newsletter_uses_link_base_for_unsubscribe(app, monkeypatch):
    monkeypatch.setenv('N8N_EMAIL_WEBHOOK_URL', 'https://example.com/webhook')
    monkeypatch.setenv('NEWSLETTER_LINK_BASE_URL', 'https://app.theacademywatch.com')

    team = Team(team_id=999, name='Link FC', country='England', season=2024)
    db.session.add(team)
    db.session.commit()

    subscription = UserSubscription(
        email='linkfan@example.com',
        team_id=team.id,
        active=True,
        unsubscribe_token='tok-link-test',
    )
    db.session.add(subscription)
    db.session.commit()

    newsletter = Newsletter(
        team_id=team.id,
        title='Link FC Weekly',
        content=json.dumps({'title': 'Link FC Weekly'}),
        structured_content=json.dumps({'title': 'Link FC Weekly', 'sections': []}),
        issue_date=date(2024, 9, 20),
        week_start_date=date(2024, 9, 13),
        week_end_date=date(2024, 9, 19),
        published=True,
        public_slug=_test_slug('link-fc'),
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)

    captured: list[dict] = []

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        captured.append({'url': url, 'json': json})
        return _DummyResponse()

    monkeypatch.setattr('requests.post', fake_post)

    with app.test_request_context('/'):
        _deliver_newsletter_via_webhook(newsletter)

    assert captured, 'Expected payload to be sent via webhook'
    unsubscribe_url = captured[0]['json']['meta']['unsubscribe_url']
    assert unsubscribe_url == 'https://app.theacademywatch.com/subscriptions/unsubscribe/tok-link-test'
    expected_public_slug = newsletter.public_slug
    assert expected_public_slug
    html_payload = captured[0]['json']['html']
    assert f'/newsletters/{expected_public_slug}' in html_payload


def test_newsletter_template_includes_buy_me_coffee_button(app):
    with app.app_context():
        html = render_template(
            'newsletter_email.html',
            title='Weekly Update',
            team_name='The Academy Watch',
            range=('Jan 1', 'Jan 7'),
            summary='Summary',
            highlights=[],
            sections=[],
            unsubscribe_url='https://example.com/unsub',
        )

    assert 'buymeacoffee.com/TheAcademyWatch' in html
    assert 'Buy me a coffee' in html


def test_lint_and_enrich_infers_player_id_from_latest_lookup(app, monkeypatch):
    with app.app_context():
        content = {
            'title': 'Weekly Update',
            'summary': '',
            'sections': [
                {
                    'title': 'Highlights',
                    'items': [
                        {
                            'player_name': 'H. Ogunneye',
                            'loan_team': 'Newport County',
                            'stats': {
                                'minutes': 90,
                                'goals': 0,
                                'assists': 0,
                                'yellows': 0,
                                'reds': 0,
                            },
                        }
                    ]
                }
            ]
        }

        lookup_key = weekly_agent._normalize_player_key('H. Ogunneye')
        weekly_agent._set_latest_player_lookup({
            lookup_key: [
                {
                    'player_id': 555,
                    'loan_team_api_id': 200,
                    'loan_team_name': 'Newport County',
                }
            ]
        })

        monkeypatch.setattr(weekly_agent, '_player_photo_for', lambda pid: f'https://cdn.example.com/players/{pid}.png')
        monkeypatch.setattr(weekly_agent, '_team_logo_for_player', lambda pid, loan_team_name=None: f'https://cdn.example.com/teams/{pid}.png')

        adjusted, changed = weekly_agent._apply_player_lookup(content)
        assert changed is True

        enriched = weekly_agent.lint_and_enrich(adjusted)
        item = enriched['sections'][0]['items'][0]
        assert item['player_id'] == 555
        assert item['player_photo'] == 'https://cdn.example.com/players/555.png'
        assert item['loan_team_logo'] == 'https://cdn.example.com/teams/555.png'

        weekly_agent._set_latest_player_lookup({})


def test_build_player_summary_skips_llm_for_zero_minutes(monkeypatch):
    called = False

    def fake_llm(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM should not run for zero-minute players")

    monkeypatch.setattr(weekly_nl_agent, '_summarize_player_with_groq', fake_llm)
    monkeypatch.setenv('NEWSLETTER_USE_GROQ', '1')

    loanee = {
        'player_name': 'J. Prospect',
        'player_full_name': 'J. Prospect',
        'loan_team_name': 'Sample FC',
        'can_fetch_stats': True,
        'totals': {
            'minutes': 0,
            'goals': 0,
            'assists': 0,
            'yellows': 0,
            'reds': 0,
        },
        'matches': [
            {
                'played': False,
                'competition': 'League Cup',
                'opponent': 'Rivals FC',
                'score': '0-0',
                'result': 'D',
            }
        ],
    }

    media_hits = [
        {
            'title': 'Academy prospect shines in training',
            'url': 'https://example.com/report',
        }
    ]

    item = _build_player_report_item(loanee, hits=media_hits, week_start=date(2025, 10, 27), week_end=date(2025, 11, 2))

    assert 'Media spotlight' in item['week_summary']
    assert called is False


def test_match_notes_render_scores_without_json(monkeypatch):
    monkeypatch.setenv('NEWSLETTER_USE_GROQ', '0')
    loanee = {
        'player_name': 'Match Test',
        'player_full_name': 'Match Test',
        'loan_team_name': 'Sample FC',
        'can_fetch_stats': True,
        'totals': {'minutes': 90, 'goals': 0, 'assists': 0},
        'matches': [
            {
                'competition': 'Premier League',
                'opponent': 'Liverpool',
                'score': {'home': 2, 'away': 0},
            }
        ],
    }

    assert weekly_nl_agent._format_score({'home': 2, 'away': 0}, None) == '2-0'
    item = _build_player_report_item(loanee, hits=[], week_start=date(2025, 10, 27), week_end=date(2025, 11, 2))
    assert isinstance(loanee['matches'][0]['score'], dict)
    assert item['match_notes'][0] == 'Premier League vs Liverpool: 2-0.'


def test_persist_newsletter_assigns_public_slug(app, monkeypatch):
    monkeypatch.setattr(weekly_nl_agent, '_render_variants', _stub_render_variants)

    with app.app_context():
        team = Team(team_id=321, name='Placeholder FC', country='England', season=2024)
        db.session.add(team)
        db.session.commit()

        content = json.dumps({
            'title': 'Placeholder FC Newsletter',
            'summary': 'Testing placeholder slug path',
            'sections': [],
        })

        newsletter = weekly_nl_agent.persist_newsletter(
            team_db_id=team.id,
            content_json_str=content,
            week_start=date(2024, 9, 1),
            week_end=date(2024, 9, 7),
            issue_date=date(2024, 9, 8),
            newsletter_type='weekly',
        )

        assert newsletter.public_slug
        assert newsletter.public_slug.startswith('placeholder-fc-') or newsletter.public_slug.startswith('newsletter-')


def test_lint_and_enrich_attaches_sofascore_id_when_present(app):
    with app.app_context():
        player = Player(player_id=777, name='Harrison Ogunneye')
        # Expecting new sofascore_id column to persist Sofascore mapping
        player.sofascore_id = 1101989
        db.session.add(player)
        db.session.commit()

        content = {
            'title': 'Weekly Update',
            'sections': [
                {
                    'title': 'Active Loans',
                    'items': [
                        {
                            'player_id': 777,
                            'player_name': 'H. Ogunneye',
                            'loan_team': 'Newport County',
                            'stats': {
                                'minutes': 90,
                                'goals': 0,
                                'assists': 0,
                                'yellows': 0,
                                'reds': 0,
                            },
                        }
                    ],
                }
            ],
        }

        enriched = weekly_agent.lint_and_enrich(content)
        item = enriched['sections'][0]['items'][0]
        assert item['player_id'] == 777
        assert item.get('sofascore_player_id') == 1101989


def test_apply_stat_summaries_uses_player_id_over_display_name():
    report = {
        'loanees': [
            {
                'player_id': 18,
                'player_name': 'Jadon Sancho',
                'player_full_name': 'Jadon Sancho',
                'loan_team_name': 'Aston Villa',
                'loan_team_id': 66,
                'totals': {
                    'minutes': 112,
                    'goals': 0,
                    'assists': 1,
                    'shots_total': 3,
                    'shots_on': 2,
                    'passes_total': 45,
                    'passes_key': 1,
                    'tackles_total': 2,
                    'duels_total': 14,
                    'duels_won': 6,
                },
                'matches': [
                    {
                        'opponent': 'Manchester City',
                        'score': '1-0',
                        'result': 'W',
                        'played': True,
                        'match_notes': ['Assist vs Manchester City'],
                    }
                ],
            },
            {
                'player_id': 909,
                'player_name': 'Marcus Rashford',
                'player_full_name': 'Marcus Rashford',
                'loan_team_name': 'Barcelona',
                'loan_team_id': 529,
                'totals': {
                    'minutes': 180,
                    'goals': 2,
                    'assists': 1,
                    'shots_total': 6,
                    'shots_on': 3,
                    'passes_total': 58,
                    'passes_key': 4,
                    'tackles_total': 1,
                    'duels_total': 18,
                    'duels_won': 7,
                },
                'matches': [
                    {
                        'opponent': 'Real Madrid',
                        'score': '1-2',
                        'result': 'L',
                        'played': True,
                        'match_notes': ['Assist vs Real Madrid'],
                    },
                    {
                        'opponent': 'Olympiakos',
                        'score': '6-1',
                        'result': 'W',
                        'played': True,
                        'match_notes': ['Two goals vs Olympiakos'],
                    },
                ],
            },
        ],
    }

    content = {
        'sections': [
            {
                'title': 'Active Loans',
                'items': [
                    {
                        'player_id': 18,
                        'player_name': 'J. Sancho',
                        'loan_team': 'Aston Villa',
                        'stats': {},
                    },
                    {
                        'player_id': 909,
                        'player_name': 'J. Sancho',  # Intentional duplicate to stress matching
                        'loan_team': 'Barcelona',
                        'stats': {},
                    },
                ],
            }
        ]
    }

    updated = _apply_stat_driven_summaries(deepcopy(content), report, brave_ctx={})
    items = updated['sections'][0]['items']

    sancho_summary = items[0]['week_summary']
    rashford_summary = items[1]['week_summary']

    assert 'Manchester City' in sancho_summary
    assert 'across 2 matches' in rashford_summary
    assert ('2 goals' in rashford_summary) or ('two goals' in rashford_summary.lower())


def test_apply_stat_summaries_respects_can_fetch_stats_flag():
    report = {
        'loanees': [
            {
                'player_id': None,
                'player_name': 'E. Kana-Biyik',
                'player_full_name': 'Enzo Kana-Biyik',
                'loan_team_name': 'Lausanne-Sport',
                'loan_team_id': None,
                'can_fetch_stats': False,
                'totals': {
                    'minutes': 0,
                    'goals': 0,
                    'assists': 0,
                    'shots_total': 0,
                    'shots_on': 0,
                    'passes_total': 0,
                    'passes_key': 0,
                    'tackles_total': 0,
                    'duels_total': 0,
                    'duels_won': 0,
                },
                'matches': [],
            }
        ]
    }

    content = {
        'sections': [
            {
                'title': 'Active Loans',
                'items': [
                    {
                        'player_name': 'E. Kana-Biyik',
                        'loan_team': 'Lausanne-Sport',
                        'can_fetch_stats': True,  # Simulate LLM output defaulting to True
                        'stats': {'minutes': 0},
                        'week_summary': 'Did not feature this week.',
                    }
                ],
            }
        ]
    }

    updated = _apply_stat_driven_summaries(deepcopy(content), report, brave_ctx={})
    item = updated['sections'][0]['items'][0]

    assert item['can_fetch_stats'] is False
    assert "We can’t track detailed stats" in item['week_summary']
    assert 'unused' not in item['week_summary']


def test_supplemental_loans_preserve_sofascore_id_in_summary(app, monkeypatch):
    with app.app_context():
        parent = Team(team_id=101, name='Parent FC', country='England', season=2025)
        loan_team = Team(team_id=202, name='Loan FC', country='England', season=2025)
        db.session.add_all([parent, loan_team])
        db.session.commit()

        supplemental = SupplementalLoan(
            player_name='Jordan Loan',
            parent_team_id=parent.id,
            parent_team_name=parent.name,
            loan_team_id=loan_team.id,
            loan_team_name=loan_team.name,
            season_year=2025,
            sofascore_player_id=1101989,
        )
        db.session.add(supplemental)
        db.session.commit()

        client = APIFootballClient()
        monkeypatch.setattr(client, 'get_team_name', lambda *_args, **_kwargs: parent.name)

        week_start = date(2025, 9, 15)
        week_end = week_start + timedelta(days=6)

        summary = client.summarize_parent_loans_week(
            parent_team_db_id=parent.id,
            parent_team_api_id=parent.team_id,
            season=2025,
            week_start=week_start,
            week_end=week_end,
            include_team_stats=False,
            db_session=db.session,
        )

        supplemental_items = [it for it in summary['loanees'] if it.get('source') == 'supplemental']
        assert supplemental_items, 'Expected supplemental source entries in weekly summary'
        assert supplemental_items[0].get('sofascore_player_id') == 1101989
        assert supplemental_items[0].get('loan_team_country') == 'England'


def test_newsletter_templates_render_sofascore_embed_when_available(app):
    sections = [
        {
            'title': 'Active Loans',
            'items': [
                {
                    'player_name': 'H. Ogunneye',
                    'loan_team': 'Newport County',
                    'stats': {
                        'minutes': 90,
                        'goals': 0,
                        'assists': 0,
                        'yellows': 0,
                        'reds': 0,
                    },
                    'sofascore_player_id': 1101989,
                }
            ],
        }
    ]

    with app.app_context():
        email_html = render_template(
            'newsletter_email.html',
            title='Weekly Update',
            team_name='The Academy Watch',
            sections=sections,
            highlights=[],
        )
        web_html = render_template(
            'newsletter_web.html',
            title='Weekly Update',
            team_name='The Academy Watch',
            sections=sections,
            highlights=[],
        )

    expected_src = 'https://widgets.sofascore.com/embed/player/1101989?widgetTheme=dark'
    assert expected_src in email_html
    assert expected_src in web_html
    assert 'Sofascore for H. Ogunneye' in email_html
    assert 'Sofascore for H. Ogunneye' in web_html


def test_templates_hide_stats_for_untracked_players(app):
    sections = [
        {
            'title': 'Active Loans',
            'items': [
                {
                    'player_name': 'Jordan Loan',
                    'loan_team': 'Lower League FC',
                    'week_summary': 'Jordan Loan is on our radar but stats are unavailable from the provider.',
                    'can_fetch_stats': False,
                    'stats': {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0},
                    'links': ['https://example.com/update'],
                    'sofascore_player_id': 123456,
                }
            ],
        }
    ]

    with app.app_context():
        email_html = render_template(
            'newsletter_email.html',
            title='Weekly Update',
            team_name='The Academy Watch',
            sections=sections,
            highlights=[],
        )
        web_html = render_template(
            'newsletter_web.html',
            title='Weekly Update',
            team_name='The Academy Watch',
            sections=sections,
            highlights=[],
        )

    assert "We can’t track detailed stats for this player yet." in email_html
    assert "We can’t track detailed stats for this player yet." in web_html
    assert "0’" not in email_html
    assert "0’" not in web_html


def test_enforce_metadata_handles_core_supplemental_and_internet():
    core_item = {
        'player_name': 'Core Player',
        'player_id': 777,
        'stats': {'minutes': 120, 'goals': 1, 'assists': 0, 'yellows': 0, 'reds': 0},
        'sofascore_player_id': 555,
    }
    supplemental_item = {
        'player_name': 'Supp Player',
        'stats': {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0},
    }
    internet_item = {
        'player_name': 'Supp Player',
        'links': ['https://example.com'],
        'stats': {'minutes': 0},
        'sofascore_player_id': 999,
        'player_photo': 'https://example.com/photo.png',
    }

    content = {
        'sections': [
            {'title': 'Active Loans', 'items': [core_item, supplemental_item]},
            'legacy-string-section',
            {'title': 'What the Internet is Saying', 'items': [internet_item]},
        ]
    }

    meta_pid = {
        777: {'can_fetch_stats': True, 'sofascore_player_id': 555},
    }
    meta_key = {
        weekly_agent._normalize_player_key('Supp Player'): {
            'can_fetch_stats': False,
            'sofascore_player_id': 222,
        }
    }

    updated = _enforce_loanee_metadata(content, meta_pid, meta_key)
    assert [sec['title'] for sec in updated['sections']] == ['Active Loans', 'Supplemental Loans']
    active = updated['sections'][0]['items'][0]
    supplemental = updated['sections'][1]['items'][0]

    # Core players retain stats and sofascore ids
    assert active.get('can_fetch_stats') is True
    assert 'stats' in active
    assert active.get('sofascore_player_id') == 555

    # Supplemental players move to separate section, drop stats, keep sofascore
    assert supplemental.get('can_fetch_stats') is False
    assert 'stats' not in supplemental
    assert supplemental.get('sofascore_player_id') == 222
    assert supplemental.get('week_summary') == "We can’t track detailed stats for this player yet."

    # Links from internet context merged onto supplemental item
    internet_links = supplemental.get('links')
    assert internet_links and internet_links[0] == 'https://example.com'


def test_newsletter_list_includes_rendered_variants(app, client):
    with app.app_context():
        team = Team(team_id=3030, name='Rendered FC', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        rendered_payload = {
            'title': 'Rendered FC Weekly',
            'summary': 'Summary placeholder',
            'sections': [],
            'rendered': {
                'web_html': '<div class="player-stats-grid"><div class="stat-group"><span>Shots</span></div></div>',
                'email_html': '<div>Email content</div>',
                'text': 'Shots: 3',
            },
        }

        newsletter = Newsletter(
            team_id=team.id,
            title='Rendered FC Weekly',
            content=json.dumps({'title': 'Rendered FC Weekly'}),
            structured_content=json.dumps(rendered_payload),
            published=True,
            public_slug=_test_slug('rendered-fc'),
        )
        db.session.add(newsletter)
        db.session.commit()
        slug_value = newsletter.public_slug

    response = client.get('/newsletters?published_only=true')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list) and len(data) == 1
    row = data[0]
    assert 'rendered' in row, 'Expected rendered variants to be included in newsletter payload'
    assert isinstance(row['rendered'], dict)
    assert 'web_html' in row['rendered']
    assert 'Shots' in row['rendered']['web_html']
    assert row.get('public_slug') == slug_value


def test_compose_weekly_builds_per_player_reports_with_history(app, monkeypatch):
    from datetime import date

    with app.app_context():
        team = Team(team_id=9100, name='Manchester United', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        week_range = ("2025-10-13", "2025-10-19")
        loanee_a = {
            "player_id": 101,
            "player_api_id": 101,
            "player_name": "Marcus Rashford",
            "player_full_name": "Marcus Rashford",
            "loan_team_name": "Sevilla",
            "loan_team_api_id": 1234,
            "loan_team_id": 1234,
            "loan_team_country": "ES",
            "can_fetch_stats": True,
            "totals": {
                "minutes": 90,
                "goals": 1,
                "assists": 0,
                "rating": 7.6,
                "shots_total": 6,
                "shots_on": 3,
                "passes_total": 42,
                "passes_key": 2,
                "tackles_total": 1,
                "duels_total": 8,
                "duels_won": 5,
            },
            "matches": [
                {
                    "opponent": "Real Betis",
                    "played": True,
                    "minutes": 90,
                    "result": "W",
                    "score": "2-0",
                    "competition": "La Liga",
                }
            ],
            "season_context": {
                "season_stats": {
                    "games_played": 8,
                    "minutes": 620,
                    "goals": 4,
                    "assists": 2,
                    "yellows": 1,
                    "reds": 0,
                    "shots_total": 30,
                    "shots_on": 15,
                    "passes_key": 12,
                    "tackles_total": 9,
                    "duels_won": 40,
                    "duels_total": 70,
                    "clean_sheets": 2,
                    "avg_rating": 7.1,
                },
                "recent_form": [],
                "trends": {
                    "goals_per_90": 0.58,
                    "assists_per_90": 0.29,
                },
            },
        }
        loanee_b = {
            "player_id": 202,
            "player_api_id": 202,
            "player_name": "Hannibal Mejbri",
            "player_full_name": "Hannibal Mejbri",
            "loan_team_name": "Borussia Dortmund",
            "loan_team_api_id": 5678,
            "loan_team_id": 5678,
            "loan_team_country": "DE",
            "can_fetch_stats": True,
            "totals": {
                "minutes": 28,
                "goals": 0,
                "assists": 1,
                "rating": 6.9,
                "shots_total": 1,
                "shots_on": 0,
                "passes_total": 15,
                "passes_key": 1,
                "tackles_total": 2,
                "duels_total": 7,
                "duels_won": 3,
            },
            "matches": [
                {
                    "opponent": "Bayer Leverkusen",
                    "played": True,
                    "minutes": 28,
                    "result": "D",
                    "score": "1-1",
                    "competition": "Bundesliga",
                }
            ],
            "season_context": {
                "season_stats": {
                    "games_played": 9,
                    "minutes": 410,
                    "goals": 1,
                    "assists": 3,
                    "yellows": 2,
                    "reds": 0,
                    "shots_total": 10,
                    "shots_on": 4,
                    "passes_key": 9,
                    "tackles_total": 18,
                    "duels_won": 28,
                    "duels_total": 55,
                    "clean_sheets": 0,
                    "avg_rating": 6.8,
                },
                "recent_form": [],
                "trends": {
                    "assists_last_5": 2,
                },
            },
        }

        report = {
            "season": "2025-26",
            "range": list(week_range),
            "parent_team": {"name": "Manchester United"},
            "loanees": [loanee_a, loanee_b],
        }

        brave_ctx = {
            '"Marcus Rashford" "Sevilla" match report': [
                {
                    "title": "Rashford shines in Sevilla victory",
                    "url": "https://example.com/rashford",
                }
            ],
            '"Hannibal Mejbri" "Borussia Dortmund" match report': [
                {
                    "title": "Mejbri swings match with late assist",
                    "url": "https://example.com/mejbri",
                }
            ],
        }
        monkeypatch.setattr(weekly_agent, "_set_latest_player_lookup", lambda *_a, **_k: None)
        monkeypatch.setattr(weekly_agent, "_apply_player_lookup", lambda payload, _lookup: (payload, False))
        monkeypatch.setattr(weekly_agent, "lint_and_enrich", lambda payload: payload)
        monkeypatch.setattr(weekly_nl_agent, "_apply_player_lookup", lambda payload, _lookup: (payload, False))
        monkeypatch.setattr(weekly_nl_agent, "legacy_lint_and_enrich", lambda payload: payload)
        monkeypatch.setattr(weekly_nl_agent, "fetch_weekly_report_tool", lambda *_args, **_kwargs: report)
        monkeypatch.setattr(weekly_nl_agent, "brave_context_for_team_and_loans", lambda *_args, **_kwargs: brave_ctx)
        monkeypatch.setattr(weekly_nl_agent, "ENV_VALIDATE_FINAL_LINKS", False)
        monkeypatch.setattr(weekly_nl_agent, "ENV_CHECK_LINKS", False)
        # New Groq summaries
        monkeypatch.setattr(weekly_nl_agent, "ENV_ENABLE_GROQ_SUMMARIES", True)

        def fake_player_summary(loanee, stats, season_ctx, links):
            return f"{loanee['player_name']} produced {stats.get('minutes')} minutes with {stats.get('goals')} goals."
        monkeypatch.setattr(weekly_nl_agent, "_summarize_player_with_groq", fake_player_summary)
        monkeypatch.setattr(weekly_nl_agent, "_summarize_team_with_groq", lambda team_name, window, players: f"{team_name} overview via Groq.")
        monkeypatch.setattr(
            weekly_nl_agent,
            "api_client",
            type(
                "DummyAPI",
                (),
                {
                    "set_season_year": lambda self, *_a, **_k: None,
                    "_prime_team_cache": lambda self, *_a, **_k: None,
                },
            )(),
        )

        output = compose_team_weekly_newsletter(team.id, date(2025, 10, 19))
        content = json.loads(output["content_json"])

    reports_section = next(sec for sec in content["sections"] if sec["title"] == "Player Reports")
    internet_section = next(sec for sec in content["sections"] if sec["title"] == "What the Internet is Saying")

    assert len(reports_section["items"]) == 2
    rashford_item = next(item for item in reports_section["items"] if item["player_name"].startswith("M. Rashford"))
    mejbri_item = next(item for item in reports_section["items"] if item["player_name"].startswith("H. Mejbri"))

    assert rashford_item["week_summary"].startswith("Marcus Rashford produced 90 minutes with 1 goals.")
    assert "Latest coverage: Rashford shines in Sevilla victory." in rashford_item["week_summary"]
    assert rashford_item["links"][0]["url"] == "https://example.com/rashford"

    assert mejbri_item["week_summary"].startswith("Hannibal Mejbri produced 28 minutes with 0 goals.")
    assert "Latest coverage: Mejbri swings match with late assist." in mejbri_item["week_summary"]
    assert mejbri_item["links"][0]["url"] == "https://example.com/mejbri"

    assert any(link for link in internet_section["items"] if link["player_name"].startswith("M. Rashford"))
    assert content["summary"] == "Manchester United overview via Groq."


def test_compose_weekly_handles_supplemental_player(app, monkeypatch):
    from datetime import date

    with app.app_context():
        team = Team(team_id=9200, name='Arsenal', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        week_range = ("2025-10-13", "2025-10-19")
        supplemental_loanee = {
            "player_name": "E. Kana-Biyik",
            "player_full_name": "Eloge Kana-Biyik",
            "loan_team_name": "Lausanne",
            "loan_team_api_id": 2020718,
            "loan_team_id": 2020718,
            "loan_team_country": "CH",
            "can_fetch_stats": False,
            "source": "supplemental",
            "totals": {
                "minutes": 0,
                "goals": 0,
                "assists": 0,
                "rating": None,
                "shots_total": 0,
                "shots_on": 0,
                "passes_total": 0,
                "passes_key": 0,
                "tackles_total": 0,
                "duels_total": 0,
                "duels_won": 0,
            },
            "matches": [],
        }

        report = {
            "season": "2025-26",
            "range": list(week_range),
            "parent_team": {"name": "Arsenal"},
            "loanees": [supplemental_loanee],
        }

        brave_ctx = {
            '"Eloge Kana-Biyik" "Lausanne" match report': [
                {
                    "title": "Kana-Biyik impresses local media despite limited data",
                    "url": "https://example.com/kana-biyik",
                }
            ],
        }

        monkeypatch.setattr(weekly_agent, "_set_latest_player_lookup", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(weekly_agent, "_apply_player_lookup", lambda payload, _lookup: (payload, False))
        monkeypatch.setattr(weekly_agent, "lint_and_enrich", lambda payload: payload)
        monkeypatch.setattr(weekly_nl_agent, "_apply_player_lookup", lambda payload, _lookup: (payload, False))
        monkeypatch.setattr(weekly_nl_agent, "legacy_lint_and_enrich", lambda payload: payload)
        monkeypatch.setattr(weekly_nl_agent, "fetch_weekly_report_tool", lambda *_args, **_kwargs: report)
        monkeypatch.setattr(weekly_nl_agent, "brave_context_for_team_and_loans", lambda *_args, **_kwargs: brave_ctx)
        monkeypatch.setattr(weekly_nl_agent, "ENV_VALIDATE_FINAL_LINKS", False)
        monkeypatch.setattr(weekly_nl_agent, "ENV_CHECK_LINKS", False)
        monkeypatch.setattr(
            weekly_nl_agent,
            "api_client",
            type(
                "DummyAPI",
                (),
                {
                    "set_season_year": lambda self, *_a, **_k: None,
                    "_prime_team_cache": lambda self, *_a, **_k: None,
                },
            )(),
        )

        output = compose_team_weekly_newsletter(team.id, date(2025, 10, 19))
        content = json.loads(output["content_json"])

    sections = content["sections"]
    reports_section = next((sec for sec in sections if sec["title"] == "Player Reports"), None)
    if reports_section is None:
        reports_section = next(sec for sec in sections if sec["title"] == "Supplemental Loans")
    item = reports_section["items"][0]
    week_summary = item["week_summary"]
    assert "We can’t track detailed stats for this player yet." in week_summary
    assert "Kana-Biyik impresses local media despite limited data" in week_summary
    assert item["links"][0]["url"] == "https://example.com/kana-biyik"


def test_compose_weekly_handles_no_loanees(app, monkeypatch):
    with app.app_context():
        team = Team(team_id=4242, name='Everton', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        week_range = ("2025-10-13", "2025-10-19")
        report = {
            "season": "2025-26",
            "range": list(week_range),
            "parent_team": {"name": "Everton"},
            "loanees": [],
        }

        monkeypatch.setattr(weekly_agent, "_set_latest_player_lookup", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(weekly_agent, "_apply_player_lookup", lambda payload, _lookup: (payload, False))
        monkeypatch.setattr(weekly_agent, "lint_and_enrich", lambda payload: payload)
        monkeypatch.setattr(weekly_nl_agent, "_apply_player_lookup", lambda payload, _lookup: (payload, False))
        monkeypatch.setattr(weekly_nl_agent, "legacy_lint_and_enrich", lambda payload: payload)
        monkeypatch.setattr(weekly_nl_agent, "fetch_weekly_report_tool", lambda *_args, **_kwargs: report)

        def _no_brave(*_args, **_kwargs):
            raise AssertionError("brave_context_for_team_and_loans should not run when no loanees exist")
        monkeypatch.setattr(weekly_nl_agent, "brave_context_for_team_and_loans", _no_brave)

        monkeypatch.setattr(weekly_nl_agent, "ENV_VALIDATE_FINAL_LINKS", False)
        monkeypatch.setattr(weekly_nl_agent, "ENV_CHECK_LINKS", False)
        monkeypatch.setattr(weekly_nl_agent, "ENV_ENABLE_GROQ_SUMMARIES", False)
        monkeypatch.setattr(weekly_nl_agent, "ENV_ENABLE_GROQ_TEAM_SUMMARIES", False)
        monkeypatch.setattr(
            weekly_nl_agent,
            "api_client",
            type(
                "DummyAPI",
                (),
                {
                    "set_season_year": lambda self, *_a, **_k: None,
                    "_prime_team_cache": lambda self, *_a, **_k: None,
                    "clear_stats_cache": lambda self, *_a, **_k: None,
                },
            )(),
        )

        output = compose_team_weekly_newsletter(team.id, date(2025, 10, 19))
        content = json.loads(output["content_json"])

    assert content["summary"].startswith("No active loan updates for Everton")
    assert content["sections"][0]["title"] == "Player Reports"
    assert content["sections"][0]["items"] == []


def _write_png(path: str) -> None:
    """Write a tiny opaque PNG for tests without Pillow dependencies."""
    tiny_png = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAI0lEQVQoU2NkYGD4z0AEYBxVSFJgKgImBqoEUx0NFA0AoFoGBPX57HAAAAAASUVORK5CYII="
    )
    with open(path, 'wb') as fh:
        fh.write(tiny_png)


def test_newsletter_web_render_includes_social_meta(app, client, monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://theacademywatch.test')
    monkeypatch.setenv('TWITTER_HANDLE', '@theacademywatch')
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    static_root = app.static_folder
    newsletters_dir = os.path.join(static_root, 'newsletters')
    if os.path.isdir(newsletters_dir):
        for root, dirs, files in os.walk(newsletters_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    team_logo_rel = os.path.join('assets', 'test-team-logo.png')
    team_logo_path = os.path.join(static_root, team_logo_rel)
    os.makedirs(os.path.dirname(team_logo_path), exist_ok=True)
    _write_png(team_logo_path)

    team = Team(team_id=987, name='Meta FC', country='England', season=2025, logo=f'/static/{team_logo_rel}')
    db.session.add(team)
    db.session.commit()

    summary_text = 'Goals, minutes, and form tracker for every United loanee this week.'

    newsletter = Newsletter(
        team_id=team.id,
        title='Manchester United Loan Watch — Week Ending 21 Sep 2025',
        content=json.dumps({'title': 'ignored for test'}),
        structured_content=json.dumps({
            'title': 'Manchester United Loan Watch — Week Ending 21 Sep 2025',
            'summary': summary_text,
            'range': ['2025-09-15', '2025-09-21'],
        }),
        issue_date=date(2025, 9, 21),
        week_start_date=date(2025, 9, 15),
        week_end_date=date(2025, 9, 21),
        published=True,
        public_slug=_test_slug('manchester-united'),
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)

    admin_token = issue_user_token('admin@example.com', role='admin')['token']
    headers = {
        'Authorization': f'Bearer {admin_token}',
        'X-API-Key': 'test-admin-key',
    }

    response = client.get(f'/newsletters/{newsletter.id}/render.html', headers=headers)

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    expected_slug = newsletter.public_slug
    image_path = os.path.join(static_root, 'newsletters', expected_slug, 'cover.jpg')
    assert os.path.isfile(image_path), 'cover.jpg should be generated on render'

    assert '<meta property="og:type" content="article">' in html
    assert '<meta name="description" content="Goals, minutes, and form tracker for every United loanee this week.">' in html
    assert '<meta property="og:title" content="Manchester United Loan Watch — Week Ending 21 Sep 2025">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '<meta name="twitter:site" content="@theacademywatch">' in html

    og_url = f'content="https://theacademywatch.test/newsletters/{expected_slug}"'
    assert f'<meta property="og:url" {og_url}>' in html

    og_image = f'content="https://theacademywatch.test/static/newsletters/{expected_slug}/cover.jpg"'
    assert f'<meta property="og:image" {og_image}>' in html

def test_render_newsletter_includes_team_logo(app):
    with app.app_context():
        team = Team(team_id=555, name='Logo FC', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        content = {
            'title': 'Logo FC Weekly',
            'summary': 'Summary text',
            'team_logo': 'https://cdn.example.com/logo-fc.png',
            'sections': [
                {
                    'title': 'Highlights',
                    'items': [
                        {
                            'player_name': 'Player One',
                            'loan_team': 'Loan City',
                            'player_photo': 'https://cdn.example.com/player-one.jpg',
                        }
                    ]
                }
            ],
        }

        newsletter = Newsletter(
            team_id=team.id,
            title='Logo FC Weekly',
            content=json.dumps(content),
            structured_content=json.dumps(content),
            published=True,
            public_slug=_test_slug('logo-fc'),
        )
        db.session.add(newsletter)
        db.session.commit()
        newsletter_id = newsletter.id

    render_fn = getattr(render_newsletter, '__wrapped__', render_newsletter)

    with app.test_request_context(f'/newsletters/{newsletter_id}?fmt=email'):
        resp = render_fn(newsletter_id, 'email')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'https://cdn.example.com/logo-fc.png' in html


def test_get_newsletter_returns_rendered_and_comments(app, client):
    with app.app_context():
        team = Team(team_id=456, name='Detail FC', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        content = {
            'title': 'Detail FC Weekly',
            'summary': 'Summary text',
            'rendered': {'web_html': '<h1>Detail FC Weekly</h1>'},
        }
        newsletter = Newsletter(
            team_id=team.id,
            title='Detail FC Weekly',
            content=json.dumps(content),
            structured_content=json.dumps(content),
            published=True,
            public_slug=_test_slug('detail-fc'),
        )
        db.session.add(newsletter)
        db.session.commit()

        comment = NewsletterComment(
            newsletter_id=newsletter.id,
            author_email='fan@example.com',
            author_name='Supporter',
            body='Brilliant issue!',
        )
        db.session.add(comment)
        db.session.commit()

        newsletter_id = newsletter.id

    resp = client.get(f'/newsletters/{newsletter_id}')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['id'] == newsletter_id
    assert payload['rendered']['web_html'] == '<h1>Detail FC Weekly</h1>'
    assert isinstance(payload['comments'], list)
    assert payload['comments'][0]['body'] == 'Brilliant issue!'


def test_admin_preview_send_routes_to_admin_emails(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')
    monkeypatch.setenv('ADMIN_EMAILS', 'admin1@example.com, admin2@example.com ')

    team = Team(team_id=321, name='Admin FC', country='England', season=2024)
    db.session.add(team)
    db.session.commit()

    newsletter = Newsletter(
        team_id=team.id,
        title='Admin FC Preview',
        content=json.dumps({'title': 'Admin FC Preview'}),
        structured_content=json.dumps({'title': 'Admin FC Preview', 'summary': 'Summary'}),
        issue_date=date(2024, 9, 20),
        week_start_date=date(2024, 9, 13),
        week_end_date=date(2024, 9, 19),
        published=False,
        public_slug=_test_slug('admin-fc'),
    )
    db.session.add(newsletter)
    db.session.commit()

    captured = {}

    def fake_deliver(
        n,
        *,
        recipients=None,
        subject_override=None,
        webhook_url_override=None,
        http_method_override=None,
        dry_run=False,
    ):
        captured['newsletter_id'] = n.id
        captured['recipients'] = recipients
        captured['subject'] = subject_override
        captured['dry_run'] = dry_run
        return {'status': 'ok', 'recipient_count': len(recipients or [])}

    monkeypatch.setattr('src.routes.api._deliver_newsletter_via_webhook', fake_deliver)

    token = issue_user_token('admin1@example.com', role='admin')['token']
    headers = {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
    }

    resp = client.post(
        f'/newsletters/{newsletter.id}/send',
        json={'test_to': '__admins__', 'subject': 'Preview Subject', 'dry_run': True},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    assert body['recipient_count'] == 2
    assert body['admin_preview'] is True
    assert body['admin_recipients'] == ['admin1@example.com', 'admin2@example.com']
    assert captured['newsletter_id'] == newsletter.id
    assert captured['recipients'] == ['admin1@example.com', 'admin2@example.com']
    assert captured['subject'] == 'Preview Subject'
    assert captured['dry_run'] is True

    refreshed = Newsletter.query.get(newsletter.id)
    assert not refreshed.email_sent


def test_delete_newsletter_removes_record_and_comments(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=901, name='Delete FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    newsletter = Newsletter(
        team_id=team.id,
        title='Delete Me Weekly',
        content=json.dumps({'title': 'Delete Me Weekly'}),
        structured_content=json.dumps({'title': 'Delete Me Weekly', 'summary': 'Summary'}),
        issue_date=date(2025, 9, 19),
        week_start_date=date(2025, 9, 12),
        week_end_date=date(2025, 9, 18),
        published=True,
        public_slug=_test_slug('delete-fc'),
    )
    db.session.add(newsletter)
    db.session.commit()

    comment = NewsletterComment(
        newsletter_id=newsletter.id,
        author_email='deleter@example.com',
        body='Remove this please',
    )
    db.session.add(comment)
    db.session.commit()

    token = issue_user_token('admin@example.com', role='admin')['token']
    headers = {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
    }

    resp = client.delete(f'/newsletters/{newsletter.id}', headers=headers)

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'deleted'
    assert payload['newsletter_id'] == newsletter.id

    assert Newsletter.query.get(newsletter.id) is None
    assert NewsletterComment.query.filter_by(newsletter_id=newsletter.id).count() == 0


def _auth_headers(role_email='admin@example.com'):
    token = issue_user_token(role_email, role='admin')['token']
    return {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
    }


def _make_newsletter(team_id, *, issue_day=1, published=False, title_prefix='Bulk', idx=0):
    issue_dt = date(2025, 9, issue_day)
    week_end = issue_dt - timedelta(days=1)
    week_start = week_end - timedelta(days=6)
    newsletter = Newsletter(
        team_id=team_id,
        title=f'{title_prefix} Issue {idx + 1}',
        content=json.dumps({'title': f'{title_prefix} Issue {idx + 1}'}),
        structured_content=json.dumps({'title': f'{title_prefix} Issue {idx + 1}', 'summary': 'Summary'}),
        issue_date=issue_dt,
        week_start_date=week_start,
        week_end_date=week_end,
        published=published,
        public_slug=_test_slug(f"{title_prefix.lower()}-{idx}"),
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)
    return newsletter


def test_admin_bulk_publish_with_filter_params_and_exclusions(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=701, name='Bulk Publish FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    inside_1 = _make_newsletter(team.id, issue_day=1, idx=0, published=False)
    inside_2 = _make_newsletter(team.id, issue_day=8, idx=1, published=False)
    inside_excluded = _make_newsletter(team.id, issue_day=15, idx=2, published=False)
    inside_already = _make_newsletter(team.id, issue_day=22, idx=3, published=True)
    outside = _make_newsletter(team.id, issue_day=30, idx=4, published=False)
    outside.issue_date = date(2025, 10, 6)
    db.session.commit()

    payload = {
        'publish': True,
        'filter_params': {
            'issue_start': '2025-09-01',
            'issue_end': '2025-09-30',
        },
        'exclude_ids': [inside_excluded.id],
        'expected_total': 4,
    }

    resp = client.post('/admin/newsletters/bulk-publish', json=payload, headers=_auth_headers('bulk@example.com'))

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['publish'] is True
    assert body['updated'] == 2
    assert body.get('unchanged') == 1
    meta = body.get('meta') or {}
    assert meta.get('mode') == 'filters'
    assert meta.get('total_matched') == 4
    assert meta.get('total_selected') == 3
    assert meta.get('total_excluded') == 1
    assert inside_excluded.id in meta.get('excluded_ids', [])

    db.session.refresh(inside_1)
    db.session.refresh(inside_2)
    db.session.refresh(inside_excluded)
    db.session.refresh(inside_already)
    db.session.refresh(outside)

    assert inside_1.published is True
    assert inside_2.published is True
    assert inside_excluded.published is False
    assert inside_already.published is True
    assert outside.published is False


def test_admin_bulk_publish_filters_require_expected_total(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=702, name='Bulk Guard FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    _make_newsletter(team.id, issue_day=1, idx=0, published=False)
    _make_newsletter(team.id, issue_day=8, idx=1, published=False)

    resp = client.post(
        '/admin/newsletters/bulk-publish',
        json={
            'publish': True,
            'filter_params': {'issue_start': '2025-09-01', 'issue_end': '2025-09-30'},
        },
        headers=_auth_headers('guard@example.com'),
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert 'expected_total' in body.get('error', '') or body.get('field') == 'expected_total'


def test_admin_bulk_delete_with_filters_and_exclusions(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=703, name='Bulk Delete FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    keep_excluded = _make_newsletter(team.id, issue_day=1, idx=0, published=False)
    delete_one = _make_newsletter(team.id, issue_day=8, idx=1, published=False)
    delete_two = _make_newsletter(team.id, issue_day=15, idx=2, published=True)
    delete_three = _make_newsletter(team.id, issue_day=22, idx=3, published=False)
    outside = _make_newsletter(team.id, issue_day=30, idx=4, published=False)
    outside.issue_date = date(2025, 10, 6)
    db.session.commit()

    resp = client.delete(
        '/admin/newsletters/bulk',
        json={
            'filter_params': {
                'issue_start': '2025-09-01',
                'issue_end': '2025-09-30',
            },
            'exclude_ids': [keep_excluded.id],
            'expected_total': 4,
        },
        headers=_auth_headers('deleter@example.com'),
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['deleted'] == 3
    meta = body.get('meta') or {}
    assert meta.get('mode') == 'filters'
    assert meta.get('total_matched') == 4
    assert meta.get('total_selected') == 3
    assert meta.get('total_excluded') == 1
    assert keep_excluded.id in meta.get('excluded_ids', [])

    remaining_ids = {row.id for row in Newsletter.query.all()}
    assert remaining_ids == {keep_excluded.id, outside.id}


def test_generate_newsletter_force_refresh_regenerates(app, client, monkeypatch):
    team = Team(team_id=101, name='Refresh FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    counter = {'n': 0}

    def fake_compose(_team_id, target_date, force_refresh=False):
        counter['n'] += 1
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        payload = {'title': f'Weekly Update {counter["n"]}', 'summary': '', 'sections': []}
        return {
            'content_json': json.dumps(payload),
            'week_start': week_start,
            'week_end': week_end,
        }

    monkeypatch.setattr(weekly_nl_agent, '_render_variants', _stub_render_variants)
    monkeypatch.setattr(weekly_nl_agent, 'compose_team_weekly_newsletter', fake_compose)

    response = client.post(
        '/api/newsletters/generate',
        json={'team_id': team.id, 'target_date': '2025-01-08'},
    )
    assert response.status_code == 200
    assert Newsletter.query.count() == 1
    first = Newsletter.query.first()
    first_content = json.loads(first.structured_content or first.content)
    assert first_content['title'] == 'Weekly Update 1'

    response = client.post(
        '/api/newsletters/generate',
        json={'team_id': team.id, 'target_date': '2025-01-08', 'force_refresh': True},
    )
    assert response.status_code == 200
    assert Newsletter.query.count() == 1
    refreshed = Newsletter.query.first()
    refreshed_content = json.loads(refreshed.structured_content or refreshed.content)
    assert refreshed_content['title'] == 'Weekly Update 2'


def test_generate_newsletter_no_duplicates_for_same_week(app, client, monkeypatch):
    team = Team(team_id=202, name='No Duplicates FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    def fake_compose(_team_id, target_date, force_refresh=False):
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        payload = {'title': 'Weekly Update', 'summary': '', 'sections': []}
        return {
            'content_json': json.dumps(payload),
            'week_start': week_start,
            'week_end': week_end,
        }

    monkeypatch.setattr(weekly_nl_agent, '_render_variants', _stub_render_variants)
    monkeypatch.setattr(weekly_nl_agent, 'compose_team_weekly_newsletter', fake_compose)

    response = client.post(
        '/api/newsletters/generate',
        json={'team_id': team.id, 'target_date': '2025-09-15'},
    )
    assert response.status_code == 200
    response = client.post(
        '/api/newsletters/generate',
        json={'team_id': team.id, 'target_date': '2025-09-17'},
    )
    assert response.status_code == 200
    assert Newsletter.query.count() == 1


def test_admin_update_newsletter_title_syncs_to_json(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=303, name='Title Sync FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    original_payload = {'title': 'Original Title', 'summary': '', 'sections': []}
    newsletter = Newsletter(
        team_id=team.id,
        newsletter_type='weekly',
        title='Original Title',
        content=json.dumps(original_payload),
        structured_content=json.dumps(original_payload),
        issue_date=date(2025, 1, 8),
        week_start_date=date(2025, 1, 6),
        week_end_date=date(2025, 1, 12),
        public_slug=_test_slug('title-sync'),
    )
    db.session.add(newsletter)
    db.session.commit()

    response = client.put(
        f'/api/admin/newsletters/{newsletter.id}',
        headers=_auth_headers(),
        json={'title': 'New Title'},
    )
    assert response.status_code == 200

    updated = Newsletter.query.get(newsletter.id)
    assert updated.title == 'New Title'
    updated_content = json.loads(updated.structured_content or updated.content)
    assert updated_content['title'] == 'New Title'
