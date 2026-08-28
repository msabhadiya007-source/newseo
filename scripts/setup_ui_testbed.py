"""Set up a test bed for the Remove Demo Data UI test:
- ensure a viewer (non-admin) account exists
- insert LIVE-tagged marker records (product/collection/draft/publish job+item/audit/csv job)
  so the destructive UI cleanup can be proven to leave LIVE data untouched.
Idempotent-ish: LIVE markers use a fixed tag so we can find/verify/clean them.
"""
import os
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]}
VIEWER = {"email": "viewer@urbandotted.com", "password": "Viewer@12345", "name": "QA Viewer", "role": "viewer"}
TAG = "LIVEKEEP-UITEST"


def main():
    tok = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    # viewer account (ignore 'already exists')
    r = requests.post(f"{API}/auth/register", headers=h, json=VIEWER, timeout=30)
    print("viewer register:", r.status_code, r.text[:120])

    # LIVE markers (clean any prior run first)
    db.products.delete_many({"title": TAG})
    db.collections_seo.delete_many({"title": TAG})
    db.audit_log.delete_many({"id": f"AUD-{TAG}"})
    db.publish_jobs.delete_many({"id": f"PUB-{TAG}"})
    db.publish_items.delete_many({"id": f"PITM-{TAG}"})
    db.csv_jobs.delete_many({"id": f"CSVX-{TAG}"})

    pid, cid = f"lp-{TAG}", f"lc-{TAG}"
    db.products.insert_one({"id": pid, "shopify_product_id": f"gid://shopify/Product/{pid}",
                            "data_source": "live", "title": TAG, "handle": TAG.lower(),
                            "current_seo_title": "Live SEO", "current_seo_description": "Live meta",
                            "has_draft": True, "draft_seo_title": "Live draft", "issue_codes": [],
                            "status_bucket": "good", "seo_score": 80, "publication_status": "draft"})
    db.collections_seo.insert_one({"id": cid, "shopify_collection_id": f"gid://shopify/Collection/{cid}",
                                   "data_source": "live", "title": TAG, "handle": TAG.lower(),
                                   "has_draft": True, "issue_codes": [], "status_bucket": "good", "seo_score": 80})
    db.audit_log.insert_one({"id": f"AUD-{TAG}", "resource_id": pid, "resource_type": "product",
                             "source": "Manual", "timestamp": "2026-01-01T00:00:00+00:00",
                             "changes": [], "reverted": False})
    db.publish_jobs.insert_one({"id": f"PUB-{TAG}", "type": "bulk_publish", "source": "live",
                                "status": "completed", "counts": {"total": 1}})
    db.publish_items.insert_one({"id": f"PITM-{TAG}", "job_id": f"PUB-{TAG}", "resource_id": pid,
                                 "resource_type": "product", "status": "verified"})
    db.csv_jobs.insert_one({"id": f"CSVX-{TAG}", "kind": "export", "data_source": "live", "status": "completed"})

    print("LIVE markers seeded. live_products=", db.products.count_documents({"data_source": "live"}))
    print("demo_products=", db.products.count_documents({"data_source": "demo"}))


if __name__ == "__main__":
    main()
