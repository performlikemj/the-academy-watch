"""Authenticated field encryption for private grassroots claim evidence."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import Text, TypeDecorator

_PREFIX = "fernet:v1:"


class EvidenceEncryptionError(RuntimeError):
    """Raised when evidence cannot be encrypted or safely decrypted."""


def _fernet() -> Fernet:
    raw_key = (os.getenv("FUNDING_EVIDENCE_ENCRYPTION_KEY") or "").strip()
    if not raw_key:
        raise EvidenceEncryptionError("FUNDING_EVIDENCE_ENCRYPTION_KEY is required")
    try:
        return Fernet(raw_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise EvidenceEncryptionError("FUNDING_EVIDENCE_ENCRYPTION_KEY must be a valid Fernet key") from exc


class EncryptedEvidenceText(TypeDecorator):
    """Store claim evidence as opaque, authenticated ciphertext."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            raise EvidenceEncryptionError("evidence values must be strings")
        token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return f"{_PREFIX}{token}"

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith(_PREFIX):
            raise EvidenceEncryptionError("unencrypted evidence value rejected")
        try:
            return _fernet().decrypt(value.removeprefix(_PREFIX).encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise EvidenceEncryptionError("evidence value failed authentication") from exc
