"""Rule-based auto tagging & categorization (issue #107)."""
import json, logging, re
from ..extensions import redis_client, db
from ..models import Category, Expense

logger = logging.getLogger("finmind.tagger")
RULES_KEY = "autotag:rules:"
TTL = 60 * 60 * 24 * 365

DEFAULT_RULES = [
    {"pattern": r"(uber|lyft|taxi|cab|metro|transit|bart|mta|train|bus)", "category": "Transport"},
    {"pattern": r"(netflix|hulu|spotify|disney|youtube premium|prime video)", "category": "Entertainment"},
    {"pattern": r"(walmart|target|costco|whole foods|trader joe|kroger|safeway|grocery|supermarket)", "category": "Groceries"},
    {"pattern": r"(restaurant|cafe|starbucks|mcdonald|burger|pizza|sushi|dining|doordash|uber eat)", "category": "Dining"},
    {"pattern": r"(amazon|ebay|etsy|shop|store|purchase)", "category": "Shopping"},
    {"pattern": r"(electric|gas bill|water|utilities|pge|con ed|utility)", "category": "Utilities"},
    {"pattern": r"(rent|mortgage|landlord|lease)", "category": "Housing"},
    {"pattern": r"(doctor|hospital|pharmacy|medical|health|dental|vision)", "category": "Healthcare"},
    {"pattern": r"(gym|fitness|yoga|crossfit|peloton)", "category": "Fitness"},
    {"pattern": r"(salary|payroll|direct deposit|paycheck|income)", "category": "Income"},
]


def _rules_key(user_id): return f"{RULES_KEY}{user_id}"


def get_rules(user_id: int) -> list:
    raw = redis_client.get(_rules_key(user_id))
    return json.loads(raw) if raw else DEFAULT_RULES[:]


def add_rule(user_id: int, pattern: str, category: str):
    rules = get_rules(user_id)
    rules.insert(0, {"pattern": pattern, "category": category, "custom": True})
    redis_client.setex(_rules_key(user_id), TTL, json.dumps(rules))


def suggest_category(user_id: int, description: str) -> dict | None:
    rules = get_rules(user_id)
    desc = (description or "").lower()
    for rule in rules:
        if re.search(rule["pattern"], desc, re.I):
            return {"category": rule["category"], "pattern": rule["pattern"],
                    "confidence": "high" if rule.get("custom") else "medium"}
    return None


def auto_tag_expenses(user_id: int, dry_run: bool = True) -> dict:
    """Apply rules to all uncategorized expenses."""
    uncategorized = (db.session.query(Expense)
                     .filter(Expense.user_id == user_id, Expense.category_id.is_(None))
                     .all())
    tagged, skipped = [], []
    for e in uncategorized:
        suggestion = suggest_category(user_id, e.notes or "")
        if suggestion:
            cat = db.session.query(Category).filter_by(
                user_id=user_id, name=suggestion["category"]).first()
            if not cat and not dry_run:
                cat = Category(user_id=user_id, name=suggestion["category"])
                db.session.add(cat); db.session.flush()
            if not dry_run and cat:
                e.category_id = cat.id
            tagged.append({"expense_id": e.id, "suggested_category": suggestion["category"],
                           "description": e.notes, "applied": not dry_run})
        else:
            skipped.append(e.id)
    if not dry_run: db.session.commit()
    return {"tagged": len(tagged), "skipped": len(skipped),
            "dry_run": dry_run, "results": tagged}
