"""
payload_optimizer.py — utility helpers for lean API responses.

Provides:
  - strip_none_values(obj)  — recursively remove None-valued keys from dicts/lists
  - paginate_query(query, page, per_page) — standard cursor pagination helper
  - make_etag(data)  — deterministic ETag from response content for caching
"""
import hashlib
import json
from math import ceil


def strip_none_values(obj):
    """Recursively remove keys with None values from a dict or list of dicts."""
    if isinstance(obj, dict):
        return {k: strip_none_values(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_none_values(item) for item in obj]
    return obj


def paginate_query(query, page: int = 1, per_page: int = 50):
    """
    Apply LIMIT/OFFSET pagination to a SQLAlchemy query.

    Returns:
        dict with keys: items, page, per_page, total, pages
    """
    page = max(1, page)
    per_page = min(max(1, per_page), 200)   # cap at 200
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": ceil(total / per_page) if total else 0,
    }


def make_etag(data: dict | list) -> str:
    """
    Generate a stable ETag from serialisable response data.
    Uses MD5 (non-cryptographic, fast) — appropriate for cache validation only.
    """
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(payload.encode()).hexdigest()
