"""Logging-only privacy proofs, with real routes and mocked mail transports."""

import ast
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from src.auth import _ensure_user_account
from src.models.league import EmailToken, Newsletter, NewsletterDigestQueue, Team, UserAccount, db
from src.services.email_service import EmailResult, EmailService
from src.utils.log_privacy import EmailLogFilter, _scan_text, get_logger, mask_email

EMAIL = "john.private@example.com"
OTHER = "jane.private@example.net"
MASKED = "jo…@example.com"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (EMAIL, MASKED),
        ("jo@example.com", "j…@example.com"),
        ("j@example.com", "…@example.com"),
        ("abc@example.com", "ab…@example.com"),
        ("  john@example.com  ", MASKED),
        ("jo…@example.com", "[masked]"),
        (None, "[masked]"),
        (123, "[masked]"),
        ([], "[masked]"),
        ({}, "[masked]"),
        ("missing", "[masked]"),
        ("@example.com", "[masked]"),
        ("john@", "[masked]"),
        ("john@@example.com", "[masked]"),
        ("john@example.com\nother@else.com", "[masked]"),
        ("john@bad domain", "[masked]"),
        ("j ohn@example.com", "[masked]"),
    ],
)
def test_mask_email(value, expected):
    assert mask_email(value) == expected
    assert mask_email(value) != value


def assert_private(caplog, *addresses):
    for address in addresses or (EMAIL,):
        assert address not in caplog.text
        assert mask_email(address) in caplog.text


def test_filter_traceback_chains_stack_and_structured_fields(caplog):
    logger = get_logger("test.email_privacy")
    try:
        try:
            raise ValueError(f"provider echoed {EMAIL}")
        except ValueError as exc:
            raise RuntimeError(f"delivery to {OTHER} failed") from exc
    except RuntimeError:
        logger.exception("account %s %s", 42, EMAIL, extra={"recipient": OTHER, "payload": {"to": [EMAIL]}})
    assert EMAIL not in caplog.text and OTHER not in caplog.text
    assert "[masked]" in caplog.text
    record = caplog.records[-1]
    assert record.recipient == "[masked]"
    assert record.payload == {"to": ["[masked]"]}
    assert "ValueError" in caplog.text and "RuntimeError" in caplog.text
    assert "account 42" in caplog.text
    # A second handler/filter keeps the masking stable.
    EmailLogFilter().filter(record)
    assert record.getMessage() == "account 42 [masked]"
    assert EMAIL not in logging.Formatter().format(record)


