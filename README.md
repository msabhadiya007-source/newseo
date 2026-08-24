# UrbanDotted SEO Operations

A production-ready, **SEO-only** Shopify management platform for a store with 35,000+ products.
It can **read** commerce data (price, inventory, SKU, variants) for context, but can only ever
**write** `seo.title`, `seo.description` (products & collections) and image ALT text. All other
Shopify writes are denied by a backend allowlist (`NON_SEO_FIELD_WRITE_DENIED`).

## Stack
- **Frontend:** React + Tailwind + shadcn/ui (desktop-first dashboard)
- **Backend:** FastAPI (Python 3.11)
- **Database:** MongoDB (persistent working state; source of truth)
- **Jobs:** Async background jobs, state persisted in MongoDB (survive restarts)
- **AI (optional):** OpenAI GPT-5.4 / Claude Sonnet 4.6 / Gemini 3.1 Pro (configurable)

## Core safety principles
1. Commerce/operational fields are read-only. 2. Only SEO allowlisted fields can be mutated.
3. AI cannot publish directly. 4. CSV cannot modify non-SEO fields. 5. Every publish is audited.
6. Every publish is rollback-capable. 7. Secrets stay server-side. 8. Bulk jobs are rate-controlled.
9. Existing valid SEO is never auto-overwritten.

## Local development
### Requirements
- Python 3.11+, Node 18+ / Yarn, MongoDB

### Environment variables
Copy `.env.example`. Backend reads `backend/.env`, frontend reads `frontend/.env`.
Key vars: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_ACCESS_TOKEN`, `SHOPIFY_API_VERSION`,
`AI_PROVIDER`, `AI_MODEL`, `EMERGENT_LLM_KEY`, `DEMO_MODE`, `CORS_ORIGINS`, `FRONTEND_URL`, `PORT`.

### Backend
```
cd backend && pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}
```
### Frontend
```
cd frontend && yarn install && yarn start
```

Login with the seeded admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`). Click **Sync Now** to load the
demo catalog (`DEMO_MODE=true`), then explore the SEO workflow.

## Shopify setup
- Required scopes (minimum): `read_products`, `write_products`, `read_content` (for SEO metafields on collections). Request only what is needed.
- Put credentials in `SHOPIFY_STORE_DOMAIN` and `SHOPIFY_ADMIN_ACCESS_TOKEN`. When set, the app switches from `demo` to `shopify` data source automatically.
- Test the connection from **Settings → Test Shopify Connection**.

## Production deployment
The backend binds to `0.0.0.0:$PORT` and reads all config from environment variables.
Set `DEMO_MODE=false` in production so demo seeding is disabled.

### Railway
- Add a MongoDB plugin (or external Mongo) → set `MONGO_URL`, `DB_NAME`.
- Deploy backend service: Start command `uvicorn server:app --host 0.0.0.0 --port $PORT`.
- Set env vars (see `.env.example`), `CORS_ORIGINS`/`FRONTEND_URL` to your frontend domain.
- Health check path: `/health`.
- Deploy frontend separately (static build) with `REACT_APP_BACKEND_URL` pointing to the backend.

### Render
- **Backend:** Web Service, Build `pip install -r backend/requirements.txt`,
  Start `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`, Health check `/health`.
- **Database:** MongoDB (Render external / Atlas) → `MONGO_URL`.
- **Frontend:** Static Site, Build `yarn install && yarn build`, publish `frontend/build`,
  env `REACT_APP_BACKEND_URL`.

### Docker
```
docker build -t urbandotted-seo .
docker run -p 8001:8001 --env-file .env urbandotted-seo
```

## Health endpoints
- `GET /health` → `{"status":"ok"}`
- `GET /ready` → verifies database connectivity.

## Notes / known limitations (current phase)
- Phases 1–3 delivered (auth, sync architecture, SEO analyzer, live editor, draft/publish, verify, rollback, jobs, audit, settings, collections, single AI suggest).
- Bulk spreadsheet editor, CSV import/export and bulk AI jobs are scaffolded (allowlist, pagination, job system in place) and land in the next phase.
- Runs in `demo` data source until real Shopify credentials are provided.
