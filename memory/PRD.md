# UrbanDotted SEO Operations — PRD

## Original Problem Statement
Production-ready, SEO-ONLY Shopify management platform for a store with ~35,000+ products. The platform may READ commerce data (price, inventory, SKU, variants, etc.) for context but must NEVER write anything except SEO fields: product `seo.title`/`seo.description`, collection `seo.title`/`seo.description`, and image ALT text. All other writes are denied with `NON_SEO_FIELD_WRITE_DENIED`. Must be deployment-safe (Railway/Render/Docker), authenticated, with background jobs, persistent DB, SEO analyzer/scoring, live editor, draft/publish, verification, rollback, audit, and (optional) AI generation.

## Architecture
- **Frontend:** React (CRA) + Tailwind + shadcn/ui. Dark-first dashboard. Token (JWT) auth stored in localStorage.
- **Backend:** FastAPI (modular: auth, seo analyzer, shopify_client service layer w/ allowlist, analysis, jobs, routes, ai_service, seed).
- **Database:** MongoDB (source of working state). Indexed on shopify id, handle, status_bucket, seo_score, issue_codes, current SEO values.
- **Jobs:** Persistent async background jobs stored in Mongo (survive restarts). Used for sync + reanalysis.
- **Data sources:** `demo` (seeded phone-case catalog, DEMO_MODE) vs `shopify` (when SHOPIFY_* env set). Never mixed. Demo disabled in prod.

## User Personas
- **Admin** (msabhadiya007@gmail.com): sync, edit, ai, csv, publish, rollback, settings.
- **SEO Editor:** edit, draft, ai, csv, publish.
- **Viewer:** read-only.

## Core Requirements (static)
- SEO-only backend allowlist enforced at route boundary AND inside shopify_client. No generic product update route.
- Deterministic (70%) + AI-assisted (30%) explainable scoring, 0–100.
- Recommended ranges (configurable): title 50–60, meta 140–160 (never claim hard Google limits).
- Draft vs Published; publish → Shopify (demo-simulated) → verify → reanalyze → auto queue removal.
- Immutable audit log + rollback (obeys allowlist).
- Existing valid SEO never auto-overwritten.

## Implemented (2026-08-24)
- Phase 1: JWT auth + roles + admin seed; MongoDB models/indexes; Shopify service layer + allowlist; demo sync via background job; health `/health`+`/api/health`, `/ready`+`/api/ready`, `/api/diagnostics`.
- Phase 2: Deterministic SEO analyzer (missing/length/duplicate/keyword-stuffing/ALT), scoring, status buckets, product + collection queues, dashboard metrics from real DB analysis.
- Phase 3: Live SEO editor (read-only locked commerce panel w/ lock icons, editable title/meta w/ live counters + progress + recommended ranges from settings, SERP preview, SEO rules sidebar, explainable score breakdown), draft state, publish + verification, single + audit rollback.
- Collections SEO module (list, draft, publish, SERP, guarded).
- Job Center (progress, persisted), Audit & Rollback UI, Settings (SEO rules config, Shopify test, diagnostics, demo notice), single-product AI suggest (multi-provider via Emergent key, hallucination guard).
- Deployment: Dockerfile, .dockerignore, .env.example, README (Railway/Render/Docker), 0.0.0.0:$PORT, env-driven config, CORS.
- Testing: 96/96 backend pytest pass incl. security acceptance (all forbidden fields → 403 NON_SEO_FIELD_WRITE_DENIED) + draft→publish→verify→queue-removal→rollback; frontend E2E passed.

## Backlog / Remaining
- **P1 Phase 4 (Bulk & CSV):** spreadsheet bulk editor (server-paginated, SEO-only cells, batch draft/validate/publish), CSV export (filtered), CSV import with Ready/Warnings/Errors preview + forbidden-column rejection. (Stub pages present.)
- **P1 Real Shopify ingestion:** implement Admin GraphQL paginated sync in jobs.run_sync_job real branch (currently returns "not implemented"). Incremental sync via updated_at.
- **P2 Phase 5 safety:** stale-data/concurrency warnings (make publishing lock atomic via find_one_and_update), bulk pre-publish review, retry of failed publishes, rate-limit tuning.
- **P2 Phase 6 AI:** bulk AI generation background jobs (pause/cancel/progress), AI cost tracking/limits, AI quality (30%) scoring wired into score.
- **P2 Phase 7 Image ALT module:** dedicated ALT analyzer + editing + bulk + AI suggestions.
- **P3:** login_attempts TTL index; saved filters; multi-user management UI.

## Next Tasks
1. Phase 6: AI bulk generation (source hooks already in place: manual|bulk|csv|ai|rollback|retry).
2. Phase 7: Image ALT Studio.

