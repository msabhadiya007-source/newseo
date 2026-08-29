"""Deterministic SEO analyzer + scoring (70% deterministic, 30% AI-assisted)."""
import re
from collections import Counter

DEFAULT_RULES = {
    "title_min": 50,
    "title_max": 60,
    "meta_min": 140,
    "meta_max": 160,
    "brand": "UrbanDotted",
    "country": "Australia",
}

# Issue codes
MISSING_SEO_TITLE = "MISSING_SEO_TITLE"
MISSING_META_DESCRIPTION = "MISSING_META_DESCRIPTION"
TITLE_TOO_SHORT = "TITLE_TOO_SHORT"
TITLE_ABOVE_RANGE = "TITLE_ABOVE_RANGE"
META_TOO_SHORT = "META_TOO_SHORT"
META_ABOVE_RANGE = "META_ABOVE_RANGE"
DUPLICATE_TITLE = "DUPLICATE_TITLE"
DUPLICATE_META = "DUPLICATE_META"
KEYWORD_STUFFING = "KEYWORD_STUFFING"
REPETITIVE_TITLE = "REPETITIVE_TITLE"

ISSUE_LABELS = {
    MISSING_SEO_TITLE: "Missing SEO title",
    MISSING_META_DESCRIPTION: "Missing meta description",
    TITLE_TOO_SHORT: "SEO title too short",
    TITLE_ABOVE_RANGE: "SEO title above recommended range",
    META_TOO_SHORT: "Meta description too short",
    META_ABOVE_RANGE: "Meta description above recommended range",
    DUPLICATE_TITLE: "Duplicate SEO title",
    DUPLICATE_META: "Duplicate meta description",
    KEYWORD_STUFFING: "Keyword stuffing indicators",
    REPETITIVE_TITLE: "Repetitive title",
}


def _keyword_stuffing(text: str) -> bool:
    words = [w for w in re.findall(r"[a-zA-Z0-9']+", (text or "").lower()) if len(w) > 2]
    if not words:
        return False
    counts = Counter(words)
    return any(c >= 4 for c in counts.values())


def analyze(product: dict, rules: dict, dup_titles: set, dup_metas: set):
    """Return (issue_codes, score, breakdown, status_bucket)."""
    r = {**DEFAULT_RULES, **(rules or {})}
    title = (product.get("current_seo_title") or "").strip()
    meta = (product.get("current_seo_description") or "").strip()
    brand = r["brand"].lower()

    issues = []
    positives = []
    problems = []

    # Deterministic points out of 70
    det = 0.0

    # Title presence (16)
    if title:
        det += 16
        positives.append("SEO title present")
    else:
        issues.append(MISSING_SEO_TITLE)
        problems.append("SEO title is missing")

    # Title length (10)
    tlen = len(title)
    if title:
        if r["title_min"] <= tlen <= r["title_max"]:
            det += 10
            positives.append(f"Title length is in the recommended range ({tlen} chars)")
        elif tlen < r["title_min"]:
            issues.append(TITLE_TOO_SHORT)
            det += max(0, 10 * (tlen / max(1, r["title_min"])) * 0.6)
            problems.append(f"Title is only {tlen} characters (recommended {r['title_min']}-{r['title_max']})")
        else:
            issues.append(TITLE_ABOVE_RANGE)
            det += 5
            problems.append(f"Title is {tlen} characters, above the recommended {r['title_min']}-{r['title_max']}")

    # Meta presence (16)
    if meta:
        det += 16
        positives.append("Meta description present")
    else:
        issues.append(MISSING_META_DESCRIPTION)
        problems.append("Meta description is missing")

    # Meta length (10)
    mlen = len(meta)
    if meta:
        if r["meta_min"] <= mlen <= r["meta_max"]:
            det += 10
            positives.append(f"Meta length is in the recommended range ({mlen} chars)")
        elif mlen < r["meta_min"]:
            issues.append(META_TOO_SHORT)
            det += max(0, 10 * (mlen / max(1, r["meta_min"])) * 0.6)
            problems.append(f"Meta description is only {mlen} characters (recommended {r['meta_min']}-{r['meta_max']})")
        else:
            issues.append(META_ABOVE_RANGE)
            det += 5
            problems.append(f"Meta description is {mlen} characters, above the recommended {r['meta_min']}-{r['meta_max']}")

    # Uniqueness (7 + 7)
    if title:
        if title.lower() in dup_titles:
            issues.append(DUPLICATE_TITLE)
            problems.append("SEO title is duplicated across other products")
        else:
            det += 7
            positives.append("SEO title is unique")
    if meta:
        if meta.lower() in dup_metas:
            issues.append(DUPLICATE_META)
            problems.append("Meta description is duplicated across other products")
        else:
            det += 7
            positives.append("Meta description is unique")

    # Keyword stuffing (4)
    if title and _keyword_stuffing(title):
        issues.append(KEYWORD_STUFFING)
        problems.append("Title shows keyword stuffing / excessive repetition")
    else:
        det += 4

    # Brand presence (informational positive, no dedicated points)
    if title and brand in title.lower():
        positives.append(f"Brand '{r['brand']}' present in title")

    # (Image ALT SEO analysis has been removed from scope — it contributes ZERO to the
    # score and is never emitted as an issue. The 3 former ALT points were redistributed
    # to Title presence (+1), Meta presence (+1) and Keyword stuffing (+1) so the
    # deterministic maximum remains 70 and scores still normalize to 0-100.)

    det = round(min(70.0, det), 1)

    ai_quality = product.get("ai_quality")  # 0-30 or None
    if ai_quality is not None:
        score = int(round(det + min(30, max(0, ai_quality))))
    else:
        score = int(round(det / 70 * 100))
    score = max(0, min(100, score))

    # Status bucket
    if MISSING_SEO_TITLE in issues or MISSING_META_DESCRIPTION in issues:
        bucket = "missing"
    elif not issues and score >= 85:
        bucket = "optimised"
    elif score < 55:
        bucket = "critical"
    elif score < 75:
        bucket = "needs_improvement"
    else:
        bucket = "good"

    breakdown = {
        "deterministic": det,
        "ai_quality": ai_quality,
        "positives": positives,
        "problems": problems,
    }
    return issues, score, breakdown, bucket
