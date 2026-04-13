import json
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import AuditLog, Expense, Bill

bp = Blueprint("digital_twin", __name__)
logger = logging.getLogger("finmind.digital_twin")


@bp.post("/create")
@jwt_required()
def create_snapshot():
    uid = int(get_jwt_identity())

    total_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == uid, Expense.expense_type != "INCOME")
        .scalar()
    )
    total_income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == uid, Expense.expense_type == "INCOME")
        .scalar()
    )
    total_bills = float(
        db.session.query(func.coalesce(func.sum(Bill.amount), 0))
        .filter(Bill.user_id == uid, Bill.active.is_(True))
        .scalar()
    )

    snapshot = {
        "total_expenses": total_expenses,
        "total_income": total_income,
        "total_bills": total_bills,
        "net_worth": round(total_income - total_expenses, 2),
        "created_at": datetime.utcnow().isoformat(),
    }
    log = AuditLog(user_id=uid, action=f"digital_twin_snapshot:{json.dumps(snapshot)}")
    db.session.add(log)
    db.session.commit()
    snapshot["snapshot_id"] = log.id
    logger.info("Created digital twin snapshot user=%s", uid)
    return jsonify(snapshot), 201


@bp.get("/snapshots")
@jwt_required()
def list_snapshots():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid, AuditLog.action.like("digital_twin_snapshot:%"))
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    snapshots = []
    for r in rows:
        try:
            data = json.loads(r.action.split(":", 1)[1])
            data["snapshot_id"] = r.id
            snapshots.append(data)
        except (json.JSONDecodeError, IndexError):
            continue
    return jsonify(snapshots)


@bp.post("/simulate")
@jwt_required()
def simulate():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    snapshot_id = data.get("snapshot_id")
    adjustments = data.get("adjustments", {})
    if not snapshot_id:
        return jsonify(error="snapshot_id required"), 400

    log = db.session.query(AuditLog).filter(
        AuditLog.id == snapshot_id,
        AuditLog.user_id == uid,
        AuditLog.action.like("digital_twin_snapshot:%"),
    ).first()
    if not log:
        return jsonify(error="snapshot not found"), 404

    try:
        snapshot = json.loads(log.action.split(":", 1)[1])
    except (json.JSONDecodeError, IndexError):
        return jsonify(error="corrupt snapshot"), 500

    projected = {
        "total_income": snapshot["total_income"] + adjustments.get("income_change", 0),
        "total_expenses": snapshot["total_expenses"] + adjustments.get("expense_change", 0),
        "total_bills": snapshot["total_bills"] + adjustments.get("bills_change", 0),
    }
    projected["net_worth"] = round(projected["total_income"] - projected["total_expenses"], 2)
    projected["snapshot_id"] = snapshot_id
    projected["adjustments"] = adjustments
    logger.info("Simulated digital twin user=%s snapshot=%s", uid, snapshot_id)
    return jsonify(projected)
