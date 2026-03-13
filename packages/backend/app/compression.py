"""
API response compression & payload optimization (Issue #129).

Provides gzip compression for JSON/text responses via Flask after_request hook.
Uses Python's built-in gzip — no extra dependencies required.

Features:
- Gzip when client sends Accept-Encoding: gzip
- Skips compression for small responses (< MIN_SIZE bytes)
- Skips already-encoded responses
- Skips non-compressible content types (images, binary)
- Tracks compression ratio in X-Compression-Ratio header (dev/debug)
"""

from __future__ import annotations

import gzip
import logging

from flask import Flask, Request, Response

logger = logging.getLogger("finmind.compression")

# Minimum payload size (bytes) before we bother compressing
MIN_COMPRESS_SIZE = 512

# Content types that benefit from compression
_COMPRESSIBLE = {
    "application/json",
    "text/html",
    "text/plain",
    "text/csv",
    "application/javascript",
    "text/javascript",
    "application/xml",
    "text/xml",
}


def init_compression(app: Flask) -> None:
    """Register the compression after_request hook with the Flask app."""

    @app.after_request
    def compress_response(response: Response) -> Response:
        return _maybe_compress(response)

    logger.info("Response compression enabled (min_size=%d bytes)", MIN_COMPRESS_SIZE)


def _maybe_compress(response: Response) -> Response:
    # Already compressed or explicitly opted out
    if response.headers.get("Content-Encoding"):
        return response

    # Client must accept gzip
    from flask import request as current_request
    accept_encoding = current_request.headers.get("Accept-Encoding", "")
    if "gzip" not in accept_encoding.lower():
        return response

    # Only compress compressible content types
    content_type = response.content_type.split(";")[0].strip()
    if content_type not in _COMPRESSIBLE:
        return response

    # Get response data (force evaluation of lazy responses)
    data = response.get_data()

    # Skip tiny payloads — compression overhead isn't worth it
    if len(data) < MIN_COMPRESS_SIZE:
        return response

    compressed = gzip.compress(data, compresslevel=6)

    # Only use compressed version if it's actually smaller
    if len(compressed) >= len(data):
        return response

    ratio = round(1 - len(compressed) / len(data), 3)
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = len(compressed)
    response.headers["Vary"] = "Accept-Encoding"
    # Debug header (remove in prod if desired)
    response.headers["X-Compression-Ratio"] = str(ratio)

    return response
