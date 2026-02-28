"""Notification priority and grouping system.

Groups and prioritizes alerts for clarity, reducing notification
fatigue while ensuring critical alerts are never missed.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class Priority(str, Enum):
    CRITICAL = "critical"   # Overdraft, failed payment, security
    HIGH = "high"           # Bill due today, large expense
    MEDIUM = "medium"       # Bill due this week, budget warning
    LOW = "low"             # Tips, insights, weekly summary
    INFO = "info"           # System updates, feature announcements


class NotificationGroup(str, Enum):
    BILLS = "bills"
    EXPENSES = "expenses"
    BUDGET = "budget"
    SECURITY = "security"
    INSIGHTS = "insights"
    SYSTEM = "system"


# Priority rules: condition -> priority mapping
PRIORITY_RULES = {
    "bill_overdue": Priority.CRITICAL,
    "payment_failed": Priority.CRITICAL,
    "security_alert": Priority.CRITICAL,
    "bill_due_today": Priority.HIGH,
    "large_expense": Priority.HIGH,
    "budget_exceeded": Priority.HIGH,
    "bill_due_week": Priority.MEDIUM,
    "budget_warning": Priority.MEDIUM,
    "recurring_charge": Priority.MEDIUM,
    "savings_milestone": Priority.LOW,
    "spending_insight": Priority.LOW,
    "weekly_summary": Priority.LOW,
    "feature_update": Priority.INFO,
    "tip": Priority.INFO,
}

# Group mapping
GROUP_RULES = {
    "bill_overdue": NotificationGroup.BILLS,
    "bill_due_today": NotificationGroup.BILLS,
    "bill_due_week": NotificationGroup.BILLS,
    "payment_failed": NotificationGroup.BILLS,
    "large_expense": NotificationGroup.EXPENSES,
    "recurring_charge": NotificationGroup.EXPENSES,
    "budget_exceeded": NotificationGroup.BUDGET,
    "budget_warning": NotificationGroup.BUDGET,
    "security_alert": NotificationGroup.SECURITY,
    "spending_insight": NotificationGroup.INSIGHTS,
    "savings_milestone": NotificationGroup.INSIGHTS,
    "weekly_summary": NotificationGroup.INSIGHTS,
    "feature_update": NotificationGroup.SYSTEM,
    "tip": NotificationGroup.SYSTEM,
}


class Notification:
    """A single notification with priority and grouping."""

    def __init__(self, event_type: str, title: str, message: str,
                 user_id: int, data: Optional[Dict] = None):
        self.id = f"{user_id}:{event_type}:{int(datetime.utcnow().timestamp())}"
        self.event_type = event_type
        self.title = title
        self.message = message
        self.user_id = user_id
        self.data = data or {}
        self.priority = PRIORITY_RULES.get(event_type, Priority.INFO)
        self.group = GROUP_RULES.get(event_type, NotificationGroup.SYSTEM)
        self.created_at = datetime.utcnow()
        self.read = False
        self.dismissed = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "group": self.group.value,
            "created_at": self.created_at.isoformat(),
            "read": self.read,
            "dismissed": self.dismissed,
            "data": self.data,
        }


class NotificationManager:
    """Manages notification priority, grouping, and delivery."""

    # Max notifications per group before collapsing
    GROUP_COLLAPSE_THRESHOLD = 5

    def __init__(self):
        self._notifications: Dict[int, List[Notification]] = {}
        self._preferences: Dict[int, Dict] = {}

    def notify(self, event_type: str, title: str, message: str,
               user_id: int, data: Optional[Dict] = None) -> Notification:
        """Create and store a notification."""
        n = Notification(event_type, title, message, user_id, data)
        if user_id not in self._notifications:
            self._notifications[user_id] = []
        self._notifications[user_id].append(n)
        return n

    def get_notifications(self, user_id: int, unread_only: bool = False,
                          group: Optional[str] = None,
                          priority: Optional[str] = None,
                          limit: int = 50) -> List[Dict]:
        """Get notifications for a user, sorted by priority then time."""
        notes = self._notifications.get(user_id, [])
        if unread_only:
            notes = [n for n in notes if not n.read]
        if group:
            notes = [n for n in notes if n.group.value == group]
        if priority:
            notes = [n for n in notes if n.priority.value == priority]

        priority_order = {
            Priority.CRITICAL: 0, Priority.HIGH: 1,
            Priority.MEDIUM: 2, Priority.LOW: 3, Priority.INFO: 4,
        }
        notes.sort(key=lambda n: (priority_order.get(n.priority, 5),
                                   -n.created_at.timestamp()))
        return [n.to_dict() for n in notes[:limit]]

    def get_grouped(self, user_id: int, unread_only: bool = True) -> Dict:
        """Get notifications grouped by category with counts."""
        notes = self._notifications.get(user_id, [])
        if unread_only:
            notes = [n for n in notes if not n.read]

        groups: Dict[str, List] = {}
        for n in notes:
            g = n.group.value
            if g not in groups:
                groups[g] = []
            groups[g].append(n.to_dict())

        result = {}
        for g, items in groups.items():
            count = len(items)
            collapsed = count > self.GROUP_COLLAPSE_THRESHOLD
            result[g] = {
                "count": count,
                "collapsed": collapsed,
                "items": items[:self.GROUP_COLLAPSE_THRESHOLD] if collapsed else items,
                "summary": f"{count} {g} notifications" if collapsed else None,
            }
        return result

    def mark_read(self, user_id: int, notification_id: str) -> bool:
        """Mark a notification as read."""
        for n in self._notifications.get(user_id, []):
            if n.id == notification_id:
                n.read = True
                return True
        return False

    def mark_all_read(self, user_id: int, group: Optional[str] = None) -> int:
        """Mark all notifications as read. Returns count."""
        count = 0
        for n in self._notifications.get(user_id, []):
            if not n.read and (group is None or n.group.value == group):
                n.read = True
                count += 1
        return count

    def dismiss(self, user_id: int, notification_id: str) -> bool:
        """Dismiss a notification."""
        for n in self._notifications.get(user_id, []):
            if n.id == notification_id:
                n.dismissed = True
                return True
        return False

    def get_summary(self, user_id: int) -> Dict:
        """Get notification summary counts by priority."""
        notes = [n for n in self._notifications.get(user_id, []) if not n.read]
        counts = {}
        for p in Priority:
            c = sum(1 for n in notes if n.priority == p)
            if c > 0:
                counts[p.value] = c
        return {"unread_total": len(notes), "by_priority": counts}

    def set_preferences(self, user_id: int, prefs: Dict):
        """Set user notification preferences."""
        self._preferences[user_id] = prefs

    def get_preferences(self, user_id: int) -> Dict:
        """Get user notification preferences."""
        return self._preferences.get(user_id, {
            "critical": True, "high": True,
            "medium": True, "low": True, "info": False,
        })


# Global instance
_manager = NotificationManager()


def get_notification_manager() -> NotificationManager:
    return _manager
