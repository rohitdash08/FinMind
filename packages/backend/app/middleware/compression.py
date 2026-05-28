"""API response compression middleware for FinMind.

Provides gzip/deflate compression with:
- Configurable minimum size threshold
- Content-type aware (only compresses JSON, HTML, text, CSV)
- Compression level tuning
- Response size metrics
"""

import gzip
import zlib
import logging
from io import BytesIO
from functools import wraps

from flask import request, Response, current_app

logger = logging.getLogger("finmind.compression")

# Content types worth compressing
COMPRESSIBLE_TYPES = {
    "application/json",
    "application/javascript",
    "text/html",
    "text/plain",
    "text/css",
    "text/csv",
    "text/xml",
    "application/xml",
}

DEFAULT_MIN_SIZE = 500       # bytes
DEFAULT_COMPRESS_LEVEL = 6   # 1-9


def should_compress(response: Response) -> bool:
    """Check if a response should be compressed."""
    # Skip if already encoded
    if response.content_encoding:
        return False

    # Check content type
    ct = response.content_type or ""
    base_ct = ct.split(";")[0].strip().lower()
    if base_ct not in COMPRESSIBLE_TYPES:
        return False

    # Check response size
    response_data = response.get_data()
    min_size = current_app.config.get("COMPRESSION_MIN_SIZE", DEFAULT_MIN_SIZE)
    if len(response_data) < min_size:
        return False

    return True


def get_client_encoding() -> str | None:
    """Get the best compression encoding supported by the client."""
    accept_encoding = request.headers.get("Accept-Encoding", "")
    encodings = [e.strip().lower() for e in accept_encoding.split(",")]

    if "gzip" in encodings:
        return "gzip"
    if "deflate" in encodings:
        return "deflate"
    return None


def compress_response(response: Response) -> Response:
    """Compress response body using gzip or deflate."""
    if not should_compress(response):
        return response

    encoding = get_client_encoding()
    if not encoding:
        return response

    data = response.get_data()
    original_size = len(data)
    level = current_app.config.get("COMPRESSION_LEVEL", DEFAULT_COMPRESS_LEVEL)

    if encoding == "gzip":
        buf = BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=level) as f:
            f.write(data)
        compressed = buf.getvalue()
    else:  # deflate
        compressed = zlib.compress(data, level)

    ratio = len(compressed) / max(original_size, 1)
    logger.debug(
        "Compressed %dB -> %dB (%.1f%%) via %s",
        original_size, len(compressed), ratio * 100, encoding,
    )

    response.set_data(compressed)
    response.content_encoding = encoding
    response.headers["Content-Length"] = len(compressed)
    response.headers["X-Compression-Ratio"] = f"{ratio:.2f}"

    return response


def init_compression(app):
    """Register compression after_request hook on the Flask app."""
    app.config.setdefault("COMPRESSION_MIN_SIZE", DEFAULT_MIN_SIZE)
    app.config.setdefault("COMPRESSION_LEVEL", DEFAULT_COMPRESS_LEVEL)

    @app.after_request
    def after_request_compress(response):
        return compress_response(response)
