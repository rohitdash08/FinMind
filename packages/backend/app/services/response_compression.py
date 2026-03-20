"""
API Response Compression & Payload Optimization.

Implements:
1. Gzip/deflate middleware for large responses (> 1KB threshold)
2. Response payload optimization: remove null fields, trim whitespace
3. Field filtering: ?fields=id,name,amount to return only needed fields
4. Response size analytics: tracking compression ratios

For Flask, this hooks into after_request to compress responses.
Also provides a @compress_response decorator for individual endpoints.
"""
from __future__ import annotations
import gzip
import zlib
import json
import re
from functools import wraps
from typing import Callable
from datetime import datetime

from flask import request, current_app, Response


# ── Configuration ──────────────────────────────────────────────────────

COMPRESS_THRESHOLD_BYTES = 1024  # Only compress responses > 1KB
COMPRESS_LEVEL = 6               # zlib compression level (1-9, 6 is default)
COMPRESSIBLE_TYPES = {
    "application/json",
    "text/html",
    "text/plain",
    "text/css",
    "application/javascript",
}


# ── Compression helpers ────────────────────────────────────────────────

def _gzip_compress(data: bytes) -> bytes:
    """Compress bytes using gzip."""
    return gzip.compress(data, compresslevel=COMPRESS_LEVEL)


def _deflate_compress(data: bytes) -> bytes:
    """Compress bytes using deflate (zlib without header)."""
    return zlib.compress(data, COMPRESS_LEVEL)


def _accepts_encoding(encoding: str) -> bool:
    """Check if client accepts a given content encoding."""
    accept_encoding = request.headers.get("Accept-Encoding", "")
    # Simple check for encoding presence
    return encoding in accept_encoding


def _is_compressible(content_type: str) -> bool:
    """Check if the content type is worth compressing."""
    base_type = content_type.split(";")[0].strip().lower()
    return base_type in COMPRESSIBLE_TYPES


def compress_response_data(
    data: bytes,
    content_type: str = "application/json",
) -> tuple[bytes, str]:
    """
    Compress response data if it meets the threshold.

    Returns (compressed_data, content_encoding) or (original_data, "")
    """
    if len(data) < COMPRESS_THRESHOLD_BYTES:
        return data, ""

    if not _is_compressible(content_type):
        return data, ""

    # Prefer gzip over deflate
    if _accepts_encoding("gzip"):
        compressed = _gzip_compress(data)
        if len(compressed) < len(data):
            return compressed, "gzip"

    if _accepts_encoding("deflate"):
        compressed = _deflate_compress(data)
        if len(compressed) < len(data):
            return compressed, "deflate"

    return data, ""


# ── Payload optimization ──────────────────────────────────────────────

def strip_null_fields(obj: object) -> object:
    """
    Recursively remove null/None values from a dict or list.
    Reduces payload size by eliminating unnecessary nulls.
    """
    if isinstance(obj, dict):
        return {k: strip_null_fields(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_null_fields(item) for item in obj]
    return obj


def filter_fields(obj: object, fields: list[str]) -> object:
    """
    Filter a dict (or list of dicts) to only include specified fields.
    Nested fields supported via dot notation (e.g. "user.name").
    """
    if not fields:
        return obj

    if isinstance(obj, list):
        return [filter_fields(item, fields) for item in obj]

    if isinstance(obj, dict):
        result = {}
        for field in fields:
            if "." in field:
                top, rest = field.split(".", 1)
                if top in obj:
                    nested = filter_fields(obj[top], [rest])
                    if nested:
                        result[top] = nested
            elif field in obj:
                result[field] = obj[field]
        return result

    return obj


def optimize_payload(
    data: dict,
    fields: list[str] | None = None,
    strip_nulls: bool = True,
) -> dict:
    """
    Apply all payload optimizations to a response dict.

    Args:
        data: Response payload dict
        fields: Optional list of field names to include (field filtering)
        strip_nulls: Remove null values (default True)

    Returns:
        Optimized payload dict
    """
    if strip_nulls:
        data = strip_null_fields(data)
    if fields:
        data = filter_fields(data, fields)
    return data


# ── Flask middleware ──────────────────────────────────────────────────

def init_compression(app) -> None:
    """
    Register after_request handler to automatically compress large responses.

    Usage in app factory:
        from .services.response_compression import init_compression
        init_compression(app)
    """
    @app.after_request
    def compress_after_request(response: Response) -> Response:
        # Skip already-compressed or non-JSON responses
        if response.content_encoding:
            return response
        content_type = response.content_type or ""
        if not _is_compressible(content_type):
            return response
        data = response.get_data()
        if len(data) < COMPRESS_THRESHOLD_BYTES:
            return response

        compressed, encoding = compress_response_data(data, content_type)
        if encoding:
            response.set_data(compressed)
            response.headers["Content-Encoding"] = encoding
            response.headers["Vary"] = "Accept-Encoding"
            response.headers["Content-Length"] = len(compressed)
        return response


def fields_from_request() -> list[str] | None:
    """Extract ?fields=a,b,c from request query string."""
    fields_str = request.args.get("fields", "")
    if not fields_str:
        return None
    return [f.strip() for f in fields_str.split(",") if f.strip()]


# ── Decorator ─────────────────────────────────────────────────────────

def compress_response(f: Callable) -> Callable:
    """
    Decorator to compress a single endpoint's response.
    Also supports ?fields=a,b,c for field filtering.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        response = f(*args, **kwargs)
        # Only handle Response objects with JSON
        if not isinstance(response, Response):
            return response
        content_type = response.content_type or ""
        if "json" not in content_type:
            return response

        # Apply field filtering if requested
        fields = fields_from_request()
        if fields:
            try:
                data = response.get_json()
                if data:
                    data = filter_fields(data, fields)
                    response.set_data(json.dumps(data))
            except Exception:
                pass

        # Compress
        data = response.get_data()
        compressed, encoding = compress_response_data(data, content_type)
        if encoding:
            response.set_data(compressed)
            response.headers["Content-Encoding"] = encoding
            response.headers["Vary"] = "Accept-Encoding"
            response.headers["Content-Length"] = len(compressed)
        return response

    return decorated


# ── Compression stats ──────────────────────────────────────────────────

def measure_compression(data: bytes) -> dict:
    """
    Measure compression ratios for a payload.
    Returns size stats for original, gzip, and deflate.
    """
    gzip_compressed = _gzip_compress(data)
    deflate_compressed = _deflate_compress(data)
    original_size = len(data)

    return {
        "original_bytes": original_size,
        "gzip_bytes": len(gzip_compressed),
        "deflate_bytes": len(deflate_compressed),
        "gzip_ratio": round(len(gzip_compressed) / original_size, 3) if original_size else 1,
        "deflate_ratio": round(len(deflate_compressed) / original_size, 3) if original_size else 1,
        "gzip_savings_pct": round((1 - len(gzip_compressed) / original_size) * 100, 1) if original_size else 0,
    }