"""Phase 4/5 API routes: Bulk Editor, bulk publish/rollback jobs, CSV import/export.

Every write path re-asserts the SEO-only allowlist. No non-SEO Shopify field is writable.
"""
import os
import uuid
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, Form, Query
from fastapi.responses import FileResponse

from db import db
from utils import now_iso, strip_id
from auth import get_current_user, require_permission
from shopify_client import (assert_seo_only, NonSeoFieldWriteDenied,
                            ALLOWED_PRODUCT_FIELDS, ALLOWED_COLLECTION_FIELDS)
from analysis import get_rules
from routes import _product_query, resolve_source, BUCKETS
import bulk_common as bc
import bulk_jobs
import csv_service

logger = logging.getLogger("bulk.routes")
api2 = APIRouter(prefix="/api")

MAX_SELECTION = int(os.environ.get("BULK_MAX_SELECTION", "50000"))


def _allowed(rtype):
    return ALLOWED_PRODUCT_FIELDS if rtype == "product" else ALLOWED_COLLECTION_FIELDS


def _rescol(rtype):
    return db.products if rtype == "product" else db.collections_seo


def _idf(rtype):
    return "shopify_product_id" if rtype == "product" else "shopify_collection_id"


def _bulk_query(source, f):
    f = f or {}
    if f.get("resource_type") == "collection":
        q = {"data_source": source}
        if f.get("search"):
            q["$or"] = [{"title": {"$regex": f["search"], "$options": "i"}},
                        {"handle": {"$regex": f["search"], "$options": "i"}}]
    else:
        q = _product_query(source, f.get("bucket", "all"), f.get("issue"), f.get("search"),
                           f.get("min_score"), f.get("max_score"), f.get("missing"))
    extra = []
    if f.get("has_draft"):
        extra.append({"has_draft": True})
    if f.get("publish_status"):
        extra.append({"publication_status": f["publish_status"]})
    if f.get("draft_source"):
        extra.append({"draft_source": f["draft_source"]})
    if f.get("conflict"):
        extra.append({"seo_conflict": True})
    if extra:
        q.setdefault("$and", []).extend(extra)
    return q


async def _resolve_ids(rtype, body, source):
    if body.get("ids"):
        return list(dict.fromkeys(body["ids"]))
    if body.get("all_filtered"):
        col = _rescol(rtype)
        q = _bulk_query(source, {**(body.get("filter") or {}), "resource_type": rtype})
        ids = [d["id"] async for d in col.find(q, {"_id": 0, "id": 1}).limit(MAX_SELECTION + 1)]
        if len(ids) > MAX_SELECTION:
            raise HTTPException(status_code=400, detail=f"Selection exceeds max {MAX_SELECTION}")
        return ids
    return []


# ============================ BULK EDITOR: list ============================
@api2.get("/bulk/products")
async def bulk_products(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 50,
                        bucket: str = "all", issue: str = None, search: str = None,
                        min_score: int = None, max_score: int = None, missing: str = None,
                        has_draft: bool = None, publish_status: str = None,
                        draft_source: str = None, conflict: bool = None,
                        sort: str = "seo_score", order: str = "asc", source: str = None):
    source = resolve_source(user, source)
    f = {"bucket": bucket, "issue": issue, "search": search, "min_score": min_score,
         "max_score": max_score, "missing": missing, "has_draft": has_draft,
         "publish_status": publish_status, "draft_source": draft_source, "conflict": conflict,
         "resource_type": "product"}
    q = _bulk_query(source, f)
    page_size = min(max(page_size, 1), 200)
    skip = (max(page, 1) - 1) * page_size
    total = await db.products.count_documents(q)
    proj = {"_id": 0, "id": 1, "title": 1, "handle": 1, "shopify_product_id": 1,
            "current_seo_title": 1, "current_seo_description": 1,
            "draft_seo_title": 1, "draft_seo_description": 1, "has_draft": 1,
            "seo_score": 1, "status_bucket": 1, "issue_codes": 1, "publication_status": 1,
            "draft_source": 1, "shopify_updated_at": 1, "draft_updated_at": 1,
            "draft_base_title": 1, "draft_base_description": 1, "shopify_state": 1,
            "conflict_resolved": 1}
    items = await db.products.find(q, proj).sort(sort, 1 if order == "asc" else -1) \
        .skip(skip).limit(page_size).to_list(page_size)
    for it in items:
        it["conflict_state"] = bc.compute_conflict(it)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api2.get("/bulk/collections")
