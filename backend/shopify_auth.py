"""Shopify embedded-app authentication via the OAuth 2.0 Token Exchange flow.

Flow (no manual shpat_ token, no legacy auth-code redirect):
  1. Embedded React frontend loads App Bridge and obtains a fresh Shopify *session
     token* (a.k.a. ID token) — a short-lived HS256 JWT signed with the app's
     client secret.
  2. Frontend sends it to the backend as `Authorization: Bearer <id_token>`.
  3. Backend validates the JWT locally (signature/exp/nbf/aud/iss/dest) using
     SHOPIFY_CLIENT_SECRET + SHOPIFY_CLIENT_ID — NO network call needed to verify.
  4. Backend exchanges the validated ID token at
        POST https://{shop}/admin/oauth/access_token
     using grant_type=token-exchange, requesting an *offline* Admin API access
     token suitable for background sync/jobs.
  5. The offline token is stored ONLY server-side, encrypted at rest via
     secrets_store (logical name 'shopify_token'). It is never returned to the
     browser, written to logs, or exposed in any API response.

Security notes:
  - Client id/secret come exclusively from server environment variables.
  - Access tokens / secrets are never logged.
  - The shop hostname is taken from the validated `dest` claim (authoritative).
"""
import os
import asyncio
import logging
from urllib.parse import urlparse

import jwt  # PyJWT

logger = logging.getLogger("shopify.auth")

# --- OAuth 2.0 Token Exchange grant / token-type URNs (Shopify) ---
GRANT_TYPE_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
SUBJECT_TOKEN_TYPE_ID_TOKEN = "urn:ietf:params:oauth:token-type:id_token"
OFFLINE_ACCESS_TOKEN_TYPE = "urn:shopify:params:oauth:token-type:offline-access-token"
ONLINE_ACCESS_TOKEN_TYPE = "urn:shopify:params:oauth:token-type:online-access-token"

_ALG = "HS256"


class ShopifyAuthError(Exception):
    """Raised for any validation/exchange failure. `status` maps to an HTTP code."""

    def __init__(self, code: str, message: str, status: int = 401):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def client_id() -> str:
    return (os.environ.get("SHOPIFY_CLIENT_ID") or "").strip()


def client_secret() -> str:
    return (os.environ.get("SHOPIFY_CLIENT_SECRET") or "").strip()


def is_app_configured() -> bool:
    """True when both client credentials are present in the environment."""
    return bool(client_id() and client_secret())


def _shop_hostname(url_or_host: str) -> str:
    if not url_or_host:
        return ""
    if "://" not in url_or_host:
        url_or_host = "https://" + url_or_host
    return (urlparse(url_or_host).hostname or "").lower()


def validate_id_token(id_token: str) -> dict:
    """Validate a Shopify session (ID) token JWT.

    Verifies: HS256 signature (SHOPIFY_CLIENT_SECRET), exp, nbf, aud == client_id,
    and iss/dest shop hostname consistency. Returns a dict:
        {"claims": <decoded claims>, "shop": "<shop>.myshopify.com"}
    Raises ShopifyAuthError on any failure. NEVER logs the token or claims.
    """
    if not id_token or not id_token.strip():
        raise ShopifyAuthError("MISSING_ID_TOKEN", "Authorization Bearer ID token is required.", 401)
    if not is_app_configured():
        raise ShopifyAuthError(
            "APP_NOT_CONFIGURED",
            "Shopify app credentials (SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET) are not configured on the server.",
            503,
        )

    try:
        claims = jwt.decode(
            id_token,
            client_secret(),
            algorithms=[_ALG],
            audience=client_id(),               # verifies aud == client_id
            options={"require": ["exp", "nbf", "iss", "dest", "aud"]},
            leeway=10,                          # small tolerance for clock skew
        )
    except jwt.ExpiredSignatureError:
        raise ShopifyAuthError("TOKEN_EXPIRED", "Shopify ID token has expired.", 401)
    except jwt.ImmatureSignatureError:
        raise ShopifyAuthError("TOKEN_NOT_YET_VALID", "Shopify ID token is not valid yet (nbf).", 401)
    except jwt.InvalidAudienceError:
        raise ShopifyAuthError("INVALID_AUDIENCE", "Shopify ID token audience does not match this app.", 401)
    except jwt.InvalidTokenError:
        # covers bad signature, malformed token, missing required claims
        raise ShopifyAuthError("INVALID_ID_TOKEN", "Shopify ID token is invalid.", 401)

    dest_host = _shop_hostname(claims.get("dest", ""))
    iss_host = _shop_hostname(claims.get("iss", ""))
    if not dest_host or not iss_host:
        raise ShopifyAuthError("INVALID_CLAIMS", "Shopify ID token missing shop (iss/dest).", 401)
    if dest_host != iss_host:
        raise ShopifyAuthError("SHOP_MISMATCH", "Shopify ID token iss/dest shop mismatch.", 401)
    if not dest_host.endswith(".myshopify.com"):
        raise ShopifyAuthError("INVALID_SHOP", "Shopify ID token shop is not a valid myshopify.com host.", 401)

    return {"claims": claims, "shop": dest_host}


async def exchange_offline_token(shop: str, id_token: str) -> dict:
    """Exchange a validated ID token for an OFFLINE Admin API access token.

    Returns {"access_token": str, "scope": str}. Raises ShopifyAuthError on failure.
    The returned access_token is a secret — callers must store it via secrets_store
    and must never log or return it.
    """
    if not is_app_configured():
        raise ShopifyAuthError("APP_NOT_CONFIGURED", "Shopify app credentials are not configured.", 503)

    import requests

    url = f"https://{shop}/admin/oauth/access_token"
    payload = {
        "client_id": client_id(),
        "client_secret": client_secret(),
        "grant_type": GRANT_TYPE_TOKEN_EXCHANGE,
        "subject_token": id_token,
        "subject_token_type": SUBJECT_TOKEN_TYPE_ID_TOKEN,
        "requested_token_type": OFFLINE_ACCESS_TOKEN_TYPE,
    }
    try:
        resp = await asyncio.to_thread(
            requests.post, url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
    except Exception as e:  # noqa - network layer
        raise ShopifyAuthError("EXCHANGE_UNAVAILABLE", f"Could not reach Shopify token endpoint: {e}", 502)

    if resp.status_code != 200:
        # Do NOT include response body verbatim in case it echoes sensitive input.
        detail = ""
        try:
            body = resp.json()
            detail = body.get("error_description") or body.get("error") or ""
        except Exception:  # noqa
            pass
        logger.warning("Shopify token exchange failed for shop=%s status=%s", shop, resp.status_code)
        raise ShopifyAuthError(
            "EXCHANGE_FAILED",
            f"Shopify rejected the token exchange (HTTP {resp.status_code}). {detail}".strip(),
            502,
        )

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise ShopifyAuthError("EXCHANGE_NO_TOKEN", "Shopify token exchange returned no access token.", 502)
    return {"access_token": access_token, "scope": data.get("scope", "")}
