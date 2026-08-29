"""Shopify embedded-app authentication routes (Token Exchange flow).

Endpoints:
  POST /api/shopify/auth/token-exchange  -> authenticated by the Shopify ID token
                                            itself (Authorization: Bearer <id_token>),
                                            NOT the app's own JWT. Validates + exchanges
                                            + stores the offline Admin token server-side.
  GET  /api/shopify/auth/status          -> app-admin only; non-secret auth status.
  GET  /api/shopify/auth/test            -> app-admin only; tests the stored exchanged
                                            token against the real Admin GraphQL API.
  POST /api/shopify/auth/disconnect      -> app-admin only; removes the stored token.
  GET  /api/shopify/config               -> PUBLIC; exposes only the non-secret client id
                                            so the embedded frontend can boot App Bridge.

Security: the offline Admin access token is stored encrypted (secrets_store) and is
never returned to the browser, written to logs, or included in any response body.
"""
import logging
from fastapi import APIRouter, Request, HTTPException, Depends

from db import db
from utils import now_iso
from auth import require_permission
from shopify_client import shopify_client
import shopify_auth
import app_config
import secrets_store

logger = logging.getLogger("shopify.auth.routes")

api4 = APIRouter(prefix="/api/shopify")


def _bearer_id_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer ID token.")
    return header[7:].strip()


async def _auth_status() -> dict:
    conn = await db.app_state.find_one({"id": "shopify_conn"}, {"_id": 0}) or {}
    return {
        "app_configured": shopify_auth.is_app_configured(),   # client id+secret present
        "authenticated": await secrets_store.is_configured("shopify_token"),
        "shop": shopify_client.domain or conn.get("shop") or "",
        "api_version": shopify_client.api_version,
        "mode": shopify_client.mode,
        "granted_scopes": conn.get("granted_scopes", []),
        "last_connection": conn.get("last_connection"),
        "auth_method": "token_exchange",
    }


@api4.get("/config")
async def public_config():
    """Public, non-secret config for the embedded frontend to initialise App Bridge.
    Exposes ONLY the client id (a.k.a. API key), which is public by design."""
    return {
        "api_key": shopify_auth.client_id(),
        "app_configured": shopify_auth.is_app_configured(),
        "shop": shopify_client.domain or "",
    }


@api4.post("/auth/token-exchange")
async def token_exchange(request: Request):
    """Authenticated solely by the Shopify ID token (App Bridge session token).

    Validates the ID token -> exchanges it for an OFFLINE Admin API access token ->
    stores it encrypted server-side. Returns only non-secret status.
    """
    id_token = _bearer_id_token(request)

    # 1) Validate the session/ID token locally (signature, exp, nbf, aud, iss/dest).
    try:
        result = shopify_auth.validate_id_token(id_token)
    except shopify_auth.ShopifyAuthError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})
    shop = result["shop"]

    # 2) Exchange the validated ID token for an offline Admin API access token.
    try:
        exchanged = await shopify_auth.exchange_offline_token(shop, id_token)
    except shopify_auth.ShopifyAuthError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})

    # 3) Persist the offline token encrypted at rest (server-side only).
    if not secrets_store.secrets_available():
        raise HTTPException(status_code=503,
                            detail="Secrets unavailable: APP_SECRETS_ENCRYPTION_KEY is not configured on the server.")
    await secrets_store.set_secret("shopify_token", exchanged["access_token"])

    # 4) Record non-secret connection metadata; shop domain is authoritative (from dest).
    scopes = [s.strip() for s in (exchanged.get("scope") or "").split(",") if s.strip()]
    await app_config.update_shopify({"domain": shop})
    await db.app_state.update_one(
        {"id": "shopify_conn"},
        {"$set": {"id": "shopify_conn", "shop": shop, "granted_scopes": scopes,
                  "last_connection": now_iso(), "auth_method": "token_exchange"}},
        upsert=True,
    )
    await db.audit_log.insert_one({
        "id": f"AUTH-{now_iso()}", "resource_id": "shopify_auth", "resource_type": "auth",
        "source": "TokenExchange", "actor": shop, "actor_role": "shopify",
        "timestamp": now_iso(), "changes": [{"field": "shopify_offline_token", "action": "obtained"}],
        "reverted": False,
    })

    # NOTE: APP_DATA_MODE is intentionally NOT changed here, and NO sync is triggered.
    await shopify_client.reload()
    logger.info("Shopify offline token obtained & stored for shop=%s (scopes=%s)", shop, ",".join(scopes))

    status = await _auth_status()
    return {"authenticated": True, "shop": shop, "granted_scopes": scopes,
            "message": "Shopify authentication successful. Offline Admin token stored securely.",
            "status": status}


@api4.get("/auth/status")
async def auth_status(user: dict = Depends(require_permission("settings"))):
    return await _auth_status()


@api4.get("/auth/test")
async def auth_test(user: dict = Depends(require_permission("settings"))):
    """Test the stored exchanged token against the real Admin GraphQL API.
    Works regardless of APP_DATA_MODE (it validates the credential itself)."""
    await shopify_client.reload()
    return await shopify_client.verify_stored_connection()


@api4.post("/auth/disconnect")
async def auth_disconnect(user: dict = Depends(require_permission("settings"))):
    await secrets_store.delete_secret("shopify_token")
    await db.app_state.update_one(
        {"id": "shopify_conn"},
        {"$set": {"id": "shopify_conn", "granted_scopes": [], "last_connection": None,
                  "disconnected_at": now_iso()}},
        upsert=True,
    )
    await shopify_client.reload()
    await db.audit_log.insert_one({
        "id": f"AUTH-{now_iso()}", "resource_id": "shopify_auth", "resource_type": "auth",
        "source": "Disconnect", "actor": user.get("email"), "actor_role": user.get("role"),
        "timestamp": now_iso(), "changes": [{"field": "shopify_offline_token", "action": "revoked"}],
        "reverted": False,
    })
    return await _auth_status()
