"""DEV/DEMO seed data generator. Produces a realistic phone-case catalog.

Never mixes with real Shopify records (records are tagged data_source='demo').
Demo seeding is only triggered explicitly (Sync) and disabled when DEMO_MODE is off.
"""
import os
import uuid
import random

BRAND = "UrbanDotted"

DEVICES = [
    "iPhone 17 Pro Max", "iPhone 17 Pro", "iPhone 17", "iPhone 16 Pro", "iPhone 16",
    "iPhone 15 Pro", "iPhone 15", "Samsung Galaxy S25 Ultra", "Samsung Galaxy S25",
    "Samsung Galaxy S24", "Google Pixel 10 Pro", "Google Pixel 10", "Google Pixel 9",
]
CASE_TYPES = [
    "Clear Case", "Silicone Case", "Frosted Slim Case", "Rugged Armor Case",
    "Magnetic Clear Case", "Shockproof Bumper Case", "Wallet Case", "Matte Hard Case",
    "Soft Touch Case", "Transparent Grip Case",
]
COLORS = ["Black", "Midnight Blue", "Sage Green", "Lavender", "Charcoal",
          "Sand", "Rose", "Clear", "Graphite", "Coral"]
TYPES = ["Phone Case", "Protective Case", "Accessory"]
GOOD_ADJ = ["Premium", "Slim", "Protective", "Durable", "Everyday", "Signature", "Classic", "Matte"]

IMAGE_POOL = [
    "https://images.unsplash.com/photo-1535157412991-2ef801c1748b?crop=entropy&cs=srgb&fm=jpg&q=85&w=400",
    "https://images.unsplash.com/photo-1583291023438-41cef6453b1f?crop=entropy&cs=srgb&fm=jpg&q=85&w=400",
    "https://images.unsplash.com/photo-1593055454503-531d165c2ed8?crop=entropy&cs=srgb&fm=jpg&q=85&w=400",
    "https://images.pexels.com/photos/1670768/pexels-photo-1670768.jpeg?auto=compress&cs=tinysrgb&w=400",
]

COLLECTION_NAMES = [
    "iPhone 17 Cases", "iPhone 16 Cases", "iPhone 15 Cases", "Samsung Galaxy Cases",
    "Google Pixel Cases", "Clear Cases", "Rugged Cases", "Wallet Cases",
    "Magnetic Cases", "Silicone Cases", "Slim Cases", "Best Sellers",
    "New Arrivals", "Sale Cases", "Matte Finish", "Frosted Cases",
]


