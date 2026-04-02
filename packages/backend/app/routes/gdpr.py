from flask import Blueprint, request, jsonify, g, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from ..extensions import db
from ..models import (
    User, Category, Expense, RecurringExpense, Bill, 
    Reminder, AdImpression, UserSubscription, AuditLog, DeletionRequest
)
import logging
import json
import io
import zipfile

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")

# Grace period in days before permanent deletion
GRACE_PERIOD_DAYS = 30



def _log_audit(user_id: int, action: str, details: dict = None, ip_address: str = None, user_agent: str = None):
    """Log an audit trail entry for GDPR actions."""
    audit = AuditLog(
        user_id=user_id,
        action=action,
    )
    db.session.add(audit)
    db.session.commit()
    log_details = {
        "user_id": user_id,
        "action": action,
        "details": details or {},
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": datetime.utcnow().isoformat(),
    }
    logger.info("GDPR Audit: %s", json.dumps(log_details))
    return audit


def _get_request_metadata():
    """Extract IP address and user agent from request."""
    ip_address = request.remote_addr
    if request.headers.get("X-Forwarded-For"):
        ip_address = request.headers.get("X-Forwarded-For").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    return ip_address, user_agent



def _collect_user_pii(user_id: int) -> dict:
    """Collect all PII for a user across all tables."""
    user = db.session.get(User, user_id)
    if not user:
        return None

    data = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": [],
        "expenses": [],
        "recurring_expenses": [],
        "bills": [],
        "reminders": [],
        "ad_impressions": [],
        "subscriptions": [],
    }

    for cat in db.session.query(Category).filter_by(user_id=user_id).all():
        data["categories"].append({
            "id": cat.id, "name": cat.name,
            "created_at": cat.created_at.isoformat() if cat.created_at else None,
        })

    for exp in db.session.query(Expense).filter_by(user_id=user_id).all():
        data["expenses"].append({
            "id": exp.id, "category_id": exp.category_id,
            "amount": str(exp.amount), "currency": exp.currency,
            "expense_type": exp.expense_type, "notes": exp.notes,
            "spent_at": exp.spent_at.isoformat() if exp.spent_at else None,
            "source_recurring_id": exp.source_recurring_id,
            "created_at": exp.created_at.isoformat() if exp.created_at else None,
        })

    for rec in db.session.query(RecurringExpense).filter_by(user_id=user_id).all():
        data["recurring_expenses"].append({
            "id": rec.id, "category_id": rec.category_id,
            "amount": str(rec.amount), "currency": rec.currency,
            "expense_type": rec.expense_type, "notes": rec.notes,
            "cadence": rec.cadence.value if rec.cadence else None,
            "start_date": rec.start_date.isoformat() if rec.start_date else None,
            "end_date": rec.end_date.isoformat() if rec.end_date else None,
            "active": rec.active,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })

    for bill in db.session.query(Bill).filter_by(user_id=user_id).all():
        data["bills"].append({
            "id": bill.id, "name": bill.name, "amount": str(bill.amount),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat() if bill.next_due_date else None,
            "cadence": bill.cadence.value if bill.cadence else None,
            "autopay_enabled": bill.autopay_enabled,
            "channel_whatsapp": bill.channel_whatsapp, "channel_email": bill.channel_email,
            "active": bill.active,
            "created_at": bill.created_at.isoformat() if bill.created_at else None,
        })

    for rem in db.session.query(Reminder).filter_by(user_id=user_id).all():
        data["reminders"].append({
            "id": rem.id, "bill_id": rem.bill_id, "message": rem.message,
            "send_at": rem.send_at.isoformat() if rem.send_at else None,
            "sent": rem.sent, "channel": rem.channel,
        })

    for ad in db.session.query(AdImpression).filter_by(user_id=user_id).all():
        data["ad_impressions"].append({
            "id": ad.id, "placement": ad.placement,
            "created_at": ad.created_at.isoformat() if ad.created_at else None,
        })

    for sub in db.session.query(UserSubscription).filter_by(user_id=user_id).all():
        data["subscriptions"].append({
            "id": sub.id, "plan_id": sub.plan_id, "active": sub.active,
            "started_at": sub.started_at.isoformat() if sub.started_at else None,
        })

    return data



