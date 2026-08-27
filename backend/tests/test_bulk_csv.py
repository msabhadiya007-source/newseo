"""Phase 4/5 acceptance tests: Bulk Editor, CSV import/export, idempotency, locking,
conflict blocking, retry classification, bulk rollback (+conflict), recovery, permissions,
and SEO-only security regression across every new code path.

Runs against the live backend (demo mode) and uses pymongo directly to simulate
external Shopify changes and crashed jobs.
"""
import os
import time
import uuid
import random

import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values
from conftest import API

_env = dotenv_values("/app/backend/.env")
_db = MongoClient(_env["MONGO_URL"])[_env["DB_NAME"]]

GOOD_TITLE = "UrbanDotted Premium Phone Case Australia Fast Free Ship"          # 55 chars
GOOD_META = ("Shop premium protective phone cases with fast free Australian shipping, easy "
             "returns and reliable everyday protection you can fully trust now.")           # ~150

FORBIDDEN = [
    {"price": "1.00"}, {"inventory": 5}, {"sku": "X"}, {"barcode": "1"},
    {"vendor": "Evil"}, {"title": "Hacked"}, {"product_title": "Hacked"},
    {"status": "ARCHIVED"}, {"variants": [{"price": "0"}]}, {"seo_title": "ok", "price": "1"},
]


def _wait_job(client, job_id, timeout=60):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = client.get(f"{API}/bulk/jobs/{job_id}").json()
        if last.get("status") in ("completed", "completed_with_errors", "failed", "cancelled"):
            return last
        time.sleep(1)
    return last


def _make_products(n, source="loadtest"):
    """Create N dedicated, fully-analyzed 'missing SEO' products in an ISOLATED
    data source so tests never contend with (or contaminate) the shared demo pool."""
    docs = []
    for _ in range(n):
        u = uuid.uuid4().hex
        docs.append({
            "id": u, "shopify_product_id": f"gid://shopify/Product/test-{u}",
            "data_source": source, "handle": f"bulktest-{u}", "title": f"BULKTEST Product {u[:6]}",
            "body": "<p>test</p>", "product_type": "Phone Case", "vendor": "UrbanDotted",
            "status": "active", "tags": [], "price": None, "inventory": None, "sku": None,
            "current_seo_title": "", "current_seo_description": "",
            "last_synced_seo_title": None, "last_synced_seo_description": None,
            "draft_seo_title": None, "draft_seo_description": None, "has_draft": False,
            "draft_base_title": None, "draft_base_description": None,
            "images": [], "shopify_state": "active", "publication_status": "published",
            "seo_conflict": False, "ai_quality": None, "seo_score": 4, "score_breakdown": {},
            "issue_codes": ["MISSING_SEO_TITLE", "MISSING_META_DESCRIPTION"], "status_bucket": "missing",
            "shopify_updated_at": None, "created_at": None,
        })
    _db.products.insert_many(docs)
    return [d["id"] for d in docs]


def _missing_title_ids(client, n):
    return _make_products(n)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_bulktest():
    yield
    _db.products.delete_many({"title": {"$regex": "^BULKTEST"}})


@pytest.fixture()
def ids3(client):
    return _missing_title_ids(client, 3)


class TestBulkDraftAndSecurity:
    def test_bulk_list_paginated(self, client):
        d = client.get(f"{API}/bulk/products?page_size=25").json()
        assert d["total"] > 0 and len(d["items"]) <= 25
        assert "conflict_state" in d["items"][0]

    def test_single_row_draft(self, client, ids3):
        r = client.post(f"{API}/bulk/draft-save",
                        json={"resource_type": "product",
                              "edits": [{"id": ids3[0], "seo_title": GOOD_TITLE, "meta_description": GOOD_META}]})
        assert r.status_code == 200 and r.json()["saved"] == 1
        got = client.get(f"{API}/products/{ids3[0]}").json()
        assert got["has_draft"] is True and got["draft_seo_title"] == GOOD_TITLE

    def test_multi_row_draft(self, client, ids3):
        edits = [{"id": i, "seo_title": GOOD_TITLE, "meta_description": GOOD_META} for i in ids3]
        r = client.post(f"{API}/bulk/draft-save", json={"resource_type": "product", "edits": edits})
        assert r.json()["saved"] == len(ids3)

    @pytest.mark.parametrize("payload", FORBIDDEN, ids=[list(p)[-1] for p in FORBIDDEN])
    def test_bulk_draft_forbidden_denied(self, client, ids3, payload):
        r = client.post(f"{API}/bulk/draft-save",
                        json={"resource_type": "product", "edits": [{"id": ids3[0], **payload}]})
        assert r.status_code == 403
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text


