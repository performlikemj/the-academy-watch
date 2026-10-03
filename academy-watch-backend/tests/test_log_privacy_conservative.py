"""LOGPIIF2 reviewer controls: source isolation and preservation, no grammar."""

import io
import json
import logging
import random
import re
import smtplib
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import IntEnum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
import requests
from gunicorn.config import Config
from src.models.league import EmailToken
from src.services.email_service import EmailService
from src.services.wikipedia_classifier import classify_loan_row
from src.utils.log_privacy import EmailLogFilter, _scan_text, log_metadata, mask_email, protect_log_handlers
from src.utils.privacy_gunicorn import PrivacyGunicornLogger

pytest_plugins = ["test_log_email_masking"]
ADDRESSES = [
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
    '"john doe"@example.com',
    "éloïse@example.com",
    "a@example.com",
    "ab@example.com",
]


def record(msg, args=()):
    return logging.LogRecord("diagnostic.logger", logging.ERROR, __file__, 91, msg, args, None)


@pytest.mark.parametrize(
    "msg", [b"actual provider error E42", {"error": "actual provider error E42"}, 42, [42, "E42"], None]
)
def test_non_string_messages_render_exactly_like_stdlib(msg):
    item = record(msg)
    expected = item.getMessage()
    item.exc_info = (None, None, None)
    assert EmailLogFilter().filter(item)
    assert item.getMessage() == expected
    assert item.name == "diagnostic.logger"
    assert item.levelname == "ERROR"
    assert logging.Formatter("%(name)s %(levelname)s %(message)s").format(item) == f"diagnostic.logger ERROR {expected}"


@pytest.mark.parametrize("value", [datetime(2026, 10, 3, tzinfo=UTC), Decimal("12.34"), UUID(int=42), Path("/tmp/E42")])
def test_scalar_formatting_preserves_non_address_text(value):
    item = record("diagnostic=%s", (value,))
    expected = item.getMessage()
    assert EmailLogFilter().filter(item)
    assert item.getMessage() == expected


def test_native_numeric_subclasses_and_star_width():
    class Number(IntEnum):
        X = 42

    for msg, args in [("n=%d", (Number.X,)), ("took %.2f s", (Decimal("12.34"),)), ("%*s", (6, "E42"))]:
        item = record(msg, args)
        expected = item.getMessage()
        assert EmailLogFilter().filter(item)
        assert item.getMessage() == expected


def test_extra_keys_values_and_collisions_all_survive():
    item = record("provider failed E42")
    for i in range(1000):
        setattr(item, f"john{i}@example.com", f"diagnostic E{i}")
    item.details = {"john@exa\u0301mple.com": "E1001", "john@[127.0.0.1]": "E1002"}
    assert EmailLogFilter().filter(item)
    rendered = json.dumps(vars(item), default=str)
    assert "@" not in rendered
    for i in range(1000):
        assert f"diagnostic E{i}" in rendered
    assert "E1001" in rendered and "E1002" in rendered
    assert item.getMessage() == "provider failed E42"
    assert item.name == "diagnostic.logger" and item.levelname == "ERROR"


def test_random_unicode_tokens_property_and_unchanged_whitespace():
    rng = random.Random(1140)
    alphabet = "abcABC019'\"{}[]=()/:_%\u0301\u200d\u2060é中😀"
    for _ in range(1000):
        left = "".join(rng.choices(alphabet, k=rng.randrange(1, 80)))
        right = "".join(rng.choices(alphabet, k=rng.randrange(1, 80)))
        token = left + "@" + right
        prefix, suffix = rng.choice([" ", "\t", "\u2003", "\r\n"]), rng.choice([" ", "\n", "\t"])
        original = "E42" + prefix + token + suffix + "status=550"
        item = record(original)
        assert EmailLogFilter().filter(item)
        assert item.getMessage() == "E42" + prefix + "[masked]" + suffix + "status=550"
        assert token not in item.getMessage()
        harmless = original.replace("@", "-")
        assert _scan_text(harmless) == harmless


