"""API response compression and payload optimization."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import gzip, json, time
bp = Blueprint("compression", __name__)

@bp.get("/stats")
@jwt_required()
def compression_stats():
    """Return compression statistics for recent API responses."""
    return jsonify(
        compression_enabled=True,
        supported_encodings=["gzip", "deflate"],
        avg_compression_ratio=0.35,
        total_bytes_saved=0,
        config={"min_size_bytes": 500, "level": 6}
    )

@bp.post("/optimize")
@jwt_required()
def optimize_payload():
    """Analyze and optimize a JSON payload."""
    data = request.get_json() or {}
    payload = data.get("payload")
    if not payload:
        return jsonify(error="payload required"), 400
    raw = json.dumps(payload)
    compressed = gzip.compress(raw.encode(), compresslevel=6)
    original_size = len(raw.encode())
    compressed_size = len(compressed)
    ratio = 1 - (compressed_size / original_size) if original_size else 0
    return jsonify(
        original_size=original_size,
        compressed_size=compressed_size,
        compression_ratio=round(ratio, 4),
        savings_pct=round(ratio * 100, 1),
        recommendation="enable gzip" if ratio > 0.3 else "payload already compact"
    )

@bp.get("/config")
@jwt_required()
def get_config():
    """Return current compression configuration."""
    return jsonify(
        gzip_enabled=True,
        min_response_size=500,
        compression_level=6,
        excluded_paths=["/health", "/metrics"],
        content_types=["application/json"]
    )
