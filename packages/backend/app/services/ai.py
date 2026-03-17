import json
import logging
import math
import re
from datetime import date

import requests
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Category, Expense

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

logger = logging.getLogger("finmind.ai")

_settings = Settings()
DEFAULT_PERSONA = (
    "You are a pragmatic financial analyst and budget coach. Be concise, "
    "non-judgmental, data-driven, and action-oriented. When the user provides "
    "additional context or manual input, factor it into your analysis. "
    "Return actionable, realistic guidance."
)

MIN_MONTHS = 3
MAX_MONTHS = 6
DEFAULT_BUDGET = 500.0


def _month_range(target_ym: str, lookback: int = MAX_MONTHS):
    """Return list of YYYY-MM strings for *lookback* months before *target_ym*."""
    year, month = map(int, target_ym.split("-"))
    anchor = date(year, month, 1)
    return [
        (anchor - relativedelta(months=i)).strftime("%Y-%m")
        for i in range(1, lookback + 1)
    ]


def _fetch_monthly_totals(uid: int, months: list[str]):
    """Fetch total spending (expenses only, excluding INCOME) per month."""
    results = {}
    for ym in months:
        y, m = map(int, ym.split("-"))
        total = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        val = float(total or 0)
        if val > 0:
            results[ym] = val
    return results


def _fetch_category_monthly_totals(uid: int, months: list[str]):
    """Fetch spending per category per month (expenses only)."""
    month_filters = []
    for ym in months:
        y, m = map(int, ym.split("-"))
        month_filters.append((y, m))

    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("cat_name"),
            extract("year", Expense.spent_at).label("yr"),
            extract("month", Expense.spent_at).label("mo"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
        )
        .group_by(
            Expense.category_id,
            Category.name,
            extract("year", Expense.spent_at),
            extract("month", Expense.spent_at),
        )
        .all()
    )

    category_data = {}
    for row in rows:
        ym = f"{int(row.yr):04d}-{int(row.mo):02d}"
        if ym not in months:
            continue
        cat_id = row.category_id
        cat_name = row.cat_name or "Uncategorized"
        if cat_id not in category_data:
            category_data[cat_id] = {"name": cat_name, "monthly": {}}
        category_data[cat_id]["monthly"][ym] = float(row.total)

    return category_data


def _monthly_totals(uid: int, ym: str) -> tuple[float, float]:
    """Return (income, expenses) for a single month."""
    year, month = map(int, ym.split("-"))
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_spend(uid: int, ym: str) -> dict[str, float]:
    year, month = map(int, ym.split("-"))
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _previous_month(ym: str) -> str:
    year, month = map(int, ym.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _build_analytics(uid: int, ym: str) -> dict:
    _, current_expenses = _monthly_totals(uid, ym)
    _, prev_expenses = _monthly_totals(uid, _previous_month(ym))
    if prev_expenses > 0:
        mom = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        mom = 0.0
    cats = _category_spend(uid, ym)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "month_over_month_change_pct": mom,
        "current_month_expenses": round(current_expenses, 2),
        "previous_month_expenses": round(prev_expenses, 2),
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
    }


def _weighted_average(values: list[float]) -> float:
    """Compute weighted average giving more weight to recent months."""
    if not values:
        return 0.0
    n = len(values)
    weights = list(range(1, n + 1))
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return weighted_sum / sum(weights)


def _compute_confidence(months_with_data: int) -> dict:
    if months_with_data <= 0:
        return {"score": 0.0, "label": "no_data", "months_analyzed": 0}

    score = min(1.0, 1 - math.exp(-0.5 * months_with_data))
    score = round(score, 2)

    if score < 0.3:
        label = "low"
    elif score < 0.6:
        label = "medium"
    elif score < 0.85:
        label = "high"
    else:
        label = "very_high"

    return {
        "score": score,
        "label": label,
        "months_analyzed": months_with_data,
    }


def _compute_trend_pct(values: list[float]) -> float:
    """Positive means spending is increasing."""
    if len(values) < 2:
        return 0.0
    recent = values[-1]
    older_avg = sum(values[:-1]) / len(values[:-1])
    if older_avg == 0:
        return 0.0
    return round(((recent - older_avg) / older_avg) * 100, 1)