@pytest.fixture
def auth_client(app, monkeypatch):
    from src.routes.auth_routes import auth_bp

    app.register_blueprint(auth_bp, url_prefix="/api")
    monkeypatch.delenv("REVIEW_LOGIN_ACCOUNTS", raising=False)
    monkeypatch.delenv("REVIEW_LOGIN_EMAIL", raising=False)
    monkeypatch.delenv("REVIEW_LOGIN_CODE", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setattr("src.services.admin_notify_service.notify_new_user", Mock())
    return app.test_client()


@pytest.mark.parametrize("outcome", ["success", "failure", "exception", "unconfigured"])
def test_request_code_logs_and_dev_print(auth_client, monkeypatch, caplog, capsys, outcome):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("src.routes.auth_routes._is_production", lambda: False)
    service = Mock()
    service.is_configured.return_value = outcome != "unconfigured"
    service.send_email.return_value = EmailResult(outcome == "success", "mailgun", error=f"refused {EMAIL}")
    if outcome == "exception":
        service.send_email.side_effect = requests.RequestException(f"echoed {EMAIL}")
    monkeypatch.setattr("src.routes.auth_routes.email_service", service)
    response = auth_client.post("/api/auth/request-code", json={"email": EMAIL})
    assert response.status_code == 200
    assert_private(caplog)
    assert EMAIL not in capsys.readouterr().out
    token = EmailToken.query.filter_by(email=EMAIL).one()
    assert f"token_id={token.id}" in caplog.text
    if outcome != "unconfigured":
        assert service.send_email.call_args.kwargs["to"] == EMAIL


@pytest.mark.parametrize("existing", [False, True])
def test_verify_and_new_user_logging(auth_client, monkeypatch, caplog, existing):
    caplog.set_level(logging.INFO)
    if existing:
        _ensure_user_account(EMAIL)
    token = EmailToken(
        email=EMAIL, token="test-code", purpose="login", expires_at=datetime.now(UTC) + timedelta(minutes=5)
    )
    db.session.add(token)
    db.session.commit()
    caplog.clear()
    response = auth_client.post("/api/auth/verify-code", json={"email": EMAIL, "code": token.token})
    assert response.status_code == 200
    assert response.json["token"]
    user = UserAccount.query.filter_by(email=EMAIL).one()
    assert_private(caplog)
    assert f"user_id={user.id}" in caplog.text
    assert ("Created user account" in caplog.text) == (not existing)


def test_verify_invalid_code_and_database_error(auth_client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    assert auth_client.post("/api/auth/verify-code", json={"email": EMAIL, "code": "wrong"}).status_code == 400
    assert_private(caplog)
    caplog.clear()
    monkeypatch.setattr(
        "src.routes.auth_routes._create_email_token", Mock(side_effect=ValueError(f"SQL params {EMAIL}"))
    )
    assert auth_client.post("/api/auth/request-code", json={"email": EMAIL}).status_code == 500
    assert_private(caplog)


@pytest.mark.parametrize("outcome", ["success", "client_error", "retry", "timeout", "exception"])
def test_mailgun_logs_without_provider_body(monkeypatch, caplog, outcome):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("MAILGUN_API_KEY", "test-key")
    monkeypatch.setenv("MAILGUN_DOMAIN", "example.org")
    service = EmailService()
    post = Mock(
        return_value=SimpleNamespace(
            ok=outcome == "success",
            status_code=400 if outcome == "client_error" else 503,
            text=f"PRIVATE_PROVIDER_BODY {EMAIL} {OTHER}",
            json=lambda: {"id": f"id-{EMAIL}"},
        )
    )
    if outcome in {"timeout", "exception"}:
        post.side_effect = (requests.Timeout if outcome == "timeout" else requests.RequestException)(
            f"failed {EMAIL} {OTHER}"
        )
    monkeypatch.setattr("src.services.email_service.requests.post", post)
    result = service.send_email(to=[EMAIL, OTHER], subject="test", html="body", text="body", use_fallback=False)
    assert result.success == (outcome == "success")
    assert_private(caplog, EMAIL, OTHER)
    assert "PRIVATE_PROVIDER_BODY" not in caplog.text
    assert post.call_args.kwargs["data"]["to"] == [EMAIL, OTHER]


@pytest.mark.parametrize("outcome", ["success", "auth_error", "smtp_error", "unexpected"])
def test_smtp_fallback_logs(monkeypatch, caplog, outcome):
    caplog.set_level(logging.INFO)
    monkeypatch.delenv("MAILGUN_API_KEY", raising=False)
    for key, value in {
        "SMTP_HOST": "localhost",
        "SMTP_USERNAME": EMAIL,
        "SMTP_PASSWORD": "test",
        "SMTP_USE_TLS": "true",
    }.items():
        monkeypatch.setenv(key, value)
    server = Mock()
    if outcome != "success":
        exc = {
            "auth_error": smtplib.SMTPAuthenticationError(535, f"refused {EMAIL}".encode()),
            "smtp_error": smtplib.SMTPRecipientsRefused({EMAIL: (550, b"refused")}),
            "unexpected": RuntimeError(f"unexpected {EMAIL}"),
        }[outcome]
        server.sendmail.side_effect = exc
    monkeypatch.setattr("src.services.email_service.smtplib.SMTP", Mock(return_value=server))
    result = EmailService().send_email(to=EMAIL, subject="test", html="body", text="body")
    assert result.success == (outcome == "success")
    assert_private(caplog)
    assert server.sendmail.call_args.args[1] == [EMAIL]


@pytest.mark.parametrize("outcome", ["success", "error", "exception"])
def test_n8n_digest_logs(app, monkeypatch, caplog, outcome):
    from src.services.newsletter_deadline_service import _send_single_digest

    caplog.set_level(logging.INFO)
    monkeypatch.setenv("N8N_EMAIL_WEBHOOK_URL", "https://example.org/test-only")
    monkeypatch.setattr("src.utils.data_mode.require_newsletters_enabled", lambda: None)
    user = _ensure_user_account(EMAIL)
    team = Team(name="Test team", team_id=123, country="England", season=2026)
    db.session.add(team)
    db.session.flush()
    newsletter = Newsletter(team_id=team.id, title="Test", content="{}", public_slug="test-private-logs")
    db.session.add(newsletter)
    db.session.flush()
    entry = NewsletterDigestQueue(user_id=user.id, newsletter_id=newsletter.id, week_key="2026-W40")
    db.session.add(entry)
    db.session.commit()
    post = Mock(
        return_value=SimpleNamespace(ok=outcome == "success", status_code=500, text=f"PRIVATE_PROVIDER_BODY {EMAIL}")
    )
    if outcome == "exception":
        post.side_effect = requests.RequestException(f"provider echoed {EMAIL}")
    monkeypatch.setattr("src.services.newsletter_deadline_service.requests.post", post)
    result = _send_single_digest(user.id, "2026-W40")
    assert result["success"] == (outcome == "success")
    assert_private(caplog)
    assert f"user_id={user.id}" in caplog.text
    assert "PRIVATE_PROVIDER_BODY" not in caplog.text
    assert post.call_args.kwargs["json"]["email"] == EMAIL


def test_compatibility_mail_helper_exception(app, monkeypatch, caplog):
    from src.routes.api import _send_email_via_webhook

    monkeypatch.setattr("src.routes.api.email_service.is_configured", lambda: True)
    monkeypatch.setattr("src.routes.api.email_service.send_email", Mock(side_effect=RuntimeError(f"echoed {EMAIL}")))
    with pytest.raises(RuntimeError):
        _send_email_via_webhook(email=EMAIL, subject="Test", html="Test", text="Test")
    assert_private(caplog)


# No address-bearing exceptions: only booleans/counts are safe without masking.
SAFE_WRAPPERS = {"mask_email", "log_metadata", "safe_exc_info", "bool", "len"}
EMAIL_NAMES = {
    "email",
    "user_email",
    "admin_email",
    "recipient",
    "to_email",
    "from_email",
    "reply_to",
    "address",
    "recipients",
    "to",
}


def email_name(value):
    name = value.lower()
    return name in EMAIL_NAMES or "email" in name or "recipient" in name


def unmasked_email_nodes(node):
    if isinstance(node, ast.IfExp):
        return unmasked_email_nodes(node.body) + unmasked_email_nodes(node.orelse)
    if (
        isinstance(node, ast.ListComp)
        and isinstance(node.elt, ast.Call)
        and isinstance(node.elt.func, ast.Name)
        and node.elt.func.id == "mask_email"
    ):
        return []
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SAFE_WRAPPERS:
        return []
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and email_name(str(node.args[1].value))
    ):
        return [node]
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and _scan_text(node.value) != node.value:
        return [node]
    if isinstance(node, ast.Name) and email_name(node.id):
        return [node]
    if isinstance(node, ast.Attribute) and email_name(node.attr):
        return [node]
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and email_name(str(node.slice.value)):
        return [node]
    return [found for child in ast.iter_child_nodes(node) for found in unmasked_email_nodes(child)]


def test_backend_logging_calls_mask_email_variables():
    root = Path(__file__).resolve().parents[1]
    failures = []
    paths = [*root.glob("*.py"), *(root / "src").rglob("*.py"), *(root / "scripts").rglob("*.py")]
    for path in paths:
        tree = ast.parse(path.read_text())
        if path.relative_to(root).as_posix() == "src/services/email_service.py":
            bindings = [
                n.value
                for n in ast.walk(tree)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "masked_recipients" for t in n.targets)
            ]
            assert bindings and all(
                isinstance(n, ast.ListComp)
                and isinstance(n.elt, ast.Call)
                and isinstance(n.elt.func, ast.Name)
                and n.elt.func.id == "mask_email"
                for n in bindings
            ), "EmailService masked_recipients allowlist requires helper-produced values"
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            logging_call = (
                isinstance(func, ast.Attribute)
                and func.attr in {"debug", "info", "warning", "error", "exception", "critical", "log"}
                and ("logger" in ast.unparse(func.value).lower() or "logging" in ast.unparse(func.value))
            )
            print_call = isinstance(func, ast.Name) and func.id == "print"
            if not (logging_call or print_call):
                continue
            for arg in [*call.args, *(kw.value for kw in call.keywords)]:
                # Already-built masked recipient list in EmailService.
                if (
                    path.relative_to(root).as_posix() == "src/services/email_service.py"
                    and isinstance(arg, ast.Name)
                    and arg.id == "masked_recipients"
                ):
                    continue
                if unmasked_email_nodes(arg):
                    failures.append(f"{path.relative_to(root)}:{call.lineno}: {ast.unparse(call)}")
    assert not failures, "Unmasked email log arguments:\n" + "\n".join(failures)


