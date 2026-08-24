"""Core flows: dashboard metrics, products list/filters, SEO detection, draft->publish->verify->queue
removal, rollback, collections, jobs/sync, audit, settings, diagnostics."""
import os
import time

import pytest
from conftest import API, BASE_URL


class TestHealth:
    def test_diagnostics(self, client):
        r = client.get(f"{API}/diagnostics")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["database_connected"] is True
        assert "shopify_connected" in d and "active_jobs" in d

    def test_health_and_ready_direct(self):
        """/health and /ready lack the /api prefix -> not reachable through ingress."""
        import requests
        r = requests.get(f"{BASE_URL}/health", timeout=20)
        assert r.status_code == 200
        if "application/json" not in r.headers.get("content-type", ""):
            pytest.skip("/health not routed to backend via ingress (missing /api prefix)")
        assert r.json()["status"] == "ok"


class TestDashboardMetrics:
    def test_metrics_non_zero_and_consistent(self, client):
        r = client.get(f"{API}/dashboard/metrics")
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["empty"] is False, "No data synced; run POST /api/sync first"
        assert m["total"] > 0
        buckets = m["buckets"]
        for b in ["missing", "critical", "needs_improvement", "good", "optimised"]:
            assert b in buckets, f"missing bucket {b}"
            assert buckets[b] > 0, f"bucket {b} is empty ({buckets})"
        assert sum(buckets.values()) == m["total"], f"buckets {buckets} != total {m['total']}"
        assert 0 < m["health"] <= 100
        assert m["missing_seo"] == buckets["missing"]
        assert m["fully_optimised"] == buckets["optimised"]
        assert m["issues"].get("MISSING_SEO_TITLE", 0) > 0
        assert m["collections_total"] > 0
        assert m["data_source"] == "demo"

    def test_metrics_match_products_endpoint(self, client):
        m = client.get(f"{API}/dashboard/metrics").json()
        p = client.get(f"{API}/products?page_size=1").json()
        assert p["tabs"]["all"] == m["total"]
        assert p["tabs"]["missing"] == m["buckets"]["missing"]

    def test_metrics_requires_auth(self, anon):
        assert anon.get(f"{API}/dashboard/metrics").status_code == 401


class TestProductsList:
    def test_pagination(self, client):
        p1 = client.get(f"{API}/products?page=1&page_size=5").json()
        assert len(p1["items"]) == 5 and p1["page_size"] == 5
        p2 = client.get(f"{API}/products?page=2&page_size=5").json()
        ids1 = {i["id"] for i in p1["items"]}
        ids2 = {i["id"] for i in p2["items"]}
        assert not (ids1 & ids2), "page 2 overlaps page 1"
        assert p1["total"] == p2["total"] > 5
        assert "_id" not in p1["items"][0]

    def test_page_size_capped(self, client):
        r = client.get(f"{API}/products?page_size=5000").json()
        assert r["page_size"] == 100 and len(r["items"]) <= 100

    @pytest.mark.parametrize("bucket", ["all", "missing", "critical", "needs_improvement",
                                        "good", "optimised", "drafts"])
    def test_bucket_tabs(self, client, bucket):
        r = client.get(f"{API}/products?bucket={bucket}&page_size=10")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == d["tabs"][bucket], f"{bucket}: total {d['total']} != tab {d['tabs'][bucket]}"
        for item in d["items"]:
            if bucket == "drafts":
                assert item["has_draft"] is True
            elif bucket != "all":
                assert item["status_bucket"] == bucket

    def test_issue_filter(self, client):
        d = client.get(f"{API}/products?issue=MISSING_SEO_TITLE&page_size=10").json()
        assert d["total"] > 0
        for item in d["items"]:
            assert "MISSING_SEO_TITLE" in item["issue_codes"]

    def test_search(self, client):
        sample = client.get(f"{API}/products?page_size=1").json()["items"][0]
        term = sample["title"].split()[0]
        d = client.get(f"{API}/products", params={"search": term, "page_size": 10}).json()
        assert d["total"] > 0
        for item in d["items"]:
            hay = " ".join(str(item.get(k) or "") for k in
                           ["title", "handle", "shopify_product_id", "current_seo_title"]).lower()
            assert term.lower() in hay

    def test_score_range_filter(self, client):
        d = client.get(f"{API}/products?min_score=80&max_score=100&page_size=10").json()
        for item in d["items"]:
            assert 80 <= item["seo_score"] <= 100

    def test_get_product_detail_and_404(self, client):
        pid = client.get(f"{API}/products?page_size=1").json()["items"][0]["id"]
        r = client.get(f"{API}/products/{pid}")
        assert r.status_code == 200
        p = r.json()
        assert p["id"] == pid and "_id" not in p
        assert "issue_codes" in p and "score_breakdown" in p or "seo_score" in p
        assert client.get(f"{API}/products/does-not-exist").status_code == 404


