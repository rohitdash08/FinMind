"""API response compression, payload optimization, and ETag support.

Provides:
- gzip/brotli compression via flask-compress
- Automatic null-field stripping from JSON responses
- ETag generation for conditional GET (304 Not Modified)
- Response-size observability headers (X-Original-Size / X-Compressed-Size)
- A generic ``paginate_query`` helper for list endpoints
"""

import hashlib
import json
import logging
from typing import Any

from flask import Flask, Response, request

logger = logging.getLogger("finmind.compression")


# ---------------------------------------------------------------------------
# flask-compress configuration
# ---------------------------------------------------------------------------

def init_compression(app: Flask) -> None:
    """Initialise flask-compress with sensible defaults for an API backend."""
    from flask_compress import Compress

    app.config.setdefault("COMPRESS_ALGORITHM", ["br", "gzip", "deflate"])
    app.config.setdefault("COMPRESS_MIN_SIZE", 256)  # bytes
    # Compress JSON and plain-text responses
    app.config.setdefault(
        "COMPRESS_MIMETYPES",
        [
            "application/json",
            "text/plain",
            "text/html",
            "text/css",
            "application/javascript",
        ],
    )
    Compress(app)
    logger.info("Response compression enabled (br + gzip)")


# ---------------------------------------------------------------------------
# JSON payload optimisation – strip null / None values
# ---------------------------------------------------------------------------

def _strip_nulls(obj: Any) -> Any:
    """Recursively remove keys whose value is ``None`` from dicts."""
    if isinstance(obj, dict):
        return {k: _strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nulls(item) for item in obj]
    return obj


def optimize_json_response(response: Response) -> Response:
    """Strip null fields from JSON responses and inject size / ETag headers.

    This is designed to be called from an ``after_request`` hook.
    """
    if response.content_type and "application/json" not in response.content_type:
        return response

    # Only process successful responses with a body
    if response.status_code < 200 or response.status_code >= 300:
        return response

    raw = response.get_data(as_text=True)
    if not raw:
        return response

    original_size = len(raw.encode("utf-8"))

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return response

    optimized = _strip_nulls(data)
    compact = json.dumps(optimized, separators=(",", ":"), sort_keys=True)
    optimized_size = len(compact.encode("utf-8"))

    # ETag based on content hash – enables 304 responses
    etag = '"' + hashlib.md5(compact.encode("utf-8")).hexdigest() + '"'

    # Check If-None-Match for conditional GET
    if request.method == "GET":
        if_none_match = request.headers.get("If-None-Match", "").strip()
        if if_none_match == etag:
            not_modified = Response(status=304)
            not_modified.headers["ETag"] = etag
            return not_modified

    response.set_data(compact)
    response.headers["ETag"] = etag
    response.headers["X-Original-Size"] = str(original_size)
    response.headers["X-Compressed-Size"] = str(optimized_size)
    response.headers["Content-Length"] = str(optimized_size)

    savings_pct = (
        round((1 - optimized_size / original_size) * 100, 1)
        if original_size > 0
        else 0
    )
    if savings_pct > 0:
        logger.debug(
            "JSON optimised %s %s: %d -> %d bytes (%.1f%% savings)",
            request.method,
            request.path,
            original_size,
            optimized_size,
            savings_pct,
        )

    return response


# ---------------------------------------------------------------------------
# Generic pagination helper
# ---------------------------------------------------------------------------

def paginate_query(query, *, page: int = 1, page_size: int = 50, max_page_size: int = 200):
    """Apply LIMIT/OFFSET pagination to an SQLAlchemy query.

    Returns ``(items, meta)`` where *meta* is a dict with pagination info.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, max_page_size))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return items, {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, -(-total // page_size)),  # ceil division
    }


def parse_pagination_args() -> tuple[int, int]:
    """Extract ``page`` and ``page_size`` from the current request query string."""
    try:
        page = max(1, int(request.args.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = max(1, min(200, int(request.args.get("page_size", "50"))))
    except (ValueError, TypeError):
        page_size = 50
    return page, page_size
