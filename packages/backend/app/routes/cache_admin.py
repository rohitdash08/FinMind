"""Cache administration endpoints for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import User
from ..services.smart_cache import cache
from flask_jwt_extended import get_jwt_identity

bp = Blueprint("cache_admin", __name__)


@bp.get("/metrics")
@jwt_required()
def get_metrics():
    """Get cache performance metrics (admin only)."""
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="Admin access required"), 403

    namespace = request.args.get("namespace", "")
    if namespace:
        return jsonify(cache.get_metrics(namespace))

    # Return metrics for known namespaces
    namespaces = ["dashboard", "analytics", "expenses", "heatmap", "insights"]
    return jsonify([cache.get_metrics(ns) for ns in namespaces])


@bp.delete("/invalidate")
@jwt_required()
def invalidate():
    """Invalidate cache by tag or namespace (admin only)."""
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="Admin access required"), 403

    tag = request.args.get("tag")
    namespace = request.args.get("namespace")

    if tag:
        count = cache.invalidate_tag(tag)
        return jsonify(invalidated=count, method="tag", tag=tag)
    elif namespace:
        count = cache.invalidate_namespace(namespace)
        return jsonify(invalidated=count, method="namespace", namespace=namespace)
    else:
        return jsonify(error="Provide tag or namespace parameter"), 400
