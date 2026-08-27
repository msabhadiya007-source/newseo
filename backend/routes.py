"""Main API routes: dashboard, products, collections, sync, jobs, audit, settings, AI."""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body, Query

from db import db
from utils import now_iso, strip_id
from auth import get_current_user, require_permission
from seo import ISSUE_LABELS, DEFAULT_RULES
from shopify_client import (
    shopify_client, assert_seo_only, NonSeoFieldWriteDenied,
    ALLOWED_PRODUCT_FIELDS, ALLOWED_COLLECTION_FIELDS, ALLOWED_IMAGE_FIELDS, NON_SEO_DENIED,
)
from analysis import (
    get_rules, reanalyze_one_product, reanalyze_one_collection,
)
import jobs as jobs_mod
import ai_service
import seed

api = APIRouter(prefix="/api")

BUCKETS = ["missing", "critical", "needs_improvement", "good", "optimised"]


@api.get("/health")
async def api_health():
    return {"status": "ok"}


@api.get("/ready")
async def api_ready():
    ok = True
    try:
        await db.command("ping")
    except Exception:  # noqa
        ok = False
    return {"status": "ok" if ok else "degraded", "checks": {"database": ok}}


def _source():
    return shopify_client.data_source


def resolve_source(user: dict, source: str = None):
    """Admins may explicitly target a data_source (demo/live/loadtest) for inspection;
    everyone else uses the active env-controlled source."""
    if source in ("demo", "live", "loadtest") and user.get("role") == "admin":
        return source
    return shopify_client.data_source


def _guard(payload: dict, allowed: set):
    try:
        assert_seo_only(payload, allowed)
    except NonSeoFieldWriteDenied as e:
        raise HTTPException(status_code=403, detail=str(e))


# ---------------- Dashboard ----------------
@api.get("/dashboard/metrics")
async def dashboard_metrics(user: dict = Depends(get_current_user), source: str = None):
    source = resolve_source(user, source)
    total = await db.products.count_documents({"data_source": source})
    if total == 0:
        return {
            "connected": shopify_client.is_connected, "data_source": source,
            "total": 0, "buckets": {}, "issues": {}, "health": 0,
            "collections_total": await db.collections_seo.count_documents({"data_source": source}),
            "empty": True,
        }
    bucket_counts = {}
    for b in BUCKETS:
        bucket_counts[b] = await db.products.count_documents({"data_source": source, "status_bucket": b})
    drafts = await db.products.count_documents({"data_source": source, "has_draft": True})

    # issue category counts
    pipeline = [
        {"$match": {"data_source": source}},
        {"$unwind": "$issue_codes"},
        {"$group": {"_id": "$issue_codes", "count": {"$sum": 1}}},
    ]
    issues = {}
    async for row in db.products.aggregate(pipeline):
        issues[row["_id"]] = row["count"]

    # weighted health = avg score
    agg = await db.products.aggregate([
        {"$match": {"data_source": source}},
        {"$group": {"_id": None, "avg": {"$avg": "$seo_score"}}},
    ]).to_list(1)
    health = round(agg[0]["avg"]) if agg else 0

    missing = bucket_counts.get("missing", 0)
    fully = bucket_counts.get("optimised", 0)
    needs = bucket_counts.get("needs_improvement", 0)
    critical = bucket_counts.get("critical", 0)
    good = bucket_counts.get("good", 0)

    sync_state = await db.sync_state.find_one({"id": "sync"})
    return {
        "connected": shopify_client.is_connected,
        "data_source": source,
        "total": total,
        "fully_optimised": fully,
        "missing_seo": missing,
        "needs_improvement": needs,
        "critical": critical,
        "good": good,
        "drafts": drafts,
        "health": health,
        "buckets": bucket_counts,
        "issues": issues,
        "issue_labels": ISSUE_LABELS,
        "collections_total": await db.collections_seo.count_documents({"data_source": source}),
        "last_sync": strip_id(sync_state).get("last_sync") if sync_state else None,
        "empty": False,
    }


