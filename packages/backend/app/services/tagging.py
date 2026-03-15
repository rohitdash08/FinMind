"""Rule-based Auto Tagging & Categorization Service.

Users define rules with match conditions. When expenses are created
or checked, matching rules automatically assign categories and tags.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc

from ..extensions import db
from ..models import TaggingRule, Expense, Category, MatchType


# ── Rule CRUD ────────────────────────────────────────────

def create_rule(
    user_id: int,
    name: str,
    match_pattern: str,
    match_field: str = "notes",
    match_type: str = "contains",
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    currency: str | None = None,
    assign_category_id: int | None = None,
    assign_tags: str | None = None,
    priority: int = 0,
    auto_apply: bool = True,
) -> dict:
    """Create a new tagging rule."""
    # Validate category belongs to user
    if assign_category_id:
        cat = Category.query.filter_by(id=assign_category_id, user_id=user_id).first()
        if not cat:
            return None  # Invalid category

    rule = TaggingRule(
        user_id=user_id,
        name=name,
        match_field=match_field,
        match_pattern=match_pattern,
        match_type=match_type,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=currency.upper() if currency else None,
        assign_category_id=assign_category_id,
        assign_tags=assign_tags,
        priority=priority,
        auto_apply=auto_apply,
    )
    db.session.add(rule)
    db.session.commit()
    return _rule_to_dict(rule)


def update_rule(user_id: int, rule_id: int, updates: dict) -> dict | None:
    """Update an existing rule."""
    rule = TaggingRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return None

    allowed = {
        "name", "match_field", "match_pattern", "match_type",
        "min_amount", "max_amount", "currency",
        "assign_category_id", "assign_tags",
        "priority", "is_active", "auto_apply",
    }

    for key, val in updates.items():
        if key in allowed:
            if key == "currency" and val:
                val = val.upper()
            setattr(rule, key, val)

    rule.updated_at = datetime.utcnow()
    db.session.commit()
    return _rule_to_dict(rule)


def delete_rule(user_id: int, rule_id: int) -> bool:
    """Delete a tagging rule."""
    rule = TaggingRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return False
    db.session.delete(rule)
    db.session.commit()
    return True


def get_rule(user_id: int, rule_id: int) -> dict | None:
    """Get a single rule."""
    rule = TaggingRule.query.filter_by(id=rule_id, user_id=user_id).first()
    return _rule_to_dict(rule) if rule else None


def list_rules(user_id: int, active_only: bool = False) -> list[dict]:
    """List all rules for a user, ordered by priority (highest first)."""
    q = TaggingRule.query.filter_by(user_id=user_id)
    if active_only:
        q = q.filter_by(is_active=True)
    rules = q.order_by(desc(TaggingRule.priority)).all()
    return [_rule_to_dict(r) for r in rules]


# ── Rule Matching Engine ─────────────────────────────────

def _matches_pattern(value: str, pattern: str, match_type: str) -> bool:
    """Check if a value matches a pattern based on match type."""
    if not value or not pattern:
        return False
    value_lower = value.lower()
    pattern_lower = pattern.lower()

    if match_type == MatchType.CONTAINS.value:
        return pattern_lower in value_lower
    elif match_type == MatchType.EXACT.value:
        return value_lower == pattern_lower
    elif match_type == MatchType.STARTS_WITH.value:
        return value_lower.startswith(pattern_lower)
    elif match_type == MatchType.ENDS_WITH.value:
        return value_lower.endswith(pattern_lower)
    elif match_type == MatchType.REGEX.value:
        try:
            return bool(re.search(pattern, value, re.IGNORECASE))
        except re.error:
            return False
    return False


def _rule_matches_expense(rule: TaggingRule, expense: Expense) -> bool:
    """Check if a rule matches an expense."""
    # Field match
    if rule.match_field == "notes":
        if not _matches_pattern(expense.notes or "", rule.match_pattern, rule.match_type):
            return False
    elif rule.match_field == "currency":
        if not _matches_pattern(expense.currency or "", rule.match_pattern, rule.match_type):
            return False

    # Amount range check
    amount = Decimal(str(expense.amount)) if expense.amount else Decimal("0")
    if rule.min_amount is not None and amount < Decimal(str(rule.min_amount)):
        return False
    if rule.max_amount is not None and amount > Decimal(str(rule.max_amount)):
        return False

    # Currency filter
    if rule.currency and expense.currency:
        if rule.currency.upper() != expense.currency.upper():
            return False

    return True


def apply_rules_to_expense(user_id: int, expense: Expense) -> dict:
    """Apply all active rules to a single expense.

    Returns dict with applied changes and matched rule IDs.
    """
    rules = (
        TaggingRule.query
        .filter_by(user_id=user_id, is_active=True, auto_apply=True)
        .order_by(desc(TaggingRule.priority))
        .all()
    )

    matched_rules = []
    applied_category = None
    collected_tags = set()

    for rule in rules:
        if _rule_matches_expense(rule, expense):
            matched_rules.append(rule.id)

            # Apply category (highest priority wins)
            if rule.assign_category_id and not applied_category:
                expense.category_id = rule.assign_category_id
                applied_category = rule.assign_category_id

            # Collect tags
            if rule.assign_tags:
                for tag in rule.assign_tags.split(","):
                    tag = tag.strip()
                    if tag:
                        collected_tags.add(tag)

            # Increment applied count
            rule.applied_count += 1

    if matched_rules:
        db.session.commit()

    return {
        "matched_rules": matched_rules,
        "applied_category_id": applied_category,
        "applied_tags": sorted(collected_tags),
        "rules_checked": len(rules),
    }


def test_rules_against_expense(user_id: int, expense_data: dict) -> list[dict]:
    """Dry-run: test which rules would match given expense data.

    Does NOT modify anything.
    """
    rules = (
        TaggingRule.query
        .filter_by(user_id=user_id, is_active=True)
        .order_by(desc(TaggingRule.priority))
        .all()
    )

    # Create a temporary expense-like object
    class FakeExpense:
        pass

    fake = FakeExpense()
    fake.notes = expense_data.get("notes", "")
    fake.amount = Decimal(str(expense_data.get("amount", 0)))
    fake.currency = expense_data.get("currency", "INR")

    matches = []
    for rule in rules:
        if _rule_matches_expense(rule, fake):
            matches.append(_rule_to_dict(rule))

    return matches


def bulk_apply_rules(user_id: int) -> dict:
    """Apply all active rules to all uncategorized expenses.

    Returns summary of changes made.
    """
    rules = (
        TaggingRule.query
        .filter_by(user_id=user_id, is_active=True, auto_apply=True)
        .order_by(desc(TaggingRule.priority))
        .all()
    )

    if not rules:
        return {"expenses_checked": 0, "expenses_updated": 0, "rules_applied": 0}

    # Get uncategorized expenses
    expenses = Expense.query.filter_by(
        user_id=user_id, category_id=None
    ).all()

    updated = 0
    total_applied = 0

    for expense in expenses:
        for rule in rules:
            if _rule_matches_expense(rule, expense):
                if rule.assign_category_id:
                    expense.category_id = rule.assign_category_id
                    rule.applied_count += 1
                    updated += 1
                    total_applied += 1
                    break  # First matching rule wins for category

    db.session.commit()

    return {
        "expenses_checked": len(expenses),
        "expenses_updated": updated,
        "rules_applied": total_applied,
    }


# ── Helpers ──────────────────────────────────────────────

def _rule_to_dict(r: TaggingRule) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "name": r.name,
        "match_field": r.match_field,
        "match_pattern": r.match_pattern,
        "match_type": r.match_type,
        "min_amount": str(r.min_amount) if r.min_amount is not None else None,
        "max_amount": str(r.max_amount) if r.max_amount is not None else None,
        "currency": r.currency,
        "assign_category_id": r.assign_category_id,
        "assign_tags": r.assign_tags,
        "priority": r.priority,
        "is_active": r.is_active,
        "auto_apply": r.auto_apply,
        "applied_count": r.applied_count,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }
