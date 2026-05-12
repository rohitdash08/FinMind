"""Rule-based auto tagging & categorization engine."""

from ..extensions import db
from ..models import Expense, Category
import logging
import re

logger = logging.getLogger("finmind.autocategorize")

# Default rules - keywords mapped to category patterns
DEFAULT_RULES = [
    {"pattern": r"uber|lyft|taxi|grab|gojek", "category": "Transport"},
    {"pattern": r"netflix|spotify|youtube|disney|hulu", "category": "Subscriptions"},
    {"pattern": r"grocery|supermarket|walmart|costco|bigbasket", "category": "Groceries"},
    {"pattern": r"restaurant|cafe|coffee|starbucks|mcdonald|pizza|food", "category": "Food & Dining"},
    {"pattern": r"electricity|water|gas|internet|phone|mobile", "category": "Utilities"},
    {"pattern": r"rent|mortgage|housing", "category": "Housing"},
    {"pattern": r"gym|fitness|yoga|health|doctor|pharmacy|medical", "category": "Health"},
    {"pattern": r"amazon|shopping|mall|store|purchase", "category": "Shopping"},
    {"pattern": r"salary|income|freelance|payment received", "category": "Income"},
    {"pattern": r"transfer|sent to|received from", "category": "Transfers"},
]


def auto_categorize(user_id: int, notes: str) -> int | None:
    """Suggest a category_id based on expense notes/description.

    First checks user's custom rules (based on historical categorization),
    then falls back to default keyword rules.

    Returns category_id or None if no match.
    """
    if not notes:
        return None

    notes_lower = notes.lower()

    # Try user's historical patterns first
    user_categories = (
        db.session.query(Category).filter_by(user_id=user_id).all()
    )
    cat_map = {c.id: c.name for c in user_categories}

    # Check recent expenses with same keywords
    for cat_id, cat_name in cat_map.items():
        recent = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.category_id == cat_id,
            )
            .order_by(Expense.created_at.desc())
            .limit(20)
            .all()
        )
        for exp in recent:
            if exp.notes and exp.notes.lower() in notes_lower:
                return cat_id

    # Fall back to default rules
    for rule in DEFAULT_RULES:
        if re.search(rule["pattern"], notes_lower):
            # Find or suggest matching category
            for cat_id, cat_name in cat_map.items():
                if cat_name.lower() == rule["category"].lower():
                    return cat_id
            # Category doesn't exist yet - return None (could auto-create)
            break

    return None


def suggest_category_name(notes: str) -> str | None:
    """Suggest a category name based on notes (for new categories)."""
    if not notes:
        return None
    notes_lower = notes.lower()
    for rule in DEFAULT_RULES:
        if re.search(rule["pattern"], notes_lower):
            return rule["category"]
    return None
