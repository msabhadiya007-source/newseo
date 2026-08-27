"""Persistent background job system (survives restarts; state stored in MongoDB).

Handles DEMO seeding and LIVE Shopify Admin GraphQL ingestion (paginated, throttled,
incremental, non-destructive) as background jobs.
"""
import os
import uuid
import asyncio
import logging

from db import db
from utils import now_iso
from seed import generate_products, generate_collections, demo_enabled
from shopify_client import shopify_client
from analysis import reanalyze_all

logger = logging.getLogger("jobs")

PAGE_SIZE = int(os.environ.get("SHOPIFY_PAGE_SIZE", "100"))
MAX_PAGES = int(os.environ.get("SHOPIFY_MAX_PAGES", "1000"))


async def create_job(job_type, total, created_by, meta=None):
    job = {
        "id": f"JOB-{uuid.uuid4().hex[:8].upper()}",
        "type": job_type, "status": "queued", "created_at": now_iso(),
        "started_at": None, "completed_at": None, "total": total,
        "success": 0, "warning": 0, "failed": 0, "progress": 0,
        "created_by": created_by, "message": "",
        "new": 0, "updated": 0, "unchanged": 0, "deleted": 0,
        "pages": 0, "cursor": None, "meta": meta or {},
    }
    await db.jobs.insert_one(dict(job))
    return job


async def update_job(job_id, **fields):
    await db.jobs.update_one({"id": job_id}, {"$set": fields})


# ---------------- product/collection mapping (READ ONLY ingestion) ----------------
def map_product_node(node, existing):
    seo = node.get("seo") or {}
    images = []
    for e in (node.get("images", {}) or {}).get("edges", []):
        n = e["node"]
        images.append({"id": n["id"], "src": n.get("url"), "alt": n.get("altText") or "", "draft_alt": None})
    shopify_fields = {
        "handle": node.get("handle"),
        "title": node.get("title"),
        "body": node.get("descriptionHtml"),
        "product_type": node.get("productType"),
        "vendor": node.get("vendor"),
        "status": (node.get("status") or "").lower(),
        "tags": node.get("tags") or [],
        "current_seo_title": seo.get("title"),
        "current_seo_description": seo.get("description"),
        "last_synced_seo_title": seo.get("title"),
        "last_synced_seo_description": seo.get("description"),
        "images": images,
        "shopify_updated_at": node.get("updatedAt"),
        "created_at": node.get("createdAt"),
        "shopify_state": "active",
        "data_source": "live",
    }
    return shopify_fields


async def ingest_live(job_id, full_resync):
    state = await db.sync_state.find_one({"id": "live"})
    updated_since = None if full_resync else (state.get("last_sync") if state else None)

    counters = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0, "deleted": 0}
    seen_ids = set()
    cursor, has_next, pages, processed = None, True, 0, 0

    while has_next and pages < MAX_PAGES:
        try:
            nodes, has_next, cursor = await shopify_client.fetch_products_page(cursor, PAGE_SIZE, updated_since)
        except Exception as e:  # noqa
            await update_job(job_id, message=f"Product page fetch failed: {e}")
            raise
        pages += 1
        for node in nodes:
            try:
                gid = node["id"]
                seen_ids.add(gid)
                existing = await db.products.find_one({"shopify_product_id": gid})
                fields = map_product_node(node, existing)
                if not existing:
                    doc = {
                        "id": str(uuid.uuid4()), "shopify_product_id": gid,
                        "price": None, "inventory": None, "sku": None,
                        "draft_seo_title": None, "draft_seo_description": None, "has_draft": False,
                        "ai_quality": None, "seo_score": 0, "score_breakdown": {}, "issue_codes": [],
                        "status_bucket": "missing", "publication_status": "published",
                        "seo_conflict": False, **fields,
                    }
                    await db.products.insert_one(doc)
                    counters["new"] += 1
                else:
                    # Non-destructive: never touch local drafts / publication status.
                    conflict = False
                    if existing.get("has_draft"):
                        ls_t = existing.get("last_synced_seo_title")
                        ls_d = existing.get("last_synced_seo_description")
                        if (ls_t is not None or ls_d is not None) and (
                                ls_t != fields["current_seo_title"] or ls_d != fields["current_seo_description"]):
                            conflict = True
                    changed = existing.get("shopify_updated_at") != fields["shopify_updated_at"]
                    upd = dict(fields)
                    upd["seo_conflict"] = conflict or existing.get("seo_conflict", False)
                    await db.products.update_one({"shopify_product_id": gid}, {"$set": upd})
                    counters["updated" if changed else "unchanged"] += 1
                processed += 1
            except Exception:  # noqa
                counters["failed"] += 1
        await update_job(job_id, pages=pages, cursor=cursor, success=processed,
                         new=counters["new"], updated=counters["updated"],
                         unchanged=counters["unchanged"], failed=counters["failed"],
                         progress=min(55, 10 + pages), message=f"Ingested {processed} products ({pages} pages)")
        await db.sync_state.update_one({"id": "live"}, {"$set": {"cursor": cursor, "in_progress": True}}, upsert=True)

    # Collections
    ccursor, chas, cpages = None, True, 0
    while chas and cpages < MAX_PAGES:
        nodes, chas, ccursor = await shopify_client.fetch_collections_page(ccursor, PAGE_SIZE, updated_since)
        cpages += 1
        for node in nodes:
            seo = node.get("seo") or {}
            gid = node["id"]
            existing = await db.collections_seo.find_one({"shopify_collection_id": gid})
            fields = {
                "handle": node.get("handle"), "title": node.get("title"),
                "current_seo_title": seo.get("title"), "current_seo_description": seo.get("description"),
                "last_synced_seo_title": seo.get("title"), "last_synced_seo_description": seo.get("description"),
                "shopify_updated_at": node.get("updatedAt"), "products_count": node.get("productsCount"),
                "shopify_state": "active", "data_source": "live",
            }
            if not existing:
                await db.collections_seo.insert_one({
                    "id": str(uuid.uuid4()), "shopify_collection_id": gid,
                    "draft_seo_title": None, "draft_seo_description": None, "has_draft": False,
                    "ai_quality": None, "seo_score": 0, "score_breakdown": {}, "issue_codes": [],
                    "status_bucket": "missing", "publication_status": "published",
                    "images": [], "seo_conflict": False, **fields,
                })
            else:
                await db.collections_seo.update_one({"shopify_collection_id": gid}, {"$set": fields})

    # Deleted-record handling (only meaningful on a full re-sync)
    if full_resync:
        async for p in db.products.find({"data_source": "live", "shopify_product_id": {"$nin": list(seen_ids)}},
                                        {"shopify_product_id": 1}):
            await db.products.update_one({"shopify_product_id": p["shopify_product_id"]},
                                         {"$set": {"shopify_state": "deleted"}})
            counters["deleted"] += 1

    await update_job(job_id, progress=60, message="Analyzing SEO")

    async def cb(done, total):
        await update_job(job_id, progress=60 + int((done / max(1, total)) * 40),
                         message=f"Analyzing SEO ({done}/{total})")

    total = await reanalyze_all("live", cb)
    await db.sync_state.update_one({"id": "live"}, {"$set": {
        "id": "live", "last_sync": now_iso(), "data_source": "live", "cursor": None,
        "in_progress": False, "counts": counters, "products_processed": total,
        "status": "ok", "mock": shopify_client.mock_mode, "full_resync": full_resync,
    }}, upsert=True)
    await update_job(job_id, status="completed", completed_at=now_iso(), progress=100,
                     total=total, success=processed, new=counters["new"], updated=counters["updated"],
                     unchanged=counters["unchanged"], failed=counters["failed"], deleted=counters["deleted"],
                     message=(f"Live sync complete: {counters['new']} new, {counters['updated']} updated, "
                              f"{counters['unchanged']} unchanged, {counters['deleted']} deleted, {counters['failed']} failed"))


