"""
Smart Onboarding Financial Setup Wizard (Issue #101).

Guides new users through a personalized initial financial setup based on
their stated goals and lifestyle profile.

The wizard is implemented as a stateless service: the client drives the
multi-step flow by passing the current step + accumulated answers.  Each
call returns the next step definition and any recommendations produced so far.

Steps
-----
1. profile       — basic lifestyle (income range, family size, rent/own)
2. goals         — primary financial goals (save, pay debt, invest, etc.)
3. spending      — typical spending categories the user wants to track
4. budget_method — preferred budgeting approach (50/30/20, zero-based, envelope)
5. complete      — summary + initial budget recommendations + pre-seeded categories

No DB writes occur until step 5 (complete), which optionally creates the
initial category list for the user.

Public API
----------
get_step(step_name)                    → StepDefinition dict
process_step(uid, step, answers)       → StepResult dict
complete_onboarding(uid, all_answers)  → OnboardingResult dict
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import Category, User

logger = logging.getLogger("finmind.onboarding")

# ── Step definitions ──────────────────────────────────────────────────────────

STEPS = ["profile", "goals", "spending", "budget_method", "complete"]

_STEP_DEFS: dict[str, dict] = {
    "profile": {
        "step": "profile",
        "title": "Tell us about yourself",
        "description": "Help us personalise your financial setup.",
        "fields": [
            {
                "key": "income_range",
                "label": "Monthly income range",
                "type": "select",
                "options": [
                    {"value": "low",    "label": "Under ₹25,000"},
                    {"value": "mid",    "label": "₹25,000 – ₹75,000"},
                    {"value": "high",   "label": "₹75,000 – ₹1,50,000"},
                    {"value": "very_high", "label": "Above ₹1,50,000"},
                ],
                "required": True,
            },
            {
                "key": "housing",
                "label": "Housing situation",
                "type": "select",
                "options": [
                    {"value": "rent",  "label": "Renting"},
                    {"value": "own",   "label": "Own home (no mortgage)"},
                    {"value": "mortgage", "label": "Paying mortgage"},
                    {"value": "family", "label": "Living with family"},
                ],
                "required": True,
            },
            {
                "key": "dependents",
                "label": "Number of financial dependents",
                "type": "select",
                "options": [
                    {"value": "0", "label": "None"},
                    {"value": "1", "label": "1"},
                    {"value": "2", "label": "2–3"},
                    {"value": "3+", "label": "4 or more"},
                ],
                "required": False,
            },
        ],
        "next_step": "goals",
    },
    "goals": {
        "step": "goals",
        "title": "What are your financial goals?",
        "description": "Choose up to 3 goals that matter most to you right now.",
        "fields": [
            {
                "key": "primary_goals",
                "label": "Primary goals",
                "type": "multiselect",
                "max_selections": 3,
                "options": [
                    {"value": "emergency_fund",  "label": "Build emergency fund"},
                    {"value": "pay_debt",        "label": "Pay off debt"},
                    {"value": "save_home",       "label": "Save for a home"},
                    {"value": "invest",          "label": "Start investing"},
                    {"value": "reduce_spending", "label": "Reduce monthly spending"},
                    {"value": "track_spending",  "label": "Simply track spending"},
                    {"value": "retirement",      "label": "Plan for retirement"},
                ],
                "required": True,
            },
        ],
        "next_step": "spending",
    },
    "spending": {
        "step": "spending",
        "title": "How do you usually spend?",
        "description": "Select the categories you want to track.",
        "fields": [
            {
                "key": "categories",
                "label": "Spending categories",
                "type": "multiselect",
                "options": [
                    {"value": "food",        "label": "Food & Groceries"},
                    {"value": "dining",      "label": "Dining & Restaurants"},
                    {"value": "transport",   "label": "Transport & Fuel"},
                    {"value": "utilities",   "label": "Utilities & Bills"},
                    {"value": "health",      "label": "Health & Medical"},
                    {"value": "education",   "label": "Education"},
                    {"value": "shopping",    "label": "Shopping & Clothing"},
                    {"value": "entertainment","label": "Entertainment"},
                    {"value": "travel",      "label": "Travel & Holidays"},
                    {"value": "savings",     "label": "Savings & Investments"},
                    {"value": "emi",         "label": "EMI / Loan Repayment"},
                    {"value": "insurance",   "label": "Insurance"},
                ],
                "required": True,
            },
        ],
        "next_step": "budget_method",
    },
    "budget_method": {
        "step": "budget_method",
        "title": "Choose your budgeting style",
        "description": "Pick the approach that fits your personality.",
        "fields": [
            {
                "key": "method",
                "label": "Budgeting method",
                "type": "select",
                "options": [
                    {
                        "value": "50_30_20",
                        "label": "50/30/20 Rule",
                        "description": "50% needs, 30% wants, 20% savings. Simple and popular.",
                    },
                    {
                        "value": "zero_based",
                        "label": "Zero-based budgeting",
                        "description": "Every rupee has a job. Best for tight control.",
                    },
                    {
                        "value": "envelope",
                        "label": "Envelope method",
                        "description": "Fixed cash envelopes per category. Visual and tactile.",
                    },
                    {
                        "value": "pay_yourself_first",
                        "label": "Pay yourself first",
                        "description": "Save a fixed amount first, spend the rest freely.",
                    },
                ],
                "required": True,
            },
        ],
        "next_step": "complete",
    },
    "complete": {
        "step": "complete",
        "title": "You're all set! 🎉",
        "description": "Here's your personalized financial setup.",
        "fields": [],
        "next_step": None,
    },
}

# ── Category mapping ──────────────────────────────────────────────────────────

_CATEGORY_LABELS = {
    "food": "Food & Groceries",
    "dining": "Dining & Restaurants",
    "transport": "Transport & Fuel",
    "utilities": "Utilities & Bills",
    "health": "Health & Medical",
    "education": "Education",
    "shopping": "Shopping & Clothing",
    "entertainment": "Entertainment",
    "travel": "Travel & Holidays",
    "savings": "Savings & Investments",
    "emi": "EMI / Loan Repayment",
    "insurance": "Insurance",
}

# ── Budget recommendation engine ──────────────────────────────────────────────

_INCOME_MIDPOINTS = {
    "low":      20000,
    "mid":      50000,
    "high":    112500,
    "very_high": 200000,
}

_GOAL_SAVINGS_BOOST = {
    "emergency_fund": 0.05,
    "pay_debt":       0.10,
    "save_home":      0.10,
    "invest":         0.05,
    "retirement":     0.05,
    "reduce_spending": 0.05,
    "track_spending": 0.0,
}


def _build_budget_recommendations(answers: dict) -> dict[str, Any]:
    income_range = answers.get("profile", {}).get("income_range", "mid")
    income_est   = _INCOME_MIDPOINTS.get(income_range, 50000)
    goals        = answers.get("goals", {}).get("primary_goals", [])
    method       = answers.get("budget_method", {}).get("method", "50_30_20")
    housing      = answers.get("profile", {}).get("housing", "rent")
    dependents   = answers.get("profile", {}).get("dependents", "0")

    # Extra savings boost based on goals
    savings_boost = sum(_GOAL_SAVINGS_BOOST.get(g, 0) for g in goals[:3])
    savings_pct   = min(0.40, 0.20 + savings_boost)

    # Adjust needs pct for housing & dependents
    needs_pct = 0.50
    if housing in ("rent", "mortgage"):
        needs_pct += 0.05
    if dependents in ("2", "3+"):
        needs_pct += 0.05
    needs_pct = min(0.70, needs_pct)
    wants_pct = max(0.10, 1.0 - needs_pct - savings_pct)

    rec = {
        "method": method,
        "estimated_monthly_income": income_est,
        "needs_budget":    round(income_est * needs_pct, 2),
        "wants_budget":    round(income_est * wants_pct, 2),
        "savings_budget":  round(income_est * savings_pct, 2),
        "needs_pct":       round(needs_pct * 100, 1),
        "wants_pct":       round(wants_pct * 100, 1),
        "savings_pct":     round(savings_pct * 100, 1),
        "goal_notes": [
            f"Extra {_GOAL_SAVINGS_BOOST[g]*100:.0f}% savings allocation for '{g}'"
            for g in goals[:3]
            if _GOAL_SAVINGS_BOOST.get(g, 0) > 0
        ],
    }
    return rec


def _build_tips(answers: dict) -> list[str]:
    goals   = answers.get("goals", {}).get("primary_goals", [])
    method  = answers.get("budget_method", {}).get("method", "50_30_20")
    housing = answers.get("profile", {}).get("housing", "rent")
    tips = []

    if "emergency_fund" in goals:
        tips.append("Aim for 3–6 months of expenses in your emergency fund before investing.")
    if "pay_debt" in goals:
        tips.append("Use the avalanche method: pay off highest-interest debt first.")
    if "invest" in goals:
        tips.append("Start with index funds — low cost, diversified, long-term growth.")
    if method == "zero_based":
        tips.append("Review your zero-based budget weekly to catch overspending early.")
    if method == "envelope":
        tips.append("Set up your envelopes on the 1st of each month with fresh allocations.")
    if housing == "rent":
        tips.append("Keep rent below 30% of take-home pay if possible.")

    return tips[:4]  # max 4 tips at onboarding


# ── Public API ────────────────────────────────────────────────────────────────

def get_step(step_name: str) -> dict[str, Any] | None:
    """Return the step definition for *step_name*, or None if unknown."""
    return _STEP_DEFS.get(step_name)


def validate_step_answers(step_name: str, answers: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    step_def = _STEP_DEFS.get(step_name)
    if not step_def:
        return [f"Unknown step: {step_name}"]
    errors = []
    for field in step_def["fields"]:
        if field.get("required") and not answers.get(field["key"]):
            errors.append(f"'{field['key']}' is required for step '{step_name}'")
    return errors


def complete_onboarding(uid: int, all_answers: dict) -> dict[str, Any]:
    """
    Finalize onboarding: create suggested categories in the DB and return
    the full personalized setup summary.
    """
    selected_cats = all_answers.get("spending", {}).get("categories", [])
    budget_rec    = _build_budget_recommendations(all_answers)
    tips          = _build_tips(all_answers)

    # Create categories in DB (idempotent — skip if name already exists)
    created_categories = []
    existing_names = {
        c.name for c in db.session.query(Category).filter_by(user_id=uid).all()
    }
    for cat_key in selected_cats:
        label = _CATEGORY_LABELS.get(cat_key, cat_key.title())
        if label not in existing_names:
            cat = Category(user_id=uid, name=label)
            db.session.add(cat)
            created_categories.append(label)

    db.session.commit()
    logger.info("Onboarding complete uid=%s categories_created=%d", uid, len(created_categories))

    return {
        "status":              "complete",
        "categories_created":  created_categories,
        "budget_recommendation": budget_rec,
        "tips":                tips,
        "next_steps": [
            "Add your first expense to start tracking",
            "Set up bill reminders for recurring payments",
            "Review your budget at the end of this month",
        ],
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }
