"""Phase 4/5 shared foundations: validation/severity engine, normalization + hashing,
conflict detection, lease-based locks, correlation IDs and source-metadata constants.

SECURITY: the SEO-only write allowlist is defined in shopify_client and re-asserted here.
Nothing in this module may broaden the set of writable Shopify fields.
"""
import re
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from pymongo.errors import DuplicateKeyError

from db import db
from utils import now_iso
from seo import _keyword_stuffing, DEFAULT_RULES

logger = logging.getLogger("bulk")

# ---- draft/publish source provenance (Phase 6 AI hook left intentionally) ----
SOURCE_MANUAL = "manual"
SOURCE_BULK = "bulk"
SOURCE_CSV = "csv"
SOURCE_AI = "ai"          # reserved for Phase 6 (not implemented in this delivery)
SOURCE_ROLLBACK = "rollback"
SOURCE_RETRY = "retry"

# ---- forbidden (non-SEO) columns/fields — superset used by CSV + bulk guards ----
FORBIDDEN_FIELDS = {
    "price", "compare_at_price", "compare_at", "compareatprice", "cost",
    "inventory", "inventory_quantity", "inventory_qty", "stock", "quantity",
    "sku", "barcode", "vendor", "product_title", "title", "name",
    "product_status", "status", "published", "variants", "variant", "option",
    "weight", "shipping", "tax", "taxes", "body", "body_html", "description",
    "collection_membership", "collections", "image", "images", "media",
    "orders", "customers", "discounts", "tags", "handle_new", "product_type",
}

# columns that are read-only context (allowed to be present, ignored for writes)
READ_ONLY_COLUMNS = {
    "shopify_product_id", "shopify_collection_id", "handle",
    "product_title_read_only", "collection_title_read_only",
    "current_seo_title", "current_meta_description", "current_score",
    "issue_codes", "last_synced_at",
}

# only these CSV columns may become writes, mapped to SEO draft fields
CSV_WRITE_MAP = {
    "new_seo_title": "seo_title",
    "new_meta_description": "meta_description",
    "new_meta": "meta_description",
}

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def new_correlation_id() -> str:
    return f"cid-{uuid.uuid4().hex[:16]}"


