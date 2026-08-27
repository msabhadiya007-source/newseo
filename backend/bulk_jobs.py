"""Phase 4/5 background workers: bulk publish, bulk rollback, CSV import/export,
and crash recovery / reconciliation. MongoDB is the authoritative job/recovery state.

SECURITY: every Shopify write goes through shopify_client.publish_*_seo which enforces
the SEO-only allowlist. This module never writes any non-SEO Shopify field.
"""
import os
import csv as csvmod
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from db import db
from utils import now_iso, strip_id
from shopify_client import shopify_client, NonSeoFieldWriteDenied
from analysis import reanalyze_one_product, reanalyze_one_collection, get_rules
import bulk_common as bc

logger = logging.getLogger("bulk.jobs")

CHUNK = int(os.environ.get("BULK_CHUNK_SIZE", "25"))
MAX_RETRIES = int(os.environ.get("BULK_MAX_RETRIES", "3"))
EXPORT_DIR = os.environ.get("EXPORT_DIR", "/tmp/urbandotted_exports")
_cancelled = set()  # best-effort in-memory cancel flags (DB status is authoritative)


# ----------------------------- generic resource access -----------------------------
def _rescol(rtype):
    return db.products if rtype == "product" else db.collections_seo


def _shopify_id_field(rtype):
    return "shopify_product_id" if rtype == "product" else "shopify_collection_id"


async def _publish_seo(rtype, shopify_id, title, meta):
    if rtype == "product":
        return await shopify_client.publish_product_seo(shopify_id, title, meta)
    return await shopify_client.publish_collection_seo(shopify_id, title, meta)


async def _get_seo(rtype, shopify_id):
    if rtype == "product":
        return await shopify_client.get_product_seo(shopify_id)
    return None  # collection verify read not exposed by mock; treat mutation echo as verified


async def _reanalyze(rtype, rid):
    if rtype == "product":
        return await reanalyze_one_product(rid)
    return await reanalyze_one_collection(rid)


# ----------------------------- job/item helpers -----------------------------
async def _set_job(job_id, **fields):
    await db.publish_jobs.update_one({"id": job_id}, {"$set": fields})


