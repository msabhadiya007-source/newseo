"""Analysis orchestration: apply the SEO analyzer across products/collections."""
from db import db
from seo import analyze, DEFAULT_RULES


async def get_rules() -> dict:
    doc = await db.settings.find_one({"id": "seo_rules"})
    if not doc:
        return dict(DEFAULT_RULES)
    return {k: doc.get(k, v) for k, v in DEFAULT_RULES.items()}


def _dup_sets(items):
    """Values appearing more than once (case-insensitive)."""
    titles, metas = {}, {}
    for p in items:
        t = (p.get("current_seo_title") or "").strip().lower()
        m = (p.get("current_seo_description") or "").strip().lower()
        if t:
            titles[t] = titles.get(t, 0) + 1
        if m:
            metas[m] = metas.get(m, 0) + 1
    return ({k for k, v in titles.items() if v > 1},
            {k for k, v in metas.items() if v > 1})


async def reanalyze_all(source: str, progress_cb=None):
    rules = await get_rules()
    products = await db.products.find({"data_source": source}).to_list(None)
    dt, dm = _dup_sets(products)
    total = len(products)
    for idx, p in enumerate(products):
        issues, score, breakdown, bucket = analyze(p, rules, dt, dm)
        await db.products.update_one({"id": p["id"]}, {"$set": {
            "issue_codes": issues, "seo_score": score,
            "score_breakdown": breakdown, "status_bucket": bucket,
        }})
        if progress_cb and idx % 200 == 0:
            await progress_cb(idx, total)
    # Collections
    collections = await db.collections_seo.find({"data_source": source}).to_list(None)
    ct, cm = _dup_sets(collections)
    for c in collections:
        issues, score, breakdown, bucket = analyze(c, rules, ct, cm)
        await db.collections_seo.update_one({"id": c["id"]}, {"$set": {
            "issue_codes": issues, "seo_score": score,
            "score_breakdown": breakdown, "status_bucket": bucket,
        }})
    if progress_cb:
        await progress_cb(total, total)
    return total


async def reanalyze_one_product(product_id: str):
    rules = await get_rules()
    p = await db.products.find_one({"id": product_id})
    if not p:
        return None
    title = (p.get("current_seo_title") or "").strip()
    meta = (p.get("current_seo_description") or "").strip()
    dt, dm = set(), set()
    if title and await db.products.count_documents(
            {"current_seo_title": p["current_seo_title"], "id": {"$ne": product_id}}) > 0:
        dt.add(title.lower())
    if meta and await db.products.count_documents(
            {"current_seo_description": p["current_seo_description"], "id": {"$ne": product_id}}) > 0:
        dm.add(meta.lower())
    issues, score, breakdown, bucket = analyze(p, rules, dt, dm)
    await db.products.update_one({"id": product_id}, {"$set": {
        "issue_codes": issues, "seo_score": score,
        "score_breakdown": breakdown, "status_bucket": bucket,
    }})
    p.update({"issue_codes": issues, "seo_score": score,
              "score_breakdown": breakdown, "status_bucket": bucket})
    return p


async def reanalyze_one_collection(collection_id: str):
    rules = await get_rules()
    c = await db.collections_seo.find_one({"id": collection_id})
    if not c:
        return None
    issues, score, breakdown, bucket = analyze(c, rules, set(), set())
    await db.collections_seo.update_one({"id": collection_id}, {"$set": {
        "issue_codes": issues, "seo_score": score,
        "score_breakdown": breakdown, "status_bucket": bucket,
    }})
    c.update({"issue_codes": issues, "seo_score": score,
              "score_breakdown": breakdown, "status_bucket": bucket})
    return c
