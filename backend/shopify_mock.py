"""In-memory mock Shopify store used when SHOPIFY_MOCK_MODE is enabled.

Returns Admin GraphQL-shaped payloads (edges/pageInfo/extensions.cost) so the real
ingestion pipeline (pagination, throttle handling, mapping, incremental, publish
verification) can be exercised end-to-end WITHOUT real Shopify credentials.
Nothing here ever talks to a real store.
"""
import base64
import random
from datetime import datetime, timezone, timedelta

BRAND = "UrbanDotted"
_DEVICES = ["iPhone 17 Pro Max", "iPhone 17", "iPhone 16 Pro", "Samsung Galaxy S25 Ultra",
            "Samsung Galaxy S25", "Google Pixel 10 Pro", "Google Pixel 10", "iPhone 15"]
_CASES = ["Clear Case", "Silicone Case", "Rugged Armor Case", "Magnetic Clear Case",
          "Wallet Case", "Matte Hard Case", "Slim Frosted Case"]
_COLORS = ["Black", "Midnight Blue", "Sage Green", "Lavender", "Charcoal", "Sand", "Rose", "Clear"]
_IMG = ["https://images.unsplash.com/photo-1535157412991-2ef801c1748b?w=400",
        "https://images.unsplash.com/photo-1583291023438-41cef6453b1f?w=400"]

_PRODUCTS = []
_COLLECTIONS = []


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _build():
    if _PRODUCTS:
        return
    rnd = random.Random(42)
    now = datetime.now(timezone.utc)
    combos = [(d, c, col) for d in _DEVICES for c in _CASES for col in _COLORS]
    rnd.shuffle(combos)
    for i in range(180):
        d, c, col = combos[i % len(combos)]
        title = f"{BRAND} {d} {c} - {col}"
        handle = "".join(ch if ch.isalnum() else "-" for ch in f"{d}-{c}-{col}-{i}".lower())
        roll = rnd.random()
        seo_title = seo_desc = None
        alts = ["", "", ""]
        if roll < 0.25:
            pass
        elif roll < 0.45:
            seo_title = f"{d} {c} in {col} | {BRAND}"
            alts = [f"{title} front"]
        elif roll < 0.6:
            seo_title = (f"{d} {c} {col} Premium Protective Phone Cover by {BRAND} Australia Best Quality 2026 Range")
            seo_desc = ("Discover premium protection with precise cutouts, wireless friendly design and durable "
                        "materials plus fast free Australian shipping on every single order placed with us today now.")
        else:
            seo_title = f"{d} {c} in {col} | {BRAND} AU Store"[:60]
            seo_desc = (f"Shop the {BRAND} {d} {c.lower()} in {col.lower()} with fast free Australian shipping, "
                        "easy returns and reliable everyday protection you can trust. Order online today now.")[:160]
            alts = [f"{title} — photo 1", f"{title} — photo 2"]
        n_img = rnd.choice([1, 2])
        images = []
        for k in range(n_img):
            images.append({"node": {"id": f"gid://shopify/ProductImage/{9000000 + i*10 + k}",
                                    "url": _IMG[k % len(_IMG)],
                                    "altText": (alts[k] if k < len(alts) else "") or None}})
        updated = now - timedelta(days=rnd.randint(0, 400), hours=rnd.randint(0, 23))
        created = updated - timedelta(days=rnd.randint(1, 200))
        _PRODUCTS.append({
            "id": f"gid://shopify/Product/{8100000000 + i}",
            "handle": handle,
            "title": title,
            "descriptionHtml": f"<p>{title}. Durable everyday protection.</p>",
            "productType": rnd.choice(["Phone Case", "Protective Case"]),
            "vendor": BRAND,
            "status": "ACTIVE",
            "tags": [d.split()[0], col, c.split()[0]],
            "createdAt": _iso(created),
            "updatedAt": _iso(updated),
            "seo": {"title": seo_title, "description": seo_desc},
            "images": {"edges": images},
        })
    for i in range(15):
        name = ["iPhone 17 Cases", "iPhone 16 Cases", "Samsung Galaxy Cases", "Google Pixel Cases",
                "Clear Cases", "Rugged Cases", "Wallet Cases", "Magnetic Cases", "Slim Cases",
                "Best Sellers", "New Arrivals", "Sale Cases", "Matte Finish", "Frosted Cases",
                "Premium Range"][i]
        roll = random.Random(i).random()
        seo_title = seo_desc = None
        if roll < 0.5:
            seo_title = f"{name} | {BRAND} Australia"
            seo_desc = (f"Explore the {name.lower()} collection at {BRAND} with fast free Australian shipping "
                        "and reliable protection. Shop the full range online today for quick delivery now.")
        _COLLECTIONS.append({
            "id": f"gid://shopify/Collection/{330000000 + i}",
            "handle": "".join(ch if ch.isalnum() else "-" for ch in name.lower()),
            "title": name,
            "updatedAt": _iso(datetime.now(timezone.utc) - timedelta(days=i)),
            "seo": {"title": seo_title, "description": seo_desc},
            "productsCount": random.Random(i).randint(5, 400),
        })


