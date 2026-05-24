"""
FinMind — Weekly Financial Summary Service

Generates AI-powered weekly summaries highlighting spending trends,
budget insights, and actionable recommendations.

Fixes applied:
  1. N+1 queries → single CASE-WHEN aggregation per date range
  2. API key no longer accepted from client headers — server-side only
  3. urllib replaced with httpx (explicit SSL verify=True)
  4. Broad `except Exception` split into precise exception types
  5. Date boundary: `spent_at <= week_end` → `spent_at < next_day`
  6. ref_date future-date validation moved to route layer
  7. Test isolation via db_session fixture (see tests/)
  8. WEEKLY_PERSONA now locale-aware via _build_persona()
  9. Response caching + rate-limiting hooks (applied in route layer)
"""

import json
import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import case, func, text

from ..config import Settings
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.weekly_summary")
_settings = Settings()

# ---------------------------------------------------------------------------
# Fix #8 — locale-aware persona builder
# ---------------------------------------------------------------------------

_PERSONAS: dict[str, str] = {
    "en": (
        "You are FinMind's pragmatic financial coach. Be concise, non-judgmental, "
        "data-driven, and action-oriented. Return actionable, realistic guidance "
        "for a weekly financial summary."
    ),
    "zh": (
        "你是 FinMind 的理财教练，请用简体中文回答。风格简洁、客观、以数据为依据，"
        "给出切实可行的每周财务建议。"
    ),
    "es": (
        "Eres el coach financiero de FinMind. Sé conciso, objetivo y orientado "
        "a datos. Devuelve orientación realista y accionable en español."
    ),
}


def _build_persona(locale: str = "en") -> str:
    return _PERSONAS.get(locale, _PERSONAS["en"])


# ---------------------------------------------------------------------------
# Week range helpers
# ---------------------------------------------------------------------------

def _week_range(ref: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) of the ISO week containing *ref*."""
    if ref is None:
        ref = date.today()
    start = ref - timedelta(days=ref.weekday())
    return start, start + timedelta(days=6)


def _previous_week_range(ref: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) of the week before *ref*'s week."""
    if ref is None:
        ref = date.today()
    this_monday = ref - timedelta(days=ref.weekday())
    last_monday = this_monday - timedelta(days=7)
    return last_monday, last_monday + timedelta(days=6)


# ---------------------------------------------------------------------------
# Fix #1 — single aggregation query replaces 3 separate scalar queries
# Fix #5 — date boundary uses `< next_day` instead of `<= week_end`
# ---------------------------------------------------------------------------

