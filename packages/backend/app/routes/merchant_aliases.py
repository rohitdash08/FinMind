from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.merchant_aliases import (
    create_alias,
    get_aliases,
    update_alias,
    delete_alias,
    suggest_aliases,
    merge_aliases,
)
import logging

bp = Blueprint("merchant_aliases", __name__)
logger = logging.getLogger("finmind.merchant_aliases")


@bp.get("")
@jwt_required()
def list_aliases():
    uid = int(get_jwt_identity())
    return jsonify(get_aliases(uid))


@bp.post("")
@jwt_required()
def add_alias():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    canonical = (data.get("canonical_name") or "").strip()
    alias = (data.get("alias") or "").strip()
    if not canonical or not alias:
        return jsonify(error="canonical_name and alias required"), 400
    result = create_alias(uid, canonical, alias)
    if "error" in result:
        return jsonify(error=result["error"]), 409
    return jsonify(result), 201


@bp.patch("/<int:alias_id>")
@jwt_required()
def edit_alias(alias_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    canonical = (data.get("canonical_name") or "").strip()
    if not canonical:
        return jsonify(error="canonical_name required"), 400
    result = update_alias(uid, alias_id, canonical)
    if not result:
        return jsonify(error="not found"), 404
    return jsonify(result)


@bp.delete("/<int:alias_id>")
@jwt_required()
def remove_alias(alias_id: int):
    uid = int(get_jwt_identity())
    if not delete_alias(uid, alias_id):
        return jsonify(error="not found"), 404
    return jsonify(message="deleted")


@bp.get("/suggest")
@jwt_required()
def suggest():
    uid = int(get_jwt_identity())
    return jsonify(suggest_aliases(uid))


@bp.post("/merge")
@jwt_required()
def merge():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    source_id = data.get("source_id")
    target_id = data.get("target_id")
    if not source_id or not target_id:
        return jsonify(error="source_id and target_id required"), 400
    result = merge_aliases(uid, int(source_id), int(target_id))
    if not result:
        return jsonify(error="not found"), 404
    return jsonify(result)