async def bulk_collections(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 50,
                           bucket: str = "all", search: str = None, has_draft: bool = None,
                           source: str = None):
    source = resolve_source(user, source)
    q = _bulk_query(source, {"resource_type": "collection", "search": search, "has_draft": has_draft})
    if bucket and bucket != "all":
        q["status_bucket"] = bucket
    page_size = min(max(page_size, 1), 200)
    total = await db.collections_seo.count_documents(q)
    items = await db.collections_seo.find(q, {"_id": 0}).sort("seo_score", 1) \
        .skip((max(page, 1) - 1) * page_size).limit(page_size).to_list(page_size)
    for it in items:
        it["conflict_state"] = bc.compute_conflict(it)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ============================ BULK EDITOR: draft save ============================
@api2.post("/bulk/draft-save")
async def bulk_draft_save(payload: dict = Body(...), user: dict = Depends(require_permission("edit"))):
    rtype = payload.get("resource_type", "product")
    edits = payload.get("edits") or []
    allowed = _allowed(rtype)
    col = _rescol(rtype)
    # guard every edit BEFORE writing anything
    for e in edits:
        fields = {k: v for k, v in e.items() if k != "id"}
        try:
            assert_seo_only(fields, allowed)
        except NonSeoFieldWriteDenied as ex:
            raise HTTPException(status_code=403, detail=str(ex))
    saved = 0
    for e in edits:
        rec = await col.find_one({"id": e.get("id")}, {"_id": 0})
        if not rec:
            continue
        update = {"has_draft": True, "publication_status": "draft",
                  "draft_source": bc.SOURCE_BULK, "draft_updated_at": now_iso(),
                  "conflict_resolved": False}
        if not rec.get("has_draft"):
            update["draft_base_title"] = rec.get("current_seo_title")
            update["draft_base_description"] = rec.get("current_seo_description")
        if "seo_title" in e:
            update["draft_seo_title"] = e["seo_title"]
        if "meta_description" in e:
            update["draft_seo_description"] = e["meta_description"]
        await col.update_one({"id": e["id"]}, {"$set": update})
        saved += 1
    return {"saved": saved}


@api2.post("/bulk/clear-drafts")
async def bulk_clear_drafts(payload: dict = Body(...), user: dict = Depends(require_permission("edit"))):
    rtype = payload.get("resource_type", "product")
    source = resolve_source(user, None)
    ids = await _resolve_ids(rtype, payload, source)
    r = await _rescol(rtype).update_many({"id": {"$in": ids}}, {"$set": {
        "has_draft": False, "draft_seo_title": None, "draft_seo_description": None,
        "draft_base_title": None, "draft_base_description": None, "publication_status": "published"}})
    return {"cleared": r.modified_count}


# ============================ BULK: validate ============================
async def _dup_sets(source):
    """Normalized duplicate value sets over current SEO values for the source."""
    titles, metas = {}, {}
    async for d in db.products.find({"data_source": source},
                                    {"_id": 0, "current_seo_title": 1, "current_seo_description": 1}):
        t = bc.normalize_seo(d.get("current_seo_title"))
        m = bc.normalize_seo(d.get("current_seo_description"))
        if t:
            titles[t] = titles.get(t, 0) + 1
        if m:
            metas[m] = metas.get(m, 0) + 1
    return ({k for k, v in titles.items() if v > 1}, {k for k, v in metas.items() if v > 1})


