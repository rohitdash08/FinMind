"""Routes for spending trend heatmap visualization."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.spending_heatmap import (
    get_daily_heatmap,
    get_weekly_heatmap,
    get_hourly_heatmap,
    get_category_heatmap,
    get_heatmap_summary,
)

bp = Blueprint("spending_heatmap", __name__)


@bp.get("/daily")
@jwt_required()
def daily():
    """Get daily spending heatmap (GitHub-style)."""
    user_id = int(get_jwt_identity())
    days = int(request.args.get("days", 365))
    category_id = request.args.get("category_id", type=int)
    result = get_daily_heatmap(user_id, days=days, category_id=category_id)
    return jsonify(result), 200


@bp.get("/weekly")
@jwt_required()
def weekly():
    """Get weekly spending heatmap."""
    user_id = int(get_jwt_identity())
    weeks = int(request.args.get("weeks", 52))
    category_id = request.args.get("category_id", type=int)
    result = get_weekly_heatmap(user_id, weeks=weeks, category_id=category_id)
    return jsonify(result), 200


@bp.get("/hourly")
@jwt_required()
def hourly():
    """Get hour-of-day × day-of-week heatmap."""
    user_id = int(get_jwt_identity())
    days = int(request.args.get("days", 30))
    category_id = request.args.get("category_id", type=int)
    result = get_hourly_heatmap(user_id, days=days, category_id=category_id)
    return jsonify(result), 200


@bp.get("/categories")
@jwt_required()
def categories():
    """Get category spending heatmap."""
    user_id = int(get_jwt_identity())
    days = int(request.args.get("days", 30))
    result = get_category_heatmap(user_id, days=days)
    return jsonify(result), 200


@bp.get("/summary")
@jwt_required()
def summary():
    """Get heatmap summary statistics."""
    user_id = int(get_jwt_identity())
    days = int(request.args.get("days", 365))
    result = get_heatmap_summary(user_id, days=days)
    return jsonify(result), 200
