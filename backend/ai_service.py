"""Optional AI-assisted SEO generation. Never publishes; produces drafts only.

Falls back gracefully when AI is unavailable so the app never depends on AI.
"""
import os
import logging

logger = logging.getLogger("ai")


def ai_configured() -> bool:
    return bool(os.environ.get("EMERGENT_LLM_KEY"))


HALLUCINATION_GUARD = (
    "Strict rules: Only use facts present in the provided product context. "
    "NEVER invent product properties such as waterproof, military-grade, MagSafe, "
    "drop-tested, leather, wireless charging, materials, certifications or protection "
    "claims unless they explicitly appear in the context. If uncertain, omit the claim."
)


def _build_context(product: dict, rules: dict) -> str:
    return (
        f"Brand: {rules.get('brand', 'UrbanDotted')}\n"
        f"Target market: {rules.get('country', 'Australia')}\n"
        f"Product title: {product.get('title', '')}\n"
        f"Product type: {product.get('product_type', '')}\n"
        f"Vendor: {product.get('vendor', '')}\n"
        f"Tags: {', '.join(product.get('tags', []) or [])}\n"
        f"Handle: {product.get('handle', '')}\n"
        f"Existing SEO title: {product.get('current_seo_title', '') or '(none)'}\n"
        f"Existing meta description: {product.get('current_seo_description', '') or '(none)'}\n"
    )


async def generate_seo(product: dict, rules: dict, field: str) -> str:
    """field: 'seo_title' | 'meta_description'. Returns generated text.

    Routes through the settings-based multi-provider layer (ai_providers) so the saved
    default provider, its encrypted API key and saved model are ACTUALLY used. Previously
    this used only the EMERGENT_LLM_KEY env var, so a saved Gemini default was never
    resolved -> "AI provider unavailable". Draft-only: this never publishes to Shopify.
    """
    import ai_providers  # local import avoids any import cycle at module load

    # Resolves the saved default provider, checks AI-enabled, loads the encrypted key
    # and saved model (raises ProviderError with a clear code if disabled/not configured).
    prov = await ai_providers.get_provider()

    tmin, tmax = rules.get("title_min", 50), rules.get("title_max", 60)
    mmin, mmax = rules.get("meta_min", 140), rules.get("meta_max", 160)
    system = (
        "You are an expert ecommerce SEO copywriter for the Australian market. "
        + HALLUCINATION_GUARD
        + f" Produce an SEO title ({tmin}-{tmax} characters) and a meta description "
        f"({mmin}-{mmax} characters). Include the brand naturally; use natural search "
        'language and avoid keyword stuffing. Return ONLY compact JSON of the exact form '
        '{"seo_title": "...", "meta_description": "..."}.'
    )
    context = {
        "brand": rules.get("brand", "UrbanDotted"),
        "country": rules.get("country", "Australia"),
        "product_name": product.get("title", ""),
        "product_title": product.get("title", ""),
        "product_type": product.get("product_type", ""),
        "vendor": product.get("vendor", ""),
        "tags": product.get("tags", []) or [],
        "handle": product.get("handle", ""),
        "verified_features": [],
        "current_seo_title": product.get("current_seo_title", "") or "",
        "current_seo_description": product.get("current_seo_description", "") or "",
    }

    res = await prov.generate_product_seo(system, context)
    data = (res or {}).get("result", {}) or {}
    value = data.get("seo_title") if field == "seo_title" else data.get("meta_description")
    if not value:
        raise RuntimeError("AI returned no suggestion")
    return str(value).strip().strip('"').strip()
