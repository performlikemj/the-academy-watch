"""V3 real-path probes compared with main e510612a's native log messages."""

import io
import logging
import smtplib
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from gunicorn.config import Config
from gunicorn.workers.base import Worker
from src.services.email_service import SMTPProvider
from src.utils.log_privacy import EmailLogFilter, _scan_text, email_exc_info, protect_log_handlers
from src.utils.privacy_gunicorn import PrivacyGunicornLogger

pytest_plugins = ["test_log_email_masking"]
EMAIL = "john@example.com"


def diagnostic(caplog, prefix, main):
    """Compare the actual diagnostic to main, allowing only token masking."""
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix))
    assert line == _scan_text(main)
    assert EMAIL not in line
    return line


def test_academy_fixture_failure_keeps_main_event_id_and_error(monkeypatch, caplog):
    from src.services import academy_sync_service as sync

    protect_log_handlers()
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("src.utils.data_mode.require_api_enabled", lambda: None)
    monkeypatch.setattr(sync, "db", SimpleNamespace(session=Mock()))
    service = sync.AcademySyncService(api_client=Mock(), rate_limiter=Mock())
    monkeypatch.setattr(service, "_ensure_current_season", lambda leagues: None)
    monkeypatch.setattr(service, "_fetch_fixtures", lambda **kw: [{"fixture": {"id": 424242}}])
    monkeypatch.setattr(service, "_get_tracked_player_ids", lambda: set())
    monkeypatch.setattr(service, "_process_fixture", Mock(side_effect=ValueError(f"bad fixture {EMAIL}")))
    league = SimpleNamespace(id=7, api_league_id=123, name="Premier League 2", season=2026, sync_enabled=True)
    result = service.sync_league(league, date_from=date(2026, 9, 28), date_to=date(2026, 10, 4))
    main = f"Error processing fixture 424242: bad fixture {EMAIL}"
    diagnostic(caplog, "Error processing fixture", main)
    assert result["errors"] == [main]
    assert "Syncing Premier League 2 (123) from 2026-09-28 to 2026-10-04" in caplog.text


@pytest.mark.parametrize("code", [535, 454])
def test_smtp_auth_failure_keeps_main_code_and_reason(monkeypatch, caplog, code):
    for key, value in {"SMTP_HOST": "localhost", "SMTP_USERNAME": "test", "SMTP_PASSWORD": "test"}.items():
        monkeypatch.setenv(key, value)
    error = smtplib.SMTPAuthenticationError(code, f"5.7.8 authentication rejected {EMAIL}".encode())
    server = Mock()
    server.login.side_effect = error
    monkeypatch.setattr("src.services.email_service.smtplib.SMTP", Mock(return_value=server))
    result = SMTPProvider().send(to=EMAIL, subject="test", html="test", text="test")
    main = f"SMTP authentication failed: {error}"
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("SMTP authentication failed:"))
    assert line.split(" to=", 1)[0] == _scan_text(main)
    assert f"({code}," in line and "5.7.8 authentication rejected" in line
    assert "jo…@example.com" in line and EMAIL not in line
    assert result.error == f"Authentication failed: {error}"


def test_api_football_429_keeps_main_status_endpoint_and_error(monkeypatch, caplog):
    from src import api_football_client as api
    from src.models.api_cache import APICache

    protect_log_handlers()
    monkeypatch.setattr(api, "api_football_frozen", lambda: False)
    monkeypatch.setattr(APICache, "get_cached", lambda *a, **k: None)
    client = api.APIFootballClient.__new__(api.APIFootballClient)
    client.mode, client.base_url, client.headers = "live", "https://v3.football.api-sports.io", {}
    monkeypatch.setattr(client, "_check_quota_limit", lambda: None)
    response = requests.Response()
    response.status_code = 429
    response.reason = "Too Many Requests"
    response.url = client.base_url + "/players?id=1"
    response._content = b"rateLimit"
    monkeypatch.setattr(api.requests, "get", Mock(return_value=response))
    with pytest.raises(RuntimeError, match="429 Client Error: Too Many Requests"):
        client._make_request("players", params={"id": 1})
    main = f"❌ API request failed: 429 Client Error: Too Many Requests for url: {response.url}"
    diagnostic(caplog, "❌ API request failed:", main)


