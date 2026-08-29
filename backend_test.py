#!/usr/bin/env python3
"""Phase-6 Secure Configuration Backend Testing
Tests secure Shopify/AI config endpoints, secret non-disclosure, prompt manager, role gating.
"""
import requests
import json
import time

# Base URL from frontend/.env
BASE_URL = "https://admin-demo-cleanup.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "msabhadiya007@gmail.com"
ADMIN_PASSWORD = "Admin@12345"
VIEWER_EMAIL = "viewer@urbandotted.com"
VIEWER_PASSWORD = "Viewer@12345"

# Test state
admin_token = None
viewer_token = None
test_product_id = None

def log(msg):
    print(f"  {msg}")

def login(email, password):
    """Login and return JWT token"""
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise Exception(f"Login failed for {email}: {r.status_code} {r.text}")
    return r.json()["token"]

def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def test_1_get_config_structure():
    """TEST 1: GET /api/settings/config returns correct structure with NO secrets"""
    log("TEST 1: GET /api/settings/config structure + secret non-disclosure")
    r = requests.get(f"{BASE_URL}/settings/config", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    
    # Check top-level keys
    assert "secrets_available" in data, "Missing secrets_available"
    assert "shopify" in data, "Missing shopify"
    assert "ai" in data, "Missing ai"
    assert "usage_today" in data, "Missing usage_today"
    
    # Check shopify structure
    shopify = data["shopify"]
    required_shopify = ["mode", "mock_mode", "domain", "api_version", "connected", 
                        "config_error", "token_configured", "last_sync", "last_connection"]
    for key in required_shopify:
        assert key in shopify, f"Missing shopify.{key}"
    
    # Check AI structure
    ai = data["ai"]
    assert "enabled" in ai, "Missing ai.enabled"
    assert "default_provider" in ai, "Missing ai.default_provider"
    assert "providers" in ai, "Missing ai.providers"
    assert "usage_today" in data, "Missing usage_today"
    
    # Check AI providers
    providers = ai["providers"]
    for p in ["openai", "anthropic", "gemini", "deepseek"]:
        assert p in providers, f"Missing provider {p}"
        assert "enabled" in providers[p], f"Missing {p}.enabled"
        assert "model" in providers[p], f"Missing {p}.model"
        assert "key_configured" in providers[p], f"Missing {p}.key_configured"
    
    # CRITICAL: Verify NO secrets in response
    response_text = json.dumps(data)
    forbidden_patterns = ["token", "api_key", "shpat_", "sk-", "Bearer"]
    # Allow "token_configured" and "key_configured" but not actual token values
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Shopify token exposed"
    assert "sk-" not in response_text, "SECURITY VIOLATION: API key exposed"
    
    log(f"✅ PASS: Config structure correct, secrets_available={data['secrets_available']}")
    log(f"   Shopify: mode={shopify['mode']}, mock={shopify['mock_mode']}, token_configured={shopify['token_configured']}")
    log(f"   AI: default={ai['default_provider']}, providers={list(providers.keys())}")
    return data

def test_2_secret_write_only():
    """TEST 2: Secret write-only + non-disclosure (PUT shopify token, PUT AI keys)"""
    log("TEST 2: Secret write-only + non-disclosure")
    
    # 2a. PUT Shopify token
    log("  2a. PUT /api/settings/shopify with token")
    payload = {
        "domain": "unittest.myshopify.com",
        "mode": "demo",
        "mock_mode": True,
        "token": "shpat_TESTSECRET_ABC123"
    }
    r = requests.put(f"{BASE_URL}/settings/shopify", headers=headers(admin_token), json=payload)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    
    shopify_resp = r.json()
    # Response must NOT contain the token
    assert "shpat_TESTSECRET_ABC123" not in json.dumps(shopify_resp), "SECURITY VIOLATION: Token echoed in response"
    assert shopify_resp.get("token_configured") == True, "token_configured should be true"
    log(f"  ✅ Shopify token stored, token_configured={shopify_resp['token_configured']}, NOT echoed")
    
    # 2b. PUT OpenAI key
    log("  2b. PUT /api/settings/ai/openai with api_key")
    payload = {
        "api_key": "sk-TESTKEY-OPENAI-XYZ",
        "model": "gpt-5.4",
        "enabled": True
    }
    r = requests.put(f"{BASE_URL}/settings/ai/openai", headers=headers(admin_token), json=payload)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    
    ai_resp = r.json()
    # Response must NOT contain the key
    assert "sk-TESTKEY-OPENAI-XYZ" not in json.dumps(ai_resp), "SECURITY VIOLATION: API key echoed in response"
    assert ai_resp["status"]["key_configured"] == True, "key_configured should be true"
    log(f"  ✅ OpenAI key stored, key_configured={ai_resp['status']['key_configured']}, NOT echoed")
    
    # 2c. GET /api/settings/config again - secrets must NOT appear
    log("  2c. GET /api/settings/config - verify secrets NOT in response")
    r = requests.get(f"{BASE_URL}/settings/config", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    config_text = json.dumps(r.json())
    assert "shpat_TESTSECRET_ABC123" not in config_text, "SECURITY VIOLATION: Shopify token in config response"
    assert "sk-TESTKEY-OPENAI-XYZ" not in config_text, "SECURITY VIOLATION: OpenAI key in config response"
    log(f"  ✅ Secrets NOT disclosed in GET /api/settings/config")

def test_3_per_provider_test_connection():
    """TEST 3: Per-provider test connection"""
    log("TEST 3: Per-provider test connection")
    
    # 3a. Test Anthropic (no key configured)
    log("  3a. GET /api/settings/ai/anthropic/test (no key)")
    r = requests.get(f"{BASE_URL}/settings/ai/anthropic/test", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["connected"] == False, "Should be not connected"
    assert data["status"] == "not_configured", f"Expected not_configured, got {data['status']}"
    log(f"  ✅ Anthropic (no key): connected={data['connected']}, status={data['status']}")
    
    # 3b. Test OpenAI (fake key from test 2)
    log("  3b. GET /api/settings/ai/openai/test (fake key)")
    r = requests.get(f"{BASE_URL}/settings/ai/openai/test", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["connected"] == False, "Should be not connected with fake key"
    assert data["status"] in ["invalid_api_key", "error"], f"Expected invalid_api_key or error, got {data['status']}"
    # Must NOT leak the key
    assert "sk-TESTKEY-OPENAI-XYZ" not in json.dumps(data), "SECURITY VIOLATION: Key leaked in test response"
    log(f"  ✅ OpenAI (fake key): connected={data['connected']}, status={data['status']}, key NOT leaked")
    
    # 3c. Test invalid provider
    log("  3c. GET /api/settings/ai/foobar/test (invalid provider)")
    r = requests.get(f"{BASE_URL}/settings/ai/foobar/test", headers=headers(admin_token))
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
    log(f"  ✅ Invalid provider returns 404")

def test_4_default_provider_validation():
    """TEST 4: Default provider + validation"""
    log("TEST 4: Default provider validation")
    
    # 4a. Set valid default provider
    log("  4a. PUT /api/settings/ai with default_provider=gemini")
    r = requests.put(f"{BASE_URL}/settings/ai", headers=headers(admin_token), 
                     json={"default_provider": "gemini"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    log(f"  ✅ Set default_provider=gemini")
    
    # Verify in config
    r = requests.get(f"{BASE_URL}/settings/config", headers=headers(admin_token))
    assert r.status_code == 200
    assert r.json()["ai"]["default_provider"] == "gemini", "default_provider not updated"
    log(f"  ✅ Verified default_provider=gemini in config")
    
    # 4b. Try invalid default provider
    log("  4b. PUT /api/settings/ai with default_provider=notreal")
    r = requests.put(f"{BASE_URL}/settings/ai", headers=headers(admin_token), 
                     json={"default_provider": "notreal"})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    log(f"  ✅ Invalid default_provider rejected with 400")
    
    # 4c. Try invalid mode
    log("  4c. PUT /api/settings/shopify with mode=sideways")
    r = requests.put(f"{BASE_URL}/settings/shopify", headers=headers(admin_token), 
                     json={"mode": "sideways"})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    log(f"  ✅ Invalid mode rejected with 400")
    
    # 4d. Try invalid provider endpoint
    log("  4d. PUT /api/settings/ai/foobar")
    r = requests.put(f"{BASE_URL}/settings/ai/foobar", headers=headers(admin_token), 
                     json={"model": "x"})
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
    log(f"  ✅ Invalid provider endpoint returns 404")

def test_5_live_safety():
    """TEST 5: LIVE safety (must revert after!)"""
    log("TEST 5: LIVE safety (will revert)")
    
    # 5a. Delete token first
    log("  5a. DELETE /api/settings/shopify/token")
    r = requests.delete(f"{BASE_URL}/settings/shopify/token", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    log(f"  ✅ Token deleted")
    
    # 5b. Switch to LIVE mode
    log("  5b. PUT /api/settings/shopify mode=live, mock_mode=false")
    r = requests.put(f"{BASE_URL}/settings/shopify", headers=headers(admin_token), 
                     json={"mode": "live", "mock_mode": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    
    data = r.json()
    assert data["mode"] == "live", f"Expected mode=live, got {data['mode']}"
    assert data["data_source"] == "live", f"Expected data_source=live, got {data['data_source']}"
    assert data["connected"] == False, "Should be not connected without token"
    assert data["config_error"] != "", "config_error should be non-empty"
    log(f"  ✅ LIVE mode: mode={data['mode']}, data_source={data['data_source']}, connected={data['connected']}")
    log(f"     config_error='{data['config_error']}'")
    
    # 5c. Revert to DEMO
    log("  5c. REVERT to demo+mock")
    r = requests.put(f"{BASE_URL}/settings/shopify", headers=headers(admin_token), 
                     json={"mode": "demo", "mock_mode": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    assert data["mode"] == "demo", "Failed to revert to demo"
    # config_error can be None or "" in demo mode (both mean no error)
    assert data["config_error"] in (None, ""), f"config_error should be cleared, got '{data['config_error']}'"
    log(f"  ✅ Reverted to DEMO: mode={data['mode']}, config_error cleared")

def test_6_prompt_manager():
    """TEST 6: Prompt manager CRUD"""
    log("TEST 6: Prompt manager")
    
    # 6a. GET /api/settings/prompts
    log("  6a. GET /api/settings/prompts")
    r = requests.get(f"{BASE_URL}/settings/prompts", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    for ptype in ["product_seo", "collection_seo", "quality_review"]:
        assert ptype in data, f"Missing prompt type {ptype}"
        p = data[ptype]
        assert "active_version" in p, f"Missing {ptype}.active_version"
        assert "text" in p, f"Missing {ptype}.text"
        assert "versions" in p, f"Missing {ptype}.versions"
        assert "is_default" in p, f"Missing {ptype}.is_default"
    log(f"  ✅ All 3 prompt types present with correct structure")
    
    # Store original state
    original_product_seo = data["product_seo"]
    original_version = original_product_seo["active_version"]
    
    # 6b. PUT custom prompt (valid)
    log("  6b. PUT /api/settings/prompts/product_seo (custom 60+ char prompt)")
    custom_prompt = "This is a custom SEO prompt for testing purposes. It must be at least 60 characters long to pass validation and return JSON only."
    r = requests.put(f"{BASE_URL}/settings/prompts/product_seo", headers=headers(admin_token), 
                     json={"text": custom_prompt})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    
    result = r.json()
    assert result["ok"] == True, "Expected ok=true"
    assert result["version"] > original_version, f"Version should increment, got {result['version']}"
    log(f"  ✅ Custom prompt saved, version incremented to {result['version']}")
    
    # 6c. Verify in GET
    log("  6c. GET /api/settings/prompts - verify custom prompt active")
    r = requests.get(f"{BASE_URL}/settings/prompts", headers=headers(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert data["product_seo"]["is_default"] == False, "Should not be default"
    assert data["product_seo"]["active_version"] > original_version, "Version should be higher"
    assert custom_prompt in data["product_seo"]["text"], "Custom prompt not active"
    log(f"  ✅ Custom prompt active, is_default=false, version={data['product_seo']['active_version']}")
    
    # 6d. PUT too short (validation)
    log("  6d. PUT /api/settings/prompts/product_seo (too short)")
    r = requests.put(f"{BASE_URL}/settings/prompts/product_seo", headers=headers(admin_token), 
                     json={"text": "x"})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    log(f"  ✅ Too-short prompt rejected with 400")
    
    # 6e. POST restore-default
    log("  6e. POST /api/settings/prompts/product_seo/restore-default")
    r = requests.post(f"{BASE_URL}/settings/prompts/product_seo/restore-default", 
                      headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    log(f"  ✅ Restore default successful")
    
    # 6f. Verify default restored
    log("  6f. GET /api/settings/prompts - verify is_default=true")
    r = requests.get(f"{BASE_URL}/settings/prompts", headers=headers(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert data["product_seo"]["is_default"] == True, "Should be default again"
    log(f"  ✅ Default restored, is_default=true")
    
    # 6g. Invalid prompt type
    log("  6g. GET /api/settings/prompts/badtype/history")
    r = requests.get(f"{BASE_URL}/settings/prompts/badtype/history", headers=headers(admin_token))
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
    log(f"  ✅ Invalid prompt type returns 404")

def test_7_role_gating_viewer():
    """TEST 7: Role gating - viewer must get 403 on all settings endpoints"""
    log("TEST 7: Role gating (viewer)")
    
    endpoints = [
        ("GET", "/settings/config", None),
        ("PUT", "/settings/shopify", {"mode": "demo"}),
        ("PUT", "/settings/ai/openai", {"model": "gpt-5.4"}),
        ("GET", "/settings/ai/openai/test", None),
        ("GET", "/settings/prompts", None),
        ("PUT", "/settings/prompts/product_seo", {"text": "x" * 60}),
    ]
    
    for method, path, payload in endpoints:
        log(f"  {method} {path}")
        if method == "GET":
            r = requests.get(f"{BASE_URL}{path}", headers=headers(viewer_token))
        elif method == "PUT":
            r = requests.put(f"{BASE_URL}{path}", headers=headers(viewer_token), json=payload)
        elif method == "POST":
            r = requests.post(f"{BASE_URL}{path}", headers=headers(viewer_token), json=payload or {})
        
        assert r.status_code == 403, f"Expected 403 for viewer on {method} {path}, got {r.status_code}"
    
    log(f"  ✅ All {len(endpoints)} endpoints correctly return 403 for viewer")

def test_8_regression_seo_only_allowlist():
    """TEST 8: Regression - SEO-only allowlist still enforced"""
    log("TEST 8: Regression - SEO-only allowlist")
    
    # Get a demo product
    log("  8a. GET /api/products (get test product)")
    r = requests.get(f"{BASE_URL}/products?page=1&page_size=1", 
                     headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    items = data.get("items", [])
    
    # If no products, seed demo data first
    if len(items) == 0:
        log("  No products found, seeding demo data...")
        r = requests.post(f"{BASE_URL}/sync", headers=headers(admin_token))
        assert r.status_code == 200, f"Sync failed: {r.status_code}"
        time.sleep(5)  # Wait for sync
        
        r = requests.get(f"{BASE_URL}/products?page=1&page_size=1", 
                         headers=headers(admin_token))
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        items = r.json().get("items", [])
    
    assert len(items) > 0, "No products found even after sync"
    
    global test_product_id
    test_product_id = items[0]["id"]
    log(f"  ✅ Got test product: {test_product_id}")
    
    # 8b. PATCH with forbidden field (price)
    log("  8b. PATCH /api/products/{id}/seo-draft with forbidden field (price)")
    r = requests.patch(f"{BASE_URL}/products/{test_product_id}/seo-draft", 
                       headers=headers(admin_token), 
                       json={"price": "1.00"})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    assert "NON_SEO_FIELD_WRITE_DENIED" in r.text, "Expected NON_SEO_FIELD_WRITE_DENIED error"
    log(f"  ✅ Forbidden field (price) rejected with 403 NON_SEO_FIELD_WRITE_DENIED")
    
    # 8c. POST publish-seo with forbidden field (vendor)
    log("  8c. POST /api/products/{id}/publish-seo with forbidden field (vendor)")
    r = requests.post(f"{BASE_URL}/products/{test_product_id}/publish-seo", 
                      headers=headers(admin_token), 
                      json={"vendor": "x"})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    assert "NON_SEO_FIELD_WRITE_DENIED" in r.text, "Expected NON_SEO_FIELD_WRITE_DENIED error"
    log(f"  ✅ Forbidden field (vendor) rejected with 403 NON_SEO_FIELD_WRITE_DENIED")
    
    # 8d. PATCH with SEO-only fields (should work)
    log("  8d. PATCH /api/products/{id}/seo-draft with SEO-only fields")
    r = requests.patch(f"{BASE_URL}/products/{test_product_id}/seo-draft", 
                       headers=headers(admin_token), 
                       json={"seo_title": "Test SEO Title", "meta_description": "Test meta description"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    log(f"  ✅ SEO-only draft PATCH works (200)")

def revert_all_config():
    """CRITICAL: Revert all config to DEMO state"""
    log("REVERTING ALL CONFIG TO DEMO STATE")
    
    # 1. Revert Shopify to demo+mock
    log("  1. PUT /api/settings/shopify (demo+mock)")
    r = requests.put(f"{BASE_URL}/settings/shopify", headers=headers(admin_token), 
                     json={"mode": "demo", "mock_mode": True})
    assert r.status_code == 200, f"Revert shopify failed: {r.status_code}"
    
    # 2. Delete Shopify token
    log("  2. DELETE /api/settings/shopify/token")
    r = requests.delete(f"{BASE_URL}/settings/shopify/token", headers=headers(admin_token))
    assert r.status_code == 200, f"Delete token failed: {r.status_code}"
    
    # 3. Delete all AI provider keys and disable
    for provider in ["openai", "anthropic", "gemini", "deepseek"]:
        log(f"  3.{provider}. DELETE /api/settings/ai/{provider}/key")
        r = requests.delete(f"{BASE_URL}/settings/ai/{provider}/key", headers=headers(admin_token))
        assert r.status_code == 200, f"Delete {provider} key failed: {r.status_code}"
        
        log(f"  3.{provider}. PUT /api/settings/ai/{provider} (enabled=false)")
        r = requests.put(f"{BASE_URL}/settings/ai/{provider}", headers=headers(admin_token), 
                         json={"enabled": False})
        assert r.status_code == 200, f"Disable {provider} failed: {r.status_code}"
    
    # 4. Reset default provider to openai
    log("  4. PUT /api/settings/ai (default_provider=openai)")
    r = requests.put(f"{BASE_URL}/settings/ai", headers=headers(admin_token), 
                     json={"default_provider": "openai"})
    assert r.status_code == 200, f"Reset default provider failed: {r.status_code}"
    
    log("✅ ALL CONFIG REVERTED TO DEMO STATE")

def main():
    global admin_token, viewer_token
    
    print("\n" + "="*80)
    print("PHASE-6 SECURE CONFIGURATION BACKEND TESTING")
    print("="*80 + "\n")
    
    # Login
    print("SETUP: Logging in...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    viewer_token = login(VIEWER_EMAIL, VIEWER_PASSWORD)
    print(f"✅ Admin logged in: {ADMIN_EMAIL}")
    print(f"✅ Viewer logged in: {VIEWER_EMAIL}\n")
    
    # Run tests
    tests = [
        test_1_get_config_structure,
        test_2_secret_write_only,
        test_3_per_provider_test_connection,
        test_4_default_provider_validation,
        test_5_live_safety,
        test_6_prompt_manager,
        test_7_role_gating_viewer,
        test_8_regression_seo_only_allowlist,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            print(f"\n{test_func.__name__.replace('_', ' ').upper()}")
            print("-" * 80)
            test_func()
            passed += 1
            print(f"✅ {test_func.__name__} PASSED\n")
        except AssertionError as e:
            failed += 1
            print(f"❌ {test_func.__name__} FAILED: {e}\n")
        except Exception as e:
            failed += 1
            print(f"❌ {test_func.__name__} ERROR: {e}\n")
    
    # CRITICAL: Revert config
    print("\n" + "="*80)
    try:
        revert_all_config()
    except Exception as e:
        print(f"❌ CONFIG REVERT FAILED: {e}")
        print("⚠️  WARNING: App may be in LIVE mode or have test secrets!")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"PASSED: {passed}/{len(tests)}")
    print(f"FAILED: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED - Phase-6 secure configuration is working correctly")
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
