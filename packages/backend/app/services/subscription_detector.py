"""Auto-detect subscriptions from recurring transactions and monitor cost changes.

Detection algorithm:
1. Group transactions by merchant (normalized)
2. Check for recurring patterns (monthly, weekly, yearly)
3. Score confidence based on consistency of amounts and intervals
4. Detect cost increases by comparing with original amount
"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from ..extensions import db
from ..models_subscriptions import DetectedSubscription, SubscriptionCostAlert

logger = logging.getLogger("finmind.subscription_detector")


def _normalize_merchant(name: str) -> str:
    """Normalize merchant name for grouping."""
    return name.lower().strip()


def detect_subscriptions(user_id: int, transactions: list[dict]) -> list[DetectedSubscription]:
    """Detect subscriptions from a list of transactions.

    Args:
        user_id: User ID
        transactions: List of transaction dicts with merchant, amount, date fields

    Returns:
        List of newly detected or updated subscriptions
    """
    # Group by normalized merchant
    groups = defaultdict(list)
    for tx in transactions:
        merchant = _normalize_merchant(tx.get("merchant", ""))
        if merchant:
            groups[merchant].append(tx)

    results = []
    for merchant, txs in groups.items():
        if len(txs) < 2:
            continue

        # Sort by date
        sorted_txs = sorted(txs, key=lambda x: x.get("date", ""))

        # Calculate intervals
        amounts = [float(tx.get("amount", 0)) for tx in sorted_txs]
        dates = []
        for tx in sorted_txs:
            d = tx.get("date")
            if isinstance(d, str):
                d = datetime.fromisoformat(d)
            dates.append(d)

        # Check for consistent intervals (monthly ~28-35 days, weekly ~5-9 days, yearly ~340-390 days)
        intervals = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i-1]).days
            intervals.append(delta)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)

        # Determine frequency
        frequency = None
        if 25 <= avg_interval <= 35:
            frequency = "monthly"
        elif 5 <= avg_interval <= 9:
            frequency = "weekly"
        elif 340 <= avg_interval <= 390:
            frequency = "yearly"

        if not frequency:
            continue

        # Calculate confidence based on consistency
        amount_variance = max(amounts) - min(amounts) if amounts else 0
        interval_variance = max(intervals) - min(intervals) if intervals else 0

        confidence = 0.5
        if amount_variance <= 5:
            confidence += 0.3  # Consistent amounts
        if interval_variance <= 5:
            confidence += 0.2  # Consistent intervals
        confidence = min(confidence, 1.0)

        avg_amount = sum(amounts) / len(amounts)

        # Check if subscription already exists
        existing = DetectedSubscription.query.filter_by(
            user_id=user_id, merchant=merchant, is_active=True
        ).first()

        if existing:
            # Update existing
            existing.amount = avg_amount
            existing.occurrence_count += len(txs)
            existing.last_seen = dates[-1]
            existing.confidence = max(existing.confidence, confidence)

            # Check for cost increase
            if existing.original_amount and avg_amount > existing.original_amount * 1.05:
                increase_pct = ((avg_amount - existing.original_amount) / existing.original_amount) * 100
                alert = SubscriptionCostAlert(
                    user_id=user_id,
                    subscription_id=existing.id,
                    merchant=merchant,
                    old_amount=existing.original_amount,
                    new_amount=avg_amount,
                    increase_percentage=increase_pct,
                )
                db.session.add(alert)
                logger.info("Cost increase detected for %s: %.2f -> %.2f (+%.1f%%)",
                           merchant, existing.original_amount, avg_amount, increase_pct)

            results.append(existing)
        else:
            # Create new subscription
            sub = DetectedSubscription(
                user_id=user_id,
                merchant=merchant,
                amount=avg_amount,
                original_amount=avg_amount,
                category=sorted_txs[0].get("category"),
                frequency=frequency,
                confidence=confidence,
                occurrence_count=len(txs),
                first_seen=dates[0],
                last_seen=dates[-1],
            )

            # Calculate next expected date
            if frequency == "monthly":
                sub.next_expected = dates[-1] + timedelta(days=30)
            elif frequency == "weekly":
                sub.next_expected = dates[-1] + timedelta(days=7)
            elif frequency == "yearly":
                sub.next_expected = dates[-1] + timedelta(days=365)

            db.session.add(sub)
            results.append(sub)

    db.session.commit()
    return results


def get_user_subscriptions(user_id: int, active_only: bool = True) -> list[DetectedSubscription]:
    """Get detected subscriptions for a user."""
    query = DetectedSubscription.query.filter_by(user_id=user_id)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(DetectedSubscription.amount.desc()).all()


def get_cost_alerts(user_id: int, unread_only: bool = False) -> list[SubscriptionCostAlert]:
    """Get subscription cost increase alerts."""
    query = SubscriptionCostAlert.query.filter_by(user_id=user_id)
    if unread_only:
        query = query.filter_by(is_read=False)
    return query.order_by(SubscriptionCostAlert.created_at.desc()).all()


def confirm_subscription(sub_id: int, user_id: int) -> DetectedSubscription:
    """Confirm a detected subscription."""
    sub = DetectedSubscription.query.filter_by(id=sub_id, user_id=user_id).first()
    if not sub:
        raise ValueError("Subscription not found")
    sub.is_confirmed = True
    db.session.commit()
    return sub


def dismiss_subscription(sub_id: int, user_id: int) -> bool:
    """Dismiss a detected subscription (not a subscription)."""
    sub = DetectedSubscription.query.filter_by(id=sub_id, user_id=user_id).first()
    if not sub:
        return False
    sub.is_active = False
    db.session.commit()
    return True


def mark_alert_read(alert_id: int, user_id: int) -> bool:
    """Mark a cost alert as read."""
    alert = SubscriptionCostAlert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return False
    alert.is_read = True
    db.session.commit()
    return True
