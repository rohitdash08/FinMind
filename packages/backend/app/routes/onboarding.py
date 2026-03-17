"""
Smart Onboarding Wizard routes (Issue #101).

Endpoints:
  GET  /onboarding/steps            → list all steps
  GET  /onboarding/steps/<step>     → get step definition
  POST /onboarding/validate/<step>  → validate answers for a step
  POST /onboarding/complete         → finalise setup (create categories, return budget plan)
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.onboarding import (
    STEPS,
    complete_onboarding,
    get_step,
    validate_step_answers,
)

bp = Blueprint("onboarding", __name__)
logger = logging.getLogger("finmind.onboarding_routes")


@bp.get("/steps")
@jwt_required()
def list_steps():
    """Return the ordered list of all onboarding step names."""
    return jsonify({"steps": STEPS, "total": len(STEPS)})


@bp.get("/steps/<step_name>")
@jwt_required()
def get_step_def(step_name: str):
    """Return the full definition (fields, options) for a single step."""
    step = get_step(step_name)
    if not step:
        return jsonify(error=f"Unknown step '{step_name}'. Valid steps: {STEPS}"), 404
    return jsonify(step)


@bp.post("/validate/<step_name>")
@jwt_required()
def validate_step(step_name: str):
    """
    Validate the user's answers for a single step without persisting anything.

    Request body: {answers: {field_key: value, ...}}
    Response: {valid: bool, errors: [...]}
    """
    data    = request.get_json(silent=True) or {}
    answers = data.get("answers") or {}

    if not isinstance(answers, dict):
        return jsonify(error="'answers' must be an object"), 400

    errors = validate_step_answers(step_name, answers)
    return jsonify({"valid": len(errors) == 0, "errors": errors})


@bp.post("/complete")
@jwt_required()
def complete():
    """
    Finalise the onboarding wizard.

    Validates all steps, creates the selected categories in the DB,
    and returns a personalised budget plan + actionable tips.

    Request body:
        answers (dict, required):
            profile:       {income_range, housing, dependents}
            goals:         {primary_goals: [...]}
            spending:      {categories: [...]}
            budget_method: {method}

    Response:
        status, categories_created, budget_recommendation, tips, next_steps, completed_at
    """
    uid  = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    answers = data.get("answers")
    if not isinstance(answers, dict):
        return jsonify(error="'answers' must be an object with step keys"), 400

    # Validate required steps
    required_steps = ["profile", "goals", "spending", "budget_method"]
    all_errors: dict[str, list] = {}
    for step in required_steps:
        step_answers = answers.get(step, {})
        errs = validate_step_answers(step, step_answers)
        if errs:
            all_errors[step] = errs

    if all_errors:
        return jsonify(error="validation failed", details=all_errors), 400

    result = complete_onboarding(uid, answers)
    return jsonify(result), 201
