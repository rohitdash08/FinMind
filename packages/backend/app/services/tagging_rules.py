"""
Rule-based auto-tagging and categorization service.
"""
from __future__ import annotations
from ..extensions import db
from ..models import Expense, TaggingRule


def _matches(rule, expense) -> bool:
    field = (rule.match_field or "").lower()
    op = (rule.match_operator or "").lower()
    raw_value = rule.match_value or ""

    if field == "notes":
        target = (expense.notes or "").lower()
        cmp = raw_value.lower()
        if op == "contains":
            return cmp in target
        if op == "starts_with":
            return target.startswith(cmp)
        if op == "ends_with":
            return target.endswith(cmp)
        if op == "equals":
            return target == cmp
        return False

    if field == "amount":
        try:
            threshold = float(raw_value)
            amount = float(expense.amount)
        except (TypeError, ValueError):
            return False
        if op == "gt":
            return amount > threshold
        if op == "lt":
            return amount < threshold
        if op == "gte":
            return amount >= threshold
        if op == "lte":
            return amount <= threshold
        if op == "equals":
            return amount == threshold
        return False

    if field == "category":
        cat_id = str(expense.category_id or "")
        if op == "equals":
            return cat_id == str(raw_value)
        return False

    return False


def apply_rules_to_expense(expense, rules: list) -> dict:
    sorted_rules = sorted(rules, key=lambda r: r.priority)
    category_changed = False
    tags_added = []
    for rule in sorted_rules:
        if not rule.active:
            continue
        if not _matches(rule, expense):
            continue
        if rule.action_set_category_id is not None:
            expense.category_id = rule.action_set_category_id
            category_changed = True
        if rule.action_set_notes_tag:
            clean = rule.action_set_notes_tag.lstrip("#")
            tag = "#" + clean
            current_notes = expense.notes or ""
            if tag not in current_notes:
                expense.notes = (current_notes + " " + tag).strip()
                tags_added.append(tag)
    return {"category_changed": category_changed, "tags_added": tags_added}


def apply_rules_to_all(uid: int) -> dict:
    rules = db.session.query(TaggingRule).filter_by(user_id=uid, active=True).all()
    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    total_changed = 0
    for exp in expenses:
        result = apply_rules_to_expense(exp, rules)
        if result["category_changed"] or result["tags_added"]:
            total_changed += 1
    if total_changed:
        db.session.commit()
    return {"expenses_updated": total_changed, "rules_applied": len(rules)}
