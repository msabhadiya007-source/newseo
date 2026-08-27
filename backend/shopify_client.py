"""Centralised Shopify Admin GraphQL service layer with SEO-only write allowlist.

All Shopify access is centralised here: auth, GraphQL, API version, retries,
rate-limit/cost handling, error parsing and the SEO-only mutation allowlist.

Modes (strictly env-controlled via APP_DATA_MODE = demo | live):
  - demo:  application works on seeded demo data; no Shopify access.
  - live:  application works on real Shopify data.
When SHOPIFY_MOCK_MODE is true, the live path uses an in-memory mock store so the
whole pipeline is verifiable without real credentials. Set it false + provide real
SHOPIFY_STORE_DOMAIN/ACCESS_TOKEN to hit the real Admin API.
"""
import os
import asyncio
import logging

import shopify_mock

logger = logging.getLogger("shopify")

# --- SEO-only write allowlist (non-negotiable security boundary) ---
ALLOWED_PRODUCT_FIELDS = {"seo_title", "meta_description"}
ALLOWED_COLLECTION_FIELDS = {"seo_title", "meta_description"}
ALLOWED_IMAGE_FIELDS = {"alt"}
NON_SEO_DENIED = "NON_SEO_FIELD_WRITE_DENIED"
REQUIRED_SCOPES = ["read_products", "write_products", "read_content"]


class NonSeoFieldWriteDenied(Exception):
    def __init__(self, fields):
        self.fields = fields
        super().__init__(f"{NON_SEO_DENIED}: {', '.join(fields)}")


def assert_seo_only(payload: dict, allowed: set):
    forbidden = [k for k in (payload or {}).keys() if k not in allowed]
    if forbidden:
        raise NonSeoFieldWriteDenied(forbidden)


PRODUCTS_QUERY = """
query Products($first: Int!, $after: String, $query: String) {
  products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
    edges { cursor node {
      id handle title descriptionHtml productType vendor status tags createdAt updatedAt
      seo { title description }
      images(first: 20) { edges { node { id url altText } } }
    } }
    pageInfo { hasNextPage endCursor }
  }
}"""

COLLECTIONS_QUERY = """
query Collections($first: Int!, $after: String, $query: String) {
  collections(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
    edges { cursor node { id handle title updatedAt productsCount seo { title description } } }
    pageInfo { hasNextPage endCursor }
  }
}"""

PRODUCT_SEO_QUERY = """
query($id: ID!) { product(id: $id) { id handle seo { title description } } }"""

PRODUCT_UPDATE = """
mutation productUpdate($input: ProductInput!) {
  productUpdate(input: $input) { product { id seo { title description } } userErrors { field message } }
}"""

COLLECTION_UPDATE = """
mutation collectionUpdate($input: CollectionInput!) {
  collectionUpdate(input: $input) { collection { id seo { title description } } userErrors { field message } }
}"""

SHOP_QUERY = """
{ shop { name myshopifyDomain }
  currentAppInstallation { accessScopes { handle } } }"""