@api2.post("/bulk/validate")
async def bulk_validate(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    rtype = payload.get("resource_type", "product")
    source = resolve_source(user, None)
    col = _rescol(rtype)
    if payload.get("all_drafts"):
        q = {"data_source": source, "has_draft": True}
    else:
        ids = await _resolve_ids(rtype, payload, source)
        q = {"id": {"$in": ids}}
    rules = await get_rules()
    dt, dm = await _dup_sets(source)
    summary = {"READY": 0, "WARNING": 0, "ERROR": 0, "total": 0, "conflicts": 0,
               "title_changes": 0, "meta_changes": 0}
    samples = []
    async for rec in col.find(q, {"_id": 0}):
        v = bc.validate_record(rec, rules, dt, dm)
        summary["total"] += 1
        summary[v["severity"]] += 1
        if v["conflict"] not in ("none",):
            summary["conflicts"] += 1
        if rec.get("has_draft"):
            if (rec.get("draft_seo_title") or "") != (rec.get("current_seo_title") or ""):
                summary["title_changes"] += 1
            if (rec.get("draft_seo_description") or "") != (rec.get("current_seo_description") or ""):
                summary["meta_changes"] += 1
        if len(samples) < 50 and v["severity"] != "READY":
            samples.append({"id": rec["id"], "title": rec.get("title"),
                            "severity": v["severity"], "codes": v["codes"], "messages": v["messages"]})
    return {"summary": summary, "samples": samples}


# ============================ BULK: publish preview + publish ============================
async def _build_selection_records(rtype, ids, source):
    col = _rescol(rtype)
    rules = await get_rules()
    dt, dm = await _dup_sets(source)
    out = []
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        async for rec in col.find({"id": {"$in": chunk}}, {"_id": 0}):
            v = bc.validate_record(rec, rules, dt, dm)
            out.append((rec, v))
    return out


@api2.post("/bulk/publish-preview")
async def bulk_publish_preview(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    rtype = payload.get("resource_type", "product")
    source = resolve_source(user, None)
    ids = await _resolve_ids(rtype, payload, source)
    recs = await _build_selection_records(rtype, ids, source)
    ready = warn = err = conflicts = t_changes = m_changes = 0
    samples = {"warnings": [], "errors": []}
    for rec, v in recs:
        if not rec.get("has_draft"):
            continue
        if v["severity"] == "READY":
            ready += 1
        elif v["severity"] == "WARNING":
            warn += 1
            if len(samples["warnings"]) < 15:
                samples["warnings"].append({"id": rec["id"], "title": rec.get("title"), "codes": v["codes"]})
        else:
            err += 1
            if len(samples["errors"]) < 15:
                samples["errors"].append({"id": rec["id"], "title": rec.get("title"), "codes": v["codes"]})
        if v["conflict"] != "none":
            conflicts += 1
        if (rec.get("draft_seo_title") or "") != (rec.get("current_seo_title") or ""):
            t_changes += 1
        if (rec.get("draft_seo_description") or "") != (rec.get("current_seo_description") or ""):
            m_changes += 1
    return {"selected": len(ids), "with_drafts": ready + warn + err,
            "ready": ready, "warnings": warn, "errors": err, "conflicts": conflicts,
            "title_changes": t_changes, "meta_changes": m_changes, "samples": samples,
            "requires_confirmation": (ready + warn) > 100}


@api2.post("/bulk/publish")
async def bulk_publish(payload: dict = Body(...), user: dict = Depends(require_permission("publish"))):
    rtype = payload.get("resource_type", "product")
    source = resolve_source(user, None)
    allow_warnings = bool(payload.get("allow_warnings"))
    ids = await _resolve_ids(rtype, payload, source)
    if not ids:
        raise HTTPException(status_code=400, detail="No records selected")
    recs = await _build_selection_records(rtype, ids, source)

    # build publishable item list (READY only by default; WARNING if acknowledged). Never ERROR/conflict.
    items_src = []
    for rec, v in recs:
        if not rec.get("has_draft"):
            continue
        if v["severity"] == "ERROR":
            continue
        if v["severity"] == "WARNING" and not allow_warnings:
            continue
        items_src.append((rec, v))
    if not items_src:
        raise HTTPException(status_code=400, detail="No publishable (Ready) drafts in selection")

    # idempotency: dedupe double-submit of the same effective change set
    sig = hashlib.sha1(("|".join(sorted(
        f"{r['id']}:{v['effective_title']}:{v['effective_meta']}" for r, v in items_src))
    ).encode()).hexdigest()
    existing = await db.publish_jobs.find_one(
        {"idempotency_key": sig, "status": {"$in": ["queued", "running", "recovering"]}}, {"_id": 0})
    if existing:
        return {"job_id": existing["id"], "deduped": True, "status": existing["status"]}

    job_id = f"PUB-{uuid.uuid4().hex[:8].upper()}"
    cid = bc.new_correlation_id()
    await db.publish_jobs.insert_one({
        "id": job_id, "type": "bulk_publish", "status": "queued", "resource_type": rtype,
        "created_by": user["email"], "actor_role": user.get("role"), "created_at": now_iso(),
        "started_at": None, "completed_at": None, "correlation_id": cid,
        "idempotency_key": sig, "source": source, "progress": 0,
        "options": {"allow_warnings": allow_warnings, "ready_only": not allow_warnings},
        "counts": {"total": len(items_src)},
        "message": f"Queued {len(items_src)} records",
    })
    item_docs = []
    for rec, v in items_src:
        item_docs.append({
            "id": f"PITM-{uuid.uuid4().hex[:10]}", "job_id": job_id, "kind": "publish",
            "resource_type": rtype, "resource_id": rec["id"], "shopify_id": rec.get(_idf(rtype)),
            "resource_title": rec.get("title"), "status": "queued",
            "before": {"title": rec.get("current_seo_title"), "description": rec.get("current_seo_description")},
            "after": {"title": v["effective_title"], "description": v["effective_meta"]},
            "validation": {"severity": v["severity"], "codes": v["codes"]},
            "retry_count": 0, "conflict_state": "none", "last_error": None,
        })
    for i in range(0, len(item_docs), 2000):
        await db.publish_items.insert_many(item_docs[i:i + 2000])
    bulk_jobs.launch(bulk_jobs.run_bulk_publish(job_id))
    return {"job_id": job_id, "queued": len(item_docs), "correlation_id": cid}


# ============================ BULK: jobs ============================
@api2.get("/bulk/jobs")
async def list_publish_jobs(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 25):
    page_size = min(max(page_size, 1), 100)
    total = await db.publish_jobs.count_documents({})
    items = await db.publish_jobs.find({}, {"_id": 0}).sort("created_at", -1) \
        .skip((max(page, 1) - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api2.get("/bulk/jobs/{job_id}")
async def get_publish_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.publish_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@api2.get("/bulk/jobs/{job_id}/items")
async def get_publish_items(job_id: str, user: dict = Depends(get_current_user),
                            page: int = 1, page_size: int = 50, status: str = None):
    q = {"job_id": job_id}
    if status:
        q["status"] = status
    page_size = min(max(page_size, 1), 200)
    total = await db.publish_items.count_documents(q)
    items = await db.publish_items.find(q, {"_id": 0}).skip((max(page, 1) - 1) * page_size) \
        .limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api2.post("/bulk/jobs/{job_id}/retry")
async def retry_failed(job_id: str, user: dict = Depends(require_permission("publish"))):
    job = await db.publish_jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # requeue only retryable failed items (transient errors); never permanent ones
    n = 0
    async for it in db.publish_items.find({"job_id": job_id, "status": "failed"}):
        if bc.is_retryable(it.get("last_error") or ""):
            await db.publish_items.update_one({"id": it["id"]},
                {"$set": {"status": "queued", "last_error": None}})
            n += 1
    if n == 0:
        return {"requeued": 0, "message": "No retryable failed records"}
    await db.publish_jobs.update_one({"id": job_id}, {"$set": {"status": "running"}})
    launcher = bulk_jobs.run_bulk_rollback if job.get("type") == "bulk_rollback" else bulk_jobs.run_bulk_publish
    bulk_jobs.launch(launcher(job_id))
    return {"requeued": n}


@api2.post("/bulk/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: dict = Depends(require_permission("publish"))):
    job = await db.publish_jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] in ("completed", "completed_with_errors", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Job is not cancellable")
    bulk_jobs._cancelled.add(job_id)
    await db.publish_jobs.update_one({"id": job_id}, {"$set": {"message": "Cancellation requested"}})
    return {"cancelling": True}


@api2.post("/bulk/jobs/{job_id}/rollback-preview")
async def rollback_preview(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.publish_jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rtype = job["resource_type"]
    col = _rescol(rtype)
    total = restorable = conflicts = 0
    async for it in db.publish_items.find({"job_id": job_id, "status": {"$in": ["verified", "unverified"]}}):
        total += 1
        rec = await col.find_one({"id": it["resource_id"]}, {"_id": 0, "current_seo_title": 1,
                                                             "current_seo_description": 1})
        if not rec:
            conflicts += 1
            continue
        if (rec.get("current_seo_title") or None) != (it["after"]["title"] or None) or \
           (rec.get("current_seo_description") or None) != (it["after"]["description"] or None):
            conflicts += 1
        else:
            restorable += 1
    return {"job_id": job_id, "published": total, "restorable": restorable, "conflicts": conflicts}


@api2.post("/bulk/jobs/{job_id}/rollback")
async def rollback_job(job_id: str, payload: dict = Body(default={}),
                       user: dict = Depends(require_permission("rollback"))):
    job = await db.publish_jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rtype = job["resource_type"]
    rb_id = f"RB-{uuid.uuid4().hex[:8].upper()}"
    cid = bc.new_correlation_id()
    src_items = await db.publish_items.find(
        {"job_id": job_id, "status": {"$in": ["verified", "unverified"]}}, {"_id": 0}).to_list(None)
    if not src_items:
        raise HTTPException(status_code=400, detail="No successfully published records to roll back")
    await db.publish_jobs.insert_one({
        "id": rb_id, "type": "bulk_rollback", "status": "queued", "resource_type": rtype,
        "created_by": user["email"], "actor_role": user.get("role"), "created_at": now_iso(),
        "correlation_id": cid, "rollback_of": job_id, "source": job.get("source"),
        "progress": 0, "counts": {"total": len(src_items)},
        "message": f"Rollback of {job_id}",
    })
    rb_items = []
    for it in src_items:
        rb_items.append({
            "id": f"PITM-{uuid.uuid4().hex[:10]}", "job_id": rb_id, "kind": "rollback",
            "resource_type": rtype, "resource_id": it["resource_id"], "shopify_id": it.get("shopify_id"),
            "resource_title": it.get("resource_title"), "status": "queued",
            "before": it["before"],     # original value → restore target
            "after": it["after"],       # published value → current must still equal this
            "origin_audit_id": it.get("audit_id"),
            "retry_count": 0, "conflict_state": "none",
        })
    for i in range(0, len(rb_items), 2000):
        await db.publish_items.insert_many(rb_items[i:i + 2000])
    bulk_jobs.launch(bulk_jobs.run_bulk_rollback(rb_id))
    return {"job_id": rb_id, "queued": len(rb_items)}


@api2.post("/bulk/reconcile")
async def reconcile(user: dict = Depends(require_permission("settings"))):
    return await bulk_jobs.reconcile_publish_state()


@api2.post("/bulk/recover")
async def recover(user: dict = Depends(require_permission("settings"))):
    """Admin maintenance: re-drive any in-flight bulk jobs from MongoDB state
    (same routine that runs on worker startup). Idempotent and safe to call."""
    await bulk_jobs.recover_jobs_on_startup()
    return {"recovered": True}


@api2.post("/bulk/resolve-conflict")
async def resolve_conflict(payload: dict = Body(...), user: dict = Depends(require_permission("edit"))):
    rtype = payload.get("resource_type", "product")
    rid = payload.get("id")
    resolution = payload.get("resolution")  # keep_shopify | keep_draft
    col = _rescol(rtype)
    rec = await col.find_one({"id": rid})
    if not rec:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resolution == "keep_shopify":
        await col.update_one({"id": rid}, {"$set": {
            "has_draft": False, "draft_seo_title": None, "draft_seo_description": None,
            "draft_base_title": None, "draft_base_description": None,
            "publication_status": "published", "conflict_resolved": True, "seo_conflict": False}})
    elif resolution == "keep_draft":
        # rebase draft onto the current Shopify value so it can publish over it
        await col.update_one({"id": rid}, {"$set": {
            "draft_base_title": rec.get("current_seo_title"),
            "draft_base_description": rec.get("current_seo_description"),
            "conflict_resolved": True, "seo_conflict": False}})
    else:
        raise HTTPException(status_code=400, detail="resolution must be keep_shopify or keep_draft")
    return await col.find_one({"id": rid}, {"_id": 0})


# ============================ CSV ============================
@api2.post("/csv/export")
async def csv_export(payload: dict = Body(...), user: dict = Depends(require_permission("csv"))):
    rtype = payload.get("resource_type", "product")
    source = resolve_source(user, None)
    if payload.get("ids"):
        q = {"id": {"$in": list(payload["ids"])}}
    else:
        q = _bulk_query(source, {**(payload.get("filter") or {}), "resource_type": rtype})
    job_id = f"CSVX-{uuid.uuid4().hex[:8].upper()}"
    await db.csv_jobs.insert_one({
        "id": job_id, "kind": "export", "status": "queued", "resource_type": rtype,
        "query": q, "created_by": user["email"], "created_at": now_iso(),
        "download_token": uuid.uuid4().hex, "progress": 0,
        "filename": f"urbandotted_{rtype}_seo_{job_id}.csv",
    })
    bulk_jobs.launch(bulk_jobs.run_csv_export(job_id))
    return {"job_id": job_id, "status": "queued"}


@api2.get("/csv/jobs")
async def csv_jobs_list(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 25):
    page_size = min(max(page_size, 1), 100)
    total = await db.csv_jobs.count_documents({})
    items = await db.csv_jobs.find({}, {"_id": 0, "query": 0, "file_path": 0}).sort("created_at", -1) \
        .skip((max(page, 1) - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api2.get("/csv/jobs/{job_id}")
async def csv_job_detail(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.csv_jobs.find_one({"id": job_id}, {"_id": 0, "query": 0, "file_path": 0})
    if not job:
        raise HTTPException(status_code=404, detail="CSV job not found")
    return job


@api2.get("/csv/download/{job_id}")
async def csv_download(job_id: str, token: str = Query(...), user: dict = Depends(require_permission("csv"))):
    job = await db.csv_jobs.find_one({"id": job_id})
    if not job or job.get("kind") != "export":
        raise HTTPException(status_code=404, detail="Export not found")
    if token != job.get("download_token"):
        raise HTTPException(status_code=403, detail="Invalid download token")
    path = job.get("file_path")
    if not path or not os.path.isfile(path):
        # temporary artifact gone (e.g., restart) — regenerate from persisted params
        await db.csv_jobs.update_one({"id": job_id}, {"$set": {"status": "queued"}})
        await bulk_jobs.run_csv_export(job_id)
        job = await db.csv_jobs.find_one({"id": job_id})
        path = job.get("file_path")
        if not path or not os.path.isfile(path):
            raise HTTPException(status_code=410, detail="Export unavailable; please regenerate")
    return FileResponse(path, media_type="text/csv", filename=job.get("filename", "export.csv"))


@api2.post("/csv/import")
async def csv_import(file: UploadFile = File(...), resource_type: str = Form("product"),
                     source: str = Form(None), user: dict = Depends(require_permission("csv"))):
    content = await file.read()
    ds = resolve_source(user, source)
    try:
        result = await csv_service.parse_and_validate(content, file.filename, resource_type, user, ds)
    except csv_service.CsvError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message, **e.extra})
    return result


@api2.get("/csv/import/{csv_job_id}/rows")
async def csv_import_rows(csv_job_id: str, user: dict = Depends(get_current_user),
                          severity: str = None, page: int = 1, page_size: int = 50):
    q = {"csv_job_id": csv_job_id}
    if severity:
        q["severity"] = severity
    page_size = min(max(page_size, 1), 200)
    total = await db.csv_rows.count_documents(q)
    items = await db.csv_rows.find(q, {"_id": 0}).skip((max(page, 1) - 1) * page_size) \
        .limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api2.post("/csv/import/{csv_job_id}/confirm")
async def csv_import_confirm(csv_job_id: str, payload: dict = Body(default={}),
                             user: dict = Depends(require_permission("csv"))):
    job = await db.csv_jobs.find_one({"id": csv_job_id})
    if not job:
        raise HTTPException(status_code=404, detail="CSV import not found")
    include_warnings = bool(payload.get("include_warnings"))
    bulk_jobs.launch(bulk_jobs.run_csv_import_confirm(csv_job_id, include_warnings))
    return {"job_id": csv_job_id, "status": "running", "include_warnings": include_warnings}
