"""Lifestyle inflation detection insights.

Analyzes spending trends over time to detect rising lifestyle expenses.
Compares month-over-month, quarter-over-quarter, and year-over-year
spending to identify inflation patterns.
"""

from datetime import datetime, timedelta, date
from decimal import Decimal
from sqlalchemy import func, desc
from app.extensions import db
from app.models import LifestyleSnapshot, InflationAlert, Expense, Category


def generate_snapshot(user_id, period_start, period_end):
    """Generate a spending snapshot for a given period."""
    spending = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= period_start,
            Expense.spent_at <= period_end,
        )
        .group_by(Expense.category_id)
        .all()
    )

    total = sum(float(s.total) for s in spending)
    count = sum(s.count for s in spending)

    category_spending = {}
    top_cats = []
    for s in spending:
        if s.category_id:
            cat = db.session.get(Category, s.category_id)
            cat_name = cat.name if cat else f"cat_{s.category_id}"
            category_spending[cat_name] = float(s.total)
            top_cats.append({
                "category_id": s.category_id,
                "name": cat_name,
                "amount": float(s.total),
                "count": s.count,
            })

    top_cats.sort(key=lambda x: x["amount"], reverse=True)

    # Upsert snapshot
    existing = LifestyleSnapshot.query.filter_by(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
    ).first()

    if existing:
        existing.total_spending = total
        existing.category_spending = category_spending
        existing.transaction_count = count
        existing.avg_transaction = round(total / count, 2) if count > 0 else 0
        existing.top_categories = top_cats[:5]
        db.session.commit()
        return _snapshot_to_dict(existing)

    snapshot = LifestyleSnapshot(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        total_spending=total,
        category_spending=category_spending,
        transaction_count=count,
        avg_transaction=round(total / count, 2) if count > 0 else 0,
        top_categories=top_cats[:5],
    )
    db.session.add(snapshot)
    db.session.commit()
    return _snapshot_to_dict(snapshot)


def detect_inflation(user_id, months=6):
    """Detect lifestyle inflation by comparing monthly spending periods.

    Compares each month to the previous month and generates alerts
    for significant spending increases.
    """
    today = date.today()
    alerts = []

    monthly_data = []
    for i in range(months):
        month_end = today.replace(day=1) - timedelta(days=i * 30)
        month_start = month_end - timedelta(days=30)

        total = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= month_start,
                Expense.spent_at <= month_end,
            )
            .scalar()
        )
        monthly_data.append({
            "start": month_start,
            "end": month_end,
            "total": float(total) if total else 0,
        })

    # Compare consecutive months for overall inflation
    for i in range(len(monthly_data) - 1):
        current = monthly_data[i]
        previous = monthly_data[i + 1]

        if previous["total"] > 0 and current["total"] > 0:
            change_pct = ((current["total"] - previous["total"]) / previous["total"]) * 100

            if change_pct >= 10:
                severity = "high" if change_pct >= 25 else "moderate"
                alert = _create_alert(
                    user_id=user_id,
                    alert_type="monthly_increase",
                    severity=severity,
                    current_amount=current["total"],
                    previous_amount=previous["total"],
                    change_pct=change_pct,
                    message=(
                        f"Your spending increased {change_pct:.1f}% from "
                        f"${previous['total']:.2f} to ${current['total']:.2f}."
                    ),
                )
                alerts.append(alert)

    # Per-category inflation detection
    cat_alerts = _detect_category_inflation(user_id, months=months)
    alerts.extend(cat_alerts)

    return alerts


def _detect_category_inflation(user_id, months=6):
    """Detect per-category spending inflation."""
    today = date.today()
    alerts = []

    # Current month spending by category
    current_start = today.replace(day=1) - timedelta(days=30)
    current_end = today

    current_cats = dict(
        db.session.query(
            Expense.category_id, func.sum(Expense.amount)
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= current_start,
            Expense.spent_at <= current_end,
        )
        .group_by(Expense.category_id)
        .all()
    )

    # Previous month spending by category
    prev_start = current_start - timedelta(days=30)
    prev_end = current_start

    prev_cats = dict(
        db.session.query(
            Expense.category_id, func.sum(Expense.amount)
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_start,
            Expense.spent_at < prev_end,
        )
        .group_by(Expense.category_id)
        .all()
    )

    for cat_id, current_amount in current_cats.items():
        if cat_id is None:
            continue
        prev_amount = prev_cats.get(cat_id)
        if prev_amount and float(prev_amount) > 0:
            change_pct = ((float(current_amount) - float(prev_amount)) / float(prev_amount)) * 100

            if change_pct >= 20:
                cat = db.session.get(Category, cat_id)
                cat_name = cat.name if cat else "Unknown"
                severity = "high" if change_pct >= 50 else "moderate"

                alert = _create_alert(
                    user_id=user_id,
                    alert_type="category_increase",
                    severity=severity,
                    current_amount=float(current_amount),
                    previous_amount=float(prev_amount),
                    change_pct=change_pct,
                    category_id=cat_id,
                    category_name=cat_name,
                    message=(
                        f"Your {cat_name} spending increased {change_pct:.1f}% "
                        f"from ${float(prev_amount):.2f} to ${float(current_amount):.2f}."
                    ),
                )
                alerts.append(alert)

    return alerts


