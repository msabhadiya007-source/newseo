#!/usr/bin/env python3
"""
Comprehensive backend test for Image ALT SEO analysis REMOVAL verification.
Tests that MISSING_ALT and DUPLICATE_ALT issue codes are completely removed
from the deterministic analyzer and no longer appear in products or dashboard.
"""
import os
import sys
import requests
import json
from typing import Dict, List, Any

# Base URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://c3f633d2-05c2-4681-b4a1-dbca84ba1a5b.preview.emergentagent.com")
API_BASE = f"{BASE_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@urbandotted.com"
ADMIN_PASSWORD = "Admin@12345"

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.details = []
    
    def add_pass(self, test_name: str, detail: str = ""):
        self.passed += 1
        self.details.append(f"{GREEN}✅ PASS{RESET}: {test_name}" + (f" - {detail}" if detail else ""))
    
    def add_fail(self, test_name: str, detail: str = ""):
        self.failed += 1
        self.details.append(f"{RED}❌ FAIL{RESET}: {test_name}" + (f" - {detail}" if detail else ""))
    
    def print_summary(self):
        print("\n" + "="*80)
        print(f"{BLUE}TEST SUMMARY{RESET}")
        print("="*80)
        for detail in self.details:
            print(detail)
        print("="*80)
        total = self.passed + self.failed
        print(f"Total: {total} | {GREEN}Passed: {self.passed}{RESET} | {RED}Failed: {self.failed}{RESET}")
        print("="*80)
        return self.failed == 0