def test_reddit_failure_keeps_main_subreddit_and_error(monkeypatch, caplog):
    # Legacy optional PRAW is not a backend dependency. Execute the actual
    # method AST, substituting only unavailable SDK exception types.
    import ast
    from pathlib import Path
    from types import MethodType

    tree = ast.parse(Path("src/services/reddit_service.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RedditService")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "post_to_subreddit")
    namespace = {
        "logger": logging.getLogger("src.services.reddit_service"),
        "PrawcoreException": type("PrawcoreException", (Exception,), {}),
        "RedditPostingError": RuntimeError,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), "src/services/reddit_service.py", "exec"), namespace)
    protect_log_handlers()
    service = SimpleNamespace()
    service.post_to_subreddit = MethodType(namespace["post_to_subreddit"], service)
    reddit = Mock()
    reddit.subreddit.return_value.submit.side_effect = RuntimeError(f"rate limit E42 {EMAIL}")
    service.authenticate = lambda: reddit
    monkeypatch.setattr("src.utils.data_mode.require_newsletters_enabled", lambda: None)
    with pytest.raises(RuntimeError):
        service.post_to_subreddit("TestAcademy", "title", "body")
    diagnostic(caplog, "Unexpected error posting", f"Unexpected error posting to r/TestAcademy: rate limit E42 {EMAIL}")


def test_teams_failure_keeps_main_error_and_traceback(app, monkeypatch, caplog):
    from src.routes import teams

    protect_log_handlers()
    monkeypatch.setattr(
        teams, "Team", SimpleNamespace(query=Mock(count=Mock(side_effect=RuntimeError(f"DB E43 {EMAIL}"))))
    )
    with app.test_request_context("/api/teams"):
        response, status = teams.get_teams()
    assert status == 500 and response.json["error"]
    diagnostic(caplog, "Error in get_teams:", f"Error in get_teams: DB E43 {EMAIL}")
    trace = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("Traceback:"))
    assert "Traceback (most recent call last):" in trace and "RuntimeError: DB E43 [masked]" in trace
    assert EMAIL not in trace


def test_database_exception_keeps_constraint_id_and_complete_chain(caplog):
    protect_log_handlers()
    try:
        try:
            raise ValueError(f"DB id=284324 {EMAIL}")
        except ValueError as cause:
            raise RuntimeError('violates unique constraint "uq_tracked_player_team" team_id=33') from cause
    except RuntimeError:
        logging.getLogger("db.diagnostic").exception("Transaction failed")
    assert "uq_tracked_player_team" in caplog.text and "team_id=33" in caplog.text
    assert "ValueError: DB id=284324 [masked]" in caplog.text
    assert "direct cause" in caplog.text and EMAIL not in caplog.text


