"""Smart onboarding financial setup wizard API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.onboarding import (
    get_progress, advance, skip_step, reset, get_suggestions,
)

bp = Blueprint("onboarding", __name__)


@bp.get("/")
@jwt_required()
def progress():
    uid = int(get_jwt_identity())
    return jsonify(get_progress(uid))


@bp.post("/advance")
@jwt_required()
def next_step():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    return jsonify(advance(uid, data.get("step_data")))


@bp.post("/skip")
@jwt_required()
def skip():
    uid = int(get_jwt_identity())
    try:
        return jsonify(skip_step(uid))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/reset")
@jwt_required()
def restart():
    uid = int(get_jwt_identity())
    try:
        return jsonify(reset(uid))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/suggestions/<int:step>")
@jwt_required()
def suggestions(step):
    return jsonify(get_suggestions(step))
