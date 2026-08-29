"""Central non-secret application configuration (Shopify mode + AI provider models).

Stored in db.app_config (single doc id='app_config'). An in-memory cache is loaded
at startup and refreshed after every change so sync code (ShopifyClient properties)
can read effective values without awaiting Mongo.

Secret VALUES never live here — only non-sensitive settings (models, enabled flags,
mode, domain, api_version, limits). Secrets live in secrets_store.
"""
import copy

from db import db

DEFAULTS = {
    "id": "app_config",
    "shopify": {
        "mode": "demo",          # demo | live
        "mock_mode": True,        # simulate Shopify without real credentials
        "domain": "",
        "api_version": "2025-01",
    },
    "ai": {
        "enabled": True,
        "default_provider": "openai",
        "max_products_per_job": 5000,
        "daily_limit": 5000,
        "max_concurrency": 3,
        "daily_cost_limit": None,
        "fallback_enabled": False,
        "providers": {
            "openai":    {"enabled": False, "model": "gpt-5.4"},
            "anthropic": {"enabled": False, "model": "claude-sonnet-4-5"},
            "gemini":    {"enabled": False, "model": "gemini-3.1-pro-preview"},
            "deepseek":  {"enabled": False, "model": "deepseek-v4-flash"},
        },
    },
}

_cache = None


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


async def load():
    global _cache
    doc = await db.app_config.find_one({"id": "app_config"}, {"_id": 0})
    if not doc:
        doc = copy.deepcopy(DEFAULTS)
        await db.app_config.insert_one(copy.deepcopy(doc))
    # merge over defaults so newly added keys always exist
    _cache = _merge(DEFAULTS, doc)
    return _cache


def get():
    return _cache if _cache is not None else copy.deepcopy(DEFAULTS)


async def update_shopify(patch: dict):
    cur = get()
    new_shop = _merge(cur["shopify"], patch)
    await db.app_config.update_one({"id": "app_config"}, {"$set": {"shopify": new_shop}}, upsert=True)
    return await load()


async def update_ai(patch: dict):
    cur = get()
    new_ai = _merge(cur["ai"], patch)
    await db.app_config.update_one({"id": "app_config"}, {"$set": {"ai": new_ai}}, upsert=True)
    return await load()


async def update_provider(provider: str, patch: dict):
    cur = get()
    providers = copy.deepcopy(cur["ai"]["providers"])
    providers.setdefault(provider, {"enabled": False, "model": ""})
    providers[provider] = _merge(providers[provider], patch)
    await db.app_config.update_one({"id": "app_config"}, {"$set": {"ai.providers": providers}}, upsert=True)
    return await load()
