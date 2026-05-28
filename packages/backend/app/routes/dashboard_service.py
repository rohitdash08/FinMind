"""Dashboard API."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.dashboard_service import DashboardService

bp = Blueprint("dashboard", __name__)

_services = {}

def _get_service(user_id: str) -> DashboardService:
    if user_id not in _services:
        _services[user_id] = DashboardService()
    return _services[user_id]


@bp.get("/")
@jwt_required()
def get_dashboard():
    """Full dashboard data."""
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    # In production, fetch from DB
    return jsonify(service.get_dashboard(
        transactions=[],
        budgets={},
        goals=[],
    ))


@bp.get("/quick")
@jwt_required()
def quick_summary():
    """Quick summary for widgets."""
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_quick_summary([]))


@bp.get("/alerts")
@jwt_required()
def get_alerts():
    """Financial alerts."""
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"alerts": service.get_alerts([], {})})
