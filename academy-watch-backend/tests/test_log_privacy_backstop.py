"""Review repros: adversarial records and real route/provider/handler boundaries."""

import io
import json
import logging
import sys
import time
from collections import OrderedDict, defaultdict, namedtuple
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import quote, unquote

import pytest
import requests
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import EmailToken, Team, UserAccount, db
from src.services.email_service import EmailResult, EmailService
from src.utils.log_privacy import EmailLogFilter, get_logger, mask_email, protect_log_handlers

pytest_plugins = ["test_log_email_masking"]

EMAIL = "john.private@example.com"
VARIANTS = [
    '"john doe"@example.com',
    '"john"@example.com',
    "éloïse@example.com",
    "a…@example.com",
    "a@example.com",
    "ab@example.com",
    "john@exa\u0301mple.com",
    "john@[127.0.0.1]",
    "john(comment)@example.com",
    "john.private@gmailcom",
    "john.private@gmail",
    "john.private@mailhost",
    "john.private@gmail,com",
    "john.private @example.com",
    "patrick.o'neil@example.com",
    "first.last=tag@example.com",
    "john{dept}private@example.com",
]


def record(message, args=()):
    return logging.LogRecord("privacy.probe", logging.ERROR, __file__, 42, message, args, None)


@pytest.mark.parametrize("address", [a for a in VARIANTS if " @" not in a])
def test_untrusted_spellings_message_traceback_and_extra(address, caplog):
    logger = get_logger("privacy.variants")
    try:
        raise requests.RequestException(f"provider rejected {address}")
    except requests.RequestException:
        logger.exception("provider rejected %s", address, extra={"details": {"recipient": address}})
    assert address not in caplog.text
    assert address not in repr(caplog.records[-1].details)
    assert "[masked]" in caplog.text
    assert "RequestException" in caplog.text
    assert "line " in caplog.text


@pytest.mark.parametrize("address", VARIANTS)
@pytest.mark.parametrize("outcome", ["result_failure", "exception"])
def test_real_auth_failure_variants(auth_client, monkeypatch, caplog, address, outcome):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("src.routes.auth_routes._is_production", lambda: True)
    service = Mock()
    service.send_email.return_value = EmailResult(False, "mailgun", error=f"provider rejected {address}")
    if outcome == "exception":
        service.send_email.side_effect = requests.RequestException(f"provider rejected {address}")
    monkeypatch.setattr("src.routes.auth_routes.email_service", service)
    response = auth_client.post("/api/auth/request-code", json={"email": address})
    assert response.status_code == 200
    assert address not in caplog.text
    assert mask_email(address) in caplog.text
    assert service.send_email.call_args.kwargs["to"] == address


@pytest.mark.parametrize("address", VARIANTS)
def test_real_verify_new_user_variants(auth_client, caplog, address):
    caplog.set_level(logging.INFO)
    token = EmailToken(
        email=address, token="valid", purpose="login", expires_at=datetime.now(UTC) + timedelta(minutes=5)
    )
    db.session.add(token)
    db.session.commit()
    response = auth_client.post("/api/auth/verify-code", json={"email": address, "code": "valid"})
    assert response.status_code == 200
    assert address not in caplog.text
    assert mask_email(address) in caplog.text
    assert f"user_id={UserAccount.query.filter_by(email=address).one().id}" in caplog.text


@pytest.mark.parametrize("address", VARIANTS)
@pytest.mark.parametrize("transport", ["mailgun", "smtp"])
def test_real_mail_failure_variants(monkeypatch, caplog, address, transport):
    caplog.set_level(logging.INFO)
    if transport == "mailgun":
        monkeypatch.setenv("MAILGUN_API_KEY", "test")
        monkeypatch.setenv("MAILGUN_DOMAIN", "example.org")
        send = Mock(side_effect=requests.RequestException(f"provider rejected {address}"))
        monkeypatch.setattr("src.services.email_service.requests.post", send)
    else:
        monkeypatch.delenv("MAILGUN_API_KEY", raising=False)
        monkeypatch.setenv("SMTP_HOST", "localhost")
        monkeypatch.setenv("SMTP_USERNAME", "test")
        monkeypatch.setenv("SMTP_PASSWORD", "test")
        server = Mock()
        send = server.sendmail
        send.side_effect = RuntimeError(f"provider rejected {address}")
        monkeypatch.setattr("src.services.email_service.smtplib.SMTP", Mock(return_value=server))
    result = EmailService().send_email(
        to=address, subject="test", html="body", text="body", use_fallback=transport == "smtp"
    )
    assert not result.success
    assert address not in caplog.text
    assert mask_email(address) in caplog.text
    if transport == "mailgun":
        assert send.call_args.kwargs["data"]["to"] == [address]
    else:
        assert send.call_args.args[1] == [address]