def login() -> str:
    """Login and return JWT token."""
    print(f"\n{BLUE}[AUTH]{RESET} Logging in as {ADMIN_EMAIL}...")
    resp = requests.post(f"{API_BASE}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        print(f"{RED}Login failed: {resp.status_code} {resp.text}{RESET}")
        sys.exit(1)
    token = resp.json()["token"]
    print(f"{GREEN}✓ Login successful{RESET}")
    return token

def headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def test_1_recompute_demo_data(token: str, results: TestResults):
    """Test 1: POST /api/reanalyze to recompute demo data."""
    print(f"\n{BLUE}[TEST 1]{RESET} Recomputing demo data via POST /api/reanalyze...")
    
    resp = requests.post(f"{API_BASE}/reanalyze", headers=headers(token))
    
    if resp.status_code != 200:
        results.add_fail("Reanalyze endpoint", f"Expected 200, got {resp.status_code}: {resp.text}")
        return
    
    data = resp.json()
    job_id = data.get("job_id")
    
    if not job_id:
        results.add_fail("Reanalyze response", "No job_id in response")
        return
    
    results.add_pass("Reanalyze endpoint", f"Job {job_id} started")
    
    # Wait for job to complete
    import time
    max_wait = 60
    waited = 0
    while waited < max_wait:
        time.sleep(2)
        waited += 2
        job_resp = requests.get(f"{API_BASE}/jobs/{job_id}", headers=headers(token))
        if job_resp.status_code == 200:
            job = job_resp.json()
            status = job.get("status")
            if status == "completed":
                results.add_pass("Reanalyze job completion", f"Completed in {waited}s")
                return
            elif status == "failed":
                results.add_fail("Reanalyze job completion", f"Job failed: {job.get('error')}")
                return
    
    results.add_fail("Reanalyze job completion", f"Timeout after {max_wait}s")

def test_2_no_alt_issues_in_products(token: str, results: TestResults):
    """Test 2: GET /api/products and verify NO MISSING_ALT or DUPLICATE_ALT in issue_codes."""
    print(f"\n{BLUE}[TEST 2]{RESET} Checking products for ALT issue codes...")
    
    # Sample first 200 products (8 pages of 25)
    total_checked = 0
    products_with_alt_issues = []
    
    for page in range(1, 9):
        resp = requests.get(f"{API_BASE}/products", params={
            "page": page,
            "page_size": 25,
            "source": "demo"
        }, headers=headers(token))
        
        if resp.status_code != 200:
            results.add_fail(f"Products list page {page}", f"Expected 200, got {resp.status_code}")
            continue
        
        data = resp.json()
        items = data.get("items", [])
        
        for product in items:
            total_checked += 1
            issue_codes = product.get("issue_codes", [])
            
            # Check for ALT-related issue codes
            if "MISSING_ALT" in issue_codes or "DUPLICATE_ALT" in issue_codes:
                products_with_alt_issues.append({
                    "id": product.get("id"),
                    "title": product.get("title"),
                    "issue_codes": issue_codes
                })
    
    if products_with_alt_issues:
        results.add_fail("No ALT issues in products", 
                        f"Found {len(products_with_alt_issues)} products with ALT issues: {products_with_alt_issues[:3]}")
    else:
        results.add_pass("No ALT issues in products", f"Checked {total_checked} products, ZERO have MISSING_ALT or DUPLICATE_ALT")

def test_3_no_alt_text_in_breakdown(token: str, results: TestResults):
    """Test 3: Check score_breakdown has NO ALT-related text."""
    print(f"\n{BLUE}[TEST 3]{RESET} Checking score_breakdown for ALT-related text...")
    
    # Get a few products and check their score_breakdown
    resp = requests.get(f"{API_BASE}/products", params={
        "page": 1,
        "page_size": 10,
        "source": "demo"
    }, headers=headers(token))
    
    if resp.status_code != 200:
        results.add_fail("Products for breakdown check", f"Expected 200, got {resp.status_code}")
        return
    
    items = resp.json().get("items", [])
    products_with_alt_text = []
    
    alt_keywords = ["ALT text", "images are missing ALT", "All images have ALT text", "missing ALT", "duplicate ALT"]
    
    for product in items:
        breakdown = product.get("score_breakdown", {})
        problems = breakdown.get("problems", [])
        positives = breakdown.get("positives", [])
        
        all_text = " ".join(problems + positives).lower()
        
        for keyword in alt_keywords:
            if keyword.lower() in all_text:
                products_with_alt_text.append({
                    "id": product.get("id"),
                    "title": product.get("title"),
                    "found": keyword
                })
                break
    
    if products_with_alt_text:
        results.add_fail("No ALT text in breakdown", 
                        f"Found {len(products_with_alt_text)} products with ALT text in breakdown: {products_with_alt_text[:2]}")
    else:
        results.add_pass("No ALT text in breakdown", f"Checked {len(items)} products, ZERO have ALT-related text in problems/positives")

def test_4_dashboard_no_alt_issues(token: str, results: TestResults):
    """Test 4: GET /api/dashboard/metrics and verify NO ALT issues."""
    print(f"\n{BLUE}[TEST 4]{RESET} Checking dashboard metrics for ALT issues...")
    
    resp = requests.get(f"{API_BASE}/dashboard/metrics", params={"source": "demo"}, headers=headers(token))
    
    if resp.status_code != 200:
        results.add_fail("Dashboard metrics", f"Expected 200, got {resp.status_code}")
        return
    
    data = resp.json()
    issues = data.get("issues", {})
    issue_labels = data.get("issue_labels", {})
    health = data.get("health")
    
    # Check issues dict
    alt_issues_in_dict = []
    for issue_code in ["MISSING_ALT", "DUPLICATE_ALT"]:
        if issue_code in issues:
            alt_issues_in_dict.append(f"{issue_code}: {issues[issue_code]}")
    
    if alt_issues_in_dict:
        results.add_fail("Dashboard issues dict", f"Found ALT issues: {alt_issues_in_dict}")
    else:
        results.add_pass("Dashboard issues dict", "NO MISSING_ALT or DUPLICATE_ALT keys present")
    
    # Check issue_labels
    alt_labels = []
    for issue_code in ["MISSING_ALT", "DUPLICATE_ALT"]:
        if issue_code in issue_labels:
            alt_labels.append(f"{issue_code}: {issue_labels[issue_code]}")
    
    if alt_labels:
        results.add_fail("Dashboard issue_labels", f"Found ALT labels: {alt_labels}")
    else:
        results.add_pass("Dashboard issue_labels", "NO MISSING_ALT or DUPLICATE_ALT in issue_labels")
    
    # Check health is 0-100
    if health is None or not isinstance(health, int) or health < 0 or health > 100:
        results.add_fail("Dashboard health score", f"Health is {health}, expected integer 0-100")
    else:
        results.add_pass("Dashboard health score", f"Health is {health} (valid 0-100 range)")

def test_5_score_normalization(token: str, results: TestResults):
    """Test 5: Verify all scores are 0-100 and some reach high scores."""
    print(f"\n{BLUE}[TEST 5]{RESET} Checking score normalization...")
    
    # Get a larger sample
    all_scores = []
    for page in range(1, 5):
        resp = requests.get(f"{API_BASE}/products", params={
            "page": page,
            "page_size": 50,
            "source": "demo"
        }, headers=headers(token))
        
        if resp.status_code != 200:
            continue
        
        items = resp.json().get("items", [])
        for product in items:
            score = product.get("seo_score")
            if score is not None:
                all_scores.append(score)
    
    if not all_scores:
        results.add_fail("Score normalization", "No scores found")
        return
    
    # Check all scores are 0-100
    invalid_scores = [s for s in all_scores if s < 0 or s > 100]
    if invalid_scores:
        results.add_fail("Scores in 0-100 range", f"Found {len(invalid_scores)} invalid scores: {invalid_scores[:5]}")
    else:
        results.add_pass("Scores in 0-100 range", f"All {len(all_scores)} scores are between 0 and 100")
    
    # Check some reach high scores
    high_scores = [s for s in all_scores if s >= 85]
    max_score = max(all_scores) if all_scores else 0
    
    if high_scores:
        results.add_pass("High scores achievable", f"Found {len(high_scores)} products with score ≥85, max={max_score}")
    else:
        results.add_fail("High scores achievable", f"NO products with score ≥85, max={max_score}")

def test_6_regression_seo_draft(token: str, results: TestResults):
    """Test 6: Regression - SEO draft creation works."""
    print(f"\n{BLUE}[TEST 6]{RESET} Testing SEO draft creation (regression)...")
    
    # Get a product
    resp = requests.get(f"{API_BASE}/products", params={"page": 1, "page_size": 1, "source": "demo"}, 
                       headers=headers(token))
    if resp.status_code != 200:
        results.add_fail("Get product for draft test", f"Expected 200, got {resp.status_code}")
        return
    
    items = resp.json().get("items", [])
    if not items:
        results.add_fail("Get product for draft test", "No products found")
        return
    
    product_id = items[0]["id"]
    
    # Create draft
    draft_resp = requests.patch(f"{API_BASE}/products/{product_id}/seo-draft", 
                               json={"seo_title": "Regression Test SEO Title Example"},
                               headers=headers(token))
    
    if draft_resp.status_code != 200:
        results.add_fail("SEO draft creation", f"Expected 200, got {draft_resp.status_code}: {draft_resp.text}")
        return
    
    draft_data = draft_resp.json()
    
    # Verify draft created
    if draft_data.get("has_draft") != True:
        results.add_fail("SEO draft creation", f"has_draft is {draft_data.get('has_draft')}, expected True")
        return
    
    if draft_data.get("publication_status") != "draft":
        results.add_fail("SEO draft creation", f"publication_status is {draft_data.get('publication_status')}, expected 'draft'")
        return
    
    results.add_pass("SEO draft creation", "Draft created successfully, has_draft=true, publication_status=draft")

def test_7_regression_forbidden_fields(token: str, results: TestResults):
    """Test 7: Regression - Forbidden commerce fields are denied."""
    print(f"\n{BLUE}[TEST 7]{RESET} Testing forbidden field security (regression)...")
    
    # Get a product
    resp = requests.get(f"{API_BASE}/products", params={"page": 1, "page_size": 1, "source": "demo"}, 
                       headers=headers(token))
    if resp.status_code != 200:
        results.add_fail("Get product for forbidden test", f"Expected 200, got {resp.status_code}")
        return
    
    items = resp.json().get("items", [])
    if not items:
        results.add_fail("Get product for forbidden test", "No products found")
        return
    
    product_id = items[0]["id"]
    
    # Test 1: PATCH seo-draft with forbidden field 'price'
    resp1 = requests.patch(f"{API_BASE}/products/{product_id}/seo-draft", 
                          json={"price": 123},
                          headers=headers(token))
    
    if resp1.status_code != 403:
        results.add_fail("Forbidden field 'price' in seo-draft", f"Expected 403, got {resp1.status_code}")
    elif "NON_SEO_FIELD_WRITE_DENIED" not in resp1.text:
        results.add_fail("Forbidden field 'price' in seo-draft", f"Expected NON_SEO_FIELD_WRITE_DENIED, got: {resp1.text}")
    else:
        results.add_pass("Forbidden field 'price' in seo-draft", "Correctly denied with 403 NON_SEO_FIELD_WRITE_DENIED")
    
    # Test 2: POST publish-seo with forbidden field 'vendor'
    resp2 = requests.post(f"{API_BASE}/products/{product_id}/publish-seo", 
                         json={"vendor": "TestVendor"},
                         headers=headers(token))
    
    if resp2.status_code != 403:
        results.add_fail("Forbidden field 'vendor' in publish-seo", f"Expected 403, got {resp2.status_code}")
    elif "NON_SEO_FIELD_WRITE_DENIED" not in resp2.text:
        results.add_fail("Forbidden field 'vendor' in publish-seo", f"Expected NON_SEO_FIELD_WRITE_DENIED, got: {resp2.text}")
    else:
        results.add_pass("Forbidden field 'vendor' in publish-seo", "Correctly denied with 403 NON_SEO_FIELD_WRITE_DENIED")

def test_8_regression_ai_suggest(token: str, results: TestResults):
    """Test 8: Regression - AI single suggest works."""
    print(f"\n{BLUE}[TEST 8]{RESET} Testing AI single suggest (regression)...")
    
    # Get a product
    resp = requests.get(f"{API_BASE}/products", params={"page": 1, "page_size": 1, "source": "demo"}, 
                       headers=headers(token))
    if resp.status_code != 200:
        results.add_fail("Get product for AI test", f"Expected 200, got {resp.status_code}")
        return
    
    items = resp.json().get("items", [])
    if not items:
        results.add_fail("Get product for AI test", "No products found")
        return
    
    product_id = items[0]["id"]
    
    # Test AI suggest
    ai_resp = requests.post(f"{API_BASE}/products/{product_id}/ai-suggest", 
                           json={"field": "seo_title"},
                           headers=headers(token))
    
    if ai_resp.status_code != 200:
        results.add_fail("AI suggest endpoint", f"Expected 200, got {ai_resp.status_code}: {ai_resp.text}")
        return
    
    ai_data = ai_resp.json()
    suggestion = ai_data.get("suggestion")
    
    if not suggestion or len(suggestion) == 0:
        results.add_fail("AI suggest response", f"Expected non-empty suggestion, got: {suggestion}")
        return
    
    results.add_pass("AI suggest endpoint", f"Returned non-empty suggestion (length={len(suggestion)})")

def test_9_regression_ai_providers(token: str, results: TestResults):
    """Test 9: Regression - AI providers config."""
    print(f"\n{BLUE}[TEST 9]{RESET} Testing AI providers config (regression)...")
    
    resp = requests.get(f"{API_BASE}/settings/config", headers=headers(token))
    
    if resp.status_code != 200:
        results.add_fail("Settings config endpoint", f"Expected 200, got {resp.status_code}")
        return
    
    data = resp.json()
    ai_config = data.get("ai", {})
    providers = ai_config.get("providers", {})
    
    expected_providers = ["openai", "anthropic", "gemini", "deepseek"]
    missing_providers = [p for p in expected_providers if p not in providers]
    
    if missing_providers:
        results.add_fail("AI providers present", f"Missing providers: {missing_providers}")
    else:
        results.add_pass("AI providers present", f"All 4 providers present: {expected_providers}")

def main():
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}IMAGE ALT SEO ANALYSIS REMOVAL VERIFICATION TEST{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    print(f"Base URL: {BASE_URL}")
    print(f"API Base: {API_BASE}")
    
    results = TestResults()
    
    try:
        # Login
        token = login()
        
        # Run all tests
        test_1_recompute_demo_data(token, results)
        test_2_no_alt_issues_in_products(token, results)
        test_3_no_alt_text_in_breakdown(token, results)
        test_4_dashboard_no_alt_issues(token, results)
        test_5_score_normalization(token, results)
        test_6_regression_seo_draft(token, results)
        test_7_regression_forbidden_fields(token, results)
        test_8_regression_ai_suggest(token, results)
        test_9_regression_ai_providers(token, results)
        
    except Exception as e:
        print(f"\n{RED}FATAL ERROR: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Print summary
    success = results.print_summary()
    
    # Create summary table
    print(f"\n{BLUE}PASS/FAIL TABLE{RESET}")
    print("="*80)
    print(f"{'Test':<50} {'Status':<15} {'Details':<15}")
    print("-"*80)
    
    test_names = [
        "1. Recompute demo data (POST /api/reanalyze)",
        "2. No ALT issues in products (200 sampled)",
        "3. No ALT text in score_breakdown",
        "4. Dashboard has NO ALT issues/labels",
        "5. Score normalization (0-100, high scores)",
        "6. SEO draft creation works",
        "7. Forbidden fields denied (price, vendor)",
        "8. AI suggest works",
        "9. AI providers config present"
    ]
    
    for i, name in enumerate(test_names, 1):
        # Find result for this test
        status = "UNKNOWN"
        for detail in results.details:
            if f"TEST {i}" in detail or any(keyword in detail for keyword in name.split()):
                if "✅ PASS" in detail:
                    status = f"{GREEN}PASS{RESET}"
                elif "❌ FAIL" in detail:
                    status = f"{RED}FAIL{RESET}"
                break
        print(f"{name:<50} {status:<15}")
    
    print("="*80)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
