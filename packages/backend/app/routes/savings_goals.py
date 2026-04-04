from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import SavingsGoal

bp = Blueprint("savings_goals", __name__)


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    saved = float(g.saved_amount)
    pct = round((saved / target) * 100, 1) if target > 0 else 0
    milestones = [m for m in [25, 50, 75, 100] if pct >= m]
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "saved_amount": saved,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "progress_pct": pct,
        "milestones": milestones,
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = db.session.query(SavingsGoal).filter_by(user_id=uid).order_by(SavingsGoal.created_at.desc()).all()
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    try:
        target = Decimal(str(data.get("target_amount", 0))).quantize(Decimal("0.01"))
        if target <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        return jsonify(error="invalid target_amount"), 400
    target_date = None
    if data.get("target_date"):
        try:
            target_date = date.fromisoformat(data["target_date"])
        except ValueError:
            return jsonify(error="invalid target_date"), 400
    g = SavingsGoal(user_id=uid, name=name, target_amount=target, target_date=target_date)
    db.session.add(g)
    db.session.commit()
    return jsonify(_goal_to_dict(g)), 201


@bp.put("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        g.name = (data["name"] or "").strip() or g.name
    if "target_amount" in data:
        try:
            g.target_amount = Decimal(str(data["target_amount"])).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            return jsonify(error="invalid target_amount"), 400
    if "saved_amount" in data:
        try:
            g.saved_amount = Decimal(str(data["saved_amount"])).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            return jsonify(error="invalid saved_amount"), 400
    if "target_date" in data:
        if data["target_date"]:
            try:
                g.target_date = date.fromisoformat(data["target_date"])
            except ValueError:
                return jsonify(error="invalid target_date"), 400
        else:
            g.target_date = None
    db.session.commit()
    return jsonify(_goal_to_dict(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(g)
    db.session.commit()
    return jsonify(message="deleted")
