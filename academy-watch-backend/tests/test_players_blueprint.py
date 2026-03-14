"""Tests for players blueprint endpoints in src/routes/players.py."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
from flask import Flask

from src.models.league import db, Team, League, LoanedPlayer, Player, NewsletterCommentary, Newsletter, UserAccount
import src.models.weekly  # Ensure weekly models are registered for db.create_all()


@pytest.fixture
def players_app():
    """Create a minimal Flask app with players blueprint registered."""
    os.environ.setdefault('SKIP_API_HANDSHAKE', '1')
    os.environ.setdefault('API_USE_STUB_DATA', 'true')

    from src.routes.players import players_bp

    root_dir = os.path.dirname(os.path.dirname(__file__))
    template_dir = os.path.join(root_dir, 'src', 'templates')

    app = Flask(__name__, template_folder=template_dir)
    app.config.update(
        TESTING=True,
        SECRET_KEY='test-secret-key',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(app)
    app.register_blueprint(players_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def players_client(players_app):
    return players_app.test_client()


@pytest.fixture
def sample_league(players_app):
    """Create a sample league for testing."""
    with players_app.app_context():
        league = League(
            league_id=39,
            name='Premier League',
            country='England',
            season=2024,
            is_european_top_league=True,
        )
        db.session.add(league)
        db.session.commit()
        return league.id


@pytest.fixture
def sample_teams(players_app, sample_league):
    """Create sample teams for testing."""
    with players_app.app_context():
        parent = Team(
            team_id=33,
            name='Manchester United',
            country='England',
            season=2024,
            league_id=sample_league,
            is_active=True,
            logo='https://example.com/manu.png',
        )
        loan_team = Team(
            team_id=50,
            name='Loan FC',
            country='England',
            season=2024,
            league_id=sample_league,
            is_active=True,
            logo='https://example.com/loan.png',
        )
        db.session.add_all([parent, loan_team])
        db.session.commit()
        return {'parent_id': parent.id, 'loan_team_id': loan_team.id, 'parent_api_id': 33, 'loan_team_api_id': 50}


@pytest.fixture
def sample_player(players_app):
    """Create a sample player for testing."""
    with players_app.app_context():
        player = Player(
            player_id=12345,
            name='Test Player',
            photo_url='https://example.com/photo.jpg',
            position='M',
            nationality='England',
            age=22,
        )
        db.session.add(player)
        db.session.commit()
        return player.player_id


@pytest.fixture
def sample_loan(players_app, sample_teams, sample_player):
    """Create a sample loan for testing."""
    with players_app.app_context():
        loan = LoanedPlayer(
            player_id=sample_player,
            player_name='Test Player',
            primary_team_id=sample_teams['parent_id'],
            primary_team_name='Manchester United',
            loan_team_id=sample_teams['loan_team_id'],
            loan_team_name='Loan FC',
            window_key='2024-25::FULL',
            is_active=True,
            data_source='test',
            can_fetch_stats=False,  # Disable API verification in tests
        )
        db.session.add(loan)
        db.session.commit()
        return loan.id


class TestGetPlayerStats:
    """Tests for GET /players/<id>/stats endpoint."""

    def test_get_player_stats_returns_list(self, players_client, sample_loan, sample_player):
        """Should return list of stats."""
        res = players_client.get(f'/api/players/{sample_player}/stats')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)

    def test_get_player_stats_empty_for_unknown_player(self, players_client):
        """Should return empty list for unknown player."""
        res = players_client.get('/api/players/99999/stats')
        assert res.status_code == 200
        data = res.get_json()
        assert data == []


class TestGetPlayerProfile:
    """Tests for GET /players/<id>/profile endpoint."""

    def test_get_player_profile_returns_profile(self, players_client, sample_loan, sample_player):
        """Should return player profile."""
        res = players_client.get(f'/api/players/{sample_player}/profile')
        assert res.status_code == 200
        data = res.get_json()
        assert 'player_id' in data
        assert 'name' in data
        assert data['name'] == 'Test Player'

    def test_get_player_profile_includes_team_info(self, players_client, sample_loan, sample_player):
        """Should include loan and parent team info."""
        res = players_client.get(f'/api/players/{sample_player}/profile')
        assert res.status_code == 200
        data = res.get_json()
        assert data['loan_team_name'] == 'Loan FC'
        assert data['parent_team_name'] == 'Manchester United'

    def test_get_player_profile_fallback_name(self, players_client):
        """Should provide fallback name for unknown player."""
        res = players_client.get('/api/players/99999/profile')
        assert res.status_code == 200
        data = res.get_json()
        assert data['name'] == 'Player #99999'

    def test_get_player_profile_includes_loan_history(self, players_client, sample_loan, sample_player):
        """Should include loan history."""
        res = players_client.get(f'/api/players/{sample_player}/profile')
        assert res.status_code == 200
        data = res.get_json()
        assert 'loan_history' in data
        assert isinstance(data['loan_history'], list)


class TestGetPlayerSeasonStats:
    """Tests for GET /players/<id>/season-stats endpoint."""

    def test_get_season_stats_returns_structure(self, players_client, sample_loan, sample_player):
        """Should return stats structure."""
        res = players_client.get(f'/api/players/{sample_player}/season-stats')
        assert res.status_code == 200
        data = res.get_json()
        assert 'player_id' in data
        assert 'season' in data
        assert 'appearances' in data
        assert 'goals' in data
        assert 'assists' in data

    def test_get_season_stats_empty_for_no_loans(self, players_client):
        """Should return zero stats for player without loans."""
        res = players_client.get('/api/players/99999/season-stats')
        assert res.status_code == 200
        data = res.get_json()
        assert data['appearances'] == 0
        assert data['goals'] == 0

    def test_get_season_stats_includes_clubs(self, players_client, sample_loan, sample_player):
        """Should include clubs breakdown."""
        res = players_client.get(f'/api/players/{sample_player}/season-stats')
        assert res.status_code == 200
        data = res.get_json()
        assert 'clubs' in data
        assert isinstance(data['clubs'], list)


class TestGetPlayerCommentaries:
    """Tests for GET /players/<id>/commentaries endpoint."""

    def test_get_commentaries_returns_structure(self, players_client, sample_player):
        """Should return commentaries structure."""
        res = players_client.get(f'/api/players/{sample_player}/commentaries')
        assert res.status_code == 200
        data = res.get_json()
        assert 'player_id' in data
        assert 'commentaries' in data
        assert 'total_count' in data
        assert 'authors' in data
        assert isinstance(data['commentaries'], list)

    def test_get_commentaries_empty_for_no_content(self, players_client, sample_player):
        """Should return empty list when no commentaries exist."""
        res = players_client.get(f'/api/players/{sample_player}/commentaries')
        assert res.status_code == 200
        data = res.get_json()
        assert data['total_count'] == 0
        assert data['commentaries'] == []

    def test_get_commentaries_with_content(self, players_app, players_client, sample_player, sample_teams, sample_loan):
        """Should return commentaries when they exist."""
        with players_app.app_context():
            # Create author
            author = UserAccount(
                email='writer@example.com',
                display_name='Test Writer',
                display_name_lower='test writer',
                is_journalist=True,
            )
            db.session.add(author)
            db.session.commit()

            # Create newsletter
            newsletter = Newsletter(
                team_id=sample_teams['parent_id'],
                week_start_date=datetime(2024, 12, 1).date(),
                week_end_date=datetime(2024, 12, 7).date(),
                title='Test Newsletter',
                content='Sample newsletter content',
                public_slug='test-newsletter-2024-12',
            )
            db.session.add(newsletter)
            db.session.commit()

            # Create commentary
            commentary = NewsletterCommentary(
                newsletter_id=newsletter.id,
                player_id=sample_player,
                author_id=author.id,
                author_name='Test Writer',
                content='Great performance!',
                title='Player Review',
                commentary_type='general',
                is_active=True,
            )
            db.session.add(commentary)
            db.session.commit()

        res = players_client.get(f'/api/players/{sample_player}/commentaries')
        assert res.status_code == 200
        data = res.get_json()
        assert data['total_count'] == 1
        assert len(data['commentaries']) == 1
        assert data['commentaries'][0]['content'] == 'Great performance!'
        assert data['commentaries'][0]['author']['display_name'] == 'Test Writer'
