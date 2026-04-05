"""
GDPR-ready PII export & account deletion with audit trail (issue #76 — $500 bounty).
"""
import json
import logging
import zipfile
import io
from datetime import datetime, timezone
from ..extensions import db
from ..models import User, Expense, Category, Bill, RecurringExpense

logger = logging.getLogger("finmind.gdpr")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def export_user_data(user_id: int) -> bytes:
    """
    Generate a ZIP containing all user PII as JSON files.
    Returns raw ZIP bytes.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # profile.json
        profile = {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
            "exported_at": _utcnow(),
        }
        zf.writestr("profile.json", json.dumps(profile, indent=2))

        # expenses.json
        expenses = [
            {
                "id": e.id, "amount": float(e.amount), "currency": e.currency,
                "type": e.expense_type, "notes": e.notes,
                "spent_at": e.spent_at.isoformat(), "category_id": e.category_id,
                "created_at": e.created_at.isoformat(),
            }
            for e in db.session.query(Expense).filter_by(user_id=user_id).all()
        ]
        zf.writestr("expenses.json", json.dumps(expenses, indent=2))

        # categories.json
        cats = [
            {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
            for c in db.session.query(Category).filter_by(user_id=user_id).all()
        ]
        zf.writestr("categories.json", json.dumps(cats, indent=2))

        # bills.json
        bills = [
            {
                "id": b.id, "name": b.name, "amount": float(b.amount),
                "currency": b.currency, "cadence": b.cadence.value,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
            }
            for b in db.session.query(Bill).filter_by(user_id=user_id).all()
        ]
        zf.writestr("bills.json", json.dumps(bills, indent=2))

        # manifest.json
        manifest = {
            "user_id": user_id, "exported_at": _utcnow(),
            "files": ["profile.json", "expenses.json", "categories.json", "bills.json"],
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    _audit_log(user_id, "export_requested")
    return buf.getvalue()


def delete_user_account(user_id: int) -> dict:
    """
    Permanently delete all user data. Irreversible.
    Returns audit record.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    email = user.email
    counts = {}

    # Delete in FK order
    counts["recurring_expenses"] = db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()
    counts["expenses"] = db.session.query(Expense).filter_by(user_id=user_id).delete()
    counts["bills"] = db.session.query(Bill).filter_by(user_id=user_id).delete()
    counts["categories"] = db.session.query(Category).filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()

    record = {
        "user_id": user_id, "email": email,
        "deleted_at": _utcnow(), "records_deleted": counts,
    }
    _audit_log(user_id, "account_deleted", extra=record)
    logger.warning("GDPR account deletion: user_id=%d email=%s records=%s", user_id, email, counts)
    return record


def _audit_log(user_id: int, action: str, extra: dict = None):
    """Append to audit log file (append-only, never deleted)."""
    import os
    log_dir = os.environ.get("AUDIT_LOG_DIR", "/tmp/finmind_audit")
    os.makedirs(log_dir, exist_ok=True)
    entry = {"ts": _utcnow(), "user_id": user_id, "action": action}
    if extra:
        entry.update(extra)
    with open(os.path.join(log_dir, "gdpr_audit.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")
