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
1. Bulk spreadsheet editor + CSV import/export with validation preview.
2. Real Shopify GraphQL paginated + incremental sync.
3. Image ALT module + bulk AI generation jobs.
