"""Centralised Shopify Admin GraphQL service layer with SEO-only write allowlist.

The rest of the application must NEVER make Shopify calls directly. All writes go
through here and are validated against a strict allowlist. Non-SEO fields are denied.
"""
import os
import asyncio
import logging

logger = logging.getLogger("shopify")

# --- SEO-only write allowlist (non-negotiable security boundary) ---
ALLOWED_PRODUCT_FIELDS = {"seo_title", "meta_description"}
ALLOWED_COLLECTION_FIELDS = {"seo_title", "meta_description"}
ALLOWED_IMAGE_FIELDS = {"alt"}

NON_SEO_DENIED = "NON_SEO_FIELD_WRITE_DENIED"


class NonSeoFieldWriteDenied(Exception):
    def __init__(self, fields):
        self.fields = fields
        super().__init__(f"{NON_SEO_DENIED}: {', '.join(fields)}")


def assert_seo_only(payload: dict, allowed: set):
    """Raise if the payload contains any field outside the allowlist."""
    forbidden = [k for k in (payload or {}).keys() if k not in allowed]
    if forbidden:
        raise NonSeoFieldWriteDenied(forbidden)


class ShopifyClient:
    MAX_RETRIES = 5

    def __init__(self):
        self.domain = os.environ.get("SHOPIFY_STORE_DOMAIN", "").strip()
        self.token = os.environ.get("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
        self.api_version = os.environ.get("SHOPIFY_API_VERSION", "2025-01").strip()

    @property
    def is_connected(self) -> bool:
        return bool(self.domain and self.token)

    @property
    def data_source(self) -> str:
        return "shopify" if self.is_connected else "demo"

    def endpoint(self) -> str:
        return f"https://{self.domain}/admin/api/{self.api_version}/graphql.json"

    async def test_connection(self) -> dict:
        if not self.is_connected:
            return {"connected": False, "status": "not_connected",
                    "message": "Shopify is not connected. Add store domain and access token in Settings."}
        try:
            data = await self._graphql("{ shop { name myshopifyDomain } }", {})
            shop = data.get("data", {}).get("shop", {})
            return {"connected": True, "status": "connected", "shop": shop}
        except Exception as e:  # noqa
            return {"connected": False, "status": "error", "message": str(e)}

    async def _graphql(self, query: str, variables: dict) -> dict:
        """Execute a GraphQL request with exponential backoff on rate limits."""
        import requests
        delay = 1.0
        for attempt in range(self.MAX_RETRIES):
            resp = await asyncio.to_thread(
                requests.post,
                self.endpoint(),
                json={"query": query, "variables": variables},
                headers={
                    "X-Shopify-Access-Token": self.token,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code == 429:
                logger.warning("Shopify rate limit hit, backing off %.1fs", delay)
                await asyncio.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            body = resp.json()
            if body.get("errors"):
                if any("throttled" in str(e).lower() for e in body["errors"]):
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(f"Shopify GraphQL error: {body['errors']}")
            return body
        raise RuntimeError("Shopify rate limit retries exhausted")

    async def publish_product_seo(self, shopify_id: str, seo_title: str, meta_description: str) -> dict:
        """Publish ONLY seo.title and seo.description for a product."""
        assert_seo_only({"seo_title": seo_title, "meta_description": meta_description}, ALLOWED_PRODUCT_FIELDS)
        if not self.is_connected:
            # DEMO mode: no external write; caller persists locally.
            return {"ok": True, "demo": True, "verified": {"title": seo_title, "description": meta_description}}
        mutation = """
        mutation productUpdate($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id seo { title description } }
            userErrors { field message }
          }
        }"""
        variables = {"input": {"id": shopify_id, "seo": {"title": seo_title, "description": meta_description}}}
        data = await self._graphql(mutation, variables)
        result = data["data"]["productUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"Shopify mutation rejected: {result['userErrors']}")
        seo = result["product"]["seo"]
        return {"ok": True, "demo": False, "verified": {"title": seo.get("title"), "description": seo.get("description")}}

    async def publish_collection_seo(self, shopify_id: str, seo_title: str, meta_description: str) -> dict:
        assert_seo_only({"seo_title": seo_title, "meta_description": meta_description}, ALLOWED_COLLECTION_FIELDS)
        if not self.is_connected:
            return {"ok": True, "demo": True, "verified": {"title": seo_title, "description": meta_description}}
        mutation = """
        mutation collectionUpdate($input: CollectionInput!) {
          collectionUpdate(input: $input) {
            collection { id seo { title description } }
            userErrors { field message }
          }
        }"""
        variables = {"input": {"id": shopify_id, "seo": {"title": seo_title, "description": meta_description}}}
        data = await self._graphql(mutation, variables)
        result = data["data"]["collectionUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"Shopify mutation rejected: {result['userErrors']}")
        seo = result["collection"]["seo"]
        return {"ok": True, "demo": False, "verified": {"title": seo.get("title"), "description": seo.get("description")}}


shopify_client = ShopifyClient()