@pytest.mark.parametrize("suffix", ["", "@", "@example.com", "@" * 1000])
def test_megabyte_record_has_fixed_small_cost(suffix):
    item = record("a" * 1_000_000 + suffix)
    start = time.perf_counter()
    assert EmailLogFilter().filter(item)
    assert time.perf_counter() - start < 0.5
    assert item.getMessage() == ("[masked]" if suffix not in {"", "@"} else "a" * 1_000_000 + suffix)
    assert item.levelno == logging.ERROR


@pytest.mark.parametrize("suffix", ["", "@"])
def test_candidate_scan_linear_control(suffix):
    # A same-size input which is scanned rather than omitted.
    item = record("a" * 20_000 + suffix)
    start = time.perf_counter()
    EmailLogFilter().filter(item)
    assert time.perf_counter() - start < 0.1


@pytest.mark.parametrize(
    "message,args", [("%s %s", ("one",)), ("%d", ("1",)), ("%1000000000s", ("x",)), ("%*s", (1000000000, "x"))]
)
def test_malformed_or_expansive_format_never_raises(message, args):
    item = record(message, args)
    assert EmailLogFilter().filter(item)
    assert "privacy formatting failed" in item.getMessage()
    assert item.levelno == logging.ERROR


def test_structured_containers_cycles_objects_and_bytes():
    class Broken:
        def __str__(self):
            raise RuntimeError(EMAIL)

        __repr__ = __str__

    cycle = []
    cycle.append(cycle)
    item = record(Broken())
    item.details = {
        "set": {EMAIL},
        "frozen": frozenset({EMAIL}),
        "ordered": OrderedDict([("email", EMAIL)]),
        "default": defaultdict(list, {"email": EMAIL}),
        "named": namedtuple("Recipient", "email count")(EMAIL, 1),
        "cycle": cycle,
        "broken": Broken(),
        "bytes": b"\xff\xfe\x00 no address",
        "address_bytes": EMAIL.encode(),
    }
    assert EmailLogFilter().filter(item)
    assert EMAIL not in repr(item.details)
    assert item.details["bytes"] == b"\xff\xfe\x00 no address"
    assert isinstance(item.details["ordered"], OrderedDict)
    assert isinstance(item.details["default"], defaultdict)
    assert item.details["default"].default_factory is list
    assert "cyclic" in repr(item.details["cycle"])
    assert "Broken" in item.getMessage()


def test_failed_scanner_keeps_error_record_fail_closed(monkeypatch):
    import src.utils.log_privacy as privacy

    item = record(f"error {EMAIL}")
    item.details = {"email": EMAIL}
    item.exc_info = (ValueError, ValueError(EMAIL), None)
    monkeypatch.setattr(privacy, "_scan_text", Mock(side_effect=RuntimeError("scanner failure")))
    assert privacy.EmailLogFilter().filter(item)
    rendered = logging.Formatter().format(item)
    assert EMAIL not in rendered and EMAIL not in repr(vars(item))
    assert "ValueError" in rendered
    assert item.levelno == logging.ERROR


@pytest.mark.parametrize(
    "text",
    [
        "https://cdn.example.com/img/logo.png failed",
        "GET https://api.x.com/users/me 404",
        "handle",
        "requests 2.31.0",
        "price 5 / 3.00",
        "@leading trailing@ @",
    ],
)
def test_non_address_diagnostics_unchanged(text):
    item = record(text)
    EmailLogFilter().filter(item)
    assert item.getMessage() == text