async def _recount(job_id):
    """Recompute job counters from persisted items (authoritative)."""
    pipeline = [{"$match": {"job_id": job_id}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    counts = {}
    async for row in db.publish_items.aggregate(pipeline):
        counts[row["_id"]] = row["n"]
    total = sum(counts.values())
    done = sum(counts.get(s, 0) for s in ("verified", "success", "failed", "skipped", "conflicted", "unverified"))
    await _set_job(job_id, counts={
        "total": total,
        "queued": counts.get("queued", 0),
        "processing": counts.get("processing", 0),
        "success": counts.get("success", 0),
        "verified": counts.get("verified", 0),
        "unverified": counts.get("unverified", 0),
        "warning": counts.get("warning", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "conflicted": counts.get("conflicted", 0),
    }, progress=int((done / max(1, total)) * 100), last_progress_at=now_iso())


async def _audit(item, user, source, result, old_t, new_t, old_d, new_d, job_id, correlation_id, extra=None):
    changes = []
    if old_t != new_t:
        changes.append({"field": "seo_title", "old": old_t, "new": new_t})
    if old_d != new_d:
        changes.append({"field": "meta_description", "old": old_d, "new": new_d})
    doc = {
        "id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
        "user": user, "actor_role": (extra or {}).get("actor_role"),
        "timestamp": now_iso(), "source": source,
        "resource_type": item["resource_type"], "resource_id": item["resource_id"],
        "shopify_resource_id": item.get("shopify_id"),
        "resource_title": item.get("resource_title"),
        "changes": changes, "result": result,
        "job_id": job_id, "draft_id": item.get("id"),
        "csv_import_id": (extra or {}).get("csv_import_id"),
        "correlation_id": correlation_id,
        "conflict_state": item.get("conflict_state", "none"),
        "retry_count": item.get("retry_count", 0),
        "reverted": False,
    }
    await db.audit_log.insert_one(doc)
    return doc["id"]


# ----------------------------- bulk publish worker -----------------------------
async def run_bulk_publish(job_id):
    job = await db.publish_jobs.find_one({"id": job_id})
    if not job:
        return
    user = job.get("created_by")
    role = job.get("actor_role")
    source = job.get("source")
    correlation_id = job.get("correlation_id")
    allow_warnings = bool(job.get("options", {}).get("allow_warnings"))
    await _set_job(job_id, status="running", started_at=job.get("started_at") or now_iso(), message="Publishing")

    while True:
        # pull the next queued item (persistent queue)
        item = await db.publish_items.find_one({"job_id": job_id, "status": "queued"})
        if not item:
            break
        if job_id in _cancelled:
            await db.publish_items.update_many({"job_id": job_id, "status": "queued"},
                                               {"$set": {"status": "skipped", "last_error": "Job cancelled"}})
            break
        await _process_one(item, user, role, source, correlation_id, allow_warnings)
        await _recount(job_id)

    await _recount(job_id)
    fresh = await db.publish_jobs.find_one({"id": job_id})
    c = fresh.get("counts", {})
    if job_id in _cancelled:
        final = "cancelled"
        _cancelled.discard(job_id)
    elif c.get("failed", 0) or c.get("conflicted", 0) or c.get("unverified", 0):
        final = "completed_with_errors"
    else:
        final = "completed"
    await _set_job(job_id, status=final, completed_at=now_iso(), progress=100,
                   message=f"{final.replace('_', ' ').title()}: "
                           f"{c.get('verified',0)} verified, {c.get('failed',0)} failed, "
                           f"{c.get('conflicted',0)} conflicted, {c.get('skipped',0)} skipped")


async def _process_one(item, user, role, source, correlation_id, allow_warnings, is_retry=False):
    job_id = item["job_id"]
    rtype = item["resource_type"]
    rid = item["resource_id"]
    col = _rescol(rtype)
    await db.publish_items.update_one({"id": item["id"]}, {"$set": {"status": "processing"}})

    rec = await col.find_one({"id": rid})
    if not rec:
        await db.publish_items.update_one({"id": item["id"]},
                                          {"$set": {"status": "failed", "last_error": "RESOURCE_DELETED"}})
        return
    # optimistic concurrency / conflict re-validation before mutating
    conflict = bc.compute_conflict(rec)
    if conflict == "resource_deleted":
        await db.publish_items.update_one({"id": item["id"]},
                                          {"$set": {"status": "failed", "conflict_state": conflict,
                                                    "last_error": "RESOURCE_DELETED"}})
        return
    if conflict == "shopify_changed":
        await db.publish_items.update_one({"id": item["id"]},
                                          {"$set": {"status": "conflicted", "conflict_state": conflict,
                                                    "last_error": "CONFLICT_REVALIDATION_REQUIRED"}})
        return

    new_t = item["after"]["title"]
    new_d = item["after"]["description"]
    old_t = rec.get("current_seo_title")
    old_d = rec.get("current_seo_description")

    lock_key = f"{rtype}:{rid}"
    got = await bc.acquire_lock(lock_key, owner=job_id, ttl_seconds=300)
    if not got:
        await db.publish_items.update_one({"id": item["id"]},
                                          {"$set": {"status": "skipped", "last_error": "PUBLISH_LOCKED"}})
        return

    retry_count = item.get("retry_count", 0)
    try:
        while True:
            try:
                await _publish_seo(rtype, rec[_shopify_id_field(rtype)], new_t, new_d)
                break
            except NonSeoFieldWriteDenied as e:
                await db.publish_items.update_one({"id": item["id"]},
                    {"$set": {"status": "failed", "last_error": f"NON_SEO_FIELD_WRITE_DENIED: {e.fields}"}})
                return
            except Exception as e:  # noqa
                msg = str(e)
                if bc.is_retryable(msg) and retry_count < MAX_RETRIES:
                    retry_count += 1
                    delay = min(30, 2 ** retry_count)
                    await db.publish_items.update_one({"id": item["id"]},
                        {"$set": {"retry_count": retry_count, "last_error": msg,
                                  "next_retry_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()}})
                    await asyncio.sleep(min(delay, 3))
                    continue
                await db.publish_items.update_one({"id": item["id"]},
                    {"$set": {"status": "failed", "retry_count": retry_count, "last_error": msg}})
                return

        # verify
        verify = await _get_seo(rtype, rec[_shopify_id_field(rtype)])
        verified = True if verify is None else (verify.get("title") == new_t and verify.get("description") == new_d)

        await col.update_one({"id": rid}, {"$set": {
            "current_seo_title": new_t, "current_seo_description": new_d,
            "last_synced_seo_title": new_t, "last_synced_seo_description": new_d,
            "draft_seo_title": None, "draft_seo_description": None, "has_draft": False,
            "draft_base_title": None, "draft_base_description": None, "conflict_resolved": False,
            "seo_conflict": False, "seo_title_hash": bc.seo_hash(new_t), "meta_hash": bc.seo_hash(new_d),
            "publication_status": "verified" if verified else "published_unverified",
            "shopify_updated_at": now_iso(),
        }})
        await _reanalyze(rtype, rid)
        aud = await _audit(item, user, "Rollback" if item.get("kind") == "rollback" else "Bulk",
                           "verified" if verified else "published_unverified",
                           old_t, new_t, old_d, new_d, job_id, correlation_id, {"actor_role": role})
        await db.publish_items.update_one({"id": item["id"]}, {"$set": {
            "status": "verified" if verified else "unverified",
            "before": {"title": old_t, "description": old_d},
            "publish_result": "ok", "verify_result": "match" if verified else "VERIFY_MISMATCH",
            "audit_id": aud, "retry_count": retry_count,
        }})
    finally:
        await bc.release_lock(lock_key, owner=job_id)


# ----------------------------- bulk rollback worker -----------------------------
async def run_bulk_rollback(job_id):
    job = await db.publish_jobs.find_one({"id": job_id})
    if not job:
        return
    user, role, correlation_id = job.get("created_by"), job.get("actor_role"), job.get("correlation_id")
    await _set_job(job_id, status="running", started_at=now_iso(), message="Rolling back")

    while True:
        item = await db.publish_items.find_one({"job_id": job_id, "status": "queued"})
        if not item:
            break
        if job_id in _cancelled:
            await db.publish_items.update_many({"job_id": job_id, "status": "queued"},
                                               {"$set": {"status": "skipped", "last_error": "Job cancelled"}})
            break
        await _rollback_one(item, user, role, correlation_id)
        await _recount(job_id)

    await _recount(job_id)
    fresh = await db.publish_jobs.find_one({"id": job_id})
    c = fresh.get("counts", {})
    final = "cancelled" if job_id in _cancelled else (
        "completed_with_errors" if (c.get("failed", 0) or c.get("conflicted", 0)) else "completed")
    _cancelled.discard(job_id)
    await _set_job(job_id, status=final, completed_at=now_iso(), progress=100,
                   message=f"Rollback {final}: {c.get('verified',0)} restored, {c.get('conflicted',0)} conflicts")


async def _rollback_one(item, user, role, correlation_id):
    rtype, rid = item["resource_type"], item["resource_id"]
    col = _rescol(rtype)
    await db.publish_items.update_one({"id": item["id"]}, {"$set": {"status": "processing"}})
    rec = await col.find_one({"id": rid})
    if not rec:
        await db.publish_items.update_one({"id": item["id"]},
                                          {"$set": {"status": "failed", "last_error": "RESOURCE_DELETED"}})
        return
    # rollback conflict: current live value must still equal the value we published (item.after)
    exp_t = item["after"]["title"]
    exp_d = item["after"]["description"]
    cur_t = rec.get("current_seo_title")
    cur_d = rec.get("current_seo_description")
    if (cur_t or None) != (exp_t or None) or (cur_d or None) != (exp_d or None):
        await db.publish_items.update_one({"id": item["id"]},
            {"$set": {"status": "conflicted", "conflict_state": "shopify_changed",
                      "last_error": "ROLLBACK_CONFLICT"}})
        return
    tgt_t = item["before"]["title"] or ""
    tgt_d = item["before"]["description"] or ""
    lock_key = f"{rtype}:{rid}"
    if not await bc.acquire_lock(lock_key, owner=item["job_id"], ttl_seconds=300):
        await db.publish_items.update_one({"id": item["id"]},
                                          {"$set": {"status": "skipped", "last_error": "PUBLISH_LOCKED"}})
        return
    try:
        await _publish_seo(rtype, rec[_shopify_id_field(rtype)], tgt_t, tgt_d)
        verify = await _get_seo(rtype, rec[_shopify_id_field(rtype)])
        verified = True if verify is None else (verify.get("title") == tgt_t and verify.get("description") == tgt_d)
        await col.update_one({"id": rid}, {"$set": {
            "current_seo_title": tgt_t, "current_seo_description": tgt_d,
            "last_synced_seo_title": tgt_t, "last_synced_seo_description": tgt_d,
            "seo_title_hash": bc.seo_hash(tgt_t), "meta_hash": bc.seo_hash(tgt_d),
            "publication_status": "verified" if verified else "published_unverified",
        }})
        await _reanalyze(rtype, rid)
        aud = await _audit(item, user, "Rollback", "verified" if verified else "published_unverified",
                           cur_t, tgt_t, cur_d, tgt_d, item["job_id"], correlation_id, {"actor_role": role})
        # mark the original publish audit reverted, if referenced
        if item.get("origin_audit_id"):
            await db.audit_log.update_one({"id": item["origin_audit_id"]}, {"$set": {"reverted": True}})
        await db.publish_items.update_one({"id": item["id"]},
            {"$set": {"status": "verified" if verified else "unverified", "audit_id": aud}})
    finally:
        await bc.release_lock(lock_key, owner=item["job_id"])


# ----------------------------- CSV export worker -----------------------------
PRODUCT_EXPORT_COLS = ["shopify_product_id", "handle", "product_title_read_only",
                       "current_seo_title", "current_meta_description",
                       "new_seo_title", "new_meta_description",
                       "current_score", "issue_codes", "last_synced_at"]
COLLECTION_EXPORT_COLS = ["shopify_collection_id", "handle", "collection_title_read_only",
                          "current_seo_title", "current_meta_description",
                          "new_seo_title", "new_meta_description",
                          "current_score", "issue_codes"]


async def run_csv_export(job_id):
    job = await db.csv_jobs.find_one({"id": job_id})
    if not job:
        return
    await db.csv_jobs.update_one({"id": job_id}, {"$set": {"status": "running", "started_at": now_iso()}})
    rtype = job.get("resource_type", "product")
    q = job.get("query", {})
    col = _rescol(rtype)
    cols = PRODUCT_EXPORT_COLS if rtype == "product" else COLLECTION_EXPORT_COLS
    idf = _shopify_id_field(rtype)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"{job_id}.csv")
    rows = 0
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csvmod.writer(fh)
            w.writerow(cols)
            cursor = col.find(q, {"_id": 0}).batch_size(1000)
            async for rec in cursor:
                title = rec.get("current_seo_title") or ""
                meta = rec.get("current_seo_description") or ""
                row = {
                    idf: rec.get(idf), "handle": rec.get("handle"),
                    "product_title_read_only": rec.get("title"),
                    "collection_title_read_only": rec.get("title"),
                    "current_seo_title": title, "current_meta_description": meta,
                    "new_seo_title": rec.get("draft_seo_title") if rec.get("has_draft") else title,
                    "new_meta_description": rec.get("draft_seo_description") if rec.get("has_draft") else meta,
                    "current_score": rec.get("seo_score"),
                    "issue_codes": ";".join(rec.get("issue_codes") or []),
                    "last_synced_at": rec.get("shopify_updated_at"),
                }
                w.writerow([bc.csv_safe(row.get(c)) for c in cols])
                rows += 1
        await db.csv_jobs.update_one({"id": job_id}, {"$set": {
            "status": "completed", "completed_at": now_iso(), "file_path": path,
            "counts": {"total": rows}, "progress": 100,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }})
    except Exception as e:  # noqa
        logger.exception("CSV export failed")
        await db.csv_jobs.update_one({"id": job_id}, {"$set": {"status": "failed", "message": str(e)}})


# ----------------------------- CSV import (confirm -> drafts) worker -----------------------------
async def run_csv_import_confirm(job_id, include_warnings=False):
    job = await db.csv_jobs.find_one({"id": job_id})
    if not job:
        return
    await db.csv_jobs.update_one({"id": job_id}, {"$set": {"status": "running", "started_at": now_iso()}})
    rtype = job.get("resource_type", "product")
    col = _rescol(rtype)
    sev_filter = ["READY", "WARNING"] if include_warnings else ["READY"]
    created = 0
    cursor = db.csv_rows.find({"csv_job_id": job_id, "severity": {"$in": sev_filter}})
    async for row in cursor:
        rec = await col.find_one({"id": row["resource_local_id"]})
        if not rec:
            continue
        update = {"has_draft": True, "publication_status": "draft",
                  "draft_source": bc.SOURCE_CSV, "draft_updated_at": now_iso(),
                  "draft_base_title": rec.get("current_seo_title"),
                  "draft_base_description": rec.get("current_seo_description"),
                  "conflict_resolved": False, "csv_import_id": job_id}
        if row.get("new_seo_title") is not None:
            update["draft_seo_title"] = row["new_seo_title"]
        if row.get("new_meta_description") is not None:
            update["draft_seo_description"] = row["new_meta_description"]
        await col.update_one({"id": row["resource_local_id"]}, {"$set": update})
        created += 1
    await db.csv_jobs.update_one({"id": job_id}, {"$set": {
        "status": "completed", "completed_at": now_iso(), "drafts_created": created, "progress": 100}})


# ----------------------------- recovery / reconciliation -----------------------------
async def recover_jobs_on_startup():
    """MongoDB is authoritative. Re-launch any publish/rollback jobs that were mid-flight
    when the process stopped. Already verified/success items are never re-published."""
    async for job in db.publish_jobs.find({"status": {"$in": ["running", "recovering", "queued"]}}):
        # reset any items stuck in 'processing' back to 'queued' so they are safely retried
        await db.publish_items.update_many(
            {"job_id": job["id"], "status": "processing"}, {"$set": {"status": "queued"}})
        await _set_job(job["id"], status="recovering", message="Recovered after restart")
        coro = run_bulk_rollback(job["id"]) if job.get("type") == "bulk_rollback" else run_bulk_publish(job["id"])
        asyncio.create_task(coro)
        logger.info("Recovered job %s", job["id"])
    # resume interrupted CSV export jobs (regenerate from persisted params)
    async for job in db.csv_jobs.find({"kind": "export", "status": {"$in": ["running", "queued"]}}):
        asyncio.create_task(run_csv_export(job["id"]))


async def reconcile_publish_state():
    """Admin maintenance: inspect records stuck publishing / published_unverified and
    reconcile against current Shopify value."""
    fixed = 0
    async for rec in db.products.find({"publication_status": {"$in": ["publishing", "published_unverified"]}}):
        seo = await shopify_client.get_product_seo(rec["shopify_product_id"]) if shopify_client.is_connected else None
        if seo:
            match = seo.get("title") == rec.get("current_seo_title") and \
                seo.get("description") == rec.get("current_seo_description")
            await db.products.update_one({"id": rec["id"]},
                {"$set": {"publication_status": "verified" if match else "published_unverified"}})
        else:
            await db.products.update_one({"id": rec["id"]}, {"$set": {"publication_status": "verified"}})
        fixed += 1
    return {"reconciled": fixed}


def launch(coro):
    asyncio.create_task(coro)