class ShopifyClient:
    MAX_RETRIES = 5

    def __init__(self):
        self.domain = os.environ.get("SHOPIFY_STORE_DOMAIN", "").strip()
        self.token = os.environ.get("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
        self.api_version = os.environ.get("SHOPIFY_API_VERSION", "").strip() or "2025-01"

    # ---- mode / connectivity ----
    @property
    def mode(self) -> str:
        return os.environ.get("APP_DATA_MODE", "demo").strip().lower()

    @property
    def mock_mode(self) -> bool:
        return os.environ.get("SHOPIFY_MOCK_MODE", "true").strip().lower() == "true"

    @property
    def data_source(self) -> str:
        return "live" if self.mode == "live" else "demo"

    @property
    def use_real(self) -> bool:
        return (not self.mock_mode) and bool(self.domain and self.token)

    @property
    def is_connected(self) -> bool:
        if self.mode != "live":
            return False
        return self.mock_mode or bool(self.domain and self.token)

    def endpoint(self) -> str:
        return f"https://{self.domain}/admin/api/{self.api_version}/graphql.json"

    # ---- transport ----
    async def _http_graphql(self, query: str, variables: dict) -> dict:
        import requests
        delay = 1.0
        for _ in range(self.MAX_RETRIES):
            resp = await asyncio.to_thread(
                requests.post, self.endpoint(),
                json={"query": query, "variables": variables},
                headers={"X-Shopify-Access-Token": self.token, "Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 429:
                await asyncio.sleep(delay); delay = min(delay * 2, 30); continue
            resp.raise_for_status()
            body = resp.json()
            if body.get("errors"):
                if any("throttled" in str(e).lower() for e in body["errors"]):
                    await asyncio.sleep(delay); delay = min(delay * 2, 30); continue
                raise RuntimeError(f"Shopify GraphQL error: {body['errors']}")
            # proactive cost-based throttle
            try:
                ts = body["extensions"]["cost"]["throttleStatus"]
                avail, rate = ts["currentlyAvailable"], ts["restoreRate"]
                if avail < 200:
                    await asyncio.sleep(min(5.0, (200 - avail) / max(1.0, rate)))
            except Exception:  # noqa
                pass
            return body
        raise RuntimeError("Shopify rate limit retries exhausted")

    # ---- reads ----
    async def fetch_products_page(self, cursor, first, updated_since=None):
        if self.use_real:
            q = f"updated_at:>'{updated_since}'" if updated_since else None
            body = await self._http_graphql(PRODUCTS_QUERY, {"first": first, "after": cursor, "query": q})
            conn = body["data"]["products"]
            nodes = [e["node"] for e in conn["edges"]]
            return nodes, conn["pageInfo"]["hasNextPage"], conn["pageInfo"]["endCursor"]
        if self.mock_mode:
            page = shopify_mock.products_page(cursor, first, updated_since)
            return [e["node"] for e in page["edges"]], page["pageInfo"]["hasNextPage"], page["pageInfo"]["endCursor"]
        raise RuntimeError("Shopify is not configured (no credentials and mock disabled)")

    async def fetch_collections_page(self, cursor, first, updated_since=None):
        if self.use_real:
            q = f"updated_at:>'{updated_since}'" if updated_since else None
            body = await self._http_graphql(COLLECTIONS_QUERY, {"first": first, "after": cursor, "query": q})
            conn = body["data"]["collections"]
            nodes = [e["node"] for e in conn["edges"]]
            return nodes, conn["pageInfo"]["hasNextPage"], conn["pageInfo"]["endCursor"]
        if self.mock_mode:
            page = shopify_mock.collections_page(cursor, first, updated_since)
            return [e["node"] for e in page["edges"]], page["pageInfo"]["hasNextPage"], page["pageInfo"]["endCursor"]
        raise RuntimeError("Shopify is not configured")

    async def get_product_seo(self, gid):
        if self.use_real:
            body = await self._http_graphql(PRODUCT_SEO_QUERY, {"id": gid})
            p = body["data"]["product"]
            return p["seo"] if p else None
        if self.mock_mode:
            p = shopify_mock.get_product(gid)
            return p["seo"] if p else None
        return None

    # ---- writes (SEO only) ----
    async def publish_product_seo(self, shopify_id, seo_title, meta_description):
        assert_seo_only({"seo_title": seo_title, "meta_description": meta_description}, ALLOWED_PRODUCT_FIELDS)
        if self.use_real:
            data = await self._http_graphql(PRODUCT_UPDATE, {"input": {"id": shopify_id,
                    "seo": {"title": seo_title, "description": meta_description}}})
            r = data["data"]["productUpdate"]
            if r["userErrors"]:
                raise RuntimeError(f"Shopify mutation rejected: {r['userErrors']}")
            seo = r["product"]["seo"]
            return {"ok": True, "demo": False, "verified": {"title": seo.get("title"), "description": seo.get("description")}}
        if self.mock_mode and shopify_mock.get_product(shopify_id) is not None:
            p = shopify_mock.update_product_seo(shopify_id, seo_title, meta_description)
            return {"ok": True, "demo": False, "mock": True, "verified": {"title": p["seo"]["title"], "description": p["seo"]["description"]}}
        # demo data source (resource not in Shopify): local-only simulation
        return {"ok": True, "demo": True, "verified": {"title": seo_title, "description": meta_description}}

    async def publish_collection_seo(self, shopify_id, seo_title, meta_description):
        assert_seo_only({"seo_title": seo_title, "meta_description": meta_description}, ALLOWED_COLLECTION_FIELDS)
        if self.use_real:
            data = await self._http_graphql(COLLECTION_UPDATE, {"input": {"id": shopify_id,
                    "seo": {"title": seo_title, "description": meta_description}}})
            r = data["data"]["collectionUpdate"]
            if r["userErrors"]:
                raise RuntimeError(f"Shopify mutation rejected: {r['userErrors']}")
            seo = r["collection"]["seo"]
            return {"ok": True, "demo": False, "verified": {"title": seo.get("title"), "description": seo.get("description")}}
        return {"ok": True, "demo": self.mode != "live", "mock": self.mock_mode and self.mode == "live",
                "verified": {"title": seo_title, "description": meta_description}}

    # ---- connection test ----
    async def test_connection(self) -> dict:
        if self.mode != "live":
            return {"connected": False, "status": "demo_mode",
                    "message": "Application is in DEMO mode. Set APP_DATA_MODE=live to connect Shopify."}
        if self.mock_mode:
            info = shopify_mock.shop_info()
            scopes = shopify_mock.granted_scopes()
            missing = [s for s in REQUIRED_SCOPES if s not in scopes]
            return {"connected": True, "status": "connected", "mock": True, "shop": info,
                    "api_version": self.api_version, "granted_scopes": scopes,
                    "missing_scopes": missing,
                    "message": "Connected to MOCK Shopify store (no real credentials)."}
        if not (self.domain and self.token):
            return {"connected": False, "status": "authentication_failed",
                    "message": "Shopify credentials are missing. Set SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_ACCESS_TOKEN."}
        try:
            body = await self._http_graphql(SHOP_QUERY, {})
            data = body.get("data", {})
            shop = data.get("shop", {})
            scopes = [s["handle"] for s in (data.get("currentAppInstallation", {}) or {}).get("accessScopes", [])]
            missing = [s for s in REQUIRED_SCOPES if s not in scopes]
            if missing:
                return {"connected": True, "status": "missing_permission", "shop": shop,
                        "api_version": self.api_version, "granted_scopes": scopes, "missing_scopes": missing,
                        "message": f"Connected but missing required scopes: {', '.join(missing)}"}
            return {"connected": True, "status": "connected", "shop": shop,
                    "api_version": self.api_version, "granted_scopes": scopes, "missing_scopes": []}
        except Exception as e:  # noqa
            msg = str(e).lower()
            if "401" in msg or "unauthorized" in msg or "invalid" in msg:
                return {"connected": False, "status": "authentication_failed", "message": "Shopify authentication failed (invalid token)."}
            if "not found" in msg or "404" in msg:
                return {"connected": False, "status": "api_error", "message": "Shopify API/version error or store not found."}
            return {"connected": False, "status": "unavailable", "message": f"Shopify unavailable: {e}"}


shopify_client = ShopifyClient()