def _build_category_suggestions(category_data: dict, months: list[str]) -> list[dict]:
    suggestions = []
    sorted_months = sorted(months)

    for cat_id, info in category_data.items():
        monthly = info["monthly"]
        ordered_values = [monthly.get(m, 0.0) for m in sorted_months]
        nonzero = [v for v in ordered_values if v > 0]

        if not nonzero:
            continue

        avg = _weighted_average(nonzero)
        suggested = round(avg * 0.95, 2)
        trend_pct = _compute_trend_pct(nonzero)
        months_active = len(nonzero)

        suggestions.append(
            {
                "category_id": cat_id,
                "category_name": info["name"],
                "suggested_limit": suggested,
                "average_spending": round(avg, 2),
                "trend_pct": trend_pct,
                "trend_direction": (
                    "increasing"
                    if trend_pct > 2
                    else "decreasing" if trend_pct < -2 else "stable"
                ),
                "months_with_data": months_active,
                "monthly_history": {m: monthly.get(m, 0.0) for m in sorted_months},
            }
        )

    suggestions.sort(key=lambda s: s["average_spending"], reverse=True)
    return suggestions


def _heuristic_budget(
    uid: int,
    ym: str,
    lookback: int = MAX_MONTHS,
    persona: str | None = None,
    warnings: list[str] | None = None,
):
    """Multi-month heuristic budget with confidence, analytics, and persona."""
    months = _month_range(ym, lookback)
    monthly_totals = _fetch_monthly_totals(uid, months)
    category_data = _fetch_category_monthly_totals(uid, months)

    months_with_data = len(monthly_totals)
    confidence = _compute_confidence(months_with_data)
    income, expenses = _monthly_totals(uid, ym)

    if not monthly_totals:
        target = DEFAULT_BUDGET
        payload = {
            "month": ym,
            "suggested_total": target,
            "breakdown": {
                "needs": round(target * 0.5, 2),
                "wants": round(target * 0.3, 2),
                "savings": round(target * 0.2, 2),
            },
            "confidence": confidence,
            "category_suggestions": [],
            "data_range": {"months_requested": lookback, "months_with_data": 0},
            "tips": [
                "Cap discretionary spending in the highest category by 10%.",
                "Set one automatic transfer to savings on payday.",
            ],
            "analytics": _build_analytics(uid, ym),
            "persona": persona or DEFAULT_PERSONA,
            "method": "heuristic_default",
        }
        if warnings:
            payload["warnings"] = warnings
        payload["net_flow"] = round(income - expenses, 2)
        return payload

    sorted_months = sorted(monthly_totals.keys())
    ordered_totals = [monthly_totals[m] for m in sorted_months]
    weighted_avg = _weighted_average(ordered_totals)

    reduction = 0.95 if months_with_data >= MIN_MONTHS else 0.90
    target = round(weighted_avg * reduction, 2)

    trend_pct = _compute_trend_pct(ordered_totals)

    category_suggestions = _build_category_suggestions(category_data, months)

    payload = {
        "month": ym,
        "suggested_total": target,
        "breakdown": {
            "needs": round(target * 0.5, 2),
            "wants": round(target * 0.3, 2),
            "savings": round(target * 0.2, 2),
        },
        "confidence": confidence,
        "spending_trend": {
            "direction": (
                "increasing"
                if trend_pct > 2
                else "decreasing" if trend_pct < -2 else "stable"
            ),
            "change_pct": trend_pct,
        },
        "category_suggestions": category_suggestions,
        "data_range": {
            "months_requested": lookback,
            "months_with_data": months_with_data,
            "oldest_month": sorted_months[0],
            "newest_month": sorted_months[-1],
        },
        "monthly_totals": {m: monthly_totals.get(m, 0.0) for m in sorted(months)},
        "tips": [
            "Cap discretionary spending in the highest category by 10%.",
            "Set one automatic transfer to savings on payday.",
        ],
        "analytics": _build_analytics(uid, ym),
        "persona": persona or DEFAULT_PERSONA,
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    payload["net_flow"] = round(income - expenses, 2)
    return payload


FINANCIAL_ANALYST_PERSONA = (
    "You are a certified financial analyst and personal budget coach who "
    "empowers users to build lasting financial health.\n\n"
    "## Core Expertise\n"
    "- Multi-month spending analysis with trend detection and anomaly "
    "identification\n"
    "- Zero-based budgeting and the 50/30/20 rule (needs/wants/savings)\n"
    "- Behavioral nudges: identify impulse-spend categories and suggest "
    "realistic caps\n"
    "- Savings-goal modelling: if the user can cut X, they save Y per year\n"
    "- Debt-to-income ratio awareness and payoff strategies\n"
    "- Income vs. expense gap analysis for net-flow optimization\n\n"
    "## Manual Input Handling\n"
    "When the user provides additional context (upcoming expenses, salary "
    "changes, financial goals, life events such as relocation or a new job), "
    "incorporate that information into the budget suggestion. Adjust the "
    "50/30/20 split and category limits accordingly.\n\n"
    "## Personality\n"
    "- Encouraging yet direct — praise discipline, flag overspending with "
    "specific numbers\n"
    "- Culturally aware — adapt currency symbols and merchant examples to "
    "the user's locale\n"
    "- Concise — no filler, every sentence adds value\n"
    "- Non-judgmental — focus on progress, not perfection\n\n"
    "## Rules\n"
    "1. Always ground advice in the actual transaction data provided.\n"
    "2. If the user shares manual context, blend it with the data-driven "
    "analysis — never ignore user-supplied information.\n"
    "3. Highlight the single biggest saving opportunity first.\n"
    "4. Provide at least 2 actionable tips tied to specific categories.\n"
    "5. When spending in a category is rising, quantify the increase and "
    "suggest a concrete cap.\n"
    "6. Include one short motivational insight.\n"
    "7. Suggest a realistic emergency-fund target when savings data allows.\n"
    "8. Respond ONLY with valid JSON — no markdown, no commentary."
)


def _parse_ai_json(text: str) -> dict:
    """Extract JSON from AI response, stripping markdown fences if present."""
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, flags=re.S)
    if fenced:
        candidate = fenced.group(1)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        candidate = candidate[start : end + 1]
    return json.loads(candidate)


