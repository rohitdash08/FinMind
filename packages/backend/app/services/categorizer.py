"""Intelligent transaction categorization engine."""
KEYWORD_MAP = {
    "grocery": "Groceries", "supermarket": "Groceries", "walmart": "Groceries", "costco": "Groceries",
    "restaurant": "Dining", "cafe": "Dining", "coffee": "Dining", "pizza": "Dining", "burger": "Dining",
    "uber": "Transport", "lyft": "Transport", "gas": "Transport", "fuel": "Transport", "parking": "Transport",
    "rent": "Housing", "mortgage": "Housing", "electric": "Utilities", "water": "Utilities", "internet": "Utilities",
    "netflix": "Entertainment", "spotify": "Entertainment", "movie": "Entertainment", "game": "Entertainment",
    "doctor": "Healthcare", "pharmacy": "Healthcare", "hospital": "Healthcare", "dental": "Healthcare",
    "amazon": "Shopping", "ebay": "Shopping", "mall": "Shopping",
    "salary": "Income", "freelance": "Income", "dividend": "Income", "bonus": "Income",
    "gym": "Fitness", "insurance": "Insurance", "school": "Education", "tuition": "Education",
}

def suggest_category(description):
    desc = (description or "").lower()
    for keyword, category in KEYWORD_MAP.items():
        if keyword in desc:
            return {"suggested_category": category, "confidence": 0.8, "matched_keyword": keyword}
    return {"suggested_category": None, "confidence": 0, "matched_keyword": None}

def bulk_categorize(expenses):
    results = []
    for e in expenses:
        s = suggest_category(e.get("description") or e.get("notes", ""))
        results.append({"expense_id": e.get("id"), "description": e.get("description") or e.get("notes"), **s})
    return results
