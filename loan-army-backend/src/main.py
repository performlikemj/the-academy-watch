import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from flask import Flask, send_from_directory, jsonify
from src.models.league import db, League, Team, LoanedPlayer, Newsletter, UserSubscription
import src.models.weekly  # Ensure weekly models are registered with SQLAlchemy
import src.models.journey  # Ensure journey models are registered with SQLAlchemy
import src.models.cohort   # Ensure cohort models are registered with SQLAlchemy
import src.models.formation  # Ensure formation models are registered with SQLAlchemy
import src.models.api_cache  # Ensure API cache models are registered with SQLAlchemy
import src.models.tracked_player  # Ensure TrackedPlayer model is registered with SQLAlchemy
from src.routes.api import api_bp, require_api_key
from src.routes.auth_routes import auth_bp
from src.routes.journalist import journalist_bp
from src.routes.newsletter_deadline import newsletter_deadline_bp
from src.routes.community_takes import community_takes_bp
from src.routes.academy import academy_bp
from src.routes.journey import journey_bp
from src.routes.cohort import cohort_bp
from src.routes.gol import gol_bp
from src.routes.formation import formation_bp
from src.routes.teams import teams_bp
from src.routes.feeder import feeder_bp
import logging
from sqlalchemy.engine.url import make_url, URL
from flask_migrate import Migrate
import dotenv
from flask_cors import CORS
from flask_talisman import Talisman
from werkzeug.exceptions import HTTPException
from src.extensions import limiter
dotenv.load_dotenv(dotenv.find_dotenv())
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("🚀 Starting Flask application...")

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "")
allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

if allowed_origins:
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
else:
    # Safe default if not set; you can remove this to force explicit config
    CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

env_mode = os.getenv("FLASK_ENV") or "development"
is_prod = env_mode.lower() in ("prod", "production", "stage", "staging")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict' if is_prod else 'Lax',
    SESSION_COOKIE_SECURE=is_prod,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=is_prod,
    PREFERRED_URL_SCHEME='https' if is_prod else 'http',
    JSONIFY_PRETTYPRINT_REGULAR=False,
    PROPAGATE_EXCEPTIONS=False,
)

logger.info(f"📁 Static folder: {app.static_folder}")
logger.info(f"🔑 Secret key configured: {'Yes' if app.config['SECRET_KEY'] else 'No'}")

# Suppress repetitive MCP notification validation logs but keep the first one
_seen_mcp_validation = False
class _MCPValidationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        global _seen_mcp_validation
        msg = record.getMessage()
        if "Failed to validate notification" in msg:
            if _seen_mcp_validation:
                return False
            _seen_mcp_validation = True
        return True

root_logger = logging.getLogger()
root_logger.addFilter(_MCPValidationFilter())
for name in ("mcp", "agents.mcp", "mcp.shared.session", "mcp.client"):
    logging.getLogger(name).setLevel(logging.WARNING)

app.register_blueprint(journey_bp, url_prefix='/api')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(journalist_bp, url_prefix='/api')
app.register_blueprint(newsletter_deadline_bp, url_prefix='/api')
app.register_blueprint(community_takes_bp, url_prefix='/api')
app.register_blueprint(academy_bp, url_prefix='/api')
app.register_blueprint(cohort_bp, url_prefix='/api')
app.register_blueprint(gol_bp, url_prefix='/api')
app.register_blueprint(formation_bp, url_prefix='/api')
app.register_blueprint(teams_bp, url_prefix='/api')
app.register_blueprint(feeder_bp, url_prefix='/api')

csp = {
    'default-src': ["'self'"],
    'img-src': ["'self'", "data:", "https:"],
    'script-src': ["'self'"],
    'style-src': ["'self'", "'unsafe-inline'", "https:"],
    'font-src': ["'self'", "data:", "https:"],
    'connect-src': ["'self'", "https:"],
    'frame-ancestors': ["'none'"],
}

Talisman(
    app,
    content_security_policy=csp,
    force_https=is_prod,
    strict_transport_security=is_prod,
    session_cookie_secure=is_prod,
    session_cookie_http_only=True,
    referrer_policy='strict-origin-when-cross-origin',
)

limiter.init_app(app)

# Initialize email service for background job support
from src.services.email_service import email_service
email_service.init_app(app)


def _env_value(key: str, *, allow_inline_comment: bool = False) -> str | None:
    raw = os.getenv(key)
    if raw is None:
        return None
    value = raw.strip()
    if allow_inline_comment and "#" in value:
        for idx, ch in enumerate(value):
            if ch == "#" and (idx == 0 or value[idx - 1].isspace()):
                value = value[:idx].rstrip()
                break
    return value or None


