"""Routes for shared household budgeting."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.household import (
    create_household, get_household, invite_member,
    remove_member, household_summary,
)

bp = Blueprint("household", __name__)
logger = logging.getLogger("finmind.household")


@bp.post("/")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    h = create_household(uid, name)
    logger.info("Household created user=%s name=%s", uid, name)
    return jsonify(h), 201


@bp.get("/")
@jwt_required()
def show():
    uid = int(get_jwt_identity())
    h = get_household(uid)
    if not h:
        return jsonify(error="not in a household"), 404
    return jsonify(h)


@bp.post("/invite")
@jwt_required()
def invite():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify(error="email is required"), 400
    result = invite_member(uid, email)
    if result is None:
        return jsonify(error="not owner or user not found"), 400
    if "error" in result:
        return jsonify(result), 409
    return jsonify(result)


@bp.delete("/members/<int:member_user_id>")
@jwt_required()
def remove(member_user_id: int):
    uid = int(get_jwt_identity())
    if remove_member(uid, member_user_id):
        return jsonify(message="removed"), 200
    return jsonify(error="not found or not authorized"), 404


@bp.get("/summary")
@jwt_required()
def summary():
    uid = int(get_jwt_identity())
    ym = request.args.get("month")
    result = household_summary(uid, ym)
    if result is None:
        return jsonify(error="not in a household"), 404
    return jsonify(result)
