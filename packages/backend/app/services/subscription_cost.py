"""Subscription cost increase detection service.

Monitors subscription plan pricing for changes and generates alerts
for affected users when their subscription costs increase.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc

from app.extensions import db
from app.models import (
    SubscriptionPlan,
    UserSubscription,
    SubscriptionPriceHistory,
    SubscriptionCostAlert,
)


# ── Price Update & Detection ──────────────────────────────────────


def update_plan_price(plan_id: int, new_price_cents: int) -> dict:
    """Update a plan's price and record history if changed.

    Returns the price change record or None if unchanged.
    """
    plan = SubscriptionPlan.query.get(plan_id)
    if not plan:
        return {"error": "Plan not found"}

    old_price = plan.price_cents
    if old_price == new_price_cents:
        return {
            "plan_id": plan_id,
            "changed": False,
            "price_cents": old_price,
        }

    change_pct = round(((new_price_cents - old_price) / old_price) * 100, 2) if old_price else 0

    # Record price history
    history = SubscriptionPriceHistory(
        plan_id=plan_id,
        old_price_cents=old_price,
        new_price_cents=new_price_cents,
        change_pct=change_pct,
    )
    db.session.add(history)

    # Update the plan
    plan.price_cents = new_price_cents
    db.session.flush()

    # If price increased, alert affected users
    alerts_created = 0
    if new_price_cents > old_price:
        alerts_created = _create_alerts_for_plan(
            plan_id, old_price, new_price_cents, change_pct
        )

    db.session.commit()

    return {
        "plan_id": plan_id,
        "changed": True,
        "old_price_cents": old_price,
        "new_price_cents": new_price_cents,
        "change_pct": float(change_pct),
        "direction": "increase" if new_price_cents > old_price else "decrease",
        "alerts_created": alerts_created,
    }


def _create_alerts_for_plan(
    plan_id: int, old_price: int, new_price: int, change_pct: float
) -> int:
    """Create cost alerts for all active subscribers of a plan."""
    subscriptions = UserSubscription.query.filter_by(
        plan_id=plan_id, active=True
    ).all()

    count = 0
    for sub in subscriptions:
        alert = SubscriptionCostAlert(
            user_id=sub.user_id,
            plan_id=plan_id,
            old_price_cents=old_price,
            new_price_cents=new_price,
            change_pct=change_pct,
        )
        db.session.add(alert)
        count += 1

    return count


# ── Price History ─────────────────────────────────────────────────


def get_price_history(plan_id: int, limit: int = 20) -> list:
    """Get price change history for a subscription plan."""
    records = (
        SubscriptionPriceHistory.query
        .filter_by(plan_id=plan_id)
        .order_by(desc(SubscriptionPriceHistory.detected_at))
        .limit(limit)
        .all()
    )
    return [_serialize_history(r) for r in records]


def get_all_price_changes(limit: int = 50) -> list:
    """Get recent price changes across all plans."""
    records = (
        SubscriptionPriceHistory.query
        .order_by(desc(SubscriptionPriceHistory.detected_at))
        .limit(limit)
        .all()
    )
    return [_serialize_history(r) for r in records]


# ── User Alerts ───────────────────────────────────────────────────


def get_user_alerts(
    user_id: int,
    unacknowledged_only: bool = False,
    limit: int = 50,
) -> list:
    """Get cost increase alerts for a user."""
    query = SubscriptionCostAlert.query.filter_by(user_id=user_id)
    if unacknowledged_only:
        query = query.filter_by(acknowledged=False)
    records = (
        query.order_by(desc(SubscriptionCostAlert.created_at))
        .limit(limit)
        .all()
    )
    return [_serialize_alert(r) for r in records]


def acknowledge_alert(user_id: int, alert_id: int) -> dict:
    """Mark an alert as acknowledged."""
    alert = SubscriptionCostAlert.query.filter_by(
        id=alert_id, user_id=user_id
    ).first()
    if not alert:
        return {"error": "Alert not found"}

    alert.acknowledged = True
    db.session.commit()
    return _serialize_alert(alert)


def acknowledge_all_alerts(user_id: int) -> dict:
    """Acknowledge all pending alerts for a user."""
    count = (
        SubscriptionCostAlert.query
        .filter_by(user_id=user_id, acknowledged=False)
        .update({"acknowledged": True})
    )
    db.session.commit()
    return {"acknowledged_count": count}


# ── Cost Analysis ─────────────────────────────────────────────────


def get_user_cost_summary(user_id: int) -> dict:
    """Get subscription cost summary for a user.

    Returns total monthly cost and any recent increases.
    """
    subscriptions = UserSubscription.query.filter_by(
        user_id=user_id, active=True
    ).all()

    if not subscriptions:
        return {
            "total_monthly_cents": 0,
            "subscription_count": 0,
            "plans": [],
            "recent_increases": [],
        }

    plans = []
    total = 0
    for sub in subscriptions:
        plan = SubscriptionPlan.query.get(sub.plan_id)
        if plan:
            plans.append({
                "plan_id": plan.id,
                "name": plan.name,
                "price_cents": plan.price_cents,
                "interval": plan.interval,
            })
            # Normalize to monthly
            if plan.interval == "yearly":
                total += plan.price_cents // 12
            elif plan.interval == "weekly":
                total += plan.price_cents * 4
            else:
                total += plan.price_cents

    # Recent increases
    plan_ids = [s.plan_id for s in subscriptions]
    recent = []
    if plan_ids:
        increases = (
            SubscriptionPriceHistory.query
            .filter(
                SubscriptionPriceHistory.plan_id.in_(plan_ids),
                SubscriptionPriceHistory.new_price_cents > SubscriptionPriceHistory.old_price_cents,
            )
            .order_by(desc(SubscriptionPriceHistory.detected_at))
            .limit(10)
            .all()
        )
        recent = [_serialize_history(r) for r in increases]

    return {
        "total_monthly_cents": total,
        "subscription_count": len(plans),
        "plans": plans,
        "recent_increases": recent,
    }


def detect_increases(plan_id: Optional[int] = None) -> list:
    """Detect all price increases, optionally for a specific plan.

    Returns list of plans with increases and affected user counts.
    """
    query = SubscriptionPriceHistory.query.filter(
        SubscriptionPriceHistory.new_price_cents > SubscriptionPriceHistory.old_price_cents
    )
    if plan_id:
        query = query.filter_by(plan_id=plan_id)

    records = query.order_by(desc(SubscriptionPriceHistory.detected_at)).all()

    results = []
    for r in records:
        affected = UserSubscription.query.filter_by(
            plan_id=r.plan_id, active=True
        ).count()
        entry = _serialize_history(r)
        entry["affected_users"] = affected
        results.append(entry)

    return results


# ── Serializers ───────────────────────────────────────────────────


def _serialize_history(record: SubscriptionPriceHistory) -> dict:
    return {
        "id": record.id,
        "plan_id": record.plan_id,
        "old_price_cents": record.old_price_cents,
        "new_price_cents": record.new_price_cents,
        "change_pct": float(record.change_pct),
        "detected_at": record.detected_at.isoformat() if record.detected_at else None,
        "notified": record.notified,
    }


def _serialize_alert(record: SubscriptionCostAlert) -> dict:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "plan_id": record.plan_id,
        "old_price_cents": record.old_price_cents,
        "new_price_cents": record.new_price_cents,
        "change_pct": float(record.change_pct),
        "acknowledged": record.acknowledged,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
