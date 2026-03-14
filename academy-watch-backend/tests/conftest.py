import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
    
from types import SimpleNamespace

import pytest
from flask import Flask
import sqlalchemy as sa

if 'bleach' not in sys.modules:
    def _clean(value, *args, **kwargs):
        return value

    def _linkify(value, *args, **kwargs):
        return value

    sys.modules['bleach'] = SimpleNamespace(clean=_clean, linkify=_linkify)


if 'flask_limiter' not in sys.modules:
    class _Limiter:
        def __init__(self, *args, **kwargs):
            pass

        def limit(self, *args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

        def init_app(self, app):
            return None

    sys.modules['flask_limiter'] = SimpleNamespace(Limiter=_Limiter)


if 'flask_limiter.util' not in sys.modules:
    def _get_remote_address(*args, **kwargs):
        return '127.0.0.1'

    sys.modules['flask_limiter.util'] = SimpleNamespace(get_remote_address=_get_remote_address)

# Ensure the API client runs in stub/offline mode for unit tests before importing blueprints
os.environ.setdefault('SKIP_API_HANDSHAKE', '1')
os.environ.setdefault('API_USE_STUB_DATA', 'true')
os.environ.setdefault('TEST_ONLY_MANU', 'false')

# Map PostgreSQL JSONB to generic JSON so SQLite can handle it in tests
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
compiles(JSONB, 'sqlite')(lambda element, compiler, **kw: 'JSON')

from src.models.league import db
from src.routes.api import api_bp
from src.routes.teams import teams_bp
from src.routes.loans import loans_bp
from src.routes.players import players_bp
from src.routes.subscriptions import subscriptions_bp
from src.extensions import limiter
import src.models.weekly  # Ensure weekly models are registered for db.create_all()


@pytest.fixture
def app():
    root_dir = Path(__file__).resolve().parent.parent
    template_dir = root_dir / 'src' / 'templates'
    static_dir = root_dir / 'src' / 'static'

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY='test-secret',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(teams_bp, url_prefix='/api')
    app.register_blueprint(loans_bp, url_prefix='/api')
    app.register_blueprint(players_bp, url_prefix='/api')
    app.register_blueprint(subscriptions_bp, url_prefix='/api')
    from src.routes.journalist import journalist_bp
    app.register_blueprint(journalist_bp, url_prefix='/api')
    from src.routes.cohort import cohort_bp
    app.register_blueprint(cohort_bp, url_prefix='/api')

    ctx = app.app_context()
    ctx.push()
    db.create_all()

    # Provide default public URLs for templates/tests unless overridden per-test
    os.environ.setdefault('PUBLIC_BASE_URL', 'https://example.com')

    yield app

    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sqlite_memory_engine():
    engine = sa.create_engine('sqlite:///:memory:')
    try:
        yield engine
    finally:
        engine.dispose()
