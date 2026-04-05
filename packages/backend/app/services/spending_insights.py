"""Explainable spending insights (issue #89)."""
import logging
from datetime import date
from sqlalchemy import extract, func
from dateutil.relativedelta import relativedelta
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.insights")


def generate_insights(user_id: int, year: int, month: int) -> dict:
    """Generate plain-English spending insights with explanations."""

    def monthly_by_cat(y, m):
        rows = (db.session.query(
                    func.coalesce(Category.name, "Uncategorized").label("name"),
                    func.sum(Expense.amount).label("total"))
                .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
                .filter(Expense.user_id == user_id,
                        extract("year", Expense.spent_at) == y,
                        extract("month", Expense.spent_at) == m,
                        Expense.expense_type != "INCOME")
                .group_by(Expense.category_id, Category.name).all())
        return {r.name: float(r.total or 0) for r in rows}

    this = monthly_by_cat(year, month)
    prev_date = date(year, month, 1) - relativedelta(months=1)
    prev = monthly_by_cat(prev_date.year, prev_date.month)

    total_this = sum(this.values())
    total_prev = sum(prev.values())
    insights = []

    # Insight 1: Overall trend
    if total_prev > 0:
        change_pct = (total_this - total_prev) / total_prev * 100
        if abs(change_pct) > 5:
            direction = "up" if change_pct > 0 else "down"
            insights.append({
                "type": "trend",
                "title": f"Total spending {direction} {abs(change_pct):.0f}%",
                "explanation": f"You spent ${total_this:.0f} this month vs ${total_prev:.0f} last month — a {abs(change_pct):.1f}% {'increase' if change_pct > 0 else 'decrease'}.",
                "impact": "negative" if change_pct > 10 else "positive" if change_pct < -5 else "neutral",
            })

    # Insight 2: Biggest category spike
    spikes = {cat: (this.get(cat,0) - prev.get(cat,0)) for cat in this}
    if spikes:
        top_spike_cat = max(spikes, key=spikes.get)
        spike_amt = spikes[top_spike_cat]
        if spike_amt > 20:
            insights.append({
                "type": "spike",
                "title": f"{top_spike_cat} spending up ${spike_amt:.0f}",
                "explanation": f"'{top_spike_cat}' increased by ${spike_amt:.0f} compared to last month (${prev.get(top_spike_cat,0):.0f} → ${this.get(top_spike_cat,0):.0f}).",
                "impact": "negative",
            })

    # Insight 3: Biggest category this month
    if this:
        top_cat = max(this, key=this.get)
        top_pct = this[top_cat] / total_this * 100 if total_this else 0
        insights.append({
            "type": "top_category",
            "title": f"{top_cat} is your biggest expense ({top_pct:.0f}%)",
            "explanation": f"${this[top_cat]:.0f} spent on {top_cat} this month — {top_pct:.1f}% of total spending.",
            "impact": "info",
        })

    return {
        "period": f"{year}-{month:02d}",
        "total_this_month": round(total_this, 2),
        "total_last_month": round(total_prev, 2),
        "insights": insights,
        "insight_count": len(insights),
    }
