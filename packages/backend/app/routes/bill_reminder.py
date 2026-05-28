"""Bill Reminder API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.bill_reminder import BillReminderService

bp = Blueprint("bill_reminder", __name__)

_services = {}

def _get_service(user_id: str) -> BillReminderService:
    if user_id not in _services:
        _services[user_id] = BillReminderService()
    return _services[user_id]


@bp.post("/")
@jwt_required()
def create_bill():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.create_bill(
        user_id=user_id,
        name=data.get("name", ""),
        amount=float(data.get("amount", 0)),
        due_date=data.get("due_date", ""),
        frequency=data.get("frequency", "monthly"),
        category=data.get("category", "utilities"),
        remind_days_before=int(data.get("remind_days_before", 3)),
        auto_pay=data.get("auto_pay", False),
        notes=data.get("notes", ""),
    ))


@bp.get("/")
@jwt_required()
def list_bills():
    user_id = str(get_jwt_identity())
    status = request.args.get("status")
    service = _get_service(user_id)
    return jsonify({"bills": service.get_all(user_id, status)})


@bp.post("/<bill_id>/pay")
@jwt_required()
def mark_paid(bill_id: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.mark_paid(
        bill_id,
        amount=float(data.get("amount", 0)) or None,
        paid_date=data.get("paid_date"),
    ))


@bp.post("/<bill_id>/snooze")
@jwt_required()
def snooze(bill_id: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.snooze(bill_id, int(data.get("days", 7))))


@bp.get("/upcoming")
@jwt_required()
def get_upcoming():
    user_id = str(get_jwt_identity())
    days = int(request.args.get("days", 30))
    service = _get_service(user_id)
    return jsonify({"upcoming": service.get_upcoming(user_id, days)})


@bp.get("/overdue")
@jwt_required()
def get_overdue():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"overdue": service.get_overdue(user_id)})


@bp.get("/calendar")
@jwt_required()
def get_calendar():
    user_id = str(get_jwt_identity())
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    service = _get_service(user_id)
    return jsonify(service.get_calendar(user_id, month, year))


@bp.get("/summary")
@jwt_required()
def get_summary():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_summary(user_id))
