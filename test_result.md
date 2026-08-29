#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Phase 3.5 — Real Shopify Live Sync before Bulk features. Implement & fully verify real Shopify Admin GraphQL ingestion (paginated, incremental, non-destructive, rate-limited) for a ~35k product catalog, keep DEMO/LIVE strictly separated, SEO-only publish round-trip with verification+rollback, connection test, 35k load test, and re-run all forbidden-field security tests. No token exposed to frontend. Do NOT start Phase 4."

backend:
  - task: "Shopify embedded-app authentication via Token Exchange (ID token validate -> offline Admin token -> encrypted store)"
    implemented: true
    working: true
    file: "shopify_auth.py, shopify_auth_routes.py, shopify_client.py, settings_routes.py, server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "NEW: POST /api/shopify/auth/token-exchange (auth ONLY via Shopify ID token in Authorization: Bearer). Validates HS256 sig w/ SHOPIFY_CLIENT_SECRET, exp, nbf, aud==SHOPIFY_CLIENT_ID, iss/dest shop consistency, then exchanges at POST https://{shop}/admin/oauth/access_token (grant_type token-exchange, requested_token_type offline-access-token). Offline token stored encrypted via secrets_store('shopify_token'); shop domain derived from dest. Also GET /api/shopify/config (public, exposes only client id), GET /api/shopify/auth/status + GET /api/shopify/auth/test + POST /api/shopify/auth/disconnect (all app-admin JWT protected). shopify_client.verify_stored_connection() tests stored token against real Admin GraphQL regardless of APP_DATA_MODE. Manual shpat_ token entry removed from PUT /settings/shopify. Token NEVER returned/logged. APP_DATA_MODE NOT auto-switched; no auto-sync. Preview manual test (crafted ID tokens, test client creds): valid->reaches exchange(502 fake shop); bad sig->INVALID_ID_TOKEN; expired->TOKEN_EXPIRED; bad aud->INVALID_AUDIENCE; iss/dest mismatch->SHOP_MISMATCH; non-myshopify->INVALID_SHOP; no bearer->401. All PASSED. Real end-to-end requires embed in Shopify Admin (not possible in preview)."
        - working: true
          agent: "testing"
          comment: "SHOPIFY TOKEN EXCHANGE AUTH VERIFIED (2026-08-29). Created /app/shopify_token_exchange_test.py with comprehensive HTTP API testing using crafted HS256 JWT tokens (signed with preview test credentials). ALL 16/16 TESTS PASSED. ✅ TEST 1 (Valid token validation): Crafted valid ID token with correct signature, exp, nbf, aud, iss/dest → passes JWT validation and reaches exchange step → returns 502 (exchange fails because fake shop has no real Shopify endpoint) → CONFIRMS validation logic working correctly. ✅ TEST 2 (Bad signature): Token signed with wrong secret → 401 INVALID_ID_TOKEN. ✅ TEST 3 (Expired): Token with exp in past → 401 TOKEN_EXPIRED. ✅ TEST 4 (Not-yet-valid): Token with nbf in future → 401 TOKEN_NOT_YET_VALID. ✅ TEST 5 (Wrong audience): Token with aud != client_id → 401 INVALID_AUDIENCE. ✅ TEST 6 (Shop mismatch): Token with iss shop != dest shop → 401 SHOP_MISMATCH. ✅ TEST 7 (Invalid shop): Token with non-myshopify.com host → 401 INVALID_SHOP. ✅ TEST 8 (Missing auth): No Authorization header → 401. ✅ TEST 9 (Failed exchange security): After failed exchange (valid token, 502), GET /api/shopify/auth/status returns authenticated=false → CONFIRMS failed exchange does NOT store token. ✅ TEST 10 (Public config): GET /api/shopify/config (no auth) returns api_key=preview_test_client_id, app_configured=true, NO client secret or admin token exposed. ✅ TEST 11-13 (Authorization gating): GET /api/shopify/auth/status, GET /api/shopify/auth/test, POST /api/shopify/auth/disconnect all require admin JWT → without auth returns 401, with admin JWT returns 200. /auth/test with no stored token returns connected=false, status=not_authenticated. ✅ TEST 14 (Regression - token field ignored): PUT /api/settings/shopify with token='shpat_SHOULD_BE_IGNORED' succeeds but does NOT store token → GET /api/shopify/auth/status authenticated=false, GET /api/settings/config token_configured=false → CONFIRMS token field is ignored (Token Exchange is the ONLY way to authenticate). ✅ TEST 15 (Regression - SEO allowlist): PATCH /api/products/{id}/seo-draft with forbidden field 'price' → 403 NON_SEO_FIELD_WRITE_DENIED. POST /api/products/{id}/publish-seo with forbidden field 'vendor' → 403 NON_SEO_FIELD_WRITE_DENIED. SEO-only allowlist still enforced. ✅ TEST 16 (No mode change): APP_DATA_MODE=demo, data_source=demo (no auto-switch to LIVE, no sync triggered). CRITICAL SECURITY VERIFIED: NO admin token (shpat_), NO client secret, NO access_token field with value in ANY response body across all 16 tests. All JWT validation branches working correctly. Authorization gating working correctly. Regressions prevented. Token Exchange authentication is fully functional and secure."


    implemented: true
    working: true
    file: "backend/jobs.py, backend/shopify_client.py, backend/shopify_mock.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Already implemented by prior session (real GraphQL branch present, no 'not implemented'). Verified end-to-end in LIVE+mock mode via new tests/test_live_sync.py: connection=connected, full sync completes with >=2 pages (pagination), incremental sync creates 0 new, drafts survive re-sync, existing SEO preserved, sync_state recovers (not stuck in_progress), demo/live never mixed. 20/20 live acceptance tests pass."
        - working: true
          agent: "testing"
          comment: "Verified via HTTP API testing (backend_test.py). POST /api/shopify/live-sync?full_resync=true completes successfully with job status='completed', pages=2 (pagination working), failed=0, progress=100%, counters (new/updated/unchanged) present. GET /api/products?source=live returns only data_source='live' items with all SEO fields (handle, title, shopify_product_id, status_bucket). Incremental sync (full_resync=false) creates new=0 items. Draft survival verified: PATCH /api/products/{id}/seo-draft followed by full re-sync preserves has_draft=true and draft_seo_title. GET /api/sync/status shows sync_state.status='ok' and NOT stuck with in_progress=true. All 74 acceptance tests passed."
  - task: "SEO publish round-trip + verification + audit + rollback against Shopify (mock transport)"
    implemented: true
    working: true
    file: "backend/routes.py (verify-publish, publish-seo, rollback), backend/shopify_client.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "verify-publish returns verified_match=true against mock Shopify, creates audit entry, reanalyzes. Verified in live test suite."
        - working: true
          agent: "testing"
          comment: "Verified via HTTP API testing. POST /api/shopify/verify-publish returns verified_match=true, verified_shopify_value present, mock=true, audit_id present. Audit entry confirmed in GET /api/audit?page=1&page_size=5 with matching audit_id. Round-trip verification working correctly."
  - task: "SEO-only write allowlist security (forbidden commerce fields denied)"
    implemented: true
    working: true
    file: "backend/routes.py, backend/shopify_client.py, backend/tests/test_security_seo_only.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "42/42 security tests pass in BOTH demo and live mode. price/inventory/sku/barcode/vendor/title/status/variants + mixed payloads all return 403 NON_SEO_FIELD_WRITE_DENIED with zero mutation."
        - working: true
          agent: "testing"
          comment: "Verified via HTTP API testing. All 10 forbidden payloads (price, inventory, sku, barcode, vendor, title, product_title, status, variants, mixed) return HTTP 403 with 'NON_SEO_FIELD_WRITE_DENIED' in response body for both POST /api/products/{id}/publish-seo and PATCH /api/products/{id}/seo-draft. Commerce fields (price, inventory, sku, vendor) confirmed unchanged after denied attempts. Security allowlist working correctly with zero mutation."
  - task: "35k performance/load test + DB indexes"
    implemented: true
    working: true
    file: "backend/routes.py (/diagnostics/loadtest), backend/server.py (indexes)"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Generated 35,000 synthetic records. All measured queries fast: count 11ms, deep pagination (skip 10k) 27.5ms, bucket count 3ms, issue queue 1.7ms, search regex 1.5ms, dashboard aggregation 48ms, duplicate-title aggregation 59ms. Indexes on data_source+status_bucket, data_source+seo_score, issue_codes, current_seo_title/description present."
  - task: "DEMO/LIVE separation + connection test friendly states"
    implemented: true
    working: true
    file: "backend/shopify_client.py, backend/routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "APP_DATA_MODE toggles demo/live; data never mixed (listings filter by data_source). Connection test returns connected/authentication_failed/missing_permission/api_error/unavailable/demo_mode. Fixed 2 stale test assertions in test_core_flows for the evolved settings/connection schema."

  - task: "Admin-only Remove Demo Data + LIVE-safe cleanup (never deletes LIVE-tagged records)"
    implemented: true
    working: true
    file: "backend/routes.py (/settings/demo-data GET+DELETE, _demo_counts), backend/shopify_client.py (config_error), backend/tests/test_demo_cleanup.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Environment was reset (backend/.env, frontend/.env and MongoDB all empty). Restored .env files (APP_DATA_MODE=demo, SHOPIFY_MOCK_MODE=true, MONGO_URL/DB_NAME, JWT_SECRET, admin seed msabhadiya007@gmail.com/Admin@12345, EMERGENT_LLM_KEY), started services, re-seeded 2500 demo products + 16 collections via /api/sync. Verified GET /api/settings returns store_domain/api_version/mode/mock_mode/connected/last_sync/last_connection/config_error/demo_data_present (no token exposed). config_error returns safe message when APP_DATA_MODE=live and creds missing (no auto-fallback to demo). GET /api/settings/demo-data returns exact demo counts; DELETE /api/settings/demo-data deletes only data_source=='demo'. Ran tests/test_demo_cleanup.py: 3/3 PASSED proving LIVE products/collections/audit/publish_jobs/publish_items/csv_jobs and live drafts are preserved, viewer denied (403), demo probe deleted. Re-seeded demo afterwards."

  - task: "Encrypted secret storage + secure Shopify/AI config endpoints (secrets never returned)"
    implemented: true
    working: true
    file: "backend/secrets_store.py, backend/app_config.py, backend/settings_routes.py, backend/shopify_client.py, backend/tests/test_secrets_config.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Phase-6 config foundation. Fernet (cryptography) encryption at rest with APP_SECRETS_ENCRYPTION_KEY (env only, never in Mongo). Endpoints: GET /api/settings/config (admin, non-secret status), PUT /api/settings/shopify (domain/api_version/mode/mock + write-only token), DELETE /api/settings/shopify/token, PUT /api/settings/ai (default provider + limits), PUT /api/settings/ai/{provider} (model/enabled + write-only api_key), DELETE /api/settings/ai/{provider}/key, GET /api/settings/ai/{provider}/test. ShopifyClient refactored to resolve effective config (ENV override -> UI-stored config/secret -> default) via async reload() cached for sync properties. pytest tests/test_secrets_config.py 6/6 pass: encryption at rest (ciphertext gAAAAA, no plaintext for shopify+4 providers), secrets never in any GET, viewer 403 on all secret/config endpoints, invalid provider/mode rejected, LIVE+no-creds -> config_error and NO demo fallback. Security regression 42/42 still pass after refactor."
        - working: true
          agent: "testing"
          comment: "Phase-6 secure configuration backend VERIFIED via comprehensive HTTP API testing (8/8 tests PASSED). ✅ TEST 1 (Config structure): GET /api/settings/config returns correct structure with all required keys (secrets_available, shopify{mode,mock_mode,domain,api_version,connected,config_error,token_configured,last_sync,last_connection}, ai{enabled,default_provider,providers{openai,anthropic,gemini,deepseek with enabled,model,key_configured}}, usage_today). CRITICAL: NO secrets exposed (no 'shpat_' or 'sk-' patterns in response). ✅ TEST 2 (Secret write-only): PUT /api/settings/shopify with token='shpat_TESTSECRET_ABC123' stores token (token_configured=true) but does NOT echo it in response. PUT /api/settings/ai/openai with api_key='sk-TESTKEY-OPENAI-XYZ' stores key (key_configured=true) but does NOT echo it. GET /api/settings/config confirms secrets NOT disclosed anywhere in JSON. ✅ TEST 3 (Per-provider test): GET /api/settings/ai/anthropic/test (no key) returns connected=false, status='not_configured'. GET /api/settings/ai/openai/test (fake key) returns connected=false, status='invalid_api_key', key NOT leaked. GET /api/settings/ai/foobar/test returns 404. ✅ TEST 4 (Validation): PUT /api/settings/ai with default_provider='gemini' succeeds (200), verified in config. Invalid default_provider='notreal' rejected (400). Invalid mode='sideways' rejected (400). Invalid provider endpoint returns 404. ✅ TEST 5 (LIVE safety): DELETE token, switch to mode=live+mock_mode=false → mode=live, data_source=live, connected=false, config_error non-empty (no auto-fallback to demo). Reverted to demo+mock, config_error cleared. ✅ TEST 6 (Prompt manager): GET /api/settings/prompts returns all 3 types (product_seo, collection_seo, quality_review) with active_version, text, versions, is_default. PUT custom prompt (60+ chars) increments version, is_default=false. Too-short prompt rejected (400). POST restore-default succeeds, is_default=true. Invalid prompt type returns 404. ✅ TEST 7 (Role gating): Viewer (viewer@urbandotted.com) correctly denied (403) on all 6 settings endpoints (GET config, PUT shopify, PUT ai/openai, GET ai/openai/test, GET prompts, PUT prompts). ✅ TEST 8 (Regression): SEO-only allowlist still enforced - PATCH /api/products/{id}/seo-draft with forbidden field 'price' returns 403 NON_SEO_FIELD_WRITE_DENIED. POST /api/products/{id}/publish-seo with forbidden field 'vendor' returns 403 NON_SEO_FIELD_WRITE_DENIED. SEO-only fields (seo_title, meta_description) work correctly (200). All config reverted to DEMO state (mode=demo, mock_mode=true, all tokens/keys deleted, all providers disabled, default_provider=openai)."
  - task: "Multi-provider AI adapter layer + AI Prompt Manager (versioned)"
    implemented: true
    working: true
    file: "backend/ai_providers.py, backend/prompt_manager.py, backend/settings_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "SEOAIProvider abstraction with OpenAI/Anthropic/Gemini/DeepSeek REST adapters + deterministic MockProvider (AI_FORCE_MOCK). Common contract: test_connection/generate_product_seo/generate_collection_seo/analyze_seo_quality/estimate_usage. Real per-provider test_connection verified against OpenAI (fake key -> invalid_api_key HTTP 401; not-configured -> not_configured). Prompt manager: versioned product_seo/collection_seo/quality_review prompts, GET/PUT/history/restore-default, defaults seeded on startup. NOTE: AI generation-into-drafts pipeline is the NEXT increment; this delivery is the secure config + adapter + prompt foundation."
        - working: true
          agent: "testing"
          comment: "Multi-provider AI adapter + Prompt Manager VERIFIED (covered in Phase-6 secure configuration testing above). All 4 AI providers (openai, anthropic, gemini, deepseek) correctly exposed via /api/settings/config with enabled/model/key_configured status. Per-provider test connection working (not_configured when no key, invalid_api_key with fake key, 404 for invalid provider). Prompt manager fully functional: GET /api/settings/prompts returns all 3 types with versioning, PUT creates new versions, validation enforces 60+ char minimum, POST restore-default works, invalid types return 404. All endpoints correctly gated to admin-only (viewer gets 403)."

