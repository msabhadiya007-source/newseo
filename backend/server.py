import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from db import db, client
from auth import router as auth_router, seed_admin
from routes import api
from bulk_routes import api2
from seo import DEFAULT_RULES

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("server")

app = FastAPI(title="UrbanDotted SEO Operations")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    checks = {"database": False, "worker": True}
    try:
        await db.command("ping")
        checks["database"] = True
    except Exception:  # noqa
        checks["database"] = False
    status = "ok" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks}


app.include_router(auth_router)
app.include_router(api)
app.include_router(api2)

_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
_frontend = os.environ.get("FRONTEND_URL")
if _frontend and _frontend not in _origins:
    _origins.append(_frontend)
for local in ["http://localhost:3000", "http://127.0.0.1:3000"]:
    if local not in _origins:
        _origins.append(local)
if "*" in _origins:
    _origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logger.info("Starting UrbanDotted SEO Operations backend")
    await seed_admin()
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.products.create_index("id", unique=True)
    await db.products.create_index("shopify_product_id")
    await db.products.create_index("handle")
    await db.products.create_index([("data_source", 1), ("status_bucket", 1)])
    await db.products.create_index([("data_source", 1), ("seo_score", 1)])
    await db.products.create_index("issue_codes")
    await db.products.create_index("current_seo_title")
    await db.products.create_index("current_seo_description")
    await db.collections_seo.create_index("id", unique=True)
    await db.jobs.create_index("id", unique=True)
    await db.audit_log.create_index("resource_id")
    await db.audit_log.create_index("timestamp")
    # ---- Phase 4/5 collections + indexes ----
    await db.products.create_index("has_draft")
    await db.products.create_index("publication_status")
    await db.products.create_index("draft_source")
    await db.products.create_index("seo_title_hash")
    await db.products.create_index("meta_hash")
    await db.products.create_index("shopify_updated_at")
    await db.publish_jobs.create_index("id", unique=True)
    await db.publish_jobs.create_index("created_at")
    await db.publish_jobs.create_index("idempotency_key")
    await db.publish_items.create_index("id", unique=True)
    await db.publish_items.create_index([("job_id", 1), ("status", 1)])
    await db.publish_items.create_index("resource_id")
    await db.csv_jobs.create_index("id", unique=True)
    await db.csv_jobs.create_index("created_at")
    await db.csv_rows.create_index([("csv_job_id", 1), ("severity", 1)])
    # locks: _id is the lock key (unique by default); TTL cleanup on expiry field
    try:
        await db.locks.create_index("expires_at", expireAfterSeconds=0)
    except Exception:  # noqa
        pass
    await db.audit_log.create_index("job_id")
    await db.audit_log.create_index("correlation_id")
    if not await db.settings.find_one({"id": "seo_rules"}):
        await db.settings.insert_one({"id": "seo_rules", **DEFAULT_RULES})
    # crash recovery: resume any in-flight bulk jobs (MongoDB is authoritative)
    try:
        import bulk_jobs
        await bulk_jobs.recover_jobs_on_startup()
    except Exception:  # noqa
        logger.exception("Job recovery on startup failed")
    from shopify_client import shopify_client
    logger.info("Startup complete. Mode: %s | data_source: %s | mock: %s",
                shopify_client.mode, shopify_client.data_source, shopify_client.mock_mode)


@app.on_event("shutdown")
async def shutdown():
    client.close()