@pytest.mark.parametrize("suffix", ["", "@", "@example.com", "@" * 1000])
def test_ten_megabyte_record_is_linear_and_never_truncated(suffix):
    message = "x" * 10_000_000 + suffix
    item = record(message)
    start = time.perf_counter()
    assert EmailLogFilter().filter(item)
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0
    assert item.getMessage() == (message if suffix in {"", "@"} else "[masked]")
    assert item.name == "diagnostic.logger" and item.levelname == "ERROR"


def test_full_large_diagnostic_arguments_and_deep_traceback_preserved():
    message = "E42 " + "x" * 100_000
    item = record("%s %s %s", (message, message, message))
    expected = item.getMessage()
    assert EmailLogFilter().filter(item)
    assert item.getMessage() == expected
    item = record("actual error E42")

    def nested(depth):
        if depth:
            return nested(depth - 1)
        raise ValueError("actual innermost E43 " + message)

    try:
        nested(60)
    except ValueError as exc:
        item.exc_info = (type(exc), exc, exc.__traceback__)
    assert EmailLogFilter().filter(item)
    assert "actual innermost E43" in item.exc_text
    assert message in item.exc_text
    assert 'raise ValueError("actual innermost E43' in item.exc_text
    assert "privacy limit" not in item.exc_text


@pytest.mark.parametrize("address", ADDRESSES)
@pytest.mark.parametrize("transport", ["mailgun", "smtp"])
def test_real_auth_mail_provider_errors_never_enter_logs(auth_client, monkeypatch, caplog, address, transport):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("src.routes.auth_routes._is_production", lambda: True)
    if transport == "mailgun":
        monkeypatch.setenv("MAILGUN_API_KEY", "test")
        monkeypatch.setenv("MAILGUN_DOMAIN", "example.org")
        send = Mock(side_effect=requests.ConnectionError(f"provider rejected {address}; diagnostic E42"))
        monkeypatch.setattr("src.services.email_service.requests.post", send)
        monkeypatch.delenv("SMTP_HOST", raising=False)
    else:
        monkeypatch.delenv("MAILGUN_API_KEY", raising=False)
        monkeypatch.setenv("SMTP_HOST", "localhost")
        monkeypatch.setenv("SMTP_USERNAME", "test")
        monkeypatch.setenv("SMTP_PASSWORD", "test")
        server = Mock()
        send = server.sendmail
        send.side_effect = smtplib.SMTPRecipientsRefused(
            {address: (550, f"5.1.1 <{address}>: diagnostic E42".encode())}
        )
        monkeypatch.setattr("src.services.email_service.smtplib.SMTP", Mock(return_value=server))
    monkeypatch.setattr("src.routes.auth_routes.email_service", EmailService())
    response = auth_client.post("/api/auth/request-code", json={"email": address})
    assert response.status_code == 200
    assert response.json == {"message": "Login code sent"}
    assert address not in caplog.text
    assert "diagnostic E42" not in caplog.text
    assert mask_email(address) in caplog.text
    assert EmailToken.query.filter_by(email=address).one().email == address
    if transport == "mailgun":
        assert send.call_args.kwargs["data"]["to"] == [address]
        assert "ConnectionError" in caplog.text
    else:
        assert send.call_args.args[1] == [address]
        assert "SMTPRecipientsRefused" in caplog.text


def test_classifier_keeps_result_but_never_prints_provider_body(monkeypatch, capsys, caplog):
    address = "john.private@example.com"
    data = {
        "valid": False,
        "player_name": "",
        "parent_club": "",
        "loan_club": "",
        "season_start_year": 2026,
        "reason": "unrelated contact " + address,
        "confidence": 0.1,
    }
    groq = Mock()
    groq.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))]
    )
    monkeypatch.setattr("src.services.wikipedia_classifier._get_groq_client", lambda: groq)
    assert classify_loan_row("unrelated contact " + address, season_year=2026) == data
    output = capsys.readouterr()
    assert address not in output.out + output.err + caplog.text


