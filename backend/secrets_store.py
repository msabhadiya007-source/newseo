"""Server-side encrypted secret storage.

Secrets (Shopify Admin token + AI provider API keys) are encrypted at rest with
Fernet (authenticated AES-128-CBC + HMAC) using a master key supplied ONLY through
the server environment (APP_SECRETS_ENCRYPTION_KEY). The master key is NEVER stored
in MongoDB. Ciphertext lives in db.app_secrets.

Resolution priority (documented):
    environment secret  ->  encrypted stored secret  ->  unavailable

Secret VALUES are never returned to any API response; only presence/'configured'
booleans are exposed. If the master key is missing we fail safely (Secrets
unavailable) and never rewrite/corrupt existing ciphertext.
"""
import os
import logging

from cryptography.fernet import Fernet, InvalidToken

from db import db

logger = logging.getLogger("secrets")

# logical secret name -> production ENV override variable
SECRET_ENV_MAP = {
    "shopify_token": "SHOPIFY_ADMIN_ACCESS_TOKEN",
    "ai_openai": "OPENAI_API_KEY",
    "ai_anthropic": "ANTHROPIC_API_KEY",
    "ai_gemini": "GEMINI_API_KEY",
    "ai_deepseek": "DEEPSEEK_API_KEY",
}


def _fernet():
    key = os.environ.get("APP_SECRETS_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:  # noqa - malformed key
        logger.error("APP_SECRETS_ENCRYPTION_KEY is present but invalid (must be a urlsafe base64 32-byte Fernet key).")
        return None


def secrets_available() -> bool:
    """True when the master encryption key is usable."""
    return _fernet() is not None


async def set_secret(name: str, value: str):
    f = _fernet()
    if f is None:
        raise RuntimeError("SECRETS_UNAVAILABLE")
    if not value:
        raise ValueError("empty secret")
    ciphertext = f.encrypt(value.encode()).decode()
    await db.app_secrets.update_one(
        {"id": name}, {"$set": {"id": name, "ciphertext": ciphertext}}, upsert=True)


async def get_secret(name: str):
    """Return the plaintext secret for server-side use ONLY. Never expose in responses."""
    env_var = SECRET_ENV_MAP.get(name)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    doc = await db.app_secrets.find_one({"id": name})
    if not doc:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(doc["ciphertext"].encode()).decode()
    except InvalidToken:
        logger.error("Could not decrypt secret '%s' (master key changed?). Leaving ciphertext untouched.", name)
        return None


async def secret_source(name: str) -> str:
    env_var = SECRET_ENV_MAP.get(name)
    if env_var and os.environ.get(env_var):
        return "env"
    if await db.app_secrets.find_one({"id": name}):
        return "stored"
    return "none"


async def is_configured(name: str) -> bool:
    return (await secret_source(name)) != "none"


async def delete_secret(name: str):
    # only removes the UI-stored ciphertext; an env override (if any) is untouched
    await db.app_secrets.delete_one({"id": name})
