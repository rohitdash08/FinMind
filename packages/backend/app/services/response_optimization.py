"""HTTP response compression and payload optimization helpers."""

from __future__ import annotations

import gzip
from flask import request
from werkzeug.wrappers import Response

COMPRESSIBLE_TYPES = (
    "application/json",
    "application/javascript",
    "application/xml",
    "text/",
)
MIN_COMPRESS_SIZE_BYTES = 500


def optimize_response(response: Response) -> Response:
    """Apply safe response optimizations without changing endpoint code.

    The helper is intentionally conservative: it only gzips final, non-streamed,
    successful text/JSON/XML/JS responses when the client advertises gzip support
    and the compressed body is actually smaller.
    """
    _set_payload_hints(response)

    if not _should_compress(response):
        return response

    body = response.get_data()
    if len(body) < MIN_COMPRESS_SIZE_BYTES:
        return response

    compressed = gzip.compress(body, compresslevel=6, mtime=0)
    if len(compressed) >= len(body):
        return response

    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    response.headers["X-Original-Content-Length"] = str(len(body))
    response.headers["X-Compression-Ratio"] = f"{len(compressed) / len(body):.3f}"
    response.headers.add("Vary", "Accept-Encoding")
    response.headers.pop("ETag", None)
    return response


def _set_payload_hints(response: Response) -> None:
    """Tell shared/client caches which responses may vary by encoding."""
    if _is_compressible_mimetype(response.mimetype):
        response.headers.add("Vary", "Accept-Encoding")


def _should_compress(response: Response) -> bool:
    if request.method == "HEAD":
        return False
    if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
        return False
    if response.direct_passthrough or response.is_streamed:
        return False
    if response.status_code < 200 or response.status_code in {204, 304}:
        return False
    if response.headers.get("Content-Encoding"):
        return False
    if not _is_compressible_mimetype(response.mimetype):
        return False
    return True


def _is_compressible_mimetype(mimetype: str | None) -> bool:
    if not mimetype:
        return False
    return mimetype.startswith(COMPRESSIBLE_TYPES) or mimetype in COMPRESSIBLE_TYPES
