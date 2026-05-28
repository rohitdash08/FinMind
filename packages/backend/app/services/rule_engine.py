"""Rule-based auto tagging and categorization engine for FinMind.

Evaluates user-defined rules against transactions to auto-apply tags, categories, and notes.
Supports AND/OR logic, regex, and various field operators.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional

from ..extensions import db
from ..models_rules import TaggingRule

logger = logging.getLogger("finmind.rule_engine")


def create_rule(user_id: int, name: str, conditions: dict, **kwargs) -> TaggingRule:
    """Create a new tagging rule."""
    _validate_conditions(conditions)

    rule = TaggingRule(
        user_id=user_id,
        name=name,
        conditions=conditions,
        tag=kwargs.get("tag"),
        category=kwargs.get("category"),
        note=kwargs.get("note"),
        priority=kwargs.get("priority", 0),
        is_active=kwargs.get("is_active", True),
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Created tagging rule '%s' for user %d", name, user_id)
    return rule


def _validate_conditions(conditions: dict):
    """Validate rule conditions structure."""
    if "field" in conditions:
        # Single condition
        if conditions["field"] not in TaggingRule.FIELDS:
            raise ValueError(f"Invalid field: {conditions['field']}")
        if conditions.get("operator") not in TaggingRule.OPERATORS:
            raise ValueError(f"Invalid operator: {conditions.get('operator')}")
    elif "logic" in conditions:
        # Compound condition
        if conditions["logic"] not in ("AND", "OR"):
            raise ValueError(f"Invalid logic: {conditions['logic']}")
        for sub in conditions.get("rules", []):
            _validate_conditions(sub)
    else:
        raise ValueError("Conditions must have 'field' or 'logic' key")


def evaluate_condition(condition: dict, transaction: dict) -> bool:
    """Evaluate a single condition against a transaction."""
    field = condition.get("field", "")
    operator = condition.get("operator", "")
    value = condition.get("value")

    # Amount field is numeric
    if field == "amount":
        try:
            tx_value = float(transaction.get("amount", 0))
            target = float(value)
        except (TypeError, ValueError):
            return False

        if operator == "greater_than":
            return tx_value > target
        elif operator == "less_than":
            return tx_value < target
        elif operator == "between":
            min_val = float(condition.get("min", 0))
            max_val = float(condition.get("max", 0))
            return min_val <= tx_value <= max_val
        elif operator == "equals":
            return tx_value == target
        return False

    # String fields
    tx_value = str(transaction.get(field, "")).lower()
    target = str(value).lower()

    if operator == "contains":
        return target in tx_value
    elif operator == "not_contains":
        return target not in tx_value
    elif operator == "equals":
        return tx_value == target
    elif operator == "not_equals":
        return tx_value != target
    elif operator == "starts_with":
        return tx_value.startswith(target)
    elif operator == "ends_with":
        return tx_value.endswith(target)
    elif operator == "regex":
        try:
            return bool(re.search(value, tx_value, re.IGNORECASE))
        except re.error:
            return False

    return False


def evaluate_rule(rule: TaggingRule, transaction: dict) -> bool:
    """Evaluate a rule (possibly compound) against a transaction."""
    return _evaluate_conditions(rule.conditions, transaction)


def _evaluate_conditions(conditions: dict, transaction: dict) -> bool:
    """Recursively evaluate conditions."""
    if "logic" in conditions:
        results = [_evaluate_conditions(sub, transaction) for sub in conditions.get("rules", [])]
        if conditions["logic"] == "AND":
            return all(results) if results else False
        else:  # OR
            return any(results) if results else False
    else:
        return evaluate_condition(conditions, transaction)


def apply_rules_to_transaction(user_id: int, transaction: dict) -> dict:
    """Apply all active rules to a transaction. Returns modifications."""
    rules = TaggingRule.query.filter_by(
        user_id=user_id, is_active=True
    ).order_by(TaggingRule.priority.desc()).all()

    modifications = {"tags": [], "category": None, "notes": []}

    for rule in rules:
        if evaluate_rule(rule, transaction):
            if rule.tag:
                modifications["tags"].append(rule.tag)
            if rule.category and not modifications["category"]:
                modifications["category"] = rule.category  # First match wins
            if rule.note:
                modifications["notes"].append(rule.note)

            # Update rule stats
            rule.match_count += 1
            rule.last_matched = datetime.now(timezone.utc)

    if modifications["tags"] or modifications["category"] or modifications["notes"]:
        db.session.commit()

    return modifications


def get_user_rules(user_id: int) -> list[TaggingRule]:
    """Get all rules for a user, ordered by priority."""
    return TaggingRule.query.filter_by(
        user_id=user_id
    ).order_by(TaggingRule.priority.desc(), TaggingRule.created_at.desc()).all()


def delete_rule(rule_id: int, user_id: int) -> bool:
    """Delete a tagging rule."""
    rule = TaggingRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return False
    db.session.delete(rule)
    db.session.commit()
    return True