def _cost(available=985):
    return {"extensions": {"cost": {"requestedQueryCost": 12, "actualQueryCost": 12,
            "throttleStatus": {"maximumAvailable": 1000, "currentlyAvailable": available, "restoreRate": 50}}}}


def _cursor(idx):
    return base64.b64encode(str(idx).encode()).decode()


def _decode(cursor):
    if not cursor:
        return 0
    try:
        return int(base64.b64decode(cursor.encode()).decode())
    except Exception:  # noqa
        return 0


def _filter_updated(items, updated_since):
    if not updated_since:
        return items
    return [it for it in items if it["updatedAt"] > updated_since]


def products_page(cursor, first, updated_since=None):
    _build()
    items = _filter_updated(_PRODUCTS, updated_since)
    start = _decode(cursor)
    page = items[start:start + first]
    has_next = start + first < len(items)
    edges = [{"node": p, "cursor": _cursor(start + i + 1)} for i, p in enumerate(page)]
    end_cursor = _cursor(start + len(page)) if page else cursor
    return {"edges": edges, "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
            "total_available": len(items), **_cost()}


def collections_page(cursor, first, updated_since=None):
    _build()
    items = _filter_updated(_COLLECTIONS, updated_since)
    start = _decode(cursor)
    page = items[start:start + first]
    has_next = start + first < len(items)
    edges = [{"node": c, "cursor": _cursor(start + i + 1)} for i, c in enumerate(page)]
    end_cursor = _cursor(start + len(page)) if page else cursor
    return {"edges": edges, "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
            "total_available": len(items), **_cost()}


def get_product(gid):
    _build()
    for p in _PRODUCTS:
        if p["id"] == gid:
            return p
    return None


def update_product_seo(gid, title, description):
    """Simulate productUpdate mutation on the mock store."""
    _build()
    for p in _PRODUCTS:
        if p["id"] == gid:
            p["seo"] = {"title": title, "description": description}
            p["updatedAt"] = _iso(datetime.now(timezone.utc))
            return p
    # allow verifying against a test product that wasn't in the base set
    p = {"id": gid, "handle": "test-product", "title": "Mock Test Product",
         "descriptionHtml": "<p>Mock</p>", "productType": "Phone Case", "vendor": BRAND,
         "status": "ACTIVE", "tags": [], "createdAt": _iso(datetime.now(timezone.utc)),
         "updatedAt": _iso(datetime.now(timezone.utc)),
         "seo": {"title": title, "description": description}, "images": {"edges": []}}
    _PRODUCTS.append(p)
    return p


def shop_info():
    return {"name": "UrbanDotted (Mock)", "myshopifyDomain": "urbandotted-mock.myshopify.com"}


def granted_scopes():
    return ["read_products", "write_products", "read_content", "write_content"]
