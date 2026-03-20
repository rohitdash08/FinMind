"""
Intelligent Transaction Categorization Engine.

Features:
- Rule-based categorization: regex pattern matching for 60+ merchant/keyword patterns
- User correction learning: stores overrides and applies them to future transactions
- Confidence scoring: high (0.9) for exact matches, lower for partial/fuzzy
- Batch auto-categorization endpoint for uncategorized expenses
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import re
from datetime import datetime

from ..models import Expense, Category
from .. import db


# ──────────────────────────────────────────────────────────────────────
# Rule table: (pattern, category_name, confidence)
# Patterns are case-insensitive
# ──────────────────────────────────────────────────────────────────────
CATEGORIZATION_RULES: list[tuple[str, str, float]] = [
    # Food & Dining
    (r"\b(mcdonald|burger king|wendy|kfc|popeyes|chick.?fil|taco bell|subway|chipotle|domino|pizza hut|papa john)\b", "Food & Dining", 0.92),
    (r"\b(starbucks|dunkin|peet.?s coffee|costa coffee|tim horton)\b", "Food & Dining", 0.92),
    (r"\b(doordash|ubereats|grubhub|deliveroo|just eat|postmates)\b", "Food & Dining", 0.90),
    (r"\b(restaurant|bistro|diner|cafe|eatery|sushi|ramen|pizzeria|steakhouse|grill|tavern|brasserie)\b", "Food & Dining", 0.80),
    (r"\b(whole foods|trader joe|safeway|kroger|publix|aldi|lidl|costco|sam.?s club|walmart grocery)\b", "Groceries", 0.90),
    (r"\b(grocery|supermarket|market|food store|fresh market)\b", "Groceries", 0.80),
    # Transport
    (r"\b(uber|lyft|bolt|grab|ola cab|didi)\b", "Transportation", 0.90),
    (r"\b(delta|united|american airlines|lufthansa|british airways|ryanair|easyjet|southwest)\b", "Travel", 0.92),
    (r"\b(airbnb|booking\.com|expedia|hotels\.com|hyatt|marriott|hilton|sheraton|radisson)\b", "Travel", 0.92),
    (r"\b(gas station|shell|bp|exxon|chevron|mobil|valero|sunoco|circle k|speedway)\b", "Transportation", 0.90),
    (r"\b(parking|toll|transit|metro|bus pass|train ticket|amtrak|eurostar)\b", "Transportation", 0.80),
    # Shopping
    (r"\b(amazon|ebay|etsy|alibaba|aliexpress|wish\.com|shein|zalando|asos)\b", "Shopping", 0.90),
    (r"\b(apple store|best buy|target|walmart|ikea|home depot|lowe.?s|b&h)\b", "Shopping", 0.88),
    # Entertainment
    (r"\b(netflix|hulu|disney\+|hbo|spotify|apple music|tidal|pandora|youtube premium)\b", "Entertainment", 0.95),
    (r"\b(xbox|playstation|steam|nintendo|epic games|twitch)\b", "Entertainment", 0.92),
    (r"\b(cinema|movie|theater|concert|ticket master|ticketmaster|eventbrite|fandango)\b", "Entertainment", 0.85),
    # Health
    (r"\b(cvs|walgreens|rite aid|boots pharmacy|pharmacy|drugstore)\b", "Health", 0.88),
    (r"\b(doctor|dentist|optometrist|hospital|clinic|urgent care|lab corp|quest diagnostics)\b", "Health", 0.85),
    (r"\b(gym|fitness|planet fitness|la fitness|anytime fitness|crossfit|equinox|peloton)\b", "Health", 0.90),
    # Utilities
    (r"\b(electric|electricity|water bill|gas bill|utility|power company|energy)\b", "Utilities", 0.85),
    (r"\b(comcast|xfinity|at&t|verizon|t.?mobile|spectrum|cox|charter|internet)\b", "Utilities", 0.88),
    # Finance
    (r"\b(insurance|allstate|geico|state farm|progressive|liberty mutual|aetna|cigna|anthem)\b", "Insurance", 0.90),
    (r"\b(mortgage|rent|lease payment|landlord)\b", "Housing", 0.90),
    (r"\b(loan|student loan|auto loan|car payment|credit card payment)\b", "Debt Payments", 0.88),
    # Software / SaaS
    (r"\b(microsoft|adobe|slack|zoom|notion|figma|github|dropbox|google workspace|salesforce)\b", "Software", 0.90),
    # Education
    (r"\b(udemy|coursera|linkedin learning|skillshare|pluralsight|masterclass|duolingo)\b", "Education", 0.92),
    (r"\b(tuition|university|college|school|textbook)\b", "Education", 0.82),
    # Personal Care
    (r"\b(salon|barber|spa|beauty|nail|massage|hairdresser)\b", "Personal Care", 0.85),
    (r"\b(sephora|ulta|mac cosmetics|clinique|lush|bath & body)\b", "Personal Care", 0.88),
    # ATM / Cash
    (r"\b(atm withdrawal|cash withdrawal|atm fee)\b", "Cash & ATM", 0.92),
    # Transfer
    (r"\b(paypal|venmo|zelle|cashapp|wise|revolut|transfer|wire)\b", "Transfers", 0.85),
]

# Compiled rules for performance
_COMPILED_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(pattern, re.IGNORECASE), category, confidence)
    for pattern, category, confidence in CATEGORIZATION_RULES
]


@dataclass
class CategorizationSuggestion:
    expense_id: int
    description: str
    suggested_category: str
    confidence: float
    source: str  # "rule", "user_history", "fallback"


def _match_rules(description: str) -> tuple[str, float, str]:
    """
    Apply rule-based categorization. Returns (category, confidence, source).
    """
    desc_clean = description.strip()
    for pattern, category, confidence in _COMPILED_RULES:
        if pattern.search(desc_clean):
            return category, confidence, "rule"
    return "Uncategorized", 0.40, "fallback"


def _match_user_history(user_id: int, description: str) -> tuple[Optional[str], float]:
    """
    Look up user's correction history for this description or similar descriptions.
    Returns (category, confidence) if match found, else (None, 0.0).
    """
    desc_lower = description.lower().strip()
    # Look for exact description match in recent user corrections
    match = (
        Expense.query
        .filter(
            Expense.user_id == user_id,
            Expense.description.ilike(desc_lower),
            Expense.category_id.isnot(None),
        )
        .order_by(Expense.id.desc())
        .first()
    )
    if match and match.category_id:
        category = Category.query.get(match.category_id)
        if category:
            return category.name, 0.88

    # Partial match: any expense containing key words
    words = [w for w in desc_lower.split() if len(w) > 3]
    for word in words[:3]:  # check top 3 words
        match = (
            Expense.query
            .filter(
                Expense.user_id == user_id,
                Expense.description.ilike(f"%{word}%"),
                Expense.category_id.isnot(None),
            )
            .order_by(Expense.id.desc())
            .first()
        )
        if match and match.category_id:
            category = Category.query.get(match.category_id)
            if category:
                return category.name, 0.72

    return None, 0.0


def categorize_transaction(
    user_id: int,
    description: str,
    amount: Optional[float] = None,
) -> CategorizationSuggestion:
    """
    Suggest a category for a transaction description.
    Priority: user history > rule-based > fallback.

    Args:
        user_id: User ID (for personalization from correction history)
        description: Transaction description text
        amount: Optional transaction amount (unused but reserved for ML)

    Returns:
        CategorizationSuggestion with category, confidence, and source.
    """
    expense_id = 0  # placeholder for batch use

    # 1. Check user correction history (personalized)
    hist_category, hist_confidence = _match_user_history(user_id, description)
    if hist_category and hist_confidence > 0:
        return CategorizationSuggestion(
            expense_id=expense_id,
            description=description,
            suggested_category=hist_category,
            confidence=hist_confidence,
            source="user_history",
        )

    # 2. Rule-based matching
    category, confidence, source = _match_rules(description)
    return CategorizationSuggestion(
        expense_id=expense_id,
        description=description,
        suggested_category=category,
        confidence=confidence,
        source=source,
    )


def auto_categorize_batch(user_id: int, min_confidence: float = 0.75) -> dict:
    """
    Auto-categorize all expenses for a user that have no category or
    have confidence below threshold.

    Args:
        user_id: User ID
        min_confidence: Only apply if confidence >= this threshold

    Returns:
        Dict with counts and list of applied suggestions.
    """
    # Get uncategorized expenses
    expenses = (
        Expense.query
        .filter(
            Expense.user_id == user_id,
            Expense.category_id.is_(None),
        )
        .limit(200)  # cap per-call to avoid timeout
        .all()
    )

    applied = []
    skipped = []

    for exp in expenses:
        suggestion = categorize_transaction(user_id, exp.description or "", exp.amount)
        suggestion.expense_id = exp.id

        if suggestion.confidence >= min_confidence and suggestion.source != "fallback":
            # Find or create category
            cat = Category.query.filter_by(
                user_id=user_id,
                name=suggestion.suggested_category
            ).first()
            if not cat:
                cat = Category(user_id=user_id, name=suggestion.suggested_category)
                db.session.add(cat)
                db.session.flush()

            exp.category_id = cat.id
            applied.append({
                "expense_id": exp.id,
                "description": exp.description,
                "category": suggestion.suggested_category,
                "confidence": suggestion.confidence,
                "source": suggestion.source,
            })
        else:
            skipped.append({
                "expense_id": exp.id,
                "description": exp.description,
                "suggested_category": suggestion.suggested_category,
                "confidence": suggestion.confidence,
                "reason": "low_confidence" if suggestion.confidence < min_confidence else "fallback",
            })

    db.session.commit()

    return {
        "total_uncategorized": len(expenses),
        "applied": len(applied),
        "skipped": len(skipped),
        "min_confidence_used": min_confidence,
        "suggestions_applied": applied,
        "suggestions_skipped": skipped,
    }


def get_category_suggestion(
    user_id: int,
    description: str,
) -> dict:
    """
    Return a single category suggestion for the given description.
    Does NOT modify any data.
    """
    suggestion = categorize_transaction(user_id, description)
    return {
        "description": description,
        "suggested_category": suggestion.suggested_category,
        "confidence": suggestion.confidence,
        "source": suggestion.source,
    }