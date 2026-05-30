import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense, RecurringExpense, SavingsSuggestion

logger = logging.getLogger("finmind.savings_opportunity")

SUBSCRIPTION_KEYWORDS = [
    "netflix", "spotify", "hulu", "disney", "prime", "apple",
    "subscription", "membership", "patreon", "dropbox",
    "google one", "icloud", "medium", "new york times",
    "audible", "canva", "figma", "slack", "notion",
]


def generate_suggestions(user_id: int) -> list[dict]:
    suggestions = []
    suggestions.extend(_detect_subscription_overlaps(user_id))
    suggestions.extend(_detect_unused_subscriptions(user_id))
    suggestions.extend(_detect_high_fees(user_id))

    for s in suggestions:
        existing = (
            db.session.query(SavingsSuggestion.id)
            .filter(
                SavingsSuggestion.user_id == user_id,
                SavingsSuggestion.suggestion_type == s["suggestion_type"],
                SavingsSuggestion.title == s["title"],
                SavingsSuggestion.dismissed.is_(False),
            )
            .first()
        )
        if existing:
            continue

        suggestion = SavingsSuggestion(
            user_id=user_id,
            suggestion_type=s["suggestion_type"],
            title=s["title"],
            description=s["description"],
            estimated_savings=s.get("estimated_savings"),
        )
        db.session.add(suggestion)

    db.session.commit()
    return suggestions


def _detect_subscription_overlaps(user_id: int) -> list[dict]:
    results = []
    three_months_ago = date.today() - timedelta(days=90)
    subs = (
        db.session.query(
            Category.name,
            Expense.notes,
            func.sum(Expense.amount).label("total"),
        )
        .join(Category, Category.id == Expense.category_id)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= three_months_ago,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name, Expense.notes)
        .all()
    )

    sub_map: dict[str, list[dict]] = {}
    for cat_name, notes, total in subs:
        notes_lower = (notes or "").lower()
        for keyword in SUBSCRIPTION_KEYWORDS:
            if keyword in notes_lower:
                sub_map.setdefault(cat_name, []).append({
                    "name": notes or "Unknown",
                    "total": float(total or 0),
                })
                break

    if len(sub_map) >= 2:
        total_cost = sum(s["total"] for subs_list in sub_map.values() for s in subs_list)
        savings = round(total_cost * 0.3, 2)
        sub_names = []
        for subs_list in sub_map.values():
            for s in subs_list:
                sub_names.append(s["name"])
        results.append({
            "suggestion_type": "subscription_overlap",
            "title": "Subscription Overlap Detected",
            "description": f"You have overlapping subscriptions across {', '.join(sub_map.keys())}: "
                           f"{', '.join(sub_names)}. Consider consolidating.",
            "estimated_savings": savings,
        })

    return results


def _detect_unused_subscriptions(user_id: int) -> list[dict]:
    results = []
    three_months_ago = date.today() - timedelta(days=90)

    recurring = (
        db.session.query(RecurringExpense)
        .filter(
            RecurringExpense.user_id == user_id,
            RecurringExpense.active.is_(True),
        )
        .all()
    )

    for r in recurring:
        notes_lower = (r.notes or "").lower()
        is_sub = any(k in notes_lower for k in SUBSCRIPTION_KEYWORDS)

        if not is_sub:
            continue

        usage_count = (
            db.session.query(func.count(Expense.id))
            .filter(
                Expense.user_id == user_id,
                Expense.source_recurring_id == r.id,
                Expense.spent_at >= three_months_ago,
            )
            .scalar()
        ) or 0

        if usage_count <= 1:
            results.append({
                "suggestion_type": "unused_subscription",
                "title": f"Unused Subscription: {r.notes}",
                "description": f"'{r.notes}' ({r.currency} {r.amount}/mo) has little or no recent usage.",
                "estimated_savings": float(r.amount * 12),
            })

    return results


def _detect_high_fees(user_id: int) -> list[dict]:
    results = []
    today = date.today()

    total_fees = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type != "INCOME",
            extract("year", Expense.spent_at) == today.year,
        )
        .scalar()
    ) or 0
    total_fees = float(total_fees)

    three_months_ago = today - timedelta(days=90)
    recent_fees = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= three_months_ago,
        )
        .scalar()
    ) or 0
    recent_fees = float(recent_fees)

    projected_annual = recent_fees * 4

    if projected_annual > total_fees * 1.2 and total_fees > 0:
        increase_pct = round((projected_annual - total_fees) / total_fees * 100, 1)
        results.append({
            "suggestion_type": "spending_increase",
            "title": "Spending Trend Alert",
            "description": f"Your spending has increased by ~{increase_pct}% this quarter.",
            "estimated_savings": round(projected_annual - total_fees, 2),
        })

    return results


def list_suggestions(user_id: int, limit: int = 50) -> list[dict]:
    items = (
        db.session.query(SavingsSuggestion)
        .filter(SavingsSuggestion.user_id == user_id, SavingsSuggestion.dismissed.is_(False))
        .order_by(SavingsSuggestion.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": s.id,
            "suggestion_type": s.suggestion_type,
            "title": s.title,
            "description": s.description,
            "estimated_savings": float(s.estimated_savings) if s.estimated_savings else None,
            "dismissed": s.dismissed,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in items
    ]


def dismiss_suggestion(suggestion_id: int, user_id: int) -> bool:
    suggestion = db.session.get(SavingsSuggestion, suggestion_id)
    if not suggestion or suggestion.user_id != user_id:
        return False
    suggestion.dismissed = True
    db.session.commit()
    return True


def refresh_suggestions(user_id: int) -> list[dict]:
    db.session.query(SavingsSuggestion).filter(
        SavingsSuggestion.user_id == user_id, SavingsSuggestion.dismissed.is_(False)
    ).delete()
    db.session.commit()
    return generate_suggestions(user_id)
