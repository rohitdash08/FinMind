"""Guided monthly financial review routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.monthly_review import (
    get_review,
    get_review_step,
    get_available_months,
)

bp = Blueprint("monthly_review", __name__)


@bp.get("/<int:year>/<int:month>")
@jwt_required()
def review_route(year, month):
    """Get complete monthly financial review."""
    user_id = int(get_jwt_identity())
    if month < 1 or month > 12:
        return jsonify({"error": "Invalid month"}), 400
    result = get_review(user_id, year, month)
    return jsonify(result), 200


@bp.get("/<int:year>/<int:month>/step/<int:step>")
@jwt_required()
def review_step_route(year, month, step):
    """Get a single review step."""
    user_id = int(get_jwt_identity())
    if month < 1 or month > 12:
        return jsonify({"error": "Invalid month"}), 400
    result = get_review_step(user_id, year, month, step)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 200


@bp.get("/months")
@jwt_required()
def available_months_route():
    """Get months with available data for review."""
    user_id = int(get_jwt_identity())
    result = get_available_months(user_id)
    return jsonify(result), 200