async def run_sync_job(job_id, source, full_resync=False, product_count=2500, collection_count=40):
    try:
        await update_job(job_id, status="running", started_at=now_iso(), message="Starting sync")
        if source == "demo":
            if not demo_enabled():
                await update_job(job_id, status="failed", completed_at=now_iso(),
                                 message="Demo mode disabled. Set APP_DATA_MODE=live to sync real data.")
                return
            products = generate_products(product_count)
            for i in range(0, len(products), 500):
                for p in products[i:i + 500]:
                    await db.products.update_one({"shopify_product_id": p["shopify_product_id"]},
                                                 {"$setOnInsert": dict(p)}, upsert=True)
                await update_job(job_id, progress=int((i / max(1, len(products))) * 60),
                                 success=i, message="Importing demo products")
            for c in generate_collections(collection_count):
                await db.collections_seo.update_one({"shopify_collection_id": c["shopify_collection_id"]},
                                                    {"$setOnInsert": dict(c)}, upsert=True)

            async def cb(done, total):
                await update_job(job_id, progress=60 + int((done / max(1, total)) * 40),
                                 message=f"Analyzing SEO ({done}/{total})")
            total = await reanalyze_all("demo", cb)
            await db.sync_state.update_one({"id": "demo"}, {"$set": {
                "id": "demo", "last_sync": now_iso(), "data_source": "demo",
                "products_processed": total, "status": "ok"}}, upsert=True)
            await update_job(job_id, status="completed", completed_at=now_iso(),
                             progress=100, success=total, total=total,
                             message=f"Demo sync complete: {total} products analyzed")
        else:
            await ingest_live(job_id, full_resync)
    except Exception as e:  # noqa
        logger.exception("Sync job failed")
        await update_job(job_id, status="failed", completed_at=now_iso(), message=str(e))
        await db.sync_state.update_one({"id": source}, {"$set": {"in_progress": False, "status": "failed"}}, upsert=True)


async def run_reanalysis_job(job_id, source):
    try:
        await update_job(job_id, status="running", started_at=now_iso(), message="Recomputing SEO analysis")

        async def cb(done, total):
            await update_job(job_id, progress=int((done / max(1, total)) * 100), total=total, success=done)
        total = await reanalyze_all(source, cb)
        await update_job(job_id, status="completed", completed_at=now_iso(), progress=100,
                         total=total, success=total, message=f"Reanalyzed {total} records")
    except Exception as e:  # noqa
        logger.exception("Reanalysis job failed")
        await update_job(job_id, status="failed", completed_at=now_iso(), message=str(e))


def launch(coro):
    asyncio.create_task(coro)