@pytest.mark.parametrize("failed", [False, True])
def test_admin_notification_logs(app, monkeypatch, caplog, failed):
    from src.services.admin_notify_service import _notify_in_background

    caplog.set_level(logging.INFO)
    monkeypatch.setenv("ADMIN_EMAILS", OTHER)
    # Run the existing background callback inline; no real sends or threads.
    monkeypatch.setattr(
        "src.services.admin_notify_service.threading.Thread", lambda target, **kwargs: SimpleNamespace(start=target)
    )
    send = Mock(return_value=EmailResult(True, "test"))
    if failed:
        send.side_effect = RuntimeError(f"provider echoed {EMAIL} {OTHER}")
    monkeypatch.setattr("src.services.email_service.email_service.send_email", send)
    _notify_in_background(f"New user {EMAIL}", "test body", "test body")
    assert EMAIL not in caplog.text
    assert_private(caplog, OTHER)
    assert send.call_args.kwargs["to"] == OTHER


@pytest.mark.parametrize("failed", [False, True])
def test_staff_invite_logging(app, monkeypatch, caplog, failed):
    from src.services.club_access import send_invite_email

    caplog.set_level(logging.INFO)
    monkeypatch.setattr("src.auth._is_production", lambda: False)
    monkeypatch.setenv("FLASK_ENV", "development")
    send = Mock(return_value=EmailResult(True, "test"))
    if failed:
        send.side_effect = RuntimeError(f"provider echoed {EMAIL}")
    monkeypatch.setattr("src.services.email_service.email_service.send_email", send)
    invite = SimpleNamespace(id=42, email=EMAIL, role="coach")
    assert send_invite_email(invite, "test-token", "Test club") == (not failed)
    assert_private(caplog)
    assert "42" in caplog.text
    assert send.call_args.kwargs["to"] == EMAIL


