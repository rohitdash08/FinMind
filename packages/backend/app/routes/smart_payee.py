"""Smart payee & merchant alias management routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.smart_payee import (
    create_merchant,
    get_merchant,
    list_merchants,
    update_merchant,
    delete_merchant,
    add_alias,
    remove_alias,
    list_aliases,
    merge_merchants,
    match_merchant,
    suggest_duplicates,
)

bp = Blueprint("smart_payee", __name__)


# ── Merchant CRUD ─────────────────────────────────────────────────


@bp.get("")
@jwt_required()
def list_merchants_route():
    """List merchants with optional search and filtering."""
    user_id = int(get_jwt_identity())
    search = request.args.get("search")
    category_id = request.args.get("category_id", type=int)
    sort_by = request.args.get("sort", "name")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    result = list_merchants(user_id, search=search, category_id=category_id,
                            sort_by=sort_by, limit=limit, offset=offset)
    return jsonify(result), 200


@bp.post("")
@jwt_required()
def create_merchant_route():
    """Create a new merchant."""
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400

    try:
        result = create_merchant(
            user_id=user_id,
            name=data["name"],
            category_id=data.get("category_id"),
            default_currency=data.get("default_currency", "INR"),
            notes=data.get("notes"),
        )
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@bp.get("/<int:merchant_id>")
@jwt_required()
def get_merchant_route(merchant_id):
    """Get a single merchant."""
    user_id = int(get_jwt_identity())
    result = get_merchant(user_id, merchant_id)
    if not result:
        return jsonify({"error": "Merchant not found"}), 404
    return jsonify(result), 200


@bp.put("/<int:merchant_id>")
@jwt_required()
def update_merchant_route(merchant_id):
    """Update a merchant."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    result = update_merchant(user_id, merchant_id, **data)
    if not result:
        return jsonify({"error": "Merchant not found"}), 404
    return jsonify(result), 200


@bp.delete("/<int:merchant_id>")
@jwt_required()
def delete_merchant_route(merchant_id):
    """Delete a merchant."""
    user_id = int(get_jwt_identity())
    if delete_merchant(user_id, merchant_id):
        return jsonify({"message": "Deleted"}), 200
    return jsonify({"error": "Merchant not found"}), 404


# ── Alias Management ─────────────────────────────────────────────


@bp.get("/<int:merchant_id>/aliases")
@jwt_required()
def list_aliases_route(merchant_id):
    """List aliases for a merchant."""
    user_id = int(get_jwt_identity())
    aliases = list_aliases(user_id, merchant_id)
    return jsonify({"aliases": aliases}), 200


@bp.post("/<int:merchant_id>/aliases")
@jwt_required()
def add_alias_route(merchant_id):
    """Add an alias to a merchant."""
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("alias"):
        return jsonify({"error": "Alias is required"}), 400

    try:
        result = add_alias(user_id, merchant_id, data["alias"])
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@bp.delete("/<int:merchant_id>/aliases/<int:alias_id>")
@jwt_required()
def remove_alias_route(merchant_id, alias_id):
    """Remove an alias from a merchant."""
    user_id = int(get_jwt_identity())
    if remove_alias(user_id, merchant_id, alias_id):
        return jsonify({"message": "Deleted"}), 200
    return jsonify({"error": "Alias not found"}), 404


# ── Merge & Matching ─────────────────────────────────────────────


@bp.post("/merge")
@jwt_required()
def merge_merchants_route():
    """Merge source merchants into a target merchant."""
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("target_id") or not data.get("source_ids"):
        return jsonify({"error": "target_id and source_ids are required"}), 400

    try:
        result = merge_merchants(user_id, data["target_id"], data["source_ids"])
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.get("/match")
@jwt_required()
def match_merchant_route():
    """Find a merchant by name or alias."""
    user_id = int(get_jwt_identity())
    name = request.args.get("name", "")

    if not name:
        return jsonify({"error": "Name query parameter is required"}), 400

    result = match_merchant(user_id, name)
    if result:
        return jsonify(result), 200
    return jsonify({"message": "No match found"}), 404


@bp.get("/duplicates")
@jwt_required()
def suggest_duplicates_route():
    """Suggest potential duplicate merchants."""
    user_id = int(get_jwt_identity())
    duplicates = suggest_duplicates(user_id)
    return jsonify({"duplicates": duplicates, "total": len(duplicates)}), 200
