"""Admin-only secure configuration endpoints.

Shopify credentials + AI provider API keys are written here but NEVER read back.
GET endpoints return only non-secret status (configured true/false, model, mode).
All secret-management is gated behind the 'settings' permission (Admin only).
"""
from fastapi import APIRouter, Depends, HTTPException, Body

from db import db
from utils import now_iso
from auth import get_current_user, require_permission
from shopify_client import shopify_client
import app_config
import secrets_store
import ai_providers
import prompt_manager

api3 = APIRouter(prefix="/api")


async def _shopify_status():
    cfg = app_config.get().get("shopify", {})
    state = await db.sync_state.find_one({"id": shopify_client.data_source}, {"_id": 0})
    conn = await db.app_state.find_one({"id": "shopify_conn"}, {"_id": 0})
    return {
        "mode": shopify_client.mode,
        "mock_mode": shopify_client.mock_mode,
        "domain": shopify_client.domain or "",
        "api_version": shopify_client.api_version,
        "data_source": shopify_client.data_source,
        "connected": shopify_client.is_connected,
        "config_error": shopify_client.config_error,
        "token_configured": await secrets_store.is_configured("shopify_token"),
        "last_sync": state.get("last_sync") if state else None,
        "last_connection": conn.get("last_connection") if conn else None,
    }


async def _usage_today():
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    agg = await db.ai_usage.aggregate([
        {"$match": {"day": day}},
        {"$group": {"_id": None, "requests": {"$sum": 1},
                    "products": {"$sum": {"$ifNull": ["$products", 0]}},
                    "input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                    "output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                    "cost": {"$sum": {"$ifNull": ["$estimated_cost", 0]}}}},
    ]).to_list(1)
    a = agg[0] if agg else {}
    return {"day": day, "requests": a.get("requests", 0), "products": a.get("products", 0),
            "input_tokens": a.get("input_tokens", 0), "output_tokens": a.get("output_tokens", 0),
            "estimated_cost": round(a.get("cost", 0), 4)}


@api3.get("/settings/config")
async def get_config(user: dict = Depends(require_permission("settings"))):
    ai = app_config.get().get("ai", {})
    return {
        "secrets_available": secrets_store.secrets_available(),
        "shopify": await _shopify_status(),
        "ai": {
            "enabled": ai.get("enabled", True),
            "default_provider": ai.get("default_provider", "openai"),
            "max_products_per_job": ai.get("max_products_per_job"),
            "daily_limit": ai.get("daily_limit"),
            "max_concurrency": ai.get("max_concurrency"),
            "daily_cost_limit": ai.get("daily_cost_limit"),
            "fallback_enabled": ai.get("fallback_enabled", False),
            "providers": await ai_providers.provider_status(),
        },
        "usage_today": await _usage_today(),
    }


# ------------------------- Shopify secure config -------------------------
@api3.put("/settings/shopify")
async def put_shopify(payload: dict = Body(...), user: dict = Depends(require_permission("settings"))):
    if not secrets_store.secrets_available():
        raise HTTPException(status_code=503, detail="Secrets unavailable: APP_SECRETS_ENCRYPTION_KEY is not configured on the server.")
    patch = {}
    if "domain" in payload:
        patch["domain"] = str(payload["domain"] or "").strip().replace("https://", "").replace("http://", "").strip("/")
    if "api_version" in payload:
        patch["api_version"] = str(payload["api_version"] or "").strip() or "2025-01"
    if "mode" in payload:
        mode = str(payload["mode"]).strip().lower()
        if mode not in ("demo", "live"):
            raise HTTPException(status_code=400, detail="mode must be 'demo' or 'live'")
        patch["mode"] = mode
    if "mock_mode" in payload:
        patch["mock_mode"] = bool(payload["mock_mode"])
    if patch:
        await app_config.update_shopify(patch)
    token = payload.get("token")
    if token:  # only store when a non-empty value is submitted
        await secrets_store.set_secret("shopify_token", str(token).strip())
    await shopify_client.reload()
    await db.audit_log.insert_one({"id": f"CFG-{now_iso()}", "resource_id": "shopify_config",
                                   "resource_type": "config", "source": "SettingsUpdate",
                                   "actor": user.get("email"), "actor_role": user.get("role"),
                                   "timestamp": now_iso(), "changes": [{"field": "shopify_config"}],
                                   "reverted": False})
    return await _shopify_status()


@api3.delete("/settings/shopify/token")
async def delete_shopify_token(user: dict = Depends(require_permission("settings"))):
    await secrets_store.delete_secret("shopify_token")
    await shopify_client.reload()
    return await _shopify_status()


