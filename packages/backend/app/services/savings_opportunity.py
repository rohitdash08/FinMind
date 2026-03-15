"""Savings opportunity detection engine.

Analyzes user spending patterns to identify areas where users can
reduce spending and save money. Provides categorized, confidence-scored
opportunities with actionable recommendations.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, desc
from app.extensions import db
from app.models import SavingsOpportunity, Expense, Category


# Opportunity types
OPPORTUNITY_TYPES = [
    "spending_spike",
    "category_overspend",
    "recurring_reduction",
    "comparison_savings",
    "unused_subscription",
    "seasonal_pattern",
    "budget_optimization",
]


def detect_spending_spikes(user_id, days=30, threshold=1.5):
    """Detect categories with spending spikes above historical average.

    Args:
        user_id: User to analyze
        days: Recent period to analyze
        threshold: Multiplier above average to flag (1.5 = 50% above)
    """
    since = datetime.utcnow() - timedelta(days=days)
    historical_since = datetime.utcnow() - timedelta(days=days * 3)

    # Get recent spending by category
    recent = dict(
        db.session.query(
            Expense.category_id, func.sum(Expense.amount)
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= since,
        )
        .group_by(Expense.category_id)
        .all()
    )

    # Get historical average by category (per period)
    historical = dict(
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount) / 3,  # average over 3 periods
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= historical_since,
            Expense.spent_at < since,
        )
        .group_by(Expense.category_id)
        .all()
    )

    opportunities = []
    for cat_id, recent_amount in recent.items():
        if cat_id is None:
            continue
        avg_amount = historical.get(cat_id)
        if avg_amount and avg_amount > 0:
            ratio = float(recent_amount) / float(avg_amount)
            if ratio >= threshold:
                potential = float(recent_amount) - float(avg_amount)
                confidence = min(0.95, 0.5 + (ratio - threshold) * 0.2)

                cat = db.session.get(Category, cat_id)
                cat_name = cat.name if cat else "Unknown"

                opp = _create_opportunity(
                    user_id=user_id,
                    type="spending_spike",
                    title=f"Spending spike in {cat_name}",
                    description=(
                        f"Your {cat_name} spending is {ratio:.1f}x higher than "
                        f"your usual average. You spent ${float(recent_amount):.2f} "
                        f"vs your average of ${float(avg_amount):.2f}."
                    ),
                    category_id=cat_id,
                    current_amount=float(recent_amount),
                    target_amount=float(avg_amount),
                    potential_savings=potential,
                    confidence=confidence,
                )
                opportunities.append(opp)

    return opportunities


def detect_category_overspend(user_id, days=30):
    """Detect categories consuming disproportionate share of total spending."""
    since = datetime.utcnow() - timedelta(days=days)

    spending = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
        )
        .filter(Expense.user_id == user_id, Expense.spent_at >= since)
        .group_by(Expense.category_id)
        .all()
    )

    if not spending:
        return []

    total_spend = sum(float(s.total) for s in spending)
    if total_spend == 0:
        return []

    opportunities = []
    for s in spending:
        if s.category_id is None:
            continue
        pct = float(s.total) / total_spend
        if pct > 0.4:  # Category is > 40% of total
            target = total_spend * 0.3  # Suggest 30% as target
            potential = float(s.total) - target

            cat = db.session.get(Category, s.category_id)
            cat_name = cat.name if cat else "Unknown"

            opp = _create_opportunity(
                user_id=user_id,
                type="category_overspend",
                title=f"High concentration in {cat_name}",
                description=(
                    f"{cat_name} accounts for {pct:.0%} of your total spending. "
                    f"Consider diversifying or reducing from ${float(s.total):.2f} "
                    f"to ${target:.2f}."
                ),
                category_id=s.category_id,
                current_amount=float(s.total),
                target_amount=target,
                potential_savings=max(0, potential),
                confidence=min(0.9, pct),
            )
            opportunities.append(opp)

    return opportunities


def run_full_detection(user_id, days=30):
    """Run all detection algorithms and return combined opportunities."""
    all_opps = []
    all_opps.extend(detect_spending_spikes(user_id, days=days))
    all_opps.extend(detect_category_overspend(user_id, days=days))
    return sorted(all_opps, key=lambda o: o["potential_savings"], reverse=True)


def get_opportunities(user_id, type=None, status=None, limit=50):
    """Get saved opportunities for a user."""
    query = SavingsOpportunity.query.filter_by(
        user_id=user_id, is_dismissed=False
    )

    if type:
        query = query.filter_by(type=type)
    if status:
        query = query.filter_by(status=status)

    # Filter expired
    query = query.filter(
        db.or_(
            SavingsOpportunity.expires_at.is_(None),
            SavingsOpportunity.expires_at > datetime.utcnow(),
        )
    )

    opps = query.order_by(
        desc(SavingsOpportunity.potential_savings)
    ).limit(limit).all()

    return [_opportunity_to_dict(o) for o in opps]


def get_opportunity(opportunity_id, user_id):
    """Get a single opportunity."""
    o = SavingsOpportunity.query.filter_by(
        id=opportunity_id, user_id=user_id
    ).first()
    if not o:
        return None
    return _opportunity_to_dict(o)


def dismiss_opportunity(opportunity_id, user_id):
    """Dismiss an opportunity."""
    o = SavingsOpportunity.query.filter_by(
        id=opportunity_id, user_id=user_id
    ).first()
    if not o:
        return None
    o.is_dismissed = True
    o.status = "dismissed"
    db.session.commit()
    return _opportunity_to_dict(o)


def mark_action_taken(opportunity_id, user_id):
    """Mark that user has acted on an opportunity."""
    o = SavingsOpportunity.query.filter_by(
        id=opportunity_id, user_id=user_id
    ).first()
    if not o:
        return None
    o.action_taken = True
    o.status = "acted"
    db.session.commit()
    return _opportunity_to_dict(o)


def get_savings_summary(user_id):
    """Get summary of all opportunities for a user."""
    opps = SavingsOpportunity.query.filter_by(
        user_id=user_id, is_dismissed=False
    ).all()

    total_potential = sum(float(o.potential_savings) for o in opps)
    acted = [o for o in opps if o.action_taken]
    total_acted = sum(float(o.potential_savings) for o in acted)

    by_type = {}
    for o in opps:
        if o.type not in by_type:
            by_type[o.type] = {"count": 0, "potential_savings": 0}
        by_type[o.type]["count"] += 1
        by_type[o.type]["potential_savings"] += float(o.potential_savings)

    return {
        "total_opportunities": len(opps),
        "total_potential_savings": round(total_potential, 2),
        "acted_count": len(acted),
        "acted_savings": round(total_acted, 2),
        "pending_count": len(opps) - len(acted),
        "by_type": by_type,
        "avg_confidence": round(
            sum(float(o.confidence) for o in opps) / len(opps), 2
        ) if opps else 0.0,
    }


def _create_opportunity(
    user_id, type, title, description, category_id=None,
    current_amount=0, target_amount=0, potential_savings=0,
    confidence=0.5, expires_at=None,
):
    """Create and save a savings opportunity."""
    # Avoid duplicates: check for existing active opportunity of same type/category
    existing = SavingsOpportunity.query.filter_by(
        user_id=user_id,
        type=type,
        category_id=category_id,
        is_dismissed=False,
    ).filter(
        SavingsOpportunity.status.in_(["active"]),
    ).first()

    if existing:
        # Update existing opportunity with new data
        existing.current_amount = current_amount
        existing.target_amount = target_amount
        existing.potential_savings = potential_savings
        existing.confidence = confidence
        existing.description = description
        existing.detected_at = datetime.utcnow()
        db.session.commit()
        return _opportunity_to_dict(existing)

    opp = SavingsOpportunity(
        user_id=user_id,
        type=type,
        title=title,
        description=description,
        category_id=category_id,
        current_amount=current_amount,
        target_amount=target_amount,
        potential_savings=potential_savings,
        confidence=confidence,
        expires_at=expires_at,
    )
    db.session.add(opp)
    db.session.commit()
    return _opportunity_to_dict(opp)


def _opportunity_to_dict(o):
    """Convert opportunity model to dict."""
    return {
        "id": o.id,
        "user_id": o.user_id,
        "type": o.type,
        "title": o.title,
        "description": o.description,
        "category_id": o.category_id,
        "current_amount": float(o.current_amount),
        "target_amount": float(o.target_amount),
        "potential_savings": float(o.potential_savings),
        "confidence": float(o.confidence),
        "status": o.status,
        "is_dismissed": o.is_dismissed,
        "action_taken": o.action_taken,
        "detected_at": o.detected_at.isoformat() if o.detected_at else None,
        "expires_at": o.expires_at.isoformat() if o.expires_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
