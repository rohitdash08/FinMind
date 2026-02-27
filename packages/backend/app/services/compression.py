"""API response compression & payload optimization.

Middleware for gzip/deflate compression, field selection,
pagination helpers, and response size tracking.
"""

import gzip
import io
import json
import time
from functools import wraps
from flask import request, make_response, g, jsonify
from ..extensions import db


class ResponseMetric(db.Model):
    __tablename__ = "response_metrics"
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    original_size = db.Column(db.Integer, default=0)
    compressed_size = db.Column(db.Integer, default=0)
    compression_ratio = db.Column(db.Float, default=1.0)
    duration_ms = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


def init_compression(app):
    """Register compression middleware on the Flask app."""

    @app.before_request
    def _before():
        g.request_start = time.time()

    @app.after_request
    def _compress(response):
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if response.direct_passthrough:
            return response

        content_type = response.content_type or ""
        if "application/json" not in content_type and "text/" not in content_type:
            return response

        # Field selection
        fields = request.args.get("fields")
        if fields and "application/json" in content_type:
            response = _apply_field_selection(response, fields)

        # Compression
        accept = request.headers.get("Accept-Encoding", "")
        original_size = len(response.get_data())

        if original_size < 500:  # skip small responses
            return response

        if "gzip" in accept:
            response = _gzip_response(response)
        elif "deflate" in accept:
            response = _deflate_response(response)

        compressed_size = len(response.get_data())

        # Track metrics (best effort)
        try:
            duration = int((time.time() - g.get("request_start", time.time())) * 1000)
            metric = ResponseMetric(
                endpoint=request.path, method=request.method,
                status_code=response.status_code,
                original_size=original_size, compressed_size=compressed_size,
                compression_ratio=round(compressed_size / original_size, 3) if original_size > 0 else 1.0,
                duration_ms=duration,
            )
            db.session.add(metric)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return response


def _gzip_response(response):
    data = response.get_data()
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as f:
        f.write(data)
    compressed = buf.getvalue()

    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = len(compressed)
    response.headers["Vary"] = "Accept-Encoding"
    return response


def _deflate_response(response):
    import zlib
    data = response.get_data()
    compressed = zlib.compress(data, 6)

    response.set_data(compressed)
    response.headers["Content-Encoding"] = "deflate"
    response.headers["Content-Length"] = len(compressed)
    response.headers["Vary"] = "Accept-Encoding"
    return response


def _apply_field_selection(response, fields_str):
    """Filter JSON response to only include requested fields."""
    try:
        data = response.get_json()
        if data is None:
            return response

        field_list = [f.strip() for f in fields_str.split(",")]

        if isinstance(data, list):
            filtered = [{k: v for k, v in item.items() if k in field_list}
                        for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            filtered = {k: v for k, v in data.items() if k in field_list}
        else:
            return response

        response.set_data(json.dumps(filtered))
        return response
    except Exception:
        return response


def paginate(query, page: int = 1, per_page: int = 20, max_per_page: int = 100):
    """Helper for consistent pagination."""
    per_page = min(per_page, max_per_page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "has_next": page * per_page < total,
        "has_prev": page > 1,
    }


def get_compression_stats(limit: int = 100) -> dict:
    from sqlalchemy import func
    metrics = ResponseMetric.query.order_by(ResponseMetric.created_at.desc()).limit(limit).all()

    if not metrics:
        return {"total_requests": 0, "avg_compression_ratio": 1.0,
                "total_saved_bytes": 0, "endpoints": []}

    total_original = sum(m.original_size for m in metrics)
    total_compressed = sum(m.compressed_size for m in metrics)
    avg_ratio = total_compressed / total_original if total_original > 0 else 1.0

    # Per-endpoint stats
    endpoint_stats = (
        db.session.query(
            ResponseMetric.endpoint,
            func.count(ResponseMetric.id),
            func.avg(ResponseMetric.compression_ratio),
            func.avg(ResponseMetric.duration_ms),
        ).group_by(ResponseMetric.endpoint).limit(20).all()
    )

    return {
        "total_requests": len(metrics),
        "avg_compression_ratio": round(avg_ratio, 3),
        "total_saved_bytes": total_original - total_compressed,
        "endpoints": [
            {"endpoint": ep, "requests": cnt, "avg_ratio": round(float(ratio), 3),
             "avg_duration_ms": round(float(dur), 1)}
            for ep, cnt, ratio, dur in endpoint_stats
        ],
    }
