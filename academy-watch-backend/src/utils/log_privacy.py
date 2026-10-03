"""Logging-only privacy: explicit email masks and linear whole-token redaction."""

import logging
import re
import sys
import traceback
from collections import OrderedDict, defaultdict
from datetime import date, time, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from secrets import token_hex
from uuid import UUID

# This cap belongs only to the explicit address helper, never to log records.
MAX_LOG_CHARS = 65536
_DELIMITERS = frozenset("@<>\"',;:=()[]{}/?\\\x00")
_TOKEN = re.compile(r"\S+")
_FORMAT_WIDTH = re.compile(r"%(?:\([^)%]*\))?[-+ #0]*(\d+|\*)(?:\.(\d+|\*))?")
_FAILURE = "[privacy formatting failed]"
_DONE = object()
_STANDARD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


class _LogException(Exception):
    """A rendered exception snapshot without request objects or live frames."""


class _MaskedEmail(str):
    """Provenance from our helper, never inferred from user-controlled spelling."""


def mask_email(value) -> str:
    """Keep at most two local characters and the domain, hiding short locals."""
    try:
        if not isinstance(value, str) or len(value) > MAX_LOG_CHARS or value.count("@") != 1:
            return _MaskedEmail("[masked]")
        local, domain = value.strip().split("@")
        if (
            not local
            or not domain
            or not all(c.isalnum() or c in "._-" for c in domain)
            or any(c.isspace() or c in _DELIMITERS or c == "…" for c in local)
        ):
            return _MaskedEmail("[masked]")
        prefix = local[: min(2, max(0, len(local) - 1))]
        return _MaskedEmail(f"{prefix}…@{domain}")
    except Exception:
        return _MaskedEmail("[masked]")


def _redact_tokens(value):
    if "@" not in value:
        return value

    # Whitespace alone delimits tokens. No address grammar, backwards search,
    # Unicode alphabet classification, input budget or recursive URL decoding.
    def replace(match):
        token = match.group()
        return "[masked]" if token.find("@", 1, len(token) - 1) >= 0 else token

    return _TOKEN.sub(replace, value)


def _scan_text(value):
    """Replace entire non-space tokens with an interior @ in O(input length)."""
    return _redact_tokens(value)


def _text(value):
    try:
        return _scan_text(value)
    except Exception:
        # Independent primitive fallback: preserve all other text and metadata.
        return _redact_tokens(value)


def redact_email_text(value, addresses=()):
    """Mask known destinations (including malformed spacing), then @ tokens.

    Used only for mail/auth error text. Preserve provider codes and diagnostics;
    delivery/result objects and exceptions remain untouched.
    """
    text = _render(value)
    for address in addresses:
        if isinstance(address, str) and address and any(c.isspace() for c in address):
            text = text.replace(address, "[masked]")
    return _text(text)


class _RenderedTraceback(Exception):
    """Helper-owned complete traceback already scrubbed of known recipients."""


def email_exc_info(addresses=()):
    """Keep the native class, message, chain and stack; redact only addresses."""
    kind, error, tb = sys.exc_info()
    if kind is None:
        return None
    try:
        rendered = "".join(traceback.format_exception(kind, error, tb))
        return kind, _RenderedTraceback(redact_email_text(rendered, addresses)), None
    except Exception:
        return kind, _RenderedTraceback(f"{kind.__name__}: {redact_email_text(error, addresses)}"), None


def _render(value):
    try:
        return str(value)
    except Exception:
        return f"[{_text(type(value).__name__)} could not be rendered]"


def _has_helper_mask(value):
    """Leave ordinary arguments native, including cycles and set ordering."""
    pending, seen = [value], set()
    while pending:
        item = pending.pop()
        if type(item) is _MaskedEmail:
            return True
        if type(item) not in (dict, OrderedDict, defaultdict, list, tuple, set, frozenset):
            continue
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        else:
            pending.extend(item)
    return False


