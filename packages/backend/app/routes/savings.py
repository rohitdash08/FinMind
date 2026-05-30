import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.savings_opportunity import (
    dismiss_suggestion,
    generate_suggestions,
    list_suggestions,
    refresh_suggestions,
)

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("/suggestions")
@jwt_required()
def list_savings_suggestions():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    suggestions = list_suggestions(uid, limit=min(limit, 200))
    return jsonify(suggestions)


@bp.post("/suggestions/generate")
@jwt_required()
def generate_savings_suggestions():
    uid = int(get_jwt_identity())
    suggestions = generate_suggestions(uid)
    return jsonify(suggestions)


@bp.post("/suggestions/refresh")
@jwt_required()
def refresh_savings_suggestions():
    uid = int(get_jwt_identity())
    suggestions = refresh_suggestions(uid)
    return jsonify(suggestions)


@bp.post("/suggestions/<int:suggestion_id>/dismiss")
@jwt_required()
def dismiss_savings_suggestion(suggestion_id: int):
    uid = int(get_jwt_identity())
    if not dismiss_suggestion(suggestion_id, uid):
        return jsonify(error="not found"), 404
    return jsonify(message="dismissed"), 200