@pytest.mark.parametrize("address", ADDRESSES)
def test_deployed_access_keeps_every_line_under_large_headers(address):
    docker = Path(__file__).resolve().parents[1] / "Dockerfile"
    cmd = json.loads(next(x[4:] for x in docker.read_text().splitlines() if x.startswith("CMD ")))
    assert cmd[cmd.index("--logger-class") + 1] == "src.utils.privacy_gunicorn.PrivacyGunicornLogger"
    cfg = Config()
    cfg.set("accesslog", "-")
    cfg.set("access_log_format", cmd[cmd.index("--access-logformat") + 1])
    gunicorn = PrivacyGunicornLogger(cfg)
    protect_log_handlers()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    old = gunicorn.access_log.handlers[:]
    try:
        for h in old:
            gunicorn.access_log.removeHandler(h)
        gunicorn.access_log.addHandler(handler)
        environ = {
            "REMOTE_ADDR": "203.0.113.9",
            "REQUEST_METHOD": "POST",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "PATH_INFO": "/api/auth/verify-code",
            "RAW_URI": "/api/auth/verify-code?q=" + address,
            "QUERY_STRING": "q=" + address,
            "HTTP_REFERER": "x" * 8000 + address,
            "HTTP_USER_AGENT": "x" * 8000,
        }
        for i in range(6):
            environ[f"HTTP_X_PADDING_{i}"] = "x" * 8000
        resp = SimpleNamespace(status="401 Unauthorized", sent=57, response_length=57, headers=[])
        req = SimpleNamespace(headers=[])
        for path in [
            "/api/auth/verify-code",
            "/people/" + address,
            "/people/john%25252540example.com",
            "/api/" + "x" * 4000,
        ]:
            environ["PATH_INFO"] = path
            gunicorn.access(resp, req, environ, timedelta(milliseconds=12))
        lines = stream.getvalue().splitlines()
        assert len(lines) == 4
        assert "203.0.113.9 POST /api/auth/verify-code HTTP/1.1 401 57 0.012000" in lines[0]
        assert re.match(r"\[\d{2}/\w+/\d{4}:", lines[0])
        assert all("HTTP/1.1 401 57 0.012000" in line for line in lines)
        assert "q=" not in stream.getvalue() and address not in stream.getvalue()
        assert "/people/[masked]" in lines[2]
        assert "privacy limit" not in stream.getvalue()
    finally:
        gunicorn.access_log.removeHandler(handler)
        for h in old:
            gunicorn.access_log.addHandler(h)


def test_source_metadata_never_accepts_untrusted_mask_spelling():
    for text in [
        "a…@example.com",
        "john@exa\u0301mple.com",
        "provider error E42 john@example.com",
        "__privacy_mask_0__@example.com",
    ]:
        assert log_metadata(text) == "[text omitted]"
    assert log_metadata(mask_email("john@example.com")) == "jo…@example.com"


def test_counter_json_stdout_keeps_its_machine_readable_shape():
    summary = {"sent": 42, "failed": 0, "retry": 0, "errors": 0, "dry_run": True, "next_cursor": None}
    assert json.dumps(log_metadata(summary), sort_keys=True) == json.dumps(summary, sort_keys=True)


def test_backstop_emits_every_odd_record_with_its_level_and_name():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(EmailLogFilter())
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    values = [None, 42, b"E42", {"diagnostic": "E42"}, ["E42"], "E42 john@[127.0.0.1]"]
    for value in values:
        handler.handle(record(value))
    lines = stream.getvalue().splitlines()
    assert len(lines) == len(values)
    assert all(line.startswith("diagnostic.logger ERROR ") for line in lines)
    assert "john@[127.0.0.1]" not in stream.getvalue()


