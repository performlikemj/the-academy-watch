"""Tests for background job utilities extracted to src/utils/background_jobs.py."""

from datetime import datetime, timezone

import pytest
from flask import Flask

from src.models.league import db, BackgroundJob


@pytest.fixture
def job_app():
    """Create a minimal Flask app for testing background job utilities."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY='test-secret-key',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def job_client(job_app):
    return job_app.test_client()


class TestCreateBackgroundJob:
    """Tests for the _create_background_job function."""

    def test_create_background_job_returns_id(self, job_app):
        """Should return a UUID job ID."""
        from src.utils.background_jobs import create_background_job

        with job_app.app_context():
            job_id = create_background_job('test_job')
            assert job_id is not None
            assert len(job_id) == 36  # UUID format

    def test_create_background_job_stores_in_db(self, job_app):
        """Should create a BackgroundJob record in the database."""
        from src.utils.background_jobs import create_background_job

        with job_app.app_context():
            job_id = create_background_job('sync_fixtures')

            job = db.session.get(BackgroundJob, job_id)
            assert job is not None
            assert job.job_type == 'sync_fixtures'
            assert job.status == 'running'
            assert job.progress == 0
            assert job.total == 0

    def test_create_background_job_sets_started_at(self, job_app):
        """Should set started_at timestamp."""
        from src.utils.background_jobs import create_background_job

        with job_app.app_context():
            before = datetime.now(timezone.utc)
            job_id = create_background_job('test')
            after = datetime.now(timezone.utc)

            job = db.session.get(BackgroundJob, job_id)
            assert job.started_at is not None
            # The started_at should be between before and after


class TestUpdateJob:
    """Tests for the update_job function."""

    def test_update_job_progress(self, job_app):
        """Should update progress field."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, progress=50, total=100)

            job = db.session.get(BackgroundJob, job_id)
            assert job.progress == 50
            assert job.total == 100

    def test_update_job_status(self, job_app):
        """Should update status field."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, status='completed')

            job = db.session.get(BackgroundJob, job_id)
            assert job.status == 'completed'

    def test_update_job_current_player(self, job_app):
        """Should update current_player field."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, current_player='John Doe')

            job = db.session.get(BackgroundJob, job_id)
            assert job.current_player == 'John Doe'

    def test_update_job_error(self, job_app):
        """Should update error field."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, error='Something went wrong')

            job = db.session.get(BackgroundJob, job_id)
            assert job.error == 'Something went wrong'

    def test_update_job_results_json(self, job_app):
        """Should update results_json field."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, results={'processed': 10, 'errors': []})

            job = db.session.get(BackgroundJob, job_id)
            assert '"processed": 10' in job.results_json

    def test_update_job_completed_at_datetime(self, job_app):
        """Should update completed_at with datetime object."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            completed = datetime.now(timezone.utc)
            update_job(job_id, completed_at=completed)

            job = db.session.get(BackgroundJob, job_id)
            assert job.completed_at is not None

    def test_update_job_completed_at_iso_string(self, job_app):
        """Should parse ISO string for completed_at."""
        from src.utils.background_jobs import create_background_job, update_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, completed_at='2024-01-15T10:30:00Z')

            job = db.session.get(BackgroundJob, job_id)
            assert job.completed_at is not None
            assert job.completed_at.year == 2024

    def test_update_job_nonexistent_id_no_error(self, job_app):
        """Should not raise error for nonexistent job ID."""
        from src.utils.background_jobs import update_job

        with job_app.app_context():
            # Should not raise
            update_job('nonexistent-job-id', status='completed')


class TestGetJob:
    """Tests for the get_job function."""

    def test_get_job_returns_dict(self, job_app):
        """Should return job as dictionary."""
        from src.utils.background_jobs import create_background_job, get_job

        with job_app.app_context():
            job_id = create_background_job('test')
            result = get_job(job_id)

            assert result is not None
            assert isinstance(result, dict)
            assert result['id'] == job_id
            assert result['type'] == 'test'  # Model uses 'type' not 'job_type'
            assert result['status'] == 'running'

    def test_get_job_nonexistent_returns_none(self, job_app):
        """Should return None for nonexistent job ID."""
        from src.utils.background_jobs import get_job

        with job_app.app_context():
            result = get_job('nonexistent-id')
            assert result is None

    def test_get_job_includes_progress(self, job_app):
        """Should include progress in returned dict."""
        from src.utils.background_jobs import create_background_job, update_job, get_job

        with job_app.app_context():
            job_id = create_background_job('test')
            update_job(job_id, progress=75, total=100)

            result = get_job(job_id)
            assert result['progress'] == 75
            assert result['total'] == 100
