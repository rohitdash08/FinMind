"""Merchant alias management API routes (closes #114)."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.merchant_aliases import (
    get_aliases_for_user,
    create_alias,
    delete_alias,
    resolve_merchant,
)
import logging

bp = Blueprint("merchant_aliases", __name__)
logger = logging.getLogger("finmind.merchant_aliases")


@bp.get("")
@jwt_required()
def list_aliases():
    """List all merchant aliases for the authenticated user."""
    uid = int(get_jwt_identity())
    aliases = get_aliases_for_user(uid)
    logger.info("List merchant aliases user=%s count=%s", uid, len(aliases))
    return jsonify(aliases)


@bp.post("")
@jwt_required()
def create_merchant_alias():
    """Create or update a merchant alias."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    raw_name = (data.get("raw_name") or "").strip()
    canonical_name = (data.get("canonical_name") or "").strip()

    if not raw_name or not canonical_name:
        return jsonify(error="raw_name and canonical_name are required"), 400

    try:
        alias = create_alias(uid, raw_name, canonical_name)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    logger.info(
        "Created/updated alias user=%s raw=%r canonical=%r", uid, raw_name, canonical_name
    )
    return jsonify(alias), 201


@bp.delete("/<int:alias_id>")
@jwt_required()
def delete_merchant_alias(alias_id: int):
    """Delete a merchant alias."""
    uid = int(get_jwt_identity())
    deleted = delete_alias(uid, alias_id)
    if not deleted:
        return jsonify(error="Alias not found"), 404
    logger.info("Deleted alias id=%s user=%s", alias_id, uid)
    return jsonify(status="deleted")


@bp.get("/resolve")
@jwt_required()
def resolve_merchant_name():
    """Resolve a raw merchant name to its canonical form."""
    uid = int(get_jwt_identity())
    raw = (request.args.get("raw_name") or "").strip()
    if not raw:
        return jsonify(error="raw_name query parameter is required"), 400
    canonical = resolve_merchant(uid, raw)
    return jsonify(raw_name=raw, canonical_name=canonical)