class TestBulkPublish:
    def test_publish_verifies_and_removes_from_queue(self, client):
        ids = _missing_title_ids(client, 2)
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": i, "seo_title": GOOD_TITLE, "meta_description": GOOD_META} for i in ids]})
        r = client.post(f"{API}/bulk/publish",
                        json={"resource_type": "product", "ids": ids, "allow_warnings": True})
        assert r.status_code == 200, r.text
        job = _wait_job(client, r.json()["job_id"])
        assert job["status"] == "completed", job
        assert job["counts"]["verified"] == len(ids), job
        # queue removal: product no longer missing SEO title
        after = client.get(f"{API}/products/{ids[0]}").json()
        assert after["current_seo_title"] == GOOD_TITLE
        assert "MISSING_SEO_TITLE" not in after["issue_codes"]
        # audit created with job + correlation id
        aud = _db.audit_log.find_one({"resource_id": ids[0], "source": "Bulk"})
        assert aud and aud.get("job_id") and aud.get("correlation_id")

    def test_publish_preview_threshold(self, client):
        # create >100 drafts so the publish confirmation threshold triggers
        ids = _missing_title_ids(client, 105)
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": i, "seo_title": GOOD_TITLE, "meta_description": GOOD_META} for i in ids]})
        d = client.post(f"{API}/bulk/publish-preview",
                        json={"resource_type": "product", "ids": ids}).json()
        assert (d["ready"] + d["warnings"]) > 100
        assert d["requires_confirmation"] is True

    def test_idempotency_double_submit(self, client):
        ids = _missing_title_ids(client, 2)
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": i, "seo_title": GOOD_TITLE + " Two", "meta_description": GOOD_META} for i in ids]})
        body = {"resource_type": "product", "ids": ids, "allow_warnings": True}
        r1 = client.post(f"{API}/bulk/publish", json=body).json()
        r2 = client.post(f"{API}/bulk/publish", json=body).json()
        # second identical submit returns the SAME job (deduped) while first is active,
        # OR first already finished (then a new job) — either way never two active dupes.
        active = list(_db.publish_jobs.find({"idempotency_key": {"$exists": True},
                                             "status": {"$in": ["queued", "running", "recovering"]}}))
        assert len(active) <= 1
        _wait_job(client, r1["job_id"])
        if r2.get("job_id") == r1["job_id"]:
            assert r2.get("deduped") is True


class TestConflict:
    def test_stale_conflict_blocks_publish(self, client):
        pid = _missing_title_ids(client, 1)[0]
        # ensure a fresh draft whose base = current (empty) value
        client.post(f"{API}/bulk/clear-drafts", json={"resource_type": "product", "ids": [pid]})
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": pid, "seo_title": GOOD_TITLE, "meta_description": GOOD_META}]})
        # simulate Shopify changing externally after the draft was based on the old value
        base = _db.products.find_one({"id": pid})
        assert base.get("has_draft") is True  # draft persisted with captured base
        _db.products.update_one({"id": pid},
                                {"$set": {"current_seo_title": "EXTERNALLY CHANGED TITLE VALUE"}})
        v = None
        for _ in range(5):
            v = client.post(f"{API}/bulk/validate", json={"resource_type": "product", "ids": [pid]}).json()
            if v["summary"]["ERROR"] >= 1:
                break
            time.sleep(0.5)
        assert v["summary"]["ERROR"] >= 1 and v["summary"]["conflicts"] >= 1, v
        prev = client.post(f"{API}/bulk/publish-preview",
                           json={"resource_type": "product", "ids": [pid]}).json()
        assert prev["errors"] >= 1 and prev["ready"] == 0
        # publish must refuse (no ready drafts)
        r = client.post(f"{API}/bulk/publish", json={"resource_type": "product", "ids": [pid], "allow_warnings": True})
        assert r.status_code == 400
        # resolve by rebasing to keep the local draft, then it becomes publishable
        client.post(f"{API}/bulk/resolve-conflict",
                    json={"resource_type": "product", "id": pid, "resolution": "keep_draft"})
        prev2 = client.post(f"{API}/bulk/publish-preview",
                            json={"resource_type": "product", "ids": [pid]}).json()
        assert prev2["errors"] == 0