def test_actual_gunicorn_worker_error_keeps_path_reason_access_and_startup(monkeypatch):
    import gunicorn.workers.base as base

    cfg = Config()
    cfg.set("errorlog", "-")
    cfg.set("accesslog", "-")
    cfg.set("access_log_format", "%(t)s %(h)s %(m)s %(U)s %(H)s %(s)s %(b)s %(L)s")
    logger = PrivacyGunicornLogger(cfg)
    error, access = io.StringIO(), io.StringIO()
    handlers = [logging.StreamHandler(error), logging.StreamHandler(access)]
    original = [logger.error_log.handlers[:], logger.access_log.handlers[:]]
    try:
        for target, handler in zip((logger.error_log, logger.access_log), handlers, strict=True):
            target.handlers = [handler]
            handler.addFilter(EmailLogFilter())
        worker = Worker.__new__(Worker)
        worker.cfg, worker.log = cfg, logger
        req = SimpleNamespace(
            method="GET",
            uri=f"/boom/john%40example.com?q={EMAIL}",
            path="/boom/john%40example.com",
            query=f"q={EMAIL}",
            version=(1, 1),
            headers=[],
            body=io.BytesIO(),
        )
        monkeypatch.setattr(base.util, "write_error", Mock())
        try:
            raise RuntimeError(f"native worker failure E44 {EMAIL}")
        except RuntimeError as exc:
            worker.handle_error(req, Mock(), ("203.0.113.9", 42), exc)
        logger.info("Listening at: %s (%s)", "http://0.0.0.0:5001", 28516)
        logger.info("Control socket listening at %s", "unix:/tmp/gunicorn.sock")
        assert "Error handling request GET /boom/[masked]" in error.getvalue()
        assert "RuntimeError: native worker failure E44 [masked]" in error.getvalue()
        assert "Listening at: http://0.0.0.0:5001 (28516)" in error.getvalue()
        assert "Control socket listening at unix:/tmp/gunicorn.sock" in error.getvalue()
        assert "GET /boom/[masked] HTTP/1.1 500" in access.getvalue()
        assert EMAIL not in error.getvalue() + access.getvalue()
        assert "q=" not in error.getvalue() + access.getvalue()
    finally:
        logger.error_log.handlers, logger.access_log.handlers = original


@pytest.mark.parametrize("value", [date(2026, 10, 3)])
def test_non_address_extra_native_formatting_is_unchanged(value):
    record = logging.LogRecord("diagnostic", logging.ERROR, __file__, 1, "E42", (), None)
    record.detail = value
    formatter = logging.Formatter("%(name)s %(levelname)s %(message)s %(detail)r")
    expected = formatter.format(record)
    assert EmailLogFilter().filter(record)
    assert formatter.format(record) == expected


def test_named_mapping_native_rendering_is_unchanged():
    record = logging.LogRecord(
        "diagnostic", logging.ERROR, __file__, 1, "%(state)s | %(code)r", ({"state": "ready", "code": 42},), None
    )
    expected = record.getMessage()
    assert EmailLogFilter().filter(record)
    assert record.getMessage() == expected


def test_cyclic_and_sparse_set_arguments_preserve_native_repr():
    cycle = []
    cycle.append(cycle)
    sparse = set(range(100))
    for value in range(99):
        sparse.remove(value)
    for value in [cycle, sparse]:
        record = logging.LogRecord("diagnostic", logging.ERROR, __file__, 1, "value=%r", (value,), None)
        expected = record.getMessage()
        assert EmailLogFilter().filter(record)
        assert record.getMessage() == expected


class NativeDetail:
    def __str__(self):
        return "E86 native detail"

    def __repr__(self):
        return "NativeDetail(code=86)"


def safe_extra_values():
    cycle = []
    cycle.append(cycle)
    mapping = {"code": 86}
    mapping["self"] = mapping
    return [ValueError("E86 invalid season"), SimpleNamespace(code=86), NativeDetail(), cycle, mapping]


@pytest.mark.parametrize("value", safe_extra_values())
@pytest.mark.parametrize("conversion", ["s", "r"])
def test_address_free_extra_preserves_native_object_and_formatter(value, conversion):
    record = logging.LogRecord("diagnostic", logging.ERROR, __file__, 1, "event E86", (), None)
    record.detail = value
    formatter = logging.Formatter("%(message)s detail=%(detail)" + conversion)
    expected = formatter.format(record)
    assert EmailLogFilter().filter(record)
    assert record.detail is value
    assert formatter.format(record) == expected