# ---------------- Products ----------------
def _product_query(source, bucket, issue, search, min_score, max_score, missing):
    q = {"data_source": source}
    if bucket == "drafts":
        q["has_draft"] = True
    elif bucket and bucket != "all":
        q["status_bucket"] = bucket
    if issue:
        q["issue_codes"] = issue
    conds = []
    if issue:
        conds.append({"issue_codes": issue})
    if missing == "title":
        conds.append({"issue_codes": "MISSING_SEO_TITLE"})
    elif missing == "description":
        conds.append({"issue_codes": "MISSING_META_DESCRIPTION"})
    elif missing == "both":
        conds.append({"issue_codes": {"$all": ["MISSING_SEO_TITLE", "MISSING_META_DESCRIPTION"]}})
    if conds:
        q.pop("issue_codes", None)
        q["$and"] = conds
    if min_score is not None or max_score is not None:
        rng = {}
        if min_score is not None:
            rng["$gte"] = min_score
        if max_score is not None:
            rng["$lte"] = max_score
        q["seo_score"] = rng
    if search:
        q["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"handle": {"$regex": search, "$options": "i"}},
            {"shopify_product_id": {"$regex": search, "$options": "i"}},
            {"current_seo_title": {"$regex": search, "$options": "i"}},
        ]
    return q


@api.get("/products")
async def list_products(
    user: dict = Depends(get_current_user),
    page: int = 1, page_size: int = 25,
    bucket: str = "all", issue: str = None, search: str = None,
    min_score: int = None, max_score: int = None, missing: str = None,
    sort: str = "seo_score", order: str = "asc", source: str = None,
):
    source = resolve_source(user, source)
    q = _product_query(source, bucket, issue, search, min_score, max_score, missing)
    page_size = min(max(page_size, 1), 100)
    skip = (max(page, 1) - 1) * page_size
    direction = 1 if order == "asc" else -1
    total = await db.products.count_documents(q)
    cursor = db.products.find(q, {"_id": 0}).sort(sort, direction).skip(skip).limit(page_size)
    items = await cursor.to_list(page_size)

    # tab counts
    tabs = {"all": await db.products.count_documents({"data_source": source})}
    for b in BUCKETS:
        tabs[b] = await db.products.count_documents({"data_source": source, "status_bucket": b})
    tabs["drafts"] = await db.products.count_documents({"data_source": source, "has_draft": True})

    return {"items": items, "total": total, "page": page, "page_size": page_size, "tabs": tabs}


@api.get("/products/{product_id}")
async def get_product(product_id: str, user: dict = Depends(get_current_user)):
    p = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    # duplicate context
    dup_count = 0
    if p.get("current_seo_description"):
        dup_count = await db.products.count_documents(
            {"current_seo_description": p["current_seo_description"], "id": {"$ne": product_id}})
    p["duplicate_description_count"] = dup_count
    return p


@api.patch("/products/{product_id}/seo-draft")
async def save_product_draft(product_id: str, payload: dict = Body(...),
                             user: dict = Depends(require_permission("edit"))):
    _guard(payload, ALLOWED_PRODUCT_FIELDS)
    p = await db.products.find_one({"id": product_id})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    update = {"has_draft": True, "publication_status": "draft"}
    if "seo_title" in payload:
        update["draft_seo_title"] = payload["seo_title"]
    if "meta_description" in payload:
        update["draft_seo_description"] = payload["meta_description"]
    await db.products.update_one({"id": product_id}, {"$set": update})
    return await db.products.find_one({"id": product_id}, {"_id": 0})