def _gemini_budget_suggestion(
    uid: int,
    ym: str,
    lookback: int = MAX_MONTHS,
    api_key: str | None = None,
    persona: str | None = None,
):
    """Use Gemini to generate budget suggestions with multi-month data."""
    key = api_key or _settings.gemini_api_key
    model = _settings.gemini_model or "gemini-1.5-flash"
    persona_text = (persona or FINANCIAL_ANALYST_PERSONA).strip()

    months = _month_range(ym, lookback)
    monthly_totals = _fetch_monthly_totals(uid, months)
    category_data = _fetch_category_monthly_totals(uid, months)

    months_with_data = len(monthly_totals)
    confidence = _compute_confidence(months_with_data)

    cat_summary = {}
    for cat_id, info in category_data.items():
        cat_summary[info["name"]] = {
            m: info["monthly"].get(m, 0) for m in sorted(months)
        }

    prompt = (
        f"{persona_text}\n\n"
        f"Here is my spending data. Please suggest a budget for {ym}.\n\n"
        f"Monthly totals: {json.dumps(monthly_totals)}\n"
        f"Category breakdown: {json.dumps(cat_summary)}\n\n"
        "Analyse trends and return ONLY valid JSON (no markdown) with:\n"
        "{\n"
        '  "suggested_total": number,\n'
        '  "breakdown": {"needs": number, "wants": number, '
        '"savings": number},\n'
        '  "category_suggestions": [{"category_name": string, '
        '"suggested_limit": number, "reason": string}],\n'
        '  "insights": [string],\n'
        '  "tips": [string]\n'
        "}"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": key},
        json={
            "generationConfig": {"temperature": 0.2},
            "contents": [{"parts": [{"text": prompt}]}],
        },
        timeout=45,
    )
    resp.raise_for_status()

    payload = resp.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates")

    parts = (
        candidates[0].get("content", {}).get("parts", [])
        if isinstance(candidates[0], dict)
        else []
    )
    text_blob = "\n".join(
        str(part.get("text") or "") for part in parts if isinstance(part, dict)
    ).strip()

    obj = _parse_ai_json(text_blob)
    obj["month"] = ym
    obj["method"] = "gemini"
    obj["confidence"] = confidence
    obj["data_range"] = {
        "months_requested": lookback,
        "months_with_data": months_with_data,
    }
    if monthly_totals:
        sorted_keys = sorted(monthly_totals.keys())
        obj["data_range"]["oldest_month"] = sorted_keys[0]
        obj["data_range"]["newest_month"] = sorted_keys[-1]
    obj["monthly_totals"] = {m: monthly_totals.get(m, 0.0) for m in sorted(months)}
    obj["analytics"] = _build_analytics(uid, ym)
    obj["persona"] = persona_text
    return obj


