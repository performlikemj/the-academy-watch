"""Bounded, fail-closed logging privacy; never alter delivery or stored values."""

import logging
import re
from collections import OrderedDict, defaultdict
from itertools import islice
from urllib.parse import unquote

MAX_LOG_CHARS = 65536
MAX_LOG_NODES = 512
MAX_CONTAINER_ITEMS = 64
_MAX_DEPTH = 8
_OMITTED = "[log value withheld: privacy limit]"
_FAILURE = "[log message withheld: privacy formatting failed]"
_TOKEN_PREFIX = "__privacy_mask_"
_DONE = object()
_FORMAT_WIDTH = re.compile(r"%(?:\([^)%]*\))?[-+ #0]*(\d+|\*)(?:\.(\d+|\*))?")
_DELIMITERS = frozenset("@<>\"',;:=()[]{}/?\\\x00")


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


def _scan_text(value):
    """Each candidate's local/domain span is visited at most twice (O(n))."""
    if "@" not in value:
        return value
    pieces = []
    copied = floor = index = 0
    last_quote = previous_quote = -1
    while index < len(value):
        if value[index] != "@":
            if value[index] == '"':
                previous_quote, last_quote = last_quote, index
            index += 1
            continue
        end = index + 1
        while end < len(value) and (value[end].isalnum() or value[end] in "._-"):
            end += 1
        domain = value[index + 1 : end].rstrip(".")
        end = index + 1 + len(domain)
        start = index
        if start > 0 and value[start - 1] == '"':
            # Quoted local parts may contain spaces and escaped quotes.
            if previous_quote >= 0:
                start = max(copied, previous_quote)
        else:
            while start > floor and not value[start - 1].isspace() and value[start - 1] not in _DELIMITERS:
                start -= 1
        # Avoid @handles, asset scale suffixes and numeric package versions.
        host = "." in domain and domain.rsplit(".", 1)[-1].isalpha()
        scale = domain.split(".", 1)[0]
        asset_scale = start > 0 and value[start - 1] == "/" and scale.endswith("x") and scale[:-1].isdigit()
        chained_at = end < len(value) and value[end] == "@"
        if chained_at or (start < index and host and not asset_scale):
            replacement = "[masked]" if chained_at else str(mask_email(value[start:end]))
            pieces.extend((value[copied:start], replacement))
            copied = end
        floor = end if end > index + 1 else index + 1
        index = floor
    pieces.append(value[copied:])
    return "".join(pieces)


class _Budget:
    def __init__(self):
        self.chars = MAX_LOG_CHARS
        self.nodes = MAX_LOG_NODES
        self.active = set()
        self.trusted = []

    def text(self, value, *, rendered=False):
        # Discard an entire oversized value: a truncated prefix might itself
        # contain a complete local part whose @ lies beyond the limit.
        if len(value) > self.chars:
            return _OMITTED
        self.chars -= len(value)
        if not rendered:
            value = value.replace("\x00", "?").replace(_TOKEN_PREFIX, "[reserved]")
        masked = _scan_text(value)
        # Access/request URLs can encode both @ and Unicode local parts.
        # At most three bounded decoding passes; ordinary encoded text stays as-is.
        decoded = value
        for _ in range(3):
            if "%" not in decoded:
                break
            decoded = unquote(decoded)
            candidate = _scan_text(decoded)
            if candidate != decoded:
                return candidate
        return masked

    def field(self, value, depth=0, *, placeholders=False):
        self.nodes -= 1
        if self.nodes < 0 or depth > _MAX_DEPTH:
            return _OMITTED
        if type(value) is _MaskedEmail:
            if len(value) > self.chars:
                return _OMITTED
            self.chars -= len(value)
            if placeholders:
                token = f"{_TOKEN_PREFIX}{len(self.trusted)}__"
                self.trusted.append(str(value))
                return token
            return value
        if isinstance(value, str):
            if placeholders:
                if len(value) > self.chars:
                    return _OMITTED
                self.chars -= len(value)
                return value.replace("\x00", "?").replace(_TOKEN_PREFIX, "[reserved]")
            return self.text(value)
        if isinstance(value, bytes):
            if len(value) > self.chars:
                return _OMITTED.encode()
            if b"@" not in value and b"%" not in value:
                self.chars -= len(value)
                return value
            # Latin-1 is lossless, including invalid UTF-8. Ordinary bytes retain
            # their exact representation; address spans alone are replaced.
            return self.text(value.decode("latin-1")).encode("latin-1", errors="backslashreplace")
        if value is None or type(value) in (bool, int, float):
            return value
        if isinstance(value, BaseException):
            return f"{self.text(type(value).__name__)}: {self.field(value.args, depth + 1, placeholders=placeholders)}"
        if isinstance(value, (dict, tuple, list, set, frozenset)):
            ident = id(value)
            if ident in self.active:
                return "[cyclic log value withheld]"
            self.active.add(ident)
            try:
                if isinstance(value, dict):
                    pairs = [
                        (self.field(k, depth + 1), self.field(v, depth + 1, placeholders=placeholders))
                        for k, v in islice(value.items(), MAX_CONTAINER_ITEMS)
                    ]
                    if len(value) > MAX_CONTAINER_ITEMS:
                        pairs.append((_OMITTED, _OMITTED))
                    if type(value) is defaultdict:
                        return defaultdict(value.default_factory, pairs)
                    if type(value) is OrderedDict:
                        return OrderedDict(pairs)
                    return dict(pairs)
                items = [
                    self.field(v, depth + 1, placeholders=placeholders) for v in islice(value, MAX_CONTAINER_ITEMS)
                ]
                if len(value) > MAX_CONTAINER_ITEMS:
                    items.append(_OMITTED)
                if isinstance(value, tuple):
                    return tuple(items)  # namedtuples need positional construction
                if isinstance(value, set):
                    return set(items)
                if isinstance(value, frozenset):
                    return frozenset(items)
                return items
            finally:
                self.active.remove(ident)
        # Do not invoke arbitrary __str__/__repr__ on untrusted objects.
        return f"[{self.text(type(value).__name__)} log value withheld]"

    def exception(self, exc, tb, depth=0):
        if depth > _MAX_DEPTH or self.nodes <= 0:
            return _OMITTED
        self.nodes -= 1
        parts = []
        linked = exc.__cause__ or (exc.__context__ if not exc.__suppress_context__ else None)
        if linked is not None:
            parts.append(self.exception(linked, linked.__traceback__, depth + 1))
            parts.append("The above exception caused the following exception:")
        parts.append("Traceback (most recent call last):")
        for _ in range(20):
            if tb is None:
                break
            code = tb.tb_frame.f_code
            parts.append(self.text(f'  File "{code.co_filename}", line {tb.tb_lineno}, in {code.co_name}'))
            tb = tb.tb_next
        if tb is not None:
            parts.append(_OMITTED)
        parts.append(str(self.field(exc)))
        return "\n".join(parts)


