"""Email masking at logging boundaries; never alter stored or delivered values."""

import logging
import re
import traceback

# Deliberately broader than an email validator: malformed address-like tokens
# in exception messages must also be withheld. Exclude log/JSON delimiters.
_ADDRESS = re.compile(r"[^\s@<>\"',;:=()\[\]{}]+@[^\s<>\"',;:()\[\]{}]+")
_DOMAIN = re.compile(r"[\w.-]+", re.UNICODE)


def mask_email(value) -> str:
    """Keep at most two local characters and the domain, hiding short locals."""
    if not isinstance(value, str) or value.count("@") != 1:
        return "[masked]"
    local, domain = value.strip().split("@")
    if not local or not domain or not _DOMAIN.fullmatch(domain) or any(c.isspace() for c in local):
        return "[masked]"
    if "…" in local:
        return "[masked]"
    prefix = local[: min(2, max(0, len(local) - 1))]
    return f"{prefix}…@{domain}"


def _mask_text(value: str) -> str:
    def replace(match):
        token = match.group()
        if token.count("@") != 1:
            return mask_email(token)
        local, domain = token.split("@", 1)
        # Explicit call-site masking and multiple handlers remain idempotent.
        if local.endswith("…") and len(local) <= 3 and _DOMAIN.fullmatch(domain):
            return token
        return mask_email(token)

    return _ADDRESS.sub(replace, value)


def _mask_field(value):
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, bytes):
        return _mask_text(value.decode("utf-8", errors="replace")).encode("utf-8")
    if isinstance(value, dict):
        return {_mask_field(k): _mask_field(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(_mask_field(v) for v in value)
    return value


class EmailLogFilter(logging.Filter):
    """Mask rendered messages, tracebacks and structured extras before handlers."""

    def filter(self, record):
        message = record.getMessage()
        masked = _mask_text(message)
        if masked != message:
            record.msg = masked
            record.args = ()
        if record.exc_info:
            text = "".join(traceback.format_exception(*record.exc_info)).rstrip()
            masked = _mask_text(text)
            if masked != text:
                record.exc_text = masked
                record.exc_info = None
        for key, value in list(vars(record).items()):
            if key not in {"msg", "args"}:
                setattr(record, key, _mask_field(value))
        return True


_FILTER = EmailLogFilter()


def get_logger(name: str) -> logging.Logger:
    """Protect email-related loggers even in standalone jobs and unit tests."""
    logger = logging.getLogger(name)
    if _FILTER not in logger.filters:
        logger.addFilter(_FILTER)
    return logger


def protect_log_handlers() -> None:
    """Cover propagated third-party/other backend errors at app startup."""
    for handler in logging.getLogger().handlers:
        if _FILTER not in handler.filters:
            handler.addFilter(_FILTER)