# ------------------------- AI global config -------------------------
@api3.put("/settings/ai")
async def put_ai(payload: dict = Body(...), user: dict = Depends(require_permission("settings"))):
    patch = {}
    if "enabled" in payload:
        patch["enabled"] = bool(payload["enabled"])
    if "fallback_enabled" in payload:
        patch["fallback_enabled"] = bool(payload["fallback_enabled"])
    if "default_provider" in payload:
        dp = str(payload["default_provider"]).strip().lower()
        if dp not in ai_providers.PROVIDERS:
            raise HTTPException(status_code=400, detail=f"default_provider must be one of {ai_providers.PROVIDERS}")
        patch["default_provider"] = dp
    for k in ("max_products_per_job", "daily_limit", "max_concurrency"):
        if k in payload and payload[k] is not None:
            try:
                patch[k] = max(1, int(payload[k]))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{k} must be an integer")
    if "daily_cost_limit" in payload:
        v = payload["daily_cost_limit"]
        patch["daily_cost_limit"] = None if v in (None, "", 0) else float(v)
    if patch:
        await app_config.update_ai(patch)
    ai = app_config.get().get("ai", {})
    return {"ok": True, "ai": {k: ai.get(k) for k in ("enabled", "default_provider", "max_products_per_job",
                                                       "daily_limit", "max_concurrency", "daily_cost_limit",
                                                       "fallback_enabled")}}


@api3.put("/settings/ai/{provider}")
async def put_ai_provider(provider: str, payload: dict = Body(...),
                          user: dict = Depends(require_permission("settings"))):
    provider = provider.lower()
    if provider not in ai_providers.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    patch = {}
    if "model" in payload:
        patch["model"] = str(payload["model"] or "").strip()
    if "enabled" in payload:
        patch["enabled"] = bool(payload["enabled"])
    if patch:
        await app_config.update_provider(provider, patch)
    api_key = payload.get("api_key")
    if api_key:
        if not secrets_store.secrets_available():
            raise HTTPException(status_code=503, detail="Secrets unavailable: APP_SECRETS_ENCRYPTION_KEY not configured.")
        await secrets_store.set_secret(f"ai_{provider}", str(api_key).strip())
    status = await ai_providers.provider_status()
    return {"ok": True, "provider": provider, "status": status[provider]}


@api3.delete("/settings/ai/{provider}/key")
async def delete_ai_key(provider: str, user: dict = Depends(require_permission("settings"))):
    provider = provider.lower()
    if provider not in ai_providers.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    await secrets_store.delete_secret(f"ai_{provider}")
    status = await ai_providers.provider_status()
    return {"ok": True, "provider": provider, "status": status[provider]}


@api3.get("/settings/ai/{provider}/test")
async def test_ai_provider(provider: str, user: dict = Depends(require_permission("settings"))):
    provider = provider.lower()
    if provider not in ai_providers.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    try:
        prov = await ai_providers.get_provider(provider, allow_mock=False)
    except ai_providers.ProviderError as e:
        if e.code == "NOT_CONFIGURED":
            return {"connected": False, "status": "not_configured",
                    "message": f"{provider} API key is not configured."}
        return {"connected": False, "status": "error", "message": e.message}
    result = await prov.test_connection()
    # never leak key / raw provider payloads
    return {k: v for k, v in result.items() if k in
            ("connected", "status", "message", "model", "mock")}


# ------------------------- Prompt manager -------------------------
@api3.get("/settings/prompts")
async def get_prompts(user: dict = Depends(require_permission("settings"))):
    out = {}
    for t in prompt_manager.PROMPT_TYPES:
        active = await prompt_manager.get_active_version(t)
        versions = await prompt_manager.list_versions(t)
        out[t] = {"active_version": active.get("version") if active else None,
                  "text": active.get("text") if active else prompt_manager.DEFAULTS[t],
                  "versions": len(versions),
                  "is_default": (active.get("text") if active else "") == prompt_manager.DEFAULTS[t]}
    return out


@api3.get("/settings/prompts/{prompt_type}/history")
async def prompt_history(prompt_type: str, user: dict = Depends(require_permission("settings"))):
    if prompt_type not in prompt_manager.PROMPT_TYPES:
        raise HTTPException(status_code=404, detail="unknown prompt type")
    return {"type": prompt_type, "versions": await prompt_manager.list_versions(prompt_type)}


@api3.put("/settings/prompts/{prompt_type}")
async def update_prompt(prompt_type: str, payload: dict = Body(...),
                        user: dict = Depends(require_permission("settings"))):
    if prompt_type not in prompt_manager.PROMPT_TYPES:
        raise HTTPException(status_code=404, detail="unknown prompt type")
    text = str(payload.get("text", "")).strip()
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Prompt text is too short.")
    res = await prompt_manager.save_version(prompt_type, text, user.get("email", "admin"))
    return {"ok": True, **res}


@api3.post("/settings/prompts/{prompt_type}/restore-default")
async def restore_prompt(prompt_type: str, user: dict = Depends(require_permission("settings"))):
    if prompt_type not in prompt_manager.PROMPT_TYPES:
        raise HTTPException(status_code=404, detail="unknown prompt type")
    res = await prompt_manager.restore_default(prompt_type, user.get("email", "admin"))
    return {"ok": True, **res}
