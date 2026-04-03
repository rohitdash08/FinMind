"""REST routes for smart onboarding financial setup wizard."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.onboarding_wizard import (
    get_wizard_status,
    submit_step,
    reset_wizard,
    VALID_GOALS,
    VALID_LIFESTYLES,
)
import logging

bp = Blueprint("onboarding", __name__)
logger = logging.getLogger("finmind.onboarding")


@bp.get("/status")
@jwt_required()
def wizard_status():
    """GET /onboarding/status — Return current wizard state."""
    uid = int(get_jwt_identity())
    status = get_wizard_status(uid)
    return jsonify(status), 200


@bp.post("/step/<step>")
@jwt_required()
def wizard_step(step: str):
    """
    POST /onboarding/step/<step> — Submit data for a wizard step.

    Steps: goals, income, lifestyle, categories
    """
    uid = int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}

    try:
        result = submit_step(uid, step, payload)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    logger.info("Wizard step submitted user=%s step=%s", uid, step)
    return jsonify(result), 200


@bp.post("/reset")
@jwt_required()
def wizard_reset():
    """POST /onboarding/reset — Reset wizard to initial state."""
    uid = int(get_jwt_identity())
    result = reset_wizard(uid)
    logger.info("Wizard reset user=%s", uid)
    return jsonify(result), 200


@bp.get("/options")
@jwt_required()
def wizard_options():
    """GET /onboarding/options — List valid goals and lifestyles."""
    return jsonify({
        "goals": sorted(VALID_GOALS),
        "lifestyles": sorted(VALID_LIFESTYLES),
    }), 200