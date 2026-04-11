"""Rule engine: evaluate AutoTagRule conditions against an expense and compute actions.

This module contains only pure functions — no database access, no Flask context.
That makes it straightforward to unit-test and keeps route handlers thin.

Condition schema
----------------
Each condition is a dict::

    {
        "field":    "description" | "amount" | "expense_type",
        "operator": "contains" | "not_contains" | "regex" | "equals"
                  | "gt" | "lt" | "between",
        "value":    <str, number, or [min, max] for "between">
    }

ALL conditions in a rule must match for the rule to fire (AND semantics).

Action schema
-------------
::

    {
        "set_category_id":  <int | null>,       # optional
        "add_tags":         ["<tag>", ...],     # optional
        "set_expense_type": "<EXPENSE|INCOME>"  # optional
    }
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger("finmind.rule_engine")

# ── condition evaluation ───────────────────────────────────────────────────────


def _get_field_value(expense: dict, field: str) -> Any:
    """Extract the field value from an expense dict (uses canonical key names)."""
    if field == "description":
        return str(expense.get("description") or expense.get("notes") or "")
    if field == "amount":
        try:
            return Decimal(str(expense.get("amount", 0)))
        except (InvalidOperation, ValueError):
            return Decimal(0)
    if field == "expense_type":
        return str(expense.get("expense_type") or "EXPENSE").upper()
    return None


def _evaluate_condition(condition: dict, expense: dict) -> bool:
    """Return True if a single condition matches the expense."""
    field = condition.get("field", "")
    operator = condition.get("operator", "")
    value = condition.get("value")
    actual = _get_field_value(expense, field)

    if actual is None:
        return False

    try:
        if field == "amount":
            # Numeric operators
            if operator == "gt":
                return actual > Decimal(str(value))
            if operator == "lt":
                return actual < Decimal(str(value))
            if operator == "equals":
                return actual == Decimal(str(value))
            if operator == "between":
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    return False
                lo, hi = Decimal(str(value[0])), Decimal(str(value[1]))
                return lo <= actual <= hi
            # String-style operators on amounts (edge case)
            if operator in ("contains", "not_contains", "regex"):
                str_actual = str(actual)
                str_value = str(value)
                if operator == "contains":
                    return str_value.lower() in str_actual.lower()
                if operator == "not_contains":
                    return str_value.lower() not in str_actual.lower()
                if operator == "regex":
                    return bool(re.search(str_value, str_actual, re.IGNORECASE))
        else:
            # String field operators
            str_actual = str(actual)
            str_value = str(value) if value is not None else ""
            if operator == "contains":
                return str_value.lower() in str_actual.lower()
            if operator == "not_contains":
                return str_value.lower() not in str_actual.lower()
            if operator == "equals":
                return str_actual.lower() == str_value.lower()
            if operator == "regex":
                return bool(re.search(str_value, str_actual, re.IGNORECASE))
            # Numeric operators on string fields fall through → False
    except (InvalidOperation, ValueError, re.error) as exc:
        logger.debug("Condition eval error field=%s op=%s: %s", field, operator, exc)
        return False

    logger.debug("Unknown operator %s for field %s", operator, field)
    return False


def _evaluate_rule(conditions: list[dict], expense: dict) -> bool:
    """Return True only if ALL conditions match (AND semantics)."""
    if not conditions:
        # An empty condition list matches everything.
        return True
    return all(_evaluate_condition(c, expense) for c in conditions)


# ── public API ─────────────────────────────────────────────────────────────────


def parse_conditions(raw: str | list) -> list[dict]:
    """Parse conditions from a JSON string or list."""
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []


def parse_actions(raw: str | dict) -> dict:
    """Parse actions from a JSON string or dict."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def apply_rules(expense: dict, rules: list[dict]) -> dict:
    """Evaluate rules against an expense and return a merged dict of changes.

    Parameters
    ----------
    expense:
        Dict with keys: ``description`` (or ``notes``), ``amount``,
        ``expense_type``, ``category_id``.
    rules:
        List of rule dicts sorted by priority (ascending = applied first).
        Each rule dict should have: ``conditions`` (str or list),
        ``actions`` (str or dict).

    Returns
    -------
    dict
        ``{"set_category_id": <int|None>, "add_tags": [<str>...],
           "set_expense_type": <str|None>, "matched_rule_ids": [<int>...]}``
    """
    result: dict[str, Any] = {
        "set_category_id": None,
        "add_tags": [],
        "set_expense_type": None,
        "matched_rule_ids": [],
    }
    category_set = False

    for rule in rules:
        conditions = parse_conditions(rule.get("conditions", []))
        if not _evaluate_rule(conditions, expense):
            continue

        actions = parse_actions(rule.get("actions", {}))
        rule_id = rule.get("id")
        if rule_id is not None:
            result["matched_rule_ids"].append(rule_id)

        # set_category_id: first matching rule wins
        if not category_set and "set_category_id" in actions:
            result["set_category_id"] = actions["set_category_id"]
            category_set = True

        # add_tags: accumulate across all matching rules (deduplication later)
        for tag in actions.get("add_tags") or []:
            tag_str = str(tag).strip()
            if tag_str and tag_str not in result["add_tags"]:
                result["add_tags"].append(tag_str)

        # set_expense_type: first matching rule wins
        if result["set_expense_type"] is None and actions.get("set_expense_type"):
            result["set_expense_type"] = str(actions["set_expense_type"]).upper()

    return result