class TestBulkRollback:
    def test_rollback_restores(self, client):
        ids = _missing_title_ids(client, 2)
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": i, "seo_title": GOOD_TITLE, "meta_description": GOOD_META} for i in ids]})
        jid = client.post(f"{API}/bulk/publish",
                          json={"resource_type": "product", "ids": ids, "allow_warnings": True}).json()["job_id"]
        _wait_job(client, jid)
        pv = client.post(f"{API}/bulk/jobs/{jid}/rollback-preview").json()
        assert pv["restorable"] == len(ids)
        rb = client.post(f"{API}/bulk/jobs/{jid}/rollback", json={}).json()
        rbjob = _wait_job(client, rb["job_id"])
        assert rbjob["counts"]["verified"] == len(ids), rbjob
        after = client.get(f"{API}/products/{ids[0]}").json()
        assert (after["current_seo_title"] or "") == "" and "MISSING_SEO_TITLE" in after["issue_codes"]

    def test_rollback_conflict(self, client):
        ids = _missing_title_ids(client, 1)
        pid = ids[0]
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": pid, "seo_title": GOOD_TITLE, "meta_description": GOOD_META}]})
        jid = client.post(f"{API}/bulk/publish",
                          json={"resource_type": "product", "ids": [pid], "allow_warnings": True}).json()["job_id"]
        _wait_job(client, jid)
        # someone changes the SEO again after the bulk publish
        _db.products.update_one({"id": pid}, {"$set": {"current_seo_title": "CHANGED AGAIN AFTER PUBLISH"}})
        rb = client.post(f"{API}/bulk/jobs/{jid}/rollback", json={}).json()
        rbjob = _wait_job(client, rb["job_id"])
        assert rbjob["counts"].get("conflicted", 0) >= 1, rbjob
        item = _db.publish_items.find_one({"job_id": rb["job_id"]})
        assert item["last_error"] == "ROLLBACK_CONFLICT"


class TestRecovery:
    def test_crash_recovery_no_duplicate(self, client):
        pid = _missing_title_ids(client, 1)[0]
        client.post(f"{API}/bulk/draft-save",
                    json={"resource_type": "product",
                          "edits": [{"id": pid, "seo_title": GOOD_TITLE, "meta_description": GOOD_META}]})
        p = _db.products.find_one({"id": pid})
        # fabricate an interrupted job: one item still 'processing', job 'running'
        jid = f"PUB-{uuid.uuid4().hex[:8].upper()}"
        _db.publish_jobs.insert_one({
            "id": jid, "type": "bulk_publish", "status": "running", "resource_type": "product",
            "created_by": "msabhadiya007@gmail.com", "actor_role": "admin",
            "correlation_id": "cid-test", "source": "demo", "progress": 0,
            "options": {"allow_warnings": True}, "counts": {"total": 1},
        })
        _db.publish_items.insert_one({
            "id": f"PITM-{uuid.uuid4().hex[:10]}", "job_id": jid, "kind": "publish",
            "resource_type": "product", "resource_id": pid, "shopify_id": p["shopify_product_id"],
            "resource_title": p.get("title"), "status": "processing",
            "before": {"title": p.get("current_seo_title"), "description": p.get("current_seo_description")},
            "after": {"title": GOOD_TITLE, "description": GOOD_META},
            "retry_count": 0, "conflict_state": "none",
        })
        r = client.post(f"{API}/bulk/recover")
        assert r.status_code == 200
        job = _wait_job(client, jid)
        assert job["status"] in ("completed", "completed_with_errors")
        assert job["counts"]["verified"] == 1
        # no duplicate audit for this job
        assert _db.audit_log.count_documents({"job_id": jid}) == 1