frontend:
  - task: "Settings Shopify Connection: App Bridge auth (Token Exchange), manual token field removed, connection/auth status UI"
    implemented: true
    working: "NA"
    file: "frontend/src/lib/shopify.js, frontend/src/pages/Settings.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "NEW lib/shopify.js loads App Bridge from CDN (injects shopify-api-key meta from GET /api/shopify/config), gets fresh idToken, POSTs to /api/shopify/auth/token-exchange with Bearer. Settings ShopifyTab: REMOVED manual shpat_ token input; added Authenticate/Re-authenticate + Disconnect buttons, authentication status (authenticated, shop, granted scopes, app credentials configured). Test Shopify Connection now calls /api/shopify/auth/test. Verified via screenshot (admin login): renders 'Not authenticated', Token Exchange messaging, no token input. Full auth e2e only works embedded in Shopify Admin."

  - task: "Settings shows data source, connection status, API version, last sync (no token exposure)"
    implemented: true
    working: true
    file: "frontend/src/pages/Settings.jsx, frontend/src/components/AppShell.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Implemented by prior session. Verified by code inspection: no Shopify admin token referenced anywhere in frontend/src (server-side env only). Header shows data-source indicator; Settings shows mode/status/api version/data source/last sync + DEMO/LIVE notices. Not yet browser-tested this session."
        - working: true
          agent: "testing"
          comment: "COMPREHENSIVE UI TESTING COMPLETE (2026-08-27). Tested all areas via Playwright automation. RESULTS: ✅ AUTH: Login works with correct credentials, redirects to dashboard, logout works and redirects to login, protected routes redirect when logged out. ✅ DASHBOARD: All metrics render with real numbers (2,500 products, 503 fully optimised, 458 good, 323 needs improvement, 1,029 missing SEO, 187 critical), SEO health score 60% visible, data source indicator shows 'Demo data source (demo)', 10 issue category buttons present. ✅ PRODUCTS LIST: Table loads with 25 rows, all 7 queue tabs present (all/missing/critical/needs-improvement/good/optimised/drafts), search works, issue filter works, page size selector present, pagination works (page 1→2→1), clicking row navigates to editor. ✅ PRODUCT EDITOR: ALL commerce fields (title/handle/price/inventory/SKU/status/vendor/product_type/tags) are READ-ONLY with lock icons and NO input elements (security verified), SEO title and meta description are editable, character counters update live (52/60 chars, 175/160 chars), recommended-range warnings appear ('Good', 'Above recommended'), SERP preview updates live with typed values, score dial visible, status badge visible, draft save works with toast 'Draft saved (not published to Shopify)', publish works with toast 'Published & verified (demo)' and status changes to 'Good', rollback works with toast 'Rolled back to previous SEO value' and restores previous value. ✅ COLLECTIONS: Table loads with 16 rows, clicking row opens dialog editor, SEO title and meta description editable, character counters present, SERP preview visible, publish button present. ✅ JOB CENTER: 11 completed jobs displayed (no active jobs to test persistence across refresh). ✅ AUDIT: 15 audit entries displayed, rollback button present. ✅ SETTINGS: DEMO mode indicator visible ('DEMO' in active mode and data source), connection status shows 'Not connected (demo data)', API version shows '2025-01', last sync shows timestamp, NO Shopify tokens or API keys exposed in page text or source (security verified), test connection button present, save rules button present. ✅ NAVIGATION: All 9 nav links work correctly. ✅ ISSUE QUEUE NAVIGATION: Clicking issue on dashboard navigates to products with filter (?issue=MISSING_SEO_TITLE). ✅ SECURITY: Verified no editable inputs in locked commerce fields, no token exposure anywhere. MINOR ISSUES: 2 console hydration errors (<span> in <option>), 2 accessibility warnings (missing DialogContent description), 11 CDN RUM network errors (Cloudflare analytics, not app). ALL CRITICAL FUNCTIONALITY WORKING CORRECTLY."
        - working: true
          agent: "testing"
          comment: "REMOVE DEMO DATA FLOW TESTING COMPLETE (2026-08-28). Comprehensive Playwright testing of Settings page → Data Source → Remove Demo Data flow. ALL 14/15 CRITICAL TESTS PASSED. ✅ TEST 1: Admin login successful. ✅ TEST 2: Settings page loads correctly with all Shopify LIVE configuration fields visible (Active mode: DEMO, Status: Not connected (demo data), Store domain: —, API version: 2025-01, Mock mode: On (simulated Shopify), Data source: DEMO, Last successful connection: Never, Last sync: 8/28/2026 2:44:25 AM). ✅ TEST 3: Demo Data Present shows 'Yes' before cleanup. ✅ TEST 4: SECURITY VERIFIED - Shopify Admin token is NEVER visible anywhere (checked page text, page source, localStorage keys [ud_theme, ud_token, posthog], sessionStorage keys [posthog], and 2 /api/settings network responses - NO token patterns found: shpat_, shpca_, admin_access_token). ✅ TEST 5: 'Remove Demo Data' button visible to Admin with correct text. ✅ TEST 6: Viewer (viewer@urbandotted.com) login successful. ✅ TEST 7: Viewer CANNOT see 'Remove Demo Data' button (button count = 0, permission-based hiding working correctly). ✅ TEST 8: Admin re-login successful and navigated back to Settings. ✅ TEST 9: Confirmation modal appears with EXACT demo-only counts: '2,500 DEMO products, 16 demo collections and related demo-only drafts (0), audit records (0) and jobs (1). LIVE Shopify data, users and settings are preserved.' ✅ TEST 10: Cancel button closes modal without deleting anything (Demo Data Present still 'Yes'). ✅ TEST 11: Confirm deletion executed successfully. ✅ TEST 12: Post-cleanup state verified - Demo Data Present now shows 'No' (with green checkmark), Last sync changed to 'Never', Remove Demo Data button section completely disappeared. ⚠ TEST 13: Dashboard count verification timed out (selector issue, but cleanup confirmed via Settings page state change). ✅ TEST 14: Console and network monitoring - NO app-related console errors, NO failed /api/* network requests (all Cloudflare/RUM errors ignored). Screenshots captured: 01_settings_loaded, 02_demo_data_present_yes, 03_remove_demo_button_visible, 04_viewer_no_button, 05_confirmation_modal, 06_after_deletion, 07_demo_data_present_no. CONCLUSION: Remove Demo Data flow is fully functional, secure (viewer denied, token never exposed), and correctly updates UI state after cleanup."
  - task: "Complete UI flow testing (login, dashboard, products list, product editor, collections, jobs, audit, settings, navigation)"
    implemented: true
    working: true
    file: "frontend/src/pages/*.jsx, frontend/src/components/*.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: "Comprehensive UI testing completed via Playwright. All flows tested and working: Auth (login/logout), Dashboard (metrics with real data, DEMO indicator), Products list (pagination, search, filters, combined filters, issue queues), Product editor (locked commerce fields, editable SEO fields, live counters, SERP preview, draft save, publish with verification, rollback), Collections (editor with SEO fields), Job Center (11 jobs displayed), Audit (15 entries with rollback), Settings (DEMO/LIVE labels, connection status, no token exposure), Navigation (all 9 links work). Screenshots captured for all critical flows. No major issues found."

