"""Multi-provider AI adapter layer (SEOAIProvider).

All AI provider access is centralised behind one interface so the rest of the SEO
application never knows provider-specific request formats. Adapters:
  OpenAIProvider, AnthropicProvider, GeminiProvider, DeepSeekProvider, MockProvider

All requests originate from the backend only. Keys are read from the encrypted
secret store at call time and never logged or returned.

This layer is draft-only: it produces structured SEO suggestions. It has NO Shopify
mutation capability whatsoever.
"""
import os
import re
import json
import logging
import asyncio

import requests

import app_config
import secrets_store

logger = logging.getLogger("ai_providers")

PROVIDERS = ["openai", "anthropic", "gemini", "deepseek"]
TIMEOUT = 30


class ProviderError(Exception):
    def __init__(self, code, message=""):
        self.code = code
        self.message = message or code
        super().__init__(f"{code}: {self.message}")


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    # strip code fences
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except Exception:  # noqa
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa
                return None
    return None


class SEOAIProvider:
    name = "base"

    def __init__(self, api_key, model):
        self.api_key = api_key
        self.model = model

    async def test_connection(self):
        raise NotImplementedError

    async def _chat(self, system, user, json_mode=True):
        """Return (text, usage_dict)."""
        raise NotImplementedError

    async def generate_product_seo(self, system_prompt, context: dict):
        user = "VERIFIED PRODUCT DATA (JSON):\n" + json.dumps(context, ensure_ascii=False)
        text, usage = await self._chat(system_prompt, user)
        data = _extract_json(text) or {"status": "malformed", "warnings": ["MALFORMED_OUTPUT"]}
        return {"result": data, "usage": usage, "provider": self.name, "model": self.model}

    async def generate_collection_seo(self, system_prompt, context: dict):
        return await self.generate_product_seo(system_prompt, context)

    async def analyze_seo_quality(self, system_prompt, payload: dict):
        user = "SEO TO REVIEW (JSON):\n" + json.dumps(payload, ensure_ascii=False)
        text, usage = await self._chat(system_prompt, user)
        data = _extract_json(text) or {"ai_quality": 0, "breakdown": {}, "warnings": ["MALFORMED_OUTPUT"]}
        return {"result": data, "usage": usage, "provider": self.name, "model": self.model}

    def estimate_usage(self, n):
        return {"calls": n, "est_input_tokens": n * 650, "est_output_tokens": n * 180, "estimated": True}


# ------------------------- OpenAI / DeepSeek (OpenAI-compatible) -------------------------
class _OpenAICompatible(SEOAIProvider):
    BASE = "https://api.openai.com/v1"

    async def test_connection(self):
        def _do():
            return requests.get(f"{self.BASE}/models",
                                headers={"Authorization": f"Bearer {self.api_key}"}, timeout=TIMEOUT)
        try:
            r = await asyncio.to_thread(_do)
        except Exception as e:  # noqa
            return {"connected": False, "status": "provider_unavailable", "message": str(e)[:180]}
        return _map_status(r.status_code, self.model)

    async def _chat(self, system, user, json_mode=True):
        def _do():
            body = {"model": self.model,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}]}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            return requests.post(f"{self.BASE}/chat/completions",
                                 headers={"Authorization": f"Bearer {self.api_key}",
                                          "Content-Type": "application/json"},
                                 json=body, timeout=TIMEOUT)
        r = await asyncio.to_thread(_do)
        _raise_for_provider(r.status_code)
        body = r.json()
        text = body["choices"][0]["message"]["content"]
        u = body.get("usage", {}) or {}
        usage = {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
                 "total_tokens": u.get("total_tokens"), "estimated": False}
        return text, usage


class OpenAIProvider(_OpenAICompatible):
    name = "openai"
    BASE = "https://api.openai.com/v1"


class DeepSeekProvider(_OpenAICompatible):
    name = "deepseek"
    BASE = "https://api.deepseek.com"


# ------------------------- Anthropic -------------------------
class AnthropicProvider(SEOAIProvider):
    name = "anthropic"
    BASE = "https://api.anthropic.com/v1"
    VERSION = "2023-06-01"

    def _headers(self):
        return {"x-api-key": self.api_key, "anthropic-version": self.VERSION,
                "Content-Type": "application/json"}

    async def test_connection(self):
        def _do():
            return requests.get(f"{self.BASE}/models", headers=self._headers(), timeout=TIMEOUT)
        try:
            r = await asyncio.to_thread(_do)
        except Exception as e:  # noqa
            return {"connected": False, "status": "provider_unavailable", "message": str(e)[:180]}
        return _map_status(r.status_code, self.model)

    async def _chat(self, system, user, json_mode=True):
        def _do():
            body = {"model": self.model, "max_tokens": 700, "system": system,
                    "messages": [{"role": "user", "content": user}]}
            return requests.post(f"{self.BASE}/messages", headers=self._headers(), json=body, timeout=TIMEOUT)
        r = await asyncio.to_thread(_do)
        _raise_for_provider(r.status_code)
        body = r.json()
        parts = body.get("content", [])
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        u = body.get("usage", {}) or {}
        usage = {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                 "total_tokens": (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0), "estimated": False}
        return text, usage


