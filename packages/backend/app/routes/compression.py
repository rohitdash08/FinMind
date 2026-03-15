"""Routes for API compression configuration and statistics."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.compression import (
    get_compression_stats,
    _reset_stats,
    optimize_json_payload,
    paginate_response,
    slim_response,
    DEFAULT_CONFIG,
)

bp = Blueprint("compression", __name__)


@bp.route("/stats", methods=["GET"])
@jwt_required()
def compression_stats():
    """Get compression statistics.

    Returns metrics including:
    - Total requests processed
    - Compression ratio
    - Bytes saved
    - Per-endpoint breakdown
    """
    user_id = int(get_jwt_identity())
    stats = get_compression_stats()
    return jsonify(stats), 200


@bp.route("/stats/reset", methods=["POST"])
@jwt_required()
def reset_stats():
    """Reset compression statistics."""
    user_id = int(get_jwt_identity())
    _reset_stats()
    return jsonify({"message": "Compression statistics reset"}), 200


@bp.route("/config", methods=["GET"])
@jwt_required()
def get_config():
    """Get current compression configuration."""
    user_id = int(get_jwt_identity())
    config = {
        "min_size_bytes": DEFAULT_CONFIG["min_size"],
        "compression_level": DEFAULT_CONFIG["compression_level"],
        "etag_enabled": DEFAULT_CONFIG["enable_etag"],
        "stats_enabled": DEFAULT_CONFIG["enable_stats"],
        "max_page_size": DEFAULT_CONFIG["max_page_size"],
        "default_page_size": DEFAULT_CONFIG["default_page_size"],
        "excluded_content_types": list(DEFAULT_CONFIG["excluded_content_types"]),
    }
    return jsonify(config), 200


@bp.route("/optimize", methods=["POST"])
@jwt_required()
def optimize_payload():
    """Demonstrate payload optimization.

    Accepts JSON body with:
    - data: object or array to optimize
    - fields: list of fields to keep (optional)
    - exclude_nulls: boolean (optional, default true)
    - exclude_empty: boolean (optional, default false)
    """
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}

    data = body.get("data")
    if data is None:
        return jsonify({"error": "data field is required"}), 400

    fields = body.get("fields")
    exclude_nulls = body.get("exclude_nulls", True)
    exclude_empty = body.get("exclude_empty", False)

    # Apply field selection
    optimized = optimize_json_payload(data, fields)

    # Apply null/empty removal
    if isinstance(optimized, list):
        optimized = [slim_response(item, exclude_nulls, exclude_empty)
                     if isinstance(item, dict) else item
                     for item in optimized]
    elif isinstance(optimized, dict):
        optimized = slim_response(optimized, exclude_nulls, exclude_empty)

    # Calculate size reduction
    import json
    original_size = len(json.dumps(data))
    optimized_size = len(json.dumps(optimized))
    reduction = round(1 - (optimized_size / original_size), 4) if original_size > 0 else 0

    return jsonify({
        "optimized": optimized,
        "metrics": {
            "original_size": original_size,
            "optimized_size": optimized_size,
            "reduction_ratio": reduction,
            "bytes_saved": original_size - optimized_size,
        },
    }), 200


@bp.route("/paginate", methods=["POST"])
@jwt_required()
def paginate_endpoint():
    """Demonstrate pagination optimization.

    Accepts JSON body with:
    - items: array of items
    - page: page number (default 1)
    - page_size: items per page (default 20)
    """
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}

    items = body.get("items")
    if items is None or not isinstance(items, list):
        return jsonify({"error": "items array is required"}), 400

    page = body.get("page", 1)
    page_size = body.get("page_size", 20)

    result = paginate_response(items, page, page_size)
    return jsonify(result), 200
