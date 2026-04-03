from __future__ import annotations

"""
Rule-based auto tagging & categorization (Issue #107)

Provides a tag management system and rule engine that auto-assigns tags
to expenses based on configurable rules (keyword match, amount range, merchant).
"""

import re
from datetime import date, timedelta
from typing import Optional

from app.models import db, Expense


# ---------------------------------------------------------------------------
# Tag model (stored as simple string tags on Expense)
# ---------------------------------------------------------------------------

class AutoTagRule:
    """In-memory representation of a tagging rule (persisted in DB if Tag/Rule models exist)."""
    def __init__(self, tag: str, field: str, match_type: str, value: str, priority: int = 0):
        self.tag = tag
        self.field = field        # "note", "amount", "category_id"
        self.match_type = match_type  # "contains", "startswith", "regex", "gte", "lte", "between"
        self.value = value
        self.priority = priority

    def matches(self, expense: Expense) -> bool:
        try:
            if self.field in ("note", "description"):
                text = str(getattr(expense, "note", "") or getattr(expense, "description", "") or "").lower()
                v = self.value.lower()
                if self.match_type == "contains":
                    return v in text
                if self.match_type == "startswith":
                    return text.startswith(v)
                if self.match_type == "regex":
                    return bool(re.search(v, text))
            elif self.field == "amount":
                amt = float(getattr(expense, "amount", 0) or 0)
                parts = self.value.split("-")
                if self.match_type == "gte":
                    return amt >= float(self.value)
                if self.match_type == "lte":
                    return amt <= float(self.value)
                if self.match_type == "between" and len(parts) == 2:
                    return float(parts[0]) <= amt <= float(parts[1])
            elif self.field == "category_id":
                return str(getattr(expense, "category_id", "")) == str(self.value)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Default rule set
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[AutoTagRule] = [
    AutoTagRule("dining", "note", "contains", "restaurant"),
    AutoTagRule("dining", "note", "contains", "cafe"),
    AutoTagRule("dining", "note", "contains", "food"),
    AutoTagRule("transport", "note", "contains", "uber"),
    AutoTagRule("transport", "note", "contains", "taxi"),
    AutoTagRule("transport", "note", "contains", "fuel"),
    AutoTagRule("shopping", "note", "contains", "amazon"),
    AutoTagRule("shopping", "note", "contains", "mall"),
    AutoTagRule("health", "note", "contains", "pharmacy"),
    AutoTagRule("health", "note", "contains", "hospital"),
    AutoTagRule("health", "note", "contains", "clinic"),
    AutoTagRule("subscription", "note", "contains", "netflix"),
    AutoTagRule("subscription", "note", "contains", "spotify"),
    AutoTagRule("subscription", "note", "contains", "subscription"),
    AutoTagRule("large_expense", "amount", "gte", "500"),
    AutoTagRule("micro_expense", "amount", "lte", "5"),
]


# ---------------------------------------------------------------------------
# Tag application
# ---------------------------------------------------------------------------

def _parse_tags(expense: Expense) -> list[str]:
    """Parse existing tags stored as comma-separated string in expense.tags field."""
    raw = getattr(expense, "tags", None) or ""
    return [t.strip() for t in raw.split(",") if t.strip()]


def _write_tags(expense: Expense, tags: list[str]) -> None:
    if hasattr(expense, "tags"):
        expense.tags = ",".join(sorted(set(tags)))


def apply_rules_to_expense(expense: Expense, rules: list[AutoTagRule] | None = None) -> list[str]:
    """Apply rules to a single expense and return list of new tags added."""
    if rules is None:
        rules = DEFAULT_RULES
    existing = set(_parse_tags(expense))
    new_tags = []
    for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
        if rule.matches(expense) and rule.tag not in existing:
            new_tags.append(rule.tag)
            existing.add(rule.tag)
    if new_tags:
        _write_tags(expense, list(existing))
    return new_tags


def bulk_auto_tag(uid: int, rules: list[AutoTagRule] | None = None, months: int = 3) -> dict:
    """Auto-tag all expenses for a user over the last N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    expenses = db.session.query(Expense).filter(
        Expense.user_id == uid, Expense.date >= cutoff
    ).all()

    total_tagged = 0
    tag_counts: dict[str, int] = {}
    for exp in expenses:
        added = apply_rules_to_expense(exp, rules)
        if added:
            total_tagged += 1
            for t in added:
                tag_counts[t] = tag_counts.get(t, 0) + 1

    db.session.commit()
    return {
        "expenses_processed": len(expenses),
        "expenses_tagged": total_tagged,
        "tags_applied": tag_counts,
    }


def get_expense_tags(uid: int, expense_id: int) -> list[str]:
    """Return tags for a specific expense."""
    exp = db.session.query(Expense).filter_by(id=expense_id, user_id=uid).first()
    if exp is None:
        raise ValueError(f"Expense {expense_id} not found")
    return _parse_tags(exp)


def set_expense_tags(uid: int, expense_id: int, tags: list[str]) -> list[str]:
    """Manually set tags on an expense."""
    exp = db.session.query(Expense).filter_by(id=expense_id, user_id=uid).first()
    if exp is None:
        raise ValueError(f"Expense {expense_id} not found")
    clean = sorted(set(t.strip().lower() for t in tags if t.strip()))
    _write_tags(exp, clean)
    db.session.commit()
    return clean