def test_mask_provenance_cannot_be_forged_by_string_spelling():
    item = record("%s %s %s", ("a…@example.com", "__privacy_mask_0__", mask_email(EMAIL)))
    EmailLogFilter().filter(item)
    assert "a…@example.com" not in item.getMessage()
    assert "jo…@example.com" in item.getMessage()
    assert "__privacy_mask_0__" in item.getMessage()
    assert item.getMessage().count("jo…@example.com") == 1


def test_root_private_and_late_handlers_emit_only_masked_text():
    streams = [io.StringIO(), io.StringIO()]
    root_handler = logging.StreamHandler(streams[0])
    private_handler = logging.StreamHandler(streams[1])
    logger = logging.getLogger("privacy.private")
    previous = logger.propagate
    logging.getLogger().addHandler(root_handler)
    logger.propagate = False
    logger.addHandler(private_handler)
    try:
        protect_log_handlers()
        late_stream = io.StringIO()
        late_handler = logging.StreamHandler(late_stream)
        logger.addHandler(late_handler)
        logger.error("provider %s", EMAIL)
        logging.getLogger().error("root %s", EMAIL)
        for stream in [*streams, late_stream]:
            assert EMAIL not in stream.getvalue()
            assert "[masked]" in stream.getvalue()
    finally:
        logger.propagate = previous
        logger.removeHandler(private_handler)
        logger.removeHandler(late_handler)
        logging.getLogger().removeHandler(root_handler)


def test_late_sqlalchemy_echo_emission(capsys):
    from sqlalchemy import create_engine, text

    protect_log_handlers()
    engine = create_engine("sqlite:///:memory:", echo=True)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("select :email"), {"email": EMAIL}).scalar() == EMAIL
        output = capsys.readouterr().out
        assert EMAIL not in output
        assert "[masked]" in output
    finally:
        engine.dispose()


