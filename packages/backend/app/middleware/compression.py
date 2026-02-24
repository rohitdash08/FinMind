"""
compression.py — ETag-based conditional response middleware.

Wraps after_request to attach ETag headers and honour If-None-Match,
complementing Flask-Compress's gzip layer.
"""
from flask import request, Response
import hashlib


def add_etag_support(response: Response) -> Response:
    """
    After-request hook: attach ETag to JSON responses and return 304
    when the client's If-None-Match matches.

    Only applied to 200 OK JSON responses that are not streaming.
    """
    if (
        response.status_code == 200
        and response.content_type.startswith("application/json")
        and not response.is_streamed
    ):
        data = response.get_data()
        etag = hashlib.md5(data).hexdigest()
        response.set_etag(etag)

        if_none_match = request.headers.get("If-None-Match", "")
        if if_none_match and etag in if_none_match:
            response.status_code = 304
            response.set_data(b"")

    return response
