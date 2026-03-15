"""Notification priority & grouping service.

Provides intelligent notification management with priority levels,
category-based grouping, batch operations, and analytics.
"""

from datetime import datetime, timedelta
from sqlalchemy import func, case, desc
from app.extensions import db
from app.models import Notification


# Priority weights for sorting (higher = more important)
PRIORITY_WEIGHTS = {
    "critical": 4,
    "high": 3,
    "normal": 2,
    "low": 1,
}

# Default categories
CATEGORIES = [
    "general",
    "bill_due",
    "budget_alert",
    "transaction",
    "security",
    "insight",
    "reminder",
    "system",
]


def create_notification(
    user_id,
    title,
    message,
    priority="normal",
    category="general",
    group_key=None,
    action_url=None,
    action_type=None,
    metadata=None,
    expires_at=None,
):
    """Create a new notification."""
    if priority not in PRIORITY_WEIGHTS:
        priority = "normal"
    if category not in CATEGORIES:
        category = "general"

    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        priority=priority,
        category=category,
        group_key=group_key,
        action_url=action_url,
        action_type=action_type,
        extra_data=metadata or {},
        expires_at=expires_at,
    )
    db.session.add(notification)
    db.session.commit()
    return _notification_to_dict(notification)


def get_notifications(
    user_id,
    category=None,
    priority=None,
    is_read=None,
    group_key=None,
    limit=50,
    offset=0,
):
    """Get notifications for a user, sorted by priority then recency."""
    query = Notification.query.filter_by(
        user_id=user_id, is_dismissed=False
    )

    # Filter expired notifications
    query = query.filter(
        db.or_(
            Notification.expires_at.is_(None),
            Notification.expires_at > datetime.utcnow(),
        )
    )

    if category:
        query = query.filter_by(category=category)
    if priority:
        query = query.filter_by(priority=priority)
    if is_read is not None:
        query = query.filter_by(is_read=is_read)
    if group_key:
        query = query.filter_by(group_key=group_key)

    # Sort by priority weight (descending) then created_at (descending)
    priority_order = case(
        (Notification.priority == "critical", 4),
        (Notification.priority == "high", 3),
        (Notification.priority == "normal", 2),
        (Notification.priority == "low", 1),
        else_=0,
    )

    query = query.order_by(desc(priority_order), desc(Notification.created_at))
    total = query.count()
    notifications = query.limit(limit).offset(offset).all()

    return {
        "notifications": [_notification_to_dict(n) for n in notifications],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_grouped_notifications(user_id, category=None):
    """Get notifications grouped by group_key and category."""
    query = Notification.query.filter_by(
        user_id=user_id, is_dismissed=False
    ).filter(
        db.or_(
            Notification.expires_at.is_(None),
            Notification.expires_at > datetime.utcnow(),
        )
    )

    if category:
        query = query.filter_by(category=category)

    notifications = query.order_by(
        desc(Notification.created_at)
    ).all()

    groups = {}
    ungrouped = []

    for n in notifications:
        d = _notification_to_dict(n)
        if n.group_key:
            if n.group_key not in groups:
                groups[n.group_key] = {
                    "group_key": n.group_key,
                    "category": n.category,
                    "count": 0,
                    "unread_count": 0,
                    "latest": None,
                    "notifications": [],
                }
            group = groups[n.group_key]
            group["count"] += 1
            if not n.is_read:
                group["unread_count"] += 1
            group["notifications"].append(d)
            if group["latest"] is None:
                group["latest"] = d
        else:
            ungrouped.append(d)

    # Sort groups by highest priority notification in each group
    sorted_groups = sorted(
        groups.values(),
        key=lambda g: max(
            PRIORITY_WEIGHTS.get(n.get("priority", "normal"), 0)
            for n in g["notifications"]
        ),
        reverse=True,
    )

    return {
        "groups": sorted_groups,
        "ungrouped": ungrouped,
        "total_groups": len(sorted_groups),
        "total_ungrouped": len(ungrouped),
    }


def mark_read(notification_id, user_id):
    """Mark a single notification as read."""
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return None
    n.is_read = True
    n.updated_at = datetime.utcnow()
    db.session.commit()
    return _notification_to_dict(n)


def mark_all_read(user_id, category=None, group_key=None):
    """Mark all notifications as read with optional filters."""
    query = Notification.query.filter_by(user_id=user_id, is_read=False)
    if category:
        query = query.filter_by(category=category)
    if group_key:
        query = query.filter_by(group_key=group_key)

    count = query.update(
        {"is_read": True, "updated_at": datetime.utcnow()},
        synchronize_session="fetch",
    )
    db.session.commit()
    return {"marked_read": count}


def dismiss_notification(notification_id, user_id):
    """Dismiss (soft-delete) a notification."""
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return None
    n.is_dismissed = True
    n.updated_at = datetime.utcnow()
    db.session.commit()
    return _notification_to_dict(n)


def dismiss_group(user_id, group_key):
    """Dismiss all notifications in a group."""
    count = Notification.query.filter_by(
        user_id=user_id, group_key=group_key, is_dismissed=False
    ).update(
        {"is_dismissed": True, "updated_at": datetime.utcnow()},
        synchronize_session="fetch",
    )
    db.session.commit()
    return {"dismissed": count}


def get_unread_count(user_id):
    """Get unread notification counts by priority and category."""
    base = Notification.query.filter_by(
        user_id=user_id, is_read=False, is_dismissed=False
    ).filter(
        db.or_(
            Notification.expires_at.is_(None),
            Notification.expires_at > datetime.utcnow(),
        )
    )

    total = base.count()

    by_priority = dict(
        db.session.query(
            Notification.priority, func.count(Notification.id)
        )
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,
            Notification.is_dismissed == False,
            db.or_(
                Notification.expires_at.is_(None),
                Notification.expires_at > datetime.utcnow(),
            ),
        )
        .group_by(Notification.priority)
        .all()
    )

    by_category = dict(
        db.session.query(
            Notification.category, func.count(Notification.id)
        )
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,
            Notification.is_dismissed == False,
            db.or_(
                Notification.expires_at.is_(None),
                Notification.expires_at > datetime.utcnow(),
            ),
        )
        .group_by(Notification.category)
        .all()
    )

    return {
        "total": total,
        "by_priority": by_priority,
        "by_category": by_category,
    }


