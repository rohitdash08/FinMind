"""API response compression and payload optimization middleware."""

import gzip
import json
from io import BytesIO
from flask import Flask, request, Response
from functools import wraps


def init_compression(app: Flask, minimum_size: int = 500, compression_level: int = 6):
    """Initialize gzip compression for API responses.

    Args:
        app: Flask application instance.
        minimum_size: Minimum response size in bytes to compress.
        compression_level: Gzip compression level (1-9).
    """

    @app.after_request
    def compress_response(response: Response) -> Response:
        # Skip if client doesn't accept gzip
        if "gzip" not in request.headers.get("Accept-Encoding", ""):
            return response

        # Skip non-JSON and small responses
        if response.content_type and "application/json" not in response.content_type:
            return response

        if (
            response.status_code < 200
            or response.status_code >= 300
            or response.direct_passthrough
        ):
            return response

        data = response.get_data()
        if len(data) < minimum_size:
            return response

        # Compress
        buf = BytesIO()
        with gzip.GzipFile(
            fileobj=buf, mode="wb", compresslevel=compression_level
        ) as f:
            f.write(data)

        compressed = buf.getvalue()

        # Only use compressed if actually smaller
        if len(compressed) >= len(data):
            return response

        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = len(compressed)
        response.headers["Vary"] = "Accept-Encoding"

        return response

    return app


def slim_response(fields=None, exclude=None):
    """Decorator to optimize JSON payload by selecting/excluding fields.

    Usage:
        @slim_response(fields=['id', 'name', 'amount'])
        def get_items(): ...

        @slim_response(exclude=['internal_notes', 'debug_info'])
        def get_details(): ...
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            result = f(*args, **kwargs)

            # Support ?fields=id,name,amount query param override
            query_fields = request.args.get("fields")
            if query_fields:
                active_fields = set(query_fields.split(","))
            elif fields:
                active_fields = set(fields)
            else:
                active_fields = None

            active_exclude = set(exclude) if exclude else set()

            if isinstance(result, tuple):
                data, status = result[0], result[1] if len(result) > 1 else 200
            else:
                data, status = result, 200

            if isinstance(data, Response):
                return result

            data = _filter_payload(data, active_fields, active_exclude)
            return data, status

        return wrapper

    return decorator


def _filter_payload(data, fields, exclude):
    """Filter dict or list of dicts by field selection."""
    if isinstance(data, dict):
        return _filter_dict(data, fields, exclude)
    elif isinstance(data, list):
        return [_filter_dict(item, fields, exclude) for item in data if isinstance(item, dict)]
    return data


def _filter_dict(d, fields, exclude):
    """Filter a single dict."""
    if not isinstance(d, dict):
        return d
    result = {}
    for k, v in d.items():
        if fields and k not in fields:
            continue
        if k in exclude:
            continue
        result[k] = v
    return result


def add_pagination_headers(response: Response, page: int, per_page: int, total: int):
    """Add standard pagination headers to reduce payload metadata."""
    response.headers["X-Page"] = str(page)
    response.headers["X-Per-Page"] = str(per_page)
    response.headers["X-Total"] = str(total)
    response.headers["X-Total-Pages"] = str((total + per_page - 1) // per_page)
    return response