class TestSeoDetection:
    def test_missing_bucket_products_lack_seo(self, client):
        d = client.get(f"{API}/products?bucket=missing&page_size=25").json()
        assert d["total"] > 0
        for item in d["items"]:
            codes = item["issue_codes"]
            assert ("MISSING_SEO_TITLE" in codes) or ("MISSING_META_DESCRIPTION" in codes)
            if "MISSING_SEO_TITLE" in codes:
                assert not (item.get("current_seo_title") or "").strip()

    def test_title_above_range_not_missing(self, client):
        d = client.get(f"{API}/products?issue=TITLE_ABOVE_RANGE&page_size=25").json()
        assert d["total"] > 0
        for item in d["items"]:
            assert item["status_bucket"] != "missing" or "MISSING_META_DESCRIPTION" in item["issue_codes"]
            assert (item.get("current_seo_title") or "").strip() != ""

    def test_duplicates_flagged(self, client):
        for code in ["DUPLICATE_TITLE", "DUPLICATE_META"]:
            d = client.get(f"{API}/products?issue={code}&page_size=5").json()
            assert d["total"] > 0, f"{code} never flagged"
            for item in d["items"]:
                assert code in item["issue_codes"]

    def test_optimised_products_have_no_issues(self, client):
        d = client.get(f"{API}/products?bucket=optimised&page_size=15").json()
        assert d["total"] > 0
        for item in d["items"]:
            assert item["issue_codes"] == [], f"{item['id']} optimised but has {item['issue_codes']}"
            assert item["seo_score"] >= 85


