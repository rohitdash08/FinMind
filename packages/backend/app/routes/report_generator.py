"""Report Generator API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.report_generator import ReportGeneratorService

bp = Blueprint("report_generator", __name__)

_services = {}

def _get_service(user_id: str) -> ReportGeneratorService:
    if user_id not in _services:
        _services[user_id] = ReportGeneratorService()
    return _services[user_id]


@bp.post("/generate")
@jwt_required()
def generate_report():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.generate_report(
        user_id=user_id,
        report_type=data.get("report_type", "summary"),
        period=data.get("period", "monthly"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
    ))


@bp.post("/transactions")
@jwt_required()
def add_transaction():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.add_transaction(
        user_id=user_id,
        amount=float(data.get("amount", 0)),
        category=data.get("category", ""),
        date=data.get("date", ""),
        t_type=data.get("type", "expense"),
        description=data.get("description", ""),
    ))


@bp.post("/budget")
@jwt_required()
def set_budget():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    service.set_budget(
        user_id,
        data.get("category", ""),
        float(data.get("amount", 0)),
    )
    return jsonify({"status": "ok"})


@bp.get("/<report_id>")
@jwt_required()
def get_report(report_id: str):
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_report(report_id))


@bp.get("/")
@jwt_required()
def list_reports():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"reports": service.get_all_reports(user_id)})
