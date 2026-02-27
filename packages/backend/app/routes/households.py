"""Household collaborative budgeting API endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.households import (
    create_household, get_user_households, get_household,
    add_member, remove_member, set_budget, get_budget_summary, delete_household,
)
import logging

bp = Blueprint("households", __name__)
logger = logging.getLogger("finmind.households")


@bp.get("/")
@jwt_required()
def list_households():
    uid = int(get_jwt_identity())
    return jsonify(get_user_households(uid))


@bp.post("/")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    h = create_household(uid, data["name"])
    logger.info("Household created user=%s name=%s", uid, data["name"])
    return jsonify(h), 201


@bp.get("/<int:hid>")
@jwt_required()
def get_one(hid):
    uid = int(get_jwt_identity())
    h = get_household(uid, hid)
    if not h:
        return jsonify({"error": "Household not found or access denied"}), 404
    return jsonify(h)


@bp.post("/<int:hid>/members")
@jwt_required()
def invite_member(hid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("email"):
        return jsonify({"error": "email is required"}), 400
    result = add_member(uid, hid, data["email"])
    if not result:
        return jsonify({"error": "Household not found, not owner, or user not found"}), 404
    logger.info("Member added household=%s email=%s", hid, data["email"])
    return jsonify(result)


@bp.delete("/<int:hid>/members/<int:member_uid>")
@jwt_required()
def kick_member(hid, member_uid):
    uid = int(get_jwt_identity())
    if remove_member(uid, hid, member_uid):
        return jsonify({"message": "Member removed"})
    return jsonify({"error": "Cannot remove member"}), 400


@bp.post("/<int:hid>/budgets")
@jwt_required()
def set_budget_endpoint(hid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("category_name") or not data.get("monthly_limit"):
        return jsonify({"error": "category_name and monthly_limit are required"}), 400
    try:
        result = set_budget(uid, hid, data["category_name"], data["monthly_limit"], data.get("month"))
        if not result:
            return jsonify({"error": "Household not found or access denied"}), 404
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:hid>/budgets")
@jwt_required()
def budget_summary(hid):
    uid = int(get_jwt_identity())
    month = request.args.get("month")
    result = get_budget_summary(uid, hid, month)
    if not result:
        return jsonify({"error": "Household not found or access denied"}), 404
    return jsonify(result)


@bp.delete("/<int:hid>")
@jwt_required()
def delete(hid):
    uid = int(get_jwt_identity())
    if delete_household(uid, hid):
        return jsonify({"message": "Household deleted"})
    return jsonify({"error": "Not found or not owner"}), 404
