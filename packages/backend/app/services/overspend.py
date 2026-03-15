"""Category overspend early warning system.

Monitors spending per category against user-defined budget limits and
generates alerts when spending approaches or exceeds thresholds.

Alert levels:
  - warning: spending reaches warning_threshold (default 80%)
  - critical: spending reaches critical_threshold (default 95%)
  - exceeded: spending exceeds 100% of budget
"""

import calendar
import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import CategoryBudget, Category, Expense, OverspendAlert

logger = logging.getLogger("finmind.overspend")


# ─── Budget CRUD ────────────────────────────────────────────────────────


def create_budget(
    user_id: int,
    category_id: int,
    monthly_limit: float,
    currency: str = "INR",
    warning_threshold: float = 80.0,
    critical_threshold: float = 95.0,
) -> dict | None:
    """Create a monthly budget for a category.

    Returns the budget dict or None if category doesn't exist.
    """
    # Validate category belongs to user
    cat = (
        db.session.query(Category)
        .filter_by(id=category_id, user_id=user_id)
        .first()
    )
    if not cat:
        return None

    # Check for existing budget
    existing = (
        db.session.query(CategoryBudget)
        .filter_by(user_id=user_id, category_id=category_id)
        .first()
    )
    if existing:
        existing.monthly_limit = Decimal(str(monthly_limit))
        existing.currency = currency
        existing.warning_threshold = Decimal(str(warning_threshold))
        existing.critical_threshold = Decimal(str(critical_threshold))
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        db.session.commit()
        return _budget_to_dict(existing)

    budget = CategoryBudget(
        user_id=user_id,
        category_id=category_id,
        monthly_limit=Decimal(str(monthly_limit)),
        currency=currency,
        warning_threshold=Decimal(str(warning_threshold)),
        critical_threshold=Decimal(str(critical_threshold)),
        is_active=True,
    )
    db.session.add(budget)
    db.session.commit()
    logger.info(
        "Created budget id=%d user=%d category=%d limit=%s",
        budget.id, user_id, category_id, monthly_limit,
    )
    return _budget_to_dict(budget)


def get_budgets(user_id: int, active_only: bool = True) -> list[dict]:
    """Get all category budgets for a user."""
    q = db.session.query(CategoryBudget).filter_by(user_id=user_id)
    if active_only:
        q = q.filter_by(is_active=True)
    budgets = q.order_by(CategoryBudget.created_at.desc()).all()
    return [_budget_to_dict(b) for b in budgets]


def get_budget_by_id(user_id: int, budget_id: int) -> CategoryBudget | None:
    """Get a specific budget by ID."""
    return (
        db.session.query(CategoryBudget)
        .filter_by(id=budget_id, user_id=user_id)
        .first()
    )


def update_budget(
    user_id: int, budget_id: int, updates: dict
) -> dict | None:
    """Update a budget's settings."""
    budget = get_budget_by_id(user_id, budget_id)
    if not budget:
        return None

    allowed = {"monthly_limit", "warning_threshold", "critical_threshold", "is_active", "currency"}
    for key, val in updates.items():
        if key in allowed:
            if key in ("monthly_limit", "warning_threshold", "critical_threshold"):
                setattr(budget, key, Decimal(str(val)))
            else:
                setattr(budget, key, val)

    budget.updated_at = datetime.utcnow()
    db.session.commit()
    return _budget_to_dict(budget)


def delete_budget(user_id: int, budget_id: int) -> bool:
    """Soft-delete a budget by deactivating it."""
    budget = get_budget_by_id(user_id, budget_id)
    if not budget:
        return False
    budget.is_active = False
    budget.updated_at = datetime.utcnow()
    db.session.commit()
    return True


# ─── Spending analysis ──────────────────────────────────────────────────


def _get_current_month_range() -> tuple[date, date]:
    """Get the start and end dates of the current month."""
    today = date.today()
    start = today.replace(day=1)
    _, last_day = calendar.monthrange(today.year, today.month)
    end = today.replace(day=last_day)
    return start, end


def get_category_spending(
    user_id: int, category_id: int, period_start: date, period_end: date
) -> Decimal:
    """Calculate total spending for a category in a period."""
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.category_id == category_id,
            Expense.spent_at >= period_start,
            Expense.spent_at <= period_end,
        )
        .scalar()
    )
    return Decimal(str(result))


def check_budget_status(user_id: int, budget_id: int | None = None) -> list[dict]:
    """Check spending status against all active budgets for a user.

    Returns a list of budget status dicts with alert levels.
    If budget_id is provided, checks only that budget.
    """
    q = db.session.query(CategoryBudget).filter_by(user_id=user_id, is_active=True)
    if budget_id:
        q = q.filter_by(id=budget_id)
    budgets = q.all()

    period_start, period_end = _get_current_month_range()
    results = []

    for budget in budgets:
        spent = get_category_spending(
            user_id, budget.category_id, period_start, period_end
        )
        limit = budget.monthly_limit
        pct = (spent / limit * 100) if limit > 0 else Decimal("0")

        # Determine alert level
        alert_level = "normal"
        if pct >= 100:
            alert_level = "exceeded"
        elif pct >= float(budget.critical_threshold):
            alert_level = "critical"
        elif pct >= float(budget.warning_threshold):
            alert_level = "warning"

        # Get category name
        cat = db.session.get(Category, budget.category_id)
        cat_name = cat.name if cat else "Unknown"

        remaining = max(Decimal("0"), limit - spent)
        days_left = (period_end - date.today()).days + 1
        daily_safe = remaining / days_left if days_left > 0 else Decimal("0")

        results.append({
            "budget_id": budget.id,
            "category_id": budget.category_id,
            "category_name": cat_name,
            "monthly_limit": float(limit),
            "spent": float(spent),
            "remaining": float(remaining),
            "percentage_used": float(round(pct, 2)),
            "alert_level": alert_level,
            "warning_threshold": float(budget.warning_threshold),
            "critical_threshold": float(budget.critical_threshold),
            "daily_safe_spend": float(round(daily_safe, 2)),
            "days_remaining": days_left,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "currency": budget.currency,
        })

    return results


# ─── Alert generation ───────────────────────────────────────────────────


def generate_alerts(user_id: int) -> list[dict]:
    """Evaluate all budgets and generate alerts for threshold breaches.

    Only generates alerts that haven't been created in the current period.
    """
    statuses = check_budget_status(user_id)
    period_start, period_end = _get_current_month_range()
    new_alerts = []

    for status in statuses:
        if status["alert_level"] == "normal":
            continue

        # Check if we already generated this alert type for this period
        existing = (
            db.session.query(OverspendAlert)
            .filter_by(
                user_id=user_id,
                budget_id=status["budget_id"],
                alert_type=status["alert_level"],
                period_start=period_start,
                period_end=period_end,
            )
            .first()
        )
        if existing:
            continue

        alert = OverspendAlert(
            user_id=user_id,
            category_id=status["category_id"],
            budget_id=status["budget_id"],
            alert_type=status["alert_level"],
            spent_amount=Decimal(str(status["spent"])),
            budget_limit=Decimal(str(status["monthly_limit"])),
            percentage_used=Decimal(str(status["percentage_used"])),
            period_start=period_start,
            period_end=period_end,
            is_read=False,
        )
        db.session.add(alert)
        new_alerts.append(alert)

    if new_alerts:
        db.session.commit()
        logger.info(
            "Generated %d overspend alerts for user %d",
            len(new_alerts), user_id,
        )

    return [_alert_to_dict(a) for a in new_alerts]


def get_alerts(
    user_id: int, unread_only: bool = False, limit: int = 50
) -> list[dict]:
    """Get overspend alerts for a user."""
    q = db.session.query(OverspendAlert).filter_by(user_id=user_id)
    if unread_only:
        q = q.filter_by(is_read=False)
    alerts = q.order_by(OverspendAlert.created_at.desc()).limit(limit).all()
    return [_alert_to_dict(a) for a in alerts]


def mark_alert_read(user_id: int, alert_id: int) -> bool:
    """Mark an alert as read."""
    alert = (
        db.session.query(OverspendAlert)
        .filter_by(id=alert_id, user_id=user_id)
        .first()
    )
    if not alert:
        return False
    alert.is_read = True
    db.session.commit()
    return True


def mark_all_alerts_read(user_id: int) -> int:
    """Mark all unread alerts as read. Returns count updated."""
    count = (
        db.session.query(OverspendAlert)
        .filter_by(user_id=user_id, is_read=False)
        .update({"is_read": True})
    )
    db.session.commit()
    return count


def get_spending_forecast(user_id: int) -> list[dict]:
    """Forecast end-of-month spending based on current rate.

    Projects whether each budget will be exceeded by extrapolating
    the current daily spending rate.
    """
    statuses = check_budget_status(user_id)
    period_start, _ = _get_current_month_range()
    today = date.today()
    days_elapsed = max(1, (today - period_start).days + 1)

    forecasts = []
    for status in statuses:
        daily_rate = status["spent"] / days_elapsed
        _, last_day = calendar.monthrange(today.year, today.month)
        projected_total = daily_rate * last_day

        forecasts.append({
            "budget_id": status["budget_id"],
            "category_id": status["category_id"],
            "category_name": status["category_name"],
            "current_spent": status["spent"],
            "monthly_limit": status["monthly_limit"],
            "projected_total": round(projected_total, 2),
            "projected_percentage": round(
                projected_total / status["monthly_limit"] * 100
                if status["monthly_limit"] > 0
                else 0, 2
            ),
            "daily_rate": round(daily_rate, 2),
            "will_exceed": projected_total > status["monthly_limit"],
            "projected_overspend": round(
                max(0, projected_total - status["monthly_limit"]), 2
            ),
            "days_remaining": status["days_remaining"],
            "currency": status["currency"],
        })

    return forecasts


# ─── Serialization ──────────────────────────────────────────────────────


def _budget_to_dict(budget: CategoryBudget) -> dict:
    """Convert a CategoryBudget to a dict."""
    cat = db.session.get(Category, budget.category_id)
    return {
        "id": budget.id,
        "user_id": budget.user_id,
        "category_id": budget.category_id,
        "category_name": cat.name if cat else None,
        "monthly_limit": float(budget.monthly_limit),
        "currency": budget.currency,
        "warning_threshold": float(budget.warning_threshold),
        "critical_threshold": float(budget.critical_threshold),
        "is_active": budget.is_active,
        "created_at": budget.created_at.isoformat() if budget.created_at else None,
        "updated_at": budget.updated_at.isoformat() if budget.updated_at else None,
    }


def _alert_to_dict(alert: OverspendAlert) -> dict:
    """Convert an OverspendAlert to a dict."""
    cat = db.session.get(Category, alert.category_id)
    return {
        "id": alert.id,
        "category_id": alert.category_id,
        "category_name": cat.name if cat else None,
        "budget_id": alert.budget_id,
        "alert_type": alert.alert_type,
        "spent_amount": float(alert.spent_amount),
        "budget_limit": float(alert.budget_limit),
        "percentage_used": float(alert.percentage_used),
        "period_start": alert.period_start.isoformat(),
        "period_end": alert.period_end.isoformat(),
        "is_read": alert.is_read,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }
