#!/usr/bin/env python3
"""Final Pre-Deployment Regression Test for Shopify Token Exchange Auth

Additional verification tests beyond the main test suite:
- Verify SEO-only fields (seo_title, meta_description) still work correctly
- Verify no sync was triggered
- Additional security checks
"""
import requests
import json

BASE_URL = "https://c3f633d2-05c2-4681-b4a1-dbca84ba1a5b.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@urbandotted.com"
ADMIN_PASSWORD = "Admin@12345"

def log(msg):
    print(f"  {msg}")

def login(email, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise Exception(f"Login failed: {r.status_code} {r.text}")
    return r.json()["token"]

def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def test_seo_fields_work():
    """Verify SEO-only fields (seo_title, meta_description) still work correctly"""
    log("TEST: SEO-only fields work correctly")
    
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    # Get a product
    r = requests.get(f"{BASE_URL}/products?page=1&page_size=1", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    items = r.json().get("items", [])
    assert len(items) > 0, "No products found"
    
    product_id = items[0]["id"]
    original_seo_title = items[0].get("current_seo_title", "")
    log(f"  Product ID: {product_id}")
    log(f"  Original SEO title: {original_seo_title}")
    
    # Test 1: PATCH seo-draft with SEO-only fields (should work)
    log("  1. PATCH /api/products/{id}/seo-draft with seo_title and meta_description")
    new_seo_title = "Test SEO Title for Regression"
    new_meta_desc = "Test meta description for regression testing of SEO-only fields"
    
    r = requests.patch(f"{BASE_URL}/products/{product_id}/seo-draft",
                      headers=headers(admin_token),
                      json={
                          "seo_title": new_seo_title,
                          "meta_description": new_meta_desc
                      })
    
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    log(f"  ✅ SEO draft saved successfully (200)")
    
    # Verify draft was saved
    r = requests.get(f"{BASE_URL}/products/{product_id}", headers=headers(admin_token))
    assert r.status_code == 200
    product = r.json()
    
    assert product.get("has_draft") == True, "Expected has_draft=true"
    assert product.get("draft_seo_title") == new_seo_title, f"Expected draft_seo_title={new_seo_title}"
    log(f"  ✅ Draft verified: has_draft=true, draft_seo_title={product.get('draft_seo_title')}")
    
    # Test 2: POST publish-seo with SEO-only fields (should work)
    log("  2. POST /api/products/{id}/publish-seo with seo_title")
    publish_seo_title = "Published SEO Title for Regression"
    
    r = requests.post(f"{BASE_URL}/products/{product_id}/publish-seo",
                     headers=headers(admin_token),
                     json={"seo_title": publish_seo_title})
    
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    log(f"  ✅ SEO publish successful (200)")
    
    # Verify publish worked
    r = requests.get(f"{BASE_URL}/products/{product_id}", headers=headers(admin_token))
    assert r.status_code == 200
    product = r.json()
    
    assert product.get("current_seo_title") == publish_seo_title, \
        f"Expected current_seo_title={publish_seo_title}, got {product.get('current_seo_title')}"
    log(f"  ✅ Publish verified: current_seo_title={product.get('current_seo_title')}")
    
    log("✅ PASS: SEO-only fields work correctly")

def test_no_sync_triggered():
    """Verify no Shopify sync was triggered during testing"""
    log("TEST: Verify no sync was triggered")
    
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    # Check sync state
    r = requests.get(f"{BASE_URL}/sync/status", headers=headers(admin_token))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    data = r.json()
    sync_state = data.get("sync_state", {})
    
    # Verify no sync is in progress
    in_progress = sync_state.get("in_progress", False)
    assert in_progress == False, f"Expected in_progress=false, got {in_progress}"
    log(f"  ✅ No sync in progress: in_progress={in_progress}")
    
    # Verify mode is still demo
    r = requests.get(f"{BASE_URL}/settings/config", headers=headers(admin_token))
    assert r.status_code == 200
    
    config = r.json()
    mode = config.get("shopify", {}).get("mode")
    data_source = config.get("shopify", {}).get("data_source")
    
    assert mode == "demo", f"Expected mode=demo, got {mode}"
    assert data_source == "demo", f"Expected data_source=demo, got {data_source}"
    log(f"  ✅ Mode unchanged: mode={mode}, data_source={data_source}")
    
    log("✅ PASS: No sync triggered, mode remains demo")

def test_security_comprehensive():
    """Comprehensive security check across all endpoints"""
    log("TEST: Comprehensive security check")
    
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    # List of endpoints to check for secret leakage
    endpoints = [
        ("GET", f"{BASE_URL}/shopify/config", None, None),  # Public
        ("GET", f"{BASE_URL}/shopify/auth/status", headers(admin_token), None),
        ("GET", f"{BASE_URL}/shopify/auth/test", headers(admin_token), None),
        ("GET", f"{BASE_URL}/settings/config", headers(admin_token), None),
    ]
    
    forbidden_patterns = [
        "shpat_",  # Shopify admin token prefix
        "preview_test_client_secret",  # Test client secret
        "gAAAAA",  # Fernet encryption prefix
    ]
    
    for method, url, hdrs, body in endpoints:
        if method == "GET":
            r = requests.get(url, headers=hdrs)
        else:
            r = requests.post(url, headers=hdrs, json=body)
        
        response_text = r.text
        
        for pattern in forbidden_patterns:
            assert pattern not in response_text, \
                f"SECURITY VIOLATION: Found '{pattern}' in response from {url}"
        
        log(f"  ✅ {method} {url.split('/api/')[-1]}: No secrets exposed")
    
    log("✅ PASS: No secrets exposed in any endpoint")

def main():
    print("\n" + "="*80)
    print("FINAL PRE-DEPLOYMENT REGRESSION TEST")
    print("="*80 + "\n")
    
    tests = [
        test_seo_fields_work,
        test_no_sync_triggered,
        test_security_comprehensive,
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
        print("\n✅ ALL ADDITIONAL TESTS PASSED")
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
    
    print("="*80 + "\n")
    
    return failed == 0

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
