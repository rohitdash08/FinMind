from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from ..services.response_compression import (
    measure_compression,
    optimize_payload,
    strip_null_fields,
    filter_fields,
)

bp = Blueprint("response_compression", __name__)


@bp.route("/compression/analyze", methods=["POST"])
@jwt_required()
def analyze_compression():
    """
    POST /insights/compression/analyze
    Body: any JSON payload
    Returns compression stats for gzip and deflate on the submitted payload.
    """
    body = request.get_json(silent=True) or {}
    payload_bytes = json.dumps(body).encode("utf-8")
    stats = measure_compression(payload_bytes)
    return jsonify(stats)


@bp.route("/compression/optimize", methods=["POST"])
@jwt_required()
def optimize():
    """
    POST /insights/compression/optimize
    Body: { "data": {...}, "strip_nulls": true, "fields": ["id", "name"] }
    Returns optimized payload.
    """
    body = request.get_json(silent=True) or {}
    data = body.get("data", {})
    strip_nulls = bool(body.get("strip_nulls", True))
    fields = body.get("fields", None)

    original_bytes = len(json.dumps(data).encode("utf-8"))
    optimized = optimize_payload(data, fields=fields, strip_nulls=strip_nulls)
    optimized_bytes = len(json.dumps(optimized).encode("utf-8"))

    return jsonify({
        "original_bytes": original_bytes,
        "optimized_bytes": optimized_bytes,
        "savings_pct": round((1 - optimized_bytes / original_bytes) * 100, 1) if original_bytes else 0,
        "data": optimized,
    })