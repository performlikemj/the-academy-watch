import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Default in-memory storage is fine for small scale; override via RATELIMIT_STORAGE_URL
_limiter_storage = os.getenv("RATELIMIT_STORAGE_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_limiter_storage,
)

__all__ = ["limiter"]
