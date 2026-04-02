"""API response compression middleware.

Implements gzip and deflate compression for API responses to reduce
payload sizes and improve response times.  Large JSON payloads from
endpoints like ``/expenses``, ``/dashboard``, and ``/insights`` benefit
the most — typical compression ratios are 60-80 % for JSON.

Configuration (via environment / Settings):
    COMPRESS_MIN_SIZE   – minimum response bytes before compressing (default 256)
    COMPRESS_LEVEL      – gzip compression level 1-9 (default 6)

The module provides two integration paths:
    1. ``init_compression(app)`` – uses flask-compress when installed.
    2. ``GzipMiddleware``        – pure-WSGI fallback that works without
       any extra dependency.

Either path respects the ``Accept-Encoding`` header and sets
``Content-Encoding`` / ``Vary`` accordingly.
"""

from __future__ import annotations

import gzip
import io
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger("finmind.compression")

# ---------------------------------------------------------------------------
# Default tunables
# ---------------------------------------------------------------------------
DEFAULT_MIN_SIZE = 256  # bytes
DEFAULT_LEVEL = 6       # gzip level (1=fast … 9=best)

# MIME types worth compressing (others pass through untouched)
COMPRESSIBLE_TYPES = frozenset(
    {
        "application/json",
        "text/html",
        "text/plain",
        "text/css",
        "application/javascript",
        "text/javascript",
        "application/xml",
        "text/xml",
        "image/svg+xml",
    }
)


def init_compression(app: "Flask") -> None:
    """Attach response compression to *app*.

    Tries ``flask-compress`` first (richer feature set, brotli support).
    Falls back to a lightweight WSGI middleware when the package is absent.
    """
    min_size = app.config.get("COMPRESS_MIN_SIZE", DEFAULT_MIN_SIZE)
    level = app.config.get("COMPRESS_LEVEL", DEFAULT_LEVEL)

    try:
        from flask_compress import Compress  # type: ignore[import-untyped]

        app.config.setdefault("COMPRESS_MIMETYPES", list(COMPRESSIBLE_TYPES))
        app.config.setdefault("COMPRESS_MIN_SIZE", min_size)
        app.config.setdefault("COMPRESS_LEVEL", level)
        Compress(app)
        logger.info(
            "Response compression enabled (flask-compress, min_size=%s, level=%s)",
            min_size,
            level,
        )
    except ImportError:
        app.wsgi_app = GzipMiddleware(  # type: ignore[assignment]
            app.wsgi_app,
            min_size=min_size,
            level=level,
        )
        logger.info(
            "Response compression enabled (WSGI gzip fallback, min_size=%s, level=%s)",
            min_size,
            level,
        )


# ---------------------------------------------------------------------------
# Pure-WSGI gzip middleware (zero extra dependencies)
# ---------------------------------------------------------------------------

class GzipMiddleware:
    """WSGI middleware that gzip-compresses responses when beneficial.

    Respects ``Accept-Encoding``, skips small / non-compressible bodies,
    and sets the correct ``Content-Encoding`` + ``Vary`` headers.
    """

    def __init__(self, app, *, min_size: int = DEFAULT_MIN_SIZE, level: int = DEFAULT_LEVEL):
        self.app = app
        self.min_size = min_size
        self.level = level

    def __call__(self, environ, start_response):
        accept = environ.get("HTTP_ACCEPT_ENCODING", "")
        if "gzip" not in accept:
            return self.app(environ, start_response)

        # Collect the response produced by the inner app
        response_started: list = []
        body_chunks: list[bytes] = []

        def buffered_start(status, headers, exc_info=None):
            response_started.append((status, headers, exc_info))

        app_iter = self.app(environ, buffered_start)
        try:
            for chunk in app_iter:
                body_chunks.append(chunk)
        finally:
            if hasattr(app_iter, "close"):
                app_iter.close()

        if not response_started:
            return []

        status, headers, exc_info = response_started[0]
        header_dict = {k.lower(): v for k, v in headers}

        # Decide whether to compress
        content_type = header_dict.get("content-type", "")
        mime = content_type.split(";")[0].strip().lower()

        body = b"".join(body_chunks)

        if mime not in COMPRESSIBLE_TYPES or len(body) < self.min_size:
            write_fn = start_response(status, headers, exc_info)
            return [body]

        # Compress
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=self.level) as gz:
            gz.write(body)
        compressed = buf.getvalue()

        # Only use compressed version if it's actually smaller
        if len(compressed) >= len(body):
            write_fn = start_response(status, headers, exc_info)
            return [body]

        # Rewrite headers
        new_headers = [
            (k, v)
            for k, v in headers
            if k.lower() not in ("content-length", "content-encoding")
        ]
        new_headers.append(("Content-Encoding", "gzip"))
        new_headers.append(("Content-Length", str(len(compressed))))
        new_headers.append(("Vary", "Accept-Encoding"))

        start_response(status, new_headers, exc_info)
        return [compressed]
