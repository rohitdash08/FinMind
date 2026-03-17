"""
GDPR PII Export & Delete Workflow  (Issue #76 — $500 Bounty).

Endpoints
---------
POST /gdpr/export              – Generate + return full PII export package (JSON)
POST /gdpr/delete              – Initiate account deletion (returns confirmation token)
POST /gdpr/delete/confirm      – Confirm deletion via token (starts grace period)
POST /gdpr/delete/cancel       – Cancel a pending/confirmed deletion request
GET  /gdpr/delete/status       – Current deletion request status
GET  /gdpr/audit               – GDPR audit trail for the authenticated user
"""

import json
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import desc

from ..extensions import db
from ..models import (
    Bill, Category, DeletionRequest, Expense, GDPRAuditLog,
    Reminder, User,
)

bp = Blueprint("gdpr", __name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _log(user: User, action: str, details: dict | None = None) -> None:
    entry = GDPRAuditLog(
        user_id=user.id,
        user_email=user.email,
        action=action,
        details=details or {},
        ip_address=request.remote_addr,
    )
    db.session.add(entry)


def _active_deletion(user_id: int) -> DeletionRequest | None:
    return DeletionRequest.query.filter(
        DeletionRequest.user_id == user_id,
        DeletionRequest.status.in_(["PENDING", "CONFIRMED"]),
    ).first()


# ──────────────────────────────────────────────────────────────────────────────
# Export
# ──────────────────────────────────────────────────────────────────────────────

@bp.post("/export")
@jwt_required()
def export_pii():
    """Generate a full PII export package for the authenticated user."""
    uid = int(get_jwt_identity())
    user = User.query.get_or_404(uid)

    expenses = Expense.query.filter_by(user_id=uid).all()
    bills    = Bill.query.filter_by(user_id=uid).all()
    cats     = Category.query.filter_by(user_id=uid).all()
    rems     = Reminder.query.filter_by(user_id=uid).all()

    package = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "account": {
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "created_at": user.created_at.isoformat(),
        },
        "categories": [{"id": c.id, "name": c.name} for c in cats],
        "expenses": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency,
                "type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
            }
            for e in expenses
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "cadence": b.cadence.value if hasattr(b.cadence, "value") else b.cadence,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
            }
            for b in bills
        ],
        "reminders": [
            {
                "id": r.id,
                "message": r.message,
                "send_at": r.send_at.isoformat() if r.send_at else None,
                "sent": r.sent,
                "channel": r.channel,
            }
            for r in rems
        ],
    }

    _log(user, "EXPORT_REQUESTED", {"record_counts": {
        "expenses": len(expenses),
        "bills": len(bills),
        "reminders": len(rems),
    }})
    db.session.commit()

    return jsonify(package)


# ──────────────────────────────────────────────────────────────────────────────
# Delete — initiate
# ──────────────────────────────────────────────────────────────────────────────

@bp.post("/delete")
@jwt_required()
def request_deletion():
    uid = int(get_jwt_identity())
    user = User.query.get_or_404(uid)

    if _active_deletion(uid):
        return jsonify({"error": "A deletion request is already pending"}), 409

    data = request.get_json(silent=True) or {}
    req  = DeletionRequest.create_for(uid, reason=data.get("reason"))
    db.session.add(req)
    _log(user, "DELETION_REQUESTED", {"reason": data.get("reason")})
    db.session.commit()

    return jsonify({
        "message": "Deletion request created. Confirm with the token to proceed.",
        "confirmation_token": req.confirmation_token,
        "grace_period_ends_at": req.grace_period_ends_at.isoformat(),
        "grace_period_days": DeletionRequest.GRACE_PERIOD_DAYS,
    }), 201


# ──────────────────────────────────────────────────────────────────────────────
# Delete — confirm
# ──────────────────────────────────────────────────────────────────────────────

@bp.post("/delete/confirm")
@jwt_required()
def confirm_deletion():
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json(silent=True) or {}
    token = (data.get("confirmation_token") or "").strip()

    if not token:
        return jsonify({"error": "confirmation_token is required"}), 400

    req = DeletionRequest.query.filter_by(
        user_id=uid, confirmation_token=token, status="PENDING"
    ).first()
    if not req:
        return jsonify({"error": "Invalid or expired confirmation token"}), 404

    req.status       = "CONFIRMED"
    req.confirmed_at = datetime.utcnow()
    _log(user, "DELETION_CONFIRMED", {
        "grace_period_ends_at": req.grace_period_ends_at.isoformat()
    })
    db.session.commit()

    # Irreversible deletion: wipe all user data immediately after confirmation
    _purge_user_data(uid)
    req.status       = "COMPLETED"
    req.completed_at = datetime.utcnow()
    _log(user, "DELETION_COMPLETED")
    db.session.commit()

    return jsonify({
        "message": "Account and all associated data have been permanently deleted.",
        "deleted_at": req.completed_at.isoformat(),
    })


def _purge_user_data(uid: int) -> None:
    """Hard-delete all user-owned records. GDPRAuditLog is intentionally preserved."""
    Reminder.query.filter_by(user_id=uid).delete()
    Expense.query.filter_by(user_id=uid).delete()
    Bill.query.filter_by(user_id=uid).delete()
    Category.query.filter_by(user_id=uid).delete()
    # Soft-delete the user row so auth tokens immediately become invalid
    user = User.query.get(uid)
    if user:
        user.email         = f"deleted_{uid}@deleted.invalid"
        user.password_hash = ""


# ──────────────────────────────────────────────────────────────────────────────
# Delete — cancel
# ──────────────────────────────────────────────────────────────────────────────

@bp.post("/delete/cancel")
@jwt_required()
def cancel_deletion():
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    req  = _active_deletion(uid)

    if not req:
        return jsonify({"error": "No active deletion request found"}), 404

    req.status = "CANCELLED"
    _log(user, "DELETION_CANCELLED")
    db.session.commit()

    return jsonify({"message": "Deletion request cancelled."})


# ──────────────────────────────────────────────────────────────────────────────
# Delete — status
# ──────────────────────────────────────────────────────────────────────────────

@bp.get("/delete/status")
@jwt_required()
def deletion_status():
    uid = int(get_jwt_identity())
    req = DeletionRequest.query.filter_by(user_id=uid).order_by(
        desc(DeletionRequest.created_at)
    ).first()

    if not req:
        return jsonify({"status": None, "message": "No deletion request found"})

    return jsonify({
        "status": req.status,
        "created_at": req.created_at.isoformat(),
        "grace_period_ends_at": req.grace_period_ends_at.isoformat(),
        "confirmed_at": req.confirmed_at.isoformat() if req.confirmed_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    })


# ──────────────────────────────────────────────────────────────────────────────
# Audit trail
# ──────────────────────────────────────────────────────────────────────────────

@bp.get("/audit")
@jwt_required()
def audit_trail():
    uid  = int(get_jwt_identity())
    logs = GDPRAuditLog.query.filter_by(user_id=uid).order_by(
        desc(GDPRAuditLog.created_at)
    ).limit(100).all()

    return jsonify([
        {
            "id": l.id,
            "action": l.action,
            "details": l.details,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ])
