
"""
Notification priority and grouping system.
"""
from datetime import datetime, timedelta
from ..extensions import db
from enum import Enum


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationGroup(db.Model):
    __tablename__ = "notification_groups"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_key = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.String(20), default=Priority.NORMAL.value)
    count = db.Column(db.Integer, default=1)
    last_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def create_notification(user_id: int, message: str, priority: str = "normal", group_key: str = None) -> dict:
    """Create or update a grouped notification."""
    if group_key:
        existing = NotificationGroup.query.filter_by(
            user_id=user_id, group_key=group_key
        ).first()
        
        if existing:
            existing.count += 1
            existing.last_message = message
            existing.updated_at = datetime.utcnow()
            if priority_order(priority) > priority_order(existing.priority):
                existing.priority = priority
            db.session.commit()
            return {"grouped": True, "count": existing.count}
    
    group = NotificationGroup(
        user_id=user_id,
        group_key=group_key or f"single_{datetime.utcnow().timestamp()}",
        priority=priority,
        last_message=message,
    )
    db.session.add(group)
    db.session.commit()
    return {"grouped": False, "count": 1}


def get_user_notifications(user_id: int) -> list:
    """Get all notification groups for a user.
    
    Args:
        user_id: User ID to fetch notifications for
        
    Returns:
        List of NotificationGroup objects for the user
    """
    return NotificationGroup.query.filter_by(user_id=user_id).order_by(
        NotificationGroup.updated_at.desc()
    ).all()


def priority_order(priority: str) -> int:
    """Get numeric order for priority comparison."""
    return {"low": 0, "normal": 1, "high": 2, "urgent": 3}.get(priority, 1)
