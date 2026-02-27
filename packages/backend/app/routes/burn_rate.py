"""Spending velocity & burn rate API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.burn_rate import (
    analyze_burn_rate, budget_runway, category_velocity, weekly_comparison,
)
import logging

bp = Blueprint("burn_rate", __name__)
logger = logging.getLogger("finmind.burn_rate")


@bp.get("/")
@jwt_required()
def get_burn_rate():
    uid = int(get_jwt_identity())
    days = int(request.args.get("days", 30))
    return jsonify(analyze_burn_rate(uid, days))


@bp.get("/runway")
@jwt_required()
def get_runway():
    uid = int(get_jwt_identity())
    budget = request.args.get("budget")
    if not budget:
        return jsonify({"error": "budget query param is required"}), 400
    days = int(request.args.get("days", 30))
    return jsonify(budget_runway(uid, float(budget), days))


@bp.get("/categories")
@jwt_required()
def get_category_velocity():
    uid = int(get_jwt_identity())
    days = int(request.args.get("days", 30))
    return jsonify(category_velocity(uid, days))


@bp.get("/weekly")
@jwt_required()
def get_weekly():
    uid = int(get_jwt_identity())
    weeks = int(request.args.get("weeks", 4))
    return jsonify(weekly_comparison(uid, weeks))
