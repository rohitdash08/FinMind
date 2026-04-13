import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Bill, Category, Expense, WeeklyDigest

logger = logging.getLogger("finmind.weekly_digest")


def get_week_range(ref_date: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) for the week containing ref_date."""
    d = ref_date or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _aggregate_income_expenses(uid: int, week_start: date, week_end: date) -> tuple[float, float]:
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _top_spending_category(uid: int, week_start: date, week_end: date) -> tuple[str | None, float]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(1)
        .all()
    )
    if rows:
        return rows[0].name, float(rows[0].total or 0)
    return None, 0.0


def _bills_summary(uid: int, week_start: date, week_end: date) -> tuple[int, int]:
    bills_due = (
        db.session.query(func.count(Bill.id))
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= week_start,
            Bill.next_due_date <= week_end,
        )
        .scalar()
    )
    # Bills "paid" this week: those whose next_due_date was moved past the week
    # We approximate by counting bills whose next_due_date > week_end (they were
    # recently paid and advanced). This is a heuristic consistent with the
    # mark_paid behaviour that advances next_due_date.
    bills_paid = (
        db.session.query(func.count(Bill.id))
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date > week_end,
        )
        .scalar()
    )
    return int(bills_due or 0), int(bills_paid or 0)


def _savings_goal_progress(uid: int, week_start: date, week_end: date) -> dict:
    """Placeholder – savings goal model not yet in schema.
    Returns an empty dict; wired for future SavingsGoal integration."""
    return {}


def _compute_wow_change(uid: int, week_start: date, week_end: date) -> float | None:
    prev_start = week_start - timedelta(days=7)
    prev_end = week_end - timedelta(days=7)
    _, cur_exp = _aggregate_income_expenses(uid, week_start, week_end)
    _, prev_exp = _aggregate_income_expenses(uid, prev_start, prev_end)
    if prev_exp > 0:
        return round(((cur_exp - prev_exp) / prev_exp) * 100, 2)
    return None


def _build_summary_text(
    week_start: date,
    week_end: date,
    income: float,
    expenses: float,
    net: float,
    top_cat: str | None,
    top_amt: float,
    bills_due: int,
    bills_paid: int,
    wow: float | None,
) -> str:
    lines: list[str] = []
    lines.append(
        f"Weekly Summary ({week_start.isoformat()} to {week_end.isoformat()})"
    )
    lines.append(f"Income: {income:,.2f}")
    lines.append(f"Expenses: {expenses:,.2f}")
    lines.append(f"Net savings: {net:,.2f}")
    if top_cat:
        lines.append(f"Top spending category: {top_cat} ({top_amt:,.2f})")
    lines.append(f"Bills due this week: {bills_due}")
    if wow is not None:
        direction = "increase" if wow > 0 else "decrease"
        lines.append(f"Expenses {direction} of {abs(wow):.1f}% vs last week")
    return " | ".join(lines)


def _digest_to_dict(d: WeeklyDigest) -> dict:
    progress = None
    if d.savings_goal_progress:
        try:
            progress = json.loads(d.savings_goal_progress)
        except (json.JSONDecodeError, TypeError):
            progress = None
    return {
        "id": d.id,
        "user_id": d.user_id,
        "week_start": d.week_start.isoformat(),
        "week_end": d.week_end.isoformat(),
        "total_income": float(d.total_income),
        "total_expenses": float(d.total_expenses),
        "net_savings": float(d.net_savings),
        "top_category": d.top_category,
        "top_expense_amount": float(d.top_expense_amount),
        "bills_due_count": d.bills_due_count,
        "bills_paid_count": d.bills_paid_count,
        "savings_goal_progress": progress,
        "summary_text": d.summary_text,
        "wow_expense_change_pct": float(d.wow_expense_change_pct) if d.wow_expense_change_pct is not None else None,
        "generated_at": d.generated_at.isoformat() if d.generated_at else None,
    }


def generate_weekly_digest(uid: int, ref_date: date | None = None) -> dict:
    week_start, week_end = get_week_range(ref_date)
    income, expenses = _aggregate_income_expenses(uid, week_start, week_end)
    net = round(income - expenses, 2)
    top_cat, top_amt = _top_spending_category(uid, week_start, week_end)
    bills_due, bills_paid = _bills_summary(uid, week_start, week_end)
    goal_progress = _savings_goal_progress(uid, week_start, week_end)
    wow = _compute_wow_change(uid, week_start, week_end)

    summary = _build_summary_text(
        week_start, week_end, income, expenses, net,
        top_cat, top_amt, bills_due, bills_paid, wow,
    )

    existing = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=uid, week_start=week_start, week_end=week_end)
        .first()
    )
    if existing:
        existing.total_income = Decimal(str(income))
        existing.total_expenses = Decimal(str(expenses))
        existing.net_savings = Decimal(str(net))
        existing.top_category = top_cat
        existing.top_expense_amount = Decimal(str(top_amt))
        existing.bills_due_count = bills_due
        existing.bills_paid_count = bills_paid
        existing.savings_goal_progress = json.dumps(goal_progress) if goal_progress else None
        existing.summary_text = summary
        existing.wow_expense_change_pct = Decimal(str(wow)) if wow is not None else None
        db.session.commit()
        return _digest_to_dict(existing)

    digest = WeeklyDigest(
        user_id=uid,
        week_start=week_start,
        week_end=week_end,
        total_income=Decimal(str(income)),
        total_expenses=Decimal(str(expenses)),
        net_savings=Decimal(str(net)),
        top_category=top_cat,
        top_expense_amount=Decimal(str(top_amt)),
        bills_due_count=bills_due,
        bills_paid_count=bills_paid,
        savings_goal_progress=json.dumps(goal_progress) if goal_progress else None,
        summary_text=summary,
        wow_expense_change_pct=Decimal(str(wow)) if wow is not None else None,
    )
    db.session.add(digest)
    db.session.commit()
    logger.info("Generated weekly digest user=%s week=%s", uid, week_start.isoformat())
    return _digest_to_dict(digest)


def get_weekly_digest(uid: int, ref_date: date | None = None) -> dict:
    """Return existing digest or generate one."""
    week_start, week_end = get_week_range(ref_date)
    existing = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=uid, week_start=week_start, week_end=week_end)
        .first()
    )
    if existing:
        return _digest_to_dict(existing)
    return generate_weekly_digest(uid, ref_date)


def list_digest_history(uid: int, limit: int = 20) -> list[dict]:
    rows = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=uid)
        .order_by(WeeklyDigest.week_start.desc())
        .limit(limit)
        .all()
    )
    return [_digest_to_dict(r) for r in rows]
