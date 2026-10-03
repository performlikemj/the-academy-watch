"""Runtime operational control for the assistant."""

import os

MAINTENANCE_MESSAGE = "The assistant is under maintenance. Back soon."
MAINTENANCE_RETRY_SECONDS = 60


class GolMaintenance(Exception):
    def __init__(self):
        super().__init__(MAINTENANCE_MESSAGE)


def provider_config() -> tuple[str, str]:
    # Preserve the existing provider selection: only openrouter selects that provider.
    provider = os.getenv("GOL_PROVIDER", "openai")
    key_name = "OPENROUTER_API_KEY" if provider == "openrouter" else "OPENAI_API_KEY"
    return provider, (os.getenv(key_name) or "").strip()


def maintenance_enabled() -> bool:
    return os.getenv("GOL_MAINTENANCE", "false").strip().lower() in {"1", "true", "yes", "on"}


def assistant_under_maintenance() -> bool:
    return maintenance_enabled() or not provider_config()[1]


def maintenance_payload() -> dict:
    return {"error": "maintenance", "message": MAINTENANCE_MESSAGE, "retryable": True}
