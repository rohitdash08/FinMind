"""
Intelligent Transaction Categorization Service

Provides rule-based auto-categorization with:
- Keyword matching with configurable rules
- Confidence scoring (0.0 - 1.0)
- Learning from user corrections
- Fallback to default "Uncategorized" when confidence is low
"""

import re
from typing import Any

from ..extensions import db
from ..models import Category

# Default keyword rules: keywords → (category_name, base_confidence)
DEFAULT_RULES: dict[str, tuple[str, float]] = {
    # Food & Dining
    "restaurant": ("Food & Dining", 0.95),
    "cafe": ("Food & Dining", 0.90),
    "coffee": ("Food & Dining", 0.85),
    "pizza": ("Food & Dining", 0.90),
    "burger": ("Food & Dining", 0.85),
    "sushi": ("Food & Dining", 0.90),
    "mcdonald": ("Food & Dining", 0.95),
    "starbucks": ("Food & Dining", 0.95),
    "uber eats": ("Food & Dining", 0.95),
    "swiggy": ("Food & Dining", 0.95),
    "zomato": ("Food & Dining", 0.95),
    "doordash": ("Food & Dining", 0.95),
    "grubhub": ("Food & Dining", 0.95),
    "deliveroo": ("Food & Dining", 0.95),
    "dining": ("Food & Dining", 0.90),
    "grocery": ("Food & Dining", 0.85),
    "supermarket": ("Food & Dining", 0.85),
    "market": ("Food & Dining", 0.70),
    # Transportation
    "uber": ("Transportation", 0.90),
    "lyft": ("Transportation", 0.95),
    "taxi": ("Transportation", 0.90),
    "fuel": ("Transportation", 0.85),
    "petrol": ("Transportation", 0.90),
    "gas station": ("Transportation", 0.90),
    "parking": ("Transportation", 0.85),
    "toll": ("Transportation", 0.90),
    "metro": ("Transportation", 0.90),
    "bus": ("Transportation", 0.80),
    "train": ("Transportation", 0.80),
    "flight": ("Transportation", 0.85),
    "airline": ("Transportation", 0.85),
    "ola": ("Transportation", 0.95),
    "rapido": ("Transportation", 0.95),
    # Shopping
    "amazon": ("Shopping", 0.95),
    "flipkart": ("Shopping", 0.95),
    "ebay": ("Shopping", 0.90),
    "walmart": ("Shopping", 0.90),
    "target": ("Shopping", 0.85),
    "mall": ("Shopping", 0.80),
    "store": ("Shopping", 0.70),
    "shop": ("Shopping", 0.75),
    "clothing": ("Shopping", 0.85),
    "fashion": ("Shopping", 0.80),
    "ikea": ("Shopping", 0.95),
    "nike": ("Shopping", 0.95),
    "adidas": ("Shopping", 0.95),
    # Bills & Utilities
    "electric": ("Bills & Utilities", 0.90),
    "electricity": ("Bills & Utilities", 0.95),
    "water bill": ("Bills & Utilities", 0.95),
    "gas bill": ("Bills & Utilities", 0.90),
    "internet": ("Bills & Utilities", 0.90),
    "broadband": ("Bills & Utilities", 0.90),
    "phone bill": ("Bills & Utilities", 0.90),
    "mobile": ("Bills & Utilities", 0.70),
    "utility": ("Bills & Utilities", 0.85),
    "wifi": ("Bills & Utilities", 0.90),
    "bseb": ("Bills & Utilities", 0.95),
    "msedcl": ("Bills & Utilities", 0.95),
    "bsnl": ("Bills & Utilities", 0.95),
    "jio": ("Bills & Utilities", 0.85),
    "airtel": ("Bills & Utilities", 0.85),
    # Entertainment
    "netflix": ("Entertainment", 0.95),
    "spotify": ("Entertainment", 0.95),
    "disney": ("Entertainment", 0.90),
    "hbo": ("Entertainment", 0.90),
    "movie": ("Entertainment", 0.85),
    "cinema": ("Entertainment", 0.90),
    "theatre": ("Entertainment", 0.85),
    "gaming": ("Entertainment", 0.85),
    "steam": ("Entertainment", 0.90),
    "playstation": ("Entertainment", 0.90),
    "xbox": ("Entertainment", 0.90),
    "concert": ("Entertainment", 0.90),
    "ticket": ("Entertainment", 0.70),
    "youtube": ("Entertainment", 0.80),
    "hotstar": ("Entertainment", 0.95),
    "prime video": ("Entertainment", 0.95),
    # Health
    "pharmacy": ("Health", 0.90),
    "hospital": ("Health", 0.90),
    "doctor": ("Health", 0.90),
    "medical": ("Health", 0.85),
    "dental": ("Health", 0.90),
    "clinic": ("Health", 0.85),
    "insurance": ("Health", 0.75),
    "medicine": ("Health", 0.85),
    "apollo": ("Health", 0.90),
    "1mg": ("Health", 0.90),
    "pharmeasy": ("Health", 0.90),
    # Housing & Rent
    "rent": ("Housing & Rent", 0.90),
    "mortgage": ("Housing & Rent", 0.95),
    "property": ("Housing & Rent", 0.75),
    "maintenance": ("Housing & Rent", 0.70),
    "hoa": ("Housing & Rent", 0.95),
    # Subscriptions & Software
    "subscription": ("Subscriptions", 0.85),
    "saas": ("Subscriptions", 0.90),
    "adobe": ("Subscriptions", 0.90),
    "microsoft 365": ("Subscriptions", 0.95),
    "gcp": ("Subscriptions", 0.85),
    "aws": ("Subscriptions", 0.85),
    "azure": ("Subscriptions", 0.85),
    "openai": ("Subscriptions", 0.90),
    "chatgpt": ("Subscriptions", 0.90),
    # Income & Salary
    "salary": ("Income", 0.95),
    "payroll": ("Income", 0.95),
    "freelance": ("Income", 0.85),
    "consulting": ("Income", 0.85),
    "dividend": ("Income", 0.90),
    "interest": ("Income", 0.80),
    "refund": ("Income", 0.85),
    "cashback": ("Income", 0.90),
}