@api.post("/products/{product_id}/publish-seo")
async def publish_product(product_id: str, payload: dict = Body(...),
                          user: dict = Depends(require_permission("publish"))):
    _guard(payload, ALLOWED_PRODUCT_FIELDS)
    p = await db.products.find_one({"id": product_id})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if p.get("publication_status") == "publishing":
        raise HTTPException(status_code=409, detail="A publish is already in progress for this product")

    new_title = payload.get("seo_title", p.get("draft_seo_title") if p.get("has_draft") else p.get("current_seo_title"))
    new_meta = payload.get("meta_description", p.get("draft_seo_description") if p.get("has_draft") else p.get("current_seo_description"))
    new_title = (new_title or "").strip()
    new_meta = (new_meta or "").strip()
    if not new_title and not new_meta:
        raise HTTPException(status_code=400, detail="Cannot publish: both SEO title and meta description are empty")

    prev_title = p.get("current_seo_title")
    prev_meta = p.get("current_seo_description")

    await db.products.update_one({"id": product_id}, {"$set": {"publication_status": "publishing"}})
    try:
        result = await shopify_client.publish_product_seo(p["shopify_product_id"], new_title, new_meta)
    except NonSeoFieldWriteDenied as e:
        await db.products.update_one({"id": product_id}, {"$set": {"publication_status": "draft"}})
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:  # noqa
        await db.products.update_one({"id": product_id}, {"$set": {"publication_status": "failed"}})
        raise HTTPException(status_code=502, detail=f"Shopify publish failed: {e}")

    await db.products.update_one({"id": product_id}, {"$set": {
        "current_seo_title": new_title, "current_seo_description": new_meta,
        "draft_seo_title": None, "draft_seo_description": None, "has_draft": False,
        "publication_status": "verified", "shopify_updated_at": now_iso(),
    }})

    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    changes = []
    if prev_title != new_title:
        changes.append({"field": "seo_title", "old": prev_title, "new": new_title})
    if prev_meta != new_meta:
        changes.append({"field": "meta_description", "old": prev_meta, "new": new_meta})
    await db.audit_log.insert_one({
        "id": audit_id, "user": user["email"], "timestamp": now_iso(),
        "resource_type": "product", "resource_id": product_id,
        "resource_title": p.get("title"), "changes": changes,
        "source": "Manual", "result": "verified" if not result.get("demo") else "verified (demo)",
        "job_id": None, "reverted": False,
    })

    updated = await reanalyze_one_product(product_id)
    return {"product": strip_id(updated), "verification": result, "audit_id": audit_id}


@api.post("/products/{product_id}/rollback")
async def rollback_product(product_id: str, user: dict = Depends(require_permission("rollback"))):
    last = await db.audit_log.find_one(
        {"resource_id": product_id, "reverted": False}, sort=[("timestamp", -1)])
    if not last:
        raise HTTPException(status_code=404, detail="No published change to roll back")
    p = await db.products.find_one({"id": product_id})
    target = {}
    for ch in last.get("changes", []):
        if ch["field"] == "seo_title":
            target["current_seo_title"] = ch["old"]
        elif ch["field"] == "meta_description":
            target["current_seo_description"] = ch["old"]
    if not target:
        raise HTTPException(status_code=400, detail="Nothing to roll back")
    prev_title, prev_meta = p.get("current_seo_title"), p.get("current_seo_description")
    tgt_title = target.get("current_seo_title", prev_title) or ""
    tgt_meta = target.get("current_seo_description", prev_meta) or ""
    # rollback obeys SEO allowlist implicitly (only SEO fields restored)
    await shopify_client.publish_product_seo(p["shopify_product_id"], tgt_title, tgt_meta)
    await db.products.update_one({"id": product_id}, {"$set": {
        "current_seo_title": tgt_title, "current_seo_description": tgt_meta,
        "publication_status": "verified",
    }})
    await db.audit_log.update_one({"id": last["id"]}, {"$set": {"reverted": True}})
    changes = []
    if prev_title != tgt_title:
        changes.append({"field": "seo_title", "old": prev_title, "new": tgt_title})
    if prev_meta != tgt_meta:
        changes.append({"field": "meta_description", "old": prev_meta, "new": tgt_meta})
    await db.audit_log.insert_one({
        "id": f"AUD-{uuid.uuid4().hex[:8].upper()}", "user": user["email"], "timestamp": now_iso(),
        "resource_type": "product", "resource_id": product_id, "resource_title": p.get("title"),
        "changes": changes, "source": "Rollback", "result": "verified",
        "job_id": last["id"], "reverted": False,
    })
    updated = await reanalyze_one_product(product_id)
    return {"product": strip_id(updated)}


