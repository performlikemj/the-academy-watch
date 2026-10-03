"""Azure Key Vault integration for secret management.

Loads secrets from Azure Key Vault in production, falls back to
environment variables for local development.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Module-level cache for loaded secrets
_secret_cache: dict[str, str] = {}


def load_secret(secret_name: str, vault_url: str | None = None) -> str | None:
    """Load a secret from Azure Key Vault, falling back to env var.

    Args:
        secret_name: The Key Vault secret name (also used as env var name).
        vault_url: Key Vault URL. Defaults to AZURE_KEY_VAULT_URL env var.

    Returns:
        The secret value, or None if not found.
    """
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]

    vault_url = vault_url or os.getenv("AZURE_KEY_VAULT_URL")

    if vault_url:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=vault_url, credential=credential)
            secret = client.get_secret(secret_name)
            value = secret.value
            if value:
                _secret_cache[secret_name] = value
                logger.info("Loaded secret '%s' from Key Vault", secret_name)
                return value
            else:
                logger.warning("Secret '%s' exists in Key Vault but has no value", secret_name)
        except ImportError:
            logger.warning(
                "azure-identity or azure-keyvault-secrets not installed; falling back to env var for '%s'",
                secret_name,
            )
        except Exception as e:
            logger.warning(
                "Failed to load secret '%s' from Key Vault: %s; falling back to env var",
                secret_name,
                e,
            )

    # Fallback to environment variable
    value = os.getenv(secret_name)
    if value:
        value = value.strip()
        _secret_cache[secret_name] = value
        logger.info("Loaded secret '%s' from environment variable", secret_name)
    else:
        logger.warning("Secret '%s' not found in Key Vault or environment", secret_name)

    return value or None


def clear_cache():
    """Clear the secret cache (useful for testing)."""
    _secret_cache.clear()
