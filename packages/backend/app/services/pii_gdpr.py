"""
PII Export & Delete Workflow - GDPR-ready (issue #76)

Allow users to export all their personal data and permanently delete their account.
"""
from __future__ import annotations

import json
import hashlib
import zipfile
import io
from datetime import datetime
from typing import Optional
from app.extensions import db
from app.models import User, Expense, RecurringExpense, Bill


class PIIExportPackage:
    """In-memory ZIP package containing all user data in JSON format."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.created_at = datetime.utcnow().isoformat()
        self.sections: dict[str, list] = {}

    def add_section(self, name: str, records: list) -> None:
        self.sections[name] = records

    def to_zip_bytes(self) -> bytes:
        """Return ZIP file as bytes."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "user_id": self.user_id,
                "export_date": self.created_at,
                "sections": list(self.sections.keys()),
                "total_records": sum(len(v) for v in self.sections.values()),
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
            for section_name, records in self.sections.items():
                zf.writestr(
                    f"{section_name}.json",
                    json.dumps(records, indent=2, default=str)
                )
        return buf.getvalue()

    def to_dict(self) -> dict:
        """Return structured dict representation for API responses."""
        total = sum(len(v) for v in self.sections.values())
        return {
            "user_id": self.user_id,
            "export_date": self.created_at,
            "sections": {k: len(v) for k, v in self.sections.items()},
            "total_records": total,
        }

    def checksum(self) -> str:
        """SHA-256 checksum of ZIP content."""
        data = self.to_zip_bytes()
        return hashlib.sha256(data).hexdigest()


def export_user_pii(user_id: int) -> Optional[PIIExportPackage]:
    """
    Collect all personal data for a user and return an exportable package.
    Returns None if user not found.
    """
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return None

    pkg = PIIExportPackage(user_id=user_id)

    # Profile data
    pkg.add_section("profile", [{
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }])

    # Expenses
    expenses = Expense.query.filter_by(user_id=user_id).all()
    pkg.add_section("expenses", [{
        "id": e.id,
        "amount": str(e.amount),
        "currency": e.currency,
        "expense_type": e.expense_type,
        "notes": e.notes,
        "spent_at": e.spent_at.isoformat() if e.spent_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in expenses])

    # Recurring expenses
    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    pkg.add_section("recurring_expenses", [{
        "id": r.id,
        "amount": str(r.amount),
        "currency": r.currency,
        "notes": r.notes,
        "cadence": r.cadence.value if hasattr(r.cadence, "value") else str(r.cadence),
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "active": r.active,
    } for r in recurring])

    # Bills
    bills = Bill.query.filter_by(user_id=user_id).all()
    pkg.add_section("bills", [{
        "id": b.id,
        "name": b.name,
        "amount": str(b.amount),
        "currency": b.currency,
        "cadence": b.cadence.value if hasattr(b.cadence, "value") else str(b.cadence),
        "due_date": b.due_date.isoformat() if b.due_date else None,
        "active": b.active,
    } for b in bills])

    return pkg


# Deletion audit log (lightweight in-memory + model alternative)
class DeletionAuditLog(db.Model):
    """Immutable record of account deletions for compliance."""
    __tablename__ = "deletion_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    # We store a hash of the email, not the email itself (privacy-safe)
    email_hash = db.Column(db.String(64), nullable=False)
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    records_deleted = db.Column(db.Integer, default=0, nullable=False)
    reason = db.Column(db.String(200), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email_hash": self.email_hash,
            "deleted_at": self.deleted_at.isoformat(),
            "records_deleted": self.records_deleted,
            "reason": self.reason,
        }


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


def delete_user_pii(user_id: int, reason: Optional[str] = None) -> Optional[dict]:
    """
    Permanently and irreversibly delete all user data.
    Returns deletion summary, or None if user not found.
    """
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return None

    email_hash = _hash_email(user.email)
    records_deleted = 0

    # Delete in dependency order (children before parents)
    expenses = Expense.query.filter_by(user_id=user_id).all()
    records_deleted += len(expenses)
    for e in expenses:
        db.session.delete(e)

    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    records_deleted += len(recurring)
    for r in recurring:
        db.session.delete(r)

    bills = Bill.query.filter_by(user_id=user_id).all()
    records_deleted += len(bills)
    for b in bills:
        db.session.delete(b)

    # Delete user account
    db.session.delete(user)
    records_deleted += 1

    # Write compliance audit log BEFORE committing deletion
    audit_log = DeletionAuditLog(
        email_hash=email_hash,
        deleted_at=datetime.utcnow(),
        records_deleted=records_deleted,
        reason=reason or "user_requested",
    )
    db.session.add(audit_log)
    db.session.commit()

    return {
        "user_id": user_id,
        "email_hash": email_hash,
        "deleted_at": audit_log.deleted_at.isoformat(),
        "records_deleted": records_deleted,
        "reason": audit_log.reason,
        "audit_log_id": audit_log.id,
        "status": "permanently_deleted",
        "irreversible": True,
    }