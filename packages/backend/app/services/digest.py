"""
Weekly Smart Digest Service
============================

Generates weekly financial summaries with trends, insights, and AI-powered
narrative for FinMind users. Digests highlight spending patterns, anomalies,
and actionable recommendations.

Bounty: rohitdash08/FinMind#121 — $500
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from urllib import request as urllib_request

from sqlalchemy import extract, func, and_

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")
_settings = Settings()

DEFAULT_PERSONA = (
    "You are FinMind's weekly financial digest writer. Be concise, insightful, "
    "and encouraging. Highlight wins (e.g. lower spending) as well as concerns. "
    "Use clear numbers and percentages. Keep tone friendly but data-driven."
)


def _week_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the previous complete week."""
    today = reference_date or date.today()
    # Go to most recent Monday
    last_monday = today - timedelta(days=today.weekday())
    # Previous week
    week_start = last_monday - timedelta(days=7)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _week_expenses(uid: int, start: date, end: date) -> list[Expense]:
    """Fetch all expenses for a user within a date range."""
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .all()
    )


def _week_income(uid: int, start: date, end: date) -> float:
    """Sum income for a user within a date range."""
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(total or 0)


def _category_map(uid: int) -> dict[int, str]:
    """Build category_id -> name mapping for a user."""
    cats = db.session.query(Category).filter_by(user_id=uid).all()
    return {c.id: c.name for c in cats}


def _categorize_expenses(
    expenses: list[Expense], cat_map: dict[int, str]
) -> dict[str, float]:
    """Group expense totals by category name."""
    by_cat: dict[str, float] = {}
    for exp in expenses:
        name = cat_map.get(exp.category_id, "Uncategorized")
        by_cat[name] = by_cat.get(name, 0.0) + float(exp.amount)
    return {k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])}


def _detect_anomalies(
    current_by_cat: dict[str, float],
    prev_by_cat: dict[str, float],
    threshold_pct: float = 50.0,
) -> list[dict[str, Any]]:
    """Identify categories with spending changes exceeding threshold."""
    anomalies = []
    all_cats = set(current_by_cat.keys()) | set(prev_by_cat.keys())
    for cat in all_cats:
        curr = current_by_cat.get(cat, 0.0)
        prev = prev_by_cat.get(cat, 0.0)
        if prev > 0:
            change_pct = ((curr - prev) / prev) * 100
        elif curr > 0:
            change_pct = 100.0  # new category
        else:
            continue
        if abs(change_pct) >= threshold_pct and (curr > 10 or prev > 10):
            anomalies.append(
                {
                    "category": cat,
                    "current_amount": curr,
                    "previous_amount": prev,
                    "change_pct": round(change_pct, 1),
                    "direction": "up" if change_pct > 0 else "down",
                }
            )
    return sorted(anomalies, key=lambda x: abs(x["change_pct"]), reverse=True)


def _upcoming_bills(uid: int, lookahead_days: int = 7) -> list[dict]:
    """Bills due in the next N days."""
    today = date.today()
    cutoff = today + timedelta(days=lookahead_days)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active == True,  # noqa: E712
            Bill.next_due_date >= today,
            Bill.next_due_date <= cutoff,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    return [
        {
            "name": b.name,
            "amount": float(b.amount),
            "due_date": b.next_due_date.isoformat(),
            "autopay": b.autopay_enabled,
        }
        for b in bills
    ]


def _daily_breakdown(
    expenses: list[Expense], start: date, end: date
) -> list[dict[str, Any]]:
    """Per-day spending totals for the week."""
    by_day: dict[str, float] = {}
    current = start
    while current <= end:
        by_day[current.isoformat()] = 0.0
        current += timedelta(days=1)
    for exp in expenses:
        key = exp.spent_at.isoformat()
        if key in by_day:
            by_day[key] += float(exp.amount)
    return [
        {"date": d, "total": round(t, 2), "day_name": date.fromisoformat(d).strftime("%A")}
        for d, t in by_day.items()
    ]


def generate_digest(
    uid: int,
    reference_date: date | None = None,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> dict[str, Any]:
    """
    Generate a complete weekly financial digest for a user.

    Returns a dict with:
      - period: {start, end}
      - summary: {total_spent, total_income, net_flow, transaction_count}
      - comparison: {prev_total_spent, change_pct, trend}
      - by_category: [{name, amount, pct_of_total}]
      - daily_breakdown: [{date, total, day_name}]
      - anomalies: [{category, current_amount, previous_amount, change_pct, direction}]
      - upcoming_bills: [{name, amount, due_date, autopay}]
      - narrative: AI-generated or heuristic summary text
      - top_expense: {amount, notes, category, date} (single largest expense)
    """
    week_start, week_end = _week_bounds(reference_date)
    prev_start = week_start - timedelta(days=7)
    prev_end = week_start - timedelta(days=1)

    cat_map = _category_map(uid)

    # Current week data
    expenses = _week_expenses(uid, week_start, week_end)
    income = _week_income(uid, week_start, week_end)
    total_spent = sum(float(e.amount) for e in expenses)
    by_category = _categorize_expenses(expenses, cat_map)

    # Previous week data
    prev_expenses = _week_expenses(uid, prev_start, prev_end)
    prev_total = sum(float(e.amount) for e in prev_expenses)
    prev_by_category = _categorize_expenses(prev_expenses, cat_map)

    # Comparison
    if prev_total > 0:
        change_pct = round(((total_spent - prev_total) / prev_total) * 100, 1)
    else:
        change_pct = 0.0 if total_spent == 0 else 100.0
    trend = "up" if change_pct > 5 else ("down" if change_pct < -5 else "stable")

    # Category breakdown with percentages
    cat_breakdown = []
    for name, amount in by_category.items():
        pct = round((amount / total_spent * 100) if total_spent > 0 else 0, 1)
        cat_breakdown.append({"name": name, "amount": amount, "pct_of_total": pct})

    # Anomalies
    anomalies = _detect_anomalies(by_category, prev_by_category)

    # Daily breakdown
    daily = _daily_breakdown(expenses, week_start, week_end)

    # Upcoming bills
    bills = _upcoming_bills(uid)

    # Top single expense
    top_expense = None
    if expenses:
        biggest = max(expenses, key=lambda e: float(e.amount))
        top_expense = {
            "amount": float(biggest.amount),
            "notes": biggest.notes or "",
            "category": cat_map.get(biggest.category_id, "Uncategorized"),
            "date": biggest.spent_at.isoformat(),
        }

    # Build digest structure
    digest = {
        "period": {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
        },
        "summary": {
            "total_spent": round(total_spent, 2),
            "total_income": round(income, 2),
            "net_flow": round(income - total_spent, 2),
            "transaction_count": len(expenses),
        },
        "comparison": {
            "prev_total_spent": round(prev_total, 2),
            "change_pct": change_pct,
            "trend": trend,
        },
        "by_category": cat_breakdown,
        "daily_breakdown": daily,
        "anomalies": anomalies,
        "upcoming_bills": bills,
        "top_expense": top_expense,
    }

    # Generate narrative
    persona_text = (persona or DEFAULT_PERSONA).strip()
    narrative = _generate_narrative(digest, gemini_api_key, persona_text)
    digest["narrative"] = narrative

    return digest


def _heuristic_narrative(digest: dict) -> str:
    """Generate a readable narrative without AI."""
    s = digest["summary"]
    c = digest["comparison"]
    parts = []

    # Opening
    period = digest["period"]
    parts.append(
        f"Week of {period['start']} to {period['end']}: "
        f"you spent {s['total_spent']:.2f} across {s['transaction_count']} transactions."
    )

    # Comparison
    if c["trend"] == "up":
        parts.append(
            f"That's {c['change_pct']}% more than last week ({c['prev_total_spent']:.2f})."
        )
    elif c["trend"] == "down":
        parts.append(
            f"Nice — that's {abs(c['change_pct'])}% less than last week ({c['prev_total_spent']:.2f})."
        )
    else:
        parts.append("Spending was roughly flat compared to last week.")

    # Top category
    if digest["by_category"]:
        top = digest["by_category"][0]
        parts.append(
            f"Your biggest category was {top['name']} at {top['amount']:.2f} "
            f"({top['pct_of_total']}% of total)."
        )

    # Anomalies
    if digest["anomalies"]:
        a = digest["anomalies"][0]
        direction_word = "increased" if a["direction"] == "up" else "decreased"
        parts.append(
            f"Notable: {a['category']} {direction_word} {abs(a['change_pct'])}% vs last week."
        )

    # Upcoming bills
    if digest["upcoming_bills"]:
        bill_total = sum(b["amount"] for b in digest["upcoming_bills"])
        parts.append(
            f"Heads up: {len(digest['upcoming_bills'])} bill(s) due soon "
            f"totaling {bill_total:.2f}."
        )

    # Net flow
    if s["net_flow"] < 0:
        parts.append(
            f"You spent {abs(s['net_flow']):.2f} more than you earned this week."
        )
    elif s["net_flow"] > 0:
        parts.append(f"You saved {s['net_flow']:.2f} net this week. Keep it up!")

    return " ".join(parts)


def _generate_narrative(
    digest: dict, gemini_api_key: str | None, persona: str
) -> str:
    """Generate AI narrative using Gemini, falling back to heuristic."""
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    if not key:
        return _heuristic_narrative(digest)

    try:
        return _gemini_narrative(digest, key, persona)
    except Exception as e:
        logger.warning("Gemini narrative failed, using heuristic: %s", e)
        return _heuristic_narrative(digest)


def _gemini_narrative(digest: dict, api_key: str, persona: str) -> str:
    """Call Gemini to generate a narrative digest."""
    model = _settings.gemini_model
    # Build a concise data payload for the LLM
    data_for_llm = {
        "period": digest["period"],
        "total_spent": digest["summary"]["total_spent"],
        "total_income": digest["summary"]["total_income"],
        "net_flow": digest["summary"]["net_flow"],
        "transactions": digest["summary"]["transaction_count"],
        "vs_last_week_pct": digest["comparison"]["change_pct"],
        "trend": digest["comparison"]["trend"],
        "top_categories": digest["by_category"][:5],
        "anomalies": digest["anomalies"][:3],
        "upcoming_bills_count": len(digest["upcoming_bills"]),
        "upcoming_bills_total": sum(
            b["amount"] for b in digest["upcoming_bills"]
        ),
    }

    prompt = (
        f"{persona}\n\n"
        "Write a 3-5 sentence weekly financial digest for the user based on this data. "
        "Highlight the most important trend, any anomalies, and one actionable tip. "
        "Be specific with numbers. Do NOT use bullet points — write flowing prose.\n\n"
        f"Data: {json.dumps(data_for_llm)}"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 300},
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    ).strip()

    if not text:
        raise ValueError("Empty response from Gemini")
    return text
