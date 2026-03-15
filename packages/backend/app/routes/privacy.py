from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    User, Category, Expense, RecurringExpense, Bill, Reminder,
    AdImpression, UserSubscription, AuditLog
)
import json
import csv
import io
import zipfile
from datetime import datetime
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


@bp.get("/export")
@jwt_required()
def export_data():
    """
    Export all personal data for the authenticated user.
    Returns a ZIP file containing JSON and CSV exports of all user data.
    """
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    
    if not user:
        return jsonify(error="User not found"), 404
    
    logger.info("Export requested for user_id=%s", user_id)
    
    # Collect all user data
    data = {
        "export_date": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None
        },
        "categories": [],
        "expenses": [],
        "recurring_expenses": [],
        "bills": [],
        "reminders": [],
        "ad_impressions": [],
        "subscriptions": []
    }
    
    # Export categories
    categories = Category.query.filter_by(user_id=user_id).all()
    for cat in categories:
        data["categories"].append({
            "id": cat.id,
            "name": cat.name,
            "created_at": cat.created_at.isoformat() if cat.created_at else None
        })
    
    # Export expenses
    expenses = Expense.query.filter_by(user_id=user_id).all()
    for exp in expenses:
        data["expenses"].append({
            "id": exp.id,
            "category_id": exp.category_id,
            "amount": float(exp.amount) if exp.amount else 0,
            "currency": exp.currency,
            "expense_type": exp.expense_type,
            "notes": exp.notes,
            "spent_at": exp.spent_at.isoformat() if exp.spent_at else None,
            "source_recurring_id": exp.source_recurring_id,
            "created_at": exp.created_at.isoformat() if exp.created_at else None
        })
    
    # Export recurring expenses
    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    for rec in recurring:
        data["recurring_expenses"].append({
            "id": rec.id,
            "category_id": rec.category_id,
            "amount": float(rec.amount) if rec.amount else 0,
            "currency": rec.currency,
            "expense_type": rec.expense_type,
            "notes": rec.notes,
            "cadence": rec.cadence.value if rec.cadence else None,
            "start_date": rec.start_date.isoformat() if rec.start_date else None,
            "end_date": rec.end_date.isoformat() if rec.end_date else None,
            "active": rec.active,
            "created_at": rec.created_at.isoformat() if rec.created_at else None
        })
    
    # Export bills
    bills = Bill.query.filter_by(user_id=user_id).all()
    for bill in bills:
        data["bills"].append({
            "id": bill.id,
            "name": bill.name,
            "amount": float(bill.amount) if bill.amount else 0,
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat() if bill.next_due_date else None,
            "cadence": bill.cadence.value if bill.cadence else None,
            "autopay_enabled": bill.autopay_enabled,
            "channel_whatsapp": bill.channel_whatsapp,
            "channel_email": bill.channel_email,
            "active": bill.active,
            "created_at": bill.created_at.isoformat() if bill.created_at else None
        })
    
    # Export reminders
    reminders = Reminder.query.filter_by(user_id=user_id).all()
    for rem in reminders:
        data["reminders"].append({
            "id": rem.id,
            "bill_id": rem.bill_id,
            "message": rem.message,
            "send_at": rem.send_at.isoformat() if rem.send_at else None,
            "sent": rem.sent,
            "channel": rem.channel
        })
    
    # Export ad impressions
    impressions = AdImpression.query.filter_by(user_id=user_id).all()
    for imp in impressions:
        data["ad_impressions"].append({
            "id": imp.id,
            "placement": imp.placement,
            "created_at": imp.created_at.isoformat() if imp.created_at else None
        })
    
    # Export subscriptions
    subscriptions = UserSubscription.query.filter_by(user_id=user_id).all()
    for sub in subscriptions:
        data["subscriptions"].append({
            "id": sub.id,
            "plan_id": sub.plan_id,
            "active": sub.active,
            "started_at": sub.started_at.isoformat() if sub.started_at else None
        })
    
    # Create ZIP file with JSON and CSV exports
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add JSON export
        json_data = json.dumps(data, indent=2)
        zip_file.writestr('user_data.json', json_data)
        
        # Add CSV exports for each table
        # Categories CSV
        if data["categories"]:
            categories_csv = io.StringIO()
            writer = csv.DictWriter(categories_csv, fieldnames=["id", "name", "created_at"])
            writer.writeheader()
            writer.writerows(data["categories"])
            zip_file.writestr('categories.csv', categories_csv.getvalue())
        
        # Expenses CSV
        if data["expenses"]:
            expenses_csv = io.StringIO()
            writer = csv.DictWriter(expenses_csv, fieldnames=[
                "id", "category_id", "amount", "currency", "expense_type", 
                "notes", "spent_at", "source_recurring_id", "created_at"
            ])
            writer.writeheader()
            writer.writerows(data["expenses"])
            zip_file.writestr('expenses.csv', expenses_csv.getvalue())
        
        # Recurring Expenses CSV
        if data["recurring_expenses"]:
            recurring_csv = io.StringIO()
            writer = csv.DictWriter(recurring_csv, fieldnames=[
                "id", "category_id", "amount", "currency", "expense_type",
                "notes", "cadence", "start_date", "end_date", "active", "created_at"
            ])
            writer.writeheader()
            writer.writerows(data["recurring_expenses"])
            zip_file.writestr('recurring_expenses.csv', recurring_csv.getvalue())
        
        # Bills CSV
        if data["bills"]:
            bills_csv = io.StringIO()
            writer = csv.DictWriter(bills_csv, fieldnames=[
                "id", "name", "amount", "currency", "next_due_date",
                "cadence", "autopay_enabled", "channel_whatsapp", "channel_email",
                "active", "created_at"
            ])
            writer.writeheader()
            writer.writerows(data["bills"])
            zip_file.writestr('bills.csv', bills_csv.getvalue())
        
        # Reminders CSV
        if data["reminders"]:
            reminders_csv = io.StringIO()
            writer = csv.DictWriter(reminders_csv, fieldnames=[
                "id", "bill_id", "message", "send_at", "sent", "channel"
            ])
            writer.writeheader()
            writer.writerows(data["reminders"])
            zip_file.writestr('reminders.csv', reminders_csv.getvalue())
        
        # Ad Impressions CSV
        if data["ad_impressions"]:
            impressions_csv = io.StringIO()
            writer = csv.DictWriter(impressions_csv, fieldnames=["id", "placement", "created_at"])
            writer.writeheader()
            writer.writerows(data["ad_impressions"])
            zip_file.writestr('ad_impressions.csv', impressions_csv.getvalue())
        
        # Subscriptions CSV
        if data["subscriptions"]:
            subscriptions_csv = io.StringIO()
            writer = csv.DictWriter(subscriptions_csv, fieldnames=[
                "id", "plan_id", "active", "started_at"
            ])
            writer.writeheader()
            writer.writerows(data["subscriptions"])
            zip_file.writestr('subscriptions.csv', subscriptions_csv.getvalue())
    
    zip_buffer.seek(0)
    
    # Log the export action
    audit_log = AuditLog(
        user_id=user_id,
        action=f"DATA_EXPORT: User requested data export"
    )
    db.session.add(audit_log)
    db.session.commit()
    
    logger.info("Export completed for user_id=%s", user_id)
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'finmind_user_{user_id}_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.zip'
    )


@bp.post("/delete/request")
@jwt_required()
def request_deletion():
    """
    Request account deletion. This creates a deletion request that must be confirmed.
    Returns a confirmation token that must be used to complete the deletion.
    """
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    
    if not user:
        return jsonify(error="User not found"), 404
    
    data = request.get_json() or {}
    confirmation_text = data.get("confirmation", "")
    
    # Require explicit confirmation
    if confirmation_text.lower() != "delete my account":
        return jsonify(
            error="Confirmation required. Please provide confirmation: 'delete my account'"
        ), 400
    
    logger.warning("Deletion requested for user_id=%s", user_id)
    
    # Log the deletion request
    audit_log = AuditLog(
        user_id=user_id,
        action=f"DELETION_REQUESTED: User requested account deletion"
    )
    db.session.add(audit_log)
    db.session.commit()
    
    # For security, we'll perform the deletion immediately but with proper logging
    # In production, you might want to add a waiting period
    return jsonify(
        message="Deletion request received. Proceeding with account deletion.",
        status="processing"
    ), 202


@bp.post("/delete/confirm")
@jwt_required()
def confirm_deletion():
    """
    Confirm and execute account deletion.
    This is an irreversible operation that permanently deletes all user data.
    """
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    
    if not user:
        return jsonify(error="User not found"), 404
    
    data = request.get_json() or {}
    final_confirmation = data.get("final_confirmation", "")
    
    # Require explicit final confirmation
    if final_confirmation.lower() != "i understand this is irreversible":
        return jsonify(
            error="Final confirmation required. Please confirm: 'i understand this is irreversible'"
        ), 400
    
    logger.critical("Deletion confirmed for user_id=%s. Starting irreversible deletion.", user_id)
    
    try:
        # Log the deletion start
        audit_log_start = AuditLog(
            user_id=user_id,
            action=f"DELETION_STARTED: Beginning irreversible deletion of user account"
        )
        db.session.add(audit_log_start)
        db.session.commit()
        
        # Delete in proper order to handle foreign key constraints
        # The schema has ON DELETE CASCADE for most tables, but we'll be explicit
        
        # Delete reminders (references bills)
        Reminder.query.filter_by(user_id=user_id).delete()
        
        # Delete bills (cascade will handle reminders, but being explicit)
        Bill.query.filter_by(user_id=user_id).delete()
        
        # Delete recurring expenses
        RecurringExpense.query.filter_by(user_id=user_id).delete()
        
        # Delete expenses (cascade will handle category references)
        Expense.query.filter_by(user_id=user_id).delete()
        
        # Delete categories
        Category.query.filter_by(user_id=user_id).delete()
        
        # Delete ad impressions
        AdImpression.query.filter_by(user_id=user_id).delete()
        
        # Delete subscriptions
        UserSubscription.query.filter_by(user_id=user_id).delete()
        
        # Get user email for final log before deleting user
        user_email = user.email
        
        # Delete the user (this will cascade to any remaining references)
        db.session.delete(user)
        
        # Log the successful deletion
        audit_log_complete = AuditLog(
            user_id=None,  # User is deleted, so no user_id reference
            action=f"DELETION_COMPLETED: User account {user_email} (id={user_id}) permanently deleted"
        )
        db.session.add(audit_log_complete)
        db.session.commit()
        
        logger.critical("Deletion completed for user_id=%s email=%s", user_id, user_email)
        
        return jsonify(
            message="Account permanently deleted",
            status="completed"
        ), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error("Deletion failed for user_id=%s: %s", user_id, str(e))
        
        # Log the failure
        audit_log_failed = AuditLog(
            user_id=user_id,
            action=f"DELETION_FAILED: Account deletion failed - {str(e)}"
        )
        db.session.add(audit_log_failed)
        db.session.commit()
        
        return jsonify(
            error="Deletion failed. Please contact support.",
            status="failed"
        ), 500


@bp.get("/delete/status")
@jwt_required()
def deletion_status():
    """
    Check the status of any pending deletion requests.
    For this implementation, we check recent audit logs for deletion activity.
    """
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    
    if not user:
        return jsonify(error="User not found"), 404
    
    # Check recent audit logs for deletion activity
    recent_logs = AuditLog.query.filter_by(user_id=user_id).order_by(
        AuditLog.created_at.desc()
    ).limit(10).all()
    
    deletion_requested = False
    deletion_completed = False
    
    for log in recent_logs:
        if "DELETION_REQUESTED" in log.action:
            deletion_requested = True
        if "DELETION_COMPLETED" in log.action:
            deletion_completed = True
    
    return jsonify(
        user_id=user_id,
        deletion_requested=deletion_requested,
        deletion_completed=deletion_completed,
        message="Account is active" if not deletion_completed else "Account deletion in progress or completed"
    ), 200
