"""Phase 2 foundation rollout switch (dark by default)."""

import os


def foundation_enabled() -> bool:
    return os.getenv("P2_FOUNDATION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
