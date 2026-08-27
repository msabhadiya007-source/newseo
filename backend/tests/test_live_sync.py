"""Phase 3.5 acceptance tests for the LIVE Shopify Admin GraphQL pipeline.

These run against the live backend when it is configured in LIVE mode with the
in-memory mock transport (APP_DATA_MODE=live + SHOPIFY_MOCK_MODE=true), which
exercises the *real* ingestion/publish code paths (pagination, incremental,
non-destructive merge, deleted handling, cost/throttle handling, SEO-only
publish + verification + rollback) without needing real Shopify credentials.

The whole class is skipped automatically when the server is in DEMO mode, so it
is safe to leave in the default suite.
"""
import time

import pytest
from conftest import API


def _server_mode(client):
    s = client.get(f"{API}/settings").json().get("shopify", {})
    return s.get("mode"), s.get("mock_mode")


def _wait_job(client, job_id, timeout=180):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"{API}/jobs/{job_id}").json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(2)
    return last


@pytest.fixture(scope="class")
def live_ctx(admin_token):
    import requests
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {admin_token}"})
    mode, mock = _server_mode(s)
    if mode != "live":
        pytest.skip("Backend not in LIVE mode; skipping live Shopify pipeline tests")
    return {"mock": mock}


@pytest.mark.usefixtures("live_ctx")
class TestLiveShopifyPipeline:
    # ---- 16. connection test ----
    def test_01_connection_connected(self, client):
        d = client.get(f"{API}/settings/shopify/test").json()
        assert d["connected"] is True, d
        assert d["status"] == "connected", d
        assert "read_products" in d.get("granted_scopes", [])
        assert d.get("missing_scopes") == [], d
        assert d.get("api_version")

    # ---- 5/6. background full sync + pagination ----
    def test_02_full_sync_completes_with_pagination(self, client):
        r = client.post(f"{API}/shopify/live-sync?full_resync=true")
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        job = _wait_job(client, job_id)
        assert job and job["status"] == "completed", job
        # pagination actually happened (180 mock products / 100 page size => >=2 pages)
        assert job["pages"] >= 2, job
        assert job["new"] + job["updated"] + job["unchanged"] > 0
        assert job["failed"] == 0, job
        assert job["progress"] == 100

    def test_03_live_products_ingested(self, client):
        d = client.get(f"{API}/products?page_size=5").json()
        assert d["total"] > 0
        for it in d["items"]:
            assert it.get("data_source") == "live", it.get("data_source")
        # SEO-relevant read fields present
        sample = d["items"][0]
        for f in ("handle", "title", "shopify_product_id", "status_bucket"):
            assert f in sample, f

    def test_04_collections_ingested(self, client):
        d = client.get(f"{API}/collections?page_size=5").json()
        assert d["total"] > 0, d

    # ---- 2. demo/live never mixed ----
    def test_05_demo_and_live_never_mixed(self, client):
        d = client.get(f"{API}/products?page_size=50").json()
        assert all(it.get("data_source") == "live" for it in d["items"]), \
            "demo records leaked into live listing"

    # ---- 8. incremental sync ----
    def test_06_incremental_sync_reprocesses_nothing_new(self, client):
        r = client.post(f"{API}/shopify/live-sync?full_resync=false")
        job = _wait_job(client, r.json()["job_id"])
        assert job["status"] == "completed", job
        assert job["new"] == 0, f"incremental sync created new records: {job}"

    # ---- 9. non-destructive: local draft survives re-sync ----
    def test_07_local_draft_survives_resync(self, client):
        p = client.get(f"{API}/products?page_size=1").json()["items"][0]
        pid = p["id"]
        draft = {"seo_title": "DRAFT KEEP ME 123", "meta_description": "Draft meta that must survive a full re-sync."}
        r = client.patch(f"{API}/products/{pid}/seo-draft", json=draft)
        assert r.status_code == 200, r.text
        # full re-sync
        job = _wait_job(client, client.post(f"{API}/shopify/live-sync?full_resync=true").json()["job_id"])
        assert job["status"] == "completed", job
        after = client.get(f"{API}/products/{pid}").json()
        assert after.get("has_draft") is True, after
        assert after.get("draft_seo_title") == "DRAFT KEEP ME 123", after

    # ---- 12. existing valid Shopify SEO is not modified by sync ----
    def test_08_existing_seo_unchanged_after_resync(self, client):
        # find a product that already has a current SEO title
        items = client.get(f"{API}/products?page_size=50").json()["items"]
        target = next((it for it in items if (it.get("current_seo_title") or "").strip()), None)
        if not target:
            pytest.skip("no live product with an existing SEO title")
        before_title = target["current_seo_title"]
        before_desc = target.get("current_seo_description")
        job = _wait_job(client, client.post(f"{API}/shopify/live-sync?full_resync=true").json()["job_id"])
        assert job["status"] == "completed", job
        after = client.get(f"{API}/products/{target['id']}").json()
        assert after["current_seo_title"] == before_title, "sync overwrote existing SEO title"
        assert after.get("current_seo_description") == before_desc, "sync overwrote existing SEO desc"

    # ---- 13. real (mock) SEO publish round-trip + verification + audit + reanalysis ----
    def test_09_publish_roundtrip_verified(self, client):
        r = client.post(f"{API}/shopify/verify-publish")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("verified_match") is True, d
        assert d.get("verified_shopify_value"), d
        assert d.get("audit_id"), d
        assert d.get("mock") is True, d
        # audit entry visible
        audit = client.get(f"{API}/audit?page=1&page_size=5").json()
        assert any(a.get("id") == d["audit_id"] for a in audit["items"]), audit

    # ---- 6. resume/recovery: sync_state cursor cleared on completion (not stuck in-progress) ----
    def test_10_sync_state_recovers(self, client):
        st = client.get(f"{API}/sync/status").json()
        state = st.get("sync_state") or {}
        assert state.get("status") == "ok", state
        assert not state.get("in_progress", False), state

    # ---- 14. security regression under LIVE mode ----
    @pytest.mark.parametrize("payload", [
        {"price": "1.00"}, {"inventory": 5}, {"sku": "X"}, {"barcode": "1"},
        {"vendor": "Evil"}, {"title": "Hacked"}, {"product_title": "Hacked"},
        {"status": "ARCHIVED"}, {"variants": [{"price": "0"}]},
        {"seo_title": "ok", "price": "1"},
    ])
    def test_11_forbidden_fields_denied_live(self, client, payload):
        pid = client.get(f"{API}/products?page_size=1").json()["items"][0]["id"]
        r = client.post(f"{API}/products/{pid}/publish-seo", json=payload)
        assert r.status_code == 403, r.text
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text