class EmailLogFilter(logging.Filter):
    """Bound messages, exceptions and extras; logging can never fail the caller."""

    def filter(self, record):
        try:
            if getattr(record, "_email_privacy_done", None) is _DONE:
                return True
            budget = _Budget()
            template = budget.field(record.msg, placeholders=True)
            args = budget.field(record.args, placeholders=True)
            try:
                # Bound aggregate padding and repeated mapping substitutions
                # before Python's %-formatter can allocate a large output.
                values = args.values() if isinstance(args, dict) else args
                size = max((len(str(v)) for v in values), default=0)
                padding = 0
                for width in _FORMAT_WIDTH.finditer(template):
                    if any(v == "*" or len(v) > 5 or int(v) > MAX_LOG_CHARS for v in width.groups() if v):
                        raise ValueError("log format expansion limit")
                    padding += sum(int(v) for v in width.groups() if v)
                if len(template) + template.count("%") * size + padding > MAX_LOG_CHARS:
                    raise ValueError("log format expansion limit")
                message = template % args if args else str(template)
                # Bound formatting expansion as well as input strings.
                message = budget.text(message, rendered=True)
                for index, trusted in enumerate(budget.trusted):
                    message = message.replace(f"{_TOKEN_PREFIX}{index}__", trusted)
            except Exception:
                # Keep the level/context and a safe template even for bad %d/%s.
                message = f"{_FAILURE} template={budget.text(template)}"
            record.msg, record.args = message, ()
            if record.exc_info:
                record.exc_text = budget.exception(record.exc_info[1], record.exc_info[2])
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = budget.text(record.exc_text)
            safe = {}
            for key, value in islice(vars(record).items(), MAX_LOG_NODES):
                if key in {"msg", "args", "exc_info", "exc_text"}:
                    safe[key] = value
                elif key != "_email_privacy_done":
                    safe[key] = budget.field(value)
            if len(vars(record)) > MAX_LOG_NODES:
                safe["privacy_extra_overflow"] = _OMITTED
            safe["_email_privacy_done"] = _DONE
            record.__dict__ = safe
        except Exception:
            # Never suppress an error record or let masking raise into app code.
            try:
                exc_type = type(record.exc_info[1]).__name__ if record.exc_info else ""
            except Exception:
                exc_type = "Exception"
            original = vars(record)
            level = original.get("levelno", logging.ERROR)
            level = level if type(level) is int else logging.ERROR
            safe = {
                key: value
                for key, value in islice(original.items(), MAX_LOG_NODES)
                if type(value) in (int, float, bool) or value is None
            }
            for key in ("name", "pathname", "filename", "module", "funcName", "threadName", "processName"):
                safe[key] = _FAILURE
            safe.update(
                msg=_FAILURE,
                args=(),
                exc_info=None,
                exc_text=f"{exc_type}: {_FAILURE}" if exc_type else None,
                levelno=level,
                levelname=logging.getLevelName(level),
                _email_privacy_done=_DONE,
            )
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
