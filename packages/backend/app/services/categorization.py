import logging
import re
from collections import defaultdict
from typing import Optional

from ..extensions import db
from ..models import Category, CategoryRule, Expense

logger = logging.getLogger("finmind.categorization")

# Built-in keyword rules as fallback (rule-based fallback)
DEFAULT_KEYWORD_MAP: dict[str, list[str]] = {
    "Food & Dining": [
        "restaurant", "cafe", "coffee", "pizza", "burger", "sushi", "swiggy",
        "zomato", "uber eats", "food", "dining", "lunch", "dinner", "breakfast",
        "canteen", "hotel", "bistro", "dine",
    ],
    "Transport": [
        "uber", "ola", "taxi", "cab", "bus", "metro", "train", "flight",
        "airport", "fuel", "petrol", "diesel", "toll", "parking", "auto",
    ],
    "Groceries": [
        "grocery", "supermarket", "bigbasket", "blinkit", "zepto", "dmart",
        "reliance fresh", "more supermarket", "vegetables", "fruits",
    ],
    "Utilities": [
        "electricity", "water bill", "gas bill", "internet", "broadband",
        "wifi", "mobile recharge", "jio", "airtel", "bsnl",
    ],
    "Health": [
        "hospital", "clinic", "pharmacy", "medicine", "doctor", "apollo",
        "medplus", "1mg", "netmeds", "diagnostic", "lab test", "health",
    ],
    "Entertainment": [
        "netflix", "amazon prime", "hotstar", "spotify", "youtube premium",
        "movie", "cinema", "pvr", "inox", "concert", "event", "game",
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "nykaa", "meesho", "clothes",
        "fashion", "shopping", "mall", "store", "purchase",
    ],
    "Education": [
        "course", "udemy", "coursera", "book", "college", "university",
        "school", "tuition", "coaching", "exam", "certification",
    ],
    "Finance": [
        "emi", "loan", "insurance", "premium", "mutual fund", "investment",
        "sip", "tax", "credit card", "bank charge",
    ],
}


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation for comparison."""
    return re.sub(r"[^\w\s]", " ", text.lower()).strip()


def _match_keywords(note: str, keyword_map: dict[str, list[str]]) -> Optional[str]:
    """Return category name if note matches any keyword, else None."""
    norm = _normalize(note)
    for category_name, keywords in keyword_map.items():
        for kw in keywords:
            if kw in norm:
                return category_name
    return None


def categorize_note(uid: int, note: str, amount: Optional[float] = None) -> dict:
    """
    Attempt to categorize a transaction note using a 3-tier strategy:

    1. User-defined CategoryRule patterns (highest priority, confidence 0.9-1.0)
    2. Frequency-based learning from expense history (confidence 0.5-0.85)
    3. Built-in keyword fallback (confidence 0.5-0.6)

    Returns:
        {
            "category_id": int | None,
            "category_name": str | None,
            "confidence": float,  # 0.0-1.0
            "method": "user_rule" | "learned" | "keyword" | "none"
        }
    """
    if not note or not note.strip():
        return {"category_id": None, "category_name": None, "confidence": 0.0, "method": "none"}

    norm_note = _normalize(note)

    # Tier 1: User-defined rules
    user_rules = (
        db.session.query(CategoryRule)
        .filter_by(user_id=uid, active=True)
        .order_by(CategoryRule.priority.desc())
        .all()
    )
    for rule in user_rules:
        pattern = _normalize(rule.pattern)
        matched = False
        if rule.match_type == "exact":
            matched = norm_note == pattern
            conf = 1.0
        elif rule.match_type == "contains":
            matched = pattern in norm_note
            conf = 0.95
        elif rule.match_type == "regex":
            try:
                matched = bool(re.search(rule.pattern, note, re.IGNORECASE))
                conf = 0.9
            except re.error:
                matched = False
                conf = 0.0

        if matched:
            cat = db.session.get(Category, rule.category_id)
            if cat:
                return {
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "confidence": conf,
                    "method": "user_rule",
                }

    # Tier 2: Frequency-based learning
    words = [w for w in norm_note.split() if len(w) > 2]
    if words:
        freq: dict[int, int] = defaultdict(int)
        past_expenses = (
            db.session.query(Expense.category_id, Expense.notes)
            .filter(
                Expense.user_id == uid,
                Expense.category_id.isnot(None),
                Expense.notes.isnot(None),
            )
            .all()
        )
        for exp_cat, exp_note in past_expenses:
            if not exp_note:
                continue
            exp_norm = _normalize(exp_note)
            matched_words = sum(1 for w in words if w in exp_norm)
            if matched_words > 0:
                freq[exp_cat] += matched_words

        if freq:
            best_cat_id = max(freq, key=freq.__getitem__)
            best_count = freq[best_cat_id]
            total = sum(freq.values())
            confidence = min(0.85, 0.5 + (best_count / total) * 0.35)
            cat = db.session.get(Category, best_cat_id)
            if cat:
                return {
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "confidence": round(confidence, 2),
                    "method": "learned",
                }

    # Tier 3: Built-in keyword fallback
    matched_builtin = _match_keywords(note, DEFAULT_KEYWORD_MAP)
    if matched_builtin:
        user_cats = db.session.query(Category).filter_by(user_id=uid).all()
        for cat in user_cats:
            if matched_builtin.lower() in cat.name.lower() or cat.name.lower() in matched_builtin.lower():
                return {
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "confidence": 0.6,
                    "method": "keyword",
                }
        return {
            "category_id": None,
            "category_name": matched_builtin,
            "confidence": 0.5,
            "method": "keyword",
        }

    return {"category_id": None, "category_name": None, "confidence": 0.0, "method": "none"}


def apply_correction(uid: int, expense_id: int, correct_category_id: int) -> bool:
    """
    Record a user correction and auto-generate a rule to learn from it.
    Returns True if a new rule was created.
    """
    expense = db.session.get(Expense, expense_id)
    if not expense or expense.user_id != uid:
        return False

    expense.category_id = correct_category_id
    db.session.commit()

    if expense.notes and expense.notes.strip():
        existing = (
            db.session.query(CategoryRule)
            .filter_by(
                user_id=uid,
                category_id=correct_category_id,
                match_type="contains",
                pattern=expense.notes.strip().lower(),
            )
            .first()
        )
        if not existing:
            rule = CategoryRule(
                user_id=uid,
                category_id=correct_category_id,
                pattern=expense.notes.strip().lower(),
                match_type="contains",
                priority=5,
                active=True,
                auto_generated=True,
            )
            db.session.add(rule)
            db.session.commit()
            logger.info("Auto-created rule from correction expense_id=%s", expense_id)
            return True

    return False


def bulk_categorize(uid: int, expense_ids: list[int]) -> list[dict]:
    """Suggest and apply categories for multiple uncategorized expenses."""
    results = []
    expenses = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid, Expense.id.in_(expense_ids))
        .all()
    )
    for expense in expenses:
        if expense.category_id is not None:
            results.append({
                "expense_id": expense.id,
                "already_categorized": True,
                "category_id": expense.category_id,
            })
            continue
        suggestion = categorize_note(uid, expense.notes or "", float(expense.amount))
        if suggestion["category_id"] and suggestion["confidence"] >= 0.7:
            expense.category_id = suggestion["category_id"]
            db.session.commit()
            suggestion["expense_id"] = expense.id
            suggestion["applied"] = True
        else:
            suggestion["expense_id"] = expense.id
            suggestion["applied"] = False
        results.append(suggestion)
    return results

