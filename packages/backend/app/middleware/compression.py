"""
API response compression & payload optimization (issue #129).
- gzip via flask-compress on all JSON > 1KB
- Field filtering: ?fields=id,name strips unwanted keys
- Slim mode: ?slim=1 strips null values
- Pagination helper with metadata
"""
import json, logging
from flask import request, Response

logger = logging.getLogger("finmind.compression")


def init_compression(app):
    try:
        from flask_compress import Compress
        Compress(app)
        app.config.setdefault("COMPRESS_MIMETYPES", ["application/json", "text/plain"])
        app.config.setdefault("COMPRESS_MIN_SIZE", 1024)
        app.config.setdefault("COMPRESS_LEVEL", 6)
        logger.info("flask-compress enabled")
    except ImportError:
        logger.warning("flask-compress not installed — gzip disabled")


def filter_fields(data, fields_param: str):
    if not fields_param:
        return data
    wanted = {f.strip() for f in fields_param.split(",") if f.strip()}
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in wanted}
    if isinstance(data, list):
        return [filter_fields(i, fields_param) for i in data]
    return data


def strip_nulls(data):
    if isinstance(data, dict):
        return {k: strip_nulls(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [strip_nulls(i) for i in data]
    return data


def paginate(query, default_limit=50, max_limit=200):
    try:
        limit = min(int(request.args.get("limit", default_limit)), max_limit)
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        limit, offset = default_limit, 0
    total = query.count()
    items = query.limit(limit).offset(offset).all()
    return items, {"total": total, "limit": limit, "offset": offset,
                   "has_more": (offset + limit) < total}


def optimized_json(data) -> Response:
    fields = request.args.get("fields", "")
    slim = request.args.get("slim", "0") == "1"
    if fields:
        data = filter_fields(data, fields)
    if slim:
        data = strip_nulls(data)
    return Response(json.dumps(data), mimetype="application/json")
