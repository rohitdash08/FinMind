"""
Dashboard widget preferences service.

Allows users to customize which widgets are visible on their dashboard
and reorder them to match their priorities.
"""
from __future__ import annotations

from typing import Any

from app.models import db, User
from sqlalchemy import Text
import json as _json

# Default widget configuration
DEFAULT_WIDGETS = [
    {"id": "monthly_summary", "label": "Monthly Summary", "visible": True, "order": 0},
    {"id": "expense_chart", "label": "Expense Chart", "visible": True, "order": 1},
    {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True, "order": 2},
    {"id": "budget_tracker", "label": "Budget Tracker", "visible": True, "order": 3},
    {"id": "recent_expenses", "label": "Recent Expenses", "visible": True, "order": 4},
    {"id": "savings_goals", "label": "Savings Goals", "visible": False, "order": 5},
    {"id": "spending_insights", "label": "Spending Insights", "visible": True, "order": 6},
    {"id": "cash_flow", "label": "Cash Flow", "visible": False, "order": 7},
]

VALID_WIDGET_IDS = {w["id"] for w in DEFAULT_WIDGETS}


def _get_prefs_column(user: User) -> dict:
    """Read widget prefs from user.widget_prefs JSON column."""
    raw = getattr(user, "widget_prefs", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return _json.loads(raw)
    except Exception:
        return {}


def _set_prefs_column(user: User, prefs: dict) -> None:
    """Write widget prefs to user.widget_prefs JSON column."""
    user.widget_prefs = _json.dumps(prefs)


def get_widget_config(uid: int) -> list[dict[str, Any]]:
    """
    Return the user's widget configuration.
    Merges saved preferences with defaults (new widgets are always added).
    """
    user = db.session.get(User, uid)
    if user is None:
        raise ValueError(f"User {uid} not found")

    saved: dict[str, dict] = _get_prefs_column(user)

    result = []
    for default in DEFAULT_WIDGETS:
        widget_id = default["id"]
        if widget_id in saved:
            # Merge: saved overrides visible/order; label always from defaults
            w = dict(default)
            w["visible"] = bool(saved[widget_id].get("visible", default["visible"]))
            w["order"] = int(saved[widget_id].get("order", default["order"]))
            result.append(w)
        else:
            result.append(dict(default))

    result.sort(key=lambda x: x["order"])
    return result


def update_widget_config(uid: int, updates: list[dict]) -> list[dict[str, Any]]:
    """
    Update widget visibility and/or order for a user.

    Each item in updates may contain:
      - id (str, required): widget identifier
      - visible (bool, optional): show/hide the widget
      - order (int, optional): position index (0-based)

    Unknown widget IDs are ignored.
    Returns the full updated configuration.
    """
    user = db.session.get(User, uid)
    if user is None:
        raise ValueError(f"User {uid} not found")

    saved: dict[str, dict] = _get_prefs_column(user)

    for item in updates:
        widget_id = item.get("id")
        if not widget_id or widget_id not in VALID_WIDGET_IDS:
            continue

        entry = saved.get(widget_id, {})
        if "visible" in item:
            entry["visible"] = bool(item["visible"])
        if "order" in item:
            entry["order"] = int(item["order"])
        saved[widget_id] = entry

    _set_prefs_column(user, saved)
    db.session.commit()

    return get_widget_config(uid)


def reset_widget_config(uid: int) -> list[dict[str, Any]]:
    """Reset widget configuration to defaults."""
    user = db.session.get(User, uid)
    if user is None:
        raise ValueError(f"User {uid} not found")
    _set_prefs_column(user, {})
    db.session.commit()
    return get_widget_config(uid)