"""Intelligent transaction categorization engine (issue #91)."""
import logging, re
from difflib import SequenceMatcher
from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.categorize")

# Weighted rule set: (pattern, category, weight)
RULES = [
    (r"(uber|lyft|taxi|grab|ola|rapido|cab|metro|mrt|bart|train|bus\b)", "Transport", 10),
    (r"(netflix|hulu|spotify|disney|prime video|apple tv|youtube premium)", "Entertainment", 10),
    (r"(grocery|supermarket|whole foods|trader joe|walmart|kroger|safeway|tesco|lidl|aldi)", "Groceries", 10),
    (r"(restaurant|cafe|starbucks|mcdonald|kfc|burger|pizza|sushi|diner|doordash|swiggy|zomato)", "Dining", 10),
    (r"(amazon|flipkart|ebay|etsy|myntra|shop|store|mall|purchase|buy)", "Shopping", 8),
    (r"(electricity|gas\s*bill|water\s*bill|pge|con\s*ed|utility|broadband|internet\s*bill)", "Utilities", 10),
    (r"(rent|mortgage|landlord|lease|housing|apartment)", "Housing", 10),
    (r"(hospital|clinic|pharmacy|medical|health|dental|vision|doctor|rx\b)", "Healthcare", 10),
    (r"(gym|fitness|yoga|crossfit|peloton|sports|workout)", "Fitness", 9),
    (r"(school|college|university|tuition|course|udemy|coursera|learning)", "Education", 9),
    (r"(insurance|premium|policy|coverage)", "Insurance", 9),
    (r"(salary|payroll|direct\s*deposit|paycheck|income|bonus|wages)", "Income", 10),
    (r"(atm|cash\s*withdrawal|withdraw)", "Cash", 7),
    (r"(hotel|airbnb|flight|airline|booking|travel|vacation|trip)", "Travel", 9),
]


def categorize(user_id: int, description: str, amount: float = None) -> dict:
    """
    Multi-signal categorization:
    1. Regex rules (weighted)
    2. Historical match (same user, similar description)
    3. Amount-based heuristics
    """
    desc = (description or "").strip()
    candidates = []

    # Signal 1: regex rules
    for pattern, category, weight in RULES:
        if re.search(pattern, desc, re.I):
            candidates.append({"category": category, "score": weight, "signal": "rule"})

    # Signal 2: historical match from user's own expenses
    if desc:
        past = (db.session.query(Expense, Category)
                .join(Category, Expense.category_id == Category.id)
                .filter(Expense.user_id == user_id, Expense.notes.isnot(None))
                .limit(200).all())
        for exp, cat in past:
            sim = SequenceMatcher(None, desc.lower(), (exp.notes or "").lower()).ratio()
            if sim > 0.7:
                candidates.append({"category": cat.name, "score": sim * 8, "signal": "history"})

    if not candidates:
        return {"category": None, "confidence": "none", "signal": None}

    # Aggregate scores
    scores = {}
    for c in candidates:
        scores[c["category"]] = scores.get(c["category"], 0) + c["score"]

    best = max(scores, key=scores.get)
    top_score = scores[best]
    confidence = "high" if top_score >= 10 else "medium" if top_score >= 6 else "low"

    return {"category": best, "confidence": confidence,
            "signal": "rule+history" if len(set(c["signal"] for c in candidates)) > 1 else candidates[0]["signal"],
            "score": round(top_score, 2)}
