"""GDPR-compliant PII Export and Delete Workflow Service."""

import csv
import io
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

from ..extensions import db, redis_client
from ..models import (
    User,
    Category,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    UserSubscription,
    AuditLog,
)


DELETION_GRACE_PERIOD_DAYS = 30
EXPORT_TOKEN_TTL_SECONDS = 900  # 15 minutes


class GDPRService:
    """Handles PII export, deletion workflow, and audit logging for GDPR compliance."""

    @staticmethod
    def export_user_data(user_id: int) -> dict[str, Any]:
        """
        Export all PII data for a user as a structured package.
        Returns a dictionary containing user profile, transactions, budgets, goals, and accounts.
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        export_data = {
            "export_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "email": user.email,
            },
            "user_profile": {
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
            "subscriptions": [],
            "audit_logs": [],
        }

        # Categories
        categories = db.session.query(Category).filter_by(user_id=user_id).all()
        for cat in categories:
            export_data["categories"].append({
                "id": cat.id,
                "name": cat.name,
                "created_at": cat.created_at.isoformat() if cat.created_at else None,
            })

        # Expenses
        expenses = db.session.query(Expense).filter_by(user_id=user_id).all()
        for exp in expenses:
            export_data["expenses"].append({
                "id": exp.id,
                "amount": str(exp.amount),
                "currency": exp.currency,
                "expense_type": exp.expense_type,
                "notes": exp.notes,
                "spent_at": exp.spent_at.isoformat() if exp.spent_at else None,
                "category_id": exp.category_id,
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
            })

        # Recurring Expenses
        recurring = db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
        for rec in recurring:
            export_data["recurring_expenses"].append({
                "id": rec.id,
                "amount": str(rec.amount),
                "currency": rec.currency,
                "expense_type": rec.expense_type,
                "notes": rec.notes,
                "cadence": rec.cadence.value if rec.cadence else None,
                "start_date": rec.start_date.isoformat() if rec.start_date else None,
                "end_date": rec.end_date.isoformat() if rec.end_date else None,
                "active": rec.active,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            })

        # Bills
        bills = db.session.query(Bill).filter_by(user_id=user_id).all()
        for bill in bills:
            export_data["bills"].append({
                "id": bill.id,
                "name": bill.name,
                "amount": str(bill.amount),
                "currency": bill.currency,
                "next_due_date": bill.next_due_date.isoformat() if bill.next_due_date else None,
                "cadence": bill.cadence.value if bill.cadence else None,
                "autopay_enabled": bill.autopay_enabled,
                "channel_whatsapp": bill.channel_whatsapp,
                "channel_email": bill.channel_email,
                "active": bill.active,
                "created_at": bill.created_at.isoformat() if bill.created_at else None,
            })

        # Reminders
        reminders = db.session.query(Reminder).filter_by(user_id=user_id).all()
        for rem in reminders:
            export_data["reminders"].append({
                "id": rem.id,
                "bill_id": rem.bill_id,
                "message": rem.message,
                "send_at": rem.send_at.isoformat() if rem.send_at else None,
                "sent": rem.sent,
                "channel": rem.channel,
            })

        # Subscriptions
        subs = db.session.query(UserSubscription).filter_by(user_id=user_id).all()
        for sub in subs:
            export_data["subscriptions"].append({
                "id": sub.id,
                "plan_id": sub.plan_id,
                "active": sub.active,
                "started_at": sub.started_at.isoformat() if sub.started_at else None,
            })

        # Audit Logs (GDPR logs are retained, this is the user's own audit data)
        audit_logs = db.session.query(AuditLog).filter_by(user_id=user_id).all()
        for log in audit_logs:
            export_data["audit_logs"].append({
                "id": log.id,
                "action": log.action,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            })

        return export_data

    @staticmethod
    def generate_export_package(user_id: int) -> tuple[str, str]:
        """
        Generate a signed export token and returns (token, download_url).
        The token is stored in Redis with 15-minute expiry.
        """
        token = secrets.token_urlsafe(32)
        key = f"gdpr:export:{token}"
        redis_client.setex(key, EXPORT_TOKEN_TTL_SECONDS, str(user_id))

        # In production, this would be a signed S3/GCS URL
        download_url = f"/gdpr/download/{token}"
        return token, download_url

    @staticmethod
    def get_export_data_by_token(token: str) -> dict[str, Any] | None:
        """Retrieve export data using a valid export token."""
        key = f"gdpr:export:{token}"
        user_id = redis_client.get(key)
        if not user_id:
            return None
        return GDPRService.export_user_data(int(user_id))

    @staticmethod
    def initiate_user_deletion(user_id: int, request_ip: str | None = None, user_agent: str | None = None) -> str:
        """
        Initiate the GDPR deletion workflow.
        Stores a deletion request with 30-day grace period.
        Returns a confirmation token.
        """
        confirmation_token = secrets.token_urlsafe(32)
        key = f"gdpr:deletion:{confirmation_token}"

        deletion_data = json.dumps({
            "user_id": user_id,
            "initiated_at": datetime.utcnow().isoformat(),
            "grace_period_ends": (datetime.utcnow() + timedelta(days=DELETION_GRACE_PERIOD_DAYS)).isoformat(),
            "request_ip": request_ip,
            "user_agent": user_agent,
        })

        redis_client.setex(key, DELETION_GRACE_PERIOD_DAYS * 24 * 3600, deletion_data)

        # Log the initiation
        GDPRService._log_audit_event(
            user_id=user_id,
            action="GDPR_DELETION_INITIATED",
            details={
                "confirmation_token": confirmation_token,
                "grace_period_days": DELETION_GRACE_PERIOD_DAYS,
                "request_ip": request_ip,
                "user_agent": user_agent,
            }
        )

        return confirmation_token

    @staticmethod
    def confirm_user_deletion(confirmation_token: str, request_ip: str | None = None, user_agent: str | None = None) -> bool:
        """
        Confirm and execute the irreversible user deletion.
        Returns True if deletion was successful, False if token is invalid or expired.
        """
        key = f"gdpr:deletion:{confirmation_token}"
        deletion_data_raw = redis_client.get(key)

        if not deletion_data_raw:
            return False

        deletion_data = json.loads(deletion_data_raw)
        user_id = int(deletion_data["user_id"])

        user = db.session.get(User, user_id)
        if not user:
            return False

        # Log before deletion for audit trail
        GDPRService._log_audit_event(
            user_id=user_id,
            action="GDPR_DELETION_CONFIRMED",
            details={
                "confirmed_at": datetime.utcnow().isoformat(),
                "grace_period_ended": deletion_data.get("grace_period_ends"),
                "request_ip": request_ip,
                "user_agent": user_agent,
            }
        )

        # Execute cascading delete (order matters for foreign key constraints)
        # Reminders first (references bills)
        db.session.query(Reminder).filter_by(user_id=user_id).delete(synchronize_session=False)

        # Bills
        db.session.query(Bill).filter_by(user_id=user_id).delete(synchronize_session=False)

        # Recurring Expenses
        db.session.query(RecurringExpense).filter_by(user_id=user_id).delete(synchronize_session=False)

        # Expenses
        db.session.query(Expense).filter_by(user_id=user_id).delete(synchronize_session=False)

        # Categories
        db.session.query(Category).filter_by(user_id=user_id).delete(synchronize_session=False)

        # User Subscriptions
        db.session.query(UserSubscription).filter_by(user_id=user_id).delete(synchronize_session=False)

        # User (keep audit logs by setting user_id to NULL for audit logs - GDPR logs exempt)
        db.session.execute(
            db.text("UPDATE audit_logs SET user_id = NULL WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        db.session.delete(user)

        db.session.commit()

        # Clean up the deletion token
        redis_client.delete(key)

        # Log completion
        logger = __import__("logging").getLogger("finmind.gdpr")
        logger.info("GDPR deletion completed for user_id=%s", user_id)

        return True

    @staticmethod
    def cancel_user_deletion(confirmation_token: str) -> bool:
        """
        Cancel a pending deletion request during the grace period.
        """
        key = f"gdpr:deletion:{confirmation_token}"
        deletion_data_raw = redis_client.get(key)

        if not deletion_data_raw:
            return False

        deletion_data = json.loads(deletion_data_raw)
        user_id = int(deletion_data["user_id"])

        # Log cancellation
        GDPRService._log_audit_event(
            user_id=user_id,
            action="GDPR_DELETION_CANCELLED",
            details={"cancelled_at": datetime.utcnow().isoformat()}
        )

        redis_client.delete(key)
        return True

    @staticmethod
    def get_deletion_status(confirmation_token: str) -> dict[str, Any] | None:
        """Get the status of a pending deletion request."""
        key = f"gdpr:deletion:{confirmation_token}"
        deletion_data_raw = redis_client.get(key)

        if not deletion_data_raw:
            return None

        deletion_data = json.loads(deletion_data_raw)
        return {
            "user_id": int(deletion_data["user_id"]),
            "initiated_at": deletion_data.get("initiated_at"),
            "grace_period_ends": deletion_data.get("grace_period_ends"),
            "status": "pending"
        }

    @staticmethod
    def _log_audit_event(user_id: int, action: str, details: dict[str, Any] | None = None) -> AuditLog:
        """Log a GDPR-related audit event."""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
        )
        db.session.add(audit_log)
        db.session.commit()
        return audit_log

    @staticmethod
    def export_to_csv(export_data: dict[str, Any]) -> dict[str, str]:
        """
        Convert export data to CSV format for each data type.
        Returns a dict mapping data type to CSV string.
        """
        csv_packages = {}

        for data_type in ["expenses", "categories", "bills", "reminders", "subscriptions"]:
            records = export_data.get(data_type, [])
            if not records:
                csv_packages[data_type] = ""
                continue

            output = io.StringIO()
            if records:
                writer = csv.DictWriter(output, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
            csv_packages[data_type] = output.getvalue()

        return csv_packages