def test_background_mail_failure_logging(app, monkeypatch, caplog):
    service = EmailService()
    monkeypatch.setattr(service, "send_email", Mock(side_effect=RuntimeError(f"provider echoed {EMAIL}")))
    service._execute_background_send(job_id="test-job-42", to=EMAIL, subject="test", html="test", text="test")
    assert_private(caplog)
    assert "test-job-42" in caplog.text


def test_verify_error_logging(auth_client, monkeypatch, caplog):
    token = EmailToken(
        email=EMAIL, token="valid-code", purpose="login", expires_at=datetime.now(UTC) + timedelta(minutes=5)
    )
    db.session.add(token)
    db.session.commit()
    monkeypatch.setattr(
        "src.routes.auth_routes._ensure_user_account", Mock(side_effect=RuntimeError(f"SQL params {EMAIL}"))
    )
    assert auth_client.post("/api/auth/verify-code", json={"email": EMAIL, "code": token.token}).status_code == 500
    assert_private(caplog)


@pytest.mark.parametrize(
    ("expression", "unsafe"),
    [
        ("email", True),
        ("'john@example.com'", True),
        ("writer_email", True),
        ("invite_email", True),
        ("contact_email", True),
        ("email_address", True),
        ("contact_email_address", True),
        ("email_receiver", True),
        ("notification_recipient_address", True),
        ("masked_recipients", True),
        ("to", True),
        ("getattr(g, 'user_email', None)", True),
        ("mask_email(getattr(g, 'user_email', None))", False),
        ("f'{user.email}'", True),
        ("{'recipient': user_email}", True),
        ("mask_email(email)", False),
        ("[mask_email(r) for r in recipients]", False),
        ("bool(email)", False),
        ("mask_email(user.email) if user.email else user.id", False),
    ],
)
def test_logging_guard_controls(expression, unsafe):
    assert bool(unmasked_email_nodes(ast.parse(expression, mode="eval"))) == unsafe