def _build_db_uri_from_components() -> str:
    """Assemble a Postgres SQLAlchemy URI from DB_* environment variables."""
    port_raw = _env_value("DB_PORT", allow_inline_comment=True) or ""
    port_value = None
    if port_raw:
        try:
            port_value = int(port_raw)
        except ValueError:
            logger.warning("⚠️ DB_PORT value '%s' is invalid; ignoring port", port_raw)
    url = URL.create(
        drivername="postgresql+psycopg",
        username=_env_value("DB_USER"),
        password=_env_value("DB_PASSWORD"),
        host=_env_value("DB_HOST", allow_inline_comment=True),
        port=port_value,
        database=_env_value("DB_NAME", allow_inline_comment=True),
        query={"sslmode": _env_value("DB_SSLMODE") or "require"},
    )
    return url.render_as_string(hide_password=False)

# Database setup
if is_prod and os.getenv("SQLALCHEMY_DATABASE_URI"):
    raw_uri = os.getenv("SQLALCHEMY_DATABASE_URI", "")
    # Sanitize accidental quotes/whitespace
    candidate = raw_uri.strip().strip('"').strip("'")
    try:
        # Validate it parses; raises on bad format
        make_url(candidate)
        db_uri = candidate
        logger.info("🗄️ Using SQLALCHEMY_DATABASE_URI from environment (production)")
    except Exception:
        logger.warning("⚠️ SQLALCHEMY_DATABASE_URI is invalid; falling back to DB_* components")
        db_uri = _build_db_uri_from_components()
        logger.info("🗄️ Using PostgreSQL components from DB_* environment variables (dev/default)")
else:
    db_uri = _build_db_uri_from_components()
    logger.info("🗄️ Using PostgreSQL components from DB_* environment variables (dev/default)")

app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Connection pool settings for resilience against transaction aborts
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Test connections before use, discard stale/aborted ones
    'pool_recycle': 300,    # Recycle connections every 5 minutes
}
db.init_app(app)

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Ensure database session is properly cleaned up after each request.
    
    This prevents 'transaction is aborted' errors from propagating to subsequent
    requests when using PostgreSQL with connection pooling.
    """
    if exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    db.session.remove()

@app.errorhandler(HTTPException)
def handle_http_exception(exc: HTTPException):
    response = exc.get_response()
    payload = {
        'error': exc.description or exc.name,
        'code': exc.code,
    }
    response.data = json.dumps(payload)
    response.content_type = 'application/json'
    return response

# Debug endpoint - requires admin authentication
@app.route('/api/debug/database', methods=['GET'])
@require_api_key
def debug_database():
    """Debug endpoint to check database state. Requires admin authentication."""
    try:
        stats = {
            'tables': {
                'leagues': League.query.count(),
                'teams': Team.query.count(),
                'active_teams': Team.query.filter_by(is_active=True).count(),
                'loans': LoanedPlayer.query.count(),
                'active_loans': LoanedPlayer.query.filter_by(is_active=True).count(),
                'newsletters': Newsletter.query.count(),
                'subscriptions': UserSubscription.query.count()
            }
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Debug database check failed: {e}")
        return jsonify({'error': 'Database check failed'}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

migrate = Migrate(app, db)


# CLI Commands for maintenance tasks
@app.cli.command("backfill-tokens")
def backfill_unsubscribe_tokens():
    """Backfill unsubscribe_token for all subscriptions that don't have one."""
    import uuid
    subs_without_token = UserSubscription.query.filter(
        UserSubscription.unsubscribe_token.is_(None)
    ).all()
    
    count = 0
    for sub in subs_without_token:
        sub.unsubscribe_token = str(uuid.uuid4())
        count += 1
    
    db.session.commit()
    print(f"✅ Backfilled {count} subscription(s) with unsubscribe tokens")


if __name__ == "__main__":
    # Only run when you execute `python src/main.py`,
    # NOT when Flask CLI imports the app.
    with app.app_context():
        logger.info("🔨 Creating database tables...")

        # Optional stats
        total_leagues = League.query.count()
        total_teams   = Team.query.count()
        logger.info(f"📊 DB has {total_teams} teams, {total_leagues} leagues")

    debug_env = os.getenv("FLASK_DEBUG")
    if debug_env is None:
        debug_enabled = not is_prod
    else:
        debug_enabled = debug_env.lower() in {"1", "true", "yes", "on"}

    logger.info("Starting local Flask server (debug=%s)", debug_enabled)
    app.run(host="0.0.0.0", port=5001, debug=debug_enabled)
