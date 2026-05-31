from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.heatmap import (
    daily_spending,
    weekly_spending,
    monthly_spending,
    category_heatmap,
    spending_density,
)
import logging

bp = Blueprint("heatmap", __name__)
logger = logging.getLogger("finmind.heatmap")


@bp.get("/daily")
@jwt_required()
def daily():
    uid = int(get_jwt_identity())
    year = int(request.args.get("year", date.today().year))
    month = request.args.get("month")
    month = int(month) if month else None
    return jsonify(daily_spending(uid, year, month))


@bp.get("/weekly")
@jwt_required()
def weekly():
    uid = int(get_jwt_identity())
    year = int(request.args.get("year", date.today().year))
    return jsonify(weekly_spending(uid, year))


@bp.get("/monthly")
@jwt_required()
def monthly():
    uid = int(get_jwt_identity())
    year = int(request.args.get("year", date.today().year))
    return jsonify(monthly_spending(uid, year))


@bp.get("/by-category")
@jwt_required()
def by_category():
    uid = int(get_jwt_identity())
    year = int(request.args.get("year", date.today().year))
    return jsonify(category_heatmap(uid, year))


@bp.get("/density")
@jwt_required()
def density():
    uid = int(get_jwt_identity())
    year = int(request.args.get("year", date.today().year))
    return jsonify(spending_density(uid, year))
