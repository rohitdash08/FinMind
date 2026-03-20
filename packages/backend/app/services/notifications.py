"""Auto-generate notifications from financial events."""

from datetime import date, timedelta
from decimal import Decimal
from ..extensions import db
from ..models import (
    Bill,
    Notification,
    NotificationType,
    NotificationPriority,
)
import logging

logger = logging.getLogger("finmind.notifications.service")

# Priority mapping for each notification type
_TYPE_PRIORITY = {
    NotificationType.BILL_DUE: NotificationPriority.HIGH,
    NotificationType.BUDGET_EXCEEDED: NotificationPriority.CRITICAL,
    NotificationType.SAVINGS_OPPORTUNITY: NotificationPriority.MEDIUM,
    NotificationType.WEEKLY_SUMMARY: NotificationPriority.LOW,
}

# Group mapping for each notification type
_TYPE_GROUP = {
    NotificationType.BILL_DUE: "bills",
    NotificationType.BUDGET_EXCEEDED: "budgets",
    NotificationType.SAVINGS_OPPORTUNITY: "savings",
    NotificationType.WEEKLY_SUMMARY: "summary",
}


def generate_bill_due_notifications(user_id: int, days_ahead: int = 3) -> int:
    """Create notifications for bills due within `days_ahead` days."""
    threshold = date.today() + timedelta(days=days_ahead)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active == True,  # noqa: E712
            Bill.next_due_date <= threshold,
            Bill.next_due_date >= date.today(),
        )
        .all()
    )
    created = 0
    for bill in bills:
        # Avoid duplicates: check if notification already exists for this bill
        existing = (
            db.session.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.type == NotificationType.BILL_DUE.value,
                Notification.message.contains(bill.name),
                Notification.read == False,  # noqa: E712
            )
            .first()
        )
        if existing:
            continue
        n = Notification(
            user_id=user_id,
            type=NotificationType.BILL_DUE.value,
            priority=_TYPE_PRIORITY[NotificationType.BILL_DUE].value,
            group=_TYPE_GROUP[NotificationType.BILL_DUE],
            message=f"Bill '{bill.name}' ({bill.currency} {float(bill.amount):.2f}) is due on {bill.next_due_date.isoformat()}",
        )
        db.session.add(n)
        created += 1
    if created:
        db.session.commit()
    logger.info("Generated %s bill-due notifications for user=%s", created, user_id)
    return created


def generate_budget_exceeded_notification(
    user_id: int, category_name: str, spent: Decimal, budget: Decimal
) -> Notification:
    """Create a critical notification when spending exceeds budget."""
    n = Notification(
        user_id=user_id,
        type=NotificationType.BUDGET_EXCEEDED.value,
        priority=_TYPE_PRIORITY[NotificationType.BUDGET_EXCEEDED].value,
        group=_TYPE_GROUP[NotificationType.BUDGET_EXCEEDED],
        message=f"Budget exceeded for '{category_name}': spent {float(spent):.2f} of {float(budget):.2f}",
    )
    db.session.add(n)
    db.session.commit()
    logger.info("Generated budget-exceeded notification for user=%s category=%s", user_id, category_name)
    return n


def generate_savings_opportunity(user_id: int, message: str) -> Notification:
    """Create a medium-priority savings opportunity notification."""
    n = Notification(
        user_id=user_id,
        type=NotificationType.SAVINGS_OPPORTUNITY.value,
        priority=_TYPE_PRIORITY[NotificationType.SAVINGS_OPPORTUNITY].value,
        group=_TYPE_GROUP[NotificationType.SAVINGS_OPPORTUNITY],
        message=message,
    )
    db.session.add(n)
    db.session.commit()
    logger.info("Generated savings-opportunity notification for user=%s", user_id)
    return n


def generate_weekly_summary(
    user_id: int, total_spent: Decimal, transaction_count: int
) -> Notification:
    """Create a low-priority weekly summary notification."""
    n = Notification(
        user_id=user_id,
        type=NotificationType.WEEKLY_SUMMARY.value,
        priority=_TYPE_PRIORITY[NotificationType.WEEKLY_SUMMARY].value,
        group=_TYPE_GROUP[NotificationType.WEEKLY_SUMMARY],
        message=f"Weekly summary: {transaction_count} transactions totalling {float(total_spent):.2f}",
    )
    db.session.add(n)
    db.session.commit()
    logger.info("Generated weekly-summary notification for user=%s", user_id)
    return n
