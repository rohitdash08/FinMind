"""
Privacy routes – GDPR-ready PII export & account deletion.

Endpoints
---------
GET  /privacy/export          Download a ZIP of all user personal data (JSON)
POST /privacy/delete          Permanently delete account (requires password)
GET  /privacy/audit-log       View the caller's own audit-trail entries
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import (
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
    User,
    UserSubscription,
)

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_audit(user_id: int, action: str, details: str | None = None) -> None:
    """Write an entry to the audit_logs table."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        # Store extra metadata in a "details" field if the column exists;
        # fall back gracefully when running against a DB that hasn't migrated yet.
    )
    # Attach details if the model supports it (added in this migration).
    if hasattr(AuditLog, "details") and details:
        entry.details = details
    db.session.add(entry)
    db.session.commit()
    logger.info("audit user_id=%s action=%s", user_id, action)


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _serialize_expense(e: Expense) -> dict:
    return {
        "id": e.id,
        "amount": str(e.amount),
        "currency": e.currency,
        "expense_type": e.expense_type,
        "notes": e.notes,
        "spent_at": e.spent_at.isoformat() if e.spent_at else None,
        "category_id": e.category_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _serialize_category(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_bill(b: Bill) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "amount": str(b.amount),
        "currency": b.currency,
        "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
        "cadence": b.cadence.value if hasattr(b.cadence, "value") else str(b.cadence),
        "autopay_enabled": b.autopay_enabled,
        "active": b.active,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def _serialize_reminder(r: Reminder) -> dict:
    return {
        "id": r.id,
        "bill_id": r.bill_id,
        "message": r.message,
        "send_at": r.send_at.isoformat() if r.send_at else None,
        "sent": r.sent,
        "channel": r.channel,
    }


def _serialize_recurring(r: RecurringExpense) -> dict:
    return {
        "id": r.id,
        "amount": str(r.amount),
        "currency": r.currency,
        "expense_type": r.expense_type,
        "notes": r.notes,
        "cadence": r.cadence.value if hasattr(r.cadence, "value") else str(r.cadence),
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "active": r.active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_subscription(s: UserSubscription) -> dict:
    return {
        "id": s.id,
        "plan_id": s.plan_id,
        "active": s.active,
        "started_at": s.started_at.isoformat() if s.started_at else None,
    }


def _build_export_payload(uid: int) -> dict:
    """Collect all personal data for a user into a serialisable dict."""
    user = db.session.get(User, uid)
    if not user:
        return {}

    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    categories = db.session.query(Category).filter_by(user_id=uid).all()
    bills = db.session.query(Bill).filter_by(user_id=uid).all()
    reminders = db.session.query(Reminder).filter_by(user_id=uid).all()
    recurrings = db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    subscriptions = db.session.query(UserSubscription).filter_by(user_id=uid).all()

    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "profile": _serialize_user(user),
        "expenses": [_serialize_expense(e) for e in expenses],
        "categories": [_serialize_category(c) for c in categories],
        "bills": [_serialize_bill(b) for b in bills],
        "reminders": [_serialize_reminder(r) for r in reminders],
        "recurring_expenses": [_serialize_recurring(r) for r in recurrings],
        "subscriptions": [_serialize_subscription(s) for s in subscriptions],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.get("/export")
@jwt_required()
def export_data():
    """
    Generate and download a ZIP archive containing all personal data.

    Returns a ``finmind_export_<user_id>.zip`` file that contains a single
    ``data.json`` with every record belonging to the authenticated user.
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    payload = _build_export_payload(uid)

    # Build the in-memory ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "data.json",
            json.dumps(payload, indent=2, ensure_ascii=False),
        )
        # Include a human-readable README inside the ZIP
        readme = (
            "FinMind Personal Data Export\n"
            "============================\n\n"
            f"Exported at : {payload['exported_at']}\n"
            f"User email  : {user.email}\n\n"
            "This archive contains all personal data held by FinMind for your\n"
            "account in machine-readable JSON format (data.json).\n\n"
            "To request erasure of this data, use the DELETE /privacy/delete\n"
            "endpoint or contact privacy@finmind.app.\n"
        )
        zf.writestr("README.txt", readme)

    buf.seek(0)

    # Audit trail
    _log_audit(uid, "PII_EXPORT", details=f"export requested by user {uid}")

    logger.info("PII export served for user_id=%s", uid)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"finmind_export_{uid}.zip",
    )


@bp.post("/delete")
@jwt_required()
def delete_account():
    """
    Permanently and irreversibly delete the authenticated user's account.

    Requires ``{"password": "<current password>"}`` in the request body as a
    confirmation step to prevent accidental or unauthorised deletions.

    All related data (expenses, bills, reminders, etc.) is removed via
    ON DELETE CASCADE constraints.  The action is recorded in ``audit_logs``
    *before* the user row is deleted so the record is preserved even after
    the user is gone (user_id becomes NULL once the FK is dropped).
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    data = request.get_json() or {}
    password = data.get("password", "")

    if not password:
        return jsonify(error="password confirmation required"), 400

    if not check_password_hash(user.password_hash, password):
        logger.warning("Delete account: wrong password for user_id=%s", uid)
        return jsonify(error="incorrect password"), 403

    # Write audit entry BEFORE deletion so we retain the record.
    # The FK will be set to NULL by the DB after the user row is removed.
    email_snapshot = user.email
    entry = AuditLog(
        user_id=uid,
        action="ACCOUNT_DELETED",
    )
    if hasattr(AuditLog, "details"):
        entry.details = f"permanent account deletion for email={email_snapshot}"
    db.session.add(entry)
    db.session.flush()  # persist audit row while user still exists

    # Delete the user – ON DELETE CASCADE handles related rows
    db.session.delete(user)
    db.session.commit()

    logger.warning(
        "Account permanently deleted user_id=%s email=%s", uid, email_snapshot
    )
    return (
        jsonify(
            message=(
                "Your account and all associated data have been permanently deleted. "
                "This action cannot be undone."
            )
        ),
        200,
    )


@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    """
    Return the caller's own audit-trail entries (most recent first).

    Optional query params:
      - limit  (int, default 50, max 200)
      - offset (int, default 0)
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return jsonify(error="limit and offset must be integers"), 400

    entries = (
        db.session.query(AuditLog)
        .filter_by(user_id=uid)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    result = []
    for e in entries:
        row = {
            "id": e.id,
            "action": e.action,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        if hasattr(e, "details"):
            row["details"] = e.details
        result.append(row)

    return jsonify(audit_log=result, limit=limit, offset=offset)
