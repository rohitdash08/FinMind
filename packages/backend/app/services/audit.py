"""Audit logging service for GDPR compliance."""
from datetime import datetime
from typing import Optional
from ..extensions import db
from ..models import AuditLog


def log_audit_event(
    user_id: Optional[int],
    action: str,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> AuditLog:
    """Log an audit event for GDPR compliance.
    
    Args:
        user_id: The user ID associated with the action (None for unauthenticated)
        action: The action performed (e.g., 'pii_export', 'account_deletion')
        details: Optional JSON-serializable details about the action
        ip_address: Client IP address
        user_agent: Client user agent string
    
    Returns:
        The created AuditLog entry
    """
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.utcnow()
    )
    db.session.add(log_entry)
    db.session.commit()
    return log_entry


def get_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
):
    """Query audit logs with filters.
    
    Args:
        user_id: Filter by specific user
        action: Filter by action type
        start_date: Filter by start date
        end_date: Filter by end date
        limit: Maximum results to return
        offset: Pagination offset
    
    Returns:
        Tuple of (list of AuditLog entries, total count)
    """
    query = db.session.query(AuditLog)
    
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
    
    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    
    return logs, total


def get_user_audit_trail(user_id: int, limit: int = 100):
    """Get complete audit trail for a specific user.
    
    Args:
        user_id: The user ID to query
        limit: Maximum results to return
    
    Returns:
        List of AuditLog entries
    """
    return (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
