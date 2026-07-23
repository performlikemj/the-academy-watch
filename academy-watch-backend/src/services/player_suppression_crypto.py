"""Authenticated field encryption for player takedown request details.

The funding-registry branch established the project's Fernet ``TypeDecorator``
precedent for private evidence.  Suppression requests use the same fail-closed
shape, with a domain-specific key preferred and a domain-separated derivation
from Flask's existing ``SECRET_KEY`` as the deployment-safe fallback.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context
from sqlalchemy.types import Text, TypeDecorator

_PREFIX = "fernet:v1:"
_DERIVATION_CONTEXT = b"the-academy-watch/player-suppression/v1\0"


class SuppressionEncryptionError(RuntimeError):
    """Raised when suppression details cannot be encrypted or decrypted."""


def _secret_key() -> str | None:
    raw = (os.getenv("SECRET_KEY") or "").strip()
    if not raw and has_app_context():
        raw = str(current_app.config.get("SECRET_KEY") or "").strip()
    return raw or None


def _candidate_keys() -> list[bytes]:
    """Return configured Fernet keys in write preference order.

    ``PLAYER_SUPPRESSION_ENCRYPTION_KEY`` is the long-term dedicated key.  A
    domain-separated SECRET_KEY derivation keeps the public intake live when
    this trust-floor stack deploys before its dedicated secret is provisioned.
    Reads try both available keys so a later dedicated-key rollout does not
    strand earlier ciphertext.
    """

    candidates: list[bytes] = []
    for env_name in ("PLAYER_SUPPRESSION_ENCRYPTION_KEY",):
        raw = (os.getenv(env_name) or "").strip()
        if raw:
            try:
                candidates.append(raw.encode("ascii"))
            except UnicodeEncodeError as exc:
                raise SuppressionEncryptionError(f"{env_name} must be a valid Fernet key") from exc

    secret = _secret_key()
    if secret:
        digest = hashlib.sha256(_DERIVATION_CONTEXT + secret.encode("utf-8")).digest()
        candidates.append(base64.urlsafe_b64encode(digest))

    unique: list[bytes] = []
    for key in candidates:
        if key in unique:
            continue
        try:
            Fernet(key)
        except (ValueError, TypeError) as exc:
            raise SuppressionEncryptionError("player suppression encryption key must be a valid Fernet key") from exc
        unique.append(key)
    if not unique:
        raise SuppressionEncryptionError(
            "PLAYER_SUPPRESSION_ENCRYPTION_KEY or SECRET_KEY is required for takedown request encryption"
        )
    return unique


class EncryptedSuppressionText(TypeDecorator):
    """Store suppression request text as opaque authenticated ciphertext."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            raise SuppressionEncryptionError("suppression values must be strings")
        token = Fernet(_candidate_keys()[0]).encrypt(value.encode("utf-8")).decode("ascii")
        return f"{_PREFIX}{token}"

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith(_PREFIX):
            raise SuppressionEncryptionError("unencrypted suppression value rejected")
        token = value.removeprefix(_PREFIX).encode("ascii")
        for key in _candidate_keys():
            try:
                return Fernet(key).decrypt(token).decode("utf-8")
            except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError):
                continue
        raise SuppressionEncryptionError("suppression value failed authentication")


__all__ = ["EncryptedSuppressionText", "SuppressionEncryptionError"]
