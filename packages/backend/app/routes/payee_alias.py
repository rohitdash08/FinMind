from flask import Blueprint, request, jsonify, g
from ..services.payee_alias import PayeeAliasService
from ..middleware.auth import require_auth

payee_alias_bp = Blueprint("payee_alias", __name__)
svc = PayeeAliasService()

@payee_alias_bp.route("/api/payees/aliases", methods=["GET"])
@require_auth
def list_aliases():
    """List all custom payee aliases for the user."""
    user_id = g.user_id
    aliases = svc.list_aliases(user_id)
    return jsonify({"aliases": aliases, "count": len(aliases)})

@payee_alias_bp.route("/api/payees/aliases", methods=["POST"])
@require_auth
def create_alias():
    """Create or update a custom alias for a payee."""
    user_id = g.user_id
    data = request.get_json() or {}
    raw_name = data.get("raw_name", "").strip()
    alias = data.get("alias", "").strip()
    if not raw_name or not alias:
        return jsonify({"error": "raw_name and alias are required"}), 400
    record = svc.set_alias(user_id, raw_name, alias)
    return jsonify(record), 201

@payee_alias_bp.route("/api/payees/aliases/<canonical>", methods=["DELETE"])
@require_auth
def delete_alias(canonical):
    """Delete a custom alias by canonical name."""
    user_id = g.user_id
    success = svc.delete_alias(user_id, canonical)
    if not success:
        return jsonify({"error": "alias not found"}), 404
    return jsonify({"deleted": True, "canonical": canonical})

@payee_alias_bp.route("/api/payees/normalize", methods=["POST"])
@require_auth
def normalize_payees():
    """Bulk normalize raw merchant names to display names."""
    user_id = g.user_id
    data = request.get_json() or {}
    raw_names = data.get("raw_names", [])
    if not isinstance(raw_names, list):
        return jsonify({"error": "raw_names must be a list"}), 400
    results = svc.bulk_normalize(user_id, raw_names)
    return jsonify({"results": results})

@payee_alias_bp.route("/api/payees/suggestions", methods=["POST"])
@require_auth
def suggest_aliases():
    """Get alias suggestions for a list of raw merchant names."""
    user_id = g.user_id
    data = request.get_json() or {}
    raw_names = data.get("raw_names", [])
    suggestions = svc.suggest_aliases(user_id, raw_names)
    return jsonify({"suggestions": suggestions, "count": len(suggestions)})