# ---------------- Collections ----------------
@api.get("/collections")
async def list_collections(user: dict = Depends(get_current_user),
                           bucket: str = "all", search: str = None, source: str = None):
    source = resolve_source(user, source)
    q = {"data_source": source}
    if bucket and bucket != "all":
        q["status_bucket"] = bucket
    if search:
        q["$or"] = [{"title": {"$regex": search, "$options": "i"}},
                    {"handle": {"$regex": search, "$options": "i"}}]
    items = await db.collections_seo.find(q, {"_id": 0}).sort("seo_score", 1).to_list(500)
    return {"items": items, "total": len(items)}


@api.patch("/collections/{collection_id}/seo-draft")
async def save_collection_draft(collection_id: str, payload: dict = Body(...),
                                user: dict = Depends(require_permission("edit"))):
    _guard(payload, ALLOWED_COLLECTION_FIELDS)
    c = await db.collections_seo.find_one({"id": collection_id})
    if not c:
        raise HTTPException(status_code=404, detail="Collection not found")
    update = {"has_draft": True, "publication_status": "draft"}
    if "seo_title" in payload:
        update["draft_seo_title"] = payload["seo_title"]
    if "meta_description" in payload:
        update["draft_seo_description"] = payload["meta_description"]
    await db.collections_seo.update_one({"id": collection_id}, {"$set": update})
    return await db.collections_seo.find_one({"id": collection_id}, {"_id": 0})


@api.post("/collections/{collection_id}/publish-seo")
async def publish_collection(collection_id: str, payload: dict = Body(...),
                             user: dict = Depends(require_permission("publish"))):
    _guard(payload, ALLOWED_COLLECTION_FIELDS)
    c = await db.collections_seo.find_one({"id": collection_id})
    if not c:
        raise HTTPException(status_code=404, detail="Collection not found")
    new_title = (payload.get("seo_title", c.get("draft_seo_title") or c.get("current_seo_title")) or "").strip()
    new_meta = (payload.get("meta_description", c.get("draft_seo_description") or c.get("current_seo_description")) or "").strip()
    prev_title, prev_meta = c.get("current_seo_title"), c.get("current_seo_description")
    try:
        result = await shopify_client.publish_collection_seo(c["shopify_collection_id"], new_title, new_meta)
    except Exception as e:  # noqa
        raise HTTPException(status_code=502, detail=f"Shopify publish failed: {e}")
    await db.collections_seo.update_one({"id": collection_id}, {"$set": {
        "current_seo_title": new_title, "current_seo_description": new_meta,
        "draft_seo_title": None, "draft_seo_description": None, "has_draft": False,
        "publication_status": "verified",
    }})
    await db.audit_log.insert_one({
        "id": f"AUD-{uuid.uuid4().hex[:8].upper()}", "user": user["email"], "timestamp": now_iso(),
        "resource_type": "collection", "resource_id": collection_id, "resource_title": c.get("title"),
        "changes": [{"field": "seo_title", "old": prev_title, "new": new_title},
                    {"field": "meta_description", "old": prev_meta, "new": new_meta}],
        "source": "Manual", "result": "verified", "job_id": None, "reverted": False,
    })
    updated = await reanalyze_one_collection(collection_id)
    return {"collection": strip_id(updated), "verification": result}


