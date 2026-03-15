"""Customizable dashboard widgets routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.dashboard_widgets import (
    get_layout,
    initialize_layout,
    reset_layout,
    toggle_visibility,
    bulk_update_visibility,
    reorder_widgets,
    update_widget_config,
    get_widget,
    get_available_widgets,
)

bp = Blueprint("dashboard_widgets", __name__)


@bp.get("")
@jwt_required()
def get_layout_route():
    """Get dashboard widget layout."""
    user_id = int(get_jwt_identity())
    result = get_layout(user_id)
    return jsonify(result), 200


@bp.post("/initialize")
@jwt_required()
def initialize_route():
    """Initialize default widget layout."""
    user_id = int(get_jwt_identity())
    result = initialize_layout(user_id)
    return jsonify(result), 201


@bp.post("/reset")
@jwt_required()
def reset_route():
    """Reset layout to defaults."""
    user_id = int(get_jwt_identity())
    result = reset_layout(user_id)
    return jsonify(result), 200


@bp.put("/<widget_key>/visibility")
@jwt_required()
def toggle_route(widget_key):
    """Toggle widget visibility."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data or "visible" not in data:
        return jsonify({"error": "visible field is required"}), 400

    result = toggle_visibility(user_id, widget_key, data["visible"])
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.put("/visibility")
@jwt_required()
def bulk_visibility_route():
    """Update visibility for multiple widgets."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    result = bulk_update_visibility(user_id, data)
    return jsonify(result), 200


@bp.put("/reorder")
@jwt_required()
def reorder_route():
    """Reorder dashboard widgets."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data or "order" not in data:
        return jsonify({"error": "order array is required"}), 400
    result = reorder_widgets(user_id, data["order"])
    return jsonify(result), 200


@bp.put("/<widget_key>/config")
@jwt_required()
def config_route(widget_key):
    """Update widget configuration."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data:
        return jsonify({"error": "No config data provided"}), 400
    result = update_widget_config(user_id, widget_key, data)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.get("/<widget_key>")
@jwt_required()
def get_widget_route(widget_key):
    """Get single widget details."""
    user_id = int(get_jwt_identity())
    result = get_widget(user_id, widget_key)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.get("/available")
@jwt_required()
def available_route():
    """List all available widget types."""
    result = get_available_widgets()
    return jsonify(result), 200
