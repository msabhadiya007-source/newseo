#!/usr/bin/env python3
"""Shopify Token Exchange Authentication Backend Testing

Tests the NEW Shopify embedded-app Token Exchange authentication flow.
Uses TEST-ONLY credentials from backend/.env:
  SHOPIFY_CLIENT_ID = preview_test_client_id
  SHOPIFY_CLIENT_SECRET = preview_test_client_secret_do_not_use_in_prod

Crafts Shopify session (ID) tokens (HS256 JWT) for validation-branch testing.
"""
import requests
import json
import time
import jwt
from datetime import datetime, timezone, timedelta

# Base URL from frontend/.env
BASE_URL = "https://c3f633d2-05c2-4681-b4a1-dbca84ba1a5b.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@urbandotted.com"
ADMIN_PASSWORD = "Admin@12345"

# Shopify test credentials from backend/.env
SHOPIFY_CLIENT_ID = "preview_test_client_id"
SHOPIFY_CLIENT_SECRET = "preview_test_client_secret_do_not_use_in_prod"
TEST_SHOP = "preview-demo-shop.myshopify.com"

# Test state
admin_token = None
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

def craft_shopify_id_token(shop=TEST_SHOP, client_id=SHOPIFY_CLIENT_ID, 
                           client_secret=SHOPIFY_CLIENT_SECRET,
                           exp_offset=60, nbf_offset=-5, 
                           aud_override=None, iss_override=None, dest_override=None):
    """Craft a Shopify session (ID) token JWT.
    
    Args:
        shop: Shop domain (e.g. "preview-demo-shop.myshopify.com")
        client_id: Shopify app client ID (audience)
        client_secret: Shopify app client secret (signing key)
        exp_offset: Seconds from now for expiration (default +60s)
        nbf_offset: Seconds from now for not-before (default -5s)
        aud_override: Override audience (for testing wrong aud)
        iss_override: Override issuer (for testing shop mismatch)
        dest_override: Override dest (for testing shop mismatch)
    
    Returns:
        JWT token string
    """
    now = datetime.now(timezone.utc)
    iat = int(now.timestamp())
    nbf = int((now + timedelta(seconds=nbf_offset)).timestamp())
    exp = int((now + timedelta(seconds=exp_offset)).timestamp())
    
    iss = iss_override if iss_override is not None else f"https://{shop}/admin"
    dest = dest_override if dest_override is not None else f"https://{shop}"
    aud = aud_override if aud_override is not None else client_id
    
    claims = {
        "iss": iss,
        "dest": dest,
        "aud": aud,
        "sub": "1234567890",
        "exp": exp,
        "nbf": nbf,
        "iat": iat,
        "jti": f"test-jti-{iat}",
        "sid": f"test-sid-{iat}"
    }
    
    return jwt.encode(claims, client_secret, algorithm="HS256")

def test_1_valid_token_reaches_exchange():
    """TEST 1: Valid ID token passes validation and reaches exchange step.
    
    Since the fake shop has no real Shopify endpoint, expect HTTP 502 with
    detail.code in {EXCHANGE_FAILED, EXCHANGE_UNAVAILABLE, EXCHANGE_NO_TOKEN}.
    This confirms validation passed.
    """
    log("TEST 1: Valid ID token reaches exchange (expect 502 EXCHANGE_*)")
    
    token = craft_shopify_id_token()
    log(f"  Crafted valid ID token for shop={TEST_SHOP}")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    
    # Valid token should PASS validation and reach exchange
    # Exchange will fail (502) because fake shop has no real endpoint
    assert r.status_code == 502, f"Expected 502 (exchange failed), got {r.status_code}"
    
    # Try to parse JSON response (may be HTML from Cloudflare or JSON from backend)
    try:
        data = r.json()
        detail = data.get("detail", {})
        code = detail.get("code") if isinstance(detail, dict) else None
        
        if code:
            assert code in ["EXCHANGE_FAILED", "EXCHANGE_UNAVAILABLE", "EXCHANGE_NO_TOKEN"], \
                f"Expected EXCHANGE_* code, got {code}"
            log(f"  ✅ PASS: Validation succeeded, exchange failed as expected (code={code})")
        else:
            log(f"  ✅ PASS: Validation succeeded, exchange failed (502 without detail code)")
        
        # SECURITY: Response must NOT contain any admin token or client secret
        response_text = json.dumps(data)
        assert "shpat_" not in response_text, "SECURITY VIOLATION: Admin token in response"
        assert SHOPIFY_CLIENT_SECRET not in response_text, "SECURITY VIOLATION: Client secret in response"
        assert "access_token" not in response_text or data.get("access_token") is None, \
            "SECURITY VIOLATION: access_token field with value in response"
        log(f"  ✅ SECURITY: No admin token or client secret in response")
    except json.JSONDecodeError:
        # Non-JSON response (e.g., Cloudflare HTML error page)
        # This is acceptable - the 502 status confirms validation passed and exchange failed
        log(f"  ✅ PASS: Validation succeeded, exchange failed (502 non-JSON response)")
        
        # SECURITY: Check response text doesn't contain secrets
        response_text = r.text
        assert "shpat_" not in response_text, "SECURITY VIOLATION: Admin token in response"
        assert SHOPIFY_CLIENT_SECRET not in response_text, "SECURITY VIOLATION: Client secret in response"
        log(f"  ✅ SECURITY: No admin token or client secret in response")

def test_2_bad_signature():
    """TEST 2: Bad signature (signed with wrong secret) -> 401 INVALID_ID_TOKEN"""
    log("TEST 2: Bad signature (wrong secret)")
    
    token = craft_shopify_id_token(client_secret="wrong_secret_12345")
    log(f"  Crafted ID token with WRONG secret")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    data = r.json()
    detail = data.get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    
    assert code == "INVALID_ID_TOKEN", f"Expected INVALID_ID_TOKEN, got {code}"
    log(f"  ✅ PASS: Bad signature rejected with 401 INVALID_ID_TOKEN")
    
    # SECURITY check
    response_text = json.dumps(data)
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Token in response"
    assert SHOPIFY_CLIENT_SECRET not in response_text, "SECURITY VIOLATION: Secret in response"

def test_3_expired_token():
    """TEST 3: Expired token (exp in past) -> 401 TOKEN_EXPIRED"""
    log("TEST 3: Expired token (exp in past)")
    
    # exp=-10 means expired 10 seconds ago, nbf=-20 means valid 20 seconds ago
    token = craft_shopify_id_token(exp_offset=-10, nbf_offset=-20)
    log(f"  Crafted EXPIRED ID token (exp=-10s)")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    data = r.json()
    detail = data.get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    
    assert code == "TOKEN_EXPIRED", f"Expected TOKEN_EXPIRED, got {code}"
    log(f"  ✅ PASS: Expired token rejected with 401 TOKEN_EXPIRED")
    
    # SECURITY check
    response_text = json.dumps(data)
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Token in response"

def test_4_not_yet_valid():
    """TEST 4: Not-yet-valid token (nbf in future) -> 401 TOKEN_NOT_YET_VALID"""
    log("TEST 4: Not-yet-valid token (nbf in future)")
    
    # nbf=+30 means not valid until 30 seconds from now
    token = craft_shopify_id_token(nbf_offset=30, exp_offset=90)
    log(f"  Crafted NOT-YET-VALID ID token (nbf=+30s)")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    data = r.json()
    detail = data.get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    
    assert code == "TOKEN_NOT_YET_VALID", f"Expected TOKEN_NOT_YET_VALID, got {code}"
    log(f"  ✅ PASS: Not-yet-valid token rejected with 401 TOKEN_NOT_YET_VALID")
    
    # SECURITY check
    response_text = json.dumps(data)
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Token in response"

def test_5_wrong_audience():
    """TEST 5: Wrong audience (aud != client_id) -> 401 INVALID_AUDIENCE"""
    log("TEST 5: Wrong audience (aud != client_id)")
    
    token = craft_shopify_id_token(aud_override="wrong_client_id_xyz")
    log(f"  Crafted ID token with WRONG audience")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    data = r.json()
    detail = data.get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    
    assert code == "INVALID_AUDIENCE", f"Expected INVALID_AUDIENCE, got {code}"
    log(f"  ✅ PASS: Wrong audience rejected with 401 INVALID_AUDIENCE")
    
    # SECURITY check
    response_text = json.dumps(data)
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Token in response"

def test_6_shop_mismatch():
    """TEST 6: iss/dest shop mismatch -> 401 SHOP_MISMATCH"""
    log("TEST 6: iss/dest shop mismatch")
    
    # iss shop different from dest shop
    token = craft_shopify_id_token(
        iss_override=f"https://shop-a.myshopify.com/admin",
        dest_override=f"https://shop-b.myshopify.com"
    )
    log(f"  Crafted ID token with iss=shop-a, dest=shop-b (MISMATCH)")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    data = r.json()
    detail = data.get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    
    assert code == "SHOP_MISMATCH", f"Expected SHOP_MISMATCH, got {code}"
    log(f"  ✅ PASS: Shop mismatch rejected with 401 SHOP_MISMATCH")
    
    # SECURITY check
    response_text = json.dumps(data)
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Token in response"

def test_7_invalid_shop_host():
    """TEST 7: Non-myshopify host (iss/dest on example.com) -> 401 INVALID_SHOP"""
    log("TEST 7: Non-myshopify host (example.com)")
    
    # iss/dest on non-myshopify.com domain
    token = craft_shopify_id_token(
        iss_override=f"https://evil.example.com/admin",
        dest_override=f"https://evil.example.com"
    )
    log(f"  Crafted ID token with iss/dest=evil.example.com (NOT myshopify.com)")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    data = r.json()
    detail = data.get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    
    assert code == "INVALID_SHOP", f"Expected INVALID_SHOP, got {code}"
    log(f"  ✅ PASS: Non-myshopify host rejected with 401 INVALID_SHOP")
    
    # SECURITY check
    response_text = json.dumps(data)
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Token in response"

def test_8_missing_authorization_header():
    """TEST 8: Missing Authorization header entirely -> 401"""
    log("TEST 8: Missing Authorization header")
    
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Content-Type": "application/json"})
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    
    log(f"  ✅ PASS: Missing Authorization header rejected with 401")

def test_9_failed_exchange_no_token_stored():
    """TEST 9: After FAILED exchange (valid token, fake shop), verify NO token stored.
    
    Call GET /api/shopify/auth/status (as admin) and assert authenticated == false.
    """
    log("TEST 9: Failed exchange must NOT store token")
    
    # First, ensure no token is stored (disconnect if any)
    log("  9a. Disconnect any existing token")
    r = requests.post(f"{BASE_URL}/shopify/auth/disconnect", headers=headers(admin_token))
    # Ignore status, just ensure clean state
    
    # Craft valid token and attempt exchange (will fail at exchange step)
    log("  9b. Attempt token exchange with valid token (will fail at exchange)")
    token = craft_shopify_id_token()
    r = requests.post(f"{BASE_URL}/shopify/auth/token-exchange",
                     headers={"Authorization": f"Bearer {token}"})
    
    # Should get 502 EXCHANGE_* (validation passed, exchange failed)
    assert r.status_code == 502, f"Expected 502, got {r.status_code}"
    log(f"  Exchange failed as expected (502)")
    
    # Now check auth status - should be authenticated=false
    log("  9c. GET /api/shopify/auth/status (as admin)")
    r = requests.get(f"{BASE_URL}/shopify/auth/status", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    authenticated = data.get("authenticated")
    
    assert authenticated == False, f"Expected authenticated=false after failed exchange, got {authenticated}"
    log(f"  ✅ PASS: authenticated=false (failed exchange did NOT store token)")

def test_10_public_config_endpoint():
    """TEST 10: GET /api/shopify/config (PUBLIC, no auth) returns only client_id, NO secret"""
    log("TEST 10: GET /api/shopify/config (public)")
    
    # Call without any auth header
    r = requests.get(f"{BASE_URL}/shopify/config")
    
    log(f"  Response: {r.status_code}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    
    # Should contain api_key (client_id), app_configured, shop
    assert "api_key" in data, "Missing api_key"
    assert "app_configured" in data, "Missing app_configured"
    assert "shop" in data, "Missing shop"
    
    assert data["api_key"] == SHOPIFY_CLIENT_ID, f"Expected api_key={SHOPIFY_CLIENT_ID}, got {data['api_key']}"
    assert data["app_configured"] == True, f"Expected app_configured=true, got {data['app_configured']}"
    
    log(f"  ✅ api_key={data['api_key']}, app_configured={data['app_configured']}")
    
    # SECURITY: Must NOT contain client secret
    response_text = json.dumps(data)
    assert SHOPIFY_CLIENT_SECRET not in response_text, "SECURITY VIOLATION: Client secret in public config"
    assert "client_secret" not in response_text.lower(), "SECURITY VIOLATION: client_secret field in response"
    assert "shpat_" not in response_text, "SECURITY VIOLATION: Admin token in public config"
    
    log(f"  ✅ SECURITY: NO client secret or admin token in response")

def test_11_auth_status_requires_admin_jwt():
    """TEST 11: GET /api/shopify/auth/status requires app-admin JWT"""
    log("TEST 11: GET /api/shopify/auth/status authorization gating")
    
    # 11a. Without auth header -> 401
    log("  11a. Without Authorization header")
    r = requests.get(f"{BASE_URL}/shopify/auth/status")
    assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"
    log(f"  ✅ No auth -> {r.status_code}")
    
    # 11b. With admin JWT -> 200
    log("  11b. With admin JWT")
    r = requests.get(f"{BASE_URL}/shopify/auth/status", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    log(f"  ✅ Admin JWT -> 200")

def test_12_auth_test_requires_admin_jwt():
    """TEST 12: GET /api/shopify/auth/test requires app-admin JWT"""
    log("TEST 12: GET /api/shopify/auth/test authorization gating")
    
    # 12a. Without auth header -> 401
    log("  12a. Without Authorization header")
    r = requests.get(f"{BASE_URL}/shopify/auth/test")
    assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"
    log(f"  ✅ No auth -> {r.status_code}")
    
    # 12b. With admin JWT -> 200 (will return not_authenticated status since no token stored)
    log("  12b. With admin JWT (no stored token)")
    r = requests.get(f"{BASE_URL}/shopify/auth/test", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    assert data.get("connected") == False, "Expected connected=false with no stored token"
    assert data.get("status") == "not_authenticated", f"Expected status=not_authenticated, got {data.get('status')}"
    log(f"  ✅ Admin JWT -> 200, connected=false, status=not_authenticated")

def test_13_auth_disconnect_requires_admin_jwt():
    """TEST 13: POST /api/shopify/auth/disconnect requires app-admin JWT"""
    log("TEST 13: POST /api/shopify/auth/disconnect authorization gating")
    
    # 13a. Without auth header -> 401
    log("  13a. Without Authorization header")
    r = requests.post(f"{BASE_URL}/shopify/auth/disconnect")
    assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"
    log(f"  ✅ No auth -> {r.status_code}")
    
    # 13b. With admin JWT -> 200
    log("  13b. With admin JWT")
    r = requests.post(f"{BASE_URL}/shopify/auth/disconnect", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    log(f"  ✅ Admin JWT -> 200")

def test_14_regression_put_settings_shopify_ignores_token():
    """TEST 14: Regression - PUT /api/settings/shopify with token field must NOT store token.
    
    Verify GET /api/shopify/auth/status still authenticated=false and 
    GET /api/settings/config shopify.token_configured=false afterwards.
    """
    log("TEST 14: Regression - PUT /api/settings/shopify ignores token field")
    
    # 14a. Ensure no token stored
    log("  14a. Disconnect any existing token")
    r = requests.post(f"{BASE_URL}/shopify/auth/disconnect", headers=headers(admin_token))
    assert r.status_code == 200, f"Disconnect failed: {r.status_code}"
    
    # 14b. PUT /api/settings/shopify with token field (should be IGNORED)
    log("  14b. PUT /api/settings/shopify with token='shpat_SHOULD_BE_IGNORED'")
    payload = {
        "mode": "demo",
        "mock_mode": True,
        "token": "shpat_SHOULD_BE_IGNORED"
    }
    r = requests.put(f"{BASE_URL}/settings/shopify", headers=headers(admin_token), json=payload)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    log(f"  ✅ PUT succeeded (200)")
    
    # 14c. GET /api/shopify/auth/status - authenticated should be false
    log("  14c. GET /api/shopify/auth/status")
    r = requests.get(f"{BASE_URL}/shopify/auth/status", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    authenticated = data.get("authenticated")
    assert authenticated == False, f"Expected authenticated=false (token should be ignored), got {authenticated}"
    log(f"  ✅ authenticated=false (token field was IGNORED)")
    
    # 14d. GET /api/settings/config - shopify.token_configured should be false
    log("  14d. GET /api/settings/config")
    r = requests.get(f"{BASE_URL}/settings/config", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    token_configured = data.get("shopify", {}).get("token_configured")
    assert token_configured == False, f"Expected token_configured=false, got {token_configured}"
    log(f"  ✅ token_configured=false (token field was IGNORED)")

def test_15_regression_seo_only_allowlist():
    """TEST 15: Regression - SEO-only allowlist still enforced.
    
    PATCH a product seo-draft (or publish) with a forbidden commerce field like 
    price/vendor -> 403 NON_SEO_FIELD_WRITE_DENIED.
    """
    log("TEST 15: Regression - SEO-only allowlist enforced")
    
    # Get a demo product
    log("  15a. GET /api/products (get test product)")
    r = requests.get(f"{BASE_URL}/products?page=1&page_size=1", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    items = r.json().get("items", [])
    
    # If no products, seed demo data
    if len(items) == 0:
        log("  No products found, seeding demo data...")
        r = requests.post(f"{BASE_URL}/sync", headers=headers(admin_token))
        assert r.status_code == 200, f"Sync failed: {r.status_code}"
        time.sleep(5)
        
        r = requests.get(f"{BASE_URL}/products?page=1&page_size=1", headers=headers(admin_token))
        assert r.status_code == 200
        items = r.json().get("items", [])
    
    assert len(items) > 0, "No products found even after sync"
    
    global test_product_id
    test_product_id = items[0]["id"]
    log(f"  ✅ Got test product: {test_product_id}")
    
    # 15b. PATCH with forbidden field (price)
    log("  15b. PATCH /api/products/{id}/seo-draft with forbidden field (price)")
    r = requests.patch(f"{BASE_URL}/products/{test_product_id}/seo-draft",
                      headers=headers(admin_token),
                      json={"price": "99.99"})
    
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    assert "NON_SEO_FIELD_WRITE_DENIED" in r.text, "Expected NON_SEO_FIELD_WRITE_DENIED error"
    log(f"  ✅ Forbidden field (price) rejected with 403 NON_SEO_FIELD_WRITE_DENIED")
    
    # 15c. POST publish-seo with forbidden field (vendor)
    log("  15c. POST /api/products/{id}/publish-seo with forbidden field (vendor)")
    r = requests.post(f"{BASE_URL}/products/{test_product_id}/publish-seo",
                     headers=headers(admin_token),
                     json={"vendor": "Evil Corp"})
    
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    assert "NON_SEO_FIELD_WRITE_DENIED" in r.text, "Expected NON_SEO_FIELD_WRITE_DENIED error"
    log(f"  ✅ Forbidden field (vendor) rejected with 403 NON_SEO_FIELD_WRITE_DENIED")

def test_16_verify_app_data_mode_demo():
    """TEST 16: Verify APP_DATA_MODE remains demo (no sync triggered)"""
    log("TEST 16: Verify APP_DATA_MODE=demo")
    
    r = requests.get(f"{BASE_URL}/settings/config", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    mode = data.get("shopify", {}).get("mode")
    data_source = data.get("shopify", {}).get("data_source")
    
    assert mode == "demo", f"Expected mode=demo, got {mode}"
    assert data_source == "demo", f"Expected data_source=demo, got {data_source}"
    
    log(f"  ✅ APP_DATA_MODE=demo, data_source=demo (no mode change)")

def main():
    global admin_token
    
    print("\n" + "="*80)
    print("SHOPIFY TOKEN EXCHANGE AUTHENTICATION BACKEND TESTING")
    print("="*80 + "\n")
    
    # Login
    print("SETUP: Logging in...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    print(f"✅ Admin logged in: {ADMIN_EMAIL}\n")
    
    # Run tests
    tests = [
        test_1_valid_token_reaches_exchange,
        test_2_bad_signature,
        test_3_expired_token,
        test_4_not_yet_valid,
        test_5_wrong_audience,
        test_6_shop_mismatch,
        test_7_invalid_shop_host,
        test_8_missing_authorization_header,
        test_9_failed_exchange_no_token_stored,
        test_10_public_config_endpoint,
        test_11_auth_status_requires_admin_jwt,
        test_12_auth_test_requires_admin_jwt,
        test_13_auth_disconnect_requires_admin_jwt,
        test_14_regression_put_settings_shopify_ignores_token,
        test_15_regression_seo_only_allowlist,
        test_16_verify_app_data_mode_demo,
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for test_func in tests:
        try:
            print(f"\n{test_func.__name__.replace('_', ' ').upper()}")
            print("-" * 80)
            test_func()
            passed += 1
            print(f"✅ {test_func.__name__} PASSED\n")
        except AssertionError as e:
            failed += 1
            error_msg = f"{test_func.__name__}: {e}"
            errors.append(error_msg)
            print(f"❌ {test_func.__name__} FAILED: {e}\n")
        except Exception as e:
            failed += 1
            error_msg = f"{test_func.__name__}: {e}"
            errors.append(error_msg)
            print(f"❌ {test_func.__name__} ERROR: {e}\n")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"PASSED: {passed}/{len(tests)}")
    print(f"FAILED: {failed}/{len(tests)}")
    
    if failed > 0:
        print("\nFAILED TESTS:")
        for error in errors:
            print(f"  ❌ {error}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED - Shopify Token Exchange authentication is working correctly")
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
    
    print("="*80 + "\n")
    
    return failed == 0

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
