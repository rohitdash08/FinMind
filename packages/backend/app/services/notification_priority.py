"""
Notification priority & grouping system for FinMind.
Groups and prioritizes alerts for clarity.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any


class NotificationPriority(IntEnum):
    """
    Numeric priority levels.  Higher = more urgent.
    """
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class NotificationGroup(str):
    """Canonical group names."""
    BILLS = "bills"
    REMINDERS = "reminders"
    ALERTS = "alerts"
    INSIGHTS = "insights"
    SYSTEM = "system"


# Mapping from arbitrary category strings to (group, priority)
_CATEGORY_MAP: dict[str, tuple[str, NotificationPriority]] = {
    # Bills
    "bill_due_today": (NotificationGroup.BILLS, NotificationPriority.CRITICAL),
    "bill_overdue": (NotificationGroup.BILLS, NotificationPriority.CRITICAL),
    "bill_due_soon": (NotificationGroup.BILLS, NotificationPriority.HIGH),
    "bill_paid": (NotificationGroup.BILLS, NotificationPriority.NORMAL),
    "autopay_scheduled": (NotificationGroup.BILLS, NotificationPriority.NORMAL),
    # Reminders
    "reminder": (NotificationGroup.REMINDERS, NotificationPriority.NORMAL),
    "reminder_urgent": (NotificationGroup.REMINDERS, NotificationPriority.HIGH),
    # Alerts
    "budget_exceeded": (NotificationGroup.ALERTS, NotificationPriority.HIGH),
    "unusual_spending": (NotificationGroup.ALERTS, NotificationPriority.HIGH),
    "large_transaction": (NotificationGroup.ALERTS, NotificationPriority.HIGH),
    "low_balance": (NotificationGroup.ALERTS, NotificationPriority.CRITICAL),
    "subscription_increase": (NotificationGroup.ALERTS, NotificationPriority.NORMAL),
    "anomaly": (NotificationGroup.ALERTS, NotificationPriority.HIGH),
    # Insights
    "weekly_summary": (NotificationGroup.INSIGHTS, NotificationPriority.LOW),
    "monthly_report": (NotificationGroup.INSIGHTS, NotificationPriority.LOW),
    "savings_milestone": (NotificationGroup.INSIGHTS, NotificationPriority.NORMAL),
    "tip": (NotificationGroup.INSIGHTS, NotificationPriority.LOW),
    # System
    "system": (NotificationGroup.SYSTEM, NotificationPriority.NORMAL),
    "security_alert": (NotificationGroup.SYSTEM, NotificationPriority.CRITICAL),
    "login_anomaly": (NotificationGroup.SYSTEM, NotificationPriority.CRITICAL),
}

_DEFAULT_CATEGORY = (NotificationGroup.SYSTEM, NotificationPriority.NORMAL)


def classify(category: str) -> tuple[str, NotificationPriority]:
    """Return (group, priority) for a category string."""
    return _CATEGORY_MAP.get(category, _DEFAULT_CATEGORY)


def enrich_notification(notif: dict[str, Any]) -> dict[str, Any]:
    """
    Add ``group`` and ``priority`` fields to a raw notification dict.
    Input dict must have at least a ``category`` key.
    """
    category = notif.get("category", "system")
    group, priority = classify(category)
    return {
        **notif,
        "group": group,
        "priority": int(priority),
        "priority_label": priority.name.lower(),
    }


def group_and_sort(
    notifications: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Group a list of notification dicts and sort each group by priority (desc)
    then by ``created_at`` (desc).

    Returns an ordered dict: groups sorted by their max priority desc.
    """
    enriched = [enrich_notification(n) for n in notifications]

    # Build groups
    groups: dict[str, list[dict]] = {}
    for notif in enriched:
        g = notif["group"]
        groups.setdefault(g, []).append(notif)

    # Sort within each group
    for g in groups:
        groups[g].sort(
            key=lambda n: (
                -n["priority"],
                n.get("created_at", "") or "",
            ),
            reverse=False,
        )
        # secondary: reverse created_at to show newest first within same priority
        groups[g].sort(key=lambda n: -n["priority"])

    # Sort groups by max priority
    ordered: dict[str, list[dict]] = dict(
        sorted(
            groups.items(),
            key=lambda kv: max(n["priority"] for n in kv[1]),
            reverse=True,
        )
    )
    return ordered


def flatten_sorted(
    notifications: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return a flat sorted list ordered by priority desc, then created_at desc.
    """
    enriched = [enrich_notification(n) for n in notifications]
    enriched.sort(
        key=lambda n: (
            -n["priority"],
            -(datetime.fromisoformat(n["created_at"]).timestamp()
              if n.get("created_at") else 0),
        )
    )
    if limit:
        return enriched[:limit]
    return enriched


def summary(
    notifications: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Return a high-level summary: counts per group and per priority.
    """
    enriched = [enrich_notification(n) for n in notifications]
    by_group: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for n in enriched:
        by_group[n["group"]] = by_group.get(n["group"], 0) + 1
        lbl = n["priority_label"]
        by_priority[lbl] = by_priority.get(lbl, 0) + 1
    critical = by_priority.get("critical", 0)
    return {
        "total": len(enriched),
        "critical": critical,
        "by_group": by_group,
        "by_priority": by_priority,
        "has_critical": critical > 0,
    }