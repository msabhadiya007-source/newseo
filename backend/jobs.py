"""Persistent background job system (survives restarts; state stored in MongoDB)."""
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from db import db
from utils import now_iso
from seed import generate_products, generate_collections, demo_enabled
from shopify_client import shopify_client
from analysis import reanalyze_all, reanalyze_one_product

logger = logging.getLogger("jobs")


async def create_job(job_type: str, total: int, created_by: str) -> dict:
    job = {
        "id": f"JOB-{uuid.uuid4().hex[:8].upper()}",
        "type": job_type,
        "status": "queued",
        "created_at": now_iso(),
        "started_at": None,
        "completed_at": None,
        "total": total,
        "success": 0,
        "warning": 0,
        "failed": 0,
        "progress": 0,
        "created_by": created_by,
        "message": "",
    }
    await db.jobs.insert_one(dict(job))
    return job


async def update_job(job_id: str, **fields):
    await db.jobs.update_one({"id": job_id}, {"$set": fields})


async def run_sync_job(job_id: str, product_count: int, collection_count: int):
    try:
        await update_job(job_id, status="running", started_at=now_iso(), message="Starting Shopify sync")
        source = shopify_client.data_source

        if source == "demo":
            if not demo_enabled():
                await update_job(job_id, status="failed", completed_at=now_iso(),
                                 message="Demo mode disabled. Connect Shopify to sync real data.")
                return
            # Non-destructive: insert only missing products (by shopify_product_id) so
            # published/draft SEO work and audit references survive a re-sync.
            products = generate_products(product_count)
            for i in range(0, len(products), 500):
                for p in products[i:i + 500]:
                    await db.products.update_one(
                        {"shopify_product_id": p["shopify_product_id"]},
                        {"$setOnInsert": dict(p)}, upsert=True)
                await update_job(job_id, progress=int((i / max(1, len(products))) * 60),
                                 success=i, message="Importing products")
            cols = generate_collections(collection_count)
            for c in cols:
                await db.collections_seo.update_one(
                    {"shopify_collection_id": c["shopify_collection_id"]},
                    {"$setOnInsert": dict(c)}, upsert=True)
        else:
            # Real Shopify sync (Admin GraphQL pagination) is not implemented yet.
            await update_job(job_id, status="failed", completed_at=now_iso(),
                             message="Real Shopify ingestion is not implemented yet. Currently only DEMO data source is supported.")
            return

        async def cb(done, total):
            await update_job(job_id, progress=60 + int((done / max(1, total)) * 40),
                             message=f"Analyzing SEO ({done}/{total})")

        total = await reanalyze_all(source, cb)
        await db.sync_state.update_one({"id": "sync"}, {"$set": {
            "id": "sync", "last_sync": now_iso(), "data_source": source,
            "products_processed": total, "status": "ok",
        }}, upsert=True)
        await update_job(job_id, status="completed", completed_at=now_iso(),
                         progress=100, success=total, total=total,
                         message=f"Synced and analyzed {total} products")
    except Exception as e:  # noqa
        logger.exception("Sync job failed")
        await update_job(job_id, status="failed", completed_at=now_iso(), message=str(e))


async def run_reanalysis_job(job_id: str):
    try:
        await update_job(job_id, status="running", started_at=now_iso(), message="Recomputing SEO analysis")
        source = shopify_client.data_source

        async def cb(done, total):
            await update_job(job_id, progress=int((done / max(1, total)) * 100),
                             total=total, success=done)

        total = await reanalyze_all(source, cb)
        await update_job(job_id, status="completed", completed_at=now_iso(),
                         progress=100, total=total, success=total,
                         message=f"Reanalyzed {total} products")
    except Exception as e:  # noqa
        logger.exception("Reanalysis job failed")
        await update_job(job_id, status="failed", completed_at=now_iso(), message=str(e))


def launch(coro):
    """Fire-and-forget a background task."""
    asyncio.create_task(coro)
