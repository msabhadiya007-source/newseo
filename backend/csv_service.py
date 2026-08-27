"""CSV import parsing + validation and export request building.

Strict SEO-only: any forbidden commerce column rejects the whole file with
NON_SEO_FIELD_WRITE_DENIED before any draft is created.
"""
import os
import io
import csv as csvmod
import uuid
import logging

from db import db
from utils import now_iso
from analysis import get_rules
import bulk_common as bc

logger = logging.getLogger("csv")

CSV_MAX_UPLOAD_MB = float(os.environ.get("CSV_MAX_UPLOAD_MB", "10"))
CSV_MAX_ROWS = int(os.environ.get("CSV_MAX_ROWS", "50000"))


class CsvError(Exception):
    def __init__(self, code, message, extra=None):
        self.code = code
        self.message = message
        self.extra = extra or {}
        super().__init__(message)


def _norm_col(c):
    return (c or "").strip().lower().replace(" ", "_").replace("-", "_")


async def parse_and_validate(content: bytes, filename: str, resource_type: str, user: dict, ds: str = None) -> dict:
    size_mb = len(content) / (1024 * 1024)
    if size_mb > CSV_MAX_UPLOAD_MB:
        raise CsvError("CSV_TOO_LARGE", f"File is {size_mb:.1f} MB; limit is {CSV_MAX_UPLOAD_MB} MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise CsvError("CSV_ENCODING", "Unable to decode file; use UTF-8 encoding")

    reader = csvmod.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvError("CSV_EMPTY", "The CSV file is empty")
    cols = [_norm_col(c) for c in header]
    if not any(c for c in cols):
        raise CsvError("CSV_EMPTY", "The CSV file has no header row")

    # --- forbidden column rejection (before anything else) ---
    forbidden = [orig for orig, n in zip(header, cols) if n in bc.FORBIDDEN_FIELDS]
    if forbidden:
        raise CsvError("CSV_FORBIDDEN_COLUMN",
                       f"NON_SEO_FIELD_WRITE_DENIED: forbidden columns not allowed: {', '.join(forbidden)}",
                       {"forbidden_columns": forbidden})

    idf = "shopify_product_id" if resource_type == "product" else "shopify_collection_id"
    id_aliases = {idf, "shopify_id", "id"}
    # locate columns
    def find_col(names):
        for i, n in enumerate(cols):
            if n in names:
                return i
        return None
    id_idx = find_col(id_aliases)
    handle_idx = find_col({"handle"})
    title_idx = find_col({k for k, v in bc.CSV_WRITE_MAP.items() if v == "seo_title"})
    meta_idx = find_col({k for k, v in bc.CSV_WRITE_MAP.items() if v == "meta_description"})
    if id_idx is None and handle_idx is None:
        raise CsvError("CSV_NO_IDENTIFIER", f"CSV must contain a '{idf}' or 'handle' column")
    if title_idx is None and meta_idx is None:
        raise CsvError("CSV_NO_WRITABLE", "CSV must contain 'new_seo_title' and/or 'new_meta_description'")

    raw_rows = []
    for r in reader:
        raw_rows.append(r)
        if len(raw_rows) > CSV_MAX_ROWS:
            raise CsvError("CSV_TOO_MANY_ROWS", f"File exceeds the {CSV_MAX_ROWS}-row limit")
    if not raw_rows:
        raise CsvError("CSV_EMPTY", "The CSV file has a header but no data rows")

    from shopify_client import shopify_client
    ds = ds or shopify_client.data_source
    col = db.products if resource_type == "product" else db.collections_seo

    # collect referenced ids/handles and resolve to local records (batched)
    shop_ids, handles = set(), set()
    parsed = []
    for i, r in enumerate(raw_rows):
        def cell(idx):
            return r[idx].strip() if idx is not None and idx < len(r) else None
        sid = cell(id_idx)
        hnd = cell(handle_idx)
        parsed.append({"row": i + 2, "sid": sid, "handle": hnd,
                       "new_seo_title": cell(title_idx), "new_meta_description": cell(meta_idx)})
        if sid:
            shop_ids.add(sid)
        elif hnd:
            handles.add(hnd)

    # resolve maps
    id_map, handle_map = {}, {}
    if shop_ids:
        async for rec in col.find({idf: {"$in": list(shop_ids)}, "data_source": ds},
                                  {"_id": 0, "id": 1, idf: 1, "current_seo_title": 1,
                                   "current_seo_description": 1, "shopify_state": 1, "title": 1}):
            id_map[rec[idf]] = rec
    if handles:
        async for rec in col.find({"handle": {"$in": list(handles)}, "data_source": ds},
                                  {"_id": 0, "id": 1, "handle": 1, "current_seo_title": 1,
                                   "current_seo_description": 1, "shopify_state": 1, "title": 1}):
            handle_map[rec["handle"]] = rec

    rules = await get_rules()
    csv_job_id = f"CSV-{uuid.uuid4().hex[:8].upper()}"
    seen_ids = set()
    counts = {"total": 0, "READY": 0, "WARNING": 0, "ERROR": 0}
    docs = []
    for p in parsed:
        counts["total"] += 1
        codes, msgs, sev = [], [], "READY"

        def bump(s):
            nonlocal sev
            if bc._order(s) > bc._order(sev):
                sev = s

        rec = id_map.get(p["sid"]) if p["sid"] else handle_map.get(p["handle"])
        if not rec:
            codes.append("CSV_INVALID_RESOURCE_ID")
            msgs.append("Resource not found in the current data source")
            bump("ERROR")
            local_id = None
        else:
            local_id = rec["id"]
            if local_id in seen_ids:
                codes.append("CSV_DUPLICATE_ROW"); msgs.append("Duplicate resource row in file"); bump("ERROR")
            seen_ids.add(local_id)
            if rec.get("shopify_state") in ("deleted", "archived", "unavailable"):
                codes.append("RESOURCE_STALE"); msgs.append("Resource is stale/deleted in Shopify"); bump("ERROR")

        nt = p["new_seo_title"]
        nm = p["new_meta_description"]
        if (nt is None or nt == "") and (nm is None or nm == ""):
            codes.append("BLANK_UPDATE"); msgs.append("No SEO update value provided"); bump("WARNING")
        if bc.has_control_chars(nt) or bc.has_control_chars(nm):
            codes.append("INVALID_INPUT"); msgs.append("Contains invalid control characters"); bump("ERROR")
        if rec:
            if nt is not None and nt != "":
                if len(nt) > rules["title_max"]:
                    codes.append("TITLE_ABOVE_RANGE"); bump("WARNING")
                elif len(nt) < rules["title_min"]:
                    codes.append("TITLE_TOO_SHORT"); bump("WARNING")
                if nt == (rec.get("current_seo_title") or ""):
                    codes.append("UNCHANGED"); bump("WARNING")
            if nm is not None and nm != "":
                if len(nm) > rules["meta_max"]:
                    codes.append("META_ABOVE_RANGE"); bump("WARNING")
                elif len(nm) < rules["meta_min"]:
                    codes.append("META_TOO_SHORT"); bump("WARNING")

        counts[sev] += 1
        docs.append({
            "id": f"CROW-{uuid.uuid4().hex[:10]}", "csv_job_id": csv_job_id,
            "row_number": p["row"], "resource_type": resource_type,
            "resource_local_id": local_id, "shopify_ref": p["sid"] or p["handle"],
            "new_seo_title": nt if nt else None,
            "new_meta_description": nm if nm else None,
            "severity": sev, "codes": codes, "messages": msgs,
        })

    if docs:
        # store rows in chunks (insert_many mutates docs by adding _id)
        for i in range(0, len(docs), 2000):
            await db.csv_rows.insert_many(docs[i:i + 2000])
    for d in docs:
        d.pop("_id", None)
    job = {
        "id": csv_job_id, "kind": "import", "status": "previewed",
        "resource_type": resource_type, "filename": filename,
        "counts": counts, "created_by": user["email"], "created_at": now_iso(),
        "data_source": ds, "drafts_created": 0,
    }
    await db.csv_jobs.insert_one(dict(job))
    return {"csv_job_id": csv_job_id, "counts": counts, "resource_type": resource_type,
            "sample_errors": [d for d in docs if d["severity"] == "ERROR"][:20],
            "sample_warnings": [d for d in docs if d["severity"] == "WARNING"][:20]}
