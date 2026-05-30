import json
import zipfile
import io
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db, redis_client
from ..models import User, Expense, Bill, Category, Reminder, RecurringExpense, AuditLog
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


@bp.get("/export")
@jwt_required()
def export_user_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    _log_audit(uid, "DATA_EXPORT_REQUESTED")

    try:
        package = _build_export_package(user)
    except Exception:
        logger.exception("Export package generation failed user=%s", uid)
        _log_audit(uid, "DATA_EXPORT_FAILED")
        return jsonify(error="export generation failed"), 500

    _log_audit(uid, "DATA_EXPORT_COMPLETED")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("profile.json", json.dumps(package["profile"], indent=2, default=str))
        zf.writestr("expenses.json", json.dumps(package["expenses"], indent=2, default=str))
        zf.writestr("bills.json", json.dumps(package["bills"], indent=2, default=str))
        zf.writestr("categories.json", json.dumps(package["categories"], indent=2, default=str))
        zf.writestr("reminders.json", json.dumps(package["reminders"], indent=2, default=str))
        zf.writestr("recurring_expenses.json", json.dumps(package["recurring_expenses"], indent=2, default=str))
        zf.writestr("audit_log.json", json.dumps(package["audit_log"], indent=2, default=str))
        zf.writestr("manifest.json", json.dumps(package["manifest"], indent=2, default=str))
    buf.seek(0)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"finmind_data_export_{uid}_{timestamp}.zip"

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@bp.delete("/delete")
@jwt_required()
def delete_user_data():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    confirmation = str(data.get("confirmation") or "").strip()

    if confirmation != "DELETE_MY_DATA":
        return jsonify(error="confirmation required: send {\"confirmation\": \"DELETE_MY_DATA\"}"), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    _log_audit(uid, "DATA_DELETION_REQUESTED")

    try:
        _irreversible_delete(uid)
    except Exception:
        logger.exception("Data deletion failed user=%s", uid)
        db.session.rollback()
        _log_audit(uid, "DATA_DELETION_FAILED")
        return jsonify(error="deletion failed"), 500

    _log_audit(uid, "DATA_DELETION_COMPLETED")
    db.session.commit()

    _purge_user_cache(uid)

    return jsonify(message="all user data permanently deleted"), 200


@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    uid = int(get_jwt_identity())
    logs = (
        db.session.query(AuditLog)
        .filter_by(user_id=uid)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([
        {
            "id": log.id,
            "action": log.action,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ])


def _build_export_package(user: User) -> dict:
    uid = user.id
    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
    }

    expenses = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat(),
            "category_id": e.category_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in db.session.query(Expense).filter_by(user_id=uid).all()
    ]

    bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay_enabled": b.autopay_enabled,
            "channel_email": b.channel_email,
            "channel_whatsapp": b.channel_whatsapp,
            "active": b.active,
            "created_at": b.created_at.isoformat(),
        }
        for b in db.session.query(Bill).filter_by(user_id=uid).all()
    ]

    categories = [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at.isoformat(),
        }
        for c in db.session.query(Category).filter_by(user_id=uid).all()
    ]

    reminders = [
        {
            "id": r.id,
            "message": r.message,
            "send_at": r.send_at.isoformat(),
            "sent": r.sent,
            "channel": r.channel,
        }
        for r in db.session.query(Reminder).filter_by(user_id=uid).all()
    ]

    recurring_expenses = [
        {
            "id": re.id,
            "amount": float(re.amount),
            "currency": re.currency,
            "expense_type": re.expense_type,
            "notes": re.notes,
            "cadence": re.cadence.value,
            "start_date": re.start_date.isoformat(),
            "end_date": re.end_date.isoformat() if re.end_date else None,
            "active": re.active,
            "created_at": re.created_at.isoformat(),
        }
        for re in db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    ]

    audit_entries = [
        {
            "id": a.id,
            "action": a.action,
            "created_at": a.created_at.isoformat(),
        }
        for a in db.session.query(AuditLog).filter_by(user_id=uid).all()
    ]

    manifest = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "user_id": uid,
        "schema_version": "1.0",
        "counts": {
            "expenses": len(expenses),
            "bills": len(bills),
            "categories": len(categories),
            "reminders": len(reminders),
            "recurring_expenses": len(recurring_expenses),
            "audit_entries": len(audit_entries),
        },
    }

    return {
        "profile": profile,
        "expenses": expenses,
        "bills": bills,
        "categories": categories,
        "reminders": reminders,
        "recurring_expenses": recurring_expenses,
        "audit_log": audit_entries,
        "manifest": manifest,
    }


def _irreversible_delete(uid: int):
    db.session.query(Reminder).filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.query(Expense).filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.query(Bill).filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.query(Category).filter_by(user_id=uid).delete(synchronize_session=False)

    user = db.session.get(User, uid)
    if user:
        db.session.delete(user)


def _purge_user_cache(uid: int):
    try:
        patterns = [
            f"user:{uid}:*",
            f"insights:{uid}:*",
            f"digest:{uid}:*",
            f"auth:refresh:*",
        ]
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        logger.warning("Cache purge failed for user=%s", uid)


def _log_audit(uid: int, action: str):
    log = AuditLog(user_id=uid, action=action)
    db.session.add(log)
    db.session.commit()
