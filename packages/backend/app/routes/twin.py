from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digital_twin import (
    create_twin, update_twin, get_twin, list_twins, delete_twin,
    run_simulation, list_simulations, get_simulation,
    add_goal, list_goals, delete_goal,
)
import logging

bp = Blueprint("twin", __name__)
logger = logging.getLogger("finmind.twin")


@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    result = create_twin(uid, data)
    logger.info("Twin created user=%s twin=%d", uid, result["id"])
    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_all():
    uid = int(get_jwt_identity())
    result = list_twins(uid)
    return jsonify({"twins": result})


@bp.get("/<int:twin_id>")
@jwt_required()
def get(twin_id: int):
    uid = int(get_jwt_identity())
    result = get_twin(uid, twin_id)
    if not result:
        return jsonify(error="twin not found"), 404
    return jsonify(result)


@bp.put("/<int:twin_id>")
@jwt_required()
def update(twin_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    result = update_twin(uid, twin_id, data)
    if not result:
        return jsonify(error="twin not found"), 404
    return jsonify(result)


@bp.delete("/<int:twin_id>")
@jwt_required()
def delete(twin_id: int):
    uid = int(get_jwt_identity())
    if not delete_twin(uid, twin_id):
        return jsonify(error="twin not found"), 404
    return jsonify({"deleted": True})


@bp.post("/<int:twin_id>/simulate")
@jwt_required()
def simulate(twin_id: int):
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    result = run_simulation(
        uid, twin_id,
        scenario_name=body.get("scenario_name", "baseline"),
        projection_years=body.get("projection_years", 30),
        num_simulations=body.get("num_simulations", 1000),
        adjustments=body.get("adjustments"),
    )
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@bp.get("/<int:twin_id>/simulations")
@jwt_required()
def list_sims(twin_id: int):
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    result = list_simulations(uid, twin_id, limit)
    return jsonify({"simulations": result})


@bp.get("/<int:twin_id>/simulations/<int:run_id>")
@jwt_required()
def get_sim(twin_id: int, run_id: int):
    uid = int(get_jwt_identity())
    result = get_simulation(uid, run_id)
    if not result:
        return jsonify(error="simulation not found"), 404
    return jsonify(result)


@bp.post("/<int:twin_id>/goals")
@jwt_required()
def create_goal(twin_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    if "target_date" not in data:
        return jsonify(error="target_date is required"), 400
    result = add_goal(uid, twin_id, data)
    return jsonify(result), 201


@bp.get("/<int:twin_id>/goals")
@jwt_required()
def list_goals_for_twin(twin_id: int):
    uid = int(get_jwt_identity())
    result = list_goals(uid, twin_id)
    return jsonify({"goals": result})


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def remove_goal(goal_id: int):
    uid = int(get_jwt_identity())
    if not delete_goal(uid, goal_id):
        return jsonify(error="goal not found"), 404
    return jsonify({"deleted": True})