def get_notification_stats(user_id, days=30):
    """Get notification statistics for analytics."""
    since = datetime.utcnow() - timedelta(days=days)

    base = Notification.query.filter(
        Notification.user_id == user_id,
        Notification.created_at >= since,
    )

    total = base.count()
    read = base.filter_by(is_read=True).count()
    dismissed = base.filter_by(is_dismissed=True).count()
    unread = base.filter_by(is_read=False, is_dismissed=False).count()

    by_priority = dict(
        db.session.query(
            Notification.priority, func.count(Notification.id)
        )
        .filter(
            Notification.user_id == user_id,
            Notification.created_at >= since,
        )
        .group_by(Notification.priority)
        .all()
    )

    by_category = dict(
        db.session.query(
            Notification.category, func.count(Notification.id)
        )
        .filter(
            Notification.user_id == user_id,
            Notification.created_at >= since,
        )
        .group_by(Notification.category)
        .all()
    )

    # Daily volume
    daily = (
        db.session.query(
            func.date(Notification.created_at).label("date"),
            func.count(Notification.id).label("count"),
        )
        .filter(
            Notification.user_id == user_id,
            Notification.created_at >= since,
        )
        .group_by(func.date(Notification.created_at))
        .order_by(func.date(Notification.created_at))
        .all()
    )

    return {
        "total": total,
        "read": read,
        "unread": unread,
        "dismissed": dismissed,
        "read_rate": round(read / total, 3) if total > 0 else 0.0,
        "by_priority": by_priority,
        "by_category": by_category,
        "daily_volume": [{"date": str(d.date), "count": d.count} for d in daily],
        "period_days": days,
    }


def _notification_to_dict(n):
    """Convert notification model to dict."""
    return {
        "id": n.id,
        "user_id": n.user_id,
        "title": n.title,
        "message": n.message,
        "priority": n.priority,
        "category": n.category,
        "group_key": n.group_key,
        "is_read": n.is_read,
        "is_dismissed": n.is_dismissed,
        "action_url": n.action_url,
        "action_type": n.action_type,
        "extra_data": n.extra_data,
        "expires_at": n.expires_at.isoformat() if n.expires_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }
