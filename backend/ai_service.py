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
    """field: 'seo_title' | 'meta_description'. Returns generated text."""
    if not ai_configured():
        raise RuntimeError("AI provider unavailable")

    from emergentintegrations.llm.chat import LlmChat, UserMessage

    provider = os.environ.get("AI_PROVIDER", "openai")
    model = os.environ.get("AI_MODEL", "gpt-5.4")

    if field == "seo_title":
        target = f"an SEO title between {rules.get('title_min', 50)} and {rules.get('title_max', 60)} characters"
        instruction = (
            f"Write {target} for this ecommerce product. Include the brand naturally. "
            "Use natural search language, avoid keyword stuffing. Return ONLY the title text, no quotes."
        )
    else:
        target = f"a meta description between {rules.get('meta_min', 140)} and {rules.get('meta_max', 160)} characters"
        instruction = (
            f"Write {target} for this ecommerce product. Describe it accurately with meaningful "
            "purchase context and a natural call to action. Return ONLY the description text, no quotes."
        )

    system = (
        "You are an expert ecommerce SEO copywriter for the Australian market. "
        + HALLUCINATION_GUARD
    )
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"seo-{product.get('id', 'x')}-{field}",
        system_message=system,
    ).with_model(provider, model)

    prompt = f"{_build_context(product, rules)}\nTask: {instruction}"
    text = await chat.send_message(UserMessage(text=prompt))
    return (text or "").strip().strip('"').strip()