def _week_totals(
    uid: int, week_start: date, week_end: date
) -> tuple[float, float, int]:
    """Return (income, expenses, transaction_count) using ONE SQL query."""
    next_day = week_end + timedelta(days=1)

    row = (
        db.session.query(
            func.coalesce(
                func.sum(
                    case(
                        (Expense.expense_type == "INCOME", Expense.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("income"),
            func.coalesce(
                func.sum(
                    case(
                        (Expense.expense_type != "INCOME", Expense.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("expenses"),
            func.count(Expense.id).label("txn_count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at < next_day,  # Fix #5: exclusive upper bound
        )
        .one()
    )

    return float(row.income), float(row.expenses), int(row.txn_count)


def _week_category_spend(
    uid: int, week_start: date, week_end: date
) -> dict[str, float]:
    """Return {category_id: total_amount} for expense rows in the week."""
    next_day = week_end + timedelta(days=1)  # Fix #5

    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at < next_day,  # Fix #5
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _daily_breakdown(
    uid: int, week_start: date, week_end: date
) -> list[dict]:
    """Return daily spend totals for the week."""
    next_day = week_end + timedelta(days=1)  # Fix #5

    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at < next_day,  # Fix #5
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    return [{"date": str(d), "amount": round(float(a), 2)} for d, a in rows]


# ---------------------------------------------------------------------------
# Analytics builder — now makes only 3 DB round-trips instead of 8
# (week_totals=1, category_spend=1, daily_breakdown=1)
# ---------------------------------------------------------------------------

def _build_weekly_analytics(uid: int, week_start: date, week_end: date) -> dict:
    income, expenses, txn_count = _week_totals(uid, week_start, week_end)
    cats = _week_category_spend(uid, week_start, week_end)
    top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
    daily = _daily_breakdown(uid, week_start, week_end)

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": round(income - expenses, 2),
        "transaction_count": txn_count,
        "daily_spend": daily,
        "top_categories": [
            {"category_id": k, "amount": round(v, 2)} for k, v in top_cats
        ],
    }


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------

def _heuristic_weekly_summary(
    uid: int,
    this_week: tuple[date, date],
    last_week: tuple[date, date],
    warnings: list[str] | None = None,
) -> dict:
    """Rule-based summary — used when AI is unavailable."""
    current = _build_weekly_analytics(uid, *this_week)
    previous = _build_weekly_analytics(uid, *last_week)

    prev_exp = previous["total_expenses"]
    curr_exp = current["total_expenses"]
    wow = _calc_wow(curr_exp, prev_exp)

    tips: list[str] = []
    if prev_exp > 0:
        if curr_exp > prev_exp:
            tips.append(
                f"Spending increased {wow:.1f}% week-over-week. "
                "Review discretionary categories."
            )
        else:
            tips.append(
                f"Great work — spending dropped {abs(wow):.1f}% vs last week."
            )

    if current["top_categories"]:
        top = current["top_categories"][0]
        tips.append(
            f"Highest spend: {top['category_id']} at ${top['amount']:.2f}. "
            "Consider setting a weekly limit."
        )

    payload: dict = {
        "type": "weekly_summary",
        "this_week": current,
        "previous_week": previous,
        "week_over_week_change_pct": wow,
        "tips": tips or ["Track daily expenses to spot patterns."],
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


# ---------------------------------------------------------------------------
# Fix #3 — httpx with explicit SSL verification replaces urllib
# Fix #4 — precise exception types instead of bare `except Exception`
# Fix #8 — locale forwarded to prompt builder
# ---------------------------------------------------------------------------

def _extract_json_object(raw: str) -> dict:
    """Extract a JSON object from model output, stripping markdown fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("no JSON object found in model output", text, 0)
    return json.loads(text[start : end + 1])  # raises json.JSONDecodeError on bad JSON


def _ai_weekly_summary(
    uid: int,
    this_week: tuple[date, date],
    last_week: tuple[date, date],
    model: str,
    locale: str = "en",
) -> dict:
    """Generate weekly summary using Gemini AI.

    Fix #2: API key is read exclusively from server-side settings.
    Fix #3: httpx replaces urllib; SSL verification is always enabled.
    """
    api_key = (_settings.gemini_api_key or "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured on the server")

    current = _build_weekly_analytics(uid, *this_week)
    previous = _build_weekly_analytics(uid, *last_week)

    prompt = (
        f"{_build_persona(locale)}\n"
        "Use this week's financial data and return STRICT JSON only — no markdown "
        "fences, no extra keys. Required keys:\n"
        "  summary (string), highlights (array ≤3), concerns (array ≤3), tips (array ≤3)\n\n"
        f"This week ({this_week[0]} → {this_week[1]}):\n"
        f"  income={current['total_income']}, expenses={current['total_expenses']}, "
        f"transactions={current['transaction_count']}\n"
        f"  top_categories={current['top_categories']}\n"
        f"  daily_spend={current['daily_spend']}\n\n"
        f"Previous week ({last_week[0]} → {last_week[1]}):\n"
        f"  income={previous['total_income']}, expenses={previous['total_expenses']}\n"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }

    # Fix #3: httpx with verify=True (default) — no urllib, no nosec workarounds
    with httpx.Client(timeout=10.0, verify=True) as client:
        response = client.post(
            url,
            json=body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()  # raises httpx.HTTPStatusError on 4xx/5xx
        payload = response.json()

    raw_text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    # Fix #4: let json.JSONDecodeError propagate — caller handles it specifically
    ai_part = _extract_json_object(raw_text)

    return {
        "type": "weekly_summary",
        "this_week": current,
        "previous_week": previous,
        "week_over_week_change_pct": _calc_wow(
            current["total_expenses"], previous["total_expenses"]
        ),
        **ai_part,
        "method": "gemini",
    }


def _calc_wow(current: float, previous: float) -> float:
    if previous > 0:
        return round(((current - previous) / previous) * 100, 2)
    return 0.0


# ---------------------------------------------------------------------------
# Public entry point
# Fix #2: gemini_api_key parameter removed — key never comes from caller
# Fix #8: locale parameter added
# ---------------------------------------------------------------------------

def weekly_summary(
    uid: int,
    ref_date: date | None = None,
    gemini_model: str | None = None,
    locale: str = "en",
) -> dict:
    """Generate a weekly financial summary for *uid*.

    Returns a dict with:
      type, this_week, previous_week, week_over_week_change_pct,
      tips / summary / highlights / concerns, method, [warnings]
    """
    if ref_date is None:
        ref_date = date.today()

    this_week = _week_range(ref_date)
    last_week = _previous_week_range(ref_date)
    model = gemini_model or _settings.gemini_model
    has_key = bool((_settings.gemini_api_key or "").strip())

    if has_key:
        try:
            return _ai_weekly_summary(uid, this_week, last_week, model, locale)

        except json.JSONDecodeError as exc:
            # AI returned malformed JSON — degrade gracefully
            logger.warning("AI response parse error for uid=%s: %s", uid, exc)
            return _heuristic_weekly_summary(
                uid, this_week, last_week,
                warnings=[f"ai_parse_error: {exc}"],
            )

        except httpx.HTTPStatusError as exc:
            # 4xx / 5xx from Gemini endpoint
            logger.warning(
                "Gemini HTTP %s for uid=%s: %s",
                exc.response.status_code, uid, exc,
            )
            return _heuristic_weekly_summary(
                uid, this_week, last_week,
                warnings=[f"gemini_http_error: {exc.response.status_code}"],
            )

        except httpx.TimeoutException as exc:
            logger.warning("Gemini timeout for uid=%s: %s", uid, exc)
            return _heuristic_weekly_summary(
                uid, this_week, last_week,
                warnings=["gemini_timeout"],
            )

        except (httpx.RequestError, ValueError) as exc:
            # Network issues or missing key config
            logger.warning("Gemini request error for uid=%s: %s", uid, exc)
            return _heuristic_weekly_summary(
                uid, this_week, last_week,
                warnings=[f"gemini_unavailable: {exc}"],
            )

    return _heuristic_weekly_summary(uid, this_week, last_week)