def normalize_seo(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def seo_hash(s: str):
    n = normalize_seo(s)
    return hashlib.sha1(n.encode("utf-8")).hexdigest() if n else None


def has_control_chars(s: str) -> bool:
    return bool(_CONTROL_RE.search(s or ""))


def csv_safe(value):
    """Mitigate spreadsheet formula injection for user-facing CSV export ONLY.
    Never used to mutate the canonical value stored in MongoDB."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _FORMULA_PREFIX:
        return "'" + s
    return s


# --------------------------- conflict detection ---------------------------
def compute_conflict(rec: dict) -> str:
    """Returns: none | shopify_changed | resource_deleted.
    A draft is 'based on' the Shopify value captured when it was created
    (draft_base_*). If the live Shopify value moved since then, it is stale."""
    if rec.get("shopify_state") in ("deleted", "archived", "unavailable"):
        return "resource_deleted"
    if not rec.get("has_draft"):
        return "none"
    if rec.get("conflict_resolved"):
        return "none"
    base_t = rec.get("draft_base_title")
    base_d = rec.get("draft_base_description")
    if base_t is None and base_d is None:
        return "none"  # legacy draft without a captured base — treat as safe
    cur_t = rec.get("current_seo_title")
    cur_d = rec.get("current_seo_description")
    if (base_t or None) != (cur_t or None) or (base_d or None) != (cur_d or None):
        return "shopify_changed"
    return "none"


# --------------------------- validation engine ---------------------------
def _order(sev):
    return {"READY": 0, "WARNING": 1, "ERROR": 2}[sev]


def validate_record(rec: dict, rules: dict, dup_titles: set, dup_metas: set) -> dict:
    """Deterministic validation of the record's *draft* (or current if no draft).
    Returns severity (READY|WARNING|ERROR), codes, messages, effective values, conflict."""
    r = {**DEFAULT_RULES, **(rules or {})}
    codes, msgs = [], []
    sev = "READY"

    def bump(s):
        nonlocal sev
        if _order(s) > _order(sev):
            sev = s

    has_draft = bool(rec.get("has_draft"))
    title = ((rec.get("draft_seo_title") if has_draft else rec.get("current_seo_title")) or "").strip()
    meta = ((rec.get("draft_seo_description") if has_draft else rec.get("current_seo_description")) or "").strip()

    # ----- blocking (ERROR) conditions -----
    conflict = compute_conflict(rec)
    if conflict == "resource_deleted":
        codes.append("RESOURCE_DELETED"); msgs.append("Shopify resource no longer exists / archived"); bump("ERROR")
    elif conflict == "shopify_changed":
        codes.append("PUBLISH_CONFLICT")
        msgs.append("Shopify SEO changed externally since this draft was created — resolve the conflict before publishing")
        bump("ERROR")

    if has_control_chars(title) or has_control_chars(meta):
        codes.append("INVALID_INPUT"); msgs.append("Contains invalid control characters"); bump("ERROR")

    if not title and not meta:
        codes.append("EMPTY_SEO"); msgs.append("Both SEO title and meta description are empty"); bump("ERROR")

    # ----- warnings -----
    if not title:
        codes.append("MISSING_SEO_TITLE"); msgs.append("SEO title is empty"); bump("WARNING")
    else:
        if len(title) < r["title_min"]:
            codes.append("TITLE_TOO_SHORT"); msgs.append(f"Title {len(title)} chars (recommended {r['title_min']}-{r['title_max']})"); bump("WARNING")
        elif len(title) > r["title_max"]:
            codes.append("TITLE_ABOVE_RANGE"); msgs.append(f"Title {len(title)} chars, above recommended {r['title_min']}-{r['title_max']}"); bump("WARNING")
        if normalize_seo(title) in dup_titles:
            codes.append("DUPLICATE_TITLE"); msgs.append("SEO title duplicated across other records"); bump("WARNING")
        if _keyword_stuffing(title):
            codes.append("KEYWORD_STUFFING"); msgs.append("Title shows keyword stuffing / excessive repetition"); bump("WARNING")

    if not meta:
        codes.append("MISSING_META_DESCRIPTION"); msgs.append("Meta description is empty"); bump("WARNING")
    else:
        if len(meta) < r["meta_min"]:
            codes.append("META_TOO_SHORT"); msgs.append(f"Meta {len(meta)} chars (recommended {r['meta_min']}-{r['meta_max']})"); bump("WARNING")
        elif len(meta) > r["meta_max"]:
            codes.append("META_ABOVE_RANGE"); msgs.append(f"Meta {len(meta)} chars, above recommended {r['meta_min']}-{r['meta_max']}"); bump("WARNING")
        if normalize_seo(meta) in dup_metas:
            codes.append("DUPLICATE_META"); msgs.append("Meta description duplicated across other records"); bump("WARNING")

    if has_draft:
        cur_t = (rec.get("current_seo_title") or "").strip()
        cur_d = (rec.get("current_seo_description") or "").strip()
        if title == cur_t and meta == cur_d:
            codes.append("UNCHANGED"); msgs.append("Draft is identical to current Shopify value"); bump("WARNING")

    if (rec.get("seo_score") or 0) < 55 and title and meta and not has_draft:
        codes.append("LOW_SCORE"); msgs.append("SEO score is low"); bump("WARNING")

    return {"severity": sev, "codes": codes, "messages": msgs,
            "effective_title": title, "effective_meta": meta, "conflict": conflict}


# --------------------------- lease-based locks ---------------------------
async def acquire_lock(key: str, owner: str, ttl_seconds: int = 300) -> bool:
    """Atomic lease. Returns True if acquired. Expired leases can be re-acquired.
    Uses a unique _id; a live lease held by another owner raises DuplicateKeyError."""
    now = now_iso()
    exp = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    try:
        await db.locks.find_one_and_update(
            {"_id": key, "$or": [{"expires_at": {"$lt": now}}, {"owner": owner}]},
            {"$set": {"owner": owner, "expires_at": exp, "acquired_at": now}},
            upsert=True,
        )
        return True
    except DuplicateKeyError:
        return False


async def release_lock(key: str, owner: str):
    await db.locks.delete_one({"_id": key, "owner": owner})


# --------------------------- error classification ---------------------------
_PERMANENT_MARKERS = ("non_seo_field_write_denied", "invalid", "not found", "notfound",
                      "permission", "denied", "deleted", "userer", "rejected",
                      "unprocessable", "malformed", "validation")
_TRANSIENT_MARKERS = ("throttl", "timeout", "timed out", "429", "500", "502", "503",
                      "temporarily", "connection", "reset", "unavailable", "rate limit")


def is_retryable(error_message: str) -> bool:
    m = (error_message or "").lower()
    if any(k in m for k in _PERMANENT_MARKERS):
        return False
    if any(k in m for k in _TRANSIENT_MARKERS):
        return True
    return False  # default: do not retry unknown/permanent errors
