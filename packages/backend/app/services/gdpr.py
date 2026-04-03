import json
import logging
import threading
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from ..extensions import db, redis_client
from ..models import (
    User,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    Category,
    UserSubscription,
    SubscriptionPlan,
    AuditLog,
)

logger = logging.getLogger("finmind.gdpr")


def _serialize_model(obj: Any) -> Dict[str, Any]:
    """Convert SQLAlchemy model to dict with JSON-serializable values."""
    result = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if isinstance(value, datetime):
            result[column.name] = value.isoformat()
        elif isinstance(value, Decimal):
            result[column.name] = float(value)
        elif hasattr(value, "__dict__"):
            result[column.name] = str(value)
        else:
            result[column.name] = value
    return result


def export_user_data(user_id: int) -> Dict[str, Any]:
    """Export all user data into a structured JSON-serializable dict."""
    user = User.query.get(user_id)
    if not user:
        logger.warning("Export failed: user not found user_id=%s", user_id)
        return {}

    # Collect all user-related data
    data = {"user": _serialize_model(user)}

    # Expenses (including archived)
    expenses = Expense.query.filter_by(user_id=user_id).all()
    data["expenses"] = [_serialize_model(e) for e in expenses]

    # Recurring expenses
    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    data["recurring_expenses"] = [_serialize_model(r) for r in recurring]

    # Bills
    bills = Bill.query.filter_by(user_id=user_id).all()
    data["bills"] = [_serialize_model(b) for b in bills]

    # Reminders
    reminders = Reminder.query.filter_by(user_id=user_id).all()
    data["reminders"] = [_serialize_model(r) for r in reminders]

    # Categories
    categories = Category.query.filter_by(user_id=user_id).all()
    data["categories"] = [_serialize_model(c) for c in categories]

    # Subscriptions
    subscriptions = UserSubscription.query.filter_by(user_id=user_id).all()
    data["subscriptions"] = [_serialize_model(s) for s in subscriptions]

    # Subscription plan details (read-only reference)
    plan_ids = [s.plan_id for s in subscriptions]
    if plan_ids:
        plans = SubscriptionPlan.query.filter(SubscriptionPlan.id.in_(plan_ids)).all()
        data["subscription_plans"] = [_serialize_model(p) for p in plans]

    # Audit logs (last 90 days)
    cutoff = datetime.utcnow() - timedelta(days=90)
    logs = (
        AuditLog.query.filter_by(user_id=user_id)
        .filter(AuditLog.created_at >= cutoff)
        .all()
    )
    data["audit_logs"] = [_serialize_model(l) for l in logs]

    return data