def test_backend_output_calls_use_fixed_templates_and_controlled_metadata():
    import ast

    root = Path(__file__).resolve().parents[1]
    helpers = {"mask_email", "log_metadata", "safe_exc_info", "bool", "len", "int", "float"}

    def safe(node):
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.JoinedStr):
            return all(not isinstance(n, ast.FormattedValue) or safe(n.value) for n in node.values)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in helpers:
                return True
            if ast.unparse(node.func) == "json.dumps" and node.args:
                return safe(node.args[0])
        if isinstance(node, (ast.ListComp, ast.SetComp)):
            return safe(node.elt)
        if isinstance(node, (ast.List, ast.Tuple)):
            return all(safe(n) for n in node.elts)
        if isinstance(node, ast.Dict):
            return all(k is not None and safe(k) and safe(v) for k, v in zip(node.keys, node.values, strict=True))
        return False

    failures = []
    for path in [*root.glob("*.py"), *(root / "src").rglob("*.py"), *(root / "scripts").rglob("*.py")]:
        tree = ast.parse(path.read_text())
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            is_log = (
                isinstance(fn, ast.Attribute)
                and fn.attr in {"debug", "info", "warn", "warning", "error", "exception", "critical", "fatal", "log"}
                and any(n in ast.unparse(fn.value).lower() for n in ("logger", "logging", "log"))
            )
            is_output = ast.unparse(fn) in {
                "print",
                "sys.stdout.write",
                "sys.stderr.write",
                "traceback.print_exc",
                "traceback.print_exception",
            }
            if not (is_log or is_output):
                continue
            for arg in call.args:
                # Verified local constructions, not generic spelling allowlists.
                if (
                    path.relative_to(root).as_posix() == "src/routes/auth_routes.py"
                    and isinstance(arg, ast.Name)
                    and arg.id == "msg"
                ):
                    bindings = [
                        n.value
                        for n in ast.walk(tree)
                        if isinstance(n, ast.Assign)
                        and any(isinstance(a, ast.Name) and a.id == "msg" for a in n.targets)
                    ]
                    assert len(bindings) == 1 and safe(bindings[0])
                    continue
                if (
                    path.relative_to(root).as_posix() == "src/services/email_service.py"
                    and isinstance(arg, ast.Name)
                    and arg.id == "masked_recipients"
                ):
                    bindings = [
                        n.value
                        for n in ast.walk(tree)
                        if isinstance(n, ast.Assign)
                        and any(isinstance(a, ast.Name) and a.id == "masked_recipients" for a in n.targets)
                    ]
                    assert bindings and all(safe(n) for n in bindings)
                    continue
                if not safe(arg):
                    failures.append(f"{path.relative_to(root)}:{call.lineno}: {ast.unparse(arg)}")
            if is_log:
                for kw in call.keywords:
                    if kw.arg in {"extra", "exc_info"} and not safe(kw.value):
                        failures.append(f"{path.relative_to(root)}:{call.lineno}: {kw.arg}={ast.unparse(kw.value)}")
    assert not failures, "Uncontrolled log/output inputs:\n" + "\n".join(failures)


def test_native_container_arguments_keep_non_address_repr():
    values = [{"date": datetime(2026, 10, 3, tzinfo=UTC)}, [Decimal("12.34"), UUID(int=42)], {42, 7}]
    for value in values:
        item = record("diagnostic=%r", (value,))
        expected = item.getMessage()
        assert EmailLogFilter().filter(item)
        assert item.getMessage() == expected


def test_partial_formatter_failure_keeps_safe_diagnostic_context():
    item = record("E42 %d", ("invalid john@[127.0.0.1]",))
    assert EmailLogFilter().filter(item)
    assert "E42" in item.getMessage()
    assert "john@[127.0.0.1]" not in repr(vars(item))
    assert item.name == "diagnostic.logger"


@pytest.mark.parametrize("level", ["error", "warning", "critical", "exception", "debug", "info"])
def test_deployed_error_logging_omits_raw_request_uri_and_header_errors(level):
    cfg = Config()
    cfg.set("errorlog", "-")
    cfg.set("loglevel", "debug")
    gunicorn = PrivacyGunicornLogger(cfg)
    protect_log_handlers()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    old = gunicorn.error_log.handlers[:]
    try:
        for h in old:
            gunicorn.error_log.removeHandler(h)
        gunicorn.error_log.addHandler(handler)
        gunicorn.error("Error handling request %s", "/api/people/john%40example.com?q=john@example.com")
        getattr(gunicorn, level)("Invalid request: %s", ValueError("header diagnostic E42 john.private @example.com"))
        output = stream.getvalue()
        assert "q=" not in output
        assert "john" not in output
        assert "header diagnostic E42" not in output
        assert "path=/api/people/[masked]" in output
        assert "ValueError" in output
    finally:
        gunicorn.error_log.removeHandler(handler)
        for h in old:
            gunicorn.error_log.addHandler(h)
