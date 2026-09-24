"""Reversible data freeze. Read flags at use time, including in job processes."""

import logging
import os
from functools import wraps
from threading import Lock

import click
from flask import jsonify

_log_lock = Lock()
_logged = False


def api_football_frozen() -> bool:
    global _logged
    frozen = os.getenv("API_FOOTBALL_FROZEN", "").strip().lower() in {"1", "true", "yes", "on"}
    if frozen and not _logged:
        with _log_lock:
            if not _logged:
                logging.getLogger(__name__).warning(
                    "API-Football frozen mode is ON: stored data only; ingestion disabled"
                )
                _logged = True
    return frozen


def newsletters_frozen() -> bool:
    return api_football_frozen() or os.getenv("NEWSLETTERS_FROZEN", "").strip().lower() in {"1", "true", "yes", "on"}


class FrozenModeError(click.ClickException):
    """A disabled operation; CLI reports an error and exits non-zero."""


def require_api_enabled():
    if api_football_frozen():
        raise FrozenModeError("API-Football is frozen. Stored data remains available; ingestion is disabled.")


def require_newsletters_enabled():
    if newsletters_frozen():
        raise FrozenModeError(
            "Newsletters are frozen. Generation, publishing, delivery and new subscriptions are disabled."
        )


def _route_gate(check):
    def decorate(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            try:
                check()
            except FrozenModeError as exc:
                return jsonify(error=exc.message, code="frozen"), 409
            return fn(*args, **kwargs)

        return guarded

    return decorate


api_enabled_route = _route_gate(require_api_enabled)
newsletters_enabled_route = _route_gate(require_newsletters_enabled)


def job_entrypoint(fn):
    """Turn a frozen job refusal into a clean nonzero command exit."""

    @wraps(fn)
    def main(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FrozenModeError as exc:
            click.echo(exc.message, err=True)
            return 1

    return main
