"""Proves the Admin-only 'Remove Demo Data' action deletes ONLY data_source=='demo'
records and can NEVER delete any LIVE-tagged record (products, collections, audit,
publish jobs/items, csv jobs, drafts).

DESTRUCTIVE: wipes the seeded demo dataset. Run standalone; re-seed demo afterwards.
"""
import uuid
import requests
from pymongo import MongoClient
from dotenv import dotenv_values
from conftest import API

_env = dotenv_values("/app/backend/.env")
_db = MongoClient(_env["MONGO_URL"])[_env["DB_NAME"]]


def _seed_live_markers():
    tag = f"LIVEKEEP-{uuid.uuid4().hex[:8]}"
    pid, cid = f"lp-{uuid.uuid4().hex}", f"lc-{uuid.uuid4().hex}"
    _db.products.insert_one({"id": pid, "shopify_product_id": f"gid://shopify/Product/{pid}",
                             "data_source": "live", "title": tag, "handle": tag.lower(),
                             "current_seo_title": "Live SEO", "current_seo_description": "Live meta",
                             "has_draft": True, "draft_seo_title": "Live draft", "issue_codes": [],
                             "status_bucket": "good", "seo_score": 80, "publication_status": "draft"})
    _db.collections_seo.insert_one({"id": cid, "shopify_collection_id": f"gid://shopify/Collection/{cid}",
                                    "data_source": "live", "title": tag, "handle": tag.lower(),
                                    "has_draft": True, "issue_codes": [], "status_bucket": "good", "seo_score": 80})
    _db.audit_log.insert_one({"id": f"AUD-{tag}", "resource_id": pid, "resource_type": "product",
                              "source": "Manual", "timestamp": "2026-01-01T00:00:00+00:00",
                              "changes": [], "reverted": False})
    _db.publish_jobs.insert_one({"id": f"PUB-{tag}", "type": "bulk_publish", "source": "live",
                                 "status": "completed", "counts": {"total": 1}})
    _db.publish_items.insert_one({"id": f"PITM-{tag}", "job_id": f"PUB-{tag}", "resource_id": pid,
                                  "resource_type": "product", "status": "verified"})
    _db.csv_jobs.insert_one({"id": f"CSVX-{tag}", "kind": "export", "data_source": "live", "status": "completed"})
    return {"tag": tag, "pid": pid, "cid": cid}


def _seed_demo_probe():
    pid = f"dp-{uuid.uuid4().hex}"
    _db.products.insert_one({"id": pid, "shopify_product_id": f"gid://shopify/Product/{pid}",
                             "data_source": "demo", "title": f"DEMOPROBE-{pid}", "handle": pid,
                             "current_seo_title": "", "has_draft": False, "issue_codes": ["MISSING_SEO_TITLE"],
                             "status_bucket": "missing", "seo_score": 4, "publication_status": "published"})
    return pid


class TestRemoveDemoData:
    def test_preview_counts_exclude_live(self, client):
        live = _seed_live_markers()
        d = client.get(f"{API}/settings/demo-data").json()
        # live-tagged product exists but must NOT be counted as demo
        assert _db.products.find_one({"id": live["pid"]}) is not None
        demo_count = _db.products.count_documents({"data_source": "demo"})
        assert d["counts"]["products"] == demo_count
        # cleanup markers so this non-destructive test leaves no residue if delete test is skipped
        _cleanup_live(live)

    def test_remove_demo_data_preserves_all_live(self, client):
        live = _seed_live_markers()
        demo_probe = _seed_demo_probe()
        live_before = _db.products.count_documents({"data_source": "live"})

        r = client.delete(f"{API}/settings/demo-data")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["deleted"]["products"] >= 1

        # DEMO probe deleted
        assert _db.products.find_one({"id": demo_probe}) is None
        assert _db.products.count_documents({"data_source": "demo"}) == 0
        assert body["demo_data_present"] is False

        # EVERY live-tagged record preserved
        assert _db.products.find_one({"id": live["pid"]}) is not None, "LIVE product deleted!"
        assert _db.collections_seo.find_one({"id": live["cid"]}) is not None, "LIVE collection deleted!"
        assert _db.audit_log.find_one({"id": f"AUD-{live['tag']}"}) is not None, "LIVE audit deleted!"
        assert _db.publish_jobs.find_one({"id": f"PUB-{live['tag']}"}) is not None, "LIVE publish job deleted!"
        assert _db.publish_items.find_one({"id": f"PITM-{live['tag']}"}) is not None, "LIVE publish item deleted!"
        assert _db.csv_jobs.find_one({"id": f"CSVX-{live['tag']}"}) is not None, "LIVE csv job deleted!"
        # live draft preserved
        lp = _db.products.find_one({"id": live["pid"]})
        assert lp.get("has_draft") is True and lp.get("draft_seo_title") == "Live draft"
        assert _db.products.count_documents({"data_source": "live"}) == live_before
        assert body["live_products_preserved"] == live_before

        _cleanup_live(live)

    def test_requires_settings_permission(self, admin_token):
        # viewer cannot remove demo data
        email = f"viewer_{uuid.uuid4().hex[:6]}@test.com"
        requests.post(f"{API}/auth/register",
                      headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                      json={"email": email, "password": "Viewer@123", "name": "V", "role": "viewer"})
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "Viewer@123"}).json()["token"]
        r = requests.delete(f"{API}/settings/demo-data", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403


def _cleanup_live(live):
    tag = live["tag"]
    _db.products.delete_one({"id": live["pid"]})
    _db.collections_seo.delete_one({"id": live["cid"]})
    _db.audit_log.delete_one({"id": f"AUD-{tag}"})
    _db.publish_jobs.delete_one({"id": f"PUB-{tag}"})
    _db.publish_items.delete_one({"id": f"PITM-{tag}"})
    _db.csv_jobs.delete_one({"id": f"CSVX-{tag}"})
