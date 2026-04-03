"""Routes for Keyboard Shortcuts Management (issue #106)."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.keyboard_shortcuts import (
    get_all_shortcuts,
    get_shortcuts_by_category,
    get_user_shortcut_config,
    update_shortcut,
    reset_shortcut,
    reset_all_shortcuts,
    DEFAULT_SHORTCUTS,
)

bp = Blueprint("keyboard_shortcuts", __name__)


@bp.route("/keyboard-shortcuts", methods=["GET"])
def list_shortcuts():
    """List all available keyboard shortcuts (public)."""
    by_category = request.args.get("by_category", "false").lower() == "true"
    if by_category:
        return jsonify(get_shortcuts_by_category()), 200
    return jsonify({"shortcuts": get_all_shortcuts(), "count": len(DEFAULT_SHORTCUTS)}), 200


@bp.route("/keyboard-shortcuts/user", methods=["GET"])
@jwt_required()
def get_user_shortcuts():
    """Get resolved shortcuts for the current user (merged defaults + custom)."""
    user_id = int(get_jwt_identity())
    config = get_user_shortcut_config(user_id)
    return jsonify({"shortcuts": config, "count": len(config)}), 200


@bp.route("/keyboard-shortcuts/user/<string:action>", methods=["PUT"])
@jwt_required()
def set_shortcut(action: str):
    """Set a custom keybinding for an action."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    custom_key = (data.get("key") or "").strip()
    if not custom_key:
        return jsonify({"error": "key is required"}), 400

    enabled = bool(data.get("enabled", True))
    result = update_shortcut(user_id, action, custom_key, enabled)
    if result is None:
        return jsonify({"error": f"Unknown action: {action}"}), 404
    if "error" in result:
        return jsonify(result), 409  # Conflict

    return jsonify(result), 200


@bp.route("/keyboard-shortcuts/user/<string:action>", methods=["DELETE"])
@jwt_required()
def reset_shortcut_route(action: str):
    """Reset a shortcut to its default keybinding."""
    user_id = int(get_jwt_identity())
    result = reset_shortcut(user_id, action)
    if result is None:
        return jsonify({"error": f"Unknown action: {action}"}), 404
    return jsonify(result), 200


@bp.route("/keyboard-shortcuts/user/reset-all", methods=["POST"])
@jwt_required()
def reset_all_route():
    """Reset all shortcuts to defaults."""
    user_id = int(get_jwt_identity())
    count = reset_all_shortcuts(user_id)
    return jsonify({"message": f"Reset {count} custom shortcut(s) to defaults", "count": count}), 200