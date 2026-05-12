"""API response compression and payload optimization middleware."""

import gzip
from flask import Flask, request


def init_compression(app: Flask, min_size: int = 500):
    """Add gzip compression to responses larger than min_size bytes.

    Compresses JSON responses when client sends Accept-Encoding: gzip.
    """

    @app.after_request
    def compress_response(response):
        # Skip if client doesn't accept gzip
        if "gzip" not in request.headers.get("Accept-Encoding", ""):
            return response

        # Skip small responses
        if response.content_length and response.content_length < min_size:
            return response

        # Skip non-JSON or already encoded
        if (
            response.status_code < 200
            or response.status_code >= 300
            or "Content-Encoding" in response.headers
            or not response.content_type.startswith("application/json")
        ):
            return response

        data = response.get_data()
        if len(data) < min_size:
            return response

        compressed = gzip.compress(data, compresslevel=6)

        # Only use compression if it actually reduces size
        if len(compressed) >= len(data):
            return response

        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = len(compressed)
        response.headers["Vary"] = "Accept-Encoding"

        return response