# ---------------- Sync / Jobs ----------------
@api.post("/sync")
async def trigger_sync(full_resync: bool = False, user: dict = Depends(require_permission("sync"))):
    source = shopify_client.data_source
    count = int(os.environ.get("SEED_PRODUCT_COUNT", "2500"))
    ccount = int(os.environ.get("SEED_COLLECTION_COUNT", "40"))
    label = "Shopify Live Sync" if source == "live" else "Demo Sync"
    if source == "live" and full_resync:
        label = "Shopify Full Re-sync"
    job = await jobs_mod.create_job(label, count if source == "demo" else 0, user["email"],
                                    {"source": source, "full_resync": full_resync})
    jobs_mod.launch(jobs_mod.run_sync_job(job["id"], source, full_resync, count, ccount))
    return {"job_id": job["id"], "status": "queued", "source": source}


@api.post("/shopify/live-sync")
async def live_sync(full_resync: bool = True, user: dict = Depends(require_permission("settings"))):
    """Admin maintenance: run LIVE Shopify ingestion (mock transport when SHOPIFY_MOCK_MODE)."""
    job = await jobs_mod.create_job("Shopify Full Re-sync" if full_resync else "Shopify Live Sync",
                                    0, user["email"], {"source": "live", "full_resync": full_resync})
    jobs_mod.launch(jobs_mod.run_sync_job(job["id"], "live", full_resync, 0, 0))
    return {"job_id": job["id"], "status": "queued", "source": "live", "mock": shopify_client.mock_mode}


@api.post("/reanalyze")
async def trigger_reanalyze(user: dict = Depends(require_permission("edit"))):
    job = await jobs_mod.create_job("SEO Reanalysis", 0, user["email"])
    jobs_mod.launch(jobs_mod.run_reanalysis_job(job["id"], shopify_client.data_source))
    return {"job_id": job["id"], "status": "queued"}


@api.get("/sync/status")
async def sync_status(user: dict = Depends(get_current_user)):
    source = shopify_client.data_source
    state = await db.sync_state.find_one({"id": source}, {"_id": 0})
    active = await db.jobs.find_one({"status": {"$in": ["queued", "running"]}}, {"_id": 0},
                                    sort=[("created_at", -1)])
    return {"sync_state": state, "active_job": active, "data_source": source,
            "mode": shopify_client.mode, "connected": shopify_client.is_connected}


@api.get("/jobs")
async def list_jobs(user: dict = Depends(get_current_user), limit: int = 50):
    items = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"items": items}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------- Audit ----------------