## Phase 4 + 5 — Bulk Editor + CSV + Production Safety (COMPLETE & VERIFIED)
- Backend modules: bulk_common (validation/severity READY|WARNING|ERROR, normalized SEO hashes, lease locks, conflict detection, transient/permanent retry classification), bulk_jobs (chunked bulk publish + bulk rollback workers, verify→reanalyze→audit, retry w/ backoff, crash recovery + reconcile), csv_service (strict SEO-only parse/validate, forbidden-column rejection), bulk_routes (/api/bulk/* + /api/csv/*).
- Safety: per-resource lease locks (mutual exclusion), idempotency keys (double-submit dedupe), stale-data conflict BLOCKS publish (+resolve keep_shopify/keep_draft), ROLLBACK_CONFLICT detection, MongoDB-authoritative job recovery on startup + manual /bulk/recover, audit hardening (actor_role, job_id, csv_import_id, correlation_id, conflict_state, retry_count).
- Frontend: Bulk Editor (spreadsheet, page vs all-filtered selection banner, live counters, validate, publish-preview w/ >100 confirmation + warning ack, conflict resolution modal, bulk jobs w/ rollback/retry/cancel + per-record drill-down, unsaved-changes guard) and CSV (background export + secure token download + regenerate-on-miss, import forbidden-column rejection + Ready/Warnings/Errors preview + drafts-only confirm).
- Verified: pytest 132 passed / 23 skipped (stable), incl. 40 new tests (idempotency, lock mutual-exclusion, conflict blocking, rollback + ROLLBACK_CONFLICT, crash recovery no-duplicate, retry classification, permissions viewer-denied, CSV forbidden/valid/invalid/duplicate/empty/download-token, SEO-only regression across bulk+csv). Frontend UI all green. 35k load test sub-65ms with new indexes. No new dependencies.
- Limitation: CSV export files are temporary artifacts (regenerated from persisted job params if missing); production should use S3/GCS object storage. Collection publish verify relies on mutation echo (mock has no collection read-back).

## Phase 3.5 — Real Shopify Live Sync (COMPLETE & VERIFIED, this session)
- Real Shopify Admin GraphQL ingestion in jobs.ingest_live (cursor pagination, incremental via updatedAt, non-destructive merge preserving local drafts + conflict flagging, deleted-record marking on full re-sync). Mock transport (SHOPIFY_MOCK_MODE=true) exercises the real code path without live credentials.
- Rate-limit/cost handling in shopify_client._http_graphql: 429 + GraphQL "throttled" exponential backoff, proactive cost throttleStatus backoff, retry cap.
- DEMO/LIVE strictly separated via APP_DATA_MODE + data_source; listings never mix.
- SEO-only allowlist at route + shopify_client (product/collection seo.title/desc, image alt). Non-SEO writes -> 403 NON_SEO_FIELD_WRITE_DENIED.
- Publish round-trip: draft -> validate -> Shopify SEO mutation -> verify -> reanalyze -> audit -> rollback (verify-publish verified_match=true).
- Connection test friendly states (connected/authentication_failed/missing_permission/api_error/unavailable/demo_mode). No Shopify token exposed to frontend (server-side env only).
- Verification: pytest 92 (demo) + tests/test_live_sync.py 20/20 (live+mock) + security 42/42 (both modes); independent API agent 74/74. 35k load test all queries sub-60ms on existing indexes.
- NOTE: verified against MOCK transport; real store validation pending real SHOPIFY_STORE_DOMAIN/SHOPIFY_ADMIN_ACCESS_TOKEN (SHOPIFY_MOCK_MODE=false).

## Shopify Authentication — Token Exchange (added 2026-08-29)
The embedded app authenticates via Shopify's OAuth 2.0 **Token Exchange** flow (no manual
`shpat_` token, no legacy redirect). Frontend App Bridge -> fresh session (ID) token ->
`POST /api/shopify/auth/token-exchange` (Bearer id_token). Backend validates the JWT
(HS256 w/ `SHOPIFY_CLIENT_SECRET`, `exp`/`nbf`/`aud==SHOPIFY_CLIENT_ID`/`iss==dest` shop),
then exchanges it at `https://{shop}/admin/oauth/access_token` for an **offline** Admin API
token, stored encrypted via `secrets_store('shopify_token')`. Shop domain is taken from the
validated `dest` claim. Token is never returned to the browser/logs/responses.
`APP_DATA_MODE` is an explicit server-side switch (NOT auto-flipped); no auto-sync on auth.
Backend: `shopify_auth.py`, `shopify_auth_routes.py`. Routes: `POST /api/shopify/auth/token-exchange`,
`GET /api/shopify/auth/status`, `GET /api/shopify/auth/test`, `POST /api/shopify/auth/disconnect`,
`GET /api/shopify/config` (public, client id only).

