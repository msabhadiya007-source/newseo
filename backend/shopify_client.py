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
        # effective config cache (populated by reload(); safe DEMO defaults until then)
        self._domain = ""
        self._token = ""
        self._api_version = "2025-01"
        self._mode = "demo"
        self._mock = True

    async def reload(self):
        """Resolve effective config. Priority: ENV override -> UI-stored config/secret -> default.
        Called at startup and after any Shopify config/secret change so sync properties
        always reflect current settings without awaiting Mongo."""
        import app_config
        import secrets_store
        cfg = app_config.get().get("shopify", {})
        env = os.environ.get

        m = env("APP_DATA_MODE")
        self._mode = (m if m else cfg.get("mode") or "demo").strip().lower()

        mock_env = env("SHOPIFY_MOCK_MODE")
        if mock_env not in (None, ""):
            self._mock = mock_env.strip().lower() == "true"
        else:
            self._mock = bool(cfg.get("mock_mode", True))

        self._domain = (env("SHOPIFY_STORE_DOMAIN") or cfg.get("domain") or "").strip()
        self._api_version = (env("SHOPIFY_API_VERSION") or cfg.get("api_version") or "2025-01").strip()
        self._token = (await secrets_store.get_secret("shopify_token")) or ""
        return self

    # ---- effective config (backward-compatible attribute access) ----
    @property
    def domain(self) -> str:
        return self._domain

    @property
    def token(self) -> str:
        return self._token

    @property
    def api_version(self) -> str:
        return self._api_version

    # ---- mode / connectivity ----
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mock_mode(self) -> bool:
        return self._mock

    @property
    def data_source(self) -> str:
        return "live" if self._mode == "live" else "demo"

    @property
    def use_real(self) -> bool:
        return (not self._mock) and bool(self._domain and self._token)

    @property
    def is_connected(self) -> bool:
        if self._mode != "live":
            return False
        return self._mock or bool(self._domain and self._token)

    @property
    def config_error(self):
        """LIVE mode with missing real credentials must NOT silently fall back to demo."""
        if self._mode == "live" and not self._mock and not (self._domain and self._token):
            return ("Data mode is LIVE but Shopify is not authenticated. Open the app inside "
                    "Shopify Admin and authenticate (Token Exchange) from Settings -> Shopify "
                    "Connection. The app will not fall back to DEMO automatically.")
        return None

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

    # ---- verify the stored (token-exchange) credential directly ----
    async def verify_stored_connection(self) -> dict:
        """Test the currently stored Admin token + domain against the real Admin
        GraphQL API. Independent of APP_DATA_MODE / mock_mode: it validates the
        credential itself (used by the 'Test Shopify Connection' action after the
        embedded token-exchange flow). Never returns the token."""
        if not (self.domain and self.token):
            return {"connected": False, "status": "not_authenticated",
                    "message": "No Shopify Admin token is stored yet. Authenticate from the embedded app first."}
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
                return {"connected": False, "status": "authentication_failed",
                        "message": "Stored Shopify token was rejected (401). Please re-authenticate."}
            if "not found" in msg or "404" in msg:
                return {"connected": False, "status": "api_error",
                        "message": "Shopify API/version error or store not found."}
            return {"connected": False, "status": "unavailable", "message": f"Shopify unavailable: {e}"}


shopify_client = ShopifyClient()