# Confidence threshold — below this, return "Uncategorized"
CONFIDENCE_THRESHOLD = 0.5


class CategorizationRule:
    """Represents a single categorization rule with keyword and category."""

    def __init__(self, keyword: str, category_name: str, confidence: float, source: str = "default"):
        self.keyword = keyword.lower().strip()
        self.category_name = category_name
        self.confidence = min(1.0, max(0.0, confidence))
        self.source = source  # "default", "learned", "user"

    def matches(self, description: str) -> float | None:
        """Return confidence if this rule matches the description, else None."""
        desc_lower = description.lower().strip()
        if self.keyword in desc_lower:
            return self.confidence
        return None


class CategorizationResult:
    """Result of a categorization attempt."""

    def __init__(
        self,
        category: str,
        confidence: float,
        matched_rule: str | None = None,
        alternatives: list[dict[str, Any]] | None = None,
    ):
        self.category = category
        self.confidence = confidence
        self.matched_rule = matched_rule
        self.alternatives = alternatives or []

    def to_dict(self) -> dict[str, Any]:
        result = {
            "category": self.category,
            "confidence": round(self.confidence, 2),
        }
        if self.matched_rule:
            result["matched_rule"] = self.matched_rule
        if self.alternatives:
            result["alternatives"] = self.alternatives
        return result


def _load_default_rules() -> list[CategorizationRule]:
    """Load default keyword rules."""
    return [
        CategorizationRule(keyword=k, category_name=v[0], confidence=v[1], source="default")
        for k, v in DEFAULT_RULES.items()
    ]


