"""Response compression (gzip / Brotli) and payload optimization middleware."""

import gzip
import hashlib
import io
import json
from typing import Any

from flask import Flask, Response, request

try:
    import brotli  # type: ignore[import-untyped]

    _HAS_BROTLI = True
except ImportError:
    _HAS_BROTLI = False

# Minimum response size (bytes) worth compressing.
_MIN_COMPRESS_BYTES = 256

# Content types eligible for compression.
_COMPRESSIBLE_TYPES = frozenset(
    {
        "application/json",
        "text/html",
        "text/plain",
        "text/css",
        "application/javascript",
        "text/xml",
        "application/xml",
    }
)


def strip_nulls(obj: Any) -> Any:
    """Recursively remove keys whose value is ``None`` from dicts."""
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_nulls(item) for item in obj]
    return obj


def compact_json(data: Any) -> bytes:
    """Serialize *data* to compact JSON bytes with null-stripping."""
    cleaned = strip_nulls(data)
    return json.dumps(cleaned, separators=(",", ":"), default=str).encode("utf-8")


def _is_compressible(response: Response) -> bool:
    ct = (response.content_type or "").split(";")[0].strip().lower()
    return ct in _COMPRESSIBLE_TYPES


def _preferred_encoding() -> str | None:
    """Return the best supported encoding from Accept-Encoding."""
    accept = request.headers.get("Accept-Encoding", "")
    if _HAS_BROTLI and "br" in accept:
        return "br"
    if "gzip" in accept:
        return "gzip"
    return None


def _compress_gzip(data: bytes, level: int = 6) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=level) as f:
        f.write(data)
    return buf.getvalue()


def _compress_brotli(data: bytes) -> bytes:
    return brotli.compress(data, quality=4)


def _etag_for(data: bytes) -> str:
    return f'"{hashlib.md5(data).hexdigest()}"'


def init_compression(app: Flask) -> None:
    """Register the after-request hook that handles compression + ETag."""

    @app.after_request
    def compress_response(response: Response) -> Response:
        # Skip streaming / non-compressible / small responses.
        if (
            response.status_code < 200
            or response.status_code >= 300
            or response.direct_passthrough
            or not _is_compressible(response)
        ):
            return response

        data = response.get_data()
        if len(data) < _MIN_COMPRESS_BYTES:
            # Still add ETag for small JSON payloads.
            if response.content_type and "json" in response.content_type:
                etag = _etag_for(data)
                response.headers["ETag"] = etag
                if request.headers.get("If-None-Match") == etag:
                    return Response(status=304)
            return response

        # ETag (computed on uncompressed body).
        etag = _etag_for(data)
        response.headers["ETag"] = etag
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        # Compress.
        encoding = _preferred_encoding()
        if encoding is None:
            return response

        if encoding == "br":
            compressed = _compress_brotli(data)
        else:
            compressed = _compress_gzip(data)

        # Only use compressed version if it's actually smaller.
        if len(compressed) >= len(data):
            return response

        response.set_data(compressed)
        response.headers["Content-Encoding"] = encoding
        response.headers["Content-Length"] = len(compressed)
        response.headers["Vary"] = "Accept-Encoding"
        return response
