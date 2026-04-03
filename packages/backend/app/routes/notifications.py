"""
Notification priority & grouping endpoints.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Reminder, Bill
from ..services.notification_priority import (
    enrich_notification,
    group_and_sort,
    flatten_sorted,
    summary,
    classify,
    _CATEGORY_MAP,
    NotificationPriority,
)
import logging
from datetime import datetime, timedelta

bp = Blueprint("notifications", __name__)
logger = logging.getLogger("finmind.notifications")


def _build_notifications_from_db(user_id: int) -> list[dict]:
    """
    Build a unified list of notification dicts from live DB data (bills + reminders).
    """
    now = datetime.utcnow()
    today = now.date()
    notifications = []

    # --- Bills ---
    bills = db.session.query(Bill).filter_by(user_id=user_id, active=True).all()
    for bill in bills:
        due = bill.next_due_date
        if due is None:
            continue
        due_date = due.date() if isinstance(due, datetime) else due
        days_until = (due_date - today).days

        if days_until < 0:
            cat = "bill_overdue"
        elif days_until == 0:
            cat = "bill_due_today"
        elif days_until <= 3:
            cat = "bill_due_soon"
        else:
            continue  # not urgent enough

        notifications.append({
            "id": f"bill_{bill.id}",
            "category": cat,
            "title": f"Bill due: {bill.name}",
            "message": (
                f"Your bill '{bill.name}' of ${bill.amount:.2f} "
                f"{'was due' if days_until < 0 else 'is due'} "
                f"{'today' if days_until == 0 else f'in {days_until} day(s)' if days_until > 0 else f'{-days_until} day(s) ago'}."
            ),
            "amount": float(bill.amount),
            "bill_id": bill.id,
            "created_at": now.isoformat(),
        })

    # --- Reminders ---
    reminders = (
        db.session.query(Reminder)
        .filter_by(user_id=user_id, sent=False)
        .filter(Reminder.send_at <= now + timedelta(hours=24))
        .all()
    )
    for reminder in reminders:
        overdue = reminder.send_at < now
        cat = "reminder_urgent" if overdue else "reminder"
        notifications.append({
            "id": f"reminder_{reminder.id}",
            "category": cat,
            "title": "Reminder" + (" (overdue)" if overdue else ""),
            "message": reminder.message,
            "send_at": reminder.send_at.isoformat(),
            "channel": reminder.channel,
            "reminder_id": reminder.id,
            "created_at": reminder.send_at.isoformat(),
        })

    return notifications


@bp.get("")
@jwt_required()
def list_notifications():
    """
    GET /api/notifications
    Returns grouped and prioritized notifications.

    Query params:
      - view: "grouped" (default) | "flat"
      - limit: int (only for flat view)
      - priority: "low"|"normal"|"high"|"critical" (filter)
    """
    uid = int(get_jwt_identity())
    view = request.args.get("view", "grouped")
    limit_param = request.args.get("limit")
    priority_filter = request.args.get("priority")

    notifications = _build_notifications_from_db(uid)

    # Optional priority filter
    if priority_filter:
        try:
            min_priority = NotificationPriority[priority_filter.upper()]
            notifications = [
                n for n in notifications
                if classify(n.get("category", "system"))[1] >= min_priority
            ]
        except KeyError:
            return jsonify(error=f"Invalid priority: {priority_filter}. Use low, normal, high, critical."), 400

    if view == "flat":
        limit = int(limit_param) if limit_param else None
        result = flatten_sorted(notifications, limit=limit)
        return jsonify({"view": "flat", "total": len(result), "notifications": result})

    # Default: grouped
    grouped = group_and_sort(notifications)
    groups_list = [
        {
            "group": group_name,
            "count": len(items),
            "max_priority": max(n["priority"] for n in items),
            "notifications": items,
        }
        for group_name, items in grouped.items()
    ]
    return jsonify({
        "view": "grouped",
        "total": sum(g["count"] for g in groups_list),
        "groups": groups_list,
    })


@bp.get("/summary")
@jwt_required()
def notification_summary():
    """
    GET /api/notifications/summary
    Returns counts by group and priority level.
    """
    uid = int(get_jwt_identity())
    notifications = _build_notifications_from_db(uid)
    return jsonify(summary(notifications))


@bp.post("/classify")
@jwt_required()
def classify_notification():
    """
    POST /api/notifications/classify
    Body: {"category": "bill_due_today"} or {"notifications": [...]}
    Returns enriched notification(s) with group + priority fields.
    """
    data = request.get_json() or {}

    if "notifications" in data:
        items = data["notifications"]
        if not isinstance(items, list) or len(items) > 100:
            return jsonify(error="Provide a list of up to 100 notifications."), 400
        enriched = [enrich_notification(n) for n in items]
        return jsonify({"classified": enriched})

    if "category" not in data:
        return jsonify(error="Provide 'category' or 'notifications'."), 400

    group, priority = classify(data["category"])
    return jsonify({
        "category": data["category"],
        "group": group,
        "priority": int(priority),
        "priority_label": priority.name.lower(),
    })


@bp.get("/categories")
@jwt_required()
def list_categories():
    """
    GET /api/notifications/categories
    Returns all known categories with their group and priority.
    """
    cats = [
        {
            "category": cat,
            "group": group,
            "priority": int(prio),
            "priority_label": prio.name.lower(),
        }
        for cat, (group, prio) in sorted(_CATEGORY_MAP.items())
    ]
    return jsonify({"categories": cats, "total": len(cats)})