class _Fields:
    def __init__(self):
        self.active = set()
        self.trusted = {}
        self.prefix = "__privacy_" + token_hex(16) + "_"

    def field(self, value, *, placeholders=False):
        if type(value) is _MaskedEmail:
            if not placeholders:
                return value
            token = self.prefix + str(len(self.trusted)) + "__"
            self.trusted[token] = str(value)
            return token
        if isinstance(value, str):
            return _text(value)
        if isinstance(value, bytes):
            return _text(value.decode("latin-1")).encode("latin-1")
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, (dict, list, tuple, set, frozenset)):
            ident = id(value)
            if ident in self.active:
                return "[cyclic log value]"
            self.active.add(ident)
            try:
                if isinstance(value, dict):
                    pairs = []
                    used = set()
                    collision = 0
                    for key, val in value.items():
                        safe_key = self.field(key)
                        if safe_key in used:
                            collision += 1
                            while f"privacy_extra_{collision}" in used:
                                collision += 1
                            safe_key = f"privacy_extra_{collision}"
                        used.add(safe_key)
                        pairs.append((safe_key, self.field(val, placeholders=placeholders)))
                    if type(value) is defaultdict:
                        return defaultdict(value.default_factory, pairs)
                    return OrderedDict(pairs) if type(value) is OrderedDict else dict(pairs)
                items = [self.field(v, placeholders=placeholders) for v in value]
                if isinstance(value, tuple):
                    return type(value)(*items) if hasattr(value, "_fields") else tuple(items)
                if isinstance(value, set):
                    return set(items)
                if isinstance(value, frozenset):
                    return frozenset(items)
                return items
            except Exception:
                return _text(_render(value))
            finally:
                self.active.remove(ident)
        rendered = _render(value)
        redacted = _text(rendered)
        return (
            value
            if redacted == rendered and isinstance(value, (date, time, timedelta, Decimal, Enum, UUID, PurePath))
            else redacted
        )

    def message(self, record):
        # Exactly logging's normal message coercion, before %-formatting.
        template = _render(record.msg)
        if not record.args:
            return _text(template)
        try:
            # Reject only absurd formatter allocations, not large real text.
            # Templates at application sites are constants. This guards odd
            # third-party records without imposing a character/container cap.
            for match in _FORMAT_WIDTH.finditer(template):
                if any(v and v != "*" and (len(v) > 8 or int(v) > 100_000_000) for v in match.groups()):
                    raise ValueError("invalid log format expansion")
                if "*" in match.groups() and any(isinstance(v, int) and abs(v) > 100_000_000 for v in record.args):
                    raise ValueError("invalid log format expansion")
            # Native numeric/scalar formatting is unchanged. Only helper values
            # need placeholders; don't inspect unused Gunicorn header atoms.
            if not _has_helper_mask(record.args):
                args = record.args
            elif isinstance(record.args, dict) and "%(" in template:
                args = _FormatMapping(record.args, self)
            elif isinstance(record.args, dict):
                args = self.argument(record.args)
            else:
                args = tuple(self.argument(v) for v in record.args)
            rendered = _text(template % args)
            if self.trusted:
                # One replacement pass, not one scan per recipient.
                pattern = re.compile(re.escape(self.prefix) + r"\d+__")
                rendered = pattern.sub(lambda m: self.trusted.get(m.group(), "[masked]"), rendered)
            return rendered
        except Exception:
            return f"{_FAILURE} template={_text(template)} arguments={_render(self.field(record.args))}"

    def argument(self, value):
        if type(value) is _MaskedEmail:
            return self.field(value, placeholders=True)
        # Preserve native repr/formatting for ordinary containers and objects;
        # only genuine helper values need substitution before rendering.
        if type(value) not in (dict, OrderedDict, defaultdict, list, tuple, set, frozenset):
            return value
        ident = id(value)
        if ident in self.active:
            return value
        self.active.add(ident)
        try:
            if isinstance(value, dict):
                pairs = [(self.argument(k), self.argument(v)) for k, v in value.items()]
                if type(value) is defaultdict:
                    return defaultdict(value.default_factory, pairs)
                return OrderedDict(pairs) if type(value) is OrderedDict else dict(pairs)
            items = [self.argument(v) for v in value]
            if type(value) is tuple:
                return tuple(items)
            if type(value) is set:
                return set(items)
            if type(value) is frozenset:
                return frozenset(items)
            return items
        finally:
            self.active.remove(ident)


class _FormatMapping(dict):
    def __init__(self, original, fields):
        self.original, self.fields = original, fields

    def __getitem__(self, key):
        return self.fields.argument(self.original[key])


class EmailLogFilter(logging.Filter):
    """Every record survives; render normally, then redact entire @ tokens."""

    def filter(self, record):
        try:
            return self._filter(record)
        except Exception:
            original = vars(record).copy()
            safe = {}
            collision = 0
            for key, value in original.items():
                try:
                    safe_key = _text(_render(key))
                    if safe_key in safe:
                        collision += 1
                        safe_key = f"privacy_fallback_{collision}"
                    safe[safe_key] = (
                        _text(_render(value)) if value is not None and type(value) not in (bool, int, float) else value
                    )
                except Exception:
                    collision += 1
                    safe[f"privacy_fallback_{collision}"] = "[log field could not be rendered]"
            safe["msg"] = _text(_render(original.get("msg", "Operation failed")))
            safe["args"] = ()
            safe["exc_info"] = None
            safe["exc_text"] = _text(_render(original["exc_text"])) if original.get("exc_text") else None
            safe["privacy_fallback"] = "[logging privacy fallback]"
            safe["_email_privacy_done"] = _DONE
            record.__dict__ = safe
            return True

    def _filter(self, record):
        if getattr(record, "_email_privacy_done", None) is _DONE:
            return True
        fields = _Fields()
        try:
            record.msg = fields.message(record)
        except Exception:
            record.msg = _text(_render(record.msg)) + " [log arguments could not be rendered]"
        record.args = ()
        try:
            if record.exc_info and record.exc_info[0] is not None:
                kind, error, tb = record.exc_info
                rendered = (
                    str(error)
                    if type(error) is _RenderedTraceback
                    else _text("".join(traceback.format_exception(kind, error, tb)))
                )
                record.exc_text = rendered
                header = kind if kind.__module__ == "builtins" and "@" not in kind.__name__ else _LogException
                record.exc_info = (header, _LogException(rendered), None)
            elif record.exc_text:
                record.exc_text = _text(_render(record.exc_text))
                record.exc_info = None
            else:
                record.exc_info = None
        except Exception:
            record.exc_text = "Exception: [exception could not be rendered]"
            record.exc_info = None
        # Includes top-level keys; collisions retain all values under neutral
        # numbered keys, while standard field names remain intact.
        safe = {}
        collision = 0
        for key, value in vars(record).copy().items():
            if key == "_email_privacy_done":
                continue
            safe_key = key if key in _STANDARD_FIELDS else _text(_render(key))
            if safe_key in safe:
                collision += 1
                while f"privacy_extra_{collision}" in safe:
                    collision += 1
                safe_key = f"privacy_extra_{collision}"
            try:
                safe[safe_key] = value if key in {"msg", "args", "exc_info", "exc_text"} else fields.field(value)
            except Exception:
                safe[safe_key] = _text(_render(value))
        safe["_email_privacy_done"] = _DONE
        record.__dict__ = safe
        return True


_FILTER = EmailLogFilter()
_ORIGINAL_ADD_HANDLER = getattr(logging.Logger, "_email_privacy_original_add_handler", logging.Logger.addHandler)
logging.Logger._email_privacy_original_add_handler = _ORIGINAL_ADD_HANDLER


def get_logger(name: str) -> logging.Logger:
    """Protect mail-related standalone jobs even before app startup."""
    logger = logging.getLogger(name)
    if _FILTER not in logger.filters:
        logger.addFilter(_FILTER)
    return logger


def _add_protected_handler(logger, handler):
    if _FILTER not in handler.filters:
        handler.addFilter(_FILTER)
    _ORIGINAL_ADD_HANDLER(logger, handler)


def protect_log_handlers() -> None:
    """Protect existing/private handlers and future logging configuration.

    Gunicorn access/error and SQLAlchemy echo handlers do not necessarily
    propagate to root. Logger.addHandler is the standard attachment boundary,
    also used by dictConfig/basicConfig and handlers created after app preload.
    """
    logging.Logger.addHandler = _add_protected_handler
    loggers = [logging.getLogger()]
    loggers.extend(v for v in logging.Logger.manager.loggerDict.copy().values() if isinstance(v, logging.Logger))
    for logger in loggers:
        for handler in logger.handlers:
            if _FILTER not in handler.filters:
                handler.addFilter(_FILTER)
    if logging.lastResort and _FILTER not in logging.lastResort.filters:
        logging.lastResort.addFilter(_FILTER)
