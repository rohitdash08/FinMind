import json
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog

bp = Blueprint("widgets", __name__)
logger = logging.getLogger("finmind.widgets")

AVAILABLE_WIDGETS = [
    {"widget_id": "expense_summary", "name": "Expense Summary", "description": "Overview of monthly expenses by category"},
    {"widget_id": "income_tracker", "name": "Income Tracker", "description": "Track income sources and totals"},
    {"widget_id": "bill_calendar", "name": "Bill Calendar", "description": "Upcoming bills and due dates"},
    {"widget_id": "savings_goal", "name": "Savings Goal", "description": "Progress toward savings targets"},
    {"widget_id": "recent_transactions", "name": "Recent Transactions", "description": "Latest expense and income entries"},
    {"widget_id": "budget_meter", "name": "Budget Meter", "description": "Budget utilization gauge"},
]


@bp.get("")
@jwt_required()
def get_layout():
    uid = int(get_jwt_identity())
    log = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid, AuditLog.action.like("widget_layout:%"))
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if not log:
        return jsonify([])
    try:
        layout = json.loads(log.action.split(":", 1)[1])
        return jsonify(layout)
    except (json.JSONDecodeError, IndexError):
        return jsonify([])


@bp.post("")
@jwt_required()
def save_layout():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify(error="expected array of widget layout items"), 400

    for item in data:
        if not isinstance(item, dict) or "widget_id" not in item:
            return jsonify(error="each item must have widget_id"), 400

    log = AuditLog(user_id=uid, action=f"widget_layout:{json.dumps(data)}")
    db.session.add(log)
    db.session.commit()
    logger.info("Saved widget layout user=%s widgets=%s", uid, len(data))
    return jsonify(data), 201


@bp.get("/available")
@jwt_required()
def available_widgets():
    return jsonify(AVAILABLE_WIDGETS)
