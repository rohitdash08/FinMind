from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.household import (
    create_household,
    generate_invite,
    accept_invite,
    get_household_members,
    household_summary,
    get_user_households,
    HouseholdMember,
)
import logging

bp = Blueprint("households", __name__)
logger = logging.getLogger("finmind.households")


def _check_membership(household_id: int, user_id: int) -> bool:
    return HouseholdMember.query.filter_by(
        household_id=household_id, user_id=user_id
    ).first() is not None


@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json()
    name = (data or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    result = create_household(uid, name)
    logger.info("Household created id=%s by user=%s", result["id"], uid)
    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_households():
    uid = int(get_jwt_identity())
    return jsonify(get_user_households(uid))


@bp.post("/<int:hid>/invite")
@jwt_required()
def invite(hid):
    uid = int(get_jwt_identity())
    if not _check_membership(hid, uid):
        return jsonify({"error": "Not a member"}), 403
    result = generate_invite(hid, uid)
    return jsonify(result), 201


@bp.post("/join")
@jwt_required()
def join():
    uid = int(get_jwt_identity())
    data = request.get_json()
    code = (data or {}).get("invite_code", "").strip()
    if not code:
        return jsonify({"error": "invite_code is required"}), 400
    try:
        result = accept_invite(uid, code)
        logger.info("User %s joined household %s", uid, result["household_id"])
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:hid>/members")
@jwt_required()
def members(hid):
    uid = int(get_jwt_identity())
    if not _check_membership(hid, uid):
        return jsonify({"error": "Not a member"}), 403
    return jsonify(get_household_members(hid))


@bp.get("/<int:hid>/summary")
@jwt_required()
def summary(hid):
    uid = int(get_jwt_identity())
    if not _check_membership(hid, uid):
        return jsonify({"error": "Not a member"}), 403
    ym = request.args.get("month")
    return jsonify(household_summary(hid, ym))
