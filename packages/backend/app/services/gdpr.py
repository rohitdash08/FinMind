"""
GDPR PII Export & Delete Service
---------------------------------
Handles user data export (ZIP) and irreversible account deletion
with a full audit trail for GDPR compliance.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict

from ..extensions import db
from ..models import (
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    User,
)

logger = logging.getLogger("finmind.gdpr")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_row(obj: Any) -> Dict[str, Any]:
    """Convert a SQLAlchemy model instance to a plain dict."""
    out: Dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        out[col.name] = val
    return out


class GDPRService:
    """Encapsulates all GDPR data operations for a single user."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_user(self) -> User:
        user = db.session.get(User, self.user_id)
        if not user:
            raise ValueError(f"User {self.user_id} not found")
        return user

    def _log_audit(self, action: str, detail: str = "") -> None:
        entry = AuditLog(
            user_id=self.user_id,
            action=action,
            detail=detail[:1000],
            performed_at=_utcnow(),
        )
        db.session.add(entry)

    # ── Export ─────────────────────────────────────────────────────────────────

    def export_zip(self) -> bytes:
        """
        Build a GDPR data export ZIP containing:
          - profile.json
          - expenses.json
          - categories.json
          - recurring_expenses.json
          - bills.json
          - audit_log.json
          - README.txt
        Returns raw bytes of the ZIP file.
        """
        user = self._get_user()

        categories = (
            db.session.query(Category).filter_by(user_id=self.user_id).all()
        )
        expenses = (
            db.session.query(Expense).filter_by(user_id=self.user_id).all()
        )
        recurring = (
            db.session.query(RecurringExpense)
            .filter_by(user_id=self.user_id)
            .all()
        )
        bills = db.session.query(Bill).filter_by(user_id=self.user_id).all()
        audit_entries = (
            db.session.query(AuditLog)
            .filter_by(user_id=self.user_id)
            .order_by(AuditLog.performed_at)
            .all()
        )

        profile = {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("profile.json", json.dumps(profile, indent=2))
            zf.writestr(
                "categories.json",
                json.dumps([_serialize_row(c) for c in categories], indent=2),
            )
            zf.writestr(
                "expenses.json",
                json.dumps([_serialize_row(e) for e in expenses], indent=2),
            )
            zf.writestr(
                "recurring_expenses.json",
                json.dumps([_serialize_row(r) for r in recurring], indent=2),
            )
            zf.writestr(
                "bills.json",
                json.dumps([_serialize_row(b) for b in bills], indent=2),
            )
            zf.writestr(
                "audit_log.json",
                json.dumps([_serialize_row(a) for a in audit_entries], indent=2),
            )
            zf.writestr(
                "README.txt",
                (
                    "FinMind Personal Data Export\n"
                    "============================\n"
                    f"Exported at : {_utcnow().isoformat()}\n"
                    f"Account     : {user.email}\n\n"
                    "Files included:\n"
                    "  profile.json           - Account details\n"
                    "  categories.json        - Your spending categories\n"
                    "  expenses.json          - All expense records\n"
                    "  recurring_expenses.json- Recurring expense rules\n"
                    "  bills.json             - Bill reminders\n"
                    "  audit_log.json         - GDPR action history\n\n"
                    "This export was generated in compliance with GDPR Art. 20.\n"
                ),
            )

        self._log_audit("EXPORT_REQUESTED", f"ZIP export generated for {user.email}")
        db.session.commit()

        logger.info("GDPR export generated for user_id=%s", self.user_id)
        return buf.getvalue()

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete_account(self) -> Dict[str, Any]:
        """
        Permanently and irreversibly delete all PII for this user.
        Cascade order: expenses → recurring → bills → categories → audit_log → user.
        Returns a summary dict with counts of deleted records.
        """
        user = self._get_user()
        email_snapshot = user.email  # capture before deletion

        # Log intent *before* deletion so the entry exists if deletion fails
        self._log_audit(
            "DELETE_REQUESTED",
            f"Irreversible account deletion initiated for {email_snapshot}",
        )
        db.session.flush()

        counts: Dict[str, int] = {}

        counts["expenses"] = (
            db.session.query(Expense).filter_by(user_id=self.user_id).delete()
        )
        counts["recurring_expenses"] = (
            db.session.query(RecurringExpense)
            .filter_by(user_id=self.user_id)
            .delete()
        )
        counts["bills"] = (
            db.session.query(Bill).filter_by(user_id=self.user_id).delete()
        )
        counts["categories"] = (
            db.session.query(Category).filter_by(user_id=self.user_id).delete()
        )
        # Audit log last — keeps history until the very end
        counts["audit_log_entries"] = (
            db.session.query(AuditLog).filter_by(user_id=self.user_id).delete()
        )
        counts["user"] = (
            db.session.query(User).filter_by(id=self.user_id).delete()
        )

        db.session.commit()

        logger.info(
            "GDPR account deleted email=%s counts=%s", email_snapshot, counts
        )
        return {
            "deleted": True,
            "email": email_snapshot,
            "records_removed": counts,
            "performed_at": _utcnow().isoformat(),
        }
