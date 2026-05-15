from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    User, Category, Expense, RecurringExpense,
    Bill, Reminder, AdImpression, UserSubscription, AuditLog,
)
from ..services.privacy import export_user_data, delete_user_data
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


@bp.get("/export")
@jwt_required()
def export_pii():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    data = export_user_data(user)

    db.session.add(AuditLog(user_id=uid, action="pii.export"))
    db.session.commit()
    logger.info("PII export requested user_id=%s", uid)

    return jsonify(data), 200


@bp.delete("/delete")
@jwt_required()
def delete_pii():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Require explicit confirmation
    data = request.get_json() or {}
    confirm = data.get("confirm")
    if confirm != "DELETE_MY_DATA":
        return jsonify(error="confirmation required: send {\"confirm\": \"DELETE_MY_DATA\"}"), 400

    delete_user_data(uid)

    db.session.add(AuditLog(user_id=None, action="pii.delete", ))
    db.session.commit()
    logger.info("PII deletion completed user_id=%s", uid)

    return jsonify(message="all personal data deleted"), 200