def _enqueue_export_job(user_id: int) -> str:
    """Start async export job and return job ID."""
    job_id = str(uuid.uuid4())
    job_key = f"gdpr:export:{job_id}"
    status_key = f"gdpr:status:{user_id}"

    # Set initial status
    redis_client.hset(
        status_key,
        mapping={
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    redis_client.expire(status_key, 86400 * 7)  # 7 days TTL

    # Enqueue background job
    redis_client.rpush("gdpr:export:queue", f"{job_id}:{user_id}")

    # Start worker thread if not already running (simplified; in prod use Celery/RQ)
    threading.Thread(
        target=_export_worker,
        args=(job_id, user_id),
        daemon=True,
    ).start()

    logger.info("Enqueued export job job_id=%s user_id=%s", job_id, user_id)
    return job_id


def _export_worker(job_id: str, user_id: int):
    """Background worker to generate export and store result in Redis."""
    status_key = f"gdpr:status:{user_id}"
    result_key = f"gdpr:export:{job_id}"

    try:
        redis_client.hset(status_key, "status", "processing")
        data = export_user_data(user_id)
        redis_client.setex(
            result_key,
            86400 * 7,  # 7 days
            json.dumps(data),
        )
        redis_client.hset(
            status_key,
            mapping={
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "download_key": result_key,
            },
        )
        logger.info("Export completed job_id=%s user_id=%s", job_id, user_id)
    except Exception as e:
        logger.exception("Export failed job_id=%s user_id=%s", job_id, user_id)
        redis_client.hset(
            status_key,
            mapping={
                "status": "failed",
                "error": str(e),
                "failed_at": datetime.utcnow().isoformat(),
            },
        )


def request_deletion(user_id: int, password: str) -> Dict[str, Any]:
    """Request account deletion with 30-day grace period."""
    user = User.query.get(user_id)
    if not user:
        raise ValueError("User not found")

    from werkzeug.security import check_password_hash

    if not check_password_hash(user.password_hash, password):
        raise ValueError("Invalid password")

    status_key = f"gdpr:status:{user_id}"
    now = datetime.utcnow()

    # Check if already requested
    existing = redis_client.hgetall(status_key)
    if existing and existing.get("status") in ("grace_period", "deleted"):
        return {
            "already_requested": True,
            "status": existing.get("status"),
            "requested_at": existing.get("requested_at"),
        }

    # Create deletion request
    grace_period_end = now + timedelta(days=30)
    request_id = str(uuid.uuid4())

    redis_client.hset(
        status_key,
        mapping={
            "request_id": request_id,
            "status": "grace_period",
            "requested_at": now.isoformat(),
            "grace_period_ends": grace_period_end.isoformat(),
            "user_id": str(user_id),
        },
    )
    redis_client.expire(status_key, 86400 * 30 + 86400)  # ~31 days

    # Log audit
    _log_audit(
        user_id=user_id,
        action="gdpr_deletion_requested",
        metadata={"request_id": request_id, "grace_period_days": 30},
    )

    logger.info(
        "Deletion requested user_id=%s request_id=%s grace_until=%s",
        user_id,
        request_id,
        grace_period_end.isoformat(),
    )

    return {
        "request_id": request_id,
        "status": "grace_period",
        "requested_at": now.isoformat(),
        "grace_period_ends": grace_period_end.isoformat(),
    }


def cancel_deletion(user_id: int, password: str) -> Dict[str, Any]:
    """Cancel deletion request during grace period."""
    status_key = f"gdpr:status:{user_id}"
    user = User.query.get(user_id)
    if not user:
        raise ValueError("User not found")

    from werkzeug.security import check_password_hash

    if not check_password_hash(user.password_hash, password):
        raise ValueError("Invalid password")

    existing = redis_client.hgetall(status_key)
    if not existing or existing.get("status") != "grace_period":
        raise ValueError("No active deletion request")

    redis_client.delete(status_key)
    _log_audit(
        user_id=user_id,
        action="gdpr_deletion_cancelled",
        metadata={"request_id": existing.get("request_id")},
    )
    logger.info("Deletion cancelled user_id=%s", user_id)
    return {"status": "cancelled"}


def confirm_deletion(user_id: int) -> Dict[str, Any]:
    """Permanently delete user data after grace period."""
    status_key = f"gdpr:status:{user_id}"
    existing = redis_client.hgetall(status_key)
    if not existing or existing.get("status") != "grace_period":
        raise ValueError("Deletion not in grace period or not requested")

    user = User.query.get(user_id)
    if not user:
        raise ValueError("User not found")

    # Perform cascading delete
    _hard_delete_user_data(user_id)

    # Update status
    redis_client.hset(
        status_key,
        mapping={
            "status": "deleted",
            "deleted_at": datetime.utcnow().isoformat(),
        },
    )
    redis_client.expire(status_key, 86400 * 365)  # keep for 1 year

    _log_audit(
        user_id=user_id,
        action="gdpr_deletion_completed",
        metadata={"request_id": existing.get("request_id")},
    )
    logger.info("Deletion completed user_id=%s", user_id)
    return {"status": "deleted", "deleted_at": datetime.utcnow().isoformat()}


def _hard_delete_user_data(user_id: int):
    """Delete all user data permanently. Order respects FK constraints.

    Dependent records first (referencing categories), then categories,
    then remaining tables. Wrapped in transaction for atomicity.
    """
    try:
        # Records referencing categories (must be deleted before Category)
        Expense.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        RecurringExpense.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        Bill.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        Reminder.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # Now safe to delete categories (no more FK references)
        Category.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        UserSubscription.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # AdImpression and AuditLog cleanup
        AdImpression.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        AuditLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # Finally delete the user
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)

        db.session.commit()
        logger.info("Hard delete completed user_id=%s", user_id)
    except Exception:
        db.session.rollback()
        logger.exception("Hard delete FAILED for user_id=%s - rolled back", user_id)
        raise

def get_deletion_status(user_id: int) -> Dict[str, Any]:
    """Get current GDPR deletion status."""
    status_key = f"gdpr:status:{user_id}"
    data = redis_client.hgetall(status_key)
    if not data:
        return {"status": "none"}
    return dict(data)


def _log_audit(user_id: int, action: str, metadata: Dict[str, Any] = None):
    """Create an audit log entry. In production, this should be immutable and stored separately."""
    log = AuditLog(
        user_id=user_id,
        action=f"gdpr:{action}",
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception as e:
        logger.exception("Audit log failed user_id=%s action=%s", user_id, action)
        db.session.rollback()


# For periodic cleanup of expired deletion requests (cron job)
def cleanup_expired_grace_periods():
    """Find grace period requests older than 30 days and execute hard delete."""
    pattern = "gdpr:status:*"
    keys = redis_client.keys(pattern)
    now = datetime.utcnow()
    for key in keys:
        data = redis_client.hgetall(key)
        if data.get("status") != "grace_period":
            continue
        try:
            ends = datetime.fromisoformat(data.get("grace_period_ends"))
            if now >= ends:
                user_id = int(data.get("user_id"))
                logger.info("Auto-deleting expired grace period user_id=%s", user_id)
                _hard_delete_user_data(user_id)
                redis_client.hset(key, "status", "deleted")
                redis_client.hset(key, "deleted_at", now.isoformat())
                _log_audit(
                    user_id=user_id,
                    action="gdpr_deletion_auto_completed",
                    metadata={"reason": "grace_period_expired"},
                )
        except Exception as e:
            logger.exception("Cleanup failed for key %s", key)