@pytest.mark.parametrize("leaking_render", ["str", "repr", "both"])
@pytest.mark.parametrize("conversion", ["s", "r"])
def test_address_bearing_extra_checks_both_native_representations(leaking_render, conversion):
    class Detail:
        def __str__(self):
            return "error E86 " + EMAIL if leaking_render in ("str", "both") else "error E86 safe"

        def __repr__(self):
            return "Detail E86 " + EMAIL if leaking_render in ("repr", "both") else "Detail E86 safe"

    record = logging.LogRecord("diagnostic", logging.ERROR, __file__, 1, "event E86", (), None)
    record.detail = {"nested": [Detail()]}
    assert EmailLogFilter().filter(record)
    output = logging.Formatter("%(message)s detail=%(detail)" + conversion).format(record)
    assert EMAIL not in output
    assert "[masked]" in output and "E86" in output


@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("address", ["safe", EMAIL])
@pytest.mark.parametrize("newlines", [0, 1, 2])
def test_full_exception_stream_matches_native_except_masked_token(snapshot, address, newlines):
    try:
        try:
            raise ValueError("cause E86 " + address)
        except ValueError as cause:
            raise RuntimeError("league=123 E83 " + address + "\n" * newlines) from cause
    except RuntimeError:
        native_info = sys.exc_info()
        info = email_exc_info((EMAIL,)) if snapshot else native_info
    native = logging.LogRecord(
        "academy", logging.ERROR, __file__, 1, "Error syncing league Premier League 2", (), native_info
    )
    record = logging.LogRecord("academy", logging.ERROR, __file__, 1, native.msg, (), info)
    expected, actual = io.StringIO(), io.StringIO()
    logging.StreamHandler(expected).handle(native)
    handler = logging.StreamHandler(actual)
    handler.addFilter(EmailLogFilter())
    handler.handle(record)
    assert actual.getvalue() == _scan_text(expected.getvalue())


def test_unsafe_cyclic_extra_masks_address_without_rewriting_safe_cycle():
    safe_cycle = []
    safe_cycle.append(safe_cycle)
    unsafe_cycle = [EMAIL]
    unsafe_cycle.append(unsafe_cycle)
    record = logging.LogRecord("diagnostic", logging.ERROR, __file__, 1, "event E86", (), None)
    record.detail = {"safe": safe_cycle, "unsafe": unsafe_cycle}
    assert EmailLogFilter().filter(record)
    assert record.detail["safe"] is safe_cycle
    assert EMAIL not in repr(record.detail) and "[masked]" in repr(record.detail)


def test_real_academy_outer_failure_full_record_matches_main(monkeypatch, caplog):
    from src.services import academy_sync_service as sync

    protect_log_handlers()
    monkeypatch.setattr("src.utils.data_mode.require_api_enabled", lambda: None)
    monkeypatch.setattr(sync, "db", SimpleNamespace(session=Mock()))
    service = sync.AcademySyncService(api_client=Mock(), rate_limiter=Mock())
    monkeypatch.setattr(service, "_ensure_current_season", lambda leagues: None)
    monkeypatch.setattr(service, "_fetch_fixtures", Mock(side_effect=RuntimeError(f"league=123 E83 {EMAIL}")))
    league = SimpleNamespace(id=7, api_league_id=123, name="Premier League 2", season=2026, sync_enabled=True)
    native_records = []
    original = sync.logger.exception

    def capture_native(message, *args, **kwargs):
        native_records.append(
            logging.LogRecord(sync.logger.name, logging.ERROR, __file__, 1, message, args, sys.exc_info())
        )
        original(message, *args, **kwargs)

    monkeypatch.setattr(sync.logger, "exception", capture_native)
    result = service.sync_league(league, date_from=date(2026, 9, 28), date_to=date(2026, 10, 4))
    native = native_records[0]
    record = next(r for r in caplog.records if r.getMessage().startswith("Error syncing league Premier League 2:"))
    formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
    assert formatter.format(record) == _scan_text(formatter.format(native))
    assert result["errors"] == [f"Error syncing league Premier League 2: league=123 E83 {EMAIL}"]
