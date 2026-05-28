"""Emergency Fund API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.emergency_fund import EmergencyFundService

bp = Blueprint("emergency_fund", __name__)

svc = EmergencyFundService()


@bp.post("/recommended")
@jwt_required()
def recommended():
    data = request.get_json() or {}
    return jsonify(svc.calculate_recommended(
        monthly_expenses=float(data.get("monthly_expenses", 0)),
        monthly_income=float(data.get("monthly_income", 0)),
        dependents=int(data.get("dependents", 0)),
        job_stability=data.get("job_stability", "medium"),
        has_insurance=data.get("has_insurance", True),
    ))


@bp.post("/progress")
@jwt_required()
def progress():
    data = request.get_json() or {}
    return jsonify(svc.track_progress(
        current_savings=float(data.get("current_savings", 0)),
        monthly_expenses=float(data.get("monthly_expenses", 0)),
        monthly_income=float(data.get("monthly_income", 0)),
        monthly_contribution=data.get("monthly_contribution", type=float),
    ))


@bp.post("/savings-plan")
@jwt_required()
def savings_plan():
    data = request.get_json() or {}
    return jsonify(svc.savings_plan(
        target_amount=float(data.get("target_amount", 0)),
        current_savings=float(data.get("current_savings", 0)),
        timeframe_months=int(data.get("timeframe_months", 12)),
        monthly_income=float(data.get("monthly_income", 0)),
        monthly_expenses=float(data.get("monthly_expenses", 0)),
    ))


@bp.post("/scenario")
@jwt_required()
def scenario():
    data = request.get_json() or {}
    return jsonify(svc.scenario_analysis(
        monthly_expenses=float(data.get("monthly_expenses", 0)),
        emergency_fund=float(data.get("emergency_fund", 0)),
        scenario=data.get("scenario", "job_loss"),
    ))