def _openai_budget_suggestion(
    uid: int,
    ym: str,
    lookback: int = MAX_MONTHS,
    persona: str | None = None,
):
    """Use OpenAI to generate budget suggestions from multi-month data."""
    client = OpenAI(api_key=_settings.openai_api_key)
    persona_text = (persona or FINANCIAL_ANALYST_PERSONA).strip()

    months = _month_range(ym, lookback)
    monthly_totals = _fetch_monthly_totals(uid, months)
    category_data = _fetch_category_monthly_totals(uid, months)

    months_with_data = len(monthly_totals)
    confidence = _compute_confidence(months_with_data)

    cat_summary = {}
    for cat_id, info in category_data.items():
        cat_summary[info["name"]] = {
            m: info["monthly"].get(m, 0) for m in sorted(months)
        }

    user_prompt = (
        f"Here is my spending data. Please suggest a budget for {ym}.\n\n"
        f"Monthly totals: {json.dumps(monthly_totals)}\n"
        f"Category breakdown: {json.dumps(cat_summary)}\n\n"
        "Please analyse trends and return ONLY valid JSON with:\n"
        "{\n"
        '  "suggested_total": number,\n'
        '  "breakdown": {"needs": number, "wants": number, "savings": number},\n'
        '  "category_suggestions": [{"category_name": string, '
        '"suggested_limit": number, "reason": string}],\n'
        '  "insights": [string],\n'
        '  "tips": [string]\n'
        "}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": persona_text},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = resp.choices[0].message.content

    obj = json.loads(content)
    obj["month"] = ym
    obj["method"] = "openai"
    obj["confidence"] = confidence
    obj["data_range"] = {
        "months_requested": lookback,
        "months_with_data": months_with_data,
    }
    if monthly_totals:
        sorted_keys = sorted(monthly_totals.keys())
        obj["data_range"]["oldest_month"] = sorted_keys[0]
        obj["data_range"]["newest_month"] = sorted_keys[-1]
    obj["monthly_totals"] = {m: monthly_totals.get(m, 0.0) for m in sorted(months)}
    obj["analytics"] = _build_analytics(uid, ym)
    obj["persona"] = persona_text
    return obj


def monthly_budget_suggestion(
    uid: int,
    ym: str,
    lookback: int = MAX_MONTHS,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    """Generate dynamic budget suggestion.

    Priority: Gemini (free / BYOK) -> OpenAI -> Heuristic fallback.
    """
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")

    if key:
        try:
            return _gemini_budget_suggestion(
                uid, ym, lookback, api_key=key, persona=persona
            )
        except Exception as exc:
            logger.warning("Gemini budget generation failed: %s", exc)

    if _settings.openai_api_key and OpenAI:
        try:
            return _openai_budget_suggestion(uid, ym, lookback, persona=persona)
        except Exception as exc:
            logger.warning("OpenAI budget generation failed: %s", exc)

    warnings = []
    if key:
        warnings.append("gemini_unavailable")
    return _heuristic_budget(
        uid, ym, lookback, persona=persona, warnings=warnings or None
    )
