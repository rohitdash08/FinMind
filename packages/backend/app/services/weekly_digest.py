"""
Weekly digest service for FinMind.

Computes a week-over-week spending summary for a given user, comparing
the current 7-day window against the prior 7-day window.

Intended usage (from the route layer):
    from .services.weekly_digest import build_weekly_digest, digest_to_dict

Public API:
    build_weekly_digest(uid, db_session, reference_date?, currency?) -> WeeklyDigest
    digest_to_dict(digest) -> dict   (JSON-safe)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Category, Expense

logger = logging.getLogger("finmind.weekly_digest")

# ISO 4217 code → display symbol.  Add more as FinMind expands.
_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "JPY": "¥",
    "CNY": "¥",
    "AUD": "A$",
    "CAD": "C$",
    "CHF": "Fr",
    "SGD": "S$",
    "AED": "د.إ",
    "MXN": "MX$",
    "BRL": "R$",
    "KRW": "₩",
    "HKD": "HK$",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
}


def _currency_symbol(code: str) -> str:
    """Return the display symbol for *code*, falling back to the code itself."""
    return _CURRENCY_SYMBOLS.get(code.upper(), code)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _CategorySummary:
    category_id: Optional[int]
    category_name: str
    amount: Decimal
    share_pct: float
    item_count: int


@dataclass
class _WeekSummary:
    week_start: date
    week_end: date
    total_spend: Decimal
    total_income: Decimal
    net_flow: Decimal
    categories: list[_CategorySummary]


@dataclass
class _CategoryTrend:
    category_id: Optional[int]
    category_name: str
    current_amount: Decimal
    prior_amount: Decimal
    delta: Decimal
    direction: str          # "UP" | "DOWN" | "FLAT" | "NEW" | "GONE"
    pct_change: Optional[float]


@dataclass
class WeeklyDigest:
    """Complete week-over-week financial digest for one user."""
    generated_at: date
    user_id: int
    currency: str
    current_week: _WeekSummary
    prior_week: _WeekSummary
    total_spend_delta: Decimal
    total_spend_pct_change: Optional[float]
    category_trends: list[_CategoryTrend]
    top_categories: list[_CategorySummary]
    insights: list[str]


# ---------------------------------------------------------------------------
# Database loader
# ---------------------------------------------------------------------------

def _load_expenses(
    uid: int,
    session: Session,
    window_start: date,
    window_end: date,
    currency: str = "INR",
) -> list[Expense]:
    """Fetch all expenses for a user within the given date window.

    Filters by *currency* so that mixed-currency rows (e.g. EUR expenses
    appearing in an INR digest) are never summed together, which would produce
    silent, meaningless totals.
    """
    return (
        session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.currency == currency,
            Expense.spent_at >= window_start,
            Expense.spent_at <= window_end,
        )
        .order_by(Expense.spent_at.desc())
        .all()
    )


def _category_name_for(expense: Expense, category_map: dict[int, str]) -> str:
    if expense.category_id is None:
        return "Uncategorized"
    return category_map.get(expense.category_id, "Uncategorized")


def _build_category_map(uid: int, session: Session) -> dict[int, str]:
    rows = session.query(Category).filter_by(user_id=uid).all()
    return {c.id: c.name for c in rows}


# ---------------------------------------------------------------------------
# Core aggregation helpers
# ---------------------------------------------------------------------------

def _summarise_window(
    expenses: list[Expense],
    window_start: date,
    window_end: date,
    category_map: dict[int, str],
) -> _WeekSummary:
    """Aggregate a list of Expense ORM objects for a single time window."""
    window = [e for e in expenses if window_start <= e.spent_at <= window_end]

    total_spend = Decimal("0")
    total_income = Decimal("0")
    cat_totals: dict[tuple, dict] = {}

    for exp in window:
        if exp.expense_type == "INCOME":
            total_income += exp.amount
            continue

        total_spend += exp.amount
        cat_name = _category_name_for(exp, category_map)
        key = (exp.category_id, cat_name)
        if key not in cat_totals:
            cat_totals[key] = {"amount": Decimal("0"), "count": 0}
        cat_totals[key]["amount"] += exp.amount
        cat_totals[key]["count"] += 1

    categories: list[_CategorySummary] = []
    for (cat_id, cat_name), totals in sorted(
        cat_totals.items(), key=lambda x: x[1]["amount"], reverse=True
    ):
        share = (
            round(float(totals["amount"] / total_spend) * 100, 2)
            if total_spend > 0
            else 0.0
        )
        categories.append(
            _CategorySummary(
                category_id=cat_id,
                category_name=cat_name,
                amount=totals["amount"],
                share_pct=share,
                item_count=totals["count"],
            )
        )

    return _WeekSummary(
        week_start=window_start,
        week_end=window_end,
        total_spend=total_spend,
        total_income=total_income,
        net_flow=total_income - total_spend,
        categories=categories,
    )


def _compute_trends(
    current: _WeekSummary,
    prior: _WeekSummary,
) -> list[_CategoryTrend]:
    """Week-over-week category deltas."""
    current_map = {c.category_id: c for c in current.categories}
    prior_map = {c.category_id: c for c in prior.categories}
    all_ids = set(current_map) | set(prior_map)

    trends: list[_CategoryTrend] = []
    for cat_id in all_ids:
        curr = current_map.get(cat_id)
        prev = prior_map.get(cat_id)

        current_amt = curr.amount if curr else Decimal("0")
        prior_amt = prev.amount if prev else Decimal("0")
        cat_name = (curr or prev).category_name  # type: ignore[union-attr]
        delta = current_amt - prior_amt

        if prev is None:
            direction, pct_change = "NEW", None
        elif curr is None:
            direction, pct_change = "GONE", None
        elif delta > 0:
            direction = "UP"
            pct_change = round(float(delta / prior_amt) * 100, 1)
        elif delta < 0:
            direction = "DOWN"
            pct_change = round(float(delta / prior_amt) * 100, 1)
        else:
            direction, pct_change = "FLAT", 0.0

        trends.append(
            _CategoryTrend(
                category_id=cat_id,
                category_name=cat_name,
                current_amount=current_amt,
                prior_amount=prior_amt,
                delta=delta,
                direction=direction,
                pct_change=pct_change,
            )
        )

    trends.sort(key=lambda t: abs(t.delta), reverse=True)
    return trends


def _generate_insights(
    current: _WeekSummary,
    prior: _WeekSummary,
    trends: list[_CategoryTrend],
    currency: str,
) -> list[str]:
    """Rule-based plain-English insight strings. No LLM required."""
    insights: list[str] = []
    sym = _currency_symbol(currency)   # "INR" → "₹", "EUR" → "€", etc.

    # Overall spend change
    if prior.total_spend > 0:
        pct = round(
            float((current.total_spend - prior.total_spend) / prior.total_spend) * 100,
            1,
        )
        if pct > 0:
            insights.append(
                f"Spending is up {pct}% vs last week "
                f"({sym} {current.total_spend:.2f} vs {sym} {prior.total_spend:.2f})."
            )
        elif pct < 0:
            insights.append(
                f"Spending is down {abs(pct)}% vs last week — good work! "
                f"({sym} {current.total_spend:.2f} vs {sym} {prior.total_spend:.2f})."
            )
        else:
            insights.append(
                f"Spending is flat week-over-week ({sym} {current.total_spend:.2f})."
            )
    else:
        insights.append(f"Total spend this week: {sym} {current.total_spend:.2f}.")

    # Top category
    if current.categories:
        top = current.categories[0]
        insights.append(
            f"{top.category_name} is your top spending category "
            f"({sym} {top.amount:.2f}, {top.share_pct}% of spend)."
        )

    # Biggest spike
    spikes = [t for t in trends if t.direction == "UP" and t.pct_change is not None]
    if spikes:
        s = spikes[0]
        insights.append(
            f"Biggest increase: {s.category_name} is up "
            f"{s.pct_change}% ({sym} {s.delta:.2f} more than last week)."
        )

    # Biggest drop (positive signal)
    drops = [t for t in trends if t.direction == "DOWN" and t.pct_change is not None]
    if drops:
        d = drops[0]
        insights.append(
            f"Best reduction: {d.category_name} is down "
            f"{abs(d.pct_change)}% ({sym} {abs(d.delta):.2f} less than last week)."
        )

    # New categories
    new_cats = [t for t in trends if t.direction == "NEW"]
    if new_cats:
        names = ", ".join(t.category_name for t in new_cats[:3])
        insights.append(f"New spending this week in: {names}.")

    # Net flow
    if current.net_flow >= 0:
        insights.append(
            f"Net flow is positive: +{sym} {current.net_flow:.2f} "
            f"(income {sym} {current.total_income:.2f} "
            f"\u2212 expenses {sym} {current.total_spend:.2f})."
        )
    else:
        insights.append(
            f"Spent more than earned this week: "
            f"{sym} {abs(current.net_flow):.2f} deficit."
        )

    return insights


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_weekly_digest(
    uid: int,
    session: Session,
    reference_date: Optional[date] = None,
    currency: str = "INR",
) -> WeeklyDigest:
    """
    Build a complete WeeklyDigest for the given user.

    Args:
        uid:            User ID.
        session:        Active SQLAlchemy session (db.session).
        reference_date: Treat as "today" — defaults to date.today().
        currency:       User's preferred currency code for display labels.

    Returns:
        WeeklyDigest with aggregations, trends, and plain-English insights.
    """
    today = reference_date or date.today()

    current_start = today - timedelta(days=6)
    current_end = today
    prior_start = today - timedelta(days=13)
    prior_end = today - timedelta(days=7)

    logger.info(
        "Building weekly digest user=%s current=%s→%s prior=%s→%s",
        uid, current_start, current_end, prior_start, prior_end,
    )

    # Single DB query covering both windows — filtered to user's chosen currency
    # so mixed-currency rows never corrupt aggregated totals.
    all_expenses = _load_expenses(uid, session, prior_start, current_end, currency)
    category_map = _build_category_map(uid, session)

    current = _summarise_window(all_expenses, current_start, current_end, category_map)
    prior = _summarise_window(all_expenses, prior_start, prior_end, category_map)

    total_spend_delta = current.total_spend - prior.total_spend
    total_spend_pct_change = (
        round(float(total_spend_delta / prior.total_spend) * 100, 1)
        if prior.total_spend > 0
        else None
    )

    trends = _compute_trends(current, prior)
    insights = _generate_insights(current, prior, trends, currency)

    return WeeklyDigest(
        generated_at=today,
        user_id=uid,
        currency=currency,
        current_week=current,
        prior_week=prior,
        total_spend_delta=total_spend_delta,
        total_spend_pct_change=total_spend_pct_change,
        category_trends=trends,
        top_categories=current.categories[:3],
        insights=insights,
    )


def digest_to_dict(digest: WeeklyDigest) -> dict:
    """Serialise a WeeklyDigest to a JSON-safe dict."""

    def _week(w: _WeekSummary) -> dict:
        return {
            "week_start": w.week_start.isoformat(),
            "week_end": w.week_end.isoformat(),
            "total_spend": float(w.total_spend),
            "total_income": float(w.total_income),
            "net_flow": float(w.net_flow),
            "categories": [
                {
                    "category_id": c.category_id,
                    "category_name": c.category_name,
                    "amount": float(c.amount),
                    "share_pct": c.share_pct,
                    "item_count": c.item_count,
                }
                for c in w.categories
            ],
        }

    return {
        "generated_at": digest.generated_at.isoformat(),
        "user_id": digest.user_id,
        "currency": digest.currency,
        "current_week": _week(digest.current_week),
        "prior_week": _week(digest.prior_week),
        "total_spend_delta": float(digest.total_spend_delta),
        "total_spend_pct_change": digest.total_spend_pct_change,
        "top_categories": [
            {
                "category_id": c.category_id,
                "category_name": c.category_name,
                "amount": float(c.amount),
                "share_pct": c.share_pct,
            }
            for c in digest.top_categories
        ],
        "category_trends": [
            {
                "category_id": t.category_id,
                "category_name": t.category_name,
                "current_amount": float(t.current_amount),
                "prior_amount": float(t.prior_amount),
                "delta": float(t.delta),
                "direction": t.direction,
                "pct_change": t.pct_change,
            }
            for t in digest.category_trends
        ],
        "insights": digest.insights,
    }
