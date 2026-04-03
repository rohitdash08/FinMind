"""
Smart onboarding financial setup wizard service.

Guides new users through initial financial setup based on their goals
and lifestyle. Persists wizard state so users can resume incomplete setup.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
import json as _json

from app.extensions import db
from app.models import User, Category


class WizardStep(str, Enum):
    GOALS = "goals"
    INCOME = "income"
    LIFESTYLE = "lifestyle"
    CATEGORIES = "categories"
    COMPLETE = "complete"


STEP_ORDER = [
    WizardStep.GOALS,
    WizardStep.INCOME,
    WizardStep.LIFESTYLE,
    WizardStep.CATEGORIES,
    WizardStep.COMPLETE,
]

# Default categories to auto-create based on lifestyle
LIFESTYLE_CATEGORIES: dict[str, list[str]] = {
    "student": ["Tuition", "Books & Supplies", "Food", "Transport", "Entertainment"],
    "professional": ["Groceries", "Transport", "Dining Out", "Healthcare", "Entertainment"],
    "family": ["Groceries", "Healthcare", "Education", "Childcare", "Utilities", "Transport"],
    "freelancer": ["Business Expenses", "Software Tools", "Marketing", "Transport", "Healthcare"],
    "retiree": ["Healthcare", "Groceries", "Travel", "Utilities", "Entertainment"],
}

VALID_GOALS = {"save_more", "reduce_debt", "build_emergency_fund", "invest", "track_spending"}
VALID_LIFESTYLES = set(LIFESTYLE_CATEGORIES.keys())


def _get_wizard_state(user: User) -> dict:
    raw = getattr(user, "onboarding_state", None)
    if not raw:
        return {"current_step": WizardStep.GOALS.value, "completed_steps": [], "data": {}}
    try:
        return _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {"current_step": WizardStep.GOALS.value, "completed_steps": [], "data": {}}


def _save_wizard_state(user: User, state: dict) -> None:
    user.onboarding_state = _json.dumps(state)
    db.session.commit()


def get_wizard_status(uid: int) -> dict[str, Any]:
    """Return current wizard state for a user."""
    user = db.session.get(User, uid)
    if user is None:
        raise ValueError(f"User {uid} not found")

    state = _get_wizard_state(user)
    return {
        "current_step": state.get("current_step", WizardStep.GOALS.value),
        "completed_steps": state.get("completed_steps", []),
        "is_complete": state.get("current_step") == WizardStep.COMPLETE.value,
        "data": state.get("data", {}),
        "steps": [s.value for s in STEP_ORDER],
    }


def submit_step(uid: int, step: str, payload: dict) -> dict[str, Any]:
    """
    Submit data for a wizard step and advance to the next.

    Returns updated wizard status.
    Raises ValueError for invalid step or data.
    """
    user = db.session.get(User, uid)
    if user is None:
        raise ValueError(f"User {uid} not found")

    try:
        current_step = WizardStep(step)
    except ValueError:
        raise ValueError(f"Invalid step: {step}. Valid: {[s.value for s in STEP_ORDER]}")

    state = _get_wizard_state(user)

    # Validate and process step data
    if current_step == WizardStep.GOALS:
        goals = payload.get("goals", [])
        if not isinstance(goals, list) or len(goals) == 0:
            raise ValueError("goals must be a non-empty list")
        invalid = [g for g in goals if g not in VALID_GOALS]
        if invalid:
            raise ValueError(f"Invalid goals: {invalid}. Valid: {sorted(VALID_GOALS)}")
        state["data"]["goals"] = goals

    elif current_step == WizardStep.INCOME:
        monthly_income = payload.get("monthly_income")
        currency = payload.get("currency", user.preferred_currency)
        if monthly_income is None:
            raise ValueError("monthly_income is required")
        try:
            monthly_income = float(monthly_income)
        except (TypeError, ValueError):
            raise ValueError("monthly_income must be a number")
        if monthly_income < 0:
            raise ValueError("monthly_income must be non-negative")
        state["data"]["monthly_income"] = monthly_income
        state["data"]["currency"] = currency

    elif current_step == WizardStep.LIFESTYLE:
        lifestyle = payload.get("lifestyle")
        if lifestyle not in VALID_LIFESTYLES:
            raise ValueError(f"Invalid lifestyle: {lifestyle}. Valid: {sorted(VALID_LIFESTYLES)}")
        state["data"]["lifestyle"] = lifestyle

    elif current_step == WizardStep.CATEGORIES:
        # Auto-create categories based on lifestyle (or custom list)
        lifestyle = state["data"].get("lifestyle", "professional")
        custom_categories = payload.get("categories")
        cat_names = custom_categories if custom_categories else LIFESTYLE_CATEGORIES.get(lifestyle, [])

        created = []
        for name in cat_names:
            existing = Category.query.filter_by(user_id=uid, name=name).first()
            if not existing:
                cat = Category(user_id=uid, name=name)
                db.session.add(cat)
                created.append(name)
        db.session.flush()
        state["data"]["categories_created"] = created

    # Mark step complete and advance
    completed = state.get("completed_steps", [])
    if current_step.value not in completed:
        completed.append(current_step.value)
    state["completed_steps"] = completed

    # Advance to next step
    idx = STEP_ORDER.index(current_step)
    if idx + 1 < len(STEP_ORDER):
        state["current_step"] = STEP_ORDER[idx + 1].value
    else:
        state["current_step"] = WizardStep.COMPLETE.value

    _save_wizard_state(user, state)
    return get_wizard_status(uid)


def reset_wizard(uid: int) -> dict[str, Any]:
    """Reset wizard to initial state."""
    user = db.session.get(User, uid)
    if user is None:
        raise ValueError(f"User {uid} not found")
    _save_wizard_state(user, {
        "current_step": WizardStep.GOALS.value,
        "completed_steps": [],
        "data": {},
    })
    return get_wizard_status(uid)