# ------------------------- Google Gemini -------------------------
class GeminiProvider(SEOAIProvider):
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    async def test_connection(self):
        def _do():
            return requests.get(f"{self.BASE}/models?key={self.api_key}", timeout=TIMEOUT)
        try:
            r = await asyncio.to_thread(_do)
        except Exception as e:  # noqa
            return {"connected": False, "status": "provider_unavailable", "message": str(e)[:180]}
        return _map_status(r.status_code, self.model)

    async def _chat(self, system, user, json_mode=True):
        def _do():
            body = {"systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"responseMimeType": "application/json" if json_mode else "text/plain"}}
            return requests.post(f"{self.BASE}/models/{self.model}:generateContent?key={self.api_key}",
                                 headers={"Content-Type": "application/json"}, json=body, timeout=TIMEOUT)
        r = await asyncio.to_thread(_do)
        _raise_for_provider(r.status_code)
        body = r.json()
        cands = body.get("candidates", [])
        text = ""
        if cands:
            text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
        um = body.get("usageMetadata", {}) or {}
        usage = {"input_tokens": um.get("promptTokenCount"), "output_tokens": um.get("candidatesTokenCount"),
                 "total_tokens": um.get("totalTokenCount"), "estimated": False}
        return text, usage


# ------------------------- Mock (deterministic, for tests / no-key) -------------------------
class MockProvider(SEOAIProvider):
    name = "mock"

    def __init__(self, api_key="mock", model="mock-seo-v1"):
        super().__init__(api_key, model)

    async def test_connection(self):
        return {"connected": True, "status": "connected", "mock": True, "model": self.model,
                "message": "Mock AI provider is always available (used when no real key is configured)."}

    async def generate_product_seo(self, system_prompt, context: dict):
        model_name = context.get("device_model") or ""
        brand = context.get("brand", "UrbanDotted")
        ptype = context.get("product_type", "Phone Case")
        pname = context.get("product_name", "Case")
        facts = context.get("verified_features", []) or []
        title = (f"{pname} for {model_name}" if model_name else pname).strip()
        title = f"{title} | {brand}"[:60]
        meta = (f"Shop the {pname}" + (f" for {model_name}" if model_name else "") +
                f". {ptype} by {brand}" + (f" featuring {', '.join(facts)}" if facts else "") +
                ". Fast Australian shipping.")[:160]
        used = ([model_name] if model_name else []) + facts
        return {"result": {"status": "ok", "seo_title": title, "meta_description": meta,
                           "confidence": 0.9, "used_facts": used, "warnings": [],
                           "summary": "Mock suggestion grounded strictly in supplied verified facts."},
                "usage": {"input_tokens": 600, "output_tokens": 120, "total_tokens": 720, "estimated": True},
                "provider": self.name, "model": self.model}

    async def analyze_seo_quality(self, system_prompt, payload: dict):
        return {"result": {"ai_quality": 26, "breakdown": {"relevance": 6, "clarity": 5, "search_intent": 5,
                                                           "natural_language": 5, "ctr_potential": 5},
                           "warnings": [], "summary": "Mock quality analysis."},
                "usage": {"input_tokens": 300, "output_tokens": 80, "total_tokens": 380, "estimated": True},
                "provider": self.name, "model": self.model}


_CLASSES = {"openai": OpenAIProvider, "anthropic": AnthropicProvider,
            "gemini": GeminiProvider, "deepseek": DeepSeekProvider}


def _map_status(code, model):
    if code == 200:
        return {"connected": True, "status": "connected", "model": model}
    if code in (401, 403):
        return {"connected": False, "status": "invalid_api_key", "message": "Authentication failed (check API key)."}
    if code == 404:
        return {"connected": False, "status": "unsupported_model", "message": "Endpoint/model not found."}
    if code == 429:
        return {"connected": False, "status": "rate_limited", "message": "Rate limited or quota exceeded."}
    if code >= 500:
        return {"connected": False, "status": "provider_unavailable", "message": f"Provider error ({code})."}
    return {"connected": False, "status": "error", "message": f"Unexpected status {code}."}


def _raise_for_provider(code):
    if code == 200:
        return
    if code in (401, 403):
        raise ProviderError("INVALID_API_KEY", "Authentication failed")
    if code == 404:
        raise ProviderError("UNSUPPORTED_MODEL", "Model/endpoint not found")
    if code == 429:
        raise ProviderError("QUOTA_EXCEEDED", "Rate limited / quota exceeded")
    if code >= 500:
        raise ProviderError("PROVIDER_UNAVAILABLE", f"Provider error {code}")
    raise ProviderError("PROVIDER_ERROR", f"Unexpected status {code}")


def _force_mock() -> bool:
    return os.environ.get("AI_FORCE_MOCK", "false").strip().lower() == "true"


async def get_provider(name=None, allow_mock=True):
    """Resolve a provider adapter. Env AI_FORCE_MOCK=true forces MockProvider (tests).
    Raises ProviderError('NOT_CONFIGURED') if a real provider has no key."""
    cfg = app_config.get().get("ai", {})
    if name in (None, "", "default"):
        name = cfg.get("default_provider", "openai")
    if name == "mock":
        return MockProvider()
    if _force_mock() and allow_mock:
        return MockProvider()
    if not cfg.get("enabled", True):
        raise ProviderError("AI_DISABLED", "AI is disabled in settings")
    if name not in _CLASSES:
        raise ProviderError("UNKNOWN_PROVIDER", name)
    pconf = cfg.get("providers", {}).get(name, {})
    key = await secrets_store.get_secret(f"ai_{name}")
    if not key:
        raise ProviderError("NOT_CONFIGURED", f"{name} API key is not configured")
    model = pconf.get("model") or ""
    return _CLASSES[name](key, model)


async def provider_status():
    """Non-secret status for every provider (key_configured booleans + model + enabled)."""
    cfg = app_config.get().get("ai", {})
    out = {}
    for p in PROVIDERS:
        pc = cfg.get("providers", {}).get(p, {})
        out[p] = {"enabled": bool(pc.get("enabled")), "model": pc.get("model", ""),
                  "key_configured": await secrets_store.is_configured(f"ai_{p}")}
    return out
