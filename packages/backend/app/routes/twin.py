"""Personal Financial Digital Twin API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digital_twin import (
    get_profile, update_profile, get_snapshot, simulate,
    list_simulations, get_simulation, delete_simulation, SCENARIO_TYPES,
)

bp = Blueprint("twin", __name__)


@bp.get("/profile")
@jwt_required()
def profile():
    uid = int(get_jwt_identity())
    return jsonify(get_profile(uid))


@bp.put("/profile")
@jwt_required()
def update():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    return jsonify(update_profile(uid, **data))


@bp.get("/snapshot")
@jwt_required()
def snapshot():
    uid = int(get_jwt_identity())
    return jsonify(get_snapshot(uid))


@bp.get("/scenarios")
@jwt_required()
def scenarios():
    return jsonify(SCENARIO_TYPES)


@bp.post("/simulate")
@jwt_required()
def sim():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("scenario_type") or not data.get("name"):
        return jsonify({"error": "name and scenario_type required"}), 400
    try:
        result = simulate(uid, data["name"], data["scenario_type"], data.get("parameters", {}))
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/simulations")
@jwt_required()
def list_sims():
    uid = int(get_jwt_identity())
    return jsonify(list_simulations(uid))


@bp.get("/simulations/<int:sim_id>")
@jwt_required()
def get_sim(sim_id):
    uid = int(get_jwt_identity())
    s = get_simulation(uid, sim_id)
    if not s:
        return jsonify({"error": "Simulation not found"}), 404
    return jsonify(s)


@bp.delete("/simulations/<int:sim_id>")
@jwt_required()
def del_sim(sim_id):
    uid = int(get_jwt_identity())
    if delete_simulation(uid, sim_id):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Simulation not found"}), 404