@bp.get("/export")
@jwt_required()
def export_user_data():
    """Export all user data in GDPR-compliant format. Returns a ZIP file."""
    uid = int(get_jwt_identity())
    ip_address, user_agent = _get_request_metadata()
    
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404
    
    data = _collect_user_pii(uid)
    if not data:
        return jsonify(error="failed to collect user data"), 500
    
    _log_audit(
        user_id=uid,
        action="GDPR_EXPORT",
        details={"format": "json", "records_exported": sum([
            len(data["categories"]), len(data["expenses"]),
            len(data["recurring_expenses"]), len(data["bills"]),
            len(data["reminders"]), len(data["ad_impressions"]),
            len(data["subscriptions"]),
        ])},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        export_json = json.dumps(data, indent=2, default=str)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        zf.writestr(f"user_data_{uid}_{timestamp}.json", export_json)
        readme = f"""FinMind GDPR Data Export
========================
User ID: {uid}
Export Date: {data["export_timestamp"]}
This archive contains all personal data stored by FinMind.
Password hashes are not included for security reasons.
To request deletion, use DELETE /gdpr/delete endpoint.
"""
        zf.writestr("README.txt", readme)
    
    memory_file.seek(0)
    logger.info("GDPR export completed for user_id=%s", uid)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    return current_app.response_class(
        memory_file.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename=finmind_export_{uid}_{timestamp}.zip"}
    )



@bp.post("/delete-request")
@jwt_required()
def request_deletion():
    """Request account deletion. Starts the grace period countdown."""
    uid = int(get_jwt_identity())
    ip_address, user_agent = _get_request_metadata()
    
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404
    
    existing = db.session.query(DeletionRequest).filter_by(user_id=uid, cancelled=False).first()
    if existing:
        days_left = (existing.scheduled_deletion_date - datetime.utcnow()).days
        return jsonify(
            error="deletion already requested",
            scheduled_deletion_date=existing.scheduled_deletion_date.isoformat(),
            days_remaining=days_left,
        ), 409
    
    scheduled_date = datetime.utcnow() + timedelta(days=GRACE_PERIOD_DAYS)
    deletion_request = DeletionRequest(
        user_id=uid,
        requested_at=datetime.utcnow(),
        scheduled_deletion_date=scheduled_date,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.session.add(deletion_request)
    
    _log_audit(
        user_id=uid,
        action="GDPR_DELETE_REQUEST",
        details={"grace_period_days": GRACE_PERIOD_DAYS, "scheduled_date": scheduled_date.isoformat()},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    db.session.commit()
    logger.info("GDPR deletion requested for user_id=%s, scheduled for %s", uid, scheduled_date)
    
    return jsonify(
        message="deletion request received",
        scheduled_deletion_date=scheduled_date.isoformat(),
        grace_period_days=GRACE_PERIOD_DAYS,
        cancellation_endpoint="/gdpr/delete-request",
    ), 202



@bp.delete("/delete-request")
@jwt_required()
def cancel_deletion_request():
    """Cancel a pending deletion request during the grace period."""
    uid = int(get_jwt_identity())
    ip_address, user_agent = _get_request_metadata()
    
    deletion_request = db.session.query(DeletionRequest).filter_by(user_id=uid, cancelled=False).first()
    if not deletion_request:
        return jsonify(error="no pending deletion request"), 404
    
    deletion_request.cancelled = True
    deletion_request.cancelled_at = datetime.utcnow()
    deletion_request.cancellation_ip = ip_address
    
    _log_audit(
        user_id=uid,
        action="GDPR_DELETE_CANCEL",
        details={"original_scheduled_date": deletion_request.scheduled_deletion_date.isoformat()},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    db.session.commit()
    logger.info("GDPR deletion cancelled for user_id=%s", uid)
    
    return jsonify(message="deletion request cancelled"), 200


@bp.delete("/delete")
@jwt_required()
def confirm_deletion():
    uid = int(get_jwt_identity())
    ip_address, user_agent = _get_request_metadata()
    
    data = request.get_json() or {}
    if data.get("confirm") != "DELETE_MY_ACCOUNT":
        return jsonify(error="confirmation required", hint="send confirm=DELETE_MY_ACCOUNT"), 400
    
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404
    
    audit_details = {"email": user.email, "user_id_original": uid, "immediate_deletion": True, "records_deleted": {}}
    
    try:
        audit_details["records_deleted"]["subscriptions"] = db.session.query(UserSubscription).filter_by(user_id=uid).delete()
        audit_details["records_deleted"]["reminders"] = db.session.query(Reminder).filter_by(user_id=uid).delete()
        audit_details["records_deleted"]["bills"] = db.session.query(Bill).filter_by(user_id=uid).delete()
        audit_details["records_deleted"]["expenses"] = db.session.query(Expense).filter_by(user_id=uid).delete()
        audit_details["records_deleted"]["recurring_expenses"] = db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
        audit_details["records_deleted"]["categories"] = db.session.query(Category).filter_by(user_id=uid).delete()
        audit_details["records_deleted"]["ad_impressions_anonymized"] = db.session.query(AdImpression).filter_by(user_id=uid).update({"user_id": None})
        db.session.query(DeletionRequest).filter_by(user_id=uid).delete()
        db.session.delete(user)
        final_audit = AuditLog(user_id=None, action="GDPR_DELETE_CONFIRMED")
        db.session.add(final_audit)
        logger.info("GDPR IRREVERSIBLE DELETE completed: %s", json.dumps(audit_details))
        db.session.commit()
        return jsonify(message="account permanently deleted", details=audit_details["records_deleted"]), 200
    except Exception as e:
        db.session.rollback()
        logger.error("GDPR deletion failed for user_id=%%s: %%s", uid, str(e))
        return jsonify(error="deletion failed", details=str(e)), 500

@bp.get("/status")
@jwt_required()
def deletion_status():
    uid = int(get_jwt_identity())
    deletion_request = db.session.query(DeletionRequest).filter_by(user_id=uid, cancelled=False).first()
    if not deletion_request:
        return jsonify(has_pending_deletion=False, message="no pending deletion request"), 200
    days_remaining = (deletion_request.scheduled_deletion_date - datetime.utcnow()).days
    return jsonify(
        has_pending_deletion=True,
        requested_at=deletion_request.requested_at.isoformat(),
        scheduled_deletion_date=deletion_request.scheduled_deletion_date.isoformat(),
        days_remaining=max(0, days_remaining),
        grace_period_days=GRACE_PERIOD_DAYS,
        can_cancel=True,
    ), 200