def test_deployed_gunicorn_access_output_excludes_queries_and_headers(app, monkeypatch):
    from gunicorn.config import Config
    from src.routes.admin_control import admin_control_bp
    from src.utils.privacy_gunicorn import PrivacyGunicornLogger as Logger

    monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app.register_blueprint(admin_control_bp, url_prefix="/api")
    user = _ensure_user_account(EMAIL)
    db.session.commit()
    token = issue_user_token(user.email, role="admin")["token"]
    response = app.test_client().get(
        "/api/admin/people?q=" + quote(EMAIL),
        headers={"Authorization": "Bearer " + token, "X-API-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    docker = Path(__file__).resolve().parents[1] / "Dockerfile"
    command = json.loads(next(line[4:] for line in docker.read_text().splitlines() if line.startswith("CMD ")))
    cfg = Config()
    cfg.set("accesslog", "-")
    cfg.set("access_log_format", command[command.index("--access-logformat") + 1])
    logger = Logger(cfg)
    protect_log_handlers()
    stream = io.StringIO()
    handlers = logger.access_log.handlers[:]
    try:
        for handler in handlers:
            logger.access_log.removeHandler(handler)
        logger.access_log.addHandler(logging.StreamHandler(stream))
        environ = {
            "REMOTE_ADDR": "127.0.0.1",
            "REQUEST_METHOD": "GET",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "RAW_URI": "/api/admin/people?q=" + quote(EMAIL),
            "PATH_INFO": "/api/admin/people",
            "QUERY_STRING": "q=" + quote(EMAIL),
            "HTTP_REFERER": "https://example.org/" + EMAIL,
            "HTTP_USER_AGENT": EMAIL,
        }
        result = SimpleNamespace(status="200 OK", response_length=1, headers=[])
        logger.access(result, SimpleNamespace(headers=[]), environ, timedelta(milliseconds=10))
        # Malicious/legitimate path segments are still filtered, including %40.
        environ["PATH_INFO"] = "/people/" + quote(EMAIL)
        logger.access(result, SimpleNamespace(headers=[]), environ, timedelta(milliseconds=10))
        output = stream.getvalue()
        assert EMAIL not in unquote(output)
        assert "q=" not in output
        assert "GET /api/admin/people HTTP/1.1 200" in output
        assert "[masked]" in output
    finally:
        for handler in logger.access_log.handlers[:]:
            logger.access_log.removeHandler(handler)
        for handler in handlers:
            logger.access_log.addHandler(handler)


@pytest.mark.parametrize("module_name", ["bridge_match_to_club", "seed_sim_club_fixture"])
def test_real_cli_missing_manager_stderr(app, monkeypatch, capsys, module_name):
    from importlib import import_module

    module = import_module("scripts.dev." + module_name)
    monkeypatch.setattr(module, "guard_runtime_environment", lambda: None)
    monkeypatch.setattr("scripts.dev.bridge_match_to_club.guard_runtime_environment", lambda: None)
    monkeypatch.setattr("scripts.dev.bridge_match_to_club.guard_database_target", lambda *args, **kwargs: None)
    # Only app/env/target boundaries are substituted; main/lookup/rollback/print run.
    monkeypatch.setitem(sys.modules, "src.main", SimpleNamespace(app=app))
    argv = ["--manager-email", EMAIL]
    if module_name == "bridge_match_to_club":
        argv += ["--match-id", "1"]
    assert module.main(argv) == 2
    output = capsys.readouterr().err
    assert EMAIL not in output
    assert mask_email(EMAIL) in output
    assert "was not found" in output


def test_admin_mask_collision_retains_actor_and_no_bearer_sample(app, monkeypatch, caplog):
    from src.routes.admin_control import admin_control_bp

    app.register_blueprint(admin_control_bp, url_prefix="/api")
    monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    caplog.set_level(logging.INFO)
    for address in ("john.first@example.com", "john.second@example.com"):
        user = _ensure_user_account(address)
        db.session.commit()
        token = issue_user_token(address, role="admin")["token"]
        caplog.clear()
        response = app.test_client().get(
            "/api/admin/people", headers={"Authorization": "Bearer " + token, "X-API-Key": "test-admin-key"}
        )
        assert response.status_code == 200
        message = next(r.getMessage() for r in caplog.records if "Admin dual auth granted" in r.getMessage())
        assert f"user_id={user.id}" in message
        assert mask_email(address) in message
        assert address not in caplog.text
        caplog.clear()
        assert (
            app.test_client().get("/api/admin/people", headers={"Authorization": "Bearer " + token}).status_code == 401
        )
        assert "auth_present=True" in caplog.text
        assert token[:32] not in caplog.text


def test_real_curator_string_team_id_stays_success(app, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    from src.models.league import CommunityTake
    from src.routes.curator import curator_bp

    app.config["CURATOR_API_KEY"] = "test-curator"
    monkeypatch.setattr("src.utils.data_mode.require_newsletters_enabled", lambda: None)
    app.register_blueprint(curator_bp, url_prefix="/api")
    user = _ensure_user_account(EMAIL)
    user.is_curator = True
    db.session.add(Team(id=1, team_id=1, name="Test", country="England", season=2026))
    db.session.commit()
    monkeypatch.setattr("src.routes.curator._curator_can_access_team", lambda team_id: True)
    token = issue_user_token(EMAIL)["token"]
    response = app.test_client().post(
        "/api/curator/tweets",
        json={"team_id": "1", "content": "Test supplied content", "source_author": "@test"},
        headers={"Authorization": "Bearer " + token, "X-Curator-Key": "test-curator"},
    )
    assert response.status_code == 201
    assert CommunityTake.query.count() == 1
    assert EMAIL not in caplog.text
    assert "privacy formatting failed" not in caplog.text


def test_quoted_local_containing_at_and_format_failure_template():
    item = record('provider rejected "j@hn doe"@example.com')
    EmailLogFilter().filter(item)
    assert '"j@hn doe"@example.com' not in item.getMessage()
    item = record(f"{EMAIL} %d", ("invalid",))
    EmailLogFilter().filter(item)
    assert EMAIL not in item.getMessage()
    assert "formatting failed" in item.getMessage()


def test_mapping_format_width_limit():
    item = record("%(recipient)1000000000s", ({"recipient": EMAIL},))
    start = time.perf_counter()
    EmailLogFilter().filter(item)
    assert time.perf_counter() - start < 0.5
    assert EMAIL not in item.getMessage()
    assert "privacy formatting failed" in item.getMessage()


@pytest.mark.parametrize("size", [2000, 8000])
def test_real_auth_forwarded_header_latency(auth_client, monkeypatch, caplog, size):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("src.routes.auth_routes._is_production", lambda: True)
    service = Mock()
    service.send_email.return_value = EmailResult(True, "test")
    monkeypatch.setattr("src.routes.auth_routes.email_service", service)
    start = time.perf_counter()
    response = auth_client.post(
        "/api/auth/request-code", json={"email": EMAIL}, headers={"X-Forwarded-For": "a" * size + "@"}
    )
    assert time.perf_counter() - start < 0.5
    assert response.status_code == 200
    assert EMAIL not in caplog.text
    assert mask_email(EMAIL) in caplog.text


def test_real_public_teams_long_search_latency(app):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(handler)
    try:
        protect_log_handlers()
        start = time.perf_counter()
        response = app.test_client().get("/api/teams?search=" + "a" * 8000 + "@")
        assert response.status_code == 200
        assert time.perf_counter() - start < 0.5
    finally:
        logging.getLogger().removeHandler(handler)


def test_actual_app_startup_and_forced_logging_configuration():
    import os
    import subprocess

    script = """
import io
import logging
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
stream = io.StringIO()
handler = logging.StreamHandler(stream)
logging.getLogger().addHandler(handler)
import src.main
from src.utils.log_privacy import EmailLogFilter, mask_email
assert all(any(isinstance(f, EmailLogFilter) for f in h.filters) for h in logging.getLogger().handlers)
logging.getLogger().error("startup %s", "john.private@example.com")
assert "john.private@example.com" not in stream.getvalue()
assert "[masked]" in stream.getvalue()
stream = io.StringIO()
logging.basicConfig(force=True, handlers=[logging.StreamHandler(stream)])
logging.getLogger().error("late %s", "john.private@example.com")
assert "john.private@example.com" not in stream.getvalue()
assert "[masked]" in stream.getvalue()
"""
    env = {
        **os.environ,
        "FLASK_ENV": "production",
        "SECRET_KEY": "privacy-startup-test",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SKIP_API_HANDSHAKE": "1",
        "API_USE_STUB_DATA": "true",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "text",
    [
        "john@example.comjohn@example.com",
        "john@localhostjohn@example.com",
        "@john@example.com",
    ],
)
def test_embedded_adjacent_addresses_cannot_survive_in_a_domain(text):
    item = record(text)
    EmailLogFilter().filter(item)
    assert "john@example.com" not in item.getMessage()


def test_error_metadata_retained_without_raw_exception_objects(caplog):
    logger = get_logger("privacy.error_metadata")
    try:
        raise RuntimeError(f"provider {EMAIL}")
    except RuntimeError as error:
        logger.exception("operation failed")
        item = caplog.records[-1]
        assert item.exc_info[0] is RuntimeError
        assert item.exc_info[1] is not error
        assert item.exc_info[2] is None
        assert EMAIL not in str(item.exc_info[1])
        assert "line " in item.exc_text
        # Even a formatter which ignores cached exception text remains safe.
        item.exc_text = None
        assert EMAIL not in logging.Formatter().format(item)


def test_unicode_punycode_domain_address():
    address = "éloïse@example.xn--p1ai"
    item = record(address)
    EmailLogFilter().filter(item)
    assert address not in item.getMessage()
    assert "[masked]" in item.getMessage()


def test_real_claim_mail_failure_preserves_response_warning_and_writer_id(app, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    editor = _ensure_user_account("editor@example.net")
    editor.is_editor = True
    writer = _ensure_user_account(EMAIL)
    writer.managed_by_user_id = editor.id
    writer.claimed_at = None
    db.session.commit()
    token = issue_user_token(editor.email)["token"]
    send = Mock(side_effect=RuntimeError(f'provider rejected "{EMAIL}"'))
    monkeypatch.setattr("src.services.email_service.email_service.send_claim_invitation", send)
    response = app.test_client().post(
        f"/api/editor/writers/{writer.id}/send-claim-invite",
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == 200
    assert response.json["email"] == EMAIL
    assert response.json["warning"] == "Email delivery failed - share the link manually"
    assert send.call_args.kwargs["to_email"] == EMAIL
    assert EMAIL not in caplog.text
    assert mask_email(EMAIL) in caplog.text
    item = next(r for r in caplog.records if "Failed to send claim email" in r.getMessage())
    assert item.levelno == logging.WARNING
    assert f"writer_id={writer.id}" in item.getMessage()
    assert "RuntimeError" in item.exc_text
