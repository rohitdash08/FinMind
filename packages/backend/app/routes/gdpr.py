"""GDPR PII Export & Delete Workflow Routes

This module provides endpoints for GDPR-compliant data export and deletion.
- Export: Generates downloadable package with all user PII
- Delete: Irreversible deletion with audit trail
- Audit: Logs all export and deletion actions
"""

import json
import zipfile
import io
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import text

from ..extensions import db
from ..models import (
    AuditLog,
    User,
    Category,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    AdImpression,
    UserSubscription,
)

bp = Blueprint("gdpr", __name__, url_prefix="/api/gdpr")


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Get auth token from header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        
        token = auth_header.replace("Bearer ", "")
        
        # In a real implementation, verify JWT token
        # For now, we'll get user_id from a simple lookup
        # This integrates with existing auth system
        from ..routes.auth import verify_token
        user_id = verify_token(token)
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        g.user_id = user_id
        return f(*args, **kwargs)
    return decorated


def log_audit_action(user_id: int, action: str, details: dict = None):
    """Log GDPR-related actions to audit trail."""
    audit_entry = AuditLog(
        user_id=user_id,
        action=f"GDPR_{action}",
        created_at=datetime.utcnow()
    )
    db.session.add(audit_entry)
    db.session.commit()


def get_user_pii_data(user_id: int) -> dict:
    """Collect all PII data for a user across all tables."""
    user = User.query.get(user_id)
    if not user:
        return {}
    
    # Collect all user-related data
    data = {
        "export_metadata": {
            "exported_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "format_version": "1.0",
            "gdpr_request_type": "data_export"
        },
        "user_profile": {
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
            for c in Category.query.filter_by(user_id=user_id).all()
        ],
        "expenses": [
            {
                "id": e.id,
                "amount": float(e.amount) if e.amount else None,
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "category_id": e.category_id,
                "source_recurring_id": e.source_recurring_id,
            }
            for e in Expense.query.filter_by(user_id=user_id).all()
        ],
        "recurring_expenses": [
            {
                "id": re.id,
                "amount": float(re.amount) if re.amount else None,
                "currency": re.currency,
                "expense_type": re.expense_type,
                "notes": re.notes,
                "cadence": re.cadence.value if re.cadence else None,
                "start_date": re.start_date.isoformat() if re.start_date else None,
                "end_date": re.end_date.isoformat() if re.end_date else None,
                "active": re.active,
                "created_at": re.created_at.isoformat() if re.created_at else None,
                "category_id": re.category_id,
            }
            for re in RecurringExpense.query.filter_by(user_id=user_id).all()
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
            for b in Bill.query.filter_by(user_id=user_id).all()
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
            for r in Reminder.query.filter_by(user_id=user_id).all()
        ],
        "ad_impressions": [
            {
                "id": ai.id,
                "placement": ai.placement,
                "created_at": ai.created_at.isoformat() if ai.created_at else None,
            }
            for ai in AdImpression.query.filter_by(user_id=user_id).all()
        ],
        "subscriptions": [
            {
                "id": us.id,
                "plan_id": us.plan_id,
                "active": us.active,
                "started_at": us.started_at.isoformat() if us.started_at else None,
            }
            for us in UserSubscription.query.filter_by(user_id=user_id).all()
        ],
        "audit_logs": [
            {
                "id": al.id,
                "action": al.action,
                "created_at": al.created_at.isoformat() if al.created_at else None,
            }
            for al in AuditLog.query.filter_by(user_id=user_id).all()
        ],
    }
    
    return data


