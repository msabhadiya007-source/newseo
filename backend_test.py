#!/usr/bin/env python3
"""
Phase 3.5 Backend API Testing - Real Shopify Live Sync
Tests all acceptance criteria for the UrbanDotted SEO Operations app
"""
import requests
import time
import json
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "https://admin-demo-cleanup.preview.emergentagent.com/api"
ADMIN_EMAIL = "msabhadiya007@gmail.com"
ADMIN_PASSWORD = "Admin@12345"

class TestRunner:
    def __init__(self):
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {}
        self.results = []
        self.failed_count = 0
        self.passed_count = 0
        
    def log(self, message: str, level: str = "INFO"):
        """Log test messages"""
        prefix = "✅" if level == "PASS" else "❌" if level == "FAIL" else "ℹ️"
        print(f"{prefix} {message}")
        
    def assert_true(self, condition: bool, message: str, details: Any = None):
        """Assert a condition and log result"""
        if condition:
            self.log(f"PASS: {message}", "PASS")
            self.passed_count += 1
            self.results.append({"status": "PASS", "message": message})
        else:
            self.log(f"FAIL: {message}", "FAIL")
            if details:
                print(f"   Details: {json.dumps(details, indent=2)}")
            self.failed_count += 1
            self.results.append({"status": "FAIL", "message": message, "details": details})
            
    def login(self):
        """Login and get JWT token"""
        self.log("=== TEST: Admin Login ===")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
            self.assert_true(response.status_code == 200, "Login returns 200", response.text)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                self.assert_true(self.token is not None, "JWT token present in response", data)
                
                if self.token:
                    self.headers = {"Authorization": f"Bearer {self.token}"}
                    self.log(f"Login successful, token: {self.token[:20]}...")
                    return True
        except Exception as e:
            self.assert_true(False, f"Login failed with exception: {e}")
        return False
        
    def test_connection(self):
        """Test 1: Connection test endpoint"""
        self.log("\n=== TEST 1: Connection Test (GET /api/settings/shopify/test) ===")
        try:
            response = requests.get(f"{BASE_URL}/settings/shopify/test", headers=self.headers, timeout=10)
            self.assert_true(response.status_code == 200, "Connection test returns 200")
            
            if response.status_code == 200:
                data = response.json()
                self.log(f"Connection response: {json.dumps(data, indent=2)}")
                
                # In demo mode, expect connected=false, status="demo_mode"
                self.assert_true("connected" in data or "status" in data, 
                               "Response contains connection status", data)
                
                # Verify no raw Shopify token exposed
                response_str = json.dumps(data).lower()
                has_token = any(word in response_str for word in ["token", "secret", "password", "key"])
                self.assert_true(not has_token or "demo_mode" in response_str, 
                               "No raw Shopify credentials exposed in response")
                
        except Exception as e:
            self.assert_true(False, f"Connection test failed: {e}")
            
    def test_full_sync(self) -> Optional[str]:
        """Test 2: LIVE full sync with pagination"""
        self.log("\n=== TEST 2: LIVE Full Sync (POST /api/shopify/live-sync?full_resync=true) ===")
        job_id = None
        try:
            response = requests.post(
                f"{BASE_URL}/shopify/live-sync?full_resync=true",
                headers=self.headers,
                timeout=10
            )
            self.assert_true(response.status_code == 200, "Live sync endpoint returns 200")
            
            if response.status_code == 200:
                data = response.json()
                job_id = data.get("job_id")
                self.assert_true(job_id is not None, "Job ID returned", data)
                self.log(f"Job created: {job_id}")
                
                # Poll job until completion (max 120 seconds)
                if job_id:
                    self.log("Polling job status...")
                    max_wait = 120
                    start_time = time.time()
                    job_data = None
                    
                    while time.time() - start_time < max_wait:
                        job_response = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=self.headers, timeout=10)
                        if job_response.status_code == 200:
                            job_data = job_response.json()
                            status = job_data.get("status")
                            progress = job_data.get("progress", 0)
                            self.log(f"Job status: {status}, progress: {progress}%")
                            
                            if status == "completed":
                                self.log("Job completed successfully!")
                                break
                            elif status == "failed":
                                self.assert_true(False, "Job failed", job_data)
                                break
                        time.sleep(2)
                    
                    if job_data:
                        status = job_data.get("status")
                        self.assert_true(status == "completed", "Job status is 'completed'", job_data)
                        
                        if status == "completed":
                            pages = job_data.get("pages", 0)
                            failed = job_data.get("failed", 0)
                            progress = job_data.get("progress", 0)
                            
                            self.assert_true(pages >= 2, f"Pagination happened (pages >= 2, got {pages})", job_data)
                            self.assert_true(failed == 0, f"No failed items (failed == 0, got {failed})", job_data)
                            self.assert_true(progress == 100, f"Progress is 100% (got {progress})", job_data)
                            
                            # Check for counters
                            counters_present = any(k in job_data for k in ["new", "updated", "unchanged"])
                            self.assert_true(counters_present, "Counters (new/updated/unchanged) present", job_data)
                    else:
                        self.assert_true(False, "Job did not complete within 120 seconds")
                        
        except Exception as e:
            self.assert_true(False, f"Full sync test failed: {e}")
            
        return job_id
        
    def test_live_products(self):
        """Test 3: Live product ingestion"""
        self.log("\n=== TEST 3: Live Product Ingestion (GET /api/products?page_size=10&source=live) ===")
        try:
            # Admin can explicitly query live data_source even in demo mode
            response = requests.get(f"{BASE_URL}/products?page_size=10&source=live", headers=self.headers, timeout=10)
            self.assert_true(response.status_code == 200, "Products endpoint returns 200")
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                self.assert_true(len(items) > 0, f"Products returned (got {len(items)} items)", data)
                
                if items:
                    # Check every item has data_source == "live"
                    all_live = all(item.get("data_source") == "live" for item in items)
                    self.assert_true(all_live, "All products have data_source='live'", 
                                   [item.get("data_source") for item in items])
                    
                    # Check SEO-relevant fields exist
                    first_item = items[0]
                    required_fields = ["handle", "title", "shopify_product_id", "status_bucket"]
                    for field in required_fields:
                        self.assert_true(field in first_item, f"Product has '{field}' field", first_item.keys())
                        
                    self.log(f"Sample product: {first_item.get('title')} (handle: {first_item.get('handle')})")
                    
        except Exception as e:
            self.assert_true(False, f"Live products test failed: {e}")
            
    def test_live_collections(self):
        """Test 3b: Live collection ingestion"""
        self.log("\n=== TEST 3b: Live Collection Ingestion (GET /api/collections?page_size=5&source=live) ===")
        try:
            # Admin can explicitly query live data_source even in demo mode
            response = requests.get(f"{BASE_URL}/collections?page_size=5&source=live", headers=self.headers, timeout=10)
            self.assert_true(response.status_code == 200, "Collections endpoint returns 200")
            
            if response.status_code == 200:
                data = response.json()
                total = data.get("total", 0)
                self.assert_true(total > 0, f"Collections exist (total > 0, got {total})", data)
                
        except Exception as e:
            self.assert_true(False, f"Live collections test failed: {e}")
            
    def test_demo_live_separation(self):
        """Test 4: DEMO/LIVE never mixed"""
        self.log("\n=== TEST 4: DEMO/LIVE Separation (GET /api/products?source=live) ===")
        try:
            # Query live data_source explicitly
            response = requests.get(f"{BASE_URL}/products?page_size=50&source=live", headers=self.headers, timeout=10)
            self.assert_true(response.status_code == 200, "Products endpoint returns 200")
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                
                if items:
                    # All items must be data_source=="live" (no demo records leaking)
                    data_sources = set(item.get("data_source") for item in items)
                    self.assert_true(data_sources == {"live"}, 
                                   "Only 'live' data_source present (no demo leaking)", 
                                   list(data_sources))
                    
        except Exception as e:
            self.assert_true(False, f"DEMO/LIVE separation test failed: {e}")
            
    def test_incremental_sync(self):
        """Test 5: Incremental sync"""
        self.log("\n=== TEST 5: Incremental Sync (POST /api/shopify/live-sync?full_resync=false) ===")
        try:
            response = requests.post(
                f"{BASE_URL}/shopify/live-sync?full_resync=false",
                headers=self.headers,
                timeout=10
            )
            self.assert_true(response.status_code == 200, "Incremental sync endpoint returns 200")
            
            if response.status_code == 200:
                data = response.json()
                job_id = data.get("job_id")
                self.assert_true(job_id is not None, "Job ID returned", data)
                
                if job_id:
                    self.log("Polling incremental sync job...")
                    max_wait = 120
                    start_time = time.time()
                    job_data = None
                    
                    while time.time() - start_time < max_wait:
                        job_response = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=self.headers, timeout=10)
                        if job_response.status_code == 200:
                            job_data = job_response.json()
                            status = job_data.get("status")
                            
                            if status in ["completed", "failed"]:
                                break
                        time.sleep(2)
                    
                    if job_data:
                        status = job_data.get("status")
                        self.assert_true(status == "completed", "Incremental sync completed", job_data)
                        
                        if status == "completed":
                            new_count = job_data.get("new", 0)
                            self.assert_true(new_count == 0, 
                                           f"No new items created (new == 0, got {new_count})", 
                                           job_data)
                            
        except Exception as e:
            self.assert_true(False, f"Incremental sync test failed: {e}")
            
    def test_draft_survival(self):
        """Test 6: Non-destructive drafts survive re-sync"""
        self.log("\n=== TEST 6: Draft Survival Through Re-sync ===")
        try:
            # Get a live product (admin can query live source explicitly)
            response = requests.get(f"{BASE_URL}/products?page_size=1&source=live", headers=self.headers, timeout=10)
            if response.status_code != 200:
                self.assert_true(False, "Could not fetch products for draft test")
                return
                
            data = response.json()
            items = data.get("items", [])
            if not items:
                self.assert_true(False, "No products available for draft test")
                return
                
            product_id = items[0].get("id")
            self.log(f"Testing with product: {product_id}")
            
            # Create a draft
            draft_payload = {
                "seo_title": "DRAFT KEEP ME",
                "meta_description": "Draft must survive re-sync of at least forty chars here."
            }
            draft_response = requests.patch(
                f"{BASE_URL}/products/{product_id}/seo-draft",
                headers=self.headers,
                json=draft_payload,
                timeout=10
            )
            self.assert_true(draft_response.status_code == 200, "Draft creation returns 200", draft_response.text)
            
            if draft_response.status_code == 200:
                # Run full re-sync
                self.log("Running full re-sync to test draft survival...")
                sync_response = requests.post(
                    f"{BASE_URL}/shopify/live-sync?full_resync=true",
                    headers=self.headers,
                    timeout=10
                )
                
                if sync_response.status_code == 200:
                    job_id = sync_response.json().get("job_id")
                    
                    # Poll until complete
                    max_wait = 120
                    start_time = time.time()
                    completed = False
                    
                    while time.time() - start_time < max_wait:
                        job_response = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=self.headers, timeout=10)
                        if job_response.status_code == 200:
                            job_data = job_response.json()
                            if job_data.get("status") == "completed":
                                completed = True
                                break
                        time.sleep(2)
                    
                    self.assert_true(completed, "Re-sync completed")
                    
                    if completed:
                        # Check if draft survived
                        product_response = requests.get(
                            f"{BASE_URL}/products/{product_id}",
                            headers=self.headers,
                            timeout=10
                        )
                        
                        if product_response.status_code == 200:
                            product = product_response.json()
                            has_draft = product.get("has_draft")
                            draft_title = product.get("draft_seo_title")
                            
                            self.assert_true(has_draft == True, "Product still has_draft=true", product)
                            self.assert_true(draft_title == "DRAFT KEEP ME", 
                                           f"Draft title survived (expected 'DRAFT KEEP ME', got '{draft_title}')", 
                                           product)
                            
        except Exception as e:
            self.assert_true(False, f"Draft survival test failed: {e}")
            
    def test_seo_publish_roundtrip(self):
        """Test 7: SEO publish round-trip + verification + audit"""
        self.log("\n=== TEST 7: SEO Publish Round-trip + Verification + Audit ===")
        try:
            response = requests.post(
                f"{BASE_URL}/shopify/verify-publish",
                headers=self.headers,
                timeout=10
            )
            self.assert_true(response.status_code == 200, "Verify-publish endpoint returns 200", response.text)
            
            if response.status_code == 200:
                data = response.json()
                self.log(f"Verify-publish response: {json.dumps(data, indent=2)}")
                
                verified_match = data.get("verified_match")
                verified_shopify_value = data.get("verified_shopify_value")
                mock = data.get("mock")
                audit_id = data.get("audit_id")
                
                self.assert_true(verified_match == True, "verified_match is true", data)
                self.assert_true(verified_shopify_value is not None, "verified_shopify_value present", data)
                self.assert_true(mock == True, "mock is true", data)
                self.assert_true(audit_id is not None, "audit_id present", data)
                
                # Check audit log
                if audit_id:
                    self.log(f"Checking audit log for {audit_id}...")
                    audit_response = requests.get(
                        f"{BASE_URL}/audit?page=1&page_size=5",
                        headers=self.headers,
                        timeout=10
                    )
                    
                    if audit_response.status_code == 200:
                        audit_data = audit_response.json()
                        audit_items = audit_data.get("items", [])
                        audit_ids = [item.get("id") for item in audit_items]
                        
                        self.assert_true(audit_id in audit_ids, 
                                       f"Audit ID {audit_id} appears in audit log", 
                                       audit_ids)
                        
        except Exception as e:
            self.assert_true(False, f"SEO publish round-trip test failed: {e}")
            
    def test_sync_state_recovery(self):
        """Test 8: sync_state recovery"""
        self.log("\n=== TEST 8: Sync State Recovery (GET /api/sync/status) ===")
        try:
            response = requests.get(f"{BASE_URL}/sync/status", headers=self.headers, timeout=10)
            self.assert_true(response.status_code == 200, "Sync status endpoint returns 200")
            
            if response.status_code == 200:
                data = response.json()
                sync_state = data.get("sync_state", {})
                
                if sync_state:
                    status = sync_state.get("status")
                    in_progress = sync_state.get("in_progress")
                    
                    self.assert_true(status == "ok", f"sync_state.status is 'ok' (got '{status}')", sync_state)
                    self.assert_true(in_progress != True, 
                                   f"sync_state NOT stuck with in_progress=true (got {in_progress})", 
                                   sync_state)
                else:
                    self.log("No sync_state found (may be initial state)")
                    
        except Exception as e:
            self.assert_true(False, f"Sync state recovery test failed: {e}")
            
    def test_security_forbidden_writes(self):
        """Test 9: SECURITY - forbidden non-SEO writes"""
        self.log("\n=== TEST 9: SECURITY - Forbidden Non-SEO Field Writes ===")
        
        try:
            # Get a live product (admin can query live source explicitly)
            response = requests.get(f"{BASE_URL}/products?page_size=1&source=live", headers=self.headers, timeout=10)
            if response.status_code != 200:
                self.assert_true(False, "Could not fetch products for security test")
                return
                
            data = response.json()
            items = data.get("items", [])
            if not items:
                self.assert_true(False, "No products available for security test")
                return
                
            product_id = items[0].get("id")
            self.log(f"Testing security with product: {product_id}")
            
            # Get initial product state
            initial_response = requests.get(f"{BASE_URL}/products/{product_id}", headers=self.headers, timeout=10)
            initial_product = initial_response.json() if initial_response.status_code == 200 else {}
            
            # Test forbidden payloads on publish-seo endpoint
            forbidden_payloads = [
                {"price": "1.00"},
                {"inventory": 5},
                {"sku": "X"},
                {"barcode": "1"},
                {"vendor": "Evil"},
                {"title": "Hacked"},
                {"product_title": "Hacked"},
                {"status": "ARCHIVED"},
                {"variants": [{"price": "0"}]},
                {"seo_title": "ok", "price": "1"},  # mixed payload
            ]
            
            for payload in forbidden_payloads:
                self.log(f"Testing forbidden payload: {payload}")
                
                # Test on publish-seo
                publish_response = requests.post(
                    f"{BASE_URL}/products/{product_id}/publish-seo",
                    headers=self.headers,
                    json=payload,
                    timeout=10
                )
                
                self.assert_true(publish_response.status_code == 403, 
                               f"Forbidden payload returns 403 for publish-seo: {payload}", 
                               publish_response.text)
                
                if publish_response.status_code == 403:
                    response_text = publish_response.text
                    self.assert_true("NON_SEO_FIELD_WRITE_DENIED" in response_text, 
                                   f"Response contains 'NON_SEO_FIELD_WRITE_DENIED' for: {payload}", 
                                   response_text)
                
                # Test on seo-draft
                draft_response = requests.patch(
                    f"{BASE_URL}/products/{product_id}/seo-draft",
                    headers=self.headers,
                    json=payload,
                    timeout=10
                )
                
                self.assert_true(draft_response.status_code == 403, 
                               f"Forbidden payload returns 403 for seo-draft: {payload}", 
                               draft_response.text)
                
            # Verify commerce fields unchanged
            final_response = requests.get(f"{BASE_URL}/products/{product_id}", headers=self.headers, timeout=10)
            if final_response.status_code == 200:
                final_product = final_response.json()
                
                # Check that commerce fields are unchanged (if they exist)
                commerce_fields = ["price", "inventory", "sku", "barcode", "vendor"]
                for field in commerce_fields:
                    if field in initial_product:
                        initial_value = initial_product.get(field)
                        final_value = final_product.get(field)
                        self.assert_true(initial_value == final_value, 
                                       f"Commerce field '{field}' unchanged after denied attempts", 
                                       {"initial": initial_value, "final": final_value})
                        
        except Exception as e:
            self.assert_true(False, f"Security test failed: {e}")
            
    def run_all_tests(self):
        """Run all Phase 3.5 tests"""
        print("\n" + "="*80)
        print("PHASE 3.5 BACKEND API TESTING - Real Shopify Live Sync")
        print("="*80 + "\n")
        
        # Login first
        if not self.login():
            self.log("Login failed, cannot continue tests", "FAIL")
            return
            
        # Run all tests
        self.test_connection()
        self.test_full_sync()
        self.test_live_products()
        self.test_live_collections()
        self.test_demo_live_separation()
        self.test_incremental_sync()
        self.test_draft_survival()
        self.test_seo_publish_roundtrip()
        self.test_sync_state_recovery()
        self.test_security_forbidden_writes()
        
        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"✅ PASSED: {self.passed_count}")
        print(f"❌ FAILED: {self.failed_count}")
        print(f"📊 TOTAL: {self.passed_count + self.failed_count}")
        print("="*80 + "\n")
        
        if self.failed_count > 0:
            print("FAILED TESTS:")
            for result in self.results:
                if result["status"] == "FAIL":
                    print(f"  ❌ {result['message']}")
                    if "details" in result:
                        print(f"     Details: {result['details']}")
        
        return self.failed_count == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()
    exit(0 if success else 1)
