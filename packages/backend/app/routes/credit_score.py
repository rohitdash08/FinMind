"""Credit Score API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.credit_score import CreditScoreService

bp = Blueprint("credit_score", __name__)

_services = {}

def _get_service(user_id: str) -> CreditScoreService:
    if user_id not in _services:
        _services[user_id] = CreditScoreService()
    return _services[user_id]


@bp.post("/score")
@jwt_required()
def add_score():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.add_score(
        user_id=user_id,
        score=int(data.get("score", 0)),
        source=data.get("source", "manual"),
        date=data.get("date"),
    ))


@bp.get("/history")
@jwt_required()
def get_history():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    limit = request.args.get("limit", 12, type=int)
    return jsonify(service.get_history(user_id, limit))


@bp.post("/simulate")
@jwt_required()
def simulate():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.simulate(
        user_id=user_id,
        current_score=int(data.get("current_score", 700)),
        actions=data.get("actions", []),
    ))


@bp.get("/factors")
@jwt_required()
def get_factors():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    score = request.args.get("score", type=int)
    return jsonify(service.get_factor_breakdown(user_id, score))


@bp.post("/improvement-plan")
@jwt_required()
def improvement_plan():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.get_improvement_plan(
        user_id,
        current_score=data.get("current_score", type=int),
        target_score=int(data.get("target_score", 750)),
    ))


@bp.post("/utilization")
@jwt_required()
def calculate_utilization():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.calculate_utilization(
        balances=data.get("balances", []),
        limits=data.get("limits", []),
    ))