def _handle(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-").replace("--", "-")


def _build_images(state: str, title: str):
    n = random.choice([1, 1, 2, 3])
    imgs = []
    for i in range(n):
        alt = ""
        if state == "good":
            alt = f"{title} — product photo {i + 1}"
        elif state == "partial" and i == 0:
            alt = f"{BRAND} phone case"
        imgs.append({"id": f"img-{uuid.uuid4().hex[:8]}", "src": random.choice(IMAGE_POOL),
                     "alt": alt, "draft_alt": None})
    return imgs


def generate_products(count: int):
    products = []
    dup_title_pool = f"Phone Case | {BRAND} Australia Free Shipping"
    dup_meta_pool = ("Shop premium phone cases at UrbanDotted Australia. Fast free shipping, "
                     "durable protection and stylish designs for your device today.")
    combos = [(d, c, col) for d in DEVICES for c in CASE_TYPES for col in COLORS]
    random.shuffle(combos)
    i = 0
    while len(products) < count:
        d, c, col = combos[i % len(combos)]
        i += 1
        title = f"{BRAND} {d} {c} - {col}"
        handle = _handle(f"{d}-{c}-{col}-{i}")
        roll = random.random()
        seo_title = None
        seo_desc = None
        alt_state = "missing"
        if roll < 0.18:
            # both missing
            pass
        elif roll < 0.30:
            # missing meta only
            seo_title = f"{d} {c} in {col} | {BRAND}"
        elif roll < 0.40:
            # missing title only
            seo_desc = (f"Protect your {d} with the {BRAND} {c.lower()} in {col.lower()}. "
                        "Slim, durable and shipped fast across Australia. Order yours now.")
        elif roll < 0.55:
            # too long
            seo_title = f"{d} {c} {col} Premium Protective Phone Cover Case by {BRAND} Australia Best Quality 2026"
            seo_desc = (f"Discover the ultimate {d} {c.lower()} in {col.lower()} from {BRAND}. "
                        "Premium protection, precise cutouts, wireless friendly design, durable materials, "
                        "stylish finish and fast free shipping right across Australia for every order placed today.")
            alt_state = "partial"
        elif roll < 0.62:
            # too short (critical candidate)
            seo_title = f"{d} Case"
            seo_desc = "Buy phone case now."
        elif roll < 0.74:
            # duplicates
            seo_title = dup_title_pool
            seo_desc = dup_meta_pool
            alt_state = "partial"
        else:
            # good / fully optimised (unique title 50-60, meta 140-160, full alt)
            adj = GOOD_ADJ[i % len(GOOD_ADJ)]
            seo_title = f"{d} {adj} {c} in {col} | {BRAND}"[:60]
            if len(seo_title) < 50:
                seo_title = f"{d} {adj} {c} in {col} for {BRAND} Store"[:60]
            seo_desc = (f"Shop the {adj.lower()} {BRAND} {d} {c.lower()} in {col.lower()} with fast free "
                        "Australian shipping, easy returns and reliable everyday protection you can trust.")
            if len(seo_desc) < 140:
                seo_desc += " Order online now."
            seo_desc = seo_desc[:160]
            alt_state = "good"

        products.append({
            "id": str(uuid.uuid4()),
            "shopify_product_id": f"gid://shopify/Product/{7000000000 + i}",
            "handle": handle,
            "title": title,
            "product_type": random.choice(TYPES),
            "vendor": BRAND,
            "tags": [d.split()[0], col, c.split()[0]],
            "status": "active",
            "price": round(random.uniform(19.95, 49.95), 2),
            "inventory": random.randint(0, 800),
            "sku": f"UBD-{random.randint(1000, 9999)}",
            "current_seo_title": seo_title,
            "current_seo_description": seo_desc,
            "draft_seo_title": None,
            "draft_seo_description": None,
            "has_draft": False,
            "images": _build_images(alt_state, title),
            "ai_quality": None,
            "seo_score": 0,
            "score_breakdown": {},
            "issue_codes": [],
            "status_bucket": "missing",
            "publication_status": "published",
            "data_source": "demo",
            "shopify_updated_at": None,
            "created_at": None,
        })
    return products


def generate_collections(count: int):
    cols = []
    names = COLLECTION_NAMES[:count] if count <= len(COLLECTION_NAMES) else COLLECTION_NAMES
    for idx, name in enumerate(names):
        roll = random.random()
        seo_title = None
        seo_desc = None
        if roll < 0.4:
            pass
        elif roll < 0.7:
            seo_title = f"{name} | {BRAND} Australia"
            seo_desc = (f"Explore the {name.lower()} collection at {BRAND}. Durable, stylish phone "
                        "protection with fast free shipping across Australia. Shop the range online today.")
        else:
            seo_title = f"{name} Collection {BRAND} Premium Protective Phone Covers Australia Best 2026 Range"
        cols.append({
            "id": str(uuid.uuid4()),
            "shopify_collection_id": f"gid://shopify/Collection/{300000000 + idx}",
            "handle": _handle(name),
            "title": name,
            "current_seo_title": seo_title,
            "current_seo_description": seo_desc,
            "draft_seo_title": None,
            "draft_seo_description": None,
            "has_draft": False,
            "ai_quality": None,
            "seo_score": 0,
            "score_breakdown": {},
            "issue_codes": [],
            "status_bucket": "missing",
            "publication_status": "published",
            "data_source": "demo",
            "images": [],
        })
    return cols


def demo_enabled() -> bool:
    return os.environ.get("DEMO_MODE", "false").lower() == "true"
