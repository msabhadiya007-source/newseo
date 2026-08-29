"""Phase 6 config/secret security tests.

Proves:
- Shopify token + all 4 AI provider keys are ENCRYPTED at rest (never plaintext in Mongo).
- Secrets are NEVER returned by any GET (only *_configured booleans).
- Provider model/enabled config + default provider work.
- Prompt manager versioning + restore-default work.
- Role gating: viewer is denied all secret/config/prompt endpoints (403).
- LIVE data mode with missing credentials surfaces config_error and does NOT fall back to demo.

Self-cleaning: removes any secrets/config it creates and restores DEMO mode.
"""
import re
import uuid
import requests
from pymongo import MongoClient
from dotenv import dotenv_values
from conftest import API

_env = dotenv_values("/app/backend/.env")
_db = MongoClient(_env["MONGO_URL"])[_env["DB_NAME"]]

FAKE = {
    "shopify_token": "shpat_UNITTEST_" + uuid.uuid4().hex,
    "ai_openai": "sk-openai-UNITTEST-" + uuid.uuid4().hex,
    "ai_anthropic": "sk-ant-UNITTEST-" + uuid.uuid4().hex,
    "ai_gemini": "AIza-UNITTEST-" + uuid.uuid4().hex,
    "ai_deepseek": "sk-ds-UNITTEST-" + uuid.uuid4().hex,
}


def _restore_demo(client):
    client.put(f"{API}/settings/shopify", json={"mode": "demo", "mock_mode": True})
    client.delete(f"{API}/settings/shopify/token")
    for p in ("openai", "anthropic", "gemini", "deepseek"):
        client.delete(f"{API}/settings/ai/{p}/key")
        client.put(f"{API}/settings/ai/{p}", json={"enabled": False})


class TestSecretsSecurity:
    def test_encrypted_at_rest_and_never_returned(self, client):
        # store all secrets via API
        assert client.put(f"{API}/settings/shopify",
                          json={"domain": "unittest.myshopify.com", "mode": "demo",
                                "mock_mode": True, "token": FAKE["shopify_token"]}).status_code == 200
        for prov, key in (("openai", FAKE["ai_openai"]), ("anthropic", FAKE["ai_anthropic"]),
                          ("gemini", FAKE["ai_gemini"]), ("deepseek", FAKE["ai_deepseek"])):
            r = client.put(f"{API}/settings/ai/{prov}", json={"api_key": key, "model": "m-x", "enabled": True})
            assert r.status_code == 200
            assert r.json()["status"]["key_configured"] is True
            # response must NOT echo the key
            assert key not in r.text

        # (1) encryption at rest: ciphertext present, plaintext absent, Fernet prefix
        for name, plaintext in FAKE.items():
            doc = _db.app_secrets.find_one({"id": name})
            assert doc is not None, f"secret {name} not stored"
            ct = doc.get("ciphertext", "")
            assert plaintext not in ct, f"{name} stored in PLAINTEXT!"
            assert ct.startswith("gAAAAA"), f"{name} not Fernet-encrypted"

        # (2) no secret leaks through GET /settings/config
        cfg = client.get(f"{API}/settings/config")
        assert cfg.status_code == 200
        body = cfg.text
        for plaintext in FAKE.values():
            assert plaintext not in body
        j = cfg.json()
        # only booleans exposed, never 'token'/'api_key' fields
        assert "token" not in j["shopify"]
        assert j["shopify"]["token_configured"] is True
        for p in ("openai", "anthropic", "gemini", "deepseek"):
            assert "api_key" not in j["ai"]["providers"][p]
            assert j["ai"]["providers"][p]["key_configured"] is True

        # (3) no secret leaks through GET /settings either
        s = client.get(f"{API}/settings").text
        for plaintext in FAKE.values():
            assert plaintext not in s

        _restore_demo(client)

    def test_default_provider_and_models(self, client):
        client.put(f"{API}/settings/ai/gemini", json={"api_key": FAKE["ai_gemini"], "model": "gemini-x", "enabled": True})
        assert client.put(f"{API}/settings/ai", json={"default_provider": "gemini"}).status_code == 200
        cfg = client.get(f"{API}/settings/config").json()
        assert cfg["ai"]["default_provider"] == "gemini"
        assert cfg["ai"]["providers"]["gemini"]["model"] == "gemini-x"
        # invalid provider rejected
        assert client.put(f"{API}/settings/ai", json={"default_provider": "notreal"}).status_code == 400
        _restore_demo(client)
        client.put(f"{API}/settings/ai", json={"default_provider": "openai"})

    def test_unknown_provider_and_bad_mode(self, client):
        assert client.put(f"{API}/settings/ai/foobar", json={"model": "x"}).status_code == 404
        assert client.get(f"{API}/settings/ai/foobar/test").status_code == 404
        assert client.put(f"{API}/settings/shopify", json={"mode": "sideways"}).status_code == 400

    def test_live_mode_config_error_no_fallback(self, client):
        try:
            client.delete(f"{API}/settings/shopify/token")
            r = client.put(f"{API}/settings/shopify", json={"mode": "live", "mock_mode": False})
            assert r.status_code == 200
            body = r.json()
            assert body["mode"] == "live"
            assert body["data_source"] == "live"      # did NOT fall back to demo
            assert body["config_error"]                # safe error surfaced
            assert body["connected"] is False
        finally:
            _restore_demo(client)

    def test_prompt_versioning_and_restore(self, client):
        before = client.get(f"{API}/settings/prompts").json()["product_seo"]["active_version"]
        new_text = "UNITTEST custom product SEO prompt. Use only verified facts. Return JSON only. " + uuid.uuid4().hex
        r = client.put(f"{API}/settings/prompts/product_seo", json={"text": new_text})
        assert r.status_code == 200 and r.json()["version"] == before + 1
        active = client.get(f"{API}/settings/prompts").json()["product_seo"]
        assert active["active_version"] == before + 1 and active["is_default"] is False
        # too-short rejected
        assert client.put(f"{API}/settings/prompts/product_seo", json={"text": "x"}).status_code == 400
        # restore default
        rd = client.post(f"{API}/settings/prompts/product_seo/restore-default")
        assert rd.status_code == 200
        assert client.get(f"{API}/settings/prompts").json()["product_seo"]["is_default"] is True

    def test_viewer_denied_everywhere(self, admin_token):
        email = f"viewer_{uuid.uuid4().hex[:6]}@test.com"
        requests.post(f"{API}/auth/register",
                      headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                      json={"email": email, "password": "Viewer@123", "name": "V", "role": "viewer"})
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "Viewer@123"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        assert requests.get(f"{API}/settings/config", headers=h).status_code == 403
        assert requests.put(f"{API}/settings/shopify", headers=h, json={"mode": "demo"}).status_code == 403
        assert requests.put(f"{API}/settings/ai/openai", headers=h, json={"api_key": "x"}).status_code == 403
        assert requests.get(f"{API}/settings/ai/openai/test", headers=h).status_code == 403
        assert requests.get(f"{API}/settings/prompts", headers=h).status_code == 403
        assert requests.put(f"{API}/settings/prompts/product_seo", headers=h, json={"text": "y" * 30}).status_code == 403
