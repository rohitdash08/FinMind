"""Smart payee & merchant alias API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.merchant_alias import (
    set_alias, get_aliases, delete_alias, suggest_merges,
    bulk_set_aliases, merchant_summary,
)
import logging

bp = Blueprint("merchants", __name__)
logger = logging.getLogger("finmind.merchants")


@bp.get("/aliases")
@jwt_required()
def list_aliases():
    uid = int(get_jwt_identity())
    return jsonify(get_aliases(uid))


@bp.post("/aliases")
@jwt_required()
def create_alias():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("raw_name") or not data.get("display_name"):
        return jsonify({"error": "raw_name and display_name are required"}), 400
    try:
        alias = set_alias(uid, data["raw_name"], data["display_name"])
        logger.info("Alias set user=%s raw=%s display=%s", uid, data["raw_name"], data["display_name"])
        return jsonify(alias), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/aliases/bulk")
@jwt_required()
def bulk_aliases():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not isinstance(data.get("aliases"), list):
        return jsonify({"error": "aliases array is required"}), 400
    results = bulk_set_aliases(uid, data["aliases"])
    return jsonify(results), 201


@bp.delete("/aliases/<int:alias_id>")
@jwt_required()
def remove_alias(alias_id):
    uid = int(get_jwt_identity())
    if delete_alias(uid, alias_id):
        return jsonify({"message": "Alias deleted"})
    return jsonify({"error": "Alias not found"}), 404


@bp.get("/suggest-merges")
@jwt_required()
def get_suggestions():
    uid = int(get_jwt_identity())
    threshold = float(request.args.get("threshold", 0.7))
    return jsonify(suggest_merges(uid, threshold))


@bp.get("/summary")
@jwt_required()
def get_summary():
    uid = int(get_jwt_identity())
    return jsonify(merchant_summary(uid))
