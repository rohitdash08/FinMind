"""
Intelligent Transaction Categorization Engine.

Strategy (in order of precedence):
1. Learned corrections – exact normalized-description match (confidence: high)
2. User-defined rules  – keyword / merchant / amount_range (confidence: high)
3. Built-in keyword map – broad keyword matching (confidence: medium)
4. Amount-based heuristics – e.g. very small → likely transport/food (confidence: low)
5. Fallback → None / "Other"
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Optional

from ..extensions import db
from ..models import Category, CategoryRule, CategorizationCorrection, Expense

logger = logging.getLogger("finmind.categorization")

# ---------------------------------------------------------------------------
# Built-in keyword → category-name map
# ---------------------------------------------------------------------------
DEFAULT_KEYWORD_MAP: dict[str, list[str]] = {
    "Food": [
        "uber eats",
        "ubereats",
        "zomato",
        "swiggy",
        "doordash",
        "grubhub",
        "restaurant",
        "cafe",
        "coffee",
        "starbucks",
        "mcdonald",
        "mcdonalds",
        "kfc",
        "pizza",
        "burger",
        "subway",
        "dominos",
        "domino",
        "bakery",
        "grocery",
        "groceries",
        "supermarket",
        "walmart",
        "target",
        "whole foods",
        "trader joe",
        "food",
        "eat",
        "meal",
        "lunch",
        "dinner",
        "breakfast",
        "snack",
        "sushi",
        "bistro",
        "brasserie",
        "traiteur",
        "epicerie",
        "boulangerie",
        "lidl",
        "aldi",
        "carrefour",
        "leclerc",
        "monoprix",
        "franprix",
        "intermarche",
    ],
    "Transport": [
        "uber",
        "lyft",
        "ola",
        "rapido",
        "taxi",
        "cab",
        "autorickshaw",
        "metro",
        "bus",
        "train",
        "irctc",
        "railway",
        "flight",
        "airline",
        "airways",
        "indigo",
        "spicejet",
        "air india",
        "sncf",
        "ratp",
        "blablacar",
        "petrol",
        "diesel",
        "fuel",
        "parking",
        "toll",
        "fastag",
        "ola cabs",
        "redbus",
        "transport",
        "travel",
        "transit",
        "ticket",
        "billeterie",
        "navigo",
    ],
    "Entertainment": [
        "netflix",
        "spotify",
        "amazon prime",
        "prime video",
        "disney",
        "hotstar",
        "hulu",
        "youtube premium",
        "apple tv",
        "game",
        "gaming",
        "steam",
        "playstation",
        "xbox",
        "nintendo",
        "cinema",
        "movie",
        "theatre",
        "concert",
        "event",
        "ticket",
        "bookmyshow",
        "pathe",
        "ugc",
        "fnac",
        "entertainment",
        "twitch",
        "deezer",
        "canal+",
    ],
    "Bills": [
        "electricity",
        "water",
        "gas",
        "internet",
        "broadband",
        "wifi",
        "phone",
        "mobile",
        "jio",
        "airtel",
        "vi ",
        "vodafone",
        "bsnl",
        "rent",
        "emi",
        "insurance",
        "premium",
        "tax",
        "utility",
        "bill",
        "recharge",
        "dth",
        "tata sky",
        "cable",
        "sfr",
        "orange",
        "bouygues",
        "free mobile",
        "edf",
        "engie",
        "loyer",
    ],
    "Shopping": [
        "amazon",
        "flipkart",
        "myntra",
        "ajio",
        "nykaa",
        "meesho",
        "ebay",
        "aliexpress",
        "clothing",
        "clothes",
        "fashion",
        "shoes",
        "footwear",
        "electronics",
        "mobile",
        "laptop",
        "gadget",
        "accessories",
        "shop",
        "store",
        "mall",
        "retail",
        "zara",
        "h&m",
        "uniqlo",
        "nike",
        "adidas",
        "fnac",
        "darty",
        "cdiscount",
        "rakuten",
    ],
    "Health": [
        "pharmacy",
        "chemist",
        "medicine",
        "doctor",
        "hospital",
        "clinic",
        "lab",
        "diagnostic",
        "health",
        "gym",
        "fitness",
        "yoga",
        "medic",
        "pharma",
        "drug",
        "dental",
        "optician",
        "pharmacie",
        "medecin",
        "hopital",
        "sante",
    ],
    "Education": [
        "udemy",
        "coursera",
        "edx",
        "skillshare",
        "linkedin learning",
        "byju",
        "unacademy",
        "school",
        "college",
        "university",
        "tuition",
        "course",
        "education",
        "book",
        "library",
        "stationery",
        "pen",
        "notebook",
        "formation",
        "ecole",
        "universite",
    ],
    "Income": [
        "salary",
        "salaire",
        "payroll",
        "dividend",
        "interest",
        "credit",
        "refund",
        "cashback",
        "reward",
        "freelance",
        "invoice",
        "payment received",
        "transfer in",
        "deposit",
        "virement recu",
        "remboursement",
    ],
    "Transfer": [
        "transfer",
        "neft",
        "rtgs",
        "imps",
        "upi",
        "paytm",
        "phonepe",
        "google pay",
        "gpay",
        "bhim",
        "wire",
        "swift",
        "virement",
        "revolut",
        "wise",
        "paypal",
        "bank",
    ],
}

# Confidence levels
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


def _normalize(text: str) -> str:
    """Lowercase, strip extra spaces, remove special chars for matching."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _find_or_create_default_category(user_id: int, name: str) -> Optional[Category]:
    """Return existing category by name or create it for the user."""
    cat = (
        db.session.query(Category)
        .filter_by(user_id=user_id, name=name)
        .first()
    )
    if cat is None:
        cat = Category(user_id=user_id, name=name)
        db.session.add(cat)
        db.session.flush()  # get id without full commit
    return cat


def _builtin_keyword_match(
    normalized_desc: str, user_id: int
) -> tuple[Optional[Category], str]:
    """Match description against built-in keyword map."""
    for category_name, keywords in DEFAULT_KEYWORD_MAP.items():
        for kw in keywords:
            if kw in normalized_desc:
                cat = _find_or_create_default_category(user_id, category_name)
                return cat, CONFIDENCE_MEDIUM
    return None, CONFIDENCE_LOW


def categorize_expense(
    user_id: int,
    description: str,
    amount: Optional[Decimal] = None,
) -> dict:
    """
    Categorize a single transaction.

    Returns:
        {
            "category_id": int | None,
            "category_name": str | None,
            "confidence": "high" | "medium" | "low",
            "method": str,
        }
    """
    normalized = _normalize(description)

    # 1. Learned corrections (exact normalized match)
    correction = (
        db.session.query(CategorizationCorrection)
        .filter_by(user_id=user_id, description_normalized=normalized)
        .order_by(CategorizationCorrection.created_at.desc())
        .first()
    )
    if correction:
        cat = db.session.get(Category, correction.category_id)
        if cat:
            logger.debug(
                "Categorized via learned correction: desc=%r cat=%s", description, cat.name
            )
            return {
                "category_id": cat.id,
                "category_name": cat.name,
                "confidence": CONFIDENCE_HIGH,
                "method": "learned",
            }

    # 2. User-defined rules (keyword / merchant / amount_range), sorted by priority desc
    rules = (
        db.session.query(CategoryRule)
        .filter_by(user_id=user_id)
        .order_by(CategoryRule.priority.desc())
        .all()
    )
    for rule in rules:
        cat = db.session.get(Category, rule.category_id)
        if not cat:
            continue
        if rule.rule_type in ("keyword", "merchant"):
            pattern = _normalize(rule.pattern or "")
            if pattern and pattern in normalized:
                logger.debug(
                    "Categorized via user rule id=%s: desc=%r cat=%s",
                    rule.id,
                    description,
                    cat.name,
                )
                return {
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "confidence": CONFIDENCE_HIGH,
                    "method": f"rule:{rule.id}",
                }
        elif rule.rule_type == "amount_range" and amount is not None:
            lo = rule.amount_min or Decimal("0")
            hi = rule.amount_max
            if amount >= lo and (hi is None or amount <= hi):
                logger.debug(
                    "Categorized via amount rule id=%s: amount=%s cat=%s",
                    rule.id,
                    amount,
                    cat.name,
                )
                return {
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "confidence": CONFIDENCE_MEDIUM,
                    "method": f"rule:{rule.id}",
                }

    # 3. Built-in keyword map
    cat, confidence = _builtin_keyword_match(normalized, user_id)
    if cat:
        db.session.commit()  # persist any auto-created categories
        return {
            "category_id": cat.id,
            "category_name": cat.name,
            "confidence": confidence,
            "method": "builtin_keyword",
        }

    # 4. Amount-based heuristics (very rough fallback)
    if amount is not None:
        if amount < Decimal("100"):
            cat = _find_or_create_default_category(user_id, "Food")
            db.session.commit()
            return {
                "category_id": cat.id,
                "category_name": cat.name,
                "confidence": CONFIDENCE_LOW,
                "method": "amount_heuristic",
            }

    # 5. Return "Other" fallback
    cat = _find_or_create_default_category(user_id, "Other")
    db.session.commit()
    return {
        "category_id": cat.id,
        "category_name": cat.name,
        "confidence": CONFIDENCE_LOW,
        "method": "fallback",
    }


def record_correction(
    user_id: int, expense_id: Optional[int], description: str, category_id: int
) -> None:
    """
    Store a user correction and upsert a learned CategoryRule so future
    transactions with the same normalized description get the right category.
    """
    normalized = _normalize(description)

    # Store the correction record
    correction = CategorizationCorrection(
        user_id=user_id,
        expense_id=expense_id,
        description_normalized=normalized,
        category_id=category_id,
    )
    db.session.add(correction)

    # Also upsert a high-priority learned rule
    existing_rule = (
        db.session.query(CategoryRule)
        .filter_by(user_id=user_id, rule_type="learned", pattern=normalized)
        .first()
    )
    if existing_rule:
        existing_rule.category_id = category_id
    else:
        rule = CategoryRule(
            user_id=user_id,
            category_id=category_id,
            rule_type="learned",
            pattern=normalized,
            priority=100,  # highest priority
        )
        db.session.add(rule)

    db.session.commit()
    logger.info(
        "Recorded correction user=%s expense=%s desc=%r cat=%s",
        user_id,
        expense_id,
        description,
        category_id,
    )
