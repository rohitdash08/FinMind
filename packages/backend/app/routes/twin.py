from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.digital_twin import (
    build_snapshot,
    project_deterministic,
    project_monte_carlo,
    stress_test,
    track_goals,
    generate_recommendations,
)

twin_bp = Blueprint("twin", __name__, url_prefix="/twin")


@twin_bp.route("/snapshot", methods=["GET"])
@jwt_required()
def snapshot():
    """GET /twin/snapshot?months=3 - Full financial snapshot."""
    uid = int(get_jwt_identity())
    months = int(request.args.get("months", 3))
    snap = build_snapshot(uid, months)
    recs = generate_recommendations(snap)
    snap.goals = []
    d = snap.to_dict()
    d["recommendations"] = recs
    return jsonify(d), 200


@twin_bp.route("/project", methods=["GET"])
@jwt_required()
def project():
    """GET /twin/project?months=24&mode=deterministic|monte_carlo - Forward projection."""
    uid = int(get_jwt_identity())
    months = int(request.args.get("months", 24))
    mode = request.args.get("mode", "deterministic")
    if months < 1 or months > 120:
        return jsonify({"error": "months must be 1-120"}), 400
    snap = build_snapshot(uid)
    if mode == "monte_carlo":
        sims = int(request.args.get("simulations", 500))
        result = project_monte_carlo(snap, months, min(sims, 1000))
    else:
        result = {"mode": "deterministic", "projection": project_deterministic(snap, months)}
    return jsonify(result), 200


@twin_bp.route("/stress", methods=["POST"])
@jwt_required()
def stress():
    """
    POST /twin/stress
    Body: { scenario: "job_loss"|"medical_emergency"|... or {custom params}, months: int }
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario")
    if not scenario:
        return jsonify({"error": "scenario required (preset name or custom dict)"}), 400
    months = int(body.get("months", 24))
    try:
        snap = build_snapshot(uid)
        result = stress_test(snap, scenario, months)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@twin_bp.route("/goals", methods=["POST"])
@jwt_required()
def goals():
    """
    POST /twin/goals
    Body: { goals: [{type, target_amount, current_amount?, label?}, ...] }
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    goal_list = body.get("goals")
    if not goal_list or not isinstance(goal_list, list):
        return jsonify({"error": "goals must be a non-empty list"}), 400
    snap = build_snapshot(uid)
    results = track_goals(snap, goal_list)
    return jsonify({"goals": results, "monthly_surplus": round(snap.monthly_surplus, 2)}), 200


@twin_bp.route("/recommendations", methods=["GET"])
@jwt_required()
def recommendations():
    """GET /twin/recommendations - Get ranked next-best-action list."""
    uid = int(get_jwt_identity())
    snap = build_snapshot(uid)
    recs = generate_recommendations(snap)
    return jsonify({"count": len(recs), "recommendations": recs}), 200
