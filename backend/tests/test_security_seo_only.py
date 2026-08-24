"""CRITICAL SECURITY: SEO-only write allowlist must deny all non-SEO commerce fields."""
import pytest
from conftest import API

FORBIDDEN_PAYLOADS = [
    {"price": "1.00"},
    {"inventory": 999},
    {"sku": "HACK-1"},
    {"product_title": "Hacked Title"},
    {"title": "Hacked Title"},
    {"barcode": "1234567890"},
    {"vendor": "EvilCorp"},
    {"status": "ARCHIVED"},
    {"variants": [{"price": "0.01"}]},
    {"seo_title": "Valid Title", "price": "1.00"},  # mixed: must still deny
]

COMMERCE_SNAPSHOT_FIELDS = ["price", "inventory", "sku", "barcode", "vendor", "title", "status"]


@pytest.fixture(scope="module")
def product(request):
    import requests
    from pathlib import Path
    import re
    c = Path("/app/memory/test_credentials.md").read_text()
    email = re.search(r'(?im)^\s*[-*]\s*Email\s*:\s*(\S+)', c).group(1)
    pwd = re.search(r'(?im)^\s*[-*]\s*Password\s*:\s*(\S+)', c).group(1)
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}).json()["token"]
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
    p = s.get(f"{API}/products?page_size=1").json()["items"][0]
    return {"session": s, "product": p}


class TestProductSeoOnlyGuard:
    @pytest.mark.parametrize("payload", FORBIDDEN_PAYLOADS,
                             ids=[list(p.keys())[-1] + ("_mixed" if len(p) > 1 else "") for p in FORBIDDEN_PAYLOADS])
    def test_draft_denies_non_seo_field(self, product, payload):
        s, pid = product["session"], product["product"]["id"]
        before = s.get(f"{API}/products/{pid}").json()
        r = s.patch(f"{API}/products/{pid}/seo-draft", json=payload)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text, r.text[:300]
        after = s.get(f"{API}/products/{pid}").json()
        # no mutation at all
        for f in COMMERCE_SNAPSHOT_FIELDS:
            assert before.get(f) == after.get(f), f"commerce field {f} mutated!"
        assert before.get("draft_seo_title") == after.get("draft_seo_title")
        assert before.get("current_seo_title") == after.get("current_seo_title")
        assert before.get("has_draft") == after.get("has_draft")

    @pytest.mark.parametrize("payload", FORBIDDEN_PAYLOADS,
                             ids=[list(p.keys())[-1] + ("_mixed" if len(p) > 1 else "") for p in FORBIDDEN_PAYLOADS])
    def test_publish_denies_non_seo_field(self, product, payload):
        s, pid = product["session"], product["product"]["id"]
        before = s.get(f"{API}/products/{pid}").json()
        r = s.post(f"{API}/products/{pid}/publish-seo", json=payload)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text, r.text[:300]
        after = s.get(f"{API}/products/{pid}").json()
        for f in COMMERCE_SNAPSHOT_FIELDS:
            assert before.get(f) == after.get(f), f"commerce field {f} mutated!"
        assert before.get("current_seo_title") == after.get("current_seo_title")
        assert before.get("current_seo_description") == after.get("current_seo_description")
        assert after.get("publication_status") == before.get("publication_status"), \
            "publication_status changed on a denied write"


class TestCollectionSeoOnlyGuard:
    @pytest.fixture()
    def collection(self, client):
        return client.get(f"{API}/collections").json()["items"][0]

    @pytest.mark.parametrize("payload", FORBIDDEN_PAYLOADS,
                             ids=[list(p.keys())[-1] + ("_mixed" if len(p) > 1 else "") for p in FORBIDDEN_PAYLOADS])
    def test_collection_draft_denies(self, client, collection, payload):
        r = client.patch(f"{API}/collections/{collection['id']}/seo-draft", json=payload)
        assert r.status_code == 403, f"{r.status_code}: {r.text[:300]}"
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text

    @pytest.mark.parametrize("payload", FORBIDDEN_PAYLOADS,
                             ids=[list(p.keys())[-1] + ("_mixed" if len(p) > 1 else "") for p in FORBIDDEN_PAYLOADS])
    def test_collection_publish_denies(self, client, collection, payload):
        before = next(c for c in client.get(f"{API}/collections").json()["items"]
                      if c["id"] == collection["id"])
        r = client.post(f"{API}/collections/{collection['id']}/publish-seo", json=payload)
        assert r.status_code == 403, f"{r.status_code}: {r.text[:300]}"
        assert "NON_SEO_FIELD_WRITE_DENIED" in r.text
        after = next(c for c in client.get(f"{API}/collections").json()["items"]
                     if c["id"] == collection["id"])
        assert before.get("current_seo_title") == after.get("current_seo_title")
        assert before.get("title") == after.get("title")


class TestAllowlistUnit:
    def test_assert_seo_only(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from shopify_client import (assert_seo_only, NonSeoFieldWriteDenied,
                                   ALLOWED_PRODUCT_FIELDS, ALLOWED_IMAGE_FIELDS)
        assert_seo_only({"seo_title": "a", "meta_description": "b"}, ALLOWED_PRODUCT_FIELDS)
        assert_seo_only({"alt": "a"}, ALLOWED_IMAGE_FIELDS)
        for bad in ["price", "inventory", "sku", "barcode", "vendor", "title", "variants", "status"]:
            with pytest.raises(NonSeoFieldWriteDenied):
                assert_seo_only({bad: "x"}, ALLOWED_PRODUCT_FIELDS)

    def test_shopify_mutation_only_touches_seo(self):
        """Static guard: publish mutations must not reference commerce fields."""
        src = open("/app/backend/shopify_client.py").read()
        for banned in ["price", "inventoryQuantity", "sku", "barcode", "vendor", "variants"]:
            assert f'"{banned}"' not in src.split("mutation")[1] if "mutation" in src else True
