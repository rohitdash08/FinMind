"""GDPR PII Export & Delete Workflow (Issue #76).

Provides three endpoints:
- POST /gdpr/export      — generate a full data export package (JSON)
- POST /gdpr/delete      — initiate irreversible account deletion (soft-delete first step)
- DELETE /gdpr/delete/confirm — confirm and execute hard delete

Audit trail: every action is logged to the AuditLog table.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
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
import logging
import time

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")

# ---------------------------------------------------------------------------
# Rate-limit state for POST /gdpr/export
# Maps user_id → Unix timestamp (float) of the last accepted export request.
# NOTE: This is in-process only; in a multi-worker deployment replace with a
# shared backend (e.g. Redis) so limits are enforced across all workers.
# ---------------------------------------------------------------------------
_export_rate_limit: dict[int, float] = {}
_EXPORT_RATE_LIMIT_SECONDS: int = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _audit(user_id: int | None, action: str) -> None:
    """Append an immutable audit log entry."""
    entry = AuditLog(user_id=user_id, action=action)
    db.session.add(entry)
    # Flush without committing so the caller controls the transaction.
    db.session.flush()


def _serialize_date(val) -> str | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": _serialize_date(user.created_at),
    }


def _expense_to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "category_id": e.category_id,
        "amount": float(e.amount),
        "currency": e.currency,
        "expense_type": e.expense_type,
        "notes": e.notes,
        "spent_at": _serialize_date(e.spent_at),
        "created_at": _serialize_date(e.created_at),
    }


def _bill_to_dict(b: Bill) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "amount": float(b.amount),
        "currency": b.currency,
        "cadence": b.cadence.value if hasattr(b.cadence, "value") else str(b.cadence),
        "next_due_date": _serialize_date(b.next_due_date),
        "active": b.active,
        "created_at": _serialize_date(b.created_at),
    }


def _category_to_dict(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": _serialize_date(c.created_at),
    }


def _reminder_to_dict(r: Reminder) -> dict:
    return {
        "id": r.id,
        "bill_id": r.bill_id,
        "message": r.message,
        "send_at": _serialize_date(r.send_at),
        "sent": r.sent,
        "channel": r.channel,
    }


def _recurring_to_dict(r: RecurringExpense) -> dict:
    return {
        "id": r.id,
        "category_id": r.category_id,
        "amount": float(r.amount),
        "currency": r.currency,
        "cadence": r.cadence.value if hasattr(r.cadence, "value") else str(r.cadence),
        "start_date": _serialize_date(r.start_date),
        "end_date": _serialize_date(r.end_date),
        "active": r.active,
        "created_at": _serialize_date(r.created_at),
    }


def _subscription_to_dict(s: UserSubscription) -> dict:
    return {
        "id": s.id,
        "plan_id": s.plan_id,
        "active": s.active,
        "started_at": _serialize_date(s.started_at),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@bp.post("/export")
@jwt_required()
def export_pii():
    """Generate and return a structured JSON export of all user PII data.

    Rate-limited to one request per ``_EXPORT_RATE_LIMIT_SECONDS`` seconds per
    authenticated user to prevent bulk scraping by compromised accounts.
    """
    uid = int(get_jwt_identity())

    # Rate-limit check: reject if the user already triggered an export recently.
    now = time.time()
    last_export = _export_rate_limit.get(uid)
    if last_export is not None:
        elapsed = now - last_export
        if elapsed < _EXPORT_RATE_LIMIT_SECONDS:
            retry_after = int(_EXPORT_RATE_LIMIT_SECONDS - elapsed) + 1
            logger.warning(
                "GDPR export rate-limited for user_id=%s (%.1fs since last export)",
                uid,
                elapsed,
            )
            return jsonify(
                error="export rate limit exceeded; try again later",
                retry_after_seconds=retry_after,
            ), 429
    _export_rate_limit[uid] = now

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    bills = db.session.query(Bill).filter_by(user_id=uid).all()
    categories = db.session.query(Category).filter_by(user_id=uid).all()
    reminders = db.session.query(Reminder).filter_by(user_id=uid).all()
    recurring = db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    subscriptions = db.session.query(UserSubscription).filter_by(user_id=uid).all()

    package = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": _user_to_dict(user),
        "expenses": [_expense_to_dict(e) for e in expenses],
        "bills": [_bill_to_dict(b) for b in bills],
        "categories": [_category_to_dict(c) for c in categories],
        "reminders": [_reminder_to_dict(r) for r in reminders],
        "recurring_expenses": [_recurring_to_dict(r) for r in recurring],
        "subscriptions": [_subscription_to_dict(s) for s in subscriptions],
    }

    _audit(uid, "GDPR_EXPORT_REQUESTED")
    db.session.commit()
    logger.info("GDPR export generated for user_id=%s", uid)
    return jsonify(package), 200


@bp.post("/delete")
@jwt_required()
def request_delete():
    """Initiate the irreversible deletion workflow (soft-delete / grace period)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    if user.deletion_requested_at is not None:
        requested_at = user.deletion_requested_at.isoformat()
        return jsonify(
            message="deletion already pending; call DELETE /gdpr/delete/confirm to proceed",
            requested_at=requested_at,
        ), 200

    user.deletion_requested_at = datetime.now(timezone.utc)
    db.session.flush()
    _audit(uid, "GDPR_DELETE_REQUESTED")
    db.session.commit()
    logger.info("GDPR delete initiated for user_id=%s", uid)
    return jsonify(
        message=(
            "Deletion request received. "
            "Call DELETE /gdpr/delete/confirm to permanently delete your account. "
            "This action is irreversible."
        ),
        requested_at=user.deletion_requested_at.isoformat(),
    ), 202


@bp.delete("/delete/confirm")
@jwt_required()
def confirm_delete():
    """Confirm and execute the irreversible hard-delete of all user data."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    if user.deletion_requested_at is None:
        return jsonify(
            error="no pending deletion request; call POST /gdpr/delete first"
        ), 409

    # Audit before deleting (retain per GDPR compliance — logs survive deletion).
    _audit(uid, "GDPR_DELETE_CONFIRMED")
    db.session.flush()

    # NOTE — JWT token remains valid until its natural expiry: Flask-JWT-Extended
    # does not maintain a server-side token registry by default, so revoking a
    # token requires an external blocklist (e.g. Redis-backed JTI blocklist).
    # Any request made with the same bearer token after this point will return
    # 404 (user not found) because the user row is gone, which is safe but not
    # a cryptographic revocation.  Consider adding a token blocklist if
    # immediate invalidation is a hard requirement.

    # Cascade delete: reminders -> bills -> expenses -> recurring -> categories
    # -> subscriptions -> user.  AuditLog rows are kept for compliance.
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()
    db.session.query(UserSubscription).filter_by(user_id=uid).delete()
    db.session.delete(user)
    db.session.commit()

    logger.info("GDPR hard-delete executed for user_id=%s", uid)
    return jsonify(message="Account and all associated data permanently deleted."), 200
