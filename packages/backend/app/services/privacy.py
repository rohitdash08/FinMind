"""Privacy service for PII export and deletion (GDPR compliance)."""
import json
import io
import zipfile
import csv
from datetime import datetime
from flask import jsonify
from ..extensions import db
from ..models import (
    User,
    Category,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    AdImpression,
    UserSubscription,
    AuditLog,
)


def export_user_data(user_id: int) -> tuple[io.BytesIO, str]:
    """
    Export all user data to a ZIP file containing JSON and CSV exports.
    
    Args:
        user_id: The user ID to export data for
        
    Returns:
        Tuple of (BytesIO buffer, filename)
    """
    user = db.session.get(User, user_id)
    if not user:
        return None, None
    
    # Collect all user data
    data = {
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in db.session.query(Category).filter_by(user_id=user_id).all()
        ],
        "expenses": [
            {
                "id": e.id,
                "category_id": e.category_id,
                "amount": float(e.amount) if e.amount else None,
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in db.session.query(Expense).filter_by(user_id=user_id).all()
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "category_id": r.category_id,
                "amount": float(r.amount) if r.amount else None,
                "currency": r.currency,
                "expense_type": r.expense_type,
                "notes": r.notes,
                "cadence": r.cadence.value if r.cadence else None,
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "active": r.active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount) if b.amount else None,
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
                "cadence": b.cadence.value if b.cadence else None,
                "autopay_enabled": b.autopay_enabled,
                "channel_whatsapp": b.channel_whatsapp,
                "channel_email": b.channel_email,
                "active": b.active,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in db.session.query(Bill).filter_by(user_id=user_id).all()
        ],
        "reminders": [
            {
                "id": r.id,
                "bill_id": r.bill_id,
                "message": r.message,
                "send_at": r.send_at.isoformat() if r.send_at else None,
                "sent": r.sent,
                "channel": r.channel,
            }
            for r in db.session.query(Reminder).filter_by(user_id=user_id).all()
        ],
        "subscriptions": [
            {
                "id": s.id,
                "plan_id": s.plan_id,
                "active": s.active,
                "started_at": s.started_at.isoformat() if s.started_at else None,
            }
            for s in db.session.query(UserSubscription).filter_by(user_id=user_id).all()
        ],
        "ad_impressions": [
            {
                "id": a.id,
                "placement": a.placement,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in db.session.query(AdImpression).filter_by(user_id=user_id).all()
        ],
    }
    
    # Create ZIP file with JSON and CSV exports
    buffer = io.BytesIO()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"finmind_data_export_{user_id}_{timestamp}.zip"
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Full JSON export
        zf.writestr("full_export.json", json.dumps(data, indent=2, default=str))
        
        # Individual CSV files for major data types
        if data["expenses"]:
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=data["expenses"][0].keys())
            writer.writeheader()
            writer.writerows(data["expenses"])
            zf.writestr("expenses.csv", csv_buffer.getvalue())
        
        if data["bills"]:
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=data["bills"][0].keys())
            writer.writeheader()
            writer.writerows(data["bills"])
            zf.writestr("bills.csv", csv_buffer.getvalue())
        
        if data["categories"]:
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=data["categories"][0].keys())
            writer.writeheader()
            writer.writerows(data["categories"])
            zf.writestr("categories.csv", csv_buffer.getvalue())
    
    buffer.seek(0)
    
    # Log the export action
    audit_log = AuditLog(user_id=user_id, action="DATA_EXPORT")
    db.session.add(audit_log)
    db.session.commit()
    
    return buffer, filename


def delete_user_data(user_id: int) -> dict:
    """
    Irreversibly delete all user data (GDPR right to erasure).
    
    This performs a hard delete of:
    - All expenses
    - All recurring expenses  
    - All bills
    - All reminders
    - All categories
    - All ad impressions
    - All subscriptions
    - The user account itself
    
    An audit log entry is retained (with user_id nulled) for compliance.
    
    Args:
        user_id: The user ID to delete
        
    Returns:
        Dict with deletion summary
    """
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "User not found", "deleted": False}
    
    # Count records before deletion for summary
    counts = {
        "expenses": db.session.query(Expense).filter_by(user_id=user_id).count(),
        "recurring_expenses": db.session.query(RecurringExpense).filter_by(user_id=user_id).count(),
        "bills": db.session.query(Bill).filter_by(user_id=user_id).count(),
        "reminders": db.session.query(Reminder).filter_by(user_id=user_id).count(),
        "categories": db.session.query(Category).filter_by(user_id=user_id).count(),
        "ad_impressions": db.session.query(AdImpression).filter_by(user_id=user_id).count(),
        "subscriptions": db.session.query(UserSubscription).filter_by(user_id=user_id).count(),
    }
    
    # Log deletion BEFORE removing user (for audit trail)
    audit_log = AuditLog(user_id=None, action=f"ACCOUNT_DELETION:user_id={user_id}")
    db.session.add(audit_log)
    
    # Delete all user data (CASCADE handles most relations, but we're explicit)
    db.session.query(Expense).filter_by(user_id=user_id).delete()
    db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()
    db.session.query(Reminder).filter_by(user_id=user_id).delete()
    db.session.query(Bill).filter_by(user_id=user_id).delete()
    db.session.query(AdImpression).filter_by(user_id=user_id).delete()
    db.session.query(UserSubscription).filter_by(user_id=user_id).delete()
    db.session.query(Category).filter_by(user_id=user_id).delete()
    
    # Finally delete the user
    db.session.delete(user)
    db.session.commit()
    
    return {
        "deleted": True,
        "user_id": user_id,
        "records_removed": counts,
        "message": "All user data has been permanently deleted",
    }
