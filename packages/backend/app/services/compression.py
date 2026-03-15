"""API response compression and payload optimization middleware.

Provides:
- Gzip/Deflate response compression with configurable thresholds
- JSON payload optimization (field selection, pagination metadata)
- Response size tracking and analytics
- Content-type aware compression
- ETag support for conditional requests
- Compression statistics API
"""

import gzip
import hashlib
import io
import json
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import Flask, Response, request, g


# ─── Configuration ──────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "min_size": 500,  # Minimum response size (bytes) to compress
    "compression_level": 6,  # gzip level (1-9)
    "excluded_content_types": {"image/", "audio/", "video/", "application/zip"},
    "enable_etag": True,
    "enable_stats": True,
    "max_page_size": 100,
    "default_page_size": 20,
}


# ─── In-Memory Stats ────────────────────────────────────────────────

_compression_stats = {
    "total_requests": 0,
    "compressed_responses": 0,
    "total_original_bytes": 0,
    "total_compressed_bytes": 0,
    "etag_hits": 0,
    "by_endpoint": {},
    "started_at": datetime.utcnow().isoformat(),
}


def _reset_stats():
    """Reset compression statistics."""
    global _compression_stats
    _compression_stats = {
        "total_requests": 0,
        "compressed_responses": 0,
        "total_original_bytes": 0,
        "total_compressed_bytes": 0,
        "etag_hits": 0,
        "by_endpoint": {},
        "started_at": datetime.utcnow().isoformat(),
    }


def _record_stats(endpoint: str, original_size: int, compressed_size: int,
                  was_compressed: bool, etag_hit: bool = False):
    """Record compression statistics for an endpoint."""
    _compression_stats["total_requests"] += 1
    _compression_stats["total_original_bytes"] += original_size
    _compression_stats["total_compressed_bytes"] += compressed_size

    if was_compressed:
        _compression_stats["compressed_responses"] += 1

    if etag_hit:
        _compression_stats["etag_hits"] += 1

    if endpoint not in _compression_stats["by_endpoint"]:
        _compression_stats["by_endpoint"][endpoint] = {
            "requests": 0,
            "original_bytes": 0,
            "compressed_bytes": 0,
            "compressed_count": 0,
        }

    ep = _compression_stats["by_endpoint"][endpoint]
    ep["requests"] += 1
    ep["original_bytes"] += original_size
    ep["compressed_bytes"] += compressed_size
    if was_compressed:
        ep["compressed_count"] += 1


def get_compression_stats() -> dict:
    """Get compression statistics summary."""
    stats = dict(_compression_stats)
    total_orig = stats["total_original_bytes"]
    total_comp = stats["total_compressed_bytes"]

    if total_orig > 0:
        stats["overall_ratio"] = round(1 - (total_comp / total_orig), 4)
        stats["bytes_saved"] = total_orig - total_comp
    else:
        stats["overall_ratio"] = 0
        stats["bytes_saved"] = 0

    # Per-endpoint ratios
    for ep_name, ep in stats["by_endpoint"].items():
        if ep["original_bytes"] > 0:
            ep["ratio"] = round(1 - (ep["compressed_bytes"] / ep["original_bytes"]), 4)
        else:
            ep["ratio"] = 0

    return stats


# ─── Compression Engine ─────────────────────────────────────────────


def _should_compress(response: Response, config: dict) -> bool:
    """Determine if a response should be compressed."""
    # Check content type exclusions
    content_type = response.content_type or ""
    for excluded in config["excluded_content_types"]:
        if excluded in content_type:
            return False

    # Check if already encoded
    if response.headers.get("Content-Encoding"):
        return False

    # Check minimum size
    content_length = response.content_length
    if content_length is not None and content_length < config["min_size"]:
        return False

    return True


def _accepts_encoding(encoding: str) -> bool:
    """Check if client accepts a given encoding."""
    accept = request.headers.get("Accept-Encoding", "")
    return encoding in accept


def _compress_gzip(data: bytes, level: int = 6) -> bytes:
    """Compress data using gzip."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=level) as f:
        f.write(data)
    return buf.getvalue()


def _compute_etag(data: bytes) -> str:
    """Compute a weak ETag for response data."""
    return f'W/"{hashlib.md5(data).hexdigest()}"'


# ─── Payload Optimization ───────────────────────────────────────────


def optimize_json_payload(data: dict | list, fields: Optional[list] = None) -> dict | list:
    """Optimize a JSON payload by selecting only requested fields.

    Args:
        data: The JSON data to optimize
        fields: List of field names to include (None = all fields)

    Returns:
        Optimized data with only requested fields
    """
    if fields is None or not fields:
        return data

    field_set = set(fields)

    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in field_set}
                for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        return {k: v for k, v in data.items() if k in field_set}

    return data


def paginate_response(items: list, page: int = 1, page_size: int = 20,
                      max_page_size: int = 100) -> dict:
    """Create a paginated response with metadata.

    Args:
        items: Full list of items
        page: Page number (1-indexed)
        page_size: Items per page
        max_page_size: Maximum allowed page size

    Returns:
        Dict with items, pagination metadata
    """
    page_size = min(page_size, max_page_size)
    page = max(1, page)

    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "items": items[start:end],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


def slim_response(data: dict, exclude_nulls: bool = True,
                  exclude_empty: bool = False) -> dict:
    """Remove null and optionally empty values from response.

    Reduces payload size by stripping unnecessary null fields.
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        if exclude_nulls and v is None:
            continue
        if exclude_empty and v in ([], {}, ""):
            continue
        if isinstance(v, dict):
            v = slim_response(v, exclude_nulls, exclude_empty)
        result[k] = v
    return result


# ─── Middleware ──────────────────────────────────────────────────────


def init_compression(app: Flask, config: dict | None = None):
    """Initialize compression middleware on a Flask app.

    This adds after_request hooks that handle:
    - Gzip compression for eligible responses
    - ETag generation and conditional request handling
    - Compression statistics tracking

    Args:
        app: Flask application instance
        config: Optional configuration overrides
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    @app.after_request
    def compress_response(response: Response) -> Response:
        # Skip for streaming or 304 responses
        if response.status_code == 304 or response.is_streamed:
            return response

        # Get original data
        original_data = response.get_data()
        original_size = len(original_data)

        endpoint = request.endpoint or request.path

        # ETag handling
        if cfg["enable_etag"] and original_data and request.method == "GET":
            etag = _compute_etag(original_data)
            response.headers["ETag"] = etag

            if_none_match = request.headers.get("If-None-Match")
            if if_none_match and if_none_match == etag:
                if cfg["enable_stats"]:
                    _record_stats(endpoint, original_size, 0, False, etag_hit=True)
                return Response(status=304, headers={"ETag": etag})

        # Compression
        if _should_compress(response, cfg) and _accepts_encoding("gzip"):
            if original_size >= cfg["min_size"]:
                compressed = _compress_gzip(original_data, cfg["compression_level"])
                compressed_size = len(compressed)

                # Only use compression if it actually reduces size
                if compressed_size < original_size:
                    response.set_data(compressed)
                    response.headers["Content-Encoding"] = "gzip"
                    response.headers["Content-Length"] = compressed_size
                    response.headers["Vary"] = "Accept-Encoding"

                    if cfg["enable_stats"]:
                        _record_stats(endpoint, original_size, compressed_size, True)
                    return response

        # No compression applied
        if cfg["enable_stats"]:
            _record_stats(endpoint, original_size, original_size, False)

        return response

    return app
