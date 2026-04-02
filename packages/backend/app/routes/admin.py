from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Reminder
from datetime import datetime, timedelta
import logging

bp = Blueprint("admin", __name__)
logger = logging.getLogger("finmind.admin")


def _require_admin():
    """Helper to check if current user is admin."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="admin access required"), 403
    return None


@bp.get("/reminders/metrics")
@jwt_required()
def reminders_metrics():
    """Admin: Get reminder processing metrics."""
    auth_error = _require_admin()
    if auth_error:
        return auth_error

    # Total counts by status
    total = db.session.query(Reminder).count()
    by_status = (
        db.session.query(Reminder.status, db.func.count(Reminder.id))
        .group_by(Reminder.status)
        .all()
    )
    status_counts = {status: count for status, count in by_status}

    # Recent failures (last 24h)
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_failures = (
        db.session.query(Reminder)
        .filter(
            Reminder.status == "failed",
            Reminder.last_retry_at >= yesterday,
        )
        .order_by(Reminder.last_retry_at.desc())
        .all()
    )
    failures_list = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "message": r.message[:100],
            "retry_count": r.retry_count,
            "failure_reason": r.failure_reason,
            "last_retry_at": r.last_retry_at.isoformat() if r.last_retry_at else None,
        }
        for r in recent_failures
    ]

    # Reminders pending retry (next_retry_at in future)
    pending_retry = (
        db.session.query(Reminder)
        .filter(Reminder.status == "retrying", Reminder.next_retry_at > datetime.utcnow())
        .count()
    )

    # Average retry count for failed reminders
    avg_retries = (
        db.session.query(db.func.avg(Reminder.retry_count))
        .filter(Reminder.status == "failed")
        .scalar()
    )
    avg_retries = float(avg_retries) if avg_retries else 0.0

    return jsonify(
        {
            "total": total,
            "by_status": status_counts,
            "pending_retry": pending_retry,
            "avg_retries_for_failed": round(avg_retries, 2),
            "recent_failures": failures_list,
        }
    )


@bp.get("/reminders/failures")
@jwt_required()
def reminders_failures():
    """Admin: List failed reminders with details."""
    auth_error = _require_admin()
    if auth_error:
        return auth_error

    limit = request.args.get("limit", 100, type=int)
    failures = (
        db.session.query(Reminder)
        .filter(Reminder.status == "failed")
        .order_by(Reminder.last_retry_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify(
        [
            {
                "id": r.id,
                "user_id": r.user_id,
                "bill_id": r.bill_id,
                "message": r.message,
                "channel": r.channel,
                "send_at": r.send_at.isoformat(),
                "retry_count": r.retry_count,
                "last_retry_at": r.last_retry_at.isoformat() if r.last_retry_at else None,
                "failure_reason": r.failure_reason,
            }
            for r in failures
        ]
    )