def categorize_transaction(
    description: str,
    existing_category_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Categorize a transaction based on its description.

    Args:
        description: Transaction description text
        existing_category_id: If user already selected a category, use it as a hint
        user_id: User ID for loading user-specific learned rules

    Returns:
        Dict with category, confidence, matched_rule, and alternatives
    """
    if not description or not description.strip():
        return CategorizationResult(category="Uncategorized", confidence=0.0).to_dict()

    desc_lower = description.lower().strip()
    rules = _load_default_rules()

    # Load user-learned rules if user_id provided
    if user_id:
        rules.extend(_load_learned_rules(user_id))

    # Find all matching rules, sorted by confidence (highest first)
    matches: list[tuple[float, str, str]] = []  # (confidence, keyword, category)
    for rule in rules:
        conf = rule.matches(desc_lower)
        if conf is not None:
            matches.append((conf, rule.keyword, rule.category_name))

    # Sort by confidence descending
    matches.sort(key=lambda x: x[0], reverse=True)

    if not matches:
        return CategorizationResult(
            category="Uncategorized",
            confidence=0.0,
        ).to_dict()

    best_conf, best_keyword, best_category = matches[0]

    # Build alternatives list
    alternatives = []
    seen_categories = {best_category}
    for conf, kw, cat in matches[1:5]:  # Top 4 alternatives
        if cat not in seen_categories and conf >= 0.5:
            alternatives.append({"category": cat, "confidence": round(conf, 2)})
            seen_categories.add(cat)

    # Below threshold → Uncategorized
    if best_conf < CONFIDENCE_THRESHOLD:
        return CategorizationResult(
            category="Uncategorized",
            confidence=best_conf,
            alternatives=alternatives,
        ).to_dict()

    return CategorizationResult(
        category=best_category,
        confidence=best_conf,
        matched_rule=best_keyword,
        alternatives=alternatives,
    ).to_dict()


def learn_from_correction(
    description: str,
    correct_category: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Learn from a user's manual categorization correction.

    Extracts keywords from the description and stores them as
    learned rules for future categorization.

    Args:
        description: Original transaction description
        correct_category: The correct category the user assigned
        user_id: User ID to associate learned rules with

    Returns:
        Dict with status and number of rules learned
    """
    if not description or not correct_category:
        return {"status": "error", "message": "description and category required"}

    desc_lower = description.lower().strip()

    # Extract meaningful keywords (3+ chars, not common stop words)
    stop_words = {
        "the", "and", "for", "that", "this", "with", "from", "have", "has",
        "was", "were", "been", "will", "would", "could", "should", "shall",
        "about", "into", "your", "you", "are", "not", "but", "can", "did",
    }
    words = re.findall(r'\b[a-z]{3,}\b', desc_lower)
    keywords = [w for w in words if w not in stop_words]

    learned_count = 0
    learned_keywords = []

    if user_id:
        from ..models import CategorizationRule as RuleModel
        for keyword in keywords[:5]:  # Max 5 rules per correction
            # Check if rule already exists
            existing = (
                db.session.query(RuleModel)
                .filter_by(user_id=user_id, keyword=keyword)
                .first()
            )
            if existing:
                # Boost confidence
                existing.confidence = min(1.0, existing.confidence + 0.05)
                existing.category_name = correct_category
            else:
                rule = RuleModel(
                    user_id=user_id,
                    keyword=keyword,
                    category_name=correct_category,
                    confidence=0.80,
                    source="learned",
                )
                db.session.add(rule)
            learned_count += 1
            learned_keywords.append(keyword)
        db.session.commit()

    return {
        "status": "ok",
        "learned_count": learned_count,
        "keywords": learned_keywords,
        "category": correct_category,
    }


def _load_learned_rules(user_id: int) -> list[CategorizationRule]:
    """Load learned rules for a specific user from the database."""
    try:
        from ..models import CategorizationRule as RuleModel
        db_rules = (
            db.session.query(RuleModel)
            .filter_by(user_id=user_id)
            .all()
        )
        return [
            CategorizationRule(
                keyword=r.keyword,
                category_name=r.category_name,
                confidence=r.confidence,
                source=r.source,
            )
            for r in db_rules
        ]
    except Exception:
        return []


def batch_categorize(
    transactions: list[dict[str, Any]],
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Categorize multiple transactions at once.

    Args:
        transactions: List of dicts with 'description' and optional 'category_id'
        user_id: User ID for personalized rules

    Returns:
        List of categorization results
    """
    results = []
    for txn in transactions:
        desc = txn.get("description", "")
        cat_id = txn.get("category_id")
        result = categorize_transaction(
            description=desc,
            existing_category_id=cat_id,
            user_id=user_id,
        )
        result["original_description"] = desc
        results.append(result)
    return results