class TestAcceptanceDraftPublishVerify:
    """Acceptance: draft -> publish -> verify -> queue removal -> audit -> rollback."""

    GOOD_TITLE = "UrbanDotted Clear Phone Case Australia Slim Shockproof Cover"  # 58 chars
    GOOD_META = ("Shop the UrbanDotted clear phone case in Australia: slim, shockproof and drop tested "
                 "protection with fast local delivery and easy returns today.")  # ~150

    @pytest.fixture(scope="class")
    def target(self, admin_token):
        import requests
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {admin_token}"})
        d = s.get(f"{API}/products?issue=MISSING_SEO_TITLE&page_size=25").json()
        for item in d["items"]:
            if not (item.get("current_seo_title") or "").strip():
                return {"s": s, "id": item["id"]}
        pytest.fail("No product with missing SEO title found")

    def test_01_draft_saves_without_changing_bucket(self, target):
        s, pid = target["s"], target["id"]
        before = s.get(f"{API}/products/{pid}").json()
        r = s.patch(f"{API}/products/{pid}/seo-draft",
                    json={"seo_title": self.GOOD_TITLE, "meta_description": self.GOOD_META})
        assert r.status_code == 200, r.text
        after = s.get(f"{API}/products/{pid}").json()
        assert after["draft_seo_title"] == self.GOOD_TITLE
        assert after["draft_seo_description"] == self.GOOD_META
        assert after["has_draft"] is True
        assert after["publication_status"] == "draft"
        # live values untouched, bucket unchanged
        assert not (after.get("current_seo_title") or "")
        assert after["status_bucket"] == before["status_bucket"] == "missing"
        assert "MISSING_SEO_TITLE" in after["issue_codes"]

    def test_02_draft_appears_in_drafts_tab(self, target):
        s, pid = target["s"], target["id"]
        d = s.get(f"{API}/products?bucket=drafts&page_size=100").json()
        assert any(i["id"] == pid for i in d["items"]), "drafted product not in drafts tab"

    def test_03_publish_verifies_and_removes_from_queue(self, target):
        s, pid = target["s"], target["id"]
        metrics_before = s.get(f"{API}/dashboard/metrics").json()
        r = s.post(f"{API}/products/{pid}/publish-seo", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["verification"]["ok"] is True
        assert body["verification"]["verified"]["title"] == self.GOOD_TITLE
        assert body.get("audit_id")
        target["audit_id"] = body["audit_id"]

        p = s.get(f"{API}/products/{pid}").json()
        assert p["current_seo_title"] == self.GOOD_TITLE
        assert p["current_seo_description"] == self.GOOD_META
        assert p["has_draft"] is False
        assert p["draft_seo_title"] in (None, "")
        assert "MISSING_SEO_TITLE" not in p["issue_codes"], "still flagged missing after publish"
        assert "MISSING_META_DESCRIPTION" not in p["issue_codes"]
        assert p["status_bucket"] != "missing", "did not leave the Missing queue"
        assert p["seo_score"] > 0

        # queue removal confirmed via list endpoint
        q = s.get(f"{API}/products?issue=MISSING_SEO_TITLE&page_size=100&search=" + p["handle"]).json()
        assert all(i["id"] != pid for i in q["items"]), "product still in MISSING_SEO_TITLE queue"

        metrics_after = s.get(f"{API}/dashboard/metrics").json()
        assert metrics_after["buckets"]["missing"] < metrics_before["buckets"]["missing"], \
            "dashboard missing count did not decrease"

    def test_04_audit_record_created(self, target):
        s, pid = target["s"], target["id"]
        d = s.get(f"{API}/audit?page_size=50").json()
        rec = next((a for a in d["items"] if a["resource_id"] == pid), None)
        assert rec, "no audit record for published product"
        assert rec["resource_type"] == "product"
        assert "verified" in rec["result"]
        fields = {c["field"]: c for c in rec["changes"]}
        assert "seo_title" in fields
        assert fields["seo_title"]["new"] == self.GOOD_TITLE
        assert "_id" not in rec

    def test_05_rollback_restores_previous_value(self, target):
        s, pid = target["s"], target["id"]
        before = s.get(f"{API}/products/{pid}").json()
        assert before["current_seo_title"] == self.GOOD_TITLE
        r = s.post(f"{API}/products/{pid}/rollback", json={})
        assert r.status_code == 200, r.text
        p = s.get(f"{API}/products/{pid}").json()
        assert not (p.get("current_seo_title") or "").strip(), \
            f"rollback did not restore empty title, got {p.get('current_seo_title')!r}"
        assert "MISSING_SEO_TITLE" in p["issue_codes"], "not re-flagged after rollback"
        assert p["status_bucket"] == "missing"
        audit = s.get(f"{API}/audit?page_size=50").json()["items"]
        rb = next((a for a in audit if a["resource_id"] == pid and a["source"] == "Rollback"), None)
        assert rb, "no rollback audit record"

    def test_06_rollback_without_change_is_404(self, client):
        d = client.get(f"{API}/products?bucket=optimised&page_size=50").json()
        pid = None
        audited = {a["resource_id"] for a in client.get(f"{API}/audit?page_size=100").json()["items"]}
        for i in d["items"]:
            if i["id"] not in audited:
                pid = i["id"]
                break
        if not pid:
            pytest.skip("no un-audited product available")
        r = client.post(f"{API}/products/{pid}/rollback", json={})
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"

    def test_07_publish_nonexistent_product(self, client):
        r = client.post(f"{API}/products/no-such-id/publish-seo", json={"seo_title": "x"})
        assert r.status_code == 404, r.text


class TestCollections:
    def test_list_collections(self, client):
        r = client.get(f"{API}/collections")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] > 0
        item = d["items"][0]
        for k in ["id", "title", "seo_score", "status_bucket"]:
            assert k in item, f"collection missing {k}"
        assert "_id" not in item

    def test_collection_draft_then_publish(self, client):
        col = client.get(f"{API}/collections").json()["items"][0]
        cid = col["id"]
        title = "UrbanDotted Clear Cases Collection Australia Slim Shockproof"
        meta = ("Browse the UrbanDotted clear cases collection in Australia with slim shockproof "
                "protection, drop tested designs, fast shipping and simple returns.")
        r = client.patch(f"{API}/collections/{cid}/seo-draft",
                         json={"seo_title": title, "meta_description": meta})
        assert r.status_code == 200, r.text
        assert r.json()["draft_seo_title"] == title
        assert r.json()["has_draft"] is True

        r = client.post(f"{API}/collections/{cid}/publish-seo", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["verification"]["ok"] is True
        assert body["collection"]["current_seo_title"] == title
        assert body["collection"]["has_draft"] is False
        # verify persisted
        again = next(c for c in client.get(f"{API}/collections").json()["items"] if c["id"] == cid)
        assert again["current_seo_title"] == title
        assert again["current_seo_description"] == meta

    def test_collection_404(self, client):
        assert client.patch(f"{API}/collections/nope/seo-draft",
                            json={"seo_title": "x"}).status_code == 404


class TestSyncJobs:
    """DESTRUCTIVE: POST /api/sync deletes and regenerates all demo products, which races with
    the other test classes under xdist. Run with RUN_DESTRUCTIVE_SYNC=1 (ideally with -n 0)."""

    @pytest.mark.skipif(os.environ.get("RUN_DESTRUCTIVE_SYNC") != "1",
                        reason="destructive re-seed; set RUN_DESTRUCTIVE_SYNC=1 to run")
    def test_sync_creates_job_and_completes(self, client):
        r = client.post(f"{API}/sync", json={})
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        assert r.json()["status"] == "queued"
        status, job = None, None
        for _ in range(60):
            job = client.get(f"{API}/jobs/{job_id}").json()
            status = job["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(2)
        assert status == "completed", f"job ended as {status}: {job}"
        m = client.get(f"{API}/dashboard/metrics").json()
        assert m["total"] >= 2400, f"expected ~2500 products, got {m['total']}"

    def test_jobs_list_and_404(self, client):
        d = client.get(f"{API}/jobs").json()
        assert len(d["items"]) > 0
        assert "_id" not in d["items"][0]
        assert client.get(f"{API}/jobs/nope").status_code == 404

    def test_sync_status(self, client):
        d = client.get(f"{API}/sync/status").json()
        assert d["data_source"] == "demo"
        assert d["connected"] is False


class TestSettingsAudit:
    def test_get_settings(self, client):
        d = client.get(f"{API}/settings").json()
        assert d["rules"]["title_max"] > 0
        assert d["shopify"]["data_source"] == "demo"
        assert d["demo_mode"] is True

    def test_update_settings_roundtrip(self, client):
        orig = client.get(f"{API}/settings").json()["rules"]
        r = client.put(f"{API}/settings", json={"title_max": 65, "ignored_field": "x"})
        assert r.status_code == 200, r.text
        assert r.json()["title_max"] == 65
        assert "ignored_field" not in r.json()
        assert client.get(f"{API}/settings").json()["rules"]["title_max"] == 65
        client.put(f"{API}/settings", json={"title_max": orig["title_max"]})

    def test_shopify_test_connection(self, client):
        d = client.get(f"{API}/settings/shopify/test").json()
        assert d["connected"] is False
        assert d["status"] == "not_connected"

    def test_audit_pagination(self, client):
        d = client.get(f"{API}/audit?page=1&page_size=5").json()
        assert d["page_size"] == 5 and len(d["items"]) <= 5
        assert d["total"] >= len(d["items"])

    def test_audit_filter_by_type(self, client):
        d = client.get(f"{API}/audit?resource_type=product&page_size=10").json()
        for a in d["items"]:
            assert a["resource_type"] == "product"


class TestAiOptional:
    def test_ai_suggest_invalid_field(self, client):
        pid = client.get(f"{API}/products?page_size=1").json()["items"][0]["id"]
        r = client.post(f"{API}/products/{pid}/ai-suggest", json={"field": "price"})
        assert r.status_code == 400, r.text

    def test_ai_suggest_optional(self, client):
        pid = client.get(f"{API}/products?page_size=1").json()["items"][0]["id"]
        r = client.post(f"{API}/products/{pid}/ai-suggest", json={"field": "seo_title"}, timeout=120)
        if r.status_code == 503:
            pytest.skip(f"AI provider unavailable: {r.text[:200]}")
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["suggestion"], str) and r.json()["suggestion"]
