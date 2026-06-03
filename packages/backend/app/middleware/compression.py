
"""
API response compression middleware for FinMind.
Reduces payload size for large financial data responses.
"""
import gzip
import json
from functools import wraps
from flask import request, make_response


def compress_response(min_size=500):
    """Decorator to compress response bodies above min_size bytes."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            response = make_response(f(*args, **kwargs))
            data = response.get_data()
            
            if len(data) < min_size:
                return response
            
            accept = request.headers.get("Accept-Encoding", "")
            
            if "gzip" in accept:
                compressed = gzip.compress(data)
                response.set_data(compressed)
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Content-Length"] = len(compressed)
                response.headers["Vary"] = "Accept-Encoding"
            
            return response
        return decorated
    return decorator