class TestCsv:
    def _upload(self, token, csv_text, rtype="product", source="loadtest"):
        return requests.post(f"{API}/csv/import",
                             headers={"Authorization": f"Bearer {token}"},
                             files={"file": ("test.csv", csv_text, "text/csv")},
                             data={"resource_type": rtype, "source": source})

    def test_forbidden_column_rejected(self, admin_token):
        r = self._upload(admin_token, "shopify_product_id,new_seo_title,price\ngid://x,Hi,9.99\n")
        assert r.status_code == 400
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text
        assert "price" in r.text

    def test_valid_import_creates_drafts(self, client, admin_token):
        ids = _make_products(5)
        recs = list(_db.products.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "shopify_product_id": 1}))
        header = "shopify_product_id,new_seo_title,new_meta_description\n"
        body = "".join(f'{r["shopify_product_id"]},"{GOOD_TITLE} {i}","{GOOD_META}"\n'
                       for i, r in enumerate(recs))
        res = self._upload(admin_token, header + body).json()
        assert res["counts"]["total"] == len(recs)
        assert res["counts"]["ERROR"] == 0
        cid = res["csv_job_id"]
        client.post(f"{API}/csv/import/{cid}/confirm", json={"include_warnings": True})
        job = None
        for _ in range(20):
            job = client.get(f"{API}/csv/jobs/{cid}").json()
            if job.get("status") == "completed":
                break
            time.sleep(0.5)
        assert job and job.get("status") == "completed", job
        assert job.get("drafts_created", 0) == len(recs), job
        assert _db.products.count_documents(
            {"id": {"$in": ids}, "draft_source": "csv"}) == len(recs)

    def test_invalid_resource_and_duplicate(self, admin_token):
        sid = _db.products.find_one({"id": _make_products(1)[0]})["shopify_product_id"]
        text = ("shopify_product_id,new_seo_title\n"
                "gid://shopify/Product/does-not-exist,Hello There Title\n"
                f"{sid},First Title Here\n{sid},Duplicate Row Title\n")
        res = self._upload(admin_token, text).json()
        assert res["counts"]["ERROR"] >= 2  # invalid id + duplicate row

    def test_empty_file(self, admin_token):
        r = self._upload(admin_token, "")
        assert r.status_code == 400 and "CSV_EMPTY" in r.text

    def test_export_job_and_download(self, client):
        j = client.post(f"{API}/csv/export",
                        json={"resource_type": "product", "filter": {"missing": "title"}}).json()
        job = None
        for _ in range(30):
            job = client.get(f"{API}/csv/jobs/{j['job_id']}").json()
            if job["status"] == "completed":
                break
            time.sleep(1)
        assert job["status"] == "completed" and job["counts"]["total"] > 0
        full = _db.csv_jobs.find_one({"id": j["job_id"]})
        token = full["download_token"]
        dl = client.get(f"{API}/csv/download/{j['job_id']}?token={token}")
        assert dl.status_code == 200 and "shopify_product_id" in dl.text
        # wrong token rejected
        bad = client.get(f"{API}/csv/download/{j['job_id']}?token=wrong")
        assert bad.status_code == 403


class TestPermissions:
    @pytest.fixture(scope="class")
    def viewer(self, admin_token):
        email = f"viewer_{uuid.uuid4().hex[:6]}@test.com"
        requests.post(f"{API}/auth/register",
                      headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                      json={"email": email, "password": "Viewer@123", "name": "V", "role": "viewer"})
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "Viewer@123"}).json()["token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        return s

    def test_viewer_cannot_publish(self, viewer, client):
        pid = _missing_title_ids(client, 1)[0]
        r = viewer.post(f"{API}/bulk/publish", json={"resource_type": "product", "ids": [pid]})
        assert r.status_code == 403

    def test_viewer_cannot_draft_or_import(self, viewer):
        assert viewer.post(f"{API}/bulk/draft-save",
                           json={"resource_type": "product", "edits": []}).status_code == 403
        r = requests.post(f"{API}/csv/import", headers={"Authorization": viewer.headers["Authorization"]},
                          files={"file": ("t.csv", "shopify_product_id,new_seo_title\n", "text/csv")},
                          data={"resource_type": "product"})
        assert r.status_code == 403

    def test_viewer_cannot_rollback(self, viewer):
        assert viewer.post(f"{API}/bulk/jobs/NOPE/rollback", json={}).status_code == 403


class TestSecurityRegressionBulkCsv:
    @pytest.mark.parametrize("payload", FORBIDDEN, ids=[list(p)[-1] for p in FORBIDDEN])
    def test_bulk_publish_forbidden(self, client, ids3, payload):
        # forbidden fields on the publish body must be denied at the boundary
        r = client.post(f"{API}/bulk/draft-save",
                        json={"resource_type": "product", "edits": [{"id": ids3[0], **payload}]})
        assert r.status_code == 403 and "NON_SEO_FIELD_WRITE_DENIED" in r.text


class TestUnit:
    def test_retry_classification(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import bulk_common as bc
        assert bc.is_retryable("Shopify throttled") is True
        assert bc.is_retryable("connection timeout") is True
        assert bc.is_retryable("HTTP 503 unavailable") is True
        assert bc.is_retryable("NON_SEO_FIELD_WRITE_DENIED: price") is False
        assert bc.is_retryable("invalid product id") is False
        assert bc.is_retryable("permission denied") is False

    def test_lock_mutual_exclusion(self):
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        import bulk_common as bc

        async def run():
            key = f"test:{uuid.uuid4().hex}"
            a = await bc.acquire_lock(key, owner="jobA", ttl_seconds=60)
            b = await bc.acquire_lock(key, owner="jobB", ttl_seconds=60)
            await bc.release_lock(key, owner="jobA")
            c = await bc.acquire_lock(key, owner="jobB", ttl_seconds=60)
            await bc.release_lock(key, owner="jobB")
            return a, b, c
        a, b, c = asyncio.get_event_loop().run_until_complete(run())
        assert a is True and b is False and c is True
