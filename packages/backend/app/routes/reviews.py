"""Guided monthly financial review API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.monthly_review import (
    start_review, get_review, get_step_data, advance_step,
    set_action_items, list_reviews,
)

bp = Blueprint("reviews", __name__)


@bp.get("/")
@jwt_required()
def list_all():
    uid = int(get_jwt_identity())
    return jsonify(list_reviews(uid))


@bp.post("/start")
@jwt_required()
def start():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    year = data.get("year", 2026)
    month = data.get("month", 1)
    return jsonify(start_review(uid, year, month)), 201


@bp.get("/<int:year>/<int:month>")
@jwt_required()
def get_one(year, month):
    uid = int(get_jwt_identity())
    r = get_review(uid, year, month)
    if not r:
        return jsonify({"error": "Review not found"}), 404
    return jsonify(r)


@bp.get("/<int:year>/<int:month>/step/<int:step>")
@jwt_required()
def step_data(year, month, step):
    uid = int(get_jwt_identity())
    try:
        return jsonify(get_step_data(uid, year, month, step))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/<int:year>/<int:month>/advance")
@jwt_required()
def advance(year, month):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        return jsonify(advance_step(uid, year, month, data.get("notes", "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.put("/<int:year>/<int:month>/actions")
@jwt_required()
def actions(year, month):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        return jsonify(set_action_items(uid, year, month, data.get("items", "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