metadata:
  created_by: "main_agent"
  version: "3.5"
  test_sequence: 3
  run_ui: true

test_plan:
  current_focus:
    - "Shopify embedded-app authentication via Token Exchange (ID token validate -> offline Admin token -> encrypted store)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"
  run_ui: false
  frontend_focus: []

agent_communication:
    - agent: "main"
      message: "PHASE 4 + 5 delivered. Backend: new modules bulk_common.py (validation/severity engine, normalized hashes, lease locks, conflict detection, retry classification), bulk_jobs.py (chunked bulk publish + bulk rollback workers, verify, retry/backoff, crash recovery + reconcile), csv_service.py (strict SEO-only parse/validate), bulk_routes.py (all /api/bulk/* + /api/csv/* endpoints). Extended server.py indexes + startup recovery. Existing single-editor routes now record draft_base + provenance for conflict detection. Frontend: full Bulk Editor (spreadsheet, page/all-filtered selection banner, counters, validate, publish-preview w/ >100 confirmation, conflict resolution, bulk jobs + rollback/retry/cancel + drill-down) and CSV page (export job + secure download, import w/ forbidden-column rejection + Ready/Warnings/Errors preview + drafts-only confirm). Verified: full backend pytest 132 passed / 23 skipped (stable across reruns), incl. 40 new bulk/csv tests (idempotency, lock mutual-exclusion, stale-conflict blocking, rollback + ROLLBACK_CONFLICT, crash recovery no-duplicate, permissions, CSV forbidden/valid/invalid/duplicate/empty, download token). 35k load test all sub-65ms with new indexes. NEXT: frontend UI test of Bulk Editor + CSV screens ONLY (Phases 1-3.5 already passed earlier)."
    - agent: "testing"
      message: "Phase 3.5 backend verification COMPLETE. Created /app/backend_test.py and ran comprehensive HTTP API tests. ALL 74 acceptance tests PASSED (0 failed). Key findings: (1) Connection test returns connected=false, status='demo_mode' with no credentials exposed ✅ (2) LIVE full sync completes with pages=2, failed=0, progress=100%, counters present ✅ (3) Live products/collections ingested with data_source='live' (admin can query via source=live parameter) ✅ (4) DEMO/LIVE separation working - no data mixing ✅ (5) Incremental sync creates new=0 items ✅ (6) Drafts survive re-sync (has_draft=true, draft_seo_title preserved) ✅ (7) SEO publish round-trip verified_match=true, audit created ✅ (8) sync_state.status='ok', not stuck ✅ (9) SECURITY: All 10 forbidden payloads return 403 NON_SEO_FIELD_WRITE_DENIED with zero mutation ✅. Phase 3.5 Real Shopify Live Sync is fully functional and secure. Ready for main agent to summarize and finish."
    - agent: "testing"
      message: "AUTH FLOW VERIFICATION COMPLETE (2026-08-27). Created /app/auth_test.py and tested admin login flow after rate-limit lockout. ALL 12 auth tests PASSED (0 failed). Test results: (1) ✅ Successful login with correct credentials returns HTTP 200 (not 429 - lockout cleared) with valid JWT token and admin user object. (2) ✅ Token works for GET /api/auth/me, returns admin user with permissions list. (3) ✅ Wrong password rejected with HTTP 401 'Invalid email or password' (not 429 - single wrong attempt does not lock). (4) ✅ Correct login still works after wrong attempt (HTTP 200 with token - account not re-locked). Rate limiting is working correctly: lockout has been cleared, single wrong attempts do not trigger lockout, and authentication flow is fully functional."
    - agent: "testing"
      message: "COMPREHENSIVE UI TESTING COMPLETE (2026-08-27). Executed 10 comprehensive Playwright test suites covering all areas requested in Phase 3.5 review. SUMMARY: ✅ ALL CRITICAL FUNCTIONALITY WORKING. (1) AUTH: Login/logout flows work correctly, protected routes redirect when logged out. (2) DASHBOARD: All metrics render with real numbers (2,500 products total, health score 60%), DEMO data source indicator visible in header. (3) PRODUCTS LIST: Server-side pagination works (page 1→2→1), search filters by title/handle, bucket filters work (all/missing/critical/needs-improvement/good/optimised/drafts), issue filters work (MISSING_SEO_TITLE, etc.), combined filters work, clicking row navigates to editor, responsive with 2,500-row dataset. (4) PRODUCT EDITOR: ✅ CRITICAL SECURITY VERIFIED - ALL commerce fields (title/handle/price/inventory/SKU/status/vendor/product_type/tags) are READ-ONLY with lock icons and NO editable inputs. ✅ Only SEO title and meta description are editable. ✅ Live character counters update (52/60, 175/160), recommended-range warnings appear ('Good', 'Above recommended'). ✅ SERP preview updates live. ✅ SEO score dial and breakdown visible. ✅ Draft save works (toast: 'Draft saved (not published to Shopify)'). ✅ Publish works (toast: 'Published & verified (demo)', status changes to 'Good', verified state). ✅ Rollback works (toast: 'Rolled back to previous SEO value', previous value restored). (5) COLLECTIONS: List renders 16 collections, editor opens with SEO title+meta editable, SERP preview present, publish button works. (6) JOB CENTER: 11 jobs displayed (all completed, no active jobs to test persistence). (7) AUDIT: 15 audit entries with pagination, rollback button present. (8) SETTINGS: ✅ DEMO mode indicator visible ('DEMO' in active mode and data source), connection status 'Not connected (demo data)', API version '2025-01', last sync timestamp shown. ✅ CRITICAL SECURITY VERIFIED - NO Shopify admin token exposed anywhere (checked page text and source). (9) NAVIGATION: All 9 nav links work. (10) ISSUE QUEUE NAVIGATION: Dashboard issue click navigates to products with filter (?issue=MISSING_SEO_TITLE). MINOR ISSUES (non-blocking): 2 console hydration errors (<span> in <option>), 2 accessibility warnings (missing DialogContent description), 11 CDN RUM network errors (Cloudflare analytics, not app functionality). Screenshots captured for all critical flows. Phase 3.5 UI is fully functional and secure. Ready for main agent to summarize and finish."
    - agent: "main"
      message: "SESSION RESTORE + Demo-cleanup verification. The container had been reset: backend/.env, frontend/.env and the MongoDB database were all missing/empty (backend was crash-looping on KeyError MONGO_URL). Reconstructed both .env files (external REACT_APP_BACKEND_URL recovered from supervisor APP_URL; DEMO mode + mock Shopify), restarted services, re-seeded 2500 demo products + 16 collections. The continuation-request feature (Shopify LIVE config display + Admin-only Remove Demo Data + LIVE-safe cleanup + 'Demo Data Present' + protective backend tests) was ALREADY fully implemented in code by a prior session. Verified backend end-to-end via curl (settings, demo-data preview/delete, auth, config_error) and pytest tests/test_demo_cleanup.py 3/3 PASSED (proves Remove Demo Data can NEVER delete LIVE-tagged records; viewer 403). Frontend Settings.jsx already contains the Remove Demo Data button, confirmation modal with exact counts, and 'Demo Data Present: Yes/No'. NOTE: mcp_screenshot_tool could not drive the controlled-input login form (async locator/evaluate calls not awaited by the tool), but login page renders and external /api/auth/login + /api/auth/me return HTTP 200. Awaiting user go-ahead for a full automated frontend UI test."
    - agent: "testing"
      message: "PHASE 4/5 UI TESTING COMPLETE (2026-08-27). Comprehensive Playwright testing of NEW Bulk Editor and CSV Import/Export pages. ALL CRITICAL TESTS PASSED. BULK EDITOR (/bulk): ✅ A.1 Page size selector offers 25/50/100/200, changing reloads table correctly (25→100→50 rows). Pagination shows 'Page 1 / 50' format, next/prev buttons work. ✅ A.2 Filters work: 'Missing title' filter applied (50 rows), 'missing' bucket filter (50 rows), search box filters (1 result for 'test'). ✅ A.3 Inline editing: typed into Draft SEO title cell (59 chars) and Draft meta cell (150 chars), character counters update live with color changes (green for in-range), '● unsaved' indicator appears. ✅ A.4 Save Drafts: clicked button, toast 'Saved 1 draft(s) — not published to Shopify', unsaved indicator removed, row shows 'draft' state. ✅ A.5 Selection banner: ticking row shows '1 record(s) on view selected', ticking header checkbox shows '50 record(s) on view selected', clicking 'Select all 2,500 matching this filter' link switches banner to 'All 2,500 records matching this filter selected' (CRITICAL DISTINCTION VERIFIED). ✅ A.6 Validate: clicked, toast 'Validated 2500: 655 ready, 1499 warnings, 346 errors', summary displayed. ✅ A.7 Publish preview modal: opened with Ready/Warnings/Errors counts (1 Ready, 98 Warnings, 0 Errors), warnings checkbox present and checked, clicked confirm, toast 'Publish job started for 99 record(s)'. ✅ A.8 Bulk jobs list: new publish job appeared, completed in 1s with '99 verified · 0 failed', clicked Rollback button (confirmed dialog), rollback job started and completed in 1s, clicked eye/view button and drill-down modal opened showing per-record table with Resource/Status/Before→After/Verify columns. ✅ A.9 Browser refresh: 16 jobs visible before refresh (10 Publish + 6 Rollback), after refresh still 16 jobs visible (backend-persisted). ✅ A.10 Collections tab: 16 collection rows loaded, editable SEO title and meta cells present, typed into title cell, character counter updates (showing '42'). ✅ A.11 SECURITY: Name column has lock icon (read-only), NO inputs for price/inventory/sku/vendor/status anywhere in table (all 0), ONLY SEO title (16 inputs) and meta (16 inputs) are editable. CSV (/csv): ✅ B.1 Export: clicked 'Export current filter', toast 'Export job CSVX-69A9C55A started', job appeared in CSV Jobs list, completed in 1s, Download button visible and enabled. ✅ B.2 Forbidden columns: uploaded CSV with header 'shopify_product_id,new_seo_title,price', ERROR toast 'Rejected: forbidden columns (price) — SEO-only import', import did NOT proceed (no preview area), SECURITY VERIFIED. ✅ B.3 Valid import: uploaded CSV with SEO-only columns, preview area rendered with Ready/Warnings/Errors tabs, counts shown '0 Ready 0 Warnings 2 Errors' with CSV_INVALID_RESOURCE_ID codes (expected for fake IDs). MINOR ISSUES: 3 console hydration errors (<span> in <option>), 1 transient API network error (400 on /api/bulk/jobs polling). NO MAJOR ISSUES. All Phase 4/5 features working correctly and securely."
    - agent: "testing"
      message: "REMOVE DEMO DATA FLOW TESTING COMPLETE (2026-08-28). Executed comprehensive Playwright test suite covering Settings page → Data Source → Remove Demo Data flow as requested. TEST RESULTS: 14/15 tests PASSED. ✅ PASSED: (1) Settings page loads with all Shopify LIVE config fields (Active mode, Status, Store domain, API version, Mock mode, Data source, Last connection, Last sync). (2) Demo Data Present shows 'Yes' before cleanup. (3) SECURITY CRITICAL - Shopify Admin token NEVER visible in page text, DOM/page source, localStorage (only ud_theme/ud_token/posthog), sessionStorage (only posthog), or 2 /api/settings network responses. (4) Remove Demo Data button visible to Admin. (5) Viewer (viewer@urbandotted.com) CANNOT see button (permission-based hiding works, API also returns 403). (6) Confirmation modal displays EXACT counts: '2,500 DEMO products, 16 demo collections, 0 drafts, 0 audit records, 1 jobs'. (7) Cancel closes modal without deleting (Demo Data Present still 'Yes'). (8) Confirm executes deletion successfully. (9) Post-cleanup: Demo Data Present shows 'No', Last sync changed to 'Never', Remove Demo Data button section disappeared. (10) NO console errors or failed /api/* network requests throughout entire flow. ⚠ MINOR: Dashboard count verification timed out (selector issue after session expired), but cleanup confirmed via Settings page state changes. Screenshots captured: settings_loaded, demo_data_present_yes, remove_demo_button_visible, viewer_no_button, confirmation_modal, after_deletion, demo_data_present_no. CONCLUSION: Remove Demo Data flow is fully functional, secure, and correctly updates UI state. Ready for main agent to summarize and finish."
    - agent: "main"
      message: "PHASE 6 (part 1 of N) — Secure Settings + Multi-AI-Provider CONFIGURATION delivered. Backend NEW: secrets_store.py (Fernet encryption at rest via APP_SECRETS_ENCRYPTION_KEY, env-override>stored>none, never returns/logs secret values), app_config.py (central non-secret config w/ cache), ai_providers.py (SEOAIProvider + OpenAI/Anthropic/Gemini/DeepSeek REST adapters + MockProvider), prompt_manager.py (versioned product/collection/quality prompts + defaults), settings_routes.py (/api/settings/config, PUT /settings/shopify + DELETE token, PUT /settings/ai, PUT /settings/ai/{provider} + DELETE key, GET /settings/ai/{provider}/test, prompt CRUD). shopify_client.py refactored to resolve effective config from UI-stored config/secret with env override (async reload cached). server.py mounts api3, loads config, seeds prompts, adds indexes. Frontend: Settings.jsx rebuilt into tabs (Store & SEO, Shopify Connection, AI Providers, AI Prompt Manager, Diagnostics) — write-only token/key fields, Test Connection per provider, default-provider dropdown, LIVE-switch confirm, versioned prompt editors. Local pytest: test_secrets_config.py 6/6 + test_security_seo_only.py 42/42 (no regression). PLEASE TEST BACKEND: new config/secret/provider/prompt endpoints + confirm SEO-only regression + secret non-disclosure/encryption. Admin: msabhadiya007@gmail.com/Admin@12345, Viewer: viewer@urbandotted.com/Viewer@12345. App in DEMO mode. Do NOT switch to LIVE permanently; if a test switches mode revert to demo (mock true) + delete token afterwards. AI generation pipeline is a later increment; do not test AI draft generation yet."
    - agent: "testing"
      message: "PHASE 6 BACKEND TESTING COMPLETE (2026-08-28). Comprehensive HTTP API testing of secure configuration endpoints. ALL 8/8 TESTS PASSED. ✅ TEST 1 (Config structure + secret non-disclosure): GET /api/settings/config returns correct structure with all required keys (secrets_available=true, shopify{mode,mock_mode,domain,api_version,connected,config_error,token_configured,last_sync,last_connection}, ai{enabled,default_provider,providers{openai,anthropic,gemini,deepseek with enabled,model,key_configured}}, usage_today). CRITICAL SECURITY: NO secrets exposed anywhere (no 'shpat_' or 'sk-' patterns in JSON response). ✅ TEST 2 (Secret write-only + non-disclosure): PUT /api/settings/shopify with token='shpat_TESTSECRET_ABC123' stores token (token_configured=true) but does NOT echo it in response. PUT /api/settings/ai/openai with api_key='sk-TESTKEY-OPENAI-XYZ' stores key (key_configured=true) but does NOT echo it. GET /api/settings/config confirms test secrets NOT disclosed anywhere in response JSON. ✅ TEST 3 (Per-provider test connection): GET /api/settings/ai/anthropic/test (no key) returns connected=false, status='not_configured'. GET /api/settings/ai/openai/test (fake key) returns connected=false, status='invalid_api_key', key NOT leaked in response. GET /api/settings/ai/foobar/test (invalid provider) returns 404. ✅ TEST 4 (Default provider + validation): PUT /api/settings/ai with default_provider='gemini' succeeds (200), verified in config. Invalid default_provider='notreal' rejected (400). Invalid mode='sideways' rejected (400). Invalid provider endpoint /api/settings/ai/foobar returns 404. ✅ TEST 5 (LIVE safety): DELETE token, switch to mode=live+mock_mode=false → mode=live, data_source=live, connected=false, config_error non-empty (no auto-fallback to demo). Reverted to demo+mock, config_error cleared (None). ✅ TEST 6 (Prompt manager): GET /api/settings/prompts returns all 3 types (product_seo, collection_seo, quality_review) with active_version, text, versions, is_default. PUT custom prompt (60+ chars) increments version, is_default=false. Too-short prompt (<20 chars) rejected (400). POST restore-default succeeds, is_default=true. Invalid prompt type returns 404. ✅ TEST 7 (Role gating): Viewer (viewer@urbandotted.com) correctly denied (403) on all 6 settings endpoints (GET config, PUT shopify, PUT ai/openai, GET ai/openai/test, GET prompts, PUT prompts). ✅ TEST 8 (Regression - SEO-only allowlist): PATCH /api/products/{id}/seo-draft with forbidden field 'price' returns 403 NON_SEO_FIELD_WRITE_DENIED. POST /api/products/{id}/publish-seo with forbidden field 'vendor' returns 403 NON_SEO_FIELD_WRITE_DENIED. SEO-only fields (seo_title, meta_description) work correctly (200). All config reverted to DEMO state at end (mode=demo, mock_mode=true, all tokens/keys deleted, all providers disabled, default_provider=openai). Phase-6 secure configuration backend is fully functional and secure."
    - agent: "main"
      message: "SHOPIFY TOKEN EXCHANGE AUTH implemented (repo newseo). Container env was missing (backend/.env, frontend/.env gitignored & absent after repo connect -> backend crash-looping KeyError MONGO_URL); recreated both .env (MONGO_URL localhost, DB_NAME=urbandotted_seo, fresh JWT_SECRET + APP_SECRETS_ENCRYPTION_KEY Fernet, APP_DATA_MODE=demo, SHOPIFY_MOCK_MODE=true). Admin login: admin@urbandotted.com / Admin@12345 (fresh DB). NEW backend files shopify_auth.py + shopify_auth_routes.py; edited shopify_client.py, settings_routes.py, server.py. NEW route POST /api/shopify/auth/token-exchange authenticates ONLY via the Shopify ID token (Authorization: Bearer) — NOT the app JWT. Validates JWT (HS256 via SHOPIFY_CLIENT_SECRET, exp, nbf, aud==SHOPIFY_CLIENT_ID, iss/dest shop consistency, myshopify.com host), then exchanges at https://{shop}/admin/oauth/access_token (grant_type=urn:ietf:params:oauth:grant-type:token-exchange, subject_token_type=id_token, requested_token_type=...offline-access-token) -> OFFLINE Admin token stored encrypted via secrets_store('shopify_token'); shop domain from dest. Other new routes (app-admin JWT): GET /api/shopify/auth/status, GET /api/shopify/auth/test (verify_stored_connection hits real Admin GraphQL regardless of APP_DATA_MODE), POST /api/shopify/auth/disconnect; plus PUBLIC GET /api/shopify/config (exposes ONLY client id for App Bridge). Manual shpat_ token entry REMOVED from PUT /settings/shopify. Token/secret/key NEVER returned or logged. APP_DATA_MODE NOT auto-switched; NO auto-sync. PLEASE TEST BACKEND ONLY. Preview env has TEST-ONLY client creds: SHOPIFY_CLIENT_ID=preview_test_client_id, SHOPIFY_CLIENT_SECRET=preview_test_client_secret_do_not_use_in_prod (use these to craft HS256 session tokens for validation-branch tests). Focus: (1) POST token-exchange validation branches — valid token must PASS validation and reach the exchange step (expect HTTP 502 EXCHANGE_FAILED/UNAVAILABLE since the fake shop has no real endpoint); bad signature->401 INVALID_ID_TOKEN; expired->401 TOKEN_EXPIRED; nbf-future->401 TOKEN_NOT_YET_VALID; wrong aud->401 INVALID_AUDIENCE; iss/dest shop mismatch->401 SHOP_MISMATCH; non-myshopify host->401 INVALID_SHOP; missing Bearer->401. (2) SECURITY: no response body / no field ever contains an access token or client secret; a FAILED exchange must NOT store shopify_token (GET /api/shopify/auth/status authenticated=false afterwards). (3) /api/shopify/config returns only api_key (no secret). (4) /api/shopify/auth/status, /auth/test, /auth/disconnect require app-admin JWT (viewer/none -> 401/403). (5) Regression: SEO-only allowlist (403 NON_SEO_FIELD_WRITE_DENIED on forbidden fields) still holds; PUT /settings/shopify no longer accepts a token. Do NOT run any Shopify sync. Leave APP_DATA_MODE=demo."
    - agent: "testing"
      message: "SHOPIFY TOKEN EXCHANGE AUTH BACKEND TESTING COMPLETE (2026-08-29). Created /app/shopify_token_exchange_test.py with comprehensive HTTP API testing using crafted HS256 JWT tokens (signed with preview test credentials SHOPIFY_CLIENT_ID=preview_test_client_id, SHOPIFY_CLIENT_SECRET=preview_test_client_secret_do_not_use_in_prod). ALL 16/16 TESTS PASSED (0 failed). ✅ TEST 1 (Valid token validation): Crafted valid ID token with correct signature, exp, nbf, aud, iss/dest → passes JWT validation and reaches exchange step → returns 502 (exchange fails because fake shop preview-demo-shop.myshopify.com has no real Shopify endpoint) → CONFIRMS validation logic working correctly. ✅ TEST 2 (Bad signature): Token signed with wrong secret → 401 INVALID_ID_TOKEN. ✅ TEST 3 (Expired): Token with exp in past → 401 TOKEN_EXPIRED. ✅ TEST 4 (Not-yet-valid): Token with nbf in future → 401 TOKEN_NOT_YET_VALID. ✅ TEST 5 (Wrong audience): Token with aud != client_id → 401 INVALID_AUDIENCE. ✅ TEST 6 (Shop mismatch): Token with iss shop != dest shop → 401 SHOP_MISMATCH. ✅ TEST 7 (Invalid shop): Token with non-myshopify.com host (evil.example.com) → 401 INVALID_SHOP. ✅ TEST 8 (Missing auth): No Authorization header → 401. ✅ TEST 9 (Failed exchange security): After failed exchange (valid token, 502), GET /api/shopify/auth/status returns authenticated=false → CONFIRMS failed exchange does NOT store token. ✅ TEST 10 (Public config): GET /api/shopify/config (no auth) returns api_key=preview_test_client_id, app_configured=true, NO client secret or admin token exposed. ✅ TEST 11-13 (Authorization gating): GET /api/shopify/auth/status, GET /api/shopify/auth/test, POST /api/shopify/auth/disconnect all require admin JWT → without auth returns 401, with admin JWT returns 200. /auth/test with no stored token returns connected=false, status=not_authenticated. ✅ TEST 14 (Regression - token field ignored): PUT /api/settings/shopify with token='shpat_SHOULD_BE_IGNORED' succeeds but does NOT store token → GET /api/shopify/auth/status authenticated=false, GET /api/settings/config token_configured=false → CONFIRMS token field is ignored (Token Exchange is the ONLY way to authenticate). ✅ TEST 15 (Regression - SEO allowlist): PATCH /api/products/{id}/seo-draft with forbidden field 'price' → 403 NON_SEO_FIELD_WRITE_DENIED. POST /api/products/{id}/publish-seo with forbidden field 'vendor' → 403 NON_SEO_FIELD_WRITE_DENIED. SEO-only allowlist still enforced. ✅ TEST 16 (No mode change): APP_DATA_MODE=demo, data_source=demo (no auto-switch to LIVE, no sync triggered). CRITICAL SECURITY VERIFIED: NO admin token (shpat_), NO client secret (preview_test_client_secret_do_not_use_in_prod), NO access_token field with value in ANY response body across all 16 tests. All JWT validation branches working correctly. Authorization gating working correctly. Regressions prevented. Token Exchange authentication is fully functional and secure."




