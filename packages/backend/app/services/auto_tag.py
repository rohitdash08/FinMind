"""Rule-based auto-tagging engine for expenses.

Supported condition types:
  - keyword_match: case-insensitive substring match on expense notes
  - amount_range: min/max bounds on expense amount (inclusive)
  - merchant_match: case-insensitive substring match on expense notes (merchant name)

A rule matches when ALL its conditions are satisfied (AND logic).
When multiple rules match, the one with the highest priority wins (ties broken by id).
"""

from decimal import Decimal
from typing import Optional

from ..extensions import db
from ..models import AutoTagRule


def match_rule(
    user_id: int,
    notes: str,
    amount: Decimal,
) -> Optional[int]:
    """Return target_category_id of the best matching rule, or None."""
    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=user_id, active=True)
        .order_by(AutoTagRule.priority.desc(), AutoTagRule.id.asc())
        .all()
    )
    for rule in rules:
        if _evaluate_rule(rule, notes, amount):
            return rule.target_category_id
    return None


def _evaluate_rule(rule: AutoTagRule, notes: str, amount: Decimal) -> bool:
    """Return True if all conditions in the rule are satisfied."""
    conditions = rule.conditions or []
    if not conditions:
        return False
    for cond in conditions:
        if not _evaluate_condition(cond, notes, amount):
            return False
    return True


def _evaluate_condition(cond: dict, notes: str, amount: Decimal) -> bool:
    ctype = cond.get("type", "")
    notes_lower = (notes or "").lower()

    if ctype == "keyword_match":
        keyword = (cond.get("value") or "").lower().strip()
        if not keyword:
            return False
        return keyword in notes_lower

    if ctype == "merchant_match":
        merchant = (cond.get("value") or "").lower().strip()
        if not merchant:
            return False
        return merchant in notes_lower

    if ctype == "amount_range":
        min_val = cond.get("min")
        max_val = cond.get("max")
        if min_val is not None and amount < Decimal(str(min_val)):
            return False
        if max_val is not None and amount > Decimal(str(max_val)):
            return False
        return True

    # Unknown condition type — fail closed
    return False