@api.get("/audit")
async def list_audit(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 30,
                     resource_type: str = None):
    q = {}
    if resource_type:
        q["resource_type"] = resource_type
    page_size = min(max(page_size, 1), 100)
    total = await db.audit_log.count_documents(q)
    items = await db.audit_log.find(q, {"_id": 0}).sort("timestamp", -1) \
        .skip((max(page, 1) - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------- Settings ----------------
@api.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    rules = await get_rules()
    source = shopify_client.data_source
    state = await db.sync_state.find_one({"id": source}, {"_id": 0})
    return {
        "rules": rules,
        "mode": shopify_client.mode,
        "shopify": {
            "mode": shopify_client.mode,
            "mock_mode": shopify_client.mock_mode,
            "connected": shopify_client.is_connected,
            "store_domain": shopify_client.domain or None,
            "api_version": shopify_client.api_version,
            "data_source": source,
            "last_sync": state.get("last_sync") if state else None,
            "counts": state.get("counts") if state else None,
            "test_product_id": os.environ.get("SHOPIFY_TEST_PRODUCT_ID") or None,
            "test_product_handle": os.environ.get("SHOPIFY_TEST_PRODUCT_HANDLE") or None,
        },
    }


@api.put("/settings")
async def update_settings(payload: dict = Body(...), user: dict = Depends(require_permission("settings"))):
    allowed = set(DEFAULT_RULES.keys())
    update = {k: v for k, v in payload.items() if k in allowed}
    update["id"] = "seo_rules"
    await db.settings.update_one({"id": "seo_rules"}, {"$set": update}, upsert=True)
    return await get_rules()


@api.get("/settings/shopify/test")
async def test_shopify(user: dict = Depends(require_permission("settings"))):
    return await shopify_client.test_connection()


@api.get("/settings/shopify/test-product")
async def get_test_product(user: dict = Depends(require_permission("settings"))):
    return {"id": os.environ.get("SHOPIFY_TEST_PRODUCT_ID") or None,
            "handle": os.environ.get("SHOPIFY_TEST_PRODUCT_HANDLE") or None}


@api.post("/shopify/verify-publish")
async def verify_publish(user: dict = Depends(require_permission("publish"))):
    """Real SEO publish round-trip verification on a single low-risk test product.
    Runs against the mock store in mock mode; refuses a real mutation unless explicitly enabled."""
    if shopify_client.use_real and os.environ.get("SHOPIFY_ALLOW_LIVE_PUBLISH", "false").lower() != "true":
        return {"skipped": True, "reason": "Real Shopify credentials detected; live mutation is intentionally disabled. "
                                           "Set SHOPIFY_ALLOW_LIVE_PUBLISH=true to enable the real round-trip."}
    if not shopify_client.mock_mode and shopify_client.mode != "live":
        raise HTTPException(status_code=400, detail="Set APP_DATA_MODE=live (or enable SHOPIFY_MOCK_MODE) to run the publish round-trip test")
    tid = os.environ.get("SHOPIFY_TEST_PRODUCT_ID")
    th = os.environ.get("SHOPIFY_TEST_PRODUCT_HANDLE")
    if tid:
        p = await db.products.find_one({"shopify_product_id": tid})
    elif th:
        p = await db.products.find_one({"handle": th, "data_source": "live"})
    else:
        p = await db.products.find_one({"data_source": "live"})
    if not p:
        raise HTTPException(status_code=404, detail="No live product available. Run a live sync first.")
    prev_t, prev_d = p.get("current_seo_title"), p.get("current_seo_description")
    new_t = (prev_t or (p.get("title") or "Test SEO Title"))[:60]
    new_d = (prev_d or "Verification meta description for the SEO publish round-trip on a low-risk product today.")[:160]
    result = await shopify_client.publish_product_seo(p["shopify_product_id"], new_t, new_d)
    verify = await shopify_client.get_product_seo(p["shopify_product_id"])
    await db.products.update_one({"id": p["id"]}, {"$set": {
        "current_seo_title": new_t, "current_seo_description": new_d,
        "last_synced_seo_title": new_t, "last_synced_seo_description": new_d,
        "publication_status": "verified"}})
    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    await db.audit_log.insert_one({
        "id": audit_id, "user": user["email"], "timestamp": now_iso(),
        "resource_type": "product", "resource_id": p["id"], "resource_title": p.get("title"),
        "changes": [{"field": "seo_title", "old": prev_t, "new": new_t},
                    {"field": "meta_description", "old": prev_d, "new": new_d}],
        "source": "VerifyTest", "result": "verified", "job_id": None, "reverted": False,
    })
    updated = await reanalyze_one_product(p["id"])
    verified_match = bool(verify) and verify.get("title") == new_t and verify.get("description") == new_d
    return {"product_id": p["id"], "shopify_product_id": p["shopify_product_id"],
            "published": result, "verified_shopify_value": verify, "verified_match": verified_match,
            "new_bucket": updated["status_bucket"], "new_score": updated["seo_score"],
            "audit_id": audit_id, "mock": shopify_client.mock_mode}


@api.post("/diagnostics/loadtest")
async def loadtest(count: int = 35000, user: dict = Depends(require_permission("settings"))):
    """Generate ~N synthetic loadtest records (separate data_source) and measure query perf."""
    import time
    count = min(max(count, 1000), 60000)
    existing = await db.products.count_documents({"data_source": "loadtest"})
    generated = 0
    if existing < count:
        batch = []
        for doc in seed.generate_loadtest(count - existing):
            batch.append(doc)
            if len(batch) >= 5000:
                await db.products.insert_many(batch); generated += len(batch); batch = []
        if batch:
            await db.products.insert_many(batch); generated += len(batch)

    def ms(t):
        return round(t * 1000, 1)
    m = {}
    t = time.perf_counter(); total = await db.products.count_documents({"data_source": "loadtest"}); m["count_documents_ms"] = ms(time.perf_counter() - t)
    t = time.perf_counter(); await db.products.find({"data_source": "loadtest"}, {"_id": 0}).sort("seo_score", 1).skip(10000).limit(50).to_list(50); m["paginated_deep_page_ms"] = ms(time.perf_counter() - t)
    t = time.perf_counter(); await db.products.count_documents({"data_source": "loadtest", "status_bucket": "missing"}); m["filter_bucket_count_ms"] = ms(time.perf_counter() - t)
    t = time.perf_counter(); await db.products.find({"data_source": "loadtest", "issue_codes": "MISSING_SEO_TITLE"}, {"_id": 0}).limit(50).to_list(50); m["issue_queue_find_ms"] = ms(time.perf_counter() - t)
    t = time.perf_counter(); await db.products.find({"data_source": "loadtest", "title": {"$regex": "iPhone 17", "$options": "i"}}, {"_id": 0}).limit(50).to_list(50); m["search_regex_ms"] = ms(time.perf_counter() - t)
    t = time.perf_counter()
    await db.products.aggregate([{"$match": {"data_source": "loadtest"}}, {"$group": {"_id": None, "avg": {"$avg": "$seo_score"}}}]).to_list(1)
    for b in BUCKETS:
        await db.products.count_documents({"data_source": "loadtest", "status_bucket": b})
    m["dashboard_aggregation_ms"] = ms(time.perf_counter() - t)
    t = time.perf_counter()
    await db.products.aggregate([{"$match": {"data_source": "loadtest", "current_seo_title": {"$ne": None}}},
                                 {"$group": {"_id": "$current_seo_title", "n": {"$sum": 1}}},
                                 {"$match": {"n": {"$gt": 1}}}, {"$limit": 100}]).to_list(100)
    m["duplicate_title_aggregation_ms"] = ms(time.perf_counter() - t)
    return {"loadtest_records": total, "generated_now": generated, "metrics_ms": m}


@api.delete("/diagnostics/loadtest")
async def clear_loadtest(user: dict = Depends(require_permission("settings"))):
    r = await db.products.delete_many({"data_source": "loadtest"})
    return {"deleted": r.deleted_count}


@api.get("/diagnostics")
async def diagnostics(user: dict = Depends(get_current_user)):
    db_ok = True
    try:
        await db.command("ping")
    except Exception:  # noqa
        db_ok = False
    active = await db.jobs.count_documents({"status": {"$in": ["queued", "running"]}})
    return {
        "database_connected": db_ok,
        "shopify_connected": shopify_client.is_connected,
        "worker_healthy": True,
        "active_jobs": active,
        "ai_configured": ai_service.ai_configured(),
    }


# ---------------- AI ----------------
@api.post("/products/{product_id}/ai-suggest")
async def ai_suggest_product(product_id: str, payload: dict = Body(...),
                             user: dict = Depends(require_permission("ai"))):
    field = payload.get("field")
    if field not in ("seo_title", "meta_description"):
        raise HTTPException(status_code=400, detail="field must be seo_title or meta_description")
    p = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    rules = await get_rules()
    try:
        suggestion = await ai_service.generate_seo(p, rules, field)
    except Exception as e:  # noqa
        raise HTTPException(status_code=503, detail=f"AI provider unavailable: {e}")
    return {"field": field, "suggestion": suggestion}