@bp.route("/export", methods=["GET"])
@require_auth
def export_data():
    """
    Export all user PII data as a downloadable ZIP package.
    
    Returns:
        ZIP file containing:
        - user_data.json: All user data in structured JSON
        - README.txt: Information about the export
    """
    user_id = g.user_id
    
    # Generate data export
    user_data = get_user_pii_data(user_id)
    
    if not user_data:
        return jsonify({"error": "User not found"}), 404
    
    # Create ZIP file in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add user data JSON
        zf.writestr(
            "user_data.json",
            json.dumps(user_data, indent=2, default=str)
        )
        
        # Add README
        readme_content = f"""FinMind Personal Data Export
=============================

Generated: {datetime.utcnow().isoformat()}
User ID: {user_id}

This archive contains your personal data as stored in FinMind.

Files:
- user_data.json: Complete export of your data including:
  * Profile information
  * Categories
  * Expenses (regular and recurring)
  * Bills and reminders
  * Ad impressions
  * Subscription history
  * Audit logs

For questions about your data, contact support.
"""
        zf.writestr("README.txt", readme_content)
    
    memory_file.seek(0)
    
    # Log the export action
    log_audit_action(user_id, "DATA_EXPORT", {"ip": request.remote_addr})
    
    # Generate filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"finmind_data_export_{timestamp}.zip"
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=filename
    )


@bp.route("/export/preview", methods=["GET"])
@require_auth
def export_preview():
    """
    Preview what data will be exported (without downloading).
    
    Returns:
        JSON summary of data categories and counts.
    """
    user_id = g.user_id
    
    # Get counts for each data type
    summary = {
        "preview_generated_at": datetime.utcnow().isoformat(),
        "data_categories": {
            "profile": True,
            "categories": Category.query.filter_by(user_id=user_id).count(),
            "expenses": Expense.query.filter_by(user_id=user_id).count(),
            "recurring_expenses": RecurringExpense.query.filter_by(user_id=user_id).count(),
            "bills": Bill.query.filter_by(user_id=user_id).count(),
            "reminders": Reminder.query.filter_by(user_id=user_id).count(),
            "ad_impressions": AdImpression.query.filter_by(user_id=user_id).count(),
            "subscriptions": UserSubscription.query.filter_by(user_id=user_id).count(),
            "audit_logs": AuditLog.query.filter_by(user_id=user_id).count(),
        }
    }
    
    return jsonify(summary)


@bp.route("/delete", methods=["POST"])
@require_auth
def delete_data():
    """
    Irreversibly delete all user PII data (GDPR Right to be Forgotten).
    
    Request Body:
        - confirmation_token (str): Required confirmation string
        
    Returns:
        JSON with deletion confirmation and audit log ID.
    """
    user_id = g.user_id
    data = request.get_json() or {}
    
    # Require explicit confirmation
    confirmation = data.get("confirmation_token", "")
    if confirmation != "DELETE_MY_DATA_PERMANENTLY":
        return jsonify({
            "error": "Invalid confirmation token",
            "message": "To delete your data, provide confirmation_token: 'DELETE_MY_DATA_PERMANENTLY'"
        }), 400
    
    # Get user info before deletion for audit
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user_email = user.email
    
    # Log deletion request before execution
    deletion_log = AuditLog(
        user_id=user_id,
        action="GDPR_DATA_DELETION_REQUESTED",
        created_at=datetime.utcnow()
    )
    db.session.add(deletion_log)
    db.session.commit()
    
    try:
        # Delete all user data in correct order (respecting FK constraints)
        # 1. Delete child records first
        Expense.query.filter_by(user_id=user_id).delete()
        RecurringExpense.query.filter_by(user_id=user_id).delete()
        Reminder.query.filter_by(user_id=user_id).delete()
        Bill.query.filter_by(user_id=user_id).delete()
        Category.query.filter_by(user_id=user_id).delete()
        AdImpression.query.filter_by(user_id=user_id).delete()
        UserSubscription.query.filter_by(user_id=user_id).delete()
        
        # 2. Delete audit logs (optional - you might want to keep these)
        # Keeping audit logs for compliance, but anonymizing user_id
        AuditLog.query.filter_by(user_id=user_id).update(
            {"user_id": None, "action": f"ANONYMIZED_DELETED_USER_{user_id}"}
        )
        
        # 3. Finally delete the user
        User.query.filter_by(id=user_id).delete()
        
        # Commit all deletions
        db.session.commit()
        
        # Log successful deletion
        final_log = AuditLog(
            user_id=None,  # User no longer exists
            action=f"GDPR_DATA_DELETION_COMPLETED_{user_id}",
            created_at=datetime.utcnow()
        )
        db.session.add(final_log)
        db.session.commit()
        
        return jsonify({
            "message": "All personal data has been permanently deleted",
            "deleted_user_email": user_email,
            "deletion_completed_at": datetime.utcnow().isoformat(),
            "audit_log_id": final_log.id,
            "note": "This action cannot be undone. Your account and all data are gone."
        }), 200
        
    except Exception as e:
        db.session.rollback()
        
        # Log the failure
        error_log = AuditLog(
            user_id=user_id,
            action="GDPR_DATA_DELETION_FAILED",
            created_at=datetime.utcnow()
        )
        db.session.add(error_log)
        db.session.commit()
        
        return jsonify({
            "error": "Data deletion failed",
            "message": str(e)
        }), 500