def get_trends(user_id, months=6):
    """Get spending trends over time."""
    today = date.today()
    trends = []

    for i in range(months):
        month_end = today.replace(day=1) - timedelta(days=i * 30)
        month_start = month_end - timedelta(days=30)

        total = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= month_start,
                Expense.spent_at <= month_end,
            )
            .scalar()
        )

        count = (
            db.session.query(func.count(Expense.id))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= month_start,
                Expense.spent_at <= month_end,
            )
            .scalar()
        )

        amount = float(total) if total else 0
        trends.append({
            "period_start": str(month_start),
            "period_end": str(month_end),
            "total_spending": amount,
            "transaction_count": count or 0,
            "avg_transaction": round(amount / count, 2) if count else 0,
        })

    trends.reverse()  # Chronological order

    # Calculate overall trend
    if len(trends) >= 2:
        first = trends[0]["total_spending"]
        last = trends[-1]["total_spending"]
        if first > 0:
            overall_change = ((last - first) / first) * 100
        else:
            overall_change = 0
    else:
        overall_change = 0

    return {
        "monthly_trends": trends,
        "months": months,
        "overall_change_pct": round(overall_change, 1),
        "trend_direction": "up" if overall_change > 5 else ("down" if overall_change < -5 else "stable"),
    }


def get_alerts(user_id, alert_type=None, severity=None, acknowledged=None, limit=50):
    """Get inflation alerts for a user."""
    query = InflationAlert.query.filter_by(user_id=user_id)

    if alert_type:
        query = query.filter_by(alert_type=alert_type)
    if severity:
        query = query.filter_by(severity=severity)
    if acknowledged is not None:
        query = query.filter_by(is_acknowledged=acknowledged)

    alerts = query.order_by(desc(InflationAlert.created_at)).limit(limit).all()
    return [_alert_to_dict(a) for a in alerts]


def acknowledge_alert(alert_id, user_id):
    """Mark an alert as acknowledged."""
    alert = InflationAlert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return None
    alert.is_acknowledged = True
    db.session.commit()
    return _alert_to_dict(alert)


def get_inflation_summary(user_id, months=6):
    """Get inflation analysis summary."""
    trends = get_trends(user_id, months=months)
    alerts = get_alerts(user_id)

    unacked = sum(1 for a in alerts if not a["is_acknowledged"])
    high_alerts = sum(1 for a in alerts if a["severity"] == "high")

    return {
        "trend_direction": trends["trend_direction"],
        "overall_change_pct": trends["overall_change_pct"],
        "total_alerts": len(alerts),
        "unacknowledged_alerts": unacked,
        "high_severity_alerts": high_alerts,
        "monthly_trends": trends["monthly_trends"],
        "months_analyzed": months,
    }


def _create_alert(user_id, alert_type, severity, current_amount,
                  previous_amount, change_pct, message,
                  category_id=None, category_name=None):
    """Create an inflation alert."""
    alert = InflationAlert(
        user_id=user_id,
        category_id=category_id,
        category_name=category_name,
        alert_type=alert_type,
        severity=severity,
        current_amount=current_amount,
        previous_amount=previous_amount,
        change_pct=change_pct,
        message=message,
    )
    db.session.add(alert)
    db.session.commit()
    return _alert_to_dict(alert)


def _snapshot_to_dict(s):
    return {
        "id": s.id,
        "user_id": s.user_id,
        "period_start": str(s.period_start),
        "period_end": str(s.period_end),
        "total_spending": float(s.total_spending),
        "category_spending": s.category_spending,
        "transaction_count": s.transaction_count,
        "avg_transaction": float(s.avg_transaction),
        "top_categories": s.top_categories,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _alert_to_dict(a):
    return {
        "id": a.id,
        "user_id": a.user_id,
        "category_id": a.category_id,
        "category_name": a.category_name,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "current_amount": float(a.current_amount),
        "previous_amount": float(a.previous_amount),
        "change_pct": float(a.change_pct),
        "message": a.message,
        "is_acknowledged": a.is_acknowledged,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
