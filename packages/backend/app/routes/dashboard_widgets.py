"""REST routes for dashboard widget customization."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.dashboard_widgets import (
    get_widget_config,
    update_widget_config,
    reset_widget_config,
    VALID_WIDGET_IDS,
)
import logging

bp = Blueprint("dashboard_widgets", __name__)
logger = logging.getLogger("finmind.dashboard_widgets")


@bp.get("")
@jwt_required()
def get_widgets():
    """GET /dashboard/widgets — Return user's widget configuration."""
    uid = int(get_jwt_identity())
    config = get_widget_config(uid)
    return jsonify({"widgets": config}), 200


@bp.patch("")
@jwt_required()
def update_widgets():
    """
    PATCH /dashboard/widgets — Update widget visibility and/or order.

    Body: {"updates": [{"id": "monthly_summary", "visible": true, "order": 0}, ...]}
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    updates = data.get("updates", [])

    if not isinstance(updates, list):
        return jsonify(error="updates must be a list"), 400

    for item in updates:
        if not isinstance(item, dict):
            return jsonify(error="each update must be an object"), 400
        if "id" not in item:
            return jsonify(error="each update must have an id field"), 400

    config = update_widget_config(uid, updates)
    logger.info("Widget config updated user=%s count=%s", uid, len(updates))
    return jsonify({"widgets": config}), 200


@bp.post("/reset")
@jwt_required()
def reset_widgets():
    """POST /dashboard/widgets/reset — Reset to default configuration."""
    uid = int(get_jwt_identity())
    config = reset_widget_config(uid)
    logger.info("Widget config reset user=%s", uid)
    return jsonify({"widgets": config}), 200


@bp.get("/available")
@jwt_required()
def list_available_widgets():
    """GET /dashboard/widgets/available — List all available widget IDs."""
    return jsonify({"widget_ids": sorted(VALID_WIDGET_IDS)}), 200