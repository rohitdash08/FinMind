import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.heatmap")


def daily_spending(uid: int, year: int, month: int | None = None) -> list[dict[str, Any]]:
    q = db.session.query(
        Expense.spent_at, func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        Expense.expense_type != "INCOME",
        extract("year", Expense.spent_at) == year,
    )
    if month is not None:
        q = q.filter(extract("month", Expense.spent_at) == month)
    q = q.group_by(Expense.spent_at).order_by(Expense.spent_at)
    return [{"date": str(row[0]), "amount": float(row[1])} for row in q.all()]


def weekly_spending(uid: int, year: int) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            extract("year", Expense.spent_at).label("yr"),
            extract("week", Expense.spent_at).label("wk"),
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            extract("year", Expense.spent_at) == year,
        )
        .group_by("yr", "wk")
        .order_by("yr", "wk")
        .all()
    )
    return [
        {"year": int(r[0]), "week": int(r[1]), "amount": float(r[2])} for r in rows
    ]


def monthly_spending(uid: int, year: int) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            extract("month", Expense.spent_at).label("mo"),
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            extract("year", Expense.spent_at) == year,
        )
        .group_by("mo")
        .order_by("mo")
        .all()
    )
    return [
        {"month": int(r[0]), "amount": float(r[1])} for r in rows
    ]


def category_heatmap(uid: int, year: int) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            Expense.category_id,
            extract("month", Expense.spent_at).label("mo"),
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            extract("year", Expense.spent_at) == year,
        )
        .group_by(Expense.category_id, "mo")
        .order_by(Expense.category_id, "mo")
        .all()
    )
    return [
        {"category_id": r[0], "month": int(r[1]), "amount": float(r[2])} for r in rows
    ]


def spending_density(uid: int, year: int) -> dict[str, Any]:
    daily = daily_spending(uid, year)
    amounts = [d["amount"] for d in daily]
    if not amounts:
        return {"min": 0, "max": 0, "avg": 0, "total": 0, "days": 0}
    return {
        "min": round(min(amounts), 2),
        "max": round(max(amounts), 2),
        "avg": round(sum(amounts) / len(amounts), 2),
        "total": round(sum(amounts), 2),
        "days": len(amounts),
    }