@bp.route("/delete/preview", methods=["GET"])
@require_auth
def delete_preview():
    """
    Preview what will be deleted before confirming deletion.
    
    Returns:
        JSON summary of data to be deleted.
    """
    user_id = g.user_id
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    preview = {
        "warning": "This is a preview of what will be PERMANENTLY DELETED",
        "user_email": user.email,
        "data_to_be_deleted": {
            "profile": True,
            "categories_count": Category.query.filter_by(user_id=user_id).count(),
            "expenses_count": Expense.query.filter_by(user_id=user_id).count(),
            "recurring_expenses_count": RecurringExpense.query.filter_by(user_id=user_id).count(),
            "bills_count": Bill.query.filter_by(user_id=user_id).count(),
            "reminders_count": Reminder.query.filter_by(user_id=user_id).count(),
            "ad_impressions_count": AdImpression.query.filter_by(user_id=user_id).count(),
            "subscriptions_count": UserSubscription.query.filter_by(user_id=user_id).count(),
        },
        "required_confirmation": "DELETE_MY_DATA_PERMANENTLY",
        "consequences": [
            "Your account will be permanently closed",
            "All financial data will be erased",
            "This action CANNOT be undone",
            "You will need to create a new account to use FinMind again"
        ]
    }
    
    return jsonify(preview)


@bp.route("/audit-log", methods=["GET"])
@require_auth
def get_audit_log():
    """
    Get GDPR-related audit log entries for the authenticated user.
    
    Returns:
        JSON list of audit log entries.
    """
    user_id = g.user_id
    
    logs = AuditLog.query.filter(
        AuditLog.user_id == user_id,
        AuditLog.action.like("GDPR_%")
    ).order_by(AuditLog.created_at.desc()).all()
    
    return jsonify({
        "audit_entries": [
            {
                "id": log.id,
                "action": log.action,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    })


# Public GDPR info endpoint (no auth required)
@bp.route("/info", methods=["GET"])
def gdpr_info():
    """
    Get information about GDPR rights and how to exercise them.
    
    Returns:
        JSON with GDPR information and available endpoints.
    """
    return jsonify({
        "service": "FinMind",
        "gdpr_compliance": {
            "right_to_access": {
                "description": "Download all your personal data",
                "endpoint": "GET /api/gdpr/export",
                "endpoint_preview": "GET /api/gdpr/export/preview"
            },
            "right_to_erasure": {
                "description": "Permanently delete all your personal data",
                "endpoint": "POST /api/gdpr/delete",
                "endpoint_preview": "GET /api/gdpr/delete/preview",
                "warning": "This action is irreversible"
            },
            "audit_trail": {
                "description": "View GDPR-related actions taken on your account",
                "endpoint": "GET /api/gdpr/audit-log"
            }
        },
        "data_retention": {
            "active_accounts": "Data retained while account is active",
            "deleted_accounts": "Data permanently removed within 30 days of deletion request",
            "audit_logs": "Anonymized and retained for 7 years for legal compliance"
        },
        "contact": "For GDPR-related inquiries, contact support@finmind.app"